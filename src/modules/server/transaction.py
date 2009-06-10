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

import calendar
import datetime
import errno
import os
import re
import sha
import shutil
import urllib

import pkg.fmri as fmri
import pkg.misc as misc
from pkg.pkggzip import PkgGzipFile
import pkg.portable as portable

try:
        import pkg.elf as elf
        haveelf = True
except ImportError:
        haveelf = False

class TransactionError(Exception):
        """Base exception class for all Transaction exceptions."""

        def __init__(self, *args):
                Exception.__init__(self, *args)
                if args:
                        self.data = args[0]
                else:
                        self.data = None

        def __str__(self):
                return str(self.data)


class TransactionContentError(TransactionError):
        """Used to indicate that an unexpected error was encountered while
        processing the payload content for an operation."""

        def __str__(self):
                return _("Unrecognized or malformed data in operation payload: "
                    "'%s'.") % self.data


class TransactionOperationError(TransactionError):
        """Used to indicate that a Transaction operation failed.

        Data should be provided as keyword arguments."""

        def __init__(self, *args, **kwargs):
                TransactionError.__init__(self, *args)
                if kwargs is None:
                        kwargs = {}
                self.args = kwargs

        def __str__(self):
                if "client_release" in self.args:
                        return _("The specified client_release is invalid: "
                            "'%s'") % self.args.get("msg", "")
                elif "fmri_version" in self.args:
                        return _("'The specified FMRI, '%s', has an invalid "
                            "version.") % self.args.get("pfmri", "")
                elif "valid_new_fmri" in self.args:
                        return _("The specified FMRI, '%s', already exists or "
                            "has been restricted.") % self.args.get("pfmri", "")
                elif "pfmri" in self.args:
                        return _("The specified FMRI, '%s', is invalid.") % \
                            self.args["pfmri"]
                return str(self.data)


class TransactionAlreadyOpenError(TransactionError):
        """Used to indicate that a Transaction is already open for use."""

        def __str__(self):
                return _("Transaction ID '%s' is already open.") % self.data


class Transaction(object):
        """A Transaction is a server-side object used to represent the set of
        incoming changes to a package.  Manipulation of Transaction objects in
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
                    urllib.quote(str(self.fmri), ""))

        def open(self, cfg, client_release, pfmri):
                # XXX needs to be done in __init__
                self.cfg = cfg

                if client_release is None:
                        raise TransactionOperationError(client_release=None,
                            pfmri=pfmri)
                if pfmri is None:
                        raise TransactionOperationError(pfmri=None)

                self.client_release = client_release
                self.pkg_name = pfmri
                self.esc_pkg_name = urllib.quote(pfmri, "")

                # attempt to construct an FMRI object
                try:
                        self.fmri = fmri.PkgFmri(self.pkg_name,
                            self.client_release)
                except fmri.FmriError, e:
                        raise TransactionOperationError(e)

                # We must have a version supplied for publication.
                if self.fmri.version is None:
                        raise TransactionOperationError(fmri_version=None,
                            pfmri=pfmri)

                # record transaction metadata: opening_time, package, user
                # XXX publishing with a custom timestamp may require
                # authorization above the basic "can open transactions".
                self.open_time = self.fmri.get_timestamp()
                if self.open_time:
                        # Strip the timestamp information for consistency with
                        # the case where it was not specified.
                        self.pkg_name = ":".join(pfmri.split(":")[:-1])
                        self.esc_pkg_name = urllib.quote(self.pkg_name, "")
                else:
                        # A timestamp was not provided.
                        self.open_time = datetime.datetime.utcnow()
                        self.fmri.set_timestamp(self.open_time)

                # Check that the new FMRI's version is valid.  In other words,
                # the package has not been renamed or frozen for the new
                # version.
                if not cfg.catalog.valid_new_fmri(self.fmri):
                        raise TransactionOperationError(valid_new_fmri=False,
                            pfmri=pfmri)

                trans_basename = self.get_basename()
                self.dir = "%s/%s" % (cfg.trans_root, trans_basename)

                try:
                        os.makedirs(self.dir)
                except EnvironmentError, e:
                        if e.errno == errno.EEXIST:
                                raise TransactionAlreadyOpenError(
                                    trans_basename)
                        raise TransactionOperationError(e)

                #
                # always create a minimal manifest
                #
                tfile = file("%s/manifest" % self.dir, "ab")
                print >> tfile,  "# %s, client release %s" % (self.pkg_name,
                    self.client_release)
                tfile.close()

                # XXX:
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

        def close(self, refresh_index=True):
                """Closes an open transaction, returning the published FMRI for
                the corresponding package, and its current state in the catalog.
                """
                def split_trans_id(tid):
                        m = re.match("(\d+)_(.*)", tid)
                        return m.group(1), urllib.unquote(m.group(2))

                trans_id = self.get_basename()
                pkg_fmri = split_trans_id(trans_id)[1]

                # set package state to SUBMITTED
                pkg_state = "SUBMITTED"

                # set state to PUBLISHED
                pkg_fmri, pkg_state = self.accept_publish(refresh_index)

                # Discard the in-flight transaction data.
                try:
                        shutil.rmtree(os.path.join(self.cfg.trans_root,
                            trans_id))
                except EnvironmentError, e:
                        # Ensure that the error goes to stderr, and then drive
                        # on as the actual package was published.
                        misc.emsg(e)

                return (pkg_fmri, pkg_state)

        def abandon(self):
                trans_id = self.get_basename()
                # state transition from TRANSACTING to ABANDONED
                shutil.rmtree("%s/%s" % (self.cfg.trans_root, trans_id))
                return "ABANDONED"

        def add_content(self, action):
                """Adds the content of the provided action (if applicable) to
                the Transaction."""

                size = int(action.attrs.get("pkg.size", 0))

                if action.name in ("file", "license") and size <= 0:
                        # XXX hack for empty files
                        action.data = lambda: open(os.devnull, "rb")

                if action.data is not None:
                        bufsz = 64 * 1024

                        fname, data = misc.get_data_digest(action.data(),
                            length=size, return_content=True)

                        action.hash = fname

                        # Extract ELF information
                        # XXX This needs to be modularized.
                        if haveelf and data[:4] == "\x7fELF":
                                elf_name = "%s/.temp" % self.dir
                                elf_file = open(elf_name, "wb")
                                elf_file.write(data)
                                elf_file.close()

                                try:
                                        elf_info = elf.get_info(elf_name)
                                except elf.ElfError, e:
                                        raise TransactionContentError(e)

                                try:
                                        elf_hash = elf.get_dynamic(
                                            elf_name)["hash"]
                                        action.attrs["elfhash"] = elf_hash
                                except elf.ElfError:
                                        pass
                                action.attrs["elfbits"] = str(elf_info["bits"])
                                action.attrs["elfarch"] = elf_info["arch"]
                                os.unlink(elf_name)

                        #
                        # This check prevents entering into the depot store
                        # a file which is already there in the store.
                        # This takes CPU load off the depot on large imports
                        # of mostly-the-same stuff.  And in general it saves
                        # disk bandwidth, and on ZFS in particular it saves
                        # us space in differential snapshots.  We also need
                        # to check that the destination is in the same
                        # compression format as the source, as we must have
                        # properly formed files for chash/csize properties
                        # to work right.
                        #
                        fpath = misc.hash_file_name(fname)
                        dst_path = "%s/%s" % (self.cfg.file_root, fpath)
                        fileneeded = True
                        if os.path.exists(dst_path):
                                if PkgGzipFile.test_is_pkggzipfile(dst_path):
                                        fileneeded = False
                                        opath = dst_path

                        if fileneeded:
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
                        action.attrs["pkg.csize"] = str(fs.st_size)

                        # Compute the SHA hash of the compressed file.
                        # Store this as the chash attribute of the file's
                        # action.  In order for this to work correctly, we
                        # have to use the PkgGzipFile class.  It omits
                        # filename and timestamp information from the gzip
                        # header, allowing us to generate deterministic
                        # hashes for different files with identical content.
                        cfile = open(opath, "rb")
                        chash = sha.new()
                        while True:
                                cdata = cfile.read(bufsz)
                                if cdata == "":
                                        break
                                chash.update(cdata)
                        cfile.close()
                        action.attrs["chash"] = chash.hexdigest()
                        cdata = None

                tfile = file("%s/manifest" % self.dir, "a")
                print >> tfile, action
                tfile.close()

                return

        def accept_publish(self, refresh_index=True):
                """Transaction meets consistency criteria, and can be published.
                Publish, making appropriate catalog entries."""

                # XXX If we are going to publish, then we should augment
                # our response with any other packages that moved to
                # PUBLISHED due to the package's arrival.
                self.publish_package()
                self.cfg.updatelog.add_package(self.fmri, self.critical)

                if refresh_index:
                        self.cfg.catalog.refresh_index()

                return (str(self.fmri), "PUBLISHED")

        def publish_package(self):
                """This method is called by the server to publish a package.

                It moves the files associated with the transaction into the
                appropriate position in the server repository.  Callers
                shall supply a fmri, config, and transaction in fmri, cfg,
                and trans, respectively."""

                cfg = self.cfg

                pkg_name = self.fmri.pkg_name
                pkgdir = os.path.join(cfg.pkg_root, urllib.quote(pkg_name, ""))

                # If the directory isn't there, create it.
                if not os.path.exists(pkgdir):
                        os.makedirs(pkgdir)

                # mv manifest to pkg_name / version
                # A package may have no files, so there needn't be a manifest.
                mpath = os.path.join(self.dir, "manifest")
                if os.path.exists(mpath):
                        portable.rename(mpath, os.path.join(pkgdir,
                            urllib.quote(str(self.fmri.version), "")))

                # Move each file to file_root, with appropriate directory
                # structure.
                for f in os.listdir(self.dir):
                        path = misc.hash_file_name(f)
                        src_path = os.path.join(self.dir, f)
                        dst_path = os.path.join(cfg.file_root, path)
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
