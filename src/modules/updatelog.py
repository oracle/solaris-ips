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

import errno
import os
import re
import tempfile

import pkg.client.api_errors as api_errors
import pkg.fmri as fmri
import pkg.portable as portable
import pkg.server.catalog as catalog

class UpdateLogException(Exception):
        def __init__(self, args=None):
                self._args = args

class UpdateLog(object):
        """Compatibility class for receiving incremental catalog updates from
        v0 repositories.

        The catalog format is a + or -, an isoformat timestamp, and a catalog
        entry in server-side format.  They must be in order and separated by
        spaces."""

        @staticmethod
        def recv(c, path, ts, pub):
                """Take a connection object and a catalog path.  This method
                receives a catalog from the server.  If it is an incremental
                update, it is processed by the updatelog.  If it is a full
                update, we call the catalog to handle the request.
                Ts is the timestamp when the local copy of the catalog
                was last modified."""

                update_type = c.getheader("X-Catalog-Type", "full")

                try:
                        if update_type == "incremental":
                                UpdateLog._recv_updates(c, path, ts)
                        else:
                                catalog.ServerCatalog.recv(c, path, pub)
                except EnvironmentError as e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

        @staticmethod
        def _recv_updates(filep, path, cts):
                """A static method that takes a file-like object, a path, and a
                timestamp.  It reads a stream as an incoming updatelog and
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

                for s in filep:

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
                                        line = "{0} {1}\n".format(l[2], l[3])
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
                                                except fmri.IllegalFmri as e:
                                                        bad_fmri = e
                                                        mts = pts
                                                        continue

                                                line = "{0} {1} {2} {3}\n".format(
                                                    l[2], "pkg", f.pkg_name,
                                                    f.version)
                                                add_lines.append(line)
                                                added += 1

                # If we got a parse error on FMRIs and transfer
                # wasn't truncated, raise a retryable transport
                if bad_fmri:
                        raise bad_fmri

                # Verify that they aren't already in the catalog
                catpath = os.path.normpath(os.path.join(path, "catalog"))

                tmp_num, tmpfile = tempfile.mkstemp(dir=path)
                tfile = os.fdopen(tmp_num, 'w')

                try:
                        pfile = open(catpath, "rb")
                except IOError as e:
                        if e.errno == errno.ENOENT:
                                # Creating an empty file
                                open(catpath, "wb").close()
                                pfile = open(catpath, "rb")
                        else:
                                tfile.close()
                                portable.remove(tmpfile)
                                raise
                pfile.seek(0)

                for c in pfile:
                        if c[0] in tuple("CV"):
                                npkgs += 1
                        if c in add_lines:
                                pfile.close()
                                tfile.close()
                                portable.remove(tmpfile)
                                raise UpdateLogException(
                                    "Package {0} is already in the catalog".format(
                                        c))
                        tfile.write(c)

                # Write the new entries to the catalog
                tfile.seek(0, os.SEEK_END)
                tfile.writelines(add_lines)
                if len(unknown_lines) > 0:
                        tfile.writelines(unknown_lines)
                tfile.close()
                pfile.close()

                os.chmod(tmpfile, catalog.ServerCatalog.file_mode)
                portable.rename(tmpfile, catpath)

                # Now re-write npkgs and Last-Modified in attributes file
                afile = open(os.path.normpath(os.path.join(path, "attrs")),
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
                apath = os.path.normpath(os.path.join(path, "attrs"))
                tmp_num, tmpfile = tempfile.mkstemp(dir=path)
                tfile = os.fdopen(tmp_num, 'w')

                for a in attrs.keys():
                        s = "S {0}: {1}\n".format(a, attrs[a])
                        tfile.write(s)

                tfile.close()
                os.chmod(tmpfile, catalog.ServerCatalog.file_mode)
                portable.rename(tmpfile, apath)

                return True

# Allow these methods to be invoked without explictly naming the UpdateLog
# class.
recv = UpdateLog.recv
