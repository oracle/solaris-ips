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

# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import pkg.indexer as indexer
import pkg.search_errors as se

import os
import sys
import tempfile
import stat
import shutil

class TestIndexer(pkg5unittest.Pkg5TestCase):

        def __prep_indexer(self, limit):
                ind = indexer.Indexer(self.test_root, None, None,
                        sort_file_max_size=limit)

                os.mkdir(ind._tmp_dir)

                ind._sort_fh = open(os.path.join(ind._tmp_dir,
                        indexer.SORT_FILE_PREFIX +
                        str(ind._sort_file_num)), "w")

                ind._sort_file_num += 1

                d1 = {
                    ('test1/optional', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('optional', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('5.11', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('20091105T190147Z', 'set', 'pkg.fmri', 'test1/optional'): [0], 
                    ('1.0', 'set', 'pkg.fmri', 'test1/optional'): [0]
                }

                d2 = {
                    ('20091105T190153Z', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('test1/core', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('1.0', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('corge', 'set', 'pkg.fmri', 'test1/core'): [0],
                    ('5.11', 'set', 'pkg.fmri', 'test1/core'): [0]
                }

                fmri1 = "pkg://test1/optional@1.0,5.11-0:20091105T190147Z"
                fmri2 = "pkg://test1/core@1.0,5.11-0:20091105T190153Z"

                ind._add_terms(fmri1, d1)
                ind._add_terms(fmri2, d2)

                return ind

        def test_indexworkingsize(self):
                """Verify indexer sort_file_max_size works as expected."""

                # Verify that a max size of 0 raises an exception.
                self.assertRaises(se.IndexingException, indexer.Indexer,
                    self.test_root, None, None, sort_file_max_size=0)

                # Verify a number larger than total number of records expected
                # works...
                ind = self.__prep_indexer(200)

                # Each file should be under the limit.
                for file in os.listdir(ind._tmp_dir):
                        fs = os.stat(os.path.join(ind._tmp_dir, file))
                        self.assertTrue(fs.st_size <= 200)
                shutil.rmtree(ind._tmp_dir)

                # ...and that a number that matches the smallest atomic unit
                # that the indexer can write works.
                ind = self.__prep_indexer(1)

                # The first file is already opened by us, so it will fail the
                # <= 0 test by indexer, and indexer will create a new one.
                # Hence, sort.0 will be of size 0
                self.assertTrue(os.stat(os.path.join(ind._tmp_dir , "sort.0")).st_size == 0)

                # Since sort_file_max_size is a soft limit, the indexer can't
                # actually limit each file to 1 byte, but there should be at
                # most one line in each file.
                for file in os.listdir(ind._tmp_dir):
                        self.assertTrue(len(open(os.path.join(ind._tmp_dir,
                            file)).readlines()) <= 1)

if __name__ == "__main__":
        unittest.main()
