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
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

import os
import errno
import time
import hashlib
from six.moves.urllib.parse import quote, unquote

import pkg.fmri as fmri
import pkg.search_errors as search_errors
import pkg.portable as portable
from pkg.misc import PKG_FILE_BUFSIZ, force_bytes

FAST_ADD = 'fast_add.v1'
FAST_REMOVE = 'fast_remove.v1'
MANIFEST_LIST = 'manf_list.v1'
FULL_FMRI_FILE = 'full_fmri_list'
MAIN_FILE = 'main_dict.ascii.v2'
BYTE_OFFSET_FILE = 'token_byte_offset.v1'
FULL_FMRI_HASH_FILE = 'full_fmri_list.hash'
FMRI_OFFSETS_FILE = 'fmri_offsets.v1'

def consistent_open(data_list, directory, timeout = 1):
        """Opens all data holders in data_list and ensures that the
        versions are consistent among all of them.
        It retries several times in case a race condition between file
        migration and open is encountered.
        Note: Do not set timeout to be 0. It will cause an exception to be
        immediately raised.
        """

        missing = None
        cur_version = None

        start_time = time.time()

        while cur_version == None and missing != True:
                # The assignments to cur_version and missing cannot be
                # placed here. They must be reset prior to breaking out of the
                # for loop so that the while loop condition will be true. They
                # cannot be placed after the for loop since that path is taken
                # when all files are missing or opened successfully.
                if timeout != None and ((time.time() - start_time) > timeout):
                        raise search_errors.InconsistentIndexException(
                            directory)
                for d in data_list:
                        # All indexes must have the same version and all must
                        # either be present or absent for a successful return.
                        # If one of these conditions is not met, the function
                        # tries again until it succeeds or the time spent in
                        # in the function is greater than timeout.
                        try:
                                f = os.path.join(directory, d.get_file_name())
                                fh = open(f, 'r')
                                # If we get here, then the current index file
                                # is present.
                                if missing == None:
                                        missing = False
                                elif missing:
                                        for dl in data_list:
                                                dl.close_file_handle()
                                        missing = None
                                        cur_version = None
                                        break
                                d.set_file_handle(fh, f)
                                version_tmp = fh.readline()
                                version_num = \
                                    int(version_tmp.split(' ')[1].rstrip('\n'))
                                # Read the version. If this is the first file,
                                # set the expected version otherwise check that
                                # the version matches the expected version.
                                if cur_version == None:
                                        cur_version = version_num
                                elif not (cur_version == version_num):
                                        # Got inconsistent versions, so close
                                        # all files and try again.
                                        for d in data_list:
                                                d.close_file_handle()
                                        missing = None
                                        cur_version = None
                                        break
                        except IOError as e:
                                if e.errno == errno.ENOENT:
                                        # If the index file is missing, ensure
                                        # that previous files were missing as
                                        # well. If not, try again.
                                        if missing == False:
                                                for d in data_list:
                                                        d.close_file_handle()
                                                missing = None
                                                cur_version = None
                                                break
                                        missing = True
                                else:
                                        for d in data_list:
                                                d.close_file_handle()
                                        raise
        if missing:
                assert cur_version == None
                # The index is missing (ie, no files were present).
                return None
        else:
                assert cur_version is not None
                return cur_version


class IndexStoreBase(object):
        """Base class for all data storage used by the indexer and
        queryEngine. All members must have a file name and maintain
        an internal file handle to that file as instructed by external
        calls.
        """

        def __init__(self, file_name):
                self._name = file_name
                self._file_handle = None
                self._file_path = None
                self._size = None
                self._mtime = None
                self._inode = None
                self._have_read = False

        def get_file_name(self):
                return self._name

        def set_file_handle(self, f_handle, f_path):
                if self._file_handle:
                        raise RuntimeError("setting an extant file handle, "
                            "must close first, fp is: " + f_path)
                else:
                        self._file_handle = f_handle
                        self._file_path = f_path
                        if self._mtime is None:
                                stat_info = os.stat(self._file_path)
                                self._mtime = stat_info.st_mtime
                                self._size = stat_info.st_size
                                self._inode = stat_info.st_ino

        def get_file_path(self):
                return self._file_path

        def __copy__(self):
                return self.__class__(self._name)

        def close_file_handle(self):
                """Closes the file handle and clears it so that it cannot
                be reused.
                """

                if self._file_handle:
                        self._file_handle.close()
                        self._file_handle = None

        def _protected_write_dict_file(self, path, version_num, iterable):
                """Writes the dictionary in the expected format.
                Note: Only child classes should call this method.
                """
                version_string = "VERSION: "
                file_handle = open(os.path.join(path, self._name), 'w')
                file_handle.write(version_string + str(version_num) + "\n")
                for name in iterable:
                        file_handle.write(str(name) + "\n")
                file_handle.close()

        def should_reread(self):
                """This method uses the modification time and the file size
                to (heuristically) determine whether the file backing this
                storage has changed since it was last read.
                """
                stat_info = os.stat(self._file_path)
                if self._inode != stat_info.st_ino or \
                    self._mtime != stat_info.st_mtime or \
                    self._size != stat_info.st_size:
                        return True
                return not self._have_read

        def read_dict_file(self):
                self._have_read = True

        def open(self, directory):
                """This uses consistent open to ensure that the version line
                processing is done consistently and that only a single function
                actually opens files stored using this class.
                """
                return consistent_open([self], directory)


class IndexStoreMainDict(IndexStoreBase):
        """Class for representing the main dictionary file
        """
        # Here is an example of a line from the main dictionary, it is
        # explained below:
        # %25gconf.xml file!basename@basename#579,13249,13692,77391,77628
        #
        # Each line begins with a urllib quoted search token. It's followed by
        # a set of space separated lists.  Each of these lists begin with an
        # action type.  It's separated from its sublist by a '!'.  Next is the
        # key type, which is separated from its sublist by a '@'.  Next is the
        # full value, which is used in set actions to hold the full value which
        # matched the token.  It's separated from its sublist by a '#'.  The
        # next token (579) is the fmri id.  The subsequent comma separated
        # values are the byte offsets into that manifest of the lines containing
        # that token.

        sep_chars = [" ", "!", "@", "#", ","]

        def __init__(self, file_name):
                IndexStoreBase.__init__(self, file_name)
                self._old_suffix = None

        def write_dict_file(self, path, version_num):
                """This class relies on external methods to write the file.
                Making this empty call to protected_write_dict_file allows the
                file to be set up correctly with the version number stored
                correctly.
                """
                IndexStoreBase._protected_write_dict_file(self, path,
                                                          version_num, [])

        def get_file_handle(self):
                """Return the file handle. Note that doing
                anything other than sequential reads or writes
                to or from this file_handle may result in unexpected
                behavior. In short, don't use seek.
                """
                return self._file_handle

        @staticmethod
        def parse_main_dict_line(line):
                """Parses one line of a main dictionary file.
                Changes to this function must be paired with changes to
                write_main_dict_line below.

                This should produce the same data structure that
                _write_main_dict_line in indexer.py creates to write out each
                line.
                """

                split_chars = IndexStoreMainDict.sep_chars
                line = line.rstrip('\n')
                tmp = line.split(split_chars[0])
                tok = unquote(tmp[0])
                atl = tmp[1:]
                res = []
                for ati in atl:
                        tmp = ati.split(split_chars[1])
                        action_type = tmp[0]
                        stl = tmp[1:]
                        at_res = []
                        for sti in stl:
                                tmp = sti.split(split_chars[2])
                                subtype = tmp[0]
                                fvl = tmp[1:]
                                st_res = []
                                for fvi in fvl:
                                        tmp = fvi.split(split_chars[3])
                                        full_value = unquote(tmp[0])
                                        pfl = tmp[1:]
                                        fv_res = []
                                        for pfi in pfl:
                                                tmp = pfi.split(split_chars[4])
                                                pfmri_index = int(tmp[0])
                                                offsets = [
                                                    int(t) for t in tmp[1:]
                                                ]
                                                fv_res.append(
                                                    (pfmri_index, offsets))
                                        st_res.append((full_value, fv_res))
                                at_res.append((subtype, st_res))
                        res.append((action_type, at_res))
                return tok, res

        @staticmethod
        def parse_main_dict_line_for_token(line):
                """Pulls the token out of a line from a main dictionary file.
                Changes to this function must be paired with changes to
                write_main_dict_line below.
                """

                line = line.rstrip("\n")
                lst = line.split(" ", 1)
                return unquote(lst[0])

        @staticmethod
        def transform_main_dict_line(token, entries):
                """Paired with parse_main_dict_line above.  Transforms a token
                and its data into the string which can be written to the main
                dictionary.

                The "token" parameter is the token whose index line is being
                generated.

                The "entries" parameter is a list of lists of lists and so on.
                It contains information about where and how "token" was seen in
                manifests.  The depth of all lists at each level must be
                consistent, and must match the length of "sep_chars" and
                "quote".  The details of the contents on entries are described
                in _write_main_dict_line in indexer.py.
                """
                sep_chars = IndexStoreMainDict.sep_chars
                res = "{0}".format(quote(str(token)))
                for ati, atl in enumerate(entries):
                        action_type, atl = atl
                        res += "{0}{1}".format(sep_chars[0], action_type)
                        for sti, stl in enumerate(atl):
                                subtype, stl = stl
                                res += "{0}{1}".format(sep_chars[1], subtype)
                                for fvi, fvl in enumerate(stl):
                                        full_value, fvl = fvl
                                        res += "{0}{1}".format(sep_chars[2],
                                            quote(str(full_value)))
                                        for pfi, pfl in enumerate(fvl):
                                                pfmri_index, pfl = pfl
                                                res += "{0}{1}".format(sep_chars[3],
                                                    pfmri_index)
                                                for offset in pfl:
                                                        res += "{0}{1}".format(
                                                            sep_chars[4],
                                                            offset)
                return res + "\n"

        def count_entries_removed_during_partial_indexing(self):
                """Returns the number of entries removed during a second phase
                of indexing.
                """
                # This returns 0 because this class is not responsible for
                # storing anything in memory.
                return 0

        def shift_file(self, use_dir, suffix):
                """Moves the existing file with self._name in directory
                use_dir to a new file named self._name + suffix in directory
                use_dir. If it has done this previously, it removes the old
                file it moved. It also opens the newly moved file and uses
                that as the file for its file handle.
                """
                assert self._file_handle is None
                orig_path = os.path.join(use_dir, self._name)
                new_path = os.path.join(use_dir, self._name + suffix)
                portable.rename(orig_path, new_path)
                tmp_name = self._name
                self._name = self._name + suffix
                self.open(use_dir)
                self._name = tmp_name
                if self._old_suffix is not None:
                        os.remove(os.path.join(use_dir, self._old_suffix))
                self._old_suffix = self._name + suffix


class IndexStoreListDict(IndexStoreBase):
        """Used when both a list and a dictionary are needed to
        store the information. Used for bidirectional lookup when
        one item is an int (an id) and the other is not (an entity). It
        maintains a list of empty spots in the list so that adding entities
        can take advantage of unused space. It encodes empty space as a blank
        line in the file format and '' in the internal list.
        """

        def __init__(self, file_name, build_function=lambda x: x,
            decode_function=lambda x: x):
                IndexStoreBase.__init__(self, file_name)
                self._list = []
                self._dict = {}
                self._next_id = 0
                self._list_of_empties = []
                self._decode_func = decode_function
                self._build_func = build_function
                self._line_cnt = 0

        def add_entity(self, entity, is_empty):
                """Adds an entity consistently to the list and dictionary
                allowing bidirectional lookup.
                """
                assert (len(self._list) == self._next_id)
                if self._list_of_empties and not is_empty:
                        use_id = self._list_of_empties.pop(0)
                        assert use_id <= len(self._list)
                        if use_id == len(self._list):
                                self._list.append(entity)
                                self._next_id += 1
                        else:
                                self._list[use_id] = entity
                else:
                        use_id = self._next_id
                        self._list.append(entity)
                        self._next_id += 1
                if not(is_empty):
                        self._dict[entity] = use_id
                assert (len(self._list) == self._next_id)
                return use_id

        def remove_id(self, in_id):
                """deletes in_id from the list and the dictionary """
                entity = self._list[in_id]
                self._list[in_id] = ""
                self._dict[entity] = ""

        def remove_entity(self, entity):
                """deletes the entity from the list and the dictionary """
                in_id = self._dict[entity]
                self._dict[entity] = ""
                self._list[in_id] = ""

        def get_id(self, entity):
                """returns the id of entity """
                return self._dict[entity]

        def get_id_and_add(self, entity):
                """Adds entity if it's not previously stored and returns the
                id for entity.
                """
                # This code purposefully reimplements add_entity
                # code. Replacing the function calls to has_entity, add_entity,
                # and get_id with direct access to the data structure gave a
                # speed up of a factor of 4. Because this is a very hot path,
                # the tradeoff seemed appropriate.

                if entity not in self._dict:
                        assert (len(self._list) == self._next_id)
                        if self._list_of_empties:
                                use_id = self._list_of_empties.pop(0)
                                assert use_id <= len(self._list)
                                if use_id == len(self._list):
                                        self._list.append(entity)
                                        self._next_id += 1
                                else:
                                        self._list[use_id] = entity
                        else:
                                use_id = self._next_id
                                self._list.append(entity)
                                self._next_id += 1
                        self._dict[entity] = use_id
                assert (len(self._list) == self._next_id)
                return self._dict[entity]

        def get_entity(self, in_id):
                """return the entity in_id maps to """
                return self._list[in_id]

        def has_entity(self, entity):
                """check if entity is in storage """
                return entity in self._dict

        def has_empty(self):
                """Check if the structure has any empty elements which
                can be filled with data.
                """
                return (len(self._list_of_empties) > 0)

        def get_next_empty(self):
                """returns the next id which maps to no element """
                return self._list_of_empties.pop()

        def write_dict_file(self, path, version_num):
                """Passes self._list to the parent class to write to a file.
                """
                IndexStoreBase._protected_write_dict_file(self, path,
                    version_num, (self._decode_func(l) for l in self._list))
        def read_dict_file(self):
                """Reads in a dictionary previously stored using the above
                call
                """
                assert self._file_handle
                self._dict.clear()
                self._list = []
                for i, line in enumerate(self._file_handle):
                        # A blank line means that id can be reused.
                        tmp = self._build_func(line.rstrip("\n"))
                        if line == "\n":
                                self._list_of_empties.append(i)
                        else:
                                self._dict[tmp] = i
                        self._list.append(tmp)
                        self._line_cnt = i + 1
                        self._next_id = i + 1
                IndexStoreBase.read_dict_file(self)
                return self._line_cnt

        def count_entries_removed_during_partial_indexing(self):
                """Returns the number of entries removed during a second phase
                of indexing.
                """
                return len(self._list)

class IndexStoreDict(IndexStoreBase):
        """Class used when only entity -> id lookup is needed
        """

        def __init__(self, file_name):
                IndexStoreBase.__init__(self, file_name)
                self._dict = {}
                self._next_id = 0

        def get_dict(self):
                return self._dict

        def get_entity(self, in_id):
                return self._dict[in_id]

        def has_entity(self, entity):
                return entity in self._dict

        def read_dict_file(self):
                """Reads in a dictionary stored in line number -> entity
                format
                """
                self._dict.clear()
                for line_cnt, line in enumerate(self._file_handle):
                        line = line.rstrip("\n")
                        self._dict[line_cnt] = line
                IndexStoreBase.read_dict_file(self)

        def count_entries_removed_during_partial_indexing(self):
                """Returns the number of entries removed during a second phase
                of indexing.
                """
                return len(self._dict)

class IndexStoreDictMutable(IndexStoreBase):
        """Dictionary which allows dynamic update of its storage
        """

        def __init__(self, file_name):
                IndexStoreBase.__init__(self, file_name)
                self._dict = {}

        def get_dict(self):
                return self._dict

        def has_entity(self, entity):
                return entity in self._dict

        def get_id(self, entity):
                return self._dict[entity]

        def get_keys(self):
                return list(self._dict.keys())

        @staticmethod
        def __quote(str):
                if " " in str:
                        return "1" + quote(str)
                else:
                        return "0" + str

        def read_dict_file(self):
                """Reads in a dictionary stored in with an entity
                and its number on each line.
                """
                self._dict.clear()
                for line in self._file_handle:
                        token, offset = line.split(" ")
                        if token[0] == "1":
                                token = unquote(token[1:])
                        else:
                                token = token[1:]
                        offset = int(offset)
                        self._dict[token] = offset
                IndexStoreBase.read_dict_file(self)

        def open_out_file(self, use_dir, version_num):
                """Opens the output file for this class and prepares it
                to be written via write_entity.
                """
                self.write_dict_file(use_dir, version_num)
                self._file_handle = open(os.path.join(use_dir, self._name),
                    'a', buffering=PKG_FILE_BUFSIZ)

        def write_entity(self, entity, my_id):
                """Writes the entity out to the file with my_id """
                assert self._file_handle is not None
                self._file_handle.write(self.__quote(str(entity)) + " " +
                    str(my_id) + "\n")

        def write_dict_file(self, path, version_num):
                """ Generates an iterable list of string representations of
                the dictionary that the parent's protected_write_dict_file
                function can call.
                """
                IndexStoreBase._protected_write_dict_file(self, path,
                    version_num, [])

        def count_entries_removed_during_partial_indexing(self):
                """Returns the number of entries removed during a second phase
                of indexing.
                """
                return 0

class IndexStoreSetHash(IndexStoreBase):
        def __init__(self, file_name):
                IndexStoreBase.__init__(self, file_name)
                # In order to interoperate with older clients, we must use sha-1
                # here.
                self.hash_val = hashlib.sha1().hexdigest()

        def set_hash(self, vals):
                """Set the has value."""
                self.hash_val = self.calc_hash(vals)

        def calc_hash(self, vals):
                """Calculate the hash value of the sorted members of vals."""
                vl = list(vals)
                vl.sort()
                # In order to interoperate with older clients, we must use sha-1
                # here.
                shasum = hashlib.sha1()
                for v in vl:
                         # Unicode-objects must be encoded before hashing.
                         shasum.update(force_bytes(v))
                return shasum.hexdigest()

        def write_dict_file(self, path, version_num):
                """Write self.hash_val out to a line in a file """
                IndexStoreBase._protected_write_dict_file(self, path,
                    version_num, [self.hash_val])

        def read_dict_file(self):
                """Process a dictionary file written using the above method
                """
                sp = self._file_handle.tell()
                res = 0
                for res, line in enumerate(self._file_handle):
                        assert res < 1
                        self.hash_val = line.rstrip()
                self._file_handle.seek(sp)
                IndexStoreBase.read_dict_file(self)
                return res

        def check_against_file(self, vals):
                """Check the hash value of vals against the value stored
                in the file for this object."""
                if not self._have_read:
                        self.read_dict_file()
                incoming_hash = self.calc_hash(vals)
                if self.hash_val != incoming_hash:
                        raise search_errors.IncorrectIndexFileHash(
                            self.hash_val, incoming_hash)

        def count_entries_removed_during_partial_indexing(self):
                """Returns the number of entries removed during a second phase
                of indexing."""
                return 0

class IndexStoreSet(IndexStoreBase):
        """Used when only set membership is desired.
        This is currently designed for exclusive use
        with storage of fmri.PkgFmris. However, that impact
        is only seen in the read_and_discard_matching_from_argument
        method.
        """
        def __init__(self, file_name):
                IndexStoreBase.__init__(self, file_name)
                self._set = set()

        def get_set(self):
                return self._set

        def clear(self):
                self._set.clear()

        def add_entity(self, entity):
                self._set.add(entity)

        def remove_entity(self, entity):
                """Remove entity purposfully assumes that entity is
                already in the set to be removed. This is useful for
                error checking and debugging.
                """
                self._set.remove(entity)

        def has_entity(self, entity):
                return (entity in self._set)

        def write_dict_file(self, path, version_num):
                """Write each member of the set out to a line in a file """
                IndexStoreBase._protected_write_dict_file(self, path,
                    version_num, self._set)

        def read_dict_file(self):
                """Process a dictionary file written using the above method
                """
                assert self._file_handle
                res = 0
                self._set.clear()
                for i, line in enumerate(self._file_handle):
                        line = line.rstrip("\n")
                        assert i == len(self._set)
                        self.add_entity(line)
                        res = i + 1
                IndexStoreBase.read_dict_file(self)
                return res

        def read_and_discard_matching_from_argument(self, fmri_set):
                """Reads the file and removes all frmis in the file
                from fmri_set.
                """
                if self._file_handle:
                        for line in self._file_handle:
                                f = fmri.PkgFmri(line)
                                fmri_set.discard(f)

        def count_entries_removed_during_partial_indexing(self):
                """Returns the number of entries removed during a second phase
                of indexing."""
                return len(self._set)


class InvertedDict(IndexStoreBase):
        """Class used to store and process fmri to offset mappings.  It does
        delta compression and deduplication of shared offset sets when writing
        to a file."""

        def __init__(self, file_name, p_id_trans):
                """file_name is the name of the file to write to or read from.
                p_id_trans is an object which has a get entity method which,
                when given a package id number returns the PkgFmri object
                for that id number."""

                IndexStoreBase.__init__(self, file_name)
                self._p_id_trans = p_id_trans
                self._dict = {}
                self._fmri_offsets = {}

        def __copy__(self):
                return self.__class__(self._name, self._p_id_trans)

        def add_pair(self, p_id, offset):
                """Adds a package id number and an associated offset to the
                existing dictionary."""

                try:
                        self._fmri_offsets[p_id].append(offset)
                except KeyError:
                        self._fmri_offsets[p_id] = [offset]

        def invert_id_to_offsets_dict(self):
                """Does delta encoding of offsets to reduce space by only
                storing the difference between the current offset and the
                previous offset.  It also performs deduplication so that all
                packages with the same set of offsets share a common bucket."""

                inv = {}
                for p_id in list(self._fmri_offsets.keys()):
                        old_o = 0
                        bucket = []
                        for o in sorted(set(self._fmri_offsets[p_id])):
                                bucket.append(o - old_o)
                                old_o = o
                        h = " ".join([str(o) for o in bucket])
                        del self._fmri_offsets[p_id]
                        if h not in inv:
                                inv[h] = []
                        inv[h].append(p_id)
                return inv

        @staticmethod
        def __make_line(offset_str, p_ids, trans):
                """For a given offset string, a list of package id numbers,
                and a translator from package id numbers to PkgFmris, returns
                the string which represents that information. Its format is
                space separated package fmris, followed by a !, followed by
                space separated offsets which have had delta compression
                performed."""

                return " ".join([
                    trans.get_entity(p_id).get_fmri(anarchy=True,
                        include_scheme=False)
                    for p_id in p_ids
                    ]) + "!" + offset_str

        def write_dict_file(self, path, version_num):
                """Write the mapping of package fmris to offset sets out
                to the file."""

                inv = self.invert_id_to_offsets_dict()
                IndexStoreBase._protected_write_dict_file(self, path,
                    version_num, (
                        self.__make_line(o, inv[o], self._p_id_trans)
                        for o in inv
                    ))

        def read_dict_file(self):
                """Read a file written by the above function and store the
                information in a dictionary."""

                assert self._file_handle
                for l in self._file_handle:
                        fmris, offs = l.split("!")
                        self._dict[fmris] = offs
                IndexStoreBase.read_dict_file(self)

        @staticmethod
        def de_delta(offs):
                """For a list of strings of offsets, undo the delta compression
                that has been performed."""

                old_o = 0
                ret = []
                for o in offs:
                        o = int(o) + old_o
                        ret.append(o)
                        old_o = o
                return ret

        def get_offsets(self, match_func):
                """For a given function which returns true if it matches the
                desired fmri, return the offsets which are associated with the
                fmris which match."""

                offs = []
                for fmris in self._dict.keys():
                        for p in fmris.split():
                                if match_func(p):
                                        offs.extend(self.de_delta(
                                            self._dict[fmris].split()))
                                        break
                return set(offs)
