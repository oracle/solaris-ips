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
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.

import atexit
import errno
import getopt
import gettext
import hashlib
import locale
import logging
import os
import shutil
import socket
import sys
import traceback
import urllib2
import warnings

from mako.template import Template

from pkg.client import global_settings
from pkg.misc import msg, PipeError

import pkg
import pkg.catalog
import pkg.client.api
import pkg.client.progress as progress
import pkg.client.api_errors as apx
import pkg.misc as misc
import pkg.portable as portable

logger = global_settings.logger
orig_cwd = None

PKG_CLIENT_NAME = "pkg.sysrepo"
CLIENT_API_VERSION = 70
pkg.client.global_settings.client_name = PKG_CLIENT_NAME

# exit codes
EXIT_OK      = 0
EXIT_OOPS    = 1
EXIT_BADOPT  = 2

#
# This is a simple python script, run from the method script that starts
# svc:/application/pkg/system-repository:default.
#
# It writes an Apache configuration that is used to serve responses to pkg
# clients querying the system repository, as well as providing http/https proxy
# services to those clients, accessing external repositories.
# file:// repositories on the system running the system repository are also
# exposed to pkg clients, via Alias directives.
#
# See src/util/apache2/sysrepo/*.mako for the templates used to create the
# Apache configuration.
#
# The following filesystem locations are used:
#
# variable      default install path          description
# ---------     ---------------------         ------------
# runtime_dir   system/volatile/pkg/sysrepo   runtime .conf, htdocs, pid files
# template_dir  etc/pkg/sysrepo               mako templates
# log_dir       var/log/pkg/sysrepo           log files
# cache_dir     var/cache/pkg/sysrepo         apache proxy cache
#
# all of the above can be modified with command line arguments.
#

SYSREPO_CRYPTO_FILENAME = "crypto.txt"
SYSREPO_HTTP_TEMPLATE = "sysrepo_httpd.conf.mako"
SYSREPO_HTTP_FILENAME = "sysrepo_httpd.conf"

SYSREPO_PUB_TEMPLATE = "sysrepo_publisher_response.mako"
SYSREPO_PUB_FILENAME = "index.html"

SYSREPO_HTDOCS_DIRNAME = "htdocs"

SYSREPO_VERSIONS_DIRNAME = ["versions", "0"]
SYSREPO_SYSPUB_DIRNAME = ["syspub", "0"]
SYSREPO_PUB_DIRNAME = ["publisher", "0"]

# static string with our versions response
SYSREPO_VERSIONS_STR = """\
pkg-server %s
publisher 0
versions 0
catalog 1
file 1
syspub 0
manifest 0
""" % pkg.VERSION

SYSREPO_USER = "pkg5srv"
SYSREPO_GROUP = "pkg5srv"

class SysrepoException(Exception):
        def __unicode__(self):
        # To workaround python issues 6108 and 2517, this provides a
        # a standard wrapper for this class' exceptions so that they
        # have a chance of being stringified correctly.
                return str(self)

@atexit.register
def cleanup():
        """To be called at program finish."""
        pass

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if cmd:
                text = "%s: %s" % (cmd, text)
                pkg_cmd = "pkg.sysrepo "
        else:
                pkg_cmd = "pkg.sysrepo: "

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
        pkg.sysrepo -p <port> [-R image_root] [ -c cache_dir] [-h hostname]
                [-l logs_dir] [-r runtime_dir] [-s cache_size] [-t template_dir]
                [-T http_timeout] [-w http_proxy] [-W https_proxy]
     """))
        sys.exit(retcode)

def _get_image(image_dir):
        """Return a pkg.client.api.ImageInterface for the provided
        image directory."""

        cdir = os.getcwd()
        if not image_dir:
                image_dir = "/"
        api_inst = None
        tracker = progress.QuietProgressTracker()
        try:
                api_inst = pkg.client.api.ImageInterface(
                    image_dir, CLIENT_API_VERSION,
                    tracker, None, PKG_CLIENT_NAME)

                if api_inst.root != image_dir:
                        msg(_("Problem getting image at %s") % image_dir)
        except Exception, err:
                raise SysrepoException(
                    _("Unable to get image at %(dir)s: %(reason)s") %
                    {"dir": image_dir,
                    "reason": str(err)})

        # restore the current directory, which ImageInterace had changed
        os.chdir(cdir)
        return api_inst

def _follow_redirects(uri_list, http_timeout):
        """ Follow HTTP redirects from servers.  Needed so that we can create
        RewriteRules for all repository URLs that pkg clients may encounter."""

        ret_uris = set(uri_list)

        class SysrepoRedirectHandler(urllib2.HTTPRedirectHandler):
                """ A HTTPRedirectHandler that saves URIs we've been
                redirected to along the path to our eventual destination."""
                def __init__(self):
                        self.redirects = set()

                def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                        self.redirects.add(newurl)
                        return urllib2.HTTPRedirectHandler.redirect_request(
                            self, req, fp, code, msg, hdrs, newurl)

        for uri in uri_list:
                handler = SysrepoRedirectHandler()
                opener = urllib2.build_opener(handler)
                if not uri.startswith("http:"):
                        ret_uris.update([uri])
                        continue

                # otherwise, open a known url to check for redirects
                try:
                        opener.open("%s/versions/0" % uri, None, http_timeout)
                        ret_uris.update(set(
                            [item.replace("/versions/0", "").rstrip("/")
                            for item in handler.redirects]))
                except urllib2.URLError, err:
                        # We need to log this, and carry on - the url
                        # could become available at a later date.
                        msg(_("WARNING: unable to access %(uri)s when checking "
                            "for redirects: %(err)s") % locals())
        return sorted(list(ret_uris))

def _get_publisher_info(api_inst, http_timeout):
        """Returns information about the publishers configured for the given
        ImageInterface.

        The first item returned is a map of uris to tuples, (prefix, cert, key,
        hash of the uri)

        The second item returned is a list of publisher prefixes which specify
        no uris."""

        # build a map of URI to (pub.prefix, cert, key, hash) tuples
        uri_pub_map = {}
        no_uri_pubs = []

        for pub in api_inst.get_publishers():
                if pub.disabled:
                        continue

                prefix = pub.prefix
                repo = pub.repository
                uri_list = _follow_redirects(
                    [repo_uri.uri.rstrip("/")
                    for repo_uri in repo.mirrors + repo.origins],
                    http_timeout)

                for uri in uri_list:
                        # we don't support p5p archives, only directory-based
                        # repositories.  We also don't support file repositories
                        # of < version 4.
                        if uri.startswith("file:"):
                                urlresult = urllib2.urlparse.urlparse(uri)
                                if not os.path.exists(urlresult.path):
                                        raise SysrepoException(
                                            _("file repository %s does not "
                                            "exist or is not accessible") % uri)
                                if not os.path.isdir(urlresult.path):
                                        raise SysrepoException(
                                            _("p5p-based file repository %s "
                                            "cannot be proxied.") % uri)
                                if not os.path.exists(os.path.join(
                                    urlresult.path, "pkg5.repository")):
                                        raise SysrepoException(
                                            _("file repository %s cannot be "
                                            "proxied. Only file "
                                            "repositories of version 4 or "
                                            "later are supported.") % uri)

                        hash = _uri_hash(uri)
                        cert = repo_uri.ssl_cert
                        key = repo_uri.ssl_key
                        if uri in uri_pub_map:
                                uri_pub_map[uri].append((prefix, cert, key,
                                    hash))
                        else:
                                uri_pub_map[uri] = [(prefix, cert, key, hash)]

                if not repo.mirrors + repo.origins:
                        no_uri_pubs.append(prefix)
        return uri_pub_map, no_uri_pubs

def _write_httpd_conf(runtime_dir, log_dir, template_dir, host, port, cache_dir,
    cache_size, uri_pub_map, http_proxy, https_proxy):
        """Writes the apache configuration for the system repository."""

        try:
                # check our hostname
                socket.gethostbyname(host)

                # check our directories
                dirs = [runtime_dir, log_dir]
                if cache_dir not in ["None", "memory"]:
                        dirs.append(cache_dir)
                for dir in dirs + [template_dir]:
                        if os.path.exists(dir) and not os.path.isdir(dir):
                                raise SysrepoException(
                                    _("%s is not a directory") % dir)
                for dir in dirs:
                        try:
                                os.makedirs(dir, 0700)
                        except OSError, err:
                                if err.errno != errno.EEXIST:
                                        raise

                # check our port
                try:
                        num = int(port)
                        if num <= 0 or num >= 65535:
                                raise SysrepoException(_("invalid port: %s") %
                                    port)
                except ValueError:
                        raise SysrepoException(_("invalid port: %s") % port)

                # check our cache size
                try:
                        num = int(cache_size)
                        if num <= 0:
                                raise SysrepoException(_("invalid cache size: "
                                   "%s") % num)
                except ValueError:
                        raise SysrepoException(_("invalid cache size: %s") %
                            cache_size)

                # check our proxy arguments - we can use a proxy to handle
                # incoming http or https requests, but that proxy must use http.
                for key, val in [("http_proxy", http_proxy),
                    ("https_proxy", https_proxy)]:
                        if not val:
                                continue
                        try:
                                result = urllib2.urlparse.urlparse(val)
                                if result.scheme != "http":
                                        raise Exception(
                                            _("scheme must be http"))
                                if not result.netloc:
                                        raise Exception("missing netloc")
                        except Exception, e:
                                raise SysrepoException(
                                    _("invalid %(key)s: %(val)s: %(err)s") %
                                    {"key": key, "val": val, "err": str(e)})

                httpd_conf_template_path = os.path.join(template_dir,
                    SYSREPO_HTTP_TEMPLATE)
                httpd_conf_template = Template(
                    filename=httpd_conf_template_path)

                # our template expects cache size expressed in Kb
                httpd_conf_text = httpd_conf_template.render(
                    sysrepo_log_dir=log_dir,
                    sysrepo_runtime_dir=runtime_dir,
                    uri_pub_map=uri_pub_map,
                    ipv6_addr="::1",
                    host=host,
                    port=port,
                    cache_dir=cache_dir,
                    cache_size=int(cache_size) * 1024,
                    http_proxy=http_proxy,
                    https_proxy=https_proxy)
                httpd_conf_path = os.path.join(runtime_dir,
                    SYSREPO_HTTP_FILENAME)
                httpd_conf_file = file(httpd_conf_path, "w")
                httpd_conf_file.write(httpd_conf_text)
                httpd_conf_file.close()
        except socket.gaierror, err:
                raise SysrepoException(
                    _("Unable to write sysrepo_httpd.conf: %(host)s: "
                    "%(err)s") % locals())
        except (OSError, IOError), err:
                raise SysrepoException(
                    _("Unable to write sysrepo_httpd.conf: %s") % err)

def _write_crypto_conf(runtime_dir, uri_pub_map):
        """Writes the crypto.txt file, containing keys and certificates
        in order for the system repository to proxy to https repositories."""

        try:
                crypto_path = os.path.join(runtime_dir, SYSREPO_CRYPTO_FILENAME)
                file(crypto_path, "w").close()
                os.chmod(crypto_path, 0600)
                written_crypto_content = False

                for repo_list in uri_pub_map.values():
                        for (pub, cert_path, key_path, hash) in repo_list:
                                if cert_path and key_path:
                                       crypto_file = file(crypto_path, "a")
                                       crypto_file.writelines(file(cert_path))
                                       crypto_file.writelines(file(key_path))
                                       crypto_file.close()
                                       written_crypto_content = True

                # Apache needs us to have some content in this file
                if not written_crypto_content:
                        crypto_file = file(crypto_path, "w")
                        crypto_file.write(
                            "# this space intentionally left blank\n")
                        crypto_file.close()
                os.chmod(crypto_path, 0400)
        except OSError, err:
                raise SysrepoException(
                    _("unable to write crypto.txt file: %s") % err)

def _write_publisher_response(uri_pub_map, htdocs_path, template_dir):
        """Writes static html for all file-repository-based publishers that
        is served as their publisher/0 responses.  Responses for
        non-file-based publishers are handled by rewrite rules in our
        Apache configuration."""

        try:
                # build a version of our uri_pub_map, keyed by publisher
                pub_uri_map = {}
                for uri in uri_pub_map:
                        for (pub, key, cert, hash) in uri_pub_map[uri]:
                                if pub not in pub_uri_map:
                                        pub_uri_map[pub] = []
                                pub_uri_map[pub].append((uri, key, cert, hash))

                publisher_template_path = os.path.join(template_dir,
                    SYSREPO_PUB_TEMPLATE)
                publisher_template = Template(filename=publisher_template_path)

                for pub in pub_uri_map:
                        for (uri, cert_path, key_path, hash) in \
                            pub_uri_map[pub]:
                                if uri.startswith("file:"):
                                        publisher_text = \
                                            publisher_template.render(
                                            uri=uri, pub=pub)
                                        publisher_path = os.path.sep.join(
                                            [htdocs_path, pub, hash] +
                                            SYSREPO_PUB_DIRNAME)
                                        os.makedirs(publisher_path)
                                        publisher_file = file(
                                            os.path.sep.join([publisher_path,
                                            SYSREPO_PUB_FILENAME]), "w")
                                        publisher_file.write(publisher_text)
                                        publisher_file.close()
        except OSError, err:
                raise SysrepoException(
                    _("unable to write publisher response: %s") % err)

def _write_versions_response(htdocs_path):
        """Writes a static versions/0 response for the system repository."""

        try:
                versions_path = os.path.join(htdocs_path,
                    os.path.sep.join(SYSREPO_VERSIONS_DIRNAME))
                os.makedirs(versions_path)

                versions_file = file(os.path.join(versions_path, "index.html"),
                    "w")
                versions_file.write(SYSREPO_VERSIONS_STR)
                versions_file.close()
        except OSError, err:
                raise SysrepoException(
                    _("Unable to write versions response: %s") % err)

def _write_sysrepo_response(api_inst, htdocs_path, uri_pub_map, no_uri_pubs):
        """Writes a static syspub/0 response for the system repository."""

        try:
                sysrepo_path = os.path.join(htdocs_path,
                    os.path.sep.join(SYSREPO_SYSPUB_DIRNAME))
                os.makedirs(sysrepo_path)
                pub_prefixes = [
                    info[0]
                    for uri in uri_pub_map.keys()
                    for info in uri_pub_map[uri]
                ]
                pub_prefixes.extend(no_uri_pubs)
                api_inst.write_syspub(os.path.join(sysrepo_path, "index.html"),
                    pub_prefixes, 0)
        except (OSError, apx.ApiException), err:
                raise SysrepoException(
                    _("Unable to write syspub response: %s") % err)

def _uri_hash(uri):
        """Returns a string hash of the given URI"""
        return hashlib.sha1(uri).hexdigest()

def _chown_runtime_dir(runtime_dir):
        """Change the ownership of all files under runtime_dir to our sysrepo
        user/group"""

        uid = portable.get_user_by_name(SYSREPO_USER, None, False)
        gid = portable.get_group_by_name(SYSREPO_GROUP, None, False)
        try:
                misc.recursive_chown_dir(runtime_dir, uid, gid)
        except OSError, err:
                if not os.environ.get("PKG5_TEST_ENV", None):
                        raise SysrepoException(
                            _("Unable to chown to %(user)s:%(group)s: "
                            "%(err)s") %
                            {"user": SYSREPO_USER, "group": SYSREPO_GROUP,
                            "err": err})

def cleanup_conf(runtime_dir=None):
        """Destroys an old configuration."""
        try:
                shutil.rmtree(runtime_dir, ignore_errors=True)
        except OSError, err:
                raise SysrepoException(
                    _("Unable to cleanup old configuration: %s") % err)

def refresh_conf(image_root="/", port=None, runtime_dir=None,
    log_dir=None, template_dir=None, host="127.0.0.1", cache_dir=None,
    cache_size=1024, http_timeout=3, http_proxy=None, https_proxy=None):
        """Creates a new configuration for the system repository.
        That is, it copies /var/pkg/pkg5.image file the htdocs
        directory and creates an apache .conf file.

        TODO: a way to map only given zones to given publishers
        """
        try:
                ret = EXIT_OK
                cleanup_conf(runtime_dir=runtime_dir)
                try:
                        http_timeout = int(http_timeout)
                except ValueError, err:
                        raise SysrepoException(
                            _("invalid value for http_timeout: %s") % err)
                if http_timeout < 1:
                        raise SysrepoException(
                            _("http_timeout must a positive integer"))
                try:
                        api_inst = _get_image(image_root)
                        uri_pub_map, no_uri_pubs = _get_publisher_info(api_inst,
                            http_timeout)
                except SysrepoException, err:
                        raise SysrepoException(
                            _("unable to get publisher information: %s") %
                            err)
                try:
                        htdocs_path = os.path.join(runtime_dir,
                            SYSREPO_HTDOCS_DIRNAME)
                        os.makedirs(htdocs_path)
                except OSError, err:
                        raise SysrepoException(
                            _("unable to create htdocs dir: %s") % err)

                _write_httpd_conf(runtime_dir, log_dir, template_dir, host,
                    port, cache_dir, cache_size, uri_pub_map, http_proxy,
                    https_proxy)
                _write_crypto_conf(runtime_dir, uri_pub_map)
                _write_publisher_response(uri_pub_map, htdocs_path,
                    template_dir)
                _write_versions_response(htdocs_path)
                _write_sysrepo_response(api_inst, htdocs_path, uri_pub_map,
                    no_uri_pubs)
                _chown_runtime_dir(runtime_dir)
        except SysrepoException, err:
                error(err)
                ret = EXIT_OOPS
        return ret

def main_func():
        global_settings.client_name = PKG_CLIENT_NAME

        global orig_cwd

        try:
                orig_cwd = os.getcwd()
        except OSError, e:
                try:
                        orig_cwd = os.environ["PWD"]
                        if not orig_cwd or orig_cwd[0] != "/":
                                orig_cwd = None
                except KeyError:
                        orig_cwd = None

        # some sensible defaults
        host = "127.0.0.1"
        port = None
        # an empty image_root means we don't get '//' in the below
        # _get_image() deals with "" in a sane manner.
        image_root = ""
        cache_dir = "%s/var/cache/pkg/sysrepo" % image_root
        cache_size = "1024"
        template_dir = "%s/etc/pkg/sysrepo" % image_root
        runtime_dir = "%s/var/run/pkg/sysrepo" % image_root
        log_dir = "%s/var/log/pkg/sysrepo" % image_root
        http_timeout = 4
        http_proxy = None
        https_proxy = None

        try:
                opts, pargs = getopt.getopt(sys.argv[1:],
                    "c:h:l:p:r:R:s:t:T:w:W:?", ["help"])
                for opt, arg in opts:
                        if opt == "-c":
                                cache_dir = arg
                        elif opt == "-h":
                                host = arg
                        elif opt == "-l":
                                log_dir = arg
                        elif opt == "-p":
                                port = arg
                        elif opt == "-r":
                                runtime_dir = arg
                        elif opt == "-R":
                                image_root = arg
                        elif opt == "-s":
                                cache_size = arg
                        elif opt == "-t":
                                template_dir = arg
                        elif opt == "-T":
                                http_timeout = arg
                        elif opt == "-w":
                                http_proxy = arg
                        elif opt == "-W":
                                https_proxy = arg
                        else:
                                usage()

        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        if not port:
                usage(_("required port option missing."))

        ret = refresh_conf(image_root=image_root, log_dir=log_dir,
            host=host, port=port, runtime_dir=runtime_dir,
            template_dir=template_dir, cache_dir=cache_dir,
            cache_size=cache_size, http_timeout=http_timeout,
            http_proxy=http_proxy, https_proxy=https_proxy)
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
        except apx.VersionException, __e:
                error(_("The sysrepo command appears out of sync with the "
                    "libraries provided\nby pkg:/package/pkg. The client "
                    "version is %(client)s while the library\nAPI version is "
                    "%(api)s.") % {'client': __e.received_version,
                     'api': __e.expected_version
                    })
                __ret = EXIT_OOPS
        except:
                traceback.print_exc()
                error(traceback_str)
                __ret = 99
        return __ret


if __name__ == "__main__":
        misc.setlocale(locale.LC_ALL, "", error)
        gettext.install("pkg", "/usr/share/locale")

        # Make all warnings be errors.
        warnings.simplefilter('error')

        __retval = handle_errors(main_func)
        try:
                logging.shutdown()
        except IOError:
                # Ignore python's spurious pipe problems.
                pass
        sys.exit(__retval)
