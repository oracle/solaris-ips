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
REPO1_PORT=8000
REPO1_DIR=$TEMPDIR/repo.1.$$
REPO1_URL=http://localhost:$REPO1_PORT
REPO2_PORT=9000
REPO2_DIR=$TEMPDIR/repo.2.$$
REPO2_URL=http://localhost:$REPO2_PORT
IMAGE_DIR=$TEMPDIR/image.$$

restore_dir=$PWD

ROOT=$PWD/../../proto/root_$(uname -p)

export PKG_DEPOT_CONTENT=$ROOT/usr/share/lib/pkg
export PYTHONPATH=$ROOT/usr/lib/python2.4/vendor-packages/
export PATH=$ROOT/usr/bin:$PATH

print -u2 -- \
    "\n--two-depot testing------------------------------------------------"

. ./harness_lib.ksh

depots_start () {
	print -u2 "Redirecting all repository logging to stdout"
	$ROOT/usr/lib/pkg.depotd -p $REPO1_PORT -d $REPO1_DIR 2>&1 &
	DEPOT1_PID=$!
	$ROOT/usr/lib/pkg.depotd -p $REPO2_PORT -d $REPO2_DIR 2>&1 &
	DEPOT2_PID=$!
	sleep 1
}

depots_cleanup () {
	kill $DEPOT1_PID
	sleep 1
	if ps -p $DEPOT1_PID > /dev/null; then
		kill -9 $DEPOT1_PID
	fi
	rm -fr $REPO1_DIR

	kill $DEPOT2_PID
	sleep 1
	if ps -p $DEPOT2_PID > /dev/null; then
		kill -9 $DEPOT2_PID
	fi
	rm -fr $REPO2_DIR

	exit $1
}

trap "ret=$?; died; image_cleanup; depots_cleanup $ret" EXIT

depots_start

new_assert "Populate Depot 1 and Depot 2"
# {{{1

#Depot 1 gets pkg foo and pkg moo

trans_id=$(pkgsend -s $REPO1_URL open foo@1.0,5.11-0)
if [[ $? != 0 ]]; then
	fail pkgsend open failed
fi

eval $trans_id

if ! pkgsend -s $REPO1_URL close; then
	fail pkgsend close failed
fi

trans_id=$(pkgsend -s $REPO1_URL open moo@1.0,5.11-0)
if [[ $? != 0 ]]; then
	fail pkgsend open failed
fi

eval $trans_id

if ! pkgsend -s $REPO1_URL close; then
	fail pkgsend close failed
fi

#Depot 2 gets pkg foo and pkg bar

trans_id=$(pkgsend -s $REPO2_URL open foo@1.0,5.11-0)
if [[ $? != 0 ]]; then
	fail pkgsend open failed
fi

eval $trans_id

if ! pkgsend -s $REPO2_URL close; then
	fail pkgsend close failed
fi

trans_id=$(pkgsend -s $REPO2_URL open bar@1.0,5.11-0)
if [[ $? != 0 ]]; then
	fail pkgsend open failed
fi

eval $trans_id

if ! pkgsend -s $REPO2_URL close; then
	fail pkgsend close failed
fi

end_assert
# }}}1

new_assert "Create new image, add second authority, update catalogs"
# {{{1

#Create primary authority

if ! pkg image-create -F -a test1=$REPO1_URL $IMAGE_DIR; then
	fail pkg image-create failed
fi

#Add second authority

echo "[authority_test2]" >> $IMAGE_DIR/var/pkg/cfg_cache
echo "origin = $REPO2_URL" >> $IMAGE_DIR/var/pkg/cfg_cache
echo "prefix = test2" >> $IMAGE_DIR/var/pkg/cfg_cache
echo "mirrors = None" >> $IMAGE_DIR/var/pkg/cfg_cache

cd $IMAGE_DIR

if ! pkg refresh; then
	fail pkg refresh failed
fi

if ! pkg status -a; then
	fail pkg status -a failed
fi

end_assert
# }}}1

new_assert "Install and uninstall pkg moo@1.0 from authority 1"
# {{{1

if ! pkg install moo; then
	fail pkg install moo failed
fi

find $IMAGE_DIR

if ! pkg status; then
	fail pkg status failed
fi

if ! pkg uninstall moo; then
	fail pkg uninstall moo failed
fi

find $IMAGE_DIR

end_assert
# }}}1

new_assert "Install and uninstall pkg bar@1.0 from authority 2"
# {{{1

if ! pkg install bar; then
	fail pkg install bar failed
fi

find $IMAGE_DIR

if ! pkg status; then
	fail pkg status failed
fi

if ! pkg uninstall bar; then
	fail pkg uninstall bar failed
fi

find $IMAGE_DIR

end_assert
# }}}1

new_assert "Install and uninstall pkg foo@1.0 from authority 1"
# {{{1

if ! pkg status -a; then
	fail pkg status -a failed
fi

# This should fail, and require that we specify the authority

pkg install foo
expect_exit 1 $?

# This should pass now that an authority has been specified

if ! pkg install pkg://test1/foo; then
	fail pkg install foo failed
fi

find $IMAGE_DIR

if ! pkg status; then
	fail pkg status failed
fi

if ! pkg uninstall pkg://test1/foo; then
	fail pkg uninstall foo failed
fi

find $IMAGE_DIR

end_assert
# }}}1

exit 0
