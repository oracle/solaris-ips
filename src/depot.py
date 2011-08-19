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
# Copyright (c) 2007, 2011 Oracle and/or its affiliates.  All rights reserved.
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

# XXX Although we pushed the evaluation of next-version, etc. to the pull
# client, we should probably provide a query API to do same on the server, for
# dumb clients (like a notification service).

# The default path for static and other web content.
CONTENT_PATH_DEFAULT = "/usr/share/lib/pkg"
# cherrypy has a max_request_body_size parameter that determines whether the
# server should abort requests with REQUEST_ENTITY_TOO_LARGE when the request
# body is larger than the specified size (in bytes).  The maximum size supported
# by cherrypy is 2048 * 1024 * 1024 - 1 (just short of 2048MB), but the default
# here is purposefully conservative.
MAX_REQUEST_BODY_SIZE = 128 * 1024 * 1024
# The default host/port(s) to serve data from.
HOST_DEFAULT = "0.0.0.0"
PORT_DEFAULT = 80
SSL_PORT_DEFAULT = 443
# The minimum number of threads allowed.
THREADS_MIN = 1
# The default number of threads to start.
THREADS_DEFAULT = 60
# The maximum number of threads that can be started.
THREADS_MAX = 5000
# The default server socket timeout in seconds. We want this to be longer than
# the normal default of 10 seconds to accommodate clients with poor quality
# connections.
SOCKET_TIMEOUT_DEFAULT = 60

import getopt
import gettext
import locale
import logging
import os
import os.path
import OpenSSL.crypto as crypto
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

import cherrypy.process.servers
from cherrypy.process.plugins import Daemonizer

from pkg.misc import msg, emsg, setlocale
import pkg.client.api_errors as api_errors
import pkg.config as cfg
import pkg.portable.util as os_util
import pkg.search_errors as search_errors
import pkg.server.depot as ds
import pkg.server.depotresponse as dr
import pkg.server.repository as sr


class LogSink(object):
        """This is a dummy object that we can use to discard log entries
        without relying on non-portable interfaces such as /dev/null."""

        def write(self, *args, **kwargs):
                """Discard the bits."""
                pass

        def flush(self, *args, **kwargs):
                """Discard the bits."""
                pass


def usage(text=None, retcode=2, full=False):
        """Optionally emit a usage message and then exit using the specified
        exit code."""

        if text:
                emsg(text)

        if not full:
                # The full usage message isn't desired.
                emsg(_("Try `pkg.depotd --help or -?' for more "
                    "information."))
                sys.exit(retcode)

        print """\
Usage: /usr/lib/pkg.depotd [-a address] [-d inst_root] [-p port] [-s threads]
           [-t socket_timeout] [--cfg] [--content-root]
           [--disable-ops op[/1][,...]] [--debug feature_list]
           [--image-root dir] [--log-access dest] [--log-errors dest]
           [--mirror] [--nasty] [--proxy-base url] [--readonly]
           [--ssl-cert-file] [--ssl-dialog] [--ssl-key-file]
           [--sort-file-max-size size] [--writable-root dir]

        -a address      The IP address on which to listen for connections.  The
                        default value is 0.0.0.0 (INADDR_ANY) which will listen
                        on all active interfaces.  To listen on all active IPv6
                        interfaces, use '::'.
        -d inst_root    The file system path at which the server should find its
                        repository data.  Required unless PKG_REPO has been set
                        in the environment.
        -p port         The port number on which the instance should listen for
                        incoming package requests.  The default value is 80 if
                        ssl certificate and key information has not been
                        provided; otherwise, the default value is 443.
        -s threads      The number of threads that will be started to serve
                        requests.  The default value is 10.
        -t timeout      The maximum number of seconds the server should wait for
                        a response from a client before closing a connection.
                        The default value is 60.
        --cfg           The pathname of the file to use when reading and writing
                        depot configuration data, or a fully qualified service
                        fault management resource identifier (FMRI) of the SMF
                        service or instance to read configuration data from.
        --content-root  The file system path to the directory containing the
                        the static and other web content used by the depot's
                        browser user interface.  The default value is
                        '/usr/share/lib/pkg'.
        --disable-ops   A comma separated list of operations that the depot
                        should not configure.  If, for example, you wanted
                        to omit loading search v1, 'search/1' should be
                        provided as an argument, or to disable all search
                        operations, simply 'search'.
        --debug         The name of a debug feature to enable; or a whitespace
                        or comma separated list of features to enable.
                        Possible values are: headers.
        --image-root    The path to the image whose file information will be
                        used as a cache for file data.
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
        --nasty         Instruct the server to misbehave.  At random intervals
                        it will time-out, send bad responses, hang up on
                        clients, and generally be hostile.  The option
                        takes a value (1 to 100) for how nasty the server
                        should be.
        --proxy-base    The url to use as the base for generating internal
                        redirects and content.
        --readonly      Read-only operation; modifying operations disallowed.
                        Cannot be used with --mirror or --rebuild.
        --ssl-cert-file The absolute pathname to a PEM-encoded Certificate file.
                        This option must be used with --ssl-key-file.  Usage of
                        this option will cause the depot to only respond to SSL
                        requests on the provided port.
        --ssl-dialog    Specifies what method should be used to obtain the
                        passphrase needed to decrypt the file specified by
                        --ssl-key-file.  Supported values are: builtin,
                        exec:/path/to/program, smf, or an SMF FMRI.  The
                        default value is builtin.  If smf is specified, an
                        SMF FMRI must be provided using the --cfg option.
        --ssl-key-file  The absolute pathname to a PEM-encoded Private Key file.
                        This option must be used with --ssl-cert-file.  Usage of
                        this option will cause the depot to only respond to SSL
                        requests on the provided port.
        --sort-file-max-size
                        The maximum size of the indexer sort file. Used to
                        limit the amount of RAM the depot uses for indexing,
                        or increase it for speed.
        --writable-root The path to a directory to which the program has write
                        access.  Used with --readonly to allow server to
                        create needed files, such as search indices, without
                        needing write access to the package information.
Options:
        --help or -?

Environment:
        PKG_REPO                Used as default inst_root if -d not provided.
        PKG_DEPOT_CONTENT       Used as default content_root if --content-root
                                not provided."""
        sys.exit(retcode)

class OptionError(Exception):
        """Option exception. """

        def __init__(self, *args):
                Exception.__init__(self, *args)

if __name__ == "__main__":

        setlocale(locale.LC_ALL, "")
        gettext.install("pkg", "/usr/share/locale")

        add_content = False
        exit_ready = False
        rebuild = False
        reindex = False
        nasty = False
        nasty_value = 0

        # Track initial configuration values.
        ivalues = { "pkg": {} }
        if "PKG_REPO" in os.environ:
                ivalues["pkg"]["inst_root"] = os.environ["PKG_REPO"]

        try:
                content_root = os.environ["PKG_DEPOT_CONTENT"]
                ivalues["pkg"]["content_root"] = content_root
        except KeyError:
                try:
                        content_root = os.path.join(os.environ['PKG_HOME'],
                            'share/lib/pkg')
                        ivalues["pkg"]["content_root"] = content_root
                except KeyError:
                        pass

        opt = None
        addresses = set()
        debug_features = []
        disable_ops = []
        repo_props = {}
        socket_path = ""
        user_cfg = None
        try:
                long_opts = ["add-content", "cfg=", "cfg-file=",
                    "content-root=", "debug=", "disable-ops=", "exit-ready",
                    "help", "image-root=", "log-access=", "log-errors=",
                    "llmirror", "mirror", "nasty=", "proxy-base=", "readonly",
                    "rebuild", "refresh-index", "set-property=",
                    "ssl-cert-file=", "ssl-dialog=", "ssl-key-file=",
                    "sort-file-max-size=", "writable-root="]

                opts, pargs = getopt.getopt(sys.argv[1:], "a:d:np:s:t:?",
                    long_opts)

                show_usage = False
                for opt, arg in opts:
                        if opt == "-a":
                                addresses.add(arg)
                        elif opt == "-n":
                                sys.exit(0)
                        elif opt == "-d":
                                ivalues["pkg"]["inst_root"] = arg
                        elif opt == "-p":
                                ivalues["pkg"]["port"] = arg
                        elif opt == "-s":
                                threads = int(arg)
                                if threads < THREADS_MIN:
                                        raise OptionError, \
                                            "minimum value is %d" % THREADS_MIN
                                if threads > THREADS_MAX:
                                        raise OptionError, \
                                            "maximum value is %d" % THREADS_MAX
                                ivalues["pkg"]["threads"] = threads
                        elif opt == "-t":
                                ivalues["pkg"]["socket_timeout"] = arg
                        elif opt == "--add-content":
                                add_content = True
                        elif opt == "--cfg":
                                user_cfg  = arg
                        elif opt == "--cfg-file":
                                ivalues["pkg"]["cfg_file"] = arg
                        elif opt == "--content-root":
                                ivalues["pkg"]["content_root"] = arg
                        elif opt == "--debug":
                                if arg is None or arg == "":
                                        continue

                                # A list of features can be specified using a
                                # "," or any whitespace character as separators.
                                if "," in arg:
                                        features = arg.split(",")
                                else:
                                        features = arg.split()
                                debug_features.extend(features)
                        elif opt == "--disable-ops":
                                if arg is None or arg == "":
                                        raise OptionError, \
                                            "An argument must be specified."

                                disableops = arg.split(",")
                                for s in disableops:
                                        if "/" in s:
                                                op, ver = s.rsplit("/", 1)
                                        else:
                                                op = s
                                                ver = "*"

                                        if op not in \
                                            ds.DepotHTTP.REPO_OPS_DEFAULT:
                                                raise OptionError(
                                                    "Invalid operation "
                                                    "'%s'." % s)
                                        disable_ops.append(s)
                        elif opt == "--exit-ready":
                                exit_ready = True
                        elif opt == "--image-root":
                                ivalues["pkg"]["image_root"] = arg
                        elif opt.startswith("--log-"):
                                prop = "log_%s" % opt.lstrip("--log-")
                                ivalues["pkg"][prop] = arg
                        elif opt in ("--help", "-?"):
                                show_usage = True
                        elif opt == "--mirror":
                                ivalues["pkg"]["mirror"] = True
                        elif opt == "--llmirror":
                                ivalues["pkg"]["mirror"] = True
                                ivalues["pkg"]["ll_mirror"] = True
                                ivalues["pkg"]["readonly"] = True
                        elif opt == "--nasty":
                                value_err = None
                                try:
                                        nasty_value = int(arg)
                                except ValueError, e:
                                        value_err = e

                                if value_err or (nasty_value > 100 or
                                    nasty_value < 1):
                                        raise OptionError, "Invalid value " \
                                            "for nasty option.\n Please " \
                                            "choose a value between 1 and 100."
                                nasty = True
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
                                ivalues["pkg"]["proxy_base"] = \
                                    urlparse.urlunparse((scheme, netloc, path,
                                    params, query, fragment))
                        elif opt == "--readonly":
                                ivalues["pkg"]["readonly"] = True
                        elif opt == "--rebuild":
                                rebuild = True
                        elif opt == "--refresh-index":
                                # Note: This argument is for internal use
                                # only.
                                #
                                # This flag is purposefully omitted in usage.
                                # The supported way to forcefully reindex is to
                                # kill any pkg.depot using that directory,
                                # remove the index directory, and restart the
                                # pkg.depot process. The index will be rebuilt
                                # automatically on startup.
                                reindex = True
                                exit_ready = True
                        elif opt == "--set-property":
                                try:
                                        prop, p_value = arg.split("=", 1)
                                        p_sec, p_name = prop.split(".", 1)
                                except ValueError:
                                        usage(_("property arguments must be of "
                                            "the form '<section.property>="
                                            "<value>'."))
                                repo_props.setdefault(p_sec, {})
                                repo_props[p_sec][p_name] = p_value
                        elif opt == "--ssl-cert-file":
                                if arg == "none" or arg == "":
                                        # Assume this is an override to clear
                                        # the value.
                                        arg = ""
                                elif not os.path.isabs(arg):
                                        raise OptionError, "The path to " \
                                           "the Certificate file must be " \
                                           "absolute."
                                elif not os.path.exists(arg):
                                        raise OptionError, "The specified " \
                                            "file does not exist."
                                elif not os.path.isfile(arg):
                                        raise OptionError, "The specified " \
                                            "pathname is not a file."
                                ivalues["pkg"]["ssl_cert_file"] = arg
                        elif opt == "--ssl-key-file":
                                if arg == "none" or arg == "":
                                        # Assume this is an override to clear
                                        # the value.
                                        arg = ""
                                elif not os.path.isabs(arg):
                                        raise OptionError, "The path to " \
                                           "the Private Key file must be " \
                                           "absolute."
                                elif not os.path.exists(arg):
                                        raise OptionError, "The specified " \
                                            "file does not exist."
                                elif not os.path.isfile(arg):
                                        raise OptionError, "The specified " \
                                            "pathname is not a file."
                                ivalues["pkg"]["ssl_key_file"] = arg
                        elif opt == "--ssl-dialog":
                                if arg != "builtin" and \
                                    arg != "smf" and not \
                                    arg.startswith("exec:/") and not \
                                    arg.startswith("svc:"):
                                        raise OptionError, "Invalid value " \
                                            "specified.  Expected: builtin, " \
                                            "exec:/path/to/program, smf, or " \
                                            "an SMF FMRI."

                                if arg.startswith("exec:"):
                                        if os_util.get_canonical_os_type() != \
                                          "unix":
                                                # Don't allow a somewhat
                                                # insecure authentication method
                                                # on some platforms.
                                                raise OptionError, "exec is " \
                                                    "not a supported dialog " \
                                                    "type for this operating " \
                                                    "system."

                                        f = os.path.abspath(arg.split(
                                            "exec:")[1])
                                        if not os.path.isfile(f):
                                                raise OptionError, "Invalid " \
                                                    "file path specified for " \
                                                    "exec."
                                ivalues["pkg"]["ssl_dialog"] = arg
                        elif opt == "--sort-file-max-size":
                                ivalues["pkg"]["sort_file_max_size"] = arg
                        elif opt == "--writable-root":
                                ivalues["pkg"]["writable_root"] = arg

                # Set accumulated values.
                if debug_features:
                        ivalues["pkg"]["debug"] = debug_features
                if disable_ops:
                        ivalues["pkg"]["disable_ops"] = disable_ops
                if addresses:
                        ivalues["pkg"]["address"] = list(addresses)

                # Build configuration object.
                dconf = ds.DepotConfig(target=user_cfg, overrides=ivalues)
        except getopt.GetoptError, _e:
                usage("pkg.depotd: %s" % _e.msg)
        except api_errors.ApiException, _e:
                usage("pkg.depotd: %s" % str(_e))
        except OptionError, _e:
                usage("pkg.depotd: option: %s -- %s" % (opt, _e))
        except (ArithmeticError, ValueError):
                usage("pkg.depotd: illegal option value: %s specified " \
                    "for option: %s" % (arg, opt))

        if show_usage:
                usage(retcode=0, full=True)

        if not dconf.get_property("pkg", "log_errors"):
                dconf.set_property("pkg", "log_errors", "stderr")

        # If stdout is a tty, then send access output there by default instead
        # of discarding it.
        if not dconf.get_property("pkg", "log_access"):
                if os.isatty(sys.stdout.fileno()):
                        dconf.set_property("pkg", "log_access", "stdout")
                else:
                        dconf.set_property("pkg", "log_access", "none")

        # Check for invalid option combinations.
        image_root = dconf.get_property("pkg", "image_root")
        inst_root = dconf.get_property("pkg", "inst_root")
        mirror = dconf.get_property("pkg", "mirror")
        ll_mirror = dconf.get_property("pkg", "ll_mirror")
        readonly = dconf.get_property("pkg", "readonly")
        writable_root = dconf.get_property("pkg", "writable_root")
        if rebuild and add_content:
                usage("--add-content cannot be used with --rebuild")
        if rebuild and reindex:
                usage("--refresh-index cannot be used with --rebuild")
        if (rebuild or add_content) and (readonly or mirror):
                usage("--readonly and --mirror cannot be used with --rebuild "
                    "or --add-content")
        if reindex and mirror:
                usage("--mirror cannot be used with --refresh-index")
        if reindex and readonly and not writable_root:
                usage("--readonly can only be used with --refresh-index if "
                    "--writable-root is used")
        if image_root and not ll_mirror:
                usage("--image-root can only be used with --llmirror.")
        if image_root and writable_root:
                usage("--image_root and --writable-root cannot be used "
                    "together.")
        if image_root and inst_root:
                usage("--image-root and -d cannot be used together.")

        # If the image format changes this may need to be reexamined.
        if image_root:
                inst_root = os.path.join(image_root, "var", "pkg")

        # Set any values using defaults if they weren't provided.

        # Only use the first value for now; multiple bind addresses may be
        # supported later.
        address = dconf.get_property("pkg", "address")
        if address:
                address = address[0]
        elif not address:
                dconf.set_property("pkg", "address", [HOST_DEFAULT])
                address = dconf.get_property("pkg", "address")[0]

        if not inst_root:
                usage("Either PKG_REPO or -d must be provided")

        content_root = dconf.get_property("pkg", "content_root")
        if not content_root:
                dconf.set_property("pkg", "content_root", CONTENT_PATH_DEFAULT)
                content_root = dconf.get_property("pkg", "content_root")

        port = dconf.get_property("pkg", "port")
        ssl_cert_file = dconf.get_property("pkg", "ssl_cert_file")
        ssl_key_file = dconf.get_property("pkg", "ssl_key_file")
        if (ssl_cert_file and not ssl_key_file) or (ssl_key_file and not
            ssl_cert_file):
                usage("The --ssl-cert-file and --ssl-key-file options must "
                    "must both be provided when using either option.")
        elif not port:
                if ssl_cert_file and ssl_key_file:
                        dconf.set_property("pkg", "port", SSL_PORT_DEFAULT)
                else:
                        dconf.set_property("pkg", "port", PORT_DEFAULT)
                port = dconf.get_property("pkg", "port")

        socket_timeout = dconf.get_property("pkg", "socket_timeout")
        if not socket_timeout:
                dconf.set_property("pkg", "socket_timeout",
                    SOCKET_TIMEOUT_DEFAULT)
                socket_timeout = dconf.get_property("pkg", "socket_timeout")

        threads = dconf.get_property("pkg", "threads")
        if not threads:
                dconf.set_property("pkg", "threads", THREADS_DEFAULT)
                threads = dconf.get_property("pkg", "threads")

        # If the program is going to reindex, the port is irrelevant since
        # the program will not bind to a port.
        if not exit_ready:
                try:
                        cherrypy.process.servers.check_port(address, port)
                except Exception, e:
                        emsg("pkg.depotd: unable to bind to the specified "
                            "port: %d. Reason: %s" % (port, e))
                        sys.exit(1)
        else:
                # Not applicable if we're not going to serve content
                dconf.set_property("pkg", "content_root", "")

        # Any relative paths should be made absolute using pkg_root.  'pkg_root'
        # is a special property that was added to enable internal deployment of
        # multiple disparate versions of the pkg.depotd software.
        pkg_root = dconf.get_property("pkg", "pkg_root")

        repo_config_file = dconf.get_property("pkg", "cfg_file")
        if repo_config_file and not os.path.isabs(repo_config_file):
                repo_config_file = os.path.join(pkg_root, repo_config_file)

        if content_root and not os.path.isabs(content_root):
                content_root = os.path.join(pkg_root, content_root)

        if inst_root and not os.path.isabs(inst_root):
                inst_root = os.path.join(pkg_root, inst_root)

        if ssl_cert_file:
                if ssl_cert_file == "none":
                        ssl_cert_file = None
                elif not os.path.isabs(ssl_cert_file):
                        ssl_cert_file = os.path.join(pkg_root, ssl_cert_file)

        if ssl_key_file:
                if ssl_key_file == "none":
                        ssl_key_file = None
                elif not os.path.isabs(ssl_key_file):
                        ssl_key_file = os.path.join(pkg_root, ssl_key_file)

        if writable_root and not os.path.isabs(writable_root):
                writable_root = os.path.join(pkg_root, writable_root)

        # Setup SSL if requested.
        key_data = None
        ssl_dialog = dconf.get_property("pkg", "ssl_dialog")
        if not exit_ready and ssl_cert_file and ssl_key_file and \
            ssl_dialog != "builtin":
                cmdline = None
                def get_ssl_passphrase(*ignored):
                        p = None
                        try:
                                p = subprocess.Popen(cmdline, shell=True,
                                        stdout=subprocess.PIPE,
                                        stderr=None)
                                p.wait()
                        except Exception, __e:
                                emsg("pkg.depotd: an error occurred while "
                                    "executing [%s]; unable to obtain the "
                                    "passphrase needed to decrypt the SSL "
                                    "private key file: %s" % (cmdline, __e))
                                sys.exit(1)
                        return p.stdout.read().strip("\n")

                if ssl_dialog.startswith("exec:"):
                        exec_path = ssl_dialog.split("exec:")[1]
                        if not os.path.isabs(exec_path):
                                exec_path = os.path.join(pkg_root, exec_path)
                        cmdline = "%s %s %d" % (exec_path, "''", port)
                elif ssl_dialog == "smf" or ssl_dialog.startswith("svc:"):
                        if ssl_dialog == "smf":
                                # Assume the configuration target was an SMF
                                # FMRI and let svcprop fail with an error if
                                # it wasn't.
                                svc_fmri = dconf.target
                        else:
                                svc_fmri = ssl_dialog
                        cmdline = "/usr/bin/svcprop -p " \
                            "pkg_secure/ssl_key_passphrase %s" % svc_fmri

                # The key file requires decryption, but the user has requested
                # exec-based authentication, so it will have to be decoded first
                # to an un-named temporary file.
                try:
                        with file(ssl_key_file, "rb") as key_file:
                                pkey = crypto.load_privatekey(
                                    crypto.FILETYPE_PEM, key_file.read(),
                                    get_ssl_passphrase)

                        key_data = tempfile.TemporaryFile()
                        key_data.write(crypto.dump_privatekey(
                            crypto.FILETYPE_PEM, pkey))
                        key_data.seek(0)
                except EnvironmentError, _e:
                        emsg("pkg.depotd: unable to read the SSL private key "
                            "file: %s" % _e)
                        sys.exit(1)
                except crypto.Error, _e:
                        emsg("pkg.depotd: authentication or cryptography "
                            "failure while attempting to decode\nthe SSL "
                            "private key file: %s" % _e)
                        sys.exit(1)
                else:
                        # Redirect the server to the decrypted key file.
                        ssl_key_file = "/dev/fd/%d" % key_data.fileno()
                        key_data.close()

        # Setup our global configuration.
        gconf = {
            "checker.on": True,
            "environment": "production",
            "log.screen": False,
            "server.max_request_body_size": MAX_REQUEST_BODY_SIZE,
            "server.shutdown_timeout": 0,
            "server.socket_host": address,
            "server.socket_port": port,
            "server.socket_timeout": socket_timeout,
            "server.ssl_certificate": ssl_cert_file,
            "server.ssl_private_key": ssl_key_file,
            "server.thread_pool": threads,
            "tools.log_headers.on": True,
            "tools.encode.on": True
        }

        if "headers" in dconf.get_property("pkg", "debug"):
                # Despite its name, this only logs headers when there is an
                # error; it's redundant with the debug feature enabled.
                gconf["tools.log_headers.on"] = False

                # Causes the headers of every request to be logged to the error
                # log; even if an exception occurs.
                gconf["tools.log_headers_always.on"] = True
                cherrypy.tools.log_headers_always = cherrypy.Tool(
                    "on_start_resource",
                    cherrypy.lib.cptools.log_request_headers)

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
                dest = dconf.get_property("pkg", "log_%s" % log_type)
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
                elif dest:
                        if not os.path.isabs(dest):
                                dest = os.path.join(pkg_root, dest)
                gconf[log_type_map[log_type]["param"]] = dest

        cherrypy.config.update(gconf)

        # Now that our logging, etc. has been setup, it's safe to perform any
        # remaining preparation.

        # Initialize repository state.
        if not readonly:
                # Not readonly, so assume a new repository should be created.
                try:
                        sr.repository_create(inst_root, properties=repo_props)
                except sr.RepositoryExistsError:
                        # Already exists, nothing to do.
                        pass
                except (api_errors.ApiException, sr.RepositoryError), _e:
                        emsg("pkg.depotd: %s" % _e)
                        sys.exit(1)

        try:
                sort_file_max_size = dconf.get_property("pkg",
                    "sort_file_max_size")

                repo = sr.Repository(cfgpathname=repo_config_file,
                    log_obj=cherrypy, mirror=mirror, properties=repo_props,
                    read_only=readonly, root=inst_root,
                    sort_file_max_size=sort_file_max_size,
                    writable_root=writable_root)
        except (RuntimeError, sr.RepositoryError), _e:
                emsg("pkg.depotd: %s" % _e)
                sys.exit(1)
        except search_errors.IndexingException, _e:
                emsg("pkg.depotd: %s" % str(_e), "INDEX")
                sys.exit(1)
        except api_errors.ApiException, _e:
                emsg("pkg.depotd: %s" % str(_e))
                sys.exit(1)

        if not rebuild and not add_content and not repo.mirror and \
            not (repo.read_only and not repo.writable_root):
                # Automatically update search indexes on startup if not already
                # told to, and not in readonly/mirror mode.
                reindex = True

        if reindex:
                try:
                        # Only execute a index refresh here if --exit-ready was
                        # requested; it will be handled later in the setup
                        # process for other cases.
                        if repo.root and exit_ready:
                                repo.refresh_index()
                except (sr.RepositoryError, search_errors.IndexingException,
                    api_errors.ApiException), e:
                        emsg(str(e), "INDEX")
                        sys.exit(1)
        elif rebuild:
                try:
                        repo.rebuild(build_index=True)
                except sr.RepositoryError, e:
                        emsg(str(e), "REBUILD")
                        sys.exit(1)
                except (search_errors.IndexingException,
                    api_errors.UnknownErrors,
                    api_errors.PermissionsException), e:
                        emsg(str(e), "INDEX")
                        sys.exit(1)
        elif add_content:
                try:
                        repo.add_content()
                        repo.refresh_index()
                except sr.RepositoryError, e:
                        emsg(str(e), "ADD_CONTENT")
                        sys.exit(1)
                except (search_errors.IndexingException,
                    api_errors.UnknownErrors,
                    api_errors.PermissionsException), e:
                        emsg(str(e), "INDEX")
                        sys.exit(1)

        # Ready to start depot; exit now if requested.
        if exit_ready:
                sys.exit(0)

        # Next, initialize depot.
        if nasty:
                depot = ds.NastyDepotHTTP(repo, dconf)
                depot.set_nasty(nasty_value)
        else:
                depot = ds.DepotHTTP(repo, dconf)

        # Now build our site configuration.
        conf = {
            "/": {
                # We have to override cherrypy's default response_class so that
                # we have access to the write() callable to stream data
                # directly to the client.
                "wsgi.response_class": dr.DepotResponse,
            },
            "/robots.txt": {
                "tools.staticfile.on": True,
                "tools.staticfile.filename": os.path.join(depot.web_root,
                    "robots.txt")
            },
        }

        proxy_base = dconf.get_property("pkg", "proxy_base")
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

        if ll_mirror:
                ds.DNSSD_Plugin(cherrypy.engine, gconf).subscribe()

        if reindex:
                # Tell depot to update search indexes when possible;
                # this is done as a background task so that packages
                # can be served immediately while search indexes are
                # still being updated.
                depot._queue_refresh_index()

        # If stdin is not a tty and the pkgdepot controller isn't being used,
        # then assume process should be daemonized.
        if not os.environ.get("PKGDEPOT_CONTROLLER") and \
            not os.isatty(sys.stdin.fileno()):
                Daemonizer(cherrypy.engine).subscribe()

        try:
                root = cherrypy.Application(depot)
                cherrypy.quickstart(root, config=conf)
        except Exception, _e:
                emsg("pkg.depotd: unknown error starting depot server, " \
                    "illegal option value specified?")
                emsg(_e)
                sys.exit(1)
