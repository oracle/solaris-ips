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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

# __str__ methods defined for subclasses of IndexError should be defined
# for the server implementations. If the client needs different messages
# displayed, catch the exception on the client side and display a custom
# message.

class IndexingException(Exception):
        """ The base class for all exceptions that can occur while indexing. """
        def __init__(self, cause):
                self.cause = cause

class IncorrectIndexFileHash(IndexingException):
        """This is used when file with a hash in it has more than one entry."""
        def __init__(self):
                IndexingException.__init__(self, None)

class InconsistentIndexException(IndexingException):
        """ This is used when the existing index is found to have inconsistent
        versions."""
        def __str__(self):
                return "Index corrupted, remove all files and " \
                    "rebuild from scratch by clearing out %s " \
                    " and restarting the depot." % self.cause

class PartialIndexingException(IndexingException):
        """ This is used when the directory the temporary files the indexer
        should write to already exists. """
        def __str__(self):
                return "Result of partial indexing found, " \
                    "please correct that before indexing anew. Could " \
                    "not make: %s because it " \
                    "already exists. Removing this directory and " \
                    "using the --rebuild-index flag should fix this " \
                    "problem." % self.cause

class ProblematicPermissionsIndexException(IndexingException):
        """ This is used when the indexer is unable to create, move, or remove
        files or directories it should be able to. """
        def __str__(self):
                return "Could not remove or create " \
                    "%s because of incorrect " \
                    "permissions. Please correct this issue then " \
                    "rebuild the index." % self.cause

class NoIndexException(Exception):
        """ This is used when a search is executed while no index exists. """
        def __init__(self, index_dir):
                self.index_dir = index_dir
        def __str__(self):
                return "Could not find index to search, looked in: %s" \
                    % self.index_dir

