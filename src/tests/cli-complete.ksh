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

# cli-complete.ksh - basic sanity test exercising all basic pkg(1) operations
#
# cli-complete.ksh runs out of $HG/src/tests, and runs an depot server
# and issues pkg(1) commands from the $HG/proto directory relevant to
# the executing system.
#
# XXX Should really select which cases to run.

TEMPDIR=${TEMPDIR:-/tmp}
REPO_PORT=${REPO_PORT:-8000}
REPO_DIR=$TEMPDIR/repo.$$
REPO_URL=http://localhost:$REPO_PORT
IMAGE_DIR=$TEMPDIR/image.$$

restore_dir=$PWD

ROOT=$PWD/../../proto/root_$(uname -p)

export PYTHONPATH=$ROOT/usr/lib/python2.4/vendor-packages/
export PATH=$ROOT/usr/bin:$PATH

$ROOT/usr/lib/pkg.depotd -p $REPO_PORT -d $REPO_DIR &

DEPOT_PID=$!

sleep 1

usage () {
	cli-complete.ksh
	exit 2
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

fail () {
	echo "*** case $tcase: $@"
	exit 1
}

trap "ret=$?; image_cleanup; depot_cleanup $ret" EXIT

# Case 0.  Stop server, start again.
# {{{1

kill $DEPOT_PID
wait $DEPOT_PID

$ROOT/usr/lib/pkg.depotd -p $REPO_PORT -d $REPO_DIR &

DEPOT_PID=$!

sleep 1

# }}}1

# Case 1.  Send empty package foo@1.0, install and uninstall.
# {{{1

tcase=1
trans_id=$(pkgsend -s $REPO_URL open foo@1.0,5.11-0)
if [[ $? != 0 ]]; then
	fail pkgsend open failed
fi

eval $trans_id

if ! pkgsend -s $REPO_URL close; then
	fail pkgsend close failed
fi

if ! pkg image-create -F -a test=$REPO_URL $IMAGE_DIR; then
	fail pkg image-create failed
fi

find $IMAGE_DIR

cd $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

if ! pkg install foo; then
	fail pkg install foo failed
fi

find $IMAGE_DIR

if ! pkg status; then
	fail pkg status failed
fi

if ! pkg uninstall foo; then
	fail pkg uninstall foo failed
fi

find $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

# }}}1

# Case 2.  Send package foo@1.1, containing a directory and a file,
# install and uninstall.
# {{{1

tcase=2
trans_id=$(pkgsend -s $REPO_URL open foo@1.1,5.11-0)
if [[ $? != 0 ]]; then
	fail pkgsend open failed
fi

eval $trans_id

if ! pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/lib; then
	fail pkgsend add dir failed
fi

if ! pkgsend -s $REPO_URL add file /lib/libc.so.1 mode=0555 owner=root group=bin \
	path=/lib/libc.so.1; then
	fail pkgsend add file failed
fi

if ! pkgsend -s $REPO_URL close; then
	fail pkgsend close failed
fi

if ! pkg image-create -F -a test=$REPO_URL $IMAGE_DIR; then
	fail pkg image-create failed
	image_cleanup
fi

find $IMAGE_DIR

cd $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

if ! pkg install foo; then
	fail pkg install foo failed
fi

find $IMAGE_DIR

if ! pkg status; then
	fail pkg status failed
fi

if ! pkg uninstall foo; then
	fail pkg uninstall foo failed
fi

find $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

# }}}1

# Case 3.  Install foo@1.0, upgrade to foo@1.1, uninstall.
# {{{1

tcase=3

if ! pkg image-create -F -a test=$REPO_URL $IMAGE_DIR; then
	fail pkgsend close failed
fi

find $IMAGE_DIR

cd $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

if ! pkg install foo@1.0; then
	fail pkg install foo failed
fi

find $IMAGE_DIR

if ! pkg status; then
	fail pkg status failed
fi

if ! pkg install foo@1.1; then
	fail pkg install foo \(1.0 -\> 1.1\) failed
fi

find $IMAGE_DIR

if ! pkg uninstall foo; then
	fail pkg status failed
fi

find $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

# }}}1

# Case 4.  Add bar@1.0, dependent on foo@1.0, install, uninstall.
# {{{1

tcase=4
trans_id=$(pkgsend -s $REPO_URL open bar@1.0,5.11-0)
if [[ $? != 0 ]]; then
	fail pkgsend open failed
fi

eval $trans_id

if ! pkgsend -s $REPO_URL add depend type=require fmri=pkg:/foo@1.0; then
	fail pkgsend add depend require failed
fi

if ! pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/bin; then
	fail pkgsend add dir failed
fi

if ! pkgsend -s $REPO_URL add file /bin/cat mode=0555 owner=root group=bin \
	path=/bin/cat; then
	fail pkgsend add file failed
fi

if ! pkgsend -s $REPO_URL close; then
	fail pkgsend close failed
fi

if ! pkg image-create -F -a test=$REPO_URL $IMAGE_DIR; then
	fail pkgsend close failed
fi

find $IMAGE_DIR

cd $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

if ! pkg install bar@1.0; then
	fail pkg install bar failed
fi

find $IMAGE_DIR

if ! pkg status; then
	fail pkg status failed
fi

find $IMAGE_DIR

if ! pkg uninstall -v bar foo; then
	fail pkg uninstall failed
fi

find $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

# }}}1

# Case 5.  Install bar@1.0, dependent on foo@1.0, uninstall recursively.
# {{{1

tcase=5

if ! pkg image-create -F -a test=$REPO_URL $IMAGE_DIR; then
	fail pkg image-create failed
fi

find $IMAGE_DIR

cd $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

if ! pkg install bar@1.0; then
	fail pkg install bar failed
fi

find $IMAGE_DIR

if ! pkg status; then
	fail pkg status failed
fi

find $IMAGE_DIR

if ! pkg uninstall -vr bar; then
	fail pkg uninstall -vr failed
fi

find $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

# }}}1

exit 0
