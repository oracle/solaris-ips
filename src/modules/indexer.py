#!usr/bin/python
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

import errno
import os
import platform
import shutil
from six.moves.urllib.parse import unquote

import pkg.fmri as fmri
import pkg.misc as misc
import pkg.lockfile as lockfile
import pkg.manifest as manifest
import pkg.portable as portable
import pkg.search_storage as ss
import pkg.search_errors as search_errors
import pkg.version
import pkg.client.progress as progress
from pkg.misc import EmptyI, PKG_DIR_MODE, PKG_FILE_BUFSIZ

# Constants for indicating whether pkgplans or fmri-manifest path pairs are
# used as arguments.
IDX_INPUT_TYPE_PKG = 0
IDX_INPUT_TYPE_FMRI = 1

INITIAL_VERSION_NUMBER = 1

FILE_OPEN_TIMEOUT_SECS = 2

MAX_FAST_INDEXED_PKGS = 20

SORT_FILE_PREFIX = "sort."

SORT_FILE_MAX_SIZE = 128 * 1024 * 1024


def makedirs(pathname):
        """Create a directory at the specified location if it does not
        already exist (including any parent directories).
        """

        try:
                os.makedirs(pathname, PKG_DIR_MODE)
        except EnvironmentError as e:
                if e.filename == pathname and (e.errno == errno.EEXIST or
                    os.path.exists(e.filename)):
                        return
                elif e.errno in (errno.EACCES, errno.EROFS):
                        raise search_errors.ProblematicPermissionsIndexException(
                            e.filename)
                elif e.errno != errno.EEXIST or e.filename != pathname:
                        raise


class Indexer(object):
        """Indexer is a class designed to index a set of manifests or pkg plans
        and provide a compact representation on disk, which is quickly
        searchable."""

        file_version_string = "VERSION: "

        def __init__(self, index_dir, get_manifest_func, get_manifest_path_func,
            progtrack=None, excludes=EmptyI, log=None,
            sort_file_max_size=SORT_FILE_MAX_SIZE):
                self._num_keys = 0
                self._num_manifests = 0
                self._num_entries = 0
                self.get_manifest_func = get_manifest_func
                self.get_manifest_path_func = get_manifest_path_func
                self.excludes = excludes
                self.__log = log
                self.sort_file_max_size = sort_file_max_size
                if self.sort_file_max_size <= 0:
                        raise search_errors.IndexingException(
                            _("sort_file_max_size must be greater than 0"))

                # This structure was used to gather all index files into one
                # location. If a new index structure is needed, the files can
                # be added (or removed) from here. Providing a list or
                # dictionary allows an easy approach to opening or closing all
                # index files.

                self._data_dict = {
                        "fast_add":
                            ss.IndexStoreSet(ss.FAST_ADD),
                        "fast_remove":
                            ss.IndexStoreSet(ss.FAST_REMOVE),
                        "manf":
                            ss.IndexStoreListDict(ss.MANIFEST_LIST,
                                build_function=self.__build_fmri,
                                decode_function=self.__decode_fmri),
                        "full_fmri": ss.IndexStoreSet(ss.FULL_FMRI_FILE),
                        "main_dict": ss.IndexStoreMainDict(ss.MAIN_FILE),
                        "token_byte_offset":
                            ss.IndexStoreDictMutable(ss.BYTE_OFFSET_FILE)
                        }

                self._data_fast_add = self._data_dict["fast_add"]
                self._data_fast_remove = self._data_dict["fast_remove"]
                self._data_manf = self._data_dict["manf"]
                self._data_full_fmri = self._data_dict["full_fmri"]
                self._data_main_dict = self._data_dict["main_dict"]
                self._data_token_offset = self._data_dict["token_byte_offset"]

                # This is added to the dictionary after the others because it
                # needs one of the other mappings as an input.
                self._data_dict["fmri_offsets"] = \
                    ss.InvertedDict(ss.FMRI_OFFSETS_FILE, self._data_manf)
                self._data_fmri_offsets = self._data_dict["fmri_offsets"]

                self._index_dir = index_dir
                self._tmp_dir = os.path.join(self._index_dir, "TMP")

                self.__lockfile = lockfile.LockFile(os.path.join(
                    self._index_dir, "lock"),
                    set_lockstr=lockfile.generic_lock_set_str,
                    get_lockstr=lockfile.generic_lock_get_str,
                    failure_exc=search_errors.IndexLockedException)

                self._indexed_manifests = 0
                self.server_repo = True
                self.empty_index = False
                self.file_version_number = None

                if progtrack is None:
                        self._progtrack = progress.NullProgressTracker()
                else:
                        self._progtrack = progtrack

                self._file_timeout_secs = FILE_OPEN_TIMEOUT_SECS

                self._sort_fh = None
                self._sort_file_num = 0
                self._sort_file_bytes = 0

                # The action type and key indexes, which are necessary for
                # efficient searches by type or key, store their file handles in
                # dictionaries.  File handles for actions are in at_fh, while
                # filehandles for keys are kept in st_fh.
                self.at_fh = {}
                self.st_fh = {}

                self.old_out_token = None

        @staticmethod
        def __decode_fmri(pfmri):
                """Turn fmris into strings correctly while writing out
                the fmri offsets file."""

                return pfmri.get_fmri(anarchy=True, include_scheme=False)

        @staticmethod
        def __build_fmri(s):
                """Build fmris while reading the fmri offset information."""

                return fmri.PkgFmri(s)

        @staticmethod
        def _build_version(vers):
                """ Private method for building versions from a string. """

                return pkg.version.Version(unquote(vers), None)

        def _read_input_indexes(self, directory):
                """ Opens all index files using consistent_open and reads all
                of them into memory except the main dictionary file to avoid
                inefficient memory usage."""

                res = ss.consistent_open(self._data_dict.values(), directory,
                    self._file_timeout_secs)
                pt = self._progtrack
                if res == None:
                        self.file_version_number = INITIAL_VERSION_NUMBER
                        self.empty_index = True
                        return None
                self.file_version_number = res

                try:
                        pt.job_start(pt.JOB_READ_SEARCH)
                        try:
                                for d in self._data_dict.values():
                                        if (d == self._data_main_dict or
                                                d == self._data_token_offset):
                                                pt.job_add_progress(
                                                    pt.JOB_READ_SEARCH)
                                                continue
                                        d.read_dict_file()
                                        pt.job_add_progress(pt.JOB_READ_SEARCH)
                        except:
                                self._data_dict["main_dict"].close_file_handle()
                                raise
                finally:
                        for d in self._data_dict.values():
                                if d == self._data_main_dict:
                                        continue
                                d.close_file_handle()
                        pt.job_done(pt.JOB_READ_SEARCH)

        def __close_sort_fh(self):
                """Utility fuction used to close and sort the temporary
                files used to produce a sorted main_dict file."""

                self._sort_fh.close()
                self._sort_file_bytes = 0
                tmp_file_name = os.path.join(self._tmp_dir,
                    SORT_FILE_PREFIX + str(self._sort_file_num - 1))
                tmp_fh = open(tmp_file_name, "r", buffering=PKG_FILE_BUFSIZ)
                l = [
                    (ss.IndexStoreMainDict.parse_main_dict_line_for_token(line),
                    line)
                    for line in tmp_fh
                ]
                tmp_fh.close()
                l.sort()
                tmp_fh = open(tmp_file_name, "w", buffering=PKG_FILE_BUFSIZ)
                tmp_fh.writelines((line for tok, line in l))
                tmp_fh.close()

        def _add_terms(self, pfmri, new_dict):
                """Adds tokens, and the actions generating them, to the current
                temporary sort file.

                The "pfmri" parameter is the fmri the information is coming
                from.

                The "new_dict" parameter maps tokens to the information about
                the action."""

                p_id = self._data_manf.get_id_and_add(pfmri)
                pfmri = p_id

                for tok_tup in new_dict.keys():
                        tok, action_type, subtype, fv = tok_tup
                        lst = [(action_type, [(subtype, [(fv, [(pfmri,
                            list(new_dict[tok_tup]))])])])]
                        s = ss.IndexStoreMainDict.transform_main_dict_line(tok,
                            lst)
                        if len(s) + self._sort_file_bytes >= \
                            self.sort_file_max_size:
                                self.__close_sort_fh()
                                self._sort_fh = open(os.path.join(self._tmp_dir,
                                    SORT_FILE_PREFIX +
                                    str(self._sort_file_num)), "w",
                                    buffering=PKG_FILE_BUFSIZ)
                                self._sort_file_num += 1
                        self._sort_fh.write(s)
                        self._sort_file_bytes += len(s)
                return

        def _fast_update(self, filters_pkgplan_list):
                """Updates the log of packages which have been installed or
                removed since the last time the index has been rebuilt.

                There are two axes to consider: whether the package is being
                added or removed; whether this version of the package is
                already present in an update log.

                Case 1: The package is being installed and is not in the
                    update log.  In this case, the new package is simply added
                    to the install update log.
                Case 2: The package is being installed and is in the removal
                    update log. In this case, the package is removed from the
                    remove update log.  This has the effect of exposing the
                    entries in the existing index to the user.
                Case 3: The package is being removed and is not in the
                    update log.  In this case, the new package is simply added
                    to the removed update log.
                Case 4: The package is being removed and is in the installed
                    update log.  In this case, the package is removed from the
                    install update log.

                The "filters_pkgplan_list" parameter is a tuple of a list of
                filters, which are currently ignored, and a list of pkgplans
                that indicated which versions of a package are being added or
                removed."""

                nfast_add = len(self._data_fast_add._set)
                nfast_remove = len(self._data_fast_remove._set)

                #
                # First pass determines whether a fast update makes sense and
                # updates the list of fmris that will be in the index.
                #
                filters, pkgplan_list = filters_pkgplan_list
                for p in pkgplan_list:
                        d_fmri, o_fmri = p
                        if d_fmri:
                                self._data_full_fmri.add_entity(
                                    d_fmri.get_fmri(anarchy=True))
                                d_tmp = d_fmri.get_fmri(anarchy=True,
                                    include_scheme=False)
                                if self._data_fast_remove.has_entity(d_tmp):
                                        nfast_remove -= 1
                                else:
                                        nfast_add += 1
                        if o_fmri:
                                self._data_full_fmri.remove_entity(
                                    o_fmri.get_fmri(anarchy=True))
                                o_tmp = o_fmri.get_fmri(anarchy=True,
                                    include_scheme=False)
                                if self._data_fast_add.has_entity(o_tmp):
                                        nfast_add -= 1
                                else:
                                        nfast_remove += 1

                if nfast_add > MAX_FAST_INDEXED_PKGS:
                        return False

                #
                # Second pass actually updates the fast_add and fast_remove
                # sets and updates progress.
                #
                self._progtrack.job_start(self._progtrack.JOB_UPDATE_SEARCH,
                    goal=len(pkgplan_list))
                for p in pkgplan_list:
                        d_fmri, o_fmri = p

                        if d_fmri:
                                d_tmp = d_fmri.get_fmri(anarchy=True,
                                    include_scheme=False)
                                assert not self._data_fast_add.has_entity(d_tmp)
                                if self._data_fast_remove.has_entity(d_tmp):
                                        self._data_fast_remove.remove_entity(
                                            d_tmp)
                                else:
                                        self._data_fast_add.add_entity(d_tmp)
                        if o_fmri:
                                o_tmp = o_fmri.get_fmri(anarchy=True,
                                    include_scheme=False)
                                assert not self._data_fast_remove.has_entity(
                                    o_tmp)
                                if self._data_fast_add.has_entity(o_tmp):
                                        self._data_fast_add.remove_entity(o_tmp)
                                else:
                                        self._data_fast_remove.add_entity(o_tmp)

                        self._progtrack.job_add_progress(
                            self._progtrack.JOB_UPDATE_SEARCH)

                self._progtrack.job_done(self._progtrack.JOB_UPDATE_SEARCH)

                return True

        def _process_fmris(self, fmris):
                """Takes a list of fmris and updates the internal storage to
                reflect the new packages."""

                removed_paths = []

                for added_fmri in fmris:
                        self._data_full_fmri.add_entity(
                            added_fmri.get_fmri(anarchy=True))
                        new_dict = manifest.Manifest.search_dict(
                            self.get_manifest_path_func(added_fmri),
                            self.excludes, log=self.__log)
                        self._add_terms(added_fmri, new_dict)

                        self._progtrack.job_add_progress(
                            self._progtrack.JOB_REBUILD_SEARCH)
                return removed_paths

        def _write_main_dict_line(self, file_handle, token,
            fv_fmri_pos_list_list, out_dir):
                """Writes out the new main dictionary file and also adds the
                token offsets to _data_token_offset. file_handle is the file
                handle for the output main dictionary file. token is the token
                to add to the file. fv_fmri_pos_list_list is a structure of
                lists inside of lists several layers deep. The top layer is a
                list of action types. The second layer contains the keys for
                the action type it's a sublist for. The third layer contains
                the values which matched the token for the action and key it's
                contained in. The fourth layer is the fmris which contain those
                matches. The fifth layer is the offset into the manifest of
                each fmri for each matching value. out_dir points to the
                base directory to use to write a file for each package which
                contains the offsets into the main dictionary for the tokens
                this package matches."""

                if self.old_out_token is not None and \
                    self.old_out_token >= token:
                        raise RuntimeError("In writing dict line, token:{0}, "
                            "old_out_token:{1}".format(token,
                            self.old_out_token))
                self.old_out_token = token

                cur_location_int = file_handle.tell()
                cur_location = str(cur_location_int)
                self._data_token_offset.write_entity(token, cur_location)

                for at, st_list in fv_fmri_pos_list_list:
                        self._progtrack.job_add_progress(
                            self._progtrack.JOB_REBUILD_SEARCH, nitems=0)
                        if at not in self.at_fh:
                                self.at_fh[at] = open(os.path.join(out_dir,
                                    "__at_" + at), "w")
                        self.at_fh[at].write(cur_location + "\n")
                        for st, fv_list in st_list:
                                if st not in self.st_fh:
                                        self.st_fh[st] = \
                                            open(os.path.join(out_dir,
                                            "__st_" + st), "w")
                                self.st_fh[st].write(cur_location + "\n")
                                for fv, p_list in fv_list:
                                        for p_id, m_off_set in p_list:
                                                p_id = int(p_id)
                                                self._data_fmri_offsets.add_pair(
                                                    p_id, cur_location_int)
                file_handle.write(self._data_main_dict.transform_main_dict_line(
                    token, fv_fmri_pos_list_list))

        @staticmethod
        def __splice(ret_list, source_list):
                """Takes two arguments. Each of the arguments must be a list
                with the type signature list of ('a, list of 'b). Where
                the lists share a value (A) for 'a, it splices the lists of 'b
                paired with A from each list into a single list and makes that
                the new list paired with A in the result.

                Note: This modifies the ret_list rather than building a new one
                because of the large performance difference between the two
                approaches."""

                tmp_res = []
                for val, sublist in source_list:
                        found = False
                        for r_val, r_sublist in ret_list:
                                if val == r_val:
                                        found = True
                                        Indexer.__splice(r_sublist, sublist)
                                        break
                        if not found:
                                tmp_res.append((val, sublist))
                ret_list.extend(tmp_res)

        def _gen_new_toks_from_files(self):
                """Produces a stream of ordered tokens and the associated
                information for those tokens from the sorted temporary files
                produced by _add_terms. In short, this is the merge part of the
                merge sort being done on the tokens to be indexed."""

                def get_line(fh):
                        """Helper function to make the initialization of the
                        fh_dict easier to understand."""

                        try:
                                return \
                                        ss.IndexStoreMainDict.parse_main_dict_line(
                                        next(fh))
                        except StopIteration:
                                return None

                # Build a mapping from numbers to the file handle for the
                # temporary sort file with that number.
                fh_dict = dict([
                    (i, open(os.path.join(self._tmp_dir,
                    SORT_FILE_PREFIX + str(i)), "r",
                    buffering=PKG_FILE_BUFSIZ))
                    for i in range(self._sort_file_num)
                ])

                cur_toks = {}
                # Seed cur_toks with the first token from each temporary file.
                # The line may not exist since, for a empty repo, an empty file
                # is created.
                for i in list(fh_dict.keys()):
                        line = get_line(fh_dict[i])
                        if line is None:
                                del fh_dict[i]
                        else:
                                cur_toks[i] = line

                old_min_token = None
                # cur_toks will have items deleted from it as files no longer
                # have tokens to provide. When no files have tokens, the merge
                # is done.
                while cur_toks:
                        min_token = None
                        matches = []
                        # Find smallest available token and the temporary files
                        # which contain that token.
                        for i in fh_dict.keys():
                                cur_tok, info = cur_toks[i]
                                if cur_tok is None:
                                        continue
                                if min_token is None or cur_tok < min_token:
                                        min_token = cur_tok
                                        matches = [i]
                                elif cur_tok == min_token:
                                        matches.append(i)
                        assert min_token is not None
                        assert len(matches) > 0
                        res = None
                        for i in matches:
                                new_tok, new_info = cur_toks[i]
                                assert new_tok == min_token
                                try:
                                        # Continue pulling the next tokens from
                                        # and adding them to the result list as
                                        # long as the token matches min_token.
                                        while new_tok == min_token:
                                                if res is None:
                                                        res = new_info
                                                else:
                                                        self.__splice(res,
                                                            new_info)
                                                new_tok, new_info = \
                                                    ss.IndexStoreMainDict.parse_main_dict_line(next(fh_dict[i]))
                                        cur_toks[i] = new_tok, new_info
                                except StopIteration:
                                        # When a StopIteration happens, the
                                        # last line in the file has been read
                                        # and processed. Delete all the
                                        # information associated with that file
                                        # so that we no longer check that file.
                                        fh_dict[i].close()
                                        del fh_dict[i]
                                        del cur_toks[i]
                        assert res is not None
                        if old_min_token is not None and \
                            old_min_token >= min_token:
                                raise RuntimeError("Got min token:{0} greater "
                                    "than old_min_token:{1}".format(
                                    min_token, old_min_token))
                        old_min_token = min_token
                        if min_token != "":
                                yield min_token, res
                return

        def _update_index(self, dicts, out_dir):
                """Processes the main dictionary file and writes out a new
                main dictionary file reflecting the changes in the packages.

                The "dicts" parameter is the list of fmris which have been
                removed during update.

                The "out_dir" parameter is the temporary directory in which to
                build the indexes."""

                removed_paths = dicts

                if self.empty_index:
                        file_handle = []
                else:
                        file_handle = self._data_main_dict.get_file_handle()
                        assert file_handle

                if self.file_version_number == None:
                        self.file_version_number = INITIAL_VERSION_NUMBER
                else:
                        self.file_version_number += 1

                self._data_main_dict.write_dict_file(
                    out_dir, self.file_version_number)
                # The dictionary file's opened in append mode to avoid removing
                # the version information the search storage class added.
                out_main_dict_handle = \
                    open(os.path.join(out_dir,
                        self._data_main_dict.get_file_name()), "a",
                        buffering=PKG_FILE_BUFSIZ)

                self._data_token_offset.open_out_file(out_dir,
                    self.file_version_number)

                new_toks_available = True
                new_toks_it = self._gen_new_toks_from_files()
                try:
                        tmp = next(new_toks_it)
                        next_new_tok, new_tok_info = tmp
                except StopIteration:
                        new_toks_available = False

                try:
                        for line in file_handle:
                                (tok, at_lst) = \
                                    self._data_main_dict.parse_main_dict_line(
                                    line)
                                existing_entries = []
                                for at, st_list in at_lst:
                                        st_res = []
                                        for st, fv_list in st_list:
                                                fv_res = []
                                                for fv, p_list in fv_list:
                                                        p_res = []
                                                        for p_id, m_off_set in \
                                                                    p_list:
                                                                p_id = int(p_id)
                                                                pfmri = self._data_manf.get_entity(p_id)
                                                                if pfmri not in removed_paths:
                                                                        p_res.append((p_id, m_off_set))
                                                        if p_res:
                                                                fv_res.append(
                                                                    (fv, p_res))
                                                if fv_res:
                                                        st_res.append(
                                                            (st, fv_res))
                                        if st_res:
                                                existing_entries.append(
                                                    (at, st_res))
                                # Add tokens newly discovered in the added
                                # packages which are alphabetically earlier
                                # than the token most recently read from the
                                # existing main dictionary file.
                                while new_toks_available and next_new_tok < tok:
                                        assert len(next_new_tok) > 0
                                        self._write_main_dict_line(
                                            out_main_dict_handle, next_new_tok,
                                            new_tok_info, out_dir)
                                        try:
                                                next_new_tok, new_tok_info = \
                                                    next(new_toks_it)
                                        except StopIteration:
                                                new_toks_available = False
                                                del next_new_tok
                                                del new_tok_info

                                # Combine the information about the current
                                # token from the new packages with the existing
                                # information for that token.
                                if new_toks_available and next_new_tok == tok:
                                        self.__splice(existing_entries,
                                            new_tok_info)
                                        try:
                                                next_new_tok, new_tok_info = \
                                                    next(new_toks_it)
                                        except StopIteration:
                                                new_toks_available = False
                                                del next_new_tok
                                                del new_tok_info
                                # If this token has any packages still
                                # associated with it, write them to the file.
                                if existing_entries:
                                        assert len(tok) > 0
                                        self._write_main_dict_line(
                                            out_main_dict_handle,
                                            tok, existing_entries, out_dir)

                        # For any new tokens which are alphabetically after the
                        # last entry in the existing file, add them to the end
                        # of the file.
                        while new_toks_available:
                                assert len(next_new_tok) > 0
                                self._write_main_dict_line(
                                    out_main_dict_handle, next_new_tok,
                                    new_tok_info, out_dir)
                                try:
                                        next_new_tok, new_tok_info = \
                                            next(new_toks_it)
                                except StopIteration:
                                        new_toks_available = False
                finally:
                        if not self.empty_index:
                                file_handle.close()
                                self._data_main_dict.close_file_handle()

                        out_main_dict_handle.close()
                        self._data_token_offset.close_file_handle()
                        for fh in self.at_fh.values():
                                fh.close()
                        for fh in self.st_fh.values():
                                fh.close()

                        removed_paths = []

        def _write_assistant_dicts(self, out_dir):
                """Write out the companion dictionaries needed for
                translating the internal representation of the main
                dictionary into human readable information.

                The "out_dir" parameter is the temporary directory to write
                the indexes into."""

                for d in self._data_dict.values():
                        if d == self._data_main_dict or \
                            d == self._data_token_offset:
                                continue
                        d.write_dict_file(out_dir, self.file_version_number)

        def _generic_update_index(self, inputs, input_type,
            tmp_index_dir=None, image=None):
                """Performs all the steps needed to update the indexes.

                The "inputs" parameter iterates over the fmris which have been
                added or the pkgplans for the change in the image.

                The "input_type" paramter is a value specifying whether the
                input is fmris or pkgplans.

                The "tmp_index_dir" parameter allows this function to use a
                different temporary directory than the default.

                The "image" parameter must be set if "input_type" is pkgplans.
                It allows the index to automatically be rebuilt if the number
                of packages added since last index rebuild is greater than
                MAX_ADDED_NUMBER_PACKAGES."""

                self.lock()
                try:
                        # Allow the use of a directory other than the default
                        # directory to store the intermediate results in.
                        if not tmp_index_dir:
                                tmp_index_dir = self._tmp_dir
                        assert not (tmp_index_dir == self._index_dir)

                        # Read the existing dictionaries.
                        self._read_input_indexes(self._index_dir)
                except:
                        self.unlock()
                        raise

                try:
                        # If the temporary indexing directory already exists,
                        # remove it to ensure its empty.  Since the caller
                        # should have locked the index already, this should
                        # be safe.
                        if os.path.exists(tmp_index_dir):
                                shutil.rmtree(tmp_index_dir)

                        # Create directory.
                        makedirs(os.path.join(tmp_index_dir))

                        inputs = list(inputs)
                        fast_update = False

                        if input_type == IDX_INPUT_TYPE_PKG:
                                assert image

                                #
                                # Try to do a fast update; if that fails,
                                # do a full index rebuild.
                                #
                                fast_update = self._fast_update(inputs)

                                if not fast_update:
                                        self._data_main_dict.close_file_handle()
                                        self._data_fast_add.clear()
                                        self._data_fast_remove.clear()

                                        # Before passing control to rebuild
                                        # index, the index lock must be
                                        # released.
                                        self.unlock()
                                        return self.rebuild_index_from_scratch(
                                            image.gen_installed_pkgs(),
                                            tmp_index_dir)

                        elif input_type == IDX_INPUT_TYPE_FMRI:
                                assert not self._sort_fh
                                self._sort_fh = open(os.path.join(self._tmp_dir,
                                    SORT_FILE_PREFIX +
                                    str(self._sort_file_num)), "w")
                                self._sort_file_num += 1

                                self._progtrack.job_start(
                                    self._progtrack.JOB_REBUILD_SEARCH,
                                    goal=len(inputs))
                                dicts = self._process_fmris(inputs)
                                # Update the main dictionary file
                                self.__close_sort_fh()
                                self._update_index(dicts, tmp_index_dir)
                                self._progtrack.job_done(
                                    self._progtrack.JOB_REBUILD_SEARCH)

                                self.empty_index = False
                        else:
                                raise RuntimeError(
                                    "Got unknown input_type: {0}", input_type)

                        # Write out the helper dictionaries
                        self._write_assistant_dicts(tmp_index_dir)

                        # Move all files from the tmp directory into the index
                        # dir. Note: the need for consistent_open is that
                        # migrate is not an atomic action.
                        self._migrate(source_dir = tmp_index_dir,
                            fast_update=fast_update)
                        self.unlock()

                except:
                        self.unlock()
                        raise
                finally:
                        self._data_main_dict.close_file_handle()

        def client_update_index(self, pkgplan_list, image, tmp_index_dir=None):
                """This version of update index is designed to work with the
                client side of things.  Specifically, it expects a pkg plan
                list with added and removed FMRIs/manifests.  Note: if
                tmp_index_dir is specified, it must NOT exist in the current
                directory structure.  This prevents the indexer from
                accidentally removing files.  Image the image object. This is
                needed to allow correct reindexing from scratch to occur."""

                self._generic_update_index(pkgplan_list, IDX_INPUT_TYPE_PKG,
                    tmp_index_dir=tmp_index_dir, image=image)

        def server_update_index(self, fmris, tmp_index_dir=None):
                """ This version of update index is designed to work with the
                server side of things. Specifically, since we don't currently
                support removal of a package from a repo, this function simply
                takes a list of FMRIs to be added to the repot.  Currently, the
                only way to remove a package from the index is to remove it
                from the depot and reindex.  Note: if tmp_index_dir is
                specified, it must NOT exist in the current directory structure.
                This prevents the indexer from accidentally removing files."""

                self._generic_update_index(fmris, IDX_INPUT_TYPE_FMRI,
                    tmp_index_dir)

        def check_index_existence(self):
                """ Returns a boolean value indicating whether a consistent
                index exists. If an index exists but is inconsistent, an
                exception is raised."""

                try:
                        try:
                                res = \
                                    ss.consistent_open(self._data_dict.values(),
                                        self._index_dir,
                                        self._file_timeout_secs)
                        except (KeyboardInterrupt,
                            search_errors.InconsistentIndexException):
                                raise
                        except Exception:
                                return False
                finally:
                        for d in self._data_dict.values():
                                d.close_file_handle()
                assert res is not 0
                return res

        def rebuild_index_from_scratch(self, fmris, tmp_index_dir=None):
                """Removes any existing index directory and rebuilds the
                index based on the fmris and manifests provided as an
                argument.

                The "tmp_index_dir" parameter allows for a different directory
                than the default to be used."""

                self.file_version_number = INITIAL_VERSION_NUMBER
                self.empty_index = True

                # A lock can't be held while the index directory is being
                # removed as that can cause rmtree() to fail when using
                # NFS.  As such, attempt to get the lock first, then
                # unlock, immediately rename the old index directory,
                # and then remove the old the index directory and
                # create a new one.
                self.lock()
                self.unlock()

                portable.rename(self._index_dir, self._index_dir + ".old")
                try:
                        shutil.rmtree(self._index_dir + ".old")
                        makedirs(self._index_dir)
                except OSError as e:
                        if e.errno == errno.EACCES:
                                raise search_errors.ProblematicPermissionsIndexException(
                                    self._index_dir)

                self._generic_update_index(fmris, IDX_INPUT_TYPE_FMRI,
                    tmp_index_dir)
                self.empty_index = False

        def setup(self):
                """Seeds the index directory with empty stubs if the directory
                is consistently empty.  Does not overwrite existing indexes."""

                absent = False
                present = False

                makedirs(self._index_dir)
                for d in self._data_dict.values():
                        file_path = os.path.join(self._index_dir,
                            d.get_file_name())
                        if os.path.exists(file_path):
                                present = True
                        else:
                                absent = True
                        if absent and present:
                                raise search_errors.InconsistentIndexException(
                                        self._index_dir)
                if present:
                        return
                if self.file_version_number:
                        raise RuntimeError("Got file_version_number other than "
                            "None in setup.")
                self.file_version_number = INITIAL_VERSION_NUMBER
                for d in self._data_dict.values():
                        d.write_dict_file(self._index_dir,
                            self.file_version_number)

        @staticmethod
        def check_for_updates(index_root, cat):
                """Check to see whether the catalog has fmris which have not
                been indexed.

                'index_root' is the path to the index to check against.

                'cat' is the catalog to check for new fmris."""

                fmri_set = set((f.remove_publisher() for f in cat.fmris()))

                data = ss.IndexStoreSet("full_fmri_list")
                try:
                        data.open(index_root)
                except IOError as e:
                        if not os.path.exists(os.path.join(
                                index_root, data.get_file_name())):
                                return fmri_set
                        else:
                                raise
                try:
                        data.read_and_discard_matching_from_argument(fmri_set)
                finally:
                        data.close_file_handle()
                return fmri_set

        def _migrate(self, source_dir=None, dest_dir=None, fast_update=False):
                """Moves the indexes from a temporary directory to the
                permanent one.

                The "source_dir" parameter is the directory containing the
                new information.

                The "dest_dir" parameter is the directory containing the
                old information.

                The "fast_update" parameter determines whether the main
                dictionary and the token byte offset files are moved.  This is
                used so that when only the update logs are touched, the large
                files don't need to be moved."""

                if not source_dir:
                        source_dir = self._tmp_dir
                if not dest_dir:
                        dest_dir = self._index_dir
                assert not (source_dir == dest_dir)

                for d in self._data_dict.values():
                        if fast_update and (d == self._data_main_dict or
                            d == self._data_token_offset or
                            d == self._data_fmri_offsets):
                                continue
                        else:
                                shutil.move(os.path.join(source_dir,
                                    d.get_file_name()),
                                    os.path.join(dest_dir, d.get_file_name()))
                if not fast_update:
                        # Remove legacy index/pkg/ directory which is obsoleted
                        # by the fmri_offsets.v1 file.
                        try:
                                shutil.rmtree(os.path.join(dest_dir, "pkg"))
                        except KeyboardInterrupt:
                                raise
                        except Exception:
                                pass

                        for at, fh in self.at_fh.items():
                                shutil.move(
                                    os.path.join(source_dir, "__at_" + at),
                                    os.path.join(dest_dir, "__at_" + at))

                        for st, fh in self.st_fh.items():
                                shutil.move(
                                    os.path.join(source_dir, "__st_" + st),
                                    os.path.join(dest_dir, "__st_" + st))
                shutil.rmtree(source_dir)

        def lock(self, blocking=False):
                """Locks the index in preparation for an index-modifying
                operation.  Raises an IndexLockedException exception on
                failure.

                'blocking' is an optional boolean value indicating whether
                to block until the lock can be obtained or to raise an
                exception immediately if it cannot be."""

                try:
                        # Attempt to obtain a file lock.
                        self.__lockfile.lock(blocking=blocking)
                except EnvironmentError as e:
                        if e.errno == errno.ENOENT:
                                # If a lock was requested, and the only
                                # reason for failure was because the
                                # index directory doesn't exist yet,
                                # then create it and try once more.
                                if not os.path.exists(self._index_dir):
                                        makedirs(self._index_dir)
                                        return self.lock(blocking=blocking)
                                raise
                        if e.errno in (errno.EACCES, errno.EROFS):
                                raise search_errors.\
                                    ProblematicPermissionsIndexException(
                                    e.filename)
                        raise

        def unlock(self):
                """Unlocks the index."""

                self.__lockfile.unlock()
