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

import errno
import getopt
import gettext
import locale
import logging
import os
import sys
import urllib
import urlparse
import warnings

from pkg.client import global_settings
from pkg.misc import msg, PipeError
import pkg
import pkg.client.api_errors as apx
import pkg.client.publisher as publisher
import pkg.misc as misc
import pkg.server.repository as sr
import shlex
import traceback

logger = global_settings.logger

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
        pkgrepo [options] subcommand [subcmd_options] [operands]

Subcommands:
        pkgrepo create [repo_uri_or_path]
        pkgrepo publisher [pub_prefix ...]
        pkgrepo rebuild [--no-index]
        pkgrepo refresh [--no-catalog] [--no-index]
        pkgrepo version

Options:
        -s repo_uri_or_path     The location of the repository to use for
                                operations.  Network repositories are not
                                currently supported.
        --help or -?"""))

        sys.exit(retcode)

class OptionError(Exception):
        """Option exception. """

        def __init__(self, *args):
                Exception.__init__(self, *args)


def parse_uri(uri):
        """Parse the repository location provided and attempt to transform it
        into a valid repository URI.
        """

        if uri.find("://") == -1 and not uri.startswith("file:/"):
                # Convert the file path to a URI.
                uri = os.path.abspath(uri)
                uri = urlparse.urlunparse(("file", "",
                    urllib.pathname2url(uri), "", "", ""))

        scheme, netloc, path, params, query, fragment = \
            urlparse.urlparse(uri, "file", allow_fragments=0)
        scheme = scheme.lower()

        if scheme != "file":
                usage(_("Network repositories are not currently supported."),
                    retcode=1)

        if scheme == "file":
                # During urlunparsing below, ensure that the path starts with
                # only one '/' character, if any are present.
                if path.startswith("/"):
                        path = "/" + path.lstrip("/")

        # Rebuild the url with the sanitized components.
        uri = urlparse.urlunparse((scheme, netloc, path, params,
            query, fragment))
        return publisher.RepositoryURI(uri)


def get_repo(conf, read_only=True, refresh_index=False):
        """Return the repository object for current program configuration."""

        repo_uri = conf["repo_root"]
        path = repo_uri.get_pathname()
        if not path:
                # Bad URI?
                raise sr.RepositoryInvalidError(str(repo_uri))
        return sr.Repository(auto_create=False, read_only=read_only,
            refresh_index=refresh_index, repo_root=path)


def subcmd_create(conf, args):
        """Create a package repository at the given location."""

        subcommand = "create"
        opts, pargs = getopt.getopt(args, "")

        if len(pargs) > 1:
                usage(_("Only one repository location may be specified."),
                    cmd=subcommand)
        elif pargs:
                conf["repo_root"] = parse_uri(pargs[0])

        repo_root = conf.get("repo_root", None)
        if not repo_root:
                usage(_("No repository location specified."), cmd=subcommand)

        # Attempt to create a repository at the specified location.  Allow
        # whatever exceptions are raised to bubble up.
        sr.repository_create(repo_root)

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

        def set_value(entry):
                entry[0][2] = entry[1]

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


def subcmd_property(conf, args):
        """Display the list of properties for the repository."""

        subcommand = "property"
        repo = get_repo(conf)

        omit_headers = False
        out_format = "default"

        opts, pargs = getopt.getopt(args, "F:H")
        for opt, arg in opts:
                if opt == "-F":
                        out_format = arg
                        if out_format not in LISTING_FORMATS:
                                usage(_("Unrecognized format %(format)s."
                                    " Supported formats: %(valid)s") % \
                                    { "format": out_format,
                                    "valid": LISTING_FORMATS }, cmd="publisher")
                                return EXIT_OOPS
                elif opt == "-H":
                        omit_headers = True

        # Configuration index is indexed by section name and property name.
        # Flatten it to simplify listing process.
        cfg_idx = repo.cfg.get_index()
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
        del cfg_idx

        if len(pargs) >= 1:
                found = props & set(pargs)
                notfound = set(pargs) - found
                del props
        else:
                found = props
                notfound = set()

        def gen_listing():
                for prop in sorted(found):
                        sname, pname = prop.rsplit("/", 1)
                        sval = str(repo.cfg.get_property(sname, pname))
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
        desired_field_order = (_("SECTION"), "", _("PROPERTY"), _("VALUE"))

        # Default output formatting.
        def_fmt = "%-" + str(max_sname_len) + "s %-" + str(max_pname_len) + \
            "s %s"

        if found or (not pargs and out_format == "default"):
                print_col_listing(desired_field_order, field_data,
                    gen_listing(), out_format, def_fmt, omit_headers)

        if found and notfound:
                return EXIT_PARTIAL
        if pargs and not found:
                if out_format == "default":
                        # Don't pollute other output formats.
                        error(_("no matching properties found"),
                            cmd=subcommand)
                return EXIT_OOPS
        return EXIT_OK


def subcmd_set_property(conf, args):
        """Set a repository property."""

        subcommand = "property"
        repo = get_repo(conf, read_only=False)

        omit_headers = False
        out_format = "default"

        opts, pargs = getopt.getopt(args, "")
        bad_args = False
        if not pargs or len(pargs) > 1:
                bad_args = True
        else:
                try:
                        if len(pargs) == 1:
                                prop, val = pargs[0].split("=", 1)
                                sname, pname = prop.rsplit("/", 1)
                except ValueError:
                        bad_args = True

        if bad_args:
                usage(_("a property name and value must be provided in the "
                    "form <section/property>=<value> or "
                    "<section/property>=([\"<value>\", ...])"))

        if len(val) > 0  and val[0] == "(" and val[-1] == ")":
                val = shlex.split(val.strip("()"))

        repo.cfg.set_property(sname, pname, val)
        repo.write_config()


def subcmd_publisher(conf, args):
        """Display a list of known publishers and a summary of known packages
        and when the package data for the given publisher was last updated.
        """

        subcommand = "publisher"
        repo = get_repo(conf)

        omit_headers = False
        out_format = "default"

        opts, pargs = getopt.getopt(args, "F:H")
        for opt, arg in opts:
                if opt == "-F":
                        out_format = arg
                        if out_format not in LISTING_FORMATS:
                                usage(_("Unrecognized format %(format)s."
                                    " Supported formats: %(valid)s") % \
                                    { "format": out_format,
                                    "valid": LISTING_FORMATS }, cmd="publisher")
                                return EXIT_OOPS
                elif opt == "-H":
                        omit_headers = True

        cat = repo.catalog
        pub_idx = {}
        for pub, pkg_count, pkg_ver_count in cat.get_package_counts_by_pub():
                pub_idx[pub] = (pkg_count, pkg_ver_count)

        if len(pargs) >= 1:
                found = set(pub_idx.keys()) & set(pargs)
                notfound = set(pargs) - found
        else:
                found = set(pub_idx.keys())
                notfound = set()

        def gen_listing():
                for pfx in found:
                        pkg_count, pkg_ver_count = pub_idx[pfx]
                        yield {
                            "publisher": pfx,
                            "packages": pkg_count,
                            "versions": pkg_ver_count,
                            "updated": "%sZ" % cat.last_modified.isoformat(),
                        }

        #    PUBLISHER PACKAGES        VERSIONS       UPDATED
        #    <pub_1>   <num_uniq_pkgs> <num_pkg_vers> <cat_last_modified>
        #    <pub_2>   <num_uniq_pkgs> <num_pkg_vers> <cat_last_modified>
        #    ...

        field_data = {
            "publisher" : [("default", "tsv"), _("PUBLISHER"), ""],
            "packages" : [("default", "tsv"), _("PACKAGES"), ""],
            "versions" : [("default", "tsv"), _("VERSIONS"), ""],
            "updated" : [("default", "tsv"), _("UPDATED"), ""],
        }

        desired_field_order = (_("PUBLISHER"), "", _("PACKAGES"), _("VERSIONS"),
            _("UPDATED"))

        # Default output formatting.
        def_fmt = "%-24s %-8s %-8s %s"

        if found or (not pargs and out_format == "default"):
                print_col_listing(desired_field_order, field_data,
                    gen_listing(), out_format, def_fmt, omit_headers)

        if found and notfound:
                return EXIT_PARTIAL
        if pargs and not found:
                if out_format == "default":
                        # Don't pollute other output formats.
                        error(_("no matching publishers found"),
                            cmd=subcommand)
                return EXIT_OOPS
        return EXIT_OK


def subcmd_rebuild(conf, args):
        """Rebuild the repository's catalog and index data (as permitted)."""

        subcommand = "rebuild"
        repo = get_repo(conf, read_only=False)

        build_index = True
        opts, pargs = getopt.getopt(args, "", ["no-index"])
        for opt, arg in opts:
                if opt == "--no-index":
                        build_index = False

        if pargs:
                usage(_("command does not take operands"), cmd=subcommand)

        logger.info("Rebuilding package repository...")
        repo.rebuild(build_index=False)

        if build_index:
                # Always build search indexes seperately (and if permitted).
                logger.info("Building search indexes...")
                repo.refresh_index()

        return EXIT_OK


def subcmd_refresh(conf, args):
        """Refresh the repository's catalog and index data (as permitted)."""

        subcommand = "refresh"
        repo = get_repo(conf, read_only=False)

        add_content = True
        refresh_index = True
        opts, pargs = getopt.getopt(args, "", ["no-catalog", "no-index"])
        for opt, arg in opts:
                if opt == "--no-catalog":
                        add_content = False
                elif opt == "--no-index":
                        refresh_index = False

        if pargs:
                usage(_("command does not take operands"), cmd=subcommand)

        if not add_content and not refresh_index:
                # Why?  Who knows; but do what was requested--nothing!
                return EXIT_OK

        if add_content:
                logger.info("Adding new package content...")
                repo.add_content(refresh_index=False)

        if refresh_index:
                # Always update search indexes separately (and if permitted).
                logger.info("Updating search indexes...")
                repo.refresh_index()

        return EXIT_OK


def subcmd_version(conf, args):
        """Display the version of the pkg(5) API."""

        subcommand = "version"

        if conf.get("repo_root", None):
                usage(_("-s not allowed for %s subcommand") %
                      subcommand)
        if args:
                usage(_("command does not take operands"), cmd=subcommand)
        msg(pkg.VERSION)
        return EXIT_OK


def main_func():
        global_settings.client_name = PKG_CLIENT_NAME

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "s:?",
                    ["help"])
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        conf = {}
        show_usage = False
        for opt, arg in opts:
                if opt == "-s":
                        if not arg:
                                continue
                        conf["repo_root"] = parse_uri(arg)
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
                usage(_("unknown subcommand '%s'") % subcommand)

        try:
                if (subcommand != "create" and subcommand != "version") and \
                    not conf.get("repo_root", None):
                        usage(_("A package repository location must be "
                            "provided using -s."), cmd=subcommand)
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

        traceback_str = _("\n\nThis is an internal error.  Please let the "
            "developers know about this\nproblem by filing a bug at "
            "http://defect.opensolaris.org and including the\nabove "
            "traceback and this message.  The version of pkg(5) is "
            "'%s'.") % pkg.VERSION
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
