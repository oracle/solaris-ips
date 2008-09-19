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

"""
Most of the generic unix methods of our superclass can be used on
Solaris. For the following methods, there is a Solaris-specific
implementation in the 'arch' extension module.
"""

from os_unix import \
    get_group_by_name, get_user_by_name, get_name_by_gid, get_name_by_uid, \
    is_admin, get_userid, get_username, chown, rename, remove, link, \
    copyfile, split_path, get_root
import pkg.arch as arch

def get_isainfo():
        return arch.get_isainfo()

def get_release():
        return arch.get_release()

def get_platform():
        return arch.get_platform()
