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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import httplib
import pycurl

import pkg.client.api_errors as api_errors

retryable_http_errors = set((httplib.REQUEST_TIMEOUT, httplib.BAD_GATEWAY,
        httplib.GATEWAY_TIMEOUT, httplib.NOT_FOUND))

# Different protocols may have different retryable errors.  Map proto
# to set of retryable errors.

retryable_proto_errors = { "http" : retryable_http_errors,
                           "https" : retryable_http_errors }

retryable_pycurl_errors = set((pycurl.E_COULDNT_CONNECT, pycurl.E_PARTIAL_FILE,
        pycurl.E_OPERATION_TIMEOUTED, pycurl.E_GOT_NOTHING, pycurl.E_SEND_ERROR,
        pycurl.E_RECV_ERROR, pycurl.E_COULDNT_RESOLVE_HOST))

class TransportException(api_errors.TransportError):
        """Base class for various exceptions thrown by code in transport
        package."""
        def __init__(self):
                self.count = 1
                self.rcount = 1
                self.retryable = False
                self.verbose = False

        def simple_cmp(self, other):
                """Subclasses that wish to provided a simplified output
                interface must implement this routine and simple_str."""

                return self.__cmp__(other)

        def simple_str(self):
                """Subclasses that wish to provided a simplified output
                interface must implement this routine and simple_cmp."""

                return self.__str__()


class TransportOperationError(TransportException):
        """Used when transport operations fail for miscellaneous reasons."""
        def __init__(self, data):
                TransportException.__init__(self)
                self.data = data

        def __str__(self):
                return str(self.data)


class TransportFailures(TransportException):
        """This exception encapsulates multiple transport exceptions."""

        #
        # This class is a subclass of TransportException so that calling
        # code can reasonably 'except TransportException' and get either
        # a single-valued or in this case a multi-valued instance.
        #
        def __init__(self):
                TransportException.__init__(self)
                self.exceptions = []
                self.reduced_ex = []

        def append(self, exc):
                found = False

                assert isinstance(exc, TransportException)
                for x in self.exceptions:
                        if cmp(x, exc) == 0:
                                x.count += 1
                                found = True
                                break

                if not found:
                        self.exceptions.append(exc)

                found = False
                for x in self.reduced_ex:
                        if x.simple_cmp(exc) == 0:
                                x.rcount += 1
                                found = True
                                break

                if not found:
                        self.reduced_ex.append(exc)


        def __str__(self):
                if self.verbose:
                        return self.detailed_str()

                return self.simple_str()

        def detailed_str(self):
                if len(self.exceptions) == 0:
                        return "[no errors accumulated]"

                s = ""
                for i, x in enumerate(self.exceptions):
                        if len(self.exceptions) > 1:
                                s += "%d: " % (i + 1)
                        s += str(x)
                        if x.count > 1:
                                s += " (happened %d times)" % x.count
                        s += "\n"
                return s

        def simple_str(self):
                if len(self.reduced_ex) == 0:
                        return "[no errors accumulated]"

                s = ""
                for i, x in enumerate(self.reduced_ex):
                        if len(self.reduced_ex) > 1:
                                s += "%d: " % (i + 1)
                        s += x.simple_str()
                        if x.rcount > 1:
                                s += " (happened %d times)" % x.rcount
                        s += "\n"
                return s

        def __len__(self):
                return len(self.exceptions)


class TransportProtoError(TransportException):
        """Raised when errors occur in the transport protocol."""

        def __init__(self, proto, code=None, url=None, reason=None,
            repourl=None):
                TransportException.__init__(self)
                self.proto = proto
                self.code = code
                self.url = url
                self.urlstem = repourl
                self.reason = reason
                self.retryable = self.code in retryable_proto_errors[self.proto]

        def __str__(self):
                s = "%s protocol error" % self.proto
                if self.code:
                        s += ": code: %d" % self.code
                if self.reason:
                        s += "\nreason: %s" % self.reason
                if self.url:
                        s += "\nURL: '%s'." % self.url
                return s

        def __cmp__(self, other):
                if not isinstance(other, TransportProtoError):
                        return -1        
                r = cmp(self.proto, other.proto)
                if r != 0:
                        return r
                r = cmp(self.code, other.code)
                if r != 0:
                        return r
                r = cmp(self.url, other.url)
                if r != 0:
                        return r
                return cmp(self.reason, other.reason)

        def simple_cmp(self, other):
                if not isinstance(other, TransportProtoError):
                        return -1
                r = cmp(self.proto, other.proto)
                if r != 0:
                        return r
                r = cmp(self.code, other.code)
                if r != 0:
                        return r
                return cmp(self.urlstem, other.urlstem)

        def simple_str(self):
                s = "%s protocol error" % self.proto
                if self.code:
                        s += ": code: %d" % self.code
                if self.urlstem:
                        s += "\nURL: '%s'." % self.urlstem
                return s


class TransportFrameworkError(TransportException):
        """Raised when errors occur in the transport framework."""

        def __init__(self, code, url=None, reason=None, repourl=None):
                TransportException.__init__(self)
                self.code = code
                self.url = url
                self.urlstem = repourl
                self.reason = reason
                self.retryable = self.code in retryable_pycurl_errors

        def __str__(self):
                s = "Framework error: code: %d" % self.code
                if self.reason:
                        s += " reason: %s" % self.reason
                if self.url:
                        s += "\nURL: '%s'." % self.url
                return s

        def __cmp__(self, other):
                if not isinstance(other, TransportFrameworkError):
                        return -1        
                r = cmp(self.code, other.code)
                if r != 0:
                        return r
                r = cmp(self.url, other.url)
                if r != 0:
                        return r
                return cmp(self.reason, other.reason)

        def simple_cmp(self, other):
                if not isinstance(other, TransportFrameworkError):
                        return -1
                r = cmp(self.code, other.code)
                if r != 0:
                        return r
                r = cmp(self.reason, other.reason)
                if r != 0:
                        return r
                return cmp(self.urlstem, other.urlstem)

        def simple_str(self):
                s = "Framework error: code: %d" % self.code
                if self.reason:
                        s += " reason: %s" % self.reason
                if self.urlstem:
                        s += "\nURL: '%s'." % self.urlstem
                return s


class TransferContentException(TransportException):
        """Raised when there are problems downloading the requested content."""
        def __init__(self, url, reason=None):
                TransportException.__init__(self)
                self.url = url
                self.reason = reason
                self.retryable = True

        def __str__(self):
                s = "Transfer from '%s' failed" % self.url
                if self.reason:
                        s += ": %s" % self.reason
                s += "."
                return s

        def __cmp__(self, other):
                if not isinstance(other, TransferContentException):
                        return -1        
                r = cmp(self.url, other.url)
                if r != 0:
                        return r
                return cmp(self.reason, other.reason)


class InvalidContentException(TransportException):
        """Raised when the content's hash/chash doesn't verify, or the
        content is received in an unreadable format."""
        def __init__(self, path, reason, size=0):
                TransportException.__init__(self)
                self.path = path
                self.reason = reason
                self.size = size
                self.retryable = True

        def __str__(self):
                s = "Invalid content for action with path %s" % self.path
                if self.reason:
                        s += ": %s." % self.reason
                return s

        def __cmp__(self, other):
                if not isinstance(other, InvalidContentException):
                        return -1        
                r = cmp(self.path, other.path)
                if r != 0:
                        return r
                return cmp(self.reason, other.reason)

