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
# gen_os_files.py - create GUI package classification files.
#

import gettext
import getopt
import os
import simplejson
import sys

# Alias gettext.gettext to _
_ = gettext.gettext

class GenOSFiles:
    """Simple script to create the file ("opensolaris.org.sections") used by 
    the GUI Package Manager, from the existing package classification lines.
 
    See bug #4483 for more details.
 
    Usage:
      $ cd .../gate/src/util/distro-import
      $ python gen_os_files.py
 
    By default, it will automatically overwrite:
      ../../gui/data/opensolaris.org.sections
    in the pkg source workspace.
 
    It is expected that this will be run (typically using the 
    "make guiclassification" target in the Makefile), as part of the 
    preparation for turning a new WOS build into a new OpenSolaris 
    development release. In other words, the new version
    "opensolaris.org.sections" will be checked in as part of that update.
    """

    def __init__(self):
        """Creates a new instance of the GenOSFiles class.
        """

        self.prefix = "."     # Directory prefix for finding files.

        self.debug = False    # Whether to output debug messages to stderr.

        # Name of the file containing package categories.
        #
        self.os_cat_name = "../../gui/data/opensolaris.org.sections"

        # Location of the classifications file (override with -c option).
        self.class_file = "./classifications.txt"

        # Dictionary of valid categories / sub-categories.
        self.categories = {}

        # Dictionary of packages found.
        #
        self.packages = {}

        # Number of different packages found.
        #
        self.package_count = 0

    def init_categories(self):
        """Initialize a dictionary of valid categories / sub-categories.
        The categories are the keys and the sub-categories are a list
        of valid sub-categories for that category).
        """

        try:
            fileobj = open(self.class_file, 'r')
            self.categories = simplejson.load(fileobj)
        except IOError, e:
            print >> sys.stderr, "Unable to get package classifications.", e
            sys.exit(3)

    def save_entry(self, pathname, categories, sub_categories):
        """For the given package name, create a new entry in a list of
        the classifications for this package. The entry will consist of
        a build number, a list of categories and a list of sub_categories.
        If the categories and sub-categories are None, then this means 
        that for that build number, this package was not classified.
        """

        # The following adjustments are made because the GUI Package
        # Manager code is currently unable to handle sub-categories
        # with the same name in different categories:
        #
        # Desktop (GNOME)/Localizations
        #                      -> Desktop (GNOME)/Localizations (Desktop)
        # System/Databases     -> System/Databases (System)
        # System/Libraries     -> System/Libraries (System)
        # System/Localizations -> System/Localizations (System)
        # System/X11           -> System/X11 (System)
        #
        if self.package_name:
            for i, (category, sub_category) in \
                enumerate(zip(categories, sub_categories)):

                if not category in self.categories or \
                    not sub_category in self.categories[category]:
                    sys.stderr.write("WARNING: package %s: " % 
                        self.package_name)
                    sys.stderr.write(" classification %s/%s not valid\n" % 
                        (category, sub_category))

                old_sub_category = sub_category

                if category == "Desktop (GNOME)" and \
                   sub_category == "Localizations":
                    sub_categories[i] = "Localizations (Desktop)"

                elif category == "System" and sub_category == "Databases":
                    sub_categories[i] = "Databases (System)"

                elif category == "System" and sub_category == "Libraries":
                    sub_categories[i] = "Libraries (System)"

                elif category == "System" and sub_category == "Localizations":
                    sub_categories[i] = "Localizations (System)"

                elif category == "System" and sub_category == "X11":
                    sub_categories[i] = "X11 (System)"

                if self.debug:
                    if old_sub_category != sub_category:
                        sys.stderr.write("CHANGED: sub_category: %s\n" %
                                         sub_category)

                if sub_category and len(sub_category) == 0:
                    message = "**** Package %s: empty sub-category\n" % \
                              self.package_name
                    sys.stderr.write(message)
                    return

            tokens = pathname[len(self.prefix):-1].split("/")
            if self.debug:
                sys.stderr.write("tokens[1]: %s\n" % tokens[1])

            try:
                build_no = int(tokens[1])
            except ValueError:
                try:
                    build_no = int(tokens[1][:-1])
                except ValueError:
                    build_no = 0   # For unbundleds files.

            if self.package_name in self.packages:
                packages = self.packages[self.package_name]
                packages.append([build_no, categories, sub_categories])
                self.packages[self.package_name] = packages
            else:
                self.packages[self.package_name] = \
                    [ [build_no, categories, sub_categories] ]

        else:
            message = \
                "**** Classification with no package name in %s" % pathname
            sys.stderr.write(message)

    def extract_info(self, pathname):
        """Extract information that we are interested in. This will be the
        package name from "package" lines and category/sub-category from
        "classification" lines.
        """

        fin = open(pathname, 'r')
        lines = fin.readlines()
        fin.close()

        if self.debug:
            sys.stderr.write("Pathname: %s\n" % pathname)

        self.package_name = None
        classification_found = False
        categories = []
        sub_categories = []
        for line in lines:
            line = line.rstrip()
            if line.startswith("package"):
                tokens = line.split()
                try:
                    self.package_name = tokens[1]
                    if self.debug:
                        sys.stderr.write("Package name: %s\n" %
                                         self.package_name)
                except IndexError:
                    pass

            elif line.startswith("classification") or \
                line.startswith("$(i386_ONLY)classification") or \
                line.startswith("$(sparc_ONLY)classification"):
                classification_found = True
                tokens = line.split(None, 1)[1].strip('"').split("/")
                try:
                    category, sub_category = tokens
                    if self.debug:
                        sys.stderr.write("category: %s\n" % category)
                        sys.stderr.write("sub_category: %s\n" % sub_category)
                    categories.append(category)
                    sub_categories.append(sub_category)
                except IndexError:
                    message = "**** Malformed classification line: %s:\n" % line
                    sys.stderr.write(message)
                    return

            elif line.startswith("end package"):
                self.save_entry(pathname, categories, sub_categories)
                self.package_name = None
                classification_found = False
                categories = []
                sub_categories = []

        if self.package_name and not classification_found:
            self.save_entry(pathname, None, None)

    def cleanup_packages(self):
        """For each of the keys in the packages dictionary, sort the
        entries in the value by build number, and reset the dictionary
        entry to just the last value.
        """

        for key in sorted(self.packages.keys()):
            packages = self.packages[key]
            packages.sort(lambda x, y:cmp(x[0], y[0]))
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
      gen_os_files [OPTION...]

-h, --help
      Show this help message

-d, --debug
      Turn on debugging.

-c, --category=category-file-name
      Specify an alternate file name to write out the
      package category values to.""")

        sys.exit(2)

    def write_cat_file(self):
        """Sort the dictionary keys (package names) and write out the
        category information to the category file.
        """

        categories = {}
        for key in sorted(self.packages.keys()):
            build_no, pkg_categories, pkg_sub_categories = self.packages[key]

            for i, (category, sub_category) in \
                enumerate(zip(pkg_categories, pkg_sub_categories)):

                if category and sub_category:
                    if category in categories:
                        # If we already have a list started for this category,
                        # then just append this sub-category to it, if it isn't
                        # already there.
                        #
                        sub_categories = categories[category]
                        if not sub_category in sub_categories:
                            sub_categories.append(sub_category)
                            categories[category] = sub_categories
                    else:
                        categories[category] = [ sub_category ]

        fout = open(self.os_cat_name, 'w')

        # Write out the part that we can't derive from the package
        # classifications.
        #
        fout.write("[Meta Packages]\n")
        fout.write(
          "category = Builds,Releases,Developer Tools,AMP Stack,Office Tools")
        fout.write("\n\n")

        # For each of the categories, write out a sorted comma separated
        # list of all of the sub-categories.
        #
        for key in sorted(categories.keys()):
            sub_categories = ",".join(sorted(categories[key]))
            if self.debug:
                sys.stderr.write("Category: %s\n" % key)
                sys.stderr.write("Subcategories: %s\n" % sub_categories)

            fout.write("[%s]\ncategory = %s\n\n" % (key, sub_categories))
        fout.close()

    def main(self):
        """Read command line options, find a list of all files (as
        opposed to directories) under the prefix directory, and for
        each one, call extract_info to get category, subcategory 
        and build number. Finally create new versions of the new
        GUI classification files.
        """

        try:
            opts, args = getopt.getopt(sys.argv[1:], "c:dh",
                      ["category=", "debug", "help"])
        except getopt.GetoptError, e:
            self.usage(_("Illegal option -- %s") % e.opt)

        for opt, val in opts:
            if opt in ("-c", "--category"):
                self.os_cat_name = val.strip()
            if opt in ("-d", "--debug"):
                self.debug = True
            if opt in ("-h", "--help"):
                self.usage()

        self.init_categories()

        cmd = 'find %s -type f -print' % self.prefix
        lines = os.popen(cmd).readlines()
        for package_file in lines:
            self.extract_info(package_file[:-1])

        self.cleanup_packages()

        if self.debug:
            sys.stderr.write("Number of classified packages: %d\n" %
                             self.package_count)
            sys.stderr.write("Number of keys: %d\n" %
                             len(self.packages.keys()))

        self.write_cat_file()

        return 0

if __name__ == "__main__":
    gen_files = GenOSFiles()
    sys.exit(gen_files.main())
