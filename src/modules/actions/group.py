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

class GroupAction(generic.Action):
        """Class representing a group packaging object.
        note that grouplist members are selected via the user action,
        although they are stored in the /etc/group file.  Use of
        group passwds is not supported"""
        name = "group"
        key_attr = "groupname"
        attributes = [ "groupname", "gid"] 
                       
        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

        def extract(self, attrlist):
                """ return a dictionary containing attrs in attr list
                from self.attrs; omit if no such attrs in self.attrs"""
                return dict((a, self.attrs[a])
                             for a in self.attrs
                             if a in attrlist)

        def install(self, pkgplan, orig):
                """client-side method that adds the group
                   use gid from disk if different"""
                if not have_cfgfiles:
                        # the group action is ignored if cfgfiles is not available
                        return

                groupname = self.attrs["groupname"]

                template = self.extract(["groupname", "gid"])
                
                gr = GroupFile(pkgplan.image.get_root())

                cur_attrs = gr.getvalue(template)
                
                # XXX needs modification if more attrs are used
                if not cur_attrs: 
                    gr.setvalue(template)
                    gr.writefile()

        def verify(self, img, **args):
                """" verify user action installation """
                if not have_cfgfiles:
                        # the user action is ignored if cfgfiles is not available
                        return []

                gr = GroupFile(img.get_root())

                cur_attrs = gr.getvalue(self.attrs)
                
                return [ "%s: '%s' should be '%s'" % (a, cur_attrs[a], self.attrs[a])
                         for a in self.attrs
                         if self.attrs[a] != cur_attrs[a]
                         ]
                                
        def remove(self, pkgplan):
                """client-side method that removes this group"""
                if not have_cfgfiles:
                        # the user action is ignored if cfgfiles is not available
                        return
                gr = GroupFile(pkgplan.image.get_root())
                cur_attrs = gr.getvalue(self.attrs)
                # groups need to be first added, last removed
                if not cur_attrs["user-list"]:
                    gr.removevalue(self.attrs)
                    gr.writefile()

        def generate_indices(self):
                return {
                    "groupname": self.attrs["groupname"]
                }
                

