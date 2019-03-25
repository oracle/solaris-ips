#!/usr/bin/python2.7 -Es
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
# Copyright (c) 2010, 2019, Oracle and/or its affiliates. All rights reserved.
#
import pkg.no_site_packages

PKG_CLIENT_NAME = "pkgrepo"

# pkgrepo exit codes
EXIT_OK      = 0
EXIT_OOPS    = 1
EXIT_BADOPT  = 2
EXIT_PARTIAL = 3
EXIT_DIFF = 10

# listing constants
LISTING_FORMATS = ("default", "json", "json-formatted", "tsv")

# diff type
MINUS = -1
PLUS = 1
COMMON = 0
diff_type_f = {MINUS: "- ", PLUS: "+ ", COMMON: ""}

# globals
tmpdirs = []

import atexit
import collections
import copy
import errno
import getopt
import gettext
import locale
import logging
import os
import operator
import shlex
import shutil
import six
import sys
import tempfile
import textwrap
import traceback
import warnings
import itertools
from imp import reload

from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues
from pkg.misc import msg, PipeError
from prettytable import PrettyTable
import pkg
import pkg.catalog
import pkg.client.api_errors as apx
import pkg.client.pkgdefs as pkgdefs
import pkg.client.progress
import pkg.client.publisher as publisher
import pkg.client.transport.transport as transport
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.server.repository as sr
import simplejson as json

logger = global_settings.logger

@atexit.register
def cleanup():
        """To be called at program finish."""
        for d in tmpdirs:
                shutil.rmtree(d, True)


def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if cmd:
                text = "{0}: {1}".format(cmd, text)
                pkg_cmd = "pkgrepo "
        else:
                pkg_cmd = "pkgrepo: "

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


def get_tracker(quiet=False):
        if quiet:
                progtrack = pkg.client.progress.QuietProgressTracker()
        else:
                try:
                        progtrack = \
                            pkg.client.progress.FancyUNIXProgressTracker()
                except pkg.client.progress.ProgressTrackerException:
                        progtrack = \
                            pkg.client.progress.CommandLineProgressTracker()
        return progtrack


def usage(usage_error=None, cmd=None, retcode=2, full=False):
        """Emit a usage message and optionally prefix it with a more
        specific error message.  Causes program to exit.
        """

        if usage_error:
                error(usage_error, cmd=cmd)

        if not full:
                # The full usage message isn't desired.
                logger.error(_("Try `pkgrepo --help or -?' for more "
                    "information."))
                sys.exit(retcode)

        msg(_("""\
Usage:
        pkgrepo [options] command [cmd_options] [operands]

Subcommands:
     pkgrepo create [--version ver] uri_or_path

     pkgrepo add-publisher -s repo_uri_or_path publisher ...

     pkgrepo remove-publisher [-n] [--synchronous] -s repo_uri_or_path
         publisher ...

     pkgrepo get [-F format] [-p publisher ...] -s repo_uri_or_path
         [--key ssl_key ... --cert ssl_cert ...] [section/property ...]

     pkgrepo info [-F format] [-H] [-p publisher ...] -s repo_uri_or_path
         [--key ssl_key ... --cert ssl_cert ...]

     pkgrepo list [-F format] [-H] [-p publisher ...] -s repo_uri_or_path
         [--key ssl_key ... --cert ssl_cert ...] [pkg_fmri_pattern ...]

     pkgrepo contents [-m] [-t action_type ...] -s repo_uri_or_path
         [--key ssl_key ... --cert ssl_cert ...] [pkg_fmri_pattern ...]

     pkgrepo rebuild [-p publisher ...] -s repo_uri_or_path [--key ssl_key ...
         --cert ssl_cert ...] [--no-catalog] [--no-index]

     pkgrepo refresh [-p publisher ...] -s repo_uri_or_path [--key ssl_key ...
         --cert ssl_cert ...] [--no-catalog] [--no-index]

     pkgrepo remove [-n] [-p publisher ...] -s repo_uri_or_path
         pkg_fmri_pattern ...

     pkgrepo set [-p publisher ...] -s repo_uri_or_path
         section/property[+|-]=[value] ... or
         section/property[+|-]=([value]) ...

     pkgrepo verify [-d] [-p publisher ...] [-i ignored_dep_file ...]
         [--disable verification ...] -s repo_uri_or_path

     pkgrepo fix [-v] [-p publisher ...] -s repo_uri_or_path

     pkgrepo diff [-vq] [--strict] [--parsable] [-p publisher ...]
         -s first_repo_uri_or_path [--key ssl_key ... --cert ssl_cert ...]
         -s second_repo_uri_or_path [--key ssl_key ... --cert ssl_cert ...]

     pkgrepo help
     pkgrepo version

Options:
        --help or -?
            Displays a usage message."""))

        sys.exit(retcode)


class OptionError(Exception):
        """Option exception. """

        def __init__(self, *args):
                Exception.__init__(self, *args)


def parse_uri(uri):
        """Parse the repository location provided and attempt to transform it
        into a valid repository URI.
        """

        return publisher.RepositoryURI(misc.parse_uri(uri))


def subcmd_remove(conf, args):
        subcommand = "remove"

        opts, pargs = getopt.getopt(args, "np:s:")

        dry_run = False
        pubs = set()
        for opt, arg in opts:
                if opt == "-n":
                        dry_run = True
                elif opt == "-p":
                        pubs.add(arg)
                elif opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)

        if not pargs:
                usage(_("At least one package pattern must be provided."),
                    cmd=subcommand)

        # Get repository object.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)
        repo = get_repo(conf, read_only=False, subcommand=subcommand)

        if "all" in pubs:
                pubs = set()

        # Find matching packages.
        try:
                matching, refs = repo.get_matching_fmris(pargs, pubs=pubs)
        except apx.PackageMatchErrors as e:
                error(str(e), cmd=subcommand)
                return EXIT_OOPS

        if dry_run:
                # Don't make any changes; display list of packages to be
                # removed and exit.
                packages = set(f for m in matching.values() for f in m)
                count = len(packages)
                plist = "\n".join("\t{0}".format(
                    p.get_fmri(include_build=False))
                    for p in sorted(packages))
                logger.info(_("{count:d} package(s) will be removed:\n"
                    "{plist}").format(**locals()))
                return EXIT_OK

        progtrack = get_tracker()
        packages = collections.defaultdict(list)
        for m in matching.values():
                for f in m:
                        packages[f.publisher].append(f)

        for pub in packages:
                logger.info(
                    _("Removing packages for publisher {0} ...").format(pub))
                repo.remove_packages(packages[pub], progtrack=progtrack,
                    pub=pub)
                if len(packages) > 1:
                        # Add a newline between each publisher.
                        logger.info("")

        return EXIT_OK


def get_repo(conf, allow_invalid=False, read_only=True, subcommand=None):
        """Return the repository object for current program configuration.

        'allow_invalid' specifies whether potentially corrupt repositories are
        allowed; should only be True if performing a rebuild operation."""

        repo_uri = conf["repo_uri"]
        if repo_uri.scheme != "file":
                usage(_("Network repositories are not currently supported "
                    "for this operation."), cmd=subcommand)

        path = repo_uri.get_pathname()
        if not path:
                # Bad URI?
                raise sr.RepositoryInvalidError(str(repo_uri))
        return sr.Repository(allow_invalid=allow_invalid, read_only=read_only,
            root=path)


def setup_transport(repo_uri, subcommand=None, prefix=None, verbose=False,
    remote_prefix=True, ssl_key=None, ssl_cert=None):
        if not repo_uri:
                usage(_("No repository location specified."), cmd=subcommand)

        global tmpdirs
        temp_root = misc.config_temp_root()

        tmp_dir = tempfile.mkdtemp(dir=temp_root)
        tmpdirs.append(tmp_dir)

        incoming_dir = tempfile.mkdtemp(dir=temp_root)
        tmpdirs.append(incoming_dir)

        cache_dir = tempfile.mkdtemp(dir=temp_root)
        tmpdirs.append(cache_dir)

        # Create transport and transport config.
        xport, xport_cfg = transport.setup_transport()
        xport_cfg.add_cache(cache_dir, readonly=False)
        xport_cfg.incoming_root = incoming_dir
        xport_cfg.pkg_root = tmp_dir

        if not prefix:
                pub = "target"
        else:
                pub = prefix

        # Configure target publisher.
        src_pub = transport.setup_publisher(str(repo_uri), pub, xport,
            xport_cfg, remote_prefix=remote_prefix, ssl_key=ssl_key,
            ssl_cert=ssl_cert)

        return xport, src_pub, tmp_dir

def subcmd_add_publisher(conf, args):
        """Add publisher(s) to the specified repository."""

        subcommand = "add-publisher"

        opts, pargs = getopt.getopt(args, "s:")
        for opt, arg in opts:
                if opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)

        repo_uri = conf.get("repo_uri", None)
        if not repo_uri:
                usage(_("No repository location specified."), cmd=subcommand)
        if repo_uri.scheme != "file":
                usage(_("Network repositories are not currently supported "
                    "for this operation."), cmd=subcommand)

        if not pargs:
                usage(_("At least one publisher must be specified"),
                    cmd=subcommand)

        abort = False
        for pfx in pargs:
                if not misc.valid_pub_prefix(pfx):
                        error(_("Invalid publisher prefix '{0}'").format(pfx),
                            cmd=subcommand)
                        abort = True
        if abort:
                return EXIT_OOPS

        repo = get_repo(conf, read_only=False, subcommand=subcommand)
        make_default = not repo.publishers
        existing = repo.publishers & set(pargs)

        # Elide the publishers that already exist, but retain the order
        # publishers were specified in.
        new_pubs = [
            pfx for pfx in pargs
            if pfx not in repo.publishers
        ]

        # Tricky logic; _set_pub will happily add new publishers if necessary
        # and not set any properties if you didn't specify any.
        rval = _set_pub(conf, subcommand, {}, new_pubs, repo)

        if make_default:
                # No publisher existed previously, so set the default publisher
                # to be the first new one that was added.
                _set_repo(conf, subcommand, { "publisher": {
                    "prefix": new_pubs[0] } }, repo)

        if rval == EXIT_OK and existing:
                # Some of the publishers that were requested for addition
                # were already known.
                error(_("specified publisher(s) already exist: {0}").format(
                    ", ".join(existing)), cmd=subcommand)
                if new_pubs:
                        return EXIT_PARTIAL
                return EXIT_OOPS
        return rval

def subcmd_remove_publisher(conf, args):
        """Remove publisher(s) from a repository"""

        subcommand = "remove-publisher"

        dry_run = False
        synch = False
        opts, pargs = getopt.getopt(args, "ns:", ["synchronous"])
        for opt, arg in opts:
                if opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt == "-n":
                        dry_run = True
                elif opt == "--synchronous":
                        synch = True
        repo_uri = conf.get("repo_uri", None)
        if not repo_uri:
                usage(_("No repository location specified."), cmd=subcommand)
        if repo_uri.scheme != "file":
                usage(_("Network repositories are not currently supported "
                    "for this operation."), cmd=subcommand)

        if not pargs:
                usage(_("At least one publisher must be specified"),
                    cmd=subcommand)

        inv_pfxs = []
        for pfx in pargs:
                if not misc.valid_pub_prefix(pfx):
                        inv_pfxs.append(pfx)

        if inv_pfxs:
                error(_("Invalid publisher prefix(es):\n {0}").format(
                    "\n ".join(inv_pfxs)), cmd=subcommand)
                return EXIT_OOPS

        repo = get_repo(conf, read_only=False, subcommand=subcommand)
        existing = repo.publishers & set(pargs)
        noexisting = [pfx for pfx in pargs
            if pfx not in repo.publishers]
        # Publishers left if remove succeeds.
        left = [pfx for pfx in repo.publishers if pfx not in pargs]

        if noexisting:
                error(_("The following publisher(s) could not be found:\n "
                    "{0}").format("\n ".join(noexisting)), cmd=subcommand)
                return EXIT_OOPS

        logger.info(_("Removing publisher(s)"))
        for pfx in existing:
                rstore = repo.get_pub_rstore(pfx)
                numpkg = rstore.catalog.package_count
                logger.info(_("\'{pfx}\'\t({num} package(s))").format(
                    pfx=pfx, num=str(numpkg)))

        if dry_run:
                return EXIT_OK

        defaultpfx = repo.cfg.get_property("publisher", "prefix")
        repo_path = repo_uri.get_pathname()

        repo.remove_publisher(existing, repo_path, synch)
        # Change the repository publisher/prefix property, if necessary.
        if defaultpfx in existing:
                if len(left) == 1:
                        _set_repo(conf, subcommand, { "publisher" :  {
                            "prefix" :  left[0]} }, repo)
                        msg(_("The default publisher was removed."
                            " Setting 'publisher/prefix' to '{0}',"
                            " the only publisher left").format(left[0]))
                else:
                        _set_repo(conf, subcommand, { "publisher": {
                            "prefix" :  ""} }, repo)
                        msg(_("The default publisher was removed."
                            " The 'publisher/prefix' property has been"
                            " unset"))

        return EXIT_OK

def subcmd_create(conf, args):
        """Create a package repository at the given location."""

        subcommand = "create"

        opts, pargs = getopt.getopt(args, "s:", ["version="])

        version = None
        for opt, arg in opts:
                if opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt == "--version":
                        # This option is currently private and allows creating a
                        # repository with a specific format based on version.
                        try:
                                version = int(arg)
                        except ValueError:
                                usage(_("Version must be an integer value."),
                                    cmd=subcommand)

        if len(pargs) > 1:
                usage(_("Only one repository location may be specified."),
                    cmd=subcommand)
        elif pargs:
                conf["repo_uri"] = parse_uri(pargs[0])

        repo_uri = conf.get("repo_uri", None)
        if not repo_uri:
                usage(_("No repository location specified."), cmd=subcommand)
        if repo_uri.scheme != "file":
                usage(_("Network repositories are not currently supported "
                    "for this operation."), cmd=subcommand)

        # Attempt to create a repository at the specified location.  Allow
        # whatever exceptions are raised to bubble up.
        sr.repository_create(repo_uri, version=version)

        return EXIT_OK


def subcmd_get(conf, args):
        """Display repository properties."""

        subcommand = "get"
        omit_headers = False
        out_format = "default"
        pubs = set()
        key = None
        cert = None

        opts, pargs = getopt.getopt(args, "F:Hp:s:", ["key=", "cert="])
        for opt, arg in opts:
                if opt == "-F":
                        if arg not in LISTING_FORMATS:
                                raise apx.InvalidOptionError(
                                    apx.InvalidOptionError.ARG_INVALID,
                                    [arg, opt])
                        out_format = arg
                elif opt == "-H":
                        omit_headers = True
                elif opt == "-p":
                        pubs.add(arg)
                elif opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt == "--key":
                        key = arg
                elif opt == "--cert":
                        cert = arg

        # Setup transport so configuration can be retrieved.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)
        xport, xpub, tmp_dir = setup_transport(conf.get("repo_uri"),
            subcommand=subcommand, ssl_key=key, ssl_cert=cert)

        # Get properties.
        if pubs:
                return _get_pub(conf, subcommand, xport, xpub, omit_headers,
                    out_format, pubs, pargs)
        return _get_repo(conf, subcommand, xport, xpub, omit_headers,
            out_format, pargs)


def _get_repo(conf, subcommand, xport, xpub, omit_headers, out_format, pargs):
        """Display repository properties."""

        # Configuration index is indexed by section name and property name.
        # Retrieve and flatten it to simplify listing process.
        stat_idx = xport.get_status(xpub)
        cfg_idx = stat_idx.get("repository", {}).get("configuration", {})
        props = set()

        # Set minimum widths for section and property name columns by using the
        # length of the column headers.
        max_sname_len = len(_("SECTION"))
        max_pname_len = len(_("PROPERTY"))

        for sname in cfg_idx:
                max_sname_len = max(max_sname_len, len(sname))
                for pname in cfg_idx[sname]:
                        max_pname_len = max(max_pname_len, len(pname))
                        props.add("/".join((sname, pname)))

        req_props = set(pargs)
        if len(req_props) >= 1:
                found = props & req_props
                notfound = req_props - found
                del props
        else:
                found = props
                notfound = set()

        def gen_listing():
                for prop in sorted(found):
                        sname, pname = prop.rsplit("/", 1)
                        sval = cfg_idx[sname][pname]
                        yield {
                            "section": sname,
                            "property": pname,
                            "value": sval,
                        }

        #    SECTION PROPERTY VALUE
        #    <sec_1> <prop_1> <prop_1_value>
        #    <sec_2> <prop_2> <prop_2_value>
        #    ...
        field_data = {
            "section" : [("default", "json", "tsv"), _("SECTION"), ""],
            "property" : [("default", "json", "tsv"), _("PROPERTY"), ""],
            "value" : [("default", "json", "tsv"), _("VALUE"), ""],
        }
        desired_field_order = (_("SECTION"), _("PROPERTY"), _("VALUE"))

        # Default output formatting.
        def_fmt = "{0:" + str(max_sname_len) + "} {1:" + str(max_pname_len) + \
            "} {2}"

        if found or (not req_props and out_format == "default"):
                # print without trailing newline.
                sys.stdout.write(misc.get_listing(desired_field_order,
                    field_data, gen_listing(), out_format, def_fmt,
                    omit_headers))

        if found and notfound:
                return EXIT_PARTIAL
        if req_props and not found:
                if out_format == "default":
                        # Don't pollute other output formats.
                        error(_("no matching properties found"),
                            cmd=subcommand)
                return EXIT_OOPS
        return EXIT_OK


def _get_matching_pubs(subcommand, pubs, xport, xpub, out_format="default",
    use_transport=False, repo_uri=None):

        # Retrieve publisher information.
        pub_data = xport.get_publisherdata(xpub)
        known_pubs = set(p.prefix for p in pub_data)
        if len(pubs) > 0 and "all" not in pubs:
                found = known_pubs & pubs
                notfound = pubs - found
                pub_data = [p for p in pub_data if p.prefix in found]
        else:
                found = known_pubs
                notfound = set()

        if use_transport:
                # Assign transport information.
                for p in pub_data:
                        p.repository = xpub.repository

        # Establish initial return value and perform early exit if appropriate.
        rval = EXIT_OK
        if found and notfound:
                rval = EXIT_PARTIAL
        elif pubs and not found:
                if out_format == "default":
                        # Don't pollute other output formats.
                        err_msg = _("no matching publishers found")
                        if repo_uri:
                                err_msg = _("no matching publishers found in "
                                    "repository: {0}").format(repo_uri)
                        error(err_msg, cmd=subcommand)
                return EXIT_OOPS, None, None
        return rval, found, pub_data


def _get_pub(conf, subcommand, xport, xpub, omit_headers, out_format, pubs,
    pargs):
        """Display publisher properties."""

        rval, found, pub_data = _get_matching_pubs(subcommand, pubs, xport,
            xpub, out_format=out_format)
        if rval == EXIT_OOPS:
                return rval

        # Set minimum widths for section and property name columns by using the
        # length of the column headers and data.
        max_pubname_len = str(max(
            [len(_("PUBLISHER"))] + [len(p) for p in found]
        ))
        max_sname_len = len(_("SECTION"))
        max_pname_len = len(_("PROPERTY"))

        # For each requested publisher, retrieve the requested property data.
        pub_idx = {}
        for pub in pub_data:
                pub_idx[pub.prefix] = {
                    "publisher": {
                        "alias": pub.alias,
                        "prefix": pub.prefix,
                    },
                }

                pub_repo = pub.repository
                if pub_repo:
                        pub_idx[pub.prefix]["repository"] = {
                            "collection-type": pub_repo.collection_type,
                            "description": pub_repo.description,
                            "legal-uris": pub_repo.legal_uris,
                            "mirrors": pub_repo.mirrors,
                            "name": pub_repo.name,
                            "origins": pub_repo.origins,
                            "refresh-seconds": pub_repo.refresh_seconds,
                            "registration-uri": pub_repo.registration_uri,
                            "related-uris": pub_repo.related_uris,
                        }
                else:
                        pub_idx[pub.prefix]["repository"] = {
                            "collection-type": "core",
                            "description": "",
                            "legal-uris": [],
                            "mirrors": [],
                            "name": "",
                            "origins": [],
                            "refresh-seconds": "",
                            "registration-uri": "",
                            "related-uris": [],
                        }

        # Determine possible set of properties and lengths.
        props = set()
        for pub in pub_idx:
                for sname in pub_idx[pub]:
                        max_sname_len = max(max_sname_len, len(sname))
                        for pname in pub_idx[pub][sname]:
                                max_pname_len = max(max_pname_len, len(pname))
                                props.add("/".join((sname, pname)))

        # Determine properties to display.
        req_props = set(pargs)
        if len(req_props) >= 1:
                found = props & req_props
                notfound = req_props - found
                del props
        else:
                found = props
                notfound = set()

        def gen_listing():
                for pub in sorted(pub_idx.keys()):
                        for prop in sorted(found):
                                sname, pname = prop.rsplit("/", 1)
                                sval = pub_idx[pub][sname][pname]
                                yield {
                                    "publisher": pub,
                                    "section": sname,
                                    "property": pname,
                                    "value": sval,
                                }

        #    PUBLISHER SECTION PROPERTY VALUE
        #    <pub_1>   <sec_1> <prop_1> <prop_1_value>
        #    <pub_1>   <sec_2> <prop_2> <prop_2_value>
        #    ...
        field_data = {
            "publisher" : [("default", "json", "tsv"), _("PUBLISHER"), ""],
            "section" : [("default", "json", "tsv"), _("SECTION"), ""],
            "property" : [("default", "json", "tsv"), _("PROPERTY"), ""],
            "value" : [("default", "json", "tsv"), _("VALUE"), ""],
        }
        desired_field_order = (_("PUBLISHER"), _("SECTION"), _("PROPERTY"),
            _("VALUE"))

        # Default output formatting.
        def_fmt = "{0:" + str(max_pubname_len) + "} {1:" + str(max_sname_len) + \
            "} {2:" + str(max_pname_len) + "} {3}"

        if found or (not req_props and out_format == "default"):
                # print without trailing newline.
                sys.stdout.write(misc.get_listing(desired_field_order,
                    field_data, gen_listing(), out_format, def_fmt,
                    omit_headers))

        if found and notfound:
                rval = EXIT_PARTIAL
        if req_props and not found:
                if out_format == "default":
                        # Don't pollute other output formats.
                        error(_("no matching properties found"),
                            cmd=subcommand)
                rval = EXIT_OOPS
        return rval


def subcmd_info(conf, args):
        """Display a list of known publishers and a summary of known packages
        and when the package data for the given publisher was last updated.
        """

        subcommand = "info"
        omit_headers = False
        out_format = "default"
        pubs = set()
        key = None
        cert = None

        opts, pargs = getopt.getopt(args, "F:Hp:s:", ["key=", "cert="])
        for opt, arg in opts:
                if opt == "-F":
                        if arg not in LISTING_FORMATS:
                                raise apx.InvalidOptionError(
                                    apx.InvalidOptionError.ARG_INVALID,
                                    [arg, opt])
                        out_format = arg
                elif opt == "-H":
                        omit_headers = True
                elif opt == "-p":
                        pubs.add(arg)
                elif opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt == "--key":
                        key = arg
                elif opt == "--cert":
                        cert = arg

        if pargs:
                usage(_("command does not take operands"), cmd=subcommand)

        # Setup transport so status can be retrieved.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)
        xport, xpub, tmp_dir = setup_transport(conf.get("repo_uri"),
            subcommand=subcommand, ssl_key=key, ssl_cert=cert)

        # Retrieve repository status information.
        stat_idx = xport.get_status(xpub)
        pub_idx = stat_idx.get("repository", {}).get("publishers", {})
        if len(pubs) > 0 and "all" not in pubs:
                found = set(pub_idx.keys()) & pubs
                notfound = pubs - found
        else:
                found = set(pub_idx.keys())
                notfound = set()

        def gen_listing():
                for pfx in sorted(found):
                        pdata = pub_idx[pfx]
                        pkg_count = pdata.get("package-count", 0)
                        last_update = pdata.get("last-catalog-update", "")
                        if last_update:
                                # Reformat the date into something more user
                                # friendly (and locale specific).
                                last_update = pkg.catalog.basic_ts_to_datetime(
                                    last_update)
                                last_update = "{0}Z".format(
                                    pkg.catalog.datetime_to_ts(last_update))
                        rstatus = _(pub_idx[pfx].get("status", "online"))
                        yield {
                            "publisher": pfx,
                            "packages": pkg_count,
                            "status": rstatus,
                            "updated": last_update,
                        }

        #    PUBLISHER PACKAGES        STATUS   UPDATED
        #    <pub_1>   <num_uniq_pkgs> <status> <cat_last_modified>
        #    <pub_2>   <num_uniq_pkgs> <status> <cat_last_modified>
        #    ...
        field_data = {
            "publisher" : [("default", "json", "tsv"), _("PUBLISHER"), ""],
            "packages" : [("default", "json", "tsv"), _("PACKAGES"), ""],
            "status" : [("default", "json", "tsv"), _("STATUS"), ""],
            "updated" : [("default", "json", "tsv"), _("UPDATED"), ""],
        }

        desired_field_order = (_("PUBLISHER"), "", _("PACKAGES"), _("STATUS"),
            _("UPDATED"))

        # Default output formatting.
        pub_len = str(max(
            [len(desired_field_order[0])] + [len(p) for p in found]
        ))
        def_fmt = "{0:" + pub_len + "} {1:8} {2:16} {3}"

        if found or (not pubs and out_format == "default"):
                # print without trailing newline.
                sys.stdout.write(misc.get_listing(desired_field_order,
                    field_data, gen_listing(), out_format, def_fmt,
                    omit_headers))

        if found and notfound:
                return EXIT_PARTIAL
        if pubs and not found:
                if out_format == "default":
                        # Don't pollute other output formats.
                        error(_("no matching publishers found"),
                            cmd=subcommand)
                return EXIT_OOPS
        return EXIT_OK

def subcmd_list(conf, args):
        """List all packages matching the specified patterns."""

        subcommand = "list"
        omit_headers = False
        out_format = "default"
        pubs = set()
        key = None
        cert = None

        opts, pargs = getopt.getopt(args, "F:Hp:s:", ["key=", "cert="])
        for opt, arg in opts:
                if opt == "-F":
                        if arg not in LISTING_FORMATS:
                                raise apx.InvalidOptionError(
                                    apx.InvalidOptionError.ARG_INVALID,
                                    [arg, opt])
                        out_format = arg
                elif opt == "-H":
                        omit_headers = True
                elif opt == "-p":
                        pubs.add(arg)
                elif opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt == "--key":
                        key = arg
                elif opt == "--cert":
                        cert = arg


        # Setup transport so configuration can be retrieved.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)
        xport, xpub, tmp_dir = setup_transport(conf.get("repo_uri"),
            subcommand=subcommand, ssl_key=key, ssl_cert=cert)

        rval, found, pub_data = _get_matching_pubs(subcommand, pubs, xport,
            xpub, out_format=out_format, use_transport=True)
        if rval == EXIT_OOPS:
                return rval

        refresh_pub(pub_data, xport)
        listed = {}
        matched = set()
        unmatched = set()

        def gen_listing():
                collect_attrs = out_format.startswith("json")
                for pub in sorted(pub_data):
                        cat = pub.catalog
                        for f, states, attrs in cat.gen_packages(
                            collect_attrs=collect_attrs, matched=matched,
                            patterns=pargs, pubs=[pub.prefix],
                            unmatched=unmatched, return_fmris=True):
                                if not listed:
                                        listed["packages"] = True

                                state = None
                                if out_format == "default" or \
                                    out_format == "tsv":
                                        if pkgdefs.PKG_STATE_OBSOLETE in \
                                            states:
                                                state = "o"
                                        elif pkgdefs.PKG_STATE_RENAMED in \
                                            states:
                                                state = "r"

                                if out_format == "default":
                                    fver = str(f.version.get_version(
                                        include_build=False))
                                    ffmri = str(f.get_fmri(include_build=False))
                                else:
                                    fver = str(f.version)
                                    ffmri = str(f)

                                ret = {
                                    "publisher": f.publisher,
                                    "name": f.pkg_name,
                                    "version": fver,
                                    "release": str(f.version.release),
                                    "build-release":
                                        str(f.version.build_release),
                                    "branch": str(f.version.branch),
                                    "timestamp":
                                        str(f.version.timestr),
                                    "pkg.fmri": ffmri,
                                    "short_state": state,
                                }

                                for attr in attrs:
                                        ret[attr] = []
                                        for mods in attrs[attr]:
                                                d = dict(mods)
                                                d["value"] = \
                                                    attrs[attr][mods]
                                                ret[attr].append(d)
                                yield ret

                        unmatched.difference_update(matched)

        field_data = {
            "publisher": [("default", "json", "tsv"), _("PUBLISHER"), ""],
            "name": [("default", "json", "tsv"), _("NAME"), ""],
            "version": [("default", "json"), _("VERSION"), ""],
            "release": [("json", "tsv",), _("RELEASE"), ""],
            "build-release": [("json", "tsv",), _("BUILD RELEASE"), ""],
            "branch": [("json", "tsv",), _("BRANCH"), ""],
            "timestamp": [("json", "tsv",), _("PACKAGING DATE"), ""],
            "pkg.fmri": [("json", "tsv",), _("FMRI"), ""],
            "short_state": [("default", "tsv"), "O", ""],
         }

        desired_field_order = (_("PUBLISHER"), _("NAME"), "O", _("VERSION"),
            _("SUMMARY"), _("DESCRIPTION"), _("CATEGORIES"), _("RELEASE"),
            _("BUILD RELEASE"), _("BRANCH"), _("PACKAGING DATE"), _("FMRI"),
            _("STATE"))

        # Default output formatting.
        max_pub_name_len = str(
            max(list(len(p) for p in found) + [len(_("PUBLISHER"))]))
        def_fmt = "{0:" + max_pub_name_len + "} {1:45} {2:1} {3}"

        # print without trailing newline.
        sys.stdout.write(misc.get_listing(
            desired_field_order, field_data, gen_listing(),
            out_format, def_fmt, omit_headers))

        if not listed and pargs:
                # No matching packages.
                logger.error("")
                if not unmatched:
                        unmatched = pargs
                error(apx.PackageMatchErrors(unmatched_fmris=unmatched),
                    cmd=subcommand)
                return EXIT_OOPS
        elif unmatched:
                # One or more patterns didn't match a package from any
                # publisher; only display the error.
                logger.error("")
                error(apx.PackageMatchErrors(unmatched_fmris=unmatched),
                    cmd=subcommand)
                return EXIT_PARTIAL

        return EXIT_OK


def refresh_pub(pub_data, xport):
        """A helper function to refresh all specified publishers."""

        global tmpdirs
        temp_root = misc.config_temp_root()
        progtrack = get_tracker()
        progtrack.set_purpose(progtrack.PURPOSE_LISTING)

        progtrack.refresh_start(pub_cnt=len(pub_data), full_refresh=True,
            target_catalog=False)

        for pub in pub_data:
                progtrack.refresh_start_pub(pub)
                meta_root = tempfile.mkdtemp(dir=temp_root)
                tmpdirs.append(meta_root)
                pub.meta_root = meta_root
                pub.transport = xport

                try:
                        pub.refresh(True, True, progtrack=progtrack)
                except apx.TransportError:
                        # Assume that a catalog doesn't exist for the target
                        # publisher and drive on.
                        pass
                progtrack.refresh_end_pub(pub)

        progtrack.refresh_done()


def subcmd_contents(conf, args):
        """List package contents."""

        subcommand = "contents"
        display_raw = False
        pubs = set()
        key = None
        cert = None
        attrs = []
        action_types = []

        opts, pargs = getopt.getopt(args, "ms:t:", ["key=", "cert="])
        for opt, arg in opts:
                if opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt == "-m":
                        display_raw = True
                elif opt == "-t":
                        action_types.extend(arg.split(","))
                elif opt == "--key":
                        key = arg
                elif opt == "--cert":
                        cert = arg

        # Setup transport so configuration can be retrieved.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)

        xport, xpub, tmp_dir = setup_transport(conf.get("repo_uri"),
            subcommand=subcommand, ssl_key=key, ssl_cert=cert)

        rval, found, pub_data = _get_matching_pubs(subcommand, pubs, xport,
            xpub, use_transport=True)
        if rval == EXIT_OOPS:
                return rval

        # Default output prints out the raw manifest. The -m option is implicit
        # for now and supported to make the interface equivalent to pkg
        # contents.
        if not attrs or display_raw:
                attrs = ["action.raw"]

        refresh_pub(pub_data, xport)
        listed = False
        matched = set()
        unmatched = set()
        manifests = []

        for pub in pub_data:
                cat = pub.catalog
                for f, states, attr in cat.gen_packages(matched=matched,
                        patterns=pargs, pubs=[pub.prefix],
                        unmatched=unmatched, return_fmris=True):
                        if not listed:
                                listed = True
                        manifests.append(xport.get_manifest(f))
                unmatched.difference_update(matched)

        # Build a generator expression based on whether specific action types
        # were provided.
        if action_types:
                # If query is limited to specific action types, use the more
                # efficient type-based generation mechanism.
                gen_expr = (
                    (m.fmri, a, None, None, None)
                    for m in manifests
                    for a in m.gen_actions_by_types(action_types)
                )
        else:
                gen_expr = (
                    (m.fmri, a, None, None, None)
                    for m in manifests
                    for a in m.gen_actions()
                )

        # Determine if the query returned any results by "peeking" at the first
        # value returned from the generator expression.
        try:
                got = next(gen_expr)
        except StopIteration:
                got = None
                actionlist = []

        if got:
                actionlist = itertools.chain([got], gen_expr)

        rval = EXIT_OK
        if action_types and manifests and not got:
                logger.error(_(gettext.ngettext("""\
pkgrepo: contents: This package contains no actions with the types specified
using the -t option""", """\
pkgrepo: contents: These packages contain no actions with the types specified
using the -t option.""", len(pargs))))
                rval = EXIT_OOPS

        if manifests and rval == EXIT_OK:
                lines = misc.list_actions_by_attrs(actionlist, attrs)
                for line in lines:
                        text = ("{0}".format(*line)).rstrip()
                        if not text:
                               continue
                        msg(text)

        if unmatched:
                if manifests:
                        logger.error("")
                logger.error(_("""\
pkgrepo: contents: no packages matching the following patterns you specified
were found in the repository."""))
                logger.error("")
                for p in unmatched:
                        logger.error("        {0}".format(p))
                rval = EXIT_OOPS

        return rval


def __rebuild_local(subcommand, conf, pubs, build_catalog, build_index):
        """In an attempt to allow operations on potentially corrupt
        repositories, 'local' repositories (filesystem-basd ones) are handled
        separately."""

        repo = get_repo(conf, allow_invalid=build_catalog, read_only=False,
            subcommand=subcommand)

        rpubs = set(repo.publishers)
        if not pubs:
                found = rpubs
        else:
                found = rpubs & pubs
        notfound = pubs - found

        rval = EXIT_OK
        if found and notfound:
                rval = EXIT_PARTIAL
        elif pubs and not found:
                error(_("no matching publishers found"), cmd=subcommand)
                return EXIT_OOPS

        logger.info("Initiating repository rebuild.")
        for pfx in found:
                repo.rebuild(build_catalog=build_catalog,
                    build_index=build_index, pub=pfx)

        return rval


def __rebuild_remote(subcommand, conf, pubs, key, cert, build_catalog,
    build_index):
        def do_rebuild(xport, xpub):
                if build_catalog and build_index:
                        xport.publish_rebuild(xpub)
                elif build_catalog:
                        xport.publish_rebuild_packages(xpub)
                elif build_index:
                        xport.publish_rebuild_indexes(xpub)

        xport, xpub, tmp_dir = setup_transport(conf.get("repo_uri"),
            subcommand=subcommand, ssl_key=key, ssl_cert=cert)
        rval, found, pub_data = _get_matching_pubs(subcommand, pubs, xport,
            xpub)
        if rval == EXIT_OOPS:
                return rval

        logger.info("Initiating repository rebuild.")
        for pfx in found:
                xpub.prefix = pfx
                do_rebuild(xport, xpub)

        return rval


def subcmd_rebuild(conf, args):
        """Rebuild the repository's catalog and index data (as permitted)."""

        subcommand = "rebuild"
        build_catalog = True
        build_index = True
        key = None
        cert = None

        opts, pargs = getopt.getopt(args, "p:s:", ["no-catalog", "no-index",
            "key=", "cert="])
        pubs = set()
        for opt, arg in opts:
                if opt == "-p":
                        if not misc.valid_pub_prefix(arg):
                                error(_("Invalid publisher prefix '{0}'").format(
                                    arg), cmd=subcommand)
                        pubs.add(arg)
                elif opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt == "--no-catalog":
                        build_catalog = False
                elif opt == "--no-index":
                        build_index = False
                elif opt == "--key":
                        key = arg
                elif opt == "--cert":
                        cert = arg

        if pargs:
                usage(_("command does not take operands"), cmd=subcommand)

        if not build_catalog and not build_index:
                # Why?  Who knows; but do what was requested--nothing!
                return EXIT_OK

        # Setup transport so operation can be performed.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)

        if conf["repo_uri"].scheme == "file":
                return __rebuild_local(subcommand, conf, pubs, build_catalog,
                    build_index)

        return __rebuild_remote(subcommand, conf, pubs, key, cert,
            build_catalog, build_index)


def subcmd_refresh(conf, args):
        """Refresh the repository's catalog and index data (as permitted)."""

        subcommand = "refresh"
        add_content = True
        refresh_index = True
        key = None
        cert = None

        opts, pargs = getopt.getopt(args, "p:s:", ["no-catalog", "no-index",
            "key=", "cert="])
        pubs = set()
        for opt, arg in opts:
                if opt == "-p":
                        if not misc.valid_pub_prefix(arg):
                                error(_("Invalid publisher prefix '{0}'").format(
                                    arg), cmd=subcommand)
                        pubs.add(arg)
                elif opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt == "--no-catalog":
                        add_content = False
                elif opt == "--no-index":
                        refresh_index = False
                elif opt == "--key":
                        key = arg
                elif opt == "--cert":
                        cert = arg

        if pargs:
                usage(_("command does not take operands"), cmd=subcommand)

        if not add_content and not refresh_index:
                # Why?  Who knows; but do what was requested--nothing!
                return EXIT_OK

        # Setup transport so operation can be performed.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)

        def do_refresh(xport, xpub):
                if add_content and refresh_index:
                        xport.publish_refresh(xpub)
                elif add_content:
                        xport.publish_refresh_packages(xpub)
                elif refresh_index:
                        xport.publish_refresh_indexes(xpub)

        xport, xpub, tmp_dir = setup_transport(conf.get("repo_uri"),
            subcommand=subcommand, ssl_key=key, ssl_cert=cert)
        rval, found, pub_data = _get_matching_pubs(subcommand, pubs, xport,
            xpub)
        if rval == EXIT_OOPS:
                return rval

        logger.info("Initiating repository refresh.")
        for pfx in found:
                xpub.prefix = pfx
                do_refresh(xport, xpub)

        return rval


def subcmd_set(conf, args):
        """Set repository properties."""

        subcommand = "set"
        pubs = set()

        opts, pargs = getopt.getopt(args, "p:s:")
        for opt, arg in opts:
                if opt == "-p":
                        pubs.add(arg)
                elif opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)

        bad_args = False
        props = {}
        if not pargs:
                bad_args = True
        else:
                for arg in pargs:
                        try:
                                # Attempt to parse property into components.
                                prop, val = arg.split("=", 1)
                                sname, pname = prop.rsplit("/", 1)

                                # Store property values by section.
                                props.setdefault(sname, {})

                                # Parse the property value into a list if
                                # necessary, otherwise append it to the list
                                # of values for the property.
                                if len(val) > 0  and val[0] == "(" and \
                                    val[-1] == ")":
                                        val = shlex.split(val.strip("()"))

                                if sname in props and pname in props[sname]:
                                        # Determine if previous value is already
                                        # a list, and if not, convert and append
                                        # the value.
                                        pval = props[sname][pname]
                                        if not isinstance(pval, list):
                                                pval = [pval]
                                        if isinstance(val, list):
                                                pval.extend(val)
                                        else:
                                                pval.append(val)
                                        props[sname][pname] = pval
                                else:
                                        # Otherwise, just store the value.
                                        props[sname][pname] = val
                        except ValueError:
                                bad_args = True
                                break

        if bad_args:
                usage(_("a property name and value must be provided in the "
                    "form <section/property>=<value> or "
                    "<section/property>=([\"<value>\" ...])"))

        # Get repository object.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)
        repo = get_repo(conf, read_only=False, subcommand=subcommand)

        # Set properties.
        if pubs:
                return _set_pub(conf, subcommand, props, pubs, repo)

        return _set_repo(conf, subcommand, props, repo)


def _set_pub(conf, subcommand, props, pubs, repo):
        """Set publisher properties."""

        for sname, sprops in six.iteritems(props):
                if sname not in ("publisher", "repository"):
                        usage(_("unknown property section "
                            "'{0}'").format(sname), cmd=subcommand)
                for pname in sprops:
                        if sname == "publisher" and pname == "prefix":
                                usage(_("'{0}' may not be set using "
                                    "this command".format(pname)))
                        attrname = pname.replace("-", "_")
                        if not hasattr(publisher.Publisher, attrname) and \
                            not hasattr(publisher.Repository, attrname):
                                usage(_("unknown property '{0}'").format(
                                    pname), cmd=subcommand)

        if "all" in pubs:
                # Default to list of all publishers.
                pubs = repo.publishers
                if not pubs:
                        # If there are still no known publishers, this
                        # operation cannot succeed, so fail now.
                        usage(_("One or more publishers must be specified to "
                            "create and set properties for as none exist yet."),
                            cmd=subcommand)

        # Get publishers and update properties.
        failed = []
        new_pub = False
        for pfx in pubs:
                try:
                        # Get a copy of the existing publisher.
                        pub = copy.copy(repo.get_publisher(pfx))
                except sr.RepositoryUnknownPublisher as e:
                        pub = publisher.Publisher(pfx)
                        new_pub = True
                except sr.RepositoryError as e:
                        failed.append((pfx, e))
                        continue

                try:
                        # Set/update the publisher's properties.
                        for sname, sprops in six.iteritems(props):
                                if sname == "publisher":
                                        target = pub
                                elif sname == "repository":
                                        target = pub.repository
                                        if not target:
                                                target = publisher.Repository()
                                                pub.repository = target

                                for pname, val in six.iteritems(sprops):
                                        attrname = pname.replace("-", "_")
                                        pval = getattr(target, attrname)
                                        if isinstance(pval, list) and \
                                            not isinstance(val, list):
                                                # If the target property expects
                                                # a list, transform the provided
                                                # value into one if it isn't
                                                # already.
                                                if val == "":
                                                        val = []
                                                else:
                                                        val = [val]
                                        setattr(target, attrname, val)
                except apx.ApiException as e:
                        failed.append((pfx, e))
                        continue

                if new_pub:
                        repo.add_publisher(pub)
                else:
                        repo.update_publisher(pub)

        if failed:
                for pfx, details in failed:
                        error(_("Unable to set properties for publisher "
                            "'{pfx}':\n{details}").format(**locals()))
                if len(failed) < len(pubs):
                        return EXIT_PARTIAL
                return EXIT_OOPS
        return EXIT_OK


def _set_repo(conf, subcommand, props, repo):
        """Set repository properties."""

        # Set properties.
        for sname, props in six.iteritems(props):
                for pname, val in six.iteritems(props):
                        repo.cfg.set_property(sname, pname, val)
        repo.write_config()

        return EXIT_OK


def subcmd_version(conf, args):
        """Display the version of the pkg(7) API."""

        subcommand = "version"
        if args:
                usage(_("command does not take operands"), cmd=subcommand)
        msg(pkg.VERSION)
        return EXIT_OK


verify_error_header = None
verify_warning_header = None
verify_reason_headers = None

def __load_verify_msgs():
        """Since our gettext isn't loaded we need to ensure our globals have
        correct content by calling this method.  These values are used by both
        fix when in verbose mode, and verify"""

        global verify_error_header
        global verify_warning_header
        global verify_reason_headers

        # A map of error detail types to the human-readable description of each
        # type.  These correspond to keys in the dictionary returned by
        # sr.Repository.verify(..)
        verify_reason_headers = {
            "path": _("Repository path"),
            "actual": _("Computed hash"),
            "fpath": _("Path"),
            "permissionspath": _("Path"),
            "pkg": _("Package"),
            "depend": _("Dependency"),
            "type":_("Dependency type"),
            "err": _("Detail")
        }

        verify_error_header = _("ERROR")
        verify_warning_header = _("WARNING")


def __fmt_verify(verify_tuple):
        """Format a verify_tuple, of the form (error, path, message, reason)
        returning a formatted error message, and an FMRI indicating what
        packages within the repository are affected. Note that the returned FMRI
        may not be valid, in which case a path to the broken manifest in the
        repository is returned instead."""

        error, path, message, reason = verify_tuple

        formatted_message = "{error_type:>16}: {message}\n".format(
            error_type=verify_error_header, message=message)
        reason["path"] = path

        if error == sr.REPO_VERIFY_BADMANIFEST:
                reason_keys = ["path", "err"]
        elif error in [sr.REPO_VERIFY_PERM, sr.REPO_VERIFY_MFPERM]:
                reason_keys = ["pkg", "path"]
        elif error == sr.REPO_VERIFY_BADHASH:
                reason_keys = ["pkg", "path", "actual", "fpath"]
        elif error == sr.REPO_VERIFY_UNKNOWN:
                reason_keys = ["path", "err"]
        elif error == sr.REPO_VERIFY_BADSIG:
                reason_keys = ["pkg", "path", "err"]
        elif error == sr.REPO_VERIFY_DEPENDERROR:
                reason_keys = ["pkg", "depend", "type"]
        elif error == sr.REPO_VERIFY_WARN_OPENPERMS:
                formatted_message = \
                    "{error_type:>16}: {message}\n".format(
                    error_type=verify_warning_header, message=message)
                reason_keys = ["permissionspath", "err"]
        else:
                # A list of the details we provide.  Some error codes
                # have different details associated with them.
                reason_keys = ["pkg", "path", "fpath"]


        # the detailed error message can be long, so we'll wrap it.  If what we
        # have fits on a single line, use it, otherwise begin displaying the
        # message on the next line.
        if "err" in reason_keys:
                err_str = ""
                lines = textwrap.wrap(reason["err"])
                if len(lines) != 1:
                        for line in lines:
                                err_str += "{0:>18}\n".format(line)
                        reason["err"] = "\n" + err_str.rstrip()
                else:
                        reason["err"] = lines[0]

        for key in reason_keys:
                # sometimes we don't have the key we want, for example we may
                # not have a file path from the package if the error is a
                # missing repository file for a 'license' action (which don't
                # have 'path' attributes, hence no 'fpath' dictionary entry)
                if key not in reason:
                        continue
                formatted_message += "{key:>16}: {value}\n".format(
                    key=verify_reason_headers[key], value=reason[key])

        formatted_message += "\n"

        if error == sr.REPO_VERIFY_WARN_OPENPERMS:
                return formatted_message, None
        elif "depend" in reason:
                return formatted_message, reason["depend"]
        elif "pkg" in reason:
                return formatted_message, reason["pkg"]
        return formatted_message, reason["path"]


def __collect_default_ignore_dep_files(ignored_dep_files):
        """Helpler function to collect default ignored-dependency files."""

        root_ignored = "/usr/share/pkg/ignored_deps"
        altroot = DebugValues.get_value("ignored_deps")
        if altroot:
                root_ignored = altroot
        if os.path.exists(root_ignored):
                igfiles = os.listdir(root_ignored)
                for igf in igfiles:
                        ignored_dep_files.append(os.path.join(root_ignored,
                            igf))


def subcmd_verify(conf, args):
        """Verify the repository content (file, manifest content and
        dependencies only)."""

        subcommand = "verify"
        __load_verify_msgs()

        opts, pargs = getopt.getopt(args, "dp:s:i:", ["disable="])
        allowed_checks = set(sr.verify_default_checks)
        force_dep_check = False
        ignored_dep_files = []
        pubs = set()
        for opt, arg in opts:
                if opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt == "-p":
                        if not misc.valid_pub_prefix(arg):
                                error(_("Invalid publisher prefix '{0}'").format(
                                    arg), cmd=subcommand)
                        pubs.add(arg)
                elif opt == "-d":
                        force_dep_check = True
                elif opt == "--disable":
                        arg = arg.lower()
                        if arg in sr.verify_default_checks:
                                if arg in allowed_checks:
                                        allowed_checks.remove(arg)
                        else:
                                usage(_("Invalid verification to be disabled, "
                                    "please consider: {0}").format(", ".join(
                                    sr.verify_default_checks)), cmd=subcommand)
                elif opt == "-i":
                        ignored_dep_files.append(arg)

        if pargs:
                usage(_("command does not take operands"), cmd=subcommand)

        repo_uri = conf.get("repo_uri", None)
        if not repo_uri:
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)

        if repo_uri.scheme != "file":
                usage(_("Network repositories are not currently supported "
                    "for this operation."), cmd=subcommand)

        if sr.VERIFY_DEPENDENCY not in allowed_checks and \
            (force_dep_check or len(ignored_dep_files) > 0):
                usage(_("-d or -i option cannot be used when dependency "
                    "verification is disabled."), cmd=subcommand)

        xport, xpub, tmp_dir = setup_transport(repo_uri, subcommand=subcommand)
        rval, found, pub_data = _get_matching_pubs(subcommand, pubs, xport,
            xpub)

        if rval == EXIT_OOPS:
                return rval

        logger.info("Initiating repository verification.")
        bad_fmris = set()
        progtrack = get_tracker()

        def report_error(verify_tuple):
                message, bad_fmri = __fmt_verify(verify_tuple)
                if bad_fmri:
                        bad_fmris.add(bad_fmri)
                progtrack.repo_verify_yield_error(bad_fmri, message)

        if sr.VERIFY_DEPENDENCY in allowed_checks or not force_dep_check:
                __collect_default_ignore_dep_files(ignored_dep_files)

        repo = sr.Repository(root=repo_uri.get_pathname())

        found_pubs = []
        for pfx in found:
                xport, xpub, tmp_dir = setup_transport(repo_uri, prefix=pfx,
                    remote_prefix=False,
                    subcommand=subcommand)
                xpub.transport = xport
                found_pubs.append(xpub)

        for verify_tuple in repo.verify(pubs=found_pubs,
            allowed_checks=allowed_checks, force_dep_check=force_dep_check,
            ignored_dep_files=ignored_dep_files, progtrack=progtrack):
                report_error(verify_tuple)

        if bad_fmris:
                return EXIT_OOPS
        return EXIT_OK


def subcmd_fix(conf, args):
        """Fix the repository content (file and manifest content only)
        For index and catalog content corruption, a rebuild should be
        performed."""

        subcommand = "fix"
        __load_verify_msgs()
        verbose = False

        # Dependency verification. Note fix will not force dependency check.
        force_dep_check = False
        ignored_dep_files = []

        opts, pargs = getopt.getopt(args, "vp:s:")
        pubs = set()
        for opt, arg in opts:
                if opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                if opt == "-v":
                        verbose = True
                if opt == "-p":
                        if not misc.valid_pub_prefix(arg):
                                error(_("Invalid publisher prefix '{0}'").format(
                                    arg), cmd=subcommand)
                        pubs.add(arg)

        if pargs:
                usage(_("command does not take operands"), cmd=subcommand)

        repo_uri = conf.get("repo_uri", None)
        if not repo_uri:
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)

        if repo_uri.scheme != "file":
                usage(_("Network repositories are not currently supported "
                    "for this operation."), cmd=subcommand)

        xport, xpub, tmp_dir = setup_transport(repo_uri, subcommand=subcommand)
        rval, found, pub_data = _get_matching_pubs(subcommand, pubs, xport,
            xpub)
        if rval == EXIT_OOPS:
                return rval

        logger.info("Initiating repository fix.")

        def verify_cb(tracker, verify_tuple):
                """A method passed to sr.Repository.fix(..) to emit verify
                messages if verbose mode is enabled."""
                if not verbose:
                        return
                formatted_message, bad_fmri = __fmt_verify(verify_tuple)
                tracker.repo_verify_yield_error(bad_fmri, formatted_message)

        repo = sr.Repository(root=repo_uri.get_pathname())
        bad_deps = set()
        broken_fmris = set()
        failed_fix_paths = set()
        progtrack = get_tracker()
        __collect_default_ignore_dep_files(ignored_dep_files)

        found_pubs = []
        for pfx in found:
                xport, xpub, tmp_dir = setup_transport(repo_uri, prefix=pfx,
                    remote_prefix=False,
                    subcommand=subcommand)
                xpub.transport = xport
                found_pubs.append(xpub)

        for status_code, path, message, reason in \
            repo.fix(pubs=found_pubs, force_dep_check=force_dep_check,
                ignored_dep_files=ignored_dep_files,
                progtrack=progtrack,
                verify_callback=verify_cb):
                if status_code == sr.REPO_FIX_ITEM:
                        # When we can't get the FMRI, eg. in the case
                        # of a corrupt manifest, use the path instead.
                        fmri = reason["pkg"]
                        if not fmri:
                                fmri = path
                        broken_fmris.add(fmri)
                        if verbose:
                                progtrack.repo_fix_yield_info(fmri,
                                    message)
                elif status_code == sr.REPO_VERIFY_DEPENDERROR:
                        bad_deps.add(reason["depend"])
                else:
                        failed_fix_paths.add(path)

        progtrack.flush()
        logger.info("")

        if broken_fmris:
                logger.info(_("Use pkgsend(1) or pkgrecv(1) to republish the\n"
                    "following packages or paths which were quarantined:\n\n\t"
                    "{0}").format(
                    "\n\t".join([str(f) for f in broken_fmris])))
        if failed_fix_paths:
                logger.info(_("\npkgrepo could not repair the following paths "
                    "in the repository:\n\n\t{0}").format(
                    "\n\t".join([p for p in failed_fix_paths])))
        if bad_deps:
                logger.info(_("\npkgrepo could not repair the following "
                    "dependency issues in the repository:\n\n\t{0}").format(
                    "\n\t".join([p for p in bad_deps])))
        if not (broken_fmris or failed_fix_paths or bad_deps):
                logger.info(_("No repository fixes required."))
        else:
                logger.info(_("Repository repairs completed."))

        if failed_fix_paths or bad_deps:
                return EXIT_OOPS
        return EXIT_OK

def __get_pub_fmris(pub, xport, tmp_dir):
        if not pub.meta_root:
                # Create a temporary directory for catalog.
                cat_dir = tempfile.mkdtemp(prefix="pkgrepo-diff.", dir=tmp_dir)
                pub.meta_root = cat_dir
                pub.transport = xport
                pub.refresh(full_refresh=True, immediate=True)

        pkgs, fmris, unmatched = pub.catalog.get_matching_fmris("*")
        fmris = [f for f in fmris]
        return fmris, pkgs

def __format_diff(diff_type, subject):
        """formatting diff output.
        diff_type: can be MINUS, PLUS or COMMON.

        subject: can be a publisher or a package.
        """

        format_pub = "{0}{1}"
        format_fmri = "        {0}{1}"
        format_str = "        {0}{1}"
        text = ""
        if isinstance(subject, publisher.Publisher):
                text = format_pub.format(diff_type_f[diff_type],
                    subject.prefix)
        elif isinstance(subject, fmri.PkgFmri):
                text = format_fmri.format(diff_type_f[diff_type],
                    str(subject))
        else:
                text = format_str.format(diff_type_f[diff_type],
                    subject)
        return text

def __sorted(subject, stype=None):
        if stype == "pub":
                skey = operator.attrgetter("prefix")
                return sorted(subject, key=skey)
        return sorted(subject)

def __emit_msg(diff_type, subject):
        text = __format_diff(diff_type, subject)
        msg(text)

def __repo_diff(conf, pubs, xport, rpubs, rxport, tmp_dir, verbose, quiet,
    compare_ts, compare_cat, parsable):
        """Determine the differences between two repositories."""

        same_repo = True
        if conf["repo_uri"].scheme == "file":
                conf["repo_uri"] = conf["repo_uri"].get_pathname()
        if conf["com_repo_uri"].scheme == "file":
                conf["com_repo_uri"] = conf["com_repo_uri"].get_pathname()

        foundpfx = set([pub.prefix for pub in pubs])
        rfoundpfx = set([pub.prefix for pub in rpubs])

        minus_pfx = __sorted(foundpfx - rfoundpfx)
        minus_pubs = __sorted([pub for pub in pubs if pub.prefix in minus_pfx],
            stype="pub")
        plus_pfx = __sorted(rfoundpfx - foundpfx)
        plus_pubs = __sorted([pub for pub in rpubs if pub.prefix in plus_pfx],
            stype="pub")

        if minus_pubs or plus_pubs:
                same_repo = False
                if quiet:
                        return EXIT_DIFF

        pcommon_set = foundpfx & rfoundpfx
        common_pubs = __sorted([p for p in pubs if p.prefix in pcommon_set],
            stype="pub")
        common_rpubs = __sorted([p for p in rpubs if p.prefix in pcommon_set],
            stype="pub")

        res_dict = {"table_legend": [["Repo1", str(conf["repo_uri"])],
                ["Repo2", str(conf["com_repo_uri"])]],
            "table_header": [_("Publisher"),
                # This is a table column header which tells that this
                # row shows number of packages found in specific
                # repository only.
                # Use terse translation to avoid too-wide header.
                _("{repo} only").format(repo="Repo1"),
                _("{repo} only").format(repo="Repo2"),
                # This is a table column header which tells that this
                # row shows number of packages found in both
                # repositories being compared together.
                # Use terse translation to avoid too-wide header.
                _("In both"), _("Total")],
            # Row based table contents.
            "table_data": []
            }

        verbose_res_dict = {"plus_pubs": [], "minus_pubs": [],
            "common_pubs": []}

        def __diff_pub_helper(pub, symbol):
                fmris, pkgs = __get_pub_fmris(pub, xport, tmp_dir)
                # Summary level.
                if not verbose:
                        td_row = [pub.prefix,
                            {"packages": len(pkgs), "versions": len(fmris)},
                            None, {"packages": 0, "versions": 0},
                            {"packages": len(pkgs), "versions": len(fmris)}]
                        if symbol == PLUS:
                                td_row[1], td_row[2] = td_row[2], td_row[1]
                        res_dict["table_data"].append(td_row)
                        return

                if parsable:
                        key_name = "minus_pubs"
                        if symbol == PLUS:
                                key_name = "plus_pubs"
                        verbose_res_dict[key_name].append(
                            {"publisher": pub.prefix, "packages": len(pkgs),
                            "versions": len(fmris)})
                        return

                __emit_msg(symbol, pub)
                __emit_msg(symbol, _("({0:d} package(s) with "
                    "{1:d} different version(s))").format(len(pkgs),
                    len(fmris)))

        for pub in minus_pubs:
                __diff_pub_helper(pub, MINUS)

        for pub in plus_pubs:
                __diff_pub_helper(pub, PLUS)

        for pub, rpub in zip(common_pubs, common_rpubs):
                # Indicates whether those two pubs have same pkgs.
                same_pkgs = True
                same_cat = True
                fmris, pkgs = __get_pub_fmris(pub, xport, tmp_dir)
                rfmris, rpkgs = __get_pub_fmris(rpub, rxport, tmp_dir)
                fmris_str = set([str(f) for f in fmris])
                rfmris_str = set([str(f) for f in rfmris])
                del fmris, rfmris

                minus_fmris = __sorted(fmris_str - rfmris_str)
                plus_fmris = __sorted(rfmris_str - fmris_str)
                if minus_fmris or plus_fmris:
                        same_repo = False
                        same_pkgs = False
                        if quiet:
                                return EXIT_DIFF

                cat_lm_pub = None
                cat_lm_rpub = None
                if compare_cat:
                        cat_lm_pub = pub.catalog.last_modified.isoformat()
                        cat_lm_rpub = rpub.catalog.last_modified.isoformat()
                        same_cat = same_repo = cat_lm_pub == cat_lm_rpub
                        if not same_cat and quiet:
                                return EXIT_DIFF

                common_fmris = fmris_str & rfmris_str
                pkg_set = set(pkgs.keys())
                rpkg_set = set(rpkgs.keys())
                del pkgs, rpkgs
                common_pkgs = pkg_set & rpkg_set

                # Print summary.
                if not verbose:
                        if not same_cat:
                                # Common publishers with different catalog
                                # modification time.
                                res_dict.setdefault("nonstrict_pubs", []
                                    ).append(pub.prefix)

                        # Add to the table only if there are differences
                        # for this publisher.
                        if not same_pkgs:
                                minus_pkgs = pkg_set - rpkg_set
                                minus_pkg_vers = {"packages": len(minus_pkgs),
                                    "versions": len(minus_fmris)}
                                del minus_pkgs, minus_fmris

                                plus_pkgs = rpkg_set - pkg_set
                                plus_pkg_vers = {"packages": len(plus_pkgs),
                                    "versions": len(plus_fmris)}
                                del plus_pkgs, plus_fmris

                                total_pkgs = pkg_set | rpkg_set
                                total_fmris = fmris_str | rfmris_str
                                total_pkg_vers = {"packages": len(total_pkgs),
                                    "versions": len(total_fmris)}
                                del total_pkgs, total_fmris

                                com_pkg_vers = {"packages": len(common_pkgs),
                                    "versions": len(common_fmris)}

                                res_dict["table_data"].append([pub.prefix,
                                    minus_pkg_vers, plus_pkg_vers,
                                    com_pkg_vers,
                                    total_pkg_vers])
                        del common_pkgs, common_fmris, pkg_set, rpkg_set
                        continue

                com_pub_info = {}
                # Emit publisher name if there are differences.
                if not same_pkgs or not same_cat:
                        if parsable:
                                com_pub_info["publisher"] = pub.prefix
                                com_pub_info["+"] = []
                                com_pub_info["-"] = []
                        else:
                                __emit_msg(COMMON, pub)

                # Emit catalog differences.
                if not same_cat:
                        omsg = _("catalog last modified: {0}")
                        minus_cat = omsg.format(cat_lm_pub)
                        plus_cat = omsg.format(cat_lm_rpub)
                        if parsable:
                                com_pub_info["catalog"] = {"-": minus_cat,
                                    "+": plus_cat}
                        else:
                                __emit_msg(MINUS, minus_cat)
                                __emit_msg(PLUS, plus_cat)

                for f in minus_fmris:
                        if parsable:
                                com_pub_info["-"].append(str(f))
                        else:
                                __emit_msg(MINUS, f)
                del minus_fmris

                for f in plus_fmris:
                        if parsable:
                                com_pub_info["+"].append(str(f))
                        else:
                                __emit_msg(PLUS, f)
                del plus_fmris

                if not same_pkgs:
                        if parsable:
                                com_pub_info["common"] = {
                                    "packages": len(common_pkgs),
                                    "versions": len(common_fmris)}
                        else:
                                msg(_("        ({0:d} pkg(s) with {1:d} "
                                    "version(s) are in both repositories.)"
                                    ).format(len(common_pkgs),
                                    len(common_fmris)))
                del common_pkgs, common_fmris, pkg_set, rpkg_set

                if com_pub_info:
                        verbose_res_dict["common_pubs"].append(com_pub_info)

        if same_repo:
                # Same repo. Will use EXIT_OK to represent.
                return EXIT_OK

        if verbose:
                if parsable:
                        msg(json.dumps(verbose_res_dict))
                return EXIT_DIFF

        if not parsable:
                ftemp = "{0:d} [{1:{2}d}]"
                if "nonstrict_pubs" in res_dict and res_dict["nonstrict_pubs"]:
                        msg("")
                        msg(_("The catalog for the following publisher(s) "
                            "in repository {0} is not an exact copy of the "
                            "one for the same publisher in repository {1}:"
                            "\n    {2}").format(conf["repo_uri"],
                            conf["com_repo_uri"],
                            ", ".join(res_dict["nonstrict_pubs"])))
                if res_dict["table_data"]:
                        info_table = PrettyTable(res_dict["table_header"],
                            encoding=locale.getpreferredencoding())
                        info_table.align = "r"
                        info_table.align[misc.force_text(_("Publisher"),
                            locale.getpreferredencoding())] = "l"
                        # Calculate column wise maximum number for formatting.
                        col_maxs = 4 * [0]
                        for td in res_dict["table_data"]:
                                for idx, cell in enumerate(td):
                                        if idx > 0 and isinstance(cell, dict):
                                                col_maxs[idx-1] = max(
                                                    col_maxs[idx-1],
                                                    cell["versions"])

                        for td in res_dict["table_data"]:
                                t_row = []
                                for idx, cell in enumerate(td):
                                        if not cell:
                                                t_row.append("-")
                                        elif isinstance(cell, six.string_types):
                                                t_row.append(cell)
                                        elif isinstance(cell, dict):
                                                t_row.append(ftemp.format(
                                                    cell["packages"],
                                                    cell["versions"], len(str(
                                                    col_maxs[idx-1]))))
                                info_table.add_row(t_row)

                        # This message explains that each cell of the table
                        # shows two numbers in a format e.g. "4870 [10227]".
                        # Here "number of packages" and "total distinct
                        # versions" are shown outside and inside of square
                        # brackets respectively.
                        msg(_("""
The table below shows the number of packages [total distinct versions]
by publisher in the specified repositories.
"""))
                        for leg in res_dict["table_legend"]:
                                msg("* " + leg[0] + ": " + leg[1])
                        msg("")
                        msg(info_table)
        else:
                msg(json.dumps(res_dict))

        return EXIT_DIFF


def subcmd_diff(conf, args):
        """Compare two repositories."""

        opts, pargs = getopt.getopt(args, "vqp:s:", ["strict", "parsable",
            "key=", "cert="])
        subcommand = "diff"
        pubs = set()
        verbose = 0
        quiet = False
        compare_ts = True
        compare_cat = False
        parsable = False

        def key_cert_conf_helper(conf_type, arg):
                """Helper function for collecting key and cert."""

                if conf.get("repo_uri") and not conf.get("com_repo_uri"):
                        conf["repo_" + conf_type] = arg
                elif conf.get("com_repo_uri"):
                        conf["com_repo_" + conf_type] = arg
                else:
                        usage(_("--{0} must be specified following a "
                            "-s").format(conf_type), cmd=subcommand)

        for opt, arg in opts:
                if opt == "-s":
                        if "repo_uri" not in conf:
                                conf["repo_uri"] = parse_uri(arg)
                        elif "com_repo_uri" not in conf:
                                conf["com_repo_uri"] = parse_uri(arg)
                        else:
                                usage(_("only two repositories can be "
                                    "specified"), cmd=subcommand)
                if opt == "-v":
                        verbose += 1
                elif opt == "-q":
                        quiet = True
                elif opt == "--strict":
                        compare_cat = True
                elif opt == "--parsable":
                        parsable = True
                elif opt == "-p":
                        if not misc.valid_pub_prefix(arg):
                                error(_("Invalid publisher prefix '{0}'").format(
                                    arg), cmd=subcommand)
                                return EXIT_OOPS
                        pubs.add(arg)
                elif opt == "--key":
                        key_cert_conf_helper("key", arg)
                elif opt == "--cert":
                        key_cert_conf_helper("cert", arg)

        if len(pargs) > 0:
                usage(_("command does not take any operands"), cmd=subcommand)

        if quiet and verbose:
                usage(_("-q and -v can not be combined"), cmd=subcommand)

        repo_uri = conf.get("repo_uri")
        if not repo_uri:
                usage(_("Two package repository locations must be provided "
                    "using -s."), cmd=subcommand)

        com_repo_uri = conf.get("com_repo_uri")
        if not com_repo_uri:
                usage(_("A second package repository location must also be "
                    "provided using -s."), cmd=subcommand)

        xport, xpub, tmp_dir = setup_transport(repo_uri, subcommand=subcommand,
            ssl_key=conf.get("repo_key"), ssl_cert=conf.get("repo_cert"))
        cxport, cxpub, c_tmp_dir = setup_transport(com_repo_uri,
            subcommand=subcommand, prefix="com",
            ssl_key=conf.get("com_repo_key"),
            ssl_cert=conf.get("com_repo_cert"))
        rval, found, pub_data = _get_matching_pubs(subcommand, pubs, xport,
            xpub, use_transport=True, repo_uri=repo_uri)
        if rval == EXIT_OOPS:
                return rval

        rval, cfound, cpub_data = _get_matching_pubs(subcommand, pubs, cxport,
            cxpub, use_transport=True, repo_uri=com_repo_uri)
        if rval == EXIT_OOPS:
                return rval

        return  __repo_diff(conf, pub_data, xport, cpub_data, cxport, tmp_dir,
            verbose, quiet, compare_ts, compare_cat, parsable)


def main_func():
        global_settings.client_name = PKG_CLIENT_NAME

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "s:D:?",
                    ["help", "debug="])
        except getopt.GetoptError as e:
                usage(_("illegal global option -- {0}").format(e.opt))

        conf = {}
        show_usage = False
        for opt, arg in opts:
                if opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt in ("--help", "-?"):
                        show_usage = True
                elif opt == "-D" or opt == "--debug":
                        try:
                                key, value = arg.split("=", 1)
                        except (AttributeError, ValueError):
                                usage(_("{opt} takes argument of form "
                                   "name=value, not {arg}").format(
                                   opt=opt, arg=arg))
                        DebugValues.set_value(key, value)

        if DebugValues:
                reload(pkg.digest)

        subcommand = None
        if pargs:
                subcommand = pargs.pop(0)
                if subcommand == "help":
                        show_usage = True

        if show_usage:
                usage(retcode=0, full=True)
        elif not subcommand:
                usage(_("no subcommand specified"))

        subcommand = subcommand.replace("-", "_")
        func = globals().get("subcmd_{0}".format(subcommand), None)
        if not func:
                subcommand = subcommand.replace("_", "-")
                usage(_("unknown subcommand '{0}'").format(subcommand))

        try:
                return func(conf, pargs)
        except getopt.GetoptError as e:
                if e.opt in ("help", "?"):
                        usage(full=True)
                usage(_("illegal option -- {0}").format(e.opt), cmd=subcommand)


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
                                raise apx._convert_error(__e)
                        error("\n" + misc.out_of_memory())
                        __ret = EXIT_OOPS
        except SystemExit as __e:
                raise __e
        except (IOError, PipeError, KeyboardInterrupt) as __e:
                # Don't display any messages here to prevent possible further
                # broken pipe (EPIPE) errors.
                if isinstance(__e, IOError) and __e.errno != errno.EPIPE:
                        error(str(__e))
                __ret = EXIT_OOPS
        except apx.VersionException as __e:
                error(_("The pkgrepo command appears out of sync with the "
                    "libraries provided\nby pkg:/package/pkg. The client "
                    "version is {client} while the library\nAPI version is "
                    "{api}.").format(client=__e.received_version,
                     api=__e.expected_version))
                __ret = EXIT_OOPS
        except apx.BadRepositoryURI as __e:
                error(str(__e))
                __ret = EXIT_BADOPT
        except apx.InvalidOptionError as __e:
                error("{0} Supported formats: {1}".format(
                    str(__e), LISTING_FORMATS))
                __ret = EXIT_BADOPT
        except (apx.ApiException, sr.RepositoryError) as __e:
                error(str(__e))
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
        misc.set_fd_limits(printer=error)

        # Make all warnings be errors.
        warnings.simplefilter('error')
        if six.PY3:
                # disable ResourceWarning: unclosed file
                warnings.filterwarnings("ignore", category=ResourceWarning)

        __retval = handle_errors(main_func)
        try:
                logging.shutdown()
        except IOError:
                # Ignore python's spurious pipe problems.
                pass
        sys.exit(__retval)
