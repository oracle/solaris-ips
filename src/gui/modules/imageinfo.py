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

import ConfigParser
import re
import sys
import os
from ConfigParser import ParsingError

class ImageInfo(object):
        """An ImagineInfo object is a collection of information
        about the packages for the Imagine GUI"""

        def __init__(self):
                self.categories = {}

        def read(self, path):
                """This method reads specified by path file and returns lists of 
                categories per package"""
                cp = self.get_config_parser(path)
                if cp:
                        for s in cp.sections():
                                self.categories[s] = cp.get(s, "category")
                return self.categories

        def get_pixbuf_image_for_package(self, path, packageName):
                """Method that returns pixbuf field from the file specified by path for
                the given packageName"""
                cp = self.get_config_parser(path)
                if cp:
                        for s in cp.sections():
                                if re.match(packageName, s):
                                        pixbuf = cp.get(s, "pixbuf")
                                        return pixbuf
                return None

        def add_package(self, path, name, category):
                """Add the package information to the file specified by the path. If the 
                package name already exists, than returns False"""
                cp = self.get_config_parser(path)
                if cp:
                        for s in cp.sections():
                                if re.match(name, s):
                                #This should behave differently, if the repo 
                                #exists should throw some error
                                        return False
                        cp.add_section(name)
                        cp.set(name, "category", category)
                        f = open(path, "w")
                        cp.write(f)
                        return True
                return False

        def remove_package(self, path, name):
                """If exists removes package specified by name from the filename specified 
                by path"""
                cp = self.get_config_parser(path)
                if cp:
                        for s in cp.sections():
                                if re.match(name, s):
                                        cp.remove_section(name)
                                        f = open(path, "w")
                                        cp.write(f)

        def get_config_parser(self, path):
                """Creates and returns ConfigParser.SafeConfigParser()"""
                cp = ConfigParser.SafeConfigParser()
                if cp:
                        if not os.path.isfile(path):
                                print "File: " + str(path) + " not found."
                        r = cp.read(path)
                        if r:
                                if r[0] != path:
                                        raise ParsingError
                                return cp

        def mkdirs_files(self, path):
                if not os.path.isdir(os.path.dirname(path)):
                        os.makedirs(os.path.dirname(path))
                if not os.path.isfile(path):
                        f = open(path, "w")
                        f.close()

if __name__ == "__main__":
        print "Usage:"
        print "./imageinfo.py FILE..."
        sys.exit(0)
