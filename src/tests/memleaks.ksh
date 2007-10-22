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

if [[ ! -x /usr/bin/mdb ]]; then
	echo "mdb(1) not available.  No leak checking."
	exit 0
fi

LD_PRELOAD=libumem.so UMEM_DEBUG=default
export LD_PRELOAD
export UMEM_DEBUG

$ROOT/usr/lib/pkg.depotd -p $REPO_PORT -d $REPO_DIR &
DEPOT_PID=$!

sleep 1

depot_cleanup () {
	kill $DEPOT_PID
	sleep 1
	if ps -p $DEPOT_PID > /dev/null; then
		kill -9 $DEPOT_PID
	fi
	rm -fr $REPO_DIR
	exit $1
}

fail () {
	echo "*** case $tcase: $@"
	exit 1
}

trap "ret=$?; depot_cleanup $ret" EXIT

# Case 0.  Put some binaries into the server, then findleaks it.
# {{{1

tcase=0
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

echo "::findleaks" | mdb -p $DEPOT_PID

# }}}1

#
# depot_cleanup will happen on exit thanks to our trap statement above.
#
exit 0
