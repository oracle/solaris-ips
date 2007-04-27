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

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#
#ident	"%Z%%M%	%I%	%E% SMI"

import os

IMG_ENTIRE = 0
IMG_PARTIAL = 1
IMG_USER = 2

img_user_prefix = ".org.opensolaris,pkg"
img_root_prefix = "/var/pkg"

class Image(object):
        """An Image object is a directory tree containing the laid-down contents
        of a self-consistent graph of Packages.

        An Image has a root path.

        An Image of type IMG_ENTIRE does not have a parent Image.  Other Image
        types must have a parent Image.  The external state of the parent Image
        must be accessible from the Image's context, or duplicated within the
        Image (IMG_PARTIAL for zones, for instance).

        The parent of a user Image can be a partial Image.  The parent of a
        partial Image must be an entire Image.

        An Image of type IMG_USER stores its external state at self.root +
        ".org.opensolaris,pkg".

        An Image of type IMG_ENTIRE or IMG_PARTIAL stores its external state at
        self.root + "/var/pkg".

        An Image needs to be able to have a different repository set than the
        system's root Image.

        XXX Root path probably can't be absolute, so that we can combine or
        multiply use Image contents.

        XXX Image file format?  Image file manipulation API?"""

        def __init__(self):
                self.type = None
                self.root = None
                self.repo_uris = []
                self.filter_tags = {}

        def find_parent(self):
                # Ascend from current working directory to find first
                # encountered image.
                while True:
                        d = os.getcwd()

                        if os.path.isdir("%s/%s" % (d, img_user_prefix)):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                self.type = IMG_USER
                                self.root = d
                                return
                        elif os.path.isdir("%s/%s" % (d, img_root_prefix)):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                # XXX Look at image file to determine if this
                                # image is a partial image.
                                self.type = IMG_ENTIRE
                                self.root = d
                                return

                        assert d != "/"

                        os.chdir("..")

        def set_attrs(type, root):
                self.type = type
                self.root = root
                if self.type == IMG_USER:
                        self.metadata_root = self.root + "/.org.opensolaris,pkg"
                else:
                        self.metadata_root = self.root + "/var/pkg"

        def set_resource(self, resource):
                return

