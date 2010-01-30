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

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import pkg.indexer as indexer

import os
import sys
import tempfile
import stat
import shutil

class TestIndexer(pkg5unittest.Pkg5TestCase):

        def test_indexworkingsize(self):
            limit = 200

            ind = indexer.Indexer(self.test_root, None, None,
                sort_file_max_size=limit)

            os.mkdir(ind._tmp_dir)

            ind._sort_fh = open(os.path.join(ind._tmp_dir,
                indexer.SORT_FILE_PREFIX +
                str(ind._sort_file_num)), "wb")

            ind._sort_file_num += 1

            d1 = {  ('test1/optional', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('optional', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('5.11', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('20091105T190147Z', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('1.0', 'set', 'pkg.fmri', 'test1/optional'): [0]}

            d2 = {  ('20091105T190153Z', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('test1/core', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('1.0', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('corge', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('5.11', 'set', 'pkg.fmri', 'test1/core'): [0]}


            fmri1 = "pkg://test1/optional@1.0,5.11-0:20091105T190147Z"
            fmri2 = "pkg://test1/core@1.0,5.11-0:20091105T190153Z"

            ind._add_terms(fmri1, d1)
            ind._add_terms(fmri2, d2)

            # Each file should be under the limit
            for file in os.listdir(ind._tmp_dir):
                self.assert_(os.stat(os.path.join(ind._tmp_dir, file)).st_size <= \
                    limit)


        def test_indexworkingsize0(self):
            ind = indexer.Indexer(self.test_root, None, None,
                sort_file_max_size=0)

            os.mkdir(ind._tmp_dir)

            ind._sort_fh = open(os.path.join(ind._tmp_dir,
                indexer.SORT_FILE_PREFIX +
                str(ind._sort_file_num)), "wb")

            ind._sort_file_num += 1

            d1 = {  ('test1/optional', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('optional', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('5.11', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('20091105T190147Z', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('1.0', 'set', 'pkg.fmri', 'test1/optional'): [0]}

            d2 = {  ('20091105T190153Z', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('test1/core', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('1.0', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('corge', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('5.11', 'set', 'pkg.fmri', 'test1/core'): [0]}


            fmri1 = "pkg://test1/optional@1.0,5.11-0:20091105T190147Z"
            fmri2 = "pkg://test1/core@1.0,5.11-0:20091105T190153Z"

            ind._add_terms(fmri1, d1)
            ind._add_terms(fmri2, d2)

            # The first file is already opened by us, so it will fail the
            # <= 0 test by indexer, and indexer will create a new one. Hence,
            # sort.0 will be of size 0
            self.assert_(os.stat(os.path.join(ind._tmp_dir , "sort.0")).st_size == 0)

            # Each file should have at most 1 line in it ( the smallest
            # atomic unit  that the indexer can write to a file )
            for file in os.listdir(ind._tmp_dir):
                self.assert_(len(open(os.path.join(ind._tmp_dir, \
                    file)).readlines()) <= 1)

if __name__ == "__main__":
        unittest.main()
