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

import time
import os

class UserRights:
        """The installation rights specifies if the client is acting in user or
        administrative mode. The user mode allows to create user images and 
        but should only work if the user have write access to the folder where
        the image is beying placed. Administrative mode allows to make all 
        actions on all images"""

        def __init__(self):
                pass

        def check_administrative_rights(self):
                """Returns True if user have administrative rights, False if not"""
                system = self.check_platform()
                if system == "Solaris":
                        try:
                                #Check if root
                                if os.geteuid() == 0:
                                        return True
                                else:
                                        return False
                        except OSError:
                                return False
                elif system == "Linux":
                        try:
                        #Check if root
                                if os.geteuid() == 0:
                                        return True
                                else:
                                        return False
                        except OSError:
                                return False
                elif system == "Windows":
                        return False
                elif system == "MacOS":
                        return False
                else:
                        return False

        def check_platform(self):
                """Returns a string representation of the platform, currently: Solaris,
                Linux, Windows and MacOS are recognized. If the system is not recognized
                returns Unknown"""
                system = os.uname()[0]
                if system == "SunOS":
                        return "Solaris"
                elif system == "Linux":
                        return "Linux"
                elif system in ("win32", "win16", "Windows"):
                        return "Windows"
                elif system == "MacOS":
                        return "MacOS"
                else:
                        return "Unknown"

if __name__ == '__main__':
        rights = UserRights()
        system = rights.check_platform()
        haverights = rights.check_administrative_rights()
        print "Discovered Operating System: %s" % system
        print "User have administrative rights?: %s" % haverights
