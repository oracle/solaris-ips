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

# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import hashlib
import os
import os.path
import unittest
import urllib2
import shutil

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
                """A proxied file publisher works as a normal file publisher."""
                #
                # The standard system publisher client code does not use the
                # "publisher/0" response, so we need this test to exercise that.

                self.image_create(prefix="test1", repourl=self.durl1)

                # create a version of this url with a symlink, to ensure we
                # can follow links in urls
                urlresult = urllib2.urlparse.urlparse(self.rurl1)
                symlink_path = os.path.join(self.test_root, "repo_symlink")
                os.symlink(urlresult.path, symlink_path)
                symlinked_url="file://%s" % symlink_path

                for file_url in [self.rurl1, symlinked_url]:
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
                        # the sysrepo doesn't support search operations for file repos
                        self.pkg("search -r sample", exit=1)
                        self.sc.stop()

        def test_9_unsupported_publishers(self):
                """Ensure we fail when asked to proxy p5p or < v4 file repos"""

                v3_repo_root = os.path.join(self.test_root, "sysrepo_test_9")
                os.mkdir(v3_repo_root)
                v3_repo_path = os.path.join(v3_repo_root, "repo")
                p5a_path = os.path.join(v3_repo_root, "archive.p5p")
                self.pkgrecv(server_url=self.durl1, command="-a -d %s sample" %
                    p5a_path)

                self.pkgrepo("create --version 3 %s" % v3_repo_path)
                self.pkgrepo("-s %s set publisher/prefix=foo" % v3_repo_path)
                for path in [p5a_path, v3_repo_path]:
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

if __name__ == "__main__":
        unittest.main()
