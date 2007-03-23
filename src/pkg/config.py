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

# Client configuration

class ParentRepo(object):
        """Client configuration object.  Install repo URI (optional) Repository
           upon which we commit transactions.  URL list of repos, in order of
           preference.

           XXX Need a local filter policy.  One filter example would be to only
           install 32-bit binaries."""
        def __init__(self, install_uri, repo_uris):
                self.install_uri = install_uri
                self.repo_uris = repo_uris

# Server configuration

class SvrConfig(object):
        """Server configuration object.  Repository location."""
        def __init__(self, repo_root):
                self.repo_root = repo_root

