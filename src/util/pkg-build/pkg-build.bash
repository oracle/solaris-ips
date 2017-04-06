#!/usr/bin/bash

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
# Copyright (c) 2017, Oracle and/or its affiliates. All rights reserved.
#

# set some environment variables
PATH=/usr/bin:/opt/solarisstudio12.4/bin:/usr/sbin
CC=/opt/solarisstudio12.4/bin/cc
PRIVATE_BUILD=1
export PATH CC PRIVATE_BUILD

umask 0022

# build the gate
rm -rf $WORKSPACE/proto
cd $WORKSPACE/src
make clobber
make install packages || exit $?

# clean up test directory and coverage
rm -rf tests/.coverage* tests/cov_* tests/core

# run the test suite (exclude t_origin_fw for now)
# XXX coverage temporarily disabled
# tests/run.py -v -j 12 -c xml
make test JOBS=12
test_result=$?

COVERAGE=$WORKSPACE/src/tests/cov_proto.xml
# note cov_tests.xml should already have relative paths
if [[ -e $COVERAGE ]]; then
	# fix coverage report to have relative path
	sed "s@$WORKSPACE/@@" $COVERAGE > $COVERAGE.tmp
	mv $COVERAGE.tmp $COVERAGE
fi

# check for core
if [[ -e tests/core ]]; then
	echo WARNING: core detected, dumping stack...
	echo ::stack | mdb tests/core
fi

# create summary file
log=/export/home/jenkins/jobs/$JOB_NAME/builds/$BUILD_NUMBER/log
summary=/export/home/jenkins/jobs/$JOB_NAME/builds/$BUILD_NUMBER/summary

rm -f ${summary}
touch ${summary}
chmod 666 ${summary}

{
	echo "TEST REPORT   JOB: $JOB_NAME   RUN: $BUILD_NUMBER"
	echo ""

	echo "Test summary:"
	echo ""
	egrep "^/usr/bin/python.* tests|tests in|FAILED" ${log}
	echo ""

	echo "Baseline summary:"
	echo ""
	# extract text between "^BASELINE MISMATCH" and "Target .* not remade"
	# insert a blank line after each block
	nawk '
	    /^BASELINE MISMATCH/, /Target .* not remade/
	    /Target .* not remade/ {print ""}
	' ${log}
} >> ${summary}

rcode=0

# check for baselines, which indicates an error
if grep -q BASELINE ${log} ; then
	rcode=1
fi

# check for skipped tests, which we treat as errors
if grep "s - skipped" ${log} | grep -v "skipped 0" >/dev/null ; then
	{
		echo "There were skipped tests."
		echo ""
	} >> ${summary}
	rcode=1
fi

if [[ $test_result -ne 0 ]]; then
        rcode=1
fi

exit ${rcode}
