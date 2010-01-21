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
import errno

import os
import shutil
import stat
import sys
import tempfile
import unittest

class TestPkgMogrify(testutils.CliTestCase):
        pkgcontents = \
            """
# directories
dir group=bin mode=0755 owner=root path=usr/X11
dir group=bin mode=0755 owner=root path=usr/X11/bin
dir group=bin mode=0755 owner=root path=usr/X11/include
dir group=bin mode=0755 owner=root path=usr/X11/include/X11
# dependencies
depend fmri=SUNWfontconfig@2.7.1-$(BUILDID) type=require
depend fmri=SUNWfreetype2@2.3.9-$(BUILDID) type=require
depend fmri=SUNWlibms@0.5.11-$(BUILDID) type=require
$(i386_ONLY)depend fmri=SUNWxorg-mesa@7.4.4-$(BUILDID) type=require
file NOHASH elfarch=i386 elfbits=32 group=bin mode=0755 \
 owner=root path=usr/X11/bin/xkbprint
file NOHASH group=bin mode=0755 owner=root path=usr/X11/bin/Xserver
file group=bin mode=0755 owner=root path=usr/X11/bin/bdftopcf
link path=usr/X11/lib/libXdmcp.so target=./libXdmcp.so.6
link path=usr/X11/lib/libXevie.so target=./libXevie.so.1
link path=usr/X11/lib/libXext.so target=./libXext.so.0
link path=usr/X11/lib/libXfixes.so target=./libXfixes.so.1
link path=usr/X11/lib/libXi.so target=./libXi.so.5
link path=usr/X11/lib/libXinerama.so target=./libXinerama.so.1
link path=usr/X11/lib/libXmu.so target=./libXmu.so.4
"""
        transforms = [ \
""" """,
"""<transform file link dir -> edit path X11 Y11>""",
"""<transform file path='.*xkbprint.*' -> drop>""",
"""<transform file path='usr/X11/bin/.*' -> set mode 0555>""",
"""<transform file -> delete mode 0755> """,
"""<transform file >""",
"""<transform file -> edit bar >""",
"""<include transform_1>
<include transform_3>""",
"""<include transform_9>""",
"""<include transform_5>""",
"""<transform file -> add bobcat 1>""",
"""<transform file bobcat=1 -> print "ouch" >""",
"""<transform file bobcat=1 -> abort >"""
]

        transform_files = []

        def setUp(self):
                self.pid = os.getpid()
                self.pwd = os.getcwd()
                self.persistent_depot = False

                self.__test_dir = os.path.join(tempfile.gettempdir(),
                    "ips.test.%d" % self.pid)

                try:
                        os.makedirs(self.__test_dir, 0755)
                except OSError, e:
                        if e.errno != errno.EEXIST:
                                raise e

                f = file(os.path.join(self.__test_dir, "source_file"), "wb")
                f.write(self.pkgcontents)
                f.close()

                for i, s in enumerate(self.transforms):
                        fname = os.path.join(self.__test_dir,
                                "transform_%s" % i)
                        self.transform_files.append(fname)
                        f = file(fname, "wb")
                        f.write(s)
                        f.close()

        def pkgmogrify(self, args, exit=0):
                cmd="%s/usr/bin/pkgmogrify %s" % (testutils.g_proto_area, args)
                self.cmdline_run(cmd, exit=exit)

        def tearDown(self):
                #shutil.rmtree(self.__test_dir)
                pass

        def test_1(self):
                """demonstrate macros working"""
                source_file = os.path.join(self.__test_dir, "source_file")
                output_file = os.path.join(self.__test_dir, "output_file")

                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s |" \
                        "egrep -v SUNWxorg-mesa" % source_file)
                self.pkgmogrify("-Di386_ONLY=' ' -DBUILDID=0.126 %s |" \
                        "egrep SUNWxorg-mesa@7.4.4-0.126" % source_file)
                # nested macros
                self.pkgmogrify("-Di386_ONLY=' ' -DBUILDID='$(FOO)' " \
                        "-DFOO=0.126 %s | egrep SUNWxorg-mesa@7.4.4-0.126" %
                        source_file)

        def test_2(self):
                """display output to files """
                source_file = os.path.join(self.__test_dir, "source_file")
                output_file = os.path.join(self.__test_dir, "output_file")
                self.pkgmogrify("-Di386_ONLY=' ' -DBUILDID=0.126 -O %s %s ;" \
                        "egrep SUNWxorg-mesa@7.4.4-0.126 %s" %
                        (output_file, source_file, output_file))

        def test_3(self):
                source_file = os.path.join(self.__test_dir, "source_file")
                output_file = os.path.join(self.__test_dir, "output_file")
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s %s |" \
                        "egrep -v X11" %
                        (self.transform_files[1], source_file))
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s %s |" \
                        "egrep Y11" % (self.transform_files[1], source_file))
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s %s |" \
                        "egrep bobcat | wc -l | grep -w '3'" %
                        (self.transform_files[10], source_file))
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s %s |" \
                        "egrep -v mode=0755" %
                        (self.transform_files[4], source_file))

        def test_4(self):
                source_file = os.path.join(self.__test_dir, "source_file")
                output_file = os.path.join(self.__test_dir, "output_file")
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s %s |" \
                        "egrep -v xkbprint" %
                        (self.transform_files[2], source_file))

        def test_5(self):
                source_file = os.path.join(self.__test_dir, "source_file")
                output_file = os.path.join(self.__test_dir, "output_file")

                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s %s |" \
                    "egrep 'file NOHASH group=bin mode=0555 owner=root " \
                    "path=usr\/X11\/bin\/Xserver'" %
                    (self.transform_files[3], source_file))
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s %s %s|" \
                    "egrep 'file NOHASH group=bin mode=0755 owner=root " \
                    "path=usr\/Y11\/bin\/Xserver'" % (self.transform_files[1],
                    self.transform_files[3], source_file))
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 -I %s %s %s" \
                    " |egrep 'file NOHASH group=bin mode=0755 owner=root " \
                    "path=usr\/Y11\/bin\/Xserver'" % (self.__test_dir,
                    self.transform_files[7], source_file))
                # check multiple modes to the same attribute on same action
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s %s %s |" \
                    "egrep 'file NOHASH group=bin mode=0555 owner=root " \
                    "path=usr\/Y11\/bin\/Xserver'" % (self.transform_files[3],
                    self.transform_files[1], source_file))

        def test_6(self):
                source_file = os.path.join(self.__test_dir, "source_file")
                output_file = os.path.join(self.__test_dir, "output_file")
                # check omitted NOHASH
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s %s %s |" \
                    "egrep 'file NOHASH group=bin mode=0555 owner=root " \
                    "path=usr\/Y11\/bin\/bdftopcf" % (self.transform_files[3],
                    self.transform_files[1], source_file))

        def test_7(self):
                source_file = os.path.join(self.__test_dir, "source_file")
                output_file = os.path.join(self.__test_dir, "output_file")

                # check error handling
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 --froob",
                        exit=2)
                # file not found
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s" %
                        self.transform_files[8], exit=1)
                # nested tranform error
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 -I %s %s" %
                        (self.__test_dir, self.transform_files[8]), exit=1)
                # bad transform
                self.pkgmogrify("-Di386_ONLY='#' -DBUILDID=0.126 %s %s" %
                        (self.transform_files[6], source_file), exit=1)
                self.pkgmogrify("/wombat-farm", exit=1)

        def test_8(self):
                """test for graceful exit with no output on abort"""
                source_file = os.path.join(self.__test_dir, "source_file")
                no_output = os.path.join(self.__test_dir, "no_output")
                no_print = os.path.join(self.__test_dir, "no_print")
                #
                # add an abort transform that's expected to trigger
                # this should cover the "exit gracefully" part of abort
                #
                self.pkgmogrify("-Di386_ONLY=' ' -DBUILDID=0.126 -P %s " \
                        "-O %s %s %s %s" % (no_print, no_output,
                        self.transform_files[10], self.transform_files[12],
                        source_file))
                # make sure neither output nor print file was created
                self.failIf(os.access(no_output, os.F_OK))
                self.failIf(os.access(no_print, os.F_OK))

        def test_9(self):
                """test for print output to specified file"""
                source_file = os.path.join(self.__test_dir, "source_file")
                output_file = os.path.join(self.__test_dir, "output_file")
                print_file = os.path.join(self.__test_dir, "print_file")
                #
                # generate output for each file action, and count resulting
                # lines in print file to be sure it matches our expectations
                #
                self.pkgmogrify("-Di386_ONLY=' ' -DBUILDID=0.126 -P %s " \
                        "-O %s %s %s %s; egrep ouch %s | wc -l |" \
                        "grep -w '3'" % (print_file, output_file,
                        self.transform_files[10], self.transform_files[11],
                        source_file, print_file))
