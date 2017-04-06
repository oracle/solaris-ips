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
# Copyright (c) 2010, 2015, Oracle and/or its affiliates. All rights reserved.
#

import logging
import os
import six
import sys

from pkg.lint.base import DuplicateLintedAttrException, linted

# a set of lint messages that can be produced.
DEBUG, INFO, WARNING, ERROR, CRITICAL = range(5)

LEVELS = {
    "DEBUG": DEBUG,
    "INFO": INFO,
    "WARNING": WARNING,
    "ERROR": ERROR,
    "CRITICAL": CRITICAL,
    # we are our own reverse map
    DEBUG: "DEBUG",
    INFO: "INFO",
    WARNING: "WARNING",
    ERROR: "ERROR",
    CRITICAL: "CRITICAL"
    }

class LintMessage(object):
        """A base class for all lint messages."""

        msg = ""
        def __init__(self, msg, level=INFO, producer="unknown", msgid=None):
                self.msg = msg
                self.level = level
                self.producer = producer
                self.msgid = msgid

        def __str__(self):
                return str(self.msg)


class TrackerHandler(logging.StreamHandler):
        """"Inspect a given pkg.client.progress.ProgressTracker, telling it
        to flush, before emitting output."""

        def __init__(self, tracker, strm=None):
                logging.StreamHandler.__init__(self, strm)

                if os.isatty(sys.stderr.fileno()) and \
                    os.isatty(sys.stdout.fileno()):
                        self.write_crs = True
                else:
                        self.write_crs = False
                self.tracker = tracker

        def emit(self, record):
                if self.write_crs and self.tracker:
                        self.tracker.flush()
                logging.StreamHandler.emit(self, record)


class LogFormatter(object):
        """A class that formats log messages."""

        def __init__(self, tracker=None, level=INFO):
                self._level = level

                # install our own logger, writing to stderr
                self.logger = logging.getLogger("pkglint_checks")

                self._th = TrackerHandler(tracker, strm=sys.stderr)
                self.logger.setLevel(logging.INFO)
                self._th.setLevel(logging.INFO)
                self.logger.addHandler(self._th)
                self.emitted = False

                # the action and manifest we expect messages from. See advise()
                self.action = None
                self.manifest = None

                # when the logger is using an engine, the engine registers
                # itself here
                self.engine = None

        # setters/getters for the tracker being used, adding that
        # to our private log handler
        def _get_tracker(self):
                return self._th.tracker

        def _set_tracker(self, value):
                self._th.tracker = value

        def _del_tracker(self):
                del self._th.tracker

        # setters/getters for log level to allow us to set
        # string values for what's always stored as an integer
        def _get_level(self):
                return self._level

        def _set_level(self, value):
                if isinstance(value, str):
                        if value.upper() not in LEVELS:
                                raise ValueError(
                                    _("{value} is not a valid level").format(
                                    **value))
                        self._level = LEVELS[value]
                else:
                        self._level = value

        def _del_level(self):
                del self._level

        level = property(_get_level, _set_level, _del_level)
        tracker = property(_get_tracker, _set_tracker, _del_tracker)

        # convenience methods to log messages
        def debug(self, message, msgid=None, ignore_linted=False):
                self.format(LintMessage(message, level=DEBUG, msgid=msgid),
                    ignore_linted=ignore_linted)

        def info(self, message, msgid=None, ignore_linted=False):
                self.format(LintMessage(message, level=INFO, msgid=msgid),
                    ignore_linted=ignore_linted)

        def warning(self, message, msgid=None, ignore_linted=False):
                self.format(LintMessage(message, level=WARNING, msgid=msgid),
                    ignore_linted=ignore_linted)

        def error(self, message, msgid=None, ignore_linted=False):
                self.format(LintMessage(message, level=ERROR, msgid=msgid),
                    ignore_linted=ignore_linted)

        def critical(self, message, msgid=None, ignore_linted=False):
                self.format(LintMessage(message, level=CRITICAL, msgid=msgid),
                    ignore_linted=ignore_linted)

        def open(self):
                """Start a new log file"""
                pass

        def format(self, message):
                """Given a LintMessage message, format that object
                appropriately."""
                pass

        def close(self):
                """End a log file"""
                pass

        def produced_lint_msgs(self):
                """Called to determine if this logger produced any lint
                messages at a level >= its log level."""
                return self.emitted

        def advise(self, action=None, manifest=None):
                """Called to tell the logger to expect lint messages concerning
                the given action and/or manifest."""
                if action:
                        self.action = action
                if manifest:
                        self.manifest = manifest


class PlainLogFormatter(LogFormatter):
        """A basic log formatter, just prints the message."""

        def format(self, msg, ignore_linted=False):

                if not isinstance(msg, LintMessage):
                        self.logger.warning(msg)
                        self.emitted = True
                        return

                if msg.level >= self._level:
                        if not msg.msgid:
                                msg.msgid = "unknown"

                        # Format the message level and message identifier
                        key = "{0} {1}".format(LEVELS[msg.level], msg.msgid)
                        if not ignore_linted:
                                linted_flag = False
                                try:
                                        linted_flag = linted(action=self.action,
                                            manifest=self.manifest,
                                            lint_id=msg.msgid)
                                except DuplicateLintedAttrException as err:
                                        lint_key = ("{0} pkglint001.6".format(
                                            LEVELS[ERROR]))
                                        self.logger.warning("{0}{1}".format(
                                            lint_key.ljust(34),
                                            _("Logging error: {0}").format(
                                            err)))

                                if linted_flag:
                                        # we may have asked not to report errors
                                        # that have been marked as pkg.linted
                                        if self.engine:
                                                report = self.engine.get_param(
                                                    "pkglint001.5.report-linted")
                                                if report and \
                                                    report.lower() == "false":
                                                        return
                                        key = ("{0} pkglint001.5".format(
                                            LEVELS[INFO]))
                                        linted_msg = _(
                                            "Linted message: {id}  "
                                            "{msg}").format(
                                            id=msg.msgid, msg=msg)
                                        self.logger.warning("{0}{1}".format(
                                        key.ljust(34), linted_msg))
                                        return

                        self.logger.warning("{0}{1}".format(key.ljust(34),
                            msg.msg))

                        # We only treat errors, and criticals as being worthy
                        # of a flag (pkglint returns non-zero if self.emitted)
                        if msg.level > WARNING:
                                self.emitted = True
