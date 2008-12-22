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
# check_classifications.py - check for valid package classifications.
#

import gettext
import getopt
import os
import sys

# Alias gettext.gettext to _
_ = gettext.gettext

class CheckClassifications(object):
    """Simple script to list all the packages in the current preferred
    repository, then for each one, check that it has a valid classification.

    Usage:
      $ cd .../gate/src/util/distro-import
      $ python check_classifications.py > classification_report.txt

    Note that this script is slow. It does an initial:

      $ pfexec pkg list -a

    to get a list of all the "latest" packages in the current authority.
    Then for each one, it'll  do:

      $ pfexec pkg info -r <package_name>

    and extract out the "Category:" and "Size:" lines. It then performs
    the following checks:

    1/ If it's not a valid category or sub_category it flags it.
    2/ If the package has no "Category:" line and it's not empty,
       then it flags it. 
    3/ If the package has a "Category:" line and it's empty, then it flags it.

    Flagged output lines start with "***".

    If you want to check the classifications for a repository that is not
    the current authority, then you will need to do:

      $ pfexec pkg set-authority -P -O http://new.authority.org new-authority
      $ python check_classifications.py > classification_output.txt
      $ pfexec pkg set-authority -P old-authority
      $ pfexec pkg unset-authority new-authority 

    """

    def __init__(self):
        """Creates a new instance of the CheckClassifications class."""

        self.verbose = True     # Whether to output verbose messages

        # Dictionary of valid categories / sub-categories.
        self.categories = {}
        self.init_categories()

        # This script currently requires a version of pkg > OpenSolaris
        # 2008.11 RC1 in order to get the Category information when doing
        # a "pkg info -r <package_name>
        # If you have an older version of pkg, then you'll need to specify
        # the location of a pkg prototype directory. If this is present,
        #  then the script will automatically create pkg commands that will
        # work from that proto directory.
        self.proto_dir = None

        # To make pylint happy.
        self.pkg_cmd = None
        self.pkg_dir = None

    def init_categories(self):
        """Initialize a dictionary of valid categories / sub-categories.
        The categories are the keys and the sub-categories are a list
        of valid sub-categories for that category).
        """

        self.categories["Applications"] = [
            "Accessories",
            "Panels and Applets",
            "Configuration and Preferences",
            "Games",
            "Graphics and Imaging",
            "Internet",
            "Office",
            "Plug-ins and Run-times",
            "Sound and Video",
            "System Utilities",
            "Universal Access"
        ]

        self.categories["Desktop (GNOME)"] = [
            "Documentation",
            "File Managers",
            "Libraries",
            "Localizations",
            "Scripts",
            "Sessions",
            "Theming",
            "Trusted Extensions",
            "Window Managers"
        ]

        self.categories["Development"] = [
            "C",
            "C++",
            "Databases",
            "Distribution Tools",
            "GNOME and GTK+",
            "GNU",
            "Integrated Development Environments",
            "Java",
            "Other Languages",
            "PHP",
            "Perl",
            "Python",
            "Ruby",
            "Source Code Management",
            "System",
            "X11"
        ]

        self.categories["Distributions"] = [
            "Desktop"
        ]

        self.categories["Drivers"] = [
            "Display",
            "Media",
            "Networking",
            "Other Peripherals",
            "Ports",
            "Storage"
        ]

        self.categories["System"] = [
            "Administration and Configuration",
            "Core",
            "Databases",
            "Enterprise Management",
            "File System",
            "Fonts",
            "Hardware",
            "High Performance Computing",
            "Internationalization",
            "Libraries",
            "Localizations",
            "Media",
            "Multimedia Libraries",
            "Packaging",
            "Printing",
            "Security",
            "Services",
            "Shells",
            "Software Management",
            "Text Tools",
            "Trusted",
            "Virtualization",
            "X11"
        ]

        self.categories["Web Services"] = [
            "Application and Web Servers"
        ]


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
      check_classifications [OPTION...]

-h, --help
      Show this help message

-p, --proto_dir=prototype-directory
      Specify a directory containing an installed prototype of pkg and
      all the files it requires.

-v, --verbose
      Turn on verbose output.""")

        sys.exit(2)

    def main(self):
        try:
            opts, args = getopt.getopt(sys.argv[1:], "hp:v",
                      ["help", "proto_dir=", "verbose"])
        except getopt.GetoptError, e:
            self.usage(_("Illegal option -- %s") % e.opt)

        for opt, val in opts:
            if opt in ("-h", "--help"):
                self.usage()
            if opt in ("-p", "--proto_dir"):
                self.proto_dir = val.strip()
                self.pkg_dir = self.proto_dir + \
                    "/usr/lib/python2.4/vendor-packages"
                self.pkg_cmd = self.proto_dir + "/usr/bin/pkg"
            if opt in ("-v", "--verbose"):
                self.verbose = True

        if self.proto_dir:
            os.putenv('PYTHONPATH', self.pkg_dir)
            list_cmd = 'pfexec %s list -a -H' % self.pkg_cmd
        else:
            list_cmd = 'pfexec pkg list -a -H'

        for package_line in os.popen(list_cmd).readlines():
            list_tokens = package_line.split()
            package_name = list_tokens[0]
            if self.verbose:
                print "Package: %s" % package_name

            category = None
            size = ""

            if self.proto_dir:
                os.putenv('PYTHONPATH', self.pkg_dir)
                info_cmd = 'pfexec %s info -r %s' % (self.pkg_cmd, package_name)
            else:
                info_cmd = 'pfexec pkg info -r %s' % package_name

            for info_line in os.popen(info_cmd).readlines():
                info_tokens = info_line.split(":")
                if info_tokens[0].strip() == "Category":
                    category, sub_category = \
                        info_tokens[1].strip().split("/", 1)
                    if self.verbose:
                        print "Category: %s/%s" % (category, sub_category)

                    if category not in self.categories:
                        print _("***Package: %s\tCategory: %s not found.") % \
                            (package_name, category)
                        break

                    sub_categories = self.categories[category]
                    if sub_category not in sub_categories:
                        print _("***Package: %s\tSub_category: %s not found.") \
                            % (package_name, sub_category)
                        break
                if info_tokens[0].strip() == "Size":
                    size = info_tokens[1].strip()
                    if self.verbose:
                        print "Size: %s" % size

            # If no Category information was found and the package isn't empty
            # then flag it.
            if not category and size != "0.00 B":
                print _("***Package: %s has no classification.") % package_name

            # If there is a "Category:" line but the package is empty, then
            # flag it.
            #
            if category and size == "0.00 B":
                print _("***Package: %s has classification but is empty.") % \
                    package_name

if __name__ == "__main__":
    check_classifications = CheckClassifications()
    sys.exit(check_classifications.main())
