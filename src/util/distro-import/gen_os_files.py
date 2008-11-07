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
#
# gen_os_files.py - create GUI package classification files.
#

import gettext
import getopt
import os
import sys

# Alias gettext.gettext to _
_ = gettext.gettext

class GenOSFiles:
    """Simple script to create the the two files ("opensolaris.org" and
    "opensolaris.org.sections") used by the GUI Package Manager, from 
    the existing package classification lines.
 
    See bug #4483 for more details.
 
    Usage:
      $ cd .../gate/src/util/distro-import
      $ python gen_os_file.py
 
    By default, it will automatically overwrite:
      ../../gui/data/opensolaris.org   and
      ../../gui/data/opensolaris.org.sections
    in the pkg source workspace.
 
    It is expected that this will be run (typically using the 
    "make guiclassification" target in the Makefile), as part of the 
    preparation for turning a new WOS build into a new OpenSolaris 
    development release. In other words, the new versions of 
    "opensolaris.org" and "opensolaris.org.sections" will be checked 
    in as part of that update.
    """

    def __init__(self):
        """Creates a new instance of the GenOSFiles class.
        """

        self.prefix = "."     # Directory prefix for finding files.

        self.debug = False    # Whether to output debug messages to stderr.

        # Name of the file containing package categories.
        #
        self.os_cat_name = "../../gui/data/opensolaris.org.sections"

        # Name of the file containing package subcategories.
        #
        self.os_subcat_name = "../../gui/data/opensolaris.org"

        # Dictionary of packages found.
        #
        self.packages = {}

        # Number of different packages found.
        #
        self.package_count = 0

    def do_classification(self, pathname, line):
        """Extract category and subcategory values. Add package
        classification info to the dictionary of packages. If any
        entry already exists, replace it, if this info is for a newer
        build number.
        """

        tokens = line.split(None, 1)[1].strip('"').split("/")
        if len(tokens) != 2:
            message = "**** Malformed classification line: %s:\n" % line
            sys.stderr.write(message)
            return

        category = tokens[0]
        sub_category = tokens[1]
        if self.debug:
            sys.stderr.write("category: %s\n" % category)
            sys.stderr.write("sub_category: %s\n" % sub_category)

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
            old_sub_category = sub_category

            if category == "Desktop (GNOME)" and \
               sub_category == "Localizations":
                sub_category = "Localizations (Desktop)"

            elif category == "System" and sub_category == "Databases":
                sub_category = "Databases (System)"

            elif category == "System" and sub_category == "Libraries":
                sub_category = "Libraries (System)"

            elif category == "System" and sub_category == "Localizations":
                sub_category = "Localizations (System)"

            elif category == "System" and sub_category == "X11":
                sub_category = "X11 (System)"

            if self.debug:
                if old_sub_category != sub_category:
                    sys.stderr.write("CHANGED: sub_category: %s\n" %
                                     sub_category)

            if len(sub_category) == 0:
                message = "**** Package %s: empty sub-category\n" % \
                          self.package_name
                sys.stderr.write(message)
                return

            tokens = pathname[len(self.prefix):-1].split("/")
            if self.debug:
                sys.stderr.write("tokens[0]: %s\n" % tokens[0])

            try:
                new_build_no = int(tokens[0])
            except ValueError:
                try:
                    new_build_no = int(tokens[0][:-1])
                except ValueError:
                    new_build_no = 0   # For unbundleds files.

            # If we already have a dictionary entry for this
            # package, check to see if this one is for a newer
            # build.
            #
            if self.package_name in self.packages:
                build_no, old_category, old_sub_category = \
                    self.packages[self.package_name]

                if self.debug:
                    sys.stderr.write("*** EXISTS: %s\n" %
                                     self.package_name)
                    sys.stderr.write("OLD: %d NEW: %d\n" %
                                     (build_no, new_build_no))

                if new_build_no > build_no:
                    if self.debug:
                        sys.stderr.write("NEW: %s (%d) %s\n" %
                            (self.package_name, new_build_no, sub_category))

                    self.packages[self.package_name] = \
                        [new_build_no, category, sub_category]

            else:
                self.packages[self.package_name] = \
                    [new_build_no, category, sub_category]
                self.package_count += 1

        else:
            message = \
                "**** Classification (%s) with no package name in %s" % \
                    (line[:-1], pathname)
            sys.stderr.write(message)

        self.package_name = None

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
        for line in lines:
            if line.startswith("package"):
                tokens = line.split()
                try:
                    self.package_name = tokens[1]
                    if self.debug:
                        sys.stderr.write("Package name: %s\n" %
                                         self.package_name)
                except IndexError:
                    pass

            elif line.startswith("classification"):
                self.do_classification(pathname, line.rstrip())

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
      package category values to.

-s, --subcategory=subcategory-file-name
      Specify an alternate file name to write out the
      package sub-category values to.""")

        sys.exit(2)

    def write_cat_file(self):
        """Sort the dictionary keys (package names) and write out the
        category information to the category file.
        """

        categories = {}
        for key in sorted(self.packages.keys()):
            build_no, category, sub_category = self.packages[key]

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

    def write_subcat_file(self):
        """Sort the dictionary keys (package names) and write out the
        sub-category information to the sub-category file.
        """

        fout = open(self.os_subcat_name, 'w')
        for key in sorted(self.packages.keys()):
            build_no, category, sub_category = self.packages[key]
            fout.write("[%s]\ncategory = %s\n\n" % (key, sub_category))
        fout.close()

    def main(self):
        """Read command line options, find a list of all files (as
        opposed to directories) under the prefix directory, and for
        each one, call extract_info to get category, subcategory 
        and build number. Finally create new versions of the new
        GUI classification files.
        """

        try:
            opts, args = getopt.getopt(sys.argv[1:], "c:dhs:",
                      ["category=", "debug", "help", "subcategory="])
        except getopt.GetoptError, e:
            self.usage(_("Illegal option -- %s") % e.opt)

        for opt, val in opts:
            if opt in ("-c", "--category"):
                self.os_cat_name = val.strip()
            if opt in ("-d", "--debug"):
                self.debug = True
            if opt in ("-h", "--help"):
                self.usage()
            if opt in ("-s", "--subcategory"):
                self.os_subcat_name = val.strip()

        cmd = 'find %s -type f -print' % self.prefix
        lines = os.popen(cmd).readlines()
        for package_file in lines:
            self.extract_info(package_file[:-1])

        if self.debug:
            sys.stderr.write("Number of classified packages: %d\n" %
                             self.package_count)
            sys.stderr.write("Number of keys: %d\n" %
                             len(self.packages.keys()))

        self.write_subcat_file()
        self.write_cat_file()

        return 0

if __name__ == "__main__":
    gen_files = GenOSFiles()
    sys.exit(gen_files.main())
