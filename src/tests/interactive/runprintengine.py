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

#
# Copyright (c) 2012, Oracle and/or its affiliates. All rights reserved.
#

import locale
import gettext
import sys

import pkg.client.printengine as printengine
import pkg.misc as misc

if __name__ == "__main__":
        misc.setlocale(locale.LC_ALL, "", None)
        gettext.install("pkg", "/usr/share/locale")

        if len(sys.argv) >= 2:
                output_file = open(sys.argv[1], "w")
        else:
                output_file = sys.stdout

        print >> output_file, ("-" * 60)
        printengine.test_logging_printengine(output_file)
        print >> output_file, "\n\n" + ("-" * 60)
        printengine.test_posix_printengine(output_file)
