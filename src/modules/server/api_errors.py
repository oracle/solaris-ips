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

class ApiException(Exception):
        """Base exception class for all server.api exceptions."""
        def __init__(self, *args):
                Exception.__init__(self, *args)
                if args:
                        self.data = args[0]

        def __str__(self):
                return str(self.data)


class VersionException(ApiException):
        """Exception used to indicate that the client's requested api version
        is not supported.
        """
        def __init__(self, expected_version, received_version):
                ApiException.__init__(self)
                self.expected_version = expected_version
                self.received_version = received_version

        def __str__(self):
                return "Incompatible API version '{0}' specified; " \
                    "expected: '{1}'.".format(self.received_version,
                    self.expected_version)


class RedirectException(ApiException):
        """Used to indicate that the client should be redirected to a new
        URI.
        """
        pass


class UnrecognizedOptionsToInfo(ApiException):
        def __init__(self, opts):
                ApiException.__init__(self)
                self._opts = opts

        def __str__(self):
                s = _("Info does not recognize the following options: {0}").format(
                    ", ".join(str(o) for o in self._opts))
                return s
