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

import os
import stat
import tarfile
# Without the below statements, tarfile will trigger calls to getpwuid
# and getgrgid for every file extracted.  This in turn leads to nscd
# usage which slows down the install phase.  Setting these attributes
# to undefined causes tarfile to skip these calls in
# tarfile.gettarinfo().  This information is unnecesary as it will not
# be used by the client.
tarfile.pwd = None
tarfile.grp = None

class PkgTarFile(tarfile.TarFile):
        """PkgTarFile is a subclass of TarFile.  It implements
        a small number of additional instance methods to improve
        the functionality of the TarFile class for the packaging classes.

        XXX - Push these changes upstream to Python maintainers?
        """

        def __init__(self, *args, **kwargs):
                kwargs.setdefault("errorlevel", 2)
                tarfile.TarFile.__init__(self, *args, **kwargs)

        def extract_to(self, member, path="", filename=""):
                """Extract a member from the TarFile archive.  This
                method allows you to specify a new filename and path, using
                the filename and path arguments, where the file will be
                extracted.  This method is similar to extract().
                Extract() only allows the caller to prepend a directory path
                to the filename specified in the TarInfo object,
                whereas this method allows the caller to additionally
                specify a file name.
                """

                self._check("r")

                if isinstance(member, tarfile.TarInfo):
                        tarinfo = member
                else:
                        tarinfo = self.getmember(member)

                if tarinfo.islnk():
                        tarinfo._link_target = \
                            os.path.join(path, tarinfo.linkname)

                if not filename:
                        filename = tarinfo.name


                upperdirs = os.path.dirname(os.path.join(path, filename))

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
                        self._extract_member(tarinfo, os.path.join(
                            path, filename))
                except EnvironmentError as e:
                        if self.errorlevel > 0:
                                raise
                        else:
                                if e.filename is None:
                                        self._dbg(1, "tarfile {0}".format(
                                            e.strerror))
                                else:
                                        self._dbg(1,
                                            "tarfile: {0} {1!r}".format(
                                            e.strerror, e.filename))
                except tarfile.ExtractError as e:
                        if self.errorlevel > 1:
                                raise
                        else:
                                self._dbg(1, "tarfile: {0}".format(e))
