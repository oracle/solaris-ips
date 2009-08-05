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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#
"""Provides a set of publishing interfaces for interacting with a pkg(5)
repository.  Note that only the Transaction class should be used directly,
though the other classes can be referred to for documentation purposes."""

import httplib
import os
import urllib
import urllib2
import urlparse

from pkg.misc import versioned_urlopen
import pkg.portable.util as os_util
import pkg.server.catalog as catalog
import pkg.server.config as config
import pkg.server.repository as repo
import pkg.server.repositoryconfig as rc

class TransactionError(Exception):
        """Base exception class for all Transaction exceptions."""

        def __init__(self, *args, **kwargs):
                Exception.__init__(self, *args)
                if args:
                        self.data = args[0]
                self.args = kwargs

        def __str__(self):
                return str(self.data)


class TransactionRepositoryURLError(TransactionError):
        """Used to indicate the specified repository URL is not valid or is not
        supported (e.g. because of the scheme).

        The first argument, when initializing the class, should be the URL."""

        def __init__(self, *args, **kwargs):
                TransactionError.__init__(self, *args, **kwargs)

        def __str__(self):
                if "scheme" in self.args:
                        return _("Unsupported scheme '%(scheme)s' in URL: "
                            "'%(url)s'.") % { "scheme": self.args["scheme"],
                            "url": self.data }
                elif "netloc" in self.args:
                        return _("Malformed URL: '%s'.") % self.data
                return _("Invalid repository URL: '%(url)s': %(msg)s") % {
                    "url": self.data, "msg": self.args.get("msg", "") }


class TransactionOperationError(TransactionError):
        """Used to indicate that a transaction operation failed.

        The first argument, when initializing the class, should be the name of
        the operation that failed."""

        def __str__(self):
                if "status" in self.args:
                        return _("'%(op)s' failed for transaction ID "
                            "'%(trans_id)s'; status '%(status)s': "
                            "%(msg)s") % { "op": self.data,
                            "trans_id": self.args.get("trans_id", ""),
                            "status": self.args["status"],
                            "msg": self.args.get("msg", "") }
                if "trans_id" in self.args:
                        return _("'%(op)s' failed for transaction ID "
                            "'%(trans_id)s': %(msg)s") % { "op": self.data,
                            "trans_id": self.args["trans_id"],
                            "msg": self.args.get("msg", ""),
                            }
                if self.data:
                        return _("'%(op)s' failed; unable to initiate "
                            "transaction:\n%(msg)s") % { "op": self.data,
                            "msg": self.args.get("msg", "") }
                return _("Unable to initiate transaction:\n%s") % \
                    self.args.get("msg", "")


class UnsupportedRepoTypeOperationError(TransactionError):
        """Used to indicate that a requested operation is not supported for the
        type of repository being operated on (http, file, etc.)."""

        def __str__(self):
                return _("Unsupported operation '%(op)s' for the specified "
                    "repository type '%(type)s'.") % { "op": self.data,
                    "type": self.args.get("type", "") }


class FileTransaction(object):
        """Provides a publishing interface for file-based repositories."""

        # Used to avoid the overhead of initializing the repository for
        # successive transactions.
        __repo_cache = {}

        def __init__(self, origin_url, create_repo=False, pkg_name=None,
            trans_id=None):
                scheme, netloc, path, params, query, fragment = \
                    urlparse.urlparse(origin_url, "file", allow_fragments=0)
                path = urllib.url2pathname(path)

                repo_cache = self.__class__.__repo_cache

                if not os.path.isabs(path):
                        raise TransactionRepositoryURLError(origin_url,
                            msg=_("Not an absolute path."))

                if origin_url not in repo_cache:
                        scfg = config.SvrConfig(path, None, None,
                            auto_create=create_repo)
                        try:
                                scfg.init_dirs()
                        except (config.SvrConfigError, EnvironmentError), e:
                                raise TransactionOperationError(None, msg=_(
                                    "An error occurred while trying to "
                                    "initialize the repository directory "
                                    "structures:\n%s") % e)

                        scfg.acquire_in_flight()

                        try:
                                scfg.acquire_catalog()
                        except catalog.CatalogPermissionsException, e:
                                raise TransactionOperationError(None,
                                    origin_url, msg=str(e))

                        try:
                                repo_cache[origin_url] = repo.Repository(scfg)
                        except rc.InvalidAttributeValueError, e:
                                raise TransactionOperationError(None,
                                    msg=_("The specified repository's "
                                    "configuration data is not "
                                    "valid:\n%s") % e)

                self.__repo = repo_cache[origin_url]
                self.origin_url = origin_url
                self.pkg_name = pkg_name
                self.trans_id = trans_id
                return

        def add(self, action):
                """Adds an action and its related content to an in-flight
                transaction.  Returns nothing."""

                try:
                        self.__repo.add(self.trans_id, action)
                except repo.RepositoryError, e:
                        raise TransactionOperationError("add",
                            trans_id=self.trans_id, msg=str(e))

        def close(self, abandon=False, refresh_index=True):
                """Ends an in-flight transaction.  Returns a tuple containing
                a package fmri (if applicable) and the final state of the
                related package.

                If 'abandon' is omitted or False, the package will be published;
                otherwise the server will discard the current transaction and
                its related data.
                
                If 'refresh_index' is True, the repository will be instructed
                to update its search indices after publishing.  Has no effect
                if 'abandon' is True."""

                if abandon:
                        try:
                                pkg_fmri = None
                                pkg_state = self.__repo.abandon(self.trans_id)
                        except repo.RepositoryError, e:
                                raise TransactionOperationError("abandon",
                                    trans_id=self.trans_id, msg=str(e))
                else:
                        try:
                                pkg_fmri, pkg_state = self.__repo.close(
                                    self.trans_id, refresh_index=refresh_index)
                        except repo.RepositoryError, e:
                                raise TransactionOperationError("close",
                                    trans_id=self.trans_id, msg=str(e))
                return pkg_fmri, pkg_state

        def open(self):
                """Starts an in-flight transaction. Returns a URL-encoded
                transaction ID on success."""

                try:
                        self.trans_id = self.__repo.open(
                            os_util.get_os_release(), self.pkg_name)
                except repo.RepositoryError, e:
                        raise TransactionOperationError("open",
                            trans_id=self.trans_id, msg=str(e))
                return self.trans_id

        def refresh_index(self):
                """Instructs the repository to refresh its search indices.
                Returns nothing."""

                try:
                        self.__repo.refresh_index()
                except repo.RepositoryError, e:
                        raise TransactionOperationError("refresh_index",
                            msg=str(e))


class HTTPTransaction(object):
        """Provides a publishing interface for HTTP(S)-based repositories."""

        def __init__(self, origin_url, create_repo=False, pkg_name=None,
            trans_id=None):

                if create_repo:
                        scheme, netloc, path, params, query, fragment = \
                            urlparse.urlparse(origin_url, "http",
                            allow_fragments=0)
                        raise UnsupportedRepoTypeOperationError("create_repo",
                            type=scheme)

                self.origin_url = origin_url
                self.pkg_name = pkg_name
                self.trans_id = trans_id
                return

        @staticmethod
        def __get_urllib_error(e):
                """Analyzes the server error response and returns a tuple of
                status (server response code), message (the textual response
                from the server if available)."""

                status = httplib.INTERNAL_SERVER_ERROR
                msg = None


                if not e:
                        return status, msg

                if hasattr(e, "code"):
                        status = e.code

                if hasattr(e, "read") and callable(e.read):
                        # Extract the message from the server output.
                        msg = ""
                        from xml.dom.ext.reader import HtmlLib
                        reader = HtmlLib.Reader()
                        output = e.read()
                        doc = reader.fromString(output)

                        paragraphs = []
                        if not doc.isHtml():
                                # Assume the output was the message.
                                msg = output
                        else:
                                paragraphs = doc.getElementsByTagName("p")

                        # XXX this is specific to the depot server's current
                        # error output style.
                        for p in paragraphs:
                                for c in p.childNodes:
                                        if c.nodeType == c.TEXT_NODE:
                                                value = c.nodeValue
                                                if value is not None:
                                                        msg += ("\n%s" % value)

                if not msg and status == httplib.NOT_FOUND:
                        msg = _("Unsupported or temporarily unavailable "
                            "operation requested.")
                elif not msg:
                        msg = str(e)

                return status, msg

        def add(self, action):
                """Adds an action and its related content to an in-flight
                transaction.  Returns nothing."""

                attrs = action.attrs
                if action.data != None:
                        datastream = action.data()
                        # XXX Need to handle large files better;
                        # versioned_urlopen requires the whole file to be in
                        # memory because of the underlying request library.
                        data = datastream.read()
                        sz = int(attrs["pkg.size"])
                else:
                        data = ""
                        sz = 0

                headers = dict(
                    ("X-IPkg-SetAttr%s" % i, "%s=%s" % (k, attrs[k]))
                    for i, k in enumerate(attrs)
                )
                headers["Content-Length"] = sz

                try:
                        c, v = versioned_urlopen(self.origin_url, "add",
                            [0], "%s/%s" % (self.trans_id, action.name),
                            data=data, headers=headers)
                except (httplib.BadStatusLine, RuntimeError), e:
                        status = httplib.INTERNAL_SERVER_ERROR
                        msg = str(e)
                except (urllib2.HTTPError, urllib2.URLError), e:
                        status, msg = self.__get_urllib_error(e)
                else:
                        msg = None
                        status = c.code

                if status / 100 == 4 or status / 100 == 5:
                        raise TransactionOperationError("add",
                            trans_id=self.trans_id, status=status, msg=msg)

        def close(self, abandon=False, refresh_index=True):
                """Ends an in-flight transaction.  Returns a tuple containing
                a package fmri (if applicable) and the final state of the
                related package.

                If 'abandon' is omitted or False, the package will be published;
                otherwise the server will discard the current transaction and
                its related data.
                
                If 'refresh_index' is True, the repository will be instructed
                to update its search indices after publishing.  Has no effect
                if 'abandon' is True."""

                op = "close"
                if abandon:
                        op = "abandon"

                headers = {}
                if not refresh_index:
                        # The default is to do so, so only send this if false.
                        headers["X-IPkg-Refresh-Index"] = 0

                try:
                        c, v = versioned_urlopen(self.origin_url, op, [0],
                            self.trans_id, headers=headers)
                except (httplib.BadStatusLine, RuntimeError), e:
                        status = httplib.INTERNAL_SERVER_ERROR
                        msg = str(e)
                except (urllib2.HTTPError, urllib2.URLError), e:
                        status, msg = self.__get_urllib_error(e)
                except RuntimeError, e:
                        # Assume the server didn't find the transaction or
                        # can't perform the operation.
                        status = httplib.NOT_FOUND
                        msg = str(e)
                else:
                        msg = None
                        status = c.code

                if status / 100 == 4 or status / 100 == 5:
                        raise TransactionOperationError(op,
                            trans_id=self.trans_id, status=status, msg=msg)

                # Return only the headers the client should care about.
                hdrs = c.info()
                return hdrs.get("State", None), hdrs.get("Package-FMRI", None)

        def open(self):
                """Starts an in-flight transaction. Returns a URL-encoded
                transaction ID on success."""

                # XXX This opens a Transaction, but who manages the server
                # connection?  If we want a pipelined HTTP session (multiple
                # operations -- even if it's only one Transaction -- over a
                # single connection), then we can't call HTTPConnection.close()
                # here, and we shouldn't reopen the connection in add(),
                # close(), etc.
                try:
                        headers = {"Client-Release": os_util.get_os_release()}
                        c, v = versioned_urlopen(self.origin_url, "open",
                            [0], urllib.quote(self.pkg_name, ""),
                            headers=headers)
                        self.trans_id = c.headers.get("Transaction-ID", None)
                except (httplib.BadStatusLine, RuntimeError), e:
                        status = httplib.INTERNAL_SERVER_ERROR
                        msg = str(e)
                except (urllib2.HTTPError, urllib2.URLError), e:
                        status, msg = self.__get_urllib_error(e)
                else:
                        msg = None
                        status = c.code

                if status / 100 == 4 or status / 100 == 5:
                        raise TransactionOperationError("open",
                            trans_id=self.trans_id, status=status, msg=msg)
                elif self.trans_id is None:
                        raise TransactionOperationError("open",
                            status=status, msg=_("Unknown failure; no "
                            "transaction ID provided in response: %s") % msg)

                return self.trans_id

        @staticmethod
        def refresh_index():
                """Currently unsupported."""

                raise TransactionOperationError("refresh_index",
                        status=httplib.NOT_FOUND)


class NullTransaction(object):
        """Provides a simulated publishing interface suitable for testing
        purposes."""

        def __init__(self, origin_url, create_repo=False, pkg_name=None,
            trans_id=None):
                self.create_repo = create_repo
                self.origin_url = origin_url
                self.pkg_name = pkg_name
                self.trans_id = trans_id
                return

        @staticmethod
        def add(action):
                """Adds an action and its related content to an in-flight
                transaction.  Returns nothing."""
                pass

        def close(self, abandon=False, refresh_index=True):
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
                return urllib.quote(self.pkg_name, "")

        @staticmethod
        def refresh_index():
                """Instructs the repository to refresh its search indices.
                Returns nothing."""
                pass


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
            "file": FileTransaction,
            "http": HTTPTransaction,
            "https": HTTPTransaction,
            "null": NullTransaction,
        }

        def __new__(cls, origin_url, create_repo=False, pkg_name=None,
            trans_id=None, noexecute=False):
                scheme, netloc, path, params, query, fragment = \
                    urlparse.urlparse(origin_url, "http", allow_fragments=0)
                scheme = scheme.lower()

                if noexecute:
                        scheme = "null"
                if scheme not in cls.__schemes:
                        raise TransactionRepositoryURLError(origin_url,
                            scheme=scheme)
                if scheme.startswith("http") and not netloc:
                        raise TransactionRepositoryURLError(origin_url,
                            netloc=None)

                # Rebuild the url with the sanitized components.
                origin_url = urlparse.urlunparse((scheme, netloc, path, params,
                    query, fragment))

                return cls.__schemes[scheme](origin_url,
                    create_repo=create_repo, pkg_name=pkg_name,
                    trans_id=trans_id)
