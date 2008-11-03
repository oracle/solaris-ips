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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import pkg.version

class ConstraintException(Exception):
        """Constraint exception is thrown by constraint functions
        if constraint conflicts occur."""

        PRESENCE_CONFLICT  = 0
        VERSION_CONFLICT   = 1
        FMRI_CONFLICT      = 2 # same as version, but diff error
        DOWNGRADE_CONFLICT = 3


        def __init__(self, reason, new, old):
                Exception.__init__(self)
                self.new = new
                self.old = old
                self.reason = reason

        def __str__(self):
                if self.reason == self.PRESENCE_CONFLICT:                        
                        return _(
"Package presence is both required and prohibited:\n\t%s\n\t%s\n") % \
                            (self.new, self.old)
                elif self.reason == self.VERSION_CONFLICT:
                        return _(
"""Package %s contains constraint incompatible with constraint in installed package %s
         proposed: %s
        installed: %s
""") % (self.new.source_name, self.old.source_name, self.new, self.old)
                elif self.reason == self.FMRI_CONFLICT:
                        return _(
"""Package %s conflicts with constraint in installed pkg:/%s: 
        %s""") % (self.new, self.old.source_name, self.old)
                elif self.reason == self.DOWNGRADE_CONFLICT:
                        return _(
""""Package %s contains constraint that requires downgrade of installed pkg %s:
        %s""") % \
                            (self.new.source_name, self.old, self.new)
                assert 0, "Illegal reason code"

class ConstraintSet(object):
        """used to hold set of constraints on an image"""
        def __init__(self):
                self.constraints = {}
                # dict of version, constrained pkgs by pkg name
                self.loaded_fmri_versions = {}
                self.active_fmri = None

        def finish_loading(self, fmri):
                """ declare that we're done loading constraints 
                from this fmri"""
                assert self.active_fmri == fmri, \
                    "Finishing for wrong fmri (%s != %s)" %(self.active_fmri, fmri)
                self.active_fmri = None

        def start_loading(self, fmri):
                """ load a new set of constraints from fmri,
                deleting any constraints defined by previous versions
                of this fmri... skip if we're reloading the same
                one by returning False, otherwise True. """

                assert self.active_fmri == None, "Already loading!"
                self.active_fmri = fmri
                fmri_name = fmri.get_name()

                if fmri_name in self.loaded_fmri_versions:
                        oldv, pkg_list = self.loaded_fmri_versions[fmri_name]
                        if oldv == fmri.version:
                                self.active_fmri = None
                                return False # already loaded this pkg once                        
                        # remove constraints est. by previous version
                        for p in pkg_list:
                                cl = self.constraints[p]
                                deletions = 0                                
                                for i, c in enumerate(cl[:]):
                                        if c.source_name == fmri_name:
                                                del cl[i - deletions]
                                                deletions += 1

                self.loaded_fmri_versions[fmri_name] = (fmri.version, [])
                return True

        def update_constraints(self, constraint):
                """ add a constraint from the active fmri to the
                set of system constraints"""

                active_fmri_name = self.active_fmri.get_name()
                v, pkg_list = self.loaded_fmri_versions[active_fmri_name]

                assert active_fmri_name == constraint.source_name

                if constraint.presence == Constraint.ALWAYS:
                        return # don't record these here for now

                # find existing constraint list for this package                

                cl = self.constraints.get(constraint.pkg_name, None)

                if cl:
                        # check to make sure new constraint is
                        # compatible w/ existing constraints
                        # compatiblity is such that if
                        # A will combine w/ any item in list B,
                        # A will combine with combination of all of B
                        for c in cl:
                                c.combine(constraint)
                        cl.append(constraint)                        
                else:
                        self.constraints[constraint.pkg_name] = [constraint]

                if constraint.pkg_name not in pkg_list:
                        pkg_list.append(constraint.pkg_name)

        def apply_constraints(self, constraint): 
                """ if constraints exist for this package, apply 
                them.  Apply the new one last so that exception
                contains proper error message... error message
                generation will be unclear if multiple constraints
                exist"""
                cl = self.constraints.get(constraint.pkg_name, None)
                if cl:
                        mc = reduce(lambda a, b: a.combine(b), cl)
                        return mc.combine(constraint)
                return None

        def apply_constraints_to_fmri(self, fmri):
                """ treats fmri as min required version; apply any 
                constraints and if fmri is more specific, return 
                original fmri, otherwise return more constrained
                version... remap exception for better error handling"""
                ic = Constraint.reqfmri2constraint(fmri, "")
                try:
                        nc = self.apply_constraints(ic)
                except ConstraintException, e:
                        raise ConstraintException(ConstraintException.FMRI_CONFLICT, 
                            fmri, e.old)
                if not nc or ic == nc:
                        return fmri
                nfmri = fmri.copy()
                nfmri.version = nc.min_ver
                return nfmri
                        
class Constraint(object):
        """basic constraint object; describes constraints on fmris 
        and provides a method of computing the intersection of two 
        constraints"""
        # some defines for presence
        ERROR   = 0 #order matters; see self.combine for details
        ALWAYS  = 1 #required
        MAYBE   = 2 #optional
        NEVER   = 3 #exclude, not yet functional

        __presence_strs = ["ERROR", "Required", "Optional", "Excluded"]

        compat = {
            (ALWAYS, ALWAYS): ALWAYS,
            (ALWAYS, MAYBE):  ALWAYS,
            (ALWAYS, NEVER):  ERROR,
            (MAYBE,  MAYBE):  MAYBE,
            (MAYBE,  NEVER):  NEVER,
            (NEVER,  NEVER):  NEVER
        }

        def __init__(self, pkg_name, min_ver, max_ver, presence, source_name):
                self.pkg_name = pkg_name
                self.presence = presence
                self.min_ver = min_ver
                self.max_ver = max_ver
                self.source_name = source_name

        def __str__(self):
                return "Pkg %s: %s min_version: %s max version: %s defined by: pkg:/%s" % \
                    (self.pkg_name, self.__presence_strs[self.presence], 
                     self.min_ver, self.max_ver, self.source_name)

        def __eq__(self, other):
                return \
                    self.pkg_name == other.pkg_name and \
                    self.presence == other.presence and \
                    self.min_ver  == other.min_ver and \
                    self.max_ver  == other.max_ver
        
        @staticmethod
        def reqfmri2constraint(fmri, source_name):
                return Constraint(fmri.get_name(), fmri.version, 
                    None, Constraint.ALWAYS, source_name)

        @staticmethod
        def optfmri2constraint(fmri, source_name):
                return Constraint(fmri.get_name(), fmri.version, 
                    None, Constraint.MAYBE, source_name)

        @staticmethod
        def incfmri2constraint(fmri, source_name):
                return Constraint(fmri.get_name(), fmri.version, 
                    fmri.version, Constraint.MAYBE, source_name)
        
        def check_for_work(self, fmri_present):
                """Evaluate work needed to meet new constraint if fmri_present
                is the fmri installed (None if none is installed).  Returns
                None if no work to do, otherwise version to be installed.
                Raises ConstraintException in case of uninstall or downgrade
                required."""

                if not fmri_present:
                        if self.presence == Constraint.MAYBE or \
                            self.presence == Constraint.NEVER:
                                return None
                        return self.min_ver
                else:
                        # following assertion awaits rename removal
                        # assert fmri_present.get_name() == self.pkg_name
                        if self.presence == Constraint.NEVER:
                                raise Constraint.Exception(
                                    ConstraintException.PRESENCE_CONFLICT,
                                    self, fmri_present)
                version_present = fmri_present.version
                if version_present < self.min_ver:
                        return self.min_ver
                if self.max_ver and version_present > self.max_ver and not \
                    version_present.is_successor(self.max_ver, 
                    pkg.version.CONSTRAINT_AUTO):
                        raise ConstraintException(ConstraintException.DOWNGRADE_CONFLICT,
                            self, fmri_present)
                return None

        def combine(self, proposed):
                assert self.pkg_name == proposed.pkg_name

                presence = self.compat[(min(self.presence, proposed.presence),
                                        max(self.presence, proposed.presence))]

                if presence == Constraint.ERROR:
                        raise ConstraintException(
                            ConstraintException.PRESENCE_CONFLICT, proposed, self)

                # following relies on None < any version

                if self.max_ver == None or proposed.max_ver == None:
                        max_ver = max(self.max_ver, proposed.max_ver)
                else:
                        max_ver = min(self.max_ver, proposed.max_ver)
                
                min_ver = max(self.min_ver, proposed.min_ver)

                if max_ver and max_ver < min_ver and \
                    not min_ver.is_successor(max_ver, pkg.version.CONSTRAINT_AUTO):
                        raise ConstraintException(
                            ConstraintException.VERSION_CONFLICT, proposed, self)

                return Constraint(self.pkg_name, min_ver, max_ver, 
                    presence, self.source_name)

                
                
                                
        
