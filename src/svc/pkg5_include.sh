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
#
# Copyright (c) 2008, 2013 Oracle and/or its affiliates.  All rights reserved.
#

CP=/usr/bin/cp
CRONTAB=/usr/bin/crontab
DIFF=/usr/bin/diff
GREP=/usr/bin/grep
ID=/usr/bin/id
MKDIR=/usr/bin/mkdir
RM=/usr/bin/rm
RMDIR=/usr/bin/rmdir
SLEEP=/usr/bin/sleep
SVCADM=/usr/sbin/svcadm
SVCPROP=/usr/bin/svcprop

#
# Check whether the supplied exit code is 0, printing an error message
# if it is not, optionally either disabling an FMRI or exiting.
#
# Usage:
# check_failure \
#     <int exit status>  <error message> <fmri> <mode>
#
function check_failure {

	typeset RESULT=$1
	typeset ERR_MSG=$2
	typeset FMRI=$3
	typeset MODE=$4

	if [ $RESULT -ne 0 ] ; then
		echo "Error: $ERR_MSG"
		if [ "$MODE" = "degrade" ] ; then
			echo "Moving service $FMRI to maintenance mode."
			$SVCADM mark maintenance $FMRI
		elif [ "$MODE" = "exit" ] ; then
			exit 1
		fi
	fi
	return $RESULT
}

#
# Attempt to acquire a pkg5-private lock on the current users crontab.
# Note that this only protects crontab from multiple callers using
# this function, this isn't a generic locking mechanism for cron.
#
function acquire_crontab_lock {
	LOCK_OWNED="false"
	UID=$($ID -u)
	while [ "$LOCK_OWNED" == "false" ]; do
		$MKDIR /tmp/pkg5-crontab-lock.$UID > /dev/null 2>&1
		if [ $? -eq 0 ]; then
			LOCK_OWNED=true
		else
			$SLEEP 0.1
		fi
	done
}

function release_crontab_lock {
	UID=$($ID -u)
	$RMDIR /tmp/pkg5-crontab-lock.${UID}
}

#
# Update cron with a new crontab file.  We pass what we expect the
# current crontab looks like in order to verify that the content hasn't
# changed since we made our modifications.  Note that between the time
# we check for crontab modifications, and the time we apply the new
# crontab entries, another program could have altered the crontab entry,
# this is unfortunate, but unlikely.
#
# Usage:
#  update_crontab <current crontab> <new crontab>
#
function update_crontab {

	typeset CURRENT_CRONTAB=$1
	typeset NEW_CRONTAB=$2
	EXIT=0
	CRONTAB_LOCKDIR=/tmp/pkg5-crontab-lock.$UID

	$CRONTAB -l > $CRONTAB_LOCKDIR/actual-crontab.$$
	$DIFF $CRONTAB_LOCKDIR/actual-crontab.$$ - \
	    < $CURRENT_CRONTAB 2>&1 \
	    >  /dev/null
	if [ $? == 0 ]; then
		$CRONTAB $NEW_CRONTAB
		EXIT=$?
	else
		echo "Crontab file was modified unexpectedly!"
		EXIT=1
	fi
	$RM $CRONTAB_LOCKDIR/actual-crontab.$$
	return $EXIT
}

#
# Add a cron job to the current users crontab entry, passing the FMRI
# we're doing work for, the cron schedule (the first 5 fields of the
# crontab entry) and the command we'd like to run.
# We perform primitive locking around cron to protect this function from
# multiple processes.
#
# This function assumes only a single occurrence of a given command is
# valid in a crontab entry: multiple instances of the same command with
# the same arguments, but with different schedules are not allowed.
#
# Usage:
# add_cronjob <fmri> <schedule> <cmd>
#
function add_cronjob {

	typeset FMRI=$1
	typeset SCHEDULE=$2
	typeset CMD=$3

	UID=$($ID -u)
	CRONTAB_LOCKDIR=/tmp/pkg5-crontab-lock.$UID

	typeset new_crontab=$CRONTAB_LOCKDIR/pkg5-new-crontab.$$
	typeset current_crontab=$CRONTAB_LOCKDIR/pkg5-current-crontab.$$

	#
	# adding a cron job is essentially just looking for an existing
	# entry, removing it, and appending a new one.
	#
	acquire_crontab_lock
	$CRONTAB -l > $current_crontab
	EXIT=0
	# if the crontab doesn't already contain our command, add it
	$GREP -q "^[0-9, \*]+ $CMD"$ $current_crontab
	if [ $? -ne 0 ]; then
		$GREP -v " ${CMD}"$ $current_crontab > $new_crontab
		echo "$SCHEDULE $CMD" >> $new_crontab

		update_crontab $current_crontab $new_crontab
		EXIT=$?
		$RM $new_crontab
	fi
	$RM $current_crontab
	release_crontab_lock

	return $EXIT
}

#
# Remove a cron job from the current users crontab entry. We pass the
# FMRI we're doing work for, and the command we wish to remove from
# the crontab. If the the command does not exist in the crontab, this
# is treated as an error. Note that all instances of a given command
# are removed.
#
# Usage:
# remove_cronjob <fmri> <cmd>
#
function remove_cronjob {

	typeset fmri=$1
	typeset cmd=$2

	UID=$($ID -u)
	CRONTAB_LOCKDIR=/tmp/pkg5-crontab-lock.$UID
	new_crontab=$CRONTAB_LOCKDIR/pkg5-new-crontab.$$
	current_crontab=$CRONTAB_LOCKDIR/pkg5-current-crontab.$$

	acquire_crontab_lock
	$CRONTAB -l > $current_crontab
	$GREP "${cmd}" $current_crontab > /dev/null 2>&1
	check_failure $? "command $cmd did not exist in crontab" $fmri \
	    degrade

	$GREP -v "${cmd}" $current_crontab > $new_crontab

	update_crontab $current_crontab $new_crontab
	EXIT=$?

	$RM $current_crontab $new_crontab
	release_crontab_lock

	return $EXIT
}
