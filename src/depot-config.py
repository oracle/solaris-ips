#!/usr/bin/python2.6
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

#
# Copyright (c) 2013, Oracle and/or its affiliates. All rights reserved.
#

import errno
import getopt
import gettext
import locale
import logging
import os
import re
import shutil
import socket
import sys
import traceback
import warnings

from mako.template import Template
from mako.lookup import TemplateLookup

import pkg
import pkg.client.api_errors as apx
import pkg.catalog
import pkg.config as cfg
import pkg.misc as misc
import pkg.portable as portable
import pkg.p5i as p5i
import pkg.server.repository as sr
import pkg.smf as smf

from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues
from pkg.misc import msg, PipeError

logger = global_settings.logger

# exit codes
EXIT_OK      = 0
EXIT_OOPS    = 1
EXIT_BADOPT  = 2

DEPOT_HTTP_TEMPLATE = "depot_httpd.conf.mako"
DEPOT_FRAGMENT_TEMPLATE = "depot.conf.mako"

DEPOT_HTTP_FILENAME = "depot_httpd.conf"
DEPOT_FRAGMENT_FILENAME= "depot.conf"

DEPOT_PUB_FILENAME = "index.html"
DEPOT_HTDOCS_DIRNAME = "htdocs"

DEPOT_VERSIONS_DIRNAME = ["versions", "0"]
DEPOT_PUB_DIRNAME = ["publisher", "1"]

DEPOT_CACHE_FILENAME = "depot.cache"

KNOWN_SERVER_TYPES = ["apache2"]

PKG_SERVER_SVC = "svc:/application/pkg/server"

# static string with our versions response
DEPOT_FRAGMENT_VERSIONS_STR = """\
pkg-server %s
publisher 0 1
versions 0
catalog 1
file 1
manifest 0
""" % pkg.VERSION

# versions response used when we provide search capability
DEPOT_VERSIONS_STR = """%sadmin 0
search 0 1
""" % DEPOT_FRAGMENT_VERSIONS_STR

DEPOT_USER = "pkg5srv"
DEPOT_GROUP = "pkg5srv"

class DepotException(Exception):
        def __unicode__(self):
        # To workaround python issues 6108 and 2517, this provides a
        # a standard wrapper for this class' exceptions so that they
        # have a chance of being stringified correctly.
                return str(self)


def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if cmd:
                text = "%s: %s" % (cmd, text)
                pkg_cmd = "pkg.depot-config "
        else:
                pkg_cmd = "pkg.depot-config: "

                # If we get passed something like an Exception, we can convert
                # it down to a string.
                text = str(text)

        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        logger.error(ws + pkg_cmd + text_nows)

def usage(usage_error=None, cmd=None, retcode=EXIT_BADOPT):
        """Emit a usage message and optionally prefix it with a more
        specific error message.  Causes program to exit.
        """

        if usage_error:
                error(usage_error, cmd=cmd)
        msg(_("""\
Usage:
        pkg.depot-config ( -d repository_dir | -S ) -r runtime_dir
                [-c cache_dir] [-s cache_size] [-p port] [-h hostname]
                [-l logs_dir] [-T template_dir] [-A]
                [-t server_type] ( [-F] [-P server_prefix] )
"""))
        sys.exit(retcode)

def _chown_dir(dir):
        """Sets ownership for the given directory to pkg5srv:pkg5srv"""

        uid = portable.get_user_by_name(DEPOT_USER, None, False)
        gid = portable.get_group_by_name(DEPOT_GROUP, None, False)
        try:
                os.chown(dir, uid, gid)
        except OSError, err:
                if not os.environ.get("PKG5_TEST_ENV", None):
                        raise DepotException(_("Unable to chown %(dir)s to "
                            "%(user)s:%(group)s: %(err)s") %
                            {"dir": dir, "user": DEPOT_USER,
                            "group": DEPOT_GROUP, "err": err})

def _get_publishers(root):
        """Given a repository root, return the list of available publishers,
        along with the default publisher/prefix."""

        try:
                # we don't set writable_root, as we don't want to take the hit
                # on potentially building an index here.
                repository = sr.Repository(root=root, read_only=True)

                if repository.version != 4:
                        raise DepotException(
                            _("pkg.depot-config only supports v4 repositories"))
        except Exception, e:
                raise DepotException(e)

        all_pubs = [pub.prefix for pub in repository.get_publishers()]
        try:
                default_pub = repository.cfg.get_property("publisher", "prefix")
        except cfg.UnknownPropertyError:
                default_pub = None
        return all_pubs, default_pub

def _write_httpd_conf(pubs, default_pubs, runtime_dir, log_dir, template_dir,
        cache_dir, cache_size, host, port, sroot,
        fragment=False, allow_refresh=False):
        """Writes the webserver configuration for the depot.

        pubs            repository and publisher information, a list in the form
                        [(publisher_prefix, repo_dir, repo_prefix), ... ]
        default_pubs    default publishers, per repository, a list in the form
                        [(default_publisher_prefix, repo_dir, repo_prefix) ... ]

        runtime_dir     where we write httpd.conf files
        log_dir         where Apache should write its log files
        template_dir    where we find our Mako templates
        cache_dir       where Apache should write its cache and wsgi search idx
        cache_size      how large our cache can grow
        host            our hostname, needed to set ServerName properly
        port            the port on which Apache should listen
        sroot           the prefix into the server namespace,
                        ignored if fragment==False
        fragment        True if we should only write a file to drop into conf.d/
                        (i.e. a partial server configuration)

        allow_refresh   True if we allow the 'refresh' or 'refresh-indexes'
                        admin/0 operations

        The URI namespace we create on the web server looks like this:

        <sroot>/<repo_prefix>/<publisher>/<file, catalog etc.>/<version>/
        <sroot>/<repo_prefix>/<file, catalog etc.>/<version>/

        'sroot' is only used when the Apache server is serving other content
        and we want to separate pkg(5) resources from the other resources
        provided.

        'repo_prefix' exists so that we can disambiguate between multiple
        repositories that provide the same publisher.
        """

        try:
                # check our hostname
                socket.getaddrinfo(host, None)

                # Apache needs IPv6 addresses wrapped in square brackets
                if ":" in host:
                        host = "[%s]" % host

                # check our directories
                dirs = [runtime_dir]
                if not fragment:
                        dirs.append(log_dir)
                if cache_dir:
                        dirs.append(cache_dir)
                for dir in dirs + [template_dir]:
                        if os.path.exists(dir) and not os.path.isdir(dir):
                                raise DepotException(
                                    _("%s is not a directory") % dir)

                for dir in dirs:
                        misc.makedirs(dir)

                # check our port
                if not fragment:
                        try:
                                num = int(port)
                                if num <= 0 or num >= 65535:
                                        raise DepotException(
                                            _("invalid port: %s") % port)
                        except ValueError:
                                raise DepotException(_("invalid port: %s") %
                                    port)

                # check our cache size
                try:
                        num = int(cache_size)
                        if num < 0:
                                raise DepotException(_("invalid cache size: "
                                   "%s") % num)
                except ValueError:
                        raise DepotException(_("invalid cache size: %s") %
                            cache_size)

                httpd_conf_template_path = os.path.join(template_dir,
                    DEPOT_HTTP_TEMPLATE)
                fragment_conf_template_path = os.path.join(template_dir,
                    DEPOT_FRAGMENT_TEMPLATE)

                # we're disabling unicode here because we want Mako to
                # passthrough any filesystem path names, whatever the
                # original encoding.
                conf_lookup = TemplateLookup(directories=[template_dir])
                if fragment:
                        conf_template = Template(
                            filename=fragment_conf_template_path,
                            disable_unicode=True, lookup=conf_lookup)
                        conf_path = os.path.join(runtime_dir,
                            DEPOT_FRAGMENT_FILENAME)
                else:
                        conf_template = Template(
                            filename=httpd_conf_template_path,
                            disable_unicode=True, lookup=conf_lookup)
                        conf_path = os.path.join(runtime_dir,
                            DEPOT_HTTP_FILENAME)

                conf_text = conf_template.render(
                    pubs=pubs,
                    default_pubs=default_pubs,
                    log_dir=log_dir,
                    cache_dir=cache_dir,
                    cache_size=cache_size,
                    runtime_dir=runtime_dir,
                    template_dir=template_dir,
                    ipv6_addr="::1",
                    host=host,
                    port=port,
                    sroot=sroot,
                    allow_refresh=allow_refresh
                )

                with file(conf_path, "wb") as conf_file:
                        conf_file.write(conf_text)

        except socket.gaierror, err:
                raise DepotException(
                    _("Unable to write Apache configuration: %(host)s: "
                    "%(err)s") % locals())
        except (OSError, IOError, EnvironmentError, apx.ApiException), err:
                traceback.print_exc(err)
                raise DepotException(
                    _("Unable to write depot_httpd.conf: %s") % err)

def _write_versions_response(htdocs_path, fragment=False):
        """Writes a static versions/0 response for the Apache depot."""

        try:
                versions_path = os.path.join(htdocs_path,
                    *DEPOT_VERSIONS_DIRNAME)
                misc.makedirs(versions_path)

                with file(os.path.join(versions_path, "index.html"), "w") as \
                    versions_file:
                        versions_file.write(
                            fragment and DEPOT_FRAGMENT_VERSIONS_STR or
                            DEPOT_VERSIONS_STR)

                versions_file.close()
        except (OSError, apx.ApiException), err:
                raise DepotException(
                    _("Unable to write versions response: %s") % err)

def _write_publisher_response(pubs, htdocs_path, repo_prefix):
        """Writes a static publisher/0 response for the depot."""
        try:
                # convert our list of strings to a list of Publishers
                pub_objs = [pkg.client.publisher.Publisher(pub) for pub in pubs]

                # write individual reponses for the publishers
                for pub in pub_objs:
                        pub_path = os.path.join(htdocs_path,
                            os.path.sep.join(
                               [repo_prefix, pub.prefix] + DEPOT_PUB_DIRNAME))
                        misc.makedirs(pub_path)
                        with file(os.path.join(pub_path, "index.html"), "w") as\
                            pub_file:
                                p5i.write(pub_file, [pub])

                # write a response that contains all publishers
                pub_path = os.path.join(htdocs_path,
                    os.path.sep.join([repo_prefix] + DEPOT_PUB_DIRNAME))
                os.makedirs(pub_path)
                with file(os.path.join(pub_path, "index.html"), "w") as \
                    pub_file:
                        p5i.write(pub_file, pub_objs)

        except (OSError, apx.ApiException), err:
                raise DepotException(
                    _("Unable to write publisher response: %s") % err)

def cleanup_htdocs(htdocs_dir):
        """Destroy any existing "htdocs" directory."""
        try:
                shutil.rmtree(htdocs_dir, ignore_errors=True)
        except OSError, err:
                raise DepotException(
                    _("Unable to remove an existing 'htdocs' directory "
                    "in the runtime directory: %s") % err)

def refresh_conf(repo_info, log_dir, host, port, runtime_dir,
            template_dir, cache_dir, cache_size, sroot, fragment=False,
            allow_refresh=False):
        """Creates a new configuration for the depot."""
        try:
                ret = EXIT_OK
                if not repo_info:
                        raise DepotException(_("no repositories found"))

                htdocs_path = os.path.join(runtime_dir, DEPOT_HTDOCS_DIRNAME,
                    sroot)
                cleanup_htdocs(htdocs_path)
                misc.makedirs(htdocs_path)

                # pubs and default_pubs are lists of tuples of the form:
                # (publisher prefix, repository root dir, repository prefix)
                pubs = []
                default_pubs = []

                repo_prefixes = [prefix for root, prefix in repo_info]
                errors = []

                # Query each repository for its publisher information.
                for (repo_root, repo_prefix) in repo_info:
                        try:
                                publishers, default_pub = \
                                    _get_publishers(repo_root)
                                for pub in publishers:
                                        pubs.append(
                                            (pub, repo_root,
                                            repo_prefix))
                                default_pubs.append((default_pub,
                                    repo_root, repo_prefix))

                        except DepotException, err:
                                errors.append(str(err))
                if errors:
                        raise DepotException(_("Unable to get publisher "
                            "information: %s") % "\n".join(errors))

                # Write the publisher/0 response for each repository
                pubs_by_repo = {}
                for pub_prefix, repo_root, repo_prefix in pubs:
                        pubs_by_repo.setdefault(repo_prefix, []).append(
                            pub_prefix)
                for repo_prefix in pubs_by_repo:
                        _write_publisher_response(
                            pubs_by_repo[repo_prefix], htdocs_path, repo_prefix)

                _write_httpd_conf(pubs, default_pubs, runtime_dir, log_dir,
                    template_dir, cache_dir, cache_size, host, port, sroot,
                    fragment=fragment, allow_refresh=allow_refresh)
                _write_versions_response(htdocs_path, fragment=fragment)
                # If we're writing a configuration fragment, then the web server
                # is probably not running as DEPOT_USER:DEPOT_GROUP
                if not fragment:
                        _chown_dir(runtime_dir)
                        _chown_dir(cache_dir)
                else:
                        msg(_("Created %s/depot.conf") % runtime_dir)
        except (DepotException, OSError, apx.ApiException), err:
                error(err)
                ret = EXIT_OOPS
        return ret

def get_smf_repo_info():
        """Return a list of repo_info from the online instances of pkg/server
        which are marked as pkg/standalone = False and pkg/readonly = True."""

        smf_instances = smf.check_fmris(None, "%s:*" % PKG_SERVER_SVC)
        repo_info = []
        for fmri in smf_instances:
                repo_prefix = fmri.split(":")[-1]
                repo_root = smf.get_prop(fmri, "pkg/inst_root")
                state = smf.get_prop(fmri, "restarter/state")
                readonly = smf.get_prop(fmri, "pkg/readonly")
                standalone = smf.get_prop(fmri, "pkg/standalone")

                if (state == "online" and
                    readonly == "true" and
                    standalone == "false"):
                        repo_info.append((repo_root,
                            _affix_slash(repo_prefix)))
        if not repo_info:
                raise DepotException(_(
                    "No online, readonly, non-standalone instances of "
                    "%s found.") % PKG_SERVER_SVC)
        return repo_info

def _check_unique_repo_properties(repo_info):
        """Determine whether the repository root, and supplied prefixes are
        unique.  The prefixes allow two or more repositories that both contain
        the same publisher to be differentiated in the Apache configuration, so
        that requests are routed to the correct repository."""

        prefixes = set()
        roots = set()
        errors = []
        for root, prefix in repo_info:
                if prefix in prefixes:
                        errors.append(_("instance %s already exists") % prefix)
                prefixes.add(prefix)
                if root in roots:
                        errors.append(_("repo_root %s already exists") % root)
                roots.add(root)
        if errors:
                raise DepotException("\n".join(errors))
        return True

def _affix_slash(str):
        val = str.lstrip("/").rstrip("/")
        if "/" in str:
                raise DepotException(_("cannot use '/' chars in prefixes"))
        # An RE that matches valid SMF instance names works for prefixes
        if not re.match(r"^([A-Za-z][_A-Za-z0-9.-]*,)?[A-Za-z][_A-Za-z0-9-]*$",
            str):
                raise DepotException(_("%s is not a valid prefix"))
        return "%s/" % val

def main_func():

        # some sensible defaults
        host = "0.0.0.0"
        # the port we listen on
        port = None
        # a list of (repo_dir, repo_prefix) tuples
        repo_info = []
        # the path where we store indexes and disk caches
        cache_dir = None
        # our maximum cache size, in megabytes
        cache_size = 0
        # whether we're writing a full httpd.conf, or just a fragment
        fragment = False
        # an optional url-prefix, used to separate pkg5 services from the rest
        # of the webserver url namespace, only used when running in fragment
        # mode, otherwise we assume we're the only service running on this
        # web server instance, and control the entire server URL namespace.
        sroot = ""
        # the path where our Mako templates and wsgi scripts are stored
        template_dir = "/etc/pkg/depot"
        # a volatile directory used at runtime for storing state
        runtime_dir = None
        # where logs are written
        log_dir = "/var/log/pkg/depot"
        # whether we should pull configuration from
        # svc:/application/pkg/server instances
        use_smf_instances = False
        # whether we allow admin/0 operations to rebuild the index
        allow_refresh = False
        # the current server_type
        server_type = "apache2"

        try:
                opts, pargs = getopt.getopt(sys.argv[1:],
                    "Ac:d:Fh:l:P:p:r:Ss:t:T:?", ["help", "debug="])
                for opt, arg in opts:
                        if opt == "--help":
                                usage()
                        elif opt == "-h":
                                host = arg
                        elif opt == "-c":
                                cache_dir = arg
                        elif opt == "-s":
                                cache_size = arg
                        elif opt == "-l":
                                log_dir = arg
                        elif opt == "-p":
                                port = arg
                        elif opt == "-r":
                                runtime_dir = arg
                        elif opt == "-T":
                                template_dir = arg
                        elif opt == "-t":
                                server_type = arg
                        elif opt == "-d":
                                if "=" not in arg:
                                        usage(_("-d arguments must be in the "
                                            "form <prefix>=<repo path>"))
                                prefix, root = arg.split("=", 1)
                                repo_info.append((root, _affix_slash(prefix)))
                        elif opt == "-P":
                                sroot = _affix_slash(arg)
                        elif opt == "-F":
                                fragment = True
                        elif opt == "-S":
                                use_smf_instances = True
                        elif opt == "-A":
                                allow_refresh = True
                        elif opt == "--debug":
                                try:
                                        key, value = arg.split("=", 1)
                                except (AttributeError, ValueError):
                                        usage(
                                            _("%(opt)s takes argument of form "
                                            "name=value, not %(arg)s") % {
                                            "opt": opt, "arg": arg })
                                DebugValues.set_value(key, value)
                        else:
                                usage("unknown option %s" % opt)

        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        if not runtime_dir:
                usage(_("required runtime dir option -r missing."))

        # we need a cache_dir to store the search indexes
        if not cache_dir and not fragment:
                usage(_("cache_dir option -c is required if -F is not used."))

        if not fragment and not port:
                usage(_("required port option -p missing."))

        if not use_smf_instances and not repo_info:
                usage(_("at least one -d option is required if -S is "
                    "not used."))

        if repo_info and use_smf_instances:
                usage(_("cannot use -d and -S together."))

        if fragment and port:
                usage(_("cannot use -F and -p together."))

        if fragment and allow_refresh:
                usage(_("cannot use -F and -A together."))

        if sroot and not fragment:
                usage(_("cannot use -P without -F."))

        if use_smf_instances:
                try:
                        repo_info = get_smf_repo_info()
                except DepotException, e:
                        error(e)

        # In the future we may produce configuration for different
        # HTTP servers. For now, we only support "apache2"
        if server_type not in KNOWN_SERVER_TYPES:
                usage(_("unknown server type %(type)s. "
                    "Known types are: %(known)s") %
                    {"type": server_type,
                    "known": ", ".join(KNOWN_SERVER_TYPES)})

        _check_unique_repo_properties(repo_info)

        ret = refresh_conf(repo_info, log_dir, host, port, runtime_dir,
            template_dir, cache_dir, cache_size, sroot, fragment=fragment,
            allow_refresh=allow_refresh)
        return ret

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
def handle_errors(func, *args, **kwargs):
        """Catch exceptions raised by the main program function and then print
        a message and/or exit with an appropriate return code.
        """

        traceback_str = misc.get_traceback_message()

        try:
                # Out of memory errors can be raised as EnvironmentErrors with
                # an errno of ENOMEM, so in order to handle those exceptions
                # with other errnos, we nest this try block and have the outer
                # one handle the other instances.
                try:
                        __ret = func(*args, **kwargs)
                except (MemoryError, EnvironmentError), __e:
                        if isinstance(__e, EnvironmentError) and \
                            __e.errno != errno.ENOMEM:
                                raise
                        error("\n" + misc.out_of_memory())
                        __ret = EXIT_OOPS
        except SystemExit, __e:
                raise __e
        except (PipeError, KeyboardInterrupt):
                # Don't display any messages here to prevent possible further
                # broken pipe (EPIPE) errors.
                __ret = EXIT_OOPS
        except:
                traceback.print_exc()
                error(traceback_str)
                __ret = 99
        return __ret


if __name__ == "__main__":
        misc.setlocale(locale.LC_ALL, "", error)
        gettext.install("pkg", "/usr/share/locale",
            codeset=locale.getpreferredencoding())

        # Make all warnings be errors.
        warnings.simplefilter('error')

        __retval = handle_errors(main_func)
        try:
                logging.shutdown()
        except IOError:
                # Ignore python's spurious pipe problems.
                pass
        sys.exit(__retval)
