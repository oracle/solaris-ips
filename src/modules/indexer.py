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


# Indexer is a class designed to index a set of manifests or pkg plans
# and provide a compact representation on disk which is quickly searchable.
#
# The file format it uses consists of 7 dictionaries. Each of these dictionaries
# list a version number in their first line. This version number is what allows
# the files to be opened consistently even when an re-index is happeneing. 5
# of these dictionaries (id_to_fmri_dict, id_to_action_dict,
# id_to_token_type_dict, id_to_keyval_dict and id_to_version_dict) are stored
# as an unsorted list. The line number of each entry corresponds to the id
# number the main dictionary uses for that entry. Full fmri list is a list of
# all packages which the current index has indexed. This is used for checking
# whether a package needs to be reindexed on a catalog rebuild.
#
# Here is an example of a line from the main dictionary, it is explained below:
# %gconf.xml (5,3,65689 => 249,202) (5,3,65690 => 249,202)
# (5,3,65691 => 249,202) (5,3,65692 => 249,202)
#
# The main dictionary has a more complicated format. Each line begins with a
# search token (%gconf.xml) followed by a list of mappings. Each mapping takes
# a token_type, action, and keyvalue tuple ((5,3,65689), (5,3,65690), 
# (5,3,65691), (5,3,65692)) to a list of pkg-stem, version pairs (249,202) in
# which the token is found in an action with token_type, action, and keyvalues
# matching the tuple. Further compaction is gained by storing everything but
# the token as an id which the other dictionaries can turn into human-readable
# content.
#
# In short, the definition of a main dictionary entry is:
# Note: "(", ")", and "=>" actually appear in the file
#       "[", "]", and "+" are used to specify pattern
# token [(token_type_id, action_id, keyval_id => [pkg_stem_id,version_id ]+)]+
#
# To use this class, construct one passing the directory to use for index
# storage to the contructor. For example:
# ind = Indexer('/usr/foo/path/to/image/or/repo/index')
# Externally, create either a list of fmri and path to that fmri pairs
# or build a pkg_plan. These should contain the changed, added, or removed,
# packages to the system.
#
# The client code should use
# client_update_index(pkgplanList, tmp_index_dir = ?)
# where tmp_index_dir allows a different directory than the default to be
# used for storing the index while it's being built. The default is to
# create a subdirectory TMP of the index directory and store the output
# in there temporarily.
#
# The server code should use
# server_update_index(self, fmri_manifest_list, tmp_index_dir = ?)
#
# The assumption is that the client will always be passing pkg plans
# (with one exception) while the server will always be passing
# fmri's paired with the paths to their manifests. The one exception
# to the client side assumption is when the index is being rebuilt.
# In that case, the client calls check_index. check_index only
# rebuilds the index if the index is empty or if it is forced
# to by an argument.
#
# If the storage structure is changed substantially, it will be necessary
# to change _calc_ram_use to reflect the new structures. The figures used
# were generated during a server index of a repository by taking a sampling
# of the internal structures after every manifest read and observing the memory
# usage reported by pmap. This provided a correlation of .9966 between the
# predicted and observed memory used during that run. When applied to a client
# side index it provided a correlation of .9964 between the predicted and
# observed memory used.

import os
import urllib
import shutil
import errno

import pkg.version

import pkg.manifest as manifest
import pkg.search_storage as ss
import pkg.search_errors as search_errors

# Constants for indicating whether pkgplans or fmri-manifest path pairs are
# used as arguments.
IDX_INPUT_TYPE_PKG = 0
IDX_INPUT_TYPE_FMRI = 1

INITIAL_VERSION_NUMBER = 1

class Indexer(object):
        """ See block comment at top for documentation """
        file_version_string = "VERSION: "

        def __init__(self, index_dir, default_max_ram_use, progtrack=None):
                self._num_keys = 0
                self._num_manifests = 0
                self._num_entries = 0
                self._max_ram_use = float(os.environ.get("PKG_INDEX_MAX_RAM",
                    default_max_ram_use)) * 1024

                # This structure was used to gather all index files into one
                # location. If a new index structure is needed, the files can
                # be added (or removed) from here. Providing a list or
                # dictionary allows an easy approach to opening or closing all
                # index files.

                self._data_dict = {
                        'fmri': ss.IndexStoreListDict('id_to_fmri_dict.ascii'),
                        'action':
                            ss.IndexStoreListDict('id_to_action_dict.ascii'),
                        'tok_type':
                            ss.IndexStoreListDict(
                                'id_to_token_type_dict.ascii'),
                        'version':
                            ss.IndexStoreListDict('id_to_version_dict.ascii',
                                Indexer._build_version),
                        'keyval':
                            ss.IndexStoreListDict('id_to_keyval_dict.ascii'),
                        'full_fmri': ss.IndexStoreSet('full_fmri_list'),
                        'main_dict': ss.IndexStoreMainDict('main_dict.ascii'),
                        'token_byte_offset':
                            ss.IndexStoreDictMutable('token_byte_offset')
                        }

                self._data_fmri = self._data_dict['fmri']
                self._data_action = self._data_dict['action']
                self._data_tok_type = self._data_dict['tok_type']
                self._data_version = self._data_dict['version']
                self._data_keyval = self._data_dict['keyval']
                self._data_full_fmri = self._data_dict['full_fmri']
                self._data_main_dict = self._data_dict['main_dict']
                self._data_token_offset = self._data_dict['token_byte_offset']

                self._index_dir = index_dir
                self._tmp_dir = os.path.join(self._index_dir, "TMP")

                self._indexed_manifests = 0
                self.server_repo = True
                self.empty_index = False
                self.file_version_number = None

                self._progtrack = progtrack

        @staticmethod
        def _build_version(vers):
                """ Private method for building versions from a string. """
                return pkg.version.Version(urllib.unquote(vers), None)

        def _read_input_indexes(self, directory):
                """ Opens all index files using consistent_open and reads all
                of them into memory except the main dictionary file to avoid
                inefficient memory usage.

                """
                res = ss.consistent_open(self._data_dict.values(), directory)
                if self._progtrack is not None:
                        self._progtrack.index_set_goal(
                            "Reading Existing Index", len(self._data_dict))
                if res == None:
                        self.file_version_number = INITIAL_VERSION_NUMBER
                        self.empty_index = True
                        return None
                self.file_version_number = res

                try:
                        try:
                                for d in self._data_dict.values():
                                        if (d == self._data_main_dict or
                                                d == self._data_token_offset):
                                                if self._progtrack is not None:
                                                        self._progtrack.index_add_progress()
                                                continue
                                        d.read_dict_file()
                                        if self._progtrack is not None:
                                                self._progtrack.index_add_progress()
                        except:
                                self._data_dict['main_dict'].close_file_handle()
                                raise
                finally:
                        for d in self._data_dict.values():
                                if d == self._data_main_dict:
                                        continue
                                d.close_file_handle()
                if self._progtrack is not None:
                        self._progtrack.index_done()

        def _add_terms(self, added_fmri, new_dict, added_dict):
                """ Adds the terms in new_dict to added_dict as pointers to
                added_fmri. Returns the number of entries added.
                """

                # Originally the structure of added_dict was
                # dict -> dict -> set. This arrangement wasted an enormous
                # amount of space on the overhead of the second level
                # dictionaries and third level sets. That structure was
                # replaced by dict -> list of
                # (key, list of (fmri, version) tuples) tuples.
                #
                # Because the second and third levels are small,
                # especially compared to the top level, doing a linear search
                # through the second level list is worth the savings of not
                # using dictionaries at the second level.
                #
                # The use of a set at the third level was to prevent
                # duplicate entries of a fmri-version tuple; however, this
                # should almost never happen as manifests cannot 
                # contain duplicate actions. The only way for duplicate
                # entries to occur is for a token to be repeated
                # within an action. For example a description of "the package
                # installs foo in the bar directory and installs baz in the
                # random directory" would have duplicate entries for "the"
                # and "installs." This problem is resolved by the conversion
                # of the list into a set in write_main_dict_line prior to the
                # list being written to.

                added_terms = 0
                version = added_fmri.version
                pkg_stem = added_fmri.get_pkg_stem(anarchy=True)
                fmri_id = self._data_fmri.get_id_and_add(pkg_stem)
                version_id = self._data_version.get_id_and_add(version)
                for tok_type in new_dict.keys():
                        tok_type_id = \
                            self._data_tok_type.get_id_and_add(tok_type)
                        for tok in new_dict[tok_type]:
                                if not (tok in added_dict):
                                        added_dict[tok] = []
                                ak_list = new_dict[tok_type][tok]
                                for action, keyval in ak_list:
                                        action_id = self._data_action.get_id_and_add(action)
                                        keyval_id = self._data_keyval.get_id_and_add(keyval)
                                        s = (tok_type_id, action_id, keyval_id)
                                        found = False
                                        tup = fmri_id, version_id
                                        for (list_s, list_set) in \
                                            added_dict[tok]:
                                                if list_s == s:
                                                        list_set.append(tup)
                                                        found = True
                                                        break
                                        if not found:
                                                tmp_set = []
                                                tmp_set.append(tup)
                                                added_dict[tok].append(
                                                    (s, tmp_set))
                                        added_terms += 1
                return added_terms

        @staticmethod
        def _calc_ram_use(dict_size, ids, total_terms):
                """ Estimates RAM used based on size of added and
                removed dictionaries. It returns an estimated size in KB.
                """
                # As noted above, these numbers were estimated through
                # experimentation. Do not change these unless the
                # data structure has changed. If it's necessary to change
                # them, resstimating them experimentally will
                # be necessary.
                return 0.5892 * dict_size +  -0.12295 * ids + \
                    -0.009595 * total_terms + 23512

        def _process_pkgplan_list(self, pkgplan_info, start_point):
                """ Takes a list of pkg plans and updates the internal storage
                to reflect the changes to the installed packages that plan
                reflects.
                """
                (d_filters, pkgplan_list) = pkgplan_info

                added_dict = {}
                removed_packages = set()

                remove_action_ids = set()
                remove_keyval_ids = set()
                remove_fmri_ids = set()
                remove_version_ids = set()
                remove_tok_type_ids = set()

                total_terms = 0
                stopping_early = False

                if self._progtrack is not None and start_point == 0:
                        self._progtrack.index_set_goal("Indexing Packages",
                            len(pkgplan_list))

                while start_point < len(pkgplan_list) and not stopping_early:
                        (d_fmri, d_manifest_path, o_fmri,
                            o_manifest_path) = \
                            pkgplan_list[start_point]
                        dest_fmri = d_fmri
                        origin_fmri = o_fmri

                        start_point += 1

                        # The pkg plan for a newly added package has an origin
                        # fmri of None. In that case, there's nothing
                        # to remove.
                        if origin_fmri is not None:
                                self._data_full_fmri.remove_entity(
                                    origin_fmri.get_fmri(anarchy=True))
                                mfst = manifest.Manifest()
                                mfst_file = file(o_manifest_path)
                                mfst.set_content(mfst_file.read())
                                origin_dict = mfst.search_dict()
                                version = origin_fmri.version
                                pkg_stem = \
                                    origin_fmri.get_pkg_stem(anarchy=True)
                                fmri_id = self._data_fmri.get_id(pkg_stem)
                                version_id = self._data_version.get_id(version)
                                remove_fmri_ids.add(fmri_id)
                                remove_version_ids.add(version_id)
                                for tok_type in origin_dict.keys():
                                        tok_type_id = \
                                            self._data_tok_type.get_id(tok_type)
                                        remove_tok_type_ids.add(tok_type_id)
                                        for tok in origin_dict[tok_type]:
                                                ak_list = \
                                                    origin_dict[tok_type][tok]
                                                for action, keyval in ak_list:
                                                        action_id = \
                                                            self._data_action.get_id(action)
                                                        keyval_id = \
                                                            self._data_keyval.get_id(keyval)
                                                        remove_action_ids.add(action_id)
                                                        remove_keyval_ids.add(keyval_id)
                                                        removed_packages.add( \
                                                            (fmri_id,
                                                            version_id))

                        # The pkg plan when a package is uninstalled has a
                        # dest_fmri of None, in which case there's nothing
                        # to add.
                        if dest_fmri is not None:
                                self._data_full_fmri.add_entity(
                                    dest_fmri.get_fmri(anarchy=True))
                                mfst = manifest.Manifest()
                                mfst_file = file(d_manifest_path)
                                mfst.set_content(mfst_file.read())
                                mfst.filter(d_filters)
                                dest_dict = mfst.search_dict()
                                total_terms += self._add_terms(dest_fmri,
                                    dest_dict, added_dict)

                        t_cnt = 0
                        for d in self._data_dict.values():
                                t_cnt += d.count_entries_removed_during_partial_indexing()

                        est_ram_use = self._calc_ram_use(len(added_dict), t_cnt,
                            (total_terms + len(removed_packages)))

                        if self._progtrack is not None:
                                self._progtrack.index_add_progress()

                        if est_ram_use >= self._max_ram_use:
                                stopping_early = True
                                break

                return (stopping_early, start_point, (added_dict,
                    removed_packages, remove_action_ids, remove_fmri_ids,
                    remove_keyval_ids, remove_tok_type_ids, remove_version_ids))

        def _process_fmri_manifest_list(self, fmri_manifest_list, start_point):
                """ Takes a list of fmri, manifest pairs and updates the
                internal storage to reflect the new packages.
                """
                added_dict = {}
                removed_packages = set()

                remove_action_ids = set()
                remove_keyval_ids = set()
                remove_fmri_ids = set()
                remove_version_ids = set()
                remove_tok_type_ids = set()

                stopping_early = False
                total_terms = 0

                if self._progtrack is not None and start_point == 0:
                        self._progtrack.index_set_goal("Indexing Packages",
                            len(fmri_manifest_list))

                while start_point < len(fmri_manifest_list) and \
                    not stopping_early:
                        added_fmri, manifest_path = \
                            fmri_manifest_list[start_point]
                        start_point += 1
                        self._data_full_fmri.add_entity(
                            added_fmri.get_fmri(anarchy=True))
                        mfst = manifest.Manifest()
                        mfst_file = file(manifest_path)
                        mfst.set_content(mfst_file.read())
                        new_dict = mfst.search_dict()
                        total_terms += self._add_terms(added_fmri, new_dict,
                            added_dict)

                        t_cnt = 0
                        for d in self._data_dict.values():
                                t_cnt += \
                                    d.count_entries_removed_during_partial_indexing()

                        est_ram_use = self._calc_ram_use(len(added_dict), t_cnt,
                            (total_terms + len(removed_packages)))

                        if self._progtrack is not None:
                                self._progtrack.index_add_progress()

                        if est_ram_use >= self._max_ram_use:
                                stopping_early = True
                                break

                return (stopping_early, start_point, (added_dict,
                    removed_packages, remove_action_ids, remove_fmri_ids,
                    remove_keyval_ids, remove_tok_type_ids, remove_version_ids))

        def _write_main_dict_line(self, file_handle, token, k_k_list_list,
            remove_action_ids, remove_keyval_ids, remove_tok_type_ids,
            remove_fmri_ids, remove_version_ids):
                """ Writes out the new main dictionary file and also adds the
                token offsets to _data_token_offset.
                """

                cur_location = file_handle.tell()
                self._data_token_offset.write_entity(token, cur_location)

                tmp = {}

                for (k, k_list) in k_k_list_list:
                        tok_type_id, action_id, keyval_id = k
                        remove_action_ids.discard(action_id)
                        remove_keyval_ids.discard(keyval_id)
                        remove_tok_type_ids.discard(tok_type_id)
                        # This conversion to a set is necessary to prevent
                        # duplicate entries. See the block comment in
                        # add_terms for more details.
                        tmp[k] = set(k_list)
                        for pkg_id, version_id in k_list:
                                remove_fmri_ids.discard(pkg_id)
                                remove_version_ids.discard(version_id)
                self._data_main_dict.write_main_dict_line(file_handle,
                    token, tmp)


        def _update_index(self, dicts, out_dir):
                """ Processes the main dictionary file and writes out a new
                main dictionary file reflecting the changes in the packages.
                """
                (added_dict, removed_packages, remove_action_ids,
                 remove_fmri_ids, remove_keyval_ids, remove_tok_type_ids,
                 remove_version_ids) = dicts

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
                        self._data_main_dict.get_file_name()), 'ab')

                self._data_token_offset.open_out_file(out_dir,
                    self.file_version_number)

                added_toks = added_dict.keys()
                added_toks.sort()
                added_toks.reverse()

                try:
                        for line in file_handle:
                                (tok, entries) = \
                                    self._data_main_dict.parse_main_dict_line(
                                    line)
                                new_entries = []
                                for (tok_type_id, action_id, keyval_id,
                                    fmri_ids) in entries:
                                        k = (tok_type_id, action_id, keyval_id)
                                        fmri_list = []
                                        for fmri_version in fmri_ids:
                                                if not fmri_version in \
                                                    removed_packages:
                                                        fmri_list.append(
                                                            fmri_version)
                                        if fmri_list:
                                                new_entries.append(
                                                    (k, fmri_list))
                                # Add tokens newly discovered in the added
                                # packages which are alphabetically earlier
                                # than the token most recently read from the
                                # existing main dictionary file.
                                while added_toks and (added_toks[-1] < tok):
                                        new_tok = added_toks.pop()
                                        assert ' ' not in new_tok
                                        assert len(new_tok) > 0
                                        self._write_main_dict_line(
                                            out_main_dict_handle,
                                            new_tok, added_dict[new_tok],
                                            remove_action_ids,
                                            remove_keyval_ids,
                                            remove_tok_type_ids,
                                            remove_fmri_ids, remove_version_ids)

                                # Combine the information about the current
                                # token from the new packages with the existing
                                # information for that token.
                                if added_dict.has_key(tok):
                                        tmp = added_toks.pop()
                                        assert tmp == tok
                                        for (k, k_list) in added_dict[tok]:
                                                found = False
                                                for (j, j_list) in new_entries:
                                                        if j == k:
                                                                found = True
                                                                j_list.extend(
                                                                    k_list)
                                                                break
                                                if not found:
                                                        new_entries.append(
                                                            (k, k_list))
                                # If this token has any packages still
                                # associated with it, write them to the file.
                                if new_entries:
                                        assert ' ' not in tok
                                        assert len(tok) > 0
                                        self._write_main_dict_line(
                                            out_main_dict_handle,
                                            tok, new_entries, remove_action_ids,
                                            remove_keyval_ids,
                                            remove_tok_type_ids,
                                            remove_fmri_ids, remove_version_ids)
                finally:
                        if not self.empty_index:
                                file_handle.close()
                                self._data_main_dict.close_file_handle()

                # For any new tokens which are alphabetically after the last
                # entry in the existing file, add them to the end of the file.
                while added_toks:
                        new_tok = added_toks.pop()
                        assert ' ' not in new_tok
                        assert len(new_tok) > 0
                        self._write_main_dict_line(
                            out_main_dict_handle,
                            new_tok, added_dict[new_tok], remove_action_ids,
                            remove_keyval_ids, remove_tok_type_ids,
                            remove_fmri_ids, remove_version_ids)
                out_main_dict_handle.close()
                self._data_token_offset.close_file_handle()

                # Things in remove_* are no longer found in the
                # main dictionary and can be safely removed. This
                # allows for reuse of space.
                for tmp_id in remove_action_ids:
                        self._data_action.remove_id(tmp_id)
                for tmp_id in remove_keyval_ids:
                        self._data_keyval.remove_id(tmp_id)
                for tmp_id in remove_fmri_ids:
                        self._data_fmri.remove_id(tmp_id)
                for tmp_id in remove_tok_type_ids:
                        self._data_tok_type.remove_id(tmp_id)
                for tmp_id in remove_version_ids:
                        self._data_version.remove_id(tmp_id)

                added_dict.clear()
                removed_packages.clear()

        def _write_assistant_dicts(self, out_dir):
                """ Write out the companion dictionaries needed for
                translating the internal representation of the main
                dictionary into human readable information. """
                for d in self._data_dict.values():
                        if d == self._data_main_dict or \
                            d == self._data_token_offset:
                                continue
                        d.write_dict_file(out_dir, self.file_version_number)

        def _generic_update_index(self, input_list, input_type,
                                   tmp_index_dir = None):
                """ Performs all the steps needed to update the indexes."""
                
                # Allow the use of a directory other than the default
                # directory to store the intermediate results in.
                if not tmp_index_dir:
                        tmp_index_dir = self._tmp_dir
                assert not (tmp_index_dir == self._index_dir)

                # Read the existing dictionaries.
                self._read_input_indexes(self._index_dir)

                # If the tmp_index_dir exists, it suggests a previous indexing
                # attempt aborted or that another indexer is running. In either
                # case, throw an exception.
                try:
                        os.makedirs(tmp_index_dir)
                except OSError, e:
                        if e.errno == errno.EEXIST:
                                raise \
                                    search_errors.PartialIndexingException(
                                    tmp_index_dir)
                        else:
                                raise

                more_to_do = True
                start_point = 0

                while more_to_do:

                        assert start_point >= 0

                        if input_type == IDX_INPUT_TYPE_PKG:
                                (more_to_do, start_point, dicts) = \
                                    self._process_pkgplan_list(input_list,
                                        start_point)
                        elif input_type == IDX_INPUT_TYPE_FMRI:
                                (more_to_do, start_point, dicts) = \
                                    self._process_fmri_manifest_list(
                                        input_list, start_point)
                        else:
                                raise RuntimeError("Got unknown input_type: %s", 
                                    input_type)

                        # Update the main dictionary file
                        self._update_index(dicts, tmp_index_dir)

                        self.empty_index = False

                        if more_to_do:
                                self._data_main_dict.shift_file(tmp_index_dir,
                                    ("_" + str(start_point)))

                # Write out the helper dictionaries
                self._write_assistant_dicts(tmp_index_dir)

                # Move all files from the tmp directory into the index dir
                # Note: the need for consistent_open is that migrate is not
                # an atomic action.
                self._migrate(source_dir = tmp_index_dir)

                if self._progtrack is not None:
                        self._progtrack.index_done()
                
        def client_update_index(self, pkgplan_list, tmp_index_dir = None):
                """ This version of update index is designed to work with the
                client side of things. Specifically, it expects a pkg plan
                list with added and removed FMRIs/manifests. Note: if
                tmp_index_dir is specified, it must NOT exist in the current
                directory structure. This prevents the indexer from
                accidentally removing files.
                """
                assert self._progtrack is not None
                self._generic_update_index(pkgplan_list, IDX_INPUT_TYPE_PKG,
                    tmp_index_dir)

        def server_update_index(self, fmri_manifest_list, tmp_index_dir = None):
                """ This version of update index is designed to work with the
                server side of things. Specifically, since we don't currently
                support removal of a package from a repo, this function simply
                takes a list of FMRIs to be added to the repot. Currently, the
                only way to remove a package from the index is to remove it
                from the depot and reindex. Note: if tmp_index_dir is
                specified, it must NOT exist in the current directory structure.
                This prevents the indexer from accidentally removing files.
                """
                self._generic_update_index(fmri_manifest_list,
                    IDX_INPUT_TYPE_FMRI, tmp_index_dir)

        def check_index_existence(self):
                """ Returns a boolean value indicating whether a consistent
                index exists.

                """
                try:
                        try:
                                res = \
                                    ss.consistent_open(self._data_dict.values(),
                                        self._index_dir)
                        except Exception:
                                return False
                finally:
                        for d in self._data_dict.values():
                                d.close_file_handle()
                assert res is not 0
                return res

        def check_index(self, fmris, force_rebuild, tmp_index_dir = None):
                """ Rebuilds the indexes using the given fmris if it is
                needed. It's needed if the index is empty or if force_rebuild
                is true.
                """
                if not force_rebuild:
                        try:
                                res = \
                                    ss.consistent_open(self._data_dict.values(),
                                        self._index_dir)
                        finally:
                                for d in self._data_dict.values():
                                        d.close_file_handle()
                        if res == None:
                                self.file_version_number = \
                                    INITIAL_VERSION_NUMBER
                                self.empty_index = True
                        else:
                                return

                try:
                        shutil.rmtree(self._index_dir)
                        os.makedirs(self._index_dir)
                except OSError, e:
                        if e.errno == errno.EACCES:
                                raise search_errors.ProblematicPermissionsIndexException(
                                    self._index_dir)
                self._generic_update_index(fmris, IDX_INPUT_TYPE_FMRI,
                    tmp_index_dir)
                self.empty_index = False

        def setup(self):
                """ Seeds the index directory with empty stubs if the directory
                is consistently empty. Does not overwrite existing indexes.
                """
                absent = False
                present = False
                for d in self._data_dict.values():
                        file_path = os.path.join(self._index_dir,
                            d.get_file_name())
                        if os.path.exists(file_path):
                                present = True
                        else:
                                absent = True
                        if absent and present:
                                raise \
                                    search_errors.InconsistentIndexException( \
                                        self._index_dir)
                if present:
                        return
                if self.file_version_number:
                        raise RuntimeError("Got file_version_number other"
                                           "than None in setup.")
                self.file_version_number = INITIAL_VERSION_NUMBER
                for d in self._data_dict.values():
                        d.write_dict_file(self._index_dir,
                            self.file_version_number)

        @staticmethod
        def check_for_updates(index_root, fmri_set):
                """ Checks fmri_set to see which members have not been indexed.
                It modifies fmri_set.
                """
                data =  ss.IndexStoreSet('full_fmri_list')
                try:
                        data.open(index_root)
                except IOError, e:
                        if not os.path.exists(os.path.join(
                                index_root, data.get_file_name())):
                                return fmri_set
                        else:
                                raise
                try:
                        data.read_and_discard_matching_from_argument(fmri_set)
                finally:
                        data.close_file_handle()

        def _migrate(self, source_dir = None, dest_dir = None):
                """ Moves the indexes from a temporary directory to the
                permanent one.
                """
                if not source_dir:
                        source_dir = self._tmp_dir
                if not dest_dir:
                        dest_dir = self._index_dir
                assert not (source_dir == dest_dir)
                logfile = os.path.join(dest_dir, "log")
                lf = open(logfile, 'wb')
                lf.write("moving " + source_dir + " to " + dest_dir + "\n")
                lf.flush()

                for d in self._data_dict.values():
                        shutil.move(os.path.join(source_dir, d.get_file_name()),
                            os.path.join(dest_dir, d.get_file_name()))

                lf.write("finished moving\n")
                lf.close()
                os.remove(logfile)
                shutil.rmtree(source_dir)
