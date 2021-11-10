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
# Copyright (c) 2015, 2021, Oracle and/or its affiliates.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.client.client_api as cli_api
import pkg.client.progress as progress
import rapidjson as json
import jsonschema

from pkg.client import global_settings


class TestClientApi(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

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

        newpkg10 = """
            open newpkg@1.0
            close """

        newpkg210 = """
            open newpkg2@1.0
            close """

        hierfoo10 = """
            open hier/foo@1.0,5.11-0
            close """

        verifypkg10 = """
            open verifypkg@1.0,5.11-0:20160302T054916Z
            add dir mode=0755 owner=root group=sys path=/etc
            add dir mode=0755 owner=root group=sys path=/etc/security
            add dir mode=0755 owner=root group=sys path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file bobcat mode=0644 owner=root group=bin path=/usr/bin/bobcat
            add file bobcat path=/etc/preserved mode=644 owner=root group=sys preserve=true timestamp="20080731T024051Z"
            add file dricon_maj path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file dricon_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file dricon_cls path=/etc/driver_classes mode=644 owner=root group=sys preserve=true
            add file dricon_mp path=/etc/minor_perm mode=644 owner=root group=sys preserve=true
            add file dricon_dp path=/etc/security/device_policy mode=644 owner=root group=sys preserve=true
            add file dricon_ep path=/etc/security/extra_privs mode=644 owner=root group=sys preserve=true
            add file permission mode=0600 owner=root group=bin path=/etc/permission preserve=true
            add driver name=zigit alias=pci8086,1234
            close
            """

        misc_files = {
           "bobcat": "",
           "dricon_da": """zigit "pci8086,1234"\n""",
           "dricon_maj": """zigit 103\n""",
           "dricon_cls": """\n""",
           "dricon_mp": """\n""",
           "dricon_dp": """\n""",
           "dricon_ep": """\n""",
           "permission": ""
        }

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test2"])
                self.make_misc_files(self.misc_files)

                self.rurl1 = self.dcs[1].get_repo_url()
                self.pkgsend_bulk(self.rurl1, (self.foo1, self.foo10,
                    self.foo11, self.foo12, self.foo121, self.food12,
                    self.hierfoo10, self.newpkg10, self.newpkg210,
                    self.verifypkg10))

                # Ensure that the second repo's packages have exactly the same
                # timestamps as those in the first ... by copying the repo over.
                # If the repos need to have some contents which are different,
                # send those changes after restarting depot 2.
                d1dir = self.dcs[1].get_repodir()
                d2dir = self.dcs[2].get_repodir()
                self.copy_repository(d1dir, d2dir, { "test1": "test2" })

                # The new repository won't have a catalog, so rebuild it.
                self.dcs[2].get_repo(auto_create=True).rebuild()

                # The third repository should remain empty and not be
                # published to.

                # Next, create the image and configure publishers.
                self.image_create(self.rurl1, prefix="test1")
                self.rurl2 = self.dcs[2].get_repo_url()
                self.pkg("set-publisher -O " + self.rurl2 + " test2")

                self.rurl3 = self.dcs[3].get_repo_url()

        def __call_cmd(self, subcommand, args, opts):
                retjson = cli_api._pkg_invoke(subcommand=subcommand,
                    pargs_json=json.dumps(args), opts_json=json.dumps(opts))
                return retjson

        def test_01_invalid_pkg_invoke_args(self):
                """Test invalid pkg_invoke args is handled correctly."""

                pkgs = ["foo"]
                opts = {"list_installed_newest": True, "list_all": True}
                os.environ["PKG_IMAGE"] = self.img_path()
                retjson = self.__call_cmd(None, pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("Sub-command"
                    in retjson["errors"][0]["reason"])

                invalidpargs = {"invalid": -1}
                retjson = self.__call_cmd("list", invalidpargs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("pargs_json is invalid"
                    in retjson["errors"][0]["reason"])

                invalidpargs = {"invalid": -1}
                retjson = self.__call_cmd("publisher", invalidpargs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("pargs_json is invalid"
                    in retjson["errors"][0]["reason"])

                invalidpargs = "+1+1random"
                retjson = cli_api._pkg_invoke(subcommand="list",
                    pargs_json=invalidpargs,
                    opts_json=json.dumps(opts))
                self.assertTrue("errors" in retjson)
                self.assertTrue("pargs_json is invalid"
                    in retjson["errors"][0]["reason"])

                invalidopts = "+1+1random"
                retjson = cli_api._pkg_invoke(subcommand="list",
                    pargs_json=json.dumps([]),
                    opts_json=invalidopts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("opts_json is invalid"
                    in retjson["errors"][0]["reason"])

        def test_02_valid_pkg_invoke_args(self):
                """Test valid arguments for pkg json."""

                self.image_create(self.rurl1, prefix="test1")
                os.environ["PKG_IMAGE"] = self.img_path()
                pkgs = ["foo"]
                opts = {"list_newest": True}

                self.pkg("install pkg://test1/foo")
                retjson = cli_api._pkg_invoke(subcommand="list", pargs_json=None,
                    opts_json=json.dumps(opts))
                self.assertTrue("errors" not in retjson, retjson)

                retjson = cli_api._pkg_invoke(subcommand="list",
                    pargs_json=json.dumps(["foo"]),
                    opts_json=None)
                self.assertTrue("errors" not in retjson, retjson)

                retjson = self.__call_cmd("list", pkgs, opts)
                self.assertTrue("errors" not in retjson)

        def __schema_validation(self, input, schema):
                """Test if the input is valid against the schema."""

                try:
                        jsonschema.validate(input, schema)
                        return True
                except Exception as e:
                        return False

        def test_03_list_json_args_opts(self):
                """Test json args or opts for list command."""

                self.image_create(self.rurl1, prefix="test1")
                pkgs = [1, 2, 3]
                opts = {"list_installed_newest": True, "list_all": True}
                os.environ["PKG_IMAGE"] = self.img_path()
                retjson = self.__call_cmd("list", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'string'" in
                    retjson["errors"][0]["reason"])

                pkgs = [None]
                retjson = self.__call_cmd("list", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'string'" in
                    retjson["errors"][0]["reason"])

                pkgs = []
                opts = {"list_installed_newest": 1}
                retjson = self.__call_cmd("list", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'boolean'" in
                    retjson["errors"][0]["reason"])

                opts = {"origins": 1}
                retjson = self.__call_cmd("list", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'array'" in
                    retjson["errors"][0]["reason"])

                opts = {"random": 1}
                retjson = self.__call_cmd("list", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("invalid option" in \
                    retjson["errors"][0]["reason"])

                # Test args and opts directly against schema.
                pargs = "pargs_json"
                list_schema = cli_api._get_pkg_input_schema("list")
                list_input = {pargs: [], "opts_json": {}}
                self.assertTrue(self.__schema_validation(list_input, list_schema))

                list_input = {pargs: [12], "opts_json": {}}
                self.assertTrue(not self.__schema_validation(list_input,
                    list_schema))

                list_input = {pargs: [],
                    "opts_json": {"list_upgradable": "string"}}
                self.assertTrue(not self.__schema_validation(list_input,
                    list_schema))

                list_input = {pargs: [], "opts_json": {"list_upgradable":
                    False}}
                self.assertTrue(self.__schema_validation(list_input,
                    list_schema))

                list_input = {pargs: [], "opts_json": {"origins": False}}
                self.assertTrue(not self.__schema_validation(list_input,
                    list_schema))

                list_input = {pargs: [], "opts_json": {"origins": []}}
                self.assertTrue(self.__schema_validation(list_input,
                    list_schema))

        def test_04_install_json_args_opts(self):
                """Test json args or opts for install command."""

                # Test invalid pkg name.
                self.image_create(self.rurl1, prefix="test1")
                os.environ["PKG_IMAGE"] = self.img_path()
                pkgs = [1, 2, 3]
                opts = {"backup_be": True}
                retjson = self.__call_cmd("install", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'string'" in
                    retjson["errors"][0]["reason"])

                pkgs = [None]
                opts = {"backup_be": True}
                os.environ["PKG_IMAGE"] = self.img_path()
                retjson = self.__call_cmd("install", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'string'" in
                    retjson["errors"][0]["reason"])

                # Test unknown option was reported.
                pkgs = ["newpkg@1.0"]
                opts = {"unknown": "solaris"}
                retjson = self.__call_cmd("install", pkgs, opts)
                self.assertTrue("invalid option" in
                    retjson["errors"][0]["reason"])

                # Test without pkg specified.
                pkgs = []
                opts = {"verbose": 3}
                retjson = self.__call_cmd("install", pkgs, opts)
                self.assertTrue("at least one package" in
                    retjson["errors"][0]["reason"])

                # Run through pkg install.
                pkgs = ["newpkg@1.0"]
                opts = {"parsable_version": 0}
                global_settings.client_output_quiet = True
                retjson = self.__call_cmd("install", pkgs, opts)
                global_settings.client_output_quiet = False

                # Test input directly against schema.
                pargs = "pargs_json"
                install_schema = cli_api._get_pkg_input_schema("install")
                install_input = {pargs : [], "opts_json": {}}
                self.assertTrue(self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs: [12], "opts_json": {}}
                self.assertTrue(not self.__schema_validation(install_input,
                    install_schema))

                install_input = { pargs: ["pkg"], "opts_json": {}}
                self.assertTrue(self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs : ["pkg"], "opts_json":
                    {"parsable_version": "string"}}
                self.assertTrue(not self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs: ["pkg"], "opts_json":
                    {"parsable_version": 3}}
                self.assertTrue(not self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs: ["pkg"], "opts_json":
                    {"parsable_version": None}}
                self.assertTrue(self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs: ["pkg"], "opts_json": {"reject_pats":
                    False}}
                self.assertTrue(not self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs: ["pkg"], "opts_json": {"reject_pats":
                    []}}
                self.assertTrue(self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs: ["pkg"], "opts_json": {"accept": "str"}}
                self.assertTrue(not self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs: ["pkg"], "opts_json": {"accept": False}}
                self.assertTrue(self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs: ["pkg"], "opts_json":
                    {"act_timeout": 1.2}}
                self.assertTrue(not self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs: ["pkg"], "opts_json":
                    {"act_timeout": -1}}
                self.assertTrue(not self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs: ["pkg"], "opts_json":
                    {"li_erecurse_list": [None, None]}}
                self.assertTrue(not self.__schema_validation(install_input,
                    install_schema))

                install_input = {pargs: [None], "opts_json":
                    {"li_erecurse_list": []}}
                self.assertTrue(not self.__schema_validation(install_input,
                    install_schema))

        def test_05_update_json_args_opts(self):
                """Test json args or opts for update command."""

                global_settings.client_output_quiet = True
                self.image_create(self.rurl1, prefix="test1")
                os.environ["PKG_IMAGE"] = self.img_path()
                # Test invalid pkg name.
                pkgs = [1, 2, 3]
                opts = {"backup_be": True}
                retjson = self.__call_cmd("update", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'string'" in
                    retjson["errors"][0]["reason"])

                pkgs = [None]
                opts = {"backup_be": True}
                os.environ["PKG_IMAGE"] = self.img_path()
                retjson = self.__call_cmd("update", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'string'" in
                    retjson["errors"][0]["reason"])

                # Test unknown option was reported.
                pkgs = ["newpkg@1.0"]
                opts = {"unknown": "solaris"}
                retjson = self.__call_cmd("update", pkgs, opts)
                self.assertTrue("invalid option" in
                    retjson["errors"][0]["reason"])

                # Test without pkg specified.
                pkgs = []
                opts = {"verbose": 3}
                retjson = self.__call_cmd("update", pkgs, opts)
                self.assertTrue(retjson["status"] == 4)

                # Run through pkg update.
                self.pkg("install pkg://test1/foo@1.0")
                pkgs = ["foo@1.1"]
                opts = {"parsable_version": 0}

                retjson = self.__call_cmd("update", pkgs, opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(retjson["status"] == 0)

                pkgs=[]
                retjson = self.__call_cmd("update", pkgs, opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(retjson["status"] == 0)
                global_settings.client_output_quiet = False

                # Test input directly against schema.
                pargs = "pargs_json"
                update_schema = cli_api._get_pkg_input_schema("update")
                update_input = {pargs: [], "opts_json": {}}
                self.assertTrue(self.__schema_validation(update_input,
                    update_schema))

                update_input = {pargs: [None], "opts_json": {}}
                self.assertTrue(not self.__schema_validation(update_input,
                    update_schema))

                update_input = {pargs: None, "opts_json": {}}
                self.assertTrue(not self.__schema_validation(update_input,
                    update_schema))

                update_input = {pargs: [1, 2], "opts_json": {}}
                self.assertTrue(not self.__schema_validation(update_input,
                    update_schema))

                update_input = {pargs: [], "opts_json": {"force": True}}
                self.assertTrue(self.__schema_validation(update_input,
                    update_schema))

                update_input = {pargs: [], "opts_json": {"ignore_missing":
                    True}}
                self.assertTrue(self.__schema_validation(update_input,
                    update_schema))

        def test_06_uninstall_args_opts(self):
                """Test json args or opts for update command."""

                global_settings.client_output_quiet = True
                self.image_create(self.rurl1, prefix="test1")
                os.environ["PKG_IMAGE"] = self.img_path()
                # Test invalid pkg name.
                pkgs = [1, 2, 3]
                opts = {}
                retjson = self.__call_cmd("uninstall", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'string'" in
                    retjson["errors"][0]["reason"])

                pkgs = [None]
                opts = {}
                os.environ["PKG_IMAGE"] = self.img_path()
                retjson = self.__call_cmd("uninstall", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'string'" in
                    retjson["errors"][0]["reason"])

                # Test unknown option was reported.
                pkgs = ["newpkg@1.0"]
                opts = {"unknown": "solaris"}
                retjson = self.__call_cmd("uninstall", pkgs, opts)
                self.assertTrue("invalid option" in
                    retjson["errors"][0]["reason"])

                # Test without pkg specified.
                pkgs = []
                opts = {"verbose": 3}
                retjson = self.__call_cmd("uninstall", pkgs, opts)
                self.assertTrue("at least one package" in
                    retjson["errors"][0]["reason"])

                # Run through pkg uninstall.
                self.pkg("install pkg://test1/foo@1.0")
                pkgs = ["foo"]
                opts = {"parsable_version": 0}

                retjson = self.__call_cmd("uninstall", pkgs, opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(retjson["status"] == 0)
                global_settings.client_output_quiet = False

                # Test input directly against schema.
                pargs = "pargs_json"
                uninstall_schema = cli_api._get_pkg_input_schema("uninstall")
                uninstall_input = {pargs: ["pkg"], "opts_json": {}}
                self.assertTrue(self.__schema_validation(uninstall_input,
                    uninstall_schema))

                uninstall_input = {pargs: None, "opts_json": {}}
                self.assertTrue(not self.__schema_validation(uninstall_input,
                    uninstall_schema))

                uninstall_input = {pargs: [], "opts_json": {"ignore_missing":
                    True}}
                self.assertTrue(self.__schema_validation(uninstall_input,
                    uninstall_schema))

        def test_07_set_publisher_args_opts(self):
                """Test json args or opts for update command."""

                global_settings.client_output_quiet = True
                self.rurl1 = self.dcs[1].get_repo_url()
                self.image_create(self.rurl1)
                os.environ["PKG_IMAGE"] = self.img_path()
                # Test invalid pkg name.
                pubs = ["test1"]
                opts = {"origin_uri": self.rurl1}
                retjson = self.__call_cmd("set-publisher", pubs, opts)
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)

                retjson = self.__call_cmd("unset-publisher", pubs, {})
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)

                opts = {"add_origins": [self.rurl1]}
                retjson = self.__call_cmd("set-publisher", pubs, opts)
                self.assertTrue("errors" not in retjson)

                pkgs = ["newpkg@1.0"]
                opts = {"parsable_version": 0}
                retjson = self.__call_cmd("install", pkgs, opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(retjson["status"] == 0)

                pkgs = ["newpkg"]
                opts = {"parsable_version": 0}
                retjson = self.__call_cmd("uninstall", pkgs, opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(retjson["status"] == 0)

                self.pkg("set-publisher -O " + self.rurl2 + " test2")
                retjson = cli_api._pkg_invoke(
                    subcommand="unset-publisher",
                    pargs_json=json.dumps(["test2"]),
                    opts_json=None)
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)

                retjson = self.__call_cmd("unset-publisher", pubs, {})
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)

                opts = {"repo_uri": self.rurl1}
                retjson = self.__call_cmd("set-publisher", [], opts)
                self.assertTrue(retjson["data"]["added"] == ["test1"])
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)

                retjson = self.__call_cmd("set-publisher", [], opts)
                self.assertTrue(retjson["data"]["updated"] == ["test1"])
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)

                pkgs = ["pkg://test1/foo@1"]
                opts = {"parsable_version": 0}
                retjson = self.__call_cmd("install", pkgs, opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(retjson["status"] == 0)

                opts = {"repo_uri": self.rurl2, "set_props": ["prop1=here",
                    "prop2=there"]}
                retjson = self.__call_cmd("set-publisher", [], opts)
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)

                opts = {"repo_uri": self.rurl2, "unset_props": ["prop1",
                    "prop2"]}
                retjson = self.__call_cmd("set-publisher", [], opts)
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)

                opts = {"repo_uri": self.rurl2, "search_before": "a",
                    "search_after": "b"}
                retjson = self.__call_cmd("set-publisher", [], opts)
                self.assertTrue(retjson["status"] == 2)
                self.assertTrue("errors" in retjson)

                opts = {"repo_uri": self.rurl2, "add_origins": ["a"]}
                retjson = self.__call_cmd("set-publisher", [], opts)
                self.assertTrue(retjson["status"] == 2)
                self.assertTrue("errors" in retjson)

                opts = {"repo_uri": self.rurl2, "refresh_allowed": False}
                retjson = self.__call_cmd("set-publisher", [], opts)
                self.assertTrue(retjson["status"] == 2)
                self.assertTrue("combined" in retjson["errors"][0]["reason"])

                opts = {"proxy_uri": self.rurl2}
                retjson = self.__call_cmd("set-publisher", [], opts)
                self.assertTrue(retjson["status"] == 2)
                self.assertTrue("only be used" in retjson["errors"][0]["reason"])
                global_settings.client_output_quiet = False

                # Test input directly against schema.
                pargs = "pargs_json"
                schema = cli_api._get_pkg_input_schema("set-publisher")

                test_input = {pargs: ["test1"], "opts_json": {"enable": True}}
                self.assertTrue(self.__schema_validation(test_input,
                    schema))

                test_input = {pargs: None, "opts_json": {"enable": True}}
                self.assertTrue(not self.__schema_validation(test_input,
                    schema))

                test_input = {pargs: [], "opts_json": {"repo_uri": "test"}}
                self.assertTrue(self.__schema_validation(test_input,
                    schema))

                schema = cli_api._get_pkg_input_schema("unset-publisher")
                test_input = {pargs: [], "opts_json": {}}
                self.assertTrue(self.__schema_validation(test_input,
                    schema))

        def test_08_publisher_args_opts(self):
                global_settings.client_output_quiet = True
                self.rurl1 = self.dcs[1].get_repo_url()
                self.image_create(self.rurl1)
                os.environ["PKG_IMAGE"] = self.img_path()
                opts = {"repo_uri": self.rurl1}
                retjson = self.__call_cmd("set-publisher", [], opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(retjson["status"] == 0)
                # Test unset pub name.
                pubs = ["no_pub"]
                opts = {}
                retjson = self.__call_cmd("publisher", pubs, opts)
                self.assertTrue(retjson["status"] == 1)
                self.assertTrue("Unknown publisher" in \
                    retjson["errors"][0]["reason"])

                pubs = []
                opts = {"omit_headers": True}
                retjson = self.__call_cmd("publisher", pubs, opts)
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("data" in retjson)
                self.assertTrue("headers" not in retjson["data"])

                pubs = []
                opts = {"output_format": "tsv"}
                retjson = self.__call_cmd("publisher", pubs, opts)
                self.assertTrue(len(retjson["data"]["headers"]) == 8)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(retjson["status"] == 0)

                pubs = []
                opts = {"output_format": "invalid"}
                retjson = self.__call_cmd("publisher", pubs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue(retjson["status"] == 2)

                pubs = []
                opts = {"output_format": ["invalid"]}
                retjson = self.__call_cmd("publisher", pubs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue(retjson["status"] == 2)

                pubs = []
                opts = {"output_format": None}
                retjson = self.__call_cmd("publisher", pubs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue(retjson["status"] == 2)

                pubs = []
                opts = {"inc_disabled": False}
                retjson = self.__call_cmd("publisher", pubs, opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(retjson["status"] == 0)

                pubs = []
                opts = {"inc_disabled": "False"}
                retjson = self.__call_cmd("publisher", pubs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue(retjson["status"] == 2)

                pubs = ["test1"]
                opts = {}
                retjson = self.__call_cmd("publisher", pubs, opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("publisher_details" in retjson["data"])
                self.assertTrue(len(retjson["data"]["publisher_details"]) == 1)

        def test_09_info_args_opts(self):
                global_settings.client_output_quiet = True
                self.rurl1 = self.dcs[1].get_repo_url()
                self.image_create(self.rurl1)
                os.environ["PKG_IMAGE"] = self.img_path()
                opts = {"repo_uri": self.rurl1}
                retjson = self.__call_cmd("set-publisher", [], opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(retjson["status"] == 0)

                self.pkg("install pkg://test1/foo@1.0")
                pkgs = ["foo"]
                opts = {"origins": [self.rurl1]}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)
                self.assertTrue("package_attrs" in retjson["data"])
                self.assertTrue(len(retjson["data"]["package_attrs"]) == 2)

                pkgs = []
                opts = {"origins": [self.rurl1]}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue(retjson["status"] == 2)

                pkgs = []
                opts = {"origins": [None]}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue(retjson["status"] == 2)

                pkgs = []
                opts = {"origins": None}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue(retjson["status"] == 2)

                opts = {"origins": "single"}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue(retjson["status"] == 2)

                pkgs = ["foo"]
                opts = {"origins": [self.rurl1], "quiet": "True"}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("data" not in retjson)
                self.assertTrue(retjson["status"] == 2)

                pkgs = ["foo"]
                opts = {"origins": [self.rurl1], "quiet": True}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue("data" not in retjson)
                self.assertTrue(retjson["status"] == 0)

                pkgs = []
                opts = {"origins": [self.rurl1], "quiet": True}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("data" not in retjson)
                self.assertTrue(retjson["status"] == 2)

                pkgs = ["foo"]
                opts = {}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue("errors" not in retjson)
                self.assertTrue(len(retjson["data"]["package_attrs"]) == 1)
                self.assertTrue(retjson["data"]["package_attrs"][0][2][1][0] \
                    == "Installed")
                self.assertTrue(retjson["status"] == 0)

                pkgs = []
                opts = {"origins": [self.rurl1], "quiet": True}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("data" not in retjson)
                self.assertTrue(retjson["status"] == 2)

                pkgs = []
                opts = {"info_local": True, "info_remote": True}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("data" not in retjson)
                self.assertTrue(retjson["status"] == 2)

                # Test with wrong value type.
                pkgs = []
                opts = {"info_local": "true"}
                retjson = self.__call_cmd("info", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("data" not in retjson)
                self.assertTrue(retjson["status"] == 2)

        def test_10_exact_install_json_args_opts(self):
                """Test json args or opts for exact-install command."""

                # Test invalid pkg name.
                self.image_create(self.rurl1, prefix="test1")
                os.environ["PKG_IMAGE"] = self.img_path()
                pkgs = [1, 2, 3]
                opts = {"backup_be": True}
                retjson = self.__call_cmd("exact-install", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'string'" in
                    retjson["errors"][0]["reason"])

                pkgs = [None]
                opts = {"backup_be": True}
                os.environ["PKG_IMAGE"] = self.img_path()
                retjson = self.__call_cmd("exact-install", pkgs, opts)
                self.assertTrue("errors" in retjson)
                self.assertTrue("is not of type 'string'" in
                    retjson["errors"][0]["reason"])

                # Test unknown option was reported.
                pkgs = ["newpkg@1.0"]
                opts = {"unknown": "solaris"}
                retjson = self.__call_cmd("exact-install", pkgs, opts)
                self.assertTrue("invalid option" in
                    retjson["errors"][0]["reason"])

                # Test without pkg specified.
                pkgs = []
                opts = {"verbose": 3}
                retjson = self.__call_cmd("exact-install", pkgs, opts)
                self.assertTrue("at least one package" in
                    retjson["errors"][0]["reason"])

                # Run through pkg install.
                pkgs = ["newpkg@1.0"]
                opts = {"parsable_version": 0}
                global_settings.client_output_quiet = True
                retjson = self.__call_cmd("exact-install", pkgs, opts)
                global_settings.client_output_quiet = False

                # Test input directly against schema.
                pargs = "pargs_json"
                einstall_schema = cli_api._get_pkg_input_schema("exact-install")
                einstall_input = {pargs : [], "opts_json": {}}
                self.assertTrue(self.__schema_validation(einstall_input,
                    einstall_schema))

                einstall_input = {pargs: [12], "opts_json": {}}
                self.assertTrue(not self.__schema_validation(einstall_input,
                    einstall_schema))

                einstall_input = { pargs: ["pkg"], "opts_json": {}}
                self.assertTrue(self.__schema_validation(einstall_input,
                    einstall_schema))

                einstall_input = {pargs : ["pkg"], "opts_json":
                    {"parsable_version": "string"}}
                self.assertTrue(not self.__schema_validation(einstall_input,
                    einstall_schema))

                einstall_input = {pargs: ["pkg"], "opts_json":
                    {"parsable_version": 3}}
                self.assertTrue(not self.__schema_validation(einstall_input,
                    einstall_schema))

                einstall_input = {pargs: ["pkg"], "opts_json":
                    {"parsable_version": None}}
                self.assertTrue(self.__schema_validation(einstall_input,
                    einstall_schema))

                einstall_input = {pargs: ["pkg"], "opts_json": {"reject_pats":
                    False}}
                self.assertTrue(not self.__schema_validation(einstall_input,
                    einstall_schema))

                einstall_input = {pargs: ["pkg"], "opts_json": {"reject_pats":
                    []}}
                self.assertTrue(self.__schema_validation(einstall_input,
                    einstall_schema))

                einstall_input = {pargs: ["pkg"], "opts_json": {"accept":
                    "str"}}
                self.assertTrue(not self.__schema_validation(einstall_input,
                    einstall_schema))

                einstall_input = {pargs: ["pkg"], "opts_json": {"accept":
                    False}}
                self.assertTrue(self.__schema_validation(einstall_input,
                    einstall_schema))

                einstall_input = {pargs: ["pkg"], "opts_json":
                    {"reject_pats": [None, None]}}
                self.assertTrue(not self.__schema_validation(einstall_input,
                    einstall_schema))

                einstall_input = {pargs: [None], "opts_json":
                    {"reject_pats": []}}
                self.assertTrue(not self.__schema_validation(einstall_input,
                    einstall_schema))

        def test_11_verify_json_args_opts(self):
                """Test json args or opts for verify command."""

                self.image_create(self.rurl1, prefix="test1")
                os.environ["PKG_IMAGE"] = self.img_path()
                pkgs = ["verifypkg@1.0"]
                opts = {"parsable_version": 0}
                global_settings.client_output_quiet = True
                retjson = self.__call_cmd("install", pkgs, opts)
                global_settings.client_output_quiet = False

                # Test invalid options.
                pkgs = ["verifypkg"]
                opts = {"omit_headers": True, "parsable_version": 0}
                retjson = self.__call_cmd("verify", pkgs, opts)
                self.assertTrue(retjson["status"] == 2)
                self.assertTrue("combined" in retjson["errors"][0]["reason"])

                pkgs = ["verifypkg"]
                opts = {"fake_opt": True}
                retjson = self.__call_cmd("verify", pkgs, opts)
                self.assertTrue(retjson["status"] == 2)
                self.assertTrue("invalid" in retjson["errors"][0]["reason"])

                pkgs = ["verifypkg"]
                opts = {"parsable_version": "wrongValueType"}
                retjson = self.__call_cmd("verify", pkgs, opts)
                self.assertTrue(retjson["status"] == 2)

                pkgs = ["verifypkg"]
                opts = {"parsable_version": 1}
                retjson = self.__call_cmd("verify", pkgs, opts)
                self.assertTrue(retjson["status"] == 2)

                pkgs = ["verifypkg"]
                opts = {"unpackaged_only": True}
                retjson = self.__call_cmd("verify", pkgs, opts)
                self.assertTrue(retjson["status"] == 2)

                pkgs = ["verifypkg"]
                opts = {"unpackaged": True}
                retjson = self.__call_cmd("verify", pkgs, opts)
                self.assertTrue(retjson["status"] == 0)

                # Run through verify.
                pkgs = ["verifypkg"]
                opts = {"parsable_version": 0}
                retjson = self.__call_cmd("verify", pkgs, opts)
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue(retjson["data"]["plan"]["item-messages"])
                reslist = retjson["data"]["plan"]["item-messages"]
                self.assertTrue(len(reslist) == 1 and
                    reslist['pkg://test1/verifypkg@1.0,5.11-0:20160302T054916Z']
                    ["messages"][0]["msg_level"] == "info")
                verify_outschema = cli_api._get_pkg_output_schema("verify")
                self.assertTrue(self.__schema_validation(retjson,
                    verify_outschema))

                pkgs = []
                opts = {"unpackaged": True, "parsable_version": 0}
                retjson = self.__call_cmd("verify", pkgs, opts)
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue(retjson["data"]["plan"]
                    ["item-messages"])
                reslist = retjson["data"]["plan"]["item-messages"]["unpackaged"]
                self.assertTrue(len(reslist) == 2 and list(reslist.values())[0][0]["msg_level"]
                    == "info")
                # Also check if the packaged content is still there.
                reslist = retjson["data"]["plan"]["item-messages"]
                self.assertTrue(len(reslist) == 2 and
                    reslist['pkg://test1/verifypkg@1.0,5.11-0:20160302T054916Z']
                    ["messages"][0]["msg_level"] == "info")
                self.assertTrue(self.__schema_validation(retjson,
                    verify_outschema))

                pkgs = []
                opts = {"unpackaged_only": True, "parsable_version": 0}
                retjson = self.__call_cmd("verify", pkgs, opts)
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue(retjson["data"]["plan"]
                    ["item-messages"])
                reslist = retjson["data"]["plan"]["item-messages"]["unpackaged"]
                self.assertTrue(len(reslist) == 2 and list(reslist.values())[0][0]["msg_level"]
                    == "info")
                # Also check if the packaged content is gone.
                reslist = retjson["data"]["plan"]["item-messages"]
                self.assertTrue(len(reslist) == 1 and
                    'pkg://test1/verifypkg@1.0,5.11-0:20160302T054916Z'
                    not in reslist)
                self.assertTrue(self.__schema_validation(retjson,
                    verify_outschema))

                # Test input directly against schema.
                pargs = "pargs_json"
                verify_schema = cli_api._get_pkg_input_schema("verify")
                verify_input = {pargs : [], "opts_json": {}}
                self.assertTrue(self.__schema_validation(verify_input,
                    verify_schema))

                verify_input = {pargs : [], "opts_json": {"unpackaged":
                    "wrongValueType"}}
                self.assertTrue(not self.__schema_validation(verify_input,
                    verify_schema))

        def test_12_fix_json_args_opts(self):
                """Test json args or opts for fix command."""

                self.image_create(self.rurl1, prefix="test1")
                os.environ["PKG_IMAGE"] = self.img_path()
                pkgs = ["verifypkg@1.0"]
                opts = {"parsable_version": 0}
                global_settings.client_output_quiet = True
                retjson = self.__call_cmd("install", pkgs, opts)
                global_settings.client_output_quiet = False

                # Test invalid options.
                pkgs = ["verifypkg"]
                opts = {"omit_headers": True, "parsable_version": 0}
                retjson = self.__call_cmd("fix", pkgs, opts)
                self.assertTrue(retjson["status"] == 2)
                self.assertTrue("combined" in retjson["errors"][0]["reason"])

                pkgs = ["verifypkg"]
                opts = {"fake_opt": True}
                retjson = self.__call_cmd("fix", pkgs, opts)
                self.assertTrue(retjson["status"] == 2)
                self.assertTrue("invalid" in retjson["errors"][0]["reason"])

                pkgs = ["verifypkg"]
                opts = {"parsable_version": "wrongValueType"}
                retjson = self.__call_cmd("fix", pkgs, opts)
                self.assertTrue(retjson["status"] == 2)

                opts = {"unpackaged": True}
                retjson = self.__call_cmd("fix", pkgs, opts)
                self.assertTrue(retjson["status"] == 4)

                pkgs = []
                opts = {"unpackaged": True}
                retjson = self.__call_cmd("fix", pkgs, opts)
                self.assertTrue(retjson["status"] == 4)

                pkgs = []
                opts = {"unpackaged_only": True}
                retjson = self.__call_cmd("fix", pkgs, opts)
                self.assertTrue(retjson["status"] == 2)

                # Run through fix.
                pkgs = ["verifypkg"]
                opts = {"parsable_version": 0}
                retjson = self.__call_cmd("fix", pkgs, opts)
                self.assertTrue(retjson["status"] == 4)
                self.assertTrue(retjson["data"]["plan"]["item-messages"])
                reslist = retjson["data"]["plan"]["item-messages"]
                self.assertTrue(len(reslist) == 1 and
                    reslist['pkg://test1/verifypkg@1.0,5.11-0:20160302T054916Z']
                    ["messages"][0]["msg_level"] == "info")
                fix_outschema = cli_api._get_pkg_output_schema("fix")
                self.assertTrue(self.__schema_validation(retjson,
                    fix_outschema))
                # Test input directly against schema.
                pargs = "pargs_json"
                fix_schema = cli_api._get_pkg_input_schema("fix")
                fix_input = {pargs : [], "opts_json": {}}
                self.assertTrue(self.__schema_validation(fix_input,
                    fix_schema))

                pargs = "pargs_json"
                fix_schema = cli_api._get_pkg_input_schema("fix")
                fix_input = {pargs : [], "opts_json": {"verbose": "WrongType"}}
                self.assertTrue(not self.__schema_validation(fix_input,
                    fix_schema))

        def test_13_ClientInterface(self):
                """Test the clientInterface class."""
                pt = progress.QuietProgressTracker()
                cli_inst = cli_api.ClientInterface(pkg_image=self.img_path(),
                    prog_tracker=pt, opts_mapping={"be_name": "boot_env"})
                opts = {"repo_uri": self.rurl1}
                retjson = cli_inst.publisher_set(json.dumps([]),
                    json.dumps(opts))
                epset_schema_in = cli_inst.get_pkg_input_schema(
                    "set-publisher")
                epset_schema_out = cli_inst.get_pkg_output_schema(
                    "set-publisher")
                epset_input = {"pargs_json": [], "opts_json": opts}
                self.assertTrue(self.__schema_validation(epset_input,
                    epset_schema_in))
                self.assertTrue(self.__schema_validation(retjson,
                    epset_schema_out))

                # Test uninstalling an not installed pkg.
                opts = {}
                args = ["no_install"]
                retjson = cli_inst.uninstall(json.dumps(args), json.dumps(opts))
                self.assertTrue(retjson["status"] == 1)
                self.assertTrue("errors" in retjson)
                eunins_schema_in = cli_inst.get_pkg_input_schema("uninstall")
                # Test input schema was replaced by an mapped option name.
                self.assertTrue("boot_env" in json.dumps(eunins_schema_in))
                eunins_schema_out = cli_inst.get_pkg_output_schema("uninstall")
                eunins_input = {"pargs_json": args, "opts_json": opts}
                self.assertTrue(self.__schema_validation(eunins_input,
                    eunins_schema_in))
                self.assertTrue(self.__schema_validation(retjson,
                    eunins_schema_out))

                # Test be related exception does not crash the system.
                opts = {"boot_env": "s12"}
                args = ["no_install"]
                retjson = cli_inst.uninstall(json.dumps(args),
                    json.dumps(opts))
                self.assertTrue(retjson["status"] == 1)
                self.assertTrue("errors" in retjson)
                self.assertTrue("boot_env" not in json.dumps(retjson))

                retjson = cli_inst.uninstall(json.dumps(["newpkg2"]),
                    json.dumps({}))
                self.assertTrue(retjson["status"] == 1)
                self.assertTrue("errors" in retjson)

                opts = {"parsable_version": 0}
                args = ["newpkg2@1.0"]
                retjson = cli_inst.install(json.dumps(args), json.dumps(opts))
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)
                eins_schema_in = cli_inst.get_pkg_input_schema("install")
                eins_schema_out = cli_inst.get_pkg_output_schema("install")
                eins_input = {"pargs_json": args, "opts_json": opts}
                self.assertTrue(self.__schema_validation(eins_input,
                    eins_schema_in))
                self.assertTrue(self.__schema_validation(retjson,
                    eins_schema_out))

                retjson = cli_inst.list_inventory()
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)
                self.assertTrue("newpkg2" in json.dumps(retjson))

                retjson = cli_inst.uninstall(json.dumps(args), json.dumps(opts))
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)

                retjson = cli_inst.publisher_set(json.dumps(["test1"]))
                self.assertTrue(retjson["status"] == 0)
                self.assertTrue("errors" not in retjson)
