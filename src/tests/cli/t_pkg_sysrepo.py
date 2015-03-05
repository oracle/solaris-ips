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
# Copyright (c) 2011, 2015, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function
import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import copy
import os
import shutil

import pkg.client.api_errors as apx
import pkg.client.transport.exception as tx
import pkg.digest as digest
import pkg.misc as misc

try:
        import pkg.sha512_t
        sha512_supported = True
except ImportError:
        sha512_supported = False

class PC(object):
        """This class contains publisher configuration used for setting up the
        depots and https apache instances needed by the tests."""

        def __init__(self, url, sticky=True, mirrors=misc.EmptyI, https=False,
            server_ta=None, client_ta=None, disabled=False, name=None,
            sig_pol=None, req_names=None, origins=misc.EmptyI):
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
                self.signature_policy = sig_pol
                self.required_names = req_names
                self.origins = origins

class TestSysrepo(pkg5unittest.ApacheDepotTestCase):
        """Tests pkg interaction with the system repository."""

        # Tests in this suite use the read only data directory.
        need_ro_data = True

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add file tmp/example_file mode=0555 owner=root group=bin path=/usr/bin/example_path
            close"""

        foo10 = """
            open foo@1.0,5.11-0
            close"""

        foo11 = """
            open foo@1.1,5.11-0
            add file tmp/example_file mode=0555 owner=root group=bin path=/usr/bin/example_path2
            close"""

        bar10 = """
            open bar@1.0,5.11-0
            add file tmp/example_two mode=0555 owner=root group=bin path=/usr/bin/example_path3
            close"""

        bar11 = """
            open bar@1.1,5.11-0
            add file tmp/example_two mode=0555 owner=root group=bin path=/usr/bin/example_path3
            add file tmp/example_two mode=0555 owner=root group=bin path=/usr/bin/example_path4
            close"""

        baz10 = """
            open baz@1.0,5.11-0
            add file tmp/example_three mode=0555 owner=root group=bin path=/usr/bin/another_1
            close"""

        caz10 = """
            open caz@1.0,5.11-0
            add file tmp/example_four mode=0555 owner=root group=bin path=/usr/bin/another_2
            close"""

        misc_files = ["tmp/example_file", "tmp/example_two",
            "tmp/example_three", "tmp/example_four"]

        expected_all_access =  """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test12\tfalse\ttrue\ttrue\torigin\tonline\t{durl2}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\torigin\tonline\t{durl3}/\thttp://localhost:{port}
test4\ttrue\ttrue\ttrue\t\t\t\t
"""

        def setUp(self):
                # These need to be set before calling setUp in case setUp fails.
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
                        self.smf_cmds[n] = self.__smf_cmds_template[n].format(**
                            smf_conf_dict)

                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test12",
                    "test3", "test4", "test12"], start_depots=True)
                self.testdata_dir = os.path.join(self.test_root, "testdata")
                self.make_misc_files(self.misc_files)

                self.durl1 = self.dcs[1].get_depot_url()
                self.durl2 = self.dcs[2].get_depot_url()
                self.durl3 = self.dcs[3].get_depot_url()

                # we make self.durl3 multi-hash aware, to ensure that the
                # system-repository can serve packages published with multiple
                # hashes.
                self.dcs[3].stop()
                self.dcs[3].set_debug_feature("hash=sha1+sha256")
                self.dcs[3].start()

                self.durl4 = self.dcs[4].get_depot_url()
                self.durl5 = self.dcs[5].get_depot_url()

                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                self.rurl3 = self.dcs[3].get_repo_url()
                self.rurl4 = self.dcs[4].get_repo_url()
                self.rurl5 = self.dcs[5].get_repo_url()

                self.apache_dir = os.path.join(self.test_root, "apache")
                self.apache_log_dir = os.path.join(self.apache_dir,
                    "apache_logs")

                self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                self.pkgsend_bulk(self.rurl2, self.foo10)
                # We send to rurl3 using multi-hash aware publication
                self.pkgsend_bulk(self.rurl3, self.bar10,
                    debug_hash="sha1+sha256")
                self.pkgsend_bulk(self.rurl3, self.baz10,
                    debug_hash="sha1+sha256")
                if sha512_supported:
                        self.pkgsend_bulk(self.rurl3, self.caz10,
                            debug_hash="sha1+sha512_256")
                self.pkgsend_bulk(self.rurl4, self.bar10)
                self.pkgsend_bulk(self.rurl5, self.foo11)

                self.common_config_dir = os.path.join(self.test_root,
                    "apache-serve")
                self.htdocs_dir = os.path.join(self.common_config_dir, "htdocs")
                self.apache_confs = {}

                # Establish the different publisher configurations that tests
                # will need.  self.configs is a dictionary that maps config
                # names to tuples of (image properties, PC objects).  The image
                # properties are stored in a dictionary that maps the name of
                # the property to the value.  The list of PC objects represent
                # the configuration of each publisher.
                #
                # The self.configs dictionary is used to create images whose
                # configuration is used by pkg.sysrepo to create the
                # configuration files needed to set up a system-repository
                # instance for that image.
                self.configs = {
                    "all-access": ({}, [
                        PC(self.durl1),
                        PC(self.durl2, sticky=False),
                        PC(self.durl3),
                        PC(None, name="test4")]),
                    "all-access-f": ({}, [
                        PC(self.rurl1),
                        PC(self.rurl2, sticky=False),
                        PC(self.rurl3)]),
                    "disabled": ({}, [
                        PC(self.durl1, disabled=True, name="test1"),
                        PC(self.durl2, sticky=False),
                        PC(self.durl3)]),
                    "https-access": ({}, [
                        PC(self.durl1, https=True, server_ta="ta11",
                            client_ta="ta6"),
                        PC(self.durl2, sticky=False, https=True,
                            server_ta="ta7", client_ta="ta8"),
                        PC(self.durl3, https=True, server_ta="ta9",
                            client_ta="ta10")]),
                    "mirror-access": ({}, [
                        PC(self.durl1, mirrors=[("test1", self.rurl1)]),
                        PC(self.durl2, sticky=False,
                            mirrors=[("test12", self.rurl2)]),
                        PC(self.durl3, mirrors=[("test3", self.rurl3)])]),
                    "mirror-access-f": ({}, [
                        PC(self.rurl1, mirrors=[("test1", self.durl1)]),
                        PC(self.rurl2, sticky=False,
                            mirrors=[("test12", self.durl2)]),
                        PC(self.rurl3, mirrors=[("test3", self.durl3)])]),
                    "mirror-access-user": ({}, [
                        PC(self.durl1, mirrors=[("test1", self.rurl1)]),
                        PC(self.durl2, sticky=False),
                        PC(self.durl3, mirrors=[("test3", self.rurl3)])]),
                    "none": ({}, []),
                    "test1": ({}, [PC(self.durl1)]),
                    "test1-test12": ({}, [
                        PC(self.durl1),
                        PC(self.durl2, sticky=False)]),
                    "test1-test12-test12": ({}, [
                        PC(self.durl1),
                        PC(None,
                            name="test12", origins=[self.durl2, self.durl5],
                            sticky=False)]),
                    "test1-test3": ({}, [
                        PC(self.durl1),
                        PC(self.durl3)]),
                    "test1-test3-f": ({}, [
                        PC(self.rurl1),
                        PC(self.rurl3)]),
                    "test12": ({}, [
                        PC(self.durl2, sticky=False)]),
                    "test12-test12": ({}, [
                        PC(None,
                            name="test12", origins=[self.durl2, self.durl5],
                            sticky=False)]),
                    "test12-test3": ({}, [
                        PC(self.durl2, sticky=False),
                        PC(self.durl3)]),
                    "test3": ({}, [PC(self.durl3)]),
                    "nourl": ({}, [PC(None, name="test4")]),
                    "img-sig-ignore": ({"signature-policy": "ignore"}, [
                        PC(self.rurl1),
                        PC(self.rurl2, sticky=False),
                        PC(self.rurl3)]),
                    "img-sig-require": (
                        {"signature-policy": "require-signatures"}, [
                        PC(self.rurl1),
                        PC(self.rurl2, sticky=False),
                        PC(self.rurl3)]),
                    "img-sig-req-names": ({
                            "signature-policy": "require-names",
                            "signature-required-names": ["cs1_ch1_ta3"]
                        }, [
                        PC(self.rurl1),
                        PC(self.rurl2, sticky=False),
                        PC(self.rurl3)]),
                    "pub-sig-ignore": ({}, [
                        PC(self.rurl1, sig_pol="ignore"),
                        PC(self.rurl2, sticky=False,
                            sig_pol="ignore"),
                        PC(self.rurl3, sig_pol="ignore")]),
                    "pub-sig-require": ({}, [
                        PC(self.rurl1, sig_pol="require-signatures"),
                        PC(self.rurl2, sticky=False,
                            sig_pol="require-signatures"),
                        PC(self.rurl3, sig_pol="require-signatures")]),
                    "pub-sig-reqnames": ({}, [
                        PC(self.rurl1, sig_pol="require-names",
                            req_names="cs1_ch1_ta3"),
                        PC(self.rurl2, sticky=False,
                            sig_pol="require-names", req_names=["cs1_ch1_ta3"]),
                        PC(self.rurl3, sig_pol="require-names",
                            req_names="cs1_ch1_ta3")]),
                    "pub-sig-mixed": ({}, [
                        PC(self.rurl1, sig_pol="require-signatures"),
                        PC(self.rurl2, sticky=False),
                        PC(self.rurl3, sig_pol="verify")]),
                    "img-pub-sig-mixed": ({"signature-policy": "ignore"}, [
                        PC(self.rurl1, sig_pol="require-signatures"),
                        PC(self.rurl2, sticky=False, sig_pol="require-names",
                            req_names=["cs1_ch1_ta3", "foo", "bar", "baz"]),
                        PC(self.rurl3, sig_pol="ignore")]),
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
                        "{0}_cert.pem".format(pc.client_ta)),
                    "server-ca-taname": pc.client_ta,
                    "serve_root": content_dir,
                    "server-ssl-cert":os.path.join(self.cs_dir,
                        "cs1_{0}_cert.pem".format(pc.server_ta)),
                    "server-ssl-key":os.path.join(self.keys_dir,
                        "cs1_{0}_key.pem".format(pc.server_ta)),
               })
                conf_path = os.path.join(instance_dir, "https.conf")
                with open(conf_path, "wb") as fh:
                        fh.write(self.https_conf.format(**cd))

                ac = pkg5unittest.ApacheController(conf_path, https_port,
                    instance_dir, testcase=self, https=True)
                self.register_apache_controller(pc.url, ac)
                ac.start()
                return ac

        def __prep_configuration(self, names, port=None,
            use_config_cache=False):
                """Prepare the system repository configuration given either
                a string corresponding to a key in self.configs, or a list
                of keys.

                'port' if used overrides the default port to be used.

                'use_config_cache' causes us to call pkg.sysrepo twice for each
                configuration, ensuring that we use the pkg.sysrepo config
                cached in var/cache/pkg for the actual configuration.
                """

                if not port:
                        port = self.sysrepo_port
                self.__configured_names = []
                if isinstance(names, basestring):
                        names = [names]
                for name in names:
                        props, pcs = self.configs[name]
                        self.image_create(props=props)
                        for pc in pcs:
                                cmd = "set-publisher"
                                if not pc.sticky:
                                        cmd += " --non-sticky"
                                if not pc.https and pc.url:
                                        cmd += " -p {0}".format(pc.url)
                                elif not pc.https and not pc.url:
                                        for o in pc.origins:
                                                cmd += " -g {0}".format(o)
                                        cmd += " {0}".format(pc.name)
                                else:
                                        if pc.url in self.acs:
                                                ac = self.acs[pc.url]
                                        else:
                                                ac = self.__start_https(pc)
                                        # Configure image to use apache instance
                                        cmd = " --debug " \
                                            "ssl_ca_file={ca_file} {cmd} " \
                                            "-k {key} -c {cert} " \
                                            "-p {url}".format(
                                                ca_file=os.path.join(
                                                    self.raw_trust_anchor_dir,
                                                    "{0}_cert.pem".format(
                                                    pc.server_ta)),
                                                cert=os.path.join(
                                                    self.cs_dir,
                                                    "cs1_{0}_cert.pem".format(
                                                    pc.client_ta)),
                                                cmd=cmd,
                                                key=os.path.join(
                                                    self.keys_dir,
                                                    "cs1_{0}_key.pem".format(
                                                    pc.client_ta)),
                                                url=ac.url,
                                            )
                                if pc.signature_policy:
                                        cmd += " --set-property " \
                                            "signature-policy={0}".format(
                                            pc.signature_policy)
                                if pc.required_names:
                                        cmd += " --set-property " \
                                            "signature-required-names='{0}'".format(
                                            pc.required_names)
                                self.pkg(cmd, debug_smf=False)
                                for pub, m in pc.mirrors:
                                        self.pkg(
                                            "set-publisher -m {0} {1}".format(m, pub))
                                if pc.disabled:
                                        self.pkg("set-publisher -d {0}".format(
                                            pc.name))

                        if use_config_cache:
                                # Call self.sysrepo so that a config cache is
                                # created.  The subsequent call to self.sysrepo
                                # will use that cache to build the Apache
                                # configuration.
                                self.sysrepo("-l {log_locs} -p {port} "
                                    "-r {common_serve}".format(
                                        log_locs=self.apache_log_dir,
                                        port=port,
                                        common_serve=self.common_config_dir)
                                   )

                        self.sysrepo("-l {log_locs} -p {port} "
                            "-r {common_serve}".format(
                                log_locs=self.apache_log_dir,
                                port=port,
                                common_serve=self.common_config_dir)
                           )
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
                        self.pkg("property")
                        self.image_destroy()

        def __set_responses(self, name, update_conf=True):
                """Sets the system-repository to use a named configuration
                when providing responses."""

                if name not in self.__configured_names:
                        raise RuntimeError("{0} hasn't been prepared for this "
                            "test.".format(name))
                base_dir = os.path.join(self.test_root, "apache-conf", name,
                    "htdocs")
                if not os.path.isdir(base_dir):
                        raise RuntimeError("Expected {0} to already exist and "
                            "be a directory but it's not.".format(base_dir))
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
                if update_conf and "sysrepo" in self.acs:
                        # changing configuration without registering a new
                        # ApacheController is safe even if the new configuration
                        # specifies a different port, because the controller
                        # gets stopped/started by the __set_conf(..)
                        # method of ApacheController if the process is running.
                        self.acs["sysrepo"].conf = self.apache_confs[name]

        def __check_publisher_info(self, expected, set_debug_value=True,
            su_wrap=False, env_arg=None):
                self.pkg("publisher -F tsv", debug_smf=set_debug_value,
                    su_wrap=su_wrap, env_arg=env_arg)
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
                                raise RuntimeError("Publisher {0} was expected "
                                    "to exist but its directory is missing "
                                    "from the image directory.".format(p))
                for d in os.listdir(pub_dir):
                        if d not in pubs:
                                raise RuntimeError("{0} was not expected in the "
                                    "publisher directory but was found.".format(d))

        def test_01_basics(self):
                """Test that an image with no publishers can be created and that
                it can pick up its publisher configuration from the system
                repository."""
                self.base_01_basics()

        def test_01a_basics(self):
                """Tests that an image with no publishers can be created and
                that it can pick up its publisher configuration from the system
                repository when we're using a cached pkg.sysrepo config."""
                self.base_01_basics(use_config_cache=True)

        def base_01_basics(self, use_config_cache=False):
                """Implementation of test_01_basics, parameterizing
                use_config_cache"""

                self.__prep_configuration("all-access",
                    use_config_cache=use_config_cache)
                self.__set_responses("all-access")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["all-access"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})
                # Make sure that the publisher catalogs were created.
                for n in ("test1", "test12", "test3"):
                        self.assert_(os.path.isdir(os.path.join(self.img_path(),
                            "var/pkg/publisher/{0}".format(n))))
                expected = self.expected_all_access.format(
                    durl1=self.durl1, durl2=self.durl2,
                    durl3=self.durl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                # make sure none of our sysrepo-provided configuration has
                # leaked into the image configuration
                self.pkg("set-property use-system-repo False")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
"""
                self.__check_publisher_info(expected)
                self.pkg("set-property use-system-repo True")

                self.pkg("publisher test1")

                # check we have the correct number of lines, each containing
                # <system-repository>
                self.pkg("publisher -H")
                count = 0
                for line in self.output.split("\n"):
                        count += 1
                        # publisher 4 does not have any origins set
                        if not line.startswith("test4") and line:
                                self.assert_("<system-repository>" in line,
                                    "line {0} does not contain "
                                    "'<system-repository>'".format(line))
                self.assert_(count == 5,
                    "expected 5 lines of output in \n{0}\n, got {1}".format(
                    self.output, count))

                self.pkg("publisher")
                self.pkg("publisher test1")
                self.pkg("publisher test12")
                self.assert_("Proxy: http://localhost:{0}".format(self.sysrepo_port)
                    in self.output)
                self.assert_("<system-repository>" not in self.output)
                self.debug("looking for {0}".format(self.durl1))

                # Test that the publishers have the right uris and appear in
                # the correct order.
                self.pkg("publisher -F tsv")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{one}/\thttp://localhost:{port}
test12\tfalse\ttrue\ttrue\torigin\tonline\t{two}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\torigin\tonline\t{three}/\thttp://localhost:{port}
test4\ttrue\ttrue\ttrue\t\t\t\t
""".format(port=self.sysrepo_port, one=self.durl1, two=self.durl2,
    three=self.durl3)
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output, bound_white_space=True)

                # Test that a new pkg process will pick up the right catalog.
                self.pkg("list -a")
                self.pkg("install example_pkg")

                # Test that the current api object has the right catalog.
                self._api_install(api_obj, ["foo", "bar"])

                # Test that we can install a multi-hash package
                self.pkg("install baz")
                self.pkg("contents -m baz")
                self.assert_("pkg.hash.sha256" in self.output)
                if sha512_supported:
                        self.pkg("install caz")
                        self.pkg("contents -m caz")
                        self.assert_("pkg.hash.sha512_256" in self.output)

        def test_02_communication(self):
                """Test that the transport for communicating with the depots is
                actually going through the proxy. This is done by
                "misconfiguring" the system repository so that it refuses to
                proxy to certain depots then operations which would communicate
                with those depots fail.

                We also verify that $http_proxy and $no_proxy environment
                variables are not used for interactions with the system
                repository.
                """

                self.__prep_configuration(["all-access", "none", "test12-test3",
                    "test3"])
                self.__set_responses("all-access")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["none"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)

                sc.start()
                self.assertRaises(apx.CatalogRefreshException,
                    self.image_create, props={"use-system-repo": True})
                sc.conf = self.apache_confs["all-access"]
                api_obj = self.image_create(props={"use-system-repo": True})
                sc.conf = self.apache_confs["none"]

                expected =  self.expected_all_access.format(
                    durl1=self.durl1, durl2=self.durl2,
                    durl3=self.durl3, port=self.sysrepo_port)
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

                sc.conf = self.apache_confs["test3"]
                self.pkg("list -a")
                self.pkg("contents -rm example_pkg", exit=1)
                self.pkg("contents -rm foo", exit=1)
                self.pkg("contents -rm bar")
                self.assertRaises(tx.TransportFailures, self._api_install,
                    api_obj, ["example_pkg"], refresh_catalogs=False)
                self.assertRaises(tx.TransportFailures, self._api_install,
                    api_obj, ["foo"], refresh_catalogs=False)
                self._api_install(api_obj, ["bar"], refresh_catalogs=False)


                sc.conf = self.apache_confs["test12-test3"]
                self.pkg("list -a")
                self.pkg("contents -rm example_pkg", exit=1)
                self.pkg("contents -rm foo")
                self.assertRaises(tx.TransportFailures, self._api_install,
                    api_obj, ["example_pkg"], refresh_catalogs=False)
                self._api_install(api_obj, ["foo"], refresh_catalogs=False)

                sc.conf = self.apache_confs["all-access"]
                self.pkg("list -a")
                self.pkg("contents -rm example_pkg")
                self._api_install(api_obj, ["example_pkg"])

                # check that $http_proxy environment variables are ignored
                # by setting http_proxy and no_proxy values that would otherwise
                # cause us to bypass the system-repository.

                env = {"http_proxy": "http://noodles"}
                # create an image the long way, allowing us to pass an environ
                self.image_destroy()
                os.mkdir(self.img_path())
                self.pkg("image-create {0}".format(self.img_path()))
                self.pkg("set-property use-system-repo True", env_arg=env)

                self.pkg("refresh --full", env_arg=env)
                self.pkg("contents -rm example_pkg", env_arg=env)
                expected =  self.expected_all_access.format(
                    durl1=self.durl1, durl2=self.durl2,
                    durl3=self.durl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected, env_arg=env)
                self.pkg("install example_pkg", env_arg=env)

                env = {"no_proxy": "localhost"}
                # create an image the long way, allowing us to pass an environ
                self.image_destroy()
                os.mkdir(self.img_path())
                self.pkg("image-create {0}".format(self.img_path()))
                self.pkg("set-property use-system-repo True", env_arg=env)

                self.pkg("refresh --full", env_arg=env)
                self.pkg("contents -rm example_pkg", env_arg=env)
                self.__check_publisher_info(expected, env_arg=env)
                self.pkg("install example_pkg", env_arg=env)

        def test_03_user_modifying_configuration(self):
                """Test that adding and removing origins to a system publisher
                works as expected and that modifying other configuration of a
                system publisher fails."""

                self.__prep_configuration(["test1", "none",
                    "mirror-access-user"])
                self.__set_responses("test1")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["test1"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
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

                # Add a mirror to an existing system publisher
                self.pkg("set-publisher -m {0} test1".format(self.rurl1))

                # Add an origin to an existing system publisher.
                self.pkg("set-publisher -g {0} test1".format(self.rurl1))

                # Check that the publisher information is shown correctly.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test1\ttrue\ttrue\ttrue\tmirror\tonline\t{rurl1}/\t-
""".format(rurl1=self.rurl1, durl1=self.durl1, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                # Check that the publisher specific information has information
                # for both origins, and that we only have one occurrence of
                # "Proxy:"
                self.pkg("publisher test1")
                self.assert_(self.rurl1 in self.output)
                self.assert_(self.durl1 in self.output)
                self.assert_("http://localhost:{0}\n".format(self.sysrepo_port)
                    in self.output)
                self.assert_(self.output.count("Proxy:") == 1)

                # Change the proxy configuration so that the image can't use it
                # to communicate with the depot. This forces communication to
                # go through the user configured origin.
                sc.conf = self.apache_confs["none"]

                # Check that the catalog can't be refreshed and that the
                # communcation with the repository fails.
                self.pkg("contents -rm example_pkg")
                self.pkg("refresh --full", exit=1)

                # Check that removing the system configured origin fails.
                self.pkg("set-publisher -G {0} test1".format(self.durl1), exit=1)
                self.pkg("set-publisher -G {0} test1".format(self.durl1),
                    exit=1)
                # Check that removing the user configured origin succeeds.
                # --no-refresh is needed because otherwise we attempt to contact
                # the publisher to update the catalogs.
                self.pkg("set-publisher -G {0} --no-refresh test1".format(self.rurl1))

                # Check that the user configured origin is gone.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test1\ttrue\ttrue\ttrue\tmirror\tonline\t{rurl1}/\t-
""".format(durl1=self.durl1, rurl1=self.rurl1, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                # Ensure that previous communication was going through the file
                # repo by confirming that communication to the depot is still
                # refused.
                self.pkg("refresh --full", exit=1)

                # Reenable access to the depot to make sure nothing has been
                # broken in the image.
                sc.conf = self.apache_confs["test1"]
                self.pkg("refresh --full")

                # Find the hashes that will be included in the urls of the
                # proxied file repos.
                hash1 = digest.DEFAULT_HASH_FUNC("file://" +
                    self.dcs[1].get_repodir().rstrip("/")).hexdigest()
                hash3 = digest.DEFAULT_HASH_FUNC("file://" +
                    self.dcs[3].get_repodir().rstrip("/")).hexdigest()

                # Check that a user can add and remove mirrors,
                # but can't remove repo-provided mirrors
                sc.conf = self.apache_confs["mirror-access-user"]
                self.__set_responses("mirror-access-user")
                self.pkg("set-publisher -m {0} test12".format(self.rurl2))
                expected_mirrors = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test1\ttrue\ttrue\ttrue\tmirror\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:{port}/test1/{hash1}/\t-
test12\tfalse\ttrue\ttrue\torigin\tonline\t{durl2}/\thttp://localhost:{port}
test12\tfalse\ttrue\ttrue\tmirror\tonline\t{rurl2}/\t-
test3\ttrue\ttrue\ttrue\torigin\tonline\t{durl3}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:{port}/test3/{hash3}/\t-
""".format(port=self.sysrepo_port, hash1=hash1, rurl1=self.rurl1,
    rurl2=self.rurl2, hash3=hash3, durl1=self.durl1,
    durl2=self.durl2, durl3=self.durl3)
                self.__check_publisher_info(expected_mirrors)

                # turn off the sysrepo property, and ensure the mirror is there
                self.pkg("set-property use-system-repo False")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\tfalse\ttrue\tmirror\tonline\t{rurl1}/\t-
test12\tfalse\tfalse\ttrue\tmirror\tonline\t{rurl2}/\t-
""".format(rurl1=self.rurl1, rurl2=self.rurl2)
                self.__check_publisher_info(expected)
                self.pkg("set-property use-system-repo True")

                # ensure we can't remove the sysrepo-provided mirror
                self.pkg("set-publisher -M {0} test12".format(self.rurl1), exit=1)
                self.__check_publisher_info(expected_mirrors)

                # ensure we can remove the user-provided mirror
                self.pkg("set-publisher -M {0} test12".format(self.rurl2))
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test1\ttrue\ttrue\ttrue\tmirror\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:{port}/test1/{hash1}/\t-
test12\tfalse\ttrue\ttrue\torigin\tonline\t{durl2}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\torigin\tonline\t{durl3}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:{port}/test3/{hash3}/\t-
""".format(port=self.sysrepo_port, hash1=hash1, rurl1=self.rurl1,
    hash3=hash3, durl1=self.durl1, durl2=self.durl2,
    durl3=self.durl3)

                self.__check_publisher_info(expected)

        def test_04_changing_syspub_configuration(self):
                """Test that changes to the syspub/0 response are handled
                correctly by the client."""

                # Check that a syspub/0 response with no configured publisers
                # works.
                self.__prep_configuration(["none", "test1-test12",
                    "test1-test3", "test12"])
                self.__set_responses("none")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["none"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
"""
                self.__check_publisher_info(expected)

                # The user configures test1 as a publisher.
                self.pkg("set-publisher --non-sticky -p {0}".format(self.durl1))
                self.__check_publisher_dirs(["test1"])
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\tfalse\tfalse\ttrue\torigin\tonline\t{0}/\t-
""".format(self.durl1)
                self.__check_publisher_info(expected)

                self.pkg("set-publisher -d test1")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\tfalse\tfalse\tfalse\torigin\tonline\t{0}/\t-
""".format(self.durl1)
                self.__check_publisher_info(expected)
                self.__check_publisher_dirs([])

                # Now the syspub/0 response configures two publishers. The
                # test12 publisher is totally new while the test1 publisher
                # overlaps with the publisher the user configured.
                self.__set_responses("test1-test12")

                # Check that the syspub/0 sticky setting has masked the user
                # configuration and that the other publisher information is as
                # expected.  Note that the user-configured origin should be
                # hidden since we can only have a single path to an origin,
                # so we use the system repository version.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test12\tfalse\ttrue\ttrue\torigin\tonline\t{durl2}/\thttp://localhost:{port}
""".format(durl1=self.durl1, durl2=self.durl2, port=self.sysrepo_port)
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
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\torigin\tonline\t{durl3}/\thttp://localhost:{port}
""".format(durl1=self.durl1, durl3=self.durl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected)
                # Only test1 is expected to exist because only it was present in
                # both the old configuration and the current configuration.
                self.__check_publisher_dirs(["test1"])

                if sha512_supported:
                        expected = """\
bar (test3) 1.0-0 ---
baz (test3) 1.0-0 ---
caz (test3) 1.0-0 ---
example_pkg 1.0-0 ---
"""
                else:
                        expected = """\
bar (test3) 1.0-0 ---
baz (test3) 1.0-0 ---
example_pkg 1.0-0 ---
"""
                self.__check_package_lists(expected)

                self.pkg("contents -rm example_pkg")
                self.pkg("contents -rm foo", exit=1)
                self.pkg("contents -m foo", exit=1)
                self.pkg("contents -rm bar")
                self.pkg("refresh --full")

                # The user tries to add an origin to the system publisher test3
                # using the same url as the system-repository provides, which
                # should fail, because There Can Be Only One origin for a given
                # uri.
                self.pkg("set-publisher -g {0} test3".format(self.durl3), exit=1)

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\torigin\tonline\t{durl3}/\thttp://localhost:{port}
""".format(durl1=self.durl1, durl3=self.durl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected)
                self.__check_publisher_dirs(["test1", "test3"])

                if sha512_supported:
                        expected = """\
bar (test3) 1.0-0 ---
baz (test3) 1.0-0 ---
caz (test3) 1.0-0 ---
example_pkg 1.0-0 ---
"""
                else:
                        expected = """\
bar (test3) 1.0-0 ---
baz (test3) 1.0-0 ---
example_pkg 1.0-0 ---
"""
                self.__check_package_lists(expected)
                self.pkg("refresh --full")

                # Now syspub/0 removes test1 and test3 as publishers and returns
                # test12 as a publisher.
                self.__set_responses("test12")

                # test1 should be reinstated as a publisher because the
                # user added an origin for it before using the system
                # repository. test1 should also return to
                # the settings the user had previously configured. test12 should
                # be listed first since, because it's a system publisher, it's
                # higher ranked.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test12\tfalse\ttrue\ttrue\torigin\tonline\t{durl2}/\thttp://localhost:{port}
test1\tfalse\tfalse\tfalse\torigin\tonline\t{durl1}/\t-
""".format(durl2=self.durl2, durl1=self.durl1, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                self.pkg("refresh --full")

                expected = """\
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
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\tfalse\tfalse\tfalse\torigin\tonline\t{durl1}/\t-
test12\tfalse\ttrue\tfalse\t\t\t\t
""".format(durl1=self.durl1)
                self.__check_publisher_info(expected)

                # Uninstalling foo should remove test12 from the list of
                # publishers.
                self.pkg("uninstall foo")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\tfalse\tfalse\tfalse\torigin\tonline\t{durl1}/\t-
""".format(durl1=self.durl1, durl3=self.durl3)
                self.__check_publisher_info(expected)

        def test_05_simultaneous_change(self):
                """Test that simultaneous changes in both user configuration and
                system publisher state are handled correctly."""

                self.__prep_configuration(["none", "test1", "test12"])
                # Create an image with no user configured publishers and no
                # system configured publishers.
                self.__set_responses("none")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["none"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
"""
                self.__check_publisher_info(expected)

                # Have the user configure test1 at the same time that test1 is
                # made a system publisher.
                self.__set_responses("test1")

                self.pkg("set-publisher -p {0}".format(self.rurl1))
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
""".format(rurl1=self.rurl1, durl1=self.durl1, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                # Adding the origin to the publisher which now exists should
                # fail.
                self.pkg("set-publisher -g {0} test1".format(self.rurl1), exit=1)

                # The user adds an origin to test12 at the same time that test12
                # first becomes known to the image.
                self.__set_responses("test12")
                self.pkg("set-publisher -g {0} test12".format(self.rurl2))
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test12\tfalse\ttrue\ttrue\torigin\tonline\t{rurl2}/\t-
test12\tfalse\ttrue\ttrue\torigin\tonline\t{durl2}/\thttp://localhost:{port}
test1\ttrue\tfalse\ttrue\torigin\tonline\t{rurl1}/\t-
""".format(rurl2=self.rurl2, durl2=self.durl2, rurl1=self.rurl1,
    port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                self.pkg("publisher")
                self.debug(self.output)
                # The user removes the origin for test12 at the same time that
                # test12 stops being a system publisher and test1 is added as a
                # system publisher.
                self.__set_responses("test1")
                self.pkg("set-publisher -G {0} test12".format(self.rurl2))
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test12\tfalse\tfalse\ttrue\t\t\t\t
""".format(rurl1=self.rurl1, durl1=self.durl1, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                # The user now removes the originless publisher
                self.pkg("unset-publisher test12")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
""".format(rurl1=self.rurl1, durl1=self.durl1, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                # The user now unsets test1 at the same time that test1 stops
                # being a system publisher.
                self.__set_responses("none")
                self.pkg("unset-publisher test1")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
"""
                self.__check_publisher_info(expected)

        def test_06_ordering(self):
                """Test that publishers have the right search order given both
                user configuration and whether a publisher is a system
                publisher."""

                self.__prep_configuration(["all-access", "none", "test1"])
                self.__set_responses("none")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["none"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                self.pkg("set-publisher -p {0}".format(self.rurl3))
                self.pkg("set-publisher -p {0}".format(self.rurl2))
                self.pkg("set-publisher -p {0}".format(self.rurl1))

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test3\ttrue\tfalse\ttrue\torigin\tonline\t{0}/\t-
test12\ttrue\tfalse\ttrue\torigin\tonline\t{1}/\t-
test1\ttrue\tfalse\ttrue\torigin\tonline\t{2}/\t-
""".format(self.rurl3, self.rurl2, self.rurl1)
                self.__check_publisher_info(expected)

                self.__set_responses("all-access")

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test12\tfalse\ttrue\ttrue\torigin\tonline\t{rurl2}/\t-
test12\tfalse\ttrue\ttrue\torigin\tonline\t{durl2}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\torigin\tonline\t{rurl3}/\t-
test3\ttrue\ttrue\ttrue\torigin\tonline\t{durl3}/\thttp://localhost:{port}
test4\ttrue\ttrue\ttrue\t\t\t\t
""".format(rurl1=self.rurl1, durl1=self.durl1, rurl2=self.rurl2,
    durl2=self.durl2, rurl3=self.rurl3, durl3=self.durl3,
    port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                self.pkg("set-property use-system-repo False")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test3\ttrue\tfalse\ttrue\torigin\tonline\t{0}/\t-
test12\ttrue\tfalse\ttrue\torigin\tonline\t{1}/\t-
test1\ttrue\tfalse\ttrue\torigin\tonline\t{2}/\t-
""".format(self.rurl3, self.rurl2, self.rurl1)
                self.__check_publisher_info(expected)

                self.pkg("set-property use-system-repo True")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test12\tfalse\ttrue\ttrue\torigin\tonline\t{rurl2}/\t-
test12\tfalse\ttrue\ttrue\torigin\tonline\t{durl2}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\torigin\tonline\t{rurl3}/\t-
test3\ttrue\ttrue\ttrue\torigin\tonline\t{durl3}/\thttp://localhost:{port}
test4\ttrue\ttrue\ttrue\t\t\t\t
""".format(rurl1=self.rurl1, durl1=self.durl1, rurl2=self.rurl2,
    durl2=self.durl2, rurl3=self.rurl3, durl3=self.durl3,
    port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                self.__set_responses("test1")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test3\ttrue\tfalse\ttrue\torigin\tonline\t{rurl3}/\t-
test12\ttrue\tfalse\ttrue\torigin\tonline\t{rurl2}/\t-
""".format(rurl1=self.rurl1, durl1=self.durl1, rurl3=self.rurl3,
    rurl2=self.rurl2, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                self.pkg("set-publisher --search-before test3 test12")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test12\ttrue\tfalse\ttrue\torigin\tonline\t{rurl2}/\t-
test3\ttrue\tfalse\ttrue\torigin\tonline\t{rurl3}/\t-
""".format(rurl1=self.rurl1, durl1=self.durl1, rurl2=self.rurl2,
    rurl3=self.rurl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                self.pkg("set-publisher --search-after test3 test12")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test3\ttrue\tfalse\ttrue\torigin\tonline\t{rurl3}/\t-
test12\ttrue\tfalse\ttrue\torigin\tonline\t{rurl2}/\t-
""".format(rurl1=self.rurl1, durl1=self.durl1, rurl3=self.rurl3,
    rurl2=self.rurl2, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                self.pkg("set-publisher --search-before test1 test12", exit=1)
                self.pkg("set-publisher -d --search-before test1 test12",
                    exit=1)
                # Ensure that test12 is not disabled.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test3\ttrue\tfalse\ttrue\torigin\tonline\t{rurl3}/\t-
test12\ttrue\tfalse\ttrue\torigin\tonline\t{rurl2}/\t-
""".format(rurl1=self.rurl1, durl1=self.durl1, rurl3=self.rurl3,
    rurl2=self.rurl2, port=self.sysrepo_port)
                self.__check_publisher_info(expected)
                self.pkg("set-publisher --search-after test1 test12", exit=1)
                self.pkg("set-publisher --non-sticky --search-after test1 "
                    "test12", exit=1)
                # Ensure that test12 is still sticky.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test3\ttrue\tfalse\ttrue\torigin\tonline\t{rurl3}/\t-
test12\ttrue\tfalse\ttrue\torigin\tonline\t{rurl2}/\t-
""".format(rurl1=self.rurl1, durl1=self.durl1, rurl3=self.rurl3,
    rurl2=self.rurl2, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                # Check that attempting to change test12 relative to test1
                # fails.
                self.pkg("set-publisher --search-before test12 test1", exit=1)
                self.pkg("set-publisher --search-after test12 test1", exit=1)
                self.pkg("set-publisher --search-first test12")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{rurl1}/\t-
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test12\ttrue\tfalse\ttrue\torigin\tonline\t{rurl2}/\t-
test3\ttrue\tfalse\ttrue\torigin\tonline\t{rurl3}/\t-
""".format(rurl1=self.rurl1, durl1=self.durl1, rurl2=self.rurl2,
    rurl3=self.rurl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                self.pkg("set-property use-system-repo False")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test12\ttrue\tfalse\ttrue\torigin\tonline\t{0}/\t-
test3\ttrue\tfalse\ttrue\torigin\tonline\t{1}/\t-
test1\ttrue\tfalse\ttrue\torigin\tonline\t{2}/\t-
""".format(self.rurl2, self.rurl3, self.rurl1)
                self.__check_publisher_info(expected)

        def test_07_environment_variable(self):
                """Test that setting the environment variable PKG_SYSREPO_URL
                sets the url that pkg uses to communicate with the system
                repository."""

                self.__prep_configuration(["all-access"],
                    port=self.sysrepo_alt_port)
                self.__set_responses("all-access")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["all-access"],
                    self.sysrepo_alt_port, self.common_config_dir,
                    testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                old_psu = os.environ.get("PKG_SYSREPO_URL", None)
                os.environ["PKG_SYSREPO_URL"] = "localhost:{0}".format(
                    self.sysrepo_alt_port)
                api_obj = self.image_create(props={"use-system-repo": True})
                expected =  self.expected_all_access.format(
                    durl1=self.durl1, durl2=self.durl2,
                    durl3=self.durl3, port=self.sysrepo_alt_port)
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
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["all-access-f"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                # Find the hashes that will be included in the urls of the
                # proxied file repos.
                hash1 = digest.DEFAULT_HASH_FUNC("file://" +
                    self.dcs[1].get_repodir().rstrip("/")).hexdigest()
                hash2 = digest.DEFAULT_HASH_FUNC("file://" +
                    self.dcs[2].get_repodir().rstrip("/")).hexdigest()
                hash3 = digest.DEFAULT_HASH_FUNC("file://" +
                    self.dcs[3].get_repodir().rstrip("/")).hexdigest()

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test1/{hash1}/\t-
test12\tfalse\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test12/{hash2}/\t-
test3\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test3/{hash3}/\t-
""".format(port=self.sysrepo_port, hash1=hash1, hash2=hash2,
    hash3=hash3)

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
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\tfalse\t\t\t\t
"""
                self.__check_publisher_info(expected)

                # Check that when the user adds an origin to a former system
                # publisher with an installed package, the publisher becomes
                # enabled and is not a system publisher.
                self.pkg("set-publisher -g {0} test1".format(self.rurl1))
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\tfalse\ttrue\torigin\tonline\t{rurl1}/\t-
""".format(rurl1=self.rurl1)
                self.__check_publisher_info(expected)

        def test_09_test_file_http_transitions(self):
                """Test that changing publishers from http to file repos and
                back in the sysrepo works as expected."""

                self.__prep_configuration(["all-access", "all-access-f",
                    "none"])
                self.__set_responses("all-access-f")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["all-access-f"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                # Find the hashes that will be included in the urls of the
                # proxied file repos.
                hash1 = digest.DEFAULT_HASH_FUNC("file://" +
                    self.dcs[1].get_repodir().rstrip("/")).hexdigest()
                hash2 = digest.DEFAULT_HASH_FUNC("file://" +
                    self.dcs[2].get_repodir().rstrip("/")).hexdigest()
                hash3 = digest.DEFAULT_HASH_FUNC("file://" +
                    self.dcs[3].get_repodir().rstrip("/")).hexdigest()

                self.__set_responses("all-access-f")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test1/{hash1}/\t-
test12\tfalse\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test12/{hash2}/\t-
test3\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test3/{hash3}/\t-
""".format(port=self.sysrepo_port, hash1=hash1, hash2=hash2,
    hash3=hash3)

                self.__check_publisher_info(expected)

                self.__set_responses("all-access")
                expected =  self.expected_all_access.format(
                    durl1=self.durl1, durl2=self.durl2,
                    durl3=self.durl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

        def test_10_test_mirrors(self):
                """Test that mirror information from the sysrepo is handled
                correctly."""

                self.__prep_configuration(["all-access", "all-access-f",
                    "mirror-access", "mirror-access-f", "none"])
                self.__set_responses("mirror-access")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["mirror-access"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                # Find the hashes that will be included in the urls of the
                # proxied file repos.
                hash1 = digest.DEFAULT_HASH_FUNC("file://" +
                    self.dcs[1].get_repodir().rstrip("/")).hexdigest()
                hash2 = digest.DEFAULT_HASH_FUNC("file://" +
                    self.dcs[2].get_repodir().rstrip("/")).hexdigest()
                hash3 = digest.DEFAULT_HASH_FUNC("file://" +
                    self.dcs[3].get_repodir().rstrip("/")).hexdigest()

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test1\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:{port}/test1/{hash1}/\t-
test12\tfalse\ttrue\ttrue\torigin\tonline\t{durl2}/\thttp://localhost:{port}
test12\tfalse\ttrue\ttrue\tmirror\tonline\thttp://localhost:{port}/test12/{hash2}/\t-
test3\ttrue\ttrue\ttrue\torigin\tonline\t{durl3}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:{port}/test3/{hash3}/\t-
""".format(port=self.sysrepo_port, hash1=hash1, hash2=hash2,
    hash3=hash3, durl1=self.durl1, durl2=self.durl2,
    durl3=self.durl3)

                self.__check_publisher_info(expected)

                self.__set_responses("mirror-access-f")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test1/{hash1}/\t-
test1\ttrue\ttrue\ttrue\tmirror\tonline\t{durl1}/\thttp://localhost:{port}
test12\tfalse\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test12/{hash2}/\t-
test12\tfalse\ttrue\ttrue\tmirror\tonline\t{durl2}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test3/{hash3}/\t-
test3\ttrue\ttrue\ttrue\tmirror\tonline\t{durl3}/\thttp://localhost:{port}
""".format(port=self.sysrepo_port, hash1=hash1, hash2=hash2,
    hash3=hash3, durl1=self.durl1, durl2=self.durl2,
    durl3=self.durl3)

                self.__check_publisher_info(expected)

                self.__set_responses("none")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
"""
                self.__check_publisher_info(expected)

                self.__set_responses("mirror-access-f")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test1/{hash1}/\t-
test1\ttrue\ttrue\ttrue\tmirror\tonline\t{durl1}/\thttp://localhost:{port}
test12\tfalse\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test12/{hash2}/\t-
test12\tfalse\ttrue\ttrue\tmirror\tonline\t{durl2}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\torigin\tonline\thttp://localhost:{port}/test3/{hash3}/\t-
test3\ttrue\ttrue\ttrue\tmirror\tonline\t{durl3}/\thttp://localhost:{port}
""".format(port=self.sysrepo_port, hash1=hash1, hash2=hash2,
    hash3=hash3, durl1=self.durl1, durl2=self.durl2,
    durl3=self.durl3)

                self.__check_publisher_info(expected)

                self.__set_responses("all-access")
                expected =  self.expected_all_access.format(
                    durl1=self.durl1, durl2=self.durl2,
                    durl3=self.durl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

                self.__set_responses("mirror-access")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{durl1}/\thttp://localhost:{port}
test1\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:{port}/test1/{hash1}/\t-
test12\tfalse\ttrue\ttrue\torigin\tonline\t{durl2}/\thttp://localhost:{port}
test12\tfalse\ttrue\ttrue\tmirror\tonline\thttp://localhost:{port}/test12/{hash2}/\t-
test3\ttrue\ttrue\ttrue\torigin\tonline\t{durl3}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\tmirror\tonline\thttp://localhost:{port}/test3/{hash3}/\t-
""".format(port=self.sysrepo_port, hash1=hash1, hash2=hash2,
    hash3=hash3, durl1=self.durl1, durl2=self.durl2,
    durl3=self.durl3)

                self.__check_publisher_info(expected)

        def test_11_https_repos(self, use_config_cache=False):
                """Test that https repos are proxied correctly."""
                self.base_11_https_repos()

        def test_11a_https_repos(self):
                """Ensure https configurations are created properly when
                using a cached configuration."""
                self.base_11_https_repos(use_config_cache=True)

        def base_11_https_repos(self, use_config_cache=False):
                """Implementation of test_11_https_repos, parameterizing
                use_config_cache."""

                self.__prep_configuration(["https-access", "none"],
                    use_config_cache=use_config_cache)
                self.__set_responses("https-access")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["https-access"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test1\ttrue\ttrue\ttrue\torigin\tonline\t{ac1url}/\thttp://localhost:{port}
test12\tfalse\ttrue\ttrue\torigin\tonline\t{ac2url}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\torigin\tonline\t{ac3url}/\thttp://localhost:{port}
""".format(
    ac1url=self.acs[self.durl1].url.replace("https", "http"),
    ac2url=self.acs[self.durl2].url.replace("https", "http"),
    ac3url=self.acs[self.durl3].url.replace("https", "http"),
    port=self.sysrepo_port)

                self.__check_publisher_info(expected)

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg", "foo", "bar"])
                api_obj = self.get_img_api_obj()
                self._api_uninstall(api_obj, ["example_pkg", "foo", "bar"])
                self.__set_responses("none")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
"""
                self.__check_publisher_info(expected)
                self.pkg("contents -rm example_pkg", exit=1)

        def test_12_disabled_repos(self):
                """Test that repos which are disabled in the global zone do not
                create problems."""
                self.base_12_disabled_repos()

        def test_12a_disabled_repos(self):
                """Ensure disable configurations are created properly when
                using a cached configuration."""
                self.base_12_disabled_repos(use_config_cache=True)

        def base_12_disabled_repos(self, use_config_cache=False):
                """Implementation of test_12_disabled_repos, parameterizing
                use_config_cache."""

                self.__prep_configuration(["disabled"],
                    use_config_cache=use_config_cache)
                self.__set_responses("disabled")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["disabled"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test12\tfalse\ttrue\ttrue\torigin\tonline\t{durl2}/\thttp://localhost:{port}
test3\ttrue\ttrue\ttrue\torigin\tonline\t{durl3}/\thttp://localhost:{port}
""".format(durl2=self.durl2, durl3=self.durl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected)

        def test_13_no_url(self):
                """Test that publishers with no urls are allowed as syspubs
                and that we can add/remove origins."""
                self.base_13_no_url()

        def test_13a_no_url(self):
                """Test that publishers which use no url are allowed as syspubs
                when using cached configurations."""
                self.base_13_no_url(use_config_cache=True)

        def base_13_no_url(self, use_config_cache=False):
                """Implementation of test_13[a]_no_url, parameterizing
                use_config_cache."""

                self.__prep_configuration(["nourl"],
                    use_config_cache=use_config_cache)
                self.__set_responses("nourl")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["nourl"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})
                expected_empty = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test4\ttrue\ttrue\ttrue\t\t\t\t
"""
                self.pkg("publisher -F tsv")
                self.__check_publisher_info(expected_empty)
                self.pkg("unset-publisher test4", exit=1)
                self.pkg("set-publisher -g {0} test4".format(self.durl4))

                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test4\ttrue\ttrue\ttrue\torigin\tonline\t{0}/\t-
""".format(self.durl4)
                self.__check_publisher_info(expected)
                self.pkg("set-publisher -G {0} test4".format(self.durl4))
                self.__check_publisher_info(expected_empty)

                # add another empty publisher
                self.pkg("set-publisher empty")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test4\ttrue\ttrue\ttrue\t\t\t\t
empty\ttrue\tfalse\ttrue\t\t\t\t
"""
                self.__check_publisher_info(expected)
                # toggle the system publisher and verify that
                # our configuration made it to the image
                self.pkg("set-property use-system-repo False")

                expected_nonsyspub = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
test4\ttrue\tfalse\ttrue\t\t\t\t
empty\ttrue\tfalse\ttrue\t\t\t\t
"""
                # because we've added and removed local configuration for a
                # publisher, that makes that publisher hang around in the user
                # image configuration.
                # The user needs to unset the publisher to make it go away.
                self.__check_publisher_info(expected_nonsyspub)

                # verify the sysrepo configuration is still there
                self.pkg("set-property use-system-repo True")
                self.__check_publisher_info(expected)

        def test_bug_18326(self):
                """Test that an unprivileged user can use non-image modifying
                commands and that image modifying commands don't trace back."""

                self.__prep_configuration(["all-access", "none"])
                self.__set_responses("all-access")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["all-access"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                expected =  self.expected_all_access.format(
                    durl1=self.durl1, durl2=self.durl2,
                    durl3=self.durl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected, su_wrap=True)
                self.pkg("property", su_wrap=True)
                self.pkg("install foo", su_wrap=True, exit=1)

                self.__set_responses("none")
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
"""
                self.__check_publisher_info(expected, su_wrap=True)
                self.__check_publisher_info(expected)
                self.__set_responses("all-access")
                expected =  self.expected_all_access.format(
                    durl1=self.durl1, durl2=self.durl2,
                    durl3=self.durl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected, su_wrap=True)

                # Test that when the sysrepo isn't available, unprivileged users
                # don't lose functionality.
                sc.stop()
                # Since the last privileged command was done when no
                # system-publishers were available, that's what's expected when
                # the system repository isn't available.
                expected = """\
PUBLISHER\tSTICKY\tSYSPUB\tENABLED\tTYPE\tSTATUS\tURI\tPROXY
"""
                self.__check_publisher_info(expected, su_wrap=True)
                self.pkg("property", su_wrap=True)
                self.pkg("install foo", su_wrap=True, exit=1)

                # Now do a privileged command command to change what the state
                # on disk is.
                sc.start()
                expected =  self.expected_all_access.format(
                    durl1=self.durl1, durl2=self.durl2,
                    durl3=self.durl3, port=self.sysrepo_port)
                self.__check_publisher_info(expected)
                sc.stop()

                self.__check_publisher_info(expected, su_wrap=True)
                self.pkg("property", su_wrap=True)
                self.pkg("install foo", su_wrap=True, exit=1)

        def test_signature_policy_1(self):
                """Test that the image signature policy of ignore is propagated
                by the system-repository."""

                conf_name = "img-sig-ignore"
                self.__prep_configuration([conf_name])
                self.__set_responses(conf_name)
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs[conf_name], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                self.pkg("property -H signature-policy", su_wrap=True)
                self.assertEqualDiff("signature-policy ignore",
                    self.output.strip())
                self.pkg("property -H signature-policy")
                self.assertEqualDiff("signature-policy ignore",
                    self.output.strip())

        def test_signature_policy_2(self):
                """Test that the image signature policy of require is propagated
                by the system-repository."""

                conf_name = "img-sig-require"
                self.__prep_configuration([conf_name])
                self.__set_responses(conf_name)
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs[conf_name], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                self.pkg("property -H signature-policy")
                self.assertEqualDiff("signature-policy require-signatures",
                    self.output.strip())
                self.pkg("property -H signature-policy", su_wrap=True)
                self.assertEqualDiff("signature-policy require-signatures",
                    self.output.strip())

        def test_signature_policy_3(self):
                """Test that the image signature policy of require-names and the
                corresponding required names are propagated by the
                system-repository."""

                conf_name = "img-sig-req-names"
                self.__prep_configuration([conf_name])
                self.__set_responses(conf_name)
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs[conf_name], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()

                api_obj = self.image_create(props={"use-system-repo": True})

                self.pkg("property -H signature-policy", su_wrap=True)
                self.assertEqualDiff("signature-policy require-names",
                    self.output.strip())
                self.pkg("property -H signature-required-names", su_wrap=True)
                self.assertEqualDiff("signature-required-names ['cs1_ch1_ta3']",
                    self.output.strip())
                self.pkg("property -H signature-policy")
                self.assertEqualDiff("signature-policy require-names",
                    self.output.strip())
                self.pkg("property -H signature-required-names")
                self.assertEqualDiff("signature-required-names ['cs1_ch1_ta3']",
                    self.output.strip())

        def test_signature_policy_4(self):
                """Test that the publisher signature policies of ignore are
                propagated by the system-repository."""

                conf_name = "pub-sig-ignore"
                self.__prep_configuration([conf_name])
                self.__set_responses(conf_name)
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs[conf_name], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                self.pkg("publisher test1", su_wrap=True)
                self.assert_("signature-policy = ignore" in self.output)
                pubs = api_obj.get_publishers()
                for p in pubs:
                        self.assertEqualDiff(
                            p.prefix + ":" + p.properties["signature-policy"],
                            p.prefix + ":" + "ignore")

        def test_signature_policy_5(self):
                """Test that the publisher signature policies of
                require-signatures are propagated by the system-repository."""

                conf_name = "pub-sig-require"
                self.__prep_configuration([conf_name])
                self.__set_responses(conf_name)
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs[conf_name], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                pubs = api_obj.get_publishers()
                for p in pubs:
                        self.assertEqualDiff(
                            p.prefix + ":" + p.properties["signature-policy"],
                            p.prefix + ":" + "require-signatures")

        def test_signature_policy_6(self):
                """Test that publishers signature policies of require-names and
                the corresponding required names are propagated by the
                system-repository."""

                conf_name = "pub-sig-reqnames"
                self.__prep_configuration([conf_name])
                self.__set_responses(conf_name)
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs[conf_name], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                pubs = api_obj.get_publishers()
                for p in pubs:
                        self.assertEqualDiff(
                            p.prefix + ":" + p.properties["signature-policy"],
                            p.prefix + ":" + "require-names")
                        self.assertEqualDiff(
                            p.prefix + ":" +
                            " ".join(p.properties["signature-required-names"]),
                            p.prefix + ":" + "cs1_ch1_ta3")

        def test_signature_policy_7(self):
                """Test that a mixture of publisher signature policies are
                correctly propagated."""

                conf_name = "pub-sig-mixed"
                self.__prep_configuration([conf_name])
                self.__set_responses(conf_name)
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs[conf_name], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})

                pubs = api_obj.get_publishers()
                for p in pubs:
                        if p.prefix == "test1":
                                self.assertEqualDiff(
                                    p.prefix + ":" +
                                    p.properties["signature-policy"],
                                    p.prefix + ":" + "require-signatures")
                        elif p.prefix == "test12":
                                self.assert_("signature-policy" not in
                                    p.properties)
                        else:
                                self.assertEqualDiff(
                                    p.prefix + ":" +
                                    p.properties["signature-policy"],
                                    p.prefix + ":" + "verify")

        def test_signature_policy_8(self):
                """Test that a mixture of image and publisher signature policies
                are correctly propagated."""

                conf_name = "img-pub-sig-mixed"
                self.__prep_configuration([conf_name])
                self.__set_responses(conf_name)
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs[conf_name], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()

                api_obj = self.image_create(props={"use-system-repo": True})

                self.pkg("property -H signature-policy")
                self.assertEqualDiff("signature-policy ignore",
                    self.output.strip())

                pubs = api_obj.get_publishers()
                for p in pubs:
                        if p.prefix == "test1":
                                self.assertEqualDiff(
                                    p.prefix + ":" +
                                    p.properties["signature-policy"],
                                    p.prefix + ":" + "require-signatures")
                        elif p.prefix == "test12":
                                self.assertEqualDiff(
                                    p.prefix + ":" +
                                    p.properties["signature-policy"],
                                    p.prefix + ":" + "require-names")
                                self.assertEqualDiff(
                                    p.prefix + ":" +
                                    " ".join(p.properties[
                                        "signature-required-names"]),
                                    p.prefix + ":" + "cs1_ch1_ta3 foo bar baz")
                        else:
                                self.assertEqualDiff(
                                    p.prefix + ":" +
                                    p.properties["signature-policy"],
                                    p.prefix + ":" + "ignore")

        def test_catalog_is_not_cached_http(self):
                """Test that the catalog response is not cached when dealing
                with an http repo."""

                conf_name = "test1-test3"
                self.__prep_configuration([conf_name])
                self.__set_responses(conf_name)
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs[conf_name], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})
                self.pkgsend_bulk(self.rurl1, self.foo11)
                self.pkgsend_bulk(self.rurl3, self.bar11)
                self.pkg("install bar@1.1")
                self.pkg("install foo@1.1")

        def test_catalog_is_not_cached_file(self):
                """Test that the catalog response is not cached when dealing
                with an http repo."""

                conf_name = "test1-test3-f"
                self.__prep_configuration([conf_name])
                self.__set_responses(conf_name)
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs[conf_name], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                api_obj = self.image_create(props={"use-system-repo": True})
                self.pkgsend_bulk(self.rurl1, self.foo11)
                self.pkgsend_bulk(self.rurl3, self.bar11)
                self.pkg("install foo@1.1")
                self.pkg("install bar@1.1")

        def test_no_unnecessary_refresh(self):
                """Test that the pkg client doesn't rebuild the known image
                catalog unnecessarily.

                The way we test this is kinda obtuse.  To test this we use a
                staged image operation.  This allows us to break up pkg
                execution into three stages, planning, preparation, and
                execution.  At the end of the planning stage, we create and
                save an image plan to disk.  This image plan includes the last
                modified timestamp for the known catalog.  Subsequently when
                we go to load the plan from disk (during preparation and
                execution) we check that timestamp to make sure the image
                hasn't changed since the plan was generated (this ensures that
                the image plan is still valid). So if the pkg client decides
                to update the known catalog unnecessarily then we'll fail when
                we try to reload the plan during preparation
                (--stage=prepare)."""

                self.__prep_configuration(["test1-test12-test12",
                    "test12-test12"])
                self.__set_responses("test1-test12-test12")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["test1-test12-test12"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()

                # enable the test1 and test12 publishers
                self.__set_responses("test1-test12-test12")

                api_obj = self.image_create(props={"use-system-repo": True})

                # install a package from the test1 and test12 publisher
                self.pkg("install example_pkg foo@1.0")

                # disable the test1 publisher
                self.__set_responses("test12-test12")

                # do a staged update
                self.pkg("update --stage=plan")
                self.pkg("update --stage=prepare")
                self.pkg("update --stage=execute")

        def test_automatic_refresh(self):
                """Test that sysrepo publishers get refreshed automatically
                when sysrepo configuration changes."""

                self.__prep_configuration(["test1", "test1-test12",
                    "test1-test12-test12"])
                self.__set_responses("test1-test12")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["test1-test12"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()

                api_obj = self.image_create(props={"use-system-repo": True})

                # the client should see packages from the test1 and test12 pubs.
                self.pkg("list -afH")
                expected = (
                    "example_pkg 1.0-0 ---\n"
                    "foo (test12) 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # remove the test12 pub.
                self.__set_responses("test1")
                self.pkg("list -afH")
                expected = "example_pkg 1.0-0 ---\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # add the test12 pub.
                self.__set_responses("test1-test12")
                self.pkg("list -afH")
                expected = (
                    "example_pkg 1.0-0 ---\n"
                    "foo (test12) 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # add an origin (with new packages) to the test12 pub.
                self.__set_responses("test1-test12-test12")
                self.pkg("list -afH")
                expected = (
                    "example_pkg 1.0-0 ---\n"
                    "foo (test12) 1.1-0 ---\n"
                    "foo (test12) 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # push a new package into one of the test12 repos.
                # (we have to do an explicit refresh since "list" won't do it
                # because last_refreshed is too recent.)
                self.pkgsend_bulk(self.rurl2, self.bar10)
                self.pkg("refresh")
                self.pkg("list -afH")
                expected = (
                    "bar (test12) 1.0-0 ---\n"
                    "example_pkg 1.0-0 ---\n"
                    "foo (test12) 1.1-0 ---\n"
                    "foo (test12) 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # remove an origin from the test12 pub.
                self.__set_responses("test1-test12")
                self.pkg("list -afH")
                expected = (
                    "bar (test12) 1.0-0 ---\n"
                    "example_pkg 1.0-0 ---\n"
                    "foo (test12) 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # install a package from the test12 pub.
                # then re-do a bunch of the tests above.
                self.pkg("install foo")

                # remove the test12 pub.
                self.__set_responses("test1")
                self.pkg("list -afH")
                expected = (
                    "example_pkg 1.0-0 ---\n"
                    "foo (test12) 1.0-0 i--\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # add the test12 pub.
                self.__set_responses("test1-test12")
                self.pkg("list -afH")
                expected = (
                    "bar (test12) 1.0-0 ---\n"
                    "example_pkg 1.0-0 ---\n"
                    "foo (test12) 1.0-0 i--\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # add an origin (with new packages) to the test12 pub.
                self.__set_responses("test1-test12-test12")
                self.pkg("list -afH")
                expected = (
                    "bar (test12) 1.0-0 ---\n"
                    "example_pkg 1.0-0 ---\n"
                    "foo (test12) 1.1-0 ---\n"
                    "foo (test12) 1.0-0 i--\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # push a new package into one of the test12 repos.
                # (we have to do an explicit refresh since "list" won't do it
                # because last_refreshed is too recent.)
                self.pkgsend_bulk(self.rurl2, self.bar11)
                self.pkg("refresh")
                self.pkg("list -afH")
                expected = (
                    "bar (test12) 1.1-0 ---\n"
                    "bar (test12) 1.0-0 ---\n"
                    "example_pkg 1.0-0 ---\n"
                    "foo (test12) 1.1-0 ---\n"
                    "foo (test12) 1.0-0 i--\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # remove an origin from the test12 pub.
                self.__set_responses("test1-test12")
                self.pkg("list -afH")
                expected = (
                    "bar (test12) 1.1-0 ---\n"
                    "bar (test12) 1.0-0 ---\n"
                    "example_pkg 1.0-0 ---\n"
                    "foo (test12) 1.0-0 i--\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_syspub_toggle(self):
                """Test that sysrepo publishers get refreshed automatically
                when sysrepo configuration changes."""

                self.__prep_configuration(["test1"])
                self.__set_responses("test1")
                sc = pkg5unittest.SysrepoController(
                    self.apache_confs["test1"], self.sysrepo_port,
                    self.common_config_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()

                api_obj = self.image_create(props={"use-system-repo": True})

                # the client should see packages from the test1 pubs.
                self.pkg("list -afH")
                expected = (
                    "example_pkg 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # push a new package into one of the test12 repos.
                self.pkgsend_bulk(self.rurl1, self.bar10)

                # verify that the client only sees the new package after an
                # explicit refresh
                self.pkg("list -afH")
                expected = (
                    "example_pkg 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("refresh")
                self.pkg("list -afH")
                expected = (
                    "bar 1.0-0 ---\n"
                    "example_pkg 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # disable the sysrepo.
                self.pkg("set-property use-system-repo False")

                # the client should not see any packages.
                self.pkg("list -afH", exit=1)
                expected = ("")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # push a new package into one of the test12 repos.
                self.pkgsend_bulk(self.rurl1, self.bar11)

                # enable the sysrepo.
                self.pkg("set-property use-system-repo True")

                # the client should see packages from the test1 pubs.
                self.pkg("list -afH")
                expected = (
                    "bar 1.1-0 ---\n"
                    "bar 1.0-0 ---\n"
                    "example_pkg 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # install a package from the test12 pub.
                # then re-do a bunch of the tests above.
                self.pkg("install example_pkg")

                # disable the sysrepo.
                self.pkg("set-property use-system-repo False")

                # the client should only see the installed package.
                self.pkg("list -afH")
                expected = (
                    "example_pkg 1.0-0 i--\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # push a new package into one of the test12 repos.
                self.pkgsend_bulk(self.rurl1, self.foo10)

                # enable the sysrepo.
                self.pkg("set-property use-system-repo True")

                # the client should see packages from the test1 pubs.
                self.pkg("list -afH")
                expected = (
                    "bar 1.1-0 ---\n"
                    "bar 1.0-0 ---\n"
                    "example_pkg 1.0-0 i--\n"
                    "foo 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        __smf_cmds_template = { \
            "usr/bin/svcprop" : """\
#!/usr/bin/python

import getopt
import sys

if __name__ == "__main__":
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "cp:")
        except getopt.GetoptError as e:
                usage(_("illegal global option -- {{0}}").format(e.opt))

        prop_dict = {{
            "config/listen_host" : "localhost",
            "config/listen_port" : "{proxy_port}",
            "general/enabled" : "true",
        }}

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
                print(prop)
                sys.exit(0)
        for k, v in prop_dict.iteritems():
                print("{{0}} {{1}}".format(k, v))
        sys.exit(0)
""",

            "usr/sbin/svcadm" : """\
#!/usr/bin/python

import getopt
import sys

if __name__ == "__main__":
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "cp:")
        except getopt.GetoptError as e:
                usage(_("illegal global option -- {{0}}").format(e.opt))

        prop_dict = {{
            "config/proxy_host" : "localhost",
            "config/proxy_port" : "{proxy_port}"
        }}

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

PidFile "{pidfile}"

#
# Listen: Allows you to bind Apache to specific IP addresses and/or
# ports, instead of the default. See also the <VirtualHost>
# directive.
#
# Change this to Listen on specific IP addresses as shown below to
# prevent Apache from glomming onto all bound IP addresses.
#
Listen 0.0.0.0:{https_port}

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
ErrorLog "{log_locs}/error_log"

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
    LogFormat "{common_log_format}" common

    #
    # The location and format of the access logfile (Common Logfile Format).
    # If you do not define any access logfiles within a <VirtualHost>
    # container, they will be logged here.  Contrariwise, if you *do*
    # define per-<VirtualHost> access logfiles, transactions will be
    # logged therein and *not* in this file.
    #
    CustomLog "{log_locs}/access_log" common
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

<VirtualHost 0.0.0.0:{https_port}>
        AllowEncodedSlashes On
        ProxyRequests Off
        MaxKeepAliveRequests 10000

        SSLEngine On

        # Cert paths
        SSLCertificateFile {server-ssl-cert}
        SSLCertificateKeyFile {server-ssl-key}

        # Combined product CA certs for client verification
        SSLCACertificateFile {server-ca-cert}

	SSLVerifyClient require

        <Location />
                SSLVerifyDepth 1

	        # The client's certificate must pass verification, and must have
	        # a CN which matches this repository.
                SSLRequire ( {ssl-special} =~ m/{server-ca-taname}/ )

                # set max to number of threads in depot
                ProxyPass {proxied-server}/ nocanon max=500
        </Location>
</VirtualHost>


"""
