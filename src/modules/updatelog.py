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
#

import datetime
import httplib
import os
import re
import time

import pkg.fmri as fmri
import pkg.catalog as catalog
from pkg.misc import TruncatedTransferException

class UpdateLogException(Exception):
        def __init__(self, args=None):
                self.args = args

class UpdateLog(object):
        """The update log is a mechanism that allows clients and servers to
        make incremental updates to their package catalogs.  The server logs
        whether it has added or removed a package, the time when the action
        occurred, and the name of the package added or removed.  The client
        requests a list of actions that have been applied to the server's
        catalog since a particular time in the past.  The server is then able
        to send this list of actions, allowing the client to apply these
        changes to its catalog.

        This allows the client to obtain incremental updates to its catalog,
        instead of having to download an entire (and largely duplicated)
        catalog each time a refresh is requested.

        The UpdateLog must have an associated catalog; however,
        Catalogs are not required to have an UpdateLog.  The UpdateLog
        allows catalogs to support incremental updates.

        The catalog format is a + or -, an isoformat timestamp, and a catalog
        entry in server-side format.  They must be in order and separated by
        spaces."""

        def __init__(self, update_root, cat, maxfiles = 336):
                """Create an instance of the UpdateLog.  "update_root" is
                the root directory for the update log files.

                maxfiles is the maximum number of logfiles that
                the UpdateLog will keep.  A new file is added
                for each hour in which there is an update.  The
                default value of 336 means that we keep 336 hours, or
                14 days worth of log history."""

                self.rootdir = update_root
                self.logfd = None
                self.log_filename = None
                self.maxfiles = maxfiles
                self.catalog = cat
                self.close_time = None
                self.first_update = None
                self.last_update = None
                self.curfiles = 0
                self.logfiles = []
                self.logfile_size = {}

                if not os.path.exists(update_root):
                        os.makedirs(update_root)

                self._setup_logfiles()

        def __del__(self):
                """Perform any last minute cleanup."""

                if self.logfd:
                        try:
                                self.logfd.close()
                        except EnvironmentError:
                                pass

                        self.logfd = None

        def add_package(self, pfmri, critical = False):
                """Record that the catalog has added "pfmri"."""

                # First add FMRI to catalog
                ts = self.catalog.add_fmri(pfmri, critical)

                # Now add update to updatelog
                self._check_logs()

                if not self.logfd:
                        self._begin_log()

                if critical:
                        entry_type = "C"
                else:
                        entry_type = "V"

                # The format for catalog C and V records is described
                # in the docstrings for the Catalog class.

                logstr = "+ %s %s %s\n" % \
                    (ts.isoformat(), entry_type, pfmri.get_fmri(anarchy=True))

                self.logfd.write(logstr)
                self.logfd.flush()

                if self.log_filename in self.logfile_size:
                        del self.logfile_size[self.log_filename]

                self.last_update = ts

                return ts

        def rename_package(self, srcname, srcvers, destname, destvers):
                """Record that package oldname has been renamed to newname,
                effective as of version vers."""

                # Record rename in catalog
                ts, rr = self.catalog.rename_package(srcname, srcvers,
                     destname, destvers)

                # Now add rename record to updatelog
                self._check_logs()

                if not self.logfd:
                        self._begin_log()

                # The format for a catalog rename record is described
                # in the docstring for the RenameRecord class.

                logstr = "+ %s %s\n" % (ts.isoformat(), rr)

                self.logfd.write(logstr)
                self.logfd.flush()

                if self.log_filename in self.logfile_size:
                        del self.logfile_size[self.log_filename]

                self.last_update = ts

                return ts

        def _begin_log(self):
                """Open a log-file so that the UpdateLog can write updates
                into it."""

                filenm = time.strftime("%Y%m%d%H")

                ftime = datetime.datetime(
                    *time.strptime(filenm, "%Y%m%d%H")[0:6])
                delta = datetime.timedelta(hours=1)

                self.close_time = ftime + delta

                self.log_filename = filenm
                self.logfd = file(os.path.join(self.rootdir, filenm), "a")

                if filenm not in self.logfiles:
                        self.logfiles.append(filenm)
                        self.curfiles += 1

                if not self.first_update:
                        self.first_update = ftime

        def _check_logs(self):
                """Check to see if maximum number of logfiles has been
                exceeded. If so, rotate the logs.  Also, if a log is
                open, check to see if it needs to be closed."""

                if self.logfd and self.close_time < datetime.datetime.now():
                        self.logfd.close()
                        self.logfd = None
                        self.log_filename = None
                        self.close_time = 0

                if self.curfiles < self.maxfiles:
                        return

                excess = self.curfiles - self.maxfiles

                to_remove = self.logfiles[0:excess]

                for r in to_remove:
                        filepath = os.path.join(self.rootdir, "%s" % r)
                        os.unlink(filepath)
                        self.curfiles -= 1
                        if r in self.logfile_size:
                                del self.logfile_size[r]

                del self.logfiles[0:excess]

                self.first_update = datetime.datetime(*time.strptime(
                    self.logfiles[0], "%Y%m%d%H")[0:6])

        def enough_history(self, ts):
                """Returns true if the timestamp is so far behind the
                update log, that there is not enough log history to bring
                the client up to date."""

                # Absence of server-side log history also counts as
                # not enough history.
                if not self.last_update or not self.first_update:
                        return False

                if ts < self.first_update:
                        return False

                return True

        @staticmethod
        def recv(c, path, ts, auth):
                """Take a connection object and a catalog path.  This method
                receives a catalog from the server.  If it is an incremental
                update, it is processed by the updatelog.  If it is a full
                update, we call the catalog to handle the request.
                Ts is the timestamp when the local copy of the catalog
                was last modified."""

                update_type = c.info().getheader("X-Catalog-Type", "full")

                cl_size = int(c.info().getheader("Content-Length", "-1"))

                if update_type == 'incremental':
                        UpdateLog._recv_updates(c, path, ts, cl_size)
                else:
                        catalog.recv(c, path, auth, cl_size)


        @staticmethod
        def _recv_updates(filep, path, cts, content_size=-1):
                """A static method that takes a file-like object,
                a path, and a timestamp.  This is the other half of
                send_updates().  It reads a stream as an incoming updatelog and
                modifies the catalog on disk."""

                if not os.path.exists(path):
                        os.makedirs(path)

                # Build a list of FMRIs that this update would add, check to
                # make sure that they aren't present in the catalog, then
                # append the fmris.
                mts = catalog.ts_to_datetime(cts)
                cts = mts
                pts = mts
                added = 0
                npkgs = 0
                add_lines = []
                unknown_lines = []
                bad_fmri = None
                attrs = {}
                size = 0

                for s in filep:

                        size += len(s)

                        l = s.split(None, 3)
                        if len(l) < 4:
                                continue

                        elif l[2] not in catalog.known_prefixes:
                                # Add unknown line directly to catalog.
                                # This can be post-processed later, when it
                                # becomes known.
                                #
                                # XXX Notify user that unknown entry was added?
                                ts = catalog.ts_to_datetime(l[1])
                                if ts > cts:
                                        if ts > mts:
                                                pts = mts
                                                mts = ts
                                        line = "%s %s\n" % (l[2], l[3])
                                        unknown_lines.append(line)

                        elif l[0] == "+":
                                # This is a known entry type.
                                # Create a list of FMRIs to add, since
                                # additional inspection is required
                                ts = catalog.ts_to_datetime(l[1])
                                if ts > cts:
                                        if ts > mts:
                                                pts = mts
                                                mts = ts

                                        # The format for C and V records
                                        # is described in the Catalog's
                                        # docstring.
                                        if l[2] in tuple("CV"):
                                                try:
                                                        f = fmri.PkgFmri(l[3])
                                                except fmri.IllegalFmri, e:
                                                        bad_fmri = e
                                                        mts = pts
                                                        continue

                                                line = "%s %s %s %s\n" % \
                                                    (l[2], "pkg", f.pkg_name,
                                                    f.version)
                                                add_lines.append(line)
                                                added += 1

                                        # The format for R records is
                                        # described in the docstring for
                                        # RenameRecords
                                        elif l[2] == "R":
                                                sf, sv, rf, rv = l[3].split()
                                                line = "%s %s %s %s %s\n" % \
                                                    (l[2], sf, sv, rf, rv)
                                                add_lines.append(line)

                # Check that content was properly received before
                # modifying any files.
                if content_size > -1 and size != content_size:
                        url = None
                        if hasattr(filep, "geturl") and callable(filep.geturl):
                                url = filep.geturl()
                        raise TruncatedTransferException(url, size,
                            content_size)

                # If we got a parse error on FMRIs and transfer
                # wasn't truncated, raise a retryable transport
                elif bad_fmri:
                        raise bad_fmri

                # Verify that they aren't already in the catalog
                catf = file(os.path.normpath(
                    os.path.join(path, "catalog")), "a+")
                catf.seek(0)
                for c in catf:
                        if c[0] in tuple("CV"):
                                npkgs += 1
                        if c in add_lines:
                                catf.close()
                                raise UpdateLogException, \
                                    "Package %s is already in the catalog" % \
                                        c

                # Write the new entries to the catalog
                catf.seek(0, 2)
                catf.writelines(add_lines)
                if len(unknown_lines) > 0:
                        catf.writelines(unknown_lines)
                catf.close()

                # Now re-write npkgs and Last-Modified in attributes file
                afile = file(os.path.normpath(os.path.join(path, "attrs")),
                    "r")
                attrre = re.compile('^S ([^:]*): (.*)')

                for entry in afile:
                        m = attrre.match(entry)
                        if m != None:
                                attrs[m.group(1)] = m.group(2)

                afile.close()

                # Update the attributes we care about
                attrs["npkgs"] = npkgs + added
                attrs["Last-Modified"] = mts.isoformat()

                # Write attributes back out
                afile = file(os.path.normpath(os.path.join(path, "attrs")),
                    "w")
                for a in attrs.keys():
                        s = "S %s: %s\n" % (a, attrs[a])
                        afile.write(s)

                afile.close()

                return True

        def send(self, request, response):
                """This method takes a http request and sends a catalog
                to the client.  If the client is capable of receiving an
                incremental update, we'll send that.  Otherwise, it calls
                into the catalog to send a full copy."""

                modified = request.headers.get("If-Modified-Since", None)
                ts = None

                if modified:
                        try:
                                ts = catalog.ts_to_datetime(modified)
                        except ValueError:
                                ts = None

                # Incremental catalog updates
                response.headers['Content-type'] = 'text/plain'
                if ts and self.up_to_date(ts):
                        response.status = httplib.NOT_MODIFIED
                        response.headers['Last-Modified'] = \
                            self.catalog.last_modified()
                        response.headers['X-Catalog-Type'] = 'incremental'
                        return
                elif ts and self.enough_history(ts):
                        response.headers['Last-Modified'] = \
                            self.catalog.last_modified()
                        response.headers['X-Catalog-Type'] = 'incremental'
                        return self._send_updates(ts, None, response)
                else:
                        # Not enough history, or full catalog requested
                        response.headers['X-Catalog-Type'] = 'full'
                        return self.catalog.send(None, response)

        def _gen_updates(self, ts):
                """Look through the logs for updates that have occurred after
                the timestamp.  Yield each of those updates in line-update
                format."""

                # The files that need to be examined depend upon the timestamp
                # supplied by the client, and the log files actually present.
                #
                # The following cases exist:
                #
                # 1. No updates have occurred since timestamp.  Send nothing.
                #
                # 2. Timestamp is older than oldest log record.  Client needs
                # to download full catalog.
                #
                # 3. Timestamp falls within a range for which update records
                # exist.  If the timestamp is in the middle of a log-file, send
                # the entire file -- the client will pick what entries to add.
                # Then send all newer files.

                rts = datetime.datetime(ts.year, ts.month, ts.day, ts.hour)
                assert rts <= ts

                # send data from logfiles newer or equal to rts
                for lf in self.logfiles:

                        lf_time = datetime.datetime(
                            *time.strptime(lf, "%Y%m%d%H")[0:6])

                        if lf_time >= rts:
                                fn = "%s" % lf
                                logf = file(os.path.join(self.rootdir, fn),
                                    "r")
                                for line in logf:
                                        yield line
                                logf.close()

        def gen_updates_as_dictionaries(self, ts):
                """Look through the logs for updates that have occurred after
                the timestamp.  Yield each of those updates in dictionary form,
                with values for operation, timestamp, and the catalog entry."""

                for line in self._gen_updates(ts):
                        flds = line.split(None, 2)
                        ret = {
                            "operation": flds[0],
                            "timestamp": flds[1],
                            "catalog": flds[2]
                        }

                        yield ret

        def _send_updates(self, ts, filep, rspobj=None):
                """Look through the logs for updates that have occurred after
                timestamp.  Write these changes to the file-like object
                supplied in filep."""

                if self.up_to_date(ts) or not self.enough_history(ts):
                        return

                if rspobj is not None:
                        rspobj.headers['Content-Length'] = str(self.size(ts))

                if filep:
                        for line in self._gen_updates(ts):
                                filep.write(line)
                else:
                        return self._gen_updates(ts)

        def _setup_logfiles(self):
                """Scans the directory containing the update log's files.
                Sets up any necessary state for the UpdateLog."""

                # Store names of logfiles as integers for easier comparison
                self.logfiles = [f for f in os.listdir(self.rootdir)]
                self.logfiles.sort()
                self.curfiles = len(self.logfiles)

                if self.curfiles == 0:
                        self.last_update = None
                        self.first_update = None
                        return

                # Find the last update by opening the most recent logfile
                # and finding its last entry

                filenm = self.logfiles[self.curfiles - 1]
                logf = file(os.path.join(self.rootdir, filenm), "r")

                last_update = None

                for ln in logf:
                        lspl = ln.split(" ", 4)
                        if len(lspl) < 4:
                                continue

                        current_ts = catalog.ts_to_datetime(lspl[1])

                        if not last_update or current_ts > last_update:
                                last_update = current_ts

                logf.close()
                self.last_update = last_update
                self.first_update = datetime.datetime(
                    *time.strptime(self.logfiles[0], "%Y%m%d%H")[0:6])

        def size(self, ts):
                """Return the size in bytes of an update starting at time
                ts."""

                size = 0
                rts = datetime.datetime(ts.year, ts.month, ts.day, ts.hour)
                assert rts <= ts

                for lf in self.logfiles:

                        lf_time = datetime.datetime(
                            *time.strptime(lf, "%Y%m%d%H")[0:6])

                        if lf_time >= rts:

                                if lf in self.logfile_size:
                                        size += self.logfile_size[lf]
                                else:
                                        stat_logf = os.stat(os.path.join(
                                            self.rootdir, lf))
                                        entsz = stat_logf.st_size
                                        self.logfile_size[lf] = entsz
                                        size += entsz
                return size

        def up_to_date(self, ts):
                """Returns true if the timestamp is up to date."""

                if self.last_update and ts >= self.last_update:
                        return True

                return False

# Allow these methods to be invoked without explictly naming the UpdateLog
# class.
recv = UpdateLog.recv

