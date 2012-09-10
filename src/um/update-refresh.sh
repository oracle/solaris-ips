#!/bin/ksh
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
# Copyright (c) 2008, 2012, Oracle and/or its affiliates. All rights reserved.
#

#
# This script is run as part of a cron job.
# The cron job is managed by svc:/application/pkg/update:default
#
# It can be disabled by disabling the pkg/update service:
# $ /usr/sbin/svcadm disable svc:/application/pkg/update
#  or 
# By removing the pkg/update-manager package:
# $ pkg uninstall package/pkg/update-manager
#
# The script is a wrapper which refreshes the IPS catalog, then
# calls /usr/lib/pm-checkforupdates to check and cache whether updates
# are available. The generated cache is checked by
# /usr/lib/updatemanagernotifier, which in turn notifies the user
# via a popup and notification panel icon.
#

fmri=svc:/application/pkg/update

#
# We want to limit the number of times we hit the servers, but our
# calculations are all based on the canonical crontab entry.  If the
# user has modified that, then use the times as they specified.
#
cronentry=$(crontab -l | grep update-refresh.sh)
if [[ $cronentry == "30 0,9,12,18,21 * * * "* ]]; then
	# When did we last run, and how many times have we tried since?
	lastrun=$(svcprop -p update/lastrun $fmri 2> /dev/null)

	# Easiest way to get seconds since the epoch.
	now=$(LC_ALL=C /usr/bin/date '+%s')

	# The canonical crontab entry runs this script five times a day,
	# seven days a week.  We want it to complete roughly once a week.
	# But because we're not at 100% after even two weeks, we increase
	# the chance of success every fifth of a day until we're at 100%.
	rolls=$(((now - lastrun) / 17280))
	(( rolls > 34 )) && rolls=34
	chance=$((35 - rolls))
	roll=$((RANDOM % chance))
	(( roll > 0 )) && exit 0

	# Otherwise, we will run, so record the current time for later.
	cat <<-EOF | svccfg -s pkg/update
	setprop update/lastrun = integer: $now
	select default
	refresh
	EOF
fi

# Wait a random part of 30 minutes so servers do not get hit all at once
let dither=1800*$RANDOM
let dither=dither/32767
sleep $dither

image_dir=/
pkg -R $image_dir refresh -q 2>/dev/null

# Check and cache whether updates are available
/usr/lib/pm-checkforupdates --nice
exit 0
