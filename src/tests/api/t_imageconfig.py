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

import unittest
import os
import shutil
import sys
import tempfile
import pkg.client.imageconfig as imageconfig

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)
import pkg5unittest

class TestImageConfig(pkg5unittest.Pkg5TestCase):
        def setUp(self):
                self.sample_dir = tempfile.mkdtemp()
                cfgfile = os.path.join(self.sample_dir, imageconfig.CFG_FILE)
                f = open(cfgfile, "w")

                f.write("""\
[policy]
Display-Copyrights: False

[property]
name = an image
                
[authority_sfbay.sun.com]
prefix: sfbay.sun.com
origin: http://zruty.sfbay:10001
mirrors:
ssl_key:
ssl_cert:
""")
                f.close()
                self.ic = imageconfig.ImageConfig()

        def tearDown(self):
                try:
                        shutil.rmtree(self.sample_dir)
                except:
                        pass

        def test_read(self):
                self.ic.read(self.sample_dir)

        def test_unicode(self):
                self.ic.read(self.sample_dir)
                ustr = u'abc\u3041def'
                self.ic.properties['name'] = ustr
                newdir = tempfile.mkdtemp()
                self.ic.write(newdir)
                ic2 = imageconfig.ImageConfig()
                ic2.read(newdir)
                ustr2 = ic2.properties['name']
                shutil.rmtree(newdir)
                self.assert_(ustr == ustr2)

        def test_missing_conffile(self):
                #
                #  See what happens if the conf file is missing.
                #
                shutil.rmtree(self.sample_dir)
                self.assertRaises(RuntimeError, self.ic.read, self.sample_dir)

# XXX more test cases needed.

if __name__ == "__main__":
        unittest.main()
