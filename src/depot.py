#!/usr/bin/python2.4
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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

# pkg.depotd - package repository daemon

# XXX The prototype pkg.depotd combines both the version management server that
# answers to pkgsend(1) sessions and the HTTP file server that answers to the
# various GET operations that a pkg(1) client makes.  This split is expected to
# be made more explicit, by constraining the pkg(1) operations such that they
# can be served as a typical HTTP/HTTPS session.  Thus, pkg.depotd will reduce
# to a special purpose HTTP/HTTPS server explicitly for the version management
# operations, and must manipulate the various state files--catalogs, in
# particular--such that the pkg(1) pull client can operately accurately with
# only a basic HTTP/HTTPS server in place.

# XXX We should support simple "last-modified" operations via HEAD queries.

# XXX Although we pushed the evaluation of next-version, etc. to the pull
# client, we should probably provide a query API to do same on the server, for
# dumb clients (like a notification service).

# The default authority for the depot.
AUTH_DEFAULT = "opensolaris.org"
# The default repository path.
REPO_PATH_DEFAULT = "/var/pkg/repo"
# The default path for static and other web content.
CONTENT_PATH_DEFAULT = "/usr/share/lib/pkg"
# The default port(s) to serve data from.
PORT_DEFAULT = 80
SSL_PORT_DEFAULT = 443
# The minimum number of threads allowed.
THREADS_MIN = 1
# The default number of threads to start.
THREADS_DEFAULT = 10
# The maximum number of threads that can be started.
THREADS_MAX = 100
# The default server socket timeout in seconds. We want this to be longer than
# the normal default of 10 seconds to accommodate clients with poor quality
# connections.
SOCKET_TIMEOUT_DEFAULT = 60
# Whether modify operations should be allowed.
READONLY_DEFAULT = False
# Whether the repository catalog should be rebuilt on startup.
REBUILD_DEFAULT = False
# Whether the indexes should be rebuilt
REINDEX_DEFAULT = False
# Not in mirror mode by default
MIRROR_DEFAULT = False

import getopt
import gettext
import locale
import logging
import os
import os.path
import OpenSSL.crypto as crypto
import OpenSSL.SSL as ssl
import pkg.portable.util as os_util
import subprocess
import sys
import tempfile
import urlparse

try:
        import cherrypy
        version = cherrypy.__version__.split('.')
        if map(int, version) < [3, 1, 0]:
                raise ImportError
        elif map(int, version) >= [3, 2, 0]:
                raise ImportError
except ImportError:
        print >> sys.stderr, """cherrypy 3.1.0 or greater (but less than """ \
            """3.2.0) is required to use this program."""
        sys.exit(2)

import pkg.catalog as catalog
from pkg.misc import port_available, msg, emsg, setlocale
import pkg.search_errors as search_errors
import pkg.server.config as config
import pkg.server.depot as depot
import pkg.server.repository as repo
import pkg.server.repositoryconfig as rc

class LogSink(object):
        """This is a dummy object that we can use to discard log entries
        without relying on non-portable interfaces such as /dev/null."""

        def write(self, *args, **kwargs):
                """Discard the bits."""
                pass

        def flush(self, *args, **kwargs):
                """Discard the bits."""
                pass

def usage(text):
        if text:
                emsg(text)

        print """\
Usage: /usr/lib/pkg.depotd [-d repo_dir] [-p port] [-s threads]
           [-t socket_timeout] [--cfg-file] [--content-root] [--log-access dest]
           [--log-errors dest] [--mirror] [--proxy-base url] [--readonly]
           [--rebuild] [--ssl-cert-file] [--ssl-dialog] [--ssl-key-file]

        --cfg-file      The pathname of the file from which to read and to
                        write configuration information.
        --content-root  The file system path to the directory containing the
                        the static and other web content used by the depot's
                        browser user interface.  The default value is
                        '/usr/share/lib/pkg'.
        --log-access    The destination for any access related information
                        logged by the depot process.  Possible values are:
                        stderr, stdout, none, or an absolute pathname.  The
                        default value is stdout if stdout is a tty; otherwise
                        the default value is none.
        --log-errors    The destination for any errors or other information
                        logged by the depot process.  Possible values are:
                        stderr, stdout, none, or an absolute pathname.  The
                        default value is stderr.
        --mirror        Package mirror mode; publishing and metadata operations
                        disallowed.  Cannot be used with --readonly or
                        --rebuild.
        --proxy-base    The url to use as the base for generating internal
                        redirects and content.
        --readonly      Read-only operation; modifying operations disallowed.
                        Cannot be used with --mirror or --rebuild.
        --rebuild       Re-build the catalog from pkgs in depot.  Cannot be
                        used with --mirror or --readonly.
        --ssl-cert-file The absolute pathname to a PEM-encoded Certificate file.
                        This option must be used with --ssl-key-file.  Usage of
                        this option will cause the depot to only respond to SSL
                        requests on the provided port.
        --ssl-dialog    Specifies what method should be used to obtain the
                        passphrase needed to decrypt the file specified by
                        --ssl-key-file.  Supported values are: builtin,
                        exec:/path/to/program, or smf:fmri.  The default value
                        is builtin.
        --ssl-key-file  The absolute pathname to a PEM-encoded Private Key file.
                        This option must be used with --ssl-cert-file.  Usage of
                        this option will cause the depot to only respond to SSL
                        requests on the provided port.
"""
        sys.exit(2)

class OptionError(Exception):
        """Option exception. """

        def __init__(self, *args):
                Exception.__init__(self, *args)

if __name__ == "__main__":

        setlocale(locale.LC_ALL, "")
        gettext.install("pkg", "/usr/share/locale")

        port = PORT_DEFAULT
        port_provided = False
        threads = THREADS_DEFAULT
        socket_timeout = SOCKET_TIMEOUT_DEFAULT
        readonly = READONLY_DEFAULT
        rebuild = REBUILD_DEFAULT
        reindex = REINDEX_DEFAULT
        proxy_base = None
        mirror = MIRROR_DEFAULT
        repo_config_file = None
        ssl_cert_file = None
        ssl_key_file = None
        ssl_dialog = "builtin"

        if "PKG_REPO" in os.environ:
                repo_path = os.environ["PKG_REPO"]
        else:
                repo_path = REPO_PATH_DEFAULT

        try:
                content_root = os.environ["PKG_DEPOT_CONTENT"]
        except KeyError:
                try:
                        content_root = os.path.join(os.environ['PKG_HOME'],
                            'share/lib/pkg')
                except KeyError:
                        content_root = CONTENT_PATH_DEFAULT

        # By default, if the destination for a particular log type is not
        # specified, this is where we will send the output.
        log_routes = {
            "access": "none",
            "errors": "stderr"
        }
        log_opts = ["--log-%s" % log_type for log_type in log_routes]

        # If stdout is a tty, then send access output there by default instead
        # of discarding it.
        if os.isatty(sys.stdout.fileno()):
                log_routes["access"] = "stdout"

        opt = None
        try:
                long_opts = ["cfg-file", "content-root=", "mirror",
                    "proxy-base=", "readonly", "rebuild", "refresh-index",
                    "ssl-cert-file=", "ssl-dialog=", "ssl-key-file="]
                for opt in log_opts:
                        long_opts.append("%s=" % opt.lstrip('--'))
                opts, pargs = getopt.getopt(sys.argv[1:], "d:np:s:t:",
                    long_opts)
                for opt, arg in opts:
                        if opt == "-n":
                                sys.exit(0)
                        elif opt == "-d":
                                repo_path = arg
                        elif opt == "-p":
                                port = int(arg)
                                port_provided = True
                        elif opt == "-s":
                                threads = int(arg)
                                if threads < THREADS_MIN:
                                        raise OptionError, \
                                            "minimum value is %d" % THREADS_MIN
                                if threads > THREADS_MAX:
                                        raise OptionError, \
                                            "maximum value is %d" % THREADS_MAX
                        elif opt == "-t":
                                socket_timeout = int(arg)
                        elif opt == "--cfg-file":
                                repo_config_file = os.path.abspath(arg)
                        elif opt == "--content-root":
                                if arg == "":
                                        raise OptionError, "You must specify " \
                                            "a directory path."
                                content_root = arg
                        elif opt in log_opts:
                                if arg is None or arg == "":
                                        raise OptionError, \
                                            "You must specify a log " \
                                            "destination."
                                log_routes[opt.lstrip("--log-")] = arg
                        elif opt == "--mirror":
                                mirror = True
                        elif opt == "--proxy-base":
                                # Attempt to decompose the url provided into
                                # its base parts.  This is done so we can
                                # remove any scheme information since we
                                # don't need it.
                                scheme, netloc, path, params, query, \
                                    fragment = urlparse.urlparse(arg,
                                    "http", allow_fragments=0)

                                if not netloc:
                                        raise OptionError, "Unable to " \
                                            "determine the hostname from " \
                                            "the provided URL; please use a " \
                                            "fully qualified URL."

                                scheme = scheme.lower()
                                if scheme not in ("http", "https"):
                                        raise OptionError, "Invalid URL; http " \
                                            "and https are the only supported " \
                                            "schemes."

                                # Rebuild the url with the sanitized components.
                                proxy_base = urlparse.urlunparse((scheme, netloc,
                                    path, params, query, fragment)
                                    )
                        elif opt == "--readonly":
                                readonly = True
                        elif opt == "--rebuild":
                                rebuild = True
                        elif opt == "--refresh-index":
                                # Note: This argument is for internal use
                                # only. It's used when pkg.depotd is reexecing
                                # itself and needs to know that's the case.
                                # This flag is purposefully omitted in usage.
                                # The supported way to forcefully reindex is to
                                # kill any pkg.depot using that directory,
                                # remove the index directory, and restart the
                                # pkg.depot process. The index will be rebuilt
                                # automatically on startup.
                                reindex = True
                        elif opt == "--ssl-cert-file":
                                if arg == "none":
                                        continue

                                ssl_cert_file = arg
                                if not os.path.isabs(ssl_cert_file):
                                        raise OptionError, "The path to " \
                                           "the Certificate file must be " \
                                           "absolute."
                                elif not os.path.exists(ssl_cert_file):
                                        raise OptionError, "The specified " \
                                            "file does not exist."
                                elif not os.path.isfile(ssl_cert_file):
                                        raise OptionError, "The specified " \
                                            "pathname is not a file."
                        elif opt == "--ssl-key-file":
                                if arg == "none":
                                        continue

                                ssl_key_file = arg
                                if not os.path.isabs(ssl_key_file):
                                        raise OptionError, "The path to " \
                                           "the Private Key file must be " \
                                           "absolute."
                                elif not os.path.exists(ssl_key_file):
                                        raise OptionError, "The specified " \
                                            "file does not exist."
                                elif not os.path.isfile(ssl_key_file):
                                        raise OptionError, "The specified " \
                                            "pathname is not a file."
                        elif opt == "--ssl-dialog":
                                if arg != "builtin" and not \
                                    arg.startswith("exec:/") and not \
                                    arg.startswith("smf:"):
                                        raise OptionError, "Invalid value " \
                                            "specified.  Expected: builtin, " \
                                            "exec:/path/to/program, or " \
                                            "smf:fmri."

                                f = arg
                                if f.startswith("exec:"):
                                        if os_util.get_canonical_os_type() != \
                                          "unix":
                                            # Don't allow a somewhat insecure
                                            # authentication method on some
                                            # platforms.
                                            raise OptionError, "exec is not " \
                                              "a supported dialog type for " \
                                              "this operating system."

                                        f = os.path.abspath(f.split(
                                            "exec:")[1])

                                        if not os.path.isfile(f):
                                                raise OptionError, "Invalid " \
                                                    "file path specified for " \
                                                    "exec."

                                        f = "exec:%s" % f

                                ssl_dialog = f
        except getopt.GetoptError, e:
                usage("pkg.depotd: %s" % e.msg)
        except OptionError, e:
                usage("pkg.depotd: option: %s -- %s" % (opt, e))
        except (ArithmeticError, ValueError):
                usage("pkg.depotd: illegal option value: %s specified " \
                    "for option: %s" % (arg, opt))

        if rebuild and reindex:
                usage("--refresh-index cannot be used with --rebuild")
        if rebuild and (readonly or mirror):
                usage("--readonly and --mirror cannot be used with --rebuild")
        if reindex and (readonly or mirror):
                usage("--readonly and --mirror cannot be used with " \
                    "--refresh-index")

        if (ssl_cert_file and not ssl_key_file) or (ssl_key_file and not
            ssl_cert_file):
                usage("The --ssl-cert-file and --ssl-key-file options must "
                    "must both be provided when using either option.")
        elif ssl_cert_file and ssl_key_file and not port_provided:
                # If they didn't already specify a particular port, use the
                # default SSL port instead.
                port = SSL_PORT_DEFAULT

        # If the program is going to reindex, the port is irrelevant since
        # the program will not bind to a port.
        if not reindex:
                available, msg = port_available(None, port)
                if not available:
                        print "pkg.depotd: unable to bind to the specified " \
                            "port: %d. Reason: %s" % (port, msg)
                        sys.exit(1)
        else:
                # Not applicable for reindexing operations.
                content_root = None

        scfg = config.SvrConfig(repo_path, content_root, AUTH_DEFAULT)

        if rebuild:
                scfg.destroy_catalog()

        if readonly:
                scfg.set_read_only()

        if mirror:
                scfg.set_mirror()

        try:
                scfg.init_dirs()
        except (RuntimeError, EnvironmentError), e:
                print "pkg.depotd: an error occurred while trying to " \
                    "initialize the depot repository directory " \
                    "structures:\n%s" % e
                sys.exit(1)

        key_data = None
        if not reindex and ssl_cert_file and ssl_key_file and \
            ssl_dialog != "builtin":
                cmdline = None
                def get_ssl_passphrase(*ignored):
                        p = None
                        try:
                                p = subprocess.Popen(cmdline, shell=True,
                                        stdout=subprocess.PIPE,
                                        stderr=None)
                                p.wait()
                        except Exception, e:
                                print "pkg.depotd: an error occurred while " \
                                    "executing [%s]; unable to obtain the " \
                                    "passphrase needed to decrypt the SSL" \
                                    "private key file: %s" (cmd, e)
                                sys.exit(1)
                        return p.stdout.read().strip("\n")

                if ssl_dialog.startswith("exec:"):
                        cmdline = "%s %s %d" % (ssl_dialog.split("exec:")[1],
                            "''", port)
                elif ssl_dialog.startswith("smf:"):
                        cmdline = "/usr/bin/svcprop -p " \
                            "pkg_secure/ssl_key_passphrase %s" % (
                            ssl_dialog.split("smf:")[1])

                # The key file requires decryption, but the user has requested
                # exec-based authentication, so it will have to be decoded first
                # to an un-named temporary file.
                try:
                        key_file = file(ssl_key_file, "rb")
                        pkey = crypto.load_privatekey(crypto.FILETYPE_PEM,
                            key_file.read(), get_ssl_passphrase)

                        key_data = tempfile.TemporaryFile()
                        key_data.write(crypto.dump_privatekey(
                            crypto.FILETYPE_PEM, pkey))
                        key_data.seek(0)
                except EnvironmentError, e:
                        print "pkg.depotd: unable to read the SSL private " \
                            "key file: %s" % e
                        sys.exit(1)
                except crypto.Error, e:
                        print "pkg.depotd: authentication or cryptography " \
                            "failure while attempting to decode\nthe SSL " \
                            "private key file: %s" % e
                        sys.exit(1)
                else:
                        # Redirect the server to the decrypted key file.
                        ssl_key_file = "/dev/fd/%d" % key_data.fileno()

        # Setup our global configuration.
        gconf = {
            "environment": "production",
            "checker.on": True,
            "log.screen": False,
            "server.socket_host": "0.0.0.0",
            "server.socket_port": port,
            "server.thread_pool": threads,
            "server.socket_timeout": socket_timeout,
            "server.shutdown_timeout": 0,
            "tools.log_headers.on": True,
            "tools.encode.on": True,
            "server.ssl_certificate": ssl_cert_file,
            "server.ssl_private_key": ssl_key_file
        }

        log_type_map = {
            "errors": {
                "param": "log.error_file",
                "attr": "error_log"
            },
            "access": {
                "param": "log.access_file",
                "attr": "access_log"
            }
        }

        for log_type in log_type_map:
                dest = log_routes[log_type]
                if dest in ("stdout", "stderr", "none"):
                        if dest == "none":
                                h = logging.StreamHandler(LogSink())
                        else:
                                h = logging.StreamHandler(eval("sys.%s" % \
                                    dest))

                        h.setLevel(logging.DEBUG)
                        h.setFormatter(cherrypy._cplogging.logfmt)
                        log_obj = eval("cherrypy.log.%s" % \
                            log_type_map[log_type]["attr"])
                        log_obj.addHandler(h)
                        # Since we've replaced cherrypy's log handler with our
                        # own, we don't want the output directed to a file.
                        dest = ""

                gconf[log_type_map[log_type]["param"]] = dest

        cherrypy.config.update(gconf)

        # Now that our logging, etc. has been setup, it's safe to perform any
        # remaining preparation.
        if reindex:
                scfg.acquire_catalog(rebuild=False)
                try:
                        scfg.catalog.run_update_index()
                except search_errors.IndexingException, e:
                        cherrypy.log(str(e), "INDEX")
                        sys.exit(1)
                sys.exit(0)

        # Now build our site configuration.
        conf = {
            "/": {
                # We have to override cherrypy's default response_class so that
                # we have access to the write() callable to stream data
                # directly to the client.
                "wsgi.response_class": depot.DepotResponse,
            },
            "/robots.txt": {
                "tools.staticfile.on": True,
                "tools.staticfile.filename": os.path.join(scfg.web_root,
                    "robots.txt")
            },
        }

        if proxy_base:
                # This changes the base URL for our server, and is primarily
                # intended to allow our depot process to operate behind Apache
                # or some other webserver process.
                #
                # Visit the following URL for more information:
                #    http://cherrypy.org/wiki/BuiltinTools#tools.proxy
                proxy_conf = {
                        "tools.proxy.on": True,
                        "tools.proxy.local": "",
                        "tools.proxy.base": proxy_base
                }

                # Now merge or add our proxy configuration information into the
                # existing configuration.
                for entry in proxy_conf:
                        conf["/"][entry] = proxy_conf[entry]

        scfg.acquire_in_flight()
        try:
                scfg.acquire_catalog()
        except catalog.CatalogPermissionsException, e:
                emsg("pkg.depotd: %s" % e)
                sys.exit(1)

        try:
                root = cherrypy.Application(repo.Repository(scfg,
                    repo_config_file))
        except rc.InvalidAttributeValueError, e:
                emsg("pkg.depotd: repository.conf error: %s" % e)
                sys.exit(1)

        try:
                cherrypy.quickstart(root, config=conf)
        except Exception, e:
                emsg("pkg.depotd: unknown error starting depot server, " \
                    "illegal option value specified?")
                sys.exit(1)

