#!/usr/bin/python2.4
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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import os

__all__ = ["global_settings"]

class GlobalSettings(object):
        """ This class defines settings which are global
            to the client instance """

        def __init__(self):
                object.__init__(self)
                self.client_name = None
                self.pkg_client_max_timeout_default = 4
                self.pkg_client_connect_timeout_default = 60
                self.pkg_client_lowspeed_timeout_default = 30
                # Minimum bytes/sec before client thinks about giving up
                # on connection.
                self.pkg_client_lowspeed_limit = 1024
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

global_settings = GlobalSettings()
