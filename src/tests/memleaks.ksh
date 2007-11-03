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

# memleaks.ksh - basic sanity test for depot; try to make sure it doesn't
# leak.
#

TEMPDIR=${TEMPDIR:-/tmp}
REPO_PORT=${REPO_PORT:-8000}
REPO_DIR=$TEMPDIR/repo.$$
REPO_URL=http://localhost:$REPO_PORT

restore_dir=$PWD

ROOT=$PWD/../../proto/root_$(uname -p)

export PYTHONPATH=$ROOT/usr/lib/python2.4/vendor-packages/
export PATH=$ROOT/usr/bin:$PATH

print -u2 -- \
    "\n--memleaks testing----------------------------------------------------"

. ./harness_lib.ksh

if [[ ! -x /usr/bin/mdb ]]; then
	print -u2 "mdb(1) not available.  No leak checking."
	exit 0
fi

if [[ ! -x /usr/lib/libumem.so ]]; then
	print -u2 "libumem not available.  No leak checking."
	exit 0
fi

print -u2 "Note: set DBG_STOP=1 in your environment to stop for leak debugging"

LD_PRELOAD=libumem.so UMEM_DEBUG=default
export LD_PRELOAD
export UMEM_DEBUG

depot_start
trap "ret=$?; died; image_cleanup; depot_cleanup $ret" EXIT

new_assert "Put some binaries into the server, then findleaks it."
# {{{1

trans_id=$(pkgsend -s $REPO_URL open leaks@1.0,5.11-0)
if [[ $? != 0 ]]; then
	fail pkgsend open failed
fi

eval $trans_id

pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/lib || \
	fail pkgsend add dir failed

pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/usr || \
	fail pkgsend add dir failed

pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/usr/sbin || \
	fail pkgsend add dir failed

pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/usr/bin || \
	fail pkgsend add dir failed

pkgsend -s $REPO_URL add file /lib/libc.so.1 mode=0555 owner=root group=bin \
    path=/lib/libc.so.1 || \
	fail pkgsend add file failed

pkgsend -s $REPO_URL add file /lib/libm.so.1 mode=0555 owner=root group=bin \
    path=/lib/libm.so.1 || \
	fail pkgsend add file failed

pkgsend -s $REPO_URL add file /usr/bin/cat mode=0555 owner=root group=bin \
    path=/usr/bin/cat || \
	fail pkgsend add file failed

pkgsend -s $REPO_URL add file /usr/sbin/init mode=0555 owner=root group=bin \
    path=/usr/sbin/init || \
	fail pkgsend add file failed

pkgsend -s $REPO_URL close || \
	fail pkgsend close failed

new_test "echo ::findleaks | mdb"
begin_expect_test_fails 124
output=`echo ::findleaks | mdb -p $DEPOT_PID`
expect_exit $? 0

if [[ $? = 0 && -n "$output" ]]; then
	print -u2 "$output"

	if [ -n "$DBG_STOP" ]; then
		print -u2 "stopping so you can debug the leaks"
		print -u2 "depot is at $DEPOT_PID"
		trap "" EXIT
		exit 1
	fi

	fail "leaks found"
fi
end_expect_test_fails

end_assert
# }}}1

#
# depot_cleanup will happen on exit thanks to our trap statement above.
#
exit 0
