#!/usr/bin/python
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
# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.
#

import os

import pkg.elf as elf
import pkg.flavor.base as base

from pkg.portable import PD_LOCAL_PATH, PD_PROTO_DIR, PD_DEFAULT_RUNPATH

class BadElfFile(base.DependencyAnalysisError):
        """Exception that is raised when the elf dependency checker is given
        a file that errors when it tries to get the dynamic section from the
        file."""

        def __init__(self, fp, ex):
                base.DependencyAnalysisError.__init__(self)
                self.fp = fp
                self.ex = ex

        def __str__(self):
                return _("%s had this elf error:%s") % (self.fp, self.ex)

class UnsupportedDynamicToken(base.DependencyAnalysisError):
        """Exception that is used for elf dependencies which have a dynamic
        token in their path that we're unable to decode."""

        def __init__(self, proto_path, installed_path, run_path, token):
                base.DependencyAnalysisError.__init__(self)
                self.pp = proto_path
                self.ip = installed_path
                self.rp = run_path
                self.tok = token

        def __str__(self):
                return  _("%(pp)s (which will be installed at %(ip)s) had this "
                    "token, %(tok)s, in its run path: %(rp)s.  It is not "
                    "currently possible to automatically expand this token. "
                    "Please specify its value on the command line.") % \
                    self.__dict__


class ElfDependency(base.PublishingDependency):
        """Class representing a dependency from one file to another library
        as determined by elf."""

        def __init__(self, action, base_name, run_paths, pkg_vars, proto_dir):
                self.err_type = self.ERROR

                base.PublishingDependency.__init__(self, action,
                    [base_name], run_paths, pkg_vars, proto_dir, "elf")

        def is_error(self):
                """Because elf dependencies can be either warnings or errors,
                it's necessary to check whether this dependency is an error
                or not."""

                return self.err_type == self.ERROR

        def resolve_internal(self, delivered_base_names, **kwargs):
                """Checks whether this dependency has been delivered. If the
                full path has not been delivered, check whether the base name
                has. If it has, it's likely that the run path is being set
                externally. Report a warning, but not an error in this case."""
                err, vars = base.PublishingDependency.resolve_internal(
                    self, delivered_base_names=delivered_base_names, **kwargs)
                # If the none of the paths pointed to a file with the desired
                # basename, but a file with that basename was delivered by this
                # package, then treat the dependency as a warning instead of
                # an error. The failure to find the path to the right file
                # may be due to the library search path being set outside the
                # file that generates the dependency.
                if err == self.ERROR and vars.is_satisfied() and \
                    self.base_names[0] in delivered_base_names:
                        self.err_type = self.WARNING
                        self.attrs["%s.severity" % self.DEPEND_DEBUG_PREFIX] =\
                            "warning"
                        missing_vars = self.get_variant_combinations()
                        missing_vars.mark_as_satisfied(
                            delivered_base_names[self.base_names[0]])
                        return self.WARNING, missing_vars
                else:
                        return err, vars

        def __repr__(self):
                return "ElfDep(%s, %s, %s, %s)" % (self.action,
                    self.base_names[0], self.run_paths, self.pkg_vars)

def expand_variables(paths, dyn_tok_conv):
        """Replace dynamic tokens, such as $PLATFORM, in the paths in the
        paramter 'paths' with the values for that token provided in the
        dictionary 'dyn_tok_conv.'
        """

        res = []
        elist = []
        for p in paths:
                tok_start = p.find("$")
                if tok_start > -1:
                        tok = p[tok_start:]
                        tok_end = tok.find("/")
                        if tok_end > -1:
                                tok = tok[:tok_end]
                        if tok not in dyn_tok_conv:
                                elist.append((p, tok))
                        else:
                                np = [
                                    p[:tok_start] + dc + \
                                    p[tok_start + len(tok):]
                                    for dc in dyn_tok_conv[tok]
                                ]
                                # The first dynamic token has been replaced, but
                                # more may remain so process the path again.
                                rec_res, rec_elist = expand_variables(np,
                                    dyn_tok_conv)
                                res.extend(rec_res)
                                elist.extend(rec_elist)
                else:
                        res.append(p)
        return res, elist

default_run_paths = ["/lib", "/usr/lib"]

def process_elf_dependencies(action, pkg_vars, dyn_tok_conv, run_paths,
    **kwargs):
        """Produce the elf dependencies for the file delivered in the action
        provided.

        'action' is the file action to analyze.

        'pkg_vars' is the list of variants against which the package delivering
        the action was published.

        'dyn_tok_conv' is the dictionary which maps the dynamic tokens, like
        $PLATFORM, to the values they should be expanded to.

        'run_paths' contains the run paths which elf binaries should use.
        """

        if not action.name == "file":
                return [], [], {}

        installed_path = action.attrs[action.key_attr]

        proto_file = action.attrs[PD_LOCAL_PATH]

        if not os.path.exists(proto_file):
                raise base.MissingFile(proto_file)

        if not elf.is_elf_object(proto_file):
                return [], [], {}

        try:
                ei = elf.get_info(proto_file)
                ed = elf.get_dynamic(proto_file)
        except elf.ElfError, e:
                raise BadElfFile(proto_file, e)
        deps = [
            d[0]
            for d in ed.get("deps", [])
        ]
        rp = ed.get("runpath", "").split(":")
        if len(rp) == 1 and rp[0] == "":
                rp = []

        dyn_tok_conv["$ORIGIN"] = [os.path.join("/",
            os.path.dirname(installed_path))]

        kernel64 = None

        # For kernel modules, default path resolution is /platform/<platform>,
        # /kernel, /usr/kernel.  But how do we know what <platform> would be for
        # a given module?  Does it do fallbacks to, say, sun4u?
        if installed_path.startswith("kernel") or \
            installed_path.startswith("usr/kernel") or \
            (installed_path.startswith("platform") and \
            installed_path.split("/")[2] == "kernel"):
                if rp:
                        raise RuntimeError("RUNPATH set for kernel module "
                            "(%s): %s" % (installed_path, rp))
                # Add this platform to the search path.
                if installed_path.startswith("platform"):
                        rp.append("/platform/%s/kernel" %
                            installed_path.split("/")[1])
                else:
                        for p in dyn_tok_conv.get("$PLATFORM", []):
                                rp.append("/platform/%s/kernel" % p)
                # Default kernel search path
                rp.extend(["/kernel", "/usr/kernel"])
                # What subdirectory should we look in for 64-bit kernel modules?
                if ei["bits"] == 64:
                        if ei["arch"] == "i386":
                                kernel64 = "amd64"
                        elif ei["arch"] == "sparc":
                                kernel64 = "sparcv9"
                        else:
                                raise RuntimeError("Unknown arch:%s" %
                                    ei["arch"])
        else:
                for p in default_run_paths:
                        if ei["bits"] == 64:
                                p += "/64"
                        if p not in rp:
                                rp.append(p)

        elist = []
        if run_paths:
                # add our detected runpaths into the user-supplied one (if any)
                rp = base.insert_default_runpath(rp, run_paths)

        rp, errs = expand_variables(rp, dyn_tok_conv)

        elist.extend([
            UnsupportedDynamicToken(proto_file, installed_path, p, tok)
            for p, tok in errs
        ])

        res = []

        for d in deps:
                pn, fn = os.path.split(d)
                pathlist = []
                for p in rp:
                        if kernel64:
                                # Find 64-bit modules the way krtld does.
                                # XXX We don't resolve dependencies found in
                                # /platform, since we don't know where under
                                # /platform to look.
                                deppath = \
                                    os.path.join(p, pn, kernel64, fn).lstrip(
                                    os.path.sep)
                        else:
                                deppath = os.path.join(p, d).lstrip(os.path.sep)
                        # deppath includes filename; remove that.
                        head, tail = os.path.split(deppath)
                        if head:
                                pathlist.append(head)
                res.append(ElfDependency(action, fn, pathlist, pkg_vars,
                    action.attrs[PD_PROTO_DIR]))
        del dyn_tok_conv["$ORIGIN"]
        return res, elist, {}
