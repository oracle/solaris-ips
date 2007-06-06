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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import stat
import tarfile
import tempfile

class TarBundle(object):

        def __init__(self, filename):
                self.tf = tarfile.open(filename)
                # XXX This could be more intelligent.  Or get user input.
                self.pkgname = os.path.basename(filename)

        def __del__(self):
                self.tf.close()

        def __iter__(self):
                for f in self.tf:
                        yield TarBundleFile(self.tf, f)

def test(filename):
        try:
                return tarfile.is_tarfile(filename)
        except:
                return False

# XXX Make this a private class to TarBundle?
class TarBundleFile(object):

        def __init__(self, tarfile, tarinfo):

                if tarinfo.isreg():
                        (inf, self.tmpfile) = tempfile.mkstemp("", "pkg-tar.")

                        f = tarfile.extractfile(tarinfo)
                        while True:
                                buf = f.read(8192)
                                if not buf:
                                        break
                                os.write(inf, buf)

                        os.close(inf)

                        self.type = "file"
                        self.attrs = {
                                # Get rid of the S_IFXXX bits
                                "mode": oct(stat.S_IMODE(tarinfo.mode)),
                                "owner": tarinfo.uname,
                                "group": tarinfo.gname,
                                "path": tarinfo.name,
                                "file": self.tmpfile
                        }

                elif tarinfo.isdir():
                        self.type = "dir"
                        self.attrs = {
                                # Get rid of the S_IFXXX bits
                                "mode": oct(stat.S_IMODE(tarinfo.mode)),
                                "owner": tarinfo.uname,
                                "group": tarinfo.gname,
                                "path": tarinfo.name,
                        }

        def __del__(self):
                if "tmpfile" in dir(self):
                        os.remove(self.tmpfile)
