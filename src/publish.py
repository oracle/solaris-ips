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
# Copyright (c) 2007, 2011, Oracle and/or its affiliates. All rights reserved.
#

import fnmatch
import getopt
import gettext
import os
import sys
import traceback
import warnings
import errno

import pkg.actions
import pkg.bundle
import pkg.client.api_errors as apx
import pkg.fmri
import pkg.manifest
import pkg.misc as misc
import pkg.publish.transaction as trans
import pkg.client.transport.transport as transport
import pkg.client.publisher as publisher
from pkg.misc import msg, emsg, PipeError
from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues

nopub_actions = [ "unknown" ]

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if not isinstance(text, basestring):
                # Assume it's an object that can be stringified.
                text = str(text)

        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        if cmd:
                text_nows = "%s: %s" % (cmd, text_nows)
                pkg_cmd = "pkgsend "
        else:
                pkg_cmd = "pkgsend: "

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        emsg(ws + pkg_cmd + text_nows)

def usage(usage_error=None, cmd=None, retcode=2):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if usage_error:
                error(usage_error, cmd=cmd)

        print _("""\
Usage:
        pkgsend [options] command [cmd_options] [operands]

Packager subcommands:
        pkgsend generate [-T pattern] [--target file] source ...
        pkgsend publish [-b bundle ...] [-d source ...] [-s repo_uri_or_path]
            [-T pattern] [--no-catalog] [manifest ...]

Options:
        --help or -?    display usage message

Environment:
        PKG_REPO        The path or URI of the destination repository.""")
        sys.exit(retcode)

class SolarisBundleVisitor(object):
        """Used to gather information about the SVR4 packages we visit"""

        def __init__(self):
                # a list of classes for which we do not report warnings
                self.known_classes = ["none", "manifest"]
                self.errors = set()
                self.warnings = set()
                self.visited = False

        def visit(self, bundle):
                """visit a pkg.bundle.SolarisPackage*Bundle object"""

                if not bundle.pkg:
                        return

                if self.visited:
                        self.warnings.add(_(
                            "WARNING: Several SVR4 packages detected. "
                            "Multiple pkg.summary and pkg.description "
                            "attributes may have been generated."))

                for action in bundle:
                        if "path" not in action.attrs:
                                continue
                        path = action.attrs["path"]
                        if path in bundle.class_actions_dir:
                                svr4_class = bundle.class_actions_dir[path]
                                if svr4_class and \
                                    svr4_class not in self.known_classes:
                                        self.errors.add(
                                            _("ERROR: class action script "
                                            "used in %(pkg)s: %(path)s belongs "
                                            "to \"%(class)s\" class") %
                                            {"pkg": bundle.pkgname,
                                             "path": path, "class": svr4_class})
                for script in bundle.scripts:
                        self.errors.add(
                            _("ERROR: script present in %(pkg)s: %(script)s") %
                            {"pkg": bundle.pkgname, "script": script})

                self.visited = True


def trans_create_repository(repo_uri, args):
        """DEPRECATED"""

        repo_props = {}
        opts, pargs = getopt.getopt(args, "", ["set-property="])
        for opt, arg in opts:
                if opt == "--set-property":
                        try:
                                prop, p_value = arg.split("=", 1)
                                p_sec, p_name = prop.split(".", 1)
                        except ValueError:
                                usage(_("property arguments must be of "
                                    "the form '<section.property>="
                                    "<value>'."), cmd="create-repository")
                        repo_props.setdefault(p_sec, {})
                        repo_props[p_sec][p_name] = p_value

        xport, pub = setup_transport_and_pubs(repo_uri, remote=False)

        try:
                trans.Transaction(repo_uri, create_repo=True,
                    repo_props=repo_props, xport=xport, pub=pub)
        except trans.TransactionRepositoryConfigError, e:
                error(e, cmd="create-repository")
                emsg(_("Invalid repository configuration values were "
                    "specified using --set-property or required values are "
                    "missing.  Please provide the correct and/or required "
                    "values using the --set-property option."))
        except trans.TransactionError, e:
                error(e, cmd="create-repository")
                return 1
        return 0

def trans_open(repo_uri, args):
        """DEPRECATED"""

        opts, pargs = getopt.getopt(args, "en")

        parsed = []
        eval_form = True
        for opt, arg in opts:
                parsed.append(opt)
                if opt == "-e":
                        eval_form = True
                if opt == "-n":
                        eval_form = False

        if "-e" in parsed and "-n" in parsed:
                usage(_("only -e or -n may be specified"), cmd="open")

        if len(pargs) != 1:
                usage(_("open requires one package name"), cmd="open")

        xport, pub = setup_transport_and_pubs(repo_uri)

        t = trans.Transaction(repo_uri, pkg_name=pargs[0], xport=xport, pub=pub)
        if eval_form:
                msg("export PKG_TRANS_ID=%s" % t.open())
        else:
                msg(t.open())

        return 0

def trans_append(repo_uri, args):
        """DEPRECATED"""

        opts, pargs = getopt.getopt(args, "en")

        parsed = []
        eval_form = True
        for opt, arg in opts:
                parsed.append(opt)
                if opt == "-e":
                        eval_form = True
                if opt == "-n":
                        eval_form = False

        if "-e" in parsed and "-n" in parsed:
                usage(_("only -e or -n may be specified"), cmd="open")

        if len(pargs) != 1:
                usage(_("append requires one package name"), cmd="open")

        xport, pub = setup_transport_and_pubs(repo_uri)

        t = trans.Transaction(repo_uri, pkg_name=pargs[0], xport=xport, pub=pub)
        if eval_form:
                msg("export PKG_TRANS_ID=%s" % t.append())
        else:
                msg(t.append())

        return 0

def trans_close(repo_uri, args):
        """DEPRECATED"""

        abandon = False
        trans_id = None
        add_to_catalog = True

        # --no-index is now silently ignored as the publication process no
        # longer builds search indexes automatically.
        opts, pargs = getopt.getopt(args, "At:", ["no-index", "no-catalog"])

        for opt, arg in opts:
                if opt == "-A":
                        abandon = True
                elif opt == "-t":
                        trans_id = arg
                elif opt == "--no-catalog":
                        add_to_catalog = False
        if trans_id is None:
                try:
                        trans_id = os.environ["PKG_TRANS_ID"]
                except KeyError:
                        usage(_("No transaction ID specified using -t or in "
                            "$PKG_TRANS_ID."), cmd="close")

        xport, pub = setup_transport_and_pubs(repo_uri)
        t = trans.Transaction(repo_uri, trans_id=trans_id, xport=xport, pub=pub)
        pkg_state, pkg_fmri = t.close(abandon=abandon,
            add_to_catalog=add_to_catalog)
        for val in (pkg_state, pkg_fmri):
                if val is not None:
                        msg(val)
        return 0

def trans_add(repo_uri, args):
        """DEPRECATED"""

        try:
                trans_id = os.environ["PKG_TRANS_ID"]
        except KeyError:
                usage(_("No transaction ID specified in $PKG_TRANS_ID"),
                    cmd="add")

        if not args:
                usage(_("No arguments specified for subcommand."), cmd="add")

        action, lp = pkg.actions.internalizelist(args[0], args[1:])

        if action.name in nopub_actions:
                error(_("invalid action for publication: %s") % action, cmd="add")
                return 1

        xport, pub = setup_transport_and_pubs(repo_uri)
        t = trans.Transaction(repo_uri, trans_id=trans_id, xport=xport,
            pub=pub)
        t.add(action)
        return 0

def trans_publish(repo_uri, fargs):
        """Publish packages in a single step using provided manifest data and
        sources."""

        # --no-index is now silently ignored as the publication process no
        # longer builds search indexes automatically.
        opts, pargs = getopt.getopt(fargs, "b:d:s:T:", ["fmri-in-manifest",
            "no-index", "no-catalog"])

        add_to_catalog = True
        basedirs = []
        bundles = []
        timestamp_files = []
        for opt, arg in opts:
                if opt == "-b":
                        bundles.append(arg)
                elif opt == "-d":
                        basedirs.append(arg)
                elif opt == "-s":
                        repo_uri = arg
                        if repo_uri and not repo_uri.startswith("null:"):
                                repo_uri = misc.parse_uri(repo_uri)
                elif opt == "-T":
                        timestamp_files.append(arg)
                elif opt == "--no-catalog":
                        add_to_catalog = False

        if not repo_uri:
                usage(_("A destination package repository must be provided "
                    "using -s."), cmd="publish")
 
        if not pargs:
                filelist = [("<stdin>", sys.stdin)]
        else:
                try:
                        filelist = [(f, file(f)) for f in pargs]
                except IOError, e:
                        error(e, cmd="publish")
                        return 1

        lines = ""      # giant string of all input files concatenated together
        linecnts = []   # tuples of starting line number, ending line number
        linecounter = 0 # running total

        for filename, f in filelist:
                try:
                        data = f.read()
                except IOError, e:
                        error(e, cmd="publish")
                        return 1
                lines += data
                linecnt = len(data.splitlines())
                linecnts.append((linecounter, linecounter + linecnt))
                linecounter += linecnt

        m = pkg.manifest.Manifest()
        try:
                m.set_content(content=lines)
        except apx.InvalidPackageErrors, err:
                e = err.errors[0]
                lineno = e.lineno
                for i, tup in enumerate(linecnts):
                        if lineno > tup[0] and lineno <= tup[1]:
                                filename = filelist[i][0]
                                lineno -= tup[0]
                                break
                else:
                        filename = "???"
                        lineno = "???"

                error(_("File %s line %s: %s") % (filename, lineno, e),
                    cmd="publish")
                return 1

        try:
                pfmri = pkg.fmri.PkgFmri(m["pkg.fmri"], "5.11")
                if not DebugValues["allow-timestamp"]:
                        # If not debugging, timestamps are ignored.
                        pfmri.version.timestr = None
                pkg_name = pfmri.get_fmri()
        except KeyError:
                error(_("Manifest does not set pkg.fmri"))
                return 1

        xport, pub = setup_transport_and_pubs(repo_uri)
        t = trans.Transaction(repo_uri, pkg_name=pkg_name,
            xport=xport, pub=pub)
        t.open()

        target_files = []
        if bundles:
                # Ensure hardlinks marked as files in the manifest are
                # treated as files.  This necessary when sourcing files
                # from some bundle types.
                target_files.extend(
                    a.attrs["path"]
                    for a in m.gen_actions()
                    if a.name == "file"
                )

        bundles = [
            pkg.bundle.make_bundle(bundle, target_files)
            for bundle in bundles
        ]

        for a in m.gen_actions():
                # don't publish these actions
                if a.name == "signature":
                        msg(_("WARNING: Omitting signature action '%s'" % a))
                        continue
                if a.name == "set" and a.attrs["name"] in ["pkg.fmri", "fmri"]:
                        continue
                elif a.has_payload:
                        # Don't trust values provided; forcibly discard these.
                        a.attrs.pop("pkg.size", None)
                        a.attrs.pop("pkg.csize", None)
                        path = pkg.actions.set_action_data(a.hash, a,
                            basedirs=basedirs, bundles=bundles)[0]
                elif a.name in nopub_actions:
                        error(_("invalid action for publication: %s") % action,
                            cmd="publish")
                        t.close(abandon=True)
                        return 1
                if a.name == "file":
                        basename = os.path.basename(a.attrs["path"])
                        for pattern in timestamp_files:
                                if fnmatch.fnmatch(basename, pattern):
                                        if not isinstance(path, basestring):
                                                # Target is from bundle; can't
                                                # apply timestamp now.
                                                continue
                                        ts = misc.time_to_timestamp(
                                            os.stat(path).st_mtime)
                                        a.attrs["timestamp"] = ts
                                        break
                try:
                        t.add(a)
                except:
                        t.close(abandon=True)
                        raise

        pkg_state, pkg_fmri = t.close(abandon=False,
            add_to_catalog=add_to_catalog)
        for val in (pkg_state, pkg_fmri):
                if val is not None:
                        msg(val)
        return 0

def trans_include(repo_uri, fargs, transaction=None):
        """DEPRECATED"""

        basedirs = []
        timestamp_files = []
        error_occurred = False

        opts, pargs = getopt.getopt(fargs, "d:T:")
        for opt, arg in opts:
                if opt == "-d":
                        basedirs.append(arg)
                elif opt == "-T":
                        timestamp_files.append(arg)

        if transaction == None:
                try:
                        trans_id = os.environ["PKG_TRANS_ID"]
                except KeyError:
                        usage(_("No transaction ID specified in $PKG_TRANS_ID"),
                            cmd="include")
                xport, pub = setup_transport_and_pubs(repo_uri)
                t = trans.Transaction(repo_uri, trans_id=trans_id, xport=xport,
                    pub=pub)
        else:
                t = transaction

        if not pargs:
                filelist = [("<stdin>", sys.stdin)]
        else:
                try:
                        filelist = [(f, file(f)) for f in pargs]
                except IOError, e:
                        error(e, cmd="include")
                        return 1

        lines = []      # giant string of all input files concatenated together
        linecnts = []   # tuples of starting line number, ending line number
        linecounter = 0 # running total

        for filename, f in filelist:
                try:
                        data = f.read()
                except IOError, e:
                        error(e, cmd="include")
                        return 1
                lines.append(data)
                linecnt = len(data.splitlines())
                linecnts.append((linecounter, linecounter + linecnt))
                linecounter += linecnt

        m = pkg.manifest.Manifest()
        try:
                m.set_content(content="\n".join(lines))
        except apx.InvalidPackageErrors, err:
                e = err.errors[0]
                lineno = e.lineno
                for i, tup in enumerate(linecnts):
                        if lineno > tup[0] and lineno <= tup[1]:
                                filename = filelist[i][0]
                                lineno -= tup[0]
                                break
                else:
                        filename = "???"
                        lineno = "???"

                error(_("File %s line %s: %s") % (filename, lineno, e),
                    cmd="include")
                return 1

        invalid_action = False

        for a in m.gen_actions():
                # don't publish this action
                if a.name == "set" and a.attrs["name"] in  ["pkg.fmri", "fmri"]:
                        continue
                elif a.has_payload:
                        path, bd = pkg.actions.set_action_data(a.hash, a,
                            basedirs)
                if a.name == "file":
                        basename = os.path.basename(a.attrs["path"])
                        for pattern in timestamp_files:
                                if fnmatch.fnmatch(basename, pattern):
                                        ts = misc.time_to_timestamp(
                                            os.stat(path).st_mtime)
                                        a.attrs["timestamp"] = ts
                                        break

                if a.name in nopub_actions:
                        error(_("invalid action for publication: %s") % str(a),
                            cmd="include")
                        invalid_action = True
                else:
                        t.add(a)

        if invalid_action:
                return 3
        else:
                return 0

def gen_actions(files, timestamp_files, target_files, minimal=False, visitors=[]):
        for filename in files:
                bundle = pkg.bundle.make_bundle(filename, target_files)
                for visitor in visitors:
                        visitor.visit(bundle)

                for action in bundle:
                        if action.name in ("file", "dir"):
                                basename = os.path.basename(action.attrs["path"])
                                for pattern in timestamp_files:
                                        if fnmatch.fnmatch(basename, pattern):
                                                break
                                else:
                                        action.attrs.pop("timestamp", None)

                        if action.name == "license":
                                # The bundle code provides this for the importer,
                                # but it is unnecessary in all other cases.
                                action.attrs.pop("path", None)

                        if minimal:
                                # pkgsend import needs attributes such as size
                                # retained so that the publication modules know
                                # how many bytes to read from the .data prop.
                                # However, pkgsend generate attempts to
                                # minimize the attributes output for each
                                # action to only those necessary for use
                                # so that the resulting manifest remains valid
                                # even after mogrification or changing content.
                                action.attrs.pop("pkg.size", None)

                        yield action, action.name in nopub_actions

def trans_import(repo_uri, args, visitors=[]):
        """DEPRECATED"""

        try:
                trans_id = os.environ["PKG_TRANS_ID"]
        except KeyError:
                print >> sys.stderr, \
                    _("No transaction ID specified in $PKG_TRANS_ID")
                sys.exit(1)

        opts, pargs = getopt.getopt(args, "T:", ["target="])

        timestamp_files = []
        target_files = []

        for opt, arg in opts:
                if opt == "-T":
                        timestamp_files.append(arg)
                elif opt == "--target":
                        target_files.append(arg)

        if not args:
                usage(_("No arguments specified for subcommand."),
                    cmd="import")

        xport, pub = setup_transport_and_pubs(repo_uri)
        t = trans.Transaction(repo_uri, trans_id=trans_id, xport=xport, pub=pub)

        ret = 0
        abandon = False
        try:
                for action, err in gen_actions(pargs, timestamp_files,
                    target_files, visitors=visitors):
                        if err:
                                error(_("invalid action for publication: %s") %
                                    action, cmd="import")
                                abandon = True
                        else:
                                if not abandon:
                                        t.add(action)
        except TypeError, e:
                error(e, cmd="import")
                return 1
        except EnvironmentError, e:
                if e.errno == errno.ENOENT:
                        error("%s: '%s'" % (e.args[1], e.filename),
                            cmd="import")
                        return 1
                else:
                        raise

        for visitor in visitors:
                if visitor.errors:
                        abandon = True
                        ret = 1
        if abandon:
                error("Abandoning transaction due to errors.")
                t.close(abandon=True)
        return ret

def trans_generate(args, visitors=[]):
        """Generate a package manifest based on the provided sources."""

        opts, pargs = getopt.getopt(args, "T:", ["target="])

        timestamp_files = []
        target_files = []

        for opt, arg in opts:
                if opt == "-T":
                        timestamp_files.append(arg)
                elif opt == "--target":
                        target_files.append(arg)

        if not args:
                usage(_("No arguments specified for subcommand."),
                    cmd="generate")

        try:
                for action, err in gen_actions(pargs, timestamp_files,
                    target_files, minimal=True, visitors=visitors):
                        if "path" in action.attrs and hasattr(action, "hash") \
                            and action.hash == "NOHASH":
                                action.hash = action.attrs["path"]
                        print action
        except TypeError, e:
                error(e, cmd="generate")
                return 1
        except EnvironmentError, e:
                if e.errno == errno.ENOENT:
                        error("%s: '%s'" % (e.args[1], e.filename),
                            cmd="generate")
                        return 1
                else:
                        raise

        return 0

def trans_refresh_index(repo_uri, args):
        """DEPRECATED"""

        if args:
                usage(_("command does not take operands"),
                    cmd="refresh-index")

        xport, pub = setup_transport_and_pubs(repo_uri)
        try:
                t = trans.Transaction(repo_uri, xport=xport,
                    pub=pub).refresh_index()
        except trans.TransactionError, e:
                error(e, cmd="refresh-index")
                return 1
        return 0

def setup_transport_and_pubs(repo_uri, remote=True):

        if repo_uri.startswith("null:"):
                return None, None

        xport, xport_cfg = transport.setup_transport()
        targ_pub = transport.setup_publisher(repo_uri, "default",
            xport, xport_cfg, remote_prefix=remote)

        return xport, targ_pub

def main_func():
        gettext.install("pkg", "/usr/share/locale")

        repo_uri = os.getenv("PKG_REPO", None)

        show_usage = False
        global_settings.client_name = "pkgsend"
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "s:D:?", ["help"])
                for opt, arg in opts:
                        if opt == "-s":
                                repo_uri = arg
                        elif opt == "-D":
                                if arg == "allow-timestamp":
                                        key = arg
                                        value = True
                                else:
                                        try:
                                                key, value = arg.split("=", 1)
                                        except (AttributeError, ValueError):
                                                usage(_("%(opt)s takes argument of form "
                                                    "name=value, not %(arg)s") % {
                                                    "opt":  opt, "arg": arg })
                                DebugValues.set_value(key, value)
                        elif opt in ("--help", "-?"):
                                show_usage = True
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        if repo_uri and not repo_uri.startswith("null:"):
                repo_uri = misc.parse_uri(repo_uri)

        subcommand = None
        if pargs:
                subcommand = pargs.pop(0)
                if subcommand == "help":
                        show_usage = True

        if show_usage:
                usage(retcode=0)
        elif not subcommand:
                usage()

        if not repo_uri and subcommand not in ("create-repository", "generate",
            "publish"):
                usage(_("A destination package repository must be provided "
                    "using -s."), cmd=subcommand)

        visitors = [SolarisBundleVisitor()]
        ret = 0
        try:
                if subcommand == "create-repository":
                        ret = trans_create_repository(repo_uri, pargs)
                elif subcommand == "open":
                        ret = trans_open(repo_uri, pargs)
                elif subcommand == "append":
                        ret = trans_append(repo_uri, pargs)
                elif subcommand == "close":
                        ret = trans_close(repo_uri, pargs)
                elif subcommand == "add":
                        ret = trans_add(repo_uri, pargs)
                elif subcommand == "import":
                        ret = trans_import(repo_uri, pargs,
                            visitors=visitors)
                elif subcommand == "include":
                        ret = trans_include(repo_uri, pargs)
                elif subcommand == "publish":
                        ret = trans_publish(repo_uri, pargs)
                elif subcommand == "generate":
                        ret = trans_generate(pargs,
                            visitors=visitors)
                elif subcommand == "refresh-index":
                        ret = trans_refresh_index(repo_uri, pargs)
                else:
                        usage(_("unknown subcommand '%s'") % subcommand)

                printed_space = False
                for visitor in visitors:
                        for warn in visitor.warnings:
                                if not printed_space:
                                        print ""
                                        printed_space = True
                                error(warn, cmd=subcommand)

                        for err in visitor.errors:
                                if not printed_space:
                                        print ""
                                        printed_space = True
                                error(err, cmd=subcommand)
                                ret = 1
        except pkg.bundle.InvalidBundleException, e:
                error(e, cmd=subcommand)
                ret = 1
        except getopt.GetoptError, e:
                usage(_("illegal %s option -- %s") % (subcommand, e.opt))

        return ret

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":

        # Make all warnings be errors.
        warnings.simplefilter('error')

        try:
                __ret = main_func()
        except (PipeError, KeyboardInterrupt):
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                __ret = 1
        except (pkg.actions.ActionError, trans.TransactionError,
            EnvironmentError, RuntimeError, pkg.fmri.FmriError,
            apx.ApiException), _e:
                if not (isinstance(_e, IOError) and _e.errno == errno.EPIPE):
                        # Only print message if failure wasn't due to
                        # broken pipe (EPIPE) error.
                        print >> sys.stderr, "pkgsend: %s" % _e
                __ret = 1
        except SystemExit, _e:
                raise _e
        except:
                traceback.print_exc()
                error(misc.get_traceback_message())
                __ret = 99
        sys.exit(__ret)
