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

eval `pkgsend open test/preserve/A@0.1-1`
if [ $? != 0 ]; then
	echo \*\* script aborted:  couldn\'t open test/preserve/A
	exit 1
fi

echo "This is the old version" > /tmp/test1

echo $PKG_TRANS_ID
pkgsend add dir  0755 root sys /bin
pkgsend add file 0644 root sys /bin/test1 /tmp/test1 preserve=renamenew
pkgsend add file 0644 root sys /bin/test2 /tmp/test1 preserve=renameold
pkgsend add file 0644 root sys /bin/test3 /tmp/test1 preserve=true
pkgsend close

eval `pkgsend open test/preserve/A@0.2-1`
if [ $? != 0 ]; then
	echo \*\* script aborted:  couldn\'t open test/preserve/A
	exit 1
fi

echo "This is the new version" > /tmp/test1

echo $PKG_TRANS_ID
pkgsend add dir  0755 root sys /bin
pkgsend add file 0644 root sys /bin/test1 /tmp/test1 preserve=renamenew
pkgsend add file 0644 root sys /bin/test2 /tmp/test1 preserve=renameold
pkgsend add file 0644 root sys /bin/test3 /tmp/test1 preserve=true
pkgsend close

rm /tmp/test1
