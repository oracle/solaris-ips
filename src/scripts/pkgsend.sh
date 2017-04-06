#!/bin/sh
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
# Copyright (c) 2008, 2015, Oracle and/or its affiliates. All rights reserved.
#

# Resolve a symbolic link to the true file location
resolve_symlink () {
    file="$1"
    while [ -h "$file" ]; do
        ls=`ls -ld "$file"`
        link=`expr "$ls" : '^.*-> \(.*\)$' 2>/dev/null`
        if expr "$link" : '^/' 2> /dev/null >/dev/null; then
            file="$link"
        else
            file=`dirname "$1"`"/$link"
        fi
    done
    echo "$file"
}

# Take a relative path and make it absolute. Pwd -P will
# resolve any symlinks in the path
make_absolute () {
    save_pwd=`pwd`
    cd $1;
    full_path=`pwd -P`
    cd $save_pwd
    echo "$full_path"
}

cmd=`resolve_symlink $0` 
my_home_relative=`dirname $cmd`  
my_home=`make_absolute $my_home_relative`

my_base=`cd ${my_home}/../../..; pwd`
my_ips_base=`cd ${my_home}/../..; pwd`
LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:${my_ips_base}/usr/lib
PYTHONHOME=${my_base}/python
PYTHONPATH=${PYTHONPATH}:${my_ips_base}/usr/lib/python2.7/vendor-packages
PKG_HOME=${my_ips_base}/usr
export LD_LIBRARY_PATH PYTHONHOME PYTHONPATH PKG_HOME
if [ -x ${my_base}/python/bin/python2.7 ] ; then
  PYEXE=${my_base}/python/bin/python2.7
else
  PYEXE=`which python`
  unset PYTHONHOME
fi

exec ${PYEXE} ${my_home}/publish.py "$@"

