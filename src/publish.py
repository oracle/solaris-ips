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
# Copyright (c) 2007, 2010, Oracle and/or its affiliates. All rights reserved.
#

# pkgsend - publish package transactions
#
# Typical usage is
#
#       pkgsend open
#       [pkgsend summary]
#       pkgsend close
#
# A failed transaction can be cleared using
#
#       pkgsend close -A

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
import pkg.publish.transaction as trans
import pkg.client.transport.transport as transport
import pkg.client.publisher as publisher
from pkg.misc import msg, emsg, PipeError
from pkg.client import global_settings

nopub_actions = [ "unknown" ]

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if cmd:
                text = "%s: %s" % (cmd, text)
        else:
                # If we get passed something like an Exception, we can convert
                # it down to a string.
                text = str(text)

        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        emsg(ws + "pkgsend: " + text_nows)

def usage(usage_error=None, cmd=None, retcode=2):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if usage_error:
                error(usage_error, cmd=cmd)

        print _("""\
Usage:
        pkgsend [options] command [cmd_options] [operands]

Packager subcommands:
        pkgsend open [-en] pkg_fmri
        pkgsend add action arguments
        pkgsend import [-T pattern] [--target file] bundlefile ...
        pkgsend include [-d basedir] ... [manifest] ...
        pkgsend close [-A | [--no-index] [--no-catalog]]
        pkgsend publish [ -d basedir] ... [--no-index]
          [--fmri-in-manifest | pkg_fmri] [--no-catalog] [manifest] ...
        pkgsend generate [-T pattern] [--target file] bundlefile ...
        pkgsend refresh-index

Options:
        -s repo_uri     target repository URI
        --help or -?    display usage message

Environment:
        PKG_REPO""")
        sys.exit(retcode)

def trans_create_repository(repo_uri, args):
        """Creates a new repository at the location indicated by repo_uri."""

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

        xport, pub = setup_transport_and_pubs(repo_uri)

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

def trans_close(repo_uri, args):
        abandon = False
        trans_id = None
        refresh_index = True
        add_to_catalog = True

        opts, pargs = getopt.getopt(args, "At:", ["no-index", "no-catalog"])

        for opt, arg in opts:
                if opt == "-A":
                        abandon = True
                elif opt == "-t":
                        trans_id = arg
                elif opt == "--no-index":
                        refresh_index = False
                elif opt == "--no-catalog":
                        add_to_catalog = False
        if trans_id is None:
                try:
                        trans_id = os.environ["PKG_TRANS_ID"]
                except KeyError:
                        usage(_("No transaction ID specified using -t or in "
                            "$PKG_TRANS_ID."), cmd="close")

        xport, pub = setup_transport_and_pubs(repo_uri)
        t = trans.Transaction(repo_uri, trans_id=trans_id,
            add_to_catalog=add_to_catalog, xport=xport, pub=pub)
        pkg_state, pkg_fmri = t.close(abandon, refresh_index)
        for val in (pkg_state, pkg_fmri):
                if val is not None:
                        msg(val)
        return 0

def trans_add(repo_uri, args):
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
        opts, pargs = getopt.getopt(fargs, "d:", ["no-index",
            "no-catalog", "fmri-in-manifest"])
        basedirs = []

        refresh_index = True
        add_to_catalog = True
        embedded_fmri = False

        for opt, arg in opts:
                if opt == "-d":
                        basedirs.append(arg)
                elif opt == "--no-index":
                        refresh_index = False
                elif opt == "--no-catalog":
                        add_to_catalog = False
                elif opt == "--fmri-in-manifest":
                        embedded_fmri = True

        if not pargs and not embedded_fmri:
                usage(_("No fmri argument specified for subcommand"),
                    cmd="publish")

        if not embedded_fmri:
                pkg_name = pargs[0]
                del pargs[0]

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
                m.set_content(lines)
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

        if embedded_fmri:
                if "pkg.fmri" not in m:
                        error(_("Manifest does not set fmri and " +
                            "--fmri-in-manifest specified"))
                        return 1
                pkg_name = pkg.fmri.PkgFmri(m["pkg.fmri"]).get_short_fmri()

        xport, pub = setup_transport_and_pubs(repo_uri)
        t = trans.Transaction(repo_uri, pkg_name=pkg_name,
            refresh_index=refresh_index, xport=xport, pub=pub)
        t.open()

        for a in m.gen_actions():
                # don't publish this action
                if a.name == "set" and a.attrs["name"] in ["pkg.fmri", "fmri"]:
                        continue
                elif a.name in ["file", "license"]:
                        pkg.actions.set_action_data(a.hash, a, basedirs)
                elif a.name in nopub_actions:
                        error(_("invalid action for publication: %s") % action,
                            cmd="publish")
                        t.close(abandon=True)
                        return 1
                try:
                        t.add(a)
                except:
                        t.close(abandon=True)
                        raise

        pkg_state, pkg_fmri = t.close(abandon=False,
            refresh_index=refresh_index, add_to_catalog=add_to_catalog)
        for val in (pkg_state, pkg_fmri):
                if val is not None:
                        msg(val)
        return 0

def trans_include(repo_uri, fargs, transaction=None):
        basedirs = []
        error_occurred = False

        opts, pargs = getopt.getopt(fargs, "d:")
        for opt, arg in opts:
                if opt == "-d":
                        basedirs.append(arg)

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
                m.set_content("\n".join(lines))
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
                elif a.name in ["file", "license"]:
                        pkg.actions.set_action_data(a.hash, a, basedirs)

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

def gen_actions(files, timestamp_files, target_files):
        for filename in files:
                bundle = pkg.bundle.make_bundle(filename, target_files)
                for action in bundle:
                        if action.name == "file":
                                basename = os.path.basename(action.attrs["path"])
                                for pattern in timestamp_files:
                                        if fnmatch.fnmatch(basename, pattern):
                                                break
                                else:
                                        action.attrs.pop("timestamp", None)

                        yield action, action.name in nopub_actions

def trans_import(repo_uri, args):
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

        try:
                for action, err in gen_actions(pargs, timestamp_files,
                    target_files):
                        if err:
                                error(_("invalid action for publication: %s") %
                                    action, cmd="import")
                                t.close(abandon=True)
                                return 1
                        else:
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

        return 0

def trans_generate(args):
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
                    target_files):
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
        """Refreshes the indices at the location indicated by repo_uri."""

        if args:
                usage(_("command does not take operands"),
                    cmd="refresh-index")

        xport, pub = setup_transport_and_pubs(repo_uri)
        try:
                t = trans.Transaction(repo_uri, xport=xport, pub=pub).refresh_index()
        except trans.TransactionError, e:
                error(e, cmd="refresh-index")
                return 1
        return 0

def setup_transport_and_pubs(repo_uri):

        try:
                repo = publisher.Repository(origins=[repo_uri])
                pub = publisher.Publisher(prefix="default", repositories=[repo])
                xport = transport.Transport(transport.GenericTransportCfg(
                    publishers=[pub]))
        except apx.UnsupportedRepositoryURI:
                if repo_uri.startswith("null:"):
                        return None, None
                raise

        return xport, pub

def main_func():
        gettext.install("pkg", "/usr/share/locale")

        try:
                repo_uri = os.environ["PKG_REPO"]
        except KeyError:
                repo_uri = "http://localhost:10000"

        show_usage = False
        global_settings.client_name = "pkgsend"
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "s:?", ["help"])
                for opt, arg in opts:
                        if opt == "-s":
                                repo_uri = arg
                        elif opt in ("--help", "-?"):
                                show_usage = True
        except getopt.GetoptError, e:
                usage(_("pkgsend: illegal global option -- %s") % e.opt)

        subcommand = None
        if pargs:
                subcommand = pargs.pop(0)
                if subcommand == "help":
                        show_usage = True

        if show_usage:
                usage(retcode=0)
        elif not subcommand:
                usage()

        ret = 0
        try:
                if subcommand == "create-repository":
                        ret = trans_create_repository(repo_uri, pargs)
                elif subcommand == "open":
                        ret = trans_open(repo_uri, pargs)
                elif subcommand == "close":
                        ret = trans_close(repo_uri, pargs)
                elif subcommand == "add":
                        ret = trans_add(repo_uri, pargs)
                elif subcommand == "import":
                        ret = trans_import(repo_uri, pargs)
                elif subcommand == "include":
                        ret = trans_include(repo_uri, pargs)
                elif subcommand == "publish":
                        ret = trans_publish(repo_uri, pargs)
                elif subcommand == "generate":
                        ret = trans_generate(pargs)
                elif subcommand == "refresh-index":
                        ret = trans_refresh_index(repo_uri, pargs)
                else:
                        usage(_("unknown subcommand '%s'") % subcommand)
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
        except (pkg.actions.ActionError, trans.TransactionError,
            RuntimeError, pkg.fmri.IllegalFmri, apx.BadRepositoryURI,
            apx.UnsupportedRepositoryURI, apx.InvalidPackageErrors), _e:
                print >> sys.stderr, "pkgsend: %s" % _e
                __ret = 1
        except (PipeError, KeyboardInterrupt):
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                __ret = 1
        except SystemExit, _e:
                raise _e
        except:
                traceback.print_exc()
                error(
                    _("\n\nThis is an internal error.  Please let the "
                    "developers know about this\nproblem by filing a bug at "
                    "http://defect.opensolaris.org and including the\nabove "
                    "traceback and this message.  The version of pkg(5) is "
                    "'%s'.") % pkg.VERSION)
                __ret = 99
        sys.exit(__ret)
