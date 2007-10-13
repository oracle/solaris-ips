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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import errno
import gzip
import os
import re
import sha
import shutil
import socket
import time
import urllib

import pkg.fmri as fmri
import pkg.package as package
import pkg.elf as elf

import pkg.actions

class Transaction(object):
        """A Transaction is a server-side object used to represent the set of
        incoming changes to a Package.  Manipulation of Transaction objects in
        the repository server is generally initiated by a package publisher,
        such as pkgsend(1M)."""

        def __init__(self):
                # XXX Need to use an FMRI object.
                self.open_time = -1
                self.pkg_name = ""
                self.esc_pkg_name = ""
                self.critical = False
                self.cfg = None
                self.client_release = ""
                self.fmri = None
                self.dir = ""
                return

        def get_basename(self):
                return "%d_%s" % (self.open_time,
                    urllib.quote("%s" % self.fmri, ""))

        def open(self, cfg, request):
                self.cfg = cfg

                hdrs = request.headers
                self.client_release = hdrs.getheader("Client-Release", None)
                if self.client_release == None:
                        return 400
                # If client_release is not defined, then this request is
                # invalid.

                m = re.match("^/open/\d+/(.*)", request.path)
                self.esc_pkg_name = m.group(1)
                self.pkg_name = urllib.unquote(self.esc_pkg_name)
                self.open_time = time.time()

                # record transaction metadata:  opening_time, package, user

                # attempt to construct an FMRI object
                self.fmri = fmri.PkgFmri(self.pkg_name, self.client_release)
                self.fmri.set_timestamp(self.open_time)

                trans_basename = self.get_basename()
                self.dir = "%s/%s" % (self.cfg.trans_root, trans_basename)
                os.makedirs(self.dir)

		#
		# always create a minimal manifest
		#
                tfile = file("%s/manifest" % self.dir, "a")
                print >>tfile,  "# %s, client release %s" % (self.pkg_name, \
                    self.client_release)
                tfile.close()

                # lookup package by name
                p = package.Package(self.fmri)

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

                return 200

        def reopen(self, cfg, trans_dir):
                """The reopen() method is invoked on server restart, to
                reestablish the status of inflight transactions."""

                self.cfg = cfg
                self.open_time, self.esc_pkg_name = re.split("_",
                    os.path.basename(trans_dir))
                self.open_time = int(self.open_time)
                self.pkg_name = urllib.unquote(self.esc_pkg_name)

                # This conversion should always work, because we encoded the
                # client release on the initial open of the transaction.
                self.fmri = fmri.PkgFmri(self.pkg_name, None)

                self.dir = ("%s/%s", self.cfg.trans_root, self.get_basename())

        def close(self, request):
                def split_trans_id(id):
                        m = re.match("(\d+)_(.*)", id)
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
                        print "pkg.depotd: couldn't remove transaction %s" % trans_id

                request.send_response(200)
                request.send_header('Package-FMRI', pkg_fmri)
                request.send_header('State', pkg_state)
                return

        def abandon(self, request):
                trans_id = self.get_basename()
                # XXX refine try/except
                #
                # state transition from TRANSACTING to ABANDONED
                try:
                        shutil.rmtree("%s/%s" % (self.cfg.trans_root, trans_id))
                        request.send_response(200)
                except:
                        request.send_response(404)

        def add_content(self, request, type):
                """XXX We're currently taking the file from the HTTP request
                directly onto the heap, to make the hash computation convenient.
                We then do the compression as a sequence of buffers.  To handle
                large files, we'll need to process the incoming data as a
                sequence of buffers as well, with intermediate storage to
                disk."""

                attrs = dict(
                    val.split("=", 1)
                    for hdr, val in request.headers.items()
                    if hdr.startswith("x-ipkg-setattr")
                )

                # If any attributes appear to be lists, make them lists.
                for a in attrs:
                        if attrs[a].startswith("[") and attrs[a].endswith("]"):
                                attrs[a] = eval(attrs[a])

                size = int(request.headers.getheader("Content-Length", "0"))

                # The request object always has a readable rfile, even if it'll
                # return no data.  We check ahead of time to see if we'll get
                # any data, and only create the object with data if there will
                # be any.
                rfile = None
                if size > 0:
                        rfile = request.rfile
                # XXX Ugly special case to handle empty files.
                elif type == "file":
                        rfile = "/dev/null"
                action = pkg.actions.types[type](rfile, **attrs)

                # XXX Once actions are labelled with critical nature.
                # if type in critical_actions:
                #         self.critical = True

                # Record the size of the payload, if there is one.
                if size > 0:
                        action.attrs["pkg.size"] = str(size)

                if action.data != None:
                        data = action.data().read(size)

                        # Extract ELF information
                        # XXX This needs to be modularized.
                        if data[:4] == "\x7fELF":
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

                        hash = sha.new(data)
                        fname = hash.hexdigest()
                        action.hash = fname
                        ofile = gzip.GzipFile("%s/%s" % (self.dir, fname), "wb")

                        bufsz = 64 * 1024

                        nbuf = size / bufsz

                        for n in range(0, nbuf):
                                l = n * bufsz
                                h = (n + 1) * bufsz
                                ofile.write(data[l:h])

                        m = nbuf * bufsz
                        ofile.write(data[m:])
                        ofile.close()

                tfile = file("%s/manifest" % self.dir, "a")
                print >>tfile, action
                tfile.close()

                try:
                        request.send_response(200)
                except socket.error, e:
                        # If the client breaks the connection here, that's
                        # probably okay.  Everything's consistent on our end,
                        # at least.
                        if e.args[0] != errno.EPIPE:
                                raise

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
                p = package.Package(self.fmri)
                p.add_version(self.fmri)
                p.set_dir(self.cfg)
                p.update(self.cfg, self)

                # add entry to catalog
                # XXX Is self.cfg.catalog a copy or a reference??
                # XXX Could just write new catalog file...
                self.cfg.catalog.add_pkg(p, self.critical)

                return ("%s" % self.fmri, "PUBLISHED")

        def accept_incomplete(self):
                """Transaction fails consistency criteria, and can be published.
                Make appropriate catalog entries."""
                return

