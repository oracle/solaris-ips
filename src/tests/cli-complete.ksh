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

export PKG_DEPOT_CONTENT=$ROOT/usr/share/lib/pkg
export PYTHONPATH=$ROOT/usr/lib/python2.4/vendor-packages/
export PATH=$ROOT/usr/bin:$PATH

print -u2 -- \
    "\n--cli-complete testing------------------------------------------------"

usage () {
	cli-complete.ksh
	exit 2
}

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
tassert="unknown"
new_assert() {
	tassert="$*"
	intest=1
}

pass () {
	print -u2 "PASS $tcase: $tassert"
	tcase=`expr "$tcase" "+" "1"`
	intest=0
}

fail () {
	print -u2 "*** case $tcase: $@"
	print -u2 "*** ASSERT: $tassert"
	exit 1
}

died () {
	if [[ $intest -ne 0 ]]; then
		print -u2 "*** trap; died in case $tcase"
		print -u2 "*** ($tassert)"
	fi
}

depot_start
trap "ret=$?; died; image_cleanup; depot_cleanup $ret" EXIT

# {{{1
new_assert "Stop server, start again."

kill $DEPOT_PID
wait $DEPOT_PID

depot_start
pass
# }}}1

# {{{1
new_assert "Send empty package foo@1.0, install and uninstall."

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

pass
# }}}1


# {{{1
new_assert "Send package foo@1.1, containing a directory and a file, install," \
    "search, and uninstall."

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

if ! pkg search /lib/libc.so.1; then
	fail pkg search failed
fi

if ! pkg search blah; then
	fail pkg search failed
fi

if ! pkg uninstall foo; then
	fail pkg uninstall foo failed
fi

find $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

pass
# }}}1

# {{{1
new_assert "Install foo@1.0, upgrade to foo@1.1, uninstall."

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

if ! pkg status | grep foo@1.0 > /dev/null; then
	fail pkg install foo@1.0 didn\'t install version 1.0
fi

find $IMAGE_DIR

if ! pkg status; then
	fail pkg status failed
fi

if ! pkg install foo@1.1; then
	fail pkg install foo \(1.0 -\> 1.1\) failed
fi

if ! pkg status | grep foo@1.1 > /dev/null; then
	fail pkg install foo@1.1 didn\'t install version 1.1
fi

find $IMAGE_DIR

if ! pkg uninstall foo; then
	fail pkg status failed
fi

find $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

pass
# }}}1

# {{{1
new_assert "Add bar@1.0, dependent on foo@1.0, install, uninstall."

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

pass
# }}}1

# {{{1
new_assert "Install bar@1.0, dependent on foo@1.0, uninstall recursively."

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

pass
# }}}1

# {{{1
new_assert "Send package bar@1.1, dependent on foo@1.2.  Install bar@1.0." \
    "Upgrade image."

find $IMAGE_DIR

cd $IMAGE_DIR

if ! pkg refresh; then
	fail pkg refresh failed
fi

if ! pkg status -a; then
	fail pkg status -a failed
fi

if ! pkg install bar@1.0; then
	fail pkg install bar failed
fi

trans_id=$(pkgsend -s $REPO_URL open foo@1.2,5.11-0)
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

trans_id=$(pkgsend -s $REPO_URL open bar@1.1,5.11-0)
if [[ $? != 0 ]]; then
	fail pkgsend open failed
fi

eval $trans_id

if ! pkgsend -s $REPO_URL add depend type=require fmri=pkg:/foo@1.2; then
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

find $IMAGE_DIR

if ! pkg status; then
	fail pkg status failed
fi

if ! pkg refresh; then
	fail pkg refresh failed
fi

if ! pkg status; then
	fail pkg status failed
fi

if ! pkg image-update -v; then
	fail pkg image-update failed
fi

find $IMAGE_DIR

if ! pkg status -a; then
	fail pkg status -a failed
fi

if ! pkg uninstall bar foo; then
	fail pkg uninstall bar foo
fi

if ! pkg status; then
	fail pkg status faileld
fi


find $IMAGE_DIR

pass
# }}}1

exit 0
