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
# Copyright (c) 2007, 2015, Oracle and/or its affiliates. All rights reserved.
#

"""Provides a set of publishing interfaces for interacting with a pkg(5)
repository.  Note that only the Transaction class should be used directly,
though the other classes can be referred to for documentation purposes."""

import os
import six
from six.moves.urllib.parse import quote, unquote, urlparse, urlunparse

from pkg.misc import EmptyDict
import pkg.actions as actions
import pkg.config as cfg
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

        def add(self, action):
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

                if scheme == "file":
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


        def add(self, action):
                """Adds an action and its related content to an in-flight
                transaction.  Returns nothing."""

                try:
                        # Perform additional publication-time validation of
                        # actions before further processing is done.
                        action.validate()
                except actions.ActionError as e:
                        raise TransactionOperationError("add",
                            trans_id=self.trans_id, msg=str(e))

                try:
                        self.transport.publish_add(self.publisher,
                            action=action, trans_id=self.trans_id,
                            progtrack=self.progtrack)
                except apx.TransportError as e:
                        msg = str(e)
                        raise TransactionOperationError("add",
                            trans_id=self.trans_id, msg=msg)

        def add_file(self, pth):
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
                            pth=pth, trans_id=self.trans_id)
                except apx.TransportError as e:
                        msg = str(e)
                        raise TransactionOperationError("add_file",
                            trans_id=self.trans_id, msg=msg)

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
                        try:
                                state, fmri = self.transport.publish_abandon(
                                    self.publisher, trans_id=self.trans_id)
                        except apx.TransportError as e:
                                msg = str(e)
                                raise TransactionOperationError("abandon",
                                    trans_id=self.trans_id, msg=msg)
                else:
                        try:
                                state, fmri = self.transport.publish_close(
                                    self.publisher, trans_id=self.trans_id,
                                    add_to_catalog=add_to_catalog)
                        except apx.TransportError as e:
                                msg = str(e)
                                raise TransactionOperationError("close",
                                    trans_id=self.trans_id, msg=msg)

                return state, fmri

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

                return self.trans_id

        def append(self):
                """Starts an in-flight transaction to append to an existing
                manifest. Returns a URL-encoded transaction ID on success."""

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
        to a pkg(5) repository.

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
