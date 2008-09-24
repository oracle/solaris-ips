#!/bin/ksh -px
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

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

eval `pkgsend open test/upgrade/A@0.1-1`
if [ $? != 0 ]; then
	echo \*\* script aborted:  couldn\'t open test/upgrade/A
	exit 1
fi

echo "version 1 of /bin/change" > /tmp/change
echo "version 1 of /bin/nochange" > /tmp/nochange

echo $PKG_TRANS_ID
pkgsend add dir  mode=0755 owner=root group=sys path=/bin
pkgsend add file /tmp/change mode=0644 owner=root group=sys path=/bin/change
pkgsend add file /tmp/nochange mode=0644 owner=root group=sys path=/bin/nochange
pkgsend add file /dev/null mode=0644 owner=root group=sys path=/bin/toberemoved
pkgsend add file /dev/null mode=0755 owner=root group=sys path=/bin/attributechangeonly
pkgsend add link path=/bin/change-link target=change
pkgsend add link path=/bin/nochange-link target=nochange
pkgsend add link path=/bin/change-target target=target1
pkgsend add link path=/bin/change-type target=random
pkgsend close

eval `pkgsend open test/upgrade/A@0.2-1`
if [ $? != 0 ]; then
	echo \*\* script aborted:  couldn\'t open test/upgrade/A
	exit 1
fi

echo "version 2 of /bin/change" > /tmp/change

echo $PKG_TRANS_ID
pkgsend add dir  mode=0755 owner=root group=sys path=/bin
pkgsend add file /tmp/change mode=0644 owner=root group=sys path=/bin/change
pkgsend add file /tmp/nochange mode=0644 owner=root group=sys path=/bin/nochange
pkgsend add file /dev/null mode=0644 owner=root group=sys path=/bin/wasadded
pkgsend add file /dev/null mode=0444 owner=root group=sys path=/bin/attributechangeonly
pkgsend add link path=/bin/change-link target=change
pkgsend add link path=/bin/nochange-link target=nochange
pkgsend add link path=/bin/change-target target=target2
pkgsend add dir  mode=0755 owner=root group=sys path=/bin/change-type
pkgsend close

rm /tmp/change /tmp/nochange
