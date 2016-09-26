#!/usr/bin/python2.7
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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
#

import errno
import getopt
import gettext
import locale
import os
import six
import sys
import traceback
import warnings

import pkg
import pkg.actions as actions
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.publish.dependencies as dependencies
from pkg.misc import msg, emsg, PipeError
from pkg.client.pkgdefs import EXIT_OK, EXIT_OOPS, EXIT_BADOPT

CLIENT_API_VERSION = 82
PKG_CLIENT_NAME = "pkgdepend"

DEFAULT_SUFFIX = ".res"

def format_update_error(e):
        # This message is displayed to the user whenever an
        # ImageFormatUpdateNeeded exception is encountered.
        emsg("\n")
        emsg(str(e))
        emsg(_("To continue, the target image must be upgraded "
            "before it can be used.  See pkg(1) update-format for more "
            "information."))

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if cmd:
                text = "{0}: {1}".format(cmd, text)
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

def usage(usage_error=None, cmd=None, retcode=EXIT_BADOPT):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if usage_error:
                error(usage_error, cmd=cmd)
        emsg (_("""\
Usage:
        pkgdepend [options] command [cmd_options] [operands]

Subcommands:
        pkgdepend generate [-IMm] -d dir [-d dir] [-D name=value] [-k path]
            manifest_file
        pkgdepend resolve [-EmoSv] [-d output_dir]
            [-e external_package_file]... [-s suffix] manifest_file ...

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
        except getopt.GetoptError as e:
                usage(_("illegal global option -- {0}").format(e.opt))

        remove_internal_deps = True
        echo_manf = False
        show_missing = False
        show_usage = False
        isa_paths = []
        run_paths = []
        platform_paths = []
        dyn_tok_conv = {}
        proto_dirs = []

        for opt, arg in opts:
                if opt == "-d":
                        if not os.path.isdir(arg):
                                usage(_("The proto directory {0} could not be "
                                    "found.".format(arg)), retcode=EXIT_BADOPT)
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
                        run_paths.append(arg)
                elif opt == "-m":
                        echo_manf = True
                elif opt == "-M":
                        show_missing = True
                elif opt in ("--help", "-?"):
                        show_usage = True
        if show_usage:
                usage(retcode=EXIT_OK)
        if len(pargs) > 2 or len(pargs) < 1:
                usage(_("Generate only accepts one or two arguments."))

        if "$ORIGIN" in dyn_tok_conv:
                usage(_("ORIGIN may not be specified using -D. It will be "
                    "inferred from the\ninstall paths of the files."))

        retcode = EXIT_OK

        manf = pargs[0]

        if not os.path.isfile(manf):
                usage(_("The manifest file {0} could not be found.").format(manf),
                    retcode=EXIT_BADOPT)

        if len(pargs) > 1:
                if not os.path.isdir(pargs[1]):
                        usage(_("The proto directory {0} could not be found.").format(
                            pargs[1]), retcode=EXIT_BADOPT)
                proto_dirs.insert(0, os.path.abspath(pargs[1]))
        if not proto_dirs:
                usage(_("At least one proto directory must be provided."),
                    retcode=EXIT_BADOPT)

        try:
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(manf,
                    proto_dirs, dyn_tok_conv, run_paths, remove_internal_deps)
        except (actions.MalformedActionError, actions.UnknownActionError) as e:
                error(_("Could not parse manifest {manifest} because of the "
                    "following line:\n{line}").format(manifest=manf,
                    line=e.actionstr))
                return EXIT_OOPS
        except api_errors.ApiException as e:
                error(e)
                return EXIT_OOPS

        if echo_manf:
                fh = open(manf, "r")
                for l in fh:
                        msg(l.rstrip())
                fh.close()

        for d in sorted(ds):
                msg(d)

        for key, value in six.iteritems(pkg_attrs):
                msg(actions.attribute.AttributeAction(**{key: value}))

        if show_missing:
                for m in ms:
                        emsg(m)

        for e in es:
                emsg(e)
                retcode = EXIT_OOPS
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
        constraint_files = []
        extra_external_info = False
        try:
                opts, pargs = getopt.getopt(args, "d:e:Emos:Sv")
        except getopt.GetoptError as e:
                usage(_("illegal global option -- {0}").format(e.opt))
        for opt, arg in opts:
                if opt == "-d":
                        out_dir = arg
                elif opt == "-e":
                        constraint_files.append(arg)
                elif opt == "-E":
                        extra_external_info = True
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
                        usage(_("The manifest file {0} could not be found.").format(
                            manifest), retcode=EXIT_BADOPT)

        if out_dir:
                out_dir = os.path.abspath(out_dir)
                if not os.path.isdir(out_dir):
                        usage(_("The output directory {0} is not a directory.").format(
                            out_dir), retcode=EXIT_BADOPT)

        provided_image_dir = True
        pkg_image_used = False
        if img_dir == None:
                orig_cwd = None
                try:
                        orig_cwd = os.getcwd()
                except OSError:
                        # May be unreadable by user or have other problem.
                        pass

                img_dir, provided_image_dir = api.get_default_image_root(
                    orig_cwd=orig_cwd)
                if os.environ.get("PKG_IMAGE"):
                        # It's assumed that this has been checked by the above
                        # function call and hasn't been removed from the
                        # environment.
                        pkg_image_used = True

        if not img_dir:
                error(_("Could not find image.  Use the -R option or set "
                    "$PKG_IMAGE to the\nlocation of an image."))
                return EXIT_OOPS

        system_patterns = misc.EmptyI
        if constraint_files:
                system_patterns = []
                for f in constraint_files:
                        try:
                                with open(f, "r") as fh:
                                        for l in fh:
                                                l = l.strip()
                                                if l and not l.startswith("#"):
                                                        system_patterns.append(
                                                            l)
                        except EnvironmentError as e:
                                if e.errno in (errno.ENOENT, errno.EISDIR):
                                        error("{0}: '{1}'".format(
                                            e.args[1], e.filename),
                                            cmd="resolve")
                                        return EXIT_OOPS
                                raise api_errors._convert_error(e)
                if not system_patterns:
                        error(_("External package list files were provided but "
                            "did not contain any fmri patterns."))
                        return EXIT_OOPS
        elif use_system_to_resolve:
                system_patterns = ["*"]

        # Becuase building an ImageInterface permanently changes the cwd for
        # python, it's necessary to do this step after resolving the paths to
        # the manifests.
        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    progress.QuietProgressTracker(), None, PKG_CLIENT_NAME,
                    exact_match=provided_image_dir)
        except api_errors.ImageNotFoundException as e:
                if e.user_specified:
                        if pkg_image_used:
                                error(_("No image rooted at '{0}' "
                                    "(set by $PKG_IMAGE)").format(e.user_dir))
                        else:
                                error(_("No image rooted at '{0}'").format(
                                    e.user_dir))
                else:
                        error(_("No image found."))
                return EXIT_OOPS
        except api_errors.PermissionsException as e:
                error(e)
                return EXIT_OOPS
        except api_errors.ImageFormatUpdateNeeded as e:
                # This should be a very rare error case.
                format_update_error(e)
                return EXIT_OOPS

        try:
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(manifest_paths, api_inst,
                        system_patterns, prune_attrs=not verbose)
        except (actions.MalformedActionError, actions.UnknownActionError) as e:
                error(_("Could not parse one or more manifests because of "
                    "the following line:\n{0}").format(e.actionstr))
                return EXIT_OOPS
        except dependencies.DependencyError as e:
                error(e)
                return EXIT_OOPS
        except api_errors.ApiException as e:
                error(e)
                return EXIT_OOPS
        ret_code = EXIT_OK

        if output_to_screen:
                ret_code = pkgdeps_to_screen(pkg_deps, manifest_paths,
                    echo_manifest)
        elif out_dir:
                ret_code = pkgdeps_to_dir(pkg_deps, manifest_paths, out_dir,
                    suffix, echo_manifest)
        else:
                ret_code = pkgdeps_in_place(pkg_deps, manifest_paths, suffix,
                    echo_manifest)

        if extra_external_info:
                if constraint_files and unused_fmris:
                        msg(_("\nThe following fmris matched a pattern in a "
                            "constraint file but were not used in\ndependency "
                            "resolution:"))
                        for pfmri in sorted(unused_fmris):
                                msg("\t{0}".format(pfmri))
                if not constraint_files and external_deps:
                        msg(_("\nThe following fmris had dependencies resolve "
                            "to them:"))
                        for pfmri in sorted(external_deps):
                                msg("\t{0}".format(pfmri))

        for e in errs:
                if ret_code == EXIT_OK:
                        ret_code = EXIT_OOPS
                emsg(e)
        for w in warnings:
                emsg(w)
        return ret_code

def __resolve_echo_line(l):
        """Given a line from a manifest, determines whether that line should
        be repeated in the output file if echo manifest has been set."""

        try:
                act = actions.fromstr(l.rstrip())
        except KeyboardInterrupt:
                raise
        except actions.ActionError:
                return True
        else:
                return not act.name == "depend"

def __echo_manifest(pth, out_func, strip_newline=False):
        try:
                with open(pth, "r") as fh:
                        text = ""
                        act = ""
                        for l in fh:
                                text += l
                                act += l.rstrip()
                                if act.endswith("\\"):
                                        act = act.rstrip("\\")
                                        continue
                                if __resolve_echo_line(act):
                                        if strip_newline:
                                                text = text.rstrip()
                                        elif text[-1] != "\n":
                                                text += "\n"
                                        out_func(text)
                                text = ""
                                act = ""
                        if text != "" and __resolve_echo_line(act):
                                if text[-1] != "\n":
                                        text += "\n"
                                out_func(text)
        except EnvironmentError:
                ret_code = EXIT_OOPS
                emsg(_("Could not open {0} to echo manifest").format(
                    manifest_path))

def pkgdeps_to_screen(pkg_deps, manifest_paths, echo_manifest):
        """Write the resolved package dependencies to stdout.

        'pkg_deps' is a dictionary that maps a path to a manifest to the
        dependencies that were resolved for that manifest.

        'manifest_paths' is a list of the paths to the manifests for which
        file dependencies were resolved.

        'echo_manifest' is a boolean which determines whether the original
        manifest will be written out or not."""

        ret_code = EXIT_OK
        first = True
        for p in manifest_paths:
                if not first:
                        msg("\n\n")
                first = False
                msg("# {0}".format(p))
                if echo_manifest:
                        __echo_manifest(p, msg, strip_newline=True)
                for d in pkg_deps[p]:
                        msg(d)
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

        ret_code = EXIT_OK
        try:
                out_fh = open(out_file, "w")
        except EnvironmentError:
                ret_code = EXIT_OOPS
                emsg(_("Could not open output file {0} for writing").format(
                    out_file))
                return ret_code
        if echo_manifest:
                __echo_manifest(manifest_path, out_fh.write)
        for d in deps:
                out_fh.write("{0}\n".format(d))
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

        ret_code = EXIT_OK
        if not os.path.exists(out_dir):
                try:
                        os.makedirs(out_dir)
                except EnvironmentError as e:
                        e_dic = {"dir": out_dir}
                        if len(e.args) > 0:
                                e_dic["err"] = e.args[1]
                        else:
                                e_dic["err"] = e.args[0]
                        emsg(_("Out dir {out_dir} does not exist and could "
                            "not be created. Error is: {err}").format(**e_dic))
                        return EXIT_OOPS
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

        ret_code = EXIT_OK
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
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "R:?",
                    ["help"])
        except getopt.GetoptError as e:
                usage(_("illegal global option -- {0}").format(e.opt))

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
                usage(retcode=EXIT_OK)
        elif not subcommand:
                usage()

        if subcommand == "generate":
                if img_dir:
                        usage(_("generate subcommand doesn't use -R"))
                return generate(pargs)
        elif subcommand == "resolve":
                return resolve(pargs, img_dir)
        else:
                usage(_("unknown subcommand '{0}'").format(subcommand))

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
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

        try:
                __ret = main_func()
        except api_errors.MissingFileArgumentException as e:
                error("The manifest file {0} could not be found.".format(e.path))
                __ret = EXIT_OOPS
        except api_errors.VersionException as __e:
                error(_("The {cmd} command appears out of sync with the lib"
                    "raries provided\nby pkg:/package/pkg. The client version "
                    "is {client} while the library\nAPI version is {api}").format(
                    cmd=PKG_CLIENT_NAME,
                    client=__e.received_version,
                    api=__e.expected_version
                    ))
                __ret = EXIT_OOPS
        except api_errors.ApiException as e:
                error(e)
                __ret = EXIT_OOPS
        except RuntimeError as _e:
                emsg("{0}: {1}".format(PKG_CLIENT_NAME, _e))
                __ret = EXIT_OOPS
        except (PipeError, KeyboardInterrupt):
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                __ret = EXIT_OOPS
        except SystemExit as _e:
                raise _e
        except:
                traceback.print_exc()
                error(misc.get_traceback_message())
                __ret = 99
        sys.exit(__ret)
