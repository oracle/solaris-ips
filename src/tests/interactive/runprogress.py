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
# Copyright (c) 2014, 2020, Oracle and/or its affiliates. All rights reserved.
#

import sys
import getopt
import gettext
import locale
import pkg.client.progress as progress
import pkg.misc as misc

def parse_argv():
        misc.setlocale(locale.LC_ALL, "", None)
        gettext.install("pkg", "/usr/share/locale")

        gofast = False
        opts, argv = getopt.getopt(sys.argv[1:], "f")
        for (opt, arg) in opts:
                if opt == '-f':
                        gofast = True
                else:
                        sys.exit(2)

        trackers = {
            "null": progress.NullProgressTracker,
            "func": progress.FunctionProgressTracker,
            "fancy": progress.FancyUNIXProgressTracker,
            "cli": progress.CommandLineProgressTracker,
            "dot": progress.DotProgressTracker,
            "quiet": progress.QuietProgressTracker,
            "default": progress.FancyUNIXProgressTracker,
        }

        pts = []

        first = True
        while first or len(argv) > 0:
                first = False

                outputdevname = "/dev/stdout"
                if len(argv) >= 2 and argv[1] != "-":
                        outputdevname = argv[1]

                tname = "default"
                if len(argv) >= 1 and argv[0] != "-":
                        tname = argv[0]
                outputdev = open(outputdevname, "w")

                # Get a reference to the tracker class
                try:
                        trackerclass = trackers[tname]
                except KeyError:
                        print("unknown tracker {0}".format(argv[0]))
                        sys.exit(2)

                try:
                        st = trackerclass(output_file=outputdev)
                except TypeError:
                        st = trackerclass()
                pts.append(st)

                print("Created {0} progress tracker on {1}".format(
                    trackerclass.__name__, outputdevname))
                argv = argv[2:]

        if len(pts) > 1:
                t = progress.MultiProgressTracker(pts)
        else:
                t = pts[0]
        return (t, gofast)


#
# This utility is a useful aid in developing or tweaking progress trackers.
# Arguments are passed in tuples of <trackername> <outputfile>.  The
# multi-progress tracker will be used if multiple trackers are specified.  '-'
# can be used to set an argument to its default value.
#
# Example: python runprogress.py - - cli /tmp/outfile
#
# This will create the default tracker on the default device (/dev/stdout)
# and also a CommandLineProgressTracker outputting to /tmp/outfile.
# Happy hacking.
#
if __name__ == "__main__":
        try:
                (_tracker, _gofast) = parse_argv()
                progress.test_progress_tracker(_tracker, gofast=_gofast)
        except progress.ProgressTrackerException as e:
                print("Error: {0}".format(e), file=sys.stderr)
                sys.exit(1)
        sys.exit(0)

