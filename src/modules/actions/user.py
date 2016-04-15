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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

"""module describing a user packaging object

This module contains the UserAction class, which represents a user
packaging object.  This contains the attributes necessary to create
a new user."""

from . import generic
try:
        from pkg.cfgfiles import *
        have_cfgfiles = True
except ImportError:
        have_cfgfiles = False

import pkg.client.api_errors as apx
import pkg.actions

class UserAction(generic.Action):
        """Class representing a user packaging object."""

        __slots__ = []

        name = "user"
        key_attr = "username"
        globally_identical = True
        ordinality = generic._orderdict[name]

        # if these values are different on disk than in action
        # prefer on-disk version
        use_existing_attrs = [ "password", "lastchg", "min",
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

                        # prefer manifest version if either NP or *LK*
                        if attr == "password" and \
                           (out[attr] == 'NP' or
                           out[attr] == '*LK*'):
                                continue

                        if attr != "group-list":
                                out[attr] = on_disk[attr]
                        else:
                                out[attr] = list(
                                    self.as_set(out.get(attr, [])) |
                                    self.as_set(on_disk[attr]))
                return out

        def readstate(self, image, username, lock=False):
                """read state of user from files.  May raise KeyError"""
                root = image.get_root()
                pw = PasswordFile(root, lock)
                gr = GroupFile(image)
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


        def install(self, pkgplan, orig, retry=False):
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

                        self.attrs["gid"] = str(pkgplan.image.get_group_by_name(
                            self.attrs["group"]))

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

                        self.attrs["group-list"] = self.attrlist("group-list")
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
                except EnvironmentError as e:
                        if e.errno != errno.ENOENT:
                                raise
                        # If we're in the postinstall phase and the files
                        # *still* aren't there, bail gracefully.
                        if retry:
                                txt = _("User cannot be installed without user "
                                    "database files present.")
                                raise apx.ActionExecutionError(self, error=e,
                                    details=txt, fmri=pkgplan.destination_fmri)
                        img = pkgplan.image
                        img._users.add(self)
                        if "uid" in self.attrs:
                                img._usersbyname[self.attrs["username"]] = \
                                    int(self.attrs["uid"])
                        raise pkg.actions.ActionRetry(self)
                except KeyError as e:
                        # cannot find group
                        self.validate() # should raise error if no group in action
                        txt = _("{group} is an unknown or invalid group").format(
                            group=self.attrs.get("group", "None"))
                        raise apx.ActionExecutionError(self,
                            details=txt, fmri=pkgplan.destination_fmri)

                finally:
                        if "pw" in locals():
                                pw.unlock()

        def retry(self, pkgplan, orig):
                users = pkgplan.image._users
                if users:
                        assert self in users
                        self.install(pkgplan, orig, retry=True)

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
                except EnvironmentError as e:
                        if e.errno == errno.EACCES:
                                errors.append(_("Skipping: Permission denied"))
                        else:
                                errors.append(_("Unexpected Error: {0}").format(e))
                        return errors, warnings, info
                except KeyError as e:
                        errors.append(_("{group} is an unknown or invalid group").format(
                            group=self.attrs.get("group", "None")))
                        return errors, warnings, info

                if "group-list" in self.attrs:
                        self.attrs["group-list"] = \
                            sorted(self.attrlist("group-list"))

                # Get the default values if they're non-empty
                pwdefval = dict((
                    (k, v)
                    for k, v in six.iteritems(pw.getdefaultvalues())
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

                if should_be["password"] not in ["*LK*", "NP"]:
                        cur_attrs["password"] = should_be["password"]

                # Note where attributes are missing
                for k in should_be:
                        cur_attrs.setdefault(k, "<missing>")
                # Note where attributes should be empty
                for k in cur_attrs:
                        if cur_attrs[k]:
                                should_be.setdefault(k, "<empty>")

                errors.extend(
                    _("{entry}: '{found}' should be '{expected}'").format(
                        entry=a, found=cur_attrs[a],
                        expected=should_be[a])
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
                        gr = GroupFile(pkgplan.image)
                        ftp = FtpusersFile(root)

                        pw.removevalue(self.attrs)
                        gr.removeuser(self.attrs["username"])

                        # negative logic
                        ftp.setuser(self.attrs["username"], True)

                        pw.writefile()
                        gr.writefile()
                        ftp.writefile()
                except KeyError as e:
                        # Already gone; don't care.
                        if e.args[0] != (self.attrs["username"],):
                                raise
                finally:
                        pw.unlock()

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                return [("user", "name", self.attrs["username"], None)]

        def validate(self, fmri=None):
                """Performs additional validation of action attributes that
                for performance or other reasons cannot or should not be done
                during Action object creation.  An ActionError exception (or
                subclass of) will be raised if any attributes are not valid.
                This is primarily intended for use during publication or during
                error handling to provide additional diagonostics.

                'fmri' is an optional package FMRI (object or string) indicating
                what package contained this action.
                """

                generic.Action._validate(self, fmri=fmri,
                    numeric_attrs=("uid", "lastchg", "min", "max", "warn",
                    "inactive","expire", "flag"), single_attrs=("password",
                    "uid", "group", "gcos-field", "home-dir", "login-shell",
                    "ftpuser", "lastchg", "min", "max", "warn", "inactive",
                    "expire", "flag"),
                    required_attrs=("group",))

        def compare(self, other):
                """Arrange for user actions to be installed in uid order.  This
                will only hold true for actions installed at one time, but that's
                generally what we need on initial install."""
                # put unspecified uids at the end
                a = int(self.attrs.get("uid", 1024))
                b = int(other.attrs.get("uid", 1024))
                return (a > b) - (a < b)
