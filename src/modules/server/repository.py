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

import errno
import os

import pkg.fmri as fmri
import pkg.misc as misc
import pkg.server.catalog as catalog
import pkg.server.query_parser as query_p
import pkg.server.repositoryconfig as rc
import pkg.server.transaction as trans

class RepositoryError(Exception):
        """Base exception class for all Repository exceptions."""

        def __init__(self, *args):
                Exception.__init__(self, *args)
                if args:
                        self.data = args[0]

        def __str__(self):
                return str(self.data)


class RepositoryCatalogNoUpdatesError(RepositoryError):
        """Used to indicate that no updates are available for the catalog.  The
        first argument should be the type of updates requested; the second
        should be date the catalog was last modified."""

        def __init__(self, *args):
                RepositoryError.__init__(self, *args)
                if args:
                        self.last_modified = args[1]


class RepositoryFileNotFoundError(RepositoryError):
        """Used to indicate that the hash name provided for the requested file
        does not exist."""

        def __str__(self):
                return _("No file could be found for the specified "
                    "hash name: '%s'.") % self.data


class RepositoryInvalidFMRIError(RepositoryError):
        """Used to indicate that the FMRI provided is invalid."""


class RepositoryInvalidTransactionIDError(RepositoryError):
        """Used to indicate that an invalid Transaction ID was supplied."""

        def __str__(self):
                return _("The specified Transaction ID '%s' is invalid.") % \
                    self.data


class RepositoryManifestNotFoundError(RepositoryError):
        """Used to indicate that the requested manifest could not be found."""

        def __str__(self):
                return _("No manifest could be found for the FMRI: '%s'.") % \
                    self.data


class RepositoryRenameFailureError(RepositoryError):
        """Used to indicate that the rename could not be performed.  The first
        argument should be the object representing the duplicate FMRI."""

        def __str__(self):
                return _("Unable to rename the request FMRI: '%s'; ensure that "
                    "the source FMRI exists in the catalog and that the "
                    "destination FMRI does not already exist in the "
                    "catalog.") % self.data


class RepositorySearchTokenError(RepositoryError):
        """Used to indicate that the token(s) provided to search were undefined
        or invalid."""

        def __str__(self):
                if self.data is None:
                        return _("No token was provided to search.") % self.data

                return _("The specified search token '%s' is invalid.") % \
                    self.data


class RepositorySearchUnavailableError(RepositoryError):
        """Used to indicate that search is not currently available."""

        def __str__(self):
                return _("Search functionality is temporarily unavailable.")


class Repository(object):
        """A Repository object is a representation of data contained within a
        pkg(5) repository and an interface to manipulate it."""

        def __init__(self, scfg, cfgpathname=None):
                """Prepare the repository for use."""

                self.cfgpathname = None
                self.rcfg = None
                self.scfg = scfg
                self.__searching = False
                self.load_config(cfgpathname)

        def load_config(self, cfgpathname=None):
                """Load stored configuration data and configure the repository
                appropriately."""

                default_cfg_path = False

                # Now load our repository configuration / metadata.
                if cfgpathname is None:
                        cfgpathname = os.path.join(self.scfg.repo_root,
                            "cfg_cache")
                        default_cfg_path = True

                # Create or load the repository configuration.
                try:
                        self.rcfg = rc.RepositoryConfig(pathname=cfgpathname)
                except RuntimeError:
                        if not default_cfg_path:
                                raise

                        # If it doesn't exist, just create a new object, it will
                        # automatically be populated with sane defaults.
                        self.rcfg = rc.RepositoryConfig()

                self.cfgpathname = cfgpathname

        def write_config(self):
                """Save the repository's current configuration data."""

                # No changes should be written to disk in readonly mode.
                if self.scfg.is_read_only():
                        return

                # Save a new configuration (or refresh existing).
                try:
                        self.rcfg.write(self.cfgpathname)
                except EnvironmentError, e:
                        # If we're unable to write due to the following errors,
                        # it isn't critical to the operation of the repository.
                        if e.errno not in (errno.EPERM, errno.EACCES,
                            errno.EROFS):
                                raise

        def abandon(self, trans_id):
                """Aborts a transaction with the specified Transaction ID.
                Returns the current package state."""

                try:
                        t = self.scfg.in_flight_trans[trans_id]
                except KeyError:
                        raise RepositoryInvalidTransactionIDError(trans_id)

                try:
                        pstate = t.abandon()
                        del self.scfg.in_flight_trans[trans_id]
                        return pstate
                except trans.TransactionError, e:
                        raise RepositoryError(e)

        def add(self, trans_id, action):
                """Adds an action and its content to a transaction with the
                specified Transaction ID."""

                try:
                        t = self.scfg.in_flight_trans[trans_id]
                except KeyError:
                        raise RepositoryInvalidTransactionIDError(trans_id)

                try:
                        t.add_content(action)
                except trans.TransactionError, e:
                        raise RepositoryError(e)

        def catalog(self, last_modified=None):
                """Returns a generator object containing an incremental update
                if 'last_modified' is provided.  If 'last_modified' is not
                provided, a generator object for the full version of the catalog
                will be returned instead.  'last_modified' should be a datetime
                object or an ISO8601 formatted string."""

                self.scfg.inc_catalog()

                if isinstance(last_modified, basestring):
                        last_modified = catalog.ts_to_datetime(last_modified)

                # Incremental catalog updates
                c = self.scfg.catalog
                ul = self.scfg.updatelog
                if last_modified:
                        if not ul.up_to_date(last_modified) and \
                            ul.enough_history(last_modified):
                                for line in ul._gen_updates(last_modified):
                                        yield line
                        else:
                                raise RepositoryCatalogNoUpdatesError(
                                    "incremental", c.last_modified())
                        return

                # Full catalog request.
                # Return attributes first.
                for line in c.attrs_as_lines():
                        yield line

                # Return the contents last.
                for line in c.as_lines():
                        yield line

        def close(self, trans_id, refresh_index=True):
                """Closes the transaction specified by 'trans_id'.

                Returns a tuple containing the package FMRI and the current
                package state in the catalog."""

                try:
                        t = self.scfg.in_flight_trans[trans_id]
                except KeyError:
                        raise RepositoryInvalidTransactionIDError(trans_id)

                try:
                        pfmri, pstate = t.close(refresh_index=refresh_index)
                        del self.scfg.in_flight_trans[trans_id]
                        return pfmri, pstate
                except (catalog.CatalogException, trans.TransactionError), e:
                        raise RepositoryError(e)

        def file(self, fhash):
                """Returns the absolute pathname of the file specified by the
                provided SHA1-hash name."""

                self.scfg.inc_file()

                if fhash is None:
                        raise RepositoryFileNotFoundError(fhash)

                try:
                        return os.path.normpath(os.path.join(
                            self.scfg.file_root, misc.hash_file_name(fhash)))
                except EnvironmentError, e:
                        if e.errno == errno.ENOENT:
                                raise RepositoryFileNotFoundError(fhash)
                        raise

        def manifest(self, pfmri):
                """Returns the absolute pathname of the manifest file for the
                specified FMRI."""

                self.scfg.inc_manifest()

                try:
                        if not isinstance(pfmri, fmri.PkgFmri):
                                pfmri = fmri.PkgFmri(pfmri, None)
                        fpath = pfmri.get_dir_path()
                except fmri.FmriError, e:
                        raise RepositoryInvalidFMRIError(e)

                return os.path.join(self.scfg.pkg_root, fpath)

        def open(self, client_release, pfmri):
                """Starts a transaction for the specified client release and
                FMRI.  Returns the Transaction ID for the new transaction."""

                try:
                        t = trans.Transaction()
                        t.open(self.scfg, client_release, pfmri)
                        self.scfg.in_flight_trans[t.get_basename()] = t
                        return t.get_basename()
                except trans.TransactionError, e:
                        raise RepositoryError(e)

        def rename(self, src_fmri, dest_fmri):
                """Renames an existing package specified by 'src_fmri' to
                'dest_fmri'.  Returns nothing."""

                if not isinstance(src_fmri, fmri.PkgFmri):
                        try:
                                src_fmri = fmri.PkgFmri(src_fmri, None)
                        except fmri.FmriError, e:
                                raise RepositoryInvalidFMRIError(e)

                if not isinstance(dest_fmri, fmri.PkgFmri):
                        try:
                                dest_fmri = fmri.PkgFmri(dest_fmri, None)
                        except fmri.FmriError, e:
                                raise RepositoryInvalidFMRIError(e)

                try:
                        self.scfg.updatelog.rename_package(src_fmri.pkg_name,
                            str(src_fmri.version), dest_fmri.pkg_name,
                            str(dest_fmri.version))
                except (catalog.CatalogException, catalog.RenameException):
                        raise RepositoryRenameFailureError(dest_fmri)

                self.scfg.inc_renamed()

        def refresh_index(self):
                """Updates the repository's search indices."""
                self.scfg.catalog.refresh_index()

        def search(self, query_str_lst):
                """Searches the index for each query in the list of query
                strings.  Each string should be the output of str(Query)."""

                try:
                        query_lst = [
                            query_p.Query.fromstr(s)
                            for s in query_str_lst
                        ]
                except query_p.QueryException, e:
                        raise RepositoryError(e)
                
                res_list = [
                    self.scfg.catalog.search(q)
                    for q in query_lst
                ]
                return res_list

class NastyRepository(Repository):
        """A repository object that helps the Nasty server misbehave.
        At the present time, this only overrides the catalog method,
        so that the catalog may pass a scfg object to the Catalog and
        UpdateLog."""

        def __init__(self, scfg, cfgpathname=None):
                """Prepare the repository for use."""

                Repository.__init__(self, scfg, cfgpathname)

        def catalog(self, last_modified=None):
                """Returns a generator object containing an incremental update
                if 'last_modified' is provided.  If 'last_modified' is not
                provided, a generator object for the full version of the catalog
                will be returned instead.  'last_modified' should be a datetime
                object or an ISO8601 formatted string."""

                self.scfg.inc_catalog()

                if isinstance(last_modified, basestring):
                        last_modified = catalog.ts_to_datetime(last_modified)

                # Incremental catalog updates
                c = self.scfg.catalog
                ul = self.scfg.updatelog
                if last_modified:
                        if not ul.up_to_date(last_modified) and \
                            ul.enough_history(last_modified):
                                for line in ul._gen_updates(last_modified,
                                    self.scfg):
                                        yield line
                        else:
                                raise RepositoryCatalogNoUpdatesError(
                                    "incremental", c.last_modified())
                        return

                # Full catalog request.
                # Return attributes first.
                for line in c.attrs_as_lines():
                        yield line

                # Return the contents last.
                for line in c.as_lines(self.scfg):
                        yield line

