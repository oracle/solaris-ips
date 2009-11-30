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
# check_depends.py - check package dependencies.
#

import gettext
import getopt
import os
import sys
import pprint
import re

# Alias gettext.gettext to _
_ = gettext.gettext

class CheckDepends:
    """Simple script to check the dependencies of each of the latest IPS
    packages against those specified in the imported WOS SVR4 packages
    .../install/depend file, and list those not present to stdout.
 
    Usage:
      $ cd .../gate/src/util/distro-import
      $ python check_depends.py >depend-report.txt
    """

    def __init__(self):
        """Creates a new instance of the CheckDepends class.
        """

        self.prefix = "."     # Directory prefix for finding files.

        self.debug = False    # Whether to output debug messages to stderr.

        # Name of the directory containing the WOS packages.
        self.WOS_dir = \
            "/net/netinstall.sfbay/export/nv/x/latest/Solaris_11/Product"

        # Dictionary of IPS packages found.
        self.packages = {}

        # Dictionary of WOS packages found.
        self.WOS_packages = {}

        # Dictionary mapping SVR4 package names to IPS package names.
        self.SVR4_to_IPS = {}

        # List of packages to ignore as per:
        # http://defect.opensolaris.org/bz/show_bug.cgi?id=5268#c7
        #
        # SUNWcslr is not listed in the note above. However in IPS
        # SUNWcsl and SUNWcslr are merged into SUNWcsl. So any 
        # packages that requre SUNWcslr will have that dependency met
        # in IPS. We add it to this list so that we can safley ignore
        # it.
        self.deps_to_ignore = [
            "SUNWcar", "SUNWcakr", "SUNWkvm", "SUNWcsr", "SUNWckr",
            "SUNWcnetr", "SUNWcsu", "SUNWcsd", "SUNWcsl", "SUNWcslr" 
        ]


    def save_entry(self, pathname, package_name, imports, depends):
        """For the given package name, either create a new entry in the
        packages dictionary if it doesn't exist, or append a new entry to
        the existing one. Each entry consists of the build number plus a
        list of SVR4 package names that are imported by this IPS package
        plus a list of the SVR4 package names that this IPS package 
        currently depends upon.
        """

        tokens = pathname[len(self.prefix):-1].split("/")
        if self.debug:
            print >> sys.stderr, "tokens[1]: %s\n" % tokens[1]

        try:
            build_no = int(tokens[1])
        except ValueError:
            try:
                build_no = int(tokens[1][:-1])
            except ValueError:
                return             # Don't care about unbundleds files.

        if package_name in self.packages:
            packages = self.packages[package_name]
            packages.append([build_no, imports, depends ])
            self.packages[package_name] = packages
        else:
            self.packages[package_name] = [ [build_no, imports, depends] ]

    def extract_info(self, pathname):
        """Extract information that we are interested in. This will be the
        package name from "package" lines and imported packages ("import"
        lines) and dependency packages ("depend" lines).
        """

        fin = open(pathname, 'r')
        lines = fin.readlines()
        fin.close()

        if self.debug:
            print >> sys.stderr, "Pathname: %s\n" % pathname

        package_name = None
        imports = []
        depends = []
        for line in lines:
            line = line.rstrip()
            if line.startswith("package"):
                tokens = line.split()
                try:
                    package_name = tokens[1]
                    if self.debug:
                        print >> sys.stderr, "Package name: %s\n" % package_name
                except IndexError:
                    pass

            elif line.startswith("depend"):
                tokens = line.split()
                try:
                    SVR4_depend_name = tokens[1]
                    if self.debug:
                        print >> sys.stderr, \
                            "SVR4 depend package name: %s\n" % SVR4_depend_name
                except IndexError:
                    print >> sys.stderr, \
                        "**** Malformed depend line: %s:\n" % line
                    return

            elif line.startswith("import"):
                tokens = line.split()
                try:
                    SVR4_import_name = tokens[1]
                    if self.debug:
                        print >> sys.stderr, \
                            "SVR4 import package name: %s\n" % SVR4_import_name
                except IndexError:
                    print >> sys.stderr, \
                        "**** Malformed import line: %s:\n" % line
                    return

                imports.append(SVR4_import_name)
                self.SVR4_to_IPS[SVR4_import_name] = package_name

        # Get the full list of depends from the repo.
        if package_name:
            cmd = "pfexec pkg contents -rm %s" % package_name
            lines = os.popen(cmd).readlines()
            for line in lines:
                line = line.rstrip()
                if line.startswith("depend"):
                    tokens = line.split()
                    if len(tokens) < 2:
                        print >> sys.stderr, \
                            "**** Malformed depend line: %s:\n" % line  
                        return
                    pkgmatch = re.search(r'(=|/)([\w-]*?)(@|\s).*$', tokens[1])
                    if pkgmatch: 
                        pkg = pkgmatch.group(2)
                    else: 
                        pkg = ""
                    if self.debug:  
                        print >> sys.stderr, "%s\n" % line
                        print >> sys.stderr, \
                            "SVR4 depend package name: %s\n" % pkg
                    depends.append(pkg) 

            depends = set(depends)
            self.save_entry(pathname, package_name, imports, depends)

    def cleanup_packages(self):
        """For each of the keys in the packages dictionary, sort the
        entries in the value by build number, and reset the dictionary
        entry to just the last value.
        """

        for key in sorted(self.packages.keys()):
            packages = self.packages[key]
            packages.sort(lambda x, y:cmp(x[0], y[0]))
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
      check_depends [OPTION...]

-h, --help
      Show this help message

-d, --debug
      Turn on debugging.

-w, --wosdir=wos-directory
      Specify an alternate directory for the location
      of the WOS SVR4 packages""")

        sys.exit(2)

    def get_depend_info(self):
        """For each of the packages in the WOS package directory, if there
        is a .../install/depend file, then extract out all the package names
        that it depends upon.
        """

        for package_name in os.listdir(self.WOS_dir):
            depend_file_name = "%s/%s/install/depend" % \
                (self.WOS_dir, package_name)
            if os.path.exists(depend_file_name):
                depends = []
                fin = open(depend_file_name, 'r')
                for line in fin.readlines():
                    if line.startswith("P"):
                        tokens = line.split()
                        depends.append(tokens[1])

            self.WOS_packages[package_name] = depends

    def check_dependencies(self):
        """For each of the import lines in each of the latest versions
        of the IPS packages, check if all the dependencies mentioned in
        the WOS SVR4 packages .../install/depend file are present in the
        IPS package definition, and if they are not, print them out.
        """

        if self.debug:
            pp = pprint.PrettyPrinter(indent=4, stream=sys.stderr)
            print >> sys.stderr, "self.SVR4_to_IPS\n"
            pp.pprint(self.SVR4_to_IPS)
            print >> sys.stderr, "self.WOS_packages\n"
            pp.pprint(self.WOS_packages)
            print >> sys.stderr, "self.packages\n"
            pp.pprint(self.packages)

        for key in sorted(self.packages.keys()):
            build_no, imports, depends = self.packages[key]

            svr4deps = []
            missing = []
            missingsvr4 = []

            print "Package: %s" % key

            for svrpkg in imports:
                if svrpkg in self.WOS_packages:
                    for pkg in self.WOS_packages[svrpkg]:
                        if not pkg in self.deps_to_ignore:
                            svr4deps.append(pkg)
                else:
                    print "\t%s not present in SVR4 image." % svrpkg

            if self.debug: 
                print >> sys.stderr, "svr4deps for %s \n" % key
                pp.pprint(svr4deps)

            for pkg in svr4deps:
                if not pkg in (self.SVR4_to_IPS.keys()):
                    pkg += ".i"
                if not pkg in (self.SVR4_to_IPS.keys()):
                    missingsvr4.append(pkg) 
                else:  
                    ipspkg = self.SVR4_to_IPS[pkg]
                    if not ipspkg in depends:
                        if ipspkg != key:
                            missing.append(ipspkg)

            missing = set(missing)
            missingsvr4 = set(missingsvr4)
            for name in missing:
                print "\t%s" % name
            for name in missingsvr4:
                print "\t%s no corresponding IPS package found" % name

    def main(self):
        """Read command line options, find a list of all files (as
        opposed to directories) under the prefix directory, and for
        each one, call extract_info to get package name, imported
        SVR4 packages, and package dependencies.
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
        self.get_depend_info()
        self.check_dependencies()

        return 0

if __name__ == "__main__":
    check_depends = CheckDepends()
    sys.exit(check_depends.main())
