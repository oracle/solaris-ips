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

# Copyright (c) 2009, 2025, Oracle and/or its affiliates.

from . import testutils
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

from pkg5unittest import PYVER_CURRENT, PYV_CURRENT, PYVER_OTHER

mod_pats = (
    "{0}.abi3.so",
    "{0}.py",
    "{0}.pyc",
    "{0}.pyo",
    "{0}.so",
    "{0}/__init__.py",
    f"{{0}}.cpython-{PYV_CURRENT}.so",
    "64/{0}.abi3.so",
    "64/{0}.so",
    f"64/{{0}}.cpython-{PYV_CURRENT}.so",
)


class TestDependencyAnalyzer(pkg5unittest.Pkg5TestCase):

    paths = {
        "authlog_path": "var/log/authlog",
        "curses_path": "usr/xpg4/lib/libcurses.so.1",
        "indexer_path":
            f"usr/lib/python{PYVER_CURRENT}/vendor-packages/pkg_test/client/indexer.py",
        "ksh_path": "usr/bin/ksh",
        "libc_path": "lib/libc.so.1",
        "pkg_path":
            f"usr/lib/python{PYVER_CURRENT}/vendor-packages/pkg_test/client/__init__.py",
        "bypass_path": "pkgdep_test/file.py",
        "relative_dependee":
            f"usr/lib/python{PYVER_CURRENT}/vendor-packages/pkg_test/client/bar.py",
        "relative_depender":
            f"usr/lib/python{PYVER_CURRENT}/vendor-packages/pkg_test/client/foo.py",
        "runpath_mod_path": "opt/pkgdep_runpath/__init__.py",
        "runpath_mod_test_path": "opt/pkgdep_runpath/pdtest.py",
        "script_path": "lib/svc/method/svc-pkg-depot",
        "syslog_path": "var/log/syslog",
        "py_mod_path": f"usr/lib/python{PYVER_CURRENT}/vendor-packages/cProfile.py",
        "py_mod_path_alt": f"usr/lib/python{PYVER_OTHER}/vendor-packages/cProfile.py"
    }

    smf_paths = {
        "broken":
            "var/svc/manifest/broken-service.xml",
        "delete": "var/svc/manifest/delete-service.xml",
        "delivered_many_nodeps":
            "var/svc/manifest/delivered-many-nodeps.xml",
        "delivered_many_nodeps_alt":
            "var/svc/manifest/delivered-many-nodeps-alt.xml",
        "foreign_many_nodeps":
            "var/svc/manifest/foreign-many-nodeps.xml",
        "foreign_single_nodeps":
            "var/svc/manifest/foreign-single-nodeps.xml",
        "service_general": "var/svc/manifest/service-general.xml",
        "service_many": "var/svc/manifest/service-many.xml",
        "service_single": "var/svc/manifest/service-single.xml",
        "service_single_specific": "var/svc/manifest/service-specific.xml",
        "service_unknown": "var/svc/manifest/service-single-unknown.xml"
    }

    paths.update(smf_paths)

    ext_hardlink_manf = """ \
hardlink path=usr/foo target=../{syslog_path}
hardlink path=usr/bar target=../{syslog_path}
hardlink path=baz target={authlog_path}
""".format(**paths)

    int_hardlink_manf = """ \
hardlink path=usr/foo target=../{syslog_path}
file NOHASH group=sys mode=0644 owner=root path={syslog_path}
""".format(**paths)

    int_hardlink_manf_test_symlink = """ \
hardlink path=usr/foo target=../{syslog_path}
file NOHASH group=sys mode=0644 owner=root path=bar/syslog
""".format(**paths)

    ext_script_manf = """ \
file NOHASH group=bin mode=0755 owner=root path={script_path}
""".format(**paths)

    int_script_manf = """ \
file NOHASH group=bin mode=0755 owner=root path={script_path}
file NOHASH group=bin mode=0755 owner=root path={ksh_path}
""".format(**paths)

    ext_elf_manf = """ \
file NOHASH group=bin mode=0755 owner=root path={curses_path}
""".format(**paths)

    int_elf_manf = """ \
file NOHASH group=bin mode=0755 owner=root path={libc_path}
file NOHASH group=bin mode=0755 owner=root path={curses_path}
""".format(**paths)

    ext_python_manf = """ \
file NOHASH group=bin mode=0755 owner=root path={indexer_path}
""".format(**paths)

    ext_python_pkg_manf = """ \
file NOHASH group=bin mode=0755 owner=root path={pkg_path}
""".format(**paths)

    python_mod_manf = """ \
file NOHASH group=bin mode=0755 owner=root path={py_mod_path}
file NOHASH group=bin mode=0755 owner=root path={py_mod_path_alt}
""".format(**paths)

    relative_ext_depender_manf = """ \
file NOHASH group=bin mode=0755 owner=root path={relative_depender}
""".format(**paths)
    relative_int_manf = """ \
file NOHASH group=bin mode=0755 owner=root path={relative_dependee}
file NOHASH group=bin mode=0755 owner=root path={relative_depender}
""".format(**paths)

    variant_manf_1 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path={script_path}
file NOHASH group=bin mode=0755 owner=root path={ksh_path} variant.arch=foo
""".format(**paths)

    variant_manf_2 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path={script_path} variant.arch=foo
file NOHASH group=bin mode=0755 owner=root path={ksh_path} variant.arch=foo
""".format(**paths)

    variant_manf_3 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path={script_path} variant.arch=bar
file NOHASH group=bin mode=0755 owner=root path={ksh_path} variant.arch=foo
""".format(**paths)

    variant_manf_4 = """ \
set name=variant.arch value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
file NOHASH group=bin mode=0755 owner=root path={script_path} variant.opensolaris.zone=global
file NOHASH group=bin mode=0755 owner=root path={ksh_path} variant.opensolaris.zone=global
""".format(**paths)

    python_abs_text = """\
#!/usr/bin/python

import os
import sys
import pkg_test.indexer_test.foobar as indexer
import pkg.search_storage as ss
import xml.dom.minidom
from ..misc_test import EmptyI
"""

    python_text = """\
#!/usr/bin/python

import os
import sys
import pkg_test.indexer_test.foobar as indexer
import pkg.search_storage as ss
import xml.dom.minidom
from pkg_test.misc_test import EmptyI
"""
    # a python module that causes slightly different behaviour in
    # modulefinder.py
    python_module_text = """\
#! /usr/bin/python

class Foo:
        def run(self):
                import __main__
"""

    smf_fmris = {}
    smf_known_deps = {}

    smf_fmris["service_single"] = [
        "svc:/application/pkg5test/service-default",
        "svc:/application/pkg5test/service-default:default"]

    smf_known_deps["svc:/application/pkg5test/service-default"] = \
        ["svc:/application/pkg5test/delivered-many:nodeps"]
    smf_known_deps["svc:/application/pkg5test/service-default:default"] = \
        ["svc:/application/pkg5test/delivered-many:nodeps"]

    smf_manifest_text = {}
    smf_manifest_text["service_single"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='service-default'>

<!-- we deliver:
  svc:/application/pkg5test/service-default
      (deps: svc:/application/pkg5test/delivered-many:nodeps)
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
		<service_fmri value="svc:/application/pkg5test/delivered-many:nodeps" />
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

    smf_fmris["service_single_specific"] = [
        "svc:/application/pkg5test/service-specific",
        "svc:/application/pkg5test/service-specific:default"]

    smf_known_deps["svc:/application/pkg5test/service-specific"] = \
        ["svc:/application/pkg5test/delivered-many:nodeps",
        "svc:/application/pkg5test/delivered-many:nodeps2"]
    smf_known_deps["svc:/application/pkg5test/service-specific:default"] = \
        ["svc:/application/pkg5test/delivered-many:nodeps",
        "svc:/application/pkg5test/delivered-many:nodeps2"]

    smf_manifest_text["service_single_specific"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='service-default'>

<!-- we deliver:
  svc:/application/pkg5test/service-specific
      (deps: svc:/application/pkg5test/delivered-many:nodeps,
       svc:/application/pkg5test/delivered-many:nodeps1)
  svc:/application/pkg5test/service-default:default

  This manifest checks that we can create multiple dependencies that each must
  be satisfied, unlink 'service_single' which specifies a service-level
  dependency, one instance of which would satisfy the dependency.
-->
<service
	name='application/pkg5test/service-specific'
	type='service'
	version='0.1'>

	<dependency
		name="delivered-service"
		grouping="require_all"
		restart_on="none"
		type="service">
		<service_fmri value="svc:/application/pkg5test/delivered-many:nodeps" />
                <service_fmri value="svc:/application/pkg5test/delivered-many:nodeps2" />
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

    smf_fmris["service_general"] = [
        "svc:/application/pkg5test/service-general",
        "svc:/application/pkg5test/service-general:default"]

    smf_known_deps["svc:/application/pkg5test/service-general"] = \
        ["svc:/application/pkg5test/delivered-many"]
    smf_known_deps["svc:/application/pkg5test/service-general:default"] = \
        ["svc:/application/pkg5test/delivered-many"]

    smf_manifest_text["service_general"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='service-general'>

<!-- we deliver:
  svc:/application/pkg5test/service-general
      (deps: svc:/application/pkg5test/delivered-many, )
  svc:/application/pkg5test/service-default:default
-->
<service
	name='application/pkg5test/service-general'
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

    smf_fmris["service_many"] = [
        "svc:/application/pkg5test/service-many",
        "svc:/application/pkg5test/service-many:default",
        "svc:/application/pkg5test/service-many:one",
        "svc:/application/pkg5test/service-many:two"]

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

	<!-- pkg(7) shouldn't see this as a dependency -->
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

    smf_fmris["service_unknown"] = [
        "svc:/application/pkg5test/service-unknown",
        "svc:/application/pkg5test/service-unknown:default",
        "svc:/application/pkg5test/service-unknown:one"]

    smf_known_deps["svc:/application/pkg5test/service-unknown"] = \
        ["svc:/application/pkg5test/delivered-many:nodeps",
        "svc:/application/pkg5test/unknown-service"]
    smf_known_deps["svc:/application/pkg5test/service-unknown:default"] = \
        ["svc:/application/pkg5test/delivered-many:nodeps",
        "svc:/application/pkg5test/unknown-service"]
    smf_known_deps["svc:/application/pkg5test/service-unknown:one"] = \
        ["svc:/application/pkg5test/delivered-many:nodeps",
        "svc:/application/pkg5test/unknown-service",
        "svc:/application/pkg5test/another-unknown:default"]

    smf_manifest_text["service_unknown"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='service-unknown'>

<!-- we deliver:
  svc:/application/pkg5test/service-unknown
      (deps: svc:/application/pkg5test/delivered-many:nodeps
             svc:/application/pkg5test/unknown-service
  svc:/application/pkg5test/service-unknown:default
      (deps: svc:/application/pkg5test/delivered-many:nodeps
             svc:/application/pkg5test/unknown-service)
  svc:/application/pkg5test/service-unknown:one
      (deps: svc:/application/pkg5test/delivered-many:nodeps
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
		<service_fmri value="svc:/application/pkg5test/delivered-many:nodeps" />
	</dependency>


        <!-- pkg(7) should throw an error here, as we don't deliver this
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

    	    <!-- pkg(7) should throw an error being unable to resolve this -->
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

    smf_fmris["delivered_many_nodeps"] = [
        "svc:/application/pkg5test/delivered-many",
        "svc:/application/pkg5test/delivered-many:nodeps",
        "svc:/application/pkg5test/delivered-many:nodeps1"]

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

    smf_known_deps["svc:/application/pkg5test/delivered-many"] = []
    smf_known_deps["svc:/application/pkg5test/delivered-many:nodeps2"] = []
    smf_known_deps["svc:/application/pkg5test/delivered-many:nodeps3"] = []

    smf_manifest_text["delivered_many_nodeps_alt"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='default-service-many'>
<!-- we deliver alternative instances of the "delivered-many" service.

svc:/application/pkg5test/delivered-many
svc:/application/pkg5test/delivered-many:nodeps2
svc:/application/pkg5test/delivered-many:nodeps3

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

	<instance name="nodeps2" enabled="true" />
	<instance name='nodeps3' enabled='false' />
</service>
</service_bundle>
"""

    smf_fmris["foreign_single_nodeps"] = [
        "svc:/application/pkg5test/foreign-single",
        "svc:/application/pkg5test/foreign-single:nodeps"]

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

    smf_fmris["foreign_many_nodeps"] = [
        "svc:/application/pkg5test/foreign-many",
        "svc:/application/pkg5test/foreign-many:default",
        "svc:/application/pkg5test/foreign-many:nodeps",
        "svc:/application/pkg5test/foreign-opt",
        "svc:/application/pkg5test/foreign-opt:nodeps"]

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
    smf_fmris["delete"] = [
        "svc:/application/pkg5test/deleteservice",
        "svc:/application/pkg5test/deleteservice:default"]
    smf_known_deps["svc:/application/pkg5test/deleteservice"] = []
    smf_known_deps["svc:/application/pkg5test/deleteservice:default"] = []
    smf_manifest_text["delete"] = \
"""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='delete-service'>

<!-- svc:/application/pkg5test/deleteservice
     svc:/application/pkg5test/deleteservice:default
    While we do have an SMF dependency, this shouldn't be used to generate
    pkg dependencies, since it has the 'delete' attribute set to true.
-->
<service

	name='application/pkg5test/deleteservice'
	type='service'
	version='0.1'>
	<create_default_instance enabled='true' />
	<single_instance/>
        <dependency name='network'
                    grouping='require_all'
                    restart_on='error'
                    type='service'
                    delete='true'>
                    <service_fmri value='svc:/application/pkg5test/delivered-many'/>
        </dependency>
</service>
</service_bundle>
"""

    int_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path={service_single}
file NOHASH group=sys mode=0644 owner=root path={delivered_many_nodeps}
""".format(**paths)

    # service_general depends on a service, instances of which are delivered
    # by both of the other SMF manifests
    int_req_svc_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path={service_general}
file NOHASH group=sys mode=0644 owner=root path={delivered_many_nodeps_alt}
file NOHASH group=sys mode=0644 owner=root path={delivered_many_nodeps}
""".format(**paths)

    # a bypassed version of the above, to ensure that the use of
    # full_paths by SMFManifestDependency when multiple files are
    # depended on still works.
    bypassed_int_req_svc_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path={service_general} \
    pkg.depend.bypass-generate=.*var/svc/manifest/delivered-many-nodeps-alt.xml
file NOHASH group=sys mode=0644 owner=root path={delivered_many_nodeps_alt}
file NOHASH group=sys mode=0644 owner=root path={delivered_many_nodeps}
""".format(**paths)

    # service_specific depends on instances delivered by both of the
    # other SMF manifests
    int_req_inst_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path={service_single_specific}
file NOHASH group=sys mode=0644 owner=root path={delivered_many_nodeps_alt}
file NOHASH group=sys mode=0644 owner=root path={delivered_many_nodeps}
""".format(**paths)

    ext_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path={service_many}
file NOHASH group=sys mode=0644 owner=root path={foreign_single_nodeps}
""".format(**paths)

    broken_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path={broken}
file NOHASH group=sys mode=0644 owner=root path={delivered_many_nodeps}
file NOHASH group=sys mode=0644 owner=root path={service_single}
""".format(**paths)

    delete_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path={delete}
file NOHASH group=sys mode=0644 owner=root path={foreign_single_nodeps}
""".format(**paths)

    faildeps_smf_manf = """\
file NOHASH group=sys mode=0644 owner=root path={delivered_many_nodeps}
file NOHASH group=sys mode=0644 owner=root path={service_single}
file NOHASH group=sys mode=0644 owner=root path={service_unknown}
""".format(**paths)

    script_text = "#!/usr/bin/ksh -p\n"

    # the following scripts and manifests are used to test pkgdepend
    # runpath and bypass
    python_bypass_text = """\
#!/usr/bin/python{0}
# This python script has an import used to test pkgdepend runpath and bypass
# functionality. pdtest is installed in a non-standard location and generates
# dependencies on multiple files (pdtest.py, pdtest.pyc, pdtest.pyo, etc.)
import pkgdep_runpath.pdtest
""".format(PYVER_CURRENT)

    # standard use of a runpath attribute
    python_runpath_manf = """\
file NOHASH group=sys mode=0755 owner=root path={bypass_path} \
    pkg.depend.runpath=opt:$PKGDEPEND_RUNPATH:dummy_directory
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_path}
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_test_path}
""".format(**paths)

    # a manifest which has an empty runpath (which is zany) - we will
    # throw an error here and want to test for it
    python_empty_runpath_manf = """
file NOHASH group=sys mode=0755 owner=root path={bypass_path} \
    pkg.depend.runpath=""
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_path}
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_test_path}
""".format(**paths)

    # a manifest which has a broken runpath
    python_invalid_runpath_manf = """
file NOHASH group=sys mode=0755 owner=root path={bypass_path} \
    pkg.depend.runpath=foo pkg.depend.runpath=bar pkg.depend.runpath=opt
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_path}
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_test_path}
""".format(**paths)

    # a manifest which needs a runpath in order to generate deps properly
    python_invalid_runpath2_manf = """
file NOHASH group=sys mode=0755 owner=root path={bypass_path} \
    pkg.depend.runpath=$PKGDEPEND_RUNPATH:foo:$PKGDEPEND_RUNPATH
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_path}
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_test_path}
""".format(**paths)

    # a manifest that bypasses two files and sets a runpath
    python_bypass_manf = """
file NOHASH group=sys mode=0755 owner=root path={bypass_path} \
    pkg.depend.bypass-generate=opt/pkgdep_runpath/pdtest.py \
    pkg.depend.bypass-generate=usr/lib/python{0}/lib-dynload/pkgdep_runpath/pdtest.cpython-{1}.so \
    pkg.depend.runpath=opt:$PKGDEPEND_RUNPATH
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_path}
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_test_path}
""".format(PYVER_CURRENT, PYV_CURRENT, **paths)

    # a manifest that generates a single dependency, which we want to
    # bypass
    ksh_bypass_manf = """
file NOHASH group=sys mode=055 owner=root path={script_path} \
    pkg.depend.bypass-generate=usr/bin/ksh
""".format(**paths)

    # a manifest that generates a single dependency, which we want to
    # bypass.  Specifying just the filename means we should bypass all
    # paths to that filename (we implicitly add ".*/")
    ksh_bypass_filename_manf = """
file NOHASH group=sys mode=055 owner=root path={script_path} \
    pkg.depend.bypass-generate=ksh
""".format(**paths)

    # a manifest that generates a single dependency, which we want to
    # bypass, duplicating the value
    ksh_bypass_dup_manf = """
file NOHASH group=sys mode=055 owner=root path={script_path} \
    pkg.depend.bypass-generate=usr/bin/ksh \
    pkg.depend.bypass-generate=usr/bin/ksh
""".format(**paths)

    # a manifest that declares bypasses, none of which match the
    # dependences we generate
    python_bypass_nomatch_manf = """
file NOHASH group=sys mode=0755 owner=root path={bypass_path} \
    pkg.depend.bypass-generate=cats \
    pkg.depend.bypass-generate=dogs \
    pkg.depend.runpath=$PKGDEPEND_RUNPATH:opt
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_path}
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_test_path}
""".format(**paths)

    # a manifest which uses a wildcard to bypass all dependency generation
    python_wildcard_bypass_manf = """
file NOHASH group=sys mode=0755 owner=root path={bypass_path} \
    pkg.depend.bypass-generate=.* \
    pkg.depend.runpath=$PKGDEPEND_RUNPATH:opt
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_path}
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_test_path}
""".format(**paths)

    # a manifest which uses a file wildcard to bypass generation
    python_wildcard_file_bypass_manf = """
file NOHASH group=sys mode=0755 owner=root path={bypass_path} \
    pkg.depend.bypass-generate=opt/pkgdep_runpath/.* \
    pkg.depend.runpath=$PKGDEPEND_RUNPATH:opt
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_path}
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_test_path}
""".format(**paths)

    # a manifest which uses a dir wildcard to bypass generation
    python_wildcard_dir_bypass_manf = """
file NOHASH group=sys mode=0755 owner=root path={bypass_path} \
    pkg.depend.bypass-generate=pdtest.py \
    pkg.depend.bypass-generate=pdtest.pyc \
    pkg.depend.bypass-generate=pdtest.pyo \
    pkg.depend.bypass-generate=pdtest.so \
    pkg.depend.bypass-generate=pdtest.cpython-{0}.so \
    pkg.depend.runpath=$PKGDEPEND_RUNPATH:opt
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_path}
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_test_path}
""".format(PYV_CURRENT, **paths)

    # a manifest which uses a combination of directory, file and normal
    # bypass entries
    python_wildcard_combo_bypass_manf = """
file NOHASH group=sys mode=0755 owner=root path={bypass_path} \
    pkg.depend.bypass-generate=pdtest.py \
    pkg.depend.bypass-generate=usr/lib/python{0}/vendor-packages/.* \
    pkg.depend.bypass-generate=usr/lib/python{0}/site-packages/pkgdep_runpath/pdtest.cpython-{1}.so \
    pkg.depend.runpath=$PKGDEPEND_RUNPATH:opt
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_path}
file NOHASH group=sys mode=0755 owner=root path={runpath_mod_test_path}
""".format(PYVER_CURRENT, PYV_CURRENT, **paths)

    def setUp(self):
        pkg5unittest.Pkg5TestCase.setUp(self)

        self.proto_dir = os.path.join(self.test_root, "proto")
        os.makedirs(self.proto_dir)

    def make_proto_text_file(self, path, contents=""):
        self.make_misc_files({path: contents}, prefix="proto")

    def make_python_test_files(self, py_version):
        pdir = "usr/lib/python{0}/vendor-packages".format(py_version)
        self.make_proto_text_file("{0}/pkg_test/__init__.py".format(pdir),
            "#!/usr/bin/python\n")
        self.make_proto_text_file(
            "{0}/pkg_test/indexer_test/__init__.py".format(pdir),
            "#!/usr/bin/python")
        self.make_proto_text_file("{0}/cProfile.py".format(pdir),
            self.python_module_text)
        self.make_proto_text_file("{0}/pkg_test/client/foo.py".format(pdir),
            "#!/usr/bin/python\nimport bar")
        self.make_proto_text_file("{0}/pkg_test/client/bar.py".format(pdir),
            "#!/usr/bin/python\n")
        # install these in non-sys.path locations
        self.make_proto_text_file(self.paths["bypass_path"],
            self.python_bypass_text)
        self.make_proto_text_file(self.paths["runpath_mod_path"],
            f"#!/usr/bin/python{PYVER_CURRENT}")
        self.make_proto_text_file(self.paths["runpath_mod_test_path"],
            f"#!/usr/bin/python{PYVER_CURRENT}")

    def make_broken_python_test_file(self, py_version):
        pdir = "usr/lib/python{0}/vendor-packages".format(py_version)
        self.make_proto_text_file("{0}/cProfile.py".format(pdir),
            "#!/usr/bin/python\n\\1" + self.python_module_text)

    def make_smf_test_files(self):
        for manifest in self.smf_paths.keys():
            self.make_proto_text_file(self.paths[manifest],
                self.smf_manifest_text[manifest])

    def make_elf(self, final_path, static=False):
        out_file = os.path.join(self.proto_dir, final_path)

        opts = []
        # In some cases we want to generate an elf binary with no
        # dependencies of its own.  We use -c (suppress linking) for
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
            ds, es, ws, ms, pkg_attrs = res
            if es != []:
                raise RuntimeError("Got errors in results:" +
                    "\n".join([str(s) for s in es]))
            self.assertEqual(ms, {})
            self.assertTrue(len(ds) == 3)
            ans = set(["usr/foo", "usr/bar"])
            for d in ds:
                self.assertTrue(d.dep_vars.is_satisfied())
                self.assertTrue(d.is_error())
                if d.dep_key() == self.__path_to_key(
                    self.paths["syslog_path"]):
                    self.assertTrue(
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
            [self.proto_dir], {}, [], convert=False))
        _check_results(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [],
            remove_internal_deps=False, convert=False))

    def test_int_hardlink(self):
        """Check that a hardlink with a target inside the package is
        not reported as a dependency, unless the flag to show internal
        dependencies is set."""

        t_path = self.make_manifest(self.int_hardlink_manf)
        self.make_proto_text_file(self.paths["syslog_path"])
        ds, es, ws, ms, pkg_attrs = \
            dependencies.list_implicit_deps(t_path, [self.proto_dir],
                {}, [], convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertTrue(len(ms) == 1)
        self.assertTrue(len(ds) == 0)

        # Check that internal dependencies are as expected.
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(len(ms), 1)
        self.assertEqual(len(ds), 1)
        d = ds[0]
        self.assertTrue(d.dep_vars.is_satisfied())
        self.assertTrue(d.is_error())
        self.assertEqual(d.dep_key(), self.__path_to_key(
            self.paths["syslog_path"]))
        self.assertEqual(d.action.attrs["path"], "usr/foo")
        self.assertTrue(dependencies.is_file_dependency(d))

    def test_ext_script(self):
        """Check that a file that starts with #! and references a file
        outside its package is reported as a dependency."""

        def _check_res(res):
            ds, es, ws, ms, pkg_attrs = res
            if es != []:
                raise RuntimeError("Got errors in results:" +
                    "\n".join([str(s) for s in es]))
            self.assertEqual(ms, {})
            self.assertTrue(len(ds) == 1)
            d = ds[0]
            self.assertTrue(d.is_error())
            self.assertTrue(d.dep_vars.is_satisfied())
            self.assertEqual(d.dep_key(),
                self.__path_to_key(self.paths["ksh_path"]))
            self.assertEqual(d.action.attrs["path"],
                self.paths["script_path"])
        t_path = self.make_manifest(self.ext_script_manf)
        self.make_proto_text_file(self.paths["script_path"],
            self.script_text)
        _check_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False))
        _check_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False))

    def test_int_script(self):
        """Check that a file that starts with #! and references a file
        inside its package is not reported as a dependency unless
        the flag to show internal dependencies is set."""

        t_path = self.make_manifest(self.int_script_manf)
        self.make_elf(self.paths["ksh_path"])
        self.make_proto_text_file(self.paths["script_path"],
            self.script_text)
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertTrue(len(ds) == 1)
        d = ds[0]
        self.assertTrue(d.is_error())
        self.assertTrue(d.dep_vars.is_satisfied())
        self.assertEqual(d.base_names[0], "libc.so.1")
        self.assertEqual(set(d.run_paths), set(["lib",
            "usr/lib"]))

        # Check that internal dependencies are as expected.
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        self.assertEqual(len(ds), 2)
        for d in ds:
            self.assertTrue(d.is_error())
            self.assertTrue(d.dep_vars.is_satisfied())
            self.assertTrue(dependencies.is_file_dependency(d))
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
                    "dependency path:{0}".format(d))

    def test_ext_elf(self):
        """Check that an elf file that requires a library outside its
        package is reported as a dependency."""

        def _check_res(res):
            ds, es, ws, ms, pkg_attrs = res
            if es != []:
                raise RuntimeError("Got errors in results:" +
                    "\n".join([str(s) for s in es]))
            self.assertEqual(ms, {})
            self.assertTrue(len(ds) == 1)
            d = ds[0]
            self.assertTrue(d.is_error())
            self.assertTrue(d.dep_vars.is_satisfied())
            self.assertEqual(d.base_names[0], "libc.so.1")
            self.assertEqual(set(d.run_paths),
                set(["lib", "usr/lib"]))
            self.assertEqual(d.dep_key(),
                self.__path_to_key(self.paths["libc_path"]))
            self.assertEqual(
                    d.action.attrs["path"],
                    self.paths["curses_path"])
            self.assertTrue(dependencies.is_file_dependency(d))

        t_path = self.make_manifest(self.ext_elf_manf)
        self.make_elf(self.paths["curses_path"])
        _check_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False))
        _check_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False))

    def test_int_elf(self):
        """Check that an elf file that requires a library inside its
        package is not reported as a dependency unless the flag to show
        internal dependencies is set."""

        def _check_all_res(res):
            ds, es, ws, ms, pkg_attrs = res
            if es != []:
                raise RuntimeError("Got errors in results:" +
                    "\n".join([str(s) for s in es]))
            self.assertEqual(ms, {})
            self.assertEqual(len(ds), 1)
            d = ds[0]
            self.assertTrue(d.is_error())
            self.assertTrue(d.dep_vars.is_satisfied())
            self.assertEqual(d.base_names[0], "libc.so.1")
            self.assertEqual(set(d.run_paths),
                set(["lib", "usr/lib"]))
            self.assertEqual(d.dep_key(),
                self.__path_to_key(self.paths["libc_path"]))
            self.assertEqual(d.action.attrs["path"],
                self.paths["curses_path"])
            self.assertTrue(dependencies.is_file_dependency(d))

        t_path = self.make_manifest(self.int_elf_manf)
        self.make_elf(self.paths["curses_path"])
        self.make_elf(self.paths["libc_path"], static=True)
        d_map, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(
            t_path, [self.proto_dir], {}, [], convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertTrue(len(d_map) == 0)

        # Check that internal dependencies are as expected.
        _check_all_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False))

    def test_ext_python_dep(self):
        """Check that a python file that imports a module outside its
        package is reported as a dependency."""

        def _check_all_res(res):
            ds, es, ws, ms, pkg_attrs = res
            mod_names = ["foobar", "misc_test", "os",
                "search_storage", "minidom"]
            pkg_names = ["indexer_test", "pkg", "pkg_test", "xml",
                "dom"]
            expected_deps = set([("python",)] +
                [tuple(sorted([
                    pat.format(n) for pat in mod_pats
                ]))
                for n in mod_names] +
                [("{0}/__init__.py".format(n),) for n in pkg_names])
            if es != []:
                raise RuntimeError("Got errors in results:" +
                    "\n".join([str(s) for s in es]))

            self.assertEqual(ms, {})
            for d in ds:
                self.assertTrue(d.is_error())
                if d.dep_vars is None:
                    raise RuntimeError("This dep had "
                        "depvars of None:{0}".format(d))
                self.assertTrue(d.dep_vars.is_satisfied())
                if not d.dep_key()[0] in expected_deps:
                    raise RuntimeError("Got this "
                        "unexpected dep:{0}\n\nd:{1}".format(
                        d.dep_key()[0], d))
                expected_deps.remove(d.dep_key()[0])
                self.assertEqual(d.action.attrs["path"],
                        self.paths["indexer_path"])
            if expected_deps:
                raise RuntimeError("Couldn't find these "
                    "dependencies:\n" + "\n".join(
                    [str(s) for s in sorted(expected_deps)]))
        self.__debug = True
        t_path = self.make_manifest(self.ext_python_manf)
        self.make_python_test_files(PYVER_CURRENT)
        self.make_proto_text_file(self.paths["indexer_path"],
            self.python_text)
        _check_all_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False))
        _check_all_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False))

    def test_ext_python_abs_import_dep(self):
        """Check that a python file that uses absolute imports a module
        is handled correctly."""

        def _check_all_res(res):
            ds, es, ws, ms, pkg_attrs = res
            mod_names = ["foobar", "os", "search_storage",
                "minidom"]
            pkg_names = ["indexer_test", "pkg", "pkg_test", "xml",
                "dom"]
            expected_deps = set([("python",)] +
                [tuple(sorted([
                    pat.format(n) for pat in mod_pats
                ]))
                for n in mod_names] +
                [("{0}/__init__.py".format(n),) for n in pkg_names])
            if len(es) != 1:
                raise RuntimeError("Expected exactly 1 error, "
                    "got:%\n" + "\n".join([str(s) for s in es]))
            if es[0].name != "misc_test":
                raise RuntimeError("Didn't get the expected "
                    "error. Error found was:{0}".format(es[0]))

            self.assertEqual(ms, {})
            for d in ds:
                self.assertTrue(d.is_error())
                if d.dep_vars is None:
                    raise RuntimeError("This dep had "
                        "depvars of None:{0}".format(d))
                self.assertTrue(d.dep_vars.is_satisfied())
                if not d.dep_key()[0] in expected_deps:
                    raise RuntimeError("Got this "
                        "unexpected dep:{0}\n\nd:{1}".format(
                        d.dep_key()[0], d))
                expected_deps.remove(d.dep_key()[0])
                self.assertEqual(d.action.attrs["path"],
                        self.paths["indexer_path"])
            if expected_deps:
                raise RuntimeError("Couldn't find these "
                    "dependencies:\n" + "\n".join(
                    [str(s) for s in sorted(expected_deps)]))
        self.__debug = True
        t_path = self.make_manifest(self.ext_python_manf)
        self.make_python_test_files(PYVER_CURRENT)
        # Check that absolute imports still work.
        self.make_proto_text_file(self.paths["indexer_path"],
            self.python_abs_text)
        _check_all_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False))
        _check_all_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False))

    def test_ext_python_pkg_dep(self):
        """Check that a python file that is the __init__.py file for a
        package is handled correctly."""

        def _check_all_res(res):
            ds, es, ws, ms, pkg_attrs = res
            mod_names = ["foobar", "misc_test", "os",
                "search_storage", "minidom"]
            pkg_names = ["indexer_test", "pkg", "pkg_test",
                "xml", "dom"]

            # for a multi-level import, we should have the correct
            # dir suffixes generated for the pkg.debug.depend.paths
            path_suffixes = {"minidom.py": "xml/dom",
                "dom/__init__.py": "xml"}

            expected_deps = set([("python",)] +
                [tuple(sorted([
                    pat.format(n) for pat in mod_pats
                ]))
                for n in mod_names] +
                [("{0}/__init__.py".format(n),) for n in pkg_names])
            if es != []:
                raise RuntimeError("Got errors in results:" +
                    "\n".join([str(s) for s in es]))

            self.assertEqual(ms, {})
            for d in ds:
                self.assertTrue(d.is_error())
                if d.dep_vars is None:
                    raise RuntimeError("This dep had "
                        "depvars of None:{0}".format(d))
                self.assertTrue(d.dep_vars.is_satisfied())
                if not d.dep_key()[0] in expected_deps:
                    raise RuntimeError("Got this "
                        "unexpected dep:{0}\n\nd:{1}".format(
                        d.dep_key()[0], d))

                # check the suffixes generated in our
                # pkg.debug.depend.path
                for bn in d.base_names:
                    if bn not in path_suffixes:
                        continue

                    suffix = path_suffixes[bn]
                    for p in d.run_paths:
                        self.assertTrue(
                            p.endswith(suffix) or
                            p == os.path.dirname(
                            self.paths["pkg_path"]),
                            "suffix {0} not found in "
                            "paths for {1}: {2}".format(
                            suffix, bn, " ".join(
                            d.run_paths)))

                expected_deps.remove(d.dep_key()[0])
                self.assertEqual(d.action.attrs["path"],
                        self.paths["pkg_path"])
            if expected_deps:
                raise RuntimeError("Couldn't find these "
                    "dependencies:\n" + "\n".join(
                    [str(s) for s in sorted(expected_deps)]))
        self.__debug = True
        t_path = self.make_manifest(self.ext_python_pkg_manf)
        self.make_python_test_files(PYVER_CURRENT)
        self.make_proto_text_file(self.paths["pkg_path"],
            self.python_text)
        _check_all_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False))
        _check_all_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False))

    def test_python_imp_main(self):
        """Ensure we can generate a dependency from a python module
        known to cause different behaviour in modulefinder, where
        we try to import __main__"""

        t_path = self.make_manifest(self.python_mod_manf)
        # Two versions are used because the python dependency checker
        # has two code paths, one that uses the native module importer
        # and one that fires off a subprocess (depthlimited.py). So
        # there is a need to verify the output from both code paths.
        self.make_python_test_files(PYVER_OTHER)
        self.make_python_test_files(PYVER_CURRENT)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False)
        # No errors detected.
        self.assertTrue(len(es) == 0, "Unexpected errors reported: {0}".format(es))
        # Two for python and two for the __main__ dependency.
        self.assertTrue(len(ds) == 4, "Unexpected deps reported: {0}".format(ds))
        for d in ds:
            self.assertTrue(d.base_names == ["python"] or
                            "__main__.abi3.so" in d.base_names,
                            "Bad dependency generated: {0}".format(ds))

    def test_python_relative_import_generation(self):
        """This is a test for bug 14094.  It ensures that a python
        dependency's paths include the directory into which the file
        will be delivered."""

        t_path = self.make_manifest(
            self.relative_ext_depender_manf)
        self.make_python_test_files(PYVER_CURRENT)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=True,
            convert=False)

        pddt = "pkg.debug.depend.type"
        pddp = "pkg.debug.depend.path"
        pddf = "pkg.debug.depend.file"

        expected_deps = set([pat.format("bar") for pat in mod_pats])
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertEqual(len(ds), 2)
        got_relative_import = False
        for d in ds:
            if d.attrs[pddt] == "script":
                continue
            self.assertEqual(d.attrs[pddt], "python")
            self.assertEqualDiff(expected_deps, set(d.attrs[pddf]))
            ep = os.path.dirname(self.paths["relative_depender"])
            if ep not in d.attrs[pddp]:
                raise RuntimeError("Expected {0} to be in the "
                    "list of pkg.debug.depend.path attribute "
                    "values, but it wasn't seen.".format(ep))

        t_path = self.make_manifest(
            self.relative_int_manf)
        self.assertTrue(os.path.exists(os.path.join(self.proto_dir,
            self.paths["relative_dependee"])))

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=True,
            convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertEqual(len(ds), 2, "Expected two dependencies, "
            "got:\n{0}".format("\n".join([str(d) for d in ds])))
        for d in ds:
            self.assertEqual(d.attrs[pddt], "script", "Got this "
                "dependency which wasn't of the expected type:{0}".format(
                d))

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertEqual(len(ds), 3)
        got_relative_import = False
        for d in ds:
            if d.attrs[pddt] == "script":
                continue
            self.assertEqual(d.attrs[pddt], "python")
            self.assertEqualDiff(expected_deps, set(d.attrs[pddf]))
            ep = os.path.dirname(self.paths["relative_depender"])
            if ep not in d.attrs[pddp]:
                raise RuntimeError("Expected {0} to be in the "
                    "list of pkg.debug.depend.path attribute "
                    "values, but it wasn't seen.".format(ep))

    def test_bug_18031(self):
        """Test that an python file which python cannot import due to a
        syntax error doesn't cause a traceback."""

        t_path = self.make_manifest(self.python_mod_manf)
        # Two versions are used because the python dependency checker
        # has two code paths, one that uses the native module importer
        # and one that fires off a subprocess (depthlimited.py). So
        # there is a need to verify the output from both code paths.
        self.make_broken_python_test_file(PYVER_OTHER)
        self.make_broken_python_test_file(PYVER_CURRENT)
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False)
        # One error for each python version.
        self.assertTrue(len(es) == 2, "Unexpected errors reported: {0}".format(es))
        for e in es:
            self.debug(str(e))
            self.assertTrue("but contains a syntax error that" in str(e))
        # should be two dependencies (both on python)
        self.assertTrue(len(ds) == 2, "Unexpected deps reported: {0}".format(ds))
        for d in ds:
            self.assertTrue(d.base_names == ["python"],
                            "Unexpected dependency: {0}".format(ds))

    def test_variants_1(self):
        """Test that a file which satisfies a dependency only under a
        certain set of variants results in the dependency being reported
        for the other set of variants."""

        t_path = self.make_manifest(self.variant_manf_1)
        self.make_proto_text_file(self.paths["script_path"],
            self.script_text)
        self.make_elf(self.paths["ksh_path"])
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertTrue(len(ds) == 2)
        for d in ds:
            self.assertTrue(d.is_error())
            if d.dep_key() == self.__path_to_key(
                self.paths["ksh_path"]):
                self.assertEqual(d.action.attrs["path"],
                    self.paths["script_path"])
                expected_not_sat = set([
                    frozenset([("variant.arch", "bar")]),
                    frozenset([("variant.arch", "baz")])])
                expected_sat = set([
                    frozenset([("variant.arch", "foo")])])
                self.assertEqual(expected_sat,
                    d.dep_vars.sat_set)
                self.assertEqual(expected_not_sat,
                    d.dep_vars.not_sat_set)
            elif d.dep_key() == self.__path_to_key(
                self.paths["libc_path"]):
                self.assertEqual(
                    d.action.attrs["path"],
                    self.paths["ksh_path"])
                expected_not_sat = set([
                    frozenset([("variant.arch", "foo")])])
                expected_sat = set()
                self.assertEqual(expected_sat,
                    d.dep_vars.sat_set)
                self.assertEqual(expected_not_sat,
                    d.dep_vars.not_sat_set)
            else:
                raise RuntimeError("Unexpected "
                    "dependency path:{0}".format(d.dep_key()))

    def test_variants_2(self):
        """Test that when the variants of the action with the dependency
        and the action satisfying the dependency share the same
        dependency, an external dependency is not reported."""

        t_path = self.make_manifest(self.variant_manf_2)
        self.make_proto_text_file(self.paths["script_path"],
            self.script_text)
        self.make_elf(self.paths["ksh_path"])
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertTrue(len(ds) == 1)
        d = ds[0]
        self.assertTrue(d.is_error())
        expected_not_sat = set([frozenset([("variant.arch", "foo")])])
        expected_sat = set()
        self.assertEqual(expected_sat, d.dep_vars.sat_set)
        self.assertEqual(expected_not_sat, d.dep_vars.not_sat_set)
        self.assertEqual(d.base_names[0], "libc.so.1")
        self.assertEqual(set(d.run_paths), set(["lib", "usr/lib"]))

        # Check that internal dependencies are as expected.
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertTrue(len(ds) == 2)
        for d in ds:
            self.assertTrue(d.is_error())
            # Because not removing internal dependencies means that
            # no resolution of their variants happens, both
            # dependencies have their variants as unsatisfied.
            expected_not_sat = set([
                frozenset([("variant.arch", "foo")])])
            expected_sat = set()
            self.assertEqual(expected_sat, d.dep_vars.sat_set)
            self.assertEqual(expected_not_sat,
                d.dep_vars.not_sat_set)
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
                    "Unexpected dependency path:{0}".format(
                    d.dep_key()))

    def test_variants_3(self):
        """Test that when the action with the dependency is tagged with
        a different variant than the action which could satisfy it, it's
        reported as an external dependency."""

        t_path = self.make_manifest(self.variant_manf_3)
        self.make_proto_text_file(self.paths["script_path"],
            self.script_text)
        self.make_elf(self.paths["ksh_path"])
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertTrue(len(ds) == 2)
        for d in ds:
            self.assertTrue(d.is_error())
            if d.dep_key() == self.__path_to_key(
                self.paths["ksh_path"]):
                self.assertEqual(d.action.attrs["path"],
                    self.paths["script_path"])
                expected_not_sat = set([
                    frozenset([("variant.arch", "bar")])])
                expected_sat = set()
                self.assertEqual(expected_sat,
                    d.dep_vars.sat_set)
                self.assertEqual(expected_not_sat,
                    d.dep_vars.not_sat_set)
            elif d.dep_key() == self.__path_to_key(
                self.paths["libc_path"]):
                self.assertEqual(d.action.attrs["path"],
                    self.paths["ksh_path"])
                expected_not_sat = set([
                    frozenset([("variant.arch", "foo")])])
                expected_sat = set()
                self.assertEqual(expected_sat,
                    d.dep_vars.sat_set)
                self.assertEqual(expected_not_sat,
                    d.dep_vars.not_sat_set)
            else:
                raise RuntimeError("Unexpected "
                    "dependency path:{0}".format(d.dep_key()))

    def test_variants_4(self):
        """Test that an action with a variant that depends on a
        delivered action also tagged with that variant, but not with a
        package-level variant is reported as an internal dependency, not
        an external one."""

        t_path = self.make_manifest(self.variant_manf_4)
        self.make_proto_text_file(self.paths["script_path"],
            self.script_text)
        self.make_elf(self.paths["ksh_path"])

        # Check that we only report a single external dependency
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertTrue(len(ds) == 1)
        d = ds[0]

        self.assertTrue(d.is_error())
        expected_not_sat = set([frozenset([
            ("variant.opensolaris.zone", "global")])])
        expected_sat = set()
        self.assertEqualDiff(expected_sat, d.dep_vars.sat_set)
        self.assertEqualDiff(expected_not_sat, d.dep_vars.not_sat_set)

        self.assertEqual(d.base_names[0], "libc.so.1")
        self.assertEqual(set(d.run_paths), set(["lib", "usr/lib"]))

        # Check that internal dependencies are as expected.
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertEqual(pkg_attrs, {})
        self.assertTrue(len(ds) == 2)
        for d in ds:
            self.assertTrue(d.is_error())
            # Because not removing internal dependencies means that
            # no resolution of their variants happens, both
            # dependencies have their variants as unsatisfied.
            expected_not_sat = set([frozenset([
                ("variant.arch", "foo"),
                ("variant.opensolaris.zone", "global")])])
            expected_sat = set()
            self.assertEqual(expected_sat, d.dep_vars.sat_set)
            self.assertEqual(expected_not_sat,
                d.dep_vars.not_sat_set)

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
                    "Unexpected dependency path:{0}".format(
                    d.dep_key()))

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
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False)

    def test_str_methods(self):
        """Test the str methods of objects in the flavor space."""

        str(base.MissingFile("fp"))
        str(elf.BadElfFile("fp", "ex"))
        str(elf.UnsupportedDynamicToken("/proto_path", "/install",
            "run_path", "tok"))
        str(py.PythonModuleMissingPath("foo", "bar"))
        str(py.PythonMismatchedVersion(PYVER_CURRENT, PYVER_OTHER, "foo", "bar"))
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
            self.assertTrue(d.is_error())
            self.assertTrue(d.dep_vars.is_satisfied())
            self.assertEqual(d.base_names[0], "libc.so.1")
            self.assertEqual(set(d.run_paths),
                set(["lib", "usr/lib"]))
            self.assertEqual(d.dep_key(),
                self.__path_to_key(self.paths["libc_path"]))
            self.assertEqual(d.action.attrs["path"],
                self.paths["curses_path"])
            self.assertTrue(dependencies.is_file_dependency(d))

        t_path = self.make_manifest(self.int_elf_manf)
        self.make_elf(os.path.join("foo", self.paths["curses_path"]))
        self.make_elf(self.paths["libc_path"], static=True)

        # This should fail because the "foo" directory is not given
        # as a proto_dir.
        d_map, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(
            t_path, [self.proto_dir], {}, [], convert=False)
        if len(es) != 1:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        if es[0].file_path != self.paths["curses_path"]:
            raise RuntimeError("Wrong file was found missing:\n{0}".format(
                es[0]))
        self.assertEqual(es[0].dirs, [self.proto_dir])
        self.assertEqual(ms, {})
        self.assertTrue(len(d_map) == 0)

        # This should work since the "foo" directory has been added to
        # the list of proto_dirs to use.
        d_map, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(
            t_path, [self.proto_dir,
            os.path.join(self.proto_dir, "foo")], {}, [], convert=False)
        if es:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertTrue(len(d_map) == 0)

        # This should be different because the empty text file
        # is found before the binary file.
        self.make_proto_text_file(self.paths["curses_path"])
        d_map, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(
            t_path, [self.proto_dir,
            os.path.join(self.proto_dir, "foo")], {}, [],
            remove_internal_deps=False, convert=False)
        if es:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        if len(ms) != 1:
            raise RuntimeError("Didn't get expected types of "
                "missing files:\n{0}".format(ms))
        self.assertEqual(list(ms.keys())[0], "empty file")
        self.assertTrue(len(d_map) == 0)

        # This should find the binary file first and thus produce
        # a depend action.
        d_map, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(
            t_path, [os.path.join(self.proto_dir, "foo"),
            self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        if es:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertEqual(ms, {})
        self.assertTrue(len(d_map) == 1)

        # Check alternative proto_dirs with hardlinks.
        t_path = self.make_manifest(self.int_hardlink_manf)
        self.make_proto_text_file(os.path.join("foo",
            self.paths["syslog_path"]))
        # This test should fail because "foo" is not included in the
        # list of proto_dirs.
        ds, es, ws, ms, pkg_attrs = \
            dependencies.list_implicit_deps(t_path, [self.proto_dir],
                {}, [], convert=False)
        if len(es) != 1:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        if es[0].file_path != self.paths["syslog_path"]:
            raise RuntimeError("Wrong file was found missing:\n{0}".format(
                es[0]))
        self.assertEqual(es[0].dirs, [self.proto_dir])
        self.assertTrue(len(ms) == 0)
        self.assertTrue(len(ds) == 1)

        # This test should pass because the needed directory has been
        # added to the list of proto_dirs.
        ds, es, ws, ms, pkg_attrs = \
            dependencies.list_implicit_deps(t_path,
                [self.proto_dir, os.path.join(self.proto_dir, "foo")],
                {}, [], convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        self.assertTrue(len(ms) == 1)
        self.assertTrue(len(ds) == 0)

        # Check alternative proto_dirs work with python files and
        # scripts.

        def _py_check_all_res(res):
            ds, es, ws, ms, pkg_attrs = res
            mod_names = ["foobar", "misc_test", "os",
                "search_storage", "minidom"]
            pkg_names = ["indexer_test", "pkg", "pkg_test",
                "xml", "dom"]
            expected_deps = set([("python",)] +
                [tuple(sorted([
                    pat.format(n) for pat in mod_pats
                ]))
                for n in mod_names] +
                [("{0}/__init__.py".format(n),) for n in pkg_names])
            if es != []:
                raise RuntimeError("Got errors in results:" +
                    "\n".join([str(s) for s in es]))

            self.assertEqual(ms, {})
            for d in ds:
                self.assertTrue(d.is_error())
                if d.dep_vars is None:
                    raise RuntimeError("This dep had "
                        "depvars of None:{0}".format(d))
                self.assertTrue(d.dep_vars.is_satisfied())
                if not d.dep_key()[0] in expected_deps:
                    raise RuntimeError("Got this "
                        "unexpected dep:{0}\n\nd:{1}".format(
                        d.dep_key()[0], d))
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
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], convert=False)
        if len(es) != 1:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))
        if es[0].file_path != self.paths["indexer_path"]:
            raise RuntimeError("Wrong file was found missing:\n{0}".format(
                es[0]))
        self.assertEqual(es[0].dirs, [self.proto_dir])
        self.assertEqual(len(ds), 0)
        self.assertEqual(len(ms), 0)

        # Because d5 is in the list of proto dirs, this test should work
        # normally.
        _py_check_all_res(dependencies.list_implicit_deps(t_path,
            [self.proto_dir, os.path.join(self.proto_dir, "d5")], {},
            [], convert=False))

    def test_smf_manifest_parse(self):
        """ We parse valid SMF manifests returning instance
        and dependency info."""

        for manifest in self.smf_paths.keys():
            self.make_proto_text_file(self.paths[manifest],
                self.smf_manifest_text[manifest])

            # This should not parse, returning empty lists
            if manifest == "broken":
                instances, deps = smf.parse_smf_manifest(
                    self.proto_dir + "/" + self.paths[manifest])
                self.assertEqual(instances, None)
                self.assertEqual(deps, None)
                continue

            # Ensuring each manifest can be parsed
            # and we detect declared dependencies and
            # FMRIs according to those hardcoded in the test
            instances, deps = smf.parse_smf_manifest(
                self.proto_dir + "/" + self.paths[manifest])
            for fmri in instances:

                for dep in self.smf_known_deps[fmri]:
                    if dep not in deps[fmri]:
                        self.assertTrue(False,
                            "{0} not found in "
                            "dependencies for {1}".format(
                            dep, manifest))
                expected = len(self.smf_known_deps[fmri])
                actual = len(deps[fmri])

                self.assertEqual(expected, actual,
                    "expected number of deps ({0}) != "
                    "actual ({1}) for {2}"
                   .format(expected, actual, fmri))

    def check_smf_fmris(self, pkg_attrs, expected, manifest_name):
        """ Given a list of expected SMF FMRIs, verify that each is
        present in the provided pkg_attrs dictionary. Errors are
        reported in an assertion message that includes manifest_name."""

        self.assertTrue("org.opensolaris.smf.fmri" in pkg_attrs,
            "Missing org.opensolaris.smf.fmri key for {0}".format(
            manifest_name))

        found = len(pkg_attrs["org.opensolaris.smf.fmri"])
        self.assertEqual(found, len(expected),
            "Wrong no. of SMF instances/services found for {0}: expected"
            " {1} got {2}".format(manifest_name, len(expected), found))

        for fmri in expected:
            self.assertTrue(
                fmri in pkg_attrs["org.opensolaris.smf.fmri"],
                "{0} not in list of SMF instances/services "
                "from {1}".format(fmri, manifest_name))

    def print_deps(self, deps):
        for dep in deps:
            print(dep.base_names)

    def test_int_smf_manifest(self):
        """We identify SMF dependencies delivered in the same package"""

        t_path = self.make_manifest(self.int_smf_manf)
        self.make_smf_test_files()

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))

        self.assertTrue(len(ds) == 1, "Expected 1 dependency, got {0}".format(
            len(ds)))
        d = ds[0]

        # verify we have identified the one internal file we depend on
        actual = d.manifest.replace(self.proto_dir + "/", "")
        expected = self.paths["delivered_many_nodeps"]
        self.assertEqual(actual, expected,
            "Expected dependency path {0}, got {1}".format(actual, expected))

        self.check_smf_fmris(pkg_attrs,
            self.smf_fmris["service_single"] +
            self.smf_fmris["delivered_many_nodeps"],
            "int_smf_manf")

        # verify that removing internal dependencies works as expected
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=True,
            convert=False)
        self.assertTrue(len(ds) == 0, "Expected 0 dependencies, got {0}".format(
            len(ds)))
        self.assertTrue(dependencies.is_file_dependency(d))

    def test_ext_smf_manifest(self):
        """We identify SMF dependencies delivered in a different
        package"""

        t_path = self.make_manifest(self.ext_smf_manf)
        self.make_smf_test_files()

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        if es != []:
            raise RuntimeError("Got errors in results:" +
                "\n".join([str(s) for s in es]))

        self.assertTrue(len(ds) == 1, "Expected 1 dependency, got {0}".format(
            len(ds)))

        # verify we have identified the one external file we depend on
        actual = ds[0].manifest.replace(self.proto_dir + "/", "")
        expected = self.paths["foreign_many_nodeps"]
        self.assertEqual(actual, expected,
            "Expected dependency path {0}, got {1}".format(actual, expected))

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

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)

        self.assertEqual(len(ms), 1, "No unknown files reported during "
            "analysis")

        if "XML document" not in ms:
            self.assertTrue(False, "Broken SMF manifest file not"
                " declared")

        broken_path = os.path.join(self.proto_dir, self.paths["broken"])
        self.assertEqual(ms["XML document"], broken_path,
            "Did not detect broken SMF manifest file: {0} != {1}".format(
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
        self.assertTrue(len(ds) == 1, "Expected 1 dependency, got {0}".format(
            len(ds)))
        d = ds[0]

        # verify we have identified the one internal file we depend on
        actual = d.manifest.replace(self.proto_dir + "/", "")
        expected = self.paths["delivered_many_nodeps"]
        self.assertEqual(actual, expected,
            "Expected dependency path {0}, got {1}".format(actual, expected))

        self.check_smf_fmris(pkg_attrs,
            self.smf_fmris["service_single"] +
            self.smf_fmris["delivered_many_nodeps"],
            "broken_smf_manf")

    def test_faildeps_smf_manifest(self):
        """We report failed attempts to resolve dependencies"""

        t_path = self.make_manifest(self.faildeps_smf_manf)
        self.make_smf_test_files()

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)

        self.assertTrue(len(es) == 3,
            "Detected {0} error(s), expected 3".format(len(es)))

        # our two dependencies come from:
        # service_single depending on delivered_many_nodeps
        # service_unknown depending on delivered_many_nodeps
        self.assertTrue(len(ds) == 2, "Expected 2 dependencies, got {0}".format(
            len(ds)))

        for d in ds:
            actual = d.manifest.replace(self.proto_dir + "/", "")
            expected = self.paths["delivered_many_nodeps"]
            self.assertEqual(actual, expected,
                "Expected dependency path {0}, got {1}".format(
                actual, expected))

        self.check_smf_fmris(pkg_attrs,
            self.smf_fmris["service_single"] +
            self.smf_fmris["delivered_many_nodeps"] +
            self.smf_fmris["service_unknown"],
            "faildeps_smf_manf")

    def test_delete_smf_manifest(self):
        """We don't create any SMF dependencies where a manifest
        specifies a 'delete' attribute in its dependency."""

        t_path = self.make_manifest(self.delete_smf_manf)
        self.make_smf_test_files()

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)

        self.assertTrue(len(es) == 0,
            "Detected {0} error(s), expected 0".format(len(es)))
        self.assertTrue(len(ds) == 0, "Expected 0 dependencies, got {0}".format(
            len(ds)))
        self.check_smf_fmris(pkg_attrs, self.smf_fmris["delete"] +
            self.smf_fmris["foreign_single_nodeps"], "delete")

    def test_req_any_smf_manifest(self):
        """We can generate dependencies that can be turned into
        require-any dependencies.

        In this test, we generate dependencies on three different SMF
        manifests:

        The first has a single service-level dependency that is
        satisfied by two instances, delivered by two separate SMF
        manifests, generating a single dependency that can be turned
        into a require-any depend action.

        The second has two instance-level dependencies that are also
        delivered by two separate SMF manifests, and should generate two
        require dependencies (because we're being specific about which
        instances we depend on, rather than depending on any instance
        of that service, as in the first case, above)

        The last is a version of the first, with a bypass attribute, to
        ensure that we correctly process bypasses when generating
        multiple dependencies. (SMFManifestDependency doesn't use
        base_names/run_paths when multiple SMF manifests are found as
        dependencies, but instead specifies full_paths directly, which
        are modified by the bypass-generation code)
        """

        self.make_smf_test_files()

        # Test the first case: service dependencies satisfied by
        # multiple SMF manifests.
        t_path = self.make_manifest(self.int_req_svc_smf_manf)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(
            t_path, [self.proto_dir], {}, [],
            remove_internal_deps=False, convert=False)
        self.assertTrue(len(es) == 0, "Detected {0} error(s), expected 0".format(
            len(es)))
        self.assertTrue(len(ds) == 1, "Expected 1 dependency when "
            "depending on a service, got {0}".format(len(ds)))
        # ensure the dependencies are correct.
        self.assertTrue(set(ds[0].full_paths) == set([
            self.paths["delivered_many_nodeps"],
            self.paths["delivered_many_nodeps_alt"]]),
            "Expected two separate full_path entries, got {0}".format(
            ds[0].full_paths))

        # for SMF dependencies on services that are satisfied by
        # multiple instances in separate files, we should have no
        # run_paths or base_names
        self.assertTrue(ds[0].run_paths == [])
        self.assertTrue(ds[0].base_names == [])

        # Test the second case: specific dependencies on instances
        # satisfied by multiple (different) SMF manifests.
        t_path = self.make_manifest(self.int_req_inst_smf_manf)
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(
            t_path, [self.proto_dir], {}, [],
            remove_internal_deps=False, convert=False)
        self.assertTrue(len(es) == 0, "Detected {0} error(s), expected 0".format(
            len(es)))
        self.assertTrue(len(ds) == 2, "Expected 2 dependencies, got {0}".format(
            len(ds)))

        seen_nodeps3 = False
        seen_nodeps = False
        for d in ds:
            # ensure the dependencies are correct.
            actual = d.manifest.replace(self.proto_dir + "/", "")
            if actual == self.paths["delivered_many_nodeps"]:
                seen_nodeps = True
            elif actual == self.paths["delivered_many_nodeps_alt"]:
                seen_nodeps3 = True
            self.assertTrue(d.run_paths, "Expected a directory path "
                "for {0}: {1}".format(d, d.run_paths))
            self.assertTrue(d.full_paths == [], "Expected an empty "
                "list for full_paths, got {0}".format(d.full_paths))

        self.assertTrue(seen_nodeps3 and seen_nodeps, "Expected "
            "dependencies were not generated when several SMF "
            "instances were listed as 'require_all' dependencies.")

        # Test the third case: service dependencies satisfied by
        # multiple SMF manifests, but with one bypassed.
        t_path = self.make_manifest(self.bypassed_int_req_svc_smf_manf)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(
            t_path, [self.proto_dir], {}, [],
            remove_internal_deps=False, convert=False)
        self.assertTrue(len(es) == 0, "Detected {0} error(s), expected 0".format(
            len(es)))
        self.assertTrue(len(ds) == 1, "Expected 1 dependency, got {0}".format(
            len(ds)))
        # ensure the dependencies are correct.
        self.assertTrue(ds[0].full_paths ==
            [self.paths["delivered_many_nodeps"]],
            "d.full_paths entry was incorrect, got {0}".format(
            ds[0].full_paths))

        # since we've bypassed a dependency, we should not have
        # run_paths or base_names
        self.assertTrue(ds[0].run_paths == [])
        self.assertTrue(ds[0].base_names == [])

    def test_runpath_1(self):
        """Test basic functionality of runpaths."""

        t_path = self.make_manifest(self.python_runpath_manf)
        self.make_python_test_files(PYVER_CURRENT)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        self.assertTrue(es == [], "Unexpected errors reported: {0}".format(es))

        for dep in ds:
            # only interested in seeing that our runpath was changed
            if "pdtest.py" in dep.attrs["pkg.debug.depend.file"]:
                self.assertTrue("opt/pkgdep_runpath" in
                    dep.attrs["pkg.debug.depend.path"])
                self.assertTrue(f"usr/lib/python{PYVER_CURRENT}/pkgdep_runpath"
                    in dep.attrs["pkg.debug.depend.path"])
                # ensure this dependency was indeed generated
                # as a result of our test file
                self.assertTrue("pkgdep_test/file.py" in
                    dep.attrs["pkg.debug.depend.reason"])
            self.assertTrue(dependencies.is_file_dependency(dep))

    def test_runpath_2(self):
        """Test invalid runpath attributes."""

        self.make_python_test_files(PYVER_CURRENT)

        # test a runpath with multiple values
        t_path = self.make_manifest(self.python_invalid_runpath_manf)
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        self.assertTrue(es != [], "No errors reported for broken runpath")

        # test a runpath with multiple $PD_DEFAULT_RUNPATH components
        t_path = self.make_manifest(self.python_invalid_runpath2_manf)
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        self.assertTrue(es != [], "No errors reported for broken runpath")

    def test_runpath_3(self):
        """Test setting an empty runpath attribute"""

        t_path = self.make_manifest(self.python_empty_runpath_manf)
        self.make_python_test_files(PYVER_CURRENT)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        self.assertTrue(es != [], "No errors reported for empty runpath")

    def validate_bypass_dep(self, dep):
        """Given a dependency which may be bypassed, if it has been,
        it should have been expanded into a dependency containing just
        pkg.debug.depend.fullpath entries.
        """
        self.assertTrue(dependencies.is_file_dependency(dep))

        if dep.attrs.get("pkg.debug.depend.fullpath", None):
            for val in ["path", "file"]:
                self.assertTrue("pkg.debug.depend.{0}".format(val)
                    not in dep.attrs, "We should not see a {0} "
                    "entry in this dependency: {1}".format(
                    val, dep))
                self.assertTrue(not dep.run_paths,
                    "Unexpected run_paths: {0}".format(dep))
                self.assertTrue(not dep.base_names,
                    "Unexpected base_names: {0}".format(dep))
        else:
            self.assertTrue("pkg.debug.depend.fullpath" not in
                dep.attrs, "We should not see a fullpath "
                "entry in this dependency: {0}".format(dep))
            self.assertTrue(not dep.full_paths,
                "Unexpected full_paths: {0}".format(dep))

    def verify_bypass(self, ds, es, bypass):
        """Given a list of dependencies, and a list of bypass paths,
        verify that we have not generated a dependency on any of the
        items in the bypass list.

        If a bypass has been performed, the dependency will have been
        expanded to contain pkg.debug.depend.fullpath values,
        otherwise we should have p.d.d.path and p.d.d.file items.
        We should never have all three attributes set.
        """

        self.assertTrue(len(es) == 0, "Errors reported during bypass: {0}".format(
            es))

        for dep in ds:
            # generate all possible paths this dep could represent
            dep_paths = set()
            self.validate_bypass_dep(dep)
            if dep.attrs.get("pkg.debug.depend.fullpath", None):
                dep_paths.update(
                    dep.attrs["pkg.debug.depend.fullpath"])
            else:
                for filename in dep.base_names:
                    dep_paths.update([os.path.join(dir,
                        filename)
                        for dir in dep.run_paths])

            self.assertTrue(dependencies.is_file_dependency(dep))

            # finally, check the dependencies
            if dep_paths.intersection(set(bypass)):
                self.debug("Some items were not bypassed: {0}".format(
                    "\n".join(sorted(list(
                    dep_paths.intersection(set(bypass)))))))
                return False
        return True

    def verify_dep_generation(self, ds, expected):
        """Verifies that we have generated dependencies on the given
        files"""
        dep_paths = set()
        for dep in ds:
            self.debug(dep)
            self.validate_bypass_dep(dep)
            if dep.attrs.get("pkg.debug.depend.fullpath", None):
                dep_paths.update(
                    dep.attrs["pkg.debug.depend.fullpath"])
            else:
                # generate all paths this dep could represent
                for filename in dep.base_names:
                    dep_paths.update([
                        os.path.join(dir, filename)
                        for dir in dep.run_paths])
        for item in expected:
            if item not in dep_paths:
                self.debug("Expected to see dependency on {0}".format(
                    item))
                return False
        return True

    def test_bypass_1(self):
        """Ensure we can bypass dependency generation on a given file,
        or set of files
        """
        # this manifest should result in multiple dependencies
        t_path = self.make_manifest(self.python_bypass_manf)
        self.make_python_test_files(PYVER_CURRENT)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        self.assertTrue(self.verify_bypass(ds, es, [
            "opt/pkgdep_runpath/pdtest.py",
            f"usr/lib/python{PYVER_CURRENT}/lib-dynload/pkgdep_runpath/pdtest.cpython-{PYV_CURRENT}.so"]),
            "Python script was not bypassed")
        # now check we depend on some files which should not have been
        # bypassed
        self.assertTrue(self.verify_dep_generation(ds,
            [f"usr/lib/python{PYVER_CURRENT}/lib-dynload/pkgdep_runpath/pdtest.so",
            f"usr/lib/python{PYVER_CURRENT}/lib-dynload/pkgdep_runpath/pdtest.py",
            "opt/pkgdep_runpath/pdtest.pyc"]))

        # now run this again as a control, this time skipping bypass
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False, ignore_bypass=True)
        # the first two items in the list were previously bypassed
        self.assertTrue(self.verify_dep_generation(ds,
            ["opt/pkgdep_runpath/pdtest.py",
            f"usr/lib/python{PYVER_CURRENT}/lib-dynload/pkgdep_runpath/pdtest.cpython-{PYV_CURRENT}.so",
            f"usr/lib/python{PYVER_CURRENT}/lib-dynload/pkgdep_runpath/pdtest.so",
            "opt/pkgdep_runpath/pdtest.pyc"]),
            "Python script did not generate a dependency on bypassed")

        self.make_proto_text_file(self.paths["script_path"],
            self.script_text)

        # these manifests should only generate 1 dependency
        # we also test that duplicated bypass entries are ignored
        for manifest in [self.ksh_bypass_manf,
            self.ksh_bypass_dup_manf, self.ksh_bypass_filename_manf]:
            t_path = self.make_manifest(manifest)

            ds, es, ws, ms, pkg_attrs = \
                dependencies.list_implicit_deps(t_path,
                [self.proto_dir], {}, [],
                remove_internal_deps=False, convert=False)
            self.assertTrue(len(ds) == 0,
                "Did not generate exactly 0 dependencies")
            self.assertTrue(self.verify_bypass(ds, es,
                ["usr/bin/ksh"]), "Ksh script was not bypassed")

            # don't perform bypass
            ds, es, ws, ms, pkg_attrs = \
                dependencies.list_implicit_deps(t_path,
                [self.proto_dir], {}, [],
                remove_internal_deps=False, convert=False,
                ignore_bypass=True)
            self.assertTrue(len(ds) == 1,
                "Did not generate exactly 1 dependency on ksh")
            self.assertTrue(self.verify_dep_generation(
                ds, ["usr/bin/ksh"]),
                "Ksh script did not generate a dependency on ksh")

    def test_bypass_2(self):
        """Ensure that bypasses containing wildcards work"""
        t_path = self.make_manifest(self.python_wildcard_bypass_manf)
        self.make_python_test_files(PYVER_CURRENT)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)

        self.assertTrue(len(es) == 0, "Errors reported during bypass: {0}".format(
            es))

        # we should have bypassed all dependency generation on all files
        self.assertTrue(len(ds) == 0, "Generated dependencies despite "
            "request to bypass all dependency generation.")

        t_path = self.make_manifest(
            self.python_wildcard_dir_bypass_manf)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)

        self.assertTrue(self.verify_bypass(ds, es, [
            f"usr/lib/python{PYVER_CURRENT}/lib-dynload/pkgdep_runpath/pdtest.pyo",
            f"usr/lib/python{PYVER_CURRENT}/lib-dynload/pkgdep_runpath/pdtest.cpython-{PYV_CURRENT}.so"]),
            "Directory bypass wildcard failed")
        self.assertTrue(self.verify_dep_generation(ds, [
            f"usr/lib/python{PYVER_CURRENT}/pkgdep_runpath/__init__.py",
            f"usr/lib/python{PYVER_CURRENT}/lib-dynload/pkgdep_runpath/__init__.py"]),
            "Failed to generate dependencies, despite dir-wildcards")

        t_path = self.make_manifest(
            self.python_wildcard_file_bypass_manf)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        self.assertTrue(self.verify_bypass(ds, es, [
            "opt/pkgdep_runpath/pdtest.pyo",
            f"opt/pkgdep_runpath/pdtest.cpython-{PYV_CURRENT}.so"]),
            "Failed to bypass some paths despite use of file-wildcard")
        # we should still have dependencies on these
        self.assertTrue(self.verify_dep_generation(ds, [
            f"usr/lib/python{PYVER_CURRENT}/lib-dynload/pkgdep_runpath/pdtest.pyo",
            f"usr/lib/python{PYVER_CURRENT}/lib-dynload/pkgdep_runpath/pdtest.cpython-{PYV_CURRENT}.so"]),
            "Failed to generate dependencies, despite file-wildcards")

        # finally, test a combination of the above, we have:
        # pkg.depend.bypass-generate=.*/pdtest.py \
        # pkg.depend.bypass-generate=usr/lib/python3.9/vendor-packages/.* \
        # pkg.depend.bypass-generate=usr/lib/python3.9/site-packages/pkgdep_runpath/pdtest.cpython-39.so
        t_path = self.make_manifest(
            self.python_wildcard_combo_bypass_manf)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)
        self.assertTrue(self.verify_bypass(ds, es, [
            "opt/pkgdep_runpath/pdtest.py",
            f"usr/lib/python{PYVER_CURRENT}/vendor-packages/pkgdep_runpath/pdtest.py",
            f"usr/lib/python{PYVER_CURRENT}/site-packages/pkgdep_runpath/pdtest.py",
            f"usr/lib/python{PYVER_CURRENT}/site-packages/pkgdep_runpath/pdtest.cpython-{PYV_CURRENT}.so"]),
            "Failed to bypass some paths despite use of combo-wildcard")
        # we should still have dependencies on these
        self.assertTrue(self.verify_dep_generation(ds, [
            f"usr/lib/python{PYVER_CURRENT}/site-packages/pkgdep_runpath/pdtest.pyc",
            f"usr/lib/python{PYVER_CURRENT}/lib-dynload/pkgdep_runpath/pdtest.cpython-{PYV_CURRENT}.so"]),
            "Failed to generate dependencies, despite file-wildcards")

    def test_bypass_3(self):
        """Ensure that bypasses which don't match any dependencies have
        no effect on the computed dependencies."""
        t_path = self.make_manifest(self.python_bypass_nomatch_manf)
        self.make_python_test_files(PYVER_CURRENT)

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)

        for dep in ds:
            # we expect that there are only file/path attributes
            # since no bypasses have been performed
            self.assertTrue("pkg.debug.depend.file" in dep.attrs)
            self.assertTrue("pkg.debug.depend.path" in dep.attrs)
            self.assertTrue("pkg.debug.depend.fullpath"
                not in dep.attrs)

        def all_paths(ds):
            """Return all paths this list of dependencies could
            generate"""
            dep_paths = set()
            for dep in ds:
                # generate all paths this dep could represent
                dep_paths = set()
                for filename in dep.base_names + ["*"]:
                    dep_paths.update(os.path.join(dir, filename)
                        for dir in dep.run_paths + ["*"])
                dep_paths.remove("*/*")
            return dep_paths

        gen_paths = all_paths(ds)

        # now run again, without trying to perform dependency bypass
        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False, ignore_bypass=True)

        self.assertTrue(gen_paths == all_paths(ds),
            "generating dependencies with non-matching bypass entries "
            "changed the returned dependencies")

    def test_symlinked_proto(self):
        """Ensure that the behavior when using a symlink to a proto dir
        is identical to the behavior when using that proto dir for all
        flavors."""

        multi_flavor_manf = (self.ext_hardlink_manf +
             self.ext_script_manf + self.ext_elf_manf +
             self.ext_python_manf + self.ext_smf_manf +
             self.relative_int_manf)
        t_path = self.make_manifest(multi_flavor_manf)

        linked_proto = os.path.join(self.test_root, "linked_proto")
        os.symlink(self.proto_dir, linked_proto)

        self.make_proto_text_file(self.paths["script_path"],
            self.script_text)
        self.make_smf_test_files()
        self.make_python_test_files(PYVER_CURRENT)
        self.make_elf(self.paths["curses_path"])

        ds, es, ws, ms, pkg_attrs = dependencies.list_implicit_deps(t_path,
            [self.proto_dir], {}, [], remove_internal_deps=False,
            convert=False)

        smf.SMFManifestDependency._clear_cache()

        # now run the same function, this time using our symlinked dir
        dsl, esl, wsl, msl, pkg_attrsl = dependencies.list_implicit_deps(
            t_path, [linked_proto], {}, [],
            remove_internal_deps=False, convert=False)

        for a, b in [(ds, dsl), (pkg_attrs, pkg_attrsl)]:
            self.assertTrue(a == b, "Differences found comparing "
                "proto_dir with symlinked proto_dir: {0} vs. {1}"
               .format(a, b))


if __name__ == "__main__":
    unittest.main()
