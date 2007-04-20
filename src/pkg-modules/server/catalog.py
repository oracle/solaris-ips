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

import os
import re
import sha
import shutil
import time
import urllib

import pkg.fmri as fmri

class SCatalog(object):
        """An SCatalog is the server's representation of the available package
        catalog in this repository.

        XXX Does the catalog contain the incorporated relationships?  Maybe the
        catalolog is the inventory and the statements of incorporations."""

        def __init__(self):
                self.pkgs = {}
                self.relns = {}
                return

        def update_entry(self, pkg):
                return

        def __str__(self):
                s = ""
                for p in pkgs:
                        s = s + "%s" % p
                for r in self.relns:
                        s = s + "%s" % r
                return s


