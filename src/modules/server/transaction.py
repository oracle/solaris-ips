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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import calendar
import datetime
import errno
import hashlib
import os
import re
import shutil
import urllib

import pkg.actions as actions
import pkg.fmri as fmri
import pkg.manifest
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

        def __unicode__(self):
                # To workaround python issues 6108 and 2517, this provides a
                # a standard wrapper for this class' exceptions so that they
                # have a chance of being stringified correctly.
                return str(self)

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
                self._args = kwargs

        def __str__(self):
                if "client_release" in self._args:
                        return _("The specified client_release is invalid: "
                            "'%s'") % self._args.get("msg", "")
                elif "fmri_version" in self._args:
                        return _("'The specified FMRI, '%s', has an invalid "
                            "version.") % self._args.get("pfmri", "")
                elif "valid_new_fmri" in self._args:
                        return _("The specified FMRI, '%s', already exists or "
                            "has been restricted.") % self._args.get("pfmri",
                            "")
                elif "publisher_required" in self._args:
                        return _("The specified FMRI, '%s', must include the "
                            "publisher prefix as the repository contains "
                            "package data for more than one publisher or "
                            "a default publisher has not been defined.") % \
                            self._args.get("pfmri", "")
                elif "pfmri" in self._args:
                        return _("The specified FMRI, '%s', is invalid.") % \
                            self._args["pfmri"]
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
                self.repo = None
                self.client_release = ""
                self.fmri = None
                self.dir = ""
                self.obsolete = False
                self.renamed = False
                self.has_reqdeps = False
                self.types_found = set()
                return

        def get_basename(self):
                assert self.open_time
                # XXX should the timestamp be in ISO format?
                return "%d_%s" % \
                    (calendar.timegm(self.open_time.utctimetuple()),
                    urllib.quote(str(self.fmri), ""))

        def open(self, repo, client_release, pfmri):
                # XXX needs to be done in __init__
                self.repo = repo

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

                # Version is required for publication.
                if self.fmri.version is None:
                        raise TransactionOperationError(fmri_version=None,
                            pfmri=pfmri)

                # Ensure that the FMRI has been fully qualified with publisher
                # information or apply the default if appropriate.
                if not self.fmri.publisher:
                        c = repo.catalog
                        pubs = c.publishers()
                        default_pub = repo.cfg.get_property("publisher",
                            "prefix")

                        if len(pubs) > 1 or not default_pub:
                                # A publisher is required if the repository
                                # contains package data for more than one
                                # publisher or no default has been defined.
                                raise TransactionOperationError(
                                    publisher_required=True, pfmri=pfmri)

                        self.fmri.publisher = default_pub
                        pkg_name = self.pkg_name
                        pub_string = "pkg://%s/" % default_pub
                        if not pkg_name.startswith("pkg:/"):
                                pkg_name = pub_string + pkg_name
                        else:
                                pkg_name = pkg_name.replace("pkg:/", pub_string)
                        self.pkg_name = pkg_name
                        self.esc_pkg_name = urllib.quote(pkg_name, "")

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
                if not repo.valid_new_fmri(self.fmri):
                        raise TransactionOperationError(valid_new_fmri=False,
                            pfmri=pfmri)

                trans_basename = self.get_basename()
                self.dir = "%s/%s" % (repo.trans_root, trans_basename)

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
                tfile = file("%s/manifest" % self.dir, "ab+")

                # Build a set action containing the fully qualified FMRI and add
                # it to the manifest.  While it may seem inefficient to create
                # an action string, convert it to an action, and then back, it
                # does ensure that the server is adding a valid action.
                fact = actions.fromstr("set name=pkg.fmri value=%s" % self.fmri)
                print >> tfile, str(fact)
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

        def reopen(self, repo, trans_dir):
                """The reopen() method is invoked on server restart, to
                reestablish the status of inflight transactions."""

                self.repo = repo
                open_time_str, self.esc_pkg_name = \
                    os.path.basename(trans_dir).split("_", 1)
                self.open_time = \
                    datetime.datetime.utcfromtimestamp(int(open_time_str))
                self.pkg_name = urllib.unquote(self.esc_pkg_name)

                # This conversion should always work, because we encoded the
                # client release on the initial open of the transaction.
                self.fmri = fmri.PkgFmri(self.pkg_name, None)

                self.dir = "%s/%s" % (repo.trans_root, self.get_basename())

                # Find out if the package is renamed or obsolete.
                try:
                        tfile = file("%s/manifest" % self.dir, "rb+")
                except IOError, e:
                        if e.errno == errno.ENOENT:
                                return
                        raise
                m = pkg.manifest.Manifest()
                m.set_content(tfile.read())
                tfile.close()
                self.obsolete = m.getbool("pkg.obsolete", "false")
                self.renamed = m.getbool("pkg.renamed", "false")
                self.types_found = set((
                    action.name for action in m.gen_actions()
                ))

        def close(self, refresh_index=True, add_to_catalog=True):
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
                pkg_fmri, pkg_state = self.accept_publish(refresh_index,
                add_to_catalog)

                # Discard the in-flight transaction data.
                try:
                        shutil.rmtree(os.path.join(self.repo.trans_root,
                            trans_id))
                except EnvironmentError, e:
                        # Ensure that the error goes to stderr, and then drive
                        # on as the actual package was published.
                        misc.emsg(e)

                return (pkg_fmri, pkg_state)

        def abandon(self):
                trans_id = self.get_basename()
                # state transition from TRANSACTING to ABANDONED
                shutil.rmtree("%s/%s" % (self.repo.trans_root, trans_id))
                return "ABANDONED"

        def add_content(self, action):
                """Adds the content of the provided action (if applicable) to
                the Transaction."""

                # Perform additional publication-time validation of actions
                # before further processing is done.
                try:
                        action.validate()
                except actions.ActionError, e:
                        raise TransactionOperationError(e)

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
                        dst_path = self.repo.cache_store.lookup(fname)
                        fileneeded = True
                        if dst_path:
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
                        chash = hashlib.sha1()
                        while True:
                                cdata = cfile.read(bufsz)
                                if cdata == "":
                                        break
                                chash.update(cdata)
                        cfile.close()
                        action.attrs["chash"] = chash.hexdigest()
                        cdata = None

                # Do some sanity checking on packages marked or being marked
                # obsolete or renamed.
                if action.name == "set" and \
                    action.attrs["name"] == "pkg.obsolete" and \
                    action.attrs["value"] == "true":
                        self.obsolete = True
                        if self.types_found.difference(set(("set",))):
                                raise TransactionOperationError(_("An obsolete "
                                    "package cannot contain actions other than "
                                    "'set'."))
                elif action.name == "set" and \
                    action.attrs["name"] == "pkg.renamed" and \
                    action.attrs["value"] == "true":
                        self.renamed = True
                        if self.types_found.difference(set(("set", "depend"))):
                                raise TransactionOperationError(_("A renamed "
                                    "package cannot contain actions other than "
                                    "'set' and 'depend'."))

                if not self.has_reqdeps and action.name == "depend" and \
                    action.attrs["type"] == "require":
                        self.has_reqdeps = True

                if self.obsolete and self.renamed:
                        # Reset either obsolete or renamed, depending on which
                        # action this was.
                        if action.attrs["name"] == "pkg.obsolete":
                                self.obsolete = False
                        else:
                                self.renamed = False
                        raise TransactionOperationError(_("A package may not "
                            " be marked for both obsoletion and renaming."))
                elif self.obsolete and action.name != "set":
                        raise TransactionOperationError(_("A '%s' action cannot"
                            " be present in an obsolete package: %s") % 
                            (action.name, action))
                elif self.renamed and action.name not in ("set", "depend"):
                        raise TransactionOperationError(_("A '%s' action cannot"
                            " be present in a renamed package: %s") % 
                            (action.name, action))

                # Now that the action is known to be sane, we can add it to the
                # manifest.
                tfile = file("%s/manifest" % self.dir, "ab+")
                print >> tfile, action
                tfile.close()

                self.types_found.add(action.name)

        def accept_publish(self, refresh_index=True, add_to_catalog=True):
                """Transaction meets consistency criteria, and can be published.
                Publish, making appropriate catalog entries."""

                # Ensure that a renamed package has at least one dependency
                if self.renamed and not self.has_reqdeps:
                        raise TransactionOperationError(_("A renamed package "
                            "must contain at least one 'depend' action."))

                # XXX If we are going to publish, then we should augment
                # our response with any other packages that moved to
                # PUBLISHED due to the package's arrival.
                
                self.publish_package()

                if add_to_catalog:
                        self.repo.add_package(self.fmri)
                if refresh_index:
                        self.repo.refresh_index()

                return (str(self.fmri), "PUBLISHED")

        def publish_package(self):
                """This method is called by the server to publish a package.

                It moves the files associated with the transaction into the
                appropriate position in the server repository.  Callers
                shall supply a fmri, repository, and transaction in fmri,
                repo, and trans, respectively."""

                repo = self.repo

                pkg_name = self.fmri.pkg_name
                pkgdir = os.path.join(repo.manifest_root,
                    urllib.quote(pkg_name, ""))

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
                        src_path = os.path.join(self.dir, f)
                        self.repo.cache_store.insert(f, src_path)
