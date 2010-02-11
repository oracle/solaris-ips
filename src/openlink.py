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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import sys
import pwd
import os
try:
        import gobject
        import gnome
except ImportError:
        sys.exit(1)

if __name__ == '__main__':
        if len(sys.argv) != 3:
                sys.exit(1)
        name = sys.argv[1]
        link = sys.argv[2]
        try:
                pw = pwd.getpwnam(name)
                if pwd:
                        uid = pw.pw_uid
                        pw_dir = pw.pw_dir
                        os.putenv('HOME', pw_dir)
                        os.setreuid(uid, uid)
                        os.setuid(uid)
                        try:
                                gnome.url_show(link)
                        except gobject.GError:
                                sys.exit(1)
                        sys.exit(0)
                else:
                        sys.exit(1)
        except OSError:
                sys.exit(1)
