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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import errno
import os
import re
import shutil
import six
import stat
import sys
import tempfile
import unittest
from pkg.misc import EmptyI

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
depend type=require fmri=__TBD path=usr/bin/foo mode=0755
file NOHASH path="'/usr/bin/quotedpath'" moo=cowssayit
file NOHASH path=usr/share/locale/de/foo.mo
file NOHASH path=usr/share/locale/fr/foo.mo locale.fr=oui
set name=pkg.summary value="Doo wah diddy"
legacy pkg=SUNWwombat version=3
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
            "2include": "<include {X11->Y11}>\n<include {X11mode}>",
            "include 9": "<include {include 5}>",
            "include 5": "<include {empty}>",
            "add bobcat": "<transform file -> add bobcat 1>",
            "print ouch": '<transform file bobcat=1 -> print "ouch" >',
            "abort on bobcat": "<transform file bobcat=1 -> abort >",
            "exit7 on bobcat": "<transform file bobcat=1 -> exit 7>",
            "exit6 on bobcat": "<transform file bobcat=1 -> exit 6 found a bobcat>",
            "pkg.fmri": "<transform file path=usr/bin/foo -> print pkg attr \"%{{pkg.fmri}}\" and the rest>",
            "pkg.bugs": "<transform file path=usr/bin/foo -> print pkg attr \"%{{bugs}}\" and the rest>",
            "fmrival": "<transform set name=pkg.fmri -> print test of \"%(value)\" ... or is it?>",
            "fmrinoval": "<transform set name=pkg.fmri -> print test of \"%(valuee)\" ... or is it?>",
            "fmrisaved": "<transform set name=pkg.fmri -> print test of \"%(valuee;notfound=noprint)\" ... or is it?>",
            "fmriqsaved": "<transform set name=pkg.fmri -> print test of \"%(valuee;notfound=\"got quotes\")\" ... or is it?>",
            "fmrinotsaved": "<transform set name=pkg.fmri -> print test of \"%(value;notfound=noprint)\" ... or is it?>",
            "list": "<transform set name=bugs -> print test of listval \"%(value)\">",
            "listsep": "<transform set name=bugs -> print test of listval \"%(value;sep=\",\")\">",
            "listsufpresep": "<transform set name=bugs -> print test of listval \"%(value;sep=\", \";prefix=\"bug='\";suffix=\"'\")\">",
            "nolistsufpre": "<transform set name=justonebug -> print test of \"%(value;prefix=\"bug='\";suffix=\"'\")\">",
            "emitblank": "<transform set name=pkg.fmri -> emit>",
            "emitcomment": "<transform set name=pkg.fmri -> emit # comment>",
            "emitaction": "<transform set name=pkg.fmri -> emit depend type=incorporate fmri=%(value)>",
            "synthetic": "<transform file path=usr/bin/foo -> print %(pkg.manifest.filename) %(pkg.manifest.lineno)>",
            "synthetic2": "<transform file path=usr/bin/foo -> print %(action.hash) %(action.key) %(action.name)>",
            "synthetic3": "<transform file -> print %(action.hash)>",
            "synthetic4": "<transform set -> print %(action.hash)>",
            "synthetic5": "<transform set -> print %(action.hash;notfound=something)>",
            "pkgmatch": "<transform pkg -> default $(MYATTR) false>",
            "pkggen": "<transform pkg $(MYATTR)=false -> emit depend fmri=consolidation type=require>",
            "recurse": "<transform file mode=0777 -> emit file path=usr/bin/bar mode=0777>",
            "rbneeded": "<transform file reboot-needed=true -> emit set name=magic value=true>",
            "brdefault": "<transform depend fmri=__TBD path=([^/]*)/([^/]*)/ mode=0(.)55 -> default pkg.debug.depend.path %<1>/%<2>>",
            "brdefault2": "<transform depend fmri=__TBD mode=0(.)55 path=([^/]*)/([^/]*)/ -> default pkg.debug.depend.path %<2>/%<3>>",
            "brdefault3": "<transform depend fmri=__TBD mode=0(.)55 path=([^/]*)/([^/]*)/ -> default pkg.debug.depend.path %<2>/%<4>>",
            "brdefault3a": "<transform depend fmri=__TBD mode=0(.)55 path=([^/]*)/([^/]*)/ -> default pkg.debug.depend.path %<2>/%<0>>",
            "brdefault4": "<transform file path=usr/share/locale/([^/]+).* -> default locale.%<1> true>",
            "brweirdquote": "<transform file moo=(.*) path='\\'.*/([^/]*)\\'' -> default refs %<1>,%<2>>",
            "bradd": "<transform file path=usr/share/locale/([^/]+).* -> add locale.%<1> true>",
            "brset": "<transform file path=usr/share/locale/([^/]+).* -> set locale.%<1> true>",
            "bredit": "<transform file path=usr/share/locale/([^/]+).* -> edit path .*/([^/]*\\.mo) another/place/for/locales/%<1>/\\\\1>",
            "bredit2": "<transform file path=usr/share/locale/([^/]+).* -> edit path %<1> LANG>",
            "edit1": "<transform file path=usr/(share|lib)/locale.* -> edit path usr/(lib|share)/locale place/\\\\1/langs>",
            "doublequote": "<transform legacy -> default name %{{pkg.summary}}>",
            "delete-with-no-operand": "<transform file -> delete >",
            "backreference-no-object": "<transform file path=(local/)?usr/* -> default refs %<1>>",
            "backreference-empty-string": "<transform file path=usr/bin/foo(.*)-> emit file path=usr/sbin/foo%<1>>"
        }

        basic_defines = {
            "i386_ONLY": "#",
            "BUILDID": 0.126
        }

        def setUp(self):
                pkg5unittest.CliTestCase.setUp(self)

                with open(os.path.join(self.test_root, "source_file"), "w") as f:
                        f.write(self.pkgcontents)

                with open(os.path.join(self.test_root, "source_file2"), "w") as f:
                        f.write(self.pkgcontents2)

                with open(os.path.join(self.test_root, "source_file3"), "w") as f:
                        f.write(self.pkgcontents3)

                # Map the transform names to path names
                xformpaths = dict((
                    (name, os.path.join(self.test_root, "transform_{0}".format(i)))
                    for i, name in enumerate(six.iterkeys(self.transforms))
                ))

                # Now that we have path names, we can use the expandos in the
                # transform contents to embed those pathnames, and write the
                # transform files out.
                for name, path in six.iteritems(xformpaths):
                        with open(path, "w") as f:
                                self.transforms[name] = self.transforms[name].format(**xformpaths)
                                f.write(self.transforms[name])

                self.transform_contents = self.transforms
                self.transforms = xformpaths

        def pkgmogrify(self, sources=EmptyI, defines=None,
            output=None, args="", exit=0, stdin=None):
                if defines is None:
                        defines = self.basic_defines

                defines = " ".join([
                    "-D {0}={1}".format(k, v)
                    for k, v in six.iteritems(defines)
                ])

                sources = " ".join(sources)

                if output:
                        args += " -O {0}".format(output)

                cmd = sys.executable + " {0}/usr/bin/pkgmogrify {1} {2} {3}".format(
                    pkg5unittest.g_pkg_path, defines, args, sources)

                self.cmdline_run(cmd, stdin=stdin, exit=exit)

        def __countMatches(self, regex, path=None):
                """Count how many lines in the output of the previously run
                command match the regular expression 'regex'.  If 'path' is
                specified, the contents of that file are searched."""

                if path is not None:
                        with open(path) as f:
                                output = f.read()
                else:
                        output = self.output + self.errout

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

                self.assertFalse(count == c == 0,
                    "No matches for '{0}' found".format(regex))
                if count > 0:
                        self.assertTrue(c == count,
                            "{0} matches for '{1}' found, {2} expected".format(
                            c, regex, count))

        def assertNoMatch(self, regex, path=None):
                """Assert that the regular expression 'regex' is not found in
                the output of the previously run command.  If 'path' is
                specified, the contents of that file are searched."""

                c = self.__countMatches(regex, path)

                self.assertTrue(c == 0, "Match for '{0}' found unexpectedly".format(regex))

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

                # stdin only
                with open(source_file, "r") as f:
                        self.pkgmogrify(stdin=f, defines=defines)
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

                self.pkgmogrify([self.transforms["X11->Y11"], source_file])
                self.assertNoMatch("X11")
                self.assertMatch("Y11")

                # stdin and source file combined
                with open(source_file, "r") as f:
                        self.pkgmogrify(["-", self.transforms["X11->Y11"]], stdin=f)
                        self.assertNoMatch("X11")
                        self.assertMatch("Y11")

                self.pkgmogrify([self.transforms["add bobcat"], source_file])
                self.assertMatch("bobcat", count=3)

                self.pkgmogrify([self.transforms["drop mode=0755"], source_file])
                self.assertNoMatch("^file.*mode=0755")
                self.pkgmogrify([self.transforms["delete-with-no-operand"],
                    source_file], exit=1)

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
                    source_file], args="-I {0}".format(self.test_root))
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
                    args="-I {0}".format(self.test_root), exit=1)

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
                    output=no_output, args="-P {0}".format(no_print))

                # Make sure neither output nor print file was created.
                self.assertFalse(os.access(no_output, os.F_OK))
                self.assertFalse(os.access(no_print, os.F_OK))

                # Trigger an exit transform with a specific exit code.
                self.pkgmogrify([self.transforms["add bobcat"],
                    self.transforms["exit7 on bobcat"], source_file],
                    output=no_output, args="-P {0}".format(no_print), exit=7)

                # Make sure neither output nor print file was created.
                self.assertFalse(os.access(no_output, os.F_OK))
                self.assertFalse(os.access(no_print, os.F_OK))

                # Trigger an exit transform with a specific exit code and
                # message.
                self.pkgmogrify([self.transforms["add bobcat"],
                    self.transforms["exit6 on bobcat"], source_file],
                    output=no_output, args="-P {0}".format(no_print), exit=6)
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
                    args="-P {0}".format(print_file))
                self.assertMatch("ouch", path=print_file, count=3)

        def test_10(self):
                """Test to make sure we can handle leading macros, preserve comments"""

                source_file = os.path.join(self.test_root, "source_file")
                output_file = os.path.join(self.test_root, "output_file")

                self.pkgmogrify([source_file], output=output_file, defines={})
                self.cmdline_run("diff {0} {1}".format(source_file, output_file),
                    coverage=False)
                
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

                expect = "^test of \"{0}\" ... or is it\?$"
                fmri = "wombat/heaven@1.0,5.11-0.101"

                # Simple %() replacement
                self.pkgmogrify([self.transforms["fmrival"], source_file])
                self.assertMatch(expect.format(fmri))

                # We should exit with an error and exit code 1 when the %()
                # replacement fails because of a missing attribute.
                self.pkgmogrify([self.transforms["fmrinoval"], source_file],
                    exit=1)
                self.assertMatch("'valuee' not found")

                # When the attribute is missing but a notfound token is present,
                # we should see that value show up.
                self.pkgmogrify([self.transforms["fmrisaved"], source_file])
                self.assertMatch(expect.format("noprint"))

                # If the notfound value has quotes, the quoted value should show
                # up, and the quotes dropped.
                self.pkgmogrify([self.transforms["fmriqsaved"], source_file])
                self.assertMatch(expect.format('"got quotes"'))

                # When a notfound value is present, but the original attribute
                # is also present, the notfound value should be ignored.
                self.pkgmogrify([self.transforms["fmrinotsaved"], source_file])
                self.assertMatch(expect.format(fmri))

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
                self.assertMatch("^{0} 4$".format(source_file))

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

                self.pkgmogrify([self.transforms["doublequote"], source_file])
                self.assertNoMatch("^legacy .*'\"")

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

        def test_14(self):
                """Test the use of backreferences to the matching portion of the
                transform."""

                source_file = os.path.join(self.test_root, "source_file2")

                # Basic test of backreferences, using the default operation.
                self.pkgmogrify([self.transforms["brdefault"], source_file])
                self.assertMatch("pkg.debug.depend.path=usr/bin($| )")

                # Same operation, but reorder the match criteria (and the
                # references to match) to show that the reference numbers are
                # based on the literal order of the match criteria, rather than
                # some internal storage mechanism.
                self.pkgmogrify([self.transforms["brdefault2"], source_file])
                self.assertMatch("pkg.debug.depend.path=usr/bin($| )")

                # A reference to a group that doesn't exist should die
                # gracefully.
                self.pkgmogrify([self.transforms["brdefault3"], source_file],
                    exit=1)

                # A reference to group 0 should die gracefully.
                self.pkgmogrify([self.transforms["brdefault3a"], source_file],
                    exit=1)

                # A backreference may very well be used as part of an attribute
                # name.  Make sure that the "default" operation takes the fully
                # substituted attribute name into account.
                self.pkgmogrify([self.transforms["brdefault4"], source_file])
                self.assertMatch("locale.de=true")
                self.assertMatch("locale.fr=oui")

                # Quoting in a match attribute may not agree with the quoting
                # that actions use, confusing the mechanism we use to ensure
                # backreference numbers refer to the right groups.  Make sure
                # we don't tip over, but show that we didn't get the backrefs
                # right.  The right solution for this is probably to have a
                # mode for fromstr() that returns a list rather than a dict.
                self.pkgmogrify([self.transforms["brweirdquote"], source_file])
                # XXX # self.assertMatch("refs=cowssayit,quotedpath")

                # A "set" operation with a backreference works.
                self.pkgmogrify([self.transforms["brset"], source_file])
                self.assertMatch("locale.de=true")
                self.assertMatch("locale.fr=true")

                # An "add" operation with a backreference works.
                self.pkgmogrify([self.transforms["bradd"], source_file])
                self.assertMatch("locale.de=true", count=1)
                self.assertMatch("locale.fr=oui", count=1)
                self.assertMatch("locale.fr=true", count=1)

                # This is the "normal" kind of backreferencing, only available
                # for the "edit" operation, where a \1 in the replacement string
                # refers to a group in the regex string, all on the operation
                # side of the transform.
                self.pkgmogrify([self.transforms["edit1"], source_file])
                self.assertMatch("path=place/share/langs/de/foo.mo")

                # An "edit" operation with a backreference in the replacement
                # value works.  This one also uses the \1-style backreference.
                self.pkgmogrify([self.transforms["bredit"], source_file])
                self.assertMatch("path=another/place/for/locales/de/foo.mo")

                # An "edit" operation with a backreference in the matching
                # expression works.
                self.pkgmogrify([self.transforms["bredit2"], source_file])
                self.assertMatch("path=usr/share/locale/LANG/foo.mo")

                # A backreference to an unmatched group is an error.
                self.pkgmogrify([self.transforms["backreference-no-object"],
                    source_file], exit=1)

                # A backreference to an empty string should work.
                self.pkgmogrify([self.transforms["backreference-empty-string"],
                    source_file])
                self.assertMatch("path=usr/sbin/foo")

if __name__ == "__main__":
        unittest.main()
