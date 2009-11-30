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
                cpars = self.__get_config_parser(path)
                if cpars:
                        for section in cpars.sections():
                                self.categories[section] = cpars.get(section, "category")
                return self.categories

        def get_pixbuf_image_for_package(self, path, package_name):
                """Method that returns pixbuf field from the file specified by path for
                the given package_name"""
                cpars = self.__get_config_parser(path)
                if cpars:
                        for section in cpars.sections():
                                if re.match(package_name, section):
                                        pixbuf = cpars.get(section, "pixbuf")
                                        return pixbuf
                return None

        def add_package(self, path, name, category):
                """Add the package information to the file specified by the path. If the 
                package name already exists, than returns False"""
                cpars = self.__get_config_parser(path)
                if cpars:
                        for section in cpars.sections():
                                if re.match(name, section):
                                #This should behave differently, if the repo 
                                #exists should throw some error
                                        return False
                        cpars.add_section(name)
                        cpars.set(name, "category", category)
                        file_op = open(path, "w")
                        cpars.write(file_op)
                        return True
                return False

        def remove_package(self, path, name):
                """If exists removes package specified by name from the 
                filename specified by path"""
                cpars = self.__get_config_parser(path)
                if cpars:
                        for section in cpars.sections():
                                if re.match(name, section):
                                        cpars.remove_section(name)
                                        file_op = open(path, "w")
                                        cpars.write(file_op)

        @staticmethod 
        def __get_config_parser(path):
                """Creates and returns ConfigParser.SafeConfigParser()"""
                cpars = ConfigParser.SafeConfigParser()
                if cpars:
                        read_cp = cpars.read(path)
                        if read_cp:
                                if read_cp[0] != path:
                                        raise ParsingError
                                return cpars

        @staticmethod
        def __mkdirs_files(path):
                if not os.path.isdir(os.path.dirname(path)):
                        os.makedirs(os.path.dirname(path))
                if not os.path.isfile(path):
                        file_op = open(path, "w")
                        file_op.close()

if __name__ == "__main__":
        print "Usage:"
        print "./imageinfo.py FILE..."
        sys.exit(0)
