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

from __future__ import division

import errno
import os
import pycurl
import six
import time

from six.moves import http_client
from six.moves.urllib.parse import urlsplit

# Need to ignore SIGPIPE if using pycurl in NOSIGNAL mode.
try:
        import signal
        if hasattr(signal, "SIGPIPE"):
                signal.signal(signal.SIGPIPE, signal.SIG_IGN)
except ImportError:
        pass

import pkg.client.api_errors            as api_errors
import pkg.client.transport.exception   as tx
import pkg.client.transport.fileobj     as fileobj
import pkg.misc                         as misc

from collections        import deque
from pkg.client         import global_settings
from pkg.client.debugvalues import DebugValues

pipelined_protocols = ()
response_protocols = ("ftp", "http", "https")

class TransportEngine(object):
        """This is an abstract class.  It shouldn't implement any
        of the methods that it contains.  Leave that to transport-specific
        implementations."""


class CurlTransportEngine(TransportEngine):
        """Concrete class of TransportEngine for libcurl transport."""

        def __init__(self, transport, max_conn=20):

                # Backpointer to transport object
                self.__xport = transport
                # Curl handles
                self.__mhandle = pycurl.CurlMulti()
                self.__chandles = []
                self.__active_handles = 0
                self.__max_handles = max_conn
                # Request queue
                self.__req_q = deque()
                # List of failures
                self.__failures = []
                # List of URLs successfully transferred
                self.__success = []
                # List of Orphaned URLs.
                self.__orphans = set()
                # Set default file buffer size at 128k, callers override
                # this setting after looking at VFS block size.
                self.__file_bufsz = 131072
                # Header bits and pieces
                self.__user_agent = None
                self.__common_header = {}
                self.__last_stall_check = 0

                # Set options on multi-handle
                self.__mhandle.setopt(pycurl.M_PIPELINING, 0)

                # initialize easy handles
                for i in range(self.__max_handles):
                        eh = pycurl.Curl()
                        eh.url = None
                        eh.repourl = None
                        eh.fobj = None
                        eh.r_fobj = None
                        eh.filepath = None
                        eh.success = False
                        eh.fileprog = None
                        eh.filetime = -1
                        eh.starttime = -1
                        eh.uuid = None
                        self.__chandles.append(eh)

                # copy handles into handle freelist
                self.__freehandles = self.__chandles[:]

        def __call_perform(self):
                """An internal method that invokes the multi-handle's
                perform method."""

                while 1:
                        ret, active_handles = self.__mhandle.perform()
                        if ret != pycurl.E_CALL_MULTI_PERFORM:
                                break

                self.__active_handles = active_handles
                return ret

        def add_url(self, url, filepath=None, writefunc=None, header=None,
            progclass=None, progtrack=None, sslcert=None, sslkey=None,
            repourl=None, compressible=False, failonerror=True, proxy=None,
            runtime_proxy=None):
                """Add a URL to the transport engine.  Caller must supply
                either a filepath where the file should be downloaded,
                or a callback to a function that will peform the write.
                It may also optionally supply header information
                in a dictionary.  If the caller has a ProgressTracker,
                it should pass the tracker in progtrack.  The caller should
                also supply a class that wraps the tracker in progclass.

                'proxy' is the persistent proxy value for this url and is
                stored as part of the transport stats accounting.

                'runtime_proxy' is the actual proxy value that is used by pycurl
                to retrieve this resource."""

                t = TransportRequest(url, filepath=filepath,
                    writefunc=writefunc, header=header, progclass=progclass,
                    progtrack=progtrack, sslcert=sslcert, sslkey=sslkey,
                    repourl=repourl, compressible=compressible,
                    failonerror=failonerror, proxy=proxy,
                    runtime_proxy=runtime_proxy)

                self.__req_q.appendleft(t)

        def __check_for_stalls(self):
                """In some situations, libcurl can get itself
                tied in a knot, and fail to make progress.  Check that the
                active handles are making progress.  If none of the active
                handles have downloaded any content for the timeout period,
                reset the transport and generate exceptions for the failed
                requests."""

                timeout = global_settings.PKG_CLIENT_LOWSPEED_TIMEOUT
                if timeout == 0:
                        return
                current_time = time.time()
                time_list = []
                size_list = []
                failures = []
                q_hdls = [
                    hdl for hdl in self.__chandles
                    if hdl not in self.__freehandles
                ]

                # time.time() is based upon system clock.  Check that
                # our time hasn't been set backwards.  If time is set forward,
                # we'll have to expire the handles.  There's no way to detect
                # this until python properly implements gethrtime().  Solaris
                # implementations of time.clock() appear broken.

                for h in q_hdls:
                        time_elapsed = current_time - h.starttime
                        if time_elapsed < 0:
                                h.starttime = current_time
                                time_elapsed = 0
                        size_xfrd = h.getinfo(pycurl.SIZE_DOWNLOAD) + \
                            h.getinfo(pycurl.SIZE_UPLOAD)
                        time_list.append(time_elapsed)
                        size_list.append(size_xfrd)

                # If timeout is smaller than smallest elapsed time,
                # and no data has been transferred, abort.
                if timeout < min(time_list) and max(size_list) == 0:
                        for h in q_hdls:
                                url = h.url
                                uuid = h.uuid
                                urlstem = h.repourl
                                ex = tx.TransportStallError(url,
                                    repourl=urlstem, uuid=uuid)

                                self.__mhandle.remove_handle(h)
                                self.__teardown_handle(h)
                                self.__freehandles.append(h)

                                failures.append(ex)

                self.__failures.extend(failures)


        def __cleanup_requests(self):
                """Cleanup handles that have finished their request.
                Return the handles to the freelist.  Generate any
                relevant error information."""

                count, good, bad = self.__mhandle.info_read()
                failures = self.__failures
                success = self.__success
                done_handles = []
                ex_to_raise = None
                visited_repos = set()
                errors_seen = 0

                for h, en, em in bad:
                        # Get statistics for each handle.
                        # As new properties are added to URIs that differentiate
                        # them, the tuple used to index the __xport.stats entry
                        # should also include those properties so that we can
                        # track statistics uniquely for each RepoURI. That is,
                        # the format of the keys of the __xport.stats dictionary
                        # should match the one generated by
                        # pkg.client.publisher.TransportRepoURI.key()
                        repostats = self.__xport.stats[(h.repourl, h.proxy)]
                        visited_repos.add(repostats)
                        repostats.record_tx()
                        nbytes = h.getinfo(pycurl.SIZE_DOWNLOAD)
                        seconds = h.getinfo(pycurl.TOTAL_TIME)
                        conn_count = h.getinfo(pycurl.NUM_CONNECTS)
                        conn_time = h.getinfo(pycurl.CONNECT_TIME)

                        url = h.url
                        uuid = h.uuid
                        urlstem = h.repourl
                        proto = urlsplit(url)[0]

                        # When using pipelined operations, libcurl tracks the
                        # amount of time taken for the entire pipelined request
                        # as opposed to just the amount of time for a single
                        # file in the pipeline.  So, if the connection time is 0
                        # for a request using http(s), then it was pipelined and
                        # the total time must be obtained by subtracting the
                        # time the transfer of the individual request started
                        # from the total time.
                        if conn_time == 0 and proto in pipelined_protocols:
                                # Only performing this subtraction when the
                                # conn_time is 0 allows the first request in
                                # the pipeline to properly include connection
                                # time, etc. to initiate the transfer.
                                seconds -= h.getinfo(pycurl.STARTTRANSFER_TIME)
                        elif conn_time > 0:
                                seconds -= conn_time

                        # Sometimes libcurl will report no transfer time.
                        # In that case, just use starttransfer time if it's
                        # non-zero.
                        if seconds < 0:
                                seconds = h.getinfo(pycurl.STARTTRANSFER_TIME)

                        repostats.record_progress(nbytes, seconds)

                        # Only count connections if the connection time is
                        # positive for http(s); for all other protocols,
                        # record the connection regardless.
                        if conn_count > 0 and conn_time > 0:
                                repostats.record_connection(conn_time)

                        respcode = h.getinfo(pycurl.RESPONSE_CODE)

                        # If we were cancelled, raise an API error.
                        # Otherwise fall through to transport's exception
                        # generation.
                        if en == pycurl.E_ABORTED_BY_CALLBACK:
                                ex = None
                                ex_to_raise = api_errors.CanceledException
                        elif en in (pycurl.E_HTTP_RETURNED_ERROR,
                            pycurl.E_FILE_COULDNT_READ_FILE):
                                # E_HTTP_RETURNED_ERROR is only used for http://
                                # and https://, but a more specific reason for
                                # failure can be obtained from respcode.
                                #
                                # E_FILE_COULDNT_READ_FILE is only used for
                                # file://, but unfortunately can mean ENOENT,
                                # EPERM, etc. and libcurl doesn't differentiate
                                # or provide a respcode.
                                if proto not in response_protocols:
                                        # For protocols that don't provide a
                                        # pycurl.RESPONSE_CODE, use the
                                        # pycurl error number instead.
                                        respcode = en
                                proto_reason = None
                                if proto in tx.proto_code_map:
                                        # Look up protocol error code map
                                        # from transport exception's table.
                                        pmap = tx.proto_code_map[proto]
                                        if respcode in pmap:
                                                proto_reason = pmap[respcode]
                                ex = tx.TransportProtoError(proto, respcode,
                                    url, reason=proto_reason, repourl=urlstem,
                                    uuid=uuid)
                                repostats.record_error(decayable=ex.decayable)
                                errors_seen += 1
                        else:
                                timeout = en == pycurl.E_OPERATION_TIMEOUTED
                                ex = tx.TransportFrameworkError(en, url, em,
                                    repourl=urlstem, uuid=uuid)
                                repostats.record_error(decayable=ex.decayable,
                                    timeout=timeout)
                                errors_seen += 1

                        if ex and ex.retryable:
                                failures.append(ex)
                        elif ex and not ex_to_raise:
                                ex_to_raise = ex

                        done_handles.append(h)

                for h in good:
                        # Get statistics for each handle.
                        repostats = self.__xport.stats[(h.repourl, h.proxy)]
                        visited_repos.add(repostats)
                        repostats.record_tx()
                        nbytes = h.getinfo(pycurl.SIZE_DOWNLOAD)
                        seconds = h.getinfo(pycurl.TOTAL_TIME)
                        conn_count = h.getinfo(pycurl.NUM_CONNECTS)
                        conn_time = h.getinfo(pycurl.CONNECT_TIME)
                        h.filetime = h.getinfo(pycurl.INFO_FILETIME)

                        url = h.url
                        uuid = h.uuid
                        urlstem = h.repourl
                        proto = urlsplit(url)[0]

                        # When using pipelined operations, libcurl tracks the
                        # amount of time taken for the entire pipelined request
                        # as opposed to just the amount of time for a single
                        # file in the pipeline.  So, if the connection time is 0
                        # for a request using http(s), then it was pipelined and
                        # the total time must be obtained by subtracting the
                        # time the transfer of the individual request started
                        # from the total time.
                        if conn_time == 0 and proto in pipelined_protocols:
                                # Only performing this subtraction when the
                                # conn_time is 0 allows the first request in
                                # the pipeline to properly include connection
                                # time, etc. to initiate the transfer and
                                # the correct calculations of bytespersec.
                                seconds -= h.getinfo(pycurl.STARTTRANSFER_TIME)
                        elif conn_time > 0:
                                seconds -= conn_time

                        if seconds > 0:
                                bytespersec = nbytes // seconds
                        else:
                                bytespersec = 0

                        # If a request ahead of a successful request fails due
                        # to a timeout, sometimes libcurl will report impossibly
                        # large total time values.  In this case, check that the
                        # nbytes/sec exceeds our minimum threshold.  If it does
                        # not, and the total time is longer than our timeout,
                        # discard the time calculation as it is bogus.
                        if (bytespersec <
                            global_settings.pkg_client_lowspeed_limit) and (
                            seconds >
                            global_settings.PKG_CLIENT_LOWSPEED_TIMEOUT):
                                nbytes = 0
                                seconds = 0
                        repostats.record_progress(nbytes, seconds)

                        # Only count connections if the connection time is
                        # positive for http(s); for all other protocols,
                        # record the connection regardless.
                        if conn_count > 0 and conn_time > 0:
                                repostats.record_connection(conn_time)

                        respcode = h.getinfo(pycurl.RESPONSE_CODE)

                        if proto not in response_protocols or \
                            respcode == http_client.OK:
                                h.success = True
                                repostats.clear_consecutive_errors()
                                success.append(url)
                        else:
                                proto_reason = None
                                if proto in tx.proto_code_map:
                                        # Look up protocol error code map
                                        # from transport exception's table.
                                        pmap = tx.proto_code_map[proto]
                                        if respcode in pmap:
                                                proto_reason = pmap[respcode]
                                ex = tx.TransportProtoError(proto,
                                    respcode, url, reason=proto_reason,
                                    repourl=urlstem, uuid=uuid)

                                # If code >= 400, record this as an error.
                                # Handlers above the engine get to decide
                                # for 200/300 codes that aren't OK
                                if respcode >= 400:
                                        repostats.record_error(
                                            decayable=ex.decayable)
                                        errors_seen += 1
                                # If code == 0, libcurl failed to read
                                # any HTTP status.  Response is almost
                                # certainly corrupted.
                                elif respcode == 0:
                                        repostats.record_error()
                                        errors_seen += 1
                                        reason = "Invalid HTTP status code " \
                                            "from server"
                                        ex = tx.TransportProtoError(proto,
                                            url=url, reason=reason,
                                            repourl=urlstem, uuid=uuid)
                                        ex.retryable = True

                                # Stash retryable failures, arrange
                                # to raise first fatal error after
                                # cleanup.
                                if ex.retryable:
                                        failures.append(ex)
                                elif not ex_to_raise:
                                        ex_to_raise = ex

                        done_handles.append(h)

                # Call to remove_handle must be separate from info_read()
                for h in done_handles:
                        self.__mhandle.remove_handle(h)
                        self.__teardown_handle(h)
                        self.__freehandles.append(h)

                self.__failures = failures
                self.__success = success

                if ex_to_raise:
                        raise ex_to_raise

                # Don't bother to check the transient error count if no errors
                # were encountered in this transaction.
                if errors_seen == 0:
                        return

                # If errors were encountered, but no exception raised,
                # check if the maximum number of transient failures has
                # been exceeded at any of the endpoints that were visited
                # during this transaction.
                for rs in visited_repos:
                        numce = rs.consecutive_errors
                        if numce >= \
                            global_settings.PKG_CLIENT_MAX_CONSECUTIVE_ERROR:
                                # Reset consecutive error count before raising
                                # this exception.
                                rs.clear_consecutive_errors()
                                raise tx.ExcessiveTransientFailure(rs.url,
                                    numce)

        def check_status(self, urllist=None, good_reqs=False):
                """Return information about retryable failures that occured
                during the request.

                This is a list of transport exceptions.  Caller
                may raise these, or process them for failure information.

                Urllist is an optional argument to return only failures
                for a specific URLs.  Not all callers of check status
                want to claim the error state of all pending transactions.

                Transient errors are part of standard control flow.
                The caller will look at these and decide whether
                to throw them or not.  Permanent failures are raised
                by the transport engine as soon as they occur.

                If good_reqs is set to true, then check_stats will
                return a tuple of lists, the first list contains the
                transient errors that were encountered, the second list
                contains successfully transferred urls.  Because the
                list of successfully transferred URLs may be long,
                it is discarded if not requested by the caller."""

                # if list not specified, return all failures
                if not urllist:
                        rf = self.__failures
                        rs = self.__success
                        self.__failures = []
                        self.__success = []

                        if good_reqs:
                                return rf, rs

                        return rf

                # otherwise, look for failures that match just the URLs
                # in urllist.
                rf = [
                    tf
                    for tf in self.__failures
                    if hasattr(tf, "url") and tf.url in urllist
                ]

                # remove failues in separate pass, or else for loop gets
                # confused.
                for f in rf:
                        self.__failures.remove(f)

                if not good_reqs:
                        self.__success = []
                        return rf

                rs = []

                for ts in self.__success:
                        if ts in urllist:
                                rs.append(ts)

                for s in rs:
                        self.__success.remove(s)

                return rf, rs

        def get_url(self, url, header=None, sslcert=None, sslkey=None,
            repourl=None, compressible=False, ccancel=None,
            failonerror=True, proxy=None, runtime_proxy=None, system=False):
                """Invoke the engine to retrieve a single URL.  Callers
                wishing to obtain multiple URLs at once should use
                addUrl() and run().

                getUrl will return a read-only file object that allows access
                to the URL's data.

                'proxy' is the persistent proxy value for this url and is
                stored as part of the transport stats accounting.

                'runtime_proxy' is the actual proxy value that is used by pycurl
                to retrieve this resource.

                'system' whether the resource is being retrieved on behalf of
                a system-publisher or directly from the system-repository.
                """

                fobj = fileobj.StreamingFileObj(url, self, ccancel=ccancel)
                progfunc = None

                if ccancel:
                        progfunc = fobj.get_progress_func()

                t = TransportRequest(url, writefunc=fobj.get_write_func(),
                    hdrfunc=fobj.get_header_func(), header=header,
                    sslcert=sslcert, sslkey=sslkey, repourl=repourl,
                    compressible=compressible, progfunc=progfunc,
                    uuid=fobj.uuid, failonerror=failonerror, proxy=proxy,
                    runtime_proxy=runtime_proxy, system=system)

                self.__req_q.appendleft(t)

                return fobj

        def get_url_header(self, url, header=None, sslcert=None, sslkey=None,
            repourl=None, ccancel=None, failonerror=True, proxy=None,
            runtime_proxy=None):
                """Invoke the engine to retrieve a single URL's headers.

                getUrlHeader will return a read-only file object that
                contains no data.

                'proxy' is the persistent proxy value for this url and is
                stored as part of the transport stats accounting.

                'runtime_proxy' is the actual proxy value that is used by pycurl
                to retrieve this resource.
                """

                fobj = fileobj.StreamingFileObj(url, self, ccancel=ccancel)
                progfunc = None

                if ccancel:
                        progfunc = fobj.get_progress_func()

                t = TransportRequest(url, writefunc=fobj.get_write_func(),
                    hdrfunc=fobj.get_header_func(), header=header,
                    httpmethod="HEAD", sslcert=sslcert, sslkey=sslkey,
                    repourl=repourl, progfunc=progfunc, uuid=fobj.uuid,
                    failonerror=failonerror, proxy=proxy,
                    runtime_proxy=runtime_proxy)

                self.__req_q.appendleft(t)

                return fobj

        @property
        def pending(self):
                """Returns true if the engine still has outstanding
                work to perform, false otherwise."""

                return bool(self.__req_q) or self.__active_handles > 0

        def run(self):
                """Run the transport engine.  This polls the underlying
                framework to complete any asynchronous I/O.  Synchronous
                operations should have completed when startRequest
                was invoked."""

                if not self.pending:
                        return

                if self.__active_handles > 0:
                        # timeout returned in milliseconds
                        timeout = self.__mhandle.timeout()
                        if timeout == -1:
                                # Pick our own timeout.
                                timeout = 1.0
                        elif timeout > 0:
                                # Timeout of 0 means skip call
                                # to select.
                                #
                                # Convert from milliseconds to seconds.
                                timeout = timeout / 1000.0

                        if timeout:
                                self.__mhandle.select(timeout)

                # If object deletion has given the transport engine orphaned
                # requests to purge, do this first, in case the cleanup yields
                # free handles.
                while self.__orphans:
                        url, uuid = self.__orphans.pop()
                        self.remove_request(url, uuid)

                while self.__freehandles and self.__req_q:
                        t = self.__req_q.pop()
                        eh = self.__freehandles.pop(-1)
                        self.__setup_handle(eh, t)
                        self.__mhandle.add_handle(eh)

                self.__call_perform()

                self.__cleanup_requests()

                if self.__active_handles and (not self.__freehandles or not
                    self.__req_q):
                        cur_clock = time.time()
                        if cur_clock - self.__last_stall_check > 1:
                                self.__last_stall_check = cur_clock
                                self.__check_for_stalls()
                        elif cur_clock - self.__last_stall_check < 0:
                                self.__last_stall_check = cur_clock
                                self.__check_for_stalls()

        def orphaned_request(self, url, uuid):
                """Add the URL to the list of orphaned requests.  Any URL in
                list will be removed from the transport next time run() is
                invoked.  This is used by the fileobj's __del__ method
                to prevent unintended modifications to transport state
                when StreamingFileObjs that aren't close()'d get cleaned
                up."""

                self.__orphans.add((url, uuid))

        def remove_request(self, url, uuid):
                """In order to remove a request, it may be necessary
                to walk all of the items in the request queue, all of the
                currently active handles, and the list of any transient
                failures.  This is expensive, so only remove a request
                if absolutely necessary."""

                for h in self.__chandles:
                        if h.url == url and h.uuid == uuid and \
                            h not in self.__freehandles:
                                try:
                                        self.__mhandle.remove_handle(h)
                                except pycurl.error:
                                        # If cleanup is interrupted, it's
                                        # possible that a handle was removed but
                                        # not placed in freelist.  In that case,
                                        # finish cleanup and appened to
                                        # freehandles.
                                        pass
                                self.__teardown_handle(h)
                                self.__freehandles.append(h)
                                return

                for i, t in enumerate(self.__req_q):
                        if t.url == url and t.uuid == uuid:
                                del self.__req_q[i]
                                return

                for ex in self.__failures:
                        if ex.url == url and ex.uuid == uuid:
                                self.__failures.remove(ex)
                                return

        def reset(self):
                """Reset the state of the transport engine.  Do this
                before performing another type of request."""

                for c in self.__chandles:
                        if c not in self.__freehandles:
                                try:
                                        self.__mhandle.remove_handle(c)
                                except pycurl.error:
                                        # If cleanup is interrupted, it's
                                        # possible that a handle was removed but
                                        # not placed in freelist.  In that case,
                                        # finish cleanup and appened to
                                        # freehandles.
                                        pass
                                self.__teardown_handle(c)

                self.__active_handles = 0
                self.__freehandles = self.__chandles[:]
                self.__req_q = deque()
                self.__failures = []
                self.__success = []
                self.__orphans = set()

        def send_data(self, url, data=None, header=None, sslcert=None,
            sslkey=None, repourl=None, ccancel=None,
            data_fobj=None, data_fp=None, failonerror=True,
            progclass=None, progtrack=None, proxy=None, runtime_proxy=None):
                """Invoke the engine to retrieve a single URL.
                This routine sends the data in data, and returns the
                server's response.

                Callers wishing to obtain multiple URLs at once should use
                addUrl() and run().

                sendData will return a read-only file object that allows access
                to the server's response.."""

                fobj = fileobj.StreamingFileObj(url, self, ccancel=ccancel)
                progfunc = None

                if ccancel and not progtrack and not progclass:
                        progfunc = fobj.get_progress_func()

                t = TransportRequest(url, writefunc=fobj.get_write_func(),
                    hdrfunc=fobj.get_header_func(), header=header, data=data,
                    httpmethod="POST", sslcert=sslcert, sslkey=sslkey,
                    repourl=repourl, progfunc=progfunc, uuid=fobj.uuid,
                    read_fobj=data_fobj, read_filepath=data_fp,
                    failonerror=failonerror, progclass=progclass,
                    progtrack=progtrack, proxy=proxy,
                    runtime_proxy=runtime_proxy)

                self.__req_q.appendleft(t)

                return fobj

        def set_file_bufsz(self, size):
                """If the downloaded files are being written out by
                the file() mechanism, and not written using a callback,
                the I/O is buffered.  Set the buffer size using
                this function.  If it's not set, a default of 131072 (128k)
                is used."""

                if size <= 0:
                        self.__file_bufsz = 8192
                        return

                self.__file_bufsz = size

        def set_header(self, hdrdict=None):
                """Supply a dictionary of name/value pairs in hdrdict.
                These will be included on all requests issued by the transport
                engine.  To append a specific header to a certain request,
                supply a dictionary to the header argument of addUrl."""

                if not hdrdict:
                        self.__common_header = {}
                        return

                self.__common_header = hdrdict

        def set_user_agent(self, ua_str):
                """Supply a string str and the transport engine will
                use this string as its User-Agent header.  This is
                a header that will be common to all transport requests."""

                self.__user_agent = ua_str

        def __setup_handle(self, hdl, treq):
                """Setup the curl easy handle, hdl, with the parameters
                specified in the TransportRequest treq.  If global
                parameters are set, apply these to the handle as well."""

                # Set nosignal, so timeouts don't crash client
                hdl.setopt(pycurl.NOSIGNAL, 1)

                # Set connect timeout.  Its value is defined in global_settings.
                hdl.setopt(pycurl.CONNECTTIMEOUT,
                    global_settings.PKG_CLIENT_CONNECT_TIMEOUT)

                # Set lowspeed limit and timeout.  Clients that are too
                # slow or have hung after specified amount of time will
                # abort the connection.
                hdl.setopt(pycurl.LOW_SPEED_LIMIT,
                    global_settings.pkg_client_lowspeed_limit)
                hdl.setopt(pycurl.LOW_SPEED_TIME,
                    global_settings.PKG_CLIENT_LOWSPEED_TIMEOUT)

                # Follow redirects
                hdl.setopt(pycurl.FOLLOWLOCATION, True)
                # Set limit on maximum number of redirects
                hdl.setopt(pycurl.MAXREDIRS,
                    global_settings.PKG_CLIENT_MAX_REDIRECT)

                # Store the proxy in the handle so it can be used to retrieve
                # transport statistics later.
                hdl.proxy = None
                hdl.runtime_proxy = None

                if treq.system:
                        # For requests that are proxied through the system
                        # repository, we do not want to use $http_proxy
                        # variables.  For direct access to the
                        # system-repository, we set an empty proxy, which has
                        # the same effect.
                        if treq.proxy:
                                hdl.proxy = treq.proxy
                                hdl.setopt(pycurl.PROXY, treq.proxy)
                        else:
                                hdl.setopt(pycurl.PROXY, "")
                elif treq.runtime_proxy:
                        # Allow $http_proxy environment variables
                        if treq.runtime_proxy != "-":
                                # a runtime_proxy of '-' means we've found a
                                # no-proxy environment variable.
                                hdl.setopt(pycurl.PROXY, treq.runtime_proxy)
                        hdl.proxy = treq.proxy
                        hdl.runtime_proxy = treq.runtime_proxy
                else:
                        # Make sure that we don't use a proxy if the destination
                        # is localhost.
                        hdl.setopt(pycurl.NOPROXY, "localhost")

                # Set user agent, if client has defined it
                if self.__user_agent:
                        hdl.setopt(pycurl.USERAGENT, self.__user_agent)

                # Take header dictionaries and convert them into lists
                # of header strings.
                if self.__common_header or treq.header:
                        headerlist = []

                        # Headers common to all requests
                        for k, v in six.iteritems(self.__common_header):
                                headerstr = "{0}: {1}".format(k, v)
                                headerlist.append(headerstr)

                        # Headers specific to this request
                        if treq.header:
                                for k, v in six.iteritems(treq.header):
                                        headerstr = "{0}: {1}".format(k, v)
                                        headerlist.append(headerstr)

                        hdl.setopt(pycurl.HTTPHEADER, headerlist)

                # Set request url.  Also set attribute on handle.
                hdl.setopt(pycurl.URL, treq.url)
                hdl.url = treq.url
                hdl.uuid = treq.uuid
                hdl.starttime = time.time()
                # The repourl is the url stem that identifies the
                # repository. This is useful to have around for coalescing
                # error output, and statistics reporting.
                hdl.repourl = treq.repourl
                if treq.filepath:
                        try:
                                hdl.fobj = open(treq.filepath, "wb+",
                                    self.__file_bufsz)
                        except EnvironmentError as e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                if e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
                                # Raise OperationError if it's not EACCES
                                # or EROFS.
                                raise tx.TransportOperationError(
                                    "Unable to open file: {0}".format(e))

                        hdl.setopt(pycurl.WRITEDATA, hdl.fobj)
                        # Request filetime, if endpoint knows it.
                        hdl.setopt(pycurl.OPT_FILETIME, True)
                        hdl.filepath = treq.filepath
                elif treq.writefunc:
                        hdl.setopt(pycurl.WRITEFUNCTION, treq.writefunc)
                        hdl.filepath = None
                        hdl.fobj = None
                else:
                        raise tx.TransportOperationError("Transport invocation"
                            " for URL {0} did not specify filepath or write"
                            " function.".format(treq.url))

                if treq.failonerror:
                        hdl.setopt(pycurl.FAILONERROR, True)

                if treq.progtrack and treq.progclass:
                        hdl.setopt(pycurl.NOPROGRESS, 0)
                        hdl.fileprog = treq.progclass(treq.progtrack)
                        hdl.setopt(pycurl.PROGRESSFUNCTION,
                            hdl.fileprog.progress_callback)
                elif treq.progfunc:
                        # For light-weight progress tracking / cancelation.
                        hdl.setopt(pycurl.NOPROGRESS, 0)
                        hdl.setopt(pycurl.PROGRESSFUNCTION, treq.progfunc)

                proto = urlsplit(treq.url)[0]
                if not proto in ("http", "https"):
                        return

                if treq.read_filepath:
                        try:
                                hdl.r_fobj = open(treq.read_filepath, "rb",
                                    self.__file_bufsz)
                        except EnvironmentError as e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                # Raise OperationError if it's not EACCES
                                # or EROFS.
                                raise tx.TransportOperationError(
                                    "Unable to open file: {0}".format(e))

                if treq.compressible:
                        hdl.setopt(pycurl.ENCODING, "")

                if treq.hdrfunc:
                        hdl.setopt(pycurl.HEADERFUNCTION, treq.hdrfunc)

                if treq.httpmethod == "GET":
                        hdl.setopt(pycurl.HTTPGET, True)
                elif treq.httpmethod == "HEAD":
                        hdl.setopt(pycurl.NOBODY, True)
                elif treq.httpmethod == "POST":
                        hdl.setopt(pycurl.POST, True)
                        if treq.data is not None:
                                hdl.setopt(pycurl.POSTFIELDS, treq.data)
                        elif hdl.r_fobj or treq.read_fobj:
                                if not hdl.r_fobj:
                                        hdl.r_fobj = treq.read_fobj
                                hdl.setopt(pycurl.READDATA, hdl.r_fobj)
                                hdl.setopt(pycurl.POSTFIELDSIZE,
                                    os.fstat(hdl.r_fobj.fileno()).st_size)
                        else:
                                raise tx.TransportOperationError("Transport "
                                    "operation for POST URL {0} did not "
                                    "supply data or read_fobj.  At least one "
                                    "is required.".format(treq.url))
                elif treq.httpmethod == "PUT":
                        hdl.setopt(pycurl.UPLOAD, True)
                        if hdl.r_fobj or treq.read_fobj:
                                if not hdl.r_fobj:
                                        hdl.r_fobj = treq.read_fobj
                                hdl.setopt(pycurl.READDATA, hdl.r_fobj)
                                hdl.setopt(pycurl.INFILESIZE,
                                    os.fstat(hdl.r_fobj.fileno()).st_size)
                        else:
                                raise tx.TransportOperationError("Transport "
                                    "operation for PUT URL {0} did not "
                                    "supply a read_fobj.  One is "
                                    "required.".format(treq.url))
                elif treq.httpmethod == "DELETE":
                        hdl.setopt(pycurl.CUSTOMREQUEST, "DELETE")
                else:
                        raise tx.TransportOperationError("Invalid http method "
                            "'{0}' specified.".format(treq.httpmethod))

                # Set up SSL options
                if treq.sslcert:
                        hdl.setopt(pycurl.SSLCERT, treq.sslcert)
                if treq.sslkey:
                        hdl.setopt(pycurl.SSLKEY, treq.sslkey)

                # Options that apply when SSL is enabled
                if proto == "https":
                        # Verify that peer's CN matches CN on certificate
                        hdl.setopt(pycurl.SSL_VERIFYHOST, 2)
                        hdl.setopt(pycurl.SSL_VERIFYPEER, 1)
                        cadir = self.__xport.get_ca_dir()
                        hdl.setopt(pycurl.CAPATH, cadir)
                        if "ssl_ca_file" in DebugValues:
                                cafile = DebugValues["ssl_ca_file"]
                                hdl.setopt(pycurl.CAINFO, cafile)
                                hdl.unsetopt(pycurl.CAPATH)
                        else:
                                hdl.unsetopt(pycurl.CAINFO)

        def shutdown(self):
                """Shutdown the transport engine, perform cleanup."""

                for c in self.__chandles:
                        c.close()

                self.__chandles = None
                self.__freehandles = None
                self.__mhandle.close()
                self.__mhandle = None
                self.__req_q = None
                self.__failures = None
                self.__success = None
                self.__orphans = None
                self.__active_handles = 0

        @staticmethod
        def __teardown_handle(hdl):
                """Cleanup any state that we've associated with this handle.
                After a handle has been torn down, it should still be valid
                for use, but should have no previous state.  To remove
                handles from use completely, use __shutdown."""

                hdl.reset()
                if hdl.fobj:
                        hdl.fobj.close()
                        hdl.fobj = None
                        if not hdl.success:
                                if hdl.fileprog:
                                        hdl.fileprog.abort()
                                try:
                                        os.remove(hdl.filepath)
                                except EnvironmentError as e:
                                        if e.errno != errno.ENOENT:
                                                raise \
                                                    tx.TransportOperationError(
                                                    "Unable to remove file: "
                                                    "{0}".format(e))
                        else:
                                if hdl.fileprog:
                                        filesz = os.stat(hdl.filepath).st_size
                                        hdl.fileprog.commit(filesz)
                                if hdl.filepath and hdl.filetime > -1:
                                        # Set atime/mtime, if we were able to
                                        # figure it out.  File action will
                                        # override this at install time, if the
                                        # action has a timestamp property.
                                        ft = hdl.filetime
                                        os.utime(hdl.filepath, (ft, ft))

                if hdl.r_fobj:
                        hdl.r_fobj.close()
                        hdl.r_fobj = None

                hdl.url = None
                hdl.repourl = None
                hdl.success = False
                hdl.filepath = None
                hdl.fileprog = None
                hdl.uuid = None
                hdl.filetime = -1
                hdl.starttime = -1


class TransportRequest(object):
        """A class that contains per-request information for the underlying
        transport engines.  This is used to set per-request options that
        are used either by the framework, the transport, or both."""

        def __init__(self, url, filepath=None, writefunc=None,
            hdrfunc=None, header=None, data=None, httpmethod="GET",
            progclass=None, progtrack=None, sslcert=None, sslkey=None,
            repourl=None, compressible=False, progfunc=None, uuid=None,
            read_fobj=None, read_filepath=None, failonerror=False, proxy=None,
            runtime_proxy=None, system=False):
                """Create a TransportRequest with the following parameters:

                url - The url that the transport engine should retrieve

                filepath - If defined, the transport engine will download the
                file to this path.  If not defined, the caller should
                supply a write function.

                writefunc - A function, supplied instead of filepath, that
                reads the bytes supplied by the transport engine and writes
                them somewhere for processing.  This is a callback.

                hdrfunc - A callback for examining the contents of header
                data in a response to a transport request.

                header - A dictionary of key/value pairs to be included
                in the request's header.

                compressible - A boolean value that indicates whether
                the content that is requested is a candidate for transport
                level compression.

                data - If the request is sending a data payload, include
                the data in this argument.

                failonerror - If the request returns a HTTP code >= 400,
                terminate the request early, instead of running it to
                completion.

                httpmethod - If the request is a HTTP/HTTPS request,
                this can override the default HTTP method of GET.

                progtrack - If the transport wants the engine to update
                the progress of the download, supply a ProgressTracker
                object in this argument.

                progclass - If the transport was supplied with a ProgressTracker
                this must point to a class that knows how to wrap the progress
                tracking object in way that allows the transport to invoke
                the proper callbacks.  The transport instantiates an object
                of this class before beginning the request.

                progfunc - A function to be used as a progress callback.
                The preferred method is is use progtrack/progclass, but
                light-weight implementations may use progfunc instead,
                especially if they don't need per-file updates.

                read_filepath - If the request is sending a file, include
                the path here, as this is the most efficient way to send
                the data.

                read_fobj - If the request is sending a large payload,
                this points to a fileobject from which the data may be
                read.

                repouri - This is the URL stem that identifies the repo.
                It's a subset of url.  It's also used by the stats system.

                sslcert - If the request is using SSL, HTTPS for example,
                provide a path to the SSL certificate here.

                sslkey - If the request is using SSL, like HTTPS for example,
                provide a path to the SSL key here.

                uuid - In order to remove the request from the list of
                many possible requests, supply a unique identifier in uuid.

                proxy - If the request should be performed using a proxy,
                that proxy should be specified here.

                runtime_proxy - In order to avoid repeated environment lookups
                we pass the proxy that should be used at runtime, which may
                differ from the 'proxy' value.

                system - whether this request is on behalf of a system
                publisher.  Usually this isn't necessary, as the
                TransportRepoURI will have been configured with correct proxy
                and runtime_proxy properties.  However, for direct access to
                resources served by the system-repository, we use this to
                prevent $http_proxy environment variables from being used.

                A TransportRequest must contain enough information to uniquely
                identify any pkg.client.publisher.TransportRepoURI - in
                particular, it must contain all fields used by
                TransportRepoURI.key() which is currently the (url, proxy)
                tuple, and is used as the key when recording/retrieving
                transport statistics."""

                self.url = url
                self.filepath = filepath
                self.writefunc = writefunc
                self.hdrfunc = hdrfunc
                self.header = header
                self.data = data
                self.httpmethod = httpmethod
                self.progclass = progclass
                self.progtrack = progtrack
                self.progfunc = progfunc
                self.repourl = repourl
                self.sslcert = sslcert
                self.sslkey = sslkey
                self.compressible = compressible
                self.uuid = uuid
                self.read_fobj = read_fobj
                self.read_filepath = read_filepath
                self.failonerror = failonerror
                self.proxy = proxy
                self.runtime_proxy = runtime_proxy
                self.system = system
