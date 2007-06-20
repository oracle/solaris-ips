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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a generic packaging object

This module contains the Action class, which represents a generic packaging
object."""

class Action(object):
        """Class representing a generic packaging object.

        An Action is a very simple wrapper around two dictionaries: a named set
        of data streams and a set of attributes.  Data streams generally
        represent files on disk, and attributes represent metadata about those
        files.
        """

        def __init__(self, data=None, **attrs):
                """Action constructor.

                The optional 'data' argument can be a string or a dictionary of
                named objects.  If it is a string, it will be put into a
                dictionary, mapped to the name 'data'.
                
                Each of these objects may be either a string, a file-like
                object, or a callable.  If it is a string, then it will be
                substituted with a callable that will return an open handle to
                the file represented by the string.  Otherwise, if it is not
                already a callable, it is assumed to be a file-like object, and
                will be substituted with a callable that will return the object.
                If it is a callable, it will not be replaced at all.

                Any remaining named arguments will be treated as attributes.
                """
                self.attrs = attrs

                if data == None:
                        self.data = {}
                elif isinstance(data, dict):
                        self.data = data
                else:
                        self.data = {"data": data}

                for name in self.data:
                        if isinstance(self.data[name], str):
                                def file_opener():
                                        return open(oldobj)
                                oldobj = self.data[name]
                                self.data[name] = file_opener
                        elif not callable(self.data[name]):
                                def data_opener():
                                        return oldobj
                                oldobj = self.data[name]
                                self.data[name] = data_opener


        def preinstall(self):
                """Client-side method that performs pre-install actions."""
                pass

        def install(self):
                """Client-side method that installs the object."""
                pass

        def postinstall(self):
                """Client-side method that performs post-install actions."""
                pass

        @staticmethod
        def attributes():
                """Returns the tuple of required attributes."""
                return ()

        @staticmethod
        def name():
                """Returns the name of the action."""
                return "generic"
