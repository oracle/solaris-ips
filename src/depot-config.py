#!/usr/bin/python3.9 -Es
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
# Copyright (c) 2013, 2024, Oracle and/or its affiliates.
#

try:
    import pkg.no_site_packages
    import datetime
    import errno
    import getopt
    import gettext
    import locale
    import logging
    import os
    import re
    import shutil
    import rapidjson as json
    import socket
    import sys
    import traceback
    import warnings

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

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
    from pkg.client.pkgdefs import EXIT_OK, EXIT_OOPS, EXIT_BADOPT, EXIT_FATAL
except KeyboardInterrupt:
    import sys
    sys.exit(1)  # EXIT_OOPS

logger = global_settings.logger

DEPOT_HTTP_TEMPLATE = "depot_httpd.conf.mako"
DEPOT_FRAGMENT_TEMPLATE = "depot.conf.mako"

DEPOT_HTTP_FILENAME = "depot_httpd.conf"
DEPOT_FRAGMENT_FILENAME = "depot.conf"

DEPOT_PUB_FILENAME = "index.html"
DEPOT_HTDOCS_DIRNAME = "htdocs"

DEPOT_VERSIONS_DIRNAME = ["versions", "0"]
DEPOT_STATUS_DIRNAME = ["status", "0"]
DEPOT_PUB_DIRNAME = ["publisher", "1"]

DEPOT_CACHE_FILENAME = "depot.cache"

KNOWN_SERVER_TYPES = ["apache2"]

PKG_SERVER_SVC = "svc:/application/pkg/server"

# static string with our versions response
DEPOT_FRAGMENT_VERSIONS_STR = """\
pkg-server {0}
publisher 0 1
versions 0
catalog 1
file 1
manifest 0
status 0
""".format(pkg.VERSION)

# versions response used when we provide search capability
DEPOT_VERSIONS_STR = """{0}admin 0
search 0 1
""".format(DEPOT_FRAGMENT_VERSIONS_STR)

DEPOT_USER = "pkg5srv"
DEPOT_GROUP = "pkg5srv"


class DepotException(Exception):
    pass


def error(text, cmd=None):
    """Emit an error message prefixed by the command name """

    if cmd:
        text = "{0}: {1}".format(cmd, text)
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
                [-t server_type] ( ( [-F] [-P server_prefix] ) | [--https
                ( ( --cert server_cert_file --key server_key_file
                [--cert-chain ssl_cert_chain_file] ) |
                --cert-key-dir cert_key_directory ) [ (--ca-cert ca_cert_file
                --ca-key ca_key_file ) ]
                [--smf-fmri smf_pkg_depot_fmri] ] )
"""))
    sys.exit(retcode)


def _chown_dir(dir):
    """Sets ownership for the given directory to pkg5srv:pkg5srv"""

    uid = portable.get_user_by_name(DEPOT_USER, None, False)
    gid = portable.get_group_by_name(DEPOT_GROUP, None, False)
    try:
        os.chown(dir, uid, gid)
    except OSError as err:
        if not os.environ.get("PKG5_TEST_ENV", None):
            raise DepotException(_("Unable to chown {dir} to "
                "{user}:{group}: {err}").format(
                dir=dir, user=DEPOT_USER,
                group=DEPOT_GROUP, err=err))


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
    except Exception as e:
        raise DepotException(e)

    all_pubs = [pub.prefix for pub in repository.get_publishers()]
    try:
        default_pub = repository.cfg.get_property("publisher", "prefix")
    except cfg.UnknownPropertyError:
        default_pub = None
    return all_pubs, default_pub, repository.get_status()


def _write_httpd_conf(pubs, default_pubs, runtime_dir, log_dir, template_dir,
        cache_dir, cache_size, host, port, sroot,
        fragment=False, allow_refresh=False, ssl_cert_file="",
        ssl_key_file="", ssl_cert_chain_file=""):
    """Writes the webserver configuration for the depot.

    pubs            repository and publisher information, a list in the form
                    [(publisher_prefix, repo_dir, repo_prefix,
                        writable_root), ... ]
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
    and we want to separate pkg(7) resources from the other resources
    provided.

    'repo_prefix' exists so that we can disambiguate between multiple
    repositories that provide the same publisher.

    'ssl_cert_file' the location of the server certificate file.

    'ssl_key_file' the location of the server key file.

    'ssl_cert_chain_file' the location of the certificate chain file if the
        the server certificate is not signed by the top level CA.
    """

    try:
        # check our hostname
        socket.getaddrinfo(host, None)

        # Apache needs IPv6 addresses wrapped in square brackets
        if ":" in host:
            host = "[{0}]".format(host)

        # check our directories
        dirs = [runtime_dir]
        if not fragment:
            dirs.append(log_dir)
        if cache_dir:
            dirs.append(cache_dir)
        for dir in dirs + [template_dir]:
            if os.path.exists(dir) and not os.path.isdir(dir):
                raise DepotException(
                    _("{0} is not a directory").format(dir))

        for dir in dirs:
            misc.makedirs(dir)

        # check our port
        if not fragment:
            try:
                num = int(port)
                if num <= 0 or num >= 65535:
                    raise DepotException(
                        _("invalid port: {0}").format(port))
            except ValueError:
                raise DepotException(
                    _("invalid port: {0}").format(port))

        # check our cache size
        try:
            num = int(cache_size)
            if num < 0:
                raise DepotException(_("invalid cache size: "
                   "{0}").format(num))
        except ValueError:
            raise DepotException(
                _("invalid cache size: {0}").format(cache_size))

        httpd_conf_template_path = os.path.join(template_dir,
            DEPOT_HTTP_TEMPLATE)
        fragment_conf_template_path = os.path.join(template_dir,
            DEPOT_FRAGMENT_TEMPLATE)

        conf_lookup = TemplateLookup(directories=[template_dir])
        if fragment:
            conf_template = Template(
                filename=fragment_conf_template_path,
                lookup=conf_lookup)
            conf_path = os.path.join(runtime_dir,
                DEPOT_FRAGMENT_FILENAME)
        else:
            conf_template = Template(
                filename=httpd_conf_template_path,
                lookup=conf_lookup)
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
            allow_refresh=allow_refresh,
            ssl_cert_file=ssl_cert_file,
            ssl_key_file=ssl_key_file,
            ssl_cert_chain_file=ssl_cert_chain_file
        )

        with open(conf_path, "w") as conf_file:
            conf_file.write(conf_text)

    except (socket.gaierror, UnicodeError) as err:
        # socket.getaddrinfo raise UnicodeDecodeError in Python 3
        # for some input, such as '.'
        raise DepotException(
            _("Unable to write Apache configuration: {host}: "
            "{err}").format(**locals()))
    except (OSError, IOError, EnvironmentError, apx.ApiException) as err:
        traceback.print_exc()
        raise DepotException(
            _("Unable to write depot_httpd.conf: {0}").format(err))


def _write_versions_response(htdocs_path, fragment=False):
    """Writes a static versions/0 response for the Apache depot."""

    try:
        versions_path = os.path.join(htdocs_path,
            *DEPOT_VERSIONS_DIRNAME)
        misc.makedirs(versions_path)

        with open(os.path.join(versions_path, "index.html"), "w") as \
            versions_file:
            versions_file.write(
                fragment and DEPOT_FRAGMENT_VERSIONS_STR or
                DEPOT_VERSIONS_STR)

        versions_file.close()
    except (OSError, apx.ApiException) as err:
        raise DepotException(
            _("Unable to write versions response: {0}").format(err))


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
            with open(os.path.join(pub_path, "index.html"), "w") as\
                pub_file:
                p5i.write(pub_file, [pub])

        # write a response that contains all publishers
        pub_path = os.path.join(htdocs_path,
            os.path.sep.join([repo_prefix] + DEPOT_PUB_DIRNAME))
        os.makedirs(pub_path)
        with open(os.path.join(pub_path, "index.html"), "w") as \
            pub_file:
            p5i.write(pub_file, pub_objs)

    except (OSError, apx.ApiException) as err:
        raise DepotException(
            _("Unable to write publisher response: {0}").format(err))


def _write_status_response(status, htdocs_path, repo_prefix):
    """Writes a status status/0 response for the depot."""
    try:
        status_path = os.path.join(htdocs_path, repo_prefix,
            os.path.sep.join(DEPOT_STATUS_DIRNAME), "index.html")
        misc.makedirs(os.path.dirname(status_path))
        with open(status_path, "w") as status_file:
            status_file.write(json.dumps(status, ensure_ascii=False,
                indent=2, sort_keys=True))
    except OSError as err:
        raise DepotException(
            _("Unable to write status response: {0}").format(err))


def _createCertificateKey(serial, CN, starttime, endtime,
    dump_cert_path, dump_key_path, issuerCert=None, issuerKey=None):
    """Generate a certificate given a certificate request.

    'serial' is the serial number for the certificate

    'CN' is the subject common name of the certificate.

    'starttime' is the timestamp (datetime object) when the
        certificate starts being valid.

    'endtime' is the timestamp (datetime object) when the
        certificate stops being valid.

    'dump_cert_path' is the file the generated certificate gets dumped.

    'dump_key_path' is the file the generated key gets dumped.

    'issuerCert' is the certificate object of the issuer.

    'issuerKey' is the key object of the issuer.
    """

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )

    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'pkg5'),
        x509.NameAttribute(NameOID.COMMON_NAME, CN if issuerCert else "Depot Test CA"),
    ])

    # If an issuer is specified, set the issuer; otherwise set cert
    # itself as an issuer.
    issuer = issuerCert.issuer if issuerCert else subject

    # If there is a issuer key, sign with that key. Otherwise,
    # create a self-signed cert.
    if issuerKey:
        extension = x509.BasicConstraints(ca=False, path_length=None)
        sign_key = issuerKey
    else:
        extension = x509.BasicConstraints(ca=True, path_length=None)
        sign_key = key

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(starttime)
        .not_valid_after(endtime)
        .add_extension(extension, critical=True)
        .sign(sign_key, algorithm=hashes.SHA256())
    )

    with open(dump_cert_path, "wb") as f:
        f.write(cert.public_bytes(encoding=serialization.Encoding.PEM))
    with open(dump_key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    return cert, key


def _generate_server_cert_key(host, port, ca_cert_file="", ca_key_file="",
    output_dir="/tmp"):
    """ Generate certificate and key files for https service."""
    if os.path.exists(output_dir):
        if not os.path.isdir(output_dir):
            raise DepotException(
                _("{0} is not a directory").format(output_dir))
    else:
        misc.makedirs(output_dir)
    server_id = "{0}_{1}".format(host, port)

    cs_prefix = "server_{0}".format(server_id)
    server_cert_file = os.path.join(output_dir, "{0}_cert.pem".format(
        cs_prefix))
    server_key_file = os.path.join(output_dir, "{0}_key.pem".format(
        cs_prefix))

    # If the cert and key files do not exist, then generate one.
    if not os.path.exists(server_cert_file) or not os.path.exists(
        server_key_file):

        starttime = datetime.datetime.now()
        endtime = starttime + datetime.timedelta(days=10*365)

        # If user specifies ca_cert_file and ca_key_file, just load
        # the files. Otherwise, generate new ca_cert and ca_key.
        if not ca_cert_file or not ca_key_file:
            ca_cert_file = os.path.join(output_dir,
                "ca_{0}_cert.pem".format(server_id))
            ca_key_file = os.path.join(output_dir,
                "ca_{0}_key.pem".format(server_id))
            ca_cert, ca_key = _createCertificateKey(1, host,
                starttime, endtime, ca_cert_file, ca_key_file)
        else:
            if not os.path.exists(ca_cert_file):
                raise DepotException(_("Cannot find user "
                    "provided CA certificate file: {0}").format(
                    ca_cert_file))
            if not os.path.exists(ca_key_file):
                raise DepotException(_("Cannot find user "
                    "provided CA key file: {0}").format(
                    ca_key_file))
            with open(ca_cert_file, "rb") as fr:
                ca_cert = x509.load_pem_x509_certificate(fr.read())
            with open(ca_key_file, "rb") as fr:
                ca_key = serialization.load_pem_private_key(fr.read(), password=None)

        _createCertificateKey(2, host, starttime, endtime,
            server_cert_file, server_key_file, issuerCert=ca_cert,
            issuerKey=ca_key)

    return (ca_cert_file, ca_key_file, server_cert_file, server_key_file)


def cleanup_htdocs(htdocs_dir):
    """Destroy any existing "htdocs" directory."""
    try:
        shutil.rmtree(htdocs_dir, ignore_errors=True)
    except OSError as err:
        raise DepotException(
            _("Unable to remove an existing 'htdocs' directory "
            "in the runtime directory: {0}").format(err))


def refresh_conf(repo_info, log_dir, host, port, runtime_dir,
            template_dir, cache_dir, cache_size, sroot, fragment=False,
            allow_refresh=False, ssl_cert_file="", ssl_key_file="",
            ssl_cert_chain_file=""):
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
        # (publisher prefix, repository root dir, repository prefix,
        #     writable_root)
        pubs = []
        default_pubs = []
        errors = []

        # Query each repository for its publisher information.
        for (repo_root, repo_prefix, writable_root) in repo_info:
            try:
                publishers, default_pub, status = \
                    _get_publishers(repo_root)
                for pub in publishers:
                    pubs.append(
                        (pub, repo_root,
                        repo_prefix, writable_root))
                default_pubs.append((default_pub,
                    repo_root, repo_prefix))
                _write_status_response(status, htdocs_path,
                    repo_prefix)
                # The writable root must exist and must be
                # owned by pkg5srv:pkg5srv
                if writable_root:
                    misc.makedirs(writable_root)
                    _chown_dir(writable_root)

            except DepotException as err:
                errors.append(str(err))
        if errors:
            raise DepotException(_("Unable to write configuration: "
                "{0}").format("\n".join(errors)))

        # Write the publisher/0 response for each repository
        pubs_by_repo = {}
        for pub_prefix, repo_root, repo_prefix, writable_root in pubs:
            pubs_by_repo.setdefault(repo_prefix, []).append(
                pub_prefix)
        for repo_prefix in pubs_by_repo:
            _write_publisher_response(
                pubs_by_repo[repo_prefix], htdocs_path, repo_prefix)

        _write_httpd_conf(pubs, default_pubs, runtime_dir, log_dir,
            template_dir, cache_dir, cache_size, host, port, sroot,
            fragment=fragment, allow_refresh=allow_refresh,
            ssl_cert_file=ssl_cert_file, ssl_key_file=ssl_key_file,
            ssl_cert_chain_file=ssl_cert_chain_file)
        _write_versions_response(htdocs_path, fragment=fragment)
        # If we're writing a configuration fragment, then the web server
        # is probably not running as DEPOT_USER:DEPOT_GROUP
        if not fragment:
            _chown_dir(runtime_dir)
            _chown_dir(cache_dir)
        else:
            msg(_("Created {0}/depot.conf").format(runtime_dir))
    except (DepotException, OSError, apx.ApiException) as err:
        error(err)
        ret = EXIT_OOPS
    return ret


def get_smf_repo_info():
    """Return a list of repo_info from the online instances of pkg/server
    which are marked as pkg/standalone = False and pkg/readonly = True."""

    smf_instances = smf.check_fmris(None, "{0}:*".format(PKG_SERVER_SVC))
    repo_info = []
    for fmri in smf_instances:
        repo_prefix = fmri.split(":")[-1]
        repo_root = smf.get_prop(fmri, "pkg/inst_root")
        writable_root = smf.get_prop(fmri, "pkg/writable_root")
        if not writable_root or writable_root == '""':
            writable_root = None
        state = smf.get_prop(fmri, "restarter/state")
        readonly = smf.get_prop(fmri, "pkg/readonly")
        standalone = smf.get_prop(fmri, "pkg/standalone")

        if (state == "online" and
            readonly == "true" and
            standalone == "false"):
            repo_info.append((repo_root,
                _affix_slash(repo_prefix), writable_root))
    if not repo_info:
        raise DepotException(_(
            "No online, readonly, non-standalone instances of "
            "{0} found.").format(PKG_SERVER_SVC))
    return repo_info


def _check_unique_repo_properties(repo_info):
    """Determine whether the repository root, and supplied prefixes are
    unique.  The prefixes allow two or more repositories that both contain
    the same publisher to be differentiated in the Apache configuration, so
    that requests are routed to the correct repository."""

    prefixes = set()
    roots = set()
    writable_roots = set()
    errors = []
    for root, prefix, writable_root in repo_info:
        if prefix in prefixes:
            errors.append(_("prefix {0} cannot be used more than "
                "once in a given depot configuration").format(
                prefix))
        prefixes.add(prefix)
        if root in roots:
            errors.append(_("repo_root {0} cannot be used more "
                "than once in a given depot configuration").format(
                root))
        roots.add(root)
        if writable_root and writable_root in writable_roots:
            errors.append(_("writable_root {0} cannot be used more "
                "than once in a given depot configuration").format(
                writable_root))
        writable_roots.add(writable_root)
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
    return "{0}/".format(val)


def _update_smf_props(smf_fmri, prop_list, orig, dest):
    """Update the smf props after the new prop values are generated."""

    smf_instances = smf.check_fmris(None, smf_fmri)
    for fmri in smf_instances:
        refresh = False
        for i in range(len(prop_list)):
            if orig[i] != dest[i]:
                smf.set_prop(fmri, prop_list[i], dest[i])
                refresh = True
        if refresh:
            smf.refresh(fmri)


def main_func():

    # some sensible defaults
    host = "0.0.0.0"
    # the port we listen on
    port = None
    # a list of (repo_dir, repo_prefix) tuples
    repo_info = []
    # the path where we store disk caches
    cache_dir = None
    # our maximum cache size, in megabytes
    cache_size = 0
    # whether we're writing a full httpd.conf, or just a fragment
    fragment = False
    # Whether we support https service.
    https = False
    # The location of server certificate file.
    ssl_cert_file = ""
    # The location of server key file.
    ssl_key_file = ""
    # The location of the server ca certificate file.
    ssl_ca_cert_file = ""
    # The location of the server ca key file.
    ssl_ca_key_file = ""
    # Directory for storing generated certificates and keys
    cert_key_dir = ""
    # SSL certificate chain file path if the server certificate is not
    # signed by the top level CA.
    ssl_cert_chain_file = ""
    # The pkg/depot smf instance fmri.
    smf_fmri = ""
    # an optional url-prefix, used to separate pkg5 services from the rest
    # of the webserver url namespace, only used when running in fragment
    # mode, otherwise we assume we're the only service running on this
    # web server instance, and control the entire server URL namespace.
    sroot = ""
    # the path where our Mako templates and wsgi scripts are stored
    template_dir = "/etc/pkg/depot"
    option_T = False
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

    writable_root_set = False
    try:
        opts, pargs = getopt.getopt(sys.argv[1:],
            "Ac:d:Fh:l:P:p:r:Ss:t:T:?", ["help", "debug=", "https",
            "cert=", "key=", "ca-cert=", "ca-key=", "cert-chain=",
            "cert-key-dir=", "smf-fmri="])
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
                option_T = True
            elif opt == "-t":
                server_type = arg
            elif opt == "-d":
                if "=" not in arg:
                    usage(_("-d arguments must be in the "
                        "form <prefix>=<repo path>"
                        "[=writable root]"))
                components = arg.split("=", 2)
                if len(components) == 3:
                    prefix, root, writable_root = components
                    writable_root_set = True
                elif len(components) == 2:
                    prefix, root = components
                    writable_root = None
                repo_info.append((root, _affix_slash(prefix),
                    writable_root))
            elif opt == "-P":
                sroot = _affix_slash(arg)
            elif opt == "-F":
                fragment = True
            elif opt == "-S":
                use_smf_instances = True
            elif opt == "-A":
                allow_refresh = True
            elif opt == "--https":
                https = True
            elif opt == "--cert":
                ssl_cert_file = arg
            elif opt == "--key":
                ssl_key_file = arg
            elif opt == "--ca-cert":
                ssl_ca_cert_file = arg
            elif opt == "--ca-key":
                ssl_ca_key_file = arg
            elif opt == "--cert-chain":
                ssl_cert_chain_file = arg
            elif opt == "--cert-key-dir":
                cert_key_dir = arg
            elif opt == "--smf-fmri":
                smf_fmri = arg
            elif opt == "--debug":
                try:
                    key, value = arg.split("=", 1)
                except (AttributeError, ValueError):
                    usage(
                        _("{opt} takes argument of form "
                        "name=value, not {arg}").format(
                        opt=opt, arg=arg))
                DebugValues[key] = value
            else:
                usage("unknown option {0}".format(opt))

    except getopt.GetoptError as e:
        usage(_("illegal global option -- {0}").format(e.opt))

    if not runtime_dir:
        usage(_("required runtime dir option -r missing."))

    # we need a cache_dir to store the SSLSessionCache
    if not cache_dir and not fragment:
        usage(_("cache_dir option -c is required if -F is not used."))

    if not fragment and not port:
        usage(_("required port option -p missing."))

    if not use_smf_instances and not repo_info:
        usage(_("at least one -d option is required if -S is "
            "not used."))

    if repo_info and use_smf_instances:
        usage(_("cannot use -d and -S together."))

    if https:
        if fragment:
            usage(_("https configuration is not supported in "
                "fragment mode."))
        if bool(ssl_cert_file) != bool(ssl_key_file):
            usage(_("certificate and key files must be presented "
                "at the same time."))
        elif not ssl_cert_file and not ssl_key_file:
            if not cert_key_dir:
                usage(_("cert-key-dir option is require to "
                    "store the generated certificates and keys"))
            if ssl_cert_chain_file:
                usage(_("Cannot use --cert-chain without "
                    "--cert and --key"))
            if bool(ssl_ca_cert_file) != bool(ssl_ca_key_file):
                usage(_("server CA certificate and key files "
                    "must be presented at the same time."))
            # If fmri is specified for pkg/depot instance, we need
            # record the proporty values for updating.
            if smf_fmri:
                orig = (ssl_ca_cert_file, ssl_ca_key_file,
                    ssl_cert_file, ssl_key_file)
            try:
                ssl_ca_cert_file, ssl_ca_key_file, ssl_cert_file, \
                    ssl_key_file = \
                    _generate_server_cert_key(host, port,
                    ca_cert_file=ssl_ca_cert_file,
                    ca_key_file=ssl_ca_key_file,
                    output_dir=cert_key_dir)
                if ssl_ca_cert_file:
                    msg(_("Server CA certificate is "
                        "located at {0}. Please deploy it "
                        "into /etc/certs/CA directory of "
                        "each client.").format(
                        ssl_ca_cert_file))
            except (DepotException, EnvironmentError) as e:
                error(e)
                return EXIT_OOPS

            # Update the pkg/depot instance smf properties if
            # anything changes.
            if smf_fmri:
                dest = (ssl_ca_cert_file, ssl_ca_key_file,
                    ssl_cert_file, ssl_key_file)
                if orig != dest:
                    prop_list = ["config/ssl_ca_cert_file",
                        "config/ssl_ca_key_file",
                        "config/ssl_cert_file",
                        "config/ssl_key_file"]
                    try:
                        _update_smf_props(smf_fmri, prop_list,
                            orig, dest)
                    except (smf.NonzeroExitException,
                        RuntimeError) as e:
                        error(e)
                        return EXIT_OOPS
        else:
            if not os.path.exists(ssl_cert_file):
                error(_("User provided server certificate "
                    "file {0} does not exist.").format(
                    ssl_cert_file))
                return EXIT_OOPS
            if not os.path.exists(ssl_key_file):
                error(_("User provided server key file {0} "
                    "does not exist.").format(ssl_key_file))
                return EXIT_OOPS
            if ssl_cert_chain_file and not os.path.exists(
                ssl_cert_chain_file):
                error(_("User provided certificate chain file "
                    "{0} does not exist.").format(
                    ssl_cert_chain_file))
                return EXIT_OOPS
    else:
        if ssl_cert_file or ssl_key_file or ssl_ca_cert_file \
            or ssl_ca_key_file or ssl_cert_chain_file:
            usage(_("certificate or key files are given before "
                "https service is turned on. Use --https to turn "
                "on the service."))
        if smf_fmri:
            usage(_("cannot use --smf-fmri without --https."))

    # We can't support httpd.conf fragments with writable root, because
    # we don't have the mod_wsgi app that can build the index or serve
    # search requests everywhere the fragments might be used. (eg. on
    # non-Solaris systems)
    if writable_root_set and fragment:
        usage(_("cannot use -d with writable roots and -F together."))

    if fragment and port:
        usage(_("cannot use -F and -p together."))

    if fragment and allow_refresh:
        usage(_("cannot use -F and -A together."))

    if sroot and not fragment:
        usage(_("cannot use -P without -F."))

    if use_smf_instances:
        try:
            repo_info = get_smf_repo_info()
        except DepotException as e:
            error(e)

    # We can produce configuration for different HTTP servers.
    # For now, we only support "apache2" (apache 2.4).
    if server_type not in KNOWN_SERVER_TYPES:
        usage(_("unknown server type {type}. "
            "Known types are: {known}").format(
            type=server_type,
            known=", ".join(KNOWN_SERVER_TYPES)))

    try:
        _check_unique_repo_properties(repo_info)
    except DepotException as e:
        error(e)

    ret = refresh_conf(repo_info, log_dir, host, port, runtime_dir,
        template_dir, cache_dir, cache_size, sroot, fragment=fragment,
        allow_refresh=allow_refresh, ssl_cert_file=ssl_cert_file,
        ssl_key_file=ssl_key_file, ssl_cert_chain_file=ssl_cert_chain_file)
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
        except (MemoryError, EnvironmentError) as __e:
            if isinstance(__e, EnvironmentError) and \
                __e.errno != errno.ENOMEM:
                raise
            error("\n" + misc.out_of_memory())
            __ret = EXIT_OOPS
    except SystemExit:
        raise
    except (PipeError, KeyboardInterrupt):
        # Don't display any messages here to prevent possible further
        # broken pipe (EPIPE) errors.
        __ret = EXIT_OOPS
    except Exception:
        traceback.print_exc()
        error(traceback_str)
        __ret = EXIT_FATAL
    return __ret


if __name__ == "__main__":
    misc.setlocale(locale.LC_ALL, "", error)
    gettext.install("pkg", "/usr/share/locale")

    # By default, hide all warnings from users.
    if not sys.warnoptions:
        warnings.simplefilter("ignore")

    __retval = handle_errors(main_func)
    try:
        logging.shutdown()
    except IOError:
        # Ignore python's spurious pipe problems.
        pass
    sys.exit(__retval)
