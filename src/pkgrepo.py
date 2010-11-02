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
# Copyright (c) 2010 Oracle and/or its affiliates.  All rights reserved.
#

PKG_CLIENT_NAME = "pkgrepo"

# pkgrepo exit codes
EXIT_OK      = 0
EXIT_OOPS    = 1
EXIT_BADOPT  = 2
EXIT_PARTIAL = 3

# listing constants
LISTING_FORMATS = ("tsv", )

# globals
tmpdirs = []

import atexit
import copy
import errno
import getopt
import gettext
import locale
import logging
import os
import shlex
import shutil
import sys
import tempfile
import traceback
import warnings

from pkg.client import global_settings
from pkg.misc import msg, PipeError
import pkg
import pkg.catalog
import pkg.client.api_errors as apx
import pkg.client.publisher as publisher
import pkg.client.transport.transport as transport
import pkg.misc as misc
import pkg.server.repository as sr

logger = global_settings.logger
orig_cwd = None

@atexit.register
def cleanup():
        """To be called at program finish."""
        for d in tmpdirs:
                shutil.rmtree(d, True)

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if cmd:
                text = "%s: %s" % (cmd, text)
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
     pkgrepo create [--version] uri_or_path

     pkgrepo add-signing-ca-cert [-p publisher ...]
         [-s repo_uri_or_path] path ...

     pkgrepo add-signing-intermediate-cert [-p publisher ...]
         [-s repo_uri_or_path] path ...

     pkgrepo get [-p publisher ...] [-s repo_uri_or_path]
         [section/property ...]

     pkgrepo info [-F format] [-H] [-p publisher ...]
         [-s repo_uri_or_path]

     pkgrepo rebuild [-s repo_uri_or_path] [--no-catalog]
         [--no-index]

     pkgrepo refresh [-s repo_uri_or_path] [--no-catalog]
         [--no-index]

     pkgrepo remove-signing-ca-cert [-p publisher ...]
         [-s repo_uri_or_path] hash ...

     pkgrepo remove-signing-intermediate-cert [-p publisher ...]
         [-s repo_uri_or_path] hash ...

     pkgrepo set [-p publisher ...] [-s repo_uri_or_path]
         section/property[+|-]=[value] ... or
         section/property[+|-]=([value]) ...

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


def _add_certs(conf, subcommand, args, ca):
        opts, pargs = getopt.getopt(args, "p:s:")
        pubs = set()

        for opt, arg in opts:
                if opt == "-p":
                        pubs.add(arg)
                elif opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)

        # Get repository object.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)

        repo = get_repo(conf, read_only=False, subcommand=subcommand)

        if len(pargs) < 1:
                usage(_("At least one path to a certificate must be provided."))

        failed = []
        def add_certs(pfx=None):
                if orig_cwd:
                        certs = [os.path.join(orig_cwd, f) for f in pargs]
                else:
                        certs = [os.path.abspath(f) for f in pargs]

                try:
                        repo.add_signing_certs(certs, ca=ca, pub=pfx)
                except (apx.ApiException, sr.RepositoryError), e:
                        failed.append((pfx, e))

        if "all" in pubs:
                # Default to list of all publishers.
                pubs = repo.publishers

        if not pubs:
                # Assume default publisher or older repository.
                add_certs()
        else:
                # Add for each publisher specified.
                map(add_certs, pubs)

        return pubs, failed


def subcmd_add_signing_ca_cert(conf, args):
        """Add the provided signing ca certificates to the repository for
        the given publisher."""

        subcommand = "add-signing-ca-cert"
        pubs, failed = _add_certs(conf, subcommand, args, True)
        if failed:
                for pfx, details in failed:
                        error(_("Unable to add signing ca certificates for "
                            "publisher '%(pfx)s':\n%(details)s") % locals(),
                            cmd=subcommand)
                if len(failed) < len(pubs):
                        return EXIT_PARTIAL
                return EXIT_OOPS
        return EXIT_OK


def subcmd_add_signing_intermediate_cert(conf, args):
        subcommand = "add-signing-intermediate-cert"
        pubs, failed = _add_certs(conf, subcommand, args, True)
        if failed:
                for pfx, details in failed:
                        if pfx:
                                error(_("Unable to add signing intermediate "
                                    "certificates for publisher '%(pfx)s':\n"
                                    "%(details)s") % locals(), cmd=subcommand)
                        else:
                                error(_("Unable to add signing intermediate "
                                    "certificates:\n%(details)s") % locals(),
                                    cmd=subcommand)
                if len(failed) < len(pubs):
                        return EXIT_PARTIAL
                return EXIT_OOPS
        return EXIT_OK


def _remove_certs(conf, subcommand, args, ca):
        opts, pargs = getopt.getopt(args, "p:s:")
        pubs = set()

        for opt, arg in opts:
                if opt == "-p":
                        pubs.add(arg)
                elif opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)

        # Get repository object.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)

        repo = get_repo(conf, read_only=False, subcommand=subcommand)

        if len(pargs) < 1:
                usage(_("At least one certificate hash must be provided."))

        failed = []
        def remove_certs(pfx=None):
                try:
                        repo.remove_signing_certs(pargs, ca=True, pub=pfx)
                except (apx.ApiException, sr.RepositoryError), e:
                        failed.append((pfx, e))

        if "all" in pubs:
                # Default to list of all publishers.
                pubs = repo.publishers

        if not pubs:
                # Assume default publisher or older repository.
                remove_certs()
        else:
                # Add for each publisher specified.
                map(remove_certs, pubs)

        return pubs, failed


def subcmd_remove_signing_ca_cert(conf, args):
        subcommand = "remove-signing-ca-cert"
        pubs, failed = _remove_certs(conf, subcommand, args, True)
        if failed:
                for pfx, details in failed:
                        error(_("Unable to remove signing ca certificates for "
                            "publisher '%(pfx)s':\n%(details)s") % locals(),
                            cmd=subcommand)
                if len(failed) < len(pubs):
                        return EXIT_PARTIAL
                return EXIT_OOPS
        return EXIT_OK


def subcmd_remove_signing_intermediate_cert(conf, args):
        subcommand = "remove-signing-intermediate-cert"
        pubs, failed = _remove_certs(conf, subcommand, args, True)
        if failed:
                for pfx, details in failed:
                        if pfx:
                                error(_("Unable to remove signing intermediate "
                                    "certificates for publisher '%(pfx)s':\n"
                                    "%(details)s") % locals(), cmd=subcommand)
                        else:
                                error(_("Unable to remove signing intermediate "
                                    "certificates:\n%(details)s") % locals(),
                                    cmd=subcommand)
                if len(failed) < len(pubs):
                        return EXIT_PARTIAL
                return EXIT_OOPS
        return EXIT_OK


def print_col_listing(desired_field_order, field_data, field_values, out_format,
    def_fmt, omit_headers):
        """Print a columnar listing defined by provided values."""

        # Custom sort function for preserving field ordering
        def sort_fields(one, two):
                return desired_field_order.index(get_header(one)) - \
                    desired_field_order.index(get_header(two))

        # Functions for manipulating field_data records
        def filter_default(record):
                return "default" in record[0]

        def filter_tsv(record):
                return "tsv" in record[0]

        def get_header(record):
                return record[1]

        def get_value(record):
                return record[2]

        def quote_value(val):
                if out_format == "tsv":
                        # Expand tabs if tsv output requested.
                        val = val.replace("\t", " " * 8)
                nval = val
                # Escape bourne shell metacharacters.
                for c in ("\\", " ", "\t", "\n", "'", "`", ";", "&", "(", ")",
                    "|", "^", "<", ">"):
                        nval = nval.replace(c, "\\" + c)
                return nval

        def set_value(entry):
                val = entry[1]
                multi_value = False
                if isinstance(val, (list, set)):
                        multi_value = True
                elif val == "":
                        entry[0][2] = '""'
                        return
                elif val is None:
                        entry[0][2] = ''
                        return
                else:
                        val = [val]

                nval = []
                for v in val:
                        if v == "":
                                # Indicate empty string value using "".
                                nval.append('""')
                        elif v is None:
                                # Indicate no value using empty string.
                                nval.append('')
                        else:
                                # Otherwise, escape the value to be displayed.
                                nval.append(quote_value(str(v)))

                val = " ".join(nval)
                nval = None
                if multi_value:
                        val = "(%s)" % val
                entry[0][2] = val

        if out_format == "default":
                # Create a formatting string for the default output
                # format.
                fmt = def_fmt
                filter_func = filter_default
        elif out_format == "tsv":
                # Create a formatting string for the tsv output
                # format.
                num_fields = len(field_data.keys())
                fmt = "\t".join('%s' for x in xrange(num_fields))
                filter_func = filter_tsv

        # Extract the list of headers from the field_data dictionary.  Ensure
        # they are extracted in the desired order by using the custom sort
        # function.
        hdrs = map(get_header, sorted(filter(filter_func, field_data.values()),
            sort_fields))

        # Output a header if desired.
        if not omit_headers:
                msg(fmt % tuple(hdrs))

        for entry in field_values:
                map(set_value, (
                    (field_data[f], v)
                    for f, v in entry.iteritems()
                ))
                values = map(get_value, sorted(filter(filter_func,
                    field_data.values()), sort_fields))
                msg(fmt % tuple(values))


def get_repo(conf, read_only=True, subcommand=None):
        """Return the repository object for current program configuration."""

        repo_uri = conf["repo_uri"]
        if repo_uri.scheme != "file":
                usage(_("Network repositories are not currently supported "
                    "for this operation."), cmd=subcommand)

        path = repo_uri.get_pathname()
        if not path:
                # Bad URI?
                raise sr.RepositoryInvalidError(str(repo_uri))
        return sr.Repository(read_only=read_only, root=path)


def setup_transport(conf, subcommand=None):
        repo_uri = conf.get("repo_uri", None)
        if not repo_uri:
                usage(_("No repository location specified."), cmd=subcommand)

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

        # Configure target publisher.
        src_pub = transport.setup_publisher(str(repo_uri), "target", xport,
            xport_cfg, remote_prefix=True)

        return xport, src_pub, tmp_dir


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

        opts, pargs = getopt.getopt(args, "F:Hp:s:")
        for opt, arg in opts:
                if opt == "-F":
                        out_format = arg
                        if out_format not in LISTING_FORMATS:
                                usage(_("Unrecognized format %(format)s."
                                    " Supported formats: %(valid)s") % \
                                    { "format": out_format,
                                    "valid": LISTING_FORMATS }, cmd="get")
                                return EXIT_OOPS
                elif opt == "-H":
                        omit_headers = True
                elif opt == "-p":
                        pubs.add(arg)
                elif opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)

        # Setup transport so configuration can be retrieved.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)
        xport, xpub, tmp_dir = setup_transport(conf, subcommand=subcommand)

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
            "section" : [("default", "tsv"), _("SECTION"), ""],
            "property" : [("default", "tsv"), _("PROPERTY"), ""],
            "value" : [("default", "tsv"), _("VALUE"), ""],
        }
        desired_field_order = ((_("SECTION"), _("PROPERTY"), _("VALUE")))

        # Default output formatting.
        def_fmt = "%-" + str(max_sname_len) + "s %-" + str(max_pname_len) + \
            "s %s"

        if found or (not req_props and out_format == "default"):
                print_col_listing(desired_field_order, field_data,
                    gen_listing(), out_format, def_fmt, omit_headers)

        if found and notfound:
                return EXIT_PARTIAL
        if req_props and not found:
                if out_format == "default":
                        # Don't pollute other output formats.
                        error(_("no matching properties found"),
                            cmd=subcommand)
                return EXIT_OOPS
        return EXIT_OK


def _get_pub(conf, subcommand, xport, xpub, omit_headers, out_format, pubs,
    pargs):
        """Display publisher properties."""

        # Retrieve publisher information.
        pub_data = xport.get_publisherdata(xpub)
        known_pubs = set(p.prefix for p in pub_data)
        if len(pubs) > 0 and "all" not in pubs:
                found = known_pubs & pubs
                notfound = pubs - found
        else:
                found = known_pubs
                notfound = set()

        # Establish initial return value and perform early exit if appropriate.
        rval = EXIT_OK
        if found and notfound:
                rval = EXIT_PARTIAL
        elif pubs and not found:
                if out_format == "default":
                        # Don't pollute other output formats.
                        error(_("no matching publishers found"),
                            cmd=subcommand)
                return EXIT_OOPS

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
                if pub.prefix not in found:
                        continue

                pub_idx[pub.prefix] = {
                    "publisher": {
                        "alias": pub.alias,
                        "prefix": pub.prefix,
                    },
                }

                pub_repo = pub.selected_repository
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
            "publisher" : [("default", "tsv"), _("PUBLISHER"), ""],
            "section" : [("default", "tsv"), _("SECTION"), ""],
            "property" : [("default", "tsv"), _("PROPERTY"), ""],
            "value" : [("default", "tsv"), _("VALUE"), ""],
        }
        desired_field_order = (_("PUBLISHER"), _("SECTION"), _("PROPERTY"),
            _("VALUE"))

        # Default output formatting.
        def_fmt = "%-" + str(max_pubname_len) + "s %-" + str(max_sname_len) + \
            "s %-" + str(max_pname_len) + "s %s"

        if found or (not req_props and out_format == "default"):
                print_col_listing(desired_field_order, field_data,
                    gen_listing(), out_format, def_fmt, omit_headers)

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

        opts, pargs = getopt.getopt(args, "F:Hp:s:")
        for opt, arg in opts:
                if opt == "-F":
                        if arg not in LISTING_FORMATS:
                                usage(_("Unrecognized format %(format)s."
                                    " Supported formats: %(valid)s") % \
                                    { "format": arg,
                                    "valid": LISTING_FORMATS }, cmd="publisher")
                                return EXIT_OOPS
                        out_format = arg
                elif opt == "-H":
                        omit_headers = True
                elif opt == "-p":
                        pubs.add(arg)
                elif opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)

        if pargs:
                usage(_("command does not take operands"), cmd=subcommand)

        # Setup transport so status can be retrieved.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)
        xport, xpub, tmp_dir = setup_transport(conf, subcommand=subcommand)

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
                for pfx in found:
                        pdata = pub_idx[pfx]
                        pkg_count = pdata.get("package-count", 0)
                        last_update = pdata.get("last-catalog-update", "")
                        if last_update:
                                # Reformat the date into something more user
                                # friendly (and locale specific).
                                last_update = pkg.catalog.basic_ts_to_datetime(
                                    last_update)
                                last_update = "%sZ" % pkg.catalog.datetime_to_ts(
                                    last_update)
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
            "publisher" : [("default", "tsv"), _("PUBLISHER"), ""],
            "packages" : [("default", "tsv"), _("PACKAGES"), ""],
            "status" : [("default", "tsv"), _("STATUS"), ""],
            "updated" : [("default", "tsv"), _("UPDATED"), ""],
        }

        desired_field_order = (_("PUBLISHER"), "", _("PACKAGES"), _("STATUS"),
            _("UPDATED"))

        # Default output formatting.
        pub_len = str(max(
            [len(desired_field_order[0])] + [len(p) for p in found]
        ))
        def_fmt = "%-" + pub_len + "s %-8s %-16s %s"

        if found or (not pubs and out_format == "default"):
                print_col_listing(desired_field_order, field_data,
                    gen_listing(), out_format, def_fmt, omit_headers)

        if found and notfound:
                return EXIT_PARTIAL
        if pubs and not found:
                if out_format == "default":
                        # Don't pollute other output formats.
                        error(_("no matching publishers found"),
                            cmd=subcommand)
                return EXIT_OOPS
        return EXIT_OK


def subcmd_rebuild(conf, args):
        """Rebuild the repository's catalog and index data (as permitted)."""

        subcommand = "rebuild"
        build_catalog = True
        build_index = True

        opts, pargs = getopt.getopt(args, "s:", ["no-catalog", "no-index"])
        for opt, arg in opts:
                if opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt == "--no-catalog":
                        build_catalog = False
                elif opt == "--no-index":
                        build_index = False

        if pargs:
                usage(_("command does not take operands"), cmd=subcommand)

        if not build_catalog and not build_index:
                # Why?  Who knows; but do what was requested--nothing!
                return EXIT_OK

        # Setup transport so operation can be performed.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)
        xport, src_pub, tmp_dir = setup_transport(conf, subcommand=subcommand)

        logger.info("Repository rebuild initiated.")
        if build_catalog and build_index:
                xport.publish_rebuild(src_pub)
        elif build_catalog:
                xport.publish_rebuild_packages(src_pub)
        elif build_index:
                xport.publish_rebuild_indexes(src_pub)

        return EXIT_OK


def subcmd_refresh(conf, args):
        """Refresh the repository's catalog and index data (as permitted)."""

        subcommand = "refresh"
        add_content = True
        refresh_index = True

        opts, pargs = getopt.getopt(args, "s:", ["no-catalog", "no-index"])
        for opt, arg in opts:
                if opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt == "--no-catalog":
                        add_content = False
                elif opt == "--no-index":
                        refresh_index = False

        if pargs:
                usage(_("command does not take operands"), cmd=subcommand)

        if not add_content and not refresh_index:
                # Why?  Who knows; but do what was requested--nothing!
                return EXIT_OK

        # Setup transport so operation can be performed.
        if not conf.get("repo_uri", None):
                usage(_("A package repository location must be provided "
                    "using -s."), cmd=subcommand)
        xport, src_pub, tmp_dir = setup_transport(conf, subcommand=subcommand)

        logger.info("Repository refresh initiated.")
        if add_content and refresh_index:
                xport.publish_refresh(src_pub)
        elif add_content:
                xport.publish_refresh_packages(src_pub)
        elif refresh_index:
                xport.publish_refresh_indexes(src_pub)
        return EXIT_OK


def subcmd_set(conf, args):
        """Set repository properties."""

        subcommand = "set"
        omit_headers = False
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
                return _set_pub(conf, subcommand, omit_headers, props, pubs,
                    repo)

        return _set_repo(conf, subcommand, omit_headers, props, repo)


def _set_pub(conf, subcommand, omit_headers, props, pubs, repo):
        """Set publisher properties."""

        for sname, sprops in props.iteritems():
                if sname not in ("publisher", "repository"):
                        usage(_("unknown property section "
                            "'%s'") % sname, cmd=subcommand)
                for pname in sprops:
                        if sname == "publisher" and pname == "prefix":
                                usage(_("'%s' may not be set using "
                                    "this command" % pname))
                        attrname = pname.replace("-", "_")
                        if not hasattr(publisher.Publisher, attrname) and \
                            not hasattr(publisher.Repository, attrname):
                                usage(_("unknown property '%s'") %
                                    pname, cmd=subcommand)

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
                except sr.RepositoryUnknownPublisher, e:
                        pub = publisher.Publisher(pfx)
                        new_pub = True
                except sr.RepositoryError, e:
                        failed.append((pfx, e))
                        continue

                try:
                        # Set/update the publisher's properties.
                        for sname, sprops in props.iteritems():
                                if sname == "publisher":
                                        target = pub
                                elif sname == "repository":
                                        target = pub.selected_repository
                                        if not target:
                                                target = publisher.Repository()
                                                pub.repositories.append(target)

                                for pname, val in sprops.iteritems():
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
                except apx.ApiException, e:
                        failed.append((pfx, e))
                        continue

                if new_pub:
                        repo.add_publisher(pub)
                else:
                        repo.update_publisher(pub)

        if failed:
                for pfx, details in failed:
                        error(_("Unable to set properties for publisher "
                            "'%(pfx)s':\n%(details)s") % locals())
                if len(failed) < len(pubs):
                        return EXIT_PARTIAL
                return EXIT_OOPS
        return EXIT_OK


def _set_repo(conf, subcommand, omit_headers, props, repo):
        """Set repository properties."""

        # Set properties.
        for sname, props in props.iteritems():
                for pname, val in props.iteritems():
                        repo.cfg.set_property(sname, pname, val)
        repo.write_config()

        return EXIT_OK


def subcmd_version(conf, args):
        """Display the version of the pkg(5) API."""

        subcommand = "version"
        if args:
                usage(_("command does not take operands"), cmd=subcommand)
        msg(pkg.VERSION)
        return EXIT_OK


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

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "s:?",
                    ["help"])
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        conf = {}
        show_usage = False
        for opt, arg in opts:
                if opt == "-s":
                        conf["repo_uri"] = parse_uri(arg)
                elif opt in ("--help", "-?"):
                        show_usage = True

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
        func = globals().get("subcmd_%s" % subcommand, None)
        if not func:
                subcommand = subcommand.replace("_", "-")
                usage(_("unknown subcommand '%s'") % subcommand)

        try:
                return func(conf, pargs)
        except getopt.GetoptError, e:
                if e.opt in ("help", "?"):
                        usage(full=True)
                usage(_("illegal option -- %s") % e.opt, cmd=subcommand)


#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
def handle_errors(func, *args, **kwargs):
        """Catch exceptions raised by the main program function and then print
        a message and/or exit with an appropriate return code.
        """

        traceback_str = _("""\n
This is an internal error in pkg(5) version %(version)s.  Please let the
developers know about this problem by including the information above (and
this message) when filing a bug at:

%(bug_uri)s""") % { "version": pkg.VERSION, "bug_uri": misc.BUG_URI_CLI }

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
                error(_("The pkgrepo command appears out of sync with the "
                    "libraries provided\nby pkg:/package/pkg. The client "
                    "version is %(client)s while the library\nAPI version is "
                    "%(api)s.") % {'client': __e.received_version,
                     'api': __e.expected_version
                    })
                __ret = EXIT_OOPS
        except apx.BadRepositoryURI, __e:
                error(str(__e))
                __ret = EXIT_BADOPT
        except (apx.ApiException, sr.RepositoryError), __e:
                error(str(__e))
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
