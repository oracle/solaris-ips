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
# Copyright (c) 2007, 2016, Oracle and/or its affiliates. All rights reserved.
#

"""Provides a set of publishing interfaces for interacting with a pkg(7)
repository.  Note that only the Transaction class should be used directly,
though the other classes can be referred to for documentation purposes."""

import os
import shutil
import six
from six.moves.urllib.parse import quote, unquote, urlparse, urlunparse
import tempfile

from pkg.misc import EmptyDict
import pkg.actions as actions
import pkg.config as cfg
import pkg.digest as digest

# If elf module is supported, we will extract ELF information.
try:
        import pkg.elf as elf
        haveelf = True
except ImportError:
        haveelf = False
import pkg.misc as misc
import pkg.portable.util as os_util
import pkg.server.repository as sr
import pkg.client.api_errors as apx

class TransactionError(Exception):
        """Base exception class for all Transaction exceptions."""

        def __init__(self, *args, **kwargs):
                Exception.__init__(self, *args)
                if args:
                        self.data = args[0]
                self._args = kwargs

        def __str__(self):
                return str(self.data)


class TransactionRepositoryConfigError(TransactionError):
        """Used to indicate that the configuration information for the
        destination repository is invalid or is missing required values."""


class TransactionRepositoryURLError(TransactionError):
        """Used to indicate the specified repository URL is not valid or is not
        supported (e.g. because of the scheme).

        The first argument, when initializing the class, should be the URL."""

        def __init__(self, *args, **kwargs):
                TransactionError.__init__(self, *args, **kwargs)

        def __str__(self):
                if "scheme" in self._args:
                        return _("Unsupported scheme '{scheme}' in URL: "
                            "'{url}'.").format(scheme=self._args["scheme"],
                            url=self.data)
                elif "netloc" in self._args:
                        return _("Malformed URL: '{0}'.").format(self.data)
                return _("Invalid repository URL: '{url}': {msg}").format(
                    url=self.data, msg=self._args.get("msg", ""))


class TransactionOperationError(TransactionError):
        """Used to indicate that a transaction operation failed.

        The first argument, when initializing the class, should be the name of
        the operation that failed."""

        def __str__(self):
                if "status" in self._args:
                        return _("'{op}' failed for transaction ID "
                            "'{trans_id}'; status '{status}': "
                            "{msg}").format(op=self.data,
                            trans_id=self._args.get("trans_id", ""),
                            status=self._args["status"],
                            msg=self._args.get("msg", ""))
                if self._args.get("trans_id", None):
                        return _("'{op}' failed for transaction ID "
                            "'{trans_id}': {msg}").format(op=self.data,
                            trans_id=self._args["trans_id"],
                            msg=self._args.get("msg", ""),
                           )
                if self.data:
                        return _("'{op}' failed; unable to initiate "
                            "transaction:\n{msg}").format(op=self.data,
                            msg=self._args.get("msg", ""))
                return _("Unable to initiate transaction:\n{0}").format(
                    self._args.get("msg", ""))


class TransactionRepositoryInvalidError(TransactionError):
        """Used to indicate that the specified repository is not valid or can
        not be found at the requested location."""


class UnsupportedRepoTypeOperationError(TransactionError):
        """Used to indicate that a requested operation is not supported for the
        type of repository being operated on (http, file, etc.)."""

        def __str__(self):
                return _("Unsupported operation '{op}' for the specified "
                    "repository type '{type}'.").format(op=self.data,
                    type=self._args.get("type", ""))


class NullTransaction(object):
        """Provides a simulated publishing interface suitable for testing
        purposes."""

        def __init__(self, origin_url, create_repo=False, pkg_name=None,
            repo_props=EmptyDict, trans_id=None, xport=None, pub=None,
            progtrack=None):
                self.create_repo = create_repo
                self.origin_url = origin_url
                self.pkg_name = pkg_name
                self.progtrack = progtrack
                self.trans_id = trans_id

        def add(self, action, exact=False, path=None):
                """Adds an action and its related content to an in-flight
                transaction.  Returns nothing."""

                try:
                        # Perform additional publication-time validation of
                        # actions before further processing is done.
                        action.validate(fmri=self.pkg_name)
                except actions.ActionError as e:
                        raise TransactionOperationError("add",
                            trans_id=self.trans_id, msg=str(e))

        def add_file(self, pth):
                """Adds an additional file to the inflight transaction so that
                it will be available for retrieval once the transaction is
                closed."""

                if not os.path.isfile(pth):
                        raise TransactionOperationError("add_file",
                            trans_id=self.trans_id, msg=str(_("The file to "
                            "be added is not a file.  The path given was {0}.").format(
                            pth)))

        def close(self, abandon=False, add_to_catalog=True):
                """Ends an in-flight transaction.  Returns a tuple containing
                a package fmri (if applicable) and the final state of the
                related package."""

                if abandon:
                        pkg_fmri = None
                        pkg_state = "ABANDONED"
                else:
                        pkg_fmri = self.pkg_name
                        pkg_state = "PUBLISHED"

                return pkg_fmri, pkg_state

        def open(self):
                """Starts an in-flight transaction. Returns a URL-encoded
                transaction ID on success."""
                return quote(self.pkg_name, "")

        def append(self):
                """Starts an in-flight transaction to append to an existing
                manifest. Returns a URL-encoded transaction ID on success."""
                return self.open()

        @staticmethod
        def refresh_index():
                """Instructs the repository to refresh its search indices.
                Returns nothing."""
                pass


class TransportTransaction(object):
        """Provides a publishing interface that uses client transport."""

        def __init__(self, origin_url, create_repo=False, pkg_name=None,
            repo_props=EmptyDict, trans_id=None, xport=None, pub=None,
            progtrack=None):

                scheme, netloc, path, params, query, fragment = \
                    urlparse(origin_url, "http", allow_fragments=0)

                self.pkg_name = pkg_name
                self.trans_id = trans_id
                self.scheme = scheme
                if scheme == "file":
                        path = unquote(path)
                self.path = path
                self.progtrack = progtrack
                self.transport = xport
                self.publisher = pub
                self.__local = False
                self.__uploaded = 0
                self.__uploads = {}
                self.__transactions = {}
                self._tmpdir = None
                self._append_mode = False
                self._upload_mode = None

                if scheme == "file":
                        self.__local = True
                        self.create_file_repo(repo_props=repo_props,
                            create_repo=create_repo)
                elif scheme != "file" and create_repo:
                        raise UnsupportedRepoTypeOperationError("create_repo",
                            type=scheme)

        def create_file_repo(self, repo_props=EmptyDict, create_repo=False):

                if self.transport.publish_cache_contains(self.publisher):
                        return

                if create_repo:
                        try:
                                # For compatibility reasons, assume that
                                # repositories created using pkgsend
                                # should be in version 3 format (single
                                # publisher only).
                                sr.repository_create(self.path, version=3)
                        except sr.RepositoryExistsError:
                                # Already exists, nothing to do.
                                pass
                        except (apx.ApiException, sr.RepositoryError) as e:
                                raise TransactionOperationError(None,
                                    msg=str(e))

                try:
                        repo = sr.Repository(properties=repo_props,
                            root=self.path)
                except EnvironmentError as e:
                        raise TransactionOperationError(None, msg=_(
                            "An error occurred while trying to "
                            "initialize the repository directory "
                            "structures:\n{0}").format(e))
                except cfg.ConfigError as e:
                        raise TransactionRepositoryConfigError(str(e))
                except sr.RepositoryInvalidError as e:
                        raise TransactionRepositoryInvalidError(str(e))
                except sr.RepositoryError as e:
                        raise TransactionOperationError(None,
                            msg=str(e))

                self.transport.publish_cache_repository(self.publisher, repo)


        def add(self, action, exact=False, path=None):
                """Adds an action and its related content to an in-flight
                transaction.  Returns nothing."""

                try:
                        # Perform additional publication-time validation of
                        # actions before further processing is done.
                        action.validate()
                except actions.ActionError as e:
                        raise TransactionOperationError("add",
                            trans_id=self.trans_id, msg=str(e))

                # If the server supports it, we'll upload the manifest as-is
                # by accumulating the manifest contents in self.__transactions.
                man = self.__transactions.get(self.trans_id)
                if man is not None:
                        try:
                                self._process_action(action, exact=exact,
                                    path=path)
                        except apx.TransportError as e:
                                msg = str(e)
                                raise TransactionOperationError("add",
                                    trans_id=self.trans_id, msg=msg)
                        self.__transactions[self.trans_id] = man + \
                            str(action) + "\n"
                        return

                # Fallback to older logic.
                try:
                        self.transport.publish_add(self.publisher,
                            action=action, trans_id=self.trans_id,
                            progtrack=self.progtrack)
                except apx.TransportError as e:
                        msg = str(e)
                        raise TransactionOperationError("add",
                            trans_id=self.trans_id, msg=msg)

        def __get_elf_attrs(self, action, fname, data):
                """Helper function to get the ELF information."""

                # This currently uses the presence of "elfhash" to indicate the
                # need for *any* content hashes to be added. This will work as
                # expected until elfhash is no longer generated by default, and
                # then this logic will need to be updated accordingly.
                need_elf_info = False
                need_elfhash = False

                if haveelf and data[:4] == b"\x7fELF":
                        need_elf_info = (
                            "elfarch" not in action.attrs or
                            "elfbits" not in action.attrs)
                        need_elfhash = "elfhash" not in action.attrs
                if not need_elf_info or not need_elfhash:
                        return misc.EmptyDict

                elf_name = os.path.join(self._tmpdir,
                    ".temp-{0}".format(fname))
                with open(elf_name, "wb") as elf_file:
                        elf_file.write(data)

                attrs = {}
                if need_elf_info:
                        try:
                                elf_info = elf.get_info(elf_name)
                        except elf.ElfError as e:
                                raise TransactionError(e)
                        attrs["elfbits"] = str(elf_info["bits"])
                        attrs["elfarch"] = elf_info["arch"]

                # Check which content checksums to compute and add to the action
                get_elfhash = (need_elfhash and "elfhash" in
                    digest.DEFAULT_GELF_HASH_ATTRS)
                get_sha256 = (need_elfhash and
                    not digest.sha512_supported and
                    "pkg.content-hash" in
                    digest.DEFAULT_GELF_HASH_ATTRS)
                get_sha512t_256 = (need_elfhash and
                    digest.sha512_supported and
                    "pkg.content-hash" in
                    digest.DEFAULT_GELF_HASH_ATTRS)

                if get_elfhash or get_sha256 or get_sha512t_256:
                        try:
                                attrs.update(elf.get_hashes(
                                    elf_name, elfhash=get_elfhash,
                                    sha256=get_sha256,
                                    sha512t_256=get_sha512t_256))
                        except elf.ElfError:
                                pass

                os.unlink(elf_name)
                return attrs

        def __get_compressed_attrs(self, fhash, data, size):
                """Given a fhash, data, and size of a file, returns a tuple
                of (csize, chashes) where 'csize' is the size of the file
                in the repository and 'chashes' is a dictionary containing
                any hashes of the compressed data known by the repository."""

                if self.__local or self.__uploaded < \
                    self.transport.cfg.max_transfer_checks:
                        # If the repository is local (filesystem-based) or
                        # number of files uploaded is less than
                        # max_transfer_checks, call get_compressed_attrs()...
                        csize, chashes = self.transport.get_compressed_attrs(
                            fhash, pub=self.publisher, trans_id=self.trans_id)
                else:
                        # ...or the repository is not filesystem-based and
                        # enough files are missing that we want to avoid the
                        # overhead of calling get_compressed_attrs().
                        csize, chashes = None, None

                if chashes:
                        # If any of the default content hash attributes we need
                        # is not available from the repository, they must be
                        # recomputed below.
                        for k in digest.DEFAULT_CHASH_ATTRS:
                                if k not in chashes:
                                        chashes = None
                                        break
                return csize, chashes

        def _process_action(self, action, exact=False, path=None):
                """Adds all expected attributes to the provided action and
                upload the file for the action if needed.

                If 'exact' is True and 'path' is 'None', the action won't
                be modified and no file will be uploaded.

                If 'exact' is True and a 'path' is provided, the file of that
                path will be uploaded as-is (it is assumed that the file is
                already in repository format).
                """

                if self._append_mode and action.name != "signature":
                        raise TransactionOperationError(non_sig=True)

                size = int(action.attrs.get("pkg.size", 0))

                if action.has_payload and size <= 0:
                        # XXX hack for empty files
                        action.data = lambda: open(os.devnull, "rb")

                if action.data is None:
                        return

                if exact:
                        if path:
                                self.add_file(path, basename=action.hash,
                                    progtrack=self.progtrack)
                        return

                # Get all hashes for this action.
                hashes, data = misc.get_data_digest(action.data(),
                    length=size, return_content=True,
                    hash_attrs=digest.DEFAULT_HASH_ATTRS,
                    hash_algs=digest.HASH_ALGS)
                # Set the hash member for backwards compatibility and
                # remove it from the dictionary.
                action.hash = hashes.pop("hash", None)
                action.attrs.update(hashes)

                # Add file content-hash when preferred_hash is SHA2 or higher.
                if action.name != "signature" and \
                    digest.PREFERRED_HASH != "sha1":
                        hash_attr = "{0}:{1}".format(digest.EXTRACT_FILE,
                            digest.PREFERRED_HASH)
                        file_content_hash, dummy = misc.get_data_digest(
                            action.data(), length=size, return_content=False,
                            hash_attrs=[hash_attr], hash_algs=digest.HASH_ALGS)
                        action.attrs["pkg.content-hash"] = "{0}:{1}".format(
                            hash_attr, file_content_hash[hash_attr])

                # Now set the hash value that will be used for storing the file
                # in the repository.
                hash_attr, hash_val, hash_func = \
                    digest.get_least_preferred_hash(action)
                fname = hash_val

                hdata = self.__uploads.get(fname)
                if hdata is not None:
                        elf_attrs, csize, chashes = hdata
                else:
                        # We haven't processed this file before, determine if
                        # it needs to be uploaded and what information the
                        # repository knows about it.
                        elf_attrs = self.__get_elf_attrs(action, fname, data)
                        csize, chashes = self.__get_compressed_attrs(fname,
                            data, size)

                        # 'csize' indicates that if file needs to be uploaded.
                        fileneeded = csize is None
                        if fileneeded:
                                fpath = os.path.join(self._tmpdir, fname)
                                csize, chashes = misc.compute_compressed_attrs(
                                    fname, data=data, size=size,
                                    compress_dir=self._tmpdir)
                                # Upload the compressed file for each action.
                                self.add_file(fpath, basename=fname,
                                    progtrack=self.progtrack)
                                os.unlink(fpath)
                                self.__uploaded += 1
                        elif not chashes:
                                # If not fileneeded, and repository can't
                                # provide desired hashes, call
                                # compute_compressed_attrs() in a way that
                                # avoids writing the file to get the attributes
                                # we need.
                                csize, chashes = misc.compute_compressed_attrs(
                                    fname, data=data, size=size)

                        self.__uploads[fname] = (elf_attrs, csize, chashes)

                for k, v in six.iteritems(elf_attrs):
                        if isinstance(v, list):
                                action.attrs[k] = v + action.attrlist(k)
                        else:
                                action.attrs[k] = v
                action.attrs.update(chashes)
                action.attrs["pkg.csize"] = csize

        def add_file(self, pth, basename=None, progtrack=None):
                """Adds an additional file to the inflight transaction so that
                it will be available for retrieval once the transaction is
                closed."""

                if not os.path.isfile(pth):
                        raise TransactionOperationError("add_file",
                            trans_id=self.trans_id, msg=str(_("The file to "
                            "be added is not a file.  The path given was {0}.").format(
                            pth)))

                try:
                        self.transport.publish_add_file(self.publisher,
                            pth=pth, trans_id=self.trans_id, basename=basename,
                            progtrack=progtrack)
                except apx.TransportError as e:
                        msg = str(e)
                        raise TransactionOperationError("add_file",
                            trans_id=self.trans_id, msg=msg)

        def add_manifest(self, pth):
                """Adds an additional manifest to the inflight transaction so
                that it will be available for retrieval once the transaction is
                closed."""

                if not os.path.isfile(pth):
                        raise TransactionOperationError("add_manifest",
                            trans_id=self.trans_id, msg=str(_("The file to "
                            "be added is not a file.  The path given was {0}.").format(
                            pth)))

                try:
                        self.transport.publish_add_manifest(self.publisher,
                            pth=pth, trans_id=self.trans_id)
                except apx.TransportError as e:
                        msg = str(e)
                        raise TransactionOperationError("add_manifest",
                            trans_id=self.trans_id, msg=msg)

        def _cleanup_upload(self):
                """Remove any temporary files generated in upload mode."""

                if self._tmpdir:
                        # we don't care if this fails.
                        shutil.rmtree(self._tmpdir, ignore_errors=True)

        def close(self, abandon=False, add_to_catalog=True):
                """Ends an in-flight transaction.  Returns a tuple containing
                a package fmri (if applicable) and the final state of the
                related package.

                If 'abandon' is omitted or False, the package will be published;
                otherwise the server will discard the current transaction and
                its related data.

                'add_to_catalog' tells the depot to add a package to the
                catalog, if True.
                """

                if abandon:
                        self.__transactions.pop(self.trans_id, None)
                        try:
                                state, fmri = self.transport.publish_abandon(
                                    self.publisher, trans_id=self.trans_id)
                        except apx.TransportError as e:
                                msg = str(e)
                                raise TransactionOperationError("abandon",
                                    trans_id=self.trans_id, msg=msg)
                        finally:
                                self._cleanup_upload()

                else:
                        man = self.__transactions.get(self.trans_id)
                        if man is not None:
                                # upload manifest here
                                path = os.path.join(self._tmpdir, "manifest")
                                with open(path, "w") as f:
                                        f.write(man)
                                self.add_manifest(path)
                                self.__transactions.pop(self.trans_id, None)

                        try:
                                state, fmri = self.transport.publish_close(
                                    self.publisher, trans_id=self.trans_id,
                                    add_to_catalog=add_to_catalog)
                        except apx.TransportError as e:
                                msg = str(e)
                                raise TransactionOperationError("close",
                                    trans_id=self.trans_id, msg=msg)
                        finally:
                                self._cleanup_upload()

                return state, fmri

        def _init_upload(self):
                """Initialization for upload mode."""

                if self._upload_mode or self._upload_mode is not None:
                        return

                op = "init_upload"
                try:
                        self._upload_mode = self.transport.supports_version(
                            self.publisher, "manifest", [1]) > -1
                except apx.TransportError as e:
                        msg = str(e)
                        raise TransactionOperationError(op,
                            trans_id=self.trans_id, msg=msg)

                if not self._upload_mode:
                        return

                # Create temporary directory and initialize self.__transactions.
                temp_root = misc.config_temp_root()
                self._tmpdir = tempfile.mkdtemp(dir=temp_root)
                self.__transactions.setdefault(self.trans_id, "")

        def open(self):
                """Starts an in-flight transaction. Returns a URL-encoded
                transaction ID on success."""

                trans_id = None

                try:
                        trans_id = self.transport.publish_open(self.publisher,
                            client_release=os_util.get_os_release(),
                            pkg_name=self.pkg_name)
                except apx.TransportError as e:
                        msg = str(e)
                        raise TransactionOperationError("open",
                            trans_id=self.trans_id, msg=msg)

                self.trans_id = trans_id

                if self.trans_id is None:
                        raise TransactionOperationError("open",
                            msg=_("Unknown failure; no transaction ID provided"
                            " in response."))

                self._init_upload()

                return self.trans_id

        def append(self):
                """Starts an in-flight transaction to append to an existing
                manifest. Returns a URL-encoded transaction ID on success."""

                self._append_mode = True
                trans_id = None

                try:
                        trans_id = self.transport.publish_append(self.publisher,
                            client_release=os_util.get_os_release(),
                            pkg_name=self.pkg_name)
                except apx.TransportError as e:
                        msg = str(e)
                        raise TransactionOperationError("append",
                            trans_id=self.trans_id, msg=msg)

                self.trans_id = trans_id

                if self.trans_id is None:
                        raise TransactionOperationError("append",
                            msg=_("Unknown failure; no transaction ID provided"
                            " in response."))

                self._init_upload()

                return self.trans_id

        def refresh_index(self):
                """Instructs the repository to refresh its search indices.
                Returns nothing."""

                op = "index"

                try:
                        self.transport.publish_refresh_indexes(self.publisher)
                except apx.TransportError as e:
                        msg = str(e)
                        raise TransactionOperationError(op,
                            trans_id=self.trans_id, msg=msg)


class Transaction(object):
        """Returns an object representing a publishing "transaction" interface
        to a pkg(7) repository.

        The class of the object returned will depend upon the scheme of
        'origin_url', and the value of the 'noexecute' parameter.

        The 'noexecute' parameter, when provided, will force the returned
        Transaction to simulate all of the requested operations acting as if
        they succeeded.  It is intended to be used for testing of client
        publication tools.

        Each publishing operation requires different information, and as such
        the following parameters should be provided to the class constructor
        as noted:

                'pkg_name'      should be a partial FMRI representing the
                                desired name of a package and its version when
                                opening a Transaction.  Required by: open.

                'trans_id'      should be a URL-encoded transaction ID as
                                returned by open.  Required by: add and
                                close if open has not been called.
        """

        __schemes = {
            "file": TransportTransaction,
            "http": TransportTransaction,
            "https": TransportTransaction,
            "null": NullTransaction,
        }

        def __new__(cls, origin_url, create_repo=False, pkg_name=None,
            repo_props=EmptyDict, trans_id=None, noexecute=False, xport=None,
            pub=None, progtrack=None):

                scheme, netloc, path, params, query, fragment = \
                    urlparse(origin_url, "http", allow_fragments=0)
                scheme = scheme.lower()

                if noexecute:
                        scheme = "null"
                if scheme != "null" and (not xport or not pub):
                        raise TransactionError("Caller must supply transport "
                            "and publisher.")
                if scheme not in cls.__schemes:
                        raise TransactionRepositoryURLError(origin_url,
                            scheme=scheme)
                if scheme.startswith("http") and not netloc:
                        raise TransactionRepositoryURLError(origin_url,
                            netloc=None)
                if scheme.startswith("file"):
                        if netloc:
                                raise TransactionRepositoryURLError(origin_url,
                                    msg="'{0}' contains host information, which "
                                    "is not supported for filesystem "
                                    "operations.".format(netloc))
                        # as we're urlunparsing below, we need to ensure that
                        # the path starts with only one '/' character, if any
                        # are present
                        if path.startswith("/"):
                                path = "/" + path.lstrip("/")
                        elif not path:
                                raise TransactionRepositoryURLError(origin_url)

                # Rebuild the url with the sanitized components.
                origin_url = urlunparse((scheme, netloc, path, params,
                    query, fragment))

                return cls.__schemes[scheme](origin_url,
                    create_repo=create_repo, pkg_name=pkg_name,
                    repo_props=repo_props, trans_id=trans_id, xport=xport,
                    pub=pub, progtrack=progtrack)
