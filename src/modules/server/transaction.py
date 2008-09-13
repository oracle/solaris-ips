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

import cherrypy
import errno
import httplib
import logging
import os
import re
import sha
import shutil
import time
import datetime
import calendar
import urllib
import stat

import pkg.actions
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.portable as portable
from pkg.pkggzip import PkgGzipFile

try:
        import pkg.elf as elf
        haveelf = True
except ImportError:
        haveelf = False

class Transaction(object):
        """A Transaction is a server-side object used to represent the set of
        incoming changes to a Package.  Manipulation of Transaction objects in
        the repository server is generally initiated by a package publisher,
        such as pkgsend(1M)."""

        def __init__(self):
                # XXX Need to use an FMRI object.
                self.open_time = None
                self.pkg_name = ""
                self.esc_pkg_name = ""
                self.critical = False
                self.cfg = None
                self.client_release = ""
                self.fmri = None
                self.dir = ""
                return

        def get_basename(self):
                assert self.open_time
                # XXX should the timestamp be in ISO format?
                return "%d_%s" % \
                    (calendar.timegm(self.open_time.utctimetuple()),
                    urllib.quote("%s" % self.fmri, ""))

        def open(self, cfg, *tokens):
                self.cfg = cfg

                request = cherrypy.request
                self.client_release = request.headers.get("Client-Release",
                    None)
                if self.client_release == None:
                        # If client_release is not defined, then this request is
                        # invalid.
                        #
                        # XXX should test whether client-release string is
                        # a valid dotsequence
                        return (httplib.BAD_REQUEST,
                            "Client-Release header missing") 

                try:
                        self.pkg_name = tokens[0]
                        # cherrypy decoded it, but we actually need it encoded.
                        self.esc_pkg_name = urllib.quote("%s" % tokens[0], "")
                except IndexError:
                        return (httplib.BAD_REQUEST, "Missing Package Name")

                self.open_time = datetime.datetime.utcnow()

                # record transaction metadata:  opening_time, package, user

                # attempt to construct an FMRI object
                try:
                        self.fmri = fmri.PkgFmri(self.pkg_name,
                            self.client_release)
                except fmri.IllegalFmri, e:
                        return (httplib.BAD_REQUEST, str(e))

                # We must have a version supplied for publication.
                if self.fmri.version == None:
                        return (httplib.BAD_REQUEST, "Missing Version")

                self.fmri.set_timestamp(self.open_time)

                # Check that the new FMRI's version is valid.  I.e. the package
                # has not been renamed or frozen for the new version.
                if not self.cfg.catalog.valid_new_fmri(self.fmri):
                        return (httplib.BAD_REQUEST, "Invalid version")

                trans_basename = self.get_basename()
                self.dir = "%s/%s" % (self.cfg.trans_root, trans_basename)
                os.makedirs(self.dir)

                #
                # always create a minimal manifest
                #
                tfile = file("%s/manifest" % self.dir, "a")
                print >> tfile,  "# %s, client release %s" % (self.pkg_name,
                    self.client_release)
                tfile.close()

                # validate that this version can be opened
                #   if we specified no release, fail
                #   if we specified a release without branch, open next branch
                #   if we specified a release with branch major, open same
                #     branch minor
                #   if we specified a release with branch major and minor, use
                #   as specified
                # we should disallow new package creation, if so flagged

                # if not found, create package
                # set package state to TRANSACTING

                return (httplib.OK, None)

        def reopen(self, cfg, trans_dir):
                """The reopen() method is invoked on server restart, to
                reestablish the status of inflight transactions."""

                self.cfg = cfg
                open_time_str, self.esc_pkg_name = \
                    os.path.basename(trans_dir).split("_", 1)
                self.open_time = \
                    datetime.datetime.utcfromtimestamp(int(open_time_str))
                self.pkg_name = urllib.unquote(self.esc_pkg_name)

                # This conversion should always work, because we encoded the
                # client release on the initial open of the transaction.
                self.fmri = fmri.PkgFmri(self.pkg_name, None)

                self.dir = "%s/%s" % (self.cfg.trans_root, self.get_basename())

        def close(self):
                response = cherrypy.response

                def split_trans_id(tid):
                        m = re.match("(\d+)_(.*)", tid)
                        return m.group(1), urllib.unquote(m.group(2))

                trans_id = self.get_basename()
                timestamp, pkg_fmri = split_trans_id(trans_id)

                # set package state to SUBMITTED
                pkg_state = "SUBMITTED"

                # attempt to reconcile dependencies
                # XXX These shouldn't be booleans, but instead return non-empty
                # lists for the unsatisified cases.
                declarations_good = self.has_satisfied_declarations()
                implicit_good = self.has_satisfied_implicit()

                # if reconciled, set state to PUBLISHED
                if declarations_good and implicit_good:
                        pkg_fmri, pkg_state = self.accept_publish()
                else:
                        pkg_fmri = self.accept_incomplete()
                        pkg_state = "INCOMPLETE"
                        # XXX Build a response from our lists of unsatisfied
                        # dependencies.

                try:
                        shutil.rmtree("%s/%s" % (self.cfg.trans_root, trans_id))
                except:
                        cherrypy.log(
                            "pkg.depotd: couldn't remove transaction %s"
                            % trans_id, severity = logging.CRITICAL,
                            traceback = True)

                response.headers['Package-FMRI'] = pkg_fmri
                response.headers['State'] = pkg_state
                return

        def abandon(self):
                trans_id = self.get_basename()
                # XXX refine try/except
                #
                # state transition from TRANSACTING to ABANDONED
                try:
                        shutil.rmtree("%s/%s" % (self.cfg.trans_root, trans_id))
                except:
                        raise cherrypy.HTTPError(httplib.NOT_FOUND)

        def add_content(self, entry_type):
                """XXX We're currently taking the file from the HTTP request
                directly onto the heap, to make the hash computation convenient.
                We then do the compression as a sequence of buffers.  To handle
                large files, we'll need to process the incoming data as a
                sequence of buffers as well, with intermediate storage to
                disk."""

                request = cherrypy.request
                attrs = dict(
                    val.split("=", 1)
                    for hdr, val in request.headers.items()
                    if hdr.lower().startswith("x-ipkg-setattr")
                )

                # If any attributes appear to be lists, make them lists.
                for a in attrs:
                        if attrs[a].startswith("[") and attrs[a].endswith("]"):
                                attrs[a] = eval(attrs[a])

                size = int(request.headers.get("Content-Length", 0))

                # The request object always has a readable rfile, even if it'll
                # return no data.  We check ahead of time to see if we'll get
                # any data, and only create the object with data if there will
                # be any.
                rfile = None
                if size > 0:
                        rfile = request.rfile
                # XXX Ugly special case to handle empty files.
                elif entry_type == "file":
                        rfile = os.devnull
                action = pkg.actions.types[entry_type](rfile, **attrs)

                # XXX Once actions are labelled with critical nature.
                # if entry_type in critical_actions:
                #         self.critical = True

                # Record the size of the payload, if there is one.
                if size > 0:
                        action.attrs["pkg.size"] = str(size)

                if action.data != None:
                        bufsz = 64 * 1024

                        # Read in the data in chunks.  A large read on 
                        # Windows XP fails.
                        databufs = []
                        sz = size
                        while sz > 0:
                                data = action.data().read(min(bufsz, sz))
                                databufs.append(data)
                                sz -= len(data)
                        data = "".join(databufs)

                        # Extract ELF information
                        # XXX This needs to be modularized.
                        if haveelf and data[:4] == "\x7fELF":
                                elf_name = "%s/.temp" % self.dir
                                elf_file = open(elf_name, "wb")
                                elf_file.write(data)
                                elf_file.close()
                                elf_info = elf.get_info(elf_name)
                                elf_hash = elf.get_dynamic(elf_name)["hash"]
                                action.attrs["elfbits"] = str(elf_info["bits"])
                                action.attrs["elfarch"] = elf_info["arch"]
                                action.attrs["elfhash"] = elf_hash
                                os.unlink(elf_name)

                        fhash = sha.new(data)
                        fname = fhash.hexdigest()
                        action.hash = fname

                        opath = os.path.join(self.dir, fname)
                        ofile = PkgGzipFile(opath, "wb")

                        nbuf = size / bufsz

                        for n in range(0, nbuf):
                                l = n * bufsz
                                h = (n + 1) * bufsz
                                ofile.write(data[l:h])

                        m = nbuf * bufsz
                        ofile.write(data[m:])
                        ofile.close()

                        data = None
                
                        # Now that the file has been compressed, determine its
                        # size and store that as an attribute in the manifest
                        # for the file.
                        fs = os.stat(opath)
                        action.attrs["pkg.csize"] = str(fs[stat.ST_SIZE])

                        # Compute the SHA hash of the compressed file.
                        # Store this as the chash attribute of the file's
                        # action.  In order for this to work correctly, we
                        # have to use the PkgGzipFile class.  It omits
                        # filename and timestamp information from the gzip
                        # header, allowing us to generate deterministic
                        # hashes for different files with identical content.
                        cfile = open(opath, "rb")
                        cdata = cfile.read()
                        cfile.close()
                        chash = sha.new(cdata)
                        action.attrs["chash"] = chash.hexdigest()
                        cdata = None

                tfile = file("%s/manifest" % self.dir, "a")
                print >> tfile, action
                tfile.close()

                return

        def add_meta(self):
                return

        def has_satisfied_declarations(self):
                """Evaluate package's stated dependencies against catalog."""
                return True

        def has_satisfied_implicit(self):
                """Inventory all files for their implicit dependencies; evaluate
                dependencies against ."""
                return True

        def accept_publish(self):
                """Transaction meets consistency criteria, and can be published.
                Publish, making appropriate catalog entries."""

                # XXX If we are going to publish, then we should augment
                # our response with any other packages that moved to
                # PUBLISHED due to the package's arrival.

                self.publish_package()
                self.cfg.updatelog.add_package(self.fmri, self.critical)

                self.cfg.catalog.refresh_index()

                return ("%s" % self.fmri, "PUBLISHED")

        def publish_package(self):
                """This method is called by the server to publish a package.

                It moves the files associated with the transaction into the
                appropriate position in the server repository.  Callers
                shall supply a fmri, config, and transaction in fmri, cfg,
                and trans, respectively."""

                cfg = self.cfg

                authority, pkg_name, version = self.fmri.tuple()
                pkgdir = "%s/%s" % (cfg.pkg_root, urllib.quote(pkg_name, ""))

                # If the directory isn't there, create it.
                if not os.path.exists(pkgdir):
                        os.makedirs(pkgdir)

                # mv manifest to pkg_name / version
                # A package may have no files, so there needn't be a manifest.
                if os.path.exists("%s/manifest" % self.dir):
                        portable.rename("%s/manifest" % self.dir, "%s/%s" %
                            (pkgdir, urllib.quote(str(self.fmri.version), "")))

                # Move each file to file_root, with appropriate directory
                # structure.
                for f in os.listdir(self.dir):
                        path = misc.hash_file_name(f)
                        src_path = "%s/%s" % (self.dir, f)
                        dst_path = "%s/%s" % (cfg.file_root, path)
                        try:
                                portable.rename(src_path, dst_path)
                        except OSError, e:
                                # XXX We might want to be more careful with this
                                # exception, and only try makedirs() if rename()
                                # failed because the directory didn't exist.
                                #
                                # I'm not sure it matters too much, except that
                                # if makedirs() fails, we'll see that exception,
                                # rather than the original one from rename().
                                #
                                # Interestingly, rename() failing due to missing
                                # path component fails with ENOENT, not ENOTDIR
                                # like rename(2) suggests (6578404).
                                try:
                                        os.makedirs(os.path.dirname(dst_path))
                                except OSError, e:
                                        if e.errno != errno.EEXIST:
                                                raise
                                portable.rename(src_path, dst_path)

        def accept_incomplete(self):
                """Transaction fails consistency criteria, and can be published.
                Make appropriate catalog entries."""
                return

