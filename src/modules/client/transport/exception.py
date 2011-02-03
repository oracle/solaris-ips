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
# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.
#

import errno
import httplib
import pycurl

import pkg.client.api_errors as api_errors

retryable_http_errors = set((httplib.REQUEST_TIMEOUT, httplib.BAD_GATEWAY,
        httplib.GATEWAY_TIMEOUT, httplib.NOT_FOUND))
retryable_file_errors = set((pycurl.E_FILE_COULDNT_READ_FILE, errno.EAGAIN,
    errno.ENOENT))

# Errors that stats.py may include in a decay-able error rate
decayable_http_errors = set((httplib.NOT_FOUND,))
decayable_file_errors = set((pycurl.E_FILE_COULDNT_READ_FILE, errno.EAGAIN,
    errno.ENOENT))
decayable_pycurl_errors = set((pycurl.E_OPERATION_TIMEOUTED,
        pycurl.E_COULDNT_CONNECT))

# Different protocols may have different retryable errors.  Map proto
# to set of retryable errors.

retryable_proto_errors = {
    "file": retryable_file_errors,
    "http": retryable_http_errors,
    "https": retryable_http_errors,
}

decayable_proto_errors = {
    "file": decayable_file_errors,
    "http": decayable_http_errors,
    "https": decayable_http_errors,
}

proto_code_map = {
    "http": httplib.responses,
    "https": httplib.responses
}

retryable_pycurl_errors = set((pycurl.E_COULDNT_CONNECT, pycurl.E_PARTIAL_FILE,
    pycurl.E_OPERATION_TIMEOUTED, pycurl.E_GOT_NOTHING, pycurl.E_SEND_ERROR,
    pycurl.E_RECV_ERROR, pycurl.E_COULDNT_RESOLVE_HOST,
    pycurl.E_TOO_MANY_REDIRECTS, pycurl.E_BAD_CONTENT_ENCODING))

class TransportException(api_errors.TransportError):
        """Base class for various exceptions thrown by code in transport
        package."""

        def __init__(self):
                self.count = 1
                self.decayable = False
                self.retryable = False


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

        def extend(self, exc_list):
                for exc in exc_list:
                        self.append(exc)

        def __str__(self):
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
                s += self._str_autofix()
                return s

        def __len__(self):
                return len(self.exceptions)


class TransportProtoError(TransportException):
        """Raised when errors occur in the transport protocol."""

        def __init__(self, proto, code=None, url=None, reason=None,
            repourl=None, request=None, uuid=None, details=None):
                TransportException.__init__(self)
                self.proto = proto
                self.code = code
                self.url = url
                self.urlstem = repourl
                self.reason = reason
                self.request = request
                self.decayable = self.code in decayable_proto_errors[self.proto]
                self.retryable = self.code in retryable_proto_errors[self.proto]
                self.uuid = uuid
                self.details = details

        def __str__(self):
                s = "%s protocol error" % self.proto
                if self.code:
                        s += ": code: %d" % self.code
                if self.reason:
                        s += " reason: %s" % self.reason
                if self.url:
                        s += "\nURL: '%s'." % self.url
                elif self.urlstem:
                        # If the location of the resource isn't known because
                        # the error was encountered while attempting to find
                        # the location, then at least knowing where it was
                        # looking will be helpful.
                        s += "\nRepository URL: '%s'." % self.urlstem
                if self.details:
                        s +="\nAdditional Details:\n%s" % self.details
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
                r = cmp(self.details, other.details)
                if r != 0:
                        return r
                return cmp(self.reason, other.reason)


class TransportFrameworkError(TransportException):
        """Raised when errors occur in the transport framework."""

        def __init__(self, code, url=None, reason=None, repourl=None,
            uuid=None):
                TransportException.__init__(self)
                self.code = code
                self.url = url
                self.urlstem = repourl
                self.reason = reason
                self.decayable = self.code in decayable_pycurl_errors
                self.retryable = self.code in retryable_pycurl_errors
                self.uuid = uuid

        def __str__(self):
                s = "Framework error: code: %d" % self.code
                if self.reason:
                        s += " reason: %s" % self.reason
                if self.url:
                        s += "\nURL: '%s'." % self.url
                s += self._str_autofix()
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


class TransportStallError(TransportException):
        """Raised when stalls occur in the transport framework."""

        def __init__(self, url=None, repourl=None, uuid=None):
                TransportException.__init__(self)
                self.url = url
                self.urlstem = repourl
                self.retryable = True
                self.uuid = uuid

        def __str__(self):
                s = "Framework stall"
                if self.url:
                        s += ":\nURL: '%s'." % self.url
                return s

        def __cmp__(self, other):
                if not isinstance(other, TransportStallError):
                        return -1        
                return cmp(self.url, other.url)


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

        def __init__(self, path=None, reason=None, size=0, url=None):
                TransportException.__init__(self)
                self.path = path
                self.reason = reason
                self.size = size
                self.retryable = True
                self.url = url

        def __str__(self):
                s = "Invalid content"
                if self.path:
                        s += "path %s" % self.path
                if self.reason:
                        s += ": %s." % self.reason
                if self.url:
                        s += "\nURL: %s" % self.url
                return s

        def __cmp__(self, other):
                if not isinstance(other, InvalidContentException):
                        return -1        
                r = cmp(self.path, other.path)
                if r != 0:
                        return r
                r = cmp(self.reason, other.reason)
                if r != 0:
                        return r
                return cmp(self.url, other.url)


class PkgProtoError(TransportException):
        """Raised when the pkg protocol doesn't behave according to
        specification.  This is different than TransportProtoError, which
        deals with the L7 protocols that we can use to perform a pkg(5)
        transport operation.  Although it doesn't exist, this is essentially
        a L8 error, since our pkg protocol is built on top of application
        level protocols.  The Framework errors deal with L3-6 errors."""

        def __init__(self, url, operation=None, version=None, reason=None):
                TransportException.__init__(self)
                self.url = url
                self.reason = reason
                self.operation = operation
                self.version = version
        
        def __str__(self):
                s = "Invalid pkg(5) response from %s" % self.url
                if self.operation:
                        s += ": Attempting operation '%s'" % self.operation
                if self.version is not None:
                        s += " version %s" % self.version
                if self.reason:
                        s += ":\n%s" % self.reason
                return s

        def __cmp__(self, other):
                if not isinstance(other, PkgProtoError):
                        return -1
                r = cmp(self.url, other.url)
                if r != 0:
                        return r
                r = cmp(self.operation, other.operation)
                if r != 0:
                        return r
                r = cmp(self.version, other.version)
                if r != 0:
                        return r
                return cmp(self.reason, other.reason) 


class ExcessiveTransientFailure(TransportException):
        """Raised when the transport encounters too many retryable errors
        at a single endpoint."""

        def __init__(self, url, count):
                TransportException.__init__(self)
                self.url = url
                self.count = count
                self.retryable = True
                self.failures = None
                self.success = None

        def __str__(self):
                s = "Too many retryable errors encountered during transfer.\n"
                if self.url:
                        s += "URL: %s " % self.url
                if self.count:
                        s += "Count: %s " % self.count
                return s
                
        def __cmp__(self, other):
                if not isinstance(other, ExcessiveTransientFailure):
                        return -1
                r = cmp(self.url, other.url)
                if r != 0:
                        return r
                return cmp(self.count, other.count)

class mDNSException(TransportException):
        """Used when mDNS operations fail."""

        def __init__(self, errstr):
                TransportException.__init__(self)
                self.err = errstr

        def __str__(self):
                return self.err
