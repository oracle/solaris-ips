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
# Copyright (c) 2009, 2015, Oracle and/or its affiliates. All rights reserved.
#

# __str__ methods defined for subclasses of IndexError should be defined
# for the server implementations. If the client needs different messages
# displayed, catch the exception on the client side and display a custom
# message.

class IndexingException(Exception):
        """The base class for all exceptions that can occur while indexing."""

        def __init__(self, cause):
                self.cause = cause


class InconsistentIndexException(IndexingException):
        """This is used when the existing index is found to have inconsistent
        versions."""

        def __str__(self):
                return "Index corrupted, remove all files and " \
                    "rebuild from scratch by clearing out {0} " \
                    " and restarting the depot.".format(self.cause)


class IndexLockedException(IndexingException):
        """This is used when an attempt to modify an index locked by another
        thread or process is made."""

        def __init__(self, hostname=None, pid=None):
                IndexingException.__init__(self, None)
                self.hostname = hostname
                self.pid = pid

        def __str__(self):
                if self.pid is not None:
                        # Used even if hostname is undefined.
                        return _("The search index cannot be modified as it "
                            "is currently in use by another process: "
                            "pid {pid} on {host}.").format(
                            pid=self.pid, host=self.hostname)
                return _("The search index cannot be modified as it is "
                    "currently in use by another process.")


class ProblematicPermissionsIndexException(IndexingException):
        """This is used when the indexer is unable to create, move, or remove
        files or directories it should be able to."""

        def __str__(self):
                return "Could not remove or create " \
                    "{0} because of\nincorrect " \
                    "permissions. Please correct this issue then " \
                    "rebuild the index.".format(self.cause)

class NoIndexException(Exception):
        """This is used when a search is executed while no index exists."""

        def __init__(self, index_dir):
                self.index_dir = index_dir

        def __str__(self):
                return "Could not find index to search, looked in: " \
                    "{0}".format(self.index_dir)

class IncorrectIndexFileHash(Exception):
        """This is used when the index hash value doesn't match the hash of the
        packages installed in the image."""

        def __init__(self, existing_val, incoming_val):
                Exception.__init__(self)
                self.ev = existing_val
                self.iv = incoming_val

        def __str__(self):
                return "existing_val was:{0}\nincoming_val was:{1}".format(
                    self.ev, self.iv)
