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

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import datetime
import os
import shutil
import six
import tempfile
import time
import unittest

from six.moves import http_client
from six.moves.urllib.error import HTTPError, URLError
from six.moves.urllib.parse import quote, urljoin
from six.moves.urllib.request import urlopen

import pkg.client.publisher as publisher
import pkg.depotcontroller as dc
import pkg.fmri as fmri
import pkg.manifest as man
import pkg.misc as misc
import pkg.server.repository as sr
import pkg.p5i as p5i
import re
import subprocess

class TestPkgDepot(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo10 = """
            open foo@1.0,5.11-0
            add dir path=tmp/foo mode=0755 owner=root group=bin
            close """

        bar10 = """
            open bar@1.0,5.11-0
            add dir path=tmp/bar mode=0755 owner=root group=bin
            close """

        quux10 = """
            open quux@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        info10 = """
            open info@1.0,5.11-0
            close """

        update10 = """
            open update@1.0,5.11-0
            close """

        update11 = """
            open update@1.1,5.11-0
            close """

        system10 = """
            open system/libc@1.0,5.11-0
            add set name="description" value="Package to test package names with slashes"
            add dir path=tmp/foo mode=0755 owner=root group=bin
            add depend type=require fmri=pkg:/SUNWcsl
            close """

        entire10 = """
            open entire@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/foo
            close """

        info20 = """
            open info@2.0,5.11-0
            add set name="description" value="Test for checking info_0 consistency"
            add set name="pkg.human-version" value="test of human version"
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close"""

        misc_files = [ "tmp/libc.so.1", "tmp/cat" ]

        def setUp(self):
                # test_info() parses dates,
                # so set expected locale before starting depots
                os.environ['LC_ALL'] = 'C'

                # This suite, for obvious reasons, actually needs a depot.
                pkg5unittest.SingleDepotTestCase.setUp(self, start_depot=True)
                self.make_misc_files(self.misc_files)

        def test_depot_ping(self):
                """ Ping the depot several times """

                self.assert_(self.dc.is_alive())
                self.assert_(self.dc.is_alive())
                self.assert_(self.dc.is_alive())
                self.assert_(self.dc.is_alive())

        def testStartStop(self):
                """ Start and stop the depot several times """
                self.dc.stop()
                for i in range(0, 5):
                        self.dc.start()
                        self.assert_(self.dc.is_alive())
                        self.dc.stop()
                        self.assert_(not self.dc.is_alive())

                self.dc.start()

        def test_bug_1876(self):
                """ Send package quux@1.0 an action at a time, restarting the
                    depot server after each one is sent, to ensure that
                    transactions work across depot restart. Then verify that
                    the package was successfully added by performing some
                    basic operations. """

                durl = self.dc.get_depot_url()

                for line in self.quux10.split("\n"):
                        line = line.strip()
                        if line == "":
                                continue

                        try:
                                self.pkgsend(durl, line, exit = 0)
                        except:
                                self.pkgsend(durl, "close -A", exit = 0)
                                raise

                        if not line == "close":
                                self.restart_depots()

                self.image_create(durl)

                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.pkg("install quux")

                self.pkg("list")
                self.pkg("verify")

                self.pkg("uninstall quux")
                self.pkg("verify")

        def test_bad_fmris(self):
                durl = self.dc.get_depot_url()
                self.pkgsend(durl, "open foo@", exit=1)
                self.pkgsend(durl, "open foo@x.y", exit=1)
                self.pkgsend(durl, "open foo@1.0,-2.0", exit=1)

        def test_bug_3365(self):
                durl = self.dc.get_depot_url()
                depotpath = self.dc.get_repodir()

                dir_file = os.path.join(depotpath, "search.dir")
                pag_file = os.path.join(depotpath, "search.pag")

                self.assert_(not os.path.exists(dir_file))
                self.assert_(not os.path.exists(pag_file))

                f = open(dir_file, "w")
                f.close()
                f = open(pag_file, "w")
                f.close()
                self.assert_(os.path.exists(dir_file))
                self.assert_(os.path.exists(pag_file))

                self.dc.stop()
                self.dc.start()
                self.pkgsend_bulk(durl, self.quux10)
                self.assert_(not os.path.exists(dir_file))
                self.assert_(not os.path.exists(pag_file))

        def test_bug_4489(self):
                """Publish a package and then verify that the depot /info
                operation doesn't fail."""
                depot_url = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(depot_url, self.info10)
                repourl = urljoin(depot_url, "info/0/{0}".format(plist[0]))
                urlopen(repourl)

        def test_bug_3739(self):
                """Verify that a depot will return a 400 (Bad Request) error
                whenever it is provided malformed FMRIs."""

                durl = self.dc.get_depot_url()

                for operation in ("info", "manifest"):
                        for entry in ("BRCMbnx", "BRCMbnx%40a",
                            "BRCMbnx%400.5.11%2C5.11-0.101%3A20081119T231649a"):
                                try:
                                        urlopen("{0}/{1}/0/{2}".format(durl,
                                            operation, entry))
                                except HTTPError as e:
                                        if e.code != http_client.BAD_REQUEST:
                                                raise

        def test_bug_5366(self):
                """Publish a package with slashes in the name, and then verify
                that the depot manifest and info operations work regardless of
                the encoding."""
                depot_url = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(depot_url, self.system10)
                # First, try it un-encoded.
                repourl = urljoin(depot_url, "info/0/{0}".format(plist[0]))
                urlopen(repourl)
                repourl = urljoin(depot_url, "manifest/0/{0}".format(
                    plist[0]))
                urlopen(repourl)
                # Second, try it encoded.
                repourl = urljoin(depot_url, "info/0/{0}".format(
                    quote(plist[0])))
                urlopen(repourl)
                repourl = urljoin(depot_url, "manifest/0/{0}".format(
                    quote(plist[0])))
                urlopen(repourl)

        def test_info(self):
                """Testing information showed in /info/0."""

                depot_url = self.dc.get_depot_url();
                plist = self.pkgsend_bulk(depot_url, self.info20)

                openurl = urljoin(depot_url, "info/0/{0}".format(plist[0]))
                content = urlopen(openurl).read()
                # Get text from content.
                lines = content.splitlines()
                info_dic = {}
                attr_list = [
                    'Name',
                    'Summary',
                    'Publisher',
                    'Version',
                    'Build Release',
                    'Branch',
                    'Packaging Date',
                    'Size',
                    'Compressed Size',
                    'FMRI'
                ]

                for line in lines:
                        fields = line.split(":", 1)
                        attr = fields[0].strip()
                        if attr == "License":
                                break
                        if attr in attr_list:
                                if len(fields) == 2:
                                        info_dic[attr] = fields[1].strip()
                                else:
                                        info_dic[attr] = ""

                # Read manifest.
                openurl = urljoin(depot_url, "manifest/0/{0}".format(plist[0]))
                content = urlopen(openurl).read()
                manifest = man.Manifest()
                manifest.set_content(content=content)
                fmri_content = manifest.get("pkg.fmri", "")

                # Check if FMRI is empty.
                self.assert_(fmri_content)
                pfmri = fmri.PkgFmri(fmri_content, None)
                pub, name, ver = pfmri.tuple()
                size, csize = manifest.get_size()

                # Human version.
                version = info_dic['Version']
                hum_ver = ""
                if '(' in version:
                        start = version.find('(')
                        end = version.rfind(')')
                        hum_ver = version[start + 1 : end - len(version)]
                        version = version[:start - len(version)]
                        info_dic['Version'] = version.strip()

                # Compare each attribute.
                self.assertEqual(info_dic["Summary"], manifest.get("pkg.summary",
                    manifest.get("description", "")))
                self.assertEqual(info_dic["Version"], str(ver.release))
                self.assertEqual(hum_ver, manifest.get("pkg.human-version",""))
                self.assertEqual(info_dic["Name"], name)
                self.assertEqual(info_dic["Publisher"], pub)
                self.assertEqual(info_dic["Build Release"], str(ver.build_release))
                timestamp = datetime.datetime.strptime(
                    info_dic["Packaging Date"], "%a %b %d %H:%M:%S %Y")
                self.assertEqual(timestamp, ver.get_timestamp())
                self.assertEqual(info_dic["Size"], misc.bytes_to_str(size))
                self.assertEqual(info_dic["Compressed Size"], misc.bytes_to_str(csize))
                self.assertEqual(info_dic["FMRI"], fmri_content)

        def test_bug_5707(self):
                """Testing depotcontroller.refresh()."""

                depot_url = self.dc.get_depot_url()
                self.pkgsend_bulk(depot_url, self.foo10)

                self.image_create(depot_url)
                self.pkg("install foo")
                self.pkg("verify")

                depot_file_url = "file://{0}".format(self.dc.get_repodir())
                self.pkgsend_bulk(depot_url, self.bar10)
                self.pkg("refresh")

                self.pkg("install bar")
                self.pkg("verify")

                self.dc.refresh()
                self.pkg("refresh")

                self.pkg("install bar", exit=4) # nothing to do
                self.pkg("verify")

        def test_face_root(self):
                """Verify that files outside of the package content web root
                cannot be accessed, and that files inside can be."""
                depot_url = self.dc.get_depot_url()
                # Since /usr/share/lib/pkg/web/ is the content web root,
                # any attempts to go outside that directory should fail
                # with a 404 error.
                try:
                        urlopen("{0}/../../../../bin/pkg".format(depot_url))
                except HTTPError as e:
                        if e.code != http_client.NOT_FOUND:
                                raise

                f = urlopen("{0}/robots.txt".format(depot_url))
                self.assert_(len(f.read()))
                f.close()

        def test_repo_create(self):
                """Verify that starting a depot server in readonly mode with
                a non-existent or empty repo_dir fails and that permissions
                errors are handled correctly during creation.  Then verify
                that starting a depot with the same directory in publishing
                mode works and then a readonly depot again after that works.
                """

                dpath = os.path.join(self.test_root, "repo_create")

                opath = self.dc.get_repodir()
                self.dc.set_repodir(dpath)

                # First, test readonly mode with a repo_dir that doesn't exist.
                self.dc.set_readonly()
                self.dc.stop()
                self.dc.start_expected_fail()
                self.assert_(not self.dc.is_alive())

                # Next, test readonly mode with a repo_dir that is empty.
                os.makedirs(dpath, misc.PKG_DIR_MODE)
                self.dc.set_readonly()
                self.dc.start_expected_fail()
                self.assert_(not self.dc.is_alive())

                # Next, test readwrite (publishing) mode with a non-existent
                # repo_dir.
                shutil.rmtree(dpath)
                self.dc.set_readwrite()
                self.dc.start()
                self.assert_(self.dc.is_alive())
                self.dc.stop()
                self.assert_(not self.dc.is_alive())

                # Next, test readwrite (publishing) mode with a non-existent
                # repo_dir for an unprivileged user.
                shutil.rmtree(dpath)
                self.dc.set_readwrite()
                wr_start, wr_end = self.dc.get_wrapper()
                su_wrap, su_end = self.get_su_wrapper(su_wrap=True)
                try:
                        self.dc.set_wrapper([su_wrap], su_end)
                        self.dc.start_expected_fail(exit=1)
                finally:
                        # Even if this test fails, this wrapper must be reset.
                        self.dc.set_wrapper(wr_start, wr_end)
                self.assert_(not self.dc.is_alive())

                # Next, test readwrite (publishing) mode with an empty repo_dir.
                os.makedirs(dpath, misc.PKG_DIR_MODE)
                self.dc.set_readwrite()
                self.dc.start()
                self.assert_(self.dc.is_alive())
                self.dc.stop()
                self.assert_(not self.dc.is_alive())

                # Finally, re-test readonly mode now that the repository has
                # been created.
                self.dc.set_readonly()
                self.dc.start()
                self.assert_(self.dc.is_alive())
                self.dc.stop()
                self.assert_(not self.dc.is_alive())

                # Cleanup.
                shutil.rmtree(dpath)
                self.dc.set_repodir(opath)

        def test_append_reopen(self):
                """Test that if a depot has a partially finished append
                transaction, that it reopens it correctly."""

                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.foo10)
                self.pkgsend(durl, "append {0}".format(plist[0]))
                self.dc.stop()
                self.dc.start()
                self.pkgsend(durl, "close")

        def test_nonsig_append(self):
                """Test that sending a non-signature action to an append
                transaction results in an error."""

                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.foo10)
                self.pkgsend(durl, "append {0}".format(plist[0]))
                self.pkgsend(durl, "add dir path=tmp/foo mode=0755 "
                    "owner=root group=bin", exit=1)

        def test_root_link(self):
                """Verify that the depot server accepts a link to a
                directory as a repository root."""

                if self.dc.started:
                        self.dc.stop()

                # Create a link to the repository and verify that
                # the depot server allows it.
                lsrc = self.dc.get_repodir()
                ltarget = os.path.join(self.test_root, "depot_link")
                os.symlink(lsrc, ltarget)
                self.dc.set_repodir(ltarget)
                self.dc.start()

                # Reset for any tests that might execute afterwards.
                os.unlink(ltarget)
                self.dc.stop()
                self.dc.set_repodir(lsrc)
                self.dc.start()

        def test_empty_incorp_depend(self):
                """ Bug 16304629
                Test that a version-less incorporate dependency in a package
                doesn't cause a traceback and a 404 in the BUI.
                """
                depot_url = self.dc.get_depot_url()
                self.pkgsend_bulk(depot_url, self.foo10)
                self.pkgsend_bulk(depot_url, self.entire10)

                repourl = urljoin(depot_url,
                    "/en/catalog.shtml?version={0}&action=Browse".format(
                    quote("entire@1.0,5.11-0")))

                res = urlopen(repourl)

        def test_publisher_prefix(self):
                """Test that various publisher prefixes can be understood
                by CherryPy's dispatcher."""

                if self.dc.started:
                        self.dc.stop()

                depot_url = self.dc.get_depot_url()
                repopath = os.path.join(self.test_root, "repo")
                self.create_repo(repopath)
                self.dc.set_repodir(repopath)
                pubs = ["test-hyphen", "test.dot"]
                for p in pubs:
                        self.pkgrepo("-s {0} add-publisher {1}".format(
                            repopath, p))
                self.dc.start()
                for p in pubs:
                        # test that the catalog file can be found
                        url = urljoin(depot_url,
                            "{0}/catalog/1/catalog.attrs".format(p))
                        urlopen(url)


class TestDepotController(pkg5unittest.CliTestCase):

        def setUp(self):
                pkg5unittest.CliTestCase.setUp(self)

                self.__dc = dc.DepotController()
                self.__pid = os.getpid()
                self.__dc.set_property("publisher", "prefix", "test")
                self.__dc.set_depotd_path(pkg5unittest.g_pkg_path + \
                    "/usr/lib/pkg.depotd")
                self.__dc.set_depotd_content_root(pkg5unittest.g_pkg_path + \
                    "/usr/share/lib/pkg")

                repopath = os.path.join(self.test_root, "repo")
                logpath = os.path.join(self.test_root, self.id())
                self.create_repo(repopath, properties={ "publisher": {
                    "prefix": "test" }})
                self.__dc.set_repodir(repopath)
                self.__dc.set_logpath(logpath)

        def _get_repo_index_dir(self):
                depotpath = self.__dc.get_repodir()
                repo = self.__dc.get_repo()
                rstore = repo.get_pub_rstore("test")
                return rstore.index_root

        def _get_repo_writ_dir(self):
                depotpath = self.__dc.get_repodir()
                repo = self.__dc.get_repo()
                rstore = repo.get_pub_rstore("test")
                return rstore.writable_root

        def tearDown(self):
                pkg5unittest.CliTestCase.tearDown(self)
                self.__dc.kill()

        def testStartStop(self):
                self.__dc.set_port(self.next_free_port)
                for i in range(0, 5):
                        self.__dc.start()
                        self.assert_(self.__dc.is_alive())
                        self.__dc.stop()
                        self.assert_(not self.__dc.is_alive())

        def test_cfg_file(self):
                cfg_file = os.path.join(self.test_root, "cfg2")
                fh = open(cfg_file, "w")
                fh.close()
                self.__dc.set_port(self.next_free_port)
                self.__dc.set_cfg_file(cfg_file)
                self.__dc.start()

        def test_writable_root(self):
                """Tests whether the index and feed cache file are written to
                the writable root parameter."""

                self.make_misc_files(TestPkgDepot.misc_files)
                writable_root = os.path.join(self.test_root,
                    "writ_root")
                o_index_dir = os.path.join(self._get_repo_index_dir(), "index")

                timeout = 10

                def check_state(check_feed):
                        index_dir = os.path.join(self._get_repo_writ_dir(),
                            "index")
                        feed = os.path.join(writable_root, "publisher", "test",
                            "feed.xml")
                        found = not os.path.exists(o_index_dir) and \
                            os.path.isdir(index_dir) and \
                            (not check_feed or os.path.isfile(feed))
                        start_time = time.time()
                        while not found and time.time() - start_time < timeout:
                                time.sleep(1)
                                found = not os.path.exists(o_index_dir) and \
                                    os.path.isdir(index_dir) and \
                                    (not check_feed or os.path.isfile(feed))

                        self.assert_(not os.path.exists(o_index_dir))
                        self.assert_(os.path.isdir(index_dir))
                        if check_feed:
                                try:
                                        self.assert_(os.path.isfile(feed))
                                except:
                                        raise RuntimeError("Feed cache file "
                                            "not found at '{0}'.".format(feed))
                def get_feed(durl, pub=""):
                        start_time = time.time()
                        got = False
                        while not got and (time.time() - start_time) < timeout:
                                if pub:
                                        pub = "{0}/".format(pub)
                                try:
                                        urlopen("{0}{1}/feed".format(durl,
                                            pub))
                                        got = True
                                except HTTPError as e:
                                        self.debug(str(e))
                                        time.sleep(1)
                        self.assert_(got)

                self.__dc.set_port(self.next_free_port)
                durl = self.__dc.get_depot_url()

                repo = self.__dc.get_repo()
                pub = repo.get_publisher("test")
                pub_repo = pub.repository
                if not pub_repo:
                        pub_repo = publisher.Repository()
                        pub.repository = pub_repo
                pub_repo.origins = [durl]
                repo.update_publisher(pub)

                self.__dc.set_writable_root(writable_root)
                self.__dc.set_property("publisher", "prefix", "test")
                self.__dc.start()
                check_state(False)
                self.pkgsend_bulk(durl, TestPkgDepot.quux10, refresh_index=True)
                get_feed(durl)
                check_state(True)

                self.image_create(durl)
                self.pkg("search -r cat")
                self.__dc.stop()
                self.__dc.set_readonly()
                shutil.rmtree(writable_root)
                self.__dc.start()
                get_feed(durl)
                check_state(True)
                self.pkg("search -r cat")
                self.__dc.stop()
                self.__dc.set_refresh_index()
                shutil.rmtree(writable_root)
                self.__dc.start()
                check_state(False)
                self.__dc.stop()
                self.__dc.set_norefresh_index()
                self.__dc.start()
                get_feed(durl)
                check_state(True)
                self.pkg("search -r cat")

        def testBadArgs(self):
                self.__dc.set_port(self.next_free_port)
                self.__dc.set_readonly()
                self.__dc.set_rebuild()
                self.__dc.set_norefresh_index()

                self.assert_(self.__dc.start_expected_fail())

                self.__dc.set_readonly()
                self.__dc.set_norebuild()
                self.__dc.set_refresh_index()

                self.assert_(self.__dc.start_expected_fail())

                self.__dc.set_readonly()
                self.__dc.set_rebuild()
                self.__dc.set_refresh_index()

                self.assert_(self.__dc.start_expected_fail())

                self.__dc.set_readwrite()
                self.__dc.set_rebuild()
                self.__dc.set_refresh_index()

                self.assert_(self.__dc.start_expected_fail())

                self.__dc.set_mirror()
                self.__dc.set_rebuild()
                self.__dc.set_norefresh_index()

                self.assert_(self.__dc.start_expected_fail())

                self.__dc.set_mirror()
                self.__dc.set_norebuild()
                self.__dc.set_refresh_index()

                self.assert_(self.__dc.start_expected_fail())

        def test_disable_ops(self):
                """Verify that disable-ops works as expected."""

                # For this disabled case, /catalog/1/ should return
                # a NOT_FOUND error.
                self.__dc.set_disable_ops(["catalog/1"])
                self.__dc.set_port(self.next_free_port)
                self.__dc.start()
                durl = self.__dc.get_depot_url()
                try:
                        urlopen("{0}/catalog/1/".format(durl))
                except HTTPError as e:
                        self.assertEqual(e.code, http_client.NOT_FOUND)
                self.__dc.stop()

                # For this disabled case, all /catalog/ operations should return
                # a NOT_FOUND error.
                self.__dc.set_disable_ops(["catalog"])
                self.__dc.set_port(self.next_free_port)
                self.__dc.start()
                durl = self.__dc.get_depot_url()
                for ver in (0, 1):
                        try:
                                urlopen("{0}/catalog/{1:d}/".format(durl, ver))
                        except HTTPError as e:
                                self.assertEqual(e.code, http_client.NOT_FOUND)
                self.__dc.stop()

                # In the normal case, /catalog/1/ should return
                # a FORBIDDEN error.
                self.__dc.unset_disable_ops()
                self.__dc.start()
                durl = self.__dc.get_depot_url()
                try:
                        urlopen("{0}/catalog/1/".format(durl))
                except HTTPError as e:
                        self.assertEqual(e.code, http_client.FORBIDDEN)
                self.__dc.stop()

                # A bogus operation should prevent the depot from starting.
                self.__dc.set_disable_ops(["no_such_op/0"])
                self.__dc.start_expected_fail()
                self.assertFalse(self.__dc.is_alive())


class TestDepotOutput(pkg5unittest.SingleDepotTestCase):
        # Since these tests are output sensitive, the depots should be purged
        # after each one is run.
        persistent_setup = False

        quux10 = """
            open quux@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            close """

        info10 = """
            open info@1.0,5.11-0
            close """

        file10 = """
            open file@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/var
            add file tmp/file path=var/file mode=644 owner=root group=bin
            close """

        system10 = """
            open system/libc@1.0,5.11-0
            add set name="description" value="Package to test package names with slashes"
            add dir path=tmp/foo mode=0755 owner=root group=bin
            add depend type=require fmri=pkg:/SUNWcsl
            close """

        zfsextras10 = """
            open zfs-extras@1.0,5.11-0
            close """

        zfsutils10 = """
            open zfs/utils@1.0,5.11-0
            close """

        repo_cfg = {
            "publisher": {
                "prefix": "org.opensolaris.pending"
            },
        }

        pub_repo_cfg = {
            "collection_type": "supplemental",
            "description":
                "Development packages for the contrib repository.",
            "legal_uris": [
                "http://www.opensolaris.org/os/copyrights",
                "http://www.opensolaris.org/os/tou",
                "http://www.opensolaris.org/os/trademark"
            ],
            "mirrors": [],
            "name": """"Pending" Repository""",
            "origins": [],  # Has to be set during setUp for correct origin.
            "refresh_seconds": 86400,
            "registration_uri": "",
            "related_uris": [
                "http://jucr.opensolaris.org/contrib",
                "http://jucr.opensolaris.org/pending",
                "http://pkg.opensolaris.org/contrib",
            ]
        }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)

                # Prevent override of custom configuration;
                # tests will set as needed.
                self.dc.clear_property("publisher", "prefix")

                self.tpath = tempfile.mkdtemp(prefix="tpath",
                    dir=self.test_root)

                self.make_misc_files("tmp/file")

        def __depot_daemon_start(self, repopath, out_path, err_path):
                """Helper function: start a depot daemon and return a handler
                for its parent process and the port number it is running on.
                The parent process is a ctrun process. It is the user's
                responsibility to call depot_daemon_stop to stop the process.
                ctrun is used to kill the depot daemon process after finishing
                testing. It is needed because the double fork machanism of the
                daemonizer make the daemonized depot server indenpendent from
                its parent process.

                repopath: The repository path that a depot daemon will run on.

                out_path: The depot daemon stdout log file path.

                err_path: The depot daemon stderr log file path."""

                # Make sure the PKGDEPOT_CONTROLLER is not set in the newenv.
                newenv = os.environ.copy()
                newenv.pop("PKGDEPOT_CONTROLLER", None)
                cmdargs = "/usr/bin/ctrun -o noorphan {0}/usr/lib/pkg.depotd " \
                    "-p {1} -d {2} --content-root {3}/usr/share/lib/pkg " \
                    "--readonly </dev/null --log-access={4} " \
                    "--log-errors={5}".format(pkg5unittest.g_pkg_path,
                        self.next_free_port, repopath, pkg5unittest.g_pkg_path,
                        out_path, err_path)

                curport = self.next_free_port
                self.next_free_port += 1

                # Start a depot daemon process.
                try:
                        depot_handle = subprocess.Popen(cmdargs, env=newenv,
                            shell=True)

                        self.assert_(depot_handle != None, msg="Could not "
                            "start depot")
                        begintime = time.time()
                        check_interval = 0.20
                        daemon_started = False
                        durl = "http://localhost:{0}/en/index.shtml".format(curport)

                        while (time.time() - begintime) <= 40.0:
                                rc = depot_handle.poll()
                                self.assert_(rc is None, msg="Depot exited "
                                    "unexpectedly")

                                try:
                                        f = urlopen(durl)
                                        daemon_started = True
                                        break
                                except URLError as e:
                                        time.sleep(check_interval)

                        if not daemon_started:
                                if depot_handle:
                                        depot_handle.kill()
                                self.assert_(daemon_started, msg="Could not "
                                    "access depot daemon")

                        # Read the msgs from the err log file to verify log
                        # msgs.
                        with open(err_path, "r") as read_err:
                                msgs = read_err.readlines()
                                self.assert_(msgs, "Log message is "
                                    "empty. Check if the previous "
                                    "ctrun process shut down "
                                    "properly")
                        return (depot_handle, curport)
                except:
                        try:
                                if depot_handle:
                                        depot_handle.kill()
                        except:
                                pass
                        raise

        def __depot_daemon_stop(self, depot_handle):
                """Helper function: stop the depot daemon process by sending
                signal to its handle."""

                # Terminate the depot daemon. If failed, kill it.
                try:
                        if depot_handle:
                                depot_handle.terminate()
                except:
                        try:
                                if depot_handle:
                                        depot_handle.kill()
                        except:
                                pass

        def test_0_depot_bui_output(self):
                """Verify that a non-error response and valid HTML is returned
                for each known BUI page in every available depot mode."""

                pub = "test"
                self.dc.set_property("publisher", "prefix", pub)

                # A list of tuples containing the name of the method used to set
                # the mode, and then the method needed to unset that mode.
                mode_methods = [
                    ("set_readwrite", None),
                    ("set_mirror", "unset_mirror"),
                    ("set_readonly", "set_readwrite"),
                ]

                pages = [
                    "index.shtml",
                    "en/catalog.shtml",
                    "en/index.shtml",
                    "en/advanced_search.shtml",
                    "en/search.shtml",
                    "en/stats.shtml",
                ]

                repodir = self.dc.get_repodir()
                durl = self.dc.get_depot_url()
                for with_packages in (False, True):
                        shutil.rmtree(repodir, ignore_errors=True)

                        # Create repository and set publisher origins.
                        self.create_repo(self.dc.get_repodir())
                        self.pkgrepo("set -s {repodir} -p {pub} "
                            "repository/origins={durl}".format(**locals()))

                        if with_packages:
                                self.dc.set_readwrite()
                                self.dc.start()
                                self.pkgsend_bulk(durl, (self.info10,
                                    self.quux10, self.system10))
                                self.dc.stop()

                        for set_method, unset_method in mode_methods:
                                if set_method:
                                        getattr(self.dc, set_method)()

                                self.dc.start()
                                for path in pages:
                                        # Any error responses will cause an
                                        # exception.
                                        response = urlopen(
                                            "{0}/{1}".format(durl, path))

                                        fd, fpath = tempfile.mkstemp(
                                            suffix="html", dir=self.tpath)
                                        fp = os.fdopen(fd, "w")
                                        fp.write(response.read())
                                        fp.close()

                                        # Because the 'role' attribute used for
                                        # screen readers and other accessibility
                                        # tools isn't part of the official XHTML
                                        # 1.x standards, it has to be dropped
                                        # for the document to be validated.
                                        # Setting 'drop_prop_attrs' to True here
                                        # does that while ensuring that the
                                        # output of the depot is otherwise
                                        # standards-compliant.
                                        self.validate_html_file(fpath,
                                            drop_prop_attrs=True)

                                self.dc.stop()
                                if unset_method:
                                        getattr(self.dc, unset_method)()

        def __update_repo_config(self):
                """Helper function to generate test repository configuration."""
                # Find and load the repository configuration.
                rpath = self.dc.get_repodir()
                assert os.path.isdir(rpath)
                rcpath = os.path.join(rpath, "cfg_cache")

                rc = sr.RepositoryConfig(target=rcpath)

                # Update the configuration with our sample data.
                cfgdata = self.repo_cfg
                for section in cfgdata:
                        for prop in cfgdata[section]:
                                rc.set_property(section, prop,
                                    cfgdata[section][prop])

                # Save it.
                rc.write()

                # Apply publisher properties and update.
                repo = self.dc.get_repo()
                try:
                        pub = repo.get_publisher("org.opensolaris.pending")
                except sr.RepositoryUnknownPublisher:
                        pub = publisher.Publisher("org.opensolaris.pending")
                        repo.add_publisher(pub)

                pub_repo = pub.repository
                if not pub_repo:
                        pub_repo = publisher.Repository()
                        pub.repository = pub_repo

                for attr, val in six.iteritems(self.pub_repo_cfg):
                        setattr(pub_repo, attr, val)
                repo.update_publisher(pub)

        def test_1_depot_publisher(self):
                """Verify the output of the depot /publisher operation."""

                # Now update the repository configuration while the depot is
                # stopped so changes won't be overwritten on exit.
                self.__update_repo_config()

                # Start the depot.
                self.dc.start()

                durl = self.dc.get_depot_url()
                purl = urljoin(durl, "publisher/0")
                entries = p5i.parse(location=purl)
                assert entries[0][0].prefix == "test"
                assert entries[1][0].prefix == "org.opensolaris.pending"

                # Now verify that the parsed response has the expected data.
                pub, pkglist = entries[-1]
                cfgdata = self.repo_cfg
                for prop in cfgdata["publisher"]:
                        self.assertEqual(getattr(pub, prop),
                            cfgdata["publisher"][prop])

                repo = pub.repository
                for prop, expected in six.iteritems(self.pub_repo_cfg):
                        returned = getattr(repo, prop)
                        if prop.endswith("uris") or prop == "origins":
                                uris = []
                                for u in returned:
                                        uri = u.uri
                                        if uri.endswith("/"):
                                                uri = uri[:-1]
                                        uris.append(uri)
                                returned = uris
                        self.assertEqual(returned, expected)

        def test_2_depot_p5i(self):
                """Verify the output of the depot /p5i operation."""

                # Now update the repository configuration while the depot is
                # stopped so changes won't be overwritten on exit.
                self.__update_repo_config()

                # Start the depot.
                self.dc.start()

                # Then, publish some packages we can abuse for testing.
                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, (self.info10, self.quux10,
                    self.system10, self.zfsextras10, self.zfsutils10))

                # Now, for each published package, attempt to get a p5i file
                # and then verify that the parsed response has the expected
                # package information under the expected publisher.
                for p in plist:
                        purl = urljoin(durl, "p5i/0/{0}".format(p))
                        pub, pkglist = p5i.parse(location=purl)[0]

                        # p5i files contain non-qualified FMRIs as the FMRIs
                        # are already grouped by publisher.
                        nq_p = fmri.PkgFmri(p).get_fmri(anarchy=True,
                            include_scheme=False)
                        self.assertEqual(pkglist, [nq_p])

                # Try again, but only using package stems.
                for p in plist:
                        stem = fmri.PkgFmri(p).pkg_name
                        purl = urljoin(durl, "p5i/0/{0}".format(stem))
                        pub, pkglist = p5i.parse(location=purl)[0]
                        self.assertEqual(pkglist, [stem])

                # Try again, but using wildcards (which will return a list of
                # matching package stems).
                purl = urljoin(durl, "p5i/0/zfs*")
                pub, pkglist = p5i.parse(location=purl)[0]
                self.assertEqual(pkglist, ["zfs-extras", "zfs/utils"])

                # Finally, verify that a non-existent package will error out
                # with a httplib.NOT_FOUND.
                try:
                        urlopen(urljoin(durl,
                            "p5i/0/nosuchpackage"))
                except HTTPError as e:
                        if e.code != http_client.NOT_FOUND:
                                raise

        def test_3_headers(self):
                """Ensure expected headers are present for client operations
                (excluding publication)."""

                # Now update the repository configuration while the depot is
                # stopped so changes won't be overwritten on exit.
                self.__update_repo_config()

                # Start the depot.
                self.dc.start()

                durl = self.dc.get_depot_url()
                pfmri = fmri.PkgFmri(self.pkgsend_bulk(durl, self.file10,
                    refresh_index=True)[0], "5.11")

                # Wait for search indexing to complete.
                self.wait_repo(self.dc.get_repodir())

                def get_headers(req_path):
                        try:
                                rinfo = urlopen(urljoin(durl,
                                    req_path)).info()
                                return list(rinfo.items())
                        except HTTPError as e:
                                return list(e.info().items())
                        except Exception as e:
                                raise RuntimeError("retrieval of {0} "
                                    "failed: {1}".format(req_path, str(e)))

                for req_path in ("publisher/0",
                    'search/1/False_2_None_None_%2Fvar%2Ffile',
                    "versions/0", "manifest/0/{0}".format(pfmri.get_url_path()),
                    "catalog/1/catalog.attrs",
                    "file/0/3aad0bca6f3a6f502c175700ebe90ef36e312d7e"):
                        hdrs = dict(get_headers(req_path))

                        # Fields must be referenced in lowercase.
                        cc = hdrs.get("cache-control", "")
                        self.assertTrue(cc.startswith("must-revalidate, "
                            "no-transform, max-age="),
                            "cache-control for '{0}' is '{1}'".format(req_path, cc))
                        exp = hdrs.get("expires", None)
                        self.assertNotEqual(exp, None)
                        self.assertTrue(exp.endswith(" GMT"))

                for req_path in ("catalog/1/catalog.hatters",
                    "file/0/3aad0bca6f3a6f502c175700ebe90ef36e312d7f"):

                        hdrs = dict(get_headers(req_path))
                        cc = hdrs.get("cache-control", None)
                        prg = hdrs.get("pragma", None)
                        self.assertEqual(cc, None)
                        self.assertEqual(prg, None)

        def test_bug_15482(self):
                """Test to make sure BUI search doesn't trigger a traceback."""

                # Now update the repository configuration while the depot is
                # stopped so changes won't be overwritten on exit.
                self.__update_repo_config()

                # Start the depot.
                self.dc.start()

                # Then, publish some packages we can abuse for testing.
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.quux10, refresh_index=True)

                surl = urljoin(durl,
                    "en/search.shtml?action=Search&token=*")
                urlopen(surl).read()
                surl = urljoin(durl,
                    "en/advanced_search.shtml?action=Search&token=*")
                urlopen(surl).read()
                surl = urljoin(durl,
                    "en/advanced_search.shtml?token=*&show=a&rpp=50&"
                    "action=Advanced+Search")
                urlopen(surl).read()

        def test_address(self):
                """Verify that depot address can be set."""

                # Check that IPv6 address can be used.
                self.dc.set_address("::1")
                self.dc.set_port(self.next_free_port)
                self.dc.start()
                self.assert_(self.dc.is_alive())
                self.assert_(self.dc.is_alive())
                self.assert_(self.dc.is_alive())

                # Check that we can retrieve something.
                durl = self.dc.get_depot_url()
                verdata = urlopen("{0}/versions/0/".format(durl))

        def test_log_depot_daemon(self):
                """Verify that depot daemon works properly and the error
                 message is logged properly."""

                if self.dc.started:
                        self.dc.stop()

                # Create a test repo.
                repopath = os.path.join(self.test_root, "repo_tmp_depot_log")
                self.create_repo(repopath)

                out_path = os.path.join(self.test_root, "daemon_out_log")
                err_path = os.path.join(self.test_root, "daemon_err_log")

                depot_handle = None
                try:
                        depot_handle, curport = self.__depot_daemon_start(
                            repopath, out_path, err_path)

                        # Issue a bad request to trigger the server logging
                        # the error msg.
                        durl = "http://localhost:{0}/catalog/1/404".format(
                            curport)
                        try:
                                urlopen(durl)
                        except URLError as e:
                                pass
                        # Stop the depot daemon.
                        self.__depot_daemon_stop(depot_handle)

                        # Read the msgs from the err log file to verify log
                        # msgs.
                        with open(err_path, "r") as read_err:
                                msgs = read_err.readlines()
                        self.debug(durl)
                        self.debug("".join(msgs))
                        self.assertRegexp(msgs[-1], "\[[\w:/]+\]  Request "
                            "failed")
                except:
                        self.__depot_daemon_stop(depot_handle)
                        raise


if __name__ == "__main__":
        unittest.main()
