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
# Copyright (c) 2011, 2014, Oracle and/or its affiliates. All rights reserved.
#

import atexit
import errno
import getopt
import gettext
import locale
import logging
import os
import shutil
import simplejson
import socket
import stat
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
import pkg.digest as digest
import pkg.misc as misc
import pkg.portable as portable
import pkg.p5p as p5p

logger = global_settings.logger
orig_cwd = None

PKG_CLIENT_NAME = "pkg.sysrepo"
CLIENT_API_VERSION = 78
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
        RewriteRules for all repository URLs that pkg clients may encounter.

        We return a sorted list of URIs that were found having followed all
        redirects in 'uri_list'.  We also return a boolean, True if we timed out
        when following any of the URIs.
        """

        ret_uris = set(uri_list)
        timed_out = False

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
                        timed_out = True

        return sorted(list(ret_uris)), timed_out

def __validate_pub_info(pub_info, no_uri_pubs, api_inst):
        """Determine if pub_info and no_uri_pubs objects, which may have been
        decoded from a json representation are valid, raising a SysrepoException
        if they are not.

        We use the api_inst to sanity-check that all publishers configured in
        the image are represented in pub_info or no_uri_pubs, and that their
        URIs are present.

        SysrepoExceptions are raised with developer-oriented debug messages
        which are not to be translated or shown to users.
        """

        # validate the structure of the pub_info object
        if not isinstance(pub_info, dict):
                raise SysrepoException("%s is not a dict" % pub_info)
        for uri in pub_info:
                if not isinstance(uri, basestring):
                        raise SysrepoException("%s is not a basestring" % uri)
                uri_info = pub_info[uri]
                if not isinstance(uri_info, list):
                        raise SysrepoException("%s is not a list" % uri_info)
                for props in uri_info:
                        if len(props) != 6:
                                raise SysrepoException("%s does not have 6 "
                                    "items" % props)
                        # props [0] and [3] must be strings
                        if not isinstance(props[0], basestring) or \
                            not isinstance(props[3], basestring):
                                raise SysrepoException("indices 0 and 3 of %s "
                                    "are not basestrings" % props)
                        # prop[5] must be a string, either "file" or "dir"
                        # and prop[0] must start with file://
                        if not isinstance(props[5], basestring) or \
                            (props[5] not in ["file", "dir"] and
                            props[0].startswith("file://")):
                                raise SysrepoException("index 5 of %s is not a "
                                    "basestring or is not 'file' or 'dir'" %
                                    props)
        # validate the structure of the no_uri_pubs object
        if not isinstance(no_uri_pubs, list):
                raise SysrepoException("%s is not a list" % no_uri_pubs)
        for item in no_uri_pubs:
                if not isinstance(item, basestring):
                        raise SysrepoException("%s is not a basestring" % item)

        # check that we have entries for each URI for each publisher.
        # (we may have more URIs than these, due to server-side http redirects
        # that are not reflected as origins or mirrors in the image itself)
        for pub in api_inst.get_publishers():
                if pub.disabled:
                        continue
                repo = pub.repository
                for uri in repo.mirrors + repo.origins:
                        uri_key = uri.uri.rstrip("/")
                        if uri_key not in pub_info:
                                raise SysrepoException("%s is not in %s" %
                                    (uri_key, pub_info))
                if repo.mirrors + repo.origins == []:
                        if pub.prefix not in no_uri_pubs:
                                raise SysrepoException("%s is not in %s" %
                                    (pub.prefix, no_uri_pubs))
        return

def _load_publisher_info(api_inst, image_dir):
        """Loads information about the publishers configured for the
        given ImageInterface from image_dir in a format identical to that
        returned by _get_publisher_info(..)  that is, a dictionary mapping
        URIs to a list of lists. An example entry might be:
            pub_info[uri] = [[prefix, cert, key, hash of the uri, proxy], ... ]

        and a list of publishers which have no origin or mirror URIs.

        If the cache doesn't exist, or is in a format we don't recognise, or
        we've managed to determine that it's stale, we return None, None
        indicating that the publisher_info must be rebuilt.
        """
        pub_info = None
        no_uri_pubs = None
        cache_path = os.path.join(image_dir,
            pkg.client.global_settings.sysrepo_pub_cache_path)
        try:
                try:
                        st_cache = os.lstat(cache_path)
                except OSError, e:
                        if e.errno == errno.ENOENT:
                                return None, None
                        else:
                                raise

                # the cache must be a regular file
                if not stat.S_ISREG(st_cache.st_mode):
                        raise IOError("not a regular file")

                with open(cache_path, "r") as cache_file:
                        try:
                                pub_info_tuple = simplejson.load(cache_file)
                        except simplejson.JSONDecodeError:
                                error(_("Invalid config cache file at %s "
                                    "generating fresh configuration.") %
                                    cache_path)
                                return None, None

                        if len(pub_info_tuple) != 2:
                                error(_("Invalid config cache at %s "
                                    "generating fresh configuration.") %
                                    cache_path)
                                return None, None

                        pub_info, no_uri_pubs = pub_info_tuple
                        # sanity-check the cached configuration
                        try:
                                __validate_pub_info(pub_info, no_uri_pubs,
                                    api_inst)
                        except SysrepoException, e:
                                error(_("Invalid config cache at %s "
                                    "generating fresh configuration.") %
                                    cache_path)
                                return None, None

        # If we have any problems loading the publisher info, we explain why.
        except IOError, e:
                error(_("Unable to load config from %(cache_path)s: %(e)s") %
                    locals())
                return None, None

        return pub_info, no_uri_pubs

def _store_publisher_info(uri_pub_map, no_uri_pubs, image_dir):
        """Stores a given pair of (uri_pub_map, no_uri_pubs) objects to a
        configuration cache file beneath image_dir."""
        cache_path = os.path.join(image_dir,
            pkg.client.global_settings.sysrepo_pub_cache_path)
        cache_dir = os.path.dirname(cache_path)
        try:
                if not os.path.exists(cache_dir):
                        os.makedirs(cache_dir, 0700)
                try:
                        # if the cache exists, it must be a file
                        st_cache = os.lstat(cache_path)
                        if not stat.S_ISREG(st_cache.st_mode):
                                raise IOError("not a regular file")
                except OSError:
                        pass

                with open(cache_path, "wb") as cache_file:
                        simplejson.dump((uri_pub_map, no_uri_pubs), cache_file,
                            indent=True)
                        os.chmod(cache_path, 0600)
        except IOError, e:
                error(_("Unable to store config to %(cache_path)s: %(e)s") %
                    locals())

def _valid_proxy(proxy):
        """Checks the given proxy string to make sure that it does not contain
        any authentication details since these are not supported by ProxyRemote.
        """

        u = urllib2.urlparse.urlparse(proxy)
        netloc_parts = u.netloc.split("@")
        # If we don't have any authentication details, return.
        if len(netloc_parts) == 1:
                return True
        return False

def _get_publisher_info(api_inst, http_timeout, image_dir):
        """Returns information about the publishers configured for the given
        ImageInterface.

        The first item returned is a map of uris to a list of lists of the form
        [[prefix, cert, key, hash of the uri, proxy, uri type], ... ]

        The second item returned is a list of publisher prefixes which specify
        no uris.

        Where possible, we attempt to load cached publisher information, but if
        that cached information is stale or unavailable, we fall back to
        querying the image for the publisher information, verifying repository
        URIs and checking for redirects and write that information to the
        cache."""

        # the cache gets deleted by pkg.client.image.Image.save_config()
        # any time publisher configuration changes are made.
        uri_pub_map, no_uri_pubs = _load_publisher_info(api_inst, image_dir)
        if uri_pub_map:
                return uri_pub_map, no_uri_pubs

        # map URIs to (pub.prefix, cert, key, hash, proxy, utype) tuples
        uri_pub_map = {}
        no_uri_pubs = []
        timed_out = False

        for pub in api_inst.get_publishers():
                if pub.disabled:
                        continue

                prefix = pub.prefix
                repo = pub.repository

                # Determine the proxies to use per URI
                proxy_map = {}
                for uri in repo.mirrors + repo.origins:
                        key = uri.uri.rstrip("/")
                        if uri.proxies:
                                # Apache can only use a single proxy, even
                                # if many are configured. Use the first we find.
                                proxy_map[key] = uri.proxies[0].uri

                # Apache's ProxyRemote directive does not allow proxies that
                # require authentication.
                for uri in proxy_map:
                        if not _valid_proxy(proxy_map[uri]):
                                raise SysrepoException("proxy value %(val)s "
                                    "for %(uri)s is not supported." %
                                    {"uri": uri, "val": proxy_map[uri]})

                uri_list, timed_out = _follow_redirects(
                    [repo_uri.uri.rstrip("/")
                    for repo_uri in repo.mirrors + repo.origins],
                    http_timeout)

                for uri in uri_list:

                        # We keep a field to store information about the type
                        # of URI we're looking at, which saves us
                        # from needing to make os.path.isdir(..) or
                        # os.path.isfile(..) calls when processing the template.
                        # This is important when we're rebuilding the
                        # configuration from cached publisher info and an
                        # file:// repository is temporarily unreachable.
                        utype = ""
                        if uri.startswith("file:"):
                                # we only support p5p files and directory-based
                                # repositories of >= version 4.
                                urlresult = urllib2.urlparse.urlparse(uri)
                                utype = "dir"
                                if not os.path.exists(urlresult.path):
                                        raise SysrepoException(
                                            _("file repository %s does not "
                                            "exist or is not accessible") % uri)
                                if os.path.isdir(urlresult.path) and \
                                    not os.path.exists(os.path.join(
                                    urlresult.path, "pkg5.repository")):
                                        raise SysrepoException(
                                            _("file repository %s cannot be "
                                            "proxied. Only file "
                                            "repositories of version 4 or "
                                            "later are supported.") % uri)
                                if not os.path.isdir(urlresult.path):
                                        utype = "file"
                                        try:
                                                p5p.Archive(urlresult.path)
                                        except p5p.InvalidArchive:
                                                raise SysrepoException(
                                                    _("unable to read p5p "
                                                    "archive file at %s") %
                                                    urlresult.path)

                        hash = _uri_hash(uri)
                        # we don't have per-uri ssl key/cert information yet,
                        # so we just pull it from one of the RepositoryURIs.
                        cert = repo_uri.ssl_cert
                        key = repo_uri.ssl_key
                        uri_pub_map.setdefault(uri, []).append(
                            (prefix, cert, key, hash, proxy_map.get(uri), utype)
                            )

                if not repo.mirrors + repo.origins:
                        no_uri_pubs.append(prefix)

        # if we weren't able to follow all redirects, then we don't write a new
        # cache, because it could be incomplete.
        if not timed_out:
                _store_publisher_info(uri_pub_map, no_uri_pubs, image_dir)
        return uri_pub_map, no_uri_pubs

def _chown_cache_dir(dir):
        """Sets ownership for cache directory as pkg5srv:bin"""

        uid = portable.get_user_by_name(SYSREPO_USER, None, False)
        gid = portable.get_group_by_name("bin", None, False)
        try:
                os.chown(dir, uid, gid)
        except OSError, err:
                if not os.environ.get("PKG5_TEST_ENV", None):
                        raise SysrepoException(
                            _("Unable to chown to %(user)s:%(group)s: "
                            "%(err)s") %
                            {"user": SYSREPO_USER, "group": "bin",
                            "err": err})

def _write_httpd_conf(runtime_dir, log_dir, template_dir, host, port, cache_dir,
    cache_size, uri_pub_map, http_proxy, https_proxy):
        """Writes the apache configuration for the system repository.

        If http_proxy or http_proxy is supplied, it will override any proxy
        values set in the image we're reading configuration from.
        """

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
                                os.makedirs(dir, 0755)
                                # set pkg5srv:bin as ownership for cache
                                # directory.
                                if dir == cache_dir:
                                        _chown_cache_dir(dir)
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
                                if not _valid_proxy(val):
                                        raise Exception("unsupported proxy")
                        except Exception, e:
                                raise SysrepoException(
                                    _("invalid %(key)s: %(val)s: %(err)s") %
                                    {"key": key, "val": val, "err": str(e)})

                httpd_conf_template_path = os.path.join(template_dir,
                    SYSREPO_HTTP_TEMPLATE)

                # we're disabling unicode here because we want Mako to
                # passthrough any filesystem path names, whatever the
                # original encoding.
                httpd_conf_template = Template(
                    filename=httpd_conf_template_path,
                    disable_unicode=True)

                # our template expects cache size expressed in Kb
                httpd_conf_text = httpd_conf_template.render(
                    sysrepo_log_dir=log_dir,
                    sysrepo_runtime_dir=runtime_dir,
                    sysrepo_template_dir=template_dir,
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
                httpd_conf_file = file(httpd_conf_path, "wb")
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
                        for (pub, cert_path, key_path, hash, proxy, utype) in \
                            repo_list:
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
                        for (pub, cert, key, hash, proxy, utype) in \
                            uri_pub_map[uri]:
                                if pub not in pub_uri_map:
                                        pub_uri_map[pub] = []
                                pub_uri_map[pub].append(
                                    (uri, cert, key, hash, proxy, utype))

                publisher_template_path = os.path.join(template_dir,
                    SYSREPO_PUB_TEMPLATE)
                publisher_template = Template(filename=publisher_template_path)

                for pub in pub_uri_map:
                        for (uri, cert_path, key_path, hash, proxy, utype) in \
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
        return digest.DEFAULT_HASH_FUNC(uri).hexdigest()

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
                            http_timeout, api_inst.root)
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
