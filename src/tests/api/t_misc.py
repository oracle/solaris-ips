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

import os
import stat
import unittest
import tempfile
import shutil

import pkg.misc as misc
from pkg.actions.generic import Action

class TestMisc(unittest.TestCase):

    def test_hash_file_name(self):
        fn = misc.hash_file_name("abcdefghijklmnopqrstuvwxyz")
        self.assertEqual(fn, os.path.join("ab", "cdefgh", "abcdefghijklmnopqrstuvwxyz"))

    def testMakedirs(self):
        tmpdir = tempfile.mkdtemp()
        # make the parent directory read-write
        os.chmod(tmpdir, stat.S_IRWXU)
        fpath = os.path.join(tmpdir, "f")
        fopath = os.path.join(fpath, "o")
        foopath = os.path.join(fopath, "o")

        # make the leaf, and ONLY the leaf read-only
        Action.makedirs(foopath, mode = stat.S_IREAD)
        # Now make sure the directories leading up the leaf
        # are read-write, and the leaf is readonly.
        assert(os.stat(tmpdir).st_mode & (stat.S_IREAD | stat.S_IWRITE) != 0)
        assert(os.stat(fpath).st_mode & (stat.S_IREAD | stat.S_IWRITE) != 0)
        assert(os.stat(fopath).st_mode & (stat.S_IREAD | stat.S_IWRITE) != 0)
        assert(os.stat(foopath).st_mode & stat.S_IREAD != 0)
        assert(os.stat(foopath).st_mode & stat.S_IWRITE == 0)
		
        # change it back to read/write so we can delete it
        os.chmod(foopath, stat.S_IRWXU)
        shutil.rmtree(tmpdir)

        
if __name__ == "__main__":
        unittest.main()
