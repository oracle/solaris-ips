#!/usr/bin/python
# -*- coding: utf-8 -*-
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
# Copyright (c) 2013, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import copy
import httplib
import os
import time
import unittest
import urllib2

import pkg.fmri

HTTPDEPOT_USER = "pkg5srv"

class TestHttpDepot(pkg5unittest.ApacheDepotTestCase):
        """Tests that exercise the pkg.depot-config CLI as well as checking the
        functionality of the depot-config itself. This test class will
        fail if not run as root, since many of the tests use 'pkg.depot-config -a'
        which will attempt to chown a directory to pkg5srv:pkg5srv.

        The default_svcs_conf having an instance name of 'usr' is not a
        coincidence: we use it there so that we catch RewriteRules that
        mistakenly try to serve content from the root filesystem ('/') rather
        than from beneath our DocumentRoot (assuming that test systems always
        have a /usr directory)
        """

        # An array that can be used to build our svcs(1) wrapper.
        default_svcs_conf = [
            # FMRI                                   STATE
            ["svc:/application/pkg/server:default",  "online" ],
            ["svc:/application/pkg/server:usr",      "online" ],
            # repositories that we will not serve
            ["svc:/application/pkg/server:off",      "offline"],
            ["svc:/application/pkg/server:writable", "online" ],
            ["svc:/application/pkg/server:solitary", "offline"]
        ]

        # An array that can be used to build our svcprop(1)
        # wrapper in conjunction with svcs_conf.  This array
        # must be in the same order as svcs_conf and the rows
        # must correspond.
        default_svcprop_conf = [
            # inst_root           readonly  standalone
            ["%(rdir1)s",         "true",   "false"   ],
            ["%(rdir2)s",         "true",   "false"   ],
            # we intentionally use non-existent repository
            # paths in these services, and check they aren't
            # present in the httpd.conf later.
            ["/pkg5/there/aint", "true",    "false",   "offline"],
            ["/pkg5/nobody/here", "false",   "false"  ],
            ["/pkg5/but/us/chickens",  "true",    "true"   ],
        ]

        sample_pkg = """
            open sample@1.0,5.11-0
            add file tmp/sample mode=0444 owner=root group=bin path=/usr/bin/sample
            close"""

        sample_pkg_11 = """
            open sample@1.1,5.11-0
            add file tmp/updated mode=0444 owner=root group=bin path=/usr/bin/sample
            close"""

        new_pkg = """
            open new@1.0,5.11-0
            add file tmp/new mode=0444 owner=root group=bin path=/usr/bin/new
            close"""

        another_pkg = """
            open another@1.0,5.11-0
            add file tmp/another mode=0444 owner=root group=bin path=/usr/bin/another
            close"""

        carrots_pkg = """
            open pkg://carrots/carrots@1.0,5.11-0
            add file tmp/another mode=0444 owner=root group=bin path=/usr/bin/carrots
            close"""

        misc_files = ["tmp/sample", "tmp/updated", "tmp/another", "tmp/new"]

        def setUp(self):
                self.sc = None
                pkg5unittest.ApacheDepotTestCase.setUp(self, ["test1", "test2"])
                self.rdir1 = self.dcs[1].get_repodir()
                self.rdir2 = self.dcs[2].get_repodir()

                self.default_depot_runtime = os.path.join(self.test_root,
                    "depot_runtime")
                self.default_depot_conf = os.path.join(
                    self.default_depot_runtime, "depot_httpd.conf")
                self.depot_conf_fragment = os.path.join(
                    self.default_depot_runtime, "depot.conf")

                self.depot_port = self.next_free_port
                self.next_free_port += 1
                self.make_misc_files(self.misc_files)
                self.__set_smf_state()

        def __set_smf_state(self, svcs_conf=default_svcs_conf,
            svcprop_conf=default_svcprop_conf):
                """Create wrapper scripts for svcprop and svcs based on the
                arrays of arrays passed in as arguments. By default, the
                following responses are configured using the class variables
                svcs_conf and svcprop_conf:

                pkg/server:default and pkg/server:usr can be served by the
                depot-config as they are marked readonly=true, standalone=false.

                pkg/server:off is ineligible, because it is reported as being
                offline for these tests.
                pkg/server:writable and pkg/server:solitary are both not
                eligible to be served by the depot, the former, because it
                is not marked as readonly, the latter because it is marked
                as standalone.
                """

                # we don't want to modify our arguments
                _svcs_conf = copy.deepcopy(svcs_conf)
                _svcprop_conf = copy.deepcopy(svcprop_conf)

                # ensure the arrays are the same length.
                self.assert_(len(_svcs_conf) == len(_svcprop_conf))

                for index, conf in enumerate(_svcs_conf):
                        fmri = conf[0]
                        state = conf[1]
                        _svcprop_conf[index].insert(0, fmri)
                        _svcprop_conf[index].insert(1, state)

                rdirs = {"rdir1": self.rdir1, "rdir2": self.rdir2}

                # construct two strings we can use as parameters to our
                # __svc*_template values
                _svcs_conf = " ".join(["%".join([value for value in item])
                    for item in _svcs_conf])
                _svcprop_conf = " ".join(["%".join(
                    [value % rdirs for value in item])
                    for item in _svcprop_conf])

                self.smf_cmds = {
                    "usr/bin/svcs": self.__svcs_template % _svcs_conf,
                    "usr/bin/svcprop": self.__svcprop_template % _svcprop_conf
                }
                self.make_misc_files(self.smf_cmds, "smf_cmds", mode=0755)

        def start_depot(self, build_indexes=True):
                hc = pkg5unittest.HttpDepotController(
                    self.default_depot_conf, self.depot_port,
                    self.default_depot_runtime, testcase=self)
                self.register_apache_controller("depot", hc)
                self.ac.start()
                if build_indexes:
                        # we won't return until indexes are built
                        u = urllib2.urlopen(
                            "%s/depot/depot-wait-refresh" % hc.url).close()

        def test_0_htdepot(self):
                """A basic test to see that we can start the depot,
                as part of this, by starting the depot, ApacheController will
                ping the "/ URI of the server."""

                # ensure we fail when not supplying the required argument
                self.depotconfig("", exit=2, fill_missing_args=False)
                self.depotconfig("")
                self.start_depot()

                # the httpd.conf should reference our repositories
                self.file_contains(self.ac.conf, self.rdir1)
                self.file_contains(self.ac.conf, self.rdir2)
                # it should not reference the repositories that we have
                # marked as offline, writable or standalone
                self.file_doesnt_contain(self.ac.conf, "/pkg5/there/aint")
                self.file_doesnt_contain(self.ac.conf, "/pkg5/nobody/here")
                self.file_doesnt_contain(self.ac.conf, "/pkg5/but/us/chickens")

        def test_1_htdepot_usage(self):
                """Tests that we show a usage message."""

                ret, output = self.depotconfig("", fill_missing_args=False,
                    out=True, exit=2)
                self.assert_("Usage:" in output,
                    "No usage string printed: %s" % output)
                ret, output = self.depotconfig("--help", out=True, exit=2)
                self.assert_("Usage:" in output,
                    "No usage string printed: %s" % output)

        def test_2_htinvalid_root(self):
                """We return an error given an invalid image root"""

                # check for incorrectly-formed -d options
                self.depotconfig("-d usr -F -r /dev/null", exit=2)

                # ensure we pick up invalid -d directories
                for invalid_root in ["usr=/dev/null",
                    "foo=/etc/passwd", "alt=/proc"]:
                        ret, output, err = self.depotconfig(
                            "-d %s -F" % invalid_root, out=True, stderr=True,
                            exit=1)
                        expected = invalid_root.split("=")[1]
                        self.assert_(expected in err,
                            "error message did not contain %s: %s" %
                            (expected, err))

                # ensure we also catch invalid SMF inst_roots
                svcs_conf = [["svc:/application/pkg/server:default", "online" ]]
                svcprop_conf = [["/tmp", "true", "false"]]
                self.__set_smf_state(svcs_conf, svcprop_conf)
                ret, output, err = self.depotconfig("", out=True, stderr=True,
                    exit=1)
                self.assert_("/tmp" in err, "error message did not contain "
                    "/tmp")

        def test_3_invalid_htcache_dir(self):
                """We return an error given an invalid cache_dir"""

                for invalid_cache in ["/dev/null", "/etc/passwd"]:
                        ret, output, err = self.depotconfig("-c %s" %
                            invalid_cache, out=True, stderr=True, exit=1)
                        self.assert_(invalid_cache in err, "error message "
                            "did not contain %s: %s" % (invalid_cache, err))

        def test_4_invalid_hthostname(self):
                """We return an error given an invalid hostname"""

                for invalid_host in ["1.2.3.4.5.6", "pkgsysrepotestname", "."]:
                        ret, output, err = self.depotconfig("-h %s" %
                            invalid_host, out=True, stderr=True, exit=1)
                        self.assert_(invalid_host in err, "error message "
                            "did not contain %s: %s" % (invalid_host, err))

        def test_5_invalid_htlogs_dir(self):
                """We return an error given an invalid logs_dir"""

                for invalid_log in ["/dev/null", "/etc/passwd"]:
                        ret, output, err = self.depotconfig("-l %s" % invalid_log,
                            out=True, stderr=True, exit=1)
                        self.assert_(invalid_log in err, "error message "
                            "did not contain %s: %s" % (invalid_log, err))

                for invalid_log in ["/proc"]:
                        port = self.next_free_port
                        self.depotconfig("-l %s -p %s" % (invalid_log, port),
                            exit=0)
                        self.assertRaises(pkg5unittest.ApacheStateException,
                            self.start_depot)

        def test_6_invalid_htport(self):
                """We return an error given an invalid port"""

                for invalid_port in [999999, "bobcat", "-1234"]:
                        ret, output, err = self.depotconfig("-p %s" % invalid_port,
                            out=True, stderr=True, exit=1)
                        self.assert_(str(invalid_port) in err, "error message "
                            "did not contain %s: %s" % (invalid_port, err))

        def test_7_invalid_htruntime_dir(self):
                """We return an error given an invalid runtime_dir"""

                for invalid_runtime in ["/dev/null", "/etc/passwd", "/proc"]:
                        ret, output, err = self.depotconfig("-r %s" %
                            invalid_runtime, out=True, stderr=True, exit=1)
                        self.assert_(invalid_runtime in err, "error message "
                            "did not contain %s: %s" % (invalid_runtime, err))

        def test_8_invalid_htcache_size(self):
                """We return an error given an invalid cache_size"""

                for invalid_csize in ["cats", "-1234"]:
                        ret, output, err = self.depotconfig(
                            "-s %s" % invalid_csize, out=True, stderr=True,
                            exit=1)
                        self.assert_(str(invalid_csize) in err, "error message "
                            "did not contain %s: %s" % (invalid_csize, err))

        def test_9_invalid_httemplates_dir(self):
                """We return an error given an invalid templates_dir"""

                for invalid_tmp in ["/dev/null", "/etc/passwd", "/proc"]:
                        ret, output, err = self.depotconfig("-T %s" % invalid_tmp,
                            out=True, stderr=True, exit=1)
                        self.assert_(invalid_tmp in err, "error message "
                            "did not contain %s: %s" % (invalid_tmp, err))

        def test_9_invalid_httemplates_dir(self):
                """We return an error given an invalid templates_dir"""

                for invalid_tmp in ["/dev/null", "/etc/passwd", "/proc"]:
                        ret, output, err = self.depotconfig("-T %s" % invalid_tmp,
                            out=True, stderr=True, exit=1)
                        self.assert_(invalid_tmp in err, "error message "
                            "did not contain %s: %s" % (invalid_tmp, err))

        def test_10_httype(self):
                """We return an error given an invalid type option."""

                invalid_type = "weblogic"
                ret, output, err = self.depotconfig("-t %s" % invalid_type,
                    out=True, stderr=True, exit=2)
                self.assert_(invalid_type in err, "error message "
                    "did not contain %s: %s" % (invalid_type, err))
                # ensure we work with the supported type
                self.depotconfig("-t apache2")

        def test_11_htbui(self):
                """We can perform a series of HTTP requests against the BUI."""

                fmris = self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.new_pkg)
                r2_fmris = self.pkgsend_bulk(self.dcs[2].get_repo_url(),
                    self.sample_pkg)
                self.depotconfig("")
                self.start_depot()

                fmri = pkg.fmri.PkgFmri(fmris[0])
                esc_full_fmri = fmri.get_url_path()

                conf = {"prefix": "default",
                    "esc_full_fmri": esc_full_fmri}

                # a series of BUI paths we should be able to access
                paths = [
                        "/",
                        "/default/test1",
                        "/default/en",
                        "/default/en/index.shtml",
                        "/default/en/catalog.shtml",
                        "/default/p5i/0/new.p5i",
                        "/default/info/0/%(esc_full_fmri)s",
                        "/default/test1/info/0/%(esc_full_fmri)s",
                        "/default/manifest/0/%(esc_full_fmri)s",
                        "/default/en/search.shtml",
                        "/usr/test2/en/catalog.shtml",
                        "/depot/default/en/search.shtml?token=pkg&action=Search"
                ]

                def get_url(url_path):
                        try:
                                url_obj = urllib2.urlopen(url_path, timeout=10)
                                self.assert_(url_obj.code == 200,
                                    "Failed to open %s: %s" % (url_path,
                                    url_obj.code))
                                url_obj.close()
                        except urllib2.HTTPError, e:
                                self.debug("Failed to open %s: %s" %
                                    (url_path, e))
                                raise

                for p in paths:
                        get_url("%s%s" % (self.ac.url, p % conf))

                self.ac.stop()

                # test that pkg.depot-config detects missing repos
                broken_rdir = self.rdir2 + "foo"
                os.rename(self.rdir2, broken_rdir)
                self.depotconfig("", exit=1)

                # test that when we break one of the repositories we're
                # serving, that the remaining repositories are still accessible
                # from the bui. We need to fix the repo dir before rebuilding
                # the configuration, then break it once the depot has started
                os.rename(broken_rdir, self.rdir2)
                self.depotconfig("")
                os.rename(self.rdir2, broken_rdir)
                self.start_depot(build_indexes=False)

                # check the first request to the BUI works as expected
                get_url(self.ac.url)

                # and check that we get a 404 for the missing repo
                bad_url = "%s/usr/test2/en/catalog.shtml" % self.ac.url
                raised_404 = False
                try:
                        url_obj = urllib2.urlopen(bad_url, timeout=10)
                        url_obj.close()
                except urllib2.HTTPError, e:
                        if e.code == 404:
                                raised_404 = True
                self.assert_(raised_404, "Didn't get a 404 opening %s" %
                    bad_url)

                # check that we can still reach other valid paths
                paths = [
                        "/",
                        "/default/test1",
                        "/default/en",
                        "/default/en/index.shtml",
                        "/default/en/catalog.shtml",
                        "/default/p5i/0/new.p5i",
                        "/default/info/0/%(esc_full_fmri)s",
                        "/default/test1/info/0/%(esc_full_fmri)s",
                        "/default/manifest/0/%(esc_full_fmri)s",
                        "/default/en/search.shtml",
                ]
                for p in paths:
                        self.debug(p)
                        get_url("%s%s" % (self.ac.url, p % conf))
                os.rename(broken_rdir, self.rdir2)

        def test_12_htpkgclient(self):
                """A depot-config can act as a repository server for pkg(1)
                clients, with all functionality supported."""

                # publish some sample packages to our repositories
                for dc_num in self.dcs:
                        rurl = self.dcs[dc_num].get_repo_url()
                        self.pkgsend_bulk(rurl, self.sample_pkg)
                        self.pkgsend_bulk(rurl, self.sample_pkg_11)
                self.pkgsend_bulk(self.dcs[2].get_repo_url(), self.new_pkg)

                self.depotconfig("")
                self.image_create()
                self.start_depot()
                # test that we can access the default publisher
                self.pkg("set-publisher -p %s/default" % self.ac.url)
                self.pkg("publisher")
                self.pkg("install sample@1.0")
                self.file_contains("usr/bin/sample", "tmp/sample")
                self.pkg("update")
                self.file_contains("usr/bin/sample", "tmp/updated")

                # test that we can access specific publishers, this time from
                # a different repository, served by the same depot-config.
                self.pkg("set-publisher -p %s/usr/test2" % self.ac.url)
                self.pkg("contents -r new")
                self.pkg("set-publisher -G '*' test2")
                ret, output = self.pkg(
                    "search -o action.raw -s %s/usr new" % self.ac.url,
                    out=True)
                self.assert_("path=usr/bin/new" in output)

                # publish a new package, and ensure we can install it
                self.pkgsend_bulk(self.dcs[1].get_repo_url(), self.another_pkg)
                self.pkg("install another")
                self.file_contains("usr/bin/another", "tmp/another")

                # add a new publisher to an existing repository and ensure it
                # is visible from the repository
                self.ac.stop()
                self.pkgrepo("-s %s add-publisher carrots" % self.rdir1)
                self.pkgsend_bulk(self.dcs[1].get_repo_url(), self.carrots_pkg)
                self.depotconfig("")
                self.start_depot()

                self.pkg("set-publisher -g %s/default/carrots carrots" %
                    self.ac.url)

        def test_13_htpkgrecv(self):
                """A depot-config can act as a repository server for pkgrecv(1)
                clients."""

                rurl = self.dcs[1].get_repo_url()
                first = self.pkgsend_bulk(rurl, self.sample_pkg)
                second = self.pkgsend_bulk(rurl, self.sample_pkg_11)
                self.pkgsend_bulk(self.dcs[2].get_repo_url(), self.new_pkg)

                # gather the FMRIs we published and the URL-quoted version
                first_fmri = pkg.fmri.PkgFmri(first[0])
                second_fmri = pkg.fmri.PkgFmri(second[0])
                first_ver = urllib2.quote(str(first_fmri.version))
                second_ver = urllib2.quote(str(second_fmri.version))

                self.depotconfig("")
                self.image_create()
                self.start_depot()

                ret, output = self.pkgrecv(command="-s %s/default --newest" %
                    self.ac.url, out=True)
                self.assert_(str(second[0]) in output)
                dest = os.path.join(self.test_root, "test_13_hgpkgrecv")
                os.mkdir(dest)

                # pull down raw package contents
                self.pkgrecv(command="-s %s/default -m all-versions --raw "
                    "-d %s '*'" % (self.ac.url, dest))

                # Quickly sanity check the contents
                self.assert_(os.listdir(dest) == ["sample"])
                self.assert_(
                    set(os.listdir(os.path.join(dest, "sample"))) ==
                    set([first_ver, second_ver]))

                # grab one of the manifests we just downloaded, and check that
                # the file content is present and correct.
                mf_path = os.path.sep.join([dest, "sample", second_ver])
                mf = pkg.manifest.Manifest()
                mf.set_content(pathname=os.path.join(mf_path, "manifest.file"))
                f_ac = mf.actions[0]
                self.assert_(f_ac.attrs["path"] == "usr/bin/sample")
                f_path = os.path.join(mf_path, f_ac.hash)
                os.path.exists(f_path)
                self.file_contains(f_path, "tmp/updated")

        def test_14_htpkgrepo(self):
                """Test that only the 'pkgrepo refresh' command works with the
                depot-config only when the -A flag is enabled. Test that
                the index does indeed get updated when a refresh is performed
                and that new package contents are visible."""

                rurl = self.dcs[1].get_repo_url()
                self.pkgsend_bulk(rurl, self.sample_pkg)
                # allow index refreshes
                self.depotconfig("-A")
                self.start_depot()
                self.image_create()
                depot_url = "%s/default" % self.ac.url

                # verify that list commands work
                ret, output = self.pkgrepo("-s %s list -F tsv" % depot_url,
                    out=True)
                self.assert_("pkg://test1/sample@1.0" in output)
                self.assert_("pkg://test1/new@1.0" not in output)

                # rebuild, remove and set commands should fail, the latter two
                # with exit code 2
                self.pkgrepo("-s %s rebuild" % depot_url, exit=1)
                self.pkgrepo("-s %s remove sample" % depot_url, exit=2)
                self.pkgrepo("-s %s set -p test1 foo/bar=baz" % depot_url,
                    exit=2)

                # verify search works for packages in the repository
                self.pkg("set-publisher -p %s" % depot_url)
                self.pkg("search -s %s msgsh" % "%s" % depot_url,
                    exit=1)
                self.pkg("search -s %s /usr/bin/sample" % depot_url)

                # publish a new package, and verify it doesn't appear in the
                # search results
                self.pkgsend_bulk(rurl, self.new_pkg)
                self.pkg("search -s %s /usr/bin/new" % depot_url, exit=1)

                # refresh the index
                self.pkgrepo("-s %s refresh" % depot_url)
                # there isn't a synchronous option to pkgrepo, so wait a bit
                # then make sure we do see this new package.
                time.sleep(3)
                ret, output = self.pkg("search -s %s /usr/bin/new" % depot_url,
                    out=True)
                self.assert_("usr/bin/new" in output)
                ret, output = self.pkgrepo("-s %s list -F tsv" % depot_url,
                    out=True)
                self.assert_("pkg://test1/sample@1.0" in output)
                self.assert_("pkg://test1/new@1.0" in output)

                # ensure that refresh --no-catalog works, but refresh --no-index
                # does not.
                self.pkgrepo("-s %s refresh --no-catalog" % depot_url)
                self.pkgrepo("-s %s refresh --no-index" % depot_url, exit=1)

                # check that when we start the depot without -A, we cannot
                # issue refresh commands.
                self.depotconfig("")
                self.start_depot()
                self.pkgrepo("-s %s refresh" % depot_url, exit=1)

        def test_15_htheaders(self):
                """Test that the correct Content-Type and Cache-control headers
                are sent from the depot for the responses that we care about."""

                fmris = self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.sample_pkg)
                self.depotconfig("")
                self.start_depot()
                # create an image so we have something to search with
                # (bug 15807844) then retrieve the hash of a file we have
                # published
                self.image_create()
                self.pkg("set-publisher -p %s/default" % self.ac.url)
                ret, output = self.pkg("search -H -o action.hash "
                     "-r /usr/bin/sample", out=True)
                file_hash = output.strip()

                fmri = pkg.fmri.PkgFmri(fmris[0])
                esc_short_fmri = fmri.get_fmri(anarchy=True).replace(
                    "pkg:/", "")
                esc_short_fmri = esc_short_fmri.replace(",", "%2C")
                esc_short_fmri = esc_short_fmri.replace(":", "%3A")

                # a dictionary of paths we should be able to access, along with
                # expected header (name,value) pairs for each
                paths = {
                    "/default/p5i/0/sample.p5i":
                    [("Content-Type", "application/vnd.pkg5.info")],
                    "/default/catalog/1/catalog.attrs":
                    [("Cache-Control", "no-cache")],
                    "/default/manifest/0/%s" % esc_short_fmri:
                    [("Cache-Control",
                    "must-revalidate, no-transform, max-age=31536000"),
                    ("Content-Type", "text/plain;charset=utf-8")],
                    "/default/search/1/False_2_None_None_%3a%3a%3asample":
                    [("Cache-Control", "no-cache"),
                    ("Content-Type", "text/plain;charset=utf-8")],
                    "/default/file/1/%s" % file_hash:
                    [("Cache-Control",
                    "must-revalidate, no-transform, max-age=31536000"),
                    ("Content-Type", "application/data")]
                }

                def header_contains(url, header, value):
                        """Check that HTTP 'header' from 'url' contains an
                        expected value 'value'."""
                        ret = False
                        try:
                                u = urllib2.urlopen(url)
                                h = u.headers.get(header, "")
                                if value in h:
                                        return True
                        except Exception, e:
                                self.assert_(False, "Error opening %s: %s" %
                                    (url, e))
                        return ret

                for path in paths:
                        for headers in paths[path]:
                                name, value = headers
                                url = "%s%s" % (self.ac.url, path)
                                self.assert_(header_contains(url, name, value),
                                    "%s did not contain the header %s=%s" %
                                    (url, name, value))

        def test_16_htfragment(self):
                """Test that the fragment httpd.conf generated by pkg.depot-config
                can be used in a standard Apache configuration, but that
                pkg(1) admin and search operations fail."""

                self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.sample_pkg)
                self.pkgrepo("-s %s add-publisher carrots" %
                    self.dcs[1].get_repo_url())
                self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.carrots_pkg)
                self.pkgsend_bulk(self.dcs[2].get_repo_url(),
                    self.new_pkg)
                self.depotconfig("-l %s -F -d usr=%s -d spaghetti=%s "
                    "-P testpkg5" %
                    (self.default_depot_runtime, self.rdir1, self.rdir2))
                default_httpd_conf_path = os.path.join(self.test_root,
                    "default_httpd.conf")
                httpd_conf = open(default_httpd_conf_path, "w")
                httpd_conf.write(self.__default_httpd_conf %
                    {"port": self.depot_port,
                    "depot_conf": self.depot_conf_fragment,
                    "runtime_dir": self.default_depot_runtime})
                httpd_conf.close()

                # Start an Apache instance
                ac = pkg5unittest.ApacheController(default_httpd_conf_path,
                    self.depot_port, self.default_depot_runtime, testcase=self)
                self.register_apache_controller("depot", ac)
                ac.start()

                # verify the instance is definitely the one using our custom
                # httpd.conf
                u = urllib2.urlopen("%s/pkg5test-server-status" % self.ac.url)
                self.assert_(u.code == httplib.OK,
                    "Error getting pkg5-server-status")

                self.image_create()
                # add publishers for the two repositories being served by this
                # Apache instance
                self.pkg("set-publisher -p %s/testpkg5/usr" % self.ac.url)
                self.pkg("set-publisher -p %s/testpkg5/spaghetti" % self.ac.url)
                # install packages from the two different publishers in the
                # first repository
                self.pkg("install sample")
                self.pkg("install carrots")
                # install a package from the second repository
                self.pkg("install new")
                # we can't perform remote search or admin operations, since
                # we've no supporting mod_wsgi process.
                self.pkg("search -r new", exit=1)
                self.pkgrepo("-s %s/testpkg5/usr refresh" %
                    self.ac.url, exit=1)

        __svcs_template = \
"""#!/usr/bin/ksh93
#
# This script produces false svcs(1) output, using
# a list of space separated strings, with each string
# of the format <fmri>%%<state>
#
# Since the string here is generated from a Python program, we have to escape
# all 'percent' characters.
#
# eg.
# SERVICE_STATUS="svc:/application/pkg/server:foo%%online svc:/application/pkg/server:default%%offline svc:/application/pkg/server:usr%%online"
# We expect to be called with 'svcs -H -o fmri <fmri>' but completely ignore
# the <fmri> argument.
#
SERVICE_STATUS="%s"

set -- `getopt o:H $*`
for i in $* ; do
    case $i in
        -H)    minus_h=$i; shift;;
        -o)    minus_o=$2; shift;;
        *)     break;;
    esac
done

if [ "${minus_o}" ]; then
    if [ -z "${minus_h}" ]; then
        echo "FMRI"
    fi
    for service in $SERVICE_STATUS ; do
        echo $service | sed -e 's/%%/ /' | read fmri state
        echo $fmri
    done
    exit 0
fi

if [ -z "${minus_h}" ]; then
    printf "%%-14s%%6s    %%s\n" STATE STIME FMRI
fi
for service in $SERVICE_STATUS ; do
    echo $service | sed -e 's/%%/ /' | read fmri state
    printf "%%-14s%%9s %%s\n" $state 00:00:00 $fmri
done
"""

        __svcprop_template = \
"""#!/usr/bin/ksh93
#
# This script produces false svcprop(1) output, using
# a list of space separated strings, with each string
# of the format <fmri>%%<state>%%<inst_root>%%<readonly>%%<standalone>
#
# eg.
# SERVICE_PROPS="svc:/application/pkg/server:foo%%online%%/space/repo%%true%%false"
#
# we expect to be called as "svcprop -c -p <property> <fmri>"
# which is enough svcprop(1) functionalty for these tests. Any other
# command line options will cause us to return nonsense.
#

typeset -A prop_state
typeset -A prop_readonly
typeset -A prop_inst_root
typeset -A prop_standalone

SERVICE_PROPS="%s"
for service in $SERVICE_PROPS ; do
        echo $service | sed -e 's/%%/ /g' | \
            read fmri state inst_root readonly standalone
        # create a hashable version of the FMRI
        fmri=$(echo $fmri | sed -e 's/\///g' -e 's/://g')
        prop_state[$fmri]=$state
        prop_inst_root[$fmri]=$inst_root
        prop_readonly[$fmri]=$readonly
        prop_standalone[$fmri]=$standalone
done


FMRI=$(echo $4 | sed -e 's/\///g' -e 's/://g')
case $3 in
        "pkg/inst_root")
                echo ${prop_inst_root[$FMRI]}
                ;;
        "pkg/readonly")
                echo ${prop_readonly[$FMRI]}
                ;;
        "pkg/standalone")
                echo ${prop_standalone[$FMRI]}
                ;;
        "restarter/state")
                echo ${prop_state[$FMRI]}
                ;;
        *)
                echo "Completely bogus svcprop output. Sorry."
esac
"""

        # A very minimal httpd.conf, which contains an Include directive
        # that we will use to reference our pkg5 depot-config.conf file. We leave
        # an Alias pointing to /server-status to make this server distinctive
        # for this test case.
        __default_httpd_conf = \
"""ServerRoot "/usr/apache2/2.2"
PidFile "%(runtime_dir)s/default_httpd.pid"
Listen %(port)s
<IfDefine 64bit>
Include /etc/apache2/2.2/conf.d/modules-64.load
</IfDefine>
<IfDefine !64bit>
Include /etc/apache2/2.2/conf.d/modules-32.load
</IfDefine>

User webservd
Group webservd
ServerAdmin you@yourhost.com
ServerName 127.0.0.1
DocumentRoot "/var/apache2/2.2/htdocs"
<Directory "/var/apache2/2.2/htdocs">
    Options Indexes FollowSymLinks
    AllowOverride None
    Order allow,deny
    Allow from all
</Directory>
<IfModule dir_module>
    DirectoryIndex index.html
</IfModule>
LogFormat \"%%h %%l %%u %%t \\\"%%r\\\" %%>s %%b\" common
ErrorLog "%(runtime_dir)s/error_log"
CustomLog "%(runtime_dir)s/access_log" common
LogLevel debug
DefaultType text/plain
# Reference the depot.conf file generated by pkg.depot-config, which makes this
# web server into something that can serve pkg(5) repositories.
Include %(depot_conf)s
SSLRandomSeed startup builtin
SSLRandomSeed connect builtin
# We enable server-status here, using /pkg5test-server-status to it to make the
# URI distinctive.
<Location /pkg5test-server-status>
    SetHandler server-status
</Location>
"""

if __name__ == "__main__":
        unittest.main()
