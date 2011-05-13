#!/usr/bin/python2.6
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
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import copy
import hashlib
import os
import shutil
import signal
import sys
import time

import pkg.client.api as api
import pkg.client.api_errors as apx
import pkg.client.transport.exception as tx
import pkg.misc as misc

class PC(object):
        """This class contains publisher configuration used for setting up the
        depots and https apache instances needed by the tests."""

        def __init__(self, url, sticky=True, mirrors=misc.EmptyI, https=False,
            server_ta=None, client_ta=None, disabled=False, name=None):
                assert (https and server_ta and client_ta) or \
                    not (https or server_ta or client_ta)
                assert not disabled or name
                self.url= url
                self.sticky = sticky
                self.https = https
                self.mirrors = mirrors
                self.server_ta = server_ta
                self.client_ta = client_ta
                self.disabled = disabled
                self.name = name

class TestSysrepo(pkg5unittest.ManyDepotTestCase):
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add file tmp/example_file mode=0555 owner=root group=bin path=/usr/bin/example_path
            close"""

        foo10 = """
            open foo@1.0,5.11-0
            close"""

        bar10 = """
            open bar@1.0,5.11-0
            close"""

        misc_files = ["tmp/example_file"]

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
                        for ac in self.acs.values():
                                self.debug("stopping https apache proxy")
                                try:
                                        ac.stop()
                                except Exception,e :
                                        try:
                                                self.debug(
                                                    "killing apache instance")
                                                self.ac.kill()
                                        except Exception, e:
                                                pass

        def setUp(self):
                # These need to be set before calling setUp in case setUp fails.
                self.sc = None
                self.acs = {}
                self.smf_cmds = {}

                # These need to set to allow the smf commands to give the right
                # responses.
                self.sysrepo_port = self.next_free_port
                self.next_free_port += 1
                self.sysrepo_alt_port = self.next_free_port
                self.next_free_port += 1

                # Set up the smf commands that these tests use.
                smf_conf_dict = {"proxy_port": self.sysrepo_port}
                for n in self.__smf_cmds_template:
                        self.smf_cmds[n] = self.__smf_cmds_template[n] % \
                            smf_conf_dict

                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test12",
                    "test3"], start_depots=True)
                self.testdata_dir = os.path.join(self.test_root, "testdata")
                self.make_misc_files(self.misc_files)

                self.durl1 = self.dcs[1].get_depot_url()
                self.durl2 = self.dcs[2].get_depot_url()
                self.durl3 = self.dcs[3].get_depot_url()
                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                self.rurl3 = self.dcs[3].get_repo_url()
                self.apache_dir = os.path.join(self.test_root, "apache")
                self.apache_log_dir = os.path.join(self.apache_dir,
                    "apache_logs")

                self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                self.pkgsend_bulk(self.rurl2, self.foo10)
                self.pkgsend_bulk(self.rurl3, self.bar10)

                self.common_config_dir = os.path.join(self.test_root,
                    "apache-serve")
                self.htdocs_dir = os.path.join(self.common_config_dir, "htdocs")
                self.apache_confs = {}

                self.rurl2_old = self.rurl2.rstrip("/") + ".old"
                self.pkgsend(self.rurl2_old, "create-repository "
                    "--set-property publisher.prefix=test12")

                # Establish the different publisher configurations that tests
                # will need.
                self.configs = {
                    "all-access": ([
                        PC(self.durl1),
                        PC(self.durl2, sticky=False),
                        PC(self.durl3)]),
                    "all-access-f": ([
                        PC(self.rurl1),
                        PC(self.rurl2, sticky=False),
                        PC(self.rurl3)]),
                    "disabled": ([
                        PC(self.durl1, disabled=True, name="test1"),
                        PC(self.durl2, sticky=False),
                        PC(self.durl3)]),
                    "https-access": ([
                        PC(self.durl1, https=True, server_ta="ta11",
                            client_ta="ta6"),
                        PC(self.durl2, sticky=False, https=True,
                            server_ta="ta7", client_ta="ta8"),
                        PC(self.durl3, https=True, server_ta="ta9",
                            client_ta="ta10")]),
                    "mirror-access": ([
                        PC(self.durl1, mirrors=[("test1", self.rurl1)]),
                        PC(self.durl2, sticky=False,
                            mirrors=[("test12", self.rurl2)]),
                        PC(self.durl3, mirrors=[("test3", self.rurl3)])]),
                    "mirror-access-f": ([
                        PC(self.rurl1, mirrors=[("test1", self.durl1)]),
                        PC(self.rurl2, sticky=False,
                            mirrors=[("test12", self.durl2)]),
                        PC(self.rurl3, mirrors=[("test3", self.durl3)])]),
                    "none": [],
                    "old-file": ([
                        PC(self.rurl1),
                        PC(self.rurl2_old, sticky=False),
                        PC(self.rurl3)]),
                    "test1": ([PC(self.durl1)]),
                    "test1-test12": ([
                        PC(self.durl1),
                        PC(self.durl2, sticky=False)]),
                    "test1-test3": ([
                        PC(self.durl1),
                        PC(self.durl3)]),
                    "test12": ([
                        PC(self.durl2, sticky=False)]),
                    "test12-test3": ([
                        PC(self.durl2, sticky=False),
                        PC(self.durl3)]),
                    "test3": ([PC(self.durl3)]),
                }

                # Config needed for https apache instances.
                self.path_to_certs = os.path.join(self.ro_data_root,
                    "signing_certs", "produced")
                self.keys_dir = os.path.join(self.path_to_certs, "keys")
                self.cs_dir = os.path.join(self.path_to_certs,
                    "code_signing_certs")
                self.chain_certs_dir = os.path.join(self.path_to_certs,
                    "chain_certs")
                self.pub_cas_dir = os.path.join(self.path_to_certs,
                    "publisher_cas")
                self.inter_certs_dir = os.path.join(self.path_to_certs,
                    "inter_certs")
                self.raw_trust_anchor_dir = os.path.join(self.path_to_certs,
                    "trust_anchors")
                self.crl_dir = os.path.join(self.path_to_certs, "crl")

                self.base_conf_dict = {
                    "common_log_format": "%h %l %u %t \\\"%r\\\" %>s %b",
                    "ssl-special": "%{SSL_CLIENT_I_DN_OU}",
                }
                # Pick a directory to store all the https apache configuration
                # in.
                self.base_https_dir = os.path.join(self.test_root, "https")

        def __start_https(self, pc):
                # Start up an https apache config
                cd = copy.copy(self.base_conf_dict)

                # This apache instance will need a free port.
                https_port = self.next_free_port
                self.next_free_port += 1

                # Set up the directories and configuration this instance of
                # apache will need.
                instance_dir = os.path.join(self.base_https_dir,
                    str(https_port))
                log_dir = os.path.join(instance_dir, "https_logs")
                content_dir = os.path.join(instance_dir, "content")
                os.makedirs(instance_dir)
                os.makedirs(log_dir)
                os.makedirs(content_dir)
                cd.update({
                    "https_port": https_port,
                    "log_locs": log_dir,
                    "pidfile": os.path.join(instance_dir, "httpd.pid"),
                    "port": https_port,
                    "proxied-server": pc.url,
                    "server-ca-cert":os.path.join(self.raw_trust_anchor_dir,
                        "%s_cert.pem" % pc.client_ta),
                    "server-ca-taname": pc.client_ta,
                    "serve_root": content_dir,
                    "server-ssl-cert":os.path.join(self.cs_dir,
                        "cs1_%s_cert.pem" % pc.server_ta),
                    "server-ssl-key":os.path.join(self.keys_dir,
                        "cs1_%s_key.pem" % pc.server_ta),
                })
                conf_path = os.path.join(instance_dir, "https.conf")
                with open(conf_path, "wb") as fh:
                        fh.write(self.https_conf % cd)

                ac = pkg5unittest.ApacheController(conf_path, https_port,
                    instance_dir, https=True)
                self.acs[pc.url] = ac
                ac.start()
                return ac

        def __prep_configuration(self, names, port=None):
                if not port:
                        port = self.sysrepo_port
                self.__configured_names = []
                if isinstance(names, basestring):
                        names = [names]
                for name in names:
                        pcs = self.configs[name]
                        self.image_create()
                        for pc in pcs:
                                cmd = "set-publisher"
                                if not pc.sticky:
                                        cmd += " --non-sticky"
                                if not pc.https:
                                        cmd += " -p %s" % pc.url
                                else:
                                        if pc.url in self.acs:
                                                ac = self.acs[pc.url]
                                        else:
                                                ac = self.__start_https(pc)
                                        # Configure image to use apache instance
                                        cmd = " --debug " \
                                            "ssl_ca_file=%(ca_file)s %(cmd)s " \
                                            "-k %(key)s -c %(cert)s " \
                                            "-p %(url)s" % {
                                                "ca_file": os.path.join(
                                                    self.raw_trust_anchor_dir,
                                                    "%s_cert.pem" %
                                                    pc.server_ta),
                                                "cert": os.path.join(
                                                    self.cs_dir,
                                                    "cs1_%s_cert.pem" %
                                                    pc.client_ta),
                                                "cmd": cmd,
                                                "key": os.path.join(
                                                    self.keys_dir,
                                                    "cs1_%s_key.pem" %
                                                    pc.client_ta),
                                                "url": ac.url,
                                            }
                                self.pkg(cmd, debug_smf=False)
                                for pub, m in pc.mirrors:
                                        self.pkg(
                                            "set-publisher -m %s %s" % (m, pub))
                                if pc.disabled:
                                        self.pkg("set-publisher -d %s" %
                                            pc.name)

                        self.sysrepo("-l %(log_locs)s -p %(port)s "
                            "-r %(common_serve)s" % {
                                "log_locs": self.apache_log_dir,
                                "port": port,
                                "common_serve": self.common_config_dir
                            })
                        st = os.stat(os.path.join(self.common_config_dir,
                            "htdocs"))
                        uid = st.st_uid
                        gid = st.st_gid
                        conf_dir = os.path.join(self.test_root, "apache-conf",
                            name)
                        shutil.move(self.common_config_dir, conf_dir)
                        st2 = os.stat(conf_dir)
                        new_uid = st2.st_uid
                        new_gid = st2.st_gid
                        if new_uid != uid or new_gid != gid:
                                misc.recursive_chown_dir(conf_dir, uid, gid)
                        self.apache_confs[name] = os.path.join(self.test_root,
                            "apache-conf", name, "sysrepo_httpd.conf")
                        self.__configured_names.append(name)
                        self.image_destroy()

        def __set_responses(self, name, update_conf=True):
                if name not in self.__configured_names:
                        raise RuntimeError("%s hasn't been prepared for this "
                            "test." % name)
                base_dir = os.path.join(self.test_root, "apache-conf", name,
                    "htdocs")
                if not os.path.isdir(base_dir):
                        raise RuntimeError("Expected %s to already exist and "
                            "be a directory but it's not." % base_dir)
                if os.path.isdir(self.htdocs_dir):
                        shutil.rmtree(self.htdocs_dir)
                shutil.copytree(base_dir, self.htdocs_dir)
                crypto_path = os.path.join(self.common_config_dir, "crypto.txt")
                if os.path.exists(crypto_path):
                        os.chmod(crypto_path, 0600)
                shutil.copy(os.path.join(self.test_root, "apache-conf", name,
                    "crypto.txt"), self.common_config_dir)
                os.chmod(crypto_path, 0400)
                st = os.stat(base_dir)
                uid = st.st_uid
                gid = st.st_gid
                st2 = os.stat(self.htdocs_dir)
                new_uid = st2.st_uid
                new_gid = st2.st_gid
                if uid != new_gid or gid != new_gid:
                        misc.recursive_chown_dir(self.common_config_dir, uid,
                            gid)
                if update_conf and self.sc:
                        self.sc.conf = self.apache_confs[name]

        def __check_publisher_info(self, expected, set_debug_value=True):
                self.pkg("publisher -F tsv", debug_smf=set_debug_value)
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output, bound_white_space=True)

        def __check_package_lists(self, expected):
                self.pkg("list -Ha")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def __check_publisher_dirs(self, pubs):
                pub_dir = os.path.join(self.img_path(), "var/pkg/publisher")
                for p in pubs:
                        if not os.path.isdir(os.path.join(pub_dir, p)):
                                raise RuntimeError("Publisher %s was expected "
                                    "to exist but its directory is missing "
                                    "from the image directory." % p)
                for d in os.listdir(pub_dir):
                        if d not in pubs:
                                raise RuntimeError("%s was not expected in the "
                                    "publisher directory but was found." % d)

        def test_01_basics(self):
                """Test that an image with no publishers can be created and that
                it can pick up its publisher configuration from the system
                repository."""

                self.__prep_configuration("all-access")
                self.__set_responses("all-access")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["all-access"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})
                # Make sure that the publisher catalogs were created.
                for n in ("test1", "test12", "test3"):
                        self.assert_(os.path.isdir(os.path.join(self.img_path(),
                            "var/pkg/publisher/%s" % n)))
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.durl1, self.durl2, self.durl3)
                self.__check_publisher_info(expected)

                self.pkg("publisher test1")
                # Test that the publishers have the right uris.
                self.pkg(
                    "publisher test1 | grep 'proxy://%s'" % self.durl1)
                self.pkg(
                    "publisher test12 | grep 'proxy://%s'" % self.durl2)
                self.pkg(
                    "publisher test3 | grep 'proxy://%s'" % self.durl3)
                # Test that a new pkg process will pick up the right catalog.
                self.pkg("list -a")
                self.pkg("install example_pkg")

                # Test that the current api object has the right catalog.
                self._api_install(api_obj, ["foo", "bar"])

        def test_02_communication(self):
                """Test that the transport for communicating with the depots is
                actually going through the proxy. This is done by
                "misconfiguring" the system repository so that it refuses to
                proxy to certain depots then operations which would communicate
                with those depots fail."""

                self.__prep_configuration(["all-access", "none", "test12-test3",
                    "test3"])
                self.__set_responses("all-access")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["none"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)

                self.sc.start()
                self.assertRaises(apx.CatalogRefreshException,
                    self.image_create, props={"use-system-repo": True})
                self.sc.conf = self.apache_confs["all-access"]
                api_obj = self.image_create(props={"use-system-repo": True})
                self.sc.conf = self.apache_confs["none"]

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.durl1, self.durl2, self.durl3)
                self.__check_publisher_info(expected)

                self.pkg("list -a")
                self.pkg("contents -rm example_pkg", exit=1)
                self.pkg("contents -rm foo", exit=1)
                self.pkg("contents -rm bar", exit=1)
                self.pkg("install --no-refresh example_pkg", exit=1)
                self.pkg("install --no-refresh foo", exit=1)
                self.pkg("install --no-refresh bar", exit=1)
                self.assertRaises(tx.TransportFailures, self._api_install,
                    api_obj, ["example_pkg"], refresh_catalogs=False)
                self.assertRaises(tx.TransportFailures, self._api_install,
                    api_obj, ["foo"], refresh_catalogs=False)
                self.assertRaises(tx.TransportFailures, self._api_install,
                    api_obj, ["bar"], refresh_catalogs=False)

                self.sc.conf = self.apache_confs["test3"]
                self.pkg("list -a")
                self.pkg("contents -rm example_pkg", exit=1)
                self.pkg("contents -rm foo", exit=1)
                self.pkg("contents -rm bar")
                self.assertRaises(tx.TransportFailures, self._api_install,
                    api_obj, ["example_pkg"], refresh_catalogs=False)
                self.assertRaises(tx.TransportFailures, self._api_install,
                    api_obj, ["foo"], refresh_catalogs=False)
                self._api_install(api_obj, ["bar"], refresh_catalogs=False)


                self.sc.conf = self.apache_confs["test12-test3"]
                self.pkg("list -a")
                self.pkg("contents -rm example_pkg", exit=1)
                self.pkg("contents -rm foo")
                self.assertRaises(tx.TransportFailures, self._api_install,
                    api_obj, ["example_pkg"], refresh_catalogs=False)
                self._api_install(api_obj, ["foo"], refresh_catalogs=False)

                self.sc.conf = self.apache_confs["all-access"]
                self.pkg("list -a")
                self.pkg("contents -rm example_pkg")
                self._api_install(api_obj, ["example_pkg"])

        def test_03_user_modifying_configuration(self):
                """Test that adding and removing origins to a system publisher
                works as expected and that modifying other configuration of a
                system publisher fails."""

                self.__prep_configuration(["test1", "none"])
                self.__set_responses("test1")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["test1"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                # Test that most modifications to a system publisher fail.
                self.pkg("set-publisher -d test1", exit=1)
                self.pkg("set-publisher -e test1", exit=1)
                self.pkg("set-publisher --non-sticky test1", exit=1)
                self.pkg("set-publisher --sticky test1", exit=1)
                self.pkg("set-publisher --set-property foo=bar test1", exit=1)
                self.pkg("set-publisher --unset-property test-property test1",
                    exit=1)
                self.pkg("set-publisher --add-property-value test-property=bar "
                    "test1", exit=1)
                self.pkg("set-publisher --remove-property-value "
                    "test-property=test test1", exit=1)
                self.pkg("unset-publisher test1", exit=1)
                self.pkg("set-publisher --search-first test1", exit=1)
                self.pkg("set-publisher -m %s test1" % self.rurl1)

                # Add an origin to an existing system publisher.
                self.pkg("set-publisher -g %s test1" % self.rurl1)

                # Check that the publisher information is shown correctly.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.rurl1, self.durl1)
                self.__check_publisher_info(expected)

                # Check that the publisher specific information has information
                # for both origins.
                self.pkg("publisher test1 | grep %s" % self.rurl1)
                self.pkg("publisher test1 | grep proxy://%s/" % self.durl1)

                # Change the proxy configuration so that the image can't use it
                # to communicate with the depot. This forces communication to
                # go through the user configured origin.
                self.sc.conf = self.apache_confs["none"]

                # Check that the catalog can't be refreshed and that the
                # communcation with the repository fails.
                self.pkg("contents -rm example_pkg")
                self.pkg("refresh --full", exit=1)

                # Check that removing the system configured origin fails.
                self.pkg("set-publisher -G %s test1" % self.durl1, exit=1)
                self.pkg("set-publisher -G proxy://%s test1" % self.durl1,
                    exit=1)
                # Check that removing the user configured origin succeeds.
                self.pkg("set-publisher -G %s test1" % self.rurl1)

                # Check that the user configured origin is gone.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % self.durl1
                self.__check_publisher_info(expected)

                # Ensure that previous communication was going through the file
                # repo by confirming that communication to the depot is still
                # refused.
                self.pkg("refresh --full", exit=1)

                # Reenable access to the depot to make sure nothing has been
                # broken in the image.
                self.sc.conf = self.apache_confs["test1"]
                self.pkg("refresh --full")

        def test_04_changing_syspub_configuration(self):
                """Test that changes to the syspub/0 response are handled
                correctly by the client."""

                # Check that a syspub/0 response with no configured publisers
                # works.
                self.__prep_configuration(["none", "test1-test12",
                    "test1-test3", "test12"])
                self.__set_responses("none")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["none"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
"""
                self.__check_publisher_info(expected)

                # The user configures test1 as a publisher.
                self.pkg("set-publisher --non-sticky -p %s" % self.durl1)
                self.__check_publisher_dirs(["test1"])
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\tfalse\tfalse\ttrue\torigin\tonline\t%s/
""" % self.durl1
                self.__check_publisher_info(expected)

                self.pkg("set-publisher -d test1")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\tfalse\tfalse\tfalse\torigin\tonline\t%s/
""" % self.durl1
                self.__check_publisher_info(expected)
                self.__check_publisher_dirs([])

                # Now the syspub/0 response configures two publishers. The
                # test12 publisher is totally new while the test1 publisher
                # overlaps with the publisher the user configured.
                self.__set_responses("test1-test12")

                # Check that the syspub/0 sticky setting has overriden the user
                # configuration and that the other publisher information is as
                # expected.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.durl1, self.durl1, self.durl2)
                self.__check_publisher_info(expected)
                self.__check_publisher_dirs([])

                expected = """\
example_pkg 1.0-0 ---
foo (test12) 1.0-0 ---
"""
                self.__check_package_lists(expected)
                self.pkg("refresh --full")

                self.pkg("contents -rm example_pkg")
                self.pkg("contents -rm foo")
                self.pkg("contents -rm bar", exit=1)

                # Now the syspub/0 response configures two publishers, test1 and
                # test 3.
                self.__set_responses("test1-test3")

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.durl1, self.durl1, self.durl3)
                self.__check_publisher_info(expected)
                # Only test1 is expected to exist because only it was present in
                # both the old configuration and the current configuration.
                self.__check_publisher_dirs(["test1"])

                expected = """\
bar (test3) 1.0-0 ---
example_pkg 1.0-0 ---
"""
                self.__check_package_lists(expected)

                self.pkg("contents -rm example_pkg")
                self.pkg("contents -rm foo", exit=1)
                self.pkg("contents -m foo", exit=1)
                self.pkg("contents -rm bar")
                self.pkg("refresh --full")

                # The user adds an origin to the system publisher test3.
                self.pkg("set-publisher -g %s test3" % self.durl3)

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.durl1, self.durl1, self.durl3, self.durl3)
                self.__check_publisher_info(expected)
                self.__check_publisher_dirs(["test1", "test3"])


                expected = """\
bar (test3) 1.0-0 ---
example_pkg 1.0-0 ---
"""
                self.__check_package_lists(expected)
                self.pkg("refresh --full")

                # Now syspub/0 removes test1 and test3 as publishers and returns
                # test12 as a publisher.
                self.__set_responses("test12")

                # test1 and test3 should be retained as a publisher because the
                # user addded an origin for them. test1 should also return to
                # the settings the user had previously configured. test12 should
                # be listed first since, because it's a system publisher, it's
                # higher ranked.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%s/
test1\tfalse\tfalse\tfalse\torigin\tonline\t%s/
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.durl2, self.durl1, self.durl3)
                self.__check_publisher_info(expected)

                self.pkg("refresh --full")

                expected = """\
bar (test3) 1.0-0 ---
foo 1.0-0 ---
"""
                self.__check_package_lists(expected)

                # Install a package from test12.
                self.pkg("install foo")

                # Now syspub/0 removes test12 as a publisher as well.
                self.__set_responses("none")

                # test12 should be disabled and at the bottom of the list
                # because a package was installed from it prior to its removal
                # as a system publisher.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\tfalse\tfalse\tfalse\torigin\tonline\t%s/
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test12\tfalse\ttrue\tfalse\torigin\tonline\tproxy://%s/
""" % (self.durl1, self.durl3, self.durl2)
                self.__check_publisher_info(expected)

                # Uninstalling foo should remove test12 from the list of
                # publishers.
                self.pkg("uninstall foo")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\tfalse\tfalse\tfalse\torigin\tonline\t%s/
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.durl1, self.durl3)
                self.__check_publisher_info(expected)

        def test_05_simultaneous_change(self):
                """Test that simultaneous changes in both user configuration and
                system publisher state are handled correctly."""

                self.__prep_configuration(["none", "test1", "test12"])
                # Create an image with no user configured publishers and no
                # system configured publishers.
                self.__set_responses("none")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["none"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
"""
                self.__check_publisher_info(expected)

                # Have the user configure test1 at the same time that test1 is
                # made a system publisher.
                self.__set_responses("test1")
                # This fails in the same way that doing set-publisher -p for a
                # repository which provides packages for an already configured
                # publisher fails.
                self.pkg("set-publisher -p %s" % self.rurl1, exit=1)
                # Adding the origin to the publisher which now exists should
                # work fine.
                self.pkg("set-publisher -g %s test1" % self.rurl1)
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.rurl1, self.durl1)
                self.__check_publisher_info(expected)

                # The user adds an origin to test12 at the same time that test12
                # first becomes known to the image.
                self.__set_responses("test12")
                self.pkg("set-publisher -g %s test12" % self.rurl2)
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test12\tfalse\ttrue\ttrue\torigin\tonline\t%s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%s/
test1\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.rurl2, self.durl2, self.rurl1)
                self.__check_publisher_info(expected)

                self.pkg("publisher")
                self.debug(self.output)
                # The user removes the origin for test12 at the same time that
                # test12 stops being a system publisher and test1 is added as a
                # system publisher.
                self.__set_responses("test1")
                self.pkg("set-publisher -G %s test12" % self.rurl2)
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test12\ttrue\tfalse\ttrue\t\t\t
""" % (self.rurl1, self.durl1)
                self.__check_publisher_info(expected)

                # The user now removes the originless publisher
                self.pkg("unset-publisher test12")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.rurl1, self.durl1)
                self.__check_publisher_info(expected)

                # The user now unsets test1 at the same time that test1 stops
                # being a system publisher.
                self.__set_responses("none")
                self.pkg("unset-publisher test1")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
"""
                self.__check_publisher_info(expected)

        def test_06_ordering(self):
                """Test that publishers have the right search order given both
                user configuration and whether a publisher is a system
                publisher."""

                self.__prep_configuration(["all-access", "none", "test1"])
                self.__set_responses("none")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["none"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                self.pkg("set-publisher -p %s" % self.rurl3)
                self.pkg("set-publisher -p %s" % self.rurl2)
                self.pkg("set-publisher -p %s" % self.rurl1)

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test12\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test1\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.rurl3, self.rurl2, self.rurl1)
                self.__check_publisher_info(expected)

                self.__set_responses("all-access")

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test12\tfalse\ttrue\ttrue\torigin\tonline\t%s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.rurl1, self.durl1, self.rurl2, self.durl2, self.rurl3, self.durl3)
                self.__check_publisher_info(expected)

                self.pkg("set-property use-system-repo False")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test12\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test1\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.rurl3, self.rurl2, self.rurl1)
                self.__check_publisher_info(expected)

                self.pkg("set-property use-system-repo True")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test12\tfalse\ttrue\ttrue\torigin\tonline\t%s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.rurl1, self.durl1, self.rurl2, self.durl2, self.rurl3, self.durl3)
                self.__check_publisher_info(expected)

                self.__set_responses("test1")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test12\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.rurl1, self.durl1, self.rurl3, self.rurl2)
                self.__check_publisher_info(expected)

                self.pkg("set-publisher --search-before test3 test12")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test12\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.rurl1, self.durl1, self.rurl2, self.rurl3)
                self.__check_publisher_info(expected)

                self.pkg("set-publisher --search-after test3 test12")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test12\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.rurl1, self.durl1, self.rurl3, self.rurl2)
                self.__check_publisher_info(expected)

                self.pkg("set-publisher --search-before test1 test12", exit=1)
                self.pkg("set-publisher -d --search-before test1 test12",
                    exit=1)
                # Ensure that test12 is not disabled.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test12\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.rurl1, self.durl1, self.rurl3, self.rurl2)
                self.__check_publisher_info(expected)
                self.pkg("set-publisher --search-after test1 test12", exit=1)
                self.pkg("set-publisher --non-sticky --search-after test1 "
                    "test12", exit=1)
                # Ensure that test12 is still sticky.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test12\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.rurl1, self.durl1, self.rurl3, self.rurl2)
                self.__check_publisher_info(expected)

                # Check that attempting to change test12 relative to test1
                # fails.
                self.pkg("set-publisher --search-before test12 test1", exit=1)
                self.pkg("set-publisher --search-after test12 test1", exit=1)
                self.pkg("set-publisher --search-first test12")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\t%s/
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test12\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.rurl1, self.durl1, self.rurl2, self.rurl3)
                self.__check_publisher_info(expected)

                self.pkg("set-property use-system-repo False")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test12\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test3\ttrue\tfalse\ttrue\torigin\tonline\t%s/
test1\ttrue\tfalse\ttrue\torigin\tonline\t%s/
""" % (self.rurl2, self.rurl3, self.rurl1)
                self.__check_publisher_info(expected)

        def test_07_environment_variable(self):
                """Test that setting the environment variable PKG_SYSREPO_URL
                sets the url that pkg uses to communicate with the system
                repository."""

                self.__prep_configuration(["all-access"],
                    port=self.sysrepo_alt_port)
                self.__set_responses("all-access")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["all-access"],
                    self.sysrepo_alt_port, self.common_config_dir,
                    testcase=self)
                self.sc.start()
                old_psu = os.environ.get("PKG_SYSREPO_URL", None)
                os.environ["PKG_SYSREPO_URL"] = "localhost:%s" % \
                    self.sysrepo_alt_port
                api_obj = self.image_create(props={"use-system-repo": True})
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.durl1, self.durl2, self.durl3)
                self.__check_publisher_info(expected, set_debug_value=False)
                if old_psu:
                        os.environ["PKG_SYSREPO_URL"] = old_psu
                else:
                        del os.environ["PKG_SYSREPO_URL"]

        def test_08_file_repos(self):
                """Test that proxied file repos work correctly."""

                for i in self.dcs:
                        self.dcs[i].kill(now=True)
                self.__prep_configuration(["all-access-f", "none"])
                self.__set_responses("all-access-f")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["all-access-f"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                # Find the hashes that will be included in the urls of the
                # proxied file repos.
                hash1 = hashlib.sha1("file://" +
                    self.dcs[1].get_repodir().rstrip("/")).hexdigest()
                hash2 = hashlib.sha1("file://" +
                    self.dcs[2].get_repodir().rstrip("/")).hexdigest()
                hash3 = hashlib.sha1("file://" +
                    self.dcs[3].get_repodir().rstrip("/")).hexdigest()

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test1/%(hash1)s/
test12\tfalse\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test12/%(hash2)s/
test3\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test3/%(hash3)s/
""" % {"port": self.sysrepo_port, "hash1": hash1, "hash2": hash2,
    "hash3": hash3
}
                self.__check_publisher_info(expected)

                # Check connectivity with the proxied repos.
                self.pkg("install example_pkg")
                self.pkg("contents -rm foo")
                self.pkg("contents -rm bar")

                # Check that proxied file repos that disappear vanish correctly,
                # and that those with installed packages remain as disabled
                # publishers.
                self.__set_responses("none")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\tfalse\torigin\tonline\thttp://localhost:%(port)s/test1/%(hash1)s/
""" % {"port": self.sysrepo_port, "hash1": hash1}
                self.__check_publisher_info(expected)

                # Check that when the user adds an origin to a former system
                # publisher with an installed package, the publisher becomes
                # enabled and is not a system publisher.
                self.pkg("set-publisher -g %s test1" % self.rurl1)
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\tfalse\ttrue\torigin\tonline\t%(rurl1)s/
""" % {"rurl1":self.rurl1}
                self.__check_publisher_info(expected)

        def test_09_test_file_http_transitions(self):
                """Test that changing publishers from http to file repos and
                back in the sysrepo works as expected."""

                self.__prep_configuration(["all-access", "all-access-f",
                    "none"])
                self.__set_responses("all-access-f")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["all-access-f"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                # Find the hashes that will be included in the urls of the
                # proxied file repos.
                hash1 = hashlib.sha1("file://" +
                    self.dcs[1].get_repodir().rstrip("/")).hexdigest()
                hash2 = hashlib.sha1("file://" +
                    self.dcs[2].get_repodir().rstrip("/")).hexdigest()
                hash3 = hashlib.sha1("file://" +
                    self.dcs[3].get_repodir().rstrip("/")).hexdigest()

                self.__set_responses("all-access-f")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test1/%(hash1)s/
test12\tfalse\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test12/%(hash2)s/
test3\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test3/%(hash3)s/
""" % {"port": self.sysrepo_port, "hash1": hash1, "hash2": hash2,
    "hash3": hash3
}
                self.__check_publisher_info(expected)

                self.__set_responses("all-access")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%s/
""" % (self.durl1, self.durl2, self.durl3)
                self.__check_publisher_info(expected)

        def test_10_test_mirrors(self):
                """Test that mirror information from the sysrepo is handled
                correctly."""

                self.__prep_configuration(["all-access", "all-access-f",
                    "mirror-access", "mirror-access-f", "none"])
                self.__set_responses("mirror-access")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["mirror-access"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                # Find the hashes that will be included in the urls of the
                # proxied file repos.
                hash1 = hashlib.sha1("file://" +
                    self.dcs[1].get_repodir().rstrip("/")).hexdigest()
                hash2 = hashlib.sha1("file://" +
                    self.dcs[2].get_repodir().rstrip("/")).hexdigest()
                hash3 = hashlib.sha1("file://" +
                    self.dcs[3].get_repodir().rstrip("/")).hexdigest()

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%(durl1)s/
test1\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:%(port)s/test1/%(hash1)s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%(durl2)s/
test12\tfalse\ttrue\ttrue\tmirror\tonline\thttp://localhost:%(port)s/test12/%(hash2)s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%(durl3)s/
test3\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:%(port)s/test3/%(hash3)s/
""" % {"port": self.sysrepo_port, "hash1": hash1, "hash2": hash2,
    "hash3": hash3, "durl1": self.durl1, "durl2": self.durl2,
    "durl3": self.durl3
}
                self.__check_publisher_info(expected)

                self.__set_responses("mirror-access-f")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test1/%(hash1)s/
test1\ttrue\ttrue\ttrue\tmirror\tonline\tproxy://%(durl1)s/
test12\tfalse\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test12/%(hash2)s/
test12\tfalse\ttrue\ttrue\tmirror\tonline\tproxy://%(durl2)s/
test3\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test3/%(hash3)s/
test3\ttrue\ttrue\ttrue\tmirror\tonline\tproxy://%(durl3)s/
""" % {"port": self.sysrepo_port, "hash1": hash1, "hash2": hash2,
    "hash3": hash3, "durl1": self.durl1, "durl2": self.durl2,
    "durl3": self.durl3
}
                self.__check_publisher_info(expected)
                
                self.__set_responses("none")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
"""
                self.__check_publisher_info(expected)

                self.__set_responses("mirror-access-f")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test1/%(hash1)s/
test1\ttrue\ttrue\ttrue\tmirror\tonline\tproxy://%(durl1)s/
test12\tfalse\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test12/%(hash2)s/
test12\tfalse\ttrue\ttrue\tmirror\tonline\tproxy://%(durl2)s/
test3\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test3/%(hash3)s/
test3\ttrue\ttrue\ttrue\tmirror\tonline\tproxy://%(durl3)s/
""" % {"port": self.sysrepo_port, "hash1": hash1, "hash2": hash2,
    "hash3": hash3, "durl1": self.durl1, "durl2": self.durl2,
    "durl3": self.durl3
}
                self.__check_publisher_info(expected)

                self.__set_responses("all-access")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%(durl1)s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%(durl2)s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%(durl3)s/
""" % {"durl1": self.durl1, "durl2": self.durl2, "durl3": self.durl3}
                self.__check_publisher_info(expected)

                self.__set_responses("mirror-access")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%(durl1)s/
test1\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:%(port)s/test1/%(hash1)s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%(durl2)s/
test12\tfalse\ttrue\ttrue\tmirror\tonline\thttp://localhost:%(port)s/test12/%(hash2)s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%(durl3)s/
test3\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:%(port)s/test3/%(hash3)s/
""" % {"port": self.sysrepo_port, "hash1": hash1, "hash2": hash2,
    "hash3": hash3, "durl1": self.durl1, "durl2": self.durl2,
    "durl3": self.durl3
}
                self.__check_publisher_info(expected)

        def test_11_https_repos(self):
                """Test that https repos are proxied correctly."""

                self.__prep_configuration(["https-access", "none"])
                self.__set_responses("https-access")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["https-access"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%(ac1url)s/
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%(ac2url)s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%(ac3url)s/
""" % {
    "ac1url": self.acs[self.durl1].url.replace("https", "http"),
    "ac2url": self.acs[self.durl2].url.replace("https", "http"),
    "ac3url": self.acs[self.durl3].url.replace("https", "http")
}
                self.__check_publisher_info(expected)

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg", "foo", "bar"])
                api_obj = self.get_img_api_obj()
                self._api_uninstall(api_obj, ["example_pkg", "foo", "bar"])
                self.__set_responses("none")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
"""
                self.__check_publisher_info(expected)
                self.pkg("contents -rm example_pkg", exit=1)

        def test_12_disabled_repos(self):
                """Test that repos which are disabled in the global zone do not
                create problems."""

                self.__prep_configuration(["disabled"])
                self.__set_responses("disabled")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["disabled"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test12\tfalse\ttrue\ttrue\torigin\tonline\tproxy://%(durl2)s/
test3\ttrue\ttrue\ttrue\torigin\tonline\tproxy://%(durl3)s/
""" % {"durl2": self.durl2, "durl3": self.durl3}
                self.__check_publisher_info(expected)

        def test_13_old_file_repos(self):
                """Test that file repos created with pkgsend are not configured
                for the system repository."""

                self.__prep_configuration(["old-file"])
                self.__set_responses("old-file")
                self.sc = pkg5unittest.SysrepoController(
                    self.apache_confs["old-file"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                # Find the hashes that will be included in the urls of the
                # proxied file repos.
                hash1 = hashlib.sha1("file://" +
                    self.dcs[1].get_repodir().rstrip("/")).hexdigest()
                hash3 = hashlib.sha1("file://" +
                    self.dcs[3].get_repodir().rstrip("/")).hexdigest()

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI
test1\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test1/%(hash1)s/
test3\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:%(port)s/test3/%(hash3)s/
""" % {"port": self.sysrepo_port, "hash1": hash1, "hash3": hash3}



        __smf_cmds_template = { \
            "usr/bin/svcprop" : """\
#!/usr/bin/python

import getopt
import sys

if __name__ == "__main__":
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "cp:")
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %%s") %% e.opt)

        prop_dict = {
            "config/listen_host" : "localhost",
            "config/listen_port" : "%(proxy_port)s",
            "general/enabled" : "true",
        }

        found_c = False
        prop = None
        for opt, arg in opts:
                if opt == "-c":
                        found_c = True
                elif opt == "-p":
                        prop = arg
        if prop:
                prop = prop_dict.get(prop, None)
                if not found_c or not prop:
                        sys.exit(1)
                print prop
                sys.exit(0)
        for k, v in prop_dict.iteritems():
                print "%%s %%s" %% (k, v)
        sys.exit(0)
""",

            "usr/sbin/svcadm" : """\
#!/usr/bin/python

import getopt
import sys

if __name__ == "__main__":
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "cp:")
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %%s") %% e.opt)

        prop_dict = {
            "config/proxy_host" : "localhost",
            "config/proxy_port" : "%(proxy_port)s"
        }

        if len(pargs) != 2 or pargs[0] != "restart" or \
            pargs[1] != "svc:/application/pkg/system-repository":
                sys.exit(1)
        sys.exit(0)
"""}

        https_conf = """\
# Configuration and logfile names: If the filenames you specify for many
# of the server's control files begin with "/" (or "drive:/" for Win32), the
# server will use that explicit path.  If the filenames do *not* begin
# with "/", the value of ServerRoot is prepended -- so "/var/apache2/2.2/logs/foo_log"
# with ServerRoot set to "/usr/apache2/2.2" will be interpreted by the
# server as "/usr/apache2/2.2//var/apache2/2.2/logs/foo_log".

#
# ServerRoot: The top of the directory tree under which the server's
# configuration, error, and log files are kept.
#
# Do not add a slash at the end of the directory path.  If you point
# ServerRoot at a non-local disk, be sure to point the LockFile directive
# at a local disk.  If you wish to share the same ServerRoot for multiple
# httpd daemons, you will need to change at least LockFile and PidFile.
#
ServerRoot "/usr/apache2/2.2"

PidFile "%(pidfile)s"

#
# Listen: Allows you to bind Apache to specific IP addresses and/or
# ports, instead of the default. See also the <VirtualHost>
# directive.
#
# Change this to Listen on specific IP addresses as shown below to
# prevent Apache from glomming onto all bound IP addresses.
#
Listen 0.0.0.0:%(https_port)s

#
# Dynamic Shared Object (DSO) Support
#
# To be able to use the functionality of a module which was built as a DSO you
# have to place corresponding `LoadModule' lines within the appropriate
# (32-bit or 64-bit module) /etc/apache2/2.2/conf.d/modules-*.load file so that
# the directives contained in it are actually available _before_ they are used.
#
<IfDefine 64bit>
Include /etc/apache2/2.2/conf.d/modules-64.load
</IfDefine>
<IfDefine !64bit>
Include /etc/apache2/2.2/conf.d/modules-32.load
</IfDefine>

<IfModule !mpm_netware_module>
#
# If you wish httpd to run as a different user or group, you must run
# httpd as root initially and it will switch.
#
# User/Group: The name (or #number) of the user/group to run httpd as.
# It is usually good practice to create a dedicated user and group for
# running httpd, as with most system services.
#
User webservd
Group webservd

</IfModule>

# 'Main' server configuration
#
# The directives in this section set up the values used by the 'main'
# server, which responds to any requests that aren't handled by a
# <VirtualHost> definition.  These values also provide defaults for
# any <VirtualHost> containers you may define later in the file.
#
# All of these directives may appear inside <VirtualHost> containers,
# in which case these default settings will be overridden for the
# virtual host being defined.
#

#
# ServerName gives the name and port that the server uses to identify itself.
# This can often be determined automatically, but we recommend you specify
# it explicitly to prevent problems during startup.
#
# If your host doesn't have a registered DNS name, enter its IP address here.
#
ServerName 127.0.0.1

#
# DocumentRoot: The directory out of which you will serve your
# documents. By default, all requests are taken from this directory, but
# symbolic links and aliases may be used to point to other locations.
#
DocumentRoot "/"

#
# Each directory to which Apache has access can be configured with respect
# to which services and features are allowed and/or disabled in that
# directory (and its subdirectories).
#
# First, we configure the "default" to be a very restrictive set of
# features.
#
<Directory />
    Options None
    AllowOverride None
    Order deny,allow
    Deny from all
</Directory>

#
# Note that from this point forward you must specifically allow
# particular features to be enabled - so if something's not working as
# you might expect, make sure that you have specifically enabled it
# below.
#

#
# This should be changed to whatever you set DocumentRoot to.
#

#
# DirectoryIndex: sets the file that Apache will serve if a directory
# is requested.
#
<IfModule dir_module>
    DirectoryIndex index.html
</IfModule>

#
# The following lines prevent .htaccess and .htpasswd files from being
# viewed by Web clients.
#
<FilesMatch "^\.ht">
    Order allow,deny
    Deny from all
    Satisfy All
</FilesMatch>

#
# ErrorLog: The location of the error log file.
# If you do not specify an ErrorLog directive within a <VirtualHost>
# container, error messages relating to that virtual host will be
# logged here.  If you *do* define an error logfile for a <VirtualHost>
# container, that host's errors will be logged there and not here.
#
ErrorLog "%(log_locs)s/error_log"

#
# LogLevel: Control the number of messages logged to the error_log.
# Possible values include: debug, info, notice, warn, error, crit,
# alert, emerg.
#
LogLevel debug



<IfModule log_config_module>
    #
    # The following directives define some format nicknames for use with
    # a CustomLog directive (see below).
    #
    LogFormat "%(common_log_format)s" common

    #
    # The location and format of the access logfile (Common Logfile Format).
    # If you do not define any access logfiles within a <VirtualHost>
    # container, they will be logged here.  Contrariwise, if you *do*
    # define per-<VirtualHost> access logfiles, transactions will be
    # logged therein and *not* in this file.
    #
    CustomLog "%(log_locs)s/access_log" common
</IfModule>

#
# DefaultType: the default MIME type the server will use for a document
# if it cannot otherwise determine one, such as from filename extensions.
# If your server contains mostly text or HTML documents, "text/plain" is
# a good value.  If most of your content is binary, such as applications
# or images, you may want to use "application/octet-stream" instead to
# keep browsers from trying to display binary files as though they are
# text.
#
DefaultType text/plain

<IfModule mime_module>
    #
    # TypesConfig points to the file containing the list of mappings from
    # filename extension to MIME-type.
    #
    TypesConfig /etc/apache2/2.2/mime.types

    #
    # AddType allows you to add to or override the MIME configuration
    # file specified in TypesConfig for specific file types.
    #
    AddType application/x-compress .Z
    AddType application/x-gzip .gz .tgz

    # Add a new mime.type for .p5i file extension so that clicking on
    # this file type on a web page launches PackageManager in a Webinstall mode.
    AddType application/vnd.pkg5.info .p5i
</IfModule>

#
# Note: The following must must be present to support
#       starting without SSL on platforms with no /dev/random equivalent
#       but a statically compiled-in mod_ssl.
#
<IfModule ssl_module>
SSLRandomSeed startup builtin
SSLRandomSeed connect builtin
</IfModule>

<VirtualHost 0.0.0.0:%(https_port)s>
        AllowEncodedSlashes On
        ProxyRequests Off
        MaxKeepAliveRequests 10000

        SSLEngine On

        # Cert paths
        SSLCertificateFile %(server-ssl-cert)s
        SSLCertificateKeyFile %(server-ssl-key)s

        # Combined product CA certs for client verification
        SSLCACertificateFile %(server-ca-cert)s

	SSLVerifyClient require

        <Location />
                SSLVerifyDepth 1

	        # The client's certificate must pass verification, and must have
	        # a CN which matches this repository.
                SSLRequire ( %(ssl-special)s =~ m/%(server-ca-taname)s/ )

                # set max to number of threads in depot
                ProxyPass %(proxied-server)s/ nocanon max=500
        </Location>
</VirtualHost>


"""
