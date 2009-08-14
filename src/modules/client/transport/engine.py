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

import errno
import httplib
import os
import pycurl
import urlparse

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

from collections        import deque
from pkg.client         import global_settings

class TransportEngine(object):
        """This is an abstract class.  It shouldn't implement any
        of the methods that it contains.  Leave that to transport-specific
        implementations."""


class CurlTransportEngine(TransportEngine):
        """Concrete class of TransportEngine for libcurl transport."""

        def __init__(self, transport, max_conn=10):

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
                # Set default file buffer size at 128k, callers override
                # this setting after looking at VFS block size.
                self.__file_bufsz = 131072
                # Header bits and pieces
                self.__user_agent = None
                self.__common_header = {}

                # Set options on multi-handle
                self.__mhandle.setopt(pycurl.M_PIPELINING, 1)

                # initialize easy handles
                for i in range(self.__max_handles):
                        eh = pycurl.Curl()
                        eh.url = None
                        eh.repourl = None
                        eh.fobj = None
                        eh.filepath = None
                        eh.success = False
                        eh.fileprog = None
                        eh.filetime = -1
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
            progtrack=None, sslcert=None, sslkey=None, repourl=None):
                """Add a URL to the transport engine.  Caller must supply
                either a filepath where the file should be downloaded,
                or a callback to a function that will peform the write.
                It may also optionally supply header information
                in a dictionary.  If the caller has a ProgressTracker,
                supply the object in the progtrack argument."""

                t = TransportRequest(url, filepath=filepath,
                    writefunc=writefunc, header=header, progtrack=progtrack,
                    sslcert=sslcert, sslkey=sslkey, repourl=repourl)

                self.__req_q.appendleft(t)

        def __cleanup_requests(self):
                """Cleanup handles that have finished their request.
                Return the handles to the freelist.  Generate any
                relevant error information."""

                count, good, bad = self.__mhandle.info_read()
                failures = self.__failures
                done_handles = []
                ex_to_raise = None

                for h, en, em in bad:

                        # Get statistics for each handle.
                        repostats = self.__xport.stats[h.repourl]
                        repostats.record_tx()
                        bytes = h.getinfo(pycurl.SIZE_DOWNLOAD)
                        seconds = h.getinfo(pycurl.TOTAL_TIME)
                        repostats.record_progress(bytes, seconds)

                        httpcode = h.getinfo(pycurl.RESPONSE_CODE)
                        url = h.url
                        urlstem = h.repourl
                        proto = urlparse.urlsplit(url)[0]

                        # All of these are errors
                        repostats.record_error()

                        # If we were cancelled, raise an API error.
                        # Otherwise fall through to transport's exception
                        # generation.
                        if en == pycurl.E_ABORTED_BY_CALLBACK:
                                ex = None
                                ex_to_raise = api_errors.CanceledException
                        elif en == pycurl.E_HTTP_RETURNED_ERROR:
                                ex = tx.TransportProtoError(proto, httpcode,
                                    url, repourl=urlstem)
                        else:
                                ex = tx.TransportFrameworkError(en, url, em,
                                    repourl=urlstem)

                        if ex and ex.retryable:
                                failures.append(ex) 
                        elif ex and not ex_to_raise:
                                ex_to_raise = ex

                        done_handles.append(h)

                for h in good:
                        # Get statistics for each handle.
                        repostats = self.__xport.stats[h.repourl]
                        repostats.record_tx()
                        bytes = h.getinfo(pycurl.SIZE_DOWNLOAD)
                        seconds = h.getinfo(pycurl.TOTAL_TIME)
                        h.filetime = h.getinfo(pycurl.INFO_FILETIME)
                        repostats.record_progress(bytes, seconds)

                        httpcode = h.getinfo(pycurl.RESPONSE_CODE)
                        url = h.url
                        urlstem = h.repourl
                        proto = urlparse.urlsplit(url)[0]

                        if httpcode == httplib.OK:
                                h.success = True
                        else:
                                ex = tx.TransportProtoError(proto,
                                    httpcode, url, repourl=urlstem)

                                # If code >= 400, record this as an error.
                                # Handlers above the engine get to decide
                                # for 200/300 codes that aren't OK
                                if httpcode >= 400: 
                                        repostats.record_error()
                                # If code == 0, libcurl failed to read
                                # any HTTP status.  Response is almost
                                # certainly corrupted.
                                elif httpcode == 0:
                                        reason = "Invalid HTTP status code " \
                                            "from server" 
                                        ex = tx.TransportProtoError(proto,
                                            url=url, reason=reason,
                                            repourl=urlstem)
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

                if ex_to_raise:
                        raise ex_to_raise

        def check_status(self, urllist=None):
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
                by the transport engine as soon as they occur."""

                # if list not specified, return all failures
                if not urllist:
                        rf = self.__failures
                        self.__failures = []

                        return rf

                # otherwise, look for failures that match just the URLs
                # in urllist.
                rf = []

                for tf in self.__failures:
                        if hasattr(tf, "url") and tf.url in urllist:
                                rf.append(tf)

                # remove failues in separate pass, or else for loop gets
                # confused.
                for f in rf:
                        self.__failures.remove(f)

                return rf

        def get_url(self, url, header=None, sslcert=None, sslkey=None,
            repourl=None, compressible=False):
                """Invoke the engine to retrieve a single URL.  Callers
                wishing to obtain multiple URLs at once should use
                addUrl() and run().

                getUrl will return a read-only file object that allows access
                to the URL's data."""

                fobj = fileobj.StreamingFileObj(url, self)

                t = TransportRequest(url, writefunc=fobj.get_write_func(),
                    hdrfunc=fobj.get_header_func(), header=header,
                    sslcert=sslcert, sslkey=sslkey, repourl=repourl,
                    compressible=compressible)

                self.__req_q.appendleft(t)

                return fobj

        def get_url_header(self, url, header=None, sslcert=None, sslkey=None,
            repourl=None):
                """Invoke the engine to retrieve a single URL's headers.

                getUrlHeader will return a read-only file object that
                contains no data."""

                fobj = fileobj.StreamingFileObj(url, self)

                t = TransportRequest(url, writefunc=fobj.get_write_func(),
                    hdrfunc=fobj.get_header_func(), header=header,
                    httpmethod="HEAD", sslcert=sslcert, sslkey=sslkey,
                    repourl=repourl)

                self.__req_q.appendleft(t)

                return fobj

        @property
        def pending(self):
                """Returns true if the engine still has outstanding
                work to perform, false otherwise."""

                return len(self.__req_q) > 0 or self.__active_handles > 0

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

                while self.__freehandles and self.__req_q:
                        t = self.__req_q.pop()
                        eh = self.__freehandles.pop(-1)
                        self.__setup_handle(eh, t)
                        self.__mhandle.add_handle(eh)

                self.__call_perform()

                self.__cleanup_requests()


        def remove_request(self, url):
                """In order to remove a request, it may be necessary
                to walk all of the items in the request queue, all of the
                currently active handles, and the list of any transient
                failures.  This is expensive, so only remove a request
                if absolutely necessary."""

                for h in self.__chandles:
                        if h.url == url and h not in self.__freehandles:
                                self.__mhandle.remove_handle(h)
                                self.__teardown_handle(h)
                                return

                for i, t in enumerate(self.__req_q):
                        if t.url == url:
                                del self.__req_q[i]
                                return

                for ex in self.__failures:
                        if ex.url == url:
                                self.__failures.remove(ex)
                                return

        def reset(self):
                """Reset the state of the transport engine.  Do this
                before performing another type of request."""

                for c in self.__chandles:
                        if c not in self.__freehandles:
                                self.__mhandle.remove_handle(c)
                                self.__teardown_handle(c)

                self.__active_handles = 0
                self.__freehandles = self.__chandles[:]
                self.__req_q = deque()

        def send_data(self, url, data, header=None, sslcert=None, sslkey=None,
            repourl=None):
                """Invoke the engine to retrieve a single URL.  
                This routine sends the data in data, and returns the
                server's response.  

                Callers wishing to obtain multiple URLs at once should use
                addUrl() and run().

                sendData will return a read-only file object that allows access
                to the server's response.."""

                fobj = fileobj.StreamingFileObj(url, self)

                t = TransportRequest(url, writefunc=fobj.get_write_func(),
                    hdrfunc=fobj.get_header_func(), header=header, data=data,
                    httpmethod="POST", sslcert=sslcert, sslkey=sslkey,
                    repourl=repourl)

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

                # Make sure that we don't use a proxy if the destination
                # is localhost.
                hdl.setopt(pycurl.NOPROXY, "localhost")

                # Set user agent, if client has defined it
                if self.__user_agent:
                        hdl.setopt(pycurl.USERAGENT, self.__user_agent)

                # Take header dictionaries and convert them into lists
                # of header strings.
                if len(self.__common_header) > 0 or \
                    (treq.header and len(treq.header) > 0):

                        headerlist = []

                        # Headers common to all requests
                        for k, v in self.__common_header.iteritems():
                                headerstr = "%s: %s" % (k, v)
                                headerlist.append(headerstr)

                        # Headers specific to this request
                        if treq.header:
                                for k, v in treq.header.iteritems():
                                        headerstr = "%s: %s" % (k, v)
                                        headerlist.append(headerstr)

                        hdl.setopt(pycurl.HTTPHEADER, headerlist)

                # Set request url.  Also set attribute on handle.
                hdl.setopt(pycurl.URL, treq.url)
                hdl.url = treq.url
                # The repourl is the url stem that identifies the
                # repository. This is useful to have around for coalescing
                # error output, and statistics reporting.
                hdl.repourl = treq.repourl
                if treq.filepath:
                        try:
                                hdl.fobj = open(treq.filepath, "wb+",
                                    self.__file_bufsz)
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                # Raise OperationError if it's not EACCES
                                raise tx.TransportOperationError(
                                    "Unable to open file: %s" % e)
         
                        hdl.setopt(pycurl.WRITEDATA, hdl.fobj)
                        # Request filetime, if endpoint knows it.
                        hdl.setopt(pycurl.OPT_FILETIME, True)
                        hdl.filepath = treq.filepath
                elif treq.writefunc:
                        hdl.setopt(pycurl.WRITEFUNCTION, treq.writefunc)
                        hdl.setopt(pycurl.FAILONERROR, True)
                        hdl.filepath = None
                        hdl.fobj = None
                else:
                        raise tx.TransportOperationError("Transport invocation"
                            " for URL %s did not specify filepath or write"
                            " function." % treq.url)

                if treq.progtrack:
                        hdl.setopt(pycurl.NOPROGRESS, 0)
                        hdl.fileprog = FileProgress(treq.progtrack)
                        hdl.setopt(pycurl.PROGRESSFUNCTION,
                            hdl.fileprog.progress_callback)

                if treq.compressible:
                        hdl.setopt(pycurl.ENCODING, "")

                if treq.hdrfunc:
                        hdl.setopt(pycurl.HEADERFUNCTION, treq.hdrfunc)

                if treq.httpmethod == "HEAD":
                        hdl.setopt(pycurl.NOBODY, True)
                elif treq.httpmethod == "POST":
                        hdl.setopt(pycurl.POST, True)
                        hdl.setopt(pycurl.POSTFIELDS, treq.data)
                else:
                        # Default to GET
                        hdl.setopt(pycurl.HTTPGET, True)

                # Set up SSL options
                if treq.sslcert:
                        hdl.setopt(pycurl.SSLCERT, treq.sslcert)
                if treq.sslkey:
                        hdl.setopt(pycurl.SSLKEY, treq.sslkey)
                # Options that apply when SSL is enabled
                if treq.sslcert or treq.sslkey:
                        # Verify that peer's CN matches CN on certificate
                        hdl.setopt(pycurl.SSL_VERIFYHOST, 2)

                        cadir = self.__xport.get_ca_dir()
                        if cadir:
                                hdl.setopt(pycurl.SSL_VERIFYPEER, 1)
                                hdl.setopt(pycurl.CAPATH, cadir)
                                hdl.unsetopt(pycurl.CAINFO)
                        else:
                                hdl.setopt(pycurl.SSL_VERIFYPEER, 0)

        def __shutdown(self):
                """Shutdown the transport engine, perform cleanup."""

                self.reset()

                for c in self.__chandles:
                        c.close()

                self.__chandles = None
                self.__freehandles = None
                self.__mhandle.close()
                self.__mhandle = None

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
                                except EnvironmentError, e:
                                        if e.errno != errno.ENOENT:
                                                raise \
                                                    tx.TransportOperationError(
                                                    "Unable to remove file: %s"
                                                    % e)
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


                hdl.url = None
                hdl.repourl = None
                hdl.success = False
                hdl.filepath = None
                hdl.fileprog = None
                hdl.filetime = -1


class FileProgress(object):
        """This class bridges the interfaces between a ProgressTracker
        object and the progress callback that's provided by Pycurl.
        Since progress callbacks are per curl handle, and handles aren't
        guaranteed to succeed, this object watches a handle's progress
        and updates the tracker accordingly.  If the handle fails,
        it will correctly remove the bytes from the file.  The curl
        callback reports bytes even when it doesn't make progress.
        It's necessary to keep additonal state here, since the client's
        ProgressTracker has global counts of the bytes.  If we're
        unable to keep a per-file count, the numbers will get
        lost quickly."""

        def __init__(self, progtrack):
                self.progtrack = progtrack
                self.dltotal = 0
                self.dlcurrent = 0
                self.completed = False

        def abort(self):
                """Download failed.  Remove the amount of bytes downloaded
                by this file from the ProgressTracker."""

                self.progtrack.download_add_progress(0, -self.dlcurrent)
                self.completed = True

        def commit(self, size):
                """Indicate that this download has succeeded.  The size
                argument is the total size that we received.  Compare this
                value against the dlcurrent.  If it's out of sync, which
                can happen if the underlying framework swaps our request
                across connections, adjust the progress tracker by the
                amount we're off."""

                adjustment = int(size - self.dlcurrent)

                self.progtrack.download_add_progress(1, adjustment)
                self.completed = True

        def progress_callback(self, dltot, dlcur, ultot, ulcur):
                """Called by pycurl/libcurl framework to update
                progress tracking."""

                if hasattr(self.progtrack, "check_cancelation") and \
                    self.progtrack.check_cancelation():
                        return -1

                if self.completed:
                        return 0

                if self.dltotal != dltot:
                        self.dltotal = dltot

                new_progress = int(dlcur - self.dlcurrent)
                if new_progress > 0:
                        self.dlcurrent += new_progress
                        self.progtrack.download_add_progress(0, new_progress)

                return 0


class TransportRequest(object):
        """A class that contains per-request information for the underlying
        transport engines.  This is used to set per-request options that
        are used either by the framework, the transport, or both."""

        def __init__(self, url, filepath=None, writefunc=None,
            hdrfunc=None, header=None, data=None, httpmethod="GET",
            progtrack=None, sslcert=None, sslkey=None, repourl=None,
            compressible=False):
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

                httpmethod - If the request is a HTTP/HTTPS request,
                this can override the default HTTP method of GET.

                progtrack - If the transport wants the engine to update
                the progress of the download, supply a ProgressTracker
                object in this argument.

                repouri - This is the URL stem that identifies the repo.
                It's a subset of url.  It's also used by the stats system.

                sslcert - If the request is using SSL, HTTPS for example,
                provide a path to the SSL certificate here.

                sslkey - If the request is using SSL, liks HTTPS for example,
                provide a path to the SSL key here."""

                self.url = url
                self.filepath = filepath
                self.writefunc = writefunc
                self.hdrfunc = hdrfunc
                self.header = header
                self.data = data
                self.httpmethod = httpmethod
                self.progtrack = progtrack
                self.repourl = repourl
                self.sslcert = sslcert
                self.sslkey = sslkey
                self.compressible = compressible
