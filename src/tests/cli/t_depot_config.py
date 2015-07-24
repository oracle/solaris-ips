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
# Copyright (c) 2013, 2015, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import copy
import os
import time
import unittest
import certgenerator
import shutil
from six.moves import http_client
from six.moves.urllib.error import HTTPError
from six.moves.urllib.parse import quote
from six.moves.urllib.request import urlopen

from pkg.client.debugvalues import DebugValues
import pkg.fmri

HTTPDEPOT_USER = "pkg5srv"


class _Apache(object):
        # An array that can be used to build our svcs(1) wrapper.
        default_svcs_conf = [
            # FMRI                                   STATE
            ["svc:/application/pkg/server:default",  "online" ],
            ["svc:/application/pkg/server:usr",      "online" ],
            # an instance which we have a writable_root for
            ["svc:/application/pkg/server:windex",   "online" ],
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
            # inst_root           readonly  standalone  writable_root
            ["{rdir1}",         "true",   "false",    "\"\""],
            ["{rdir2}",         "true",   "false",    "\"\""],
            ["{rdir3}",         "true",   "false",    "{index_dir}"],
            # we intentionally use non-existent repository
            # paths in these services, and check they aren't
            # present in the httpd.conf later.
            ["/pkg5/there/aint", "true",    "false",    "\"\""],
            ["/pkg5/nobody/here", "false",  "false",    "\"\""],
            ["/pkg5/but/us/chickens", "true", "true",   "\"\""],
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

        _svcs_template = \
"""#!/usr/bin/ksh93
#
# This script produces false svcs(1) output, using
# a list of space separated strings, with each string
# of the format <fmri>%<state>
#
# eg.
# SERVICE_STATUS="svc:/application/pkg/server:foo%online svc:/application/pkg/server:default%offline svc:/application/pkg/server:usr%online"
# We expect to be called with 'svcs -H -o fmri <fmri>' but completely ignore
# the <fmri> argument.
#
SERVICE_STATUS="{0}"

set -- `getopt o:H $*`
for i in $* ; do
    case $i in
        -H)    minus_h=$i; shift;;
        -o)    minus_o=$2; shift;;
        *)     break;;
    esac
done

if [ "${{minus_o}}" ]; then
    if [ -z "${{minus_h}}" ]; then
        echo "FMRI"
    fi
    for service in $SERVICE_STATUS ; do
        echo $service | sed -e 's/%/ /' | read fmri state
        echo $fmri
    done
    exit 0
fi

if [ -z "${{minus_h}}" ]; then
    printf "%-14s%6s    %s\n" STATE STIME FMRI
fi
for service in $SERVICE_STATUS ; do
    echo $service | sed -e 's/%/ /' | read fmri state
    printf "%-14s%9s %s\n" $state 00:00:00 $fmri
done
"""

        _svcprop_template = \
"""#!/usr/bin/ksh93
#
# This script produces false svcprop(1) output, using
# a list of space separated strings, with each string
# of the format <fmri>%<state>%<inst_root>%<readonly>%<standalone>%<writable_root>
#
# eg.
# SERVICE_PROPS="svc:/application/pkg/server:foo%online%/space/repo%true%false%/space/writable_root"
#
# we expect to be called as "svcprop -c -p <property> <fmri>"
# which is enough svcprop(1) functionalty for these tests. Any other
# command line options will cause us to return nonsense.
#

typeset -A prop_state
typeset -A prop_readonly
typeset -A prop_inst_root
typeset -A prop_standalone
typeset -A prop_writable_root

SERVICE_PROPS="{0}"
for service in $SERVICE_PROPS ; do
        echo $service | sed -e 's/%/ /g' | \
            read fmri state inst_root readonly standalone writable_root
        # create a hashable version of the FMRI
        fmri=$(echo $fmri | sed -e 's/\///g' -e 's/://g')
        prop_state[$fmri]=$state
        prop_inst_root[$fmri]=$inst_root
        prop_readonly[$fmri]=$readonly
        prop_standalone[$fmri]=$standalone
        prop_writable_root[$fmri]=$writable_root
done


FMRI=$(echo $4 | sed -e 's/\///g' -e 's/://g')
case $3 in
        "pkg/inst_root")
                echo ${{prop_inst_root[$FMRI]}}
                ;;
        "pkg/readonly")
                echo ${{prop_readonly[$FMRI]}}
                ;;
        "pkg/standalone")
                echo ${{prop_standalone[$FMRI]}}
                ;;
        "pkg/writable_root")
                echo ${{prop_writable_root[$FMRI]}}
                ;;
        "restarter/state")
                echo ${{prop_state[$FMRI]}}
                ;;
        *)
                echo "Completely bogus svcprop output. Sorry."
esac
"""

        # A very minimal httpd.conf, which contains an Include directive
        # that we will use to reference our pkg5 depot-config.conf file. We leave
        # an Alias pointing to /server-status to make this server distinctive
        # for this test case.
        _default_httpd_conf = \
"""ServerRoot "/usr/apache2/2.4"
PidFile "{runtime_dir}/default_httpd.pid"
Listen {port}
LoadModule access_compat_module libexec/mod_access_compat.so
LoadModule alias_module libexec/mod_alias.so
LoadModule authz_core_module libexec/mod_authz_core.so
LoadModule dir_module libexec/mod_dir.so
LoadModule headers_module libexec/mod_headers.so
LoadModule log_config_module libexec/mod_log_config.so
LoadModule mpm_worker_module libexec/mod_mpm_worker.so
LoadModule rewrite_module libexec/mod_rewrite.so
LoadModule ssl_module libexec/mod_ssl.so
LoadModule status_module libexec/mod_status.so
LoadModule unixd_module libexec/mod_unixd.so

User webservd
Group webservd
ServerAdmin you@yourhost.com
ServerName 127.0.0.1
DocumentRoot "/var/apache2/2.4/htdocs"
<Directory "/var/apache2/2.4/htdocs">
    Options Indexes FollowSymLinks
    AllowOverride None
    Require all granted
</Directory>
<IfModule dir_module>
    DirectoryIndex index.html
</IfModule>
LogFormat \"%h %l %u %t \\\"%r\\\" %>s %b\" common
ErrorLog "{runtime_dir}/error_log"
CustomLog "{runtime_dir}/access_log" common
LogLevel debug
# Reference the depot.conf file generated by pkg.depot-config, which makes this
# web server into something that can serve pkg(5) repositories.
Include {depot_conf}
SSLRandomSeed startup builtin
SSLRandomSeed connect builtin
# We enable server-status here, using /pkg5test-server-status to it to make the
# URI distinctive.
<Location /pkg5test-server-status>
    SetHandler server-status
</Location>
"""

        def setUp(self):
                self.sc = None
                pkg5unittest.ApacheDepotTestCase.setUp(self, ["test1",
                    "test2", "test3"])
                self.rdir1 = self.dcs[1].get_repodir()
                self.rdir2 = self.dcs[2].get_repodir()
                self.rdir3 = self.dcs[3].get_repodir()

                self.index_dir = os.path.join(self.test_root,
                    "depot_writable_root")
                self.default_depot_runtime = os.path.join(self.test_root,
                    "depot_runtime")
                self.default_depot_conf = os.path.join(
                    self.default_depot_runtime, "depot_httpd.conf")
                self.depot_conf_fragment = os.path.join(
                    self.default_depot_runtime, "depot.conf")

                self.depot_port = self.next_free_port
                self.next_free_port += 1
                self.make_misc_files(self.misc_files)
                self._set_smf_state()

        def _set_smf_state(self, svcs_conf=default_svcs_conf,
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

                rdirs = {"rdir1": self.rdir1, "rdir2": self.rdir2,
                    "rdir3": self.rdir3, "index_dir": self.index_dir}

                # construct two strings we can use as parameters to our
                # __svc*_template values
                _svcs_conf = " ".join(["%".join([value for value in item])
                    for item in _svcs_conf])
                _svcprop_conf = " ".join(["%".join(
                    [value.format(**rdirs) for value in item])
                    for item in _svcprop_conf])

                self.smf_cmds = {
                    "usr/bin/svcs": self._svcs_template.format(_svcs_conf),
                    "usr/bin/svcprop": self._svcprop_template.format(_svcprop_conf)
                }
                self.make_misc_files(self.smf_cmds, "smf_cmds", mode=0o755)

        def start_depot(self, build_indexes=True):
                hc = pkg5unittest.HttpDepotController(
                    self.default_depot_conf, self.depot_port,
                    self.default_depot_runtime, testcase=self)
                self.register_apache_controller("depot", hc)
                self.ac.start()
                if build_indexes:
                        # we won't return until indexes are built
                        u = urlopen(
                            "{0}/depot/depot-wait-refresh".format(hc.url)).close()


class TestHttpDepot(_Apache, pkg5unittest.ApacheDepotTestCase):
        """Tests that exercise the pkg.depot-config CLI as well as checking the
        functionality of the depot-config itself for configuring http service.
        This test class will fail if not run as root, since many of the tests
        use 'pkg.depot-config -a' which will attempt to chown a directory to
        pkg5srv:pkg5srv.

        The default_svcs_conf having an instance name of 'usr' is not a
        coincidence: we use it there so that we catch RewriteRules that
        mistakenly try to serve content from the root filesystem ('/') rather
        than from beneath our DocumentRoot (assuming that test systems always
        have a /usr directory)
        """

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
                self.file_contains(self.ac.conf, self.rdir3)
                self.file_contains(self.ac.conf, self.index_dir)
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
                    "No usage string printed: {0}".format(output))
                ret, output = self.depotconfig("--help", out=True, exit=2)
                self.assert_("Usage:" in output,
                    "No usage string printed: {0}".format(output))

        def test_2_htinvalid_root(self):
                """We return an error given an invalid image root"""

                # check for incorrectly-formed -d options
                self.depotconfig("-d usr -F -r /dev/null", exit=2)

                # ensure we pick up invalid -d directories
                for invalid_root in ["usr=/dev/null",
                    "foo=/etc/passwd", "alt=/proc"]:
                        ret, output, err = self.depotconfig(
                            "-d {0} -F".format(invalid_root), out=True, stderr=True,
                            exit=1)
                        expected = invalid_root.split("=")[1]
                        self.assert_(expected in err,
                            "error message did not contain {0}: {1}".format(
                            expected, err))

                # ensure we also catch invalid SMF inst_roots
                svcs_conf = [["svc:/application/pkg/server:default", "online" ]]
                svcprop_conf = [["/tmp", "true", "false"]]
                self._set_smf_state(svcs_conf, svcprop_conf)
                ret, output, err = self.depotconfig("", out=True, stderr=True,
                    exit=1)
                self.assert_("/tmp" in err, "error message did not contain "
                    "/tmp")

                # ensure we pick up invalid writable_root directories
                ret, output, err = self.depotconfig("-d blah={0}=/dev/null".format(
                    self.rdir1), out=True, stderr=True, exit=1)

                # but check that we allow valid writeable_roots
                ret, output, err = self.depotconfig("-d blah={0}={1}".format(
                    self.rdir1, self.index_dir), out=True, stderr=True)
                self.file_contains(self.default_depot_conf,
                    "PKG5_WRITABLE_ROOT_blah {0}".format(self.index_dir))

        def test_3_invalid_htcache_dir(self):
                """We return an error given an invalid cache_dir"""

                for invalid_cache in ["/dev/null", "/etc/passwd"]:
                        ret, output, err = self.depotconfig("-c {0}".format(
                            invalid_cache), out=True, stderr=True, exit=1)
                        self.assert_(invalid_cache in err, "error message "
                            "did not contain {0}: {1}".format(invalid_cache, err))

        def test_4_invalid_hthostname(self):
                """We return an error given an invalid hostname"""

                for invalid_host in ["1.2.3.4.5.6", "pkgsysrepotestname", "."]:
                        ret, output, err = self.depotconfig("-h {0}".format(
                            invalid_host), out=True, stderr=True, exit=1)
                        self.assert_(invalid_host in err, "error message "
                            "did not contain {0}: {1}".format(invalid_host, err))

        def test_5_invalid_htlogs_dir(self):
                """We return an error given an invalid logs_dir"""

                for invalid_log in ["/dev/null", "/etc/passwd"]:
                        ret, output, err = self.depotconfig("-l {0}".format(invalid_log),
                            out=True, stderr=True, exit=1)
                        self.assert_(invalid_log in err, "error message "
                            "did not contain {0}: {1}".format(invalid_log, err))

                for invalid_log in ["/proc"]:
                        port = self.next_free_port
                        self.depotconfig("-l {0} -p {1}".format(invalid_log, port),
                            exit=0)
                        self.assertRaises(pkg5unittest.ApacheStateException,
                            self.start_depot)

        def test_6_invalid_htport(self):
                """We return an error given an invalid port"""

                for invalid_port in [999999, "bobcat", "-1234"]:
                        ret, output, err = self.depotconfig("-p {0}".format(invalid_port),
                            out=True, stderr=True, exit=1)
                        self.assert_(str(invalid_port) in err, "error message "
                            "did not contain {0}: {1}".format(invalid_port, err))

        def test_7_invalid_htruntime_dir(self):
                """We return an error given an invalid runtime_dir"""

                for invalid_runtime in ["/dev/null", "/etc/passwd", "/proc"]:
                        ret, output, err = self.depotconfig("-r {0}".format(
                            invalid_runtime), out=True, stderr=True, exit=1)
                        self.assert_(invalid_runtime in err, "error message "
                            "did not contain {0}: {1}".format(invalid_runtime, err))

        def test_8_invalid_htcache_size(self):
                """We return an error given an invalid cache_size"""

                for invalid_csize in ["cats", "-1234"]:
                        ret, output, err = self.depotconfig(
                            "-s {0}".format(invalid_csize), out=True, stderr=True,
                            exit=1)
                        self.assert_(str(invalid_csize) in err, "error message "
                            "did not contain {0}: {1}".format(invalid_csize, err))

        def test_9_invalid_httemplates_dir(self):
                """We return an error given an invalid templates_dir"""

                for invalid_tmp in ["/dev/null", "/etc/passwd", "/proc"]:
                        ret, output, err = self.depotconfig("-T {0}".format(invalid_tmp),
                            out=True, stderr=True, exit=1)
                        self.assert_(invalid_tmp in err, "error message "
                            "did not contain {0}: {1}".format(invalid_tmp, err))

        def test_10_httype(self):
                """We return an error given an invalid type option."""

                invalid_type = "weblogic"
                ret, output, err = self.depotconfig("-t {0}".format(invalid_type),
                    out=True, stderr=True, exit=2)
                self.assert_(invalid_type in err, "error message "
                    "did not contain {0}: {1}".format(invalid_type, err))
                # ensure we work with the supported type
                self.depotconfig("-t apache2")
                self.depotconfig("-t apache22")

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
                        "/default/info/0/{esc_full_fmri}",
                        "/default/test1/info/0/{esc_full_fmri}",
                        "/default/manifest/0/{esc_full_fmri}",
                        "/default/en/search.shtml",
                        "/usr/test2/en/catalog.shtml",
                        "/depot/default/en/search.shtml?token=pkg&action=Search"
                ]

                def get_url(url_path):
                        try:
                                url_obj = urlopen(url_path, timeout=10)
                                self.assert_(url_obj.code == 200,
                                    "Failed to open {0}: {1}".format(url_path,
                                    url_obj.code))
                                url_obj.close()
                        except HTTPError as e:
                                self.debug("Failed to open {0}: {1}".format(
                                    url_path, e))
                                raise

                for p in paths:
                        get_url("{0}{1}".format(self.ac.url, p.format(**conf)))

                self.ac.stop()

                # test that pkg.depot-config detects missing repos
                broken_rdir = self.rdir2 + "foo"
                os.rename(self.rdir2, broken_rdir)
                self.depotconfig("", exit=1)

                # test that when we break one of the repositories we're
                # serving, the remaining repositories are still accessible
                # from the bui. We need to fix the repo dir before rebuilding
                # the configuration, then break it once the depot has started.
                os.rename(broken_rdir, self.rdir2)
                self.depotconfig("")
                os.rename(self.rdir2, broken_rdir)
                self.start_depot(build_indexes=False)

                # check the first request to the BUI works as expected
                get_url(self.ac.url)

                # and check that we get a 404 for the missing repo
                bad_url = "{0}/usr/test2/en/catalog.shtml".format(self.ac.url)
                raised_404 = False
                try:
                        url_obj = urlopen(bad_url, timeout=10)
                        url_obj.close()
                except HTTPError as e:
                        if e.code == 404:
                                raised_404 = True
                self.assert_(raised_404, "Didn't get a 404 opening {0}".format(
                    bad_url))

                # check that we can still reach other valid paths
                paths = [
                        "/",
                        "/default/test1",
                        "/default/en",
                        "/default/en/index.shtml",
                        "/default/en/catalog.shtml",
                        "/default/p5i/0/new.p5i",
                        "/default/info/0/{esc_full_fmri}",
                        "/default/test1/info/0/{esc_full_fmri}",
                        "/default/manifest/0/{esc_full_fmri}",
                        "/default/en/search.shtml",
                ]
                for p in paths:
                        self.debug(p)
                        get_url("{0}{1}".format(self.ac.url, p.format(**conf)))
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
                self.pkgrepo("-s {0} refresh".format(self.dcs[2].get_repo_url()))

                self.depotconfig("")
                self.image_create()
                self.start_depot()
                # test that we can access the default publisher
                self.pkg("set-publisher -p {0}/default".format(self.ac.url))
                self.pkg("publisher")
                self.pkg("install sample@1.0")
                self.file_contains("usr/bin/sample", "tmp/sample")
                self.pkg("update")
                self.file_contains("usr/bin/sample", "tmp/updated")

                # test that we can access specific publishers, this time from
                # a different repository, served by the same depot-config.
                self.pkg("set-publisher -p {0}/usr/test2".format(self.ac.url))
                self.pkg("contents -r new")
                self.pkg("set-publisher -G '*' test2")
                ret, output = self.pkg(
                    "search -o action.raw -s {0}/usr new".format(self.ac.url),
                    out=True)
                self.assert_("path=usr/bin/new" in output)

                # publish a new package, and ensure we can install it
                self.pkgsend_bulk(self.dcs[1].get_repo_url(), self.another_pkg)
                self.pkg("install another")
                self.file_contains("usr/bin/another", "tmp/another")

                # add a new publisher to an existing repository and ensure it
                # is visible from the repository
                self.ac.stop()
                self.pkgrepo("-s {0} add-publisher carrots".format(self.rdir1))
                self.pkgsend_bulk(self.dcs[1].get_repo_url(), self.carrots_pkg)
                self.depotconfig("")
                self.start_depot()

                self.pkg("set-publisher -g {0}/default/carrots carrots".format(
                    self.ac.url))

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
                first_ver = quote(str(first_fmri.version))
                second_ver = quote(str(second_fmri.version))

                self.depotconfig("")
                self.image_create()
                self.start_depot()

                ret, output = self.pkgrecv(command="-s {0}/default --newest".format(
                    self.ac.url), out=True)
                sec_fmri_nobuild = pkg.fmri.PkgFmri(second[0]).get_fmri(
                    include_build=False)
                self.assert_(sec_fmri_nobuild in output)
                dest = os.path.join(self.test_root, "test_13_hgpkgrecv")
                os.mkdir(dest)

                # pull down raw package contents
                self.pkgrecv(command="-s {0}/default -m all-versions --raw "
                    "-d {1} '*'".format(self.ac.url, dest))

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
                depot-config only when the -A flag is enabled and only on
                the repository that has a writable root. Test that the index
                does indeed get updated when a refresh is performed and that
                new package contents are visible."""

                rurl = self.dcs[1].get_repo_url()
                nosearch_rurl = self.dcs[2].get_repo_url()
                writable_rurl = self.dcs[3].get_repo_url()

                self.pkgsend_bulk(rurl, self.sample_pkg)
                # we have a search index on rurl
                self.pkgrepo("-s {0} refresh".format(rurl))
                self.pkgsend_bulk(writable_rurl, self.sample_pkg)

                # we have no search index on nosearch_rurl
                self.pkgsend_bulk(nosearch_rurl, self.sample_pkg)

                # allow index refreshes for repositories that support them
                # (ie. have a writable root)
                self.depotconfig("-A")
                self.start_depot()
                self.image_create()

                depot_url = "{0}/default".format(self.ac.url)
                windex_url = "{0}/windex".format(self.ac.url)
                nosearch_url = "{0}/usr".format(self.ac.url)

                # verify that list commands work
                ret, output = self.pkgrepo("-s {0} list -F tsv".format(depot_url),
                    out=True)
                self.assert_("pkg://test1/sample@1.0" in output)
                self.assert_("pkg://test1/new@1.0" not in output)

                # rebuild, remove and set commands should fail, the latter two
                # with exit code 2
                self.pkgrepo("-s {0} rebuild".format(depot_url), exit=1)
                self.pkgrepo("-s {0} remove sample".format(depot_url), exit=2)
                self.pkgrepo("-s {0} set -p test1 foo/bar=baz".format(depot_url),
                    exit=2)

                # verify that status works
                self.pkgrepo("-s {0} info".format(depot_url))
                self.assert_("test1 1 online" in self.reduceSpaces(self.output))

                # verify search works for packages in the repository
                self.pkg("set-publisher -p {0}".format(depot_url))
                self.pkg("search -s {0} msgsh".format("{0}".format(depot_url)),
                    exit=1)
                self.pkg("search -s {0} /usr/bin/sample".format(depot_url))

                # Can't refresh this repo since it doesn't have a writable root
                self.pkgrepo("-s {0} refresh".format(depot_url), exit=1)

                # verify that search fails for repositories that don't have
                # a pre-existing search index in the repository
                self.pkg("search -s {0} /usr/bin/sample".format(nosearch_url), exit=1)

                # publish a new package, and verify it doesn't appear in the
                # search results for the repo with the writable_root
                self.pkgsend_bulk(writable_rurl, self.new_pkg)
                self.pkg("search -s {0} /usr/bin/new".format(windex_url), exit=1)

                # now refresh the index
                self.pkgrepo("-s {0} refresh".format(windex_url))

                # there isn't a synchronous option to pkgrepo, so wait a bit
                # then make sure we do see this new package.
                time.sleep(3)

                # we should now get search results for that new package
                ret, output = self.pkg("search -s {0} /usr/bin/new".format(windex_url),
                    out=True)
                self.assert_("usr/bin/new" in output)
                ret, output = self.pkgrepo("-s {0} list -F tsv".format(windex_url),
                    out=True)
                self.assert_("pkg://test3/sample@1.0" in output)
                self.assert_("pkg://test3/new@1.0" in output)

                # ensure that refresh --no-catalog works, but refresh --no-index
                # does not.
                self.pkgrepo("-s {0} refresh --no-catalog".format(windex_url))
                self.pkgrepo("-s {0} refresh --no-index".format(windex_url), exit=1)

                # check that when we start the depot without -A, we cannot
                # issue refresh commands.
                self.depotconfig("")
                self.start_depot()
                self.pkgrepo("-s {0} refresh".format(windex_url), exit=1)

        def test_15_htheaders(self):
                """Test that the correct Content-Type and Cache-control headers
                are sent from the depot for the responses that we care about."""

                fmris = self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.sample_pkg)
                self.pkgrepo("-s {0} refresh".format(self.dcs[1].get_repo_url()))
                self.depotconfig("")
                self.start_depot()

                # Create an image so we have something to search with.
                # This technically isn't necessary anymore, but the test suite
                # runs with some debug flags to make it (intentionally)
                # difficult to mess with the root image of the test system
                # (even though calling 'pkg search -s' would never actually
                # modify it) Creating an image is just the easier thing to do
                # here.
                self.image_create()
                ret, output = self.pkg("search -s {0}/default -H -o action.hash "
                     "-r /usr/bin/sample".format(self.ac.url), out=True)
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
                    "/default/manifest/0/{0}".format(esc_short_fmri):
                    [("Cache-Control",
                    "must-revalidate, no-transform, max-age=31536000"),
                    ("Content-Type", "text/plain;charset=utf-8")],
                    "/default/search/1/False_2_None_None_%3a%3a%3asample":
                    [("Cache-Control", "no-cache"),
                    ("Content-Type", "text/plain;charset=utf-8")],
                    "/default/file/1/{0}".format(file_hash):
                    [("Cache-Control",
                    "must-revalidate, no-transform, max-age=31536000"),
                    ("Content-Type", "application/data")]
                }

                def header_contains(url, header, value):
                        """Check that HTTP 'header' from 'url' contains an
                        expected value 'value'."""
                        ret = False
                        try:
                                u = urlopen(url)
                                h = u.headers.get(header, "")
                                if value in h:
                                        return True
                        except Exception as e:
                                self.assert_(False, "Error opening {0}: {1}".format(
                                    url, e))
                        return ret

                for path in paths:
                        for headers in paths[path]:
                                name, value = headers
                                url = "{0}{1}".format(self.ac.url, path)
                                self.assert_(header_contains(url, name, value),
                                    "{0} did not contain the header {1}={2}".format(
                                    url, name, value))

        def test_16_htfragment(self):
                """Test that the fragment httpd.conf generated by pkg.depot-config
                can be used in a standard Apache configuration, but that
                pkg(1) admin and search operations fail."""

                self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.sample_pkg)
                self.pkgrepo("-s {0} add-publisher carrots".format(
                    self.dcs[1].get_repo_url()))
                self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.carrots_pkg)
                self.pkgsend_bulk(self.dcs[2].get_repo_url(),
                    self.new_pkg)

                # We shouldn't be able to supply a writable root when running
                # in fragment mode
                self.depotconfig("-l {0} -F -d usr={1} -d spaghetti={2}={3} "
                    "-P testpkg5".format(
                    self.default_depot_runtime, self.rdir1, self.rdir2,
                    self.index_dir), exit=2)
                self.depotconfig("-l {0} -F -d usr={1} -d spaghetti={2} "
                    "-P testpkg5".format(
                    self.default_depot_runtime, self.rdir1, self.rdir2))

                default_httpd_conf_path = os.path.join(self.test_root,
                    "default_httpd.conf")
                httpd_conf = open(default_httpd_conf_path, "w")
                httpd_conf.write(self._default_httpd_conf.format(
                    port=self.depot_port,
                    depot_conf=self.depot_conf_fragment,
                    runtime_dir=self.default_depot_runtime))
                httpd_conf.close()

                # Start an Apache instance
                ac = pkg5unittest.ApacheController(default_httpd_conf_path,
                    self.depot_port, self.default_depot_runtime, testcase=self)
                self.register_apache_controller("depot", ac)
                ac.start()

                # verify the instance is definitely the one using our custom
                # httpd.conf
                u = urlopen("{0}/pkg5test-server-status".format(self.ac.url))
                self.assert_(u.code == http_client.OK,
                    "Error getting pkg5-server-status")

                self.image_create()
                # add publishers for the two repositories being served by this
                # Apache instance
                self.pkg("set-publisher -p {0}/testpkg5/usr".format(self.ac.url))
                self.pkg("set-publisher -p {0}/testpkg5/spaghetti".format(self.ac.url))
                # install packages from the two different publishers in the
                # first repository
                self.pkg("install sample")
                self.pkg("install carrots")
                # install a package from the second repository
                self.pkg("install new")
                # we can't perform remote search or admin operations, since
                # we've no supporting mod_wsgi process.
                self.pkg("search -r new", exit=1)
                self.pkgrepo("-s {0}/testpkg5/usr refresh".format(
                    self.ac.url), exit=1)


class TestHttpsDepot(_Apache, pkg5unittest.HTTPSTestClass):
        """Tests that exercise the pkg.depot-config CLI as well as checking the
        functionality of the depot-config itself for configuring https service.
        This test class will fail if not run as root, since many of the tests
        use 'pkg.depot-config -a' which will attempt to chown a directory to
        pkg5srv:pkg5srv.
        """

        def test_0_invalid_option_combo(self):
                """We return an error given an invalid option combo."""

                cert = os.path.join(self.test_root, "tmp",
                    "ido_exist_cert")
                key = os.path.join(self.test_root, "tmp",
                    "ido_exist_key")
                self.make_misc_files(["tmp/ido_exist_cert",
                    "tmp/ido_exist_key"])

                # Test that without --https, providing certs or keys will fail.
                dummy_ret, dummy_output, err = self.depotconfig(
                    "--cert {0} --key {1}".format(cert, key),
                    out=True, stderr=True, exit=2)
                self.assert_(len(err), "error message: Without --https, "
                            "providing cert or key should fail but succeeded "
                            "instead.")

                dummy_ret, dummy_output, err = self.depotconfig(
                    "--ca-cert {0} --ca-key {1}".format(cert, key),
                    out=True, stderr=True, exit=2)
                self.assert_(len(err), "error message: Without --https, "
                            "providing cert or key should fail but succeeded "
                            "instead.")

                dummy_ret, dummy_output, err = self.depotconfig(
                    "--cert-chain {0}".format(cert), out=True, stderr=True, exit=2)
                self.assert_(len(err), "error message: Without --https, "
                            "providing cert or key should fail but succeeded "
                            "instead.")

                # Checking that HTTPS is not supported in fragment mode.
                dummy_ret, dummy_output, err = self.depotconfig(
                    "--https -F", out=True, stderr=True, exit=2)
                self.assert_(len(err), "error message: Without --https, "
                            "providing cert or key should fail but succeeded "
                            "instead.")

        def test_1_missing_combo_options(self):
                """We return errors if the option in a combo is not specified
                at the same time."""

                cert = os.path.join(self.test_root, "tmp",
                    "ido_exist_cert")
                key = os.path.join(self.test_root, "tmp",
                    "ido_exist_key")
                self.make_misc_files(["tmp/ido_exist_cert",
                    "tmp/ido_exist_key"])

                self.depotconfig("--https --cert {0}".format(cert), exit=2)
                self.depotconfig("--https --key {0}".format(key), exit=2)
                self.depotconfig("--https --ca-cert {0}".format(cert), exit=2)
                self.depotconfig("--https --ca-key {0}".format(key), exit=2)
                self.depotconfig("--https --cert-chain {0}".format(cert), exit=2)

        def test_2_invalid_cert_key_dir(self):
                """We return an error given an invalid cer_key_dir."""

                for invalid_certkey_dir in ["/dev/null", "/etc/passwd"]:
                        ret, output, err = self.depotconfig("--https "
                            "--cert-key-dir {0}".format(
                            invalid_certkey_dir), out=True, stderr=True, exit=1)
                        self.assert_(invalid_certkey_dir in err, "error message "
                           "did not contain {0}: {1}".format(invalid_certkey_dir, err))

        def test_3_non_exist_cert_key(self):
                """We return an error given an non-exist cert or key."""

                non_exist_cert = os.path.join(self.test_root,
                    "idonot_exist_cert")
                non_exist_key = os.path.join(self.test_root,
                    "idonot_exist_key")
                exist_cert = os.path.join(self.test_root, "tmp",
                    "ido_exist_cert")
                exist_key = os.path.join(self.test_root, "tmp",
                    "ido_exist_key")
                self.make_misc_files(["tmp/ido_exist_cert",
                    "tmp/ido_exist_key"])

                # Test checking user provided server cert works.
                dummy_ret, dummy_output, err = self.depotconfig("--https "
                    "--cert {0} --key {1}".format(non_exist_cert, exist_key),
                    out=True, stderr=True, exit=1)
                self.assert_(non_exist_cert in err, "error message "
                    "did not contain {0}: {1}".format(non_exist_cert, err))

                # Test checking user provided server key works.
                dummy_ret, dummy_output, err = self.depotconfig("--https "
                    "--cert {0} --key {1}".format(exist_cert, non_exist_key),
                    out=True, stderr=True, exit=1)
                self.assert_(non_exist_key in err, "error message "
                    "did not contain {0}: {1}".format(non_exist_key, err))

                # Test checking user provided cert chain file works.
                dummy_ret, dummy_output, err = self.depotconfig("--https "
                    "--cert {0} --key {1} --cert-chain {2}".format(
                    exist_cert, exist_key, non_exist_cert),
                    out=True, stderr=True, exit=1)
                self.assert_(non_exist_cert in err, "error message "
                    "did not contain {0}: {1}".format(non_exist_cert, err))

                # Test checking user provided CA cert file works.
                tmp_dir = os.path.join(self.test_root, "tmp")
                dummy_ret, dummy_output, err = self.depotconfig("--https "
                    "--ca-cert {0} --ca-key {1} --cert-key-dir {2}".format(
                    non_exist_cert, exist_key, tmp_dir),
                    out=True, stderr=True, exit=1)
                self.assert_(non_exist_cert in err, "error message "
                    "did not contain {0}: {1}".format(non_exist_cert, err))

                # Test checking user provided CA key file works.
                dummy_ret, dummy_output, err = self.depotconfig("--https "
                    "--ca-cert {0} --ca-key {1} --cert-key-dir {2}".format(
                    exist_cert, non_exist_key, tmp_dir),
                    out=True, stderr=True, exit=1)
                self.assert_(non_exist_key in err, "error message "
                    "did not contain {0}: {1}".format(non_exist_key, err))

        def test_4_invalid_smf_fmri(self):
                """We return an error given an invalid pkg/depot smf fmri."""

                some_fake_file = os.path.join(self.test_root, "tmp",
                    "some_fake_file")
                self.make_misc_files(["tmp/some_fake_file"])
                tmp_dir = os.path.join(self.test_root, "tmp")
                # Test with invalid fmri.
                for invalid_fmri in ["svc:", "svc://notexist", some_fake_file]:
                        dummy_ret, dummy_output, err = self.depotconfig(
                            "--https --cert-key-dir {0} --smf-fmri {1}".format(
                            tmp_dir, invalid_fmri), out=True, stderr=True)
                        self.assert_(len(err), "error message: SMF FMRI "
                            "setting should fail but succeeded instead.")

                # Test with wrong fmri.
                wrong_fmri = "pkg/server:default"
                dummy_ret, dummy_output, err = self.depotconfig(
                    "--https --cert-key-dir {0} --smf-fmri {1}".format(
                    tmp_dir, wrong_fmri), out=True, stderr=True, exit=1)
                self.assert_(len(err), "error message: SMF FMRI "
                    "setting should fail but succeeded instead.")

        def test_5_https_gen_cert(self):
                """Test that https functionality works as expected."""

                self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.sample_pkg)
                self.pkgrepo("-s {0} add-publisher carrots".format(
                    self.dcs[1].get_repo_url()))
                self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.carrots_pkg)
                self.pkgsend_bulk(self.dcs[2].get_repo_url(),
                    self.new_pkg)

                cert_key_dir = os.path.join(self.default_depot_runtime,
                    "cert_key")
                if os.path.isdir(cert_key_dir):
                        shutil.rmtree(cert_key_dir)

                cache_dir = os.path.join(self.test_root, "cache_test_dir")
                self.depotconfig("-l {0} -r {1} -c {2} -d usr={3} -d spa={4} -p {5} "
                    "--https -T {6} -h localhost --cert-key-dir {7}".format(
                    self.default_depot_runtime, self.default_depot_runtime,
                    cache_dir, self.rdir1, self.rdir2, self.depot_port,
                    self.depot_template_dir, cert_key_dir))
                server_id = "localhost_{0}".format(self.depot_port)
                ca_cert_file = os.path.join(cert_key_dir, "ca_{0}_cert.pem".format(
                    server_id))
                DebugValues["ssl_ca_file"] = ca_cert_file

                # Start an Apache instance
                self.default_depot_conf = os.path.join(
                    self.default_depot_runtime, "depot_httpd.conf")
                ac = pkg5unittest.HttpDepotController(self.default_depot_conf,
                    self.depot_port, self.default_depot_runtime, testcase=self,
                    https=True)
                self.register_apache_controller("depot", ac)
                ac.start()
                self.image_create()

                # add publishers for the two repositories being served by this
                # Apache instance.
                self.pkg("set-publisher -p {0}/usr".format(self.ac.url))
                self.pkg("set-publisher -p {0}/spa".format(self.ac.url))
                # install packages from the two different publishers in the
                # first repository
                self.pkg("install sample")
                self.pkg("install carrots")
                # install a package from the second repository
                self.pkg("install new")
                # we can't perform remote search or admin operations, since
                # we've no supporting mod_wsgi process.
                self.pkg("search -r new", exit=1)
                self.pkgrepo("-s {0}/testpkg5/usr refresh".format(
                    self.ac.url), exit=1)

        def test_6_https_cert_chain(self):
                """Test that https functionality with cert chain works as
                expected."""

                self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.sample_pkg)
                self.pkgrepo("-s {0} add-publisher carrots".format(
                    self.dcs[1].get_repo_url()))
                self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.carrots_pkg)
                self.pkgsend_bulk(self.dcs[2].get_repo_url(),
                    self.new_pkg)

                cert_key_dir = os.path.join(self.default_depot_runtime,
                    "cert_key_dir")
                if os.path.isdir(cert_key_dir):
                        shutil.rmtree(cert_key_dir)
                os.makedirs(cert_key_dir)
                cg = certgenerator.CertGenerator(base_dir=cert_key_dir)
                cg.make_trust_anchor("ta", https=True)
                cg.make_ca_cert("ca_ta", "ta", https=True)
                cg.make_cs_cert("cs_ta", "ca_ta", parent_loc="chain_certs",
                    https=True)

                ta_cert_file = os.path.join(cg.raw_trust_anchor_dir,
                    "ta_cert.pem")
                ca_cert_file = os.path.join(cg.chain_certs_dir,
                    "ca_ta_cert.pem")
                cs_cert_file = os.path.join(cg.cs_dir, "cs_ta_cert.pem")
                cs_key_file = os.path.join(cg.keys_dir, "cs_ta_key.pem")

                cache_dir = os.path.join(self.test_root, "cache_test_dir")
                self.depotconfig("-l {0} -r {1} -c {2} -d usr={3} -d spa={4} -p {5} "
                    "--https -T {6} -h localhost --cert {7} --key {8} "
                    "--cert-chain {9}".format(
                    self.default_depot_runtime, self.default_depot_runtime,
                    cache_dir, self.rdir1, self.rdir2, self.depot_port,
                    self.depot_template_dir, cs_cert_file, cs_key_file,
                    ca_cert_file))

                DebugValues["ssl_ca_file"] = ta_cert_file

                # Start an Apache instance
                self.default_depot_conf = os.path.join(
                    self.default_depot_runtime, "depot_httpd.conf")
                ac = pkg5unittest.HttpDepotController(self.default_depot_conf,
                    self.depot_port, self.default_depot_runtime, testcase=self,
                    https=True)
                self.register_apache_controller("depot", ac)
                ac.start()
                self.image_create()

                # add publishers for the two repositories being served by this
                # Apache instance.
                self.pkg("set-publisher -p {0}/usr".format(self.ac.url))
                self.pkg("set-publisher -p {0}/spa".format(self.ac.url))
                # install packages from the two different publishers in the
                # first repository
                self.pkg("install sample")
                self.pkg("install carrots")
                # install a package from the second repository
                self.pkg("install new")

        def test_7_https_provided_ca(self):
                """Test that pkg.depot-config functionality with provided
                ca certificate and key works as expected."""

                self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.sample_pkg)
                self.pkgrepo("-s {0} add-publisher carrots".format(
                    self.dcs[1].get_repo_url()))
                self.pkgsend_bulk(self.dcs[1].get_repo_url(),
                    self.carrots_pkg)
                self.pkgsend_bulk(self.dcs[2].get_repo_url(),
                    self.new_pkg)

                cert_key_dir = os.path.join(self.default_depot_runtime,
                    "cert_key_dir")
                if os.path.isdir(cert_key_dir):
                        shutil.rmtree(cert_key_dir)
                os.makedirs(cert_key_dir)

                cg = certgenerator.CertGenerator(base_dir=cert_key_dir)
                cg.make_trust_anchor("ta", https=True)

                ta_cert_file = os.path.join(cg.raw_trust_anchor_dir,
                    "ta_cert.pem")
                ta_key_file = os.path.join(cg.keys_dir, "ta_key.pem")

                cache_dir = os.path.join(self.test_root, "cache_test_dir")
                self.depotconfig("-l {0} -r {1} -c {2} -d usr={3} -d spa={4} -p {5} "
                    "--https -T {6} -h localhost --ca-cert {7} --ca-key {8} "
                    "--cert-key-dir {9}".format(
                    self.default_depot_runtime, self.default_depot_runtime,
                    cache_dir, self.rdir1, self.rdir2, self.depot_port,
                    self.depot_template_dir, ta_cert_file, ta_key_file,
                    cert_key_dir))

                DebugValues["ssl_ca_file"] = ta_cert_file

                # Start an Apache instance
                self.default_depot_conf = os.path.join(
                    self.default_depot_runtime, "depot_httpd.conf")
                ac = pkg5unittest.HttpDepotController(self.default_depot_conf,
                    self.depot_port, self.default_depot_runtime, testcase=self,
                    https=True)
                self.register_apache_controller("depot", ac)
                ac.start()
                self.image_create()

                # add publishers for the two repositories being served by this
                # Apache instance.
                self.pkg("set-publisher -p {0}/usr".format(self.ac.url))
                self.pkg("set-publisher -p {0}/spa".format(self.ac.url))
                # install packages from the two different publishers in the
                # first repository
                self.pkg("install sample")
                self.pkg("install carrots")
                # install a package from the second repository
                self.pkg("install new")


if __name__ == "__main__":
        unittest.main()
