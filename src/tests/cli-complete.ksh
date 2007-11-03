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

. ./harness_lib.ksh

depot_start
trap "ret=$?; died; image_cleanup; depot_cleanup $ret" EXIT


new_assert "Stop server, start again."
# {{{1

kill $DEPOT_PID
wait $DEPOT_PID

depot_start
end_assert
# }}}1


new_assert "Send empty package foo@1.0, install and uninstall."
# {{{1

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

end_assert
# }}}1


new_assert "Send package foo@1.1, containing a directory and a file, install," \
    "search, and uninstall."
# {{{1

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

end_assert
# }}}1


new_assert "Install foo@1.0, upgrade to foo@1.1, uninstall."
# {{{1

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

end_assert
# }}}1


new_assert "Add bar@1.0, dependent on foo@1.0, install, uninstall."
# {{{1

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

end_assert
# }}}1


new_assert "Install bar@1.0, dependent on foo@1.0, uninstall recursively."
# {{{1

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

end_assert
# }}}1

new_assert "Send package shouldnotexist@1.0, then abandon the transaction"
# {{{1

trans_id=$(pkgsend -s $REPO_URL open shouldnotexist@1.0,5.11-0)
if [[ $? != 0 ]]; then
	fail pkgsend open failed
fi

eval $trans_id

if ! pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/bin; then
	fail pkgsend add dir failed
fi

if ! pkgsend -s $REPO_URL close -A; then
	fail pkgsend close failed
fi

pkg refresh
expect_exit 0 $?

#
# XXX currently broken, bugid:
# 60 'pkg status does_not_exist' throws a traceback
#
begin_expect_test_fails 60

pkg status -a shouldnotexist
expect_exit 1 $?

end_expect_test_fails

end_assert
# }}}1

new_assert "Send package bar@1.1, dependent on foo@1.2.  Install bar@1.0." \
    "Upgrade image."
# {{{1

find $IMAGE_DIR

cd $IMAGE_DIR

if ! pkg refresh; then
	fail pkg refresh failed
fi

if ! pkg status -a; then
	fail pkg status -a failed
fi

if ! pkg install -v bar@1.0; then
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
	fail pkg uninstall bar foo failed
fi

if ! pkg status; then
	fail pkg status failed
fi

find $IMAGE_DIR

end_assert
# }}}1

new_assert "bad command line options should result in error status 2"
# {{{1

new_test pkg -@ is bogus
pkg -@ 2>&1
expect_exit 2 $?

new_test pkg -s needs an arg
pkg -s 2>&1
expect_exit 2 $?

new_test pkg -R need an arg
pkg -R 2>&1
expect_exit 2 $?

new_test pkg status -@ is bogus
pkg status -@ 2>&1
expect_exit 2 $?

new_test pkg list -@ is bogus
pkg list -@ 2>&1
expect_exit 2 $?

new_test pkg list -o needs an arg
pkg list -o 2>&1
expect_exit 2 $?

new_test pkg list -s needs an arg
pkg list -s 2>&1
expect_exit 2 $?

new_test pkg list -t needs an arg
pkg list -t 2>&1
expect_exit 2 $?

new_test image-update -@ is bogus
pkg image-update -@ 2>&1
expect_exit 2 $?

new_test image-create -@ is bogus
pkg image-create -@ 2>&1
expect_exit 2 $?

new_test image-create --bozo is bogus
pkg image-create --bozo 2>&1
expect_exit 2 $?

new_test install -@ foo is bogus
pkg install -@ foo 2>&1
expect_exit 2 $?

new_test uninstall -@ foo is bogus
pkg uninstall -@ foo 2>&1
expect_exit 2 $?

new_test pkgsend -@ is bogus
trans_id=$(pkgsend -@ -s $REPO_URL open foo@1.0,5.11-0 2>&1)
expect_exit 2 $?

new_test pkgsend -s REPO -@ open is bogus
trans_id=$(pkgsend -s $REPO_URL -@ open foo@1.0,5.11-0 2>&1)
expect_exit 2 $?

# should work
trans_id=$(pkgsend -s $REPO_URL open foo@1.0,5.11-0 2>&1)
expect_exit 0 $?

eval $trans_id

# Bad command line option to close
new_test close -Q is bogus
pkgsend close -Q 2>&1
expect_exit 2 $?

# should work
pkgsend close -A 2>&1
expect_exit 0 $?

end_assert
# }}}1

new_assert "exercise pkgsend open"
# {{{1

new_test "pkgsend open should emit a shell eval-able thing"
res=`pkgsend -s $REPO_URL open foo@1.0,5.11-0`
expect_exit 0 $?

echo $res
echo $res
echo "$res" | egrep '^export PKG_TRANS_ID=[0-9]+'
expect_exit 0 $?

eval "$res"
expect_exit 0 $?

pkgsend close -A 2>&1
expect_exit 0 $?

new_test "pkgsend open -n should emit an integer"
res=`pkgsend -s $REPO_URL open -n foo@1.0,5.11-0`
expect_exit 0 $?
echo $res
echo $res | egrep '^[0-9]+'
expect_exit 0 $?

PKG_TRANS_ID="$res" pkgsend close -A 2>&1
expect_exit 0 $?

end_assert
# }}}1

new_assert "client correctly handles errors on bad pkgsends"
# {{{1

#
# See http://defect.opensolaris.org/bz/show_bug.cgi?id=89
#
new_test "client handles rejection from depot following bogus transaction"

begin_expect_test_fails 89

PKG_TRANS_ID="foobarbaz"
pkgsend -s $REPO_URL add file /lib/libc.so.1 mode=0555 owner=root group=bin \
	path=/lib/libc.so.1
expect_exit 1 $?

end_expect_test_fails

end_assert
# }}}1

exit 0
