#!/usr/bin/python
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
# actionbench - benchmark action creation
#

import pkg.actions as actions

import timeit

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":

	str = 'action = actions.fromstr("file 58371e22b5e75ec66602b966edf29bcce7038db5 elfarch=i386 elfbits=32 elfhash=cd12b081ddaef993fd0276dd04d653222d25fa77 group=bin mode=0755 owner=root path=usr/lib/libzonecfg.so.1 pkg.size=178072")'

	for i in (1, 2, 3):
		print timeit.Timer(str, 'import pkg.actions as actions').\
		    timeit(100000)

