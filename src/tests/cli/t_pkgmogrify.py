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
# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import errno
import os
import re
import shutil
import stat
import sys
import tempfile
import unittest

class TestPkgMogrify(pkg5unittest.CliTestCase):
        """Tests for the pkgmogrify publication tool."""

        persistent_setup = True

        pkgcontents = """\
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
file NOHASH group=bin mode=0755 owner=root path=usr/X11/bin/bdftopcf
link path=usr/X11/lib/libXdmcp.so target=./libXdmcp.so.6
link path=usr/X11/lib/libXevie.so target=./libXevie.so.1
link path=usr/X11/lib/libXext.so target=./libXext.so.0
link path=usr/X11/lib/libXfixes.so target=./libXfixes.so.1
link path=usr/X11/lib/libXi.so target=./libXi.so.5
link path=usr/X11/lib/libXinerama.so target=./libXinerama.so.1
link path=usr/X11/lib/libXmu.so target=./libXmu.so.4
"""

        pkgcontents2 = """\
set name=pkg.fmri value=wombat/heaven@1.0,5.11-0.101
set name=bugs value=12345 value=54321 value=13524
set name=justonebug value=12345
file thisismyhashvalue path=usr/bin/foo mode=0777 owner=root group=bin
file thisismyotherhashvalue path=usr/sfw/bin/foo mode=0777 owner=root group=bin
file path=usr/bin/bar mode=0777 owner=root group=bin
"""

        pkgcontents3 = """\
$(i386_ONLY)file NOHASH path=kernel/drv/x86_only1 reboot-needed=true
$(i386_ONLY)file NOHASH path=kernel/drv/x86_only2 reboot-needed=true
$(sparc_ONLY)file NOHASH path=kernel/drv/sparc_only1 reboot-needed=true
$(sparc_ONLY)file NOHASH path=kernel/drv/sparc_only2 reboot-needed=true
file NOHASH path=kernel/drv/common1 reboot-needed=true
file NOHASH path=kernel/drv/common2 reboot-needed=true
"""

        # Give names to simple transforms.  These transforms can use <include>
        # by referring to the named transforms using the %()s construct.
        transforms = {
            "X11->Y11": "<transform file link dir -> edit path X11 Y11>",
            "drop xkbprint": "<transform file path='.*xkbprint.*' -> drop>",
            "X11mode": "<transform file path='usr/X11/bin/.*' -> set mode 0555>",
            "drop mode=0755": "<transform file -> delete mode 0755> ",
            "empty": "<transform file >",
            "empty edit": "<transform file -> edit bar >",
            "2include": "<include %(X11->Y11)s>\n<include %(X11mode)s>",
            "include 9": "<include %(include 5)s>",
            "include 5": "<include %(empty)s>",
            "add bobcat": "<transform file -> add bobcat 1>",
            "print ouch": '<transform file bobcat=1 -> print "ouch" >',
            "abort on bobcat": "<transform file bobcat=1 -> abort >",
            "exit7 on bobcat": "<transform file bobcat=1 -> exit 7>",
            "exit6 on bobcat": "<transform file bobcat=1 -> exit 6 found a bobcat>",
            "pkg.fmri": "<transform file path=usr/bin/foo -> print pkg attr \"%%{pkg.fmri}\" and the rest>",
            "pkg.bugs": "<transform file path=usr/bin/foo -> print pkg attr \"%%{bugs}\" and the rest>",
            "fmrival": "<transform set name=pkg.fmri -> print test of \"%%(value)\" ... or is it?>",
            "fmrinoval": "<transform set name=pkg.fmri -> print test of \"%%(valuee)\" ... or is it?>",
            "fmrisaved": "<transform set name=pkg.fmri -> print test of \"%%(valuee;notfound=noprint)\" ... or is it?>",
            "fmriqsaved": "<transform set name=pkg.fmri -> print test of \"%%(valuee;notfound=\"got quotes\")\" ... or is it?>",
            "fmrinotsaved": "<transform set name=pkg.fmri -> print test of \"%%(value;notfound=noprint)\" ... or is it?>",
            "list": "<transform set name=bugs -> print test of listval \"%%(value)\">",
            "listsep": "<transform set name=bugs -> print test of listval \"%%(value;sep=\",\")\">",
            "listsufpresep": "<transform set name=bugs -> print test of listval \"%%(value;sep=\", \";prefix=\"bug='\";suffix=\"'\")\">",
            "nolistsufpre": "<transform set name=justonebug -> print test of \"%%(value;prefix=\"bug='\";suffix=\"'\")\">",
            "emitblank": "<transform set name=pkg.fmri -> emit>",
            "emitcomment": "<transform set name=pkg.fmri -> emit # comment>",
            "emitaction": "<transform set name=pkg.fmri -> emit depend type=incorporate fmri=%%(value)>",
            "synthetic": "<transform file path=usr/bin/foo -> print %%(pkg.manifest.filename) %%(pkg.manifest.lineno)>",
            "synthetic2": "<transform file path=usr/bin/foo -> print %%(action.hash) %%(action.key) %%(action.name)>",
            "synthetic3": "<transform file -> print %%(action.hash)>",
            "synthetic4": "<transform set -> print %%(action.hash)>",
            "synthetic5": "<transform set -> print %%(action.hash;notfound=something)>",
            "pkgmatch": "<transform pkg -> default $(MYATTR) false>",
            "pkggen": "<transform pkg $(MYATTR)=false -> emit depend fmri=consolidation type=require>",
            "recurse": "<transform file mode=0777 -> emit file path=usr/bin/bar mode=0777>",
            "rbneeded": "<transform file reboot-needed=true -> emit set name=magic value=true>",
        }

        basic_defines = {
            "i386_ONLY": "#",
            "BUILDID": 0.126
        }

        def setUp(self):
                pkg5unittest.CliTestCase.setUp(self)

                f = file(os.path.join(self.test_root, "source_file"), "wb")
                f.write(self.pkgcontents)
                f.close()

                f = file(os.path.join(self.test_root, "source_file2"), "wb")
                f.write(self.pkgcontents2)
                f.close()

                f = file(os.path.join(self.test_root, "source_file3"), "wb")
                f.write(self.pkgcontents3)
                f.close()

                # Map the transform names to path names
                xformpaths = dict((
                    (name, os.path.join(self.test_root, "transform_%s" % i))
                    for i, name in enumerate(self.transforms.iterkeys())
                ))

                # Now that we have path names, we can use the expandos in the
                # transform contents to embed those pathnames, and write the
                # transform files out.
                for name, path in xformpaths.iteritems():
                        f = file(path, "wb")
                        self.transforms[name] %= xformpaths
                        f.write(self.transforms[name])
                        f.close()

                self.transform_contents = self.transforms
                self.transforms = xformpaths

        def pkgmogrify(self, sources, defines=None, output=None, args="", exit=0):
                if defines is None:
                        defines = self.basic_defines

                defines = " ".join([
                    "-D %s=%s" % (k, v)
                    for k, v in defines.iteritems()
                ])
                sources = " ".join(sources)
                if output:
                        args += " -O %s" % output

                cmd = "%s/usr/bin/pkgmogrify %s %s %s" % (
                    pkg5unittest.g_proto_area, defines, args, sources)

                self.cmdline_run(cmd, exit=exit)

        def __countMatches(self, regex, path=None):
                """Count how many lines in the output of the previously run
                command match the regular expression 'regex'.  If 'path' is
                specified, the contents of that file are searched."""

                if path is not None:
                        output = file(path).read()
                else:
                        output = self.output

                c = sum((
                    int(bool(re.search(regex, line)))
                    for line in output.splitlines()
                ))

                return c

        def assertMatch(self, regex, path=None, count=0):
                """Assert that the regular expression 'regex' matches in the
                output of the previously run command.  If 'path' is specified,
                the contents of that file are searched.  If 'count' is greater
                than zero, then the number of lines which match must equal that
                number."""

                c = self.__countMatches(regex, path)

                self.failIf(count == c == 0,
                    "No matches for '%s' found" % regex)
                if count > 0:
                        self.failUnless(c == count,
                            "%s matches for '%s' found, %s expected" %
                            (c, regex, count))

        def assertNoMatch(self, regex, path=None):
                """Assert that the regular expression 'regex' is not found in
                the output of the previously run command.  If 'path' is
                specified, the contents of that file are searched."""

                c = self.__countMatches(regex, path)

                self.assert_(c == 0, "Match for '%s' found unexpectedly" % regex)

        def test_1(self):
                """Basic and nested macro substitution.  Allow a macro to
                comment out a manifest line."""

                source_file = os.path.join(self.test_root, "source_file")

                sources = [ source_file ]

                # Lines commented out by macros remain in the output.
                self.pkgmogrify(sources)
                self.assertNoMatch("^[^#].*SUNWxorg-mesa")

                defines = self.basic_defines.copy()
                defines["i386_ONLY"] = " "
                self.pkgmogrify(sources, defines=defines)
                self.assertMatch("SUNWxorg-mesa")

                # nested macros
                defines["BUILDID"] = "$(FOO)"; defines["FOO"] = "0.126"
                self.pkgmogrify(sources, defines=defines)
                self.assertMatch("SUNWxorg-mesa")

        def test_2(self):
                """The -O option: output goes to a file rather than stdout."""

                source_file = os.path.join(self.test_root, "source_file")
                output_file = os.path.join(self.test_root, "output_file")

                sources = [ source_file ]

                defines = self.basic_defines.copy()
                defines["i386_ONLY"] = " "
                self.pkgmogrify(sources, defines=defines, output=output_file)
                self.assertMatch("SUNWxorg-mesa@7.4.4-0.126", path=output_file)

        def test_3(self):
                source_file = os.path.join(self.test_root, "source_file")
                output_file = os.path.join(self.test_root, "output_file")

                self.pkgmogrify([self.transforms["X11->Y11"], source_file])
                self.assertNoMatch("X11")
                self.assertMatch("Y11")

                self.pkgmogrify([self.transforms["add bobcat"], source_file])
                self.assertMatch("bobcat", count=3)

                self.pkgmogrify([self.transforms["drop mode=0755"], source_file])
                self.assertNoMatch("^file.*mode=0755")

        def test_4(self):
                source_file = os.path.join(self.test_root, "source_file")

                self.pkgmogrify([self.transforms["drop xkbprint"], source_file])
                self.assertNoMatch("xkbprint")
                # Make sure that the line really got dropped, not just changed
                # unrecognizably.
                self.assertMatch("^.*$", count=19)

        def test_5(self):
                source_file = os.path.join(self.test_root, "source_file")

                # Basic attribute editing.
                self.pkgmogrify([self.transforms["X11mode"], source_file])
                self.assertMatch("file NOHASH group=bin mode=0555 owner=root "
                    "path=usr/X11/bin/Xserver")

                # Ensure that modifying an attribute used as matching criteria
                # by a later transform means that the later transform is not
                # invoked.
                self.pkgmogrify([self.transforms["X11->Y11"],
                    self.transforms["X11mode"], source_file])
                self.assertMatch("file NOHASH group=bin mode=0755 owner=root "
                    "path=usr/Y11/bin/Xserver")

                # Make sure that the -I flag works, with files specified on the
                # commandline as well as ones <include>d by others.
                self.pkgmogrify([os.path.basename(self.transforms["2include"]),
                    source_file], args="-I %s" % self.test_root)
                self.assertMatch("file NOHASH group=bin mode=0755 owner=root "
                    "path=usr/Y11/bin/Xserver")

                # Ensure that modifying an attribute used as matching criteria
                # by an earlier transform doesn't prevent the earlier transform
                # from being invoked.
                self.pkgmogrify([self.transforms["X11mode"],
                    self.transforms["X11->Y11"], source_file])
                self.assertMatch("file NOHASH group=bin mode=0555 owner=root "
                    "path=usr/Y11/bin/Xserver")

        def test_6(self):
                source_file = os.path.join(self.test_root, "source_file")

                # If NOHASH is omitted from the original manifest, check that it
                # gets added.
                self.pkgmogrify([self.transforms["X11mode"],
                    self.transforms["X11->Y11"], source_file])
                self.assertMatch("file NOHASH group=bin mode=0555 owner=root "
                    "path=usr/Y11/bin/bdftopcf")

        def test_7(self):
                """Test various error conditions."""

                source_file = os.path.join(self.test_root, "source_file")

                # Bad argument
                self.pkgmogrify([], args="--froob", exit=2)

                # Bad transform
                self.pkgmogrify([self.transforms["empty edit"], source_file],
                    exit=1)

                # file not found XXX this fails because of a bad transform
                self.pkgmogrify([self.transforms["include 9"]], exit=1)

                # nested tranform error XXX this fails because of a bad transform
                self.pkgmogrify([self.transforms["include 9"]],
                    args="-I %s" % self.test_root, exit=1)

                # Wombats!
                self.pkgmogrify(["/wombat-farm"], exit=1)

        def test_8(self):
                """Test for graceful exit with no output on abort."""

                source_file = os.path.join(self.test_root, "source_file")
                no_output = os.path.join(self.test_root, "no_output")
                no_print = os.path.join(self.test_root, "no_print")

                # Add an abort transform that's expected to trigger.  This
                # should cover the "exit gracefully" part of abort.
                self.pkgmogrify([self.transforms["add bobcat"],
                    self.transforms["abort on bobcat"], source_file],
                    output=no_output, args="-P %s" % no_print)

                # Make sure neither output nor print file was created.
                self.failIf(os.access(no_output, os.F_OK))
                self.failIf(os.access(no_print, os.F_OK))

                # Trigger an exit transform with a specific exit code.
                self.pkgmogrify([self.transforms["add bobcat"],
                    self.transforms["exit7 on bobcat"], source_file],
                    output=no_output, args="-P %s" % no_print, exit=7)

                # Make sure neither output nor print file was created.
                self.failIf(os.access(no_output, os.F_OK))
                self.failIf(os.access(no_print, os.F_OK))

                # Trigger an exit transform with a specific exit code and
                # message.
                self.pkgmogrify([self.transforms["add bobcat"],
                    self.transforms["exit6 on bobcat"], source_file],
                    output=no_output, args="-P %s" % no_print, exit=6)
                self.assertMatch("found a bobcat")

        def test_9(self):
                """Test for print output to specified file."""

                source_file = os.path.join(self.test_root, "source_file")
                output_file = os.path.join(self.test_root, "output_file")
                print_file = os.path.join(self.test_root, "print_file")

                # Generate output for each file action, and count resulting
                # lines in print file to be sure it matches our expectations.
                defines = self.basic_defines.copy()
                defines["i386_ONLY"] = " "
                self.pkgmogrify([self.transforms["add bobcat"],
                    self.transforms["print ouch"], source_file],
                    defines=defines, output=output_file,
                    args="-P %s" % print_file)
                self.assertMatch("ouch", path=print_file, count=3)

        def test_10(self):
                """Test to make sure we can handle leading macros, preserve comments"""

                source_file = os.path.join(self.test_root, "source_file")
                output_file = os.path.join(self.test_root, "output_file")

                self.pkgmogrify([source_file], output=output_file, defines={})
                self.cmdline_run("diff %s %s" % (source_file, output_file))
                
        def test_11(self):
                """Test the generation of new actions."""

                source_file = os.path.join(self.test_root, "source_file2")

                # The emit operation can emit a blank line ...
                self.pkgmogrify([self.transforms["emitblank"], source_file])
                self.assertMatch("^$")

                # ... or a comment ...
                self.pkgmogrify([self.transforms["emitcomment"], source_file])
                self.assertMatch("^# comment$")

                # ... or an action ...
                self.pkgmogrify([self.transforms["emitaction"], source_file])
                self.assertMatch("^depend fmri=wombat/heaven@1.0,5.11-0.101 type=incorporate")

                # Recursive transforms shouldn't blow up.
                self.pkgmogrify([self.transforms["recurse"], source_file],
                    exit=1)

                # Emitted actions shouldn't be duplicated, modulo a macro
                # prefix.
                source_file = os.path.join(self.test_root, "source_file3")
                defines = self.basic_defines.copy()
                del defines["i386_ONLY"]

                self.pkgmogrify([self.transforms["rbneeded"], source_file],
                    defines=defines)
                self.assertMatch("name=magic", count=3)

        def test_12(self):
                """Test the use of action attributes."""

                source_file = os.path.join(self.test_root, "source_file2")

                expect = "^test of \"%s\" ... or is it\?$"
                fmri = "wombat/heaven@1.0,5.11-0.101"

                # Simple %() replacement
                self.pkgmogrify([self.transforms["fmrival"], source_file])
                self.assertMatch(expect % fmri)

                # We should exit with an error and exit code 1 when the %()
                # replacement fails because of a missing attribute.
                self.pkgmogrify([self.transforms["fmrinoval"], source_file],
                    exit=1)
                self.assertMatch("'valuee' not found")

                # When the attribute is missing but a notfound token is present,
                # we should see that value show up.
                self.pkgmogrify([self.transforms["fmrisaved"], source_file])
                self.assertMatch(expect % "noprint")

                # If the notfound value has quotes, the quoted value should show
                # up, and the quotes dropped.
                self.pkgmogrify([self.transforms["fmriqsaved"], source_file])
                self.assertMatch(expect % '"got quotes"')

                # When a notfound value is present, but the original attribute
                # is also present, the notfound value should be ignored.
                self.pkgmogrify([self.transforms["fmrinotsaved"], source_file])
                self.assertMatch(expect % fmri)

                # Basic list-valued attribute
                self.pkgmogrify([self.transforms["list"], source_file])
                self.assertMatch("^test of listval \"12345 54321 13524\"$")

                # List-valued attribute with a separator
                self.pkgmogrify([self.transforms["listsep"], source_file])
                self.assertMatch("^test of listval \"12345,54321,13524\"$")

                # List-valued attribute with a prefix, suffix, and separator
                self.pkgmogrify([self.transforms["listsufpresep"], source_file])
                self.assertMatch("^test of listval \"bug='12345', bug='54321', "
                    "bug='13524'\"$")

                # Singly-valued attribute with a prefix and suffix
                self.pkgmogrify([self.transforms["nolistsufpre"], source_file])
                self.assertMatch("^test of \"bug='12345'\"$")

                # Synthetic attributes
                self.pkgmogrify([self.transforms["synthetic"], source_file])
                self.assertMatch("^%s 4$" % source_file)

                # Synthetic attributes
                self.pkgmogrify([self.transforms["synthetic2"], source_file])
                self.assertMatch("^thisismyhashvalue usr/bin/foo file$")

                # The "action.hash" attribute shouldn't cause a problem when a
                # file action doesn't specify the hash in the manifest.
                self.pkgmogrify([self.transforms["synthetic3"], source_file])

                # The "action.hash" attribute shouldn't explode when an action
                # which doesn't have one tries to use it.
                self.pkgmogrify([self.transforms["synthetic4"], source_file],
                    exit=1)

                # The "action.hash" attribute can have a "notfound" value.
                self.pkgmogrify([self.transforms["synthetic5"], source_file])
                self.assertMatch("^something$")

        def test_13(self):
                """Test the use of package attributes."""

                source_file = os.path.join(self.test_root, "source_file2")

                # Simple valued
                self.pkgmogrify([self.transforms["pkg.fmri"], source_file])
                self.assertMatch('^pkg attr "wombat/heaven@1.0,5.11-0.101" and '
                    'the rest$')

                # List valued
                self.pkgmogrify([self.transforms["pkg.bugs"], source_file])
                self.assertMatch('^pkg attr "12345 54321 13524" and the rest$')

                defines = self.basic_defines.copy()
                defines["MYATTR"] = "pkg.obsolete"
                # Match on package attributes, and generate temporary ones
                self.pkgmogrify([self.transforms["pkgmatch"],
                    self.transforms["pkggen"], source_file], defines=defines)
                self.assertMatch("^depend fmri=consolidation type=require$")

                # If we don't match, don't generate
                defines["MYATTR"] = "bugs"
                self.pkgmogrify([self.transforms["pkgmatch"],
                    self.transforms["pkggen"], source_file], defines=defines)
                self.assertNoMatch("^depend fmri=consolidation type=require$")

if __name__ == "__main__":
        unittest.main()
