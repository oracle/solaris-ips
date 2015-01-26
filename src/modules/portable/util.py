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
#
# Copyright (c) 2008, 2015, Oracle and/or its affiliates. All rights reserved.
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
        
        psl = platform.system().lower()
        if psl in ['sunos', 'darwin', 'windows', 'aix']:
                return psl

        if psl == 'linux':
                # add distro information for Linux
                return 'linux_{0}'.format(platform.dist()[0])

        # Workaround for python bug 1082, on Vista, platform.system()
        # returns 'Microsoft'
        prl = platform.release().lower()
        if psl == 'microsoft' or prl == 'vista' or prl == 'windows':
                return 'windows'

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


