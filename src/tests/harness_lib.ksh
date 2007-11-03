#!/bin/ksh -p
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
# fields enclosed by brackets "[[]]" replaced with your own identifying
# information: Portions Copyright [[yyyy]] [name of copyright owner]
#
# CDDL HEADER END
#

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

depot_start () {
	print -u2 "Redirecting all repository logging to stdout"
	$ROOT/usr/lib/pkg.depotd -p $REPO_PORT -d $REPO_DIR 2>&1 &
	DEPOT_PID=$!
	sleep 1
}

depot_cleanup () {
	kill $DEPOT_PID
	sleep 1
	if ps -p $DEPOT_PID > /dev/null; then
		kill -9 $DEPOT_PID
	fi
	rm -fr $REPO_DIR
	exit $1
}

image_cleanup () {
	cd $restore_dir
	rm -fr $IMAGE_DIR
}

tcase=0
tassert=
tassert_errors=0
ttest="unknown"
tdid_fail=
texpect_falure=

new_assert() {
	if [ -z "$*" ]; then
		print -u2 "assert must have an description"
		exit 1
	fi
	tassert="$*"
        ttest="unknown"
	tassert_errors=0
}

new_test() {
	ttest="$*"
	texpect_falure=
	tdid_fail=
}

end_assert () {
	if [ $tassert_errors -eq 0 ]; then
		print -u2 "PASS $tcase: $tassert"
	else
		print -u2 "KNOWNBUGS $tcase: passed, but with" \
		    "$tassert_errors known failures. ($tassert)"
	fi

	tassert_errors=0
	tcase=`expr "$tcase" "+" "1"`
	tassert=
	tdid_fail=
        texpect_failure=
}

begin_expect_test_fails() {
	if [ -z "$*" ]; then
		print -u2 "begin_expect_test_fails must have a bugid"
		exit 1
	fi

	print -u2 "*** Expecting test failure due to bugid $1"
	texpect_failure=$1		
}

end_expect_test_fails() {
	if [ -z "$texpect_failure" ]; then
		print -u2 "*** in end_expect_test_fails, but" \
		    "begin_expect_test_fails was not called"
		print -u2 "*** Aborting test suite"
		exit 1
	fi
	if [ -z "$tdid_fail" ]; then
		print -u2 "*** Expecting failure, but test did not fail!"
		print -u2 "*** Aborting test suite"
		exit 1
	fi
	print -u2 "*** Saw expected failure due to bug # $texpect_failure"
	texpect_failure=
	tdid_fail=
}

fail () {
	if [ -n "$@" ]; then
		print -u2 "*** case $tcase: $@"
	else
		print -u2 "*** case $tcase"
	fi

	if [ -z $AOK -a -z $texpect_failure ]; then
		# The exit trap handler will print the assert
		# and sub-assert for us.
		exit 1
	fi

	print -u2 "*** FAILED ASSERT: $tassert"
	print -u2 "*** SUB-ASSERT: $ttest"

	if [ -n "$texpect_failure" ]; then
		print -u2 "*** failed [bug # $texpect_failure]"
	fi
	if [ -n "$AOK" ]; then
		print -u2 "*** continuing, AOK was set"
	fi
	tdid_fail=1
	tassert_errors=`expr "$tassert_errors" "+" "1"`
}

expect_exit() {
	if [ $1 != $2 ]; then
		fail "expected exit status: $1, saw $2.  $3"
	fi
}

died () {
	if [[ -n "$tassert" ]]; then
		print -u2 "*** FAILED ASSERT: $tassert"
		print -u2 "*** SUB-ASSERT: $ttest"
		print -u2 "*** trapped"
	fi
}
