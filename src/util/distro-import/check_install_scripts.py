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
# check_install_scripts.py - check SVR4 package pre/postinstall and IPS 
# add lines.
#

import gettext
import getopt
import os
import sys

# Alias gettext.gettext to _
_ = gettext.gettext

class CheckInstallScripts:
    """Simple script to check the package install directory of an SVR4
    package for a postinstall or preinstall file and check that the 
    corresponding IPS package has an "add..." line

    Usage:
      $ cd .../gate/src/util/distro-import
      $ python check_install_scripts.py > install-file-report.txt
    """

    def __init__(self):
        """Creates a new instance of the CheckInstallScripts class.
        """

        self.prefix = "."     # Directory prefix for finding files.

        self.debug = False    # Whether to output debug messages to stderr.

        # Name of the directory containing the WOS packages.
        self.WOS_dir = \
            "/net/netinstall.sfbay/export/nv/x/latest/Solaris_11/Product"

        # List of IPS packages with add lines.
        self.IPS_packages_with_add_line = []

        # List of WOS packages found with postinstall scripts.
        self.WOS_packages_with_postinstall = []

        # List of WOS packages found with preinstall scripts.
        self.WOS_packages_with_preinstall = []

        # Dictionary mapping SVR4 package names to IPS package names.
        self.SVR4_to_IPS = {}

        # Dictionary of packages found.
        self.packages = {}

    def process_packages(self):
        """For each of the latest IPS package files, extract information
        that we are interested in. This will be the package name from 
        "package" lines, imported packages ("import" lines) and add lines.
        """

        for key in sorted(self.packages.keys()):
            build_no, build_letter, pathname = self.packages[key]

            fin = open(pathname, 'r')
            lines = fin.readlines()
            fin.close()

            if self.debug:
                print >> sys.stderr, "Pathname: %s\n" % pathname

            package_name = None
            for line in lines:
                line = line.rstrip()
                if line.startswith("package"):
                    tokens = line.split()
                    try:
                        package_name = tokens[1]
                        if self.debug:
                            print >> sys.stderr, \
                                "Package name: %s\n" % package_name
                    except IndexError:
                        pass

                elif line.startswith("add"):
                    self.IPS_packages_with_add_line.append(package_name)
                    if self.debug:
                        print >> sys.stderr, "add line: %s\n" % line

                elif line.startswith("import"):
                    tokens = line.split()
                    try:
                        SVR4_import_name = tokens[1]
                        if self.debug:
                            print >> sys.stderr, \
                                "SVR4 import package name: %s\n" % \
                                    SVR4_import_name
                    except IndexError:
                        print >> sys.stderr, \
                            "**** Malformed import line: %s:\n" % line
                        return

                    self.SVR4_to_IPS[SVR4_import_name] = package_name

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

    def usage(self, usage_error=None):
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
      check_install_scripts [OPTION...]

-h, --help
      Show this help message

-d, --debug
      Turn on debugging.

-w, --wosdir=wos-directory
      Specify an alternate directory for the location
      of the WOS SVR4 packages""")

        sys.exit(2)

    def get_install_script_info(self):
        """For each of the packages in the WOS package directory, if there
        is a .../install/[pre|post]install file, then add it to our list.
        """

        for package_name in os.listdir(self.WOS_dir):
            postinstall_file_name = "%s/%s/install/postinstall" % \
                (self.WOS_dir, package_name)
            preinstall_file_name = "%s/%s/install/preinstall" % \
                (self.WOS_dir, package_name)
            if os.path.exists(postinstall_file_name):
                self.WOS_packages_with_postinstall.append(package_name)
            if os.path.exists(preinstall_file_name):
                self.WOS_packages_with_preinstall.append(package_name)

    def check_for_add_lines(self):
        """For each SVR4 package that has a pre/postinstall file check
        whether there is an 'add' line in the IPS definition. If not
        print the pacakge name.
        """

        nosvr4pkg = []
        noaddline = {}

        for package in self.WOS_packages_with_postinstall:
            if not package in self.SVR4_to_IPS:
                nosvr4pkg.append(package)

            else:
                IPSpkg = self.SVR4_to_IPS[package]

                if not IPSpkg in self.IPS_packages_with_add_line:
                    noaddline[package] = IPSpkg
        
        print "Packages that have postinstall files in SVR4 but no 'add' \
lines in IPS:\n"
        print "\t%-28s\t%-28s" % ("SVR4 package", "(IPS package):")
        print "\t%-28s\t%-28s" % ("------------", "--------------")
        for pkg in sorted(noaddline.keys()):
            print "\t%-28s\t(%s)" % (pkg, noaddline[pkg])

        noaddline = {}
        for package in self.WOS_packages_with_preinstall:
            if not package in self.SVR4_to_IPS:
                nosvr4pkg.append(package)

            else:
                IPSpkg = self.SVR4_to_IPS[package]

                if not IPSpkg in self.IPS_packages_with_add_line:
                    noaddline[package] = IPSpkg

        print "\n\nPackages that have preinstall files in SVR4 but no 'add' \
lines in IPS:\n"
        print "\t%-28s\t%-28s" % ("SVR4 package", "(IPS package):")
        print "\t%-28s\t%-28s" % ("------------", "--------------")
        for pkg in sorted(noaddline.keys()):
            print "\t%-28s\t(%s)" % (pkg, noaddline[pkg])

        print "\n\nSVR4 Packages that have no corresponding IPS packages:\n"
        for pkg in nosvr4pkg:
            print "\t%s" % pkg
        print

    def main(self):
        """Read command line options, find a list of all files (as
        opposed to directories) under the prefix directory, and for
        each one, call extract_info to get package name, imported
        SVR4 packages, and package 'add' lines.
        """

        try:
            opts, args = getopt.getopt(sys.argv[1:], "dhw:",
                      ["debug", "help", "wosdir="])
        except getopt.GetoptError, e:
            self.usage(_("Illegal option -- %s") % e.opt)

        for opt, val in opts:
            if opt in ("-d", "--debug"):
                self.debug = True
            if opt in ("-h", "--help"):
                self.usage()
            if opt in ("-w", "--wosdir"):
                self.WOS_dir = val.strip()

        lines = []
        for dir, _, files in os.walk(self.prefix):
            lines.extend(os.path.join(dir, file) for file in files)
        for package_file in lines:
            self.extract_info(package_file)

        self.cleanup_packages()
        self.process_packages()

        self.get_install_script_info()
        self.check_for_add_lines()

        return 0

if __name__ == "__main__":
    check_install_scripts = CheckInstallScripts()
    sys.exit(check_install_scripts.main())
