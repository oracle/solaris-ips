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

#
# upgrade.ksh - upgrade torture test
#

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
    "\n--upgrade testing-----------------------------------------------------"

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


new_assert "Send package amber@1.0, bronze@1.0"
# {{{1

echo "Copyright 1066 Ye Olde FooBazCo" > /tmp/copyright1
echo "Copyright 1492 FooBazCo" > /tmp/copyright2
echo "Copyright 1776 FooBazCo" > /tmp/copyright3
echo "Copyright 2000 FooBazCo" > /tmp/copyright4

echo "Amber1" > /tmp/amber1
echo "Amber2" > /tmp/amber2
echo "Bronze1" > /tmp/bronze1
echo "Bronze2" > /tmp/bronze2

new_test "pkgsend amber@1.0 open, add contents, close should succeed"
trans_id=$(pkgsend -s $REPO_URL open amber@1.0,5.11-0)
expect_exit 0 $?

eval $trans_id

cat <<_EOF | \
    ( while read line; do pkgsend -s $REPO_URL $line; expect_exit 0 $?; done )
add dir mode=0755 owner=root group=bin path=/lib
add file /lib/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
add link path=/lib/libc.symlink target=/lib/libc.so.1
add hardlink path=/lib/libc.hardlink target=/lib/libc.so.1
add file /tmp/amber1 mode=0444 owner=root group=bin path=/etc/amber1
add file /tmp/amber2 mode=0444 owner=root group=bin path=/etc/amber2
close
_EOF
#add license /tmp/copyright1 path=copyright




new_test "pkgsend bronze@1.0 open, add contents, close should succeed"
trans_id=$(pkgsend -s $REPO_URL open bronze@1.0,5.11-0)
expect_exit 0 $?

eval $trans_id

#
# BRONZE 1.0
#
cat <<_EOF | \
    ( while read line; do pkgsend -s $REPO_URL $line; expect_exit 0 $?; done )
add dir mode=0755 owner=root group=bin path=/usr
add dir mode=0755 owner=root group=bin path=/usr/bin
add file /usr/bin/sh mode=0555 owner=root group=bin path=/usr/bin/sh
add link path=/usr/bin/jsh target=./sh
add hardlink path=/lib/libc.bronze target=/lib/libc.so.1
add file /tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
add file /tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
add depend fmri=pkg:/amber@1.0 type=require
close
_EOF
expect_exit 0 $?
#add license /tmp/copyright2 license=copyright

end_assert
# }}}1

new_assert "Install bronze@1.0 (should cause amber install too)"
# {{{1

image_cleanup
new_test "create image"
pkg image-create -F -a test=$REPO_URL $IMAGE_DIR
expect_exit 0 $?

cd $IMAGE_DIR

new_test "install bronze"
pkg install bronze
expect_exit 0 $?

pkg status

new_test "check for amber"
pkg status | grep amber@1.0 > /dev/null
expect_exit 0 $?

new_test "check for bronze"
pkg status | grep bronze@1.0 > /dev/null
expect_exit 0 $?

pkg verify
expect_exit 0 $?

end_assert
# }}}1

new_assert "Send amber@2.0, bronze@2.0"
# {{{1

new_test "pkgsend amber@2.0 open, add contents, close should succeed"
trans_id=$(pkgsend -s $REPO_URL open amber@2.0,5.11-0)
expect_exit 0 $?

eval $trans_id

#
# In version 2.0, several things happen:
#
# Amber and Bronze swap a file with each other in both directions.
# The dependency flips over (Amber now depends on Bronze)
#
# Bronze's 1.0 hardlink to amber's libc goes away and is replaced
# with a file of the same name.  Amber hardlinks to that.
#

#
# AMBER 2.0
#
cat <<_EOF | \
    ( while read line; do pkgsend -s $REPO_URL $line; expect_exit 0 $?; done )
add dir mode=0755 owner=root group=bin path=/lib
add file /lib/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
add link path=/lib/libc.symlink target=/lib/libc.so.1
add hardlink path=/lib/libc.amber target=/lib/libc.bronze
add hardlink path=/lib/libc.hardlink target=/lib/libc.so.1
add file /tmp/amber1 mode=0444 owner=root group=bin path=/etc/amber1
add file /tmp/amber2 mode=0444 owner=root group=bin path=/etc/bronze2
add depend fmri=pkg:/bronze@2.0 type=require
close
_EOF
#add license /tmp/copyright1 path=copyright

new_test "pkgsend bronze@2.0 open, add contents, close should succeed"
trans_id=$(pkgsend -s $REPO_URL open bronze@2.0,5.11-0)
expect_exit 0 $?

eval $trans_id

#
# BRONZE 2.0
#
cat <<_EOF | \
    ( while read line; do pkgsend -s $REPO_URL $line; expect_exit 0 $?; done )
add dir mode=0755 owner=root group=bin path=/usr
add dir mode=0755 owner=root group=bin path=/usr/bin
add file /usr/bin/sh mode=0555 owner=root group=bin path=/usr/bin/sh
add file /usr/lib/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.bronze
add link path=/usr/bin/jsh target=./sh
add hardlink path=/lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
add file /tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
add file /tmp/bronze2 mode=0444 owner=root group=bin path=/etc/amber2
close
_EOF
expect_exit 0 $?
#add license /tmp/copyright2 license=copyright

end_assert
# }}}1

new_assert "image-update to get new versions of amber and bronze"
# {{{1

cd $IMAGE_DIR

new_test "image update"
pkg refresh
expect_exit 0 $?

pkg image-update
expect_exit 0 $?

new_test "check if update did the right thing"
pkg status -a

new_test "check for amber"
pkg status | grep amber@2.0 > /dev/null
expect_exit 0 $?

new_test "check for bronze"
pkg status | grep bronze@2.0 > /dev/null
expect_exit 0 $?

pkg verify
expect_exit 0 $?

image_cleanup
end_assert
# }}}1

exit 0
