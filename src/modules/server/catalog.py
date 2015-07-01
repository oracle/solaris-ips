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
# Copyright (c) 2010, 2015, Oracle and/or its affiliates. All rights reserved.
#

import bisect
import datetime
import errno
import os
import pkg.fmri as fmri
import pkg.portable as portable
import re
import stat
import tempfile

class CatalogException(Exception):

        def __init__(self, args=None):
                self._args = args


class CatalogPermissionsException(CatalogException):
        """Used to indicate the server catalog files do not have the expected
        permissions."""

        def __init__(self, files):
                """files should contain a list object with each entry consisting
                of a tuple of filename, expected_mode, received_mode."""
                if not files:
                        files = []
                CatalogException.__init__(self, files)

        def __str__(self):
                msg = _("The following catalog files have incorrect "
                    "permissions:\n")
                for f in self._args:
                        fname, emode, fmode = f
                        msg += _("\t{fname}: expected mode: {emode}, found "
                            "mode: {fmode}\n").format(fname=fname,
                            emode=emode, fmode=fmode)
                return msg


class ServerCatalog(object):
        """A Catalog is the representation of the package FMRIs available to
        the repository.  This class is only used for compatibility with v0
        repositories.

        The serialized structure of the repository is an unordered list of
        available package versions, followed by an unordered list of
        incorporation relationships between packages.  This latter section
        allows the graph to be topologically sorted by the client.

        S Last-Modified: [timespec]

        XXX A publisher mirror-uri ...
        XXX ...

        V fmri
        V fmri
        ...
        C fmri
        C fmri
        ...
        I fmri fmri
        I fmri fmri
        ...

        In order to improve the time to search the catalog, a cached list
        of package names is kept in the catalog instance."""

        # The file mode to be used for all catalog files.
        file_mode = stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH

        def __init__(self, cat_root, publisher=None, read_only=False):
                """Create a catalog.  If the path supplied does not exist,
                this will create the required directory structure.
                Otherwise, if the directories are already in place, the
                existing catalog is opened.  publisher names the publisher
                that is represented by this catalog."""

                self.catalog_root = cat_root
                self.catalog_file = os.path.normpath(os.path.join(
                    self.catalog_root, "catalog"))
                self.attrs = {}
                self.pub = publisher
                self.read_only = read_only
                self.__size = -1

                self.attrs["npkgs"] = 0

                if not os.path.exists(cat_root):
                        try:
                                os.makedirs(cat_root)
                        except EnvironmentError as e:
                                if e.errno in (errno.EACCES, errno.EROFS):
                                        return
                                raise

                self.load_attrs()
                self.check_prefix()
                self.__set_perms()

        @staticmethod
        def destroy(root=None):
                """Removes the on-disk files for the catalog only."""

                for fname in ("attrs", "catalog"):
                        path = os.path.normpath(os.path.join(root, fname))
                        try:
                                portable.remove(path)
                        except EnvironmentError as e:
                                if e.errno != errno.ENOENT:
                                        raise

        def __set_perms(self):
                """Sets permissions on catalog files if not read_only and if the
                current user can do so; raises CatalogPermissionsException if
                the permissions are wrong and cannot be corrected."""

                apath = os.path.normpath(os.path.join(self.catalog_root,
                    "attrs"))
                cpath = os.path.normpath(os.path.join(self.catalog_root,
                    "catalog"))

                # Force file_mode, so that unprivileged users can read these.
                bad_modes = []
                for fpath in (apath, cpath):
                        try:
                                if self.read_only:
                                        try:
                                                portable.assert_mode(fpath,
                                                    self.file_mode)
                                        except AssertionError as ae:
                                                bad_modes.append((fpath,
                                                    "{0:o}".format(self.file_mode),
                                                    "{0:o}".format(ae.mode)))
                                else:
                                        os.chmod(fpath, self.file_mode)
                        except EnvironmentError as e:
                                # If the files don't exist yet, move on.
                                if e.errno == errno.ENOENT:
                                        continue

                                # If the mode change failed for another reason,
                                # check to see if we actually needed to change
                                # it, and if so, add it to bad_modes.
                                try:
                                        portable.assert_mode(fpath,
                                            self.file_mode)
                                except AssertionError as ae:
                                        bad_modes.append((fpath,
                                            "{0:o}".format(self.file_mode),
                                            "{0:o}".format(ae.mode)))

                if bad_modes:
                        raise CatalogPermissionsException(bad_modes)

        def add_fmri(self, pfmri, critical = False):
                """Add a package, named by the fmri, to the catalog.
                Throws an exception if an identical package is already
                present.  Throws an exception if package has no version."""
                if pfmri.version == None:
                        raise CatalogException(
                            "Unversioned FMRI not supported: {0}".format(pfmri))

                assert not self.read_only

                # Callers should verify that the FMRI they're going to add is
                # valid; however, this check is here in case they're
                # lackadaisical
                if not self.valid_new_fmri(pfmri):
                        raise CatalogException("FMRI {0} already exists in "
                            "the catalog.".format(pfmri))

                if critical:
                        pkgstr = "C {0}\n".format(pfmri.get_fmri(anarchy = True))
                else:
                        pkgstr = "V {0}\n".format(pfmri.get_fmri(anarchy = True))

                self.__append_to_catalog(pkgstr)

                # Catalog size has changed, force recalculation on
                # next send()
                self.__size = -1

                self.attrs["npkgs"] += 1

                ts = datetime.datetime.now()
                self.set_time(ts)

                return ts

        def __append_to_catalog(self, pkgstr):
                """Write string named pkgstr to the catalog.  This
                routine handles moving the catalog to a temporary file,
                appending the new string, and renaming the temporary file
                on top of the existing catalog."""

                # Create tempfile
                tmp_num, tmpfile = tempfile.mkstemp(dir=self.catalog_root)

                try:
                        # use fdopen since we already have a filehandle
                        tfile = os.fdopen(tmp_num, "w")
                except OSError:
                        portable.remove(tmpfile)
                        raise

                # Try to open catalog file.  If it doesn't exist,
                # create an empty catalog file, and then open it read only.
                try:
                        pfile = open(self.catalog_file, "rb")
                except IOError as e:
                        if e.errno == errno.ENOENT:
                                # Creating an empty file
                                open(self.catalog_file, "wb").close()
                                pfile = open(self.catalog_file, "rb")
                        else:
                                portable.remove(tmpfile)
                                raise

                # Make sure we're at the start of the file
                pfile.seek(0)

                # Write all of the existing entries in the catalog
                # into the tempfile.  Then append the new lines at the
                # end.
                try:
                        for entry in pfile:
                                if entry == pkgstr:
                                        raise CatalogException(
                                            "Package {0} is already in "
                                            "the catalog".format(pkgstr))
                                else:
                                        tfile.write(entry)
                        tfile.write(pkgstr)
                except Exception:
                        portable.remove(tmpfile)
                        raise

                # Close our open files
                pfile.close()
                tfile.close()

                # Set the permissions on the tempfile correctly.
                # Mkstemp creates files as 600.  Rename the new
                # cataog on top of the old one.
                try:
                        os.chmod(tmpfile, self.file_mode)
                        portable.rename(tmpfile, self.catalog_file)
                except EnvironmentError:
                        portable.remove(tmpfile)
                        raise

        @staticmethod
        def cache_fmri(d, pfmri, pub, known=True):
                """Store the fmri in a data structure 'd' for fast lookup.

                'd' is a dict that maps each package name to another dictionary,
                itself mapping:

                        * each version string, which maps to a tuple of:
                          -- the fmri object
                          -- a dict of publisher prefixes with each value
                             indicating catalog presence

                        * "versions", which maps to a list of version objects,
                          kept in sorted order

                The structure is as follows:
                    pkg_name1: {
                        "versions": [<version1>, <version2>, ... ],
                        "version1": (
                            <fmri1>,
                            { "pub1": known, "pub2": known, ... },
                        ),
                        "version2": (
                            <fmri2>,
                            { "pub1": known, "pub2": known, ... },
                        ),
                        ...
                    },
                    pkg_name2: {
                        ...
                    },
                    ...

                (where names in quotes are strings, names in angle brackets are
                objects, and the rest of the syntax is Pythonic).

                The fmri is expected not to have an embedded publisher.  If it
                does, it will be ignored."""

                if pfmri.has_publisher():
                        # Cache entries must not contain the name of the
                        # publisher, otherwise matching during packaging
                        # operations may not work correctly.
                        pfmri = fmri.PkgFmri(pfmri.get_fmri(anarchy=True))

                pversion = str(pfmri.version)
                if pfmri.pkg_name not in d:
                        # This is the simplest representation of the cache data
                        # structure.
                        d[pfmri.pkg_name] = {
                            "versions": [pfmri.version],
                            pversion: (pfmri, { pub: known })
                        }

                elif pversion not in d[pfmri.pkg_name]:
                        d[pfmri.pkg_name][pversion] = (pfmri, { pub: known })
                        bisect.insort(d[pfmri.pkg_name]["versions"],
                            pfmri.version)
                elif pub not in d[pfmri.pkg_name][pversion][1]:
                        d[pfmri.pkg_name][pversion][1][pub] = known

        def attrs_as_lines(self):
                """Takes the list of in-memory attributes and returns
                a list of strings, each string naming an attribute."""

                ret = []

                for k, v in self.attrs.items():
                        s = "S {0}: {1}\n".format(k, v)
                        ret.append(s)

                return ret

        def as_lines(self):
                """Returns a generator function that produces the contents of
                the catalog as a list of strings."""

                try:
                        cfile = open(self.catalog_file, "r")
                except EnvironmentError as e:
                        # Missing catalog is fine; other errors need to
                        # be reported.
                        if e.errno == errno.ENOENT:
                                return
                        raise

                for e in cfile:
                        yield e

                cfile.close()

        def check_prefix(self):
                """If this version of the catalog knows about new prefixes,
                check the on disk catalog to see if we can perform any
                transformations based upon previously unknown catalog formats.

                This routine will add a catalog attribute if it doesn't exist,
                otherwise it checks this attribute against a hard-coded
                version-specific tuple to see if new methods were added.

                If new methods were added, it will call an additional routine
                that updates the on-disk catalog, if necessary."""


                # If a prefixes attribute doesn't exist, write one and get on
                # with it.
                if not "prefix" in self.attrs:
                        self.attrs["prefix"] = "".join(known_prefixes)
                        if not self.read_only:
                                self.save_attrs()
                        return

                # Prefixes attribute does exist.  Check if it has changed.
                pfx_set = set(self.attrs["prefix"])

                # Nothing to do if prefixes haven't changed
                if pfx_set == known_prefixes:
                        return

                # If known_prefixes contains a prefix not in pfx_set,
                # add the prefix and perform a catalog transform.
                new = known_prefixes.difference(pfx_set)
                if new:
                        pfx_set.update(new)

                        # Write out updated prefixes list
                        self.attrs["prefix"] = "".join(pfx_set)
                        if not self.read_only:
                                self.save_attrs()

        @property
        def exists(self):
                """A boolean value indicating whether the Catalog exists
                on-disk."""

                if not self.catalog_file:
                        return False
                return os.path.exists(self.catalog_file)

        def fmris(self):
                """A generator function that produces FMRIs as it
                iterates over the contents of the catalog."""

                try:
                        pfile = open(os.path.normpath(
                            os.path.join(self.catalog_root, "catalog")), "r")
                except IOError as e:
                        if e.errno == errno.ENOENT:
                                return
                        else:
                                raise

                for entry in pfile:
                        if not entry.startswith("V pkg") and \
                            not entry.startswith("C pkg"):
                                continue

                        try:
                                yield self.__parse_entry(entry, self.pub)
                        except (KeyboardInterrupt, SystemExit):
                                raise
                        except Exception as e:
                                raise RuntimeError("corrupt catalog entry for "
                                    "publisher '{0}': {1}".format(self.pub,
                                    entry))

                pfile.close()

        def last_modified(self):
                """Return the time at which the catalog was last modified."""

                return self.attrs.get("Last-Modified", None)

        def load_attrs(self, filenm = "attrs"):
                """Load attributes from the catalog file into the in-memory
                attributes dictionary"""

                apath = os.path.normpath(
                    os.path.join(self.catalog_root, filenm))
                if not os.path.exists(apath):
                        return

                afile = open(apath, "r")
                attrre = re.compile('^S ([^:]*): (.*)')

                for entry in afile:
                        m = attrre.match(entry)
                        if m != None:
                                self.attrs[m.group(1)] = m.group(2)

                afile.close()

                # convert npkgs to integer value
                if "npkgs" in self.attrs:
                        self.attrs["npkgs"] = int(self.attrs["npkgs"])

        def npkgs(self):
                """Returns the number of packages in the catalog."""

                return self.attrs["npkgs"]

        def origin(self):
                """Returns the URL of the catalog's origin."""

                return self.attrs.get("origin", None)

        @property
        def package_count(self):
                """Returns the number of packages in the catalog."""

                return self.attrs["npkgs"] or 0

        @classmethod
        def recv(cls, filep, path, pub=None):
                """A static method that takes a file-like object and
                a path.  This is the other half of catalog.send().  It
                reads a stream as an incoming catalog and lays it down
                on disk."""

                bad_fmri = None

                if not os.path.exists(path):
                        os.makedirs(path)

                afd, attrpath = tempfile.mkstemp(dir=path)
                cfd, catpath = tempfile.mkstemp(dir=path)

                attrf = os.fdopen(afd, "w")
                catf = os.fdopen(cfd, "w")

                attrpath_final = os.path.normpath(os.path.join(path, "attrs"))
                catpath_final = os.path.normpath(os.path.join(path, "catalog"))

                try:
                        for s in filep:
                                slen = len(s)

                                # If line is too short, process the next one
                                if slen < 2:
                                        continue
                                # check that line is in the proper format
                                elif not s[1].isspace():
                                        continue
                                elif not s[0] in known_prefixes:
                                        catf.write(s)
                                elif s.startswith("S "):
                                        attrf.write(s)
                                elif s.startswith("R "):
                                        catf.write(s)
                                else:
                                        # XXX Need to be able to handle old and
                                        # new format catalogs.
                                        try:
                                                f = fmri.PkgFmri(s[2:])
                                        except fmri.IllegalFmri as e:
                                                bad_fmri = e
                                                continue

                                        catf.write("{0} {1} {2} {3}\n".format(
                                            s[0], "pkg", f.pkg_name,
                                            f.version))
                except:
                        # Re-raise all uncaught exceptions after performing
                        # cleanup.
                        attrf.close()
                        catf.close()
                        os.remove(attrpath)
                        os.remove(catpath)
                        raise

                # If we got a parse error on FMRIs and transfer
                # wasn't truncated, raise a FmriFailures error.
                if bad_fmri:
                        attrf.close()
                        catf.close()
                        os.remove(attrpath)
                        os.remove(catpath)
                        raise bad_fmri

                # Write the publisher's origin into our attributes
                if pub:
                        origstr = "S origin: {0}\n".format(pub["origin"])
                        attrf.write(origstr)

                attrf.close()
                catf.close()

                # Mkstemp sets mode 600 on these files by default.
                # Restore them to 644, so that unprivileged users
                # may read these files.
                os.chmod(attrpath, cls.file_mode)
                os.chmod(catpath, cls.file_mode)

                portable.rename(attrpath, attrpath_final)
                portable.rename(catpath, catpath_final)

        def save_attrs(self, filenm="attrs"):
                """Save attributes from the in-memory catalog to a file
                specified by filenm."""

                tmpfile = None
                assert not self.read_only

                finalpath = os.path.normpath(
                    os.path.join(self.catalog_root, filenm))

                try:
                        tmp_num, tmpfile = tempfile.mkstemp(
                            dir=self.catalog_root)

                        tfile = os.fdopen(tmp_num, "w")

                        for a in self.attrs.keys():
                                s = "S {0}: {1}\n".format(a, self.attrs[a])
                                tfile.write(s)

                        tfile.close()
                        os.chmod(tmpfile, self.file_mode)
                        portable.rename(tmpfile, finalpath)

                except EnvironmentError as e:
                        # This may get called in a situation where
                        # the user does not have write access to the attrs
                        # file.
                        if tmpfile:
                                portable.remove(tmpfile)
                        if e.errno in (errno.EACCES, errno.EROFS):
                                return
                        else:
                                raise

                # Recalculate size on next send()
                self.__size = -1

        def send(self, filep, rspobj=None):
                """Send the contents of this catalog out to the filep
                specified as an argument."""

                if rspobj is not None:
                        rspobj.headers['Content-Length'] = str(self.size())

                def output():
                        # Send attributes first.
                        for line in self.attrs_as_lines():
                                yield line

                        try:
                                cfile = open(os.path.normpath(
                                    os.path.join(self.catalog_root, "catalog")),
                                    "r")
                        except IOError as e:
                                # Missing catalog is fine; other errors need to
                                # be reported.
                                if e.errno == errno.ENOENT:
                                        return
                                else:
                                        raise

                        for e in cfile:
                                yield e

                        cfile.close()

                if filep:
                        for line in output():
                                filep.write(line)
                else:
                        return output()

        def set_time(self, ts = None):
                """Set time to timestamp if supplied by caller.  Otherwise
                use the system time."""

                assert not self.read_only

                if ts and isinstance(ts, str):
                        self.attrs["Last-Modified"] = ts
                elif ts and isinstance(ts, datetime.datetime):
                        self.attrs["Last-Modified"] = ts.isoformat()
                else:
                        self.attrs["Last-Modified"] = timestamp()

                self.save_attrs()

        def size(self):
                """Return the size in bytes of the catalog and attributes."""

                if self.__size < 0:
                        try:
                                attr_stat = os.stat(os.path.normpath(
                                    os.path.join(self.catalog_root, "attrs")))
                                attr_sz = attr_stat.st_size
                        except OSError as e:
                                if e.errno == errno.ENOENT:
                                        attr_sz = 0
                                else:
                                        raise
                        try:
                                cat_stat =  os.stat(os.path.normpath(
                                    os.path.join(self.catalog_root, "catalog")))
                                cat_sz = cat_stat.st_size
                        except OSError as e:
                                if e.errno == errno.ENOENT:
                                        cat_sz = 0
                                else:
                                        raise

                        self.__size = attr_sz + cat_sz

                return self.__size

        @staticmethod
        def valid_new_fmri(pfmri):
                """Check that the fmri supplied as an argument would be valid
                to add to the catalog.  This checks to make sure that any past
                catalog operations (such as a rename or freeze) would not
                prohibit the caller from adding this FMRI."""

                if not fmri.is_valid_pkg_name(pfmri.get_name()):
                        return False
                return True

        @staticmethod
        def __parse_entry(line, pub):
                # This allows the ServerCatalog object to parse both
                # client and server catalog files which are otherwise
                # identical.
                #
                # Server Format:
                # C pkg:/foo@0.5.11,5.11-0.111:20090507T161015Z
                #
                # Client Format:
                # V pkg foo 0.5.11,5.11-0.111:20090508T161015Z
                sfmri = line[2:]
                if sfmri[:4] == "pkg ":
                        sfmri = sfmri[4:].replace(" ", "@")
                return fmri.PkgFmri(sfmri, publisher=pub)

        @classmethod
        def read_catalog(cls, cat, path, pub=None):
                """Read the catalog file in "path" and combine it with the
                existing data in "catalog"."""

                catf = open(os.path.join(path, "catalog"))
                for line in catf:
                        if not line.startswith("V pkg") and \
                            not line.startswith("C pkg"):
                                continue
                        f = cls.__parse_entry(line, pub)
                        ServerCatalog.cache_fmri(cat, f, pub)

                catf.close()

# Prefixes that this catalog knows how to handle
known_prefixes = frozenset("CSVR")

# Method used by Catalog and UpdateLog.  Since UpdateLog needs to know
# about Catalog, keep it in Catalog to avoid circular dependency problems.
def timestamp():
        """Return an integer timestamp that can be used for comparisons."""

        tobj = datetime.datetime.now()
        tstr = tobj.isoformat()
        return tstr

def ts_to_datetime(ts):
        """Take timestamp ts in string isoformat, and convert it to a datetime
        object."""

        year = int(ts[0:4])
        month = int(ts[5:7])
        day = int(ts[8:10])
        hour = int(ts[11:13])
        minutes = int(ts[14:16])
        sec = int(ts[17:19])
        # usec is not in the string if 0
        try:
                usec = int(ts[20:26])
        except ValueError:
                usec = 0
        return datetime.datetime(year, month, day, hour, minutes, sec, usec)
