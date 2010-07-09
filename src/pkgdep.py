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
# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.
#

import getopt
import gettext
import locale
import os
import sys
import traceback
import warnings

import pkg
import pkg.actions as actions
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress
import pkg.misc as misc
import pkg.publish.dependencies as dependencies
from pkg.misc import msg, emsg, PipeError

CLIENT_API_VERSION = 40
PKG_CLIENT_NAME = "pkgdepend"

DEFAULT_SUFFIX = ".res"

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
        emsg(ws + "pkgdepend: " + text_nows)

def usage(usage_error=None, cmd=None, retcode=2):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if usage_error:
                error(usage_error, cmd=cmd)
        emsg (_("""\
Usage:
        pkgdepend [options] command [cmd_options] [operands]

Subcommands:
        pkgdepend generate [-IMm] -d dir [-d dir] [-D name=value] [-k path]
            manifest_path
        pkgdepend [options] resolve [-dmosv] manifest ...

Options:
        -R dir
        --help or -?
Environment:
        PKG_IMAGE"""))

        sys.exit(retcode)

def generate(args):
        """Produce a list of file dependencies from a manfiest and a proto
        area."""
        try:
                opts, pargs = getopt.getopt(args, "d:D:Ik:Mm?",
                    ["help"])
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        remove_internal_deps = True
        echo_manf = False
        show_missing = False
        show_usage = False
        isa_paths = []
        kernel_paths = []
        platform_paths = []
        dyn_tok_conv = {}
        proto_dirs = []

        for opt, arg in opts:
                if opt == "-d":
                        if not os.path.isdir(arg):
                                usage(_("The proto directory %s could not be "
                                    "found." % arg), retcode=2)
                        proto_dirs.append(os.path.abspath(arg))
                elif opt == "-D":
                        try:
                                dyn_tok_name, dyn_tok_val = arg.split("=", 1)
                        except:
                                usage(_("-D arguments must be of the form "
                                    "'name=value'."))
                        if not dyn_tok_name[0] == "$":
                                dyn_tok_name = "$" + dyn_tok_name
                        dyn_tok_conv.setdefault(dyn_tok_name, []).append(
                            dyn_tok_val)
                elif opt == "-I":
                        remove_internal_deps = False
                elif opt == "-k":
                        kernel_paths.append(arg)
                elif opt == "-m":
                        echo_manf = True
                elif opt == "-M":
                        show_missing = True
                elif opt in ("--help", "-?"):
                        show_usage = True
        if show_usage:
                usage(retcode=0)
        if len(pargs) > 2 or len(pargs) < 1:
                usage(_("Generate only accepts one or two arguments."))

        if not kernel_paths:
                kernel_paths = ["/kernel", "/usr/kernel"]

        if "$ORIGIN" in dyn_tok_conv:
                usage(_("ORIGIN may not be specified using -D. It will be "
                    "inferred from the\ninstall paths of the files."))

        retcode = 0

        manf = pargs[0]

        if not os.path.isfile(manf):
                usage(_("The manifest file %s could not be found.") % manf,
                    retcode=2)

        if len(pargs) > 1:
                if not os.path.isdir(pargs[1]):
                        usage(_("The proto directory %s could not be found.") %
                            pargs[1], retcode=2)
                proto_dirs.insert(0, os.path.abspath(pargs[1]))
        if not proto_dirs:
                usage(_("At least one proto directory must be provided."),
                    retcode=2)

        try:
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(manf,
                    proto_dirs, dyn_tok_conv, kernel_paths,
                    remove_internal_deps)
        except (actions.MalformedActionError, actions.UnknownActionError), e:
                error(_("Could not parse manifest %(manifest)s because of the "
                    "following line:\n%(line)s") % { 'manifest': manf ,
                    'line': e.actionstr})
                return 1

        if echo_manf:
                fh = open(manf, "rb")
                for l in fh:
                        msg(l.rstrip())
                fh.close()

        for d in sorted(ds):
                msg(d)

        for key, value in pkg_attrs.iteritems():
                msg(actions.attribute.AttributeAction(**{key: value}))

        if show_missing:
                for m in ms:
                        emsg(m)

        for e in es:
                emsg(e)
                retcode = 1
        return retcode

def resolve(args, img_dir):
        """Take a list of manifests and resolve any file dependencies, first
        against the other published manifests and then against what is installed
        on the machine."""
        out_dir = None
        echo_manifest = False
        output_to_screen = False
        suffix = None
        verbose = False
        use_system_to_resolve = True
        try:
            opts, pargs = getopt.getopt(args, "d:mos:Sv")
        except getopt.GetoptError, e:
            usage(_("illegal global option -- %s") % e.opt)
        for opt, arg in opts:
                if opt == "-d":
                        out_dir = arg
                elif opt == "-m":
                        echo_manifest = True
                elif opt == "-o":
                        output_to_screen = True
                elif opt == "-s":
                        suffix = arg
                elif opt == "-S":
                        use_system_to_resolve = False
                elif opt == "-v":
                        verbose = True

        if (out_dir or suffix) and output_to_screen:
                usage(_("-o cannot be used with -d or -s"))

        manifest_paths = [os.path.abspath(fp) for fp in pargs]

        for manifest in manifest_paths:
            if not os.path.isfile(manifest):
                usage(_("The manifest file %s could not be found.") % manifest,
                    retcode=2)

        if out_dir:
                out_dir = os.path.abspath(out_dir)
                if not os.path.isdir(out_dir):
                        usage(_("The output directory %s is not a directory.") %
                            out_dir, retcode=2)

        if img_dir is None:
                try:
                        img_dir = os.environ["PKG_IMAGE"]
                except KeyError:
                        try:
                                img_dir = os.getcwd()
                        except OSError, e:
                                try:
                                        img_dir = os.environ["PWD"]
                                        if not img_dir or img_dir[0] != "/":
                                                img_dir = None
                                except KeyError:
                                        img_dir = None

        if img_dir is None:
                error(_("Could not find image.  Use the -R option or set "
                    "$PKG_IMAGE to point\nto an image, or change the working "
                    "directory to one inside the image."))
                return 1

        # Becuase building an ImageInterface permanently changes the cwd for
        # python, it's necessary to do this step after resolving the paths to
        # the manifests.
        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    progress.QuietProgressTracker(), None, PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("'%s' is not an install image") % e.user_dir)
                return 1

        try:
            pkg_deps, errs = dependencies.resolve_deps(manifest_paths, api_inst,
                prune_attrs=not verbose, use_system=use_system_to_resolve)
        except (actions.MalformedActionError, actions.UnknownActionError), e:
            error(_("Could not parse one or more manifests because of the " +
                "following line:\n%s") % e.actionstr)
            return 1

        ret_code = 0

        if output_to_screen:
                ret_code = pkgdeps_to_screen(pkg_deps, manifest_paths,
                    echo_manifest)
        elif out_dir:
                ret_code = pkgdeps_to_dir(pkg_deps, manifest_paths, out_dir,
                    suffix, echo_manifest)
        else:
                ret_code = pkgdeps_in_place(pkg_deps, manifest_paths, suffix,
                    echo_manifest)

        for e in errs:
                if ret_code == 0:
                        ret_code = 1
                emsg(e)
        return ret_code

def resolve_echo_line(l):
        """Given a line from a manifest, determines whether that line should
        be repeated in the output file if echo manifest has been set."""

        try:
                act = actions.fromstr(l.rstrip())
        except KeyboardInterrupt:
                raise
        except actions.ActionError:
                return True
        else:
                return not act.name == "depend" or \
                    act.attrs["type"] != "require"

def explode(dep_with_variantsets):
        sat_tups = dep_with_variantsets.get_variants().get_satisfied().groups()
        if not sat_tups:
                return dep_with_variantsets
        res = []
        for tup in sat_tups:
                attrs = dep_with_variantsets.attrs.copy()
                attrs.update(dict(tup))
                res.append(str(actions.depend.DependencyAction(**attrs)))
        return "\n".join(res).rstrip()

def pkgdeps_to_screen(pkg_deps, manifest_paths, echo_manifest):
        """Write the resolved package dependencies to stdout.

        'pkg_deps' is a dictionary that maps a path to a manifest to the
        dependencies that were resolved for that manifest.

        'manifest_paths' is a list of the paths to the manifests for which
        file dependencies were resolved.

        'echo_manifest' is a boolean which determines whether the original
        manifest will be written out or not."""

        ret_code = 0
        for p in manifest_paths:
                msg(p)
                if echo_manifest:
                        try:
                                fh = open(p, "rb")
                                for l in fh:
                                        if resolve_echo_line(l):
                                                msg(l.rstrip())
                                fh.close()
                        except EnvironmentError:
                                emsg(_("Could not open %s to echo manifest") %
                                    p)
                                ret_code = 1
                for d in pkg_deps[p]:
                        msg(explode(d))
                msg(_("\n\n"))
        return ret_code

def write_res(deps, out_file, echo_manifest, manifest_path):
        """Write the dependencies resolved, and possibly the manifest, to the
        destination file.

        'deps' is a list of the resolved dependencies.

        'out_file' is the path to the destination file.

        'echo_manifest' determines whether to repeat the original manifest in
        the destination file.

        'manifest_path' the path to the manifest which generated the
        dependencies."""

        ret_code = 0
        try:
                out_fh = open(out_file, "wb")
        except EnvironmentError:
                ret_code = 1
                emsg(_("Could not open output file %s for writing") %
                    out_file)
                return ret_code
        if echo_manifest:
                try:
                        fh = open(manifest_path, "rb")
                except EnvironmentError:
                        ret_code = 1
                        emsg(_("Could not open %s to echo manifest") %
                            manifest_path)
                for l in fh:
                        if resolve_echo_line(l):
                                out_fh.write(l)
                fh.close()
        for d in deps:
                out_fh.write("%s\n" % explode(d))
        out_fh.close()
        return ret_code

def pkgdeps_to_dir(pkg_deps, manifest_paths, out_dir, suffix, echo_manifest):
        """Given an output directory, for each manifest given, writes the
        dependencies resolved to a file in the output directory.

        'pkg_deps' is a dictionary that maps a path to a manifest to the
        dependencies that were resolved for that manifest.

        'manifest_paths' is a list of the paths to the manifests for which
        file dependencies were resolved.

        'out_dir' is the path to the directory into which the dependency files
        should be written.

        'suffix' is the string to append to the end of each output file.

        'echo_manifest' is a boolean which determines whether the original
        manifest will be written out or not."""

        ret_code = 0
        if not os.path.exists(out_dir):
                try:
                        os.makedirs(out_dir)
                except EnvironmentError, e:
                        emsg(_("Out dir %s does not exist and could not be "
                            "created. Error is: %s") % e)
                        return 1
        if suffix and suffix[0] != ".":
                suffix = "." + suffix
        for p in manifest_paths:
                out_file = os.path.join(out_dir, os.path.basename(p))
                if suffix:
                        out_file += suffix
                tmp_rc = write_res(pkg_deps[p], out_file, echo_manifest, p)
                if not ret_code:
                        ret_code = tmp_rc
        return ret_code

def pkgdeps_in_place(pkg_deps, manifest_paths, suffix, echo_manifest):
        """Given an output directory, for each manifest given, writes the
        dependencies resolved to a file in the output directory.

        'pkg_deps' is a dictionary that maps a path to a manifest to the
        dependencies that were resolved for that manifest.

        'manifest_paths' is a list of the paths to the manifests for which
        file dependencies were resolved.

        'out_dir' is the path to the directory into which the dependency files
        should be written.

        'suffix' is the string to append to the end of each output file.

        'echo_manifest' is a boolean which determines whether the original
        manifest will be written out or not."""

        ret_code = 0
        if not suffix:
                suffix = DEFAULT_SUFFIX
        if suffix[0] != ".":
                suffix = "." + suffix
        for p in manifest_paths:
                out_file = p + suffix
                tmp_rc = write_res(pkg_deps[p], out_file, echo_manifest, p)
                if not ret_code:
                        ret_code = tmp_rc
        return ret_code

def main_func():
        misc.setlocale(locale.LC_ALL, "", error)
        gettext.install("pkg", "/usr/share/locale")

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "R:?",
                    ["help"])
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        show_usage = False
        img_dir = None
        for opt, arg in opts:
                if opt == "-R":
                        img_dir = arg
                elif opt in ("--help", "-?"):
                        show_usage = True

        subcommand = None
        if pargs:
                subcommand = pargs.pop(0)
                if subcommand == "help":
                        show_usage = True

        if show_usage:
                usage(retcode=0)
        elif not subcommand:
                usage()

        if subcommand == "generate":
                if img_dir:
                        usage(_("generate subcommand doesn't use -R"))
                return generate(pargs)
        elif subcommand == "resolve":
                return resolve(pargs, img_dir)
        else:
                usage(_("unknown subcommand '%s'") % subcommand)

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":

        # Make all warnings be errors.
        warnings.simplefilter('error')

        try:
                __ret = main_func()
        except api_errors.MissingFileArgumentException, e:
                error("The manifest file %s could not be found." % e.path)
                __ret = 1
        except api_errors.VersionException, __e:
                error(_("The %(cmd)s command appears out of sync with the lib"
                    "raries provided\nby pkg:/package/pkg. The client version "
                    "is %(client)s while the library\nAPI version is %(api)s") %
                    {"cmd": PKG_CLIENT_NAME,
                     "client": __e.received_version,
                     "api": __e.expected_version
                    })
                __ret = 1
        except RuntimeError, _e:
                emsg("%s: %s" % (PKG_CLIENT_NAME, _e))
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
