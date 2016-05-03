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
# Copyright (c) 2007, 2016, Oracle and/or its affiliates. All rights reserved.
#

# Missing docstring; pylint: disable=C0111

import logging
import os
import sys

__all__ = ["global_settings"]

class _LogFilter(logging.Filter):
        def __init__(self, max_level=logging.CRITICAL):
                logging.Filter.__init__(self)
                self.max_level = max_level

        def filter(self, record):
                return record.levelno <= self.max_level


class _StreamHandler(logging.StreamHandler):
        """Simple subclass to ignore exceptions raised during logging output."""

        def handleError(self, record):
                # Ignore exceptions raised during output to stdout/stderr.
                return


class GlobalSettings(object):
        """ This class defines settings which are global
            to the client instance """

        def __init__(self):
                object.__init__(self)
                self.__info_log_handler = None
                self.__error_log_handler = None
                self.__verbose = False

                #
                # These properties allow the client to describe how it
                # has been asked to behave with respect to output.  This
                # allows subprocess invocations (e.g. for linked images) to
                # discover from the global settings how they are expected
                # to behave.
                #
                self.client_output_verbose = 0
                self.client_output_quiet = False
                self.client_output_parsable_version = None
                self.client_no_network_cache = False

                # runid, used by the pkg.1 client and the linked image
                # subsystem when when generating temporary files.
                self.client_runid = os.getpid()

                # file descriptor used by ProgressTracker classes when running
                # "pkg remote" to indicate progress back to the parent/client
                # process.
                self.client_output_progfd = None

                # concurrency value used for linked image recursion
                self.client_concurrency_set = False
                self.client_concurrency_default = 1
                self.client_concurrency = self.client_concurrency_default
                try:
                        self.client_concurrency = int(os.environ.get(
                            "PKG_CONCURRENCY",
                            self.client_concurrency_default))
                        if "PKG_CONCURRENCY" in os.environ:
                                self.client_concurrency_set = True
                        # remove PKG_CONCURRENCY from the environment so child
                        # processes don't inherit it.
                        os.environ.pop("PKG_CONCURRENCY", None)
                except ValueError:
                        pass

                self.client_name = None
                self.client_args = sys.argv[:]
                # Default maximum number of redirects received before
                # aborting a connection.
                self.pkg_client_max_redirect_default = 5
                # Default number of retries per-host
                self.pkg_client_max_timeout_default = 4
                # Default number of seconds to give up if not connected
                self.pkg_client_connect_timeout_default = 60
                # Default number of seconds beneath low-speed limit before
                # giving up.
                self.pkg_client_lowspeed_timeout_default = 30
                # Minimum bytes/sec before client thinks about giving up
                # on connection.
                self.pkg_client_lowspeed_limit = 1024
                # Maximum number of transient errors before we abort an
                # endpoint.
                self.pkg_client_max_consecutive_error_default = 4

                # The location within the image of the cache for pkg.sysrepo(1M)
                self.sysrepo_pub_cache_path = \
                    "var/cache/pkg/sysrepo_pub_cache.dat"

                try:
                        # Maximum number of timeouts before client gives up.
                        self.PKG_CLIENT_MAX_TIMEOUT = int(os.environ.get(
                            "PKG_CLIENT_MAX_TIMEOUT",
                            self.pkg_client_max_timeout_default))
                except ValueError:
                        self.PKG_CLIENT_MAX_TIMEOUT = \
                            self.pkg_client_max_timeout_default
                try:
                        # Number of seconds trying to connect before client
                        # aborts.
                        self.PKG_CLIENT_CONNECT_TIMEOUT = int(os.environ.get(
                            "PKG_CLIENT_CONNECT_TIMEOUT",
                            self.pkg_client_connect_timeout_default))
                except ValueError:
                        self.PKG_CLIENT_CONNECT_TIMEOUT = \
                            self.pkg_client_connect_timeout_default
                try:
                        # Number of seconds below lowspeed limit before
                        # transaction is aborted.
                        self.PKG_CLIENT_LOWSPEED_TIMEOUT = int(os.environ.get(
                            "PKG_CLIENT_LOWSPEED_TIMEOUT",
                            self.pkg_client_lowspeed_timeout_default))
                except ValueError:
                        self.PKG_CLIENT_LOWSPEED_TIMEOUT = \
                            self.pkg_client_lowspeed_timeout_default
                try:
                        # Number of transient errors before transaction
                        # is aborted.
                        self.PKG_CLIENT_MAX_CONSECUTIVE_ERROR = int(
                            os.environ.get("PKG_CLIENT_MAX_CONSECUTIVE_ERROR",
                            self.pkg_client_max_consecutive_error_default))
                except ValueError:
                        self.PKG_CLIENT_MAX_CONSECUTIVE_ERROR = \
                            self.pkg_client_max_consecutive_error_default
                try:
                        # Number of redirects before a connection is
                        # aborted.
                        self.PKG_CLIENT_MAX_REDIRECT = int(
                            os.environ.get("PKG_CLIENT_MAX_REDIRECT",
                            self.pkg_client_max_redirect_default))
                except ValueError:
                        self.PKG_CLIENT_MAX_REDIRECT = \
                            self.pkg_client_max_redirect_default
                self.reset_logging()

        def __get_error_log_handler(self):
                return self.__error_log_handler

        def __get_info_log_handler(self):
                return self.__info_log_handler

        def __get_verbose(self):
                return self.__verbose

        def __set_error_log_handler(self, val):
                logger = logging.getLogger("pkg")
                if self.__error_log_handler:
                        logger.removeHandler(self.__error_log_handler)
                self.__error_log_handler = val
                if val:
                        logger.addHandler(val)

        def __set_info_log_handler(self, val):
                logger = logging.getLogger("pkg")
                if self.__info_log_handler:
                        logger.removeHandler(self.__info_log_handler)
                self.__info_log_handler = val
                if val:
                        logger.addHandler(val)

        def __set_verbose(self, val):
                if self.__info_log_handler:
                        if val:
                                level = logging.DEBUG
                        else:
                                level = logging.INFO
                        self.__info_log_handler.setLevel(level)
                self.__verbose = val

        @property
        def logger(self):
		# Method could be a function; pylint: disable=R0201
                return logging.getLogger("pkg")

        def reset_logging(self):
                """Resets client logging to its default state.  This will cause
                all logging.INFO entries to go to sys.stdout, and all entries of
                logging.WARNING or higher to go to sys.stderr."""

                logger = logging.getLogger("pkg")
                logger.setLevel(logging.DEBUG)

                # Don't pass messages that are rejected to the root logger.
                logger.propagate = 0

                # By default, log all informational messages, but not warnings
                # and above to stdout.
                info_h = _StreamHandler(sys.stdout)

                # Minimum logging level for informational messages.
                if self.verbose:
                        info_h.setLevel(logging.DEBUG)
                else:
                        info_h.setLevel(logging.INFO)

                log_fmt = logging.Formatter()

                # Enforce maximum logging level for informational messages.
                info_f = _LogFilter(logging.INFO)
                info_h.addFilter(info_f)
                info_h.setFormatter(log_fmt)
                logger.addHandler(info_h)

                # By default, log all warnings and above to stderr.
                error_h = _StreamHandler(sys.stderr)
                error_h.setFormatter(log_fmt)
                error_h.setLevel(logging.WARNING)
                logger.addHandler(error_h)

                # Stash the handles so they can be removed later.
                self.info_log_handler = info_h
                self.error_log_handler = error_h

        error_log_handler = property(__get_error_log_handler,
            __set_error_log_handler)

        info_log_handler = property(__get_info_log_handler,
            __set_info_log_handler)

        verbose = property(__get_verbose, __set_verbose)


global_settings = GlobalSettings()
