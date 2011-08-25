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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import random
import re
import shutil
import time
import unittest


class TestPkgHistory(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo1 = """
            open foo@1,5.11-0
            close """

        foo2 = """
            open foo@2,5.11-0
            close """

        bar1 = """
            open bar@1,5.11-0
            add depend type=incorporate fmri=pkg:/foo@1
            close """

        baz = """
            open baz@1,5.11-0
            add file tmp/baz mode=0555 owner=root group=bin path=/tmp/baz
            close"""

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2"])
                misc_files = [ "tmp/baz" ]
                self.make_misc_files(misc_files)

                rurl1 = self.dcs[1].get_repo_url()
                self.pkgsend_bulk(rurl1, (self.foo1, self.foo2, self.baz))

                # Ensure that the second repo's packages are exactly the same
                # as those in the first ... by duplicating the repo.
                d1dir = self.dcs[1].get_repodir()
                d2dir = self.dcs[2].get_repodir()
                self.copy_repository(d1dir, d2dir, { "test1": "test2" })
                self.dcs[2].get_repo(auto_create=True).rebuild()

                self.image_create(rurl1, prefix="test1")
                # add a few more entries to the history - we don't care
                # that these fail
                for item in ["cheese", "tomatoes", "bread", "pasta"]:
                            self.pkg("install %s" % item, exit=1)
                            time.sleep(1)
                self.pkg("install baz")
                self.pkg("refresh")

        def test_1_history_options(self):
                """Verify all history options are accepted or rejected as
                expected.
                """
                self.pkg("history")
                self.pkg("history -l")
                self.pkg("history -H")
                self.pkg("history -n 5")
                self.pkg("history -n foo", exit=2)
                self.pkg("history -n -5", exit=2)
                self.pkg("history -n 0", exit=2)
                self.pkg("history -lH", exit=2)
                self.pkg("history -t 2010-10-20T14:18:17 -n 1", exit=2)
                self.pkg("history -t 2010-10-20T14:18:17,rubbish", exit=1)
                self.pkg("history -t 'this is not a  time-stamp'", exit=1)
                self.pkg("history -t northis", exit=1)
                self.pkg("history -o time,command -l", exit=2)
                self.pkg("history -o time,time", exit=2)
                self.pkg("history -o unknow_column", exit=2)
                self.pkg("history -o time,command,finish", exit=2)
                self.pkg("history -o time,reason,finish", exit=2)

        def test_2_history_record(self):
                """Verify that all image operations that change an image are
                recorded as expected.
                """

                rurl2 = self.dcs[2].get_repo_url()
                commands = [
                    ("install foo@1", 0),
                    ("update", 0),
                    ("uninstall foo", 0),
                    ("set-publisher -O " + rurl2 + " test2", 0),
                    ("set-publisher -P test1", 0),
                    ("set-publisher -m " + rurl2 + " test1", 0),
                    ("set-publisher -M " + rurl2 + " test1", 0),
                    ("unset-publisher test2", 0),
                    ("rebuild-index", 0),
                    ("fix", 0)
                ]

                operations = [
                    "install",
                    "update",
                    "uninstall",
                    "add-publisher",
                    "update-publisher",
                    "remove-publisher",
                    "rebuild-index",
                    "fix"
                ]

                # remove a file in the image which will cause pkg fix to do
                # work, writing a history entry in the process
                img_file = os.path.join(self.get_img_path(), "tmp/baz")
                os.remove(img_file)

                for cmd, exit in commands:
                        self.pkg(cmd, exit=exit)

                self.pkg("history -H")
                o = self.output
                self.assert_(
                    re.search("START\s+", o.splitlines()[0]) == None)

                # Only the operation is listed in short format.
                for op in operations:
                        # Verify that each operation was recorded.
                        if o.find(op) == -1:
                                raise RuntimeError("Operation: %s wasn't "
                                    "recorded, o:%s" % (op, o))

                self.pkg("history -o start,command")
                o = self.output
                for cmd, exit in commands:
                        # Verify that each of the commands was recorded.
                        if o.find(" %s" % cmd) == -1:
                                raise RuntimeError("Command: %s wasn't recorded,"
                                    " o:%s" % (cmd, o))

                # Verify that a successful operation with no effect won't
                # be recorded.
                self.pkg("purge-history")
                self.pkg("refresh")
                self.pkg("history -l")
                self.assert_(" refresh" not in self.output)

                self.pkg("refresh --full")
                self.pkg("history -l")
                self.assert_(" refresh" in self.output)

        def test_3_purge_history(self):
                """Verify that the purge-history command works as expected.
                """
                self.pkg("purge-history")
                self.pkg("history -H")
                o = self.output
                # Ensure that the first item in history output is now
                # purge-history.
                self.assert_(
                    re.search("purge-history", o.splitlines()[0]) != None)

        def test_4_bug_4639(self):
                """Test that install and uninstall of non-existent packages
                both make the same history entry.
                """

                self.pkg("purge-history")
                self.pkg("uninstall doesnt_exist", exit=1)
                self.pkg("install doesnt_exist", exit=1)
                self.pkg("history -H -o start,operation,client,outcome,reason")
                o = self.output
                for l in o.splitlines():
                        tmp = l.split()
                        res = tmp[3]
                        reason = " ".join(tmp[4:])
                        if tmp[1] == "install" or tmp[1] == "uninstall":
                                self.assert_(reason == "Bad Request")
                        else:
                                self.assert_(tmp[1] in ("purge-history",
                                    "refresh-publishers"))

        def test_5_bug_5024(self):
                """Test that install and uninstall of non-existent packages
                both make the same history entry.
                """

                rurl1 = self.dcs[1].get_repo_url()
                self.pkgsend_bulk(rurl1, self.bar1)
                self.pkg("refresh")
                self.pkg("install bar")
                self.pkg("install foo")
                self.pkgsend_bulk(rurl1, self.foo2)
                self.pkg("refresh")
                self.pkg("purge-history")
                self.pkg("install foo@2", exit=1)
                self.pkg("history -H -o start,operation,client,outcome,reason")
                o = self.output
                for l in o.splitlines():
                        tmp = l.split()
                        ts = tmp[0]
                        res = tmp[3]
                        reason = " ".join(tmp[4:])
                        if tmp[1] == "install":
                                self.assert_(res == "Failed")
                                self.assert_(reason == "Constrained")
                        else:
                                self.assert_(tmp[1] in ("purge-history",
                                    "refresh-publishers"))

        def test_6_bug_3540(self):
                """Verify that corrupt history entries won't cause the client to
                exit abnormally.
                """
                # Overwrite first entry with bad data.
                hist_path = self.get_img_api_obj().img.history.path
                entry = sorted(os.listdir(hist_path))[0]
                f = open(os.path.join(hist_path, entry), "w")
                f.write("<Invalid>")
                f.close()
                self.pkg("history")

        def test_7_bug_5153(self):
                """Verify that an absent History directory will not cause the
                the client to exit with an error or traceback.
                """
                hist_path = self.get_img_api_obj().img.history.path
                shutil.rmtree(hist_path)
                self.pkg("history")

        def test_8_failed_record(self):
                """Verify that all failed image operations that change an image
                are recorded as expected.
                """

                commands = [
                    "install nosuchpackage",
                    "uninstall nosuchpackage",
                    "set-publisher -O http://test.invalid2 test2",
                    "set-publisher -O http://test.invalid1 test1",
                    "unset-publisher test3",
                ]

                operations = [
                    "install",
                    "uninstall",
                    "add-publisher",
                    "update-publisher",
                    "remove-publisher",
                ]

                self.pkg("purge-history")
                for cmd in commands:
                        self.pkg(cmd, exit=1)

                self.pkg("history -H")
                o = self.output
                self.assert_(
                    re.search("START\s+", o.splitlines()[0]) == None)

                # Only the operation is listed in short format.
                for op in operations:
                        # Verify that each operation was recorded as failing.
                        found_op = False
                        for line in o.splitlines():
                                if line.find(op) == -1:
                                        continue

                                found_op = True
                                if line.find("Failed") == -1:
                                        raise RuntimeError("Operation: %s "
                                            "wasn't recorded as failing, "
                                            "o:%s" % (op, l))
                                break

                        if not found_op:
                                raise RuntimeError("Operation: %s "
                                    "wasn't recorded, o:%s" % (op, o))

                # The actual commands are only found in long format.
                self.pkg("history -l")
                o = self.output
                for cmd in commands:
                        # Verify that each of the commands was recorded.
                        if o.find(" %s" % cmd) == -1:
                                raise RuntimeError("Command: %s wasn't recorded,"
                                    " o:%s" % (cmd, o))

        def test_9_history_limit(self):
                """Verify limiting the number of records to output
                """

                #
                # Make sure we have a nice number of entries with which to
                # experiment.
                #
                for i in xrange(5):
                        self.pkg("install pkg%d" % i, exit=1)
                self.pkg("history -Hn 3")
                self.assertEqual(len(self.output.splitlines()), 3)

                self.pkg("history -ln 3")
                lines = self.output.splitlines()
                nentries = len([l for l in lines if l.find("Operation:") >= 0])
                self.assertEqual(nentries, 3)

                hist_path = self.get_img_api_obj().img.history.path
                count = len(os.listdir(hist_path))

                # Asking for too many objects should return the full set
                self.pkg("history -Hn %d" % (count + 5))
                self.assertEqual(len(self.output.splitlines()), count)

        def test_10_history_columns(self):
                """Verify the -o option """                

                self.pkg("history -H -n 1")
                # START OPERATION CLIENT OUTCOME
                arr = self.output.split()
                known = {}
                known["start"] = arr[0]
                known["operation"] = arr[1]
                known["client"] = arr[2]
                known["outcome"] = arr[3]

                # Ensure we can obtain output for each column
                cols = ["be", "be_uuid", "client", "client_ver", "command",
                    "finish", "id", "new_be", "new_be_uuid", "operation",
                    "outcome", "reason", "snapshot", "start", "time", "user"]
                for col in cols:
                        self.pkg("history -H -n1 -o %s" % col)
                        self.assert_(self.output)
                        # if we've seen this column before, we can verify
                        # the -o output matches that field in the normal
                        # output.
                        if col in known:
                                self.assert_(self.output.strip() == known[col],
                                    "%s column output %s does not match %s" %
                                    (col, self.output, known[col]))

        def test_11_history_events(self):
                """ Verify the -t option, for discreet timestamps """

                self.pkg("history -H")
                output = self.output.splitlines()

                # create a dictionary of events, keyed by timestamp since we can
                # get several events per timestamp.
                events = {}
                for line in output:
                        fields = line.split()
                        timestamp = fields[0].strip()
                        operation = fields[1].strip()
                        if timestamp in events:
                                events[timestamp].append(operation)
                        else:
                                events[timestamp] = [operation]

                # verify we can retrieve each event
                for timestamp in events:                        
                        operations = set(events[timestamp])
                        self.pkg("history -H -t %s -o operation" % timestamp)
                        arr = self.output.splitlines()
                        found = set()
                        for item in arr:
                                found.add(item.strip())
                        self.assert_(found == operations,
                                    "%s does not equal %s for %s" %
                                    (found, operations, timestamp))
                
                # record timestamp and expected result for 3 random,
                # unique timestamps.  Since each timestamp can result in
                # multiple  events, we need to calculate how many events to
                # expect
                keys = events.keys()

                comma_events = ""
                expected_count = 0

                for ts in random.sample(keys, 3):
                        if not comma_events:
                                comma_events = ts
                        else:
                                comma_events = "%s,%s" % (comma_events, ts)
                        expected_count = expected_count + len(events[ts])

                self.pkg("history -H -t %s -o start,operation" % comma_events)
                output = self.output.splitlines()
                self.assert_(len(output) == expected_count,
                    "Expected %s events, got %s" % (expected_count,
                    len(output)))
                
                for line in output:
                        fields = line.split()
                        timestamp = fields[0].strip()
                        operation = fields[1].strip()
                        self.assert_(timestamp in events,
                            "Missing %s from %s" % (timestamp, events))
                        expected = events[timestamp]
                        self.assert_(operation in expected,
                            "Recorded operation %s at %s not in dictionary %s" %
                            (operation, timestamp, events))

                # verify that duplicate timestamps specified on command line
                # only output history for one instance of each timestamp
                multi_events = "%s,%s" % (comma_events, comma_events)
                self.pkg("history -H -t %s -o start,operation" % multi_events)
                output = self.output.splitlines()
                self.assert_(len(output) == expected_count,
                    "Expected %s events, got %s" % (expected_count,
                    len(output)))

        def test_12_history_range(self):
                """ Verify the -t option for ranges of timestamps """

                self.pkg("history -H")
                entire_output = self.output

                # verify that printing a very wide history range is equal to
                # printing all history entries. XXX we need to fix this in 2038
                self.pkg("history -H "
                    "-t 1970-01-01T00:00:00-2037-01-01T03:44:07")
                self.assert_(entire_output == self.output,
                    "large history range, %s not equal to %s" %
                    (entire_output, self.output))

                # checks to verify history ranges are tricky since one history
                # timestamp can correspond to more than one history entry.
                # To help with this, we build a dictionary keyed by timestamp
                # of history output
                entries = {}
                for line in entire_output.splitlines():
                        timestamp = line.strip().split()[0]
                        if timestamp in entries:
                                entries[timestamp].append(line)
                        else:
                                entries[timestamp] = [line]

                single_ts = entries.keys()[
                    random.randint(0, len(entries) - 1)]

                # verify a range specifying the same timestamp twice
                # is the same as printing just that timestamp
                self.pkg("history -H -t %s" % single_ts)
                single_entry_output = self.output
                self.pkg("history -H -t %s-%s" % (single_ts, single_ts))
                self.assert_(single_entry_output == self.output,
                    "%s does not equal %s" % (single_entry_output, self.output))

                # verify a random range taken from the history is correct
                timestamps = entries.keys()
                timestamps.sort()

                # get two random indices from our list of timestamps
                start_ts = None
                end_ts = None
                attempts = 0
                last_index = len(timestamps) - 1

                while start_ts == end_ts and attempts < 10:
                        start_ts = timestamps[random.randint(0, last_index)]
                        end_ts = timestamps[
                            random.randint(timestamps.index(start_ts),
                            last_index)]
                        attempts = attempts + 1

                self.assert_(start_ts != end_ts,
                    "Unable to test pkg history range, %s == %s" %
                    (start_ts, end_ts))

                self.pkg("history -H -t %s-%s" % (start_ts, end_ts))
                range_lines = self.output.splitlines()
                range_timestamps = []

                self.assert_(len(range_lines) >= 1, "No output from pkg history"
                    " -t %s-%s" % (start_ts, end_ts))

                # for each history line in the range output, ensure that it
                # matches timestamps that we stored from the main history output
                for line in range_lines:
                        ts = line.strip().split()[0]
                        self.assert_(line in entries[ts],
                            "%s does not appear in %s" % (line, entries[ts]))                        
                        range_timestamps.append(ts)

                # determine the reverse. That is, for each entry in the
                # list of ranges we expect taken from the entire history output,
                # verify that entry was printed as part of
                # pkg history -t <range>
                start_index = timestamps.index(start_ts)
                end_index = timestamps.index(end_ts)
                # ranges are inclusive
                if end_index != len(timestamps):
                        end_index = end_index + 1
                for ts in timestamps[start_index:end_index]:
                        for line in entries[ts]:
                                self.assert_(line in range_lines,
                                    "expected range history entry not found "
                                    "in output:\n"
                                    "Line: %s\n"
                                    "Range output %s\n"
                                    "Entire output %s" %
                                    (line, "\n".join(range_lines),
                                    entire_output))

                # now verify that each timestamp we collected does indeed fall
                # within that range
                for ts in range_timestamps:
                        self.assert_(ts >= start_ts, "%s is not >= %s" %
                            (ts, start_ts))
                        self.assert_(ts <= end_ts, "%s is not <= %s" %
                            (ts, end_ts))

        def test_13_bug_17418(self):
                """Verify we can get history for an operation that ran for a
                long time"""

                image_path = self.get_img_path()
                history_dir = os.path.sep.join([image_path, "var", "pkg",
                    "history"])
                dirlist = os.listdir(history_dir)
                dirlist.sort()

                # create a new history xml file, changing its start time to
                # 2009
                latest = os.path.join(history_dir, dirlist[-1])
                new_file = re.sub(".xml", "99.xml", latest)
                outfile = file(os.path.join(history_dir, new_file), "w")
                for line in file(latest):
                        out = re.sub("start_time=\"20..", "start_time=\"2009",
                            line)
                        outfile.write(out)
                outfile.close()

                self.pkg("history -n 1")

if __name__ == "__main__":
        unittest.main()
