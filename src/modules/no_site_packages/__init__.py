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
# Copyright (c) 2019, Oracle and/or its affiliates. All rights reserved.
#

"""Remove site-packages directories from sys.path.
This provides a stable execution platform for core Solaris commands.
Only do this on Solaris since on any other platform pkg is likely installed
in the system site-packages area."""

import sys

if sys.platform == "sunos5":
    from site import getsitepackages as getsitepackages

    pkglist = getsitepackages()
    sys.path = [ d for d in sys.path if d not in pkglist ]
