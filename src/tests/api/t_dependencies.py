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

# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import pkg.catalog as catalog
import pkg.flavor.base as base
import pkg.flavor.depthlimitedmf as dlmf
import pkg.flavor.elf as elf
import pkg.flavor.hardlink as hl
import pkg.flavor.python as py
import pkg.flavor.script as scr
import pkg.flavor.smf_manifest as smf
import pkg.fmri as fmri
import pkg.portable as portable
import pkg.publish.dependencies as dependencies
import pkg.updatelog as updatelog

class TestDependencyAnalyzer(pkg5unittest.Pkg5TestCase):

        paths = {
            "authlog_path": "var/log/authlog",
            "curses_path": "usr/xpg4/lib/libcurses.so.1",
            "indexer_path":
                "usr/lib/python2.6/vendor-packages/pkg_test/client/indexer.py",
            "ksh_path": "usr/bin/ksh",
            "libc_path": "lib/libc.so.1",
            "pkg_path":
                "usr/lib/python2.6/vendor-packages/pkg_test/client/__init__.py",
            "script_path": "lib/svc/method/svc-pkg-depot",
            "syslog_path": "var/log/syslog"
        }

        smf_paths = {
            "broken":
                "var/svc/manifest/broken-service.xml",
            "delivered_many_nodeps":
                "var/svc/manifest/delivered-many-nodeps.xml",
            "foreign_many_nodeps":
                "var/svc/manifest/foreign-many-nodeps.xml",
            "foreign_single_nodeps":
                "var/svc/manifest/foreign-single-nodeps.xml",
            "service_many": "var/svc/manifest/service-many.xml",
            "service_single": "var/svc/manifest/service-single.xml",
            "service_unknown": "var/svc/manifest/service-single-unknown.xml"
        }

        paths.update(smf_paths)

        ext_hardlink_manf = """ \
hardlink path=usr/foo target=../%(syslog_path)s
hardlink path=usr/bar target=../%(syslog_path)s
hardlink path=baz target=%(authlog_path)s
""" % paths

        int_hardlink_manf = """ \
hardlink path=usr/foo target=../%(syslog_path)s
file NOHASH group=sys mode=0644 owner=root path=%(syslog_path)s 
""" % paths

        int_hardlink_manf_test_symlink = """ \
hardlink path=usr/foo target=../%(syslog_path)s
file NOHASH group=sys mode=0644 owner=root path=bar/syslog 
""" % paths

        ext_script_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(script_path)s
""" % paths

        int_script_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(script_path)s
file NOHASH group=bin mode=0755 owner=root path=%(ksh_path)s
""" % paths

        ext_elf_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(curses_path)s
""" % paths

        int_elf_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(libc_path)s
file NOHASH group=bin mode=0755 owner=root path=%(curses_path)s
""" % paths

        ext_python_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(indexer_path)s
""" % paths

        ext_python_pkg_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(pkg_path)s
""" % paths

        variant_manf_1 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path=%(script_path)s
file NOHASH group=bin mode=0755 owner=root path=%(ksh_path)s variant.arch=foo
""" % paths

        variant_manf_2 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path=%(script_path)s variant.arch=foo
file NOHASH group=bin mode=0755 owner=root path=%(ksh_path)s variant.arch=foo
""" % paths

        variant_manf_3 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path=%(script_path)s variant.arch=bar
file NOHASH group=bin mode=0755 owner=root path=%(ksh_path)s variant.arch=foo
""" % paths

        variant_manf_4 = """ \
set name=variant.arch value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
file NOHASH group=bin mode=0755 owner=root path=%(script_path)s variant.opensolaris.zone=global
file NOHASH group=bin mode=0755 owner=root path=%(ksh_path)s variant.opensolaris.zone=global
""" % paths

        python_abs_text = """\
#!/usr/bin/python

from __future__ import absolute_import

import os
import sys
import pkg_test.indexer_test.foobar as indexer
import pkg.search_storage as ss
from ..misc_test import EmptyI
"""

        python_text = """\
#!/usr/bin/python

import os
import sys
import pkg_test.indexer_test.foobar as indexer
import pkg.search_storage as ss
from pkg_test.misc_test import EmptyI
"""

        smf_fmris = {}
        smf_known_deps = {}

        smf_fmris["service_single"] = [ \
            "svc:/application/pkg5test/service-default",
            "svc:/application/pkg5test/service-default:default" ]

        smf_known_deps["svc:/application/pkg5test/service-default"] = \
            ["svc:/application/pkg5test/delivered-many"]
        smf_known_deps["svc:/application/pkg5test/service-default:default"] = \
            ["svc:/application/pkg5test/delivered-many"]

        smf_manifest_text = {}
        smf_manifest_text["service_single"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='service-default'>

<!-- we deliver:
  svc:/application/pkg5test/service-default
      (deps: svc:/application/pkg5test/delivered-many)
  svc:/application/pkg5test/service-default:default
-->
<service
	name='application/pkg5test/service-default'
	type='service'
	version='0.1'>

	<dependency
		name="delivered-service"
		grouping="require_all"
		restart_on="none"
		type="service">
		<service_fmri value="svc:/application/pkg5test/delivered-many" />
	</dependency>

        <!-- We should not pick this up as an IPS dependency -->
        <dependency
                name="my-path"
                grouping="require_all"
                restart_on="none"
                type="path">
                <service_fmri value="/var/foo/something.conf" />
        </dependency>

	<create_default_instance enabled='true' />
	<single_instance/>
	<exec_method
		type='method'
		name='start'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

	<exec_method
		type='method'
		name='stop'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>
</service>
</service_bundle>
"""

        smf_fmris["service_many"] = [ \
            "svc:/application/pkg5test/service-many",
            "svc:/application/pkg5test/service-many:default",
            "svc:/application/pkg5test/service-many:one",
            "svc:/application/pkg5test/service-many:two" ]

        smf_known_deps["svc:/application/pkg5test/service-many"] = \
            ["svc:/application/pkg5test/foreign-many"]
        smf_known_deps["svc:/application/pkg5test/service-many:default"] = \
            ["svc:/application/pkg5test/foreign-many"]
        smf_known_deps["svc:/application/pkg5test/service-many:one"] = \
            ["svc:/application/pkg5test/foreign-many",
            "svc:/application/pkg5test/foreign-many:default"]
        smf_known_deps["svc:/application/pkg5test/service-many:two"] = \
            ["svc:/application/pkg5test/foreign-many"]

        smf_manifest_text["service_many"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='pkg5test-many-instances'>

<!-- we deliver:
  svc:/application/pkg5test/service-many
     (deps: svc:/application/pkg5test/foreign-many
            svc:/application/pkg5test/foreign-opt (not required))

  svc:/application/pkg5test/service-many:default
  svc:/application/pkg5test/service-many:one
     (deps: svc:/application/pkg5test/foreign-opt:default (not required)
            svc:/application/pkg5test/foreign-many:default)
  svc:/application/pkg5test/service-many:two
-->
<service
	name='application/pkg5test/service-many'
	type='service'
	version='0.1'>

	<!-- a dependency a different package delivers -->
	<dependency
		name="foreign-service"
		grouping="require_all"
		restart_on="none"
		type="service">
		<service_fmri value="svc:/application/pkg5test/foreign-many" />
	</dependency>

	<!-- pkg(5) shouldn't see this as a dependency -->
        <dependency
                name="optional-service"
                grouping="optional_all"
                restart_on="none"
                type="service">
                <service_fmri value="svc:/application/pkg5test/foreign-opt" />
        </dependency>

        <create_default_instance enabled='true' />

        <exec_method
                type='method'
                name='start'
                exec=':true'
                timeout_seconds='0'>
        </exec_method>

        <exec_method
                type='method'
                name='stop'
                exec=':true'
                timeout_seconds='0'>
        </exec_method>


	<instance name='one' enabled='false' >

            <dependency
                name="optional-service"
                grouping="require_all"
                restart_on="none"
                type="service">
                <service_fmri value="svc:/application/pkg5test/foreign-many:default" />
            </dependency>
	</instance>

	<!-- no dependencies here -->
	<instance name='two' enabled='false' />

</service>
</service_bundle>
"""

        smf_fmris["service_unknown"] = [ \
            "svc:/application/pkg5test/service-unknown",
            "svc:/application/pkg5test/service-unknown:default",
            "svc:/application/pkg5test/service-unknown:one"]


        smf_known_deps["svc:/application/pkg5test/service-unknown"] = \
            ["svc:/application/pkg5test/delivered-many",
            "svc:/application/pkg5test/unknown-service"]
        smf_known_deps["svc:/application/pkg5test/service-unknown:default"] = \
            ["svc:/application/pkg5test/delivered-many",
            "svc:/application/pkg5test/unknown-service"]
        smf_known_deps["svc:/application/pkg5test/service-unknown:one"] = \
            ["svc:/application/pkg5test/delivered-many",
            "svc:/application/pkg5test/unknown-service",
            "svc:/application/pkg5test/another-unknown:default"]

        smf_manifest_text["service_unknown"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='service-unknown'>

<!-- we deliver:
  svc:/application/pkg5test/service-unknown
      (deps: svc:/application/pkg5test/delivered-many
             svc:/application/pkg5test/unknown-service
  svc:/application/pkg5test/service-unknown:default
      (deps: svc:/application/pkg5test/delivered-many
             svc:/application/pkg5test/unknown-service)
  svc:/application/pkg5test/service-unknown:one
      (deps: svc:/application/pkg5test/delivered-many
             svc:/application/pkg5test/unknown-service
             svc:/application/pkg5test/another-unknown:default)
-->
<service
	name='application/pkg5test/service-unknown'
	type='service'
	version='0.1'>

	<dependency
		name="delivered-service"
		grouping="require_all"
		restart_on="none"
		type="service">
		<service_fmri value="svc:/application/pkg5test/delivered-many" />
	</dependency>


        <!-- pkg(5) should throw an error here, as we don't deliver this
             service, nor does any other package in our test suite -->
        <dependency
                name="unknown-service"
                grouping="require_all"
                restart_on="none"
                type="service">
                <service_fmri value="svc:/application/pkg5test/unknown-service" />
        </dependency>

	<create_default_instance enabled='true' />

	<exec_method
		type='method'
		name='start'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

	<exec_method
		type='method'
		name='stop'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

        <instance name='one' enabled='false' >

    	    <!-- pkg(5) should throw an error being unable to resolve this -->
            <dependency
                name="another"
                grouping="require_all"
                restart_on="none"
                type="service">
                <service_fmri value="svc:/application/pkg5test/another-unknown:default" />
            </dependency>
	</instance>
</service>
</service_bundle>
"""

        smf_fmris["delivered_many_nodeps"] = [ \
            "svc:/application/pkg5test/delivered-many",
            "svc:/application/pkg5test/delivered-many:nodeps",
            "svc:/application/pkg5test/delivered-many:nodeps1" ]

        smf_known_deps["svc:/application/pkg5test/delivered-many"] = []
        smf_known_deps["svc:/application/pkg5test/delivered-many:nodeps"] = []
        smf_known_deps["svc:/application/pkg5test/delivered-many:nodeps1"] = []

        smf_manifest_text["delivered_many_nodeps"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='default-service-many'>
<!-- we deliver

svc:/application/pkg5test/delivered-many
svc:/application/pkg5test/delivered-many:nodeps
svc:/application/pkg5test/delivered-many:nodeps1

None of these services or instances declare any dependencies.

-->
<service
	name='application/pkg5test/delivered-many'
	type='service'
	version='0.1'>

	<single_instance />

	<exec_method
		type='method'
		name='start'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

	<exec_method
		type='method'
		name='stop'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

	<instance name="nodeps" enabled="true" />
	<instance name='nodeps1' enabled='false' />
</service>
</service_bundle>
"""

        smf_fmris["foreign_single_nodeps"] = [ \
            "svc:/application/pkg5test/foreign-single",
            "svc:/application/pkg5test/foreign-single:nodeps" ]

        smf_known_deps["svc:/application/pkg5test/foreign-single"] = []
        smf_known_deps["svc:/application/pkg5test/foreign-single:nodeps"] = []

        smf_manifest_text["foreign_single_nodeps"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='SUNWcsr:cron'>

<!-- we deliver

svc:/application/pkg5test/foreign-single
svc:/application/pkg5test/foreign-single:nodeps

None of these services or instances declare any dependencies.

-->
<service
	name='application/pkg5test/foreign-single'
	type='service'
	version='0.1'>

	<exec_method
		type='method'
		name='start'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

	<exec_method
		type='method'
		name='stop'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

	<instance name='nodeps' enabled='false' />
</service>
</service_bundle>
"""

        smf_fmris["foreign_many_nodeps"] = [ \
            "svc:/application/pkg5test/foreign-many",
            "svc:/application/pkg5test/foreign-many:default",
            "svc:/application/pkg5test/foreign-many:nodeps",
            "svc:/application/pkg5test/foreign-opt",
            "svc:/application/pkg5test/foreign-opt:nodeps" ]

        smf_known_deps["svc:/application/pkg5test/foreign-many"] = []
        smf_known_deps["svc:/application/pkg5test/foreign-many:default"] = []
        smf_known_deps["svc:/application/pkg5test/foreign-many:nodeps"] = []
        smf_known_deps["svc:/application/pkg5test/foreign-opt"] = []
        smf_known_deps["svc:/application/pkg5test/foreign-opt:nodeps"] = []

        smf_manifest_text["foreign_many_nodeps"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='foreign-many-instances'>

<!-- we deliver

svc:/application/pkg5test/foreign-many
svc:/application/pkg5test/foreign-many:default
svc:/application/pkg5test/foreign-many:nodeps
svc:/application/pkg5test/foreign-opt
svc:/application/pkg5test/foreign-opt:nodeps

Note that this manifest contains two <service> elements.

None of these services or instances declare any dependencies.

-->

<service
	name='application/pkg5test/foreign-many'
	type='service'
	version='0.1'>

	<exec_method
		type='method'
		name='start'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

	<exec_method
		type='method'
		name='stop'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

	<!-- intentionally declaring the default service, as opposed to using
             create_default_service - to test smf manifest parsing code in pkg5 -->
	<instance name='default' enabled='false' />
	<instance name='nodeps' enabled='false' />
</service>

<service
	name='application/pkg5test/foreign-opt'
	type='service'
	version='0.1'>

	<single_instance />

	<exec_method
		type='method'
		name='start'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

	<exec_method
		type='method'
		name='stop'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

	<instance name='nodeps' enabled='false' />
</service>
</service_bundle>
"""

        smf_manifest_text["broken"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='broken-service'>

<!-- we deliver nothing - this service manifest is intentionally broken
-->
<service <<>  This is the broken line

	name='application/pkg5test/brokenservice'
	type='service'
	version='0.1'>

	<single_instance />

		<exec_method
		type='method'
		name='start'
		exec=':true'
		timeout_seconds='60'>
		<method_context>
			<method_credential user='root' group='root' />
		</method_context>
	</exec_method>

	<instance name='default' enabled='false' />
</service>
</service_bundle>
"""
        int_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path=%(service_single)s
file NOHASH group=sys mode=0644 owner=root path=%(delivered_many_nodeps)s
""" % paths

        ext_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path=%(service_many)s
file NOHASH group=sys mode=0644 owner=root path=%(foreign_single_nodeps)s
""" % paths

        broken_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path=%(broken)s
file NOHASH group=sys mode=0644 owner=root path=%(delivered_many_nodeps)s
file NOHASH group=sys mode=0644 owner=root path=%(service_single)s
""" % paths

        faildeps_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path=%(delivered_many_nodeps)s
file NOHASH group=sys mode=0644 owner=root path=%(service_single)s
file NOHASH group=sys mode=0644 owner=root path=%(service_unknown)s
""" % paths

        script_text = "#!/usr/bin/ksh -p\n"

        def setUp(self):
                pkg5unittest.Pkg5TestCase.setUp(self)

                self.proto_dir = os.path.join(self.test_root, "proto")
                os.makedirs(self.proto_dir)

        def make_proto_text_file(self, path, contents=""):
                self.make_misc_files({ path: contents }, prefix="proto")

        def make_python_test_files(self, py_version):
                pdir = "usr/lib/python%s/vendor-packages" % py_version
                self.make_proto_text_file("%s/pkg_test/__init__.py" % pdir,
                    "#!/usr/bin/python\n")
                self.make_proto_text_file(
                    "%s/pkg_test/indexer_test/__init__.py" % pdir,
                    "#!/usr/bin/python")
                
	def make_smf_test_files(self):
                for manifest in self.smf_paths.keys():
                        self.make_proto_text_file(self.paths[manifest],
                            self.smf_manifest_text[manifest])

        def make_elf(self, final_path, static=False):
                out_file = os.path.join(self.proto_dir, final_path)

                opts = []
                # In some cases we want to generate an elf binary with no
                # dependencies of its own.  We use -c (supress linking) for
                # this purpose.
                if static:
                        opts.extend(["-c"])
                self.c_compile("int main(){}\n", opts, out_file)

                return out_file[len(self.proto_dir)+1:]

        def __path_to_key(self, path):
                if path == self.paths["libc_path"]:
                        return ((os.path.basename(path),), tuple([
                            p.lstrip("/") for p in elf.default_run_paths
                        ]))
                return ((os.path.basename(path),), (os.path.dirname(path),))

        def test_ext_hardlink(self):
                """Check that a hardlink with a target outside the package is
                reported as a dependency."""

                def _check_results(res):
                        ds, es, ms, pkg_attrs = res
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))
                        self.assertEqual(ms, {})
                        self.assert_(len(ds) == 3)
                        ans = set(["usr/foo", "usr/bar"])
                        for d in ds:
                                self.assert_(d.dep_vars.is_satisfied())
                                self.assert_(d.is_error())
                                if d.dep_key() == self.__path_to_key(
                                    self.paths["syslog_path"]):
                                        self.assert_(
                                            d.action.attrs["path"] in ans)
                                        ans.remove(d.action.attrs["path"])
                                else:
                                        self.assertEqual(d.dep_key(),
                                            self.__path_to_key(
                                                self.paths["authlog_path"]))
                                        self.assertEqual(
                                            d.action.attrs["path"], "baz")
                t_path = self.make_manifest(self.ext_hardlink_manf)
                _check_results(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, []))
                _check_results(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [],
                    remove_internal_deps=False))

        def test_int_hardlink(self):
                """Check that a hardlink with a target inside the package is
                not reported as a dependency, unless the flag to show internal
                dependencies is set."""

                t_path = self.make_manifest(self.int_hardlink_manf)
                self.make_proto_text_file(self.paths["syslog_path"])
                ds, es, ms, pkg_attrs = \
                    dependencies.list_implicit_deps(t_path, [self.proto_dir],
                        {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assert_(len(ms) == 1)
                self.assert_(len(ds) == 0)

                # Check that internal dependencies are as expected.
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False)
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(len(ms), 1)
                self.assertEqual(len(ds), 1)
                d = ds[0]
                self.assert_(d.dep_vars.is_satisfied())
                self.assert_(d.is_error())
                self.assertEqual(d.dep_key(), self.__path_to_key(
                    self.paths["syslog_path"]))
                self.assertEqual(d.action.attrs["path"], "usr/foo")

        def test_ext_script(self):
                """Check that a file that starts with #! and references a file
                outside its package is reported as a dependency."""
                
                def _check_res(res):
                        ds, es, ms, pkg_attrs = res
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))
                        self.assertEqual(ms, {})
                        self.assert_(len(ds) == 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assert_(d.dep_vars.is_satisfied())
                        self.assertEqual(d.dep_key(),
                            self.__path_to_key(self.paths["ksh_path"]))
                        self.assertEqual(d.action.attrs["path"],
                            self.paths["script_path"])
                t_path = self.make_manifest(self.ext_script_manf)
                self.make_proto_text_file(self.paths["script_path"],
                    self.script_text)
                _check_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, []))
                _check_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False))

        def test_int_script(self):
                """Check that a file that starts with #! and references a file
                inside its package is not reported as a dependency unless
                the flag to show internal dependencies is set."""

                t_path = self.make_manifest(self.int_script_manf)
                self.make_elf(self.paths["ksh_path"])
                self.make_proto_text_file(self.paths["script_path"],
                    self.script_text)
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(ds) == 1)
                d = ds[0]
                self.assert_(d.is_error())
                self.assert_(d.dep_vars.is_satisfied())
                self.assertEqual(d.base_names[0], "libc.so.1")
                self.assertEqual(set(d.run_paths), set(["lib",
                    "usr/lib"]))

                # Check that internal dependencies are as expected.
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False)
                self.assertEqual(len(ds), 2)
                for d in ds:
                        self.assert_(d.is_error())
                        self.assert_(d.dep_vars.is_satisfied())
                        if d.dep_key() == self.__path_to_key(
                            self.paths["ksh_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["script_path"])
                        elif d.dep_key() == self.__path_to_key(
                            self.paths["libc_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["ksh_path"])
                        else:
                                raise RuntimeError("Unexpected "
                                    "dependency path:%s" % d)
                                
        def test_ext_elf(self):
                """Check that an elf file that requires a library outside its
                package is reported as a dependency."""

                def _check_res(res):
                        ds, es, ms, pkg_attrs = res
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))
                        self.assertEqual(ms, {})
                        self.assert_(len(ds) == 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assert_(d.dep_vars.is_satisfied())
                        self.assertEqual(d.base_names[0], "libc.so.1")
                        self.assertEqual(set(d.run_paths),
                            set(["lib", "usr/lib"]))
                        self.assertEqual(d.dep_key(),
                            self.__path_to_key(self.paths["libc_path"]))
                        self.assertEqual(
                                d.action.attrs["path"],
                                self.paths["curses_path"])

                t_path = self.make_manifest(self.ext_elf_manf)
                self.make_elf(self.paths["curses_path"])
                _check_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, []))
                _check_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False))

        def test_int_elf(self):
                """Check that an elf file that requires a library inside its
                package is not reported as a dependency unless the flag to show
                internal dependencies is set."""

                def _check_all_res(res):
                        ds, es, ms, pkg_attrs = res
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))
                        self.assertEqual(ms, {})
                        self.assertEqual(len(ds), 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assert_(d.dep_vars.is_satisfied())
                        self.assertEqual(d.base_names[0], "libc.so.1")
                        self.assertEqual(set(d.run_paths),
                            set(["lib", "usr/lib"]))
                        self.assertEqual(d.dep_key(),
                            self.__path_to_key(self.paths["libc_path"]))
                        self.assertEqual(d.action.attrs["path"],
                            self.paths["curses_path"])

                t_path = self.make_manifest(self.int_elf_manf)
                self.make_elf(self.paths["curses_path"])
                self.make_elf(self.paths["libc_path"], static=True)
                d_map, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(d_map) == 0)

                # Check that internal dependencies are as expected.
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False))

        def test_ext_python_dep(self):
                """Check that a python file that imports a module outside its
                package is reported as a dependency."""

                def _check_all_res(res):
                        ds, es, ms, pkg_attrs = res
                        mod_suffs = ["/__init__.py", ".py", ".pyc", ".pyo"]
                        mod_names = ["foobar", "misc_test", "os",
                            "search_storage"]
                        pkg_names = ["indexer_test", "pkg", "pkg_test"]
                        expected_deps = set([("python",)] +
                            [tuple(sorted([
                                "%s%s" % (n,s) for s in mod_suffs
                            ]))
                            for n in mod_names] +
                            [("%s/__init__.py" % n,) for n in pkg_names])
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))

                        self.assertEqual(ms, {})
                        for d in ds:
                                self.assert_(d.is_error())
                                if d.dep_vars is None:
                                        raise RuntimeError("This dep had "
                                            "depvars of None:%s" % d)
                                self.assert_(d.dep_vars.is_satisfied())
                                if not d.dep_key()[0] in expected_deps:
                                        raise RuntimeError("Got this "
                                            "unexpected dep:%s\n\nd:%s" %
                                            (d.dep_key()[0], d))
                                expected_deps.remove(d.dep_key()[0])
                                self.assertEqual(d.action.attrs["path"],
                                        self.paths["indexer_path"])
                        if expected_deps:
                                raise RuntimeError("Couldn't find these "
                                    "dependencies:\n" + "\n".join(
                                    [str(s) for s in sorted(expected_deps)]))
                self.__debug = True
                t_path = self.make_manifest(self.ext_python_manf)
                self.make_python_test_files(2.6)
                self.make_proto_text_file(self.paths["indexer_path"],
                    self.python_text)
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, []))
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False))

        def test_ext_python_abs_import_dep(self):
                """Check that a python file that uses absolute imports a module
                is handled correctly."""

                def _check_all_res(res):
                        ds, es, ms, pkg_attrs = res
                        mod_suffs = ["/__init__.py", ".py", ".pyc", ".pyo"]
                        mod_names = ["foobar", "os", "search_storage"]
                        pkg_names = ["indexer_test", "pkg", "pkg_test"]
                        expected_deps = set([("python",)] +
                            [tuple(sorted([
                                "%s%s" % (n,s) for s in mod_suffs
                            ]))
                            for n in mod_names] +
                            [("%s/__init__.py" % n,) for n in pkg_names])
                        if len(es) != 1:
                                raise RuntimeError("Expected exactly 1 error, "
                                    "got:%\n" + "\n".join([str(s) for s in es]))
                        if es[0].name != "misc_test":
                                raise RuntimeError("Didn't get the expected "
                                    "error. Error found was:%s" % es[0])

                        self.assertEqual(ms, {})
                        for d in ds:
                                self.assert_(d.is_error())
                                if d.dep_vars is None:
                                        raise RuntimeError("This dep had "
                                            "depvars of None:%s" % d)
                                self.assert_(d.dep_vars.is_satisfied())
                                if not d.dep_key()[0] in expected_deps:
                                        raise RuntimeError("Got this "
                                            "unexpected dep:%s\n\nd:%s" %
                                            (d.dep_key()[0], d))
                                expected_deps.remove(d.dep_key()[0])
                                self.assertEqual(d.action.attrs["path"],
                                        self.paths["indexer_path"])
                        if expected_deps:
                                raise RuntimeError("Couldn't find these "
                                    "dependencies:\n" + "\n".join(
                                    [str(s) for s in sorted(expected_deps)]))
                self.__debug = True
                t_path = self.make_manifest(self.ext_python_manf)
                self.make_python_test_files(2.6)
                # Check that absolute imports still work.
                self.make_proto_text_file(self.paths["indexer_path"],
                    self.python_abs_text)
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, []))
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False))

        def test_ext_python_pkg_dep(self):
                """Check that a python file that is the __init__.py file for a
                package is handled correctly."""

                def _check_all_res(res):
                        ds, es, ms, pkg_attrs = res
                        mod_suffs = ["/__init__.py", ".py", ".pyc", ".pyo"]
                        mod_names = ["foobar", "misc_test", "os",
                            "search_storage"]
                        pkg_names = ["indexer_test", "pkg", "pkg_test"]
                        expected_deps = set([("python",)] +
                            [tuple(sorted([
                                "%s%s" % (n,s) for s in mod_suffs
                            ]))
                            for n in mod_names] +
                            [("%s/__init__.py" % n,) for n in pkg_names])
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))

                        self.assertEqual(ms, {})
                        for d in ds:
                                self.assert_(d.is_error())
                                if d.dep_vars is None:
                                        raise RuntimeError("This dep had "
                                            "depvars of None:%s" % d)
                                self.assert_(d.dep_vars.is_satisfied())
                                if not d.dep_key()[0] in expected_deps:
                                        raise RuntimeError("Got this "
                                            "unexpected dep:%s\n\nd:%s" %
                                            (d.dep_key()[0], d))
                                expected_deps.remove(d.dep_key()[0])
                                self.assertEqual(d.action.attrs["path"],
                                        self.paths["pkg_path"])
                        if expected_deps:
                                raise RuntimeError("Couldn't find these "
                                    "dependencies:\n" + "\n".join(
                                    [str(s) for s in sorted(expected_deps)]))
                self.__debug = True
                t_path = self.make_manifest(self.ext_python_pkg_manf)
                self.make_python_test_files(2.6)
                self.make_proto_text_file(self.paths["pkg_path"],
                    self.python_text)
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, []))
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False))

        def test_variants_1(self):
                """Test that a file which satisfies a dependency only under a
                certain set of variants results in the dependency being reported
                for the other set of variants."""

                t_path = self.make_manifest(self.variant_manf_1)
                self.make_proto_text_file(self.paths["script_path"],
                    self.script_text)
                self.make_elf(self.paths["ksh_path"])
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(ds) == 2)
                for d in ds:
                        self.assert_(d.is_error())
                        if d.dep_key() == self.__path_to_key(
                            self.paths["ksh_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["script_path"])
                                self.assertEqual(len(d.dep_vars), 1)
                                self.assert_("variant.arch" in d.dep_vars)
                                expected_vars = set([("bar",), ("baz",)])
                                for v in d.dep_vars.not_sat_set:
                                        if v not in expected_vars:
                                                raise RuntimeError("Variant %s "
                                                    "was not in %s" %
                                                     (v, expected_vars))
                                        expected_vars.remove(v)
                                self.assertEqual(expected_vars, set())
                        elif d.dep_key() == self.__path_to_key(
                            self.paths["libc_path"]):
                                self.assertEqual(
                                    d.action.attrs["path"],
                                    self.paths["ksh_path"])
                                self.assertEqual(
                                    set(d.dep_vars["variant.arch"]),
                                    set(["foo"]))
                        else:
                                raise RuntimeError("Unexpected "
                                    "dependency path:%s" % (d.dep_key(),))

        def test_variants_2(self):
                """Test that when the variants of the action with the dependency
                and the action satisfying the dependency share the same
                dependency, an external dependency is not reported."""

                t_path = self.make_manifest(self.variant_manf_2)
                self.make_proto_text_file(self.paths["script_path"], self.script_text)
                self.make_elf(self.paths["ksh_path"])
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(ds) == 1)
                d = ds[0]
                self.assert_(d.is_error())
                self.assertEqual(set(d.dep_vars.keys()), set(["variant.arch"]))
                self.assertEqual(set(d.dep_vars["variant.arch"]), set(["foo"]))
                self.assertEqual(d.base_names[0], "libc.so.1")
                self.assertEqual(set(d.run_paths), set(["lib", "usr/lib"]))

                # Check that internal dependencies are as expected.
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False)
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(ds) == 2)
                for d in ds:
                        self.assert_(d.is_error())
                        self.assertEqual(set(d.dep_vars.keys()),
                           set(["variant.arch"]))
                        self.assertEqual(set(d.dep_vars["variant.arch"]),
                            set(["foo"]))
                        if d.dep_key() == self.__path_to_key(
                            self.paths["ksh_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["script_path"])
                        elif d.dep_key() == self.__path_to_key(
                            self.paths["libc_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["ksh_path"])
                        else:
                                raise RuntimeError(
                                    "Unexpected dependency path:%s" %
                                    (d.dep_key(),))

        def test_variants_3(self):
                """Test that when the action with the dependency is tagged with
                a different variant than the action which could satisfy it, it's
                reported as an external dependency."""

                t_path = self.make_manifest(self.variant_manf_3)
                self.make_proto_text_file(self.paths["script_path"],
                    self.script_text)
                self.make_elf(self.paths["ksh_path"])
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(ds) == 2)
                for d in ds:
                        self.assert_(d.is_error())
                        if d.dep_key() == self.__path_to_key(
                            self.paths["ksh_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["script_path"])
                                self.assertEqual(set(d.dep_vars.keys()),
                                    set(["variant.arch"]))
                                self.assertEqual(
                                    set(d.dep_vars["variant.arch"]),
                                    set(["bar"]))
                        elif d.dep_key() == self.__path_to_key(
                            self.paths["libc_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["ksh_path"])
                                self.assertEqual(set(d.dep_vars.keys()),
                                    set(["variant.arch"]))
                                self.assertEqual(
                                    set(d.dep_vars["variant.arch"]),
                                    set(["foo"]))
                        else:
                                raise RuntimeError("Unexpected "
                                    "dependency path:%s" % (d.dep_key(),))

        def test_variants_4(self):
                """Test that an action with a variant that depends on a delivered action
                also tagged with that variant, but not with a package-level variant is
                reported as an internal dependency, not an external one."""

                t_path = self.make_manifest(self.variant_manf_4)
                self.make_proto_text_file(self.paths["script_path"], self.script_text)
                self.make_elf(self.paths["ksh_path"])

                # Check that we only report a single external dependency
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(ds) == 1)
                d = ds[0]

                self.assert_(d.is_error())
                self.assertEqual(set(d.dep_vars.keys()), set(["variant.arch",
                    "variant.opensolaris.zone"]))
                self.assertEqual(set(d.dep_vars["variant.arch"]), set(["foo"]))
                self.assertEqual(set(d.dep_vars["variant.opensolaris.zone"]),
                    set(["global"]))

                self.assertEqual(d.base_names[0], "libc.so.1")
                self.assertEqual(set(d.run_paths), set(["lib", "usr/lib"]))

                # Check that internal dependencies are as expected.
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False)
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assertEqual(pkg_attrs, {})
                self.assert_(len(ds) == 2)
                for d in ds:
                        self.assert_(d.is_error())
                        self.assertEqual(set(d.dep_vars.keys()),
                            set(["variant.opensolaris.zone"]))
                        self.assertEqual(set(d.dep_vars["variant.opensolaris.zone"]),
                            set(["global"]))

                        if d.dep_key() == self.__path_to_key(
                            self.paths["ksh_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["script_path"])
                        elif d.dep_key() == self.__path_to_key(
                            self.paths["libc_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["ksh_path"])
                        else:
                                raise RuntimeError(
                                    "Unexpected dependency path:%s" % (d.dep_key(),))

        def test_symlinks(self):
                """Test that a file is recognized as delivered when a symlink
                is involved."""

                usr_path = os.path.join(self.proto_dir, "usr")
                hardlink_path = os.path.join(usr_path, "foo")
                bar_path = os.path.join(self.proto_dir, "bar")
                file_path = os.path.join(bar_path, "syslog")
                var_path = os.path.join(self.proto_dir, "var")
                symlink_loc = os.path.join(var_path, "log")
                hardlink_target = os.path.join(usr_path,
                    "../var/log/syslog")
                os.mkdir(usr_path)
                os.mkdir(bar_path)
                os.mkdir(var_path)
                fh = open(file_path, "w")
                fh.close()
                os.symlink(bar_path, symlink_loc)
                os.link(hardlink_target, hardlink_path)

                t_path = self.make_manifest(
                    self.int_hardlink_manf_test_symlink)
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [])

        def test_str_methods(self):
                """Test the str methods of objects in the flavor space."""

                str(base.MissingFile("fp"))
                str(elf.BadElfFile("fp", "ex"))
                str(elf.UnsupportedDynamicToken("/proto_path", "/install",
                    "run_path", "tok"))
                str(py.PythonModuleMissingPath("foo", "bar"))
                str(py.PythonMismatchedVersion("2.4", "2.6", "foo", "bar"))
                str(py.PythonSubprocessError(2, "foo", "bar"))
                str(py.PythonSubprocessBadLine("cmd", ["l1", "l2"]))
                mi = dlmf.ModuleInfo("name", ["/d1", "/d2"])
                str(mi)
                mi.make_package()
                str(mi)

        def test_multi_proto_dirs(self):
                """Check that analysis works correctly when multiple proto_dirs
                are given."""

                def _check_all_res(res):
                        ds, es, ms = res
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))
                        self.assertEqual(ms, {})
                        self.assertEqual(len(ds), 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assert_(d.dep_vars.is_satisfied())
                        self.assertEqual(d.base_names[0], "libc.so.1")
                        self.assertEqual(set(d.run_paths),
                            set(["lib", "usr/lib"]))
                        self.assertEqual(d.dep_key(),
                            self.__path_to_key(self.paths["libc_path"]))
                        self.assertEqual(d.action.attrs["path"],
                            self.paths["curses_path"])

                t_path = self.make_manifest(self.int_elf_manf)
                self.make_elf(os.path.join("foo", self.paths["curses_path"]))
                self.make_elf(self.paths["libc_path"], static=True)

                # This should fail because the "foo" directory is not given
                # as a proto_dir.
                d_map, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [])
                if len(es) != 1:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                if es[0].file_path != \
                    os.path.join(self.proto_dir, self.paths["curses_path"]):
                        raise RuntimeError("Wrong file was found missing:\n%s" %
                            es[0])
                self.assertEqual(ms, {})
                self.assert_(len(d_map) == 0)

                # This should work since the "foo" directory has been added to
                # the list of proto_dirs to use.
                d_map, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir, os.path.join(self.proto_dir, "foo")],
                    {}, [])
                if es:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(d_map) == 0)

                # This should be different because the empty text file
                # is found before the binary file.
                self.make_proto_text_file(self.paths["curses_path"])
                d_map, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir, os.path.join(self.proto_dir, "foo")],
                    {}, [], remove_internal_deps=False)
                if es:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                if len(ms) != 1:
                        raise RuntimeError("Didn't get expected types of "
                            "missing files:\n%s" % ms)
                self.assertEqual(ms.keys()[0], "empty file")
                self.assert_(len(d_map) == 0)

                # This should find the binary file first and thus produce
                # a depend action.
                d_map, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [os.path.join(self.proto_dir, "foo"), self.proto_dir],
                    {}, [], remove_internal_deps=False)
                if es:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(d_map) == 1)

                # Check alternative proto_dirs with hardlinks.
                t_path = self.make_manifest(self.int_hardlink_manf)
                self.make_proto_text_file(os.path.join("foo",
                    self.paths["syslog_path"]))
                # This test should fail because "foo" is not included in the
                # list of proto_dirs.
                ds, es, ms, pkg_attrs = \
                    dependencies.list_implicit_deps(t_path, [self.proto_dir],
                        {}, [])
                if len(es) != 1:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                if es[0].file_path != \
                    os.path.join(self.proto_dir, self.paths["syslog_path"]):
                        raise RuntimeError("Wrong file was found missing:\n%s" %
                            es[0])
                self.assert_(len(ms) == 0)
                self.assert_(len(ds) == 1)

                # This test should pass because the needed directory has been
                # added to the list of proto_dirs.
                ds, es, ms, pkg_attrs = \
                    dependencies.list_implicit_deps(t_path,
                        [self.proto_dir, os.path.join(self.proto_dir, "foo")],
                        {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assert_(len(ms) == 1)
                self.assert_(len(ds) == 0)

                # Check alternative proto_dirs work with python files and
                # scripts.

                def _py_check_all_res(res):
                        ds, es, ms, pkg_attrs = res
                        mod_suffs = ["/__init__.py", ".py", ".pyc", ".pyo"]
                        mod_names = ["foobar", "misc_test", "os",
                            "search_storage"]
                        pkg_names = ["indexer_test", "pkg", "pkg_test"]
                        expected_deps = set([("python",)] +
                            [tuple(sorted([
                                "%s%s" % (n,s) for s in mod_suffs
                            ]))
                            for n in mod_names] +
                            [("%s/__init__.py" % n,) for n in pkg_names])
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))

                        self.assertEqual(ms, {})
                        for d in ds:
                                self.assert_(d.is_error())
                                if d.dep_vars is None:
                                        raise RuntimeError("This dep had "
                                            "depvars of None:%s" % d)
                                self.assert_(d.dep_vars.is_satisfied())
                                if not d.dep_key()[0] in expected_deps:
                                        raise RuntimeError("Got this "
                                            "unexpected dep:%s\n\nd:%s" %
                                            (d.dep_key()[0], d))
                                expected_deps.remove(d.dep_key()[0])
                                self.assertEqual(d.action.attrs["path"],
                                        self.paths["indexer_path"])
                        if expected_deps:
                                raise RuntimeError("Couldn't find these "
                                    "dependencies:\n" + "\n".join(
                                    [str(s) for s in sorted(expected_deps)]))
                self.__debug = True
                t_path = self.make_manifest(self.ext_python_manf)

                self.make_proto_text_file(
                    os.path.join("d5", self.paths["indexer_path"]),
                    self.python_text)
                # This should have an error because it cannot find the file
                # needed.
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [])
                if len(es) != 1:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                if es[0].file_path != \
                    os.path.join(self.proto_dir, self.paths["indexer_path"]):
                        raise RuntimeError("Wrong file was found missing:\n%s" %
                            es[0])
                self.assertEqual(len(ds), 0)
                self.assertEqual(len(ms), 0)

                # Because d5 is in the list of proto dirs, this test should work
                # normally.
                _py_check_all_res(dependencies.list_implicit_deps(t_path,
                    [self.proto_dir, os.path.join(self.proto_dir, "d5")], {},
                    []))


        def test_smf_manifest_parse(self):
                """ We parse valid SMF manifests returning instance
                and dependency info."""

                for manifest in self.smf_paths.keys():
                        self.make_proto_text_file(self.paths[manifest],
                            self.smf_manifest_text[manifest])

                        # This should not parse, returning empty lists
                        if manifest == "broken":
                                instances, deps = smf.parse_smf_manifest(
                                    self.proto_dir+ "/" + self.paths[manifest])
                                self.assertEqual(instances, None)
                                self.assertEqual(deps, None)
                                continue

                        # Ensuring each manifest can be parsed
                        # and we detect declared dependencies and
                        # FMRIs according to those hardcoded in the test
                        instances, deps = smf.parse_smf_manifest(
                            self.proto_dir+ "/" + self.paths[manifest])
                        for fmri in instances:

                                for dep in self.smf_known_deps[fmri]:
                                        if dep not in deps[fmri]:
                                                self.assert_(False,
                                                    "%s not found in "
                                                    "dependencies for %s" %
                                                    (dep, manifest))
                                expected = len(self.smf_known_deps[fmri])
                                actual = len(deps[fmri])

                                self.assertEqual(expected, actual,
                                    "expected number of deps (%s) != "
                                    "actual (%s) for %s"
                                    % (expected, actual, fmri))


        def check_smf_fmris(self, pkg_attrs, expected, manifest_name):
                """ Given a list of expected SMF FMRIs, verify that each is
                present in the provided pkg_attrs dictionary. Errors are
                reported in an assertion message that includes manifest_name."""

                self.assert_(pkg_attrs.has_key("opensolaris.smf.fmri"),
                    "Missing opensolaris.smf.fmri key for %s" % manifest_name)

                found = len(pkg_attrs["opensolaris.smf.fmri"])
                self.assertEqual(found, len(expected),
                    "Wrong no. of SMF instances/services found for %s: expected"
                    " %s got %s" % (manifest_name, len(expected), found))

                for fmri in expected:
                            self.assert_(
                                fmri in pkg_attrs["opensolaris.smf.fmri"],
                                "%s not in list of SMF instances/services "
                                "from %s" % (fmri, manifest_name))

        def print_deps(self, deps):
                for dep in deps:
                        print dep.base_names

        def test_int_smf_manifest(self):
                """We identify SMF dependencies delivered in the same package"""

                t_path = self.make_manifest(self.int_smf_manf)
                self.make_smf_test_files()

                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False)
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))

                self.assert_(len(ds) == 1, "Expected 1 dependency, got %s" %
                    len(ds))
                d = ds[0]

                # verify we have identified the one internal file we depend on
                actual = d.manifest.replace(self.proto_dir + "/", "")
                expected = self.paths["delivered_many_nodeps"]
                self.assertEqual(actual, expected,
                    "Expected dependency path %s, got %s" % (actual, expected))

                self.check_smf_fmris(pkg_attrs,
                    self.smf_fmris["service_single"] +
                    self.smf_fmris["delivered_many_nodeps"],
                    "int_smf_manf")

                # verify that removing internal dependencies works as expected
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=True)
                self.assert_(len(ds) == 0, "Expected 0 dependencies, got %s" %
                    len(ds))


        def test_ext_smf_manifest(self):
                """We identify SMF dependencies delivered in a different
                package"""

                t_path = self.make_manifest(self.ext_smf_manf)
                self.make_smf_test_files()

                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False)
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))

                self.assert_(len(ds) == 1, "Expected 1 dependency, got %s" %
                    len(ds))

                # verify we have identified the one external file we depend on
                actual = ds[0].manifest.replace(self.proto_dir + "/", "")
                expected = self.paths["foreign_many_nodeps"]
                self.assertEqual(actual, expected ,
                    "Expected dependency path %s, got %s" % (actual, expected))

                self.check_smf_fmris(pkg_attrs,
                    self.smf_fmris["service_many"] +
                    self.smf_fmris["foreign_single_nodeps"],
                    "ext_smf_manf")


        def test_broken_manifest(self):
                """We report errors when dealing with a broken SMF manifest."""

                # as it happens, file(1) isn't good at spotting broken
                # XML documents, it only sniffs the header - so this file
                # gets reported as an 'XML document' despite it being invalid
                # XML.
                t_path = self.make_manifest(self.broken_smf_manf)
                self.make_smf_test_files()

                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False)

                self.assertEqual(len(ms), 1, "No unknown files reported during "
                    "analysis")

                if "XML document" not in ms:
                        self.assert_(False, "Broken SMF manifest file not"
                            " declared")

                broken_path = os.path.join(self.proto_dir, self.paths["broken"])
                self.assertEqual(ms["XML document"], broken_path,
                    "Did not detect broken SMF manifest file: %s != %s" % (
                    broken_path, ms["XML document"]))

                # We should still be able to resolve the other dependencies
                # though and it's important to check that the one broken SMF
                # manifest file didn't break the rest of the SMF manifest
                # backend.  This has been implicitly tested in other tests,
                # as the broken file is always installed in the manifest
                # location.
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))

                # our dependency comes from service_single depending on
                # delivered_many
                self.assert_(len(ds) == 1, "Expected 1 dependency, got %s" %
                    len(ds))
                d = ds[0]

                # verify we have identified the one internal file we depend on
                actual = d.manifest.replace(self.proto_dir + "/", "")
                expected = self.paths["delivered_many_nodeps"]
                self.assertEqual(actual, expected ,
                    "Expected dependency path %s, got %s" % (actual, expected))

                self.check_smf_fmris(pkg_attrs,
                    self.smf_fmris["service_single"] +
                    self.smf_fmris["delivered_many_nodeps"],
                    "broken_smf_manf")


        def test_faildeps_smf_manifest(self):
                """We report failed attempts to resolve dependencies"""

                t_path = self.make_manifest(self.faildeps_smf_manf)
                self.make_smf_test_files()

                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
                    [self.proto_dir], {}, [], remove_internal_deps=False)

                self.assert_(len(es) == 3,
                    "Detected %s error(s), expected 3" % len(es))

                # our two dependencies come from:
                # service_single depending on delivered_many_nodeps
                # service_unknown depending on delivered_many_nodeps
                self.assert_(len(ds) == 2, "Expected 2 dependencies, got %s" %
                    len(ds))

                for d in ds:
                        actual = d.manifest.replace(self.proto_dir + "/", "")
                        expected = self.paths["delivered_many_nodeps"]
                        self.assertEqual(actual, expected,
                            "Expected dependency path %s, got %s" %
                            (actual, expected))

                self.check_smf_fmris(pkg_attrs,
                    self.smf_fmris["service_single"] +
                    self.smf_fmris["delivered_many_nodeps"] +
                    self.smf_fmris["service_unknown"],
                    "faildeps_smf_manf")


if __name__ == "__main__":
        unittest.main()
