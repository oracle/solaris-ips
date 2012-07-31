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

# Copyright (c) 2012, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pty
import shutil
import sys
import tempfile
import threading
import time
import unittest
import StringIO

import pkg.fmri as fmri
import pkg.client.progress as progress
import pkg.client.printengine as printengine


class TestTrackerItem(pkg5unittest.Pkg5TestCase):
        def test_reset(self):
                """Test reset of a TrackerItem."""
                pi = progress.TrackerItem("testitem")
                pi.items = 10
                pi.reset()
                self.assert_(pi.items == 0)

        def test_str(self):
                """Test str() of a TrackerItem."""
                pi = progress.TrackerItem("testitem")
                pi.items = 10
                str(pi)

        def test_elapsed(self):
                """Test TrackerItem elapsed() functionality."""
                pi = progress.TrackerItem("testitem")
                # special case before items is set
                self.assert_(pi.elapsed() == 0.0)
                pi.items = 100
                time.sleep(0.20)
                # should work before done()
                self.assert_(pi.elapsed() >= 0.10)
                pi.done()
                # should work after done()
                self.assert_(pi.elapsed() >= 0.10)


class TestGoalTrackerItem(pkg5unittest.Pkg5TestCase):
        def test_item_before_goal(self):
                """Items must not be able to be set before goal is set."""
                def doit():
                        pi.items = 3
                pi = progress.GoalTrackerItem("testitem")
                # check can't set items before goal is set
                self.assertRaises(RuntimeError, doit)
                pi.goalitems = 100
                pi.items = 10
                pi.reset()
                self.assertRaises(RuntimeError, doit)

        def test_elapsed(self):
                """Test GoalTrackerItem elapsed() functionality."""
                pi = progress.GoalTrackerItem("testitem")
                # special case before goal is set
                self.assert_(pi.elapsed() == 0.0)
                pi.goalitems = 100
                self.assert_(pi.elapsed() == 0.0)
                pi.items = 100
                time.sleep(0.20)
                # should work before done()
                self.assert_(pi.elapsed() >= 0.10)
                pi.done()
                # should work after done()
                self.assert_(pi.elapsed() >= 0.10)

        def test_pair(self):
                """Test that pair() gives proper results."""
                pi = progress.GoalTrackerItem("testitem")
                # special case before goal is set
                self.assertEqual(pi.pair(), "0/0")
                pi.goalitems = 100
                self.assertEqual(pi.pair(), "  0/100")
                pi.items = 100
                self.assertEqual(pi.pair(), "100/100")
                pi.done()
                # should work after done()
                self.assertEqual(pi.pair(), "100/100")

        def test_pairplus1(self):
                """Test that pairplus1() gives proper results."""
                pi = progress.GoalTrackerItem("testitem")
                # special case before goal is set
                self.assertEqual(pi.pairplus1(), "1/1")
                pi.goalitems = 100
                self.assertEqual(pi.pairplus1(), "  1/100")
                pi.items = 100
                self.assertEqual(pi.pairplus1(), "100/100")
                pi.done()
                # should work after done()
                self.assertEqual(pi.pairplus1(), "100/100")

        def test_pctdone(self):
                """Test that pctdone() returns correct values."""
                pi = progress.GoalTrackerItem("testitem")
                # special case before goal is set
                self.assertEqual(pi.pctdone(), 0)
                pi.goalitems = 100
                self.assertEqual(pi.pctdone(), 0)
                pi.items = 50
                self.assertEqual(int(pi.pctdone()), 50)
                pi.items = 100
                self.assertEqual(int(pi.pctdone()), 100)
                pi.done()
                # should work after done()
                self.assertEqual(int(pi.pctdone()), 100)

        def test_metgoal(self):
                """Test that metgoal() works properly."""
                pi = progress.GoalTrackerItem("testitem")
                self.assertEqual(pi.metgoal(), True)
                pi.goalitems = 1
                self.assertEqual(pi.metgoal(), False)
                pi.items += 1
                self.assertEqual(pi.metgoal(), True)
                pi.done()
                # should work after done()
                self.assertEqual(pi.metgoal(), True)

        def test_done(self):
                """Test that done() works properly."""
                pi = progress.GoalTrackerItem("testitem")
                pi.goalitems = 1
                self.assertRaises(AssertionError, pi.done)
                pi.done(goalcheck=False)


class TestSpeedEstimator(pkg5unittest.Pkg5TestCase):

        def test_basic(self):
                """Basic test of Speed Estimator functionality."""

                # make sure that we test all of the interval handling logic
                interval = progress.SpeedEstimator(0).INTERVAL
                time_to_test = interval * 2.5
                hunkspersec = 30
                hunktime = 1.0 / hunkspersec
                hunk = 1024
                goalbytes = time_to_test * hunkspersec * hunk

                #
                # Test that estimator won't give out estimates when constructed
                #
                sp = progress.SpeedEstimator(goalbytes)
                self.assert_(sp.get_speed_estimate() == None)
                self.assert_(sp.elapsed() == None)
                self.assert_(sp.get_final_speed() == None)

                timestamp = 1000.0

                #
                # Test again after starting, but before adding data
                #
                sp.start(timestamp)
                self.assert_(sp.get_speed_estimate() == None)
                self.assert_(sp.elapsed() == None)
                self.assert_(sp.get_final_speed() == None)

                #
                # We record transactions of one hunk each until there
                # are no more transactions left, and we claim that each
                # transaction took 0.01 second.  Therefore, the final speed
                # should be 100 * hunksize/second.
                #
                while goalbytes > 0:
                        est = sp.get_speed_estimate()
                        self.assert_(est is None or est > 0)
                        sp.newdata(hunk, timestamp)
                        goalbytes -= hunk
                        timestamp += hunktime

                self.assert_(sp.get_final_speed() is None)
                sp.done(timestamp)
                self.debug("-- final speed: %f" % sp.get_final_speed())
                self.debug("-- expected final speed: %f" % (hunk * hunkspersec))
                self.debug(str(sp))
                self.assert_(int(sp.get_final_speed()) == hunk * hunkspersec)

        def test_stall(self):
                """Test that the ProgressTracker correctly diagnoses a
                "stall" in the download process."""
                hunk = 1024
                timestamp = 1000.0
                goalbytes = 10 * hunk * hunk

                #
                # Play records at the estimator until it starts giving out
                # estimates.
                #
                sp = progress.SpeedEstimator(goalbytes)
                sp.start(timestamp)
                while sp.get_speed_estimate() == None:
                        sp.newdata(hunk, timestamp)
                        timestamp += 0.01

                #
                # Now jump the timestamp forward by a lot-- 1000 seconds-- much
                # longer than the interval inside the estimator.  We should see
                # it stop giving us estimates.
                #
                timestamp = 2000.0
                sp.newdata(hunk, timestamp)
                self.assert_(sp.get_speed_estimate() == None)

        def test_format_speed(self):
                """Test that format_speed works as expected."""
                hunk = 1024
                goalbytes = 10 * hunk * hunk
                sp = progress.SpeedEstimator(goalbytes)

                testdata = {
                    0:           "0B/s",
                    999:         "999B/s",
                    1000:        "1000B/s",
                    1024:        "1.0k/s",
                    10 * 1024:   "10.0k/s",
                    999 * 1024:  "999k/s",
                    1001 * 1024: "1001k/s",
                    1024 * 1024: "1.0M/s"
                }

                for (val, expected) in testdata.items():
                        str = sp.format_speed(val)
                        self.assert_(len(str) <= 7)
                        self.assert_(str == expected)


class TestFormatPair(pkg5unittest.Pkg5TestCase):

        def test_format_pair(self):
                """Test that format_pair works as expected."""
                testdata = [
                    ["%d", 0, 0, {},                   "0/0"],
                    ["%d", 0, 1, {},                   "0/1"],
                    ["%d", 1, 100, {},                 "  1/100"],
                    ["%d", 1000, 1000, {},             "1000/1000"],
                    ["%.1f", 0, 1000, {},              "   0.0/1000.0"],
                    ["%.1f", 1000, 1000, {},           "1000.0/1000.0"],
                    ["%.1f", 1012.512, 2000.912, {},   "1012.5/2000.9"],
                    ["%.1f", 20.32, 1000.23,
                        {"targetwidth": 6, "format2": "%d"},
                                                            "  20.3/1000.2"],
                    ["%.1f", 20.322, 1000.23,
                        {"targetwidth": 5, "format2": "%d"},
                                                            "  20/1000"],
                    ["%.1f", 20.322, 1000.23,
                        {"targetwidth": 4, "format2": "%d"},
                                                            "  20/1000"],
                    ["%.1f", 20.322, 99.23,
                        {"targetwidth": 5, "format2": "%d"},
                                                            "20.3/99.2"],
                    ["%.1f", 2032, 9923,
                        {"targetwidth": 5, "format2": "%d", "scale": 100},
                                                            "20.3/99.2"],
                ]
                for (formatstr, item, goal, kwargs, expresult) in testdata:
                        result = progress.format_pair(formatstr, item,
                            goal, **kwargs)
                        self.assertEqual(result, expresult,
                            "expected: %s != result: %s" % (expresult, result))


class TestProgressTrackers(pkg5unittest.Pkg5TestCase):

        def test_basic_trackers(self):
                """Basic testing of all trackers; reset, and then retest."""
                sio_c = StringIO.StringIO()
                sio_c2 = StringIO.StringIO()
                sio_f = StringIO.StringIO()
                sio_d = StringIO.StringIO()

                tc = progress.CommandLineProgressTracker(output_file=sio_c)
                tc2 = progress.CommandLineProgressTracker(output_file=sio_c2,
                    term_delay=1)
                tf = progress.FunctionProgressTracker(output_file=sio_f)
                td = progress.DotProgressTracker(output_file=sio_d)
                tq = progress.QuietProgressTracker()

                mt = progress.MultiProgressTracker([tc, tc2, tf, tq, td])

                # run everything twice; this exercises that after a
                # reset(), everything still works correctly.
                for x in [1, 2]:
                        progress.test_progress_tracker(mt, gofast=True)

                        self.assert_(len(sio_c.getvalue()) > 100)
                        self.assert_(len(sio_c2.getvalue()) > 100)
                        self.assert_(len(sio_f.getvalue()) > 100)
                        self.assert_(len(sio_d.getvalue()) > 1)
                        # check that dot only printed dots
                        self.assert_(
                            len(sio_d.getvalue()) * "." == sio_d.getvalue())

                        for f in [sio_c, sio_c2, sio_f, sio_d]:
                                f.seek(0)
                                f.truncate(0)

                        # Reset them all, and go again, as a test of reset().
                        mt.flush()
                        mt.reset()

        def __t_pty_tracker(self, trackerclass, **kwargs):
                def __drain(masterf):
                        while True:
                                termdata = masterf.read(1024)
                                if len(termdata) == 0:
                                        break

                #
                # - Allocate a pty
                # - Create a thread to drain off the master side; without
                #   this, the slave side will block when trying to write.
                # - Connect the prog tracker to the slave side
                # - Set it running
                #
                (master, slave) = pty.openpty()
                slavef = os.fdopen(slave, "w")
                masterf = os.fdopen(master, "r")

                t = threading.Thread(target=__drain, args=(masterf,))
                t.start()

                p = trackerclass(output_file=slavef, **kwargs)
                progress.test_progress_tracker(p, gofast=True)
                slavef.close()

                t.join()
                masterf.close()

        def test_fancy_unix_tracker(self):
                """Test the terminal-based tracker we have on a pty."""
                self.__t_pty_tracker(progress.FancyUNIXProgressTracker)

        def test_fancy_unix_tracker_bad_tty(self):
                """Try to make a terminal-based tracker on non-terminals."""
                f = StringIO.StringIO()
                self.assertRaises(progress.ProgressTrackerException,
                    progress.FancyUNIXProgressTracker, f)

                tpath = self.make_misc_files("testfile")
                f = open(tpath[0], "w")
                self.assertRaises(progress.ProgressTrackerException,
                    progress.FancyUNIXProgressTracker, f)

        def test_fancy_unix_tracker_termdelay(self):
                """Test the fancy tracker with term_delay customized."""
                self.__t_pty_tracker(progress.FancyUNIXProgressTracker,
                    term_delay=0.20)


class TestMultiProgressTracker(pkg5unittest.Pkg5TestCase):
        def test_multi(self):
                """Test basic multi functionality."""
                sio1 = StringIO.StringIO()
                sio2 = StringIO.StringIO()

                #
                # The FunctionProgressTracker is used here because its
                # output doesn't contain any timing information.  The
                # output of the two Function progress trackers can thus
                # be tested for equality.
                #
                t1 = progress.FunctionProgressTracker(output_file=sio1)
                t2 = progress.FunctionProgressTracker(output_file=sio2)
                mt = progress.MultiProgressTracker([t1, t2])
                progress.test_progress_tracker(mt, gofast=True)

                self.assert_(len(sio1.getvalue()) > 100)
                self.assert_(len(sio2.getvalue()) > 100)
                self.assertEqual(sio1.getvalue(), sio2.getvalue())

        def test_multi_init(self):
                """Can't construct a Multi with zero subsidiary trackers."""
                self.assertRaises(progress.ProgressTrackerException,
                    progress.MultiProgressTracker, [])

if __name__ == "__main__":
        unittest.main()
