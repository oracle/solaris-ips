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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
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
                    "rebuild from scratch by clearing out %s " \
                    " and restarting the depot." % self.cause

class PartialIndexingException(IndexingException):
        """This is used when the directory the temporary files the indexer
        should write to already exists."""

        def __str__(self):
                return "Unable to build or update search indices. Result of " \
                    "partial indexing found:%s. Please remove this directory "\
                    "and start a depot with the --refresh-index flag." % \
                    self.cause

class ProblematicPermissionsIndexException(IndexingException):
        """This is used when the indexer is unable to create, move, or remove
        files or directories it should be able to."""

        def __str__(self):
                return "Could not remove or create " \
                    "%s because of\nincorrect " \
                    "permissions. Please correct this issue then " \
                    "rebuild the index." % self.cause

class NoIndexException(Exception):
        """This is used when a search is executed while no index exists."""

        def __init__(self, index_dir):
                self.index_dir = index_dir
        def __str__(self):
                return "Could not find index to search, looked in: %s" \
                    % self.index_dir

class IncorrectIndexFileHash(Exception):
        """This is used when the index hash value doesn't match the hash of the
        packages installed in the image."""

        def __init__(self, existing_val, incoming_val):
                Exception.__init__(self)
                self.ev = existing_val
                self.iv = incoming_val

        def __str__(self):
                return "existing_val was:%s\nincoming_val was:%s" % \
                    (self.ev, self.iv)

class MainDictParsingException(Exception):
        """This is used when an error occurred while parsing the main search
        dictionary file."""

        def __init__(self, split_chars, unquote_list, line, file_pos):
                self.split_chars = split_chars
                self.unquote_list = unquote_list
                self.line = line
                self.file_pos = file_pos
                
        
class EmptyUnquoteList(MainDictParsingException):
        """This is used when the function to parse the main dictionary file
        wasn't given enough values in its unquote_list argument."""

        def __init__(self, split_chars, line):
                Exception.__init__(self, split_chars, None, line)

        def __str__(self):
                return _("Got an empty unquote_list while indexing. split_chars"
                    " was %(sc)s and line was %(l)s" %
                    { "sc": self.split_chars, "l": self.line })

class EmptyMainDictLine(MainDictParsingException):
        """This is used when a blank line in the main dictionary file was
        encountered."""

        def __init__(self, split_chars, unquote_list):
                Exception.__init__(self, split_chars, unquote_list, None)

        def __str__(self):
                return _("Had an empty line in the main dictionary. split_chars"
                    " is %(sc)s and unquote_list is %(ul)s.%(s)s" %
                    { "sc": self.split_chars, "ul": self.unquote_list, "l": s })
        
