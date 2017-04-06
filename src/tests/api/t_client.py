#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
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

# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import logging
import os
import six
import sys
import unittest

from pkg.client import global_settings
logger = global_settings.logger

class _LogFilter(logging.Filter):
        def __init__(self, max_level=logging.CRITICAL):
                logging.Filter.__init__(self)
                self.max_level = max_level

        def filter(self, record):
                return record.levelno <= self.max_level

class TestSettings(pkg5unittest.Pkg5TestCase):

        def test_logging(self):
                global_settings.client_name = "TestSettings"

                info_out = six.StringIO()
                error_out = six.StringIO()

                log_fmt = logging.Formatter()

                # Enforce maximum logging level for informational messages.
                info_h = logging.StreamHandler(info_out)
                info_t = _LogFilter(logging.INFO)
                info_h.addFilter(info_t)
                info_h.setFormatter(log_fmt)
                info_h.setLevel(logging.INFO)

                # Log all warnings and above to stderr.
                error_h = logging.StreamHandler(error_out)
                error_h.setFormatter(log_fmt)
                error_h.setLevel(logging.WARNING)

                global_settings.info_log_handler = info_h
                global_settings.error_log_handler = error_h

                # Log some messages.
                logger.debug("DEBUG")
                logger.info("INFO")
                logger.warning("WARNING")
                logger.error("ERROR")
                logger.critical("CRITICAL")

                # Now verify that the expected output was received (DEBUG
                # shouldn't be here due to log level).
                self.assertEqual(info_out.getvalue(), "INFO\n")
                self.assertEqual(error_out.getvalue(),
                    "WARNING\nERROR\nCRITICAL\n")

                # DEBUG should now be present in the info output.
                info_out.seek(0)
                info_h.setLevel(logging.DEBUG)
                logger.debug("DEBUG")
                self.assertEqual(info_out.getvalue(), "DEBUG\n")

                # Reset logging and verify info_out, error_out are no longer
                # set to receive messagse.
                global_settings.reset_logging()
                self.assertNotEqual(global_settings.info_log_handler, info_h)
                self.assertNotEqual(global_settings.error_log_handler, error_h)

                logging.shutdown()

if __name__ == "__main__":
        unittest.main()
