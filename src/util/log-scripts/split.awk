#!/usr/bin/nawk -f
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

BEGIN {
	if (ARGC < 2) {
		print ARGC
		exit 2
	}

	timestamp = ARGV[1]
	delete ARGV[1]
}

		
/ \/1p.png/ {
	print $0 >> ("raw.ping." timestamp)
}

/ \/catalog\/0/ {
	print $0 >> ("raw.catalog." timestamp)
}

/ \/filelist/ {
	print $0 >> ("raw.filelist." timestamp)
}

/ \/manifest/ {
	print $0 >> ("raw.manifest." timestamp)
}

/ \/search/ {
	print $0 >> ("raw.search." timestamp)
}

END {
	printf("%d lines processed.", NR)
}
