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

# Copyright (c) 2011, 2012, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import errno
import hashlib
import imp
import os
import os.path
import pkg.p5p
import shutil
import unittest
import urllib2
import shutil
import simplejson
import stat
import time

import pkg.portable as portable

SYSREPO_USER = "pkg5srv"

class TestBasicSysrepoCli(pkg5unittest.CliTestCase):
        """Some basic tests checking that we can deal with all of our arguments
        and that we handle invalid input correctly."""

        def setUp(self):
                self.sc = None
                pkg5unittest.CliTestCase.setUp(self)
                self.image_create()
                self.default_sc_runtime = os.path.join(self.test_root,
                    "sysrepo_runtime")
                self.default_sc_conf = os.path.join(self.default_sc_runtime,
                    "sysrepo_httpd.conf")

        def tearDown(self):
                try:
                        pkg5unittest.CliTestCase.tearDown(self)
                finally:
                        if self.sc:
                                self.debug("stopping sysrepo")
                                try:
                                        self.sc.stop()
                                except Exception, e:
                                        try:
                                                self.debug("killing sysrepo")
                                                self.sc.kill()
                                        except Exception, e:
                                                pass

        def _start_sysrepo(self, runtime_dir=None):
                if not runtime_dir:
                        runtime_dir = self.default_sc_runtime
                self.sysrepo_port = self.next_free_port
                self.next_free_port += 1
                self.sc = pkg5unittest.SysrepoController(self.default_sc_conf,
                    self.sysrepo_port, runtime_dir, testcase=self)
                self.sc.start()

        def test_0_sysrepo(self):
                """A very basic test to see that we can start the sysrepo."""

                # ensure we fail when not supplying the required argument
                self.sysrepo("", exit=2, fill_missing_args=False)

                self.sysrepo("")
                self._start_sysrepo()
                self.sc.stop()

        def test_1_sysrepo_usage(self):
                """Tests that we show a usage message."""

                ret, output = self.sysrepo("--help", out=True, exit=2)
                self.assert_("Usage:" in output,
                    "No usage string printed: %s" % output)

        def test_2_invalid_root(self):
                """We return an error given an invalid image root"""

                for invalid_root in ["/dev/null", "/etc/passwd", "/proc"]:
                        ret, output, err = self.sysrepo("-R %s" % invalid_root,
                            out=True, stderr=True, exit=1)
                        self.assert_(invalid_root in err, "error message "
                            "did not contain %s: %s" % (invalid_root, err))

        def test_3_invalid_cache_dir(self):
                """We return an error given an invalid cache_dir"""

                for invalid_cache in ["/dev/null", "/etc/passwd"]:
                        ret, output, err = self.sysrepo("-c %s" % invalid_cache,
                            out=True, stderr=True, exit=1)
                        self.assert_(invalid_cache in err, "error message "
                            "did not contain %s: %s" % (invalid_cache, err))

        def test_4_invalid_hostname(self):
                """We return an error given an invalid hostname"""

                for invalid_host in ["1.2.3.4.5.6", "pkgsysrepotestname", "."]:
                        ret, output, err = self.sysrepo("-h %s" % invalid_host,
                            out=True, stderr=True, exit=1)
                        self.assert_(invalid_host in err, "error message "
                            "did not contain %s: %s" % (invalid_host, err))

        def test_5_invalid_logs_dir(self):
                """We return an error given an invalid logs_dir"""

                for invalid_log in ["/dev/null", "/etc/passwd"]:
                        ret, output, err = self.sysrepo("-l %s" % invalid_log,
                            out=True, stderr=True, exit=1)
                        self.assert_(invalid_log in err, "error message "
                            "did not contain %s: %s" % (invalid_log, err))

                for invalid_log in ["/proc"]:
                        port = self.next_free_port
                        ret, output, err = self.sysrepo("-l %s -p %s" %
                            (invalid_log, port), out=True, stderr=True, exit=0)
                        self.assertRaises(pkg5unittest.SysrepoStateException,
                            self._start_sysrepo)
                        self.sc.stop()

        def test_6_invalid_port(self):
                """We return an error given an invalid port"""

                for invalid_port in [999999, "bobcat", "-1234"]:
                        ret, output, err = self.sysrepo("-p %s" % invalid_port,
                            out=True, stderr=True, exit=1)
                        self.assert_(str(invalid_port) in err, "error message "
                            "did not contain %s: %s" % (invalid_port, err))

        def test_7_invalid_runtime_dir(self):
                """We return an error given an invalid runtime_dir"""

                for invalid_runtime in ["/dev/null", "/etc/passwd", "/proc"]:
                        ret, output, err = self.sysrepo("-r %s" %
                            invalid_runtime, out=True, stderr=True, exit=1)
                        self.assert_(invalid_runtime in err, "error message "
                            "did not contain %s: %s" % (invalid_runtime, err))

        def test_8_invalid_cache_size(self):
                """We return an error given an invalid cache_size"""

                for invalid_csize in [0, "cats", "-1234"]:
                        ret, output, err = self.sysrepo("-s %s" % invalid_csize,
                            out=True, stderr=True, exit=1)
                        self.assert_(str(invalid_csize) in err, "error message "
                            "did not contain %s: %s" % (invalid_csize, err))

        def test_9_invalid_templates_dir(self):
                """We return an error given an invalid templates_dir"""

                for invalid_tmp in ["/dev/null", "/etc/passwd", "/proc"]:
                        ret, output, err = self.sysrepo("-t %s" % invalid_tmp,
                            out=True, stderr=True, exit=1)
                        self.assert_(invalid_tmp in err, "error message "
                            "did not contain %s: %s" % (invalid_tmp, err))

        def test_10_invalid_http_timeout(self):
                """We return an error given an invalid http_timeout"""

                for invalid_time in ["cats", "0", "-1"]:
                        ret, output, err = self.sysrepo("-T %s" %invalid_time,
                            out=True, stderr=True, exit=1)
                        self.assert_("http_timeout" in err, "error message "
                             "did not contain http_timeout: %s" % err)

        def test_11_invalid_proxies(self):
                """We return an error given invalid proxies"""

                for invalid_proxy in ["http://", "https://foo.bar", "-1"]:
                        ret, output, err = self.sysrepo("-w %s" % invalid_proxy,
                            out=True, stderr=True, exit=1)
                        self.assert_("http_proxy" in err, "error message "
                             "did not contain http_proxy: %s" % err)
                        ret, output, err = self.sysrepo("-W %s" % invalid_proxy,
                            out=True, stderr=True, exit=1)
                        self.assert_("https_proxy" in err, "error message "
                             "did not contain https_proxy: %s" % err)


class TestDetailedSysrepoCli(pkg5unittest.ManyDepotTestCase):

        persistent_setup = True

        sample_pkg = """
            open sample@1.0,5.11-0
            add file tmp/sample_file mode=0444 owner=root group=bin path=/usr/bin/sample
            close"""

        new_pkg = """
            open new@1.0,5.11-0
            add file tmp/sample_file mode=0444 owner=root group=bin path=/usr/bin/new
            close"""

        misc_files = ["tmp/sample_file"]

        def setUp(self):
                self.sc = None
                # see test_7_response_overlaps
                self.overlap_pubs = ["versions", "versionsX", "syspub",
                    "Xsyspub"]
                pubs = ["test1", "test2"]
                pubs.extend(self.overlap_pubs)
                pkg5unittest.ManyDepotTestCase.setUp(self, pubs,
                    start_depots=True)
                self.sc = None
                self.default_sc_runtime = os.path.join(self.test_root,
                    "sysrepo_runtime")
                self.default_sc_conf = os.path.join(self.default_sc_runtime,
                    "sysrepo_httpd.conf")
                self.make_misc_files(self.misc_files)
                self.durl1 = self.dcs[1].get_depot_url()
                self.rurl1 = self.dcs[1].get_repo_url()
                for dc_num in self.dcs:
                        durl = self.dcs[dc_num].get_depot_url()
                        self.pkgsend_bulk(durl, self.sample_pkg)

        def killalldepots(self):
                try:
                        pkg5unittest.ManyDepotTestCase.killalldepots(self)
                finally:
                        if self.sc:
                                self.debug("stopping sysrepo")
                                try:
                                        self.sc.stop()
                                except Exception, e:
                                        try:
                                                self.debug("killing sysrepo")
                                                self.sc.kill()
                                        except Exception, e:
                                                pass

        def _start_sysrepo(self, runtime_dir=None):
                if not runtime_dir:
                        runtime_dir = self.default_sc_runtime
                self.sysrepo_port = self.next_free_port
                self.next_free_port += 1
                self.sc = pkg5unittest.SysrepoController(self.default_sc_conf,
                    self.sysrepo_port, runtime_dir, testcase=self)
                self.sc.start()

        def test_1_substring_proxy(self):
                """We can proxy publishers that are substrings of each other"""
                # XXX not implemented yet
                pass

        def test_2_invalid_proxy(self):
                """We return an invalid response for urls we don't proxy"""
                # XXX not implemented yet
                pass

        def test_3_cache_dir(self):
                """Our cache_dir value is used"""

                self.image_create(prefix="test1", repourl=self.durl1)

                cache_dir = os.path.join(self.test_root, "t_sysrepo_cache")
                port = self.next_free_port
                self.sysrepo("-R %s -c %s -p %s" % (self.get_img_path(),
                    cache_dir, port))
                self._start_sysrepo()

                # 1. grep for the Cache keyword in the httpd.conf
                self.file_contains(self.default_sc_conf, "CacheEnable disk /")
                self.file_doesnt_contain(self.default_sc_conf,
                    "CacheEnable mem")
                self.file_doesnt_contain(self.default_sc_conf, "MCacheSize")
                self.file_contains(self.default_sc_conf, "CacheRoot %s" %
                    cache_dir)

                # 2. publish a file, then install using the proxy
                # check that the proxy has written some content into the cache
                # XXX not implemented yet.
                self.sc.stop()

                # 3. use urllib to pull the url for the file again, verify
                # we've got a cache header on the HTTP response
                # XXX not implemented yet.

                # 4. ensure memory and None settings are written
                cache_dir = "None"
                self.sysrepo("-c %s -p %s" % (cache_dir, port))
                self.file_doesnt_contain(self.default_sc_conf, "CacheEnable")

                cache_dir = "memory"
                self.sysrepo("-c %s -p %s" % (cache_dir, port))
                self.file_doesnt_contain(self.default_sc_conf,
                    "CacheEnable disk")
                self.file_contains(self.default_sc_conf, "CacheEnable mem")
                self.file_contains(self.default_sc_conf, "MCacheSize")

        def test_4_logs_dir(self):
                """Our logs_dir value is used"""

                self.image_create(prefix="test1", repourl=self.durl1)

                logs_dir = os.path.join(self.test_root, "t_sysrepo_logs")
                port = self.next_free_port
                self.sysrepo("-l %s -p %s" % (logs_dir, port))
                self._start_sysrepo()

                # 1. grep for the logs dir in the httpd.conf
                self.file_contains(self.default_sc_conf,
                    "ErrorLog \"%s/error_log\"" % logs_dir)
                self.file_contains(self.default_sc_conf,
                    "CustomLog \"%s/access_log\"" % logs_dir)
                # 2. verify our log files exist once the sysrepo has started
                for name in ["error_log", "access_log"]:
                        os.path.exists(os.path.join(logs_dir, name))
                self.sc.stop()

        def test_5_port_host(self):
                """Our port value is used"""
                self.image_create(prefix="test1", repourl=self.durl1)

                port = self.next_free_port
                self.sysrepo("-p %s -h localhost" % port)
                self._start_sysrepo()
                self.file_contains(self.default_sc_conf, "Listen localhost:%s" %
                    port)
                self.sc.stop()

        def test_6_permissions(self):
                """Our permissions are correct on all generated files"""

                # 1. check the permissions
                # XXX not implemented yet.
                pass

        def test_7_response_overlaps(self):
                """We can proxy publishers that are == or substrings of our
                known responses"""

                self.image_create(prefix="test1", repourl=self.durl1)

                overlap_dcs = []
                # identify the interesting repos, those that we've configured
                # using publisher prefixes that match our responses
                for dc_num in [num for num in self.dcs if
                    (self.dcs[num].get_property("publisher", "prefix")
                    in self.overlap_pubs)]:
                        dc = self.dcs[dc_num]
                        name = dc.get_property("publisher", "prefix")
                        overlap_dcs.append(dc)
                        # we need to use -R here since it doesn't get added
                        # automatically by self.pkg() because we've got
                        # "versions" as one of the CLI args (it being an
                        # overlapping publisher name)
                        self.pkg("-R %(img)s set-publisher -g %(url)s %(pub)s" %
                            {"img": self.get_img_path(),
                            "url": dc.get_repo_url(), "pub": name})

                # Start a system repo based on the configuration above
                self.sysrepo("")
                self._start_sysrepo()

                # attempt to create images using the sysrepo
                for dc in overlap_dcs:
                        pub = dc.get_property("publisher", "prefix")
                        hash = hashlib.sha1("file://" +
                            dc.get_repodir().rstrip("/")).hexdigest()
                        url = "http://localhost:%(port)s/%(pub)s/%(hash)s/" % \
                            {"port": self.sysrepo_port, "hash": hash,
                            "pub": pub}
                        self.set_img_path(os.path.join(self.test_root,
                            "sysrepo_image"))
                        self.pkg_image_create(prefix=pub, repourl=url)
                        self.pkg("-R %s install sample" % self.get_img_path())

                self.sc.stop()

        def test_8_file_publisher(self):
                """A proxied file publisher works as a normal file publisher,
                including package archives"""
                #
                # The standard system publisher client code does not use the
                # "publisher/0" response, so we need this test to exercise that.

                self.image_create(prefix="test1", repourl=self.durl1)

                # create a version of this url with a symlink, to ensure we
                # can follow links in urls
                urlresult = urllib2.urlparse.urlparse(self.rurl1)
                symlink_path = os.path.join(self.test_root, "repo_symlink")
                os.symlink(urlresult.path, symlink_path)
                symlinked_url = "file://%s" % symlink_path

                # create a p5p archive
                p5p_path = os.path.join(self.test_root,
                    "test_8_file_publisher_archive.p5p")
                p5p_url = "file://%s" % p5p_path
                self.pkgrecv(server_url=self.durl1, command="-a -d %s sample" %
                    p5p_path)

                for file_url in [self.rurl1, symlinked_url, p5p_url]:
                        self.image_create(prefix="test1", repourl=self.durl1)
                        self.pkg("set-publisher -g %s test1" % file_url)
                        self.sysrepo("")
                        self._start_sysrepo()

                        hash = hashlib.sha1(file_url.rstrip("/")).hexdigest()
                        url = "http://localhost:%(port)s/test1/%(hash)s/" % \
                            {"port": self.sysrepo_port, "hash": hash}
                        self.pkg_image_create(prefix="test1", repourl=url)
                        self.pkg("install sample")
                        self.pkg("contents -rm sample")
                        # the sysrepo doesn't support search ops for file repos
                        self.pkg("search -r sample", exit=1)
                        self.sc.stop()

        def test_9_unsupported_publishers(self):
                """Ensure we fail when asked to proxy < v4 file repos"""

                v3_repo_root = os.path.join(self.test_root, "sysrepo_test_9")
                os.mkdir(v3_repo_root)
                v3_repo_path = os.path.join(v3_repo_root, "repo")

                self.pkgrepo("create --version 3 %s" % v3_repo_path)
                self.pkgrepo("-s %s set publisher/prefix=foo" % v3_repo_path)
                for path in [v3_repo_path]:
                        self.image_create(repourl="file://%s" % path)
                        self.sysrepo("-R %s" % self.img_path(), exit=1)

        def test_10_missing_file_repo(self):
                """Ensure we print the right error message in the face of
                a missing repository."""
                repo_path = os.path.join(self.test_root, "test_10_missing_repo")
                self.pkgrepo("create %s" % repo_path)
                self.pkgrecv(server_url=self.durl1, command="-d %s sample" %
                    repo_path)
                self.pkgrepo("-s %s set publisher/prefix=foo" % repo_path)
                self.pkgrepo("-s %s rebuild" % repo_path)
                self.image_create(repourl="file://%s" % repo_path)
                shutil.rmtree(repo_path)
                ret, output, err = self.sysrepo("-R %s" % self.img_path(),
                    out=True, stderr=True, exit=1)
                # restore our image before going any further
                self.assert_("does not exist" in err, "unable to find expected "
                    "error message in stderr: %s" % err)

        def test_11_proxy_args(self):
                """Ensure we write configuration to tell Apache to use a remote
                proxy when proxying requests when using -w or -W"""
                self.image_create(prefix="test1", repourl=self.durl1)

                for arg, directives in [
                    ("-w http://foo", ["ProxyRemote http http://foo"]),
                    ("-W http://foo", ["ProxyRemote https http://foo"]),
                    ("-w http://foo -W http://foo",
                    ["ProxyRemote http http://foo",
                    "ProxyRemote https http://foo"])]:
                            self.sysrepo(arg)
                            for d in directives:
                                    self.file_contains(self.default_sc_conf, d)

        def test_12_cache_dir_permissions(self):
                """Our cache_dir permissions and ownership are verified"""

                exp_uid = portable.get_user_by_name(SYSREPO_USER, None, False)
                self.image_create(prefix="test1", repourl=self.durl1)

                cache_dir = os.path.join(self.test_root, "t_sysrepo_cache")
                # first verify that the user running the test has permissions
                try:
                        os.mkdir(cache_dir)
                        os.chown(cache_dir, exp_uid, 1)
                        os.rmdir(cache_dir)
                except OSError, e:
                        if e.errno == errno.EPERM:
                                raise pkg5unittest.TestSkippedException(
                                    "User running test does not have "
                                    "permissions to chown to uid %s" % exp_uid)
                        raise

                # Run sysrepo to create cache directory
                port = self.next_free_port
                self.sysrepo("-R %s -c %s -p %s" % (self.get_img_path(),
                    cache_dir, port))

                self._start_sysrepo()
                self.sc.stop()

                # Remove cache directory
                os.rmdir(cache_dir)

                # Again run sysrepo and then verify permissions
                cache_dir = os.path.join(self.test_root, "t_sysrepo_cache")
                port = self.next_free_port
                self.sysrepo("-R %s -c %s -p %s" % (self.get_img_path(),
                    cache_dir, port))
                self._start_sysrepo()

                # Wait for service to come online. Try for 30 seconds.
                count = 0
                while (count < 10):
                        time.sleep(3)
                        count = count + 1
                        if (os.access(cache_dir, os.F_OK)):
                                break

                # Verify cache directory exists.
                self.assertTrue(os.access(cache_dir, os.F_OK))

                filemode = stat.S_IMODE(os.stat(cache_dir).st_mode)
                self.assertEqualDiff(0755, filemode)
                uid = os.stat(cache_dir)[4]
                exp_uid = portable.get_user_by_name(SYSREPO_USER, None, False)
                self.assertEqualDiff(exp_uid, uid)

                self.sc.stop()

        def test_13_changing_p5p(self):
                """Ensure that when a p5p file changes from beneath us, or
                disappears, the system repository and any pkg(5) clients
                react correctly."""

                # create a p5p archive
                p5p_path = os.path.join(self.test_root,
                    "test_12_changing_p5p_archive.p5p")
                p5p_url = "file://%s" % p5p_path
                self.pkgrecv(server_url=self.durl1, command="-a -d %s sample" %
                    p5p_path)

                # configure an image from which to generate a sysrepo config
                self.image_create(prefix="test1", repourl=self.durl1)
                self.pkg("set-publisher -g %s test1" % p5p_url)
                self.sysrepo("")
                self._start_sysrepo()

                # create an image which uses the system publisher
                hash = hashlib.sha1(p5p_url.rstrip("/")).hexdigest()
                url = "http://localhost:%(port)s/test1/%(hash)s/" % \
                    {"port": self.sysrepo_port, "hash": hash}

                self.debug("using %s as repo url" % url)
                self.pkg_image_create(prefix="test1", repourl=url)
                self.pkg("install sample")

                # modify the p5p file - publish a new package and an
                # update of the existing package, then recreate the p5p file.
                self.pkgsend_bulk(self.durl1, self.new_pkg)
                self.pkgsend_bulk(self.durl1, self.sample_pkg)
                os.unlink(p5p_path)
                self.pkgrecv(server_url=self.durl1,
                    command="-a -d %s sample new" % p5p_path)

                # ensure we can install our new packages through the system
                # publisher url
                self.pkg("install new")
                self.pkg("publisher")

                # remove the p5p file, which should still allow us to uninstall
                renamed_p5p_path = p5p_path + ".renamed"
                os.rename(p5p_path, renamed_p5p_path)
                self.pkg("uninstall new")

                # ensure we can't install the packages or perform operations
                # that require the p5p file to be present
                self.pkg("install new", exit=1)
                self.pkg("contents -rm new", exit=1)

                # replace the p5p file, and ensure the client can install again
                os.rename(renamed_p5p_path, p5p_path)
                self.pkg("install new")
                self.pkg("contents -rm new")

                self.sc.stop()

        def test_14_bad_input(self):
                """Tests the system repository with some bad input: wrong
                paths, unicode in urls, and some very long urls to ensure
                the responses are as expected."""
                # create a p5p archive
                p5p_path = os.path.join(self.test_root,
                    "test_13_bad_input.p5p")
                p5p_url = "file://%s" % p5p_path
                self.pkgrecv(server_url=self.durl1, command="-a -d %s sample" %
                    p5p_path)
                p5p_hash = hashlib.sha1(p5p_url.rstrip("/")).hexdigest()
                file_url = self.dcs[2].get_repo_url()
                file_hash = hashlib.sha1(file_url.rstrip("/")).hexdigest()

                # configure an image from which to generate a sysrepo config
                self.image_create(prefix="test1", repourl=self.durl1)

                self.pkg("set-publisher -p %s" % file_url)
                self.pkg("set-publisher -g %s test1" % p5p_url)
                self.sysrepo("")
                self._start_sysrepo()

                # some incorrect urls
                queries_404 = [
                    "noodles"
                    "/versions/1"
                    "/"
                ]

                # a place to store some long urls
                queries_414 = []

                # add urls and some unicode.  We test a file repository,
                # which makes sure Apache can deal with the URLs appropriately,
                # as well as a p5p repository, exercising our mod_wsgi app.
                for hsh, pub in [("test1", p5p_hash), ("test2", file_hash)]:
                        queries_404.append("%s/%s/catalog/1/ΰŇﺇ⊂⏣⊅ℇ" %
                            (pub, hsh))
                        queries_404.append("%s/%s/catalog/1/%s" %
                            (pub, hsh, "f" + "u" * 1000))
                        queries_414.append("%s/%s/catalog/1/%s" %
                            (pub, hsh, "f" * 900000 + "u"))

                def test_response(part, code):
                        """Given a url substring and an expected error code,
                        check that the system repository returns that code
                        for a url constructed from that part."""
                        url = "http://localhost:%s/%s" % \
                            (self.sysrepo_port, part)
                        try:
                                resp =  urllib2.urlopen(url, None, None)
                        except urllib2.HTTPError, e:
                                if e.code != code:
                                        self.assert_(False,
                                            "url %s returned: %s" % (url, e))

                for url_part in queries_404:
                        test_response(url_part, 404)
                for url_part in queries_414:
                        test_response(url_part, 414)
                self.sc.stop()

        def test_15_unicode(self):
                """Tests the system repository with some unicode paths to p5p
                files."""
                unicode_str = "ΰŇﺇ⊂⏣⊅ℇ"
                unicode_dir = os.path.join(self.test_root, unicode_str)
                os.mkdir(unicode_dir)

                # create paths to p5p files, using unicode dir or file names
                p5p_unicode_dir = os.path.join(unicode_dir,
                    "test_14_unicode.p5p")
                p5p_unicode_file = os.path.join(self.test_root,
                    "%s.p5p" % unicode_str)

                for p5p_path in [p5p_unicode_dir, p5p_unicode_file]:
                        p5p_url = "file://%s" % p5p_path
                        self.pkgrecv(server_url=self.durl1,
                            command="-a -d %s sample" % p5p_path)
                        p5p_hash = hashlib.sha1(p5p_url.rstrip("/")).hexdigest()

                        self.image_create()
                        self.pkg("set-publisher -p %s" % p5p_url)

                        self.sysrepo("")
                        self._start_sysrepo()

                        # ensure we can get content from the p5p file
                        for path in ["catalog/1/catalog.attrs",
                            "catalog/1/catalog.base.C",
                            "file/1/f5da841b7c3601be5629bb8aef928437de7d534e"]:
                                url = "http://localhost:%s/test1/%s/%s" % \
                                    (self.sysrepo_port, p5p_hash, path)
                                resp = urllib2.urlopen(url, None, None)
                                self.debug(resp.readlines())

                        self.sc.stop()

        def test_16_config_cache(self):
                """We can load/store our configuration cache correctly."""

                cache_path = "var/cache/pkg/sysrepo_pub_cache.dat"
                full_cache_path = os.path.join(self.get_img_path(), cache_path)
                sysrepo_runtime_dir = os.path.join(self.test_root,
                    "sysrepo_runtime")
                sysrepo_conf = os.path.join(sysrepo_runtime_dir,
                    "sysrepo_httpd.conf")

                # a basic check that the config cache looks sane
                self.image_create(prefix="test1", repourl=self.durl1)
                self.file_doesnt_exist(cache_path)

                self.sysrepo("", stderr=True)
                self.assert_("Unable to load config" not in self.output)
                self.assert_("Unable to store config" not in self.output)
                self.file_exists(cache_path)
                self.file_contains(sysrepo_conf, self.durl1)
                self.file_remove(cache_path)

                # install some sample packages to our image, just to ensure
                # that sysrepo doesn't mind, and cache creation works
                self.pkg("install sample")
                self.sysrepo("", stderr=True)
                self.assert_("Unable to load config" not in self.output)
                self.assert_("Unable to store config" not in self.output)
                self.file_exists(cache_path)
                self.file_contains(sysrepo_conf, self.durl1)
                self.file_remove(cache_path)

                # ensure we get warnings when we can't load/store the config
                os.makedirs(full_cache_path)
                self.sysrepo("", stderr=True)
                self.assert_("Unable to load config" in self.errout)
                self.assert_("Unable to store config" in self.errout)
                self.file_contains(sysrepo_conf, self.durl1)
                os.rmdir(full_cache_path)

                # ensure we get warnings when loading a corrupt cache
                self.sysrepo("")
                self.file_append(cache_path, "noodles")
                self.sysrepo("", stderr=True)
                self.assert_("Invalid config cache file at" in self.errout)
                # we should have overwritten the corrupt cache, so check again
                self.sysrepo("", stderr=True)
                self.assert_("Invalid config cache file at" not in self.errout)
                self.file_contains(cache_path, self.durl1)
                self.file_remove(cache_path)

                # ensure that despite valid JSON in the cache, we still
                # treat it as corrupt, and clobber the old cache
                rubbish = {"food preference": "I like noodles."}
                other = ["nonsense here"]
                with file(full_cache_path, "wb") as cache_file:
                        simplejson.dump((rubbish, other), cache_file)
                self.sysrepo("", stderr=True)
                self.assert_("Invalid config cache at" in self.errout)
                self.file_doesnt_contain(cache_path, "noodles")
                self.file_contains(cache_path, self.durl1)
                self.file_contains(sysrepo_conf, self.durl1)

                # ensure we get a new cache on publisher modification
                self.file_doesnt_contain(cache_path, self.rurl1)
                self.pkg("set-publisher -g %s test1" % self.rurl1)
                self.file_doesnt_exist(cache_path)
                self.sysrepo("")
                self.file_contains(cache_path, self.rurl1)
                self.file_contains(cache_path, self.durl1)

                # record the last modification time of the cache
                st_cache = os.lstat(full_cache_path)
                mtime = st_cache.st_mtime

                # no image modification, so no new config file
                self.sysrepo("")
                self.assert_(mtime == os.lstat(full_cache_path).st_mtime,
                    "Changed mtime of cache despite no image config change")

                # load the config from the cache, remove a URI then save
                # it - despite being well-formed, the cache doesn't contain the
                # same configuration as the image, simulating an older version
                # of pkg(1) having changed publisher configuration.
                with file(full_cache_path, "rb") as cache_file:
                        uri_pub_map, no_uri_pubs = simplejson.load(cache_file)

                with file(full_cache_path, "wb") as cache_file:
                        del uri_pub_map[self.durl1]
                        simplejson.dump((uri_pub_map, no_uri_pubs), cache_file,
                            indent=True)
                # make sure we've definitely broken it
                self.file_doesnt_contain(cache_path, self.durl1)

                # we expect an 'invalid config cache' message, and a new cache
                # written with correct content.
                self.sysrepo("", stderr=True)
                self.assert_("Invalid config cache at" in self.errout)
                self.file_contains(cache_path, self.durl1)
                self.sysrepo("")

                # rename the cache file, then symlink it
                os.rename(full_cache_path, full_cache_path + ".new")
                os.symlink(full_cache_path + ".new", full_cache_path)
                self.pkg("set-publisher -G %s test1" % self.durl1)
                # by running pkg set-publisher, we should have removed the
                # symlink
                self.file_doesnt_exist(cache_path)
                # replace the symlink
                os.symlink(full_cache_path + ".new", full_cache_path)

                self.sysrepo("", stderr=True)
                self.assert_("Unable to load config" in self.errout)
                self.assert_("not a regular file" in self.errout)
                self.assert_("Unable to store config" in self.errout)
                # our symlinked cache should be untouched, and still contain
                # rurl1, despite it being absent from our actual configuration.
                self.file_contains(cache_path, self.durl1)
                self.file_doesnt_contain(sysrepo_conf, self.durl1)

                # check that an image with no publishers works
                self.pkg("unset-publisher test1")
                self.pkg("publisher", out=True, stderr=True)
                self.file_doesnt_exist(cache_path)
                self.sysrepo("", stderr=True)
                self.assert_("Unable to load config" not in self.output)
                self.assert_("Unable to store config" not in self.output)
                self.file_doesnt_contain(sysrepo_conf, self.durl1)

                # check that removing packages doesn't impact the cache
                self.pkg("uninstall sample")
                self.sysrepo("", stderr=True)
                self.assert_("Unable to load config" not in self.output)
                self.assert_("Unable to store config" not in self.output)
                self.file_remove(cache_path)
                self.sysrepo("", stderr=True)
                self.assert_("Unable to load config" not in self.output)
                self.assert_("Unable to store config" not in self.output)


class TestP5pWsgi(pkg5unittest.SingleDepotTestCase):
        """A class to directly exercise the p4p mod_wsgi application outside
        of Apache and the system repository itself.

        By calling the web application directly, we have a little more
        flexibility when writing tests.  Other system-repository tests will
        exercise much of the mod_wsgi configuration and framework, but these
        tests will be easier to debug and faster to run.

        Note that since we call the web application directly, the web app can
        intentionally emit some tracebacks to stderr, which will be seen by
        the test framework."""

        persistent_setup = False

        sample_pkg = """
            open sample@1.0,5.11-0
            add file tmp/sample_file mode=0444 owner=root group=bin path=/usr/bin/sample
            close"""

        new_pkg = """
            open new@1.0,5.11-0
            add file tmp/sample_file mode=0444 owner=root group=bin path=/usr/bin/new
            close"""

        misc_files = { "tmp/sample_file": "carrots" }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self, start_depot=True)
                self.image_create()

                # we have to dynamically load the mod_wsgi webapp, since it
                # lives outside our normal search path
                mod_name = "sysrepo_p5p"
                src_name = "%s.py" % mod_name
                sysrepo_p5p_file = file(os.path.join(self.template_dir,
                    src_name))
                self.sysrepo_p5p = imp.load_module(mod_name, sysrepo_p5p_file,
                    src_name, ("py", "r", imp.PY_SOURCE))

                # now create a simple p5p file that we can use in our tests
                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.durl, self.sample_pkg)
                self.pkgsend_bulk(self.durl, self.new_pkg)

                self.p5p_path = os.path.join(self.test_root,
                    "mod_wsgi_archive.p5p")

                self.pkgrecv(server_url=self.durl,
                    command="-a -d %s sample new" % self.p5p_path)
                self.http_status = ""

        def test_queries(self):
                """Ensure that we return proper HTTP response codes."""

                def start_response(status, response_headers, exc_info=None):
                        """A dummy response function, used to capture output"""
                        self.http_status = status

                environ = {}
                hsh = "123abcdef"
                environ["SYSREPO_RUNTIME_DIR"] = self.test_root
                environ["PKG5_TEST_ENV"] = "True"
                environ[hsh] = self.p5p_path

                def test_query_responses(queries, code, expect_content=False):
                        """Given a list of queries, and a string we expect to
                        appear in each response, invoke the wsgi application
                        with each query and check response codes.  Also check
                        that content was returned or not."""

                        for query in queries:
                                seen_content = False
                                environ["QUERY_STRING"] = urllib2.unquote(query)
                                self.http_status = ""
                                for item in self.sysrepo_p5p.application(
                                    environ, start_response):
                                        seen_content = item

                                self.assert_(code in self.http_status,
                                    "Query %s response did not contain %s: %s" %
                                    (query, code, self.http_status))
                                if expect_content:
                                        self.assert_(seen_content,
                                            "No content returned for %s" %
                                            query)
                                else:
                                        self.assertFalse(seen_content,
                                            "Unexpected content for %s" % query)

                # the easiest way to get the name of one of the manifests
                # in the archive is to look for it in the index
                archive = pkg.p5p.Archive(self.p5p_path)
                idx = archive.get_index()
                mf = None
                for item in idx.keys():
                        if item.startswith("publisher/test/pkg/new/"):
                                mf = item.replace(
                                    "publisher/test/pkg/new/", "new@")
                archive.close()

                queries_200 = [
                    # valid file, matches the hash of the content in misc_files
                    "pub=test&hash=%s&path=file/1/f890d49474e943dc07a766c21d2bf35d6e527e89" % hsh,
                    # valid catalog parts
                    "pub=test&hash=%s&path=catalog/1/catalog.attrs" % hsh,
                    "pub=test&hash=%s&path=catalog/1/catalog.base.C" % hsh,
                    # valid manifest
                    "pub=test&hash=%s&path=manifest/0/%s" % (hsh, mf)
                ]

                queries_404 = [
                    # wrong path
                    "pub=test&hash=%s&path=catalog/1/catalog.attrsX" % hsh,
                    # invalid publisher
                    "pub=WRONG&hash=%s&path=catalog/1/catalog.attrs" % hsh,
                    # incorrect path
                    "pub=test&hash=%s&path=file/1/12u3yt123123" % hsh,
                    # incorrect path (where the first path component is unknown)
                    "pub=test&hash=%s&path=carrots/1/12u3yt123123" % hsh,
                    # incorrect manifest, with an unknown package name
                    "pub=test&hash=%s&path=manifest/0/foo%s" % (hsh, mf),
                    # incorrect manifest, with an illegal FMRI
                    "pub=test&hash=%s&path=manifest/0/%sfoo" % (hsh, mf)
                ]

                queries_400 = [
                    # missing publisher (while p5p files can return content
                    # despite no publisher, our mod_wsgi app requires a
                    # publisher)
                    "hash=%s&path=catalog/1/catalog.attrs" % hsh,
                    # missing path
                    "pub=test&hash=%s" % hsh,
                    # malformed query
                    "&&???&&&",
                    # no hash key
                    "pub=test&hashX=%s&path=catalog/1/catalog.attrs" % hsh,
                    # unknown hash value
                    "pub=test&hash=carrots&path=catalog/1/catalog.attrs"
                ]

                test_query_responses(queries_200, "200", expect_content=True)
                test_query_responses(queries_400, "400")
                test_query_responses(queries_404, "404")

                # generally we try to shield users from internal server errors,
                # however in the case of a missing p5p file on the server
                # this seems like the right thing to do, rather than to return
                # a 404.
                # The end result for pkg client with 500 or a 404 code is the
                # same, but the former will result in more useful information
                # in the system-repository error_log.
                os.unlink(self.p5p_path)
                queries_500 = queries_200 + queries_404
                test_query_responses(queries_500, "500")
                # despite the missing p5p file, we should still get 400 errors
                test_query_responses(queries_400, "400")


if __name__ == "__main__":
        unittest.main()
