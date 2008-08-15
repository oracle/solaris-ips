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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#
#ident	"%Z%%M%	%I%	%E% SMI"

import sys
import struct
import gzip

def out32u(outf, val):
        outf.write(struct.pack("<L", val))

class PkgGzipFile(gzip.GzipFile):
        """This is a version of GzipFile that does not include a file
        pathname or timestamp in the gzip header.  This allows us to get
        deterministic gzip files on compression, so that we can reliably
        use a cryptopgraphic hash on the compressed content."""

        def __init__(self, filename=None, mode=None, compresslevel=9,
            fileobj=None):

               gzip.GzipFile.__init__(self, filename, mode, compresslevel,
                    fileobj) 

        def _write_gzip_header(self):
                self.fileobj.write("\037\213")
                self.fileobj.write("\010")
                self.fileobj.write(chr(0))
                out32u(self.fileobj, long(0))
                self.fileobj.write("\002")
                self.fileobj.write("\377")
