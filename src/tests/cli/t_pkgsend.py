#!/usr/bin/python2.4
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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import unittest

class TestPkgsendBasics(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        def test_0_pkgsend_bad_opts(self):
                """Verify that non-existent or invalid option combinations
                cannot be specified."""

                durl = self.dc.get_depot_url()
                self.pkgsend(durl, "-@ open foo@1.0,5.11-0", exit=2)
                self.pkgsend(durl, "close -@", exit=2)

                # The -e and -n options are opposites and cannot be combined.
                self.pkgsend(durl, "open -en foo@1.0", exit=2)
                self.pkgsend(durl, "open -ne foo@1.0", exit=2)

        def test_1_pkgsend_abandon(self):
                """Verify that an abandoned tranasaction is not published."""

                dhurl = self.dc.get_depot_url()
                dfurl = "file://%s" % self.dc.get_repodir()

                for url in (dhurl, dfurl):
                        self.pkgsend_bulk(url,
                            """open shouldnotexist@1.0,5.11-0
                            add dir mode=0755 owner=root group=bin path=/bin
                            close -A""")

                        if url == dfurl:
                                # Must restart pkg.depotd so it will pickup the
                                # changes to the catalog.
                                self.restart_depots()

                        # For now, the pkg(1) client only supports http, so use
                        # the http url always.
                        self.image_create(dhurl)
                        self.pkg("list -a shouldnotexist", exit=1)
                        self.image_destroy()

        def test_2_invalid_url(self):
                """Verify that an invalid repository URL will result in an
                error."""

                # Verify that specifying a malformed or incomplete URL fails
                # gracefully for every known scheme and a few bogus schemes.
                for scheme in ("bogus", "file", "http", "https", "null"):
                        # The first two cases should succeed for 'null'
                        self.pkgsend(scheme + "://", "open notarepo@1.0",
                            exit=scheme != "null")
                        self.pkgsend(scheme + ":", "open notarepo@1.0",
                            exit=scheme != "null")
                        self.pkgsend(scheme, "open notarepo@1.0", exit=1)

                # Create an empty directory to abuse as a repository.
                junk_repo = os.path.join(self.get_test_prefix(), "junk-repo")
                os.makedirs(junk_repo, 0755)

                # Point at a valid directory that does not contain a repository.
                dfurl = "file://" + junk_repo

                # Verify that specifying a non-existent directory for a file://
                # repository fails gracefully.
                self.pkgsend(os.path.join(dfurl, "nochance"),
                    "open nosuchdir@1.0", exit=1)

                # Verify that specifying a directory that is not a file://
                # repository fails gracefully.
                self.pkgsend(dfurl, "open notarepo@1.0", exit=1)

                # Point at a non-existent http(s) repository; port 1 is an
                # unassigned port that nothing should use.
                dhurl = "http://localhost:1"
                dshurl = "http://localhost:1"

                # Verify that specifying a non-existent (i.e. unable to connect
                # to) http:// repository fails gracefully.
                self.pkgsend(dhurl, "open nosuchdir@1.0", exit=1)
                self.pkgsend(dshurl, "open nosuchdir@1.0", exit=1)

        def test_3_bad_transaction(self):
                """Verify that invalid Transaction IDs are handled correctly."""

                dhurl = self.dc.get_depot_url()
                dfurl = "file://%s" % self.dc.get_repodir()

                os.environ["PKG_TRANS_ID"] = "foobarbaz"

                for url in (dfurl, dhurl):
                        self.pkgsend(url, "add file /bin/ls path=/bin/ls",
                            exit=1)

        def test_4_bad_actions(self):
                """Verify that malformed or invalid actions are handled
                correctly.  This only checks a few cases as the pkg.action
                class itself should be handling the actual verification;
                the client just needs to handle the appropriate exceptions
                gracefully."""

                dhurl = self.dc.get_depot_url()
                dfurl = "file://%s" % self.dc.get_repodir()
                test_dir = self.get_test_prefix()
                imaginary_file = os.path.join(test_dir, "imaginary_file")

                # Must open transaction using HTTP url first so that transaction
                # will be seen by the depot server and when using file://.
                self.pkgsend(dhurl, "open foo@1.0")

                for url in (dhurl, dfurl):
                        # Should fail because path attribute is missing.
                        self.pkgsend(url,
                            "add file /bin/ls", exit=1)

                        # Should fail because path attribute is missing a value.
                        self.pkgsend(url,
                            "add file /bin/ls path=", exit=1)

                        # Should fail because the file does not exist.
                        self.pkgsend(url,
                            "add file %s path=/bin/ls" % imaginary_file, exit=1)

                        # Should fail because path=/bin/ls will be interpreted
                        # as the filename and is not a valid file.
                        self.pkgsend(url,
                            "add file path=/bin/ls", exit=1)

                        # Should fail because the action is unknown.
                        self.pkgsend(url,
                            "add bogusaction", exit=1)

        def test_5_bad_open(self):
                """Verify that a bad open is handled properly.  This could be
                because of an invalid FMRI that was specified, or many other
                reasons."""

                dhurl = self.dc.get_depot_url()
                dfurl = "file://%s" % self.dc.get_repodir()

                for url in (dhurl, dfurl):
                        # Should fail because no fmri was specified.
                        self.pkgsend(url, "open", exit=2)

                        # Should fail because an invalid fmri was specified.
                        self.pkgsend(url, "open foo@1.a", exit=1)

class TestPkgsendRename(testutils.SingleDepotTestCase):

        def test_rename1(self):
                """ Test some ways in which we expect rename to fail """
                durl = self.dc.get_depot_url()
                # Not in catalog
                self.pkgsend(durl, "rename foo@1.1,5.11-0 bar@1.0,5.11-0",
                    exit=1)

                self.pkgsend(durl, "open foo@1.0,5.11-0")
                self.pkgsend(durl, "close")

                # Dest. not in catalog
                self.pkgsend(durl, "rename foo@1.1,5.11-0 bar@1.0,5.11-0",
                    exit=1)

                self.pkgsend(durl, "open bar@1.0,5.11-0")
                self.pkgsend(durl, "close")

                # Build string missing in source, then in dest, then both
                self.pkgsend(durl, "rename foo@1.1 bar@1.0,5.11-0", exit=1)
                self.pkgsend(durl, "rename foo@1.1,5.11-0 bar@1.0", exit=1)
                self.pkgsend(durl, "rename foo@1.1 bar@1.0", exit=1)

                # Source must not already be in catalog.
                self.pkgsend(durl, "rename foo@1.0,5.11-0 bar@1.0,5.11-0",
                    exit=1)

        def test_rename2(self):
                """ Basic rename """
                durl = self.dc.get_depot_url()

                self.pkgsend(durl, "open foo@1.0,5.11-0")
                self.pkgsend(durl, "close")

                self.image_create(durl)
                self.pkg("install foo")
                self.pkg("verify")

                self.pkgsend(durl, "open bar@1.0,5.11-0")
                self.pkgsend(durl, "close")

                self.pkgsend(durl, "rename foo@1.1,5.11-0 bar@1.0,5.11-0")

                self.pkg("install bar")
                self.pkg("verify")

                self.pkg("list foo", exit=1)
                self.pkg("list bar", exit=0)

        def test_rename3(self):
                """ Rename to pkg previously opened without a build string """
                durl = self.dc.get_depot_url()

                self.pkgsend(durl, "open foo@1.0,5.11-0")
                self.pkgsend(durl, "close")

                self.pkgsend(durl, "open bar@1.0")
                self.pkgsend(durl, "close")

                self.pkgsend(durl, "rename foo@1.0,5.11-0 bar@1.0,5.11-0",
                    exit=1)

        def test_rename4(self):
                """ Rename package and verify dependencies.

                    Send package rar@1.0, dependent on moo@1.1.
                    Rename moo to zoo.
                    Install zoo and then rar.  Verify that zoo satisfied
                    dependency for moo.
                """

                # Send 1.0 versions of packages.
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkgsend(durl, "open moo@1.1,5.11-0")
                self.pkgsend(durl, "close")

                self.pkgsend(durl, "open zoo@1.0,5.11-0")
                self.pkgsend(durl, "close")
                self.pkgsend(durl, "rename moo@1.2,5.11-0 zoo@1.0,5.11-0")

                self.pkgsend(durl, "open rar@1.0")
                self.pkgsend(durl, "add depend type=require fmri=pkg:/moo@1.1")
                self.pkgsend(durl, "close")

                self.pkg("refresh")
                self.pkg("list -aH")
                self.pkg("install -v zoo")
                self.pkg("install -v rar")

                # Check that zoo and rar were installed
                self.pkg("list zoo")
                self.pkg("list rar")

                # Check that moo was not installed
                self.pkg("list moo", exit=1)

                self.pkg("verify")

                self.pkg("uninstall rar zoo")
                self.pkg("verify")

class TestPkgsendRenameFile(testutils.SingleDepotTestCase):

        def test_rename1(self):
                """ Test some ways in which we expect rename to fail """
                dfurl = "file://%s" % self.dc.get_repodir()

                # Not in catalog
                self.pkgsend(dfurl, "rename foo@1.1,5.11-0 bar@1.0,5.11-0",
                    exit=1)

                self.pkgsend(dfurl, "open foo@1.0,5.11-0")
                self.pkgsend(dfurl, "close")

                # Dest. not in catalog
                self.pkgsend(dfurl, "rename foo@1.1,5.11-0 bar@1.0,5.11-0",
                    exit=1)

                self.pkgsend(dfurl, "open bar@1.0,5.11-0")
                self.pkgsend(dfurl, "close")

                # Build string missing in source, then in dest, then both
                self.pkgsend(dfurl, "rename foo@1.1 bar@1.0,5.11-0", exit=1)
                self.pkgsend(dfurl, "rename foo@1.1,5.11-0 bar@1.0", exit=1)
                self.pkgsend(dfurl, "rename foo@1.1 bar@1.0", exit=1)

                # Source must not already be in catalog.
                self.pkgsend(dfurl, "rename foo@1.0,5.11-0 bar@1.0,5.11-0",
                    exit=1)

        def test_rename2(self):
                """ Basic rename """
                dfurl = "file://%s" % self.dc.get_repodir()
                dhurl = self.dc.get_depot_url()

                self.pkgsend(dfurl, "open foo@1.0,5.11-0")
                self.pkgsend(dfurl, "close")

                # Must restart pkg.depotd so it will pickup the changes to the
                # catalog.
                self.restart_depots()

                self.image_create(dhurl)
                self.pkg("install foo")
                self.pkg("verify")

                self.pkgsend(dfurl, "open bar@1.0,5.11-0")
                self.pkgsend(dfurl, "close")

                self.pkgsend(dfurl, "rename foo@1.1,5.11-0 bar@1.0,5.11-0")

                # Must restart pkg.depotd so it will pickup the changes to the
                # catalog.
                self.restart_depots()


                self.pkg("install bar")
                self.pkg("verify")

                self.pkg("list foo", exit=1)
                self.pkg("list bar", exit=0)

        def test_rename3(self):
                """ Rename to pkg previously opened without a build string """
                dfurl = "file://%s" % self.dc.get_repodir()

                self.pkgsend(dfurl, "open foo@1.0,5.11-0")
                self.pkgsend(dfurl, "close")

                self.pkgsend(dfurl, "open bar@1.0")
                self.pkgsend(dfurl, "close")

                self.pkgsend(dfurl, "rename foo@1.0,5.11-0 bar@1.0,5.11-0",
                    exit=1)

        def test_rename4(self):
                """ Rename package and verify dependencies.

                    Send package rar@1.0, dependent on moo@1.1.
                    Rename moo to zoo.
                    Install zoo and then rar.  Verify that zoo satisfied
                    dependency for moo.
                """

                # Send 1.0 versions of packages.
                dfurl = "file://%s" % self.dc.get_repodir()
                dhurl = self.dc.get_depot_url()

                self.pkgsend(dfurl, "open moo@1.1,5.11-0")
                self.pkgsend(dfurl, "close")

                self.pkgsend(dfurl, "open zoo@1.0,5.11-0")
                self.pkgsend(dfurl, "close")
                self.pkgsend(dfurl, "rename moo@1.2,5.11-0 zoo@1.0,5.11-0")

                self.pkgsend(dfurl, "open rar@1.0")
                self.pkgsend(dfurl, "add depend type=require fmri=pkg:/moo@1.1")
                self.pkgsend(dfurl, "close")

                # Must restart pkg.depotd so it will pickup the changes to the
                # catalog.
                self.restart_depots()

                self.image_create(dhurl)
                self.pkg("refresh")
                self.pkg("list -aH")
                self.pkg("install -v zoo")
                self.pkg("install -v rar")

                # Check that zoo and rar were installed
                self.pkg("list zoo")
                self.pkg("list rar")

                # Check that moo was not installed
                self.pkg("list moo", exit=1)

                self.pkg("verify")

                self.pkg("uninstall rar zoo")
                self.pkg("verify")


if __name__ == "__main__":
        unittest.main()
