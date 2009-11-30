#!/usr/bin/python2.6
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
#
# list_build_files.py - list all the package files that make up a build.
#

import gettext
import getopt
import os
import sys

# Alias gettext.gettext to _
_ = gettext.gettext

class ListBuildFiles:
    """Simple script to list all the IPS package files associated with a
    particular WOS build.
 
    Usage:
      $ cd .../gate/src/util/distro-import
      $ python list_build_files.py 101a > build-report.txt
    """

    def __init__(self):
        """Creates a new instance of the ListBuildFiles class.
        """

        self.prefix = os.path.curdir    # Directory prefix for finding files.

        self.debug = False    # Whether to output debug messages to stderr.

        # Build number to list the files for (mandatory command line option).
        # It can be suffixed by a build letter (i.e. '101a').
        #
        self.build_no = None

        # The build letter (if any) suffixed to the build number.
        #
        self.build_letter = None

        # Dictionary of packages found.
        #
        self.packages = {}

    def save_entry(self, pathname, package_name):
        """For the given package name, create a new entry in a list of
        the package files associated with this package, if the build
        number for the file is less that the requested build number.
        If it's the same, then a check is also made of the build letter
        (if present).  The entry will consist of a build number, a build
        letter (if present) and the file path name.
        """

        tokens = pathname[len(self.prefix):-1].split(os.path.sep)
        if self.debug:
            sys.stderr.write("tokens[1]: %s\n" % tokens[1])

        build_letter = None
        try:
            build_no = int(tokens[1])
        except ValueError:
            try:
                build_no = int(tokens[1][:-1])
                build_letter = tokens[1][-1]
            except ValueError:
                return      # Don't include packages from unbundleds files.

        # Don't care about package files for later builds.
        #
        if build_no > self.build_no:
            return
        if build_no == self.build_no:
            if not self.build_letter and build_letter:
                return
            if self.build_letter and (build_letter > self.build_letter):
                return

        if package_name in self.packages:
            packages = self.packages[package_name]
            packages.append([build_no, build_letter, pathname])
            self.packages[package_name] = packages
        else:
            self.packages[package_name] = \
                [ [build_no, build_letter, pathname] ]

    def extract_info(self, pathname):
        """Extract information that we are interested in. This will
        just be the package name from "package" lines.
        """

        fin = open(pathname, 'r')
        lines = fin.readlines()
        fin.close()

        if self.debug:
            sys.stderr.write("Pathname: %s\n" % pathname)

        package_name = None
        for line in lines:
            line = line.rstrip()
            if line.startswith("package"):
                tokens = line.split()
                try:
                    package_name = tokens[1]
                    if self.debug:
                        sys.stderr.write("Package name: %s\n" % package_name)
                except IndexError:
                    pass

        if package_name:
            self.save_entry(pathname, package_name)

    def cleanup_packages(self):
        """For each of the keys in the packages dictionary, sort the
        entries in the value by build number, and reset the dictionary
        entry to just the last value.
        """

        for key in sorted(self.packages.keys()):
            packages = self.packages[key]
            packages = sorted(packages, key=lambda x:(x[0], x[1]))
            self.packages[key] = packages[-1]

    def usage(self, usage_error = None):
        """Emit a usage message and optionally prefix it with a more
        specific error message. Causes program to exit.

        Argument:
        - usage_error: optional usage error message.
        """

        pname = os.path.basename(sys.argv[0])
        if usage_error:
            print >> sys.stderr, pname + ": " + usage_error

        print >> sys.stderr, _("""\
Usage: 
      list_build_files [OPTION...] build-number

-d, --debug
      Turn on debugging.

-h, --help
      Show this help message""")

        sys.exit(2)

    def list_files(self):
        """Print to stdout, a list of all the package files that make up
        this build.
        """

        for key in sorted(self.packages.keys()):
            build_no, build_letter, pathname = self.packages[key]
            print "%s\t%s" % (key.ljust(28), pathname)

    def main(self):
        """Read command line options, find a list of all files (as
        opposed to directories) under the prefix directory, and for
        each one, call extract_info to get the package name  and 
        build number. Sort package filename information, just retaining
        the last one for each package name. Finally list all the files 
        that make up the requested build.
        """

        try:
            opts, args = getopt.getopt(sys.argv[1:], "dh",
                      ["debug", "help"])
        except getopt.GetoptError, e:
            self.usage(_("Illegal option -- %s") % e.opt)

        for opt, val in opts:
            if opt in ("-d", "--debug"):
                self.debug = True
            if opt in ("-h", "--help"):
                self.usage()

        if args == None or len(args) != 1:
            self.usage()

        try:
            self.build_no = int(args[0].strip())
            self.build_letter = None
        except ValueError:
            try:
                self.build_no = int(args[0].strip()[:-1])
                self.build_letter = args[0].strip()[-1]
            except ValueError:
                self.usage()

        cmd = 'find %s -type f -print' % self.prefix
        lines = os.popen(cmd).readlines()
        for package_file in lines:
            self.extract_info(package_file[:-1])

        self.cleanup_packages()
        self.list_files()

        return 0

if __name__ == "__main__":
    build_files = ListBuildFiles()
    sys.exit(build_files.main())
