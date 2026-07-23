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
# Copyright (c) 2007, 2026, Oracle and/or its affiliates.
#

import copy
import os
import stat
import tarfile
# Without the below statements, tarfile will trigger calls to getpwuid
# and getgrgid for every file extracted.  This in turn leads to nscd
# usage which slows down the install phase.  Setting these attributes
# to undefined causes tarfile to skip these calls in
# tarfile.gettarinfo().  This information is unnecessary as it will not
# be used by the client.
tarfile.pwd = None
tarfile.grp = None


class PkgTarFile(tarfile.TarFile):
    """PkgTarFile extends the standard TarFile class with methods better
    suited for the packaging classes, and uses a stricter errorlevel by
    default.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("errorlevel", 2)
        tarfile.TarFile.__init__(self, *args, **kwargs)

    def extract_to(self, member, path="", filename=None):
        """Extract a member from the TarFile archive.

        This method is similar to extract(), but allows the caller to
        change the final file name.  It also creates missing parent
        directories with a safer mode.
        """

        self._check("r")

        if isinstance(member, tarfile.TarInfo):
            tarinfo = member
        else:
            tarinfo = self.getmember(member)

        if filename:
            # Rename the extracted file if a new filename was given.
            tarinfo = copy.copy(tarinfo)
            tarinfo.name = filename

        # Always use the most restrictive standard 'data' filter.
        filter_function = tarfile.data_filter
        filtered, _ = self._get_extract_tarinfo(tarinfo, filter_function, path)
        if filtered is None:
            return

        upperdirs = os.path.dirname(os.path.join(path, filtered.name))
        if upperdirs and not os.path.exists(upperdirs):
            # The tarfile we receive contains only files, and none
            # of the containing directories.  The tarfile code will
            # create the directories as necessary, but with mode
            # 777, which is insuffficiently secure.  Thus we create
            # these directories in advance with tighter permissions;
            # they'll be fixed up later, when the action execute
            # methods run.  If proper directory actions
            # don't exist for these directories, the permissions
            # will be wrong.
            try:
                os.makedirs(upperdirs, stat.S_IRWXU)
            except EnvironmentError:
                pass
        try:
            self._extract_member(filtered, os.path.join(path, filtered.name),
                                 filter_function=filter_function,
                                 extraction_root=path)
        except (OSError, UnicodeEncodeError) as e:
            self._handle_fatal_error(e)
        except tarfile.ExtractError as e:
            self._handle_nonfatal_error(e)
