#!/usr/bin/bash

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
# Copyright (c) 2017, Oracle and/or its affiliates. All rights reserved.
#

bindir=${0%/*}
progname=${0##*/}

function usage
{
	printf "usage: $progname journal\n" >&2
	exit 1
}

while getopts ":" OPTION ; do
	case $OPTION in
	    *) usage ;;
	esac
done

if (( $# != 1 )) ; then
	usage
fi

log="$1"

echo "Test summary:"
echo ""
egrep "^/usr/bin/python.* tests|tests in|FAILED" ${log}
echo ""

echo "Baseline summary:"
echo ""
# extract text between "^BASELINE MISMATCH" and "Target .* not remade"
nawk '
    /^BASELINE MISMATCH/, /Target .* not remade/
    /Target .* not remade/ {print ""}
' ${log}

exit 0
