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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#
#ident	"%Z%%M%	%I%	%E% SMI"

import gzip

class PkgGzipFile(gzip.GzipFile):
        """This is a version of GzipFile that does not include a file
        pathname or timestamp in the gzip header.  This allows us to get
        deterministic gzip files on compression, so that we can reliably
        use a cryptographic hash on the compressed content."""

        def __init__(self, filename=None, mode=None, compresslevel=9,
            fileobj=None):

               gzip.GzipFile.__init__(self, filename, mode, compresslevel,
                    fileobj) 

        #
        # This is a gzip header conforming to RFC1952.  The first two bytes
        # (\037,\213) are the gzip magic number.  The third byte is the
        # compression method (8, deflate).  The fourth byte is the flag byte
        # (0), which indicates that no FNAME, FCOMMENT or other extended data
        # is present.  Bytes 5-8 are the MTIME field, zeroed in this case.
        # Byte 9 is the XFL (Extra Flags) field, set to 2 (compressor used
        # max compression).  The final bit is the OS type, set to 255 (for
        # "unknown").
        magic = b"\037\213\010\000\000\000\000\000\002\377"

        def _write_gzip_header(self):
                self.fileobj.write(self.magic)

        @staticmethod
        def test_is_pkggzipfile(path):
                f = open(path, "rb")
                hdrstr = f.read(len(PkgGzipFile.magic))
                f.close()
                return (hdrstr == PkgGzipFile.magic)
