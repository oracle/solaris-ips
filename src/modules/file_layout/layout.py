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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

"""object to map content hashes to file paths

The Layout class hierarchy encapsulates bijective mappings between a hash
(or file name since those are equivalent in our system) and a relative path
that describes where to place that file in the file system.  This bijective
relation should hold when the union of all layouts is considered as a single
set of mappings.  In practical terms, this means that only one layout may
potentially deposit a hash into any particular location.  This is not a
difficult requirement to satisfy since each layout may append a unique
identifier to the file name or choose to carve out its own namespace at some
level of directory hierarchy.

The V1Layout places each file into a single layer of 256 directories.  A
fanout of 256 provides good performance compared to the other layouts
tested.  It also allows over 8M files to be stored even with filesystems
which limit the number of files in a directory to 65k.

The V0Layout layout uses two layers of directories; the first has a fanout
of 256 while the second has a fanout of 16M.  This layout has the problem
that for the sizes of images (on the order of 300-500k files) and repos (on
the order of 1M files), the second director level usually contains a single
file.  This imposes a substantial penalty for removing or resyncing the
directories because a readdir(3C) must be done for each directory and
readdir is two orders of magnitude slower than the open or read ZFS
operations, and one order of magnitude slower than ZFS remove.  Reducing
the number of directories used to hold the downloaded files was a goal for
the next layout.

To evaluate a layout, it is necessary to measure the insertion time, the
removal time, and the time to open a random file.  The insertion time
affects the publication speed.  The removal time effects the time a client
may take to clear its download cache.  The access time effects how quickly
a server can open a file to serve it.  File sizes from 1 to 10M were used
to asses the scalability of the different layouts."""


import os

class Layout(object):
        """This class is the parent class to all layouts. It defines the
        interface which those subclasses must satisfy."""
        
        def lookup(self, hashval):
                """Return the path to the file with name "hashval"."""
                raise NotImplementedError

        def path_to_hash(self, path):
                """Return the hash which would map to "path"."""
                raise NotImplementedError

        def contains(self, rel_path, file_name):
                """Returns whether this layout would place a file named
                "file_name" at "rel_path"."""
                return self.lookup(file_name) == rel_path


class V0Layout(Layout):
        """This class implements the original layout used.  It uses a 256 way
        split (2 hex digits) followed by a 16.7M way split (6 hex digits)."""

        def lookup(self, hashval):
                """Return the path to the file with name "hashval"."""
                return os.path.join(hashval[0:2], hashval[2:8], hashval)

        def path_to_hash(self, path):
                """Return the hash which would map to "path"."""
                return os.path.basename(path)


class V1Layout(Layout):
        """This class implements the new layout approach which is a single 256
        way fanout using the first two digits of the hash."""

        def lookup(self, hashval):
                """Return the path to the file with name "hashval"."""
                return os.path.join(hashval[0:2], hashval)

        def path_to_hash(self, path):
                """Return the hash which would map to "path"."""
                return os.path.basename(path)


def get_default_layouts():
        """This function describes the default order in which to use the
        layouts defined above."""

        return [V1Layout(), V0Layout()]

def get_preferred_layout():
        """This function returns the single preferred layout to use."""

        return V1Layout()
