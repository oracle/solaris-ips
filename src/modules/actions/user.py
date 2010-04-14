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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a user packaging object

This module contains the UserAction class, which represents a user
packaging object.  This contains the attributes necessary to create
a new user."""

import errno
import generic
try:
        from pkg.cfgfiles import *
        have_cfgfiles = True
except ImportError:
        have_cfgfiles = False

class UserAction(generic.Action):
        """Class representing a user packaging object."""

        __slots__ = []

        name = "user"
        key_attr = "username"
        globally_unique = True

        # if these values are different on disk than in action
        # prefer on-disk version
        use_existing_attrs = [ "passwd", "lastchng", "min",
                               "max", "expire", "flag", 
                               "warn", "inactive"]

        def as_set(self, item):
                if isinstance(item, list):
                        return set(item)
                return set([item])

        def merge(self, old_plan, on_disk):
                """ three way attribute merge between old manifest,
                what's on disk and new manifest.  For any values
                on disk that are not in the new plan, use the values
                on disk.  Use new plan values unless attribute is 
                in self.use_existing_attrs, or if old manifest and
                on-disk copy match...."""

                out = self.attrs.copy()

                for attr in on_disk:
                        if (attr in out and
                            attr not in self.use_existing_attrs) or \
                            (attr in old_plan and
                            old_plan[attr] == on_disk[attr]):
                                continue
                        if attr != "group-list":
                                out[attr] = on_disk[attr]
                        else:
                                out[attr] = list(
                                    self.as_set(out.get(attr, [])) |
                                    self.as_set(on_disk[attr]))
                return out

        def readstate(self, image, username, lock=False):
                root = image.get_root()
                pw = PasswordFile(root, lock)
                gr = GroupFile(root)
                ftp = FtpusersFile(root)

                username = self.attrs["username"]

                cur_attrs = pw.getuser(username)
                if "gid" in cur_attrs:
                        cur_attrs["group"] = \
                            image.get_name_by_gid(int(cur_attrs["gid"]))

                grps = gr.getgroups(username)
                if grps:
                        cur_attrs["group-list"] = grps

                cur_attrs["ftpuser"] = str(ftp.getuser(username)).lower()

                return (pw, gr, ftp, cur_attrs)


        def install(self, pkgplan, orig):
                """client-side method that adds the user...
                   update any attrs that changed from orig
                   unless the on-disk stuff was changed"""

                if not have_cfgfiles:
                        # The user action is ignored if cfgfiles is not
                        # available.
                        return

                username = self.attrs["username"]

                try:
                        pw, gr, ftp, cur_attrs = \
                            self.readstate(pkgplan.image, username, lock=True)

                        self.attrs["gid"] = pkgplan.image.get_group_by_name(
                            self.attrs["group"])

                        orig_attrs = {}
                        default_attrs = pw.getdefaultvalues()
                        if orig:
                                # Grab default values from files, extend by
                                # specifics from original manifest for
                                # comparisons sake.
                                orig_attrs.update(default_attrs)
                                orig_attrs["group-list"] = []
                                orig_attrs["ftpuser"] = "true"
                                orig_attrs.update(orig.attrs)
                        else:
                                # If we're installing a user for the first time,
                                # we want to override whatever value might be
                                # represented by the presence or absence of the
                                # user in the ftpusers file.  Remove the value
                                # from the representation of the file so that
                                # the new value takes precedence in the merge.
                                del cur_attrs["ftpuser"]

                        # add default values to new attrs if not present
                        for attr in default_attrs:
                                if attr not in self.attrs:
                                        self.attrs[attr] = default_attrs[attr]

                        final_attrs = self.merge(orig_attrs, cur_attrs)

                        pw.setvalue(final_attrs)

                        if "group-list" in final_attrs:
                                gr.setgroups(username,
                                    final_attrs["group-list"])

                        ftp.setuser(username,
                            final_attrs.get("ftpuser", "true") == "true")

                        pw.writefile()
                        gr.writefile()
                        ftp.writefile()
                except:
                        if "pw" in locals():
                                pw.unlockfile()
                        raise
                pw.unlockfile()

        def verify(self, img, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image."""

                errors = []
                warnings = []
                info = []

                if not have_cfgfiles:
                        # The user action is ignored if cfgfiles is not
                        # available.
                        return errors, warnings, info

                username = self.attrs["username"]

                try:
                        pw, gr, ftp, cur_attrs = self.readstate(img, username)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                errors.append(_("Skipping: Permission denied"))
                        else:
                                errors.append(_("Unexpected Error: %s") % e)
                        return errors, warnings, info

                if "group-list" in self.attrs:
                        self.attrs["group-list"] = \
                            sorted(self.attrs["group-list"])

                # Get the default values if they're non-empty
                pwdefval = dict((
                    (k, v)
                    for k, v in pw.getdefaultvalues().iteritems()
                    if v != ""
                ))

                # Certain defaults are dynamic, so we need to ignore what's on
                # disk
                if "gid" not in self.attrs:
                        cur_attrs["gid"] = ""
                if "uid" not in self.attrs:
                        cur_attrs["uid"] = ""
                if "lastchg" not in self.attrs:
                        cur_attrs["lastchg"] = ""

                pwdefval["ftpuser"] = "true"
                should_be = pwdefval.copy()
                should_be.update(self.attrs)
                # Note where attributes are missing
                for k in should_be:
                        cur_attrs.setdefault(k, "<missing>")
                # Note where attributes should be empty
                for k in cur_attrs:
                        if cur_attrs[k]:
                                should_be.setdefault(k, "<empty>")

                errors.extend(
                    _("%(entry)s: '%(found)s' should be '%(expected)s'") % {
                        "entry": a, "found": cur_attrs[a],
                        "expected": should_be[a] }
                    for a in should_be
                    if cur_attrs[a] != should_be[a]
                )
                return errors, warnings, info

        def remove(self, pkgplan):
                """client-side method that removes this user"""
                if not have_cfgfiles:
                        # The user action is ignored if cfgfiles is not
                        # available.
                        return

                root = pkgplan.image.get_root()
                pw = PasswordFile(root, lock=True)
                try:
                        gr = GroupFile(root)
                        ftp = FtpusersFile(root)

                        pw.removevalue(self.attrs)
                        gr.removeuser(self.attrs["username"])

                        # negative logic
                        ftp.setuser(self.attrs["username"], True)

                        pw.writefile()
                        gr.writefile()
                        ftp.writefile()
                finally:
                        pw.unlockfile()

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                return [("user", "name", self.attrs["username"], None)]
