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

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#
#ident	"%Z%%M%	%I%	%E% SMI"

hash_prefix_length = 4
def hash_file_name(f):
        """Return the two-level path fragment for the given filename, which is
        assumed to be a content hash of at least 8 distinct characters."""
        return "%s/%s/%s" % (f[0:hash_prefix_length],
            f[hash_prefix_length:2 * hash_prefix_length], f)

if __name__ == "__main__":
        print hash_file_name("abcdefghijklmnopqrstuvwxyz")
