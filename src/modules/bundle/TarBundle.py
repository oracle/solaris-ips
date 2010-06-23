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
# Copyright (c) 2007, 2010, Oracle and/or its affiliates. All rights reserved.
#

import os
import stat
import tarfile
import pkg.misc as misc
from pkg.actions import *

class TarBundle(object):

        def __init__(self, filename, targetpaths=()):
                self.tf = tarfile.open(filename)
                # XXX This could be more intelligent.  Or get user input.  Or
                # extend API to take FMRI.
                self.pkgname = os.path.basename(filename)

        def __del__(self):
                self.tf.close()

        def __iter__(self):
                for f in self.tf:
                        yield self.action(self.tf, f)

        def action(self, tarfile, tarinfo):
                if tarinfo.isreg():
                        return file.FileAction(tarfile.extractfile(tarinfo),
                            mode=oct(stat.S_IMODE(tarinfo.mode)),
                            owner=tarinfo.uname, group=tarinfo.gname,
                            path=tarinfo.name,
                            timestamp=misc.time_to_timestamp(tarinfo.mtime))
                elif tarinfo.isdir():
                        return directory.DirectoryAction(
                            mode=oct(stat.S_IMODE(tarinfo.mode)),
                            owner=tarinfo.uname, group=tarinfo.gname,
                            path=tarinfo.name)
                elif tarinfo.issym():
                        return link.LinkAction(path=tarinfo.name,
                            target=tarinfo.linkname)
                elif tarinfo.islnk():
                        return hardlink.HardLinkAction(path=tarinfo.name,
                            target=tarinfo.linkname)
                else:
                        return unknown.UnknownAction(path=tarinfo.name)

def test(filename):
        return tarfile.is_tarfile(filename)
