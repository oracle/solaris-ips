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
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
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

#
# Prevent PKG_IMAGE settings from leaking in from the user environment
#
unset PKG_IMAGE

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


new_assert "pkg status should fail in an empty image"
# {{{1

pkg image-create -F -a test=$REPO_URL $IMAGE_DIR
expect_exit 0 $?

cd $IMAGE_DIR

pkg status
expect_exit 1 $?

end_assert
# }}}1


new_assert "Send empty package foo@1.0, install and uninstall."
# {{{1

new_test "pkgsend open, close should succeed"
trans_id=$(pkgsend -s $REPO_URL open foo@1.0,5.11-0)
expect_exit 0 $?

eval $trans_id

pkgsend -s $REPO_URL close
expect_exit 0 $?

new_test "image-create should succeed"
pkg image-create -F -a test=$REPO_URL $IMAGE_DIR
expect_exit 0 $?

find $IMAGE_DIR

cd $IMAGE_DIR

new_test "pkg status -a should succeed"
pkg status -a
expect_exit 0 $?

new_test "pkg install foo should succeed"
pkg install foo
expect_exit 0 $?

find $IMAGE_DIR

new_test "pkg status should succeed"
pkg status
expect_exit 0 $?

new_test "pkg verify should succeed"
pkg verify
expect_exit 0 $?

new_test "pkg uninstall foo should succeed"
pkg uninstall foo
expect_exit 0 $?

new_test "pkg verify should succeed"
pkg verify
expect_exit 0 $?

find $IMAGE_DIR

new_test "pkg status -a should succeed"
pkg status -a
expect_exit 0 $?

end_assert
# }}}1


new_assert "Send package foo@1.1, containing a directory and a file, install," \
    "search, and uninstall."
# {{{1

new_test "pkgsend open, add file, add dir, close should succeed"
trans_id=$(pkgsend -s $REPO_URL open foo@1.1,5.11-0)
expect_exit 0 $?

eval $trans_id

pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/lib
expect_exit 0 $?

pkgsend -s $REPO_URL add file /lib/libc.so.1 mode=0555 owner=root group=bin \
	path=/lib/libc.so.1
expect_exit 0 $?

pkgsend -s $REPO_URL close
expect_exit 0 $?

if ! pkg image-create -F -a test=$REPO_URL $IMAGE_DIR; then
	fail pkg image-create failed
	image_cleanup
fi

find $IMAGE_DIR

cd $IMAGE_DIR

new_test "pkg status -a, install foo, verify should succeed"
pkg status -a
expect_exit 0 $?

pkg install foo
expect_exit 0 $?

pkg verify foo
expect_exit 0 $?

find $IMAGE_DIR

pkg status
expect_exit 0 $?

new_test "pkg search for a file in the package should succeed"
pkg search /lib/libc.so.1
expect_exit 0 $?

new_test "pkg search -r should succeed"
pkg search -r /lib/libc.so.1
expect_exit 0 $?

new_test "pkg search for a bogus file should fail"
pkg search blah
expect_exit 1 $?

new_test "pkg search -r for a bogus file should fail"
pkg search -r blah 
expect_exit 1 $?

new_test "pkg uninstall foo should succeed"
pkg uninstall foo
expect_exit 0 $?

find $IMAGE_DIR

new_test "pkg status -a should succeed"
pkg status -a
expect_exit 0 $?

new_test "pkg verify should succeed"
pkg verify
expect_exit 0 $?

end_assert
# }}}1


new_assert "Install foo@1.0, upgrade to foo@1.1, uninstall."
# {{{1

new_test "pkg image-create should succeed"
pkg image-create -F -a test=$REPO_URL $IMAGE_DIR
expect_exit 0 $?

find $IMAGE_DIR

cd $IMAGE_DIR

pkg status -a
expect_exit 0 $?

new_test "pkg install foo@1.0 should succeed"
pkg install foo@1.0
expect_exit 0 $?

new_test "check that version 1.0 was installed"
pkg status | grep foo@1.0 > /dev/null
expect_exit 0 $?

new_test "check that version 1.1 was not installed"
pkg status | grep foo@1.1 > /dev/null
expect_exit 1 $?

find $IMAGE_DIR

pkg status
expect_exit 0 $?

new_test "install version 1.1 (i.e. upgrade from 1.0 -> 1.1)"
pkg install foo@1.1
expect_exit 0 $?

pkg status | grep foo@1.1 > /dev/null
expect_exit 0 $?

pkg verify
expect_exit 0 $?

find $IMAGE_DIR

new_test "pkg uninstall, status -a, verify should succeed"
pkg uninstall foo
expect_exit 0 $?

find $IMAGE_DIR

pkg status -a
expect_exit 0 $?

pkg verify
expect_exit 0 $?

end_assert
# }}}1



new_assert "Add bar@1.0, dependent on foo@1.0, install, uninstall."
# {{{1

new_test "pkgsend bar@1.0"
trans_id=$(pkgsend -s $REPO_URL open bar@1.0,5.11-0)
expect_exit 0 $?

eval $trans_id

new_test "pkgsend bar@1.0: add depend"
pkgsend -s $REPO_URL add depend type=require fmri=pkg:/foo@1.0
expect_exit 0 $?

new_test "pkgsend bar@1.0: add dir"
pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/bin
expect_exit 0 $?

new_test "pkgsend bar@1.0: add file"
pkgsend -s $REPO_URL add file /bin/cat mode=0555 owner=root group=bin \
    path=/bin/cat
expect_exit 0 $?

pkgsend -s $REPO_URL close
expect_exit 0 $?

new_test "create image"
pkg image-create -F -a test=$REPO_URL $IMAGE_DIR
expect_exit 0 $?

find $IMAGE_DIR

cd $IMAGE_DIR

new_test "check status, install bar@1.0"
pkg status -a
expect_exit 0 $?

pkg install bar@1.0
expect_exit 0 $?

find $IMAGE_DIR

pkg status
expect_exit 0 $?

pkg verify
expect_exit 0 $?

new_test "uninstall bar and foo"
pkg uninstall -v bar foo
expect_exit 0 $?

find $IMAGE_DIR

new_test "check status and verify"
pkg status | grep bar@ > /dev/null
expect_exit 1 $?

pkg status | grep foo@ > /dev/null
expect_exit 1 $?

pkg verify
expect_exit 0 $?

end_assert
# }}}1



new_assert "Install bar@1.0, dependent on foo@1.0, uninstall recursively."
# {{{1

new_test "create image"
pkg image-create -F -a test=$REPO_URL $IMAGE_DIR
expect_exit 0 $?

find $IMAGE_DIR

cd $IMAGE_DIR

new_test "install bar@1.0"
pkg install bar@1.0
expect_exit 0 $?

find $IMAGE_DIR

new_test "check to see that foo and bar were installed"
pkg status | grep foo > /dev/null
expect_exit 0 $?
pkg status | grep bar > /dev/null
expect_exit 0 $?

pkg verify
expect_exit 0 $?

find $IMAGE_DIR

pkg uninstall -vr bar
expect_exit 0 $?


# http://defect.opensolaris.org/bz/show_bug.cgi?id=387
begin_expect_test_fails 387
new_test "check to see that foo and bar were uninstalled"
pkg status | grep foo > /dev/null
expect_exit 1 $?
pkg status | grep bar > /dev/null
expect_exit 1 $?
end_expect_test_fails 

find $IMAGE_DIR

end_assert
# }}}1


new_assert "Send package shouldnotexist@1.0, then abandon the transaction"
# {{{1

new_test "Open shouldnotexist@1.0"
trans_id=$(pkgsend -s $REPO_URL open shouldnotexist@1.0,5.11-0)
expect_exit 0 $?

eval $trans_id

new_test "Send dir"
pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/bin
expect_exit 0 $?

pkgsend -s $REPO_URL close -A
expect_exit 0 $?

pkg refresh
expect_exit 0 $?

pkg status -a shouldnotexist
expect_exit 1 $?

end_assert
# }}}1



new_assert "Send package bar@1.1, dependent on foo@1.2.  Install bar@1.0." \
    "List all packages.  Upgrade image."
# {{{1

find $IMAGE_DIR

cd $IMAGE_DIR

new_test "pkg refresh, status -aH"
pkg refresh
expect_exit 0 $?

pkg status -aH
expect_exit 0 $?

new_test "pkg install bar@1.0"
pkg install -v bar@1.0
expect_exit 0 $?

new_test "pkgsend foo@1.2"
trans_id=$(pkgsend -s $REPO_URL open foo@1.2,5.11-0)
expect_exit 0 $?
eval $trans_id

pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/lib
expect_exit 0 $?
pkgsend -s $REPO_URL add file /lib/libc.so.1 mode=0555 owner=root group=bin \
    path=/lib/libc.so.1
expect_exit 0 $?
pkgsend -s $REPO_URL close
expect_exit 0 $?


new_test "pkgsend bar@1.1"
trans_id=$(pkgsend -s $REPO_URL open bar@1.1,5.11-0)
expect_exit 0 $?
eval $trans_id

pkgsend -s $REPO_URL add depend type=require fmri=pkg:/foo@1.2
expect_exit 0 $?
pkgsend -s $REPO_URL add dir mode=0755 owner=root group=bin path=/bin
expect_exit 0 $?
pkgsend -s $REPO_URL add file /bin/cat mode=0555 owner=root group=bin \
    path=/bin/cat
expect_exit 0 $?
pkgsend -s $REPO_URL close
expect_exit 0 $?

new_test "list, check status, refresh"
pkg list -H
expect_exit 0 $?
pkg status
expect_exit 0 $?
pkg refresh
expect_exit 0 $?

new_test "status, image-update -v, verify"
pkg status
expect_exit 0 $?
pkg image-update -v
expect_exit 0 $?
pkg verify
expect_exit 0 $?

find $IMAGE_DIR

new_test "status -a, uninstall bar foo, verify"
pkg status -a
expect_exit 0 $?

pkg uninstall bar foo
expect_exit 0 $?

pkg verify
expect_exit 0 $?

end_assert
# }}}1


new_assert "Send package rar@1.0, dependent on moo@1.1.  Rename moo to zoo." \
    "Install zoo and then rar.  Verify that zoo satisfied dependency for moo."
# {{{1

new_test "pkg refresh, status -aH"
pkg refresh
expect_exit 0 $?

pkg status -aH
expect_exit 0 $?

new_test "pkgsend moo@1.1"
trans_id=$(pkgsend -s $REPO_URL open moo@1.1,5.11-0)
expect_exit 0 $?
eval $trans_id
pkgsend -s $REPO_URL close
expect_exit 0 $?

new_test "pkgsend zoo@1.0"
trans_id=$(pkgsend -s $REPO_URL open zoo@1.0,5.11-0)
expect_exit 0 $?
eval $trans_id
pkgsend -s $REPO_URL close
expect_exit 0 $?

new_test "pkgsend rename moo@1.2 zoo@1.0"
pkgsend -s $REPO_URL rename moo@1.2,5.11-0 zoo@1.0,5.11-0
expect_exit 0 $?

new_test "pkgsend rar@1.0"
trans_id=$(pkgsend -s $REPO_URL open rar@1.0,5.11-0)
expect_exit 0 $?
eval $trans_id
pkgsend -s $REPO_URL add depend type=require fmri=pkg:/moo@1.1
expect_exit 0 $?
pkgsend -s $REPO_URL close
expect_exit 0 $?

new_test "pkg refresh, status -aH"
pkg refresh
expect_exit 0 $?

pkg status -aH
expect_exit 0 $?

new_test "pkg install zoo@1.0"
pkg install -v zoo
expect_exit 0 $?

new_test "pkg install rar@1.0"
pkg install -v rar
expect_exit 0 $?

new_test "check to see that zoo and rar were installed"
pkg status | grep zoo > /dev/null
expect_exit 0 $?
pkg status | grep rar > /dev/null
expect_exit 0 $?

new_test "check to see that moo was NOT installed"
pkg status | grep moo > /dev/null
expect_exit 1 $?

new_test "status -a, uninstall rar zoo, verify"
pkg status -a
expect_exit 0 $?

pkg uninstall rar zoo
expect_exit 0 $?

pkg verify
expect_exit 0 $?

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

PKG_TRANS_ID="foobarbaz"
pkgsend -s $REPO_URL add file /lib/libc.so.1 mode=0555 owner=root group=bin \
	path=/lib/libc.so.1
expect_exit 1 $?

end_assert
# }}}1

exit 0
