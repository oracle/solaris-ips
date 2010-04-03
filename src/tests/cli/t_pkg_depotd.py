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

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import httplib
import os
import shutil
import tempfile
import time
import unittest
import urllib
import urllib2
import urlparse

import pkg.depotcontroller as dc
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.p5i as p5i
import pkg.server.repositoryconfig as rcfg

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

        misc_files = [ "tmp/libc.so.1", "tmp/cat" ]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
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
                misc.versioned_urlopen(depot_url, "info", [0], plist[0])

        def test_bug_3739(self):
                """Verify that a depot will return a 400 (Bad Request) error
                whenever it is provided malformed FMRIs."""

                durl = self.dc.get_depot_url()

                for operation in ("info", "manifest"):
                        for entry in ("BRCMbnx", "BRCMbnx%40a",
                            "BRCMbnx%400.5.11%2C5.11-0.101%3A20081119T231649a"):
                                try:
                                        urllib2.urlopen("%s/%s/0/%s" % (durl,
                                            operation, entry))
                                except urllib2.HTTPError, e:
                                        if e.code != httplib.BAD_REQUEST:
                                                raise

        def test_bug_5366(self):
                """Publish a package with slashes in the name, and then verify
                that the depot manifest and info operations work regardless of
                the encoding."""
                depot_url = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(depot_url, self.system10)
                # First, try it un-encoded.
                misc.versioned_urlopen(depot_url, "info", [0], plist[0])
                misc.versioned_urlopen(depot_url, "manifest", [0], plist[0])
                # Second, try it encoded.
                misc.versioned_urlopen(depot_url, "info", [0],
                    urllib.quote(plist[0]))
                misc.versioned_urlopen(depot_url, "manifest", [0],
                    urllib.quote(plist[0]))

        def test_bug_5707(self):
                """Testing depotcontroller.refresh()."""

                depot_url = self.dc.get_depot_url()
                self.pkgsend_bulk(depot_url, self.foo10)

                self.image_create(depot_url)
                self.pkg("install foo")
                self.pkg("verify")

                depot_file_url = "file://%s" % self.dc.get_repodir()
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
                        urllib2.urlopen("%s/../../../../bin/pkg" % depot_url)
                except urllib2.HTTPError, e:
                        if e.code != httplib.NOT_FOUND:
                                raise

                f = urllib2.urlopen("%s/robots.txt" % depot_url)
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


class TestDepotController(pkg5unittest.CliTestCase):

        def setUp(self):
                pkg5unittest.CliTestCase.setUp(self)

                self.__dc = dc.DepotController()
                self.__pid = os.getpid()
                self.__dc.set_property("publisher", "prefix", "test")
                self.__dc.set_depotd_path(pkg5unittest.g_proto_area + \
                    "/usr/lib/pkg.depotd")
                self.__dc.set_depotd_content_root(pkg5unittest.g_proto_area + \
                    "/usr/share/lib/pkg")

                depotpath = os.path.join(self.test_root, "depot")
                logpath = os.path.join(self.test_root, self.id())

                try:
                        os.makedirs(depotpath, misc.PKG_DIR_MODE)
                except:
                        pass

                self.__dc.set_repodir(depotpath)
                self.__dc.set_logpath(logpath)

        def tearDown(self):
                pkg5unittest.CliTestCase.tearDown(self)
                self.__dc.kill()

        def testStartStop(self):
                self.__dc.set_port(12000)
                for i in range(0, 5):
                        self.__dc.start()
                        self.assert_(self.__dc.is_alive())
                        self.__dc.stop()
                        self.assert_(not self.__dc.is_alive())

        def test_cfg_file(self):
                cfg_file = os.path.join(self.test_root, "cfg2")
                fh = open(cfg_file, "w")
                fh.close()
                self.__dc.set_port(12000)
                self.__dc.set_cfg_file(cfg_file)
                self.__dc.start()

        def test_writable_root(self):
                """Tests whether the index and feed cache file are written to
                the writable root parameter."""
                self.make_misc_files(TestPkgDepot.misc_files)

                writable_root = os.path.join(self.test_root,
                    "writ_root")
                index_dir = os.path.join(writable_root, "index")
                feed = os.path.join(writable_root, "feed.xml")
                base_dir = os.path.join(self.test_root, "depot")
                o_index_dir = os.path.join(base_dir, "index")
                o_feed = os.path.join(base_dir, "feed.xml")

                timeout = 10

                def check_state(check_feed):
                        found = not os.path.exists(o_index_dir) and \
                            not os.path.exists(o_feed) and \
                            os.path.isdir(index_dir) and \
                            (not check_feed or os.path.isfile(feed))
                        start_time = time.time()
                        while not found and time.time() - start_time < timeout:
                                time.sleep(1)
                                found = not os.path.exists(o_index_dir) and \
                                    not os.path.exists(o_feed) and \
                                    os.path.isdir(index_dir) and \
                                    (not check_feed or os.path.isfile(feed))

                        self.assert_(not os.path.exists(o_index_dir))
                        self.assert_(not os.path.exists(o_feed))
                        self.assert_(os.path.isdir(index_dir))
                        if check_feed:
                                self.assert_(os.path.isfile(feed))
                def get_feed(durl):
                        start_time = time.time()
                        got = False
                        while not got and (time.time() - start_time) < timeout:
                                try:
                                        urllib2.urlopen("%s/feed" % durl)
                                        got = True
                                except urllib2.HTTPError:
                                        time.sleep(1)
                        self.assert_(got)

                self.__dc.set_port(12000)
                self.__dc.set_writable_root(writable_root)
                durl = self.__dc.get_depot_url()
                self.__dc.set_property("publisher", "prefix", "test")
                self.__dc.set_property("repository", "origins", durl)
                self.__dc.start()
                check_state(False)
                self.pkgsend_bulk(durl, TestPkgDepot.quux10)
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
                self.__dc.set_port(12000)
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
                self.__dc.set_port(12000)
                self.__dc.start()
                durl = self.__dc.get_depot_url()
                try:
                        urllib2.urlopen("%s/catalog/1/" % durl)
                except urllib2.HTTPError, e:
                        self.assertEqual(e.code, httplib.NOT_FOUND)
                self.__dc.stop()

                # For this disabled case, all /catalog/ operations should return
                # a NOT_FOUND error.
                self.__dc.set_disable_ops(["catalog"])
                self.__dc.set_port(12000)
                self.__dc.start()
                durl = self.__dc.get_depot_url()
                for ver in (0, 1):
                        try:
                                urllib2.urlopen("%s/catalog/%d/" % (durl, ver))
                        except urllib2.HTTPError, e:
                                self.assertEqual(e.code, httplib.NOT_FOUND)
                self.__dc.stop()

                # In the normal case, /catalog/1/ should return
                # a FORBIDDEN error.
                self.__dc.unset_disable_ops()
                self.__dc.start()
                durl = self.__dc.get_depot_url()
                try:
                        urllib2.urlopen("%s/catalog/1/" % durl)
                except urllib2.HTTPError, e:
                        self.assertEqual(e.code, httplib.FORBIDDEN)
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
                "alias": "pending",
                "prefix": "org.opensolaris.pending"
            },
            "repository": {
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
        }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)

                # All of the tests will start depot if needed.
                self.dc.stop()

                # Prevent override of custom configuration;
                # tests will set as needed.
                self.dc.clear_property("publisher", "prefix")

                # Set repository origins.
                self.repo_cfg["repository"]["origins"] = \
                    [self.dc.get_depot_url()]

                self.tpath = tempfile.mkdtemp(prefix="tpath",
                    dir=self.test_root)

        def test_0_depot_bui_output(self):
                """Verify that a non-error response and valid HTML is returned
                for each known BUI page in every available depot mode."""

                self.dc.set_property("publisher", "prefix", "test")

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

                for with_packages in (False, True):
                        shutil.rmtree(self.dc.get_repodir(),
                            ignore_errors=True)

                        if with_packages:
                                self.dc.set_readwrite()
                                self.dc.set_port(12000)
                                self.dc.start()
                                durl = self.dc.get_depot_url()
                                self.pkgsend_bulk(durl, self.info10 +
                                    self.quux10 + self.system10)
                                self.dc.stop()

                        for set_method, unset_method in mode_methods:
                                if set_method:
                                        getattr(self.dc, set_method)()

                                self.dc.set_port(12000)
                                self.dc.start()
                                durl = self.dc.get_depot_url()

                                for path in pages:
                                        # Any error responses will cause an
                                        # exception.
                                        response = urllib2.urlopen(
                                            "%s/%s" % (durl, path))

                                        fd, fpath = tempfile.mkstemp(
                                            suffix="html", dir=self.tpath)
                                        fp = os.fdopen(fd, "w")
                                        fp.write(response.read())
                                        fp.close()

                                        self.validate_html_file(fpath)

                                self.dc.stop()
                                if unset_method:
                                        getattr(self.dc, unset_method)()

        def __update_repo_config(self):
                """Helper function to generate test repository configuration."""
                # Find and load the repository configuration.
                rpath = self.dc.get_repodir()
                rcpath = os.path.join(rpath, "cfg_cache")

                rc = rcfg.RepositoryConfig(pathname=rcpath)

                # Update the configuration with our sample data.
                cfg = self.repo_cfg
                for section in cfg:
                        for prop in cfg[section]:
                                rc.set_property(section, prop,
                                    cfg[section][prop])

                # Save it.
                rc.write()

        def test_1_depot_publisher(self):
                """Verify the output of the depot /publisher operation."""

                # Now update the repository configuration while the depot is
                # stopped so changes won't be overwritten on exit.
                self.__update_repo_config()

                # Start the depot.
                self.dc.start()

                durl = self.dc.get_depot_url()
                purl = urlparse.urljoin(durl, "publisher/0")
                pub, pkglist = p5i.parse(location=purl)[0]

                # Now verify that the parsed response has the expected data.
                cfg = self.repo_cfg
                for prop in cfg["publisher"]:
                        self.assertEqual(getattr(pub, prop),
                            cfg["publisher"][prop])

                repo = pub.selected_repository
                for prop in cfg["repository"]:
                        returned = getattr(repo, prop)
                        expected = cfg["repository"][prop]
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
                """Verify the output of the depot /publisher operation."""

                # Now update the repository configuration while the depot is
                # stopped so changes won't be overwritten on exit.
                self.__update_repo_config()

                # Start the depot.
                self.dc.start()

                # Then, publish some packages we can abuse for testing.
                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.info10 + self.quux10 + \
                    self.system10 + self.zfsextras10 + self.zfsutils10)

                # Now, for each published package, attempt to get a p5i file
                # and then verify that the parsed response has the expected
                # package information under the expected publisher.
                for p in plist:
                        purl = urlparse.urljoin(durl, "p5i/0/%s" % p)
                        pub, pkglist = p5i.parse(location=purl)[0]

                        # p5i files contain non-qualified FMRIs as the FMRIs
                        # are already grouped by publisher.
                        nq_p = fmri.PkgFmri(p).get_fmri(anarchy=True,
                            include_scheme=False)
                        self.assertEqual(pkglist, [nq_p])

                # Try again, but only using package stems.
                for p in plist:
                        stem = fmri.PkgFmri(p).pkg_name
                        purl = urlparse.urljoin(durl, "p5i/0/%s" % stem)
                        pub, pkglist = p5i.parse(location=purl)[0]
                        self.assertEqual(pkglist, [stem])

                # Try again, but using wildcards (which will return a list of
                # matching package stems).
                purl = urlparse.urljoin(durl, "p5i/0/zfs*")
                pub, pkglist = p5i.parse(location=purl)[0]
                self.assertEqual(pkglist, ["zfs-extras", "zfs/utils"])

                # Finally, verify that a non-existent package will error out
                # with a httplib.NOT_FOUND.
                try:
                        urllib2.urlopen(urlparse.urljoin(durl,
                            "p5i/0/nosuchpackage"))
                except urllib2.HTTPError, e:
                        if e.code != httplib.NOT_FOUND:
                                raise


if __name__ == "__main__":
        unittest.main()
