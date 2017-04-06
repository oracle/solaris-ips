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
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import re
import shutil
import stat
import sys
import tempfile
import unittest

import pkg
import pkg.client.api_errors as apx
import pkg.client.history as history
import pkg.misc as misc
import pkg.portable as portable

class TestHistory(pkg5unittest.Pkg5TestCase):
        # This is to prevent setup() being called for each test.
        persistent_setup = True

        __scratch_dir = None

        __ip_before = """UNEVALUATED:
            +pkg:/SUNWgcc@3.4.3,5.11-0.95:20080807T162946Z"""

        __ip_after = \
            """None -> pkg:/SUNWgcc@3.4.3,5.11-0.95:20080807T162946Z
            None -> pkg:/SUNWbinutils@2.15,5.11-0.95:20080807T153728Z
            None"""

        __errors = [
            "Error 1",
            "Error 2",
            "Error 3"
        ]

        # Used to store the name of a history file across tests.
        __filename = None

        def setUp(self):
                """Prepare the test for execution.
                """
                pkg5unittest.Pkg5TestCase.setUp(self)

                self.__scratch_dir = tempfile.mkdtemp(dir=self.test_root)
                # Explicitly convert these to strings as they will be
                # converted by history to deal with minidom issues.
                self.__userid = str(portable.get_userid())
                self.__username = str(portable.get_username())
                self.__h = history.History(root_dir=self.__scratch_dir)
                self.__h.client_name = "pkg-test"

        def test_00_valid_operation(self):
                """Verify that operation information can be stored and
                retrieved.
                """
                h = self.__h
                self.assertEqual(os.path.join(self.__scratch_dir, "history"),
                    h.path)

                h.log_operation_start("install")
                self.__class__.__filename = os.path.basename(h.pathname)

                # Verify that a valid start time was set.
                misc.timestamp_to_time(h.operation_start_time)

                self.assertEqual("install", h.operation_name)
                self.assertEqual(self.__username, h.operation_username)
                self.assertEqual(self.__userid, h.operation_userid)

                h.operation_start_state = self.__ip_before
                self.assertEqual(self.__ip_before, h.operation_start_state)

                h.operation_end_state = self.__ip_after
                self.assertEqual(self.__ip_after, h.operation_end_state)

                h.operation_errors.extend(self.__errors)
                self.assertEqual(self.__errors, h.operation_errors)

                h.log_operation_end()

        def test_01_client_info(self):
                """Verify that the client information can be retrieved.
                """
                h = self.__h
                self.assertEqual("pkg-test", h.client_name)
                self.assertEqual(pkg.VERSION, h.client_version)
                # The contents can't really be verified (due to possible
                # platform differences for the first element), but there
                # should be something returned.
                self.assertTrue(h.client_args)

        def test_02_clear(self):
                """Verify that clear actually resets all transient values.
                """
                h = self.__h
                h.clear()
                self.assertEqual(None, h.client_name)
                self.assertEqual(None, h.client_version)
                self.assertFalse(h.client_args)
                self.assertEqual(None, h.operation_name)
                self.assertEqual(None, h.operation_username)
                self.assertEqual(None, h.operation_userid)
                self.assertEqual(None, h.operation_result)
                self.assertEqual(None, h.operation_start_time)
                self.assertEqual(None, h.operation_end_time)
                self.assertEqual(None, h.operation_start_state)
                self.assertEqual(None, h.operation_end_state)
                self.assertEqual(None, h.operation_errors)
                self.assertEqual(None, h.pathname)

        def test_03_client_load(self):
                """Verify that the saved history can be retrieved properly.
                """
                h = history.History(root_dir=self.__scratch_dir,
                    filename=self.__filename)
                # Verify that a valid start time and end time was set.
                misc.timestamp_to_time(h.operation_start_time)
                misc.timestamp_to_time(h.operation_end_time)

                self.assertEqual("install", h.operation_name)
                self.assertEqual(self.__username, h.operation_username)
                self.assertEqual(self.__userid, h.operation_userid)
                self.assertEqual(self.__ip_before, h.operation_start_state)
                self.assertEqual(self.__ip_after, h.operation_end_state)
                self.assertEqual(self.__errors, h.operation_errors)
                self.assertEqual(history.RESULT_SUCCEEDED, h.operation_result)

        def test_04_stacked_operations(self):
                """Verify that multiple operations can be stacked properly (in
                other words, that storage and retrieval works as expected).
                """

                op_stack = {
                    "operation-1": {
                        "start_state": "op-1-start",
                        "end_state": "op-1-end",
                        "result": history.RESULT_SUCCEEDED,
                    },
                    "operation-2": {
                        "start_state": "op-2-start",
                        "end_state": "op-2-end",
                        "result": history.RESULT_FAILED_UNKNOWN,
                    },
                    "operation-3": {
                        "start_state": "op-3-start",
                        "end_state": "op-3-end",
                        "result": history.RESULT_CANCELED,
                    },
                }
                h = self.__h
                h.client_name = "pkg-test"

                for op_name in sorted(op_stack.keys()):
                        h.log_operation_start(op_name)

                for op_name in sorted(op_stack.keys(), reverse=True):
                        op_data = op_stack[op_name]
                        h.operation_start_state = op_data["start_state"]
                        h.operation_end_state = op_data["end_state"]
                        h.log_operation_end(result=op_data["result"])

                # Now load all operation data that's been saved during testing
                # for comparison.
                loaded_ops = {}
                for entry in sorted(os.listdir(h.path)):
                        # Load the history entry.
                        he = history.History(root_dir=h.root_dir,
                            filename=entry)

                        loaded_ops[he.operation_name] = {
                                "start_state": he.operation_start_state,
                                "end_state": he.operation_end_state,
                                "result": he.operation_result
                        }

                # Now verify that each operation was saved in the stack and
                # that the correct data was written for each one.
                for op_name in op_stack.keys():
                        op_data = op_stack[op_name]
                        loaded_data = loaded_ops[op_name]
                        self.assertEqual(op_data, loaded_data)

        def test_05_discarded_operations(self):
                """Verify that discarded operations are not saved.
                """

                h = self.__h
                h.client_name = "pkg-test"

                for op_name in sorted(history.DISCARDED_OPERATIONS):
                        h.log_operation_start(op_name)
                        h.log_operation_end(history.RESULT_NOTHING_TO_DO)

                # Now load all operation data that's been saved during testing
                # for comparison.
                loaded_ops = []
                for entry in sorted(os.listdir(h.path)):
                        # Load the history entry.
                        he = history.History(root_dir=h.root_dir,
                            filename=entry)
                        loaded_ops.append(he.operation_name)

                # Now verify that none of the saved operations are one that
                # should have been discarded.
                for op_name in sorted(history.DISCARDED_OPERATIONS):
                        self.assertTrue(op_name not in loaded_ops)

        def test_06_purge_history(self):
                """Verify that purge() removes all history and creates a new
                history entry.
                """
                h = self.__h
                h.clear()
                h.client_name = "pkg-test"
                h.purge()

                expected_ops = [["purge-history", history.RESULT_SUCCEEDED]]

                # Now load all operation data to verify that only an entry
                # for purge-history remains and that it was successful.
                loaded_ops = []
                for entry in sorted(os.listdir(h.path)):
                        # Load the history entry.
                        he = history.History(root_dir=h.root_dir,
                            filename=entry)
                        loaded_ops.append([he.operation_name, he.operation_result])

                self.assertTrue(loaded_ops == expected_ops)

        def test_07_aborted_operations(self):
                """Verify that aborted operations are saved properly."""

                h = self.__h
                h.client_name = "pkg-test"

                for i in range(1, 4):
                        h.log_operation_start("operation-{0:d}".format(i))

                h.abort(history.RESULT_FAILED_BAD_REQUEST)

                # Now load all operation data that's been saved during testing
                # for comparison and verify the expected result was set for
                # each.
                loaded_ops = []
                for entry in sorted(os.listdir(h.path)):
                        # Load the history entry.
                        he = history.History(root_dir=h.root_dir,
                            filename=entry)

                        if he.operation_name != "purge-history":
                                loaded_ops.append([he.operation_name,
                                    he.operation_result])

                # There should be three operations: operation-1, operation-2,
                # and operation-3.
                self.assertTrue(len(loaded_ops) == 3)

                for op in loaded_ops:
                        op_name, op_result = op
                        self.assertTrue(re.match("operation-[123]", op_name))
                        self.assertEqual(op_result,
                            history.RESULT_FAILED_BAD_REQUEST)

        def test_08_bug_3540(self):
                """Ensure that corrupt History files raise a
                HistoryLoadException with parse_failure set to True.
                """

                # Overwrite first entry with bad data.
                h = self.__h
                entry = sorted(os.listdir(h.path))[0]
                f = open(os.path.join(h.path, entry), "w")
                f.write("<Invalid>")
                f.close()

                try:
                        he = history.History(root_dir=h.root_dir,
                            filename=entry)
                except apx.HistoryLoadException as e:
                        if not e.parse_failure:
                                raise
                        pass

        def test_09_bug_5153(self):
                """Verify that purge will not raise an exception if the History
                directory doesn't already exist as it will be re-created anyway.
                """
                h = self.__h
                shutil.rmtree(h.path)
                h.purge()

        def test_10_snapshots(self):
                """Verify that snapshot methods work as expected."""

                h = self.__h
                h.client_name = "Schrodinger"
                h.log_operation_start("start-bobcat-experiment")
                h.operation_start_state = "bobcat-alive-plus-poison-in-box"

                # Brought to you by Mr. Fusion.
                h.create_snapshot()

                # Is it alive, dead, or both after this error?  Only quantum
                # mechanics knows the answer for certain, but let us assume the
                # outcome isn't good.
                h.log_operation_error("radiation-detected")
                h.operation_end_state = "bobcat-dead"

                self.assertEqual(h.operation_start_state,
                    "bobcat-alive-plus-poison-in-box")

                # Since log_operation_error will automatically combine the error
                # with a stacktrace, the last line of the logged error has to be
                # checked for the error text instead.
                error = ("".join(h.operation_errors[0])).splitlines()
                self.assertEqual(error[-1], "radiation-detected")
                self.assertEqual(h.operation_end_state, "bobcat-dead")

                # No animals were permanently harmed during this experiment.
                h.restore_snapshot()

                self.assertEqual(h.operation_start_state,
                    "bobcat-alive-plus-poison-in-box")

                # Mysteriously, no radiation was detected...
                self.assertEqual(h.operation_errors, [])

                # The experiment isn't over yet.
                self.assertEqual(h.operation_end_state, None)

                # Success!
                h.operation_end_state = "bobcat-alive"

                # Discard our last snapshot.
                h.discard_snapshot()

                # Attempt to restore, which should have no effect.
                h.restore_snapshot()
                self.assertEqual(h.operation_end_state, "bobcat-alive")

                h.log_operation_end()

        def test_11_bug_8072(self):
                """Verify that a history file with unexpected start state, end
                state, and error data won't cause an exception."""

                bad_hist = b"""<?xml version="1.0" encoding="ascii"?>
<history>
  <client name="pkg" version="e827313523d8+">
    <args>
      <arg><![CDATA[/usr/bin/pkg]]></arg>
      <arg><![CDATA[-R]]></arg>
      <arg><![CDATA[/tmp/image]]></arg>
      <arg><![CDATA[install]]></arg>
      <arg><![CDATA[Django]]></arg>
    </args>
  </client>
  <operation end_time="20090409T165520Z" name="install"
      result="Failed, Out of Memory" start_time="20090409T165520Z" userid="101"
      username="username">
    <start_state></start_state>
    <end_state></end_state>
    <errors>
      <error></error>
    </errors>
  </operation>
</history>"""

                (fd1, path1) = tempfile.mkstemp(dir=self.__scratch_dir)
                os.write(fd1, bad_hist)

                # Load the history entry.
                he = history.History(root_dir=self.__scratch_dir,
                    filename=path1)

                self.assertEqual(he.operation_start_state, "None")
                self.assertEqual(he.operation_end_state, "None")
                self.assertEqual(he.operation_errors, [])

        def test_12_bug_9287(self):
                """Verify that the current exception stack won't be logged
                unless it is for the same exception the operation ended
                with."""

                h = self.__h

                # Test that an exception that occurs before an operation
                # starts won't be recorded if it is not the same exception
                # the operation ended with.

                # Clear history completely.
                h.purge()
                shutil.rmtree(h.path)

                # Populate the exception stack.
                try:
                        d = {}
                        d['nosuchkey']
                except KeyError:
                        pass

                h.log_operation_start("test-exceptions")
                e = AssertionError()
                h.log_operation_end(error=e)

                for entry in sorted(os.listdir(h.path)):
                        # Load the history entry.
                        he = history.History(root_dir=h.root_dir,
                            filename=entry)

                        # Verify that the right exception was logged.
                        for e in he.operation_errors:
                                self.assertNotEqual(e.find("AssertionError"),
                                    -1)

        def test_13_bug_11735(self):
                """Ensure that history files are created with appropriate
                permissions"""

                h = self.__h
                self.assertEqual(stat.S_IMODE(os.stat(h.path).st_mode),
                                 misc.PKG_DIR_MODE)

                entry = os.path.join(h.path, os.listdir(h.path)[0])
                self.assertEqual(stat.S_IMODE(os.stat(entry).st_mode),
                                 misc.PKG_FILE_MODE)


if __name__ == "__main__":
        unittest.main()
