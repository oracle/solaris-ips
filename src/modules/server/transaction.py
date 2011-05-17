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
# Copyright (c) 2007, 2011, Oracle and/or its affiliates. All rights reserved.
#

import calendar
import datetime
import errno
import os
import re
import shutil
import time
import urllib

import pkg.actions as actions
import pkg.fmri as fmri
import pkg.manifest
import pkg.misc as misc
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
                elif "missing_fmri" in self._args:
                        return _("Need an existing instance of %s to exist to "
                            "append to it") % self._args.get("pfmri", "")
                elif "non_sig" in self._args:
                        return _("Only a signature can be appended to an "
                            "existing package")
                elif "pfmri" in self._args:
                        return _("The specified FMRI, '%s', is invalid.") % \
                            self._args["pfmri"]
                return str(self.data)


class TransactionUnknownIDError(TransactionError):
        """Used to indicate that the specified transaction ID is unknown."""

        def __str__(self):
                return _("No Transaction matching ID '%s' could be found.") % \
                    self.data


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
                self.rstore = None
                self.client_release = ""
                self.fmri = None
                self.dir = ""
                self.obsolete = False
                self.renamed = False
                self.has_reqdeps = False
                self.types_found = set()
                self.append_trans = False
                self.remaining_payload_cnt = 0

        def get_basename(self):
                assert self.open_time
                # XXX should the timestamp be in ISO format?
                return "%d_%s" % \
                    (calendar.timegm(self.open_time.utctimetuple()),
                    urllib.quote(str(self.fmri), ""))

        def open(self, rstore, client_release, pfmri):
                # Store a reference to the repository storage object.
                self.rstore = rstore

                if client_release is None:
                        raise TransactionOperationError(client_release=None,
                            pfmri=pfmri)
                if pfmri is None:
                        raise TransactionOperationError(pfmri=None)

                if not isinstance(pfmri, basestring):
                        pfmri = str(pfmri)

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
                        default_pub = rstore.publisher
                        if not default_pub:
                                # A publisher is required.
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
                        # A timestamp was not provided; try to generate a
                        # unique one.
                        while 1:
                                self.open_time = datetime.datetime.utcnow()
                                self.fmri.set_timestamp(self.open_time)
                                cat = rstore.catalog
                                if not cat.get_entry(self.fmri):
                                        break
                                time.sleep(.25)

                # Check that the new FMRI's version is valid.  In other words,
                # the package has not been renamed or frozen for the new
                # version.
                if not self.rstore.valid_new_fmri(self.fmri):
                        raise TransactionOperationError(valid_new_fmri=False,
                            pfmri=pfmri)

                trans_basename = self.get_basename()
                self.dir = os.path.join(self.rstore.trans_root, trans_basename)

                try:
                        os.makedirs(self.dir, misc.PKG_DIR_MODE)
                except EnvironmentError, e:
                        if e.errno == errno.EEXIST:
                                raise TransactionAlreadyOpenError(
                                    trans_basename)
                        raise TransactionOperationError(e)

                #
                # always create a minimal manifest
                #
                tfpath = os.path.join(self.dir, "manifest")
                tfile = file(tfpath, "ab+")

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

        def append(self, rstore, client_release, pfmri):
                self.rstore = rstore
                self.append_trans = True

                if client_release is None:
                        raise TransactionOperationError(client_release=None,
                            pfmri=pfmri)
                if pfmri is None:
                        raise TransactionOperationError(pfmri=None)

                if not isinstance(pfmri, basestring):
                        pfmri = str(pfmri)

                self.client_release = client_release
                self.pkg_name = pfmri
                self.esc_pkg_name = urllib.quote(pfmri, "")

                # attempt to construct an FMRI object
                try:
                        self.fmri = fmri.PkgFmri(self.pkg_name,
                            self.client_release)
                except fmri.FmriError, e:
                        raise TransactionOperationError(e)

                # Version and timestamp is required for appending.
                if self.fmri.version is None or not self.fmri.get_timestamp():
                        raise TransactionOperationError(fmri_version=None,
                            pfmri=pfmri)

                # Ensure that the FMRI has been fully qualified with publisher
                # information or apply the default if appropriate.
                if not self.fmri.publisher:
                        default_pub = rstore.publisher
                        if not default_pub:
                                # A publisher is required.
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
                self.open_time = self.fmri.get_timestamp()

                # Strip the timestamp information for consistency with
                # the case where it was not specified.
                self.pkg_name = ":".join(pfmri.split(":")[:-1])
                self.esc_pkg_name = urllib.quote(self.pkg_name, "")

                if not rstore.valid_append_fmri(self.fmri):
                        raise TransactionOperationError(missing_fmri=True,
                            pfmri=self.fmri)

                trans_basename = self.get_basename()
                self.dir = os.path.join(rstore.trans_root, trans_basename)

                try:
                        os.makedirs(self.dir, misc.PKG_DIR_MODE)
                except EnvironmentError, e:
                        if e.errno == errno.EEXIST:
                                raise TransactionAlreadyOpenError(
                                    trans_basename)
                        raise TransactionOperationError(e)

                # Record that this is an append operation so that it can be
                # reopened correctly.
                with open(os.path.join(self.dir, "append"), "wb") as fh:
                        pass

                # copy in existing manifest, then open it for appending.
                portable.copyfile(rstore.manifest(self.fmri),
                    os.path.join(self.dir, "manifest"))

        def reopen(self, rstore, trans_dir):
                """The reopen() method is invoked by the repository as needed to
                load Transaction data."""

                self.rstore = rstore
                try:
                        open_time_str, self.esc_pkg_name = \
                            os.path.basename(trans_dir).split("_", 1)
                except ValueError:
                        raise TransactionUnknownIDError(os.path.basename(
                            trans_dir))

                self.open_time = \
                    datetime.datetime.utcfromtimestamp(int(open_time_str))
                self.pkg_name = urllib.unquote(self.esc_pkg_name)

                # This conversion should always work, because we encoded the
                # client release on the initial open of the transaction.
                self.fmri = fmri.PkgFmri(self.pkg_name, None)

                self.dir = os.path.join(rstore.trans_root, self.get_basename())

                if not os.path.exists(self.dir):
                        raise TransactionUnknownIDError(self.get_basename())

                tmode = "rb"
                if not rstore.read_only:
                        # The mode is important especially when dealing with
                        # NFS because of problems with opening a file as
                        # read/write or readonly multiple times.
                        tmode += "+"

                # Find out if the package is renamed or obsolete.
                try:
                        tfpath = os.path.join(self.dir, "manifest")
                        tfile = file(tfpath, tmode)
                except IOError, e:
                        if e.errno == errno.ENOENT:
                                return
                        raise
                m = pkg.manifest.Manifest()
                m.set_content(content=tfile.read())
                tfile.close()
                if os.path.exists(os.path.join(self.dir, "append")):
                        self.append_trans = True
                self.obsolete = m.getbool("pkg.obsolete", "false")
                self.renamed = m.getbool("pkg.renamed", "false")
                self.types_found = set((
                    action.name for action in m.gen_actions()
                ))
                self.has_reqdeps = any(
                    a.attrs["type"] == "require"
                    for a in m.gen_actions_by_type("depend")
                )

        def close(self, add_to_catalog=True):
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
                if self.append_trans:
                        pkg_fmri, pkg_state = self.accept_append(add_to_catalog)
                else:
                        pkg_fmri, pkg_state = self.accept_publish(
                            add_to_catalog)

                # Discard the in-flight transaction data.
                try:
                        shutil.rmtree(self.dir)
                except EnvironmentError, e:
                        # Ensure that the error goes to stderr, and then drive
                        # on as the actual package was published.
                        misc.emsg(e)

                return (pkg_fmri, pkg_state)

        def abandon(self):
                # state transition from TRANSACTING to ABANDONED
                try:
                        shutil.rmtree(self.dir)
                except EnvironmentError, e:
                        if e.filename == self.dir and e.errno != errno.ENOENT:
                                raise
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

                if self.append_trans and action.name != "signature":
                        raise TransactionOperationError(non_sig=True)

                size = int(action.attrs.get("pkg.size", 0))

                if action.has_payload and size <= 0:
                        # XXX hack for empty files
                        action.data = lambda: open(os.devnull, "rb")

                if action.data is not None:
                        fname, data = misc.get_data_digest(action.data(),
                            length=size, return_content=True)

                        action.hash = fname

                        # Extract ELF information
                        # XXX This needs to be modularized.
                        if haveelf and data[:4] == "\x7fELF":
                                elf_name = os.path.join(self.dir, ".temp-%s"
                                    % fname)
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

                        try:
                                dst_path = self.rstore.file(fname)
                        except Exception, e:
                                # The specific exception can't be named here due
                                # to the cyclic dependency between this class
                                # and the repository class.
                                if getattr(e, "data", "") != fname:
                                        raise
                                dst_path = None

                        csize, chash = misc.compute_compressed_attrs(
                            fname, dst_path, data, size, self.dir)
                        action.attrs["chash"] = chash.hexdigest()
                        action.attrs["pkg.csize"] = csize
                        chash = None
                        data = None

                self.remaining_payload_cnt = \
                    len(action.attrs.get("chain.sizes", "").split())

                # Do some sanity checking on packages marked or being marked
                # obsolete or renamed.
                if action.name == "set" and \
                    action.attrs["name"] == "pkg.obsolete" and \
                    action.attrs["value"] == "true":
                        self.obsolete = True
                        if self.types_found.difference(
                            set(("set", "signature"))):
                                raise TransactionOperationError(_("An obsolete "
                                    "package cannot contain actions other than "
                                    "'set' and 'signature'."))
                elif action.name == "set" and \
                    action.attrs["name"] == "pkg.renamed" and \
                    action.attrs["value"] == "true":
                        self.renamed = True
                        if self.types_found.difference(
                            set(("depend", "set", "signature"))):
                                raise TransactionOperationError(_("A renamed "
                                    "package cannot contain actions other than "
                                    "'set', 'depend', and 'signature'."))

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
                elif self.obsolete and action.name not in ("set", "signature"):
                        raise TransactionOperationError(_("A '%s' action cannot"
                            " be present in an obsolete package: %s") %
                            (action.name, action))
                elif self.renamed and action.name not in \
                    ("depend", "set", "signature"):
                        raise TransactionOperationError(_("A '%s' action cannot"
                            " be present in a renamed package: %s") %
                            (action.name, action))

                # Now that the action is known to be sane, we can add it to the
                # manifest.
                tfpath = os.path.join(self.dir, "manifest")
                tfile = file(tfpath, "ab+")
                print >> tfile, action
                tfile.close()

                self.types_found.add(action.name)

        def add_file(self, f, size=None):
                """Adds the file to the Transaction."""

                fname, data = misc.get_data_digest(f, length=size,
                    return_content=True)

                if size is None:
                        size = len(data)

                try:
                        dst_path = self.rstore.file(fname)
                except Exception, e:
                        # The specific exception can't be named here due
                        # to the cyclic dependency between this class
                        # and the repository class.
                        if getattr(e, "data", "") != fname:
                                raise
                        dst_path = None

                csize, chash = misc.compute_compressed_attrs(fname, dst_path,
                    data, size, self.dir)
                chash = None
                data = None

                self.remaining_payload_cnt -= 1

        def accept_publish(self, add_to_catalog=True):
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
                        self.rstore.add_package(self.fmri)

                return (str(self.fmri), "PUBLISHED")

        def accept_append(self, add_to_catalog=True):
                """Transaction meets consistency criteria, and can be published.
                Publish, making appropriate catalog replacements."""

                # Ensure that a renamed package has at least one dependency
                if self.renamed and not self.has_reqdeps:
                        raise TransactionOperationError(_("A renamed package "
                            "must contain at least one 'depend' action."))

                if self.remaining_payload_cnt > 0:
                        raise TransactionOperationError(_("At least one "
                            "certificate has not been delivered for the "
                            "signature action."))

                # XXX If we are going to publish, then we should augment
                # our response with any other packages that moved to
                # PUBLISHED due to the package's arrival.
                
                self.publish_package()

                if add_to_catalog:
                        self.rstore.replace_package(self.fmri)

                return (str(self.fmri), "PUBLISHED")

        def publish_package(self):
                """This method is called by the server to publish a package.

                It moves the files associated with the transaction into the
                appropriate position in the server repository.  Callers
                shall supply a fmri, repo store, and transaction in fmri,
                rstore, and trans, respectively."""

                pkg_name = self.fmri.pkg_name

                # mv manifest to pkg_name / version
                src_mpath = os.path.join(self.dir, "manifest")
                dest_mpath = self.rstore.manifest(self.fmri)
                misc.makedirs(os.path.dirname(dest_mpath))
                portable.rename(src_mpath, dest_mpath)

                # Move each file to file_root, with appropriate directory
                # structure.
                for f in os.listdir(self.dir):
                        if f == "append":
                                continue
                        src_path = os.path.join(self.dir, f)
                        self.rstore.cache_store.insert(f, src_path)
