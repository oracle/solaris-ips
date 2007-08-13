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
pkgsend add dir  0755 root sys /bin
pkgsend add file 0644 root sys /bin/change /tmp/change
pkgsend add file 0644 root sys /bin/nochange /tmp/nochange
pkgsend add file 0644 root sys /bin/toberemoved /dev/null
pkgsend add file 0755 root sys /bin/attributechangeonly /dev/null
pkgsend add link /bin/change-link change
pkgsend add link /bin/nochange-link nochange
pkgsend add link /bin/change-target target1
pkgsend add link /bin/change-type random
pkgsend close

eval `pkgsend open test/upgrade/A@0.2-1`
if [ $? != 0 ]; then
	echo \*\* script aborted:  couldn\'t open test/upgrade/A
	exit 1
fi

echo "version 2 of /bin/change" > /tmp/change

echo $PKG_TRANS_ID
pkgsend add dir  0755 root sys /bin
pkgsend add file 0644 root sys /bin/change /tmp/change
pkgsend add file 0644 root sys /bin/nochange /tmp/nochange
pkgsend add file 0644 root sys /bin/wasadded /dev/null
pkgsend add file 0444 root sys /bin/attributechangeonly /dev/null
pkgsend add link /bin/change-link change
pkgsend add link /bin/nochange-link nochange
pkgsend add link /bin/change-target target2
pkgsend add dir  0755 root sys /bin/change-type
pkgsend close

rm /tmp/change /tmp/nochange
