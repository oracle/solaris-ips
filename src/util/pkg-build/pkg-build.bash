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
PACKAGE_MANAGER_ROOT=$WORKSPACE/proto/root_`uname -p`/
PATH=/opt/solarisstudio12.4/bin:/usr/sfw/bin:$PATH
CC=/opt/solarisstudio12.4/bin/cc
PRIVATE_BUILD=1
LC_ALL=C
export PACKAGE_MANAGER_ROOT PYTHONPATH PATH CC PRIVATE_BUILD LC_ALL

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
chmod 777 ${summary}
base=`egrep -n BASELINE ${log}`
stat=$?
echo "TEST RUN SUMMARY JOB: $JOB_NAME  RUN: $BUILD_NUMBER" >> ${summary}
echo "" >> ${summary}
egrep "tests in" ${log} >> ${summary}
rcode=0
if [[ ${stat} == 0 ]]; then
        start=${base%:BASELINE*}
        (( start -= 1 ))
        echo "" >> ${summary}
        egrep "FAILED" ${log} >> ${summary}
        echo "" >> ${summary}
        more +${start} ${log} >> ${summary}
        rcode=1
fi

# check for skipped tests, which we treat as errors
FOUND_SKIPPED=0
while read line
do
        echo $line | grep "s - skipped" > /dev/null
        if [ $? -eq 0 ]; then
                echo $line | grep "s - skipped 0 tests" > /dev/null
                if [ $? -ne 0 ]; then
                        FOUND_SKIPPED=1
                        echo $line >> ${summary}
                fi
        fi
done < ${log}

if [ $FOUND_SKIPPED -eq 1 ]; then
        rcode=1
fi

if [ $test_result -ne 0 ]; then
        rcode=1
fi

exit ${rcode}
