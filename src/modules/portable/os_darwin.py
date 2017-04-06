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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

"""
Most if not all of the os_unix methods apply on Darwin. The methods
below override the definitions from os_unix
"""

from .os_unix import \
    get_isainfo, get_release, get_platform, get_group_by_name, \
    get_user_by_name, get_name_by_gid, get_name_by_uid, get_usernames_by_gid, \
    is_admin, get_userid, get_username, chown, rename, remove, link, \
    split_path, get_root, assert_mode

import macostools

def copyfile(src, dst):
        """
        Use the Mac OS X-specific version of copyfile() so that
        Mac OS X stuff gets handled properly.
        """
        macostools.copy(src, dst)

