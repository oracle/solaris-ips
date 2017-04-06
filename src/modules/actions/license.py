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

"""module describing a license packaging object

This module contains the LicenseAction class, which represents a license
packaging object.  This contains a payload of the license text, and a single
attribute, 'license', which is the name of the license.  Licenses are
installed on the system in the package's directory."""

import errno
import os
from stat import S_IWRITE, S_IREAD

from . import generic
import pkg.digest as digest
import pkg.misc as misc
import pkg.portable as portable
import zlib

from pkg.client.api_errors import ActionExecutionError
from six.moves.urllib.parse import quote

class LicenseAction(generic.Action):
        """Class representing a license packaging object."""

        __slots__ = ["hash"]

        name = "license"
        key_attr = "license"
        unique_attrs = ("license", )
        reverse_indices = ("license", )
        refcountable = True
        globally_identical = True
        ordinality = generic._orderdict[name]

        has_payload = True

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                self.hash = "NOHASH"

        def preinstall(self, pkgplan, orig):
                # Set attrs["path"] so filelist can handle this action;
                # the path must be relative to the root of the image.
                self.attrs["path"] = misc.relpath(os.path.join(
                    pkgplan.image.get_license_dir(pkgplan.destination_fmri),
                    "license." + quote(self.attrs["license"], "")),
                    pkgplan.image.get_root())

        def install(self, pkgplan, orig):
                """Client-side method that installs the license."""
                owner = 0
                group = 0

                # ensure "path" is initialized.  it may not be if we've loaded
                # a plan that was previously prepared.
                self.preinstall(pkgplan, orig)

                stream = self.data()

                path = self.get_installed_path(pkgplan.image.get_root())

                # make sure the directory exists and the file is writable
                if not os.path.exists(os.path.dirname(path)):
                        self.makedirs(os.path.dirname(path),
                            mode=misc.PKG_DIR_MODE,
                            fmri=pkgplan.destination_fmri)
                elif os.path.exists(path):
                        os.chmod(path, misc.PKG_FILE_MODE)

                lfile = open(path, "wb")
                try:
                        hash_attr, hash_val, hash_func = \
                            digest.get_preferred_hash(self)
                        shasum = misc.gunzip_from_stream(stream, lfile,
                            hash_func=hash_func)
                except zlib.error as e:
                        raise ActionExecutionError(self, details=_("Error "
                            "decompressing payload: {0}").format(
                            " ".join([str(a) for a in e.args])), error=e)
                finally:
                        lfile.close()
                        stream.close()

                if shasum != hash_val:
                        raise ActionExecutionError(self, details=_("Action "
                            "data hash verification failure: expected: "
                            "{expected} computed: {actual} action: "
                            "{action}").format(
                                expected=hash_val,
                                actual=shasum,
                                action=self
                           ))

                os.chmod(path, misc.PKG_RO_FILE_MODE)

                try:
                        portable.chown(path, owner, group)
                except OSError as e:
                        if e.errno != errno.EPERM:
                                raise

        def needsdata(self, orig, pkgplan):
                # We always want to download the license
                return True

        def verify(self, img, pfmri, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image."""

                errors = []
                warnings = []
                info = []

                path = os.path.join(img.get_license_dir(pfmri),
                    "license." + quote(self.attrs["license"], ""))

                hash_attr, hash_val, hash_func = \
                    digest.get_preferred_hash(self)
                if args["forever"] == True:
                        try:
                                chash, cdata = misc.get_data_digest(path,
                                    hash_func=hash_func)
                        except EnvironmentError as e:
                                if e.errno == errno.ENOENT:
                                        errors.append(_("License file {0} does "
                                            "not exist.").format(path))
                                        return errors, warnings, info
                                raise

                        if chash != hash_val:
                                errors.append(_("Hash: '{found}' should be "
                                    "'{expected}'").format(found=chash,
                                    expected=hash_val))
                return errors, warnings, info

        def remove(self, pkgplan):
                path = os.path.join(
                    pkgplan.image.get_license_dir(pkgplan.origin_fmri),
                    "license." + quote(self.attrs["license"], ""))

                try:
                        # Make file writable so it can be deleted
                        os.chmod(path, S_IWRITE|S_IREAD)
                        os.unlink(path)
                except OSError as e:
                        if e.errno != errno.ENOENT:
                                raise

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                indices = [("license", idx, self.attrs[idx], None)
                           for idx in self.reverse_indices]
                if hasattr(self, "hash"):
                        indices.append(("license", "hash", self.hash, None))
                        indices.append(("license", "content", self.hash, None))
                for attr in digest.DEFAULT_HASH_ATTRS:
                        # we already have an index entry for self.hash
                        if attr == "hash":
                                continue
                        hash = self.attrs[attr]
                        indices.append(("license", attr, hash, None))
                return indices

        def get_text(self, img, pfmri, alt_pub=None):
                """Retrieves and returns the payload of the license (which
                should be text).  This may require remote retrieval of
                resources and so this could raise a TransportError or other
                ApiException.

                'alt_pub' is an optional alternate Publisher to use for
                any required transport operations.
                """

                path = self.get_local_path(img, pfmri)
                hash_attr, hash_attr_val, hash_func = \
                    digest.get_least_preferred_hash(self)
                try:
                        with open(path, "rb") as fh:
                                length = os.stat(path).st_size
                                chash, txt = misc.get_data_digest(fh,
                                    length=length, return_content=True,
                                    hash_func=hash_func)
                                if chash == hash_attr_val:
                                        return misc.force_str(txt)
                except EnvironmentError as e:
                        if e.errno != errno.ENOENT:
                                raise
                # If we get here, either the license file wasn't on disk, or the
                # hash didn't match.  In either case, go retrieve it from the
                # publisher.
                try:
                        if not alt_pub:
                                alt_pub = img.get_publisher(pfmri.publisher)
                        assert pfmri.publisher == alt_pub.prefix
                        return img.transport.get_content(alt_pub, hash_attr_val,
                            fmri=pfmri, hash_func=hash_func)
                finally:
                        img.cleanup_downloads()

        def get_local_path(self, img, pfmri):
                """Return an opener for the license text from the local disk or
                None if the data for the text is not on-disk."""

                if img.version <= 3:
                        # Older images stored licenses without accounting for
                        # '/', spaces, etc. properly.
                        path = os.path.join(img.get_license_dir(pfmri),
                            "license." + self.attrs["license"])
                else:
                        # Newer images ensure licenses are stored with encoded
                        # name so that '/', spaces, etc. are properly handled.
                        path = os.path.join(img.get_license_dir(pfmri),
                            "license." + quote(self.attrs["license"],
                            ""))
                return path

        @property
        def must_accept(self):
                """Returns a boolean value indicating whether this license
                action requires acceptance of its payload by clients."""

                return self.attrs.get("must-accept", "").lower() == "true"

        @property
        def must_display(self):
                """Returns a boolean value indicating whether this license
                action requires its payload to be displayed by clients."""

                return self.attrs.get("must-display", "").lower() == "true"

        def validate(self, fmri=None):
                """Performs additional validation of action attributes that
                for performance or other reasons cannot or should not be done
                during Action object creation.  An ActionError exception (or
                subclass of) will be raised if any attributes are not valid.
                This is primarily intended for use during publication or during
                error handling to provide additional diagonostics.

                'fmri' is an optional package FMRI (object or string) indicating
                what package contained this action."""

                generic.Action._validate(self, fmri=fmri,
                    numeric_attrs=("pkg.csize", "pkg.size"),
                    single_attrs=("chash", "must-accept", "must-display"))
