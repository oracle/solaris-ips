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

# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import sys
import unittest

import pkg.client.api as api
import pkg.actions.depend as depend
import pkg.client.progress as progress
import pkg.flavor.base as base
from pkg.fmri import PkgFmri
import pkg.portable as portable
import pkg.publish.dependencies as dependencies


class TestApiDependencies(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = False

        depend_dp = base.Dependency.DEPEND_DEBUG_PREFIX

        hardlink1_manf_deps = """\
hardlink path=usr/foo target=../var/log/syslog
hardlink path=usr/bar target=../var/log/syslog
depend fmri=__TBD pkg.debug.depend.file=var/log/syslog pkg.debug.depend.reason=usr/bar pkg.debug.depend.type=hardlink type=require
depend fmri=__TBD pkg.debug.depend.file=var/log/syslog pkg.debug.depend.reason=usr/foo pkg.debug.depend.type=hardlink type=require
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog
"""

        hardlink2_manf_deps = """\
hardlink path=baz target=var/log/authlog
depend fmri=__TBD pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
file NOHASH group=sys mode=0644 owner=root path=var/log/syslog
"""
        multi_deps = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/v-p/pkg/client/indexer.py
depend fmri=__TBD pkg.debug.depend.file=usr/bin/python2.6 pkg.debug.depend.reason=usr/lib/python2.6/v-p/pkg/client/indexer.py pkg.debug.depend.type=script type=require
depend fmri=__TBD pkg.debug.depend.file=usr/lib/python2.6/v-p/pkg/misc.py pkg.debug.depend.reason=usr/lib/python2.6/v-p/pkg/client/indexer.py pkg.debug.depend.type=python type=require
"""

        misc_manf = """\
set name=fmri value=pkg:/footest@0.5.11,5.11-0.117
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python2.6/v-p/pkg/misc.py
"""

        simp_manf = """\
set name=variant.foo value=bar value=baz
depend fmri=__TBD pkg.debug.depend.file=var/log/syslog pkg.debug.depend.reason=usr/bar pkg.debug.depend.type=hardlink type=require
"""

        simple_variant_deps = """\
set name=variant.foo value=bar value=baz
depend fmri=__TBD pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
"""

        simple_v_deps_bar = """
set name=fmri value=pkg:/s-v-bar
set name=variant.foo value=bar value=baz
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=bar
"""

        simple_v_deps_bar2 = """
set name=fmri value=pkg:/s-v-bar
set name=variant.foo value=bar
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog
"""

        simple_v_deps_baz = """
set name=fmri value=pkg:/s-v-baz
set name=variant.foo value=bar value=baz
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=baz
"""

        simple_v_deps_baz2 = """
set name=fmri value=pkg:/s-v-baz
set name=variant.foo value=baz
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog
"""

        two_variant_deps = """\
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
depend fmri=__TBD pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
"""

        two_v_deps_bar = """
set name=fmri value=pkg:/s-v-bar
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=bar
"""

        two_v_deps_baz_one = """
set name=fmri value=pkg:/s-v-baz-one
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=baz variant.num=one
"""

        two_v_deps_baz_two = """
set name=fmri value=pkg:/s-v-baz-two
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=baz variant.num=two
"""

        collision_manf = """\
set name=fmri value=pkg:/collision_manf
depend fmri=__TBD pkg.debug.depend.file=no_such_named_file pkg.debug.depend.path=platform/foo/baz pkg.debug.depend.path=platform/bar/baz pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=foo/bar pkg.debug.depend.type=elf type=require\
"""

        collision_manf_num_var = """\
set name=fmri value=pkg:/collision_manf
set name=variant.num value=one value=two
depend fmri=__TBD pkg.debug.depend.file=no_such_named_file pkg.debug.depend.path=platform/foo/baz pkg.debug.depend.path=platform/bar/baz pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=foo/bar pkg.debug.depend.type=elf type=require\
"""

        sat_both = """\
set name=fmri value=pkg:/sat_both
file NOHASH path=platform/bar/baz/no_such_named_file
file NOHASH path=platform/foo/baz/no_such_named_file
"""

        sat_bar_libc = """\
set name=fmri value=pkg:/sat_bar_libc
file NOHASH path=platform/bar/baz/no_such_named_file
"""

        sat_bar_libc2 = """\
set name=fmri value=pkg:/sat_bar_libc2
file NOHASH path=platform/bar/baz/no_such_named_file
"""

        sat_foo_libc = """\
set name=fmri value=pkg:/sat_foo_libc
file NOHASH path=platform/foo/baz/no_such_named_file
"""

        sat_bar_libc_num_var = """\
set name=fmri value=pkg:/sat_bar_libc
set name=variant.num value=one
file NOHASH path=platform/bar/baz/no_such_named_file
"""
        sat_foo_libc_num_var = """\
set name=fmri value=pkg:/sat_foo_libc
set name=variant.num value=two
file NOHASH path=platform/foo/baz/no_such_named_file
"""
        sat_foo_libc_num_var_both = """\
set name=fmri value=pkg:/sat_foo_libc
set name=variant.num value=one value=two
file NOHASH path=platform/foo/baz/no_such_named_file
"""

        multi_file_dep_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py
depend fmri=__TBD pkg.debug.depend.file=search_storage.py pkg.debug.depend.file=search_storage.pyc pkg.debug.depend.file=search_storage/__init__.py pkg.debug.depend.path=usr/lib/python2.6/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-dynload/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-old/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-tk/pkg pkg.debug.depend.path=usr/lib/python2.6/plat-sunos5/pkg pkg.debug.depend.path=usr/lib/python2.6/site-packages/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gst-0.10/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gtk-2.0/pkg pkg.debug.depend.path=usr/lib/python26.zip/pkg pkg.debug.depend.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py pkg.debug.depend.type=python type=require
"""

        multi_file_dep_fullpath_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py
depend fmri=__TBD pkg.debug.depend.file=search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/lib-dynload/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/lib-old/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/lib-tk/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/plat-sunos5/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/site-packages/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/vendor-packages/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/vendor-packages/gst-0.10/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/vendor-packages/gtk-2.0/pkg/search_storage.py \
        pkg.debug.depend.fullpath=usr/lib/python26.zip/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.6/lib-dynload/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.6/lib-old/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.6/lib-tk/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.6/plat-sunos5/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.6/site-packages/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.6/vendor-packages/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.6/vendor-packages/gst-0.10/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.6/vendor-packages/gtk-2.0/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python26.zip/pkg/search_storage.pyc \
        pkg.debug.depend.fullpath=usr/lib/python2.6/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/lib-dynload/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/lib-old/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/lib-tk/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/plat-sunos5/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/site-packages/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/vendor-packages/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/vendor-packages/gst-0.10/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.6/vendor-packages/gtk-2.0/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python26.zip/pkg/search_storage/__init__.py \
    pkg.debug.depend.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py \
    pkg.debug.depend.type=python type=require
"""

        multi_file_sat_both = """\
set name=fmri value=pkg:/sat_both
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/search_storage.py
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/search_storage.pyc
"""

        multi_file_sat_py = """\
set name=fmri value=pkg:/sat_py
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/search_storage.py
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/lib-tk/pkg/search_storage.py
"""
        multi_file_sat_pyc = """\
set name=fmri value=pkg:/sat_pyc
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/search_storage.pyc
"""

        inst_pkg = """\
open example2_pkg@1.0,5.11-0
add file tmp/foo mode=0555 owner=root group=bin path=/usr/bin/python2.6
close"""

        var_pkg = """\
open variant_pkg@1.0,5.11-0
add set name=variant.foo value=bar value=baz
add file tmp/foo group=sys mode=0644 owner=root path=var/log/syslog
close"""

        double_deps = """\
set name=pkg.fmri value=double_deps@1.0,5.11-0
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=elfexec pkg.debug.depend.path=kernel/exec pkg.debug.depend.path=platform/i86hvm/kernel/exec pkg.debug.depend.path=platform/i86pc/kernel/exec pkg.debug.depend.path=platform/i86xpv/kernel/exec pkg.debug.depend.path=usr/kernel/exec pkg.debug.depend.reason=usr/kernel/brand/s10_brand pkg.debug.depend.type=elf type=require
depend fmri=__TBD pkg.debug.depend.file=elfexec pkg.debug.depend.path=kernel/exec/amd64 pkg.debug.depend.path=platform/i86hvm/kernel/exec/amd64 pkg.debug.depend.path=platform/i86pc/kernel/exec/amd64 pkg.debug.depend.path=platform/i86xpv/kernel/exec/amd64 pkg.debug.depend.path=usr/kernel/exec/amd64 pkg.debug.depend.reason=usr/kernel/brand/amd64/s10_brand pkg.debug.depend.type=elf type=require
"""
        installed_double_provides = """\
open double_provides@1.0,5.11-0
add file tmp/foo group=sys mode=0755 owner=root path=kernel/exec/amd64/elfexec reboot-needed=true variant.opensolaris.zone=global
add file tmp/foo group=sys mode=0755 owner=root path=kernel/exec/elfexec reboot-needed=true variant.opensolaris.zone=global
close"""

        newer_double_provides = """\
set name=pkg.fmri value=double_provides@1.0,5.11-1
file NOHASH group=sys mode=0755 owner=root path=kernel/exec/amd64/elfexec reboot-needed=true variant.opensolaris.zone=global
file NOHASH group=sys mode=0755 owner=root path=kernel/exec/elfexec reboot-needed=true variant.opensolaris.zone=global
"""

        bug_16849_missing_build_version = """
set name=pkg.fmri value=pkg:/foo/bar@2.0.0
file NOHASH group=sys mode=0644 owner=root path=var/log/syslog
"""

        bug_16849_corrupted_version = """
set name=pkg.fmri value=pkg:/foo/bar@__whee__,5.11-1
file NOHASH group=sys mode=0644 owner=root path=var/log/syslog
"""

        bug_16849_leading_zeros = """
set name=pkg.fmri value=pkg:/foo/bar@2.06
file NOHASH group=sys mode=0644 owner=root path=var/log/syslog
"""

        bug_16849_depender = """
set name=pkg.fmri value=depender
depend fmri=__TBD pkg.debug.depend.file=var/log/syslog pkg.debug.depend.reason=usr/bar pkg.debug.depend.type=hardlink type=require
"""

        bug_17700_dep = """\
set name=pkg.fmri value=b17700_dep@1.0,5.11-1
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=sparc value=i386
depend fmri=__TBD pkg.debug.depend.file=bignum pkg.debug.depend.path=kernel/misc/sparcv9 pkg.debug.depend.path=platform/sun4u/kernel/misc/sparcv9 pkg.debug.depend.path=platform/sun4v/kernel/misc/sparcv9 pkg.debug.depend.path=usr/kernel/misc/sparcv9 pkg.debug.depend.reason=kernel/drv/sparcv9/emlxs pkg.debug.depend.type=elf type=require variant.arch=sparc variant.opensolaris.zone=global
"""
        bug_17700_res1 = """\
set name=pkg.fmri value=system/kernel@1.0,5.11-1
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=sparc value=i386
file NOHASH group=bin mode=0755 owner=root path=kernel/misc/sparcv9/bignum variant.arch=sparc variant.opensolaris.zone=global
"""

        installed_17700_res1 = """\
open system/kernel@1.0,5.11-1
add set name=variant.opensolaris.zone value=global value=nonglobal
add set name=variant.arch value=sparc value=i386
add file tmp/foo group=bin mode=0755 owner=root path=kernel/misc/sparcv9/bignum variant.arch=sparc variant.opensolaris.zone=global
close
"""

        bug_17700_res2 = """\
set name=pkg.fmri value=system/kernel/platform@1.0,5.11-1
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=sparc value=i386
file NOHASH group=bin mode=0755 owner=root path=platform/sun4u/kernel/misc/sparcv9/bignum variant.arch=sparc variant.opensolaris.zone=global
"""

        installed_17700_res2 = """\
open system/kernel/platform@1.0,5.11-1
add set name=variant.opensolaris.zone value=global value=nonglobal
add set name=variant.arch value=sparc value=i386
add file tmp/foo group=bin mode=0755 owner=root path=platform/sun4u/kernel/misc/sparcv9/bignum variant.arch=sparc variant.opensolaris.zone=global
close
"""

        # there's a single variant.arch value set here,
        # but no variant.opensolaris.zone values
        installed_18045 = """\
open runtime/python26@2.6.4,5.11-0.161
add set name=variant.foo value=i386
add file tmp/foo group=bin mode=0755 owner=root path=usr/bin/python
close
"""
        # a file dependency that declares variant.opensolaris.zone values
        bug_18045_dep = """
set name=pkg.fmri value=system/kernel/platform@1.0,5.11-1
set name=variant.foo value=i386
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=python pkg.debug.depend.path=usr/bin type=require
"""

        # there's a single variant.arch value set here,
        # and variant.opensolaris.zone values
        installed_18045_reverse = """\
open runtime/python26@2.6.4,5.11-0.161
add set name=variant.foo value=i386
add set name=variant.opensolaris.zone value=global value=nonglobal
add file tmp/foo group=bin mode=0755 owner=root path=usr/bin/python
close
"""
        # a file dependency that doesn't declare variant.opensolaris.zone values
        bug_18045_dep_reverse = """
set name=pkg.fmri value=system/kernel/platform@1.0,5.11-1
set name=variant.foo value=i386
depend fmri=__TBD pkg.debug.depend.file=python pkg.debug.depend.path=usr/bin type=require
"""

        # there's a single variant.arch value set here,
        # but no variant.opensolaris.zone values
        installed_18045_mixed = """\
open runtime/python26@2.6.4,5.11-0.161
add set name=variant.foo value=i386
add file tmp/foo group=bin mode=0755 owner=root path=usr/bin/python
close
"""
        # a file dependency that only declares variant.opensolaris.zone values
        bug_18045_dep_mixed = """
set name=pkg.fmri value=system/kernel/platform@1.0,5.11-1
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=python pkg.debug.depend.path=usr/bin type=require
"""

        bug_18130_dep = """\
depend fmri=__TBD pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
"""

        bug_18130_provider_1 = """\
set name=pkg.fmri value=provider@1.0,5.11-1
set name=variant.arch value=i386 value=sparc
set name=variant.opensolaris.zone value=global value=nonglobal
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386
"""

        bug_18130_provider_2 = """\
set name=pkg.fmri value=provider@1.0,5.11-1
set name=variant.arch value=i386 value=sparc
set name=variant.opensolaris.zone value=global value=nonglobal
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=global
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=nonglobal
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=nonglobal
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=global
"""

        bug_18130_provider_3_1 = """\
set name=pkg.fmri value=provider1@1.0,5.11-1
set name=variant.arch value=i386 value=sparc
set name=variant.opensolaris.zone value=global value=nonglobal
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=global
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=nonglobal
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=nonglobal
"""

        bug_18130_provider_3_2 = """\
set name=pkg.fmri value=provider2@1.0,5.11-1
set name=variant.arch value=i386 value=sparc
set name=variant.opensolaris.zone value=global value=nonglobal
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=global
"""

        bug_18130_provider_4 = """\
set name=pkg.fmri value=provider1@1.0,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.debug value=True value=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=nonglobal variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=nonglobal variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=nonglobal variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=global variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=nonglobal variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=global variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=nonglobal variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=global variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=nonglobal variant.debug=False
"""

        bug_18130_provider_5_1 = """\
set name=pkg.fmri value=provider1@1.0,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.debug value=True value=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=nonglobal variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=nonglobal variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=nonglobal variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=global variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=nonglobal variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=global variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=nonglobal variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=global variant.debug=False
"""

        bug_18130_provider_5_2 = """\
set name=pkg.fmri value=provider2@1.0,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.debug value=True value=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=nonglobal variant.debug=False
"""

        bug_18130_provider_6_1 = """\
set name=pkg.fmri value=provider1@1.0,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.debug value=True value=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=nonglobal variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=nonglobal variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=nonglobal variant.debug=True
"""

        bug_18130_provider_6_2 = """\
set name=pkg.fmri value=provider2@1.0,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.debug value=True value=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=nonglobal variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=nonglobal variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=global variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=nonglobal variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=global variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=global variant.debug=False
"""

        bug_18130_provider_7_1 = """\
set name=pkg.fmri value=provider1@1.0,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.debug value=True value=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=nonglobal variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=nonglobal variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=global variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=nonglobal variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=global variant.debug=False
"""

        bug_18130_provider_7_2 = """\
set name=pkg.fmri value=provider2@1.0,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.debug value=True value=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=nonglobal variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=sparc variant.opensolaris.zone=global variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=i386 variant.opensolaris.zone=nonglobal variant.debug=False
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=global variant.debug=True
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.arch=foo variant.opensolaris.zone=nonglobal variant.debug=False
"""

        bug_18172_top = """\
set name=pkg.fmri value=top@0.5.11,5.11-1
depend fmri=__TBD pkg.debug.depend.file=ksh pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=usr/lib/brand/shared/dsconvert pkg.debug.depend.type=script type=require
"""
        bug_18172_l1 = """\
set name=pkg.fmri value=ksh@0.5.11,5.11-1
link path=usr/bin/ksh target=../../usr/lib/l1
"""
        bug_18172_l2 = """\
set name=pkg.fmri value=l2@0.5.11,5.11-1
link path=usr/lib/l1 target=l2
"""
        bug_18172_l3 = """\
set name=pkg.fmri value=l3@0.5.11,5.11-1
link path=usr/lib/l2 target=isaexec
"""
        bug_18172_dest = """\
set name=pkg.fmri value=dest@0.5.11,5.11-1
file tmp/foo path=usr/lib/isaexec
"""

        bug_18173_cs_1 = """\
open cs@0.5.11,5.11-1
add set name=pkg.fmri value=cs@0.5.11,5.11-1
add file NOHASH path=usr/lib/isaexec mode=0755 owner=root group=sys

add link path=usr/sbin/sh target=../bin/i86/ksh93
add hardlink path=usr/bin/ksh target=../../usr/lib/isaexec
close
"""

        bug_18173_cs_2 = """\
set name=pkg.fmri value=cs@0.5.11,5.11-2
file tmp/foo path=usr/lib/isaexec
"""

        bug_18173_ksh = """\
set name=pkg.fmri value=ksh@0.5.11,5.11-2
hardlink path=usr/bin/ksh target=../../usr/lib/isaexec
depend fmri=__TBD pkg.debug.depend.file=isaexec pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=usr/bin/ksh pkg.debug.depend.type=hardlink type=require
"""

        bug_18173_zones = """\
set name=pkg.fmri value=zones@0.5.11,5.11-2
file NOHASH path=usr/lib/brand/shared/dsconvert mode=0755
depend fmri=__TBD pkg.debug.depend.file=ksh pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=usr/lib/brand/shared/dsconvert pkg.debug.depend.type=script type=require
"""

        bug_18315_link1_manf = """ \
set name=pkg.fmri value=link1@1,5.11-1
link path=lib/64 target=amd64
"""

        bug_18315_link2_manf = """ \
set name=pkg.fmri value=link2@1,5.11-1
link path=lib/64 target=amd64
"""

        bug_18315_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
"""

        bug_18315_dependee_manf = """ \
set name=pkg.fmri value=dependee@1,5.11-1
file NOHASH path=lib/amd64/libc.so.1
"""

        bug_18315_var_link1_manf = """ \
set name=pkg.fmri value=link1@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
link path=lib/64 target=amd64 variant.arch=i386
link path=lib/64 target=amd64 variant.arch=sparc
"""

        bug_18315_var_link2_manf = """ \
set name=pkg.fmri value=link2@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
link path=lib/64 target=amd64 variant.arch=i386
link path=lib/64 target=amd64 variant.arch=sparc
"""

        bug_18315_var_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
"""

        bug_18315_var_dependee_manf = """ \
set name=pkg.fmri value=dependee@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
file NOHASH path=lib/amd64/libc.so.1
"""

        bug_18315_var_link3_manf = """ \
set name=pkg.fmri value=link3@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
link path=lib/64 target=amd64 variant.arch=i386
"""

        bug_18315_var_link4_manf = """ \
set name=pkg.fmri value=link4@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
link path=lib/64 target=amd64 variant.arch=i386 variant.opensolaris.zone=global
"""

        bug_18315_var_link5_manf = """ \
set name=pkg.fmri value=link5@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
link path=lib/64 target=amd64 variant.arch=foo
"""

        misc_files = ["tmp/foo"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

                self.image_create(self.rurl)
                self.api_obj = self.get_img_api_obj()

        def test_broken_manifests(self):
                """Test that resolving manifests which have strange or
                unexpected depend actions doesn't cause a traceback."""

                bad_require_dep_manf = """\
set name=pkg.fmri value=badreq@1,5.11
depend fmri=pkg://// type=require
"""
                m1_path = self.make_manifest(bad_require_dep_manf)
                pkg_deps, errs = dependencies.resolve_deps([m1_path],
                    self.api_obj)
                self.assertEqual(len(errs), 1)
                err_text = """\
The package pkg:/badreq@1,5.11 contains depend actions with values in their fmri attributes which are not valid fmris.  The bad values are:
	pkg:////
"""
                self.assertEqualDiff(err_text, str(errs[0]))

                bad_require_any_dep_manf = """\
depend fmri=example_pkg fmri=pkg://////// fmri=pkg://// type=require-any
"""
                m1_path = self.make_manifest(bad_require_any_dep_manf)
                pkg_deps, errs = dependencies.resolve_deps([m1_path],
                    self.api_obj)
                self.assertEqual(len(errs), 1)
                err_text = """\
The package %s contains depend actions with values in their fmri attributes which are not valid fmris.  The bad values are:
	pkg:////
	pkg:////////
"""
                self.assertEqualDiff(err_text % os.path.basename(m1_path),
                    str(errs[0]))

        def test_resolve_permissions(self):
                """Test that a manifest that pkgdepend resolve can't access
                doesn't cause a traceback."""

                m1_path = self.make_manifest(self.hardlink1_manf_deps)
                self.pkgdepend_resolve("-m %s" % m1_path, su_wrap=True, exit=1)

        def test_resolve_cross_package(self):
                """test that cross dependencies between published packages
                works."""

                m1_path = self.make_manifest(self.hardlink1_manf_deps)
                m2_path = self.make_manifest(self.hardlink2_manf_deps)
                p1_name = 'pkg:/%s' % os.path.basename(m1_path)
                p2_name = 'pkg:/%s' % os.path.basename(m2_path)
                pkg_deps, errs = dependencies.resolve_deps(
                    [m1_path, m2_path], self.api_obj)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[m1_path]), 1)
                self.assertEqual(len(pkg_deps[m1_path][0].attrs["%s.reason" %
                    base.Dependency.DEPEND_DEBUG_PREFIX]), 2)
                self.assertEqual(len(pkg_deps[m2_path]), 1)
                for d in pkg_deps[m1_path]:
                        self.assertEqual(d.attrs["fmri"], p2_name)
                for d in pkg_deps[m2_path]:
                        self.assertEqual(d.attrs["fmri"], p1_name)

        def test_resolve_mix(self):
                """Test that resolving against both packages installed on the
                image and packages works for the same package and that the
                resolver picks up the name of the package if it's defined in
                the package."""

                self.pkgsend_bulk(self.rurl, self.inst_pkg)
                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["example2_pkg"])

                m1_path = self.make_manifest(self.multi_deps)
                m2_path = self.make_manifest(self.misc_manf)
                p3_name = "pkg:/example2_pkg@1.0-0"
                p2_name = "pkg:/footest@0.5.11-0.117"

                pkg_deps, errs = dependencies.resolve_deps(
                    [m1_path, m2_path], self.api_obj)
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[m1_path]), 2)
                self.assertEqual(len(pkg_deps[m2_path]), 0)
                self.assertEqual(len(errs), 0)
                for d in pkg_deps[m1_path]:
                        if d.attrs["fmri"] == p2_name:
                                self.assertEqual(
                                    d.attrs["%s.file" % self.depend_dp],
                                    ["usr/lib/python2.6/v-p/pkg/misc.py"])
                        elif d.attrs["fmri"] == p3_name:
                                self.assertEqual(
                                    d.attrs["%s.file" % self.depend_dp],
                                    ["usr/bin/python2.6"])
                        else:
                                raise RuntimeError("Got unexpected fmri "
                                    "%s for in dependency %s" %
                                    (d.attrs["fmri"], d))

                # Check that with use_system set to false, the system is not
                # resolved against.  Bug 15777
                pkg_deps, errs = dependencies.resolve_deps(
                    [m1_path, m2_path], self.api_obj, use_system=False)
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[m1_path]), 1)
                self.assertEqual(len(pkg_deps[m2_path]), 0)
                self.assertEqual(len(errs), 1)
                for d in pkg_deps[m1_path]:
                        if d.attrs["fmri"] == p2_name:
                                self.assertEqual(
                                    d.attrs["%s.file" % self.depend_dp],
                                    ["usr/lib/python2.6/v-p/pkg/misc.py"])
                        elif d.attrs["fmri"] == p3_name:
                                self.assertEqual(
                                    d.attrs["%s.file" % self.depend_dp],
                                    ["usr/bin/python2.6"])
                        else:
                                raise RuntimeError("Got unexpected fmri "
                                    "%s for in dependency %s" %
                                    (d.attrs["fmri"], d))
                for e in errs:
                        if isinstance(e,
                            dependencies.UnresolvedDependencyError):
                                self.assertEqual(e.path, m1_path)
                                self.assertEqual(e.file_dep.attrs[
                                    "%s.file" % self.depend_dp],
                                    "usr/bin/python2.6")
                        else:
                                raise RuntimeError("Unexpected error:%s" % e)

        def test_simple_variants_1(self):
                """Test that variants declared on the actions work correctly
                when resolving dependencies."""

                m1_path = self.make_manifest(self.simple_variant_deps)
                m2_path = self.make_manifest(self.simple_v_deps_bar)
                m3_path = self.make_manifest(self.simple_v_deps_baz)
                p2_name = "s-v-bar"
                p3_name = "s-v-baz"
                pkg_deps, errs = dependencies.resolve_deps(
                    [m1_path, m2_path, m3_path], self.api_obj)
                for d in pkg_deps[m1_path]:
                        if d.attrs["fmri"] == "pkg:/s-v-bar":
                                self.assertEqual(
                                    d.attrs["variant.foo"],
                                    "bar")
                        elif d.attrs["fmri"] == "pkg:/s-v-baz":
                                self.assertEqual(
                                    d.attrs["variant.foo"],
                                    "baz")
                        else:
                                raise RuntimeError("Unexpected fmri %s "
                                    "for dependency %s" %
                                    (d.attrs["fmri"], d))
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join([
                            "%s" % (e,) for e in errs]))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[m1_path]), 2)
                self.assertEqual(len(pkg_deps[m2_path]), 0)
                self.assertEqual(len(pkg_deps[m3_path]), 0)

        def test_simple_variants_2 (self):
                """Test that variants declared on the packages work correctly
                when resolving dependencies."""

                m1_path = self.make_manifest(self.simple_variant_deps)
                m2_path = self.make_manifest(self.simple_v_deps_bar2)
                m3_path = self.make_manifest(self.simple_v_deps_baz2)
                p2_name = "s-v-bar"
                p3_name = "s-v-baz"
                pkg_deps, errs = dependencies.resolve_deps(
                    [m1_path, m2_path, m3_path], self.api_obj)
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[m1_path]), 2)
                self.assertEqual(len(pkg_deps[m2_path]), 0)
                self.assertEqual(len(pkg_deps[m3_path]), 0)
                self.assertEqual(len(errs), 0)
                for d in pkg_deps[m1_path]:
                        if d.attrs["fmri"] == "pkg:/s-v-bar":
                                self.assertEqual(
                                    d.attrs["variant.foo"],
                                    "bar")
                        elif d.attrs["fmri"] == "pkg:/s-v-baz":
                                self.assertEqual(
                                    d.attrs["variant.foo"],
                                    "baz")
                        else:
                                raise RuntimeError("Unexpected fmri %s "
                                    "for dependency %s" %
                                    (d.attrs["fmri"], d))

        def test_two_variants (self):
                """Test that variants declared on the packages work correctly
                when resolving dependencies."""

                m1_path = self.make_manifest(self.two_variant_deps)
                m2_path = self.make_manifest(self.two_v_deps_bar)
                m3_path = self.make_manifest(self.two_v_deps_baz_one)
                m4_path = self.make_manifest(self.two_v_deps_baz_two)
                p2_name = "s-v-bar"
                p3_name = "s-v-baz-one"
                p4_name = "s-v-baz-two"
                pkg_deps, errs = dependencies.resolve_deps(
                    [m1_path, m2_path, m3_path, m4_path], self.api_obj)
                self.assertEqual(len(pkg_deps), 4)
                # This is 5 because the variant.num values are not collapsed
                # like they could be.
                self.assertEqual(len(pkg_deps[m1_path]), 3)
                self.assertEqual(len(pkg_deps[m2_path]), 0)
                self.assertEqual(len(pkg_deps[m3_path]), 0)
                self.assertEqual(len(pkg_deps[m4_path]), 0)
                self.assertEqual(len(errs), 1)
                for d in pkg_deps[m1_path]:
                        if d.attrs["fmri"] == "pkg:/s-v-bar":
                                self.assertEqual(
                                    d.attrs["variant.foo"],
                                    "bar")
                                self.assert_("variant.num" not in d.attrs)
                        elif d.attrs["fmri"] == "pkg:/s-v-baz-one":
                                self.assertEqual(
                                    d.attrs["variant.foo"],
                                    "baz")
                                self.assertEqual(
                                    d.attrs["variant.num"],
                                    "one")
                        elif d.attrs["fmri"] == "pkg:/s-v-baz-two":
                                self.assertEqual(
                                    d.attrs["variant.foo"],
                                    "baz")
                                self.assertEqual(
                                    d.attrs["variant.num"],
                                    "two")
                        else:
                                raise RuntimeError("Unexpected fmri %s "
                                    "for dependency %s" %
                                    (d.attrs["fmri"], d))

        def test_multi_file_dependencies(self):
                """This checks manifests with multiple files, both with
                pkg.debug.depend.file/path combinations, as well as
                with pkg.debug.depend.fullpath lists."""
                def __check_results(pkg_deps, errs, exp_pkg, no_deps, one_dep):
                        if errs:
                                raise RuntimeError("Got the following "
                                    "unexpected errors:\n%s" %
                                    "\n".join([str(e) for e in errs]))
                        self.assertEqual(len(pkg_deps), 2)
                        self.assertEqual(len(pkg_deps[no_deps]), 0)
                        if len(pkg_deps[one_dep]) != 1:
                                raise RuntimeError("Got more than one "
                                    "dependency:\n%s" %
                                    "\n".join(
                                        [str(d) for d in pkg_deps[one_dep]]))
                        d = pkg_deps[one_dep][0]
                        self.assertEqual(d.attrs["fmri"], exp_pkg)

                col_path = self.make_manifest(self.multi_file_dep_manf)
                # the following manifest is logically equivalent to col_path
                col_fullpath_path = self.make_manifest(self.multi_file_dep_manf)
                # This manifest provides two files that satisfy col*_path's
                # file dependencies.
                both_path = self.make_manifest(self.multi_file_sat_both)
                # This manifest provides a file that satisfies the dependency
                # in col*_path by delivering a py or pyc file..
                py_path = self.make_manifest(self.multi_file_sat_py)
                pyc_path = self.make_manifest(self.multi_file_sat_pyc)

                # The following tests should all succeed because either the same
                # package delivers both files which could satisfy the dependency
                # or only one package which delivers the dependency is being
                # resolved against.
                for mf_path in [col_path, col_fullpath_path]:
                        pkg_deps, errs = dependencies.resolve_deps(
                            [mf_path, both_path], self.api_obj)
                        __check_results(pkg_deps, errs, "pkg:/sat_both",
                            both_path, mf_path)

                        pkg_deps, errs = dependencies.resolve_deps(
                            [mf_path, py_path], self.api_obj)
                        __check_results(pkg_deps, errs, "pkg:/sat_py", py_path,
                            mf_path)

                        pkg_deps, errs = dependencies.resolve_deps(
                            [mf_path, pyc_path], self.api_obj)
                        __check_results(pkg_deps, errs, "pkg:/sat_pyc",
                            pyc_path, mf_path)

                        # This resolution should fail because files which
                        # satisfy the dependency are delivered in two packages.
                        pkg_deps, errs = dependencies.resolve_deps(
                            [mf_path, py_path, pyc_path], self.api_obj)
                        self.assertEqual(len(pkg_deps), 3)
                        for k in pkg_deps:
                                if pkg_deps[k]:
                                        raise RuntimeError("Got the following "
                                            "unexpected dependencies:\n%s" %
                                            "\n".join(["%s\n%s" %
                                                (k,"\n".join([
                                                    "\t%s" % d for d in pkg_deps[k]]))
                                                    for k in pkg_deps
                                                ]))
                        if len(errs) != 2:
                                raise RuntimeError("Didn't get two "
                                    "errors:\n%s" %
                                    "\n".join(str(e) for e in errs))
                        for e in errs:
                                if isinstance(e,
                                    dependencies.MultiplePackagesPathError):
                                        for d in e.res:
                                                if d.attrs["fmri"] not in \
                                                    ("pkg:/sat_py",
                                                    "pkg:/sat_pyc"):
                                                        raise RuntimeError(
                                                            "Unexpected "
                                                            "dependency "
                                                            "action:%s" % d)
                                        self.assertEqual(
                                            e.source.attrs["%s.file" %
                                                self.depend_dp],
                                            ["search_storage.py",
                                            "search_storage.pyc",
                                            "search_storage/__init__.py"])
                                        self.assertEqual(
                                            os.path.basename(mf_path),
                                            e.pkg_name)
                                elif isinstance(e,
                                    dependencies.UnresolvedDependencyError):
                                        self.assertEqual(e.path, mf_path)
                                        self.assertEqual(
                                            e.file_dep.attrs[
                                                "%s.file" % self.depend_dp],
                                            ["search_storage.py",
                                            "search_storage.pyc",
                                            "search_storage/__init__.py"])
                                else:
                                        raise RuntimeError(
                                            "Unexpected error:%s" % e)

        def test_bug_11518(self):
                """Test that resolving against an installed, cached, manifest
                works with variants."""

                self.pkgsend_bulk(self.rurl, self.var_pkg)
                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["variant_pkg"])

                m1_path = self.make_manifest(self.simp_manf)
                p2_name = "pkg:/variant_pkg@1.0-0"

                pkg_deps, errs = dependencies.resolve_deps(
                    [m1_path], self.api_obj)
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[m1_path]), 1)
                self.assertEqual(len(errs), 0)
                for d in pkg_deps[m1_path]:
                        if d.attrs["fmri"] == p2_name:
                                self.assertEqual(
                                    d.attrs["%s.file" % self.depend_dp],
                                    ["var/log/syslog"])
                        else:
                                raise RuntimeError("Was expecting %s, got fmri "
                                    "%s for dependency %s" %
                                    (p2_name, d.attrs["fmri"], d))

        def test_bug_12697_and_12896(self):
                """Test that pkgdep resolve handles multiple run path
                dependencies correctly when the files are delivered in the same
                package and when the files are delivered in different packages.
                """

                def __check_results(pkg_deps, errs, exp_pkg, no_deps, one_dep):
                        if errs:
                                raise RuntimeError("Got the following "
                                    "unexpected errors:\n%s" %
                                    "\n".join([str(e) for e in errs]))
                        self.assertEqual(len(pkg_deps), 2)
                        self.assertEqual(len(pkg_deps[no_deps]), 0)
                        if len(pkg_deps[one_dep]) != 1:
                                raise RuntimeError("Got more than one "
                                    "dependency:\n%s" %
                                    "\n".join(
                                        [str(d) for d in pkg_deps[col_path]]))
                        d = pkg_deps[one_dep][0]
                        self.assertEqual(d.attrs["fmri"], exp_pkg)

                col_path = self.make_manifest(self.collision_manf)
                col_path_num_var = self.make_manifest(
                    self.collision_manf_num_var)
                # This manifest provides both files that satisfy col_path's
                # dependencies.
                both_path = self.make_manifest(self.sat_both)
                # This manifest provides a file that satisfies the dependency
                # in col_path by delivering a file in patform/bar/baz/.
                bar_path = self.make_manifest(self.sat_bar_libc)
                bar2_path = self.make_manifest(self.sat_bar_libc2)
                # This manifest provides a file that satisfies the dependency
                # in col_path by delivering a file in patform/foo/baz/.
                foo_path = self.make_manifest(self.sat_foo_libc)
                # This manifest provides a file that satisfies the dependency
                # in col_path by delivering a file in patform/bar/baz/, but that
                # file is tagged with variant.num=one.
                bar_path_num_var = self.make_manifest(self.sat_bar_libc_num_var)
                # This manifest provides a file that satisfies the dependency
                # in col_path by delivering a file in patform/foo/baz/, but that
                # file is tagged with variant.num=two.
                foo_path_num_var = self.make_manifest(self.sat_foo_libc_num_var)
                # This manifest provides a file that satisfies the dependency
                # in col_path by delivering a file in patform/foo/baz/, but that
                # file is tagged with variant.num=one and variant.num=two.
                foo_path_num_var_both = self.make_manifest(
                    self.sat_foo_libc_num_var_both)

                # The following tests should all succeed because either the same
                # package delivers both files which could satisfy the dependency
                # or only one package which delivers the dependency is being
                # resolved against.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, both_path], self.api_obj)
                __check_results(pkg_deps, errs, "pkg:/sat_both", both_path,
                    col_path)

                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, bar_path], self.api_obj)
                __check_results(pkg_deps, errs, "pkg:/sat_bar_libc", bar_path,
                    col_path)

                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, foo_path], self.api_obj)
                __check_results(pkg_deps, errs, "pkg:/sat_foo_libc", foo_path,
                    col_path)

                # This test should also pass because the dependencies will be
                # variant tagged, just as the file delivery is.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path_num_var, foo_path_num_var, bar_path_num_var],
                    self.api_obj)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" %
                            "\n".join([str(e) for e in errs]))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[foo_path_num_var]), 0)
                self.assertEqual(len(pkg_deps[bar_path_num_var]), 0)
                self.assertEqual(len(pkg_deps[col_path_num_var]), 2)
                for d in pkg_deps[col_path_num_var]:
                        if d.attrs["fmri"] not in \
                            ("pkg:/sat_foo_libc", "pkg:/sat_bar_libc"):
                                raise RuntimeError("Unexpected fmri in %s" % d)

                # This resolution should fail because in the case of
                # variant.num=one, files which satisfy the dependency are
                # delivered in two packages.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path_num_var, foo_path_num_var_both, bar_path_num_var],
                    self.api_obj)
                self.assertEqual(len(pkg_deps), 3)
                for k in pkg_deps:
                        if pkg_deps[k]:
                                raise RuntimeError("Got the following "
                                    "unexpected dependencies:\n%s" %
                                    "\n".join(["%s\n%s" %
                                        (k,"\n".join([
                                            "\t%s" % d for d in pkg_deps[k]]))
                                            for k in pkg_deps
                                        ]))
                if len(errs) != 2:
                        raise RuntimeError("Didn't get two errors:\n%s" %
                            "\n".join(str(e) for e in errs))
                for e in errs:
                        if isinstance(e,
                            dependencies.MultiplePackagesPathError):
                                for d in e.res:
                                        if d.attrs["fmri"] not in \
                                            ("pkg:/sat_foo_libc",
                                            "pkg:/sat_bar_libc"):
                                                raise RuntimeError("Unexpected "
                                                    "dependency action:%s" % d)
                                self.assertEqual(
                                    e.source.attrs["%s.file" % self.depend_dp],
                                    "no_such_named_file")
                                self.assertEqual("pkg:/collision_manf",
                                    e.pkg_name)
                        elif isinstance(e,
                            dependencies.UnresolvedDependencyError):
                                self.assertEqual(e.path, col_path_num_var)
                                self.assertEqual(
                                    e.file_dep.attrs[
                                        "%s.file" % self.depend_dp],
                                    "no_such_named_file")
                        else:
                                raise RuntimeError("Unexpected error:%s" % e)

                # This resolution should fail because files which satisfy the
                # dependency are being delivered in two packages.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, bar_path, foo_path], self.api_obj)
                self.assertEqual(len(pkg_deps), 3)
                for k in pkg_deps:
                        if pkg_deps[k]:
                                raise RuntimeError("Got the following "
                                    "unexpected dependencies:\n%s" %
                                    "\n".join(["%s\n%s" %
                                        (k,"\n".join([
                                            "\t%s" % d for d in pkg_deps[k]]))
                                            for k in pkg_deps
                                        ]))
                if len(errs) != 2:
                        raise RuntimeError("Didn't get two errors:\n%s" %
                            "\n".join(str(e) for e in errs))
                for e in errs:
                        if isinstance(e,
                            dependencies.MultiplePackagesPathError):
                                for d in e.res:
                                        if d.attrs["fmri"] not in \
                                            ("pkg:/sat_foo_libc",
                                            "pkg:/sat_bar_libc"):
                                                raise RuntimeError("Unexpected "
                                                    "dependency action:%s" % d)
                                self.assertEqual(
                                    e.source.attrs["%s.file" % self.depend_dp],
                                    "no_such_named_file")
                                self.assertEqual("pkg:/collision_manf",
                                    e.pkg_name)
                        elif isinstance(e,
                            dependencies.UnresolvedDependencyError):
                                self.assertEqual(e.path, col_path)
                                self.assertEqual(
                                    e.file_dep.attrs[
                                        "%s.file" % self.depend_dp],
                                    "no_such_named_file")
                        else:
                                raise RuntimeError("Unexpected error:%s" % e)

                # This resolution should fail because files which satisfy the
                # dependency are being delivered in two packages.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, bar_path, bar2_path], self.api_obj)
                self.assertEqual(len(pkg_deps), 3)
                for k in pkg_deps:
                        if pkg_deps[k]:
                                raise RuntimeError("Got the following "
                                    "unexpected dependencies:\n%s" %
                                    "\n".join(["%s\n%s" %
                                        (k,"\n".join([
                                            "\t%s" % d for d in pkg_deps[k]]))
                                            for k in pkg_deps
                                        ]))
                if len(errs) != 2:
                        raise RuntimeError("Didn't get two errors:\n%s" %
                            "\n".join(str(e) for e in errs))
                for e in errs:
                        if isinstance(e,
                            dependencies.AmbiguousPathError):
                                for d in e.pkgs:
                                        if str(d) not in \
                                            ("pkg:/sat_bar_libc",
                                            "pkg:/sat_bar_libc2"):
                                                raise RuntimeError("Unexpected "
                                                    "dependency action:%s" % d)
                                self.assertEqual(
                                    e.source.attrs["%s.file" % self.depend_dp],
                                    "no_such_named_file")
                        elif isinstance(e,
                            dependencies.UnresolvedDependencyError):
                                self.assertEqual(e.path, col_path)
                                self.assertEqual(
                                    e.file_dep.attrs[
                                        "%s.file" % self.depend_dp],
                                    "no_such_named_file")
                        else:
                                raise RuntimeError("Unexpected error:%s" % e)

        def test_bug_15647(self):
                """Verify that in cases where both the provided manifests and
                installed image provide a resolution for a given dependency
                that the dependency is only resolved once for a given variant
                and that the resolution provided by the manifests is used."""

                self.pkgsend_bulk(self.rurl, self.installed_double_provides)
                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["double_provides"])

                manifests = [self.make_manifest(x) for x in
                    (self.newer_double_provides, self.double_deps)]

                pkg_deps, errs = dependencies.resolve_deps(manifests,
                    self.api_obj)

                self.assertEqual(len(pkg_deps[manifests[1]]), 1)
                for d in pkg_deps[manifests[1]]:
                        fmri = PkgFmri(d.attrs["fmri"], build_release="5.11")
                        if str(fmri).startswith("pkg:/double_provides"):
                                self.assertEqual(str(fmri.version.branch), "1")

        def test_bug_16849(self):
                """Test that when packages have bad fmris, or should resolve to
                depend on packages with bad fmris, pkgdep provides a reasonable
                error."""

                missing_build = self.make_manifest(
                    self.bug_16849_missing_build_version)
                corrupted_version = self.make_manifest(
                    self.bug_16849_corrupted_version)
                leading_zeros = self.make_manifest(
                    self.bug_16849_leading_zeros)
                depender = self.make_manifest(
                    self.bug_16849_depender)

                # This is a valid FMRI since bug 18243 was fixed.
                self.pkgdepend_resolve("-m %s" % missing_build)

                self.pkgdepend_resolve("-m %s" % corrupted_version, exit=1)
                self.pkgdepend_resolve("-m %s" % leading_zeros, exit=1)

                # This is a valid FMRI since bug 18243 was fixed.
                self.pkgdepend_resolve("-m %s %s" % (depender, missing_build))

                self.pkgdepend_resolve("-m %s %s" %
                    (corrupted_version, depender), exit=1)
                self.pkgdepend_resolve("-m %s %s" % (depender, leading_zeros),
                    exit=1)

        def test_bug_17700(self):
                """Test that when multiple packages satisfy a dependency under
                the same combination of two variants, that an error is reported
                instead of an assertion being raised."""

                self.pkgsend_bulk(self.rurl, self.installed_17700_res1)
                self.pkgsend_bulk(self.rurl, self.installed_17700_res2)
                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["system/kernel",
                    "system/kernel/platform"])
                dep_path = self.make_manifest(self.bug_17700_dep)
                res1_path = self.make_manifest(self.bug_17700_res1)
                res2_path = self.make_manifest(self.bug_17700_res2)

                pkg_deps, errs = dependencies.resolve_deps([dep_path,
                    res1_path, res2_path], self.api_obj)
                for k in pkg_deps:
                        self.assertEqual(len(pkg_deps[k]), 0,
                            "Should not have resolved any dependencies instead "
                            "%s had the following dependencies found:%s" %
                            (k, "\n".join([str(s) for s in pkg_deps[k]])))
                self.assertEqual(len(errs), 2, "Should have gotten exactly one "
                    "error, instead got:%s" % "\n".join([str(s) for s in errs]))
                for e in errs:
                        self.assert_(isinstance(e,
                            dependencies.MultiplePackagesPathError) or
                            isinstance(e,
                            dependencies.UnresolvedDependencyError))

        def test_bug_17756(self):
                """Test that when a package has manually specified dependencies
                which have a variant that's not set on the package or generates
                file dependencies with a variant that's not set on the package,
                pkgdepend resolve handles the error and displays it
                correctly."""

                def __check_generated(e):
                        self.assertEqual("test17756", e.pkg.pkg_name)
                        self.assertEqual(["usr/bin/foo", "usr/bin/ls"],
                            sorted(e.rvs.keys()))
                        d = e.rvs["usr/bin/foo"]
                        self.assertEqual(set(), d.type_diffs)
                        self.assertEqual(set([("variant.num", "two")]),
                            d.value_diffs)
                        d = e.rvs["usr/bin/ls"]
                        self.assertEqual(set(["variant.foo"]), d.type_diffs)
                        self.assertEqual(set(
                            [("variant.num", "two"), ("variant.num", "three")]),
                            d.value_diffs)
                        str(e)

                def __check_manual(e):
                        self.assertEqual("test17756", e.pkg.pkg_name)
                        self.assertEqual(["pkg1", "pkg2"], sorted(e.rvs.keys()))
                        d = e.rvs["pkg1"]
                        self.assertEqual(set(), d.type_diffs)
                        self.assertEqual(set([("variant.num", "four")]),
                            d.value_diffs)
                        d = e.rvs["pkg2"]
                        self.assertEqual(set(["variant.foo"]), d.type_diffs)
                        self.assertEqual(set(), d.value_diffs)
                        str(e)

                dep_manf = """\
set name=pkg.fmri value=test17756@1,5.11
set name=variant.num value=one
depend fmri=__TBD pkg.debug.depend.file=libsec.so.1 pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=usr/bin/ls pkg.debug.depend.type=elf type=require variant.foo=bar
depend fmri=__TBD pkg.debug.depend.file=libcmdutils.so.1 pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=usr/bin/foo pkg.debug.depend.type=elf type=require variant.num=two
depend fmri=__TBD pkg.debug.depend.file=libcurses.so.1 pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=usr/bin/ls pkg.debug.depend.type=elf type=require variant.num=two
depend fmri=__TBD pkg.debug.depend.file=libnvpair.so.1 pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=usr/bin/ls pkg.debug.depend.type=elf type=require variant.num=three variant.foo=bar
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=usr/bin/ls pkg.debug.depend.type=elf type=require variant.foo=baz
depend fmri=pkg1 type=require variant.num=four
depend fmri=pkg2 type=require variant.foo=bar
"""
                manf_path = self.make_manifest(dep_manf)
                pkg_deps, errs = dependencies.resolve_deps([manf_path],
                    self.api_obj, use_system=False)
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[manf_path]), 0)
                self.assertEqual(len(errs), 2)
                if errs[0].manual:
                        __check_manual(errs[0])
                        __check_generated(errs[1])
                else:
                        __check_manual(errs[1])
                        __check_generated(errs[0])

        def test_bug_18019(self):
                """Test that a package with manually annotated group,
                incorporate, or other types of dependencies doesn't end up with
                two copies of any dependencies."""

                manf = ["set name=pkg.fmri value=bug_18019@1.0,5.11-1"]
                for t in depend.known_types:
                        manf.append("depend fmri=pkg:/%(type)s@0,5.11-1 "
                            "type=%(type)s" % {"type": t})
                manf_path = self.make_manifest("\n".join(manf))
                self.pkgdepend_resolve("-m %s" % manf_path)
                res_path = manf_path + ".res"
                with open(res_path, "r") as fh:
                        s = fh.read()
                s = s.splitlines()
                self.assertEqualDiff("\n".join(sorted(manf)),
                    "\n".join(sorted(s)))

        def test_bug_18045_normal(self):
                """Test that when a package without variants has a file
                dependency on a file in a package that declares variants,
                that dependency is satisfied."""

                self.pkgsend_bulk(self.rurl, self.installed_18045)
                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["runtime/python26"])
                dep_path = self.make_manifest(self.bug_18045_dep)

                pkg_deps, errs = dependencies.resolve_deps([dep_path],
                    self.api_obj)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join([
                            "%s" % (e,) for e in errs]))
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[dep_path]), 1)
                self.debug("fmri:%s" % pkg_deps[dep_path][0].attrs["fmri"])
                self.assert_(pkg_deps[dep_path][0].attrs["fmri"].startswith(
                    "pkg:/runtime/python26@2.6.4-0.161"))

        def test_bug_18045_reverse(self):
                """Test that when a package with variants has a file dependency
                on a file in a package that declares no variants, that
                dependency is satisfied."""

                self.pkgsend_bulk(self.rurl, self.installed_18045_reverse)
                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["runtime/python26"])
                dep_path = self.make_manifest(self.bug_18045_dep_reverse)

                pkg_deps, errs = dependencies.resolve_deps([dep_path],
                    self.api_obj)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join([
                            "%s" % (e,) for e in errs]))
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[dep_path]), 1)
                self.debug("fmri:%s" % pkg_deps[dep_path][0].attrs["fmri"])
                self.assert_(pkg_deps[dep_path][0].attrs["fmri"].startswith(
                    "pkg:/runtime/python26@2.6.4-0.161"))

        def test_bug_18045_mixed(self):
                """Test that when a package with variants has a file dependency
                on a file in a package that declares a different set of variant
                types, that dependency is satisfied."""

                self.pkgsend_bulk(self.rurl, self.installed_18045_mixed)
                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["runtime/python26"])
                dep_path = self.make_manifest(self.bug_18045_dep_mixed)

                pkg_deps, errs = dependencies.resolve_deps([dep_path],
                    self.api_obj)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join([
                            "%s" % (e,) for e in errs]))
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[dep_path]), 1)
                self.debug("fmri:%s" % pkg_deps[dep_path][0].attrs["fmri"])
                self.assert_(pkg_deps[dep_path][0].attrs["fmri"].startswith(
                    "pkg:/runtime/python26@2.6.4-0.161"))

        def test_bug_18077(self):
                """Test that a package with manually annotated group,
                incorporate, or other types of dependencies on the same package
                doesn't cause pkgdep resolve to traceback."""

                manf = ["set name=pkg.fmri value=bug_18077@1.0,5.11-1"]
                for t in depend.known_types:
                        manf.append("depend fmri=pkg:/foo@0,5.11-1 "
                            "type=%(type)s" % {"type": t})
                manf_path = self.make_manifest("\n".join(manf))
                self.pkgdepend_resolve("-m %s" % manf_path)
                res_path = manf_path + ".res"
                with open(res_path, "r") as fh:
                        s = fh.read()
                s = s.splitlines()
                self.assertEqualDiff("\n".join(sorted(
                    [l for l in manf if "require-any" not in l])),
                    "\n".join(sorted(s)))

        def test_bug_18130(self):
                """Test that dependency variants get collapsed where
                possible."""

                VA = "variant.arch"
                VOZ = "variant.opensolaris.zone"
                VD = "variant.debug"

                d_path = self.make_manifest(self.bug_18130_dep)

                # Test that a single variant with two values is collapsed
                # correctly.
                p_path = self.make_manifest(self.bug_18130_provider_1)
                pkg_deps, errs = dependencies.resolve_deps([d_path, p_path],
                    self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 1, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[d_path]]))
                for k in pkg_deps[d_path][0].attrs:
                        self.assert_(not k.startswith("variant."), "The "
                            "resulting dependency should not contain any "
                            "variants. The action is:\n%s" %
                            pkg_deps[d_path][0])

                # Test that combinations of two variant types works.
                p_path = self.make_manifest(self.bug_18130_provider_2)
                pkg_deps, errs = dependencies.resolve_deps([d_path, p_path],
                    self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 1, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[d_path]]))

                # Test that splitting the variants across two packages gives the
                # right simplification.
                p_path = self.make_manifest(self.bug_18130_provider_3_1)
                p2_path = self.make_manifest(self.bug_18130_provider_3_2)
                pkg_deps, errs = dependencies.resolve_deps(
                    [d_path, p_path, p2_path], self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[p2_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 3, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[d_path]]))
                got_prov_2 = False
                got_prov_1_i386 = False
                got_prov_1_sparc = False
                for d in pkg_deps[d_path]:
                        if d.attrs["fmri"].startswith("pkg:/provider2"):
                                self.assertEqual(d.attrs[VA], "i386")
                                self.assertEqual(d.attrs[VOZ], "global")
                                got_prov_2 = True
                        elif d.attrs["fmri"].startswith("pkg:/provider1"):
                                self.assert_(VA in d.attrs)
                                if d.attrs[VA] == "i386":
                                        self.assertEqual(d.attrs[VOZ],
                                            "nonglobal")
                                        got_prov_1_i386 = True
                                else:
                                        self.assertEqual(d.attrs[VA], "sparc")
                                        self.assert_(VOZ not in d.attrs)
                                        got_prov_1_sparc = True
                        else:
                                raise RuntimeError("Unexpected fmri seen:%s" %
                                    d)
                self.assert_(got_prov_2 and got_prov_1_i386 and
                    got_prov_1_sparc, "Got the right number of dependencies "
                    "but missed one of the expected ones. Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[d_path]]))

                # Test that when a variant combination is satisfied, it's
                # reported as being unresolved.
                p_path = self.make_manifest(self.bug_18130_provider_3_1)
                pkg_deps, errs = dependencies.resolve_deps([d_path, p_path],
                    self.api_obj, use_system=False)
                self.assertEqual(len(errs), 1)
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 2, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[d_path]]))

                # Test that variants with 3 values as well as a combination of
                # three variant types are collapsed correctly.
                p_path = self.make_manifest(self.bug_18130_provider_4)
                pkg_deps, errs = dependencies.resolve_deps([d_path, p_path],
                    self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 1, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[d_path]]))
                for k in pkg_deps[d_path][0].attrs:
                        self.assert_(not k.startswith("variant."), "The "
                            "resulting dependency should not contain any "
                            "variants. The action is:\n%s" %
                            pkg_deps[d_path][0])

                # Test all but one dependency satisfier in one file, and one in
                # another package.
                p_path = self.make_manifest(self.bug_18130_provider_5_1)
                p2_path = self.make_manifest(self.bug_18130_provider_5_2)
                pkg_deps, errs = dependencies.resolve_deps(
                    [d_path, p_path, p2_path], self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[p2_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 5, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[d_path]]))
                got_prov_2 = False
                got_prov_1_i386 = False
                got_prov_1_sparc = False
                got_prov_1_foo_debug = False
                got_prov_1_foo_nondebug_global = False
                for d in pkg_deps[d_path]:
                        if d.attrs["fmri"].startswith("pkg:/provider2"):
                                self.assertEqual(d.attrs[VA], "foo")
                                self.assertEqual(d.attrs[VOZ], "nonglobal")
                                self.assertEqual(d.attrs[VD], "False")
                                got_prov_2 = True
                        elif d.attrs["fmri"].startswith("pkg:/provider1"):
                                self.assert_(VA in d.attrs)
                                if d.attrs[VA] == "i386":
                                        self.assert_(VD not in d.attrs)
                                        self.assert_(VOZ not in d.attrs)
                                        got_prov_1_i386 = True
                                elif d.attrs[VA] == "sparc":
                                        self.assert_(VD not in d.attrs)
                                        self.assert_(VOZ not in d.attrs)
                                        got_prov_1_sparc = True
                                else:
                                        self.assertEqual(d.attrs[VA], "foo")
                                        if d.attrs[VD] == "True":
                                                self.assert_(VOZ not in d.attrs)
                                                got_prov_1_foo_debug = True
                                        else:
                                                self.assertEqual(d.attrs[VD],
                                                    "False")
                                                self.assertEqual(d.attrs[VOZ],
                                                    "global")
                                                got_prov_1_foo_nondebug_global = True
                        else:
                                raise RuntimeError("Unexpected fmri seen:%s" %
                                    d)
                self.assert_(got_prov_2 and got_prov_1_i386 and
                    got_prov_1_sparc and got_prov_1_foo_debug and
                    got_prov_1_foo_nondebug_global, "Got the right number "
                    "of dependencies but missed one of the expected ones. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[d_path]]))

                # Test that when two manifests split on debug, non-debug, the
                # variants are collapsed correctly.
                p_path = self.make_manifest(self.bug_18130_provider_6_1)
                p2_path = self.make_manifest(self.bug_18130_provider_6_2)
                pkg_deps, errs = dependencies.resolve_deps(
                    [d_path, p_path, p2_path], self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[p2_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 2, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[d_path]]))
                got_prov_2 = False
                got_prov_1 = False
                for d in pkg_deps[d_path]:
                        if d.attrs["fmri"].startswith("pkg:/provider2"):
                                self.assertEqual(d.attrs[VD], "False")
                                self.assert_(VOZ not in d.attrs)
                                self.assert_(VA not in d.attrs)
                                got_prov_2 = True
                        else:
                                self.assert_(d.attrs["fmri"].startswith(
                                    "pkg:/provider1"))
                                self.assertEqual(d.attrs[VD], "True")
                                self.assert_(VA not in d.attrs)
                                self.assert_(VOZ not in d.attrs)
                                got_prov_1 = True
                self.assert_(got_prov_2 and got_prov_1, "Got the right number "
                    "of dependencies but missed one of the expected ones. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[d_path]]))

                # Test that variants won't be combined when they shouldn't be.
                p_path = self.make_manifest(self.bug_18130_provider_7_1)
                p2_path = self.make_manifest(self.bug_18130_provider_7_2)
                pkg_deps, errs = dependencies.resolve_deps(
                    [d_path, p_path, p2_path], self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[p2_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 12, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[d_path]]))

        def test_bug_18172(self):
                """Test that the via-links attribute is set correctly when
                multiple packages deliver a chain of links."""

                top_path = self.make_manifest(self.bug_18172_top)
                l1_path = self.make_manifest(self.bug_18172_l1)
                l2_path = self.make_manifest(self.bug_18172_l2)
                l3_path = self.make_manifest(self.bug_18172_l3)
                dest_path = self.make_manifest(self.bug_18172_dest)

                pkg_deps, errs = dependencies.resolve_deps(
                    [top_path, l1_path, l2_path, l3_path, dest_path],
                    self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 5)
                self.assertEqual(len(pkg_deps[dest_path]), 0)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[l3_path]), 0)
                self.assertEqual(len(pkg_deps[top_path]), 4,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[top_path]]))
                got_top = False
                got_l1 = False
                got_l2 = False
                got_l3 = False
                for d in pkg_deps[top_path]:
                        pfmri = d.attrs["fmri"]
                        if pfmri.startswith("pkg:/dest"):
                                self.assertEqual(
                                    d.attrs[dependencies.files_prefix],
                                    ["usr/lib/isaexec"])
                                self.assertEqual(
                                    d.attrs[dependencies.via_links_prefix],
                                    "usr/bin/ksh:usr/lib/l1:usr/lib/l2")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "script")
                                got_top = True
                        elif pfmri.startswith("pkg:/ksh"):
                                got_l1 = True
                        elif pfmri.startswith("pkg:/l2"):
                                got_l2 = True
                        else:
                                self.assert_(pfmri.startswith(
                                    "pkg:/l3"))
                                got_l3 = True
                self.assert_(got_top and got_l1 and got_l2 and got_l3, "Got "
                    "the right number of dependencies but missed one of the "
                    "expected ones. Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[top_path]]))

        def test_bug_18173(self):
                """Test that if a link moves in a new version of a package, the
                link in the installed version of the package doesn't interfere
                with dependency resolution."""

                self.make_misc_files("usr/lib/isaexec")
                self.pkgsend_bulk(self.rurl, self.bug_18173_cs_1)
                cs2_path = self.make_manifest(self.bug_18173_cs_2)
                ksh_path = self.make_manifest(self.bug_18173_ksh)
                zones_path = self.make_manifest(self.bug_18173_zones)

                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["cs"])

                pkg_deps, errs = dependencies.resolve_deps(
                    [cs2_path, ksh_path, zones_path], self.api_obj,
                    use_system=True)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[cs2_path]), 0)
                self.assertEqual(len(pkg_deps[ksh_path]), 1)
                self.assertEqual(len(pkg_deps[zones_path]), 2,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[zones_path]]))
                got_cs2 = False
                got_ksh = False
                for d in pkg_deps[zones_path]:
                        pfmri = d.attrs["fmri"]
                        if pfmri.startswith("pkg:/cs"):
                                self.assert_(pfmri.endswith("-2"))
                                self.assertEqual(
                                    d.attrs[dependencies.files_prefix],
                                    ["usr/lib/isaexec"])
                                self.assertEqual(
                                    d.attrs[dependencies.via_links_prefix],
                                    "usr/bin/ksh")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "script")
                                got_cs2 = True
                        else:
                                self.assert_(pfmri.startswith(
                                    "pkg:/ksh"))
                                self.assertEqual(
                                    d.attrs[dependencies.files_prefix],
                                    ["usr/bin/ksh"])
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "link")
                                got_ksh = True
                self.assert_(got_cs2 and got_ksh, "Got the right number "
                    "of dependencies but missed one of the expected ones. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[zones_path]]))

        def test_bug_18315_1(self):
                """Test that when two packages deliver a link which is needed in
                a dependency, a require-any dependency is created."""

                l1_path = self.make_manifest(self.bug_18315_link1_manf)
                l2_path = self.make_manifest(self.bug_18315_link2_manf)
                der_path = self.make_manifest(self.bug_18315_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_dependee_manf)

                pkg_deps, errs = dependencies.resolve_deps(
                    [l1_path, l2_path, der_path, dee_path], self.api_obj,
                    use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 2,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[der_path]]))
                for d in pkg_deps[der_path]:
                        if d.attrs["type"] == "require":
                                self.assert_(d.attrs["fmri"].startswith(
                                    "pkg:/dependee"))
                        else:
                                self.assertEqual(d.attrs["type"], "require-any")
                                self.assertEqual(len(d.attrs["fmri"]), 2)
                                fmri0 = d.attrs["fmri"][0]
                                fmri1 = d.attrs["fmri"][1]
                                self.assert_(
                                    (fmri0.startswith("pkg:/link1") and
                                    fmri1.startswith("pkg:/link2")) or
                                    (fmri0.startswith("pkg:/link2") and
                                    fmri1.startswith("pkg:/link1")))

        def test_bug_18315_2(self):
                """Test that variants are handled correctly when multiple
                packages deliver a link under various combinations of
                variants."""

                lv1_path = self.make_manifest(self.bug_18315_var_link1_manf)
                lv2_path = self.make_manifest(self.bug_18315_var_link2_manf)
                lv3_path = self.make_manifest(self.bug_18315_var_link3_manf)
                l1_path = self.make_manifest(self.bug_18315_var_link4_manf)
                l2_path = self.make_manifest(self.bug_18315_var_link5_manf)
                der_path = self.make_manifest(self.bug_18315_var_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_var_dependee_manf)

                pkg_deps, errs = dependencies.resolve_deps([l1_path, l2_path,
                    der_path, dee_path, lv1_path, lv2_path, lv3_path],
                    self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 7)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 5,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[der_path]]))
                for d in pkg_deps[der_path]:
                        if d.attrs["type"] == "require":
                                if d.attrs.get("variant.arch", None) == "foo":
                                        self.assert_(d.attrs["fmri"].startswith(
                                            "pkg:/link5"))
                                else:
                                        self.assert_(d.attrs["fmri"].startswith(
                                            "pkg:/dependee"))
                                continue
                        self.assertEqual(d.attrs["type"], "require-any")
                        if d.attrs["variant.arch"] == "sparc":
                                self.assertEqual(len(d.attrs["fmri"]), 2)
                        elif d.attrs["variant.opensolaris.zone"] == "nonglobal":
                                self.assertEqual(d.attrs["variant.arch"],
                                    "i386")
                                self.assertEqual(len(d.attrs["fmri"]), 3)
                        else:
                                self.assertEqual(
                                    d.attrs["variant.opensolaris.zone"],
                                    "global")
                                self.assertEqual(d.attrs["variant.arch"],
                                    "i386")
                                self.assertEqual(len(d.attrs["fmri"]), 4)

        def test_bug_18318_1(self):
                """Test that require-any dependencies are correctly removed when
                no variants are involved and a manual dependency has been set on
                one of the members of a require-any dependency."""

                bug_18318_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
depend fmri=link1 type=require
"""
                l1_path = self.make_manifest(self.bug_18315_link1_manf)
                l2_path = self.make_manifest(self.bug_18315_link2_manf)
                der_path = self.make_manifest(bug_18318_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_dependee_manf)

                pkg_deps, errs = dependencies.resolve_deps(
                    [l1_path, l2_path, der_path, dee_path], self.api_obj,
                    use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 2,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[der_path]]))
                for d in pkg_deps[der_path]:
                        self.assertEqual(d.attrs["type"], "require")
                        if d.attrs["fmri"].startswith("pkg:/dependee"):
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "elf")
                        else:
                                self.assertEqual(d.attrs["fmri"], "link1")

                # Test that things work when the order of the require-any and
                # require dependencies are changed and when the require
                # dependency is on the second fmri instead of the first.
                bug_18318_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
depend fmri=link2 type=require
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
"""
                der_path = self.make_manifest(bug_18318_depender_manf)

                pkg_deps, errs = dependencies.resolve_deps(
                    [l1_path, l2_path, der_path, dee_path], self.api_obj,
                    use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 2,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[der_path]]))
                for d in pkg_deps[der_path]:
                        self.assertEqual(d.attrs["type"], "require")
                        if d.attrs["fmri"].startswith("pkg:/dependee"):
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "elf")
                        else:
                                self.assertEqual(d.attrs["fmri"], "link2")

        def test_bug_18318_2(self):
                """Test that a manually tagged dependency cancels out
                require-any dependencies which contain that fmri."""

                bug_18318_var_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
depend fmri=link1 type=require
"""
                lv1_path = self.make_manifest(self.bug_18315_var_link1_manf)
                lv2_path = self.make_manifest(self.bug_18315_var_link2_manf)
                lv3_path = self.make_manifest(self.bug_18315_var_link3_manf)
                l1_path = self.make_manifest(self.bug_18315_var_link4_manf)
                l2_path = self.make_manifest(self.bug_18315_var_link5_manf)
                der_path = self.make_manifest(bug_18318_var_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_var_dependee_manf)

                pkg_deps, errs = dependencies.resolve_deps([l1_path, l2_path,
                    der_path, dee_path, lv1_path, lv2_path, lv3_path],
                    self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 7)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 3,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[der_path]]))
                for d in pkg_deps[der_path]:
                        self.assertEqual(d.attrs["type"], "require")
                        if d.attrs["fmri"].startswith("pkg:/dependee"):
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "elf")
                        elif d.attrs["fmri"].startswith("pkg:/link5"):
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "link")
                        else:
                                self.assertEqual(d.attrs["fmri"],"link1")

        def test_bug_18318_3(self):
                """Test that a manually tagged dependency with variants cancels
                out require-any dependencies which contain that fmri."""

                bug_18318_var_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
depend fmri=link1 type=require variant.arch=sparc
"""
                lv1_path = self.make_manifest(self.bug_18315_var_link1_manf)
                lv2_path = self.make_manifest(self.bug_18315_var_link2_manf)
                lv3_path = self.make_manifest(self.bug_18315_var_link3_manf)
                l1_path = self.make_manifest(self.bug_18315_var_link4_manf)
                l2_path = self.make_manifest(self.bug_18315_var_link5_manf)
                der_path = self.make_manifest(bug_18318_var_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_var_dependee_manf)

                pkg_deps, errs = dependencies.resolve_deps([l1_path, l2_path,
                    der_path, dee_path, lv1_path, lv2_path, lv3_path],
                    self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 7)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 5,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[der_path]]))
                for d in pkg_deps[der_path]:
                        if d.attrs.get("variant.opensolaris.zone", None) == \
                            "nonglobal":
                                self.assertEqual(d.attrs["variant.arch"],
                                    "i386")
                                self.assertEqual(len(d.attrs["fmri"]), 3)
                        elif d.attrs.get("variant.opensolaris.zone", None) == \
                            "global":
                                self.assertEqual(d.attrs["variant.arch"],
                                    "i386")
                                self.assertEqual(len(d.attrs["fmri"]), 4)
                        elif d.attrs["fmri"].startswith("pkg:/dependee"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "elf")
                        elif d.attrs["fmri"].startswith("pkg:/link5"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "link")
                        else:
                                self.assertEqual(d.attrs["fmri"], "link1")
                                self.assertEqual(d.attrs["type"], "require")

                # Now test with the manual dependency valid when variant.arch is
                # i386, this should clobber more require-any dependencies.
                bug_18318_var_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
depend fmri=link1 type=require variant.arch=i386
"""

                der_path = self.make_manifest(bug_18318_var_depender_manf)

                pkg_deps, errs = dependencies.resolve_deps([l1_path, l2_path,
                    der_path, dee_path, lv1_path, lv2_path, lv3_path],
                    self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 7)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 4,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[der_path]]))
                for d in pkg_deps[der_path]:
                        if d.attrs.get("variant.arch", None) == "sparc":
                                self.assertEqual(len(d.attrs["fmri"]), 2)
                        elif d.attrs["fmri"].startswith("pkg:/dependee"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "elf")
                        elif d.attrs["fmri"].startswith("pkg:/link5"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "link")
                        else:
                                self.assertEqual(d.attrs["fmri"], "link1")
                                self.assertEqual(d.attrs["type"], "require")

        def test_bug_18318_4(self):
                """Test that automatically generated dependencies can cancel
                require-any dependencies."""

                bug_18318_var_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
depend fmri=link1@2 fmri=link2@2 fmri=link3@2 fmri=link4@2 type=require-any variant.arch=i386
depend fmri=link2@2 fmri=link3@2 fmri=link4@2 type=require-any
depend fmri=__TBD pkg.debug.depend.reason=usr/bin/bar pkg.debug.depend.file=usr/bin/baz pkg.debug.depend.type=hardlink type=require variant.arch=i386
"""

                bug_18318_var_link1_manf = """ \
set name=pkg.fmri value=link1@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
link path=lib/64 target=amd64 variant.arch=i386
link path=lib/64 target=amd64 variant.arch=sparc
file NOHASH path=usr/bin/baz
"""

                lv1_path = self.make_manifest(bug_18318_var_link1_manf)
                lv2_path = self.make_manifest(self.bug_18315_var_link2_manf)
                lv3_path = self.make_manifest(self.bug_18315_var_link3_manf)
                l1_path = self.make_manifest(self.bug_18315_var_link4_manf)
                l2_path = self.make_manifest(self.bug_18315_var_link5_manf)
                der_path = self.make_manifest(bug_18318_var_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_var_dependee_manf)

                pkg_deps, errs = dependencies.resolve_deps([l1_path, l2_path,
                    der_path, dee_path, lv1_path, lv2_path, lv3_path],
                    self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 7)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 5,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[der_path]]))
                for d in pkg_deps[der_path]:
                        if d.attrs.get("variant.arch", None) == "sparc":
                                self.assertEqual(len(d.attrs["fmri"]), 2)
                        elif d.attrs["type"] == "require-any":
                                self.assertEqual(len(d.attrs["fmri"]), 3)
                        elif d.attrs["fmri"].startswith("pkg:/dependee"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "elf")
                        elif d.attrs["fmri"].startswith("pkg:/link5"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "link")
                        else:
                                self.assert_(
                                    d.attrs["fmri"].startswith("pkg:/link1"))
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix],
                                    "hardlink")

        def test_bug_18359(self):
                """Test that if package A needs another package to provide a
                link so one of its files can depend on the other, that A doesn't
                have a dependency on itself."""

                file_manf = """ \
set name=pkg.fmri value=file1@1,5.11-1
file NOHASH path=usr/lib/amd64/lib.so.1
file NOHASH path=usr/bin/prog
depend fmri=__TBD pkg.debug.depend.reason=usr/bin/prog pkg.debug.depend.file=usr/lib/64/lib.so.1 pkg.debug.depend.type=elf type=require
"""

                link_manf = """ \
set name=pkg.fmri value=link1@1,5.11-1
link path=usr/lib/64 target=amd64
"""
                file_path = self.make_manifest(file_manf)
                link_path = self.make_manifest(link_manf)

                pkg_deps, errs = dependencies.resolve_deps([file_path,
                    link_path], self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[link_path]), 0)
                self.assertEqual(len(pkg_deps[file_path]), 1,
                    "Got wrong number of pkgdeps for the file package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[file_path]]))
                dep = pkg_deps[file_path][0]
                self.assertEqual(dep.attrs["type"], "require")
                self.assert_(dep.attrs["fmri"].startswith("pkg:/link1"))
                self.assertEqual(dep.attrs[self.depend_dp + ".type"], "link")

        def test_bug_18884_1(self):
                """Test that a file dependency on a link whose target has
                different content under different variant combinations results
                in the correct variants (in this case, none) being tagged on the
                resolved dependency."""

                dep_manf = """ \
set name=pkg.fmri value=test@1.0
depend type=require fmri=__TBD pkg.debug.depend.file=ksh93 \
    pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=test-script.ksh93 \
    pkg.debug.depend.type=script
"""

                ksh_manf = """ \
set name=pkg.fmri value=shell/ksh@1.0
set name=variant.debug.osnet value=true value=false
set name=variant.foo value=sparc value=i386
set name=variant.opensolaris.zone value=global value=nonglobal
hardlink path=usr/bin/ksh93 target=../../usr/lib/isaexec
"""

                core_os = """ \
set name=pkg.fmri value=system/core-os@1.0
set name=variant.debug.osnet value=true value=false
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.foo value=sparc value=i386
file elfarch=sparc elfbits=32 group=bin mode=0555 owner=root path=usr/lib/isaexec pkg.csize=3633 pkg.size=12124 variant.foo=sparc variant.debug.osnet=false
file elfarch=sparc elfbits=32 group=bin mode=0555 owner=root path=usr/lib/isaexec pkg.csize=4356 pkg.size=13576 variant.foo=sparc variant.debug.osnet=true
file  elfarch=i386 elfbits=32 group=bin mode=0555 owner=root path=usr/lib/isaexec pkg.csize=3791 pkg.size=9696 variant.foo=i386 variant.debug.osnet=true
file elfarch=i386 elfbits=32 group=bin mode=0555 owner=root path=usr/lib/isaexec pkg.csize=3137 pkg.size=8208 variant.foo=i386 variant.debug.osnet=false
"""
                dep_path = self.make_manifest(dep_manf)
                ksh_path = self.make_manifest(ksh_manf)
                cos_path = self.make_manifest(core_os)

                pkg_deps, errs = dependencies.resolve_deps([dep_path,
                    ksh_path, cos_path], self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[ksh_path]), 0)
                self.assertEqual(len(pkg_deps[cos_path]), 0)
                self.assertEqual(len(pkg_deps[dep_path]), 2,
                    "Got wrong number of pkgdeps for the file package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[dep_path]]))
                for dep in pkg_deps[dep_path]:
                        self.assert_("variant.foo" not in dep.attrs, str(dep))
                        self.assert_("variant.debug.osnet" not in
                            dep.attrs, str(dep))
                        self.assert_("variant.opensolaris.zone" not in
                            dep.attrs, str(dep))

        def test_bug_18884_2(self):
                """Similar test to test_bug_18884_1 except only two variants are
                in play, not three.  This may make future debugging easier to
                handle."""

                dep_manf = """ \
set name=pkg.fmri value=test@1.0
depend type=require fmri=__TBD pkg.debug.depend.file=ksh93 \
    pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=test-script.ksh93 \
    pkg.debug.depend.type=script
"""

                ksh_manf = """ \
set name=pkg.fmri value=shell/ksh@1.0
set name=variant.foo value=sparc value=i386
set name=variant.opensolaris.zone value=global value=nonglobal
hardlink path=usr/bin/ksh93 target=../../usr/lib/isaexec
"""

                core_os = """ \
set name=pkg.fmri value=system/core-os@1.0
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.foo value=sparc value=i386
file elfarch=sparc elfbits=32 group=bin mode=0555 owner=root path=usr/lib/isaexec pkg.csize=3633 pkg.size=12124 variant.foo=sparc
file elfarch=i386 elfbits=32 group=bin mode=0555 owner=root path=usr/lib/isaexec pkg.csize=3137 pkg.size=8208 variant.foo=i386
"""
                dep_path = self.make_manifest(dep_manf)
                ksh_path = self.make_manifest(ksh_manf)
                cos_path = self.make_manifest(core_os)

                pkg_deps, errs = dependencies.resolve_deps([dep_path,
                    ksh_path, cos_path], self.api_obj, use_system=False)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[ksh_path]), 0)
                self.assertEqual(len(pkg_deps[cos_path]), 0)
                self.assertEqual(len(pkg_deps[dep_path]), 2,
                    "Got wrong number of pkgdeps for the file package. "
                    "Deps were:\n%s" %
                    "\n".join([str(d) for d in pkg_deps[dep_path]]))
                for dep in pkg_deps[dep_path]:
                        self.assert_("variant.opensolaris.zone" not in
                            dep.attrs, str(dep))
                        self.assert_("variant.debug.osnet" not in
                            dep.attrs, str(dep))


if __name__ == "__main__":
        unittest.main()
