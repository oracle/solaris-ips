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

# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import difflib
import os
import re
import shutil
import tempfile
import unittest

import pkg.catalog as catalog
import pkg.misc


class TestPkgRefreshMulti(pkg5unittest.ManyDepotTestCase):

        # Tests in this suite use the read only data directory.
        need_ro_data = True

        foo1 = """
            open foo@1,5.11-0
            close """

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo11 = """
            open foo@1.1,5.11-0
            close """

        foo12 = """
            open foo@1.2,5.11-0
            close """

        foo121 = """
            open foo@1.2.1,5.11-0
            close """

        food12 = """
            open food@1.2,5.11-0
            close """

        def setUp(self):
                # This test suite needs actual depots.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test1", "test1"], start_depots=True)

                self.durl1 = self.dcs[1].get_depot_url()
                self.durl2 = self.dcs[2].get_depot_url()
                self.durl3 = self.dcs[3].get_depot_url()

                # An empty repository for test1 to enable metadata tests
                # to continue to work as expected.
                self.durl4 = self.dcs[4].get_depot_url()

        def reduce_spaces(self, string):
                """Reduce runs of spaces down to a single space."""
                return re.sub(" +", " ", string)

        def assert_equal_diff(self, expected, actual):
                self.assertEqual(expected, actual,
                    "Actual output differed from expected output.\n" +
                    "\n".join(difflib.unified_diff(
                        expected.splitlines(), actual.splitlines(),
                        "Expected output", "Actual output", lineterm="")))

        def get_op_entries(self, dc, op, op_ver, method="GET"):
                """Scan logpath for a specific depotcontroller looking for
                access log entries for an operation.  Returns a list of request
                URIs for each log entry found for the operation in chronological
                order."""

                # 127.0.0.1 - - [15/Oct/2009:00:15:38]
                # "GET [/<pub>]/catalog/1/catalog.base.C HTTP/1.1" 200 189 ""
                # "pkg/b1f63b112bff+ (sunos i86pc; 5.11 snv_122; none; pkg)"
                entry_comps = [
                    r"(?P<host>\S+)",
                    r"\S+",
                    r"(?P<user>\S+)",
                    r"\[(?P<request_time>.+)\]",
                    r'"(?P<request>.+)"',
                    r"(?P<response_status>[0-9]+)",
                    r"(?P<content_length>\S+)",
                    r'"(?P<referer>.*)"',
                    r'"(?P<user_agent>.*)"',
                ]
                log_entry = re.compile(r"\s+".join(entry_comps) + r"\s*\Z")

                logpath = dc.get_logpath()
                self.debug("check for operation entries in %s" % logpath)
                logfile = open(logpath, "r")
                entries = []
                for line in logfile.readlines():
                        m = log_entry.search(line)
                        if not m:
                                continue

                        host, user, req_time, req, status, clen, ref, agent = \
                            m.groups()

                        req_method, uri, protocol = req.split(" ")
                        if req_method != method:
                                continue

                        # Strip publisher from URI for this part.
                        uri = uri.replace("/test1", "")
                        uri = uri.replace("/test2", "")
                        req_parts = uri.strip("/").split("/", 3)
                        if req_parts[0] != op:
                                continue

                        if req_parts[1] != op_ver:
                                continue
                        entries.append(uri)
                logfile.close()
                self.debug("Found %s for %s /%s/%s/" % (entries, method, op,
                    op_ver))
                return entries

        def _check(self, expected, actual):
                tmp_e = expected.splitlines()
                tmp_e.sort()
                tmp_a = actual.splitlines()
                tmp_a.sort()
                if tmp_e == tmp_a:
                        return True
                else:
                        self.assertEqual(tmp_e, tmp_a,
                            "Actual output differed from expected output.\n" +
                            "\n".join(difflib.unified_diff(
                                tmp_e, tmp_a,
                                "Expected output", "Actual output",
                                lineterm="")))

        def checkAnswer(self,expected, actual):
                return self._check(
                    self.reduce_spaces(expected),
                    self.reduce_spaces(actual))

 	def test_refresh_cli_options(self):
                """Test refresh and options."""

                durl = self.dcs[1].get_depot_url()
                self.image_create(durl, prefix="test1")

                self.pkg("refresh")
                self.pkg("refresh --full")
                self.pkg("refresh -F", exit=2)

        def test_general_refresh(self):
                self.image_create(self.durl1, prefix="test1")
                self.pkg("set-publisher -O " + self.durl2 + " test2")
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.pkgsend_bulk(self.durl2, self.foo12)

                # This should fail as the publisher was just updated seconds
                # ago, and not enough time has passed yet for the client to
                # contact the repository to check for updates.
                self.pkg("list -aH pkg:/foo", exit=1)

                # This should succeed as a full refresh was requested, which
                # ignores the update check interval the client normally uses
                # to determine whether or not to contact the repository to
                # check for updates.
                self.pkg("refresh --full")
                self.pkg("list -aH pkg:/foo")

                expected = \
                    "foo 1.0-0 ---\n" + \
                    "foo (test2) 1.2-0 ---\n"
                self.checkAnswer(expected, self.output)

        def test_specific_refresh(self):
                self.image_create(self.durl1, prefix="test1")
                self.pkg("set-publisher -O " + self.durl2 + " test2")
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.pkgsend_bulk(self.durl2, self.foo12)

                # This should fail since only a few seconds have passed since
                # the publisher's metadata was last checked, and so the catalog
                # will not yet reflect the last published package.
                self.pkg("list -aH pkg:/foo@1,5.11-0", exit=1)

                # This should succeed since a refresh is explicitly performed,
                # and so the catalog will reflect the last published package.
                self.pkg("refresh test1")
                self.pkg("list -aH pkg:/foo@1,5.11-0")

                expected = \
                    "foo 1.0-0 ---\n"
                self.checkAnswer(expected, self.output)

                # This should succeed since a refresh is explicitly performed,
                # and so the catalog will reflect the last published package.
                self.pkg("refresh test2")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.0-0 ---\n" + \
                    "foo (test2) 1.2-0 ---\n"
                self.checkAnswer(expected, self.output)
                self.pkg("refresh unknownAuth", exit=1)
                self.pkg("set-publisher -P test2")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo (test1) 1.0-0 ---\n" + \
                    "foo 1.2-0 ---\n"
                self.pkgsend_bulk(self.durl1, self.foo11)
                self.pkgsend_bulk(self.durl2, self.foo11)

                # This should succeed since an explicit refresh is performed,
                # and so the catalog will reflect the last published package.
                self.pkg("refresh test1 test2")
                self.pkg("list -aHf pkg:/foo")
                expected = \
                    "foo (test1) 1.0-0 ---\n" + \
                    "foo (test1) 1.1-0 ---\n" + \
                    "foo 1.1-0 ---\n" + \
                    "foo 1.2-0 ---\n"
                self.checkAnswer(expected, self.output)

        def test_set_publisher_induces_full_refresh(self):
                self.pkgsend_bulk(self.durl3, self.foo11)
                self.pkgsend_bulk(self.durl3, self.foo10)
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.pkgsend_bulk(self.durl2, self.foo11)
                self.image_create(self.durl1, prefix="test1")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.0-0 ---\n"
                self.checkAnswer(expected, self.output)

                # If a privileged user requests this, it should fail since
                # publisher metadata will have been refreshed, but it will
                # be the metadata from a repository that does not contain
                # any package metadata for this publisher.
                self.pkg("set-publisher -O " + self.durl4 + " test1")
                self.pkg("list --no-refresh -avH pkg:/foo@1.0", exit=1)
                self.pkg("list --no-refresh -avH pkg:/foo@1.1", exit=1)

                # If a privileged user requests this, it should succeed since
                # publisher metadata will have been refreshed, and contains
                # package data for the publisher.
                self.pkg("set-publisher -O " + self.durl3 + " test1")
                self.pkg("list --no-refresh -afH pkg:/foo")
                expected = \
                    "foo 1.0-0 ---\n" \
                    "foo 1.1-0 ---\n"
                self.checkAnswer(expected, self.output)

        def test_set_publisher_induces_delayed_full_refresh(self):
                self.pkgsend_bulk(self.durl3, self.foo11)
                self.pkgsend_bulk(self.durl2, self.foo11)
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.image_create(self.durl1, prefix="test1")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.0-0 ---\n"
                self.checkAnswer(expected, self.output)
                self.dcs[2].stop()
                self.pkg("set-publisher --no-refresh -O " + self.durl3 + " test1")
                self.dcs[2].start()

                # This should fail when listing all known packages, and running
                # as an unprivileged user since the publisher's metadata can't
                # be updated.
                self.pkg("list -aH pkg:/foo@1.1", su_wrap=True, exit=1)

                # This should fail when listing all known packages, and running
                # as a privileged user since --no-refresh was specified.
                self.pkg("list -aH --no-refresh pkg:/foo@1.1", exit=1)

                # This should succeed when listing all known packages, and
                # running as a privileged user since the publisher's metadata
                # will automatically be updated, and the repository contains
                # package data for the publisher.
                self.pkg("list -aH pkg:/foo@1.1")
                expected = \
                    "foo 1.1-0 ---\n"
                self.checkAnswer(expected, self.output)

                # This should fail when listing all known packages, and
                # running as a privileged user since the publisher's metadata
                # will automatically be updated, but the repository doesn't
                # contain any data for the publisher.
                self.dcs[2].stop()
                self.pkg("set-publisher -O " + self.durl1 + " test1")
                self.pkg("set-publisher --no-refresh -O " + self.durl2 + " test1")
                self.dcs[2].start()
                self.pkg("list -aH --no-refresh pkg:/foo@1.1", exit=1)

        def test_refresh_certificate_problems(self):
                """Verify that an invalid or inaccessible certificate does not
                cause unexpected failure."""

                self.image_create(self.durl1, prefix="test1")

                key_path = os.path.join(self.keys_dir, "cs1_ch1_ta3_key.pem")
                cert_path = os.path.join(self.cs_dir, "cs1_ch1_ta3_cert.pem")

                self.pkg("set-publisher --no-refresh -O https://%s1 test1" %
                    self.bogus_url)
                self.pkg("set-publisher --no-refresh -c %s test1" % cert_path)
                self.pkg("set-publisher --no-refresh -k %s test1" % key_path)


                img_key_path = os.path.join(self.img_path(), "var", "pkg",
                    "ssl", pkg.misc.get_data_digest(key_path)[0])
                img_cert_path = os.path.join(self.img_path(), "var", "pkg",
                    "ssl", pkg.misc.get_data_digest(cert_path)[0])

                # Make the cert/key unreadable by unprivileged users.
                os.chmod(img_key_path, 0000)
                os.chmod(img_cert_path, 0000)

                # Verify that an inaccessible certificate results in a normal
                # failure when attempting to refresh.
                self.pkg("refresh test1", su_wrap=True, exit=1)

                # Verify that an invalid certificate results in a normal failure
                # when attempting to refresh.
                open(img_key_path, "wb").close()
                open(img_cert_path, "wb").close()
                self.pkg("refresh test1", exit=1)

        def __get_cache_entries(self, dc):
                """Returns any HTTP cache headers found."""

                entries = []
                for hdr in ("CACHE-CONTROL", "PRAGMA"):
                        logpath = dc.get_logpath()
                        self.debug("check for HTTP cache headers in %s" %
                            logpath)
                        logfile = open(logpath, "r")
                        for line in logfile.readlines():
                                spos = line.find(hdr)
                                if spos > -1:
                                        self.debug("line: %s" % line)
                                        self.debug("hdr: %s spos: %s" % (hdr, spos))
                                        spos += len(hdr) + 1
                                        l = line[spos:].strip()
                                        l = l.strip("()")
                                        self.debug("l: %s" % l)
                                        if l:
                                                entries.append({ hdr: l })
                return entries

        def test_catalog_v1(self):
                """Verify that refresh works as expected for publishers that
                have repositories that offer catalog/1/ in exceptional error
                cases."""

                dc = self.dcs[1]
                self.pkgsend_bulk(self.durl1, self.foo10)

                # First, verify that full retrieval works.
                self.image_create(self.durl1, prefix="test1")

                self.pkg("list -aH pkg:/foo@1.0")

                # Only entries for the full catalog files should exist.
                expected = [
                    "/catalog/1/catalog.attrs",
                    "/catalog/1/catalog.base.C"
                ]
                returned = self.get_op_entries(dc, "catalog", "1")
                self.assertEqual(returned, expected)

                # Next, verify that a "normal" incremental update works as
                # expected when the catalog has changed.
                self.pkgsend_bulk(self.durl1, self.foo11)

                self.pkg("list -aH")
                self.pkg("list -aH pkg:/foo@1.0")
                self.pkg("list -aH pkg:/foo@1.1", exit=1)

                self.pkg("refresh")
                self.pkg("list -aH pkg:/foo@1.1")

                # A bit hacky, but load the repository's catalog directly
                # and then get the list of updates files it has created.
                repo = dc.get_repo()
                v1_cat = repo.get_catalog("test1")
                update = v1_cat.updates.keys()[-1]

                # All of the entries from the previous operations, and then
                # entries for the catalog attrs file, and one catalog update
                # file for the incremental update should be returned.
                expected += [
                    "/catalog/1/catalog.attrs",
                    "/catalog/1/%s" % update
                ]
                returned = self.get_op_entries(dc, "catalog", "1")
                self.assertEqual(returned, expected)

                # Next, verify that a "normal" incremental update works as
                # expected when the catalog hasn't changed.
                self.pkg("refresh test1")

                # All of the entries from the previous operations, and then
                # an entry for the catalog attrs file should be returned.
                expected += [
                    "/catalog/1/catalog.attrs"
                ]
                returned = self.get_op_entries(dc, "catalog", "1")
                self.assertEqual(returned, expected)

                # Next, verify that a "full" refresh after incrementals works
                # as expected.
                self.pkg("refresh --full test1")

                # All of the entries from the previous operations, and then
                # entries for each part of the catalog should be returned.
                expected += ["/catalog/1/catalog.attrs"]
                expected += ["/catalog/1/%s" % p for p in v1_cat.parts.keys()]
                returned = self.get_op_entries(dc, "catalog", "1")
                self.assertEqual(returned, expected)

                # Next, verify that rebuilding the repository's catalog induces
                # a full refresh.  Note that doing this wipes out the contents
                # of the log so far, so expected needs to be reset and the
                # catalog reloaded.
                expected = []
                repo = dc.get_repo()
                v1_cat = repo.get_catalog("test1")

                dc.stop()
                dc.set_rebuild()
                dc.start()
                dc.set_norebuild()

                self.pkg("refresh")

                # The catalog.attrs will be retrieved twice due to the first
                # request's incremental update failure.
                expected += ["/catalog/1/catalog.attrs"]
                expected += ["/catalog/1/catalog.attrs"]
                expected += ["/catalog/1/%s" % p for p in v1_cat.parts.keys()]
                returned = self.get_op_entries(dc, "catalog", "1")
                self.assertEqual(returned, expected)

                # Next, verify that if the client receives an incremental update
                # but the catalog is then rolled back to an earlier version
                # (think restoration of repository from backup) that the client
                # will induce a full refresh.

                # Preserve a copy of the existing repository.
                tdir = tempfile.mkdtemp(dir=self.test_root)
                trpath = os.path.join(tdir, os.path.basename(dc.get_repodir()))
                shutil.copytree(dc.get_repodir(), trpath)

                # Publish a new package.
                self.pkgsend_bulk(self.durl1, self.foo12)

                # Refresh to get an incremental update, and verify it worked.
                self.pkg("refresh")
                update = v1_cat.updates.keys()[-1]
                expected += [
                    "/catalog/1/catalog.attrs",
                    "/catalog/1/%s" % update
                ]
                repo = dc.get_repo()
                v1_cat = repo.get_catalog("test1")

                # Stop the depot server and put the old repository data back.
                dc.stop()
                shutil.rmtree(dc.get_repodir())
                shutil.move(trpath, dc.get_repodir())
                dc.start()
                expected = []
                repo = dc.get_repo()
                v1_cat = repo.get_catalog("test1")

                # Now verify that a refresh induces a full retrieval.  The
                # catalog.attrs file will be retrieved twice due to the
                # failure case.
                self.pkg("refresh")
                expected += ["/catalog/1/catalog.attrs"]
                expected += ["/catalog/1/catalog.attrs"]
                expected += ["/catalog/1/%s" % p for p in v1_cat.parts.keys()]
                returned = self.get_op_entries(dc, "catalog", "1")
                self.assertEqual(returned, expected)

                # Next, verify that if the client receives an incremental update
                # but the catalog is then rolled back to an earlier version
                # (think restoration of repository from backup) and then an
                # update that has already happened before is republished that
                # the client will induce a full refresh.

                # Preserve a copy of the existing repository.
                trpath = os.path.join(tdir, os.path.basename(dc.get_repodir()))
                shutil.copytree(dc.get_repodir(), trpath)

                # Publish a new package.
                self.pkgsend_bulk(self.durl1, self.foo12)
                repo = dc.get_repo()
                v1_cat = repo.get_catalog("test1")

                # Refresh to get an incremental update, and verify it worked.
                self.pkg("refresh")
                update = v1_cat.updates.keys()[-1]
                expected += [
                    "/catalog/1/catalog.attrs",
                    "/catalog/1/%s" % update
                ]
                repo = dc.get_repo()
                v1_cat = repo.get_catalog("test1")

                # Stop the depot server and put the old repository data back.
                dc.stop()
                shutil.rmtree(dc.get_repodir())
                shutil.move(trpath, dc.get_repodir())
                dc.start()
                expected = []

                # Re-publish the new package.  This causes the same catalog
                # entry to exist, but at a different point in time in the
                # update logs.
                self.pkgsend_bulk(self.durl1, self.foo12)
                repo = dc.get_repo()
                v1_cat = repo.get_catalog("test1")
                update = v1_cat.updates.keys()[-1]

                # Now verify that a refresh induces a full retrieval.  The
                # catalog.attrs file will be retrieved twice due to the
                # failure case, and a retrieval of the incremental update
                # file that failed to be applied should also be seen.
                self.pkg("refresh")
                expected += [
                    "/catalog/1/catalog.attrs",
                    "/catalog/1/%s" % update,
                    "/catalog/1/catalog.attrs",
                ]
                expected += ["/catalog/1/%s" % p for p in v1_cat.parts.keys()]
                returned = self.get_op_entries(dc, "catalog", "1")
                self.assertEqual(returned, expected)

                # Now verify that a full refresh will fail if the catalog parts
                # retrieved don't match the catalog attributes.  Do this by
                # saving a copy of the current repository catalog, publishing a
                # new package, putting back the old catalog parts and then
                # attempting a full refresh.  After that, verify the relevant
                # log entries exist.
                dc.stop()
                dc.set_debug_feature("headers")
                dc.start()

                old_cat = os.path.join(self.test_root, "old-catalog")
                cat_root = v1_cat.meta_root
                shutil.copytree(v1_cat.meta_root, old_cat)
                self.pkgsend_bulk(self.durl1, self.foo121)
                v1_cat = catalog.Catalog(meta_root=cat_root, read_only=True)
                for p in v1_cat.parts.keys():
                        # Overwrite the existing parts with empty ones.
                        part = catalog.CatalogPart(p, meta_root=cat_root)
                        part.destroy()

                        part = catalog.CatalogPart(p, meta_root=cat_root)
                        part.save()

                self.pkg("refresh --full", exit=1)
                expected = [
                    "/catalog/1/catalog.attrs",
                    "/catalog/1/catalog.base.C",
                ]
                returned = self.get_op_entries(dc, "catalog", "1")
                self.assertEqual(returned, expected)

                entries = self.__get_cache_entries(dc)
                expected = [
                    { "CACHE-CONTROL": "no-cache" },
                    { "CACHE-CONTROL": "no-cache" },
                ]
                self.assertEqualDiff(entries, expected)

                # Next, verify that a refresh without --full but that is
                # implicity a full because the catalog hasn't already been
                # retrieved is handled gracefully and the expected log
                # entries are present.
                dc.stop()
                dc.start()
                self.pkg("refresh", exit=1)
                expected = [
                    "/catalog/1/catalog.attrs",
                    "/catalog/1/catalog.base.C",
                    "/catalog/1/catalog.attrs",
                    "/catalog/1/catalog.base.C",
                ]
                returned = self.get_op_entries(dc, "catalog", "1")
                self.assertEqual(returned, expected)

                entries = self.__get_cache_entries(dc)
                # The first two requests should have not had any cache
                # headers attached, while the last two should have
                # triggered transport's revalidation logic.
                expected = [
                    { "CACHE-CONTROL": "max-age=0" },
                    { "CACHE-CONTROL": "max-age=0" },
                ]
                self.assertEqualDiff(entries, expected)

                # Next, purposefully corrupt the catalog.attrs file in the
                # repository and attempt a refresh.  The client should fail
                # gracefully.
                f = open(os.path.join(v1_cat.meta_root, "catalog.attrs"), "wb")
                f.write("INVALID")
                f.close()
                self.pkg("refresh", exit=1)

                # Finally, restore the catalog and verify the client can
                # refresh.
                shutil.rmtree(v1_cat.meta_root)
                shutil.copytree(old_cat, v1_cat.meta_root)
                self.pkg("refresh")


if __name__ == "__main__":
        unittest.main()
