#!/usr/bin/python2.4
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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os

import pkg.elf as elf
import pkg.flavor.base as base

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

        def __init__(self, file_path, run_path, token):
                base.DependencyAnalysisError.__init__(self)
                self.fp = file_path
                self.rp = run_path
                self.tok = token

        def __str__(self):
                return  _("%s had this token, %s, in its run path:%s. We are "
                    "unable to handle this token at this time.") % \
                    (self.fp, self.tok, self.rp)


class ElfDependency(base.MultiplePathDependency):
        """Class representing a dependency from one file to another library
        as determined by elf."""

        def __init__(self, *args, **kwargs):
                self.err_type = self.ERROR
                attrs = kwargs.get("attrs", {})
                attrs["%s.type" % self.DEPEND_DEBUG_PREFIX] = "elf"

                base.MultiplePathDependency.__init__(self, attrs=attrs, *args,
                    **kwargs)

        def is_error(self):
                return self.err_type == self.ERROR

        def resolve_internal(self, delivered_base_names, **kwargs):
                """Checks whether this dependency has been delivered. If the
                full path has not been delivered, check whether the base name
                has. If it has, it's likely that the run path is being set
                externally. Report a warning, but not an error in this case."""
                err, vars = base.MultiplePathDependency.resolve_internal(self,
                    delivered_base_names=delivered_base_names, **kwargs)
                # If the none of the paths pointed to a file with the desired
                # basename, but a file with that basename was delivered by this
                # package, then treat the dependency as a warning instead of
                # an error. The failure to find the path to the right file
                # may be due to the library search path being set outside the
                # file that generates the dependency.
                if err == self.ERROR and vars is None and \
                    self.base_name in delivered_base_names:
                        self.err_type = self.WARNING
                        self.attrs["%s.severity" % self.DEPEND_DEBUG_PREFIX] =\
                            "warning"
                        return self.WARNING, self.get_var_diff(
                            delivered_base_names[self.base_name])
                else:
                        return err, vars

        def __repr__(self):
                return "ElfDep(%s, %s, %s, %s)" % (self.action, self.base_name,
                    self.run_paths, self.pkg_vars)

def process_elf_dependencies(action, proto_dir, pkg_vars, **kwargs):
        """Given a file action and proto directory, produce the elf dependencies
        for that file."""

        if not action.name == "file":
                return []

        installed_path = action.attrs[action.key_attr]
        
        proto_file = os.path.join(proto_dir, installed_path)

        if not os.path.exists(proto_file):
                raise base.MissingFile(proto_file)

        if not elf.is_elf_object(proto_file):
                return []

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

        rp = [
            os.path.normpath(p.replace("$ORIGIN", os.path.join("/")))
            for p in rp
        ]

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
                # Default kernel search path
                rp.extend(("/kernel", "/usr/kernel"))
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
                if "/lib" not in rp:
                        rp.append("/lib")
                if "/usr/lib" not in rp:
                        rp.append("/usr/lib")

        res = []
        elist = []

        for p in rp:
                if "$" in p:
                        tok = p[p.find("$"):]
                        if "/" in tok:
                                tok = tok[:tok.find("/")]
                        elist.append(UnsupportedDynamicToken(installed_path, p,
                            tok))

        rp = [p for p in rp[:] if "$" not in p]

        return [
            ElfDependency(action, d, rp, pkg_vars, proto_dir)
            for d in deps
        ], elist
