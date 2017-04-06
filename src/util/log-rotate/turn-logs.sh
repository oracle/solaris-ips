#!/bin/ksh93
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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.

#
# This relatively basic script looks for pkg(7) depot server instances
# in the smf repository, and invokes logadm to roll their logs in
# $CHUNKSIZE chunks.  It is intended to be run from cron.  For example:
#
#    $ crontab -l root
#    ...
#    # Rotate the logs every hour
#    0 * * * * /site/cron/turn-logs.sh -e pkg@example.com
#

CHUNKSIZE=25m

usage() {
	print -u 2 "Usage: $0 [-e <email address>]"
	exit 2
}

fail() {
	print -u 2 "Error: $*"
	exit 1
}

while getopts "e:" opt; do
	case $opt in
		e)	LOGADM_EMAIL="-e $OPTARG";;
		?)	usage;;
	esac
done

LOGS=$(svcprop -c -p pkg/log_access -p pkg/log_errors pkg/server |
    awk '{print $3}' | egrep -v '^(none|stderr|stdout)$')

for log in $LOGS; do
	cd /
	if [[ ! -f $log ]]; then
		print -u 2 "failed to find log $log, skipping."
		continue
	fi
	logfile=$(basename $log)
	logdir=$(dirname $log)
	datestr=$(TZ=UTC date '+%Y-%m-%dT%H:%M:%SZ')
	[[ -n $logfile && -n $logdir && -n $datestr ]] || fail "failed set up"
	cd $logdir || fail "could not cd $logdir"
	logadm $LOGADM_EMAIL -s $CHUNKSIZE -t \$file.$datestr -c $logfile
done
