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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a user packaging object

This module contains the UserAction class, which represents a user
packaging object.  This contains the attributes necessary to create
a new user."""

import os
import errno
import generic
try:
        from pkg.cfgfiles import *
        have_cfgfiles = True
except ImportError:
        have_cfgfiles = False

class UserAction(generic.Action):
        """Class representing a user packaging object."""
        name = "user"
        key_attr = "username"
        required_attributes = ["username", "group"]

        attributes = [ "username", "password", "uid", "group", 
                       "gcos-field", "home-dir", "login-shell",
                       "lastchng", "min", "max", 
                       "warn", "inactive", "expire"
                       "flag", "group-list", "ftpuser"]
                       
        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

        def as_set(self, item):
                if isinstance(item, list):
                        return set(item)
                return set([item])
                
        def merge(self, old_plan, on_disk):
                """ three way attribute merge.  What we do is to
                take the new version if the on_disk is the same
                as the old plan, otherwise return old versions"""
                
                out = self.attrs.copy()

                for attr in on_disk:
                        if attr in old_plan and \
                            old_plan[attr] == on_disk[attr]:
                                continue
                        if attr != "group-list":
                                out[attr] = on_disk[attr]
                        else:
                                out[attr] = list(
                                        self.as_set(out[attr]) +
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

                if ftp.getuser(username):
                        cur_attrs["ftpuser"] = "false"
                else:
                        cur_attrs["ftpuser"] = "true"

                return (pw, gr, ftp, cur_attrs)

                
        def install(self, pkgplan, orig):
                """client-side method that adds the user...
                   update any attrs that changed from orig
                   unless the on-disk stuff was changed"""

                if not have_cfgfiles:
                        # the user action is ignored if cfgfiles is not available
                        return
                        
                username = self.attrs["username"]
                
                try:
                        pw, gr, ftp, cur_attrs = \
                            self.readstate(pkgplan.image, username, lock=True)
                        
                        self.attrs["gid"] = pkgplan.image.get_group_by_name(self.attrs["group"])

                        orig_attrs = {}
                        if orig:
                                # grab default values from files, extend by specifics from
                                # original manifest for comparisons sake.
                                orig_attrs.update(pw.getdefaultvalues())
                                orig_attrs["group-list"] = []
                                orig_attrs["ftpuser"] = "true"
                                orig_attrs.update(orig.attrs)

                        final_attrs = self.merge(orig_attrs, cur_attrs)

                        pw.setvalue(final_attrs)

                        if "group-list" in final_attrs:
                                gr.setgroups(username, final_attrs["group-list"])

                        ftp.setuser(username, final_attrs["ftpuser"] == "true")

                        pw.writefile()
                        gr.writefile()
                        ftp.writefile()
                except:
                        pw.unlockfile()
                        raise
                pw.unlockfile()

        def verify(self, img, **args):
                """" verify user action installation """
                if not have_cfgfiles:
                        # the user action is ignored if cfgfiles is not available
                        return []

                username = self.attrs["username"]

                pw, gr, ftp, cur_attrs = self.readstate(img, username)

                if "group-list" in self.attrs:
                        self.attrs["group-list"] = sorted(self.attrs["group-list"])

                return [ "%s: '%s' should be '%s'" % (a, cur_attrs.get(a, "<missing>"), self.attrs.get(a, "<missing>"))
                         for a in self.attrs
                         if self.attrs[a] != cur_attrs.get(a, None)
                         ]
                                
        def remove(self, pkgplan):
                """client-side method that removes this user"""
                if not have_cfgfiles:
                        # the user action is ignored if cfgfiles is not available
                        return
                
                root = pkgplan.image.get_root()
                try:
                        pw = PasswordFile(root, lock=True)
                        gr = GroupFile(root)
                        ftp = FtpusersFile(root)

                        pw.removevalue(self.attrs)
                        gr.removeuser(self.attrs["username"])
                        ftp.setuser(self.attrs["username"], True) #negative logic

                        pw.writefile()
                        gr.writefile()
                        ftp.writefile()
                except:
                        pw.unlockfile()
                        raise
                pw.unlockfile()

        def generate_indices(self):
                return {
                    "username": self.attrs["username"]
                }
