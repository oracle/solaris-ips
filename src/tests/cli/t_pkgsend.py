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
import shutil
import tempfile
import unittest

class TestPkgsendBasics(testutils.SingleDepotTestCase):
        persistent_depot = False

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
                        # Should fail because type attribute is missing.
                        self.pkgsend(url,
                            "add depend fmri=foo@1.0", exit=1)

                        # Should fail because type attribute is invalid.
                        self.pkgsend(url,
                            "add depend type=unknown fmri=foo@1.0", exit=1)

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

                # Should fail because repository does not exist.
                self.pkgsend(dfurl + "junk", "open foo@1.a", exit=1)

        def test_6_help(self):
                """Verify that help works as expected."""

                self.pkgsend(command="-?")
                self.pkgsend(command="--help")

                self.pkgsend(command="-? bobcat")
                self.pkgsend(command="--help bobcat")

                # Specifying no commands should result in usage error.
                self.pkgsend(exit=2)

        def test_7_create_repo(self):
                """Verify that create-repository works as expected."""

                self.dc.stop()
                rpath = os.path.join(self.get_test_prefix(), "example_repo")
                self.pkgsend("file://%s" % rpath, "create-repository")

                # Now verify that the repository was created by starting the
                # depot server in readonly mode using the target repository.
                # If it wasn't, restart_depots should fail with an exception
                # since the depot process will exit with a non-zero return
                # code.
                self.dc.set_repodir(rpath)
                self.dc.set_readonly()
                self.dc.start()

                # Now verify that creation of a repository is rejected for all
                # schemes execpt file://.
                self.pkgsend("http://invalid.test1", "create-repository", exit=1)
                self.pkgsend("https://invalid.test2", "create-repository", exit=1)

                # Finally, verify that specifying extra operands to
                # create-repository fails as expected.
                self.pkgsend("https://invalid.test2", "create-repository bobcat", exit=2)

        def test_8_bug_7908(self):
                """Verify that when provided the name of a symbolic link to a
                file, that publishing will still work as expected."""

                # First create our dummy data file.
                fd, fpath = tempfile.mkstemp(dir=self.get_test_prefix())
                fp = os.fdopen(fd, "wb")
                fp.write("foo")
                fp.close()

                # Then, create a link to it.
                lpath = os.path.join(self.get_test_prefix(), "test_8_foo")
                os.symlink(fpath, lpath)

                # Next, publish it using both the real path and the linked path
                # but using different names.
                dhurl = self.dc.get_depot_url()
                self.pkgsend_bulk(dhurl,
                    """open testlinkedfile@1.0
                    add file %s mode=0755 owner=root group=bin path=/tmp/f.foo
                    add file %s mode=0755 owner=root group=bin path=/tmp/l.foo
                    close""" % (fpath, lpath))

                # Finally, verify that both files were published.
                self.image_create(dhurl)
                self.pkg("contents -r -H -o action.raw -t file testlinkedfile |"
                   " grep 'f.foo.*pkg.size=3'")
                self.pkg("contents -r -H -o action.raw -t file testlinkedfile |"
                   " grep 'l.foo.*pkg.size=3'")
                self.image_destroy()

        def test_9_multiple_dirs(self):
                rootdir = self.get_test_prefix()
                dir_1 = os.path.join(rootdir, "dir_1")
                dir_2 = os.path.join(rootdir, "dir_2")
                os.mkdir(dir_1)
                os.mkdir(dir_2)
                file(os.path.join(dir_1, "A"), "wb").close()
                file(os.path.join(dir_2, "B"), "wb").close()
                mfpath = os.path.join(rootdir, "manifest_test")
                mf = file(mfpath, "w")
                # test omission of set action by having illegal fmri value
                mf.write("""file NOHASH mode=0755 owner=root group=bin path=/A
                    file NOHASH mode=0755 owner=root group=bin path=/B
                    set name="fmri" value="totally_bogus"
                    """)
                mf.close()
                dhurl = self.dc.get_depot_url()
                self.pkgsend(dhurl,
                    """publish -d %s -d %s testmultipledirs@1.0 < %s"""
                    % (dir_1, dir_2, mfpath))
                self.image_create(dhurl)
                self.pkg("install testmultipledirs")
                self.pkg("verify")
                self.image_destroy()

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

                self.pkg("refresh")
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

                self.pkg("refresh")
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
