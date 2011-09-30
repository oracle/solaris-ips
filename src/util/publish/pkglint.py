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
# Copyright (c) 2010, 2011 Oracle and/or its affiliates. All rights reserved.
#

import codecs
import logging
import sys
import gettext
import traceback
from optparse import OptionParser

gettext.install("pkg", "/usr/share/locale")

from pkg.client.api_errors import InvalidPackageErrors
from pkg import VERSION
from pkg.misc import PipeError

import pkg.lint.engine as engine
import pkg.lint.log as log
import pkg.fmri as fmri
import pkg.manifest
import pkg.misc as misc

logger = None

def error(message):
        logger.error(_("Error: %s") % message)

def msg(message):
        logger.info(message)

def debug(message):
        logger.debug(message)

def main_func():
        """Start pkglint."""

        global logger
        
        usage = \
            _("\n"
            "        %prog [-b build_no] [-c cache_dir] [-f file]\n"
            "            [-l uri] [-p regexp] [-r uri] [-v]\n"
            "            [manifest ...]\n"
            "        %prog -L")
        parser = OptionParser(usage=usage)

        parser.add_option("-b", dest="release", metavar="build_no",
            help=_("build to use from lint and reference repositories"))
        parser.add_option("-c", dest="cache", metavar="dir",
            help=_("directory to use as a repository cache"))
        parser.add_option("-f", dest="config", metavar="file",
            help=_("specify an alternative pkglintrc file"))
        parser.add_option("-l", dest="lint_uris", metavar="uri",
            action="append", help=_("lint repository URI"))
        parser.add_option("-L", dest="list_checks",
            action="store_true",
            help=_("list checks configured for this session and exit"))
        parser.add_option("-p", dest="pattern", metavar="regexp",
            help=_("pattern to match FMRIs in lint URI"))
        parser.add_option("-r", dest="ref_uris", metavar="uri",
            action="append", help=_("reference repository URI"))
        parser.add_option("-v", dest="verbose", action="store_true",
            help=_("produce verbose output, overriding settings in pkglintrc")
            )

        opts, args = parser.parse_args(sys.argv[1:])

        # without a cache option, we can't access repositories, so expect
        # local manifests.
        if not (opts.cache or opts.list_checks) and not args:
                parser.error(
                    _("Required -c option missing, no local manifests provided."
                    ))

        pattern = opts.pattern
        opts.ref_uris = _make_list(opts.ref_uris)
        opts.lint_uris = _make_list(opts.lint_uris)

        if len(opts.ref_uris) > 1:
                parser.error(
                    _("Only one -r option is supported."))

        if len(opts.lint_uris) > 1:
                parser.error(
                   _("Only one -l option is supported."))

        logger = logging.getLogger("pkglint")
        ch = logging.StreamHandler(sys.stdout)

        if opts.verbose:
                logger.setLevel(logging.DEBUG)
                ch.setLevel(logging.DEBUG)

        else:
                logger.setLevel(logging.INFO)
                ch.setLevel(logging.INFO)

        logger.addHandler(ch)

        lint_logger = log.PlainLogFormatter()
        try:
                if not opts.list_checks:
                        msg(_("Lint engine setup..."))
                lint_engine = engine.LintEngine(lint_logger,
                    config_file=opts.config, verbose=opts.verbose)

                if opts.list_checks:
                        list_checks(lint_engine.checkers,
                            lint_engine.excluded_checkers, opts.verbose)
                        return 0

                if (opts.lint_uris or opts.ref_uris) and not opts.cache:
                        parser.error(
                            _("Required -c option missing when using "
                            "repositories."))

                manifests = []
                if len(args) >= 1:
                        manifests = read_manifests(args, lint_logger)
                        if None in manifests:
                                error(_("Fatal error in manifest - exiting."))
                                return 1
                lint_engine.setup(ref_uris=opts.ref_uris,
                    lint_uris=opts.lint_uris,
                    lint_manifests=manifests,
                    cache=opts.cache,
                    pattern=pattern,
                    release=opts.release)

                msg(_("Starting lint run..."))

                lint_engine.execute()
                lint_engine.teardown()
                lint_logger.close()

        except engine.LintEngineException, err:
                error(err)
                return 1

        if lint_logger.produced_lint_msgs():
                return 1
        else:
                return 0

def list_checks(checkers, exclude, verbose=False):
        """Prints a human-readable version of configured checks."""

        # used for justifying output
        width = 28

        def get_method_desc(method, verbose):
                if "pkglint_desc" in method.func_dict and not verbose:
                        return method.pkglint_desc
                else:
                        return "%s.%s.%s" % (method.im_class.__module__,
                            method.im_class.__name__,
                            method.im_func.func_name)

        def emit(name, value):
                msg("%s %s" % (name.ljust(width), value))

        def print_list(items):
                k = items.keys()
                k.sort()
                for lint_id in k:
                        emit(lint_id, items[lint_id])

        include_items = {}
        exclude_items = {}

        for checker in checkers:
                for m, lint_id in checker.included_checks:
                        include_items[lint_id] = get_method_desc(m, verbose)

        for checker in exclude:
                for m, lint_id in checker.excluded_checks:
                        exclude_items[lint_id] = get_method_desc(m, verbose)
                for m, lint_id in checker.included_checks:
                        exclude_items[lint_id] = get_method_desc(m, verbose)

        for checker in checkers:
                for m, lint_id in checker.excluded_checks:
                        exclude_items[lint_id] = get_method_desc(m, verbose)

        if include_items or exclude_items:
                if verbose:
                        emit(_("NAME"), _("METHOD"))
                else:
                        emit(_("NAME"), _("DESCRIPTION"))
                print_list(include_items)

                if exclude_items:
                        msg(_("\nExcluded checks:"))
                        print_list(exclude_items)

def read_manifests(names, lint_logger):
        """Read a list of filenames, return a list of Manifest objects."""

        manifests = []
        for filename in names:
                data = None
                # borrowed code from publish.py
                lines = []      # giant string of all input lines
                linecnts = []   # tuples of starting line no., ending line no
                linecounter = 0 # running total
                try:
                        f = codecs.open(filename, "rb", "utf-8")
                        data = f.read()
                except UnicodeDecodeError, e:
                        lint_logger.critical(_("Invalid file %s: "
                            "manifest not encoded in UTF-8: %s") %
                            (filename, e), msgid="lint.manifest002")
                        continue
                except IOError, e:
                        lint_logger.critical(_("Unable to read manifest file "
                        "%s: %s") % (filename, e), msgid="lint.manifest001")
                        continue
                lines.append(data)
                linecnt = len(data.splitlines())
                linecnts.append((linecounter, linecounter + linecnt))
                linecounter += linecnt

                manifest = pkg.manifest.Manifest()
                try:
                        manifest.set_content(content="\n".join(lines))
                except pkg.actions.ActionError, e:
                        lineno = e.lineno
                        for i, tup in enumerate(linecnts):
                                if lineno > tup[0] and lineno <= tup[1]:
                                        lineno -= tup[0]
                                        break
                        else:
                                lineno = "???"

                        lint_logger.critical(
                            _("Error in %(file)s line: %(ln)s: %(err)s ") %
                            {"file": filename,
                             "ln": lineno,
                             "err": str(e)}, "lint.manifest002")
                        manifest = None
                except InvalidPackageErrors, e:
                        lint_logger.critical(
                            _("Error in file %(file)s: %(err)s") %
                            {"file": filename,
                            "err": str(e)}, "lint.manifest002")
                        manifest = None

                if manifest and "pkg.fmri" in manifest:
                        try:
                                manifest.fmri = \
                                    pkg.fmri.PkgFmri(manifest["pkg.fmri"],
                                        "5.11")
                        except fmri.IllegalFmri, e:
                                lint_logger.critical(
                                    _("Error in file %(file)s: "
                                    "%(err)s") %
                                    {"file": filename, "err": e},
                                    "lint.manifest002")
                        if manifest.fmri:
                                if not manifest.fmri.version:
                                        lint_logger.critical(
                                            _("Error in file %s: "
                                            "pkg.fmri does not include a "
                                            "version string") % filename,
                                            "lint.manifest003")
                                else:
                                        manifests.append(manifest)

                elif manifest:
                        lint_logger.critical(
                            _("Manifest %s does not declare fmri.") % filename,
                            "lint.manifest003")
                else:
                        manifests.append(None)
        return manifests

def _make_list(opt):
        """Makes a list out of opt, and returns it."""

        if isinstance(opt, list):
                return opt
        elif opt is None:
                return []
        else:
                return [opt]


if __name__ == "__main__":
        try:
                value = main_func()
                sys.exit(value)
        except (PipeError, KeyboardInterrupt):
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                __ret = 1
        except SystemExit, _e:
                raise _e
        except:
                traceback.print_exc()
                error(misc.get_traceback_message())
                sys.exit(99)
