#!/usr/bin/python2.6
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

import getopt
import locale
import gettext
import os
import sys
import traceback

import pkg.client.printengine as printengine
import pkg.misc as misc

if __name__ == "__main__":
        misc.setlocale(locale.LC_ALL, "", None)
        gettext.install("pkg", "/usr/share/locale")

        test_ttymode = test_nottymode = test_logging = False
        opts, argv = getopt.getopt(sys.argv[1:], "tTl")
        for (opt, arg) in opts:
                if opt == '-t':
                        test_ttymode = True
                elif opt == '-T':
                        test_nottymode = True
                elif opt == '-l':
                        test_logging = True
                else:
                        print >> sys.stderr, "bad option %s" % opt
                        sys.exit(2)

        if not (test_ttymode or test_nottymode or test_logging):
                print >> sys.stderr, \
                    "must specify one or more of -t, -T or -l"
                sys.exit(2)

        if len(argv) == 1:
                output_file = open(argv[0], "w")
        elif len(argv) > 1:
                print >> sys.stderr, "too many arguments"
                sys.exit(2)
        else:
                output_file = sys.stdout

        try:
                if test_ttymode:
                        print >> output_file, "---test_ttymode---"
                        print >> output_file, ("-" * 60)
                        printengine.test_posix_printengine(output_file, True)
                if test_nottymode:
                        print >> output_file, "---test_nottymode---"
                        print >> output_file, ("-" * 60)
                        printengine.test_posix_printengine(output_file, False)
                if test_logging:
                        print >> output_file, "---test_logging---"
                        print >> output_file, ("-" * 60)
                        printengine.test_logging_printengine(output_file)
        except printengine.PrintEngineException, e:
                print >> sys.stderr, e
                sys.exit(1)
        except:
                traceback.print_exc()
                sys.exit(99)
        sys.exit(0)
