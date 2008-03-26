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
import os
import platform
import re

def get_canonical_os_type():
        """ 
        Return a standardized, lower case version of the "type" of OS family.
        """
        if os.name == 'posix':
                return 'unix'
        elif os.name == 'mac':
                # Note that darwin systems return 'posix'.  This is for pre-darwin
                return 'mac'
        elif os.name == 'nt':
                return 'windows'
        else:
                return 'unknown'

def get_canonical_os_name():
        """
        Return a standardized, lower case version of the name of the OS.  This is
        useful to avoid the ambiguity of OS marketing names.  
        """
        
        if platform.system().lower() == 'sunos':
                return 'sunos'
        elif platform.system().lower() == 'linux':
                return 'linux'
        elif platform.system().lower() == 'darwin':
                return 'darwin'
        # Workaround for python bug 1082, on Vista, platform.system()
        # returns 'Microsoft'
        elif platform.system().lower() == 'microsoft' or \
                platform.release().lower() == 'vista':
                return 'winvista'
        elif platform.release().lower() == 'xp':
                return 'winxp'
        elif platform.release().lower() == '95':
                return 'win95'
        elif platform.release().lower() == '98':
                return 'win98'
        elif platform.release().lower().find('2003') != -1:
                return 'win2003'
        elif platform.release().lower().find('2000') != -1:
                return 'win2000'
        else:
                return 'unknown'

def get_os_release():
        """
        Return a standardized, sanitized version string, consisting of a
        dot-separated list of integers representing the release version of
        this OS. 
        """
        
        ostype = get_canonical_os_type()
        release = None
        if ostype == 'unix':
                release = os.uname()[2]
        elif ostype == 'windows':
                # Windows has no os.uname, and platform.release
                # gives you things like "XP" and "Vista"
                release = platform.version()
        else:
                release = platform.release()

        # force release into a dot-separated list of integers
        return '.'.join((re.sub('[^0-9]', ' ', release)).split())


