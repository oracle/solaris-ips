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

# Copyright (c) 2009, 2017, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import sys
import unittest

import pkg.actions as actions
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
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.7/v-p/pkg/client/indexer.py
depend fmri=__TBD pkg.debug.depend.file=usr/bin/python2.7 pkg.debug.depend.reason=usr/lib/python2.7/v-p/pkg/client/indexer.py pkg.debug.depend.type=script type=require
depend fmri=__TBD pkg.debug.depend.file=usr/lib/python2.7/v-p/pkg/misc.py pkg.debug.depend.reason=usr/lib/python2.7/v-p/pkg/client/indexer.py pkg.debug.depend.type=python type=require
"""

        misc_manf = """\
set name=fmri value=pkg:/footest@0.5.11,5.11-0.117
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python2.7/v-p/pkg/misc.py
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
file NOHASH path=platform/bar/baz/no_such_named_file group=sys mode=0600 owner=root
file NOHASH path=platform/foo/baz/no_such_named_file group=sys mode=0600 owner=root
"""

        sat_bar_libc = """\
set name=fmri value=pkg:/sat_bar_libc
file NOHASH path=platform/bar/baz/no_such_named_file group=sys mode=0600 owner=root
"""

        sat_bar_libc2 = """\
set name=fmri value=pkg:/sat_bar_libc2
file NOHASH path=platform/bar/baz/no_such_named_file group=sys mode=0600 owner=root
"""

        sat_foo_libc = """\
set name=fmri value=pkg:/sat_foo_libc
file NOHASH path=platform/foo/baz/no_such_named_file group=sys mode=0600 owner=root
"""

        sat_bar_libc_num_var = """\
set name=fmri value=pkg:/sat_bar_libc
set name=variant.num value=one
file NOHASH path=platform/bar/baz/no_such_named_file group=sys mode=0600 owner=root
"""
        sat_foo_libc_num_var = """\
set name=fmri value=pkg:/sat_foo_libc
set name=variant.num value=two
file NOHASH path=platform/foo/baz/no_such_named_file group=sys mode=0600 owner=root
"""
        sat_foo_libc_num_var_both = """\
set name=fmri value=pkg:/sat_foo_libc
set name=variant.num value=one value=two
file NOHASH path=platform/foo/baz/no_such_named_file group=sys mode=0600 owner=root
"""

        multi_file_dep_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.7/vendor-packages/pkg/client/indexer.py
depend fmri=__TBD pkg.debug.depend.file=search_storage.py pkg.debug.depend.file=search_storage.pyc pkg.debug.depend.file=search_storage/__init__.py pkg.debug.depend.path=usr/lib/python2.7/pkg pkg.debug.depend.path=usr/lib/python2.7/lib-dynload/pkg pkg.debug.depend.path=usr/lib/python2.7/lib-old/pkg pkg.debug.depend.path=usr/lib/python2.7/lib-tk/pkg pkg.debug.depend.path=usr/lib/python2.7/plat-sunos5/pkg pkg.debug.depend.path=usr/lib/python2.7/site-packages/pkg pkg.debug.depend.path=usr/lib/python2.7/vendor-packages/pkg pkg.debug.depend.path=usr/lib/python2.7/vendor-packages/gst-0.10/pkg pkg.debug.depend.path=usr/lib/python2.7/vendor-packages/gtk-2.0/pkg pkg.debug.depend.path=usr/lib/python27.zip/pkg pkg.debug.depend.reason=usr/lib/python2.7/vendor-packages/pkg/client/indexer.py pkg.debug.depend.type=python type=require
"""

        multi_file_dep_fullpath_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.7/vendor-packages/pkg/client/indexer.py
depend fmri=__TBD pkg.debug.depend.file=search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/lib-dynload/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/lib-old/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/lib-tk/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/plat-sunos5/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/site-packages/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/vendor-packages/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/vendor-packages/gst-0.10/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/vendor-packages/gtk-2.0/pkg/search_storage.py \
        pkg.debug.depend.fullpath=usr/lib/python27.zip/pkg/search_storage.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.7/lib-dynload/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.7/lib-old/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.7/lib-tk/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.7/plat-sunos5/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.7/site-packages/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.7/vendor-packages/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.7/vendor-packages/gst-0.10/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python2.7/vendor-packages/gtk-2.0/pkg/search_storage.pyc \
    pkg.debug.depend.fullpath=usr/lib/python27.zip/pkg/search_storage.pyc \
        pkg.debug.depend.fullpath=usr/lib/python2.7/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/lib-dynload/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/lib-old/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/lib-tk/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/plat-sunos5/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/site-packages/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/vendor-packages/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/vendor-packages/gst-0.10/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python2.7/vendor-packages/gtk-2.0/pkg/search_storage/__init__.py \
    pkg.debug.depend.fullpath=usr/lib/python27.zip/pkg/search_storage/__init__.py \
    pkg.debug.depend.reason=usr/lib/python2.7/vendor-packages/pkg/client/indexer.py \
    pkg.debug.depend.type=python type=require
"""

        multi_file_sat_both = """\
set name=fmri value=pkg:/sat_both
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.7/vendor-packages/pkg/search_storage.py
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.7/vendor-packages/pkg/search_storage.pyc
"""

        multi_file_sat_py = """\
set name=fmri value=pkg:/sat_py
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.7/vendor-packages/pkg/search_storage.py
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.7/lib-tk/pkg/search_storage.py
"""
        multi_file_sat_pyc = """\
set name=fmri value=pkg:/sat_pyc
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.7/vendor-packages/pkg/search_storage.pyc
"""

        inst_pkg = """\
open example2_pkg@1.0,5.11-0
add file tmp/foo mode=0555 owner=root group=bin path=/usr/bin/python2.7
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
open runtime/python-27@2.7.8,5.11-0.161
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
open runtime/python-27@2.7.8,5.11-0.161
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
open runtime/python-27@2.7.8,5.11-0.161
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
file tmp/foo path=usr/lib/isaexec group=sys mode=0600 owner=root
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
file tmp/foo path=usr/lib/isaexec group=sys mode=0600 owner=root
"""

        bug_18173_ksh = """\
set name=pkg.fmri value=ksh@0.5.11,5.11-2
hardlink path=usr/bin/ksh target=../../usr/lib/isaexec
depend fmri=__TBD pkg.debug.depend.file=isaexec pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=usr/bin/ksh pkg.debug.depend.type=hardlink type=require
"""

        bug_18173_zones = """\
set name=pkg.fmri value=zones@0.5.11,5.11-2
file NOHASH path=usr/lib/brand/shared/dsconvert group=sys mode=0755 owner=root
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
file NOHASH path=lib/amd64/libc.so.1 group=sys mode=0600 owner=root
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
file NOHASH path=lib/amd64/libc.so.1 group=sys mode=0600 owner=root
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

        misc_files = {
            "empty": "\n\n\n",
            "var_pat": "var*\n",
            "var_fmri": "variant_pkg\n",
            "bad_pat": "abcde\n",
            "ex_pat": "ex*\n",
            "tmp/foo": "tmp/foo",
        }

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
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([m1_path], self.api_obj, ["*"])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(errs), 1)
                self.assertTrue(isinstance(errs[0],
                    actions.InvalidActionAttributesError))

                bad_require_any_dep_manf = """\
depend fmri=example_pkg fmri=pkg://////// fmri=pkg://// type=require-any
"""
                m1_path = self.make_manifest(bad_require_any_dep_manf)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([m1_path], self.api_obj, ["*"])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(errs), 1)
                self.assertTrue(isinstance(errs[0],
                    actions.InvalidActionAttributesError))

                bad_variant = """\
set name=pkg.fmri value=foo@1.0,5.11-1
set name=variant.num value=one value=two
depend fmri=pkg:/a@0,5.11-1 type=conditional predicate=pkg:/b@2,5.11-1 variant.nn
"""
                m1_path = self.make_manifest(bad_variant)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([m1_path], self.api_obj, ["*"])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(errs), 1)
                self.assertTrue(isinstance(errs[0],
                    actions.MalformedActionError),
                    "Error was of the type. The type was:{0}. The error "
                    "was:\n:{1}".format(type(errs[0]), errs[0]))

        def test_constraint_files(self):
                """Test that the constraint files (-e) work as expected and that
                the output with -E is also as expected."""

                m1_path = self.make_manifest(self.hardlink1_manf_deps)
                self.pkgsend_bulk(self.rurl, self.inst_pkg)
                self.pkgsend_bulk(self.rurl, self.var_pkg)
                self.api_obj.refresh(immediate=True)

                empty_path = os.path.join(self.test_root, "empty")
                ex_path = os.path.join(self.test_root, "ex_pat")
                var_pat_path = os.path.join(self.test_root, "var_pat")
                var_fmri_path = os.path.join(self.test_root, "var_fmri")

                # Test that having constraint files but no constraints errors
                # correctly.
                self.pkgdepend_resolve("-e {0} -m {1}".format(empty_path, m1_path),
                    exit=1)
                self.assertEqualDiff("pkgdepend: External package list files "
                    "were provided but did not contain any fmri patterns.\n",
                    self.errout)

                # Test that only constrained files are used to resolve
                # dependencies.
                self._api_install(self.api_obj, ["variant_pkg"])
                self.pkgdepend_resolve("-e {0} -E -m {1}".format(
                    var_pat_path, m1_path))
                self.assertEqualDiff("", self.errout)

                expected_txt = """
The following fmris matched a pattern in a constraint file but were not used in
dependency resolution:
	example2_pkg
"""
                # Test that extraneous packages are properly displayed when -E
                # is used.
                self._api_install(self.api_obj, ["example2_pkg"])
                self.pkgdepend_resolve("-e {0} -e {1} -e {2} -E -m {3}".format(
                    var_fmri_path, ex_path, empty_path, m1_path))
                self.assertEqualDiff(expected_txt, self.output)

                # Check that changing the order of the -e options doesn't change
                # the results.
                self.pkgdepend_resolve("-e {0} -e {1} -e {2} -E -m {3}".format(
                    ex_path, var_fmri_path, empty_path, m1_path))
                self.assertEqualDiff(expected_txt, self.output)

                # Check that if -e points at a file that doesn't exist, no
                # traceback happens.
                self.pkgdepend_resolve("-e {0} -e {1} -e {2} -E -m {3}".format(
                    ex_path + "foobar", var_fmri_path, empty_path, m1_path),
                    exit=1)

                # Check that if -e points at a directory, no traceback happens.
                self.pkgdepend_resolve("-e {0} -E -m {1}".format(
                    self.test_root, m1_path), exit=1)

        def test_resolve_permissions(self):
                """Test that a manifest or constraint file that pkgdepend
                resolve can't access doesn't cause a traceback."""

                m1_path = self.make_manifest(self.hardlink1_manf_deps)
                self.pkgdepend_resolve("-m {0}".format(m1_path), su_wrap=True, exit=1)
                os.chmod(m1_path, 0o444)
                pattern_path = os.path.join(self.test_root, "ex_pat")
                os.chmod(pattern_path, 0000)
                self.pkgdepend_resolve("-e {0} -o {1}".format(
                    pattern_path, m1_path), su_wrap=True, exit=1)

        def test_resolve_cross_package(self):
                """test that cross dependencies between published packages
                works."""

                m1_path = self.make_manifest(self.hardlink1_manf_deps)
                m2_path = self.make_manifest(self.hardlink2_manf_deps)
                p1_name = 'pkg:/{0}'.format(os.path.basename(m1_path))
                p2_name = 'pkg:/{0}'.format(os.path.basename(m2_path))
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([m1_path, m2_path], self.api_obj,
                        ["*"])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[m1_path]), 1)
                self.assertEqual(len(pkg_deps[m1_path][0].attrs["{0}.reason".format(
                    base.Dependency.DEPEND_DEBUG_PREFIX)]), 2)
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

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([m1_path, m2_path], self.api_obj,
                        ["*"])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["example2_pkg"]), external_deps)
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[m1_path]), 2)
                self.assertEqual(len(pkg_deps[m2_path]), 0)
                self.assertEqual(len(errs), 0)
                for d in pkg_deps[m1_path]:
                        if d.attrs["fmri"] == p2_name:
                                self.assertEqual(
                                    d.attrs["{0}.file".format(self.depend_dp)],
                                    ["usr/lib/python2.7/v-p/pkg/misc.py"])
                        elif d.attrs["fmri"] == p3_name:
                                self.assertEqual(
                                    d.attrs["{0}.file".format(self.depend_dp)],
                                    ["usr/bin/python2.7"])
                        else:
                                raise RuntimeError("Got unexpected fmri "
                                    "{0} for in dependency {1}".format(
                                    d.attrs["fmri"], d))

                # Check that with system_patterns set to [], the system is
                # not resolved against.  Bug 15777
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([m1_path, m2_path], self.api_obj,
                        [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[m1_path]), 1)
                self.assertEqual(len(pkg_deps[m2_path]), 0)
                self.assertEqual(len(errs), 1)
                for d in pkg_deps[m1_path]:
                        if d.attrs["fmri"] == p2_name:
                                self.assertEqual(
                                    d.attrs["{0}.file".format(self.depend_dp)],
                                    ["usr/lib/python2.7/v-p/pkg/misc.py"])
                        elif d.attrs["fmri"] == p3_name:
                                self.assertEqual(
                                    d.attrs["{0}.file".format(self.depend_dp)],
                                    ["usr/bin/python2.7"])
                        else:
                                raise RuntimeError("Got unexpected fmri "
                                    "{0} for in dependency {1}".format(
                                    d.attrs["fmri"], d))
                for e in errs:
                        if isinstance(e,
                            dependencies.UnresolvedDependencyError):
                                self.assertEqual(e.path, m1_path)
                                self.assertEqual(e.file_dep.attrs[
                                    "{0}.file".format(self.depend_dp)],
                                    "usr/bin/python2.7")
                        else:
                                raise RuntimeError("Unexpected error:{0}".format(e))

        def test_simple_variants_1(self):
                """Test that variants declared on the actions work correctly
                when resolving dependencies."""

                m1_path = self.make_manifest(self.simple_variant_deps)
                m2_path = self.make_manifest(self.simple_v_deps_bar)
                m3_path = self.make_manifest(self.simple_v_deps_baz)
                p2_name = "s-v-bar"
                p3_name = "s-v-baz"
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([m1_path, m2_path, m3_path],
                        self.api_obj, ["*"])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
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
                                raise RuntimeError("Unexpected fmri {0} "
                                    "for dependency {1}".format(
                                    d.attrs["fmri"], d))
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join([
                            "{0}".format(e,) for e in errs])))
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
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([m1_path, m2_path, m3_path],
                        self.api_obj, ["*"])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
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
                                raise RuntimeError("Unexpected fmri {0} "
                                    "for dependency {1}".format(
                                    d.attrs["fmri"], d))

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
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [m1_path, m2_path, m3_path, m4_path], self.api_obj,
                        ["*"])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
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
                                self.assertTrue("variant.num" not in d.attrs)
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
                                raise RuntimeError("Unexpected fmri {0} "
                                    "for dependency {1}".format(
                                    d.attrs["fmri"], d))

        def test_multi_file_dependencies(self):
                """This checks manifests with multiple files, both with
                pkg.debug.depend.file/path combinations, as well as
                with pkg.debug.depend.fullpath lists."""
                def __check_results(pkg_deps, errs, unused_fmris, external_deps,
                    exp_pkg, no_deps, one_dep):
                        if errs:
                                raise RuntimeError("Got the following "
                                    "unexpected errors:\n{0}".format(
                                    "\n".join([str(e) for e in errs])))
                        self.assertEqualDiff(set(), unused_fmris)
                        self.assertEqualDiff(set(), external_deps)
                        self.assertEqual(len(pkg_deps), 2)
                        self.assertEqual(len(pkg_deps[no_deps]), 0)
                        if len(pkg_deps[one_dep]) != 1:
                                raise RuntimeError("Got more than one "
                                    "dependency:\n{0}".format(
                                    "\n".join(
                                        [str(d) for d in pkg_deps[one_dep]])))
                        d = pkg_deps[one_dep][0]
                        self.assertEqual(d.attrs["fmri"], exp_pkg)
                        self.assertEqual(d.attrs["type"], "require",
                            "Dependency was:{0}".format(d))

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
                        pkg_deps, errs, warnings, unused_fmris, external_deps = \
                            dependencies.resolve_deps([mf_path, both_path],
                                self.api_obj, ["*"])
                        __check_results(pkg_deps, errs, unused_fmris,
                            external_deps, "pkg:/sat_both", both_path, mf_path)

                        pkg_deps, errs, warnings, unused_fmris, external_deps = \
                            dependencies.resolve_deps([mf_path, py_path],
                                self.api_obj, ["*"])
                        __check_results(pkg_deps, errs, unused_fmris,
                            external_deps, "pkg:/sat_py", py_path, mf_path)

                        pkg_deps, errs, warnings, unused_fmris, external_deps = \
                            dependencies.resolve_deps([mf_path, pyc_path],
                                self.api_obj, ["*"])
                        __check_results(pkg_deps, errs, unused_fmris,
                            external_deps, "pkg:/sat_pyc", pyc_path, mf_path)

                        # This resolution should produce require-any
                        # dependencies because files which satisfy the
                        # dependency are delivered in two packages.
                        pkg_deps, errs, warnings, unused_fmris, external_deps = \
                            dependencies.resolve_deps([mf_path, py_path, pyc_path],
                                self.api_obj, ["*"])
                        self.assertEqual(len(pkg_deps), 3)
                        if len(errs) != 0:
                                raise RuntimeError("Unexpected errors:\n{0}".format(
                                    "\n".join(str(e) for e in errs)))
                        self.assertEqualDiff(set(), unused_fmris)
                        self.assertEqualDiff(set(), external_deps)
                        self.assertEqual(len(pkg_deps[py_path]), 0)
                        self.assertEqual(len(pkg_deps[pyc_path]), 0)
                        self.assertEqual(len(pkg_deps[mf_path]), 1,
                            "Didn't get one dependency:\n{0}".format(
                            "\n".join([str(d) for d in pkg_deps[mf_path]])))
                        d = pkg_deps[mf_path][0]
                        self.assertEqual(d.attrs["type"], "require-any")
                        self.assertEqual(set(d.attrs["fmri"]),
                            set(["pkg:/sat_py", "pkg:/sat_pyc"]))

                        pkg_deps, errs, warnings, unused_fmris, external_deps = \
                            dependencies.resolve_deps(
                                [both_path, mf_path, py_path, pyc_path],
                                self.api_obj, ["*"])
                        self.assertEqual(len(pkg_deps), 4)
                        if len(errs) != 0:
                                raise RuntimeError("Unexpected errors:\n{0}".format(
                                    "\n".join(str(e) for e in errs)))
                        self.assertEqualDiff(set(), unused_fmris)
                        self.assertEqualDiff(set(), external_deps)
                        self.assertEqual(len(pkg_deps[py_path]), 0)
                        self.assertEqual(len(pkg_deps[both_path]), 0)
                        self.assertEqual(len(pkg_deps[pyc_path]), 0)
                        self.assertEqual(len(pkg_deps[mf_path]), 1,
                            "Didn't get one dependency:\n{0}".format(
                            "\n".join([str(d) for d in pkg_deps[mf_path]])))
                        d = pkg_deps[mf_path][0]
                        self.assertEqual(d.attrs["type"], "require-any")
                        self.assertEqual(set(d.attrs["fmri"]), set(
                            ["pkg:/sat_py", "pkg:/sat_pyc", "pkg:/sat_both"]))

        def test_bug_11518(self):
                """Test that resolving against an installed, cached, manifest
                works with variants."""

                self.pkgsend_bulk(self.rurl, self.var_pkg)
                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["variant_pkg"])

                m1_path = self.make_manifest(self.simp_manf)
                p2_name = "pkg:/variant_pkg@1.0-0"

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([m1_path], self.api_obj, ["*"])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["variant_pkg"]), external_deps)
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[m1_path]), 1)
                self.assertEqual(len(errs), 0)
                for d in pkg_deps[m1_path]:
                        if d.attrs["fmri"] == p2_name:
                                self.assertEqual(
                                    d.attrs["{0}.file".format(self.depend_dp)],
                                    ["var/log/syslog"])
                        else:
                                raise RuntimeError("Was expecting {0}, got fmri "
                                    "{1} for dependency {2}".format(
                                    p2_name, d.attrs["fmri"], d))

        def test_bug_12697_and_12896(self):
                """Test that pkgdep resolve handles multiple run path
                dependencies correctly when the files are delivered in the same
                package and when the files are delivered in different packages.
                """

                def __check_results(pkg_deps, errs, unused_fmris, external_deps,
                    exp_pkg, no_deps, one_dep):
                        if errs:
                                raise RuntimeError("Got the following "
                                    "unexpected errors:\n{0}".format(
                                    "\n".join([str(e) for e in errs])))
                        self.assertEqualDiff(set(), unused_fmris)
                        self.assertEqualDiff(set(), external_deps)
                        self.assertEqual(len(pkg_deps), 2)
                        self.assertEqual(len(pkg_deps[no_deps]), 0)
                        if len(pkg_deps[one_dep]) != 1:
                                raise RuntimeError("Got more than one "
                                    "dependency:\n{0}".format(
                                    "\n".join(
                                        [str(d) for d in pkg_deps[col_path]])))
                        d = pkg_deps[one_dep][0]
                        self.assertEqual(d.attrs["fmri"], exp_pkg,
                            "Expected dependency {0}; found {1}.".format(exp_pkg,
                                d.attrs["fmri"]))

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
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([col_path, both_path],
                        self.api_obj, ["*"])
                __check_results(pkg_deps, errs, unused_fmris, external_deps,
                    "pkg:/sat_both", both_path, col_path)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([col_path, bar_path],
                        self.api_obj, ["*"])
                __check_results(pkg_deps, errs, unused_fmris, external_deps,
                    "pkg:/sat_bar_libc", bar_path, col_path)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([col_path, foo_path],
                        self.api_obj, ["*"])
                __check_results(pkg_deps, errs, unused_fmris, external_deps,
                    "pkg:/sat_foo_libc", foo_path, col_path)

                # This test should also pass because the dependencies will be
                # variant tagged, just as the file delivery is.
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [col_path_num_var, foo_path_num_var, bar_path_num_var],
                        self.api_obj, ["*"])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format(
                            "\n".join([str(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[foo_path_num_var]), 0)
                self.assertEqual(len(pkg_deps[bar_path_num_var]), 0)
                self.assertEqual(len(pkg_deps[col_path_num_var]), 2)
                for d in pkg_deps[col_path_num_var]:
                        if d.attrs["fmri"] not in \
                            ("pkg:/sat_foo_libc", "pkg:/sat_bar_libc"):
                                raise RuntimeError("Unexpected fmri in {0}".format(d))

                # This resolution should result in two, varianted, dependencies.
                # The first should have variant.num=one and a type of
                # require-any because in that case files which satisfy the
                # dependency are delivered in two packages.  The other
                # dependency should be a require dependency with
                # variant.num=two.
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                    [col_path_num_var, foo_path_num_var_both, bar_path_num_var],
                    self.api_obj, ["*"])
                self.assertEqual(len(pkg_deps), 3)
                if len(errs) != 0:
                        raise RuntimeError("Got an unexpected error:\n{0}".format(
                            "\n".join(str(e) for e in errs)))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps[foo_path_num_var_both]), 0)
                self.assertEqual(len(pkg_deps[bar_path_num_var]), 0)
                self.assertEqual(len(pkg_deps[col_path_num_var]), 2)
                have_req_any = False
                have_require = False
                for d in pkg_deps[col_path_num_var]:
                        if d.attrs["type"] == "require-any" and \
                            set(d.attrs["fmri"]) == \
                            set(["pkg:/sat_foo_libc", "pkg:/sat_bar_libc"]) and\
                            d.attrs["variant.num"] == "one":
                                have_req_any = True
                        elif d.attrs["type"] == "require" and \
                            d.attrs["fmri"] == "pkg:/sat_foo_libc" and \
                            d.attrs["variant.num"] == "two":
                                have_require = True
                        else:
                                raise RuntimeError("Unexpected dependency:{0}".format(
                                    d))
                self.assertTrue(have_req_any)
                self.assertTrue(have_require)

                # This resolution should also produce a require-any dependency.
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([col_path, bar_path, foo_path],
                        self.api_obj, ["*"])
                self.assertEqual(len(pkg_deps), 3)
                if len(errs) != 0:
                        raise RuntimeError("Got an unexpected error:\n{0}".format(
                            "\n".join(str(e) for e in errs)))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps[foo_path]), 0)
                self.assertEqual(len(pkg_deps[bar_path]), 0)
                self.assertEqual(len(pkg_deps[col_path]), 1)
                d = pkg_deps[col_path][0]
                self.assertEqual(d.attrs["type"], "require-any")
                self.assertEqual(set(d.attrs["fmri"]),
                    set(["pkg:/sat_bar_libc", "pkg:/sat_foo_libc"]))

                # This resolution should also produce a require-any dependency.
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([col_path, bar_path, bar2_path],
                        self.api_obj, ["*"])
                self.assertEqual(len(pkg_deps), 3)
                if len(errs) != 0:
                        raise RuntimeError("Got an unexpected error:\n{0}".format(
                            "\n".join(str(e) for e in errs)))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps[bar2_path]), 0)
                self.assertEqual(len(pkg_deps[bar_path]), 0)
                self.assertEqual(len(pkg_deps[col_path]), 1)
                d = pkg_deps[col_path][0]
                self.assertEqual(d.attrs["type"], "require-any")
                self.assertEqual(set(d.attrs["fmri"]),
                    set(["pkg:/sat_bar_libc", "pkg:/sat_bar_libc2"]))

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

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(manifests, self.api_obj, ["*"])

                self.assertEqual(len(pkg_deps[manifests[1]]), 1)
                for d in pkg_deps[manifests[1]]:
                        fmri = PkgFmri(d.attrs["fmri"])
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
                self.pkgdepend_resolve("-m {0}".format(missing_build))

                self.pkgdepend_resolve("-m {0}".format(corrupted_version), exit=1)
                self.pkgdepend_resolve("-m {0}".format(leading_zeros), exit=1)

                # This is a valid FMRI since bug 18243 was fixed.
                self.pkgdepend_resolve("-m {0} {1}".format(depender, missing_build))

                self.pkgdepend_resolve("-m {0} {1}".format(
                    corrupted_version, depender), exit=1)
                self.pkgdepend_resolve("-m {0} {1}".format(depender, leading_zeros),
                    exit=1)

        def test_bug_17700(self):
                """Test that when multiple packages satisfy a dependency under
                the same combination of two variants, that a require-any
                dependency is produced."""

                self.pkgsend_bulk(self.rurl, self.installed_17700_res1)
                self.pkgsend_bulk(self.rurl, self.installed_17700_res2)
                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["system/kernel",
                    "system/kernel/platform"])
                dep_path = self.make_manifest(self.bug_17700_dep)
                res1_path = self.make_manifest(self.bug_17700_res1)
                res2_path = self.make_manifest(self.bug_17700_res2)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([dep_path, res1_path, res2_path],
                        self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 3)
                if len(errs) != 0:
                        raise RuntimeError("Got an unexpected error:\n{0}".format(
                            "\n".join(str(e) for e in errs)))
                self.assertEqual(len(pkg_deps[res1_path]), 0)
                self.assertEqual(len(pkg_deps[res2_path]), 0)
                self.assertEqual(len(pkg_deps[dep_path]), 1)
                d = pkg_deps[dep_path][0]
                self.assertEqual(d.attrs["type"], "require-any")
                self.assertEqual(set(d.attrs["fmri"]), set([
                    "pkg:/system/kernel@1.0-1",
                    "pkg:/system/kernel/platform@1.0-1"]))

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([dep_path, res1_path, res2_path],
                        self.api_obj, ["*"])
                self.assertEqual(len(pkg_deps), 3)
                if len(errs) != 0:
                        raise RuntimeError("Got an unexpected error:\n{0}".format(
                            "\n".join(str(e) for e in errs)))
                self.assertEqual(len(pkg_deps[res1_path]), 0)
                self.assertEqual(len(pkg_deps[res2_path]), 0)
                self.assertEqual(len(pkg_deps[dep_path]), 1)
                d = pkg_deps[dep_path][0]
                self.assertEqual(d.attrs["type"], "require-any")
                self.assertEqual(set(d.attrs["fmri"]), set([
                    "pkg:/system/kernel@1.0-1",
                    "pkg:/system/kernel/platform@1.0-1"]))

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
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([manf_path], self.api_obj,
                        [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
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
                        if t == "conditional":
                                s = "depend fmri=pkg:/{type}@0,5.11-1 " \
                                    "predicate=pkg:/foo@0,5.11-1 " \
                                    "type={type}".format(type=t)
                        else:
                                s = "depend fmri=pkg:/{type}@0,5.11-1 " \
                                    "type={type}".format(type=t)
                        manf.append(s)

                manf_path = self.make_manifest("\n".join(manf))
                self.pkgdepend_resolve("-m {0}".format(manf_path))
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
                self._api_install(self.api_obj, ["runtime/python-27"])
                dep_path = self.make_manifest(self.bug_18045_dep)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([dep_path], self.api_obj, ["*"])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join([
                            "{0}".format(e,) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["runtime/python-27"]), external_deps)
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[dep_path]), 1)
                self.debug("fmri:{0}".format(pkg_deps[dep_path][0].attrs["fmri"]))
                self.assertTrue(pkg_deps[dep_path][0].attrs["fmri"].startswith(
                    "pkg:/runtime/python-27@2.7.8-0.161"))

        def test_bug_18045_reverse(self):
                """Test that when a package with variants has a file dependency
                on a file in a package that declares no variants, that
                dependency is satisfied."""

                self.pkgsend_bulk(self.rurl, self.installed_18045_reverse)
                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["runtime/python-27"])
                dep_path = self.make_manifest(self.bug_18045_dep_reverse)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([dep_path], self.api_obj, ["*"])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join([
                            "{0}".format(e,) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["runtime/python-27"]), external_deps)
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[dep_path]), 1)
                self.debug("fmri:{0}".format(pkg_deps[dep_path][0].attrs["fmri"]))
                self.assertTrue(pkg_deps[dep_path][0].attrs["fmri"].startswith(
                    "pkg:/runtime/python-27@2.7.8-0.161"))

        def test_bug_18045_mixed(self):
                """Test that when a package with variants has a file dependency
                on a file in a package that declares a different set of variant
                types, that dependency is satisfied."""

                self.pkgsend_bulk(self.rurl, self.installed_18045_mixed)
                self.api_obj.refresh(immediate=True)
                self._api_install(self.api_obj, ["runtime/python-27"])
                dep_path = self.make_manifest(self.bug_18045_dep_mixed)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([dep_path], self.api_obj, ["*"])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join([
                            "{0}".format(e,) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["runtime/python-27"]), external_deps)
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[dep_path]), 1)
                self.debug("fmri:{0}".format(pkg_deps[dep_path][0].attrs["fmri"]))
                self.assertTrue(pkg_deps[dep_path][0].attrs["fmri"].startswith(
                    "pkg:/runtime/python-27@2.7.8-0.161"))

        def test_bug_18077(self):
                """Test that a package with manually annotated group,
                incorporate, or other types of dependencies on the same package
                doesn't cause pkgdep resolve to traceback."""

                manf = ["set name=pkg.fmri value=bug_18077@1.0,5.11-1"]
                for t in depend.known_types:
                        if t == "conditional":
                                s = "depend fmri=pkg:/foo2@0,5.11-1 predicate=pkg:/foo3@0,5.11-1 type={type}".format(type=t)
                        else:
                                s = "depend fmri=pkg:/foo@0,5.11-1 type={type}".format(type=t)

                        manf.append(s)
                manf_path = self.make_manifest("\n".join(manf))
                self.pkgdepend_resolve("-m {0}".format(manf_path))
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
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([d_path, p_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 1, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[d_path]])))
                for k in pkg_deps[d_path][0].attrs:
                        self.assertTrue(not k.startswith("variant."), "The "
                            "resulting dependency should not contain any "
                            "variants. The action is:\n{0}".format(
                            pkg_deps[d_path][0]))

                # Test that combinations of two variant types works.
                p_path = self.make_manifest(self.bug_18130_provider_2)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([d_path, p_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 1, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[d_path]])))

                # Test that splitting the variants across two packages gives the
                # right simplification.
                p_path = self.make_manifest(self.bug_18130_provider_3_1)
                p2_path = self.make_manifest(self.bug_18130_provider_3_2)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([d_path, p_path, p2_path],
                        self.api_obj, [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[p2_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 3, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[d_path]])))
                got_prov_2 = False
                got_prov_1_i386 = False
                got_prov_1_sparc = False
                for d in pkg_deps[d_path]:
                        if d.attrs["fmri"].startswith("pkg:/provider2"):
                                self.assertEqual(d.attrs[VA], "i386")
                                self.assertEqual(d.attrs[VOZ], "global")
                                got_prov_2 = True
                        elif d.attrs["fmri"].startswith("pkg:/provider1"):
                                self.assertTrue(VA in d.attrs)
                                if d.attrs[VA] == "i386":
                                        self.assertEqual(d.attrs[VOZ],
                                            "nonglobal")
                                        got_prov_1_i386 = True
                                else:
                                        self.assertEqual(d.attrs[VA], "sparc")
                                        self.assertTrue(VOZ not in d.attrs)
                                        got_prov_1_sparc = True
                        else:
                                raise RuntimeError("Unexpected fmri seen:{0}".format(
                                    d))
                self.assertTrue(got_prov_2 and got_prov_1_i386 and
                    got_prov_1_sparc, "Got the right number of dependencies "
                    "but missed one of the expected ones. Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[d_path]])))

                # Test that when a variant combination is satisfied, it's
                # reported as being unresolved.
                p_path = self.make_manifest(self.bug_18130_provider_3_1)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([d_path, p_path], self.api_obj,
                        [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(errs), 1)
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 2, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[d_path]])))

                # Test that variants with 3 values as well as a combination of
                # three variant types are collapsed correctly.
                p_path = self.make_manifest(self.bug_18130_provider_4)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([d_path, p_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 1, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[d_path]])))
                for k in pkg_deps[d_path][0].attrs:
                        self.assertTrue(not k.startswith("variant."), "The "
                            "resulting dependency should not contain any "
                            "variants. The action is:\n{0}".format(
                            pkg_deps[d_path][0]))

                # Test all but one dependency satisfier in one file, and one in
                # another package.
                p_path = self.make_manifest(self.bug_18130_provider_5_1)
                p2_path = self.make_manifest(self.bug_18130_provider_5_2)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([d_path, p_path, p2_path],
                        self.api_obj, [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[p2_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 5, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[d_path]])))
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
                                self.assertTrue(VA in d.attrs)
                                if d.attrs[VA] == "i386":
                                        self.assertTrue(VD not in d.attrs)
                                        self.assertTrue(VOZ not in d.attrs)
                                        got_prov_1_i386 = True
                                elif d.attrs[VA] == "sparc":
                                        self.assertTrue(VD not in d.attrs)
                                        self.assertTrue(VOZ not in d.attrs)
                                        got_prov_1_sparc = True
                                else:
                                        self.assertEqual(d.attrs[VA], "foo")
                                        if d.attrs[VD] == "True":
                                                self.assertTrue(VOZ not in d.attrs)
                                                got_prov_1_foo_debug = True
                                        else:
                                                self.assertEqual(d.attrs[VD],
                                                    "False")
                                                self.assertEqual(d.attrs[VOZ],
                                                    "global")
                                                got_prov_1_foo_nondebug_global = True
                        else:
                                raise RuntimeError("Unexpected fmri seen:{0}".format(
                                    d))
                self.assertTrue(got_prov_2 and got_prov_1_i386 and
                    got_prov_1_sparc and got_prov_1_foo_debug and
                    got_prov_1_foo_nondebug_global, "Got the right number "
                    "of dependencies but missed one of the expected ones. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[d_path]])))

                # Test that when two manifests split on debug, non-debug, the
                # variants are collapsed correctly.
                p_path = self.make_manifest(self.bug_18130_provider_6_1)
                p2_path = self.make_manifest(self.bug_18130_provider_6_2)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([d_path, p_path, p2_path],
                        self.api_obj, [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[p2_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 2, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[d_path]])))
                got_prov_2 = False
                got_prov_1 = False
                for d in pkg_deps[d_path]:
                        if d.attrs["fmri"].startswith("pkg:/provider2"):
                                self.assertEqual(d.attrs[VD], "False")
                                self.assertTrue(VOZ not in d.attrs)
                                self.assertTrue(VA not in d.attrs)
                                got_prov_2 = True
                        else:
                                self.assertTrue(d.attrs["fmri"].startswith(
                                    "pkg:/provider1"))
                                self.assertEqual(d.attrs[VD], "True")
                                self.assertTrue(VA not in d.attrs)
                                self.assertTrue(VOZ not in d.attrs)
                                got_prov_1 = True
                self.assertTrue(got_prov_2 and got_prov_1, "Got the right number "
                    "of dependencies but missed one of the expected ones. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[d_path]])))

                # Test that variants won't be combined when they shouldn't be.
                p_path = self.make_manifest(self.bug_18130_provider_7_1)
                p2_path = self.make_manifest(self.bug_18130_provider_7_2)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([d_path, p_path, p2_path],
                        self.api_obj, [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[p_path]), 0)
                self.assertEqual(len(pkg_deps[p2_path]), 0)
                self.assertEqual(len(pkg_deps[d_path]), 12, "Got wrong number "
                    "of pkgdeps for the dependent package. Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[d_path]])))

        def test_bug_18172(self):
                """Test that the via-links attribute is set correctly when
                multiple packages deliver a chain of links."""

                top_path = self.make_manifest(self.bug_18172_top)
                l1_path = self.make_manifest(self.bug_18172_l1)
                l2_path = self.make_manifest(self.bug_18172_l2)
                l3_path = self.make_manifest(self.bug_18172_l3)
                dest_path = self.make_manifest(self.bug_18172_dest)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [top_path, l1_path, l2_path, l3_path, dest_path],
                        self.api_obj, [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 5)
                self.assertEqual(len(pkg_deps[dest_path]), 0)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[l3_path]), 0)
                self.assertEqual(len(pkg_deps[top_path]), 4,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[top_path]])))
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
                                self.assertTrue(pfmri.startswith(
                                    "pkg:/l3"))
                                got_l3 = True
                self.assertTrue(got_top and got_l1 and got_l2 and got_l3, "Got "
                    "the right number of dependencies but missed one of the "
                    "expected ones. Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[top_path]])))

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

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([cs2_path, ksh_path, zones_path],
                        self.api_obj, ["*"])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[cs2_path]), 0)
                self.assertEqual(len(pkg_deps[ksh_path]), 1)
                self.assertEqual(len(pkg_deps[zones_path]), 2,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[zones_path]])))
                got_cs2 = False
                got_ksh = False
                for d in pkg_deps[zones_path]:
                        pfmri = d.attrs["fmri"]
                        if pfmri.startswith("pkg:/cs"):
                                self.assertTrue(pfmri.endswith("-2"))
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
                                self.assertTrue(pfmri.startswith(
                                    "pkg:/ksh"))
                                self.assertEqual(
                                    d.attrs[dependencies.files_prefix],
                                    ["usr/bin/ksh"])
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "link")
                                got_ksh = True
                self.assertTrue(got_cs2 and got_ksh, "Got the right number "
                    "of dependencies but missed one of the expected ones. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[zones_path]])))

        def test_bug_18315_1(self):
                """Test that when two packages deliver a link which is needed in
                a dependency, a require-any dependency is created."""

                l1_path = self.make_manifest(self.bug_18315_link1_manf)
                l2_path = self.make_manifest(self.bug_18315_link2_manf)
                der_path = self.make_manifest(self.bug_18315_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_dependee_manf)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [l1_path, l2_path, der_path, dee_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 2,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[der_path]])))
                for d in pkg_deps[der_path]:
                        if d.attrs["type"] == "require":
                                self.assertTrue(d.attrs["fmri"].startswith(
                                    "pkg:/dependee"))
                        else:
                                self.assertEqual(d.attrs["type"], "require-any")
                                self.assertEqual(len(d.attrs["fmri"]), 2)
                                fmri0 = d.attrs["fmri"][0]
                                fmri1 = d.attrs["fmri"][1]
                                self.assertTrue(
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

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([l1_path, l2_path, der_path,
                        dee_path, lv1_path, lv2_path, lv3_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 7)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 5,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[der_path]])))
                for d in pkg_deps[der_path]:
                        if d.attrs["type"] == "require":
                                if d.attrs.get("variant.arch", None) == "foo":
                                        self.assertTrue(d.attrs["fmri"].startswith(
                                            "pkg:/link5"))
                                else:
                                        self.assertTrue(d.attrs["fmri"].startswith(
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
depend fmri=link1@1-1 type=require
"""
                l1_path = self.make_manifest(self.bug_18315_link1_manf)
                l2_path = self.make_manifest(self.bug_18315_link2_manf)
                der_path = self.make_manifest(bug_18318_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_dependee_manf)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [l1_path, l2_path, der_path, dee_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 2,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[der_path]])))
                for d in pkg_deps[der_path]:
                        self.assertEqual(d.attrs["type"], "require")
                        if d.attrs["fmri"].startswith("pkg:/dependee"):
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "elf")
                        else:
                                self.assertEqual(d.attrs["fmri"], "link1@1-1")

                # Test that things work when the order of the require-any and
                # require dependencies are changed and when the require
                # dependency is on the second fmri instead of the first.
                bug_18318_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
depend fmri=link2@1-1 type=require
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
"""
                der_path = self.make_manifest(bug_18318_depender_manf)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [l1_path, l2_path, der_path, dee_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 2,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[der_path]])))
                for d in pkg_deps[der_path]:
                        self.assertEqual(d.attrs["type"], "require")
                        if d.attrs["fmri"].startswith("pkg:/dependee"):
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "elf")
                        else:
                                self.assertEqual(d.attrs["fmri"], "link2@1-1")

                # Check that the require-any dependency isn't removed when the
                # require dependency is on an unversioned or lower version than
                # the require-any.
                bug_18318_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
depend fmri=link1 type=require
"""
                l1_path = self.make_manifest(self.bug_18315_link1_manf)
                l2_path = self.make_manifest(self.bug_18315_link2_manf)
                der_path = self.make_manifest(bug_18318_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_dependee_manf)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [l1_path, l2_path, der_path, dee_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 3,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[der_path]])))
                have_req_any = False
                for d in pkg_deps[der_path]:
                        if d.attrs["type"] == "require-any":
                                self.assertEqual(len(d.attrlist("fmri")), 2)
                                have_req_any = True
                        elif d.attrs["fmri"].startswith("pkg:/dependee"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "elf")
                        else:
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["fmri"], "link1")
                have_req_any = True

                bug_18318_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
depend fmri=link1@0.1 type=require
"""
                l1_path = self.make_manifest(self.bug_18315_link1_manf)
                l2_path = self.make_manifest(self.bug_18315_link2_manf)
                der_path = self.make_manifest(bug_18318_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_dependee_manf)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [l1_path, l2_path, der_path, dee_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 3,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[der_path]])))
                have_req_any = False
                for d in pkg_deps[der_path]:
                        if d.attrs["type"] == "require-any":
                                self.assertEqual(len(d.attrlist("fmri")), 2)
                                have_req_any = True
                        elif d.attrs["fmri"].startswith("pkg:/dependee"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "elf")
                        else:
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["fmri"], "link1@0.1")
                have_req_any = True

        def test_bug_18318_2(self):
                """Test that a manually tagged dependency cancels out
                require-any dependencies which contain that fmri."""

                bug_18318_var_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
depend fmri=link1@1-1 type=require
"""
                lv1_path = self.make_manifest(self.bug_18315_var_link1_manf)
                lv2_path = self.make_manifest(self.bug_18315_var_link2_manf)
                lv3_path = self.make_manifest(self.bug_18315_var_link3_manf)
                l1_path = self.make_manifest(self.bug_18315_var_link4_manf)
                l2_path = self.make_manifest(self.bug_18315_var_link5_manf)
                der_path = self.make_manifest(bug_18318_var_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_var_dependee_manf)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([l1_path, l2_path,
                        der_path, dee_path, lv1_path, lv2_path, lv3_path],
                        self.api_obj, [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(warnings), 2)
                for i in range(len(errs)):
                        self.assertTrue(isinstance(errs[i],
                            dependencies.DropPackageWarning))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 7)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 3,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[der_path]])))
                for d in pkg_deps[der_path]:
                        self.assertEqual(d.attrs["type"], "require")
                        if d.attrs["fmri"].startswith("pkg:/dependee"):
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "elf")
                        elif d.attrs["fmri"].startswith("pkg:/link5"):
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "link")
                        else:
                                self.assertEqual(d.attrs["fmri"],"link1@1-1")

        def test_bug_18318_3(self):
                """Test that a manually tagged dependency with variants cancels
                out require-any dependencies which contain that fmri."""

                bug_18318_var_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
depend fmri=link1@1-1 type=require variant.arch=sparc
"""
                lv1_path = self.make_manifest(self.bug_18315_var_link1_manf)
                lv2_path = self.make_manifest(self.bug_18315_var_link2_manf)
                lv3_path = self.make_manifest(self.bug_18315_var_link3_manf)
                l1_path = self.make_manifest(self.bug_18315_var_link4_manf)
                l2_path = self.make_manifest(self.bug_18315_var_link5_manf)
                der_path = self.make_manifest(bug_18318_var_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_var_dependee_manf)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([l1_path, l2_path, der_path,
                        dee_path, lv1_path, lv2_path, lv3_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 7)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 5,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[der_path]])))
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
                                self.assertEqual(d.attrs["fmri"], "link1@1-1")
                                self.assertEqual(d.attrs["type"], "require")

                # Now test with the manual dependency valid when variant.arch is
                # i386, this should clobber more require-any dependencies.
                bug_18318_var_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
depend fmri=link1@1-1 type=require variant.arch=i386
"""

                der_path = self.make_manifest(bug_18318_var_depender_manf)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([l1_path, l2_path, der_path,
                        dee_path, lv1_path, lv2_path, lv3_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(warnings), 1)
                self.assertTrue(isinstance(warnings[0],
                    dependencies.DropPackageWarning))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 7)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 4,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[der_path]])))
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
                                self.assertEqual(d.attrs["fmri"], "link1@1-1")
                                self.assertEqual(d.attrs["type"], "require")

        def test_bug_18318_4(self):
                """Test that automatically generated dependencies can cancel
                require-any dependencies."""

                bug_18318_var_depender_manf = """ \
set name=pkg.fmri value=depender@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib/64 pkg.depend.reason=usr/bin/binary pkg.debug.depend.type=elf type=require
depend fmri=link1@1 fmri=link2@1 fmri=link3@1 fmri=link4@1 type=require-any variant.arch=i386
depend fmri=link2@1 fmri=link3@1 fmri=link4@1 type=require-any
depend fmri=__TBD pkg.debug.depend.reason=usr/bin/bar pkg.debug.depend.file=usr/bin/baz pkg.debug.depend.type=hardlink type=require variant.arch=i386
"""

                bug_18318_var_link1_manf = """ \
set name=pkg.fmri value=link1@1,5.11-1
set name=variant.arch value=i386 value=sparc value=foo
set name=variant.opensolaris.zone value=global value=nonglobal
link path=lib/64 target=amd64 variant.arch=i386
link path=lib/64 target=amd64 variant.arch=sparc
file NOHASH path=usr/bin/baz group=sys mode=0600 owner=root
"""

                lv1_path = self.make_manifest(bug_18318_var_link1_manf)
                lv2_path = self.make_manifest(self.bug_18315_var_link2_manf)
                lv3_path = self.make_manifest(self.bug_18315_var_link3_manf)
                l1_path = self.make_manifest(self.bug_18315_var_link4_manf)
                l2_path = self.make_manifest(self.bug_18315_var_link5_manf)
                der_path = self.make_manifest(bug_18318_var_depender_manf)
                dee_path = self.make_manifest(self.bug_18315_var_dependee_manf)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([l1_path, l2_path, der_path,
                        dee_path, lv1_path, lv2_path, lv3_path], self.api_obj,
                        [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(warnings), 1)
                self.assertTrue(isinstance(warnings[0],
                    dependencies.DropPackageWarning))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 7)
                self.assertEqual(len(pkg_deps[l1_path]), 0)
                self.assertEqual(len(pkg_deps[l2_path]), 0)
                self.assertEqual(len(pkg_deps[dee_path]), 0)
                self.assertEqual(len(pkg_deps[der_path]), 5,
                    "Got wrong number of pkgdeps for the dependent package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[der_path]])))
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
                                self.assertTrue(
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
file NOHASH path=usr/lib/amd64/lib.so.1 group=sys mode=0644 owner=root
file NOHASH path=usr/bin/prog group=sys mode=0644 owner=root
depend fmri=__TBD pkg.debug.depend.reason=usr/bin/prog pkg.debug.depend.file=usr/lib/64/lib.so.1 pkg.debug.depend.type=elf type=require
"""

                link_manf = """ \
set name=pkg.fmri value=link1@1,5.11-1
link path=usr/lib/64 target=amd64
"""
                file_path = self.make_manifest(file_manf)
                link_path = self.make_manifest(link_manf)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([file_path, link_path],
                        self.api_obj, [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[link_path]), 0)
                self.assertEqual(len(pkg_deps[file_path]), 1,
                    "Got wrong number of pkgdeps for the file package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[file_path]])))
                dep = pkg_deps[file_path][0]
                self.assertEqual(dep.attrs["type"], "require",
                    "type was {0} instead of require\ndep:{1}".format(
                    dep.attrs["type"], dep))
                self.assertTrue("predicate" not in dep.attrs)
                self.assertTrue(dep.attrs["fmri"].startswith("pkg:/link1"))
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

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([dep_path, ksh_path, cos_path],
                        self.api_obj, [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[ksh_path]), 0)
                self.assertEqual(len(pkg_deps[cos_path]), 0)
                self.assertEqual(len(pkg_deps[dep_path]), 2,
                    "Got wrong number of pkgdeps for the file package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[dep_path]])))
                for dep in pkg_deps[dep_path]:
                        self.assertTrue("variant.foo" not in dep.attrs, str(dep))
                        self.assertTrue("variant.debug.osnet" not in
                            dep.attrs, str(dep))
                        self.assertTrue("variant.opensolaris.zone" not in
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

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([dep_path, ksh_path, cos_path],
                        self.api_obj, [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[ksh_path]), 0)
                self.assertEqual(len(pkg_deps[cos_path]), 0)
                self.assertEqual(len(pkg_deps[dep_path]), 2,
                    "Got wrong number of pkgdeps for the file package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[dep_path]])))
                for dep in pkg_deps[dep_path]:
                        self.assertTrue("variant.opensolaris.zone" not in
                            dep.attrs, str(dep))
                        self.assertTrue("variant.debug.osnet" not in
                            dep.attrs, str(dep))

        def test_bug_19009_conditional_collapsing_corner_cases(self):
                """Check that conditional dependencies are handled correctly in
                unusual situations."""

                # Check that conditionals are only reduced to required
                # dependencies if the require dependency specifies a successor
                # to the predicate fmri.
                manf = """
set name=pkg.fmri value=foo@1.0,5.11-1
depend fmri=pkg:/a@0-1 type=conditional predicate=pkg:/b@2-1
depend fmri=pkg:/b@1-1 type=require
"""

                manf_path = self.make_manifest(manf)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([manf_path], self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["a", "b"]), external_deps)
                self.assertEqual(len(errs), 0,
                    "\n".join([str(e) for e in errs]))
                self.debug("pkg_deps:{0}".format(pkg_deps))
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[manf_path]), 2)
                for d in pkg_deps[manf_path]:
                        if d.attrs["fmri"].startswith("pkg:/a"):
                                self.assertEqual(d.attrs["type"], "conditional")

                # The following tests check that conditional collapsing happens
                # correctly in the face of variants of conditional and require
                # dependencies.

                manf = """
set name=pkg.fmri value=foo@1.0,5.11-1
set name=variant.num value=one value=two
depend fmri=pkg:/a@0-1 type=conditional predicate=pkg:/b@2-1
depend fmri=pkg:/b@2-1 type=require variant.num=two
"""

                manf_path = self.make_manifest(manf)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([manf_path], self.api_obj, [])
                self.assertEqual(len(errs), 0,
                    "\n".join([str(e) for e in errs]))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["a", "b"]), external_deps)
                self.debug("pkg_deps:{0}".format(pkg_deps))
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[manf_path]), 3,
                    "Expected 3 dependencies got {0}. Deps are:\n{1}".format(
                    len(pkg_deps[manf_path]), "\n".join(
                    [str(s) for s in pkg_deps[manf_path]])))
                have_req = False
                have_uncollapsed_cond = False
                have_collapsed_cond = False
                for d in pkg_deps[manf_path]:
                        if d.attrs["fmri"].startswith("pkg:/b"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["variant.num"], "two")
                                have_req = True
                        elif d.attrs["type"] == "conditional":
                                self.assertEqual(d.attrs["fmri"],
                                    "pkg:/a@0-1")
                                self.assertEqual(d.attrs["variant.num"], "one")
                                self.assertTrue("predicate" in d.attrs)
                                have_uncollapsed_cond = True
                        else:
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["fmri"],
                                    "pkg:/a@0-1")
                                self.assertEqual(d.attrs["variant.num"], "two")
                                self.assertTrue("predicate" not in d.attrs)
                                have_collapsed_cond = True
                self.assertTrue(have_req)
                self.assertTrue(have_uncollapsed_cond)
                self.assertTrue(have_collapsed_cond)

                manf = """
set name=pkg.fmri value=foo@1.0,5.11-1
set name=variant.num value=one value=two
depend fmri=pkg:/a@0-1 type=conditional predicate=pkg:/b@2-1 variant.num=two
depend fmri=pkg:/b@2-1 type=require
"""

                manf_path = self.make_manifest(manf)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([manf_path], self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["a", "b"]), external_deps)
                self.assertEqual(len(errs), 0,
                    "\n".join([str(e) for e in errs]))
                self.debug("pkg_deps:{0}".format(pkg_deps))
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[manf_path]), 2)
                have_req = False
                have_collapsed_cond = False
                for d in pkg_deps[manf_path]:
                        if d.attrs["fmri"].startswith("pkg:/b"):
                                self.assertEqual(d.attrs["type"], "require")
                                have_req = True
                        else:
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["fmri"],
                                    "pkg:/a@0-1")
                                self.assertEqual(d.attrs["variant.num"], "two")
                                self.assertTrue("predicate" not in d.attrs)
                                have_collapsed_cond = True
                self.assertTrue(have_req)
                self.assertTrue(have_collapsed_cond)

                manf = """
set name=pkg.fmri value=foo@1.0,5.11-1
set name=variant.num value=one value=two
depend fmri=pkg:/a@0-1 type=conditional predicate=pkg:/b@2-1 variant.num=one
depend fmri=pkg:/b@2-1 type=require variant.num=two
"""

                manf_path = self.make_manifest(manf)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([manf_path], self.api_obj, [])
                self.assertEqual(len(errs), 0,
                    "\n".join([str(e) for e in errs]))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["a", "b"]), external_deps)
                self.debug("pkg_deps:{0}".format(pkg_deps))
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[manf_path]), 2)
                have_req = False
                have_uncollapsed_cond = False
                for d in pkg_deps[manf_path]:
                        if d.attrs["fmri"].startswith("pkg:/b"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["variant.num"], "two")
                                have_req = True
                        else:
                                self.assertEqual(d.attrs["type"], "conditional")
                                self.assertEqual(d.attrs["fmri"],
                                    "pkg:/a@0-1")
                                self.assertEqual(d.attrs["variant.num"], "one")
                                self.assertTrue("predicate" in d.attrs)
                                have_uncollapsed_cond = True
                self.assertTrue(have_req)
                self.assertTrue(have_uncollapsed_cond)

        def test_bug_19009_collapsing_conditional_to_require_any(self):
                """Check that conditional dependencies don't get collapsed into
                require-any dependencies and that manually specified
                dependencies aren't improperly collapsed."""

                # Check that manually specified conditional dependencies aren't
                # collapsed into require-any dependencies.

                manf = """
set name=pkg.fmri value=foo@1.0,5.11-1
depend fmri=pkg:/a@0-1 type=conditional predicate=pkg:/b@2-1
depend fmri=pkg:/c@0-1 type=conditional predicate=pkg:/b@2-1
depend fmri=pkg:/b@2-1 type=require
"""

                manf_path = self.make_manifest(manf)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([manf_path], self.api_obj, [])
                self.assertEqual(len(errs), 0,
                    "\n".join([str(e) for e in errs]))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["a", "b", "c"]), external_deps)
                self.debug("pkg_deps:{0}".format(pkg_deps))
                self.assertEqual(len(pkg_deps), 1)
                self.assertEqual(len(pkg_deps[manf_path]), 3)
                have_req = False
                have_cond_a = False
                have_cond_c = False
                for d in pkg_deps[manf_path]:
                        if d.attrs["fmri"].startswith("pkg:/b"):
                                self.assertEqual(d.attrs["type"], "require")
                                have_req = True
                        elif d.attrs["fmri"].startswith("pkg:/a"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["fmri"],
                                    "pkg:/a@0-1")
                                have_cond_a = True
                        else:
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["fmri"],
                                    "pkg:/c@0-1")
                                have_cond_c = True
                self.assertTrue(have_req)
                self.assertTrue(have_cond_a)
                self.assertTrue(have_cond_c)

                # Check that manually specified conditional dependencies aren't
                # collapsed into require-any dependencies even if other
                # conditional dependencies are being reduced to require-any
                # dependencies.  If the manual dependencies were not included in
                # the manifest, then a require dependency on b and a require-any
                # dependency on a and c would be produced.  Since the manual
                # conditional dependencies on a and c will reduce to simple
                # require dependencies on a and c, the require-any dependency on
                # a and c will be dropped.

                manf = """
set name=pkg.fmri value=foo@1.0,5.11-1
depend fmri=pkg:/a@3-1 type=conditional predicate=pkg:/b@2-1
depend fmri=pkg:/c@3-1 type=conditional predicate=pkg:/b@2-1
depend fmri=pkg:/b@2-1 type=require
depend fmri=__TBD pkg.debug.depend.file=var/log/syslog pkg.debug.depend.reason=usr/bar pkg.debug.depend.type=hardlink type=require
"""

                a_manf = """
set name=pkg.fmri value=a@0.0,5.11-1
link path=var/log/syslog target=bar
"""

                c_manf = """
set name=pkg.fmri value=c@0.0,5.11-1
link path=var/log/syslog target=bar
"""

                b_manf = """
set name=pkg.fmri value=b@2.0,5.11-1
file NOHASH group=sys mode=0600 owner=root path=var/log/bar
"""
                manf_path = self.make_manifest(manf)
                a_path = self.make_manifest(a_manf)
                b_path = self.make_manifest(b_manf)
                c_path = self.make_manifest(c_manf)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [manf_path, a_path, b_path, c_path],
                        self.api_obj, [])
                self.assertEqual(len(errs), 0,
                    "\n".join([str(e) for e in errs]))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.debug("pkg_deps:\n{0}".format("\n".join(
                    [str(d) for d in pkg_deps[manf_path]])))
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[manf_path]), 4)
                have_req = 0
                have_cond_a = False
                have_cond_c = False
                for d in pkg_deps[manf_path]:
                        if d.attrs["fmri"].startswith("pkg:/b"):
                                self.assertEqual(d.attrs["type"], "require")
                                have_req += 1
                        elif d.attrs["fmri"].startswith("pkg:/a"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["fmri"],
                                    "pkg:/a@3-1")
                                have_cond_a = True
                        else:
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["fmri"],
                                    "pkg:/c@3-1")
                                have_cond_c = True
                self.assertEqual(have_req, 2)
                self.assertTrue(have_cond_a)
                self.assertTrue(have_cond_c)

                # Check that an inferred require-any dependency will not be
                # removed if the require dependencies in the package are at a
                # lower version of the pacakge.

                manf = """
set name=pkg.fmri value=foo@1.0,5.11-1
depend fmri=pkg:/a@0-1 type=conditional predicate=pkg:/b@2-1
depend fmri=pkg:/c@0-1 type=conditional predicate=pkg:/b@2-1
depend fmri=pkg:/b@2-1 type=require
depend fmri=__TBD pkg.debug.depend.file=var/log/syslog pkg.debug.depend.reason=usr/bar pkg.debug.depend.type=hardlink type=require
"""

                a_manf = """
set name=pkg.fmri value=a@2,5.11-1
link path=var/log/syslog target=bar
"""

                c_manf = """
set name=pkg.fmri value=c@2,5.11-1
link path=var/log/syslog target=bar
"""

                b_manf = """
set name=pkg.fmri value=b@2.0,5.11-1
file NOHASH group=sys mode=0600 owner=root path=var/log/bar
"""
                manf_path = self.make_manifest(manf)
                a_path = self.make_manifest(a_manf)
                b_path = self.make_manifest(b_manf)
                c_path = self.make_manifest(c_manf)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([manf_path, a_path, b_path, c_path],
                        self.api_obj, [])
                self.assertEqual(len(errs), 0,
                    "\n".join([str(e) for e in errs]))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.debug("pkg_deps:\n{0}".format("\n".join(
                    [str(d) for d in pkg_deps[manf_path]])))
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[manf_path]), 5)
                have_req = 0
                have_cond_a = False
                have_cond_c = False
                have_req_any = False
                for d in pkg_deps[manf_path]:
                        if d.attrs["type"] == "require-any":
                                self.assertEqual(set(d.attrlist("fmri")),
                                    set(["pkg:/a@2-1", "pkg:/c@2-1"]))
                                self.assertTrue("predicate" not in d.attrs)
                                have_req_any = True
                        elif d.attrs["fmri"].startswith("pkg:/b"):
                                self.assertEqual(d.attrs["type"], "require")
                                have_req += 1
                        elif d.attrs["fmri"].startswith("pkg:/a"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["fmri"],
                                    "pkg:/a@0-1")
                                have_cond_a = True
                        elif d.attrs["fmri"].startswith("pkg:/c"):
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(d.attrs["fmri"],
                                    "pkg:/c@0-1")
                                have_cond_c = True
                self.assertEqual(have_req, 2)
                self.assertTrue(have_cond_a)
                self.assertTrue(have_cond_c)
                self.assertTrue(have_req_any)

        def __check_19009_results(self, pkg_deps, errs, paths,
            expected_conditionals, expected_require_any, expected_require,
            expected_num_deps):
                """Check that the generated dependencies match the expected
                dependencies.  This function is designed for tests associated
                with bug 19009."""

                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(pkg_deps), len(paths))
                # Only the first manifest should have any dependencies since the
                # others only provide files and links.
                for p in paths[1:]:
                        self.assertEqual(len(pkg_deps[p]), 0,
                            "Got unexpected dependencies for {0}.  Dependencies "
                            "are:\n{1}".format(p, pkg_deps[p]))
                deps = pkg_deps[paths[0]]
                self.debug("Dependencies are:\n{0}".format(
                    "\n".join([str(d) for d in deps])))
                self.assertEqual(len(deps), expected_num_deps,
                    "Expected {0} dependencies got {1}. The dependencies "
                    "were:\n\t{2}".format(expected_num_deps, len(deps),
                    "\n\t".join([str(s) for s in deps])))
                lec = len(expected_conditionals)
                lera = len(expected_require_any)
                ler = len(expected_require)
                self.debug("ec:{0} era:{1} er:{2}".format(lec, lera, ler))
                self.assertEqual(expected_num_deps, lec + lera + ler,
                    "Manually expected {0} but the number of dependencies in "
                    "the expected types was {1}. The dependencies were:\n\t{2}".format(
                    len(deps), lec + lera + ler,
                    "\n\t".join([str(s) for s in deps])))

                found_conditionals = set()
                found_require = set()
                found_require_any = set()
                for d in deps:
                        if d.attrs["type"] == "require":
                                found_require.add(d.attrs["fmri"])

                        elif d.attrs["type"] == "require-any":
                                found_require_any.add(frozenset(
                                    d.attrs["fmri"]))
                                self.assertTrue(len(d.attrlist("fmri")) > 1)
                        elif d.attrs["type"] == "conditional":
                                found_conditionals.add((d.attrs["fmri"],
                                    d.attrs["predicate"]))
                        else:
                                raise RuntimeError(
                                    "Got unexpected dependency:{0}".format(d))

                self.assertEqualDiff(sorted(expected_conditionals),
                    sorted(found_conditionals))
                self.assertEqualDiff(sorted(expected_require),
                    sorted(found_require))
                expected_but_not_seen = expected_require_any - found_require_any
                seen_but_not_expected = found_require_any - expected_require_any
                self.assertEqualDiff(expected_but_not_seen,
                    seen_but_not_expected)

        def __construct_19009_info(self, chains):
                """Many of the tests for bug 19009 are similar.  This function
                takes a description of the combinations of packages which should
                satisfy a file dependency and generates a set of manifests to
                match that desctiption, the dot encoding of the package
                dependency graph, and the set of expected dependencies of
                different types needed to represent the package dependencies."""

                expected_conditionals = set()
                expected_require_any = set()
                expected_require = set()

                manf_info = {}
                start_pfmri = None
                end_pfmris = set()
                dot_encoding = """\
digraph G {
        rankdir=BT;
        A [shape=box];
"""
                spacer = "        "
                pkg_template = "pkg:/{0}@1.0"

                # Collect the set of package names which should deliver a file.
                for c in chains:
                        self.assertTrue(len(c) > 1)
                        end_pfmris.add(c[-1])
                # If only a single package delivers a file, then a require
                # dependency is expected.
                if len(end_pfmris) == 1:
                        expected_require.add(pkg_template.format(end_pfmris.pop()))
                else:
                        # Otherwise all the package names which ended a chain
                        # form a require-any dependency.
                        for p in end_pfmris:
                                expected_require_any.add(pkg_template.format(p))

                # Determine what dependencies are needed to represent each chain
                # of packages.
                for c in chains:
                        if start_pfmri is None:
                                start_pfmri = c[0]
                        else:
                                self.assertEqual(c[0], start_pfmri)
                        dot_encoding += spacer + "->".join(c) + ";\n"
                        if len(c) > 2:
                                t = [pkg_template.format(p) for p in c]
                                for node, child in zip(t[1:], t[2:]):
                                        if child in expected_require:
                                                expected_require_any.add(node)
                                        else:
                                                expected_conditionals.add(
                                                    (node, child))
                        for pth, pfmri in zip(c, c[1:]):
                                manf_info.setdefault(pfmri, {}).setdefault(
                                    "path", []).append(pth.lower())
                        # Triangles indicate packages which deliver a file.
                        dot_encoding += spacer + c[-1] + " [shape=triangle]\n"
                        manf_info.setdefault(c[-1], {})["provides_file"] = \
                            c[-1].lower()

                expected_require_any = set([frozenset(expected_require_any)])
                dot_encoding += "}"
                # The first manifest always contains only a file dependency.
                manfs = ["""\
set name=pkg.fmri value={pfmri}@1.0
depend type=require fmri=__TBD pkg.debug.depend.file={path} \\
    pkg.debug.depend.reason=needs_{path} pkg.debug.depend.type=elf
""".format(pfmri=start_pfmri, path=start_pfmri.lower())]

                # These templates are used to generate the other manifests.
                template = """\
set name=pkg.fmri value={0}@1.0
"""
                file_template = """\
file path={0} group=sys mode=0600 owner=root
"""
                link_template = """\
link path={path} target={target}
"""
                # Generate each manifest desired.
                for pfmri, detail in sorted(manf_info.items()):
                        m = template.format(pfmri)
                        if "provides_file" in detail:
                                m += file_template.format(detail["provides_file"])
                        for pth in set(detail.get("path", [])):
                                m += link_template.format(
                                    path=pth, target=pfmri.lower())
                        manfs.append(m)

                # Include useful information in the debugging output of the
                # test.
                self.debug("To see the link graph of this test use dot on "
                    "this:\n{0}".format(dot_encoding))
                self.debug("The manifests for this test are:")
                for m in sorted(manfs):
                        self.debug(m + "\n")
                self.debug("Expected conditionals are:")
                for pair in sorted(expected_conditionals):
                        self.debug("\tfmri:{0}\tpredicate:{1}".format(*pair))
                if len(expected_require_any) > 1:
                        self.debug("Expected pfmris in require-any are: {0}".format(
                            " ".join(sorted(expected_require_any))))
                if expected_require:
                        self.debug("Expected pfmri in require is:{0}".format(
                            expected_require))

                return manfs, expected_conditionals, expected_require_any, \
                    expected_require

        def test_bug_19009_inexpressible_1(self):
                """Check that when resolve a configuration of dependencies that
                can't be represented using the existing dependency types, an
                error occurs."""

                chains = [
                    ("A", "B", "E"),
                    ("A", "C", "E"),
                    ("A", "D", "F"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.debug("Deps:\n{0}".format("\n".join([
                    str(d) for d in pkg_deps[paths[0]]])))
                self.assertEqual(len(errs), 1)
                err = errs[0]
                self.assertEqual(len(err.conditionals), 1)
                self.assertTrue(isinstance(err,
                    dependencies.NeedConditionalRequireAny))
                # Check that the exception prints correctly.
                self.debug(err)

        def test_bug_19009_inexpressible_2(self):
                """Check that when resolve a configuration of dependencies that
                can't be represented using the existing dependency types, an
                error occurs."""

                chains = [
                    ("A", "B", "E", "G"),
                    ("A", "C", "E", "G"),
                    ("A", "D", "F")
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.debug("Deps:\n{0}".format("\n".join([
                    str(d) for d in pkg_deps[paths[0]]])))
                self.assertEqual(len(errs), 1)
                err = errs[0]
                self.assertEqual(len(err.conditionals), 1)
                self.assertTrue(isinstance(err,
                    dependencies.NeedConditionalRequireAny))
                # Check that the exception prints correctly.
                self.debug(err)

        def test_bug_19009_inexpressible_3(self):
                """Check that when resolve a configuration of dependencies that
                can't be represented using the existing dependency types, an
                error occurs."""

                chains = [
                    ("A", "B", "D", "F", "H"),
                    ("A", "B", "E", "G", "H"),
                    ("A", "C", "I"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.debug("Deps:\n{0}".format("\n".join([
                    str(d) for d in pkg_deps[paths[0]]])))
                self.assertEqual(len(errs), 1)
                err = errs[0]
                self.assertEqual(len(err.conditionals), 1)
                self.assertTrue(isinstance(err,
                    dependencies.NeedConditionalRequireAny))
                # Check that the exception prints correctly.
                self.debug(err)

        def test_bug_19009_inexpressible_4(self):
                """Check that when resolve a configuration of dependencies that
                can't be represented using the existing dependency types, an
                error occurs."""

                chains = [
                    ("A", "B", "D", "F", "I"),
                    ("A", "B", "E", "H"),
                    ("A", "C", "G", "I"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.debug("Deps:\n{0}".format("\n".join([
                    str(d) for d in pkg_deps[paths[0]]])))
                self.assertEqual(len(errs), 1)
                err = errs[0]
                self.assertEqual(len(err.conditionals), 1)
                self.assertTrue(isinstance(err,
                    dependencies.NeedConditionalRequireAny))
                # Check that the exception prints correctly.
                self.debug(err)

        def test_bug_19009_inexpressible_5(self):
                """Check that when resolve a configuration of dependencies that
                can't be represented using the existing dependency types, an
                error occurs."""

                chains = [
                    ("A", "B", "E"),
                    ("A", "C", "E"),
                    ("A", "D"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.debug("Deps:\n{0}".format("\n".join([
                    str(d) for d in pkg_deps[paths[0]]])))
                self.assertEqual(len(errs), 1)
                err = errs[0]
                self.assertEqual(len(err.conditionals), 1)
                self.assertTrue(isinstance(err,
                    dependencies.NeedConditionalRequireAny))
                # Check that the exception prints correctly.
                self.debug(err)

        def test_bug_19009_inexpressible_with_variants_1(self):
                """Check that when resolve a configuration of dependencies that
                can't be represented using the existing dependency types, an
                error occurs and that the right error happens when variants are
                involved."""

                chains = [
                    ("A", "B", "E"),
                    ("A", "C", "E"),
                    ("A", "D", "F"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                manfs[0] += "set name=variant.num value=one value=two\n"
                manfs[1] += "set name=variant.num value=one\n"
                self.debug("The manifest for package B has been modified to "
                    "only apply when variant.num is one.")

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.debug("Deps:\n{0}".format("\n".join([
                    str(d) for d in pkg_deps[paths[0]]])))

                self.assertEqual(len(errs), 1)
                err = errs[0]
                self.assertTrue(isinstance(err,
                    dependencies.NeedConditionalRequireAny))
                self.assertEqual(len(err.conditionals), 1)
                self.assertEqualDiff(sorted(set([
                    frozenset([("variant.num", "one")])])),
                    sorted(err.conditionals[0][2].sat_set))
                # Check that the exception prints correctly.
                self.debug(err)

        def test_bug_19009_inexpressible_with_variants_2(self):
                """Check that when resolve a configuration of dependencies that
                can't be represented using the existing dependency types, an
                error occurs and that the right error happens when variants are
                involved."""

                chains = [
                    ("A", "B", "E"),
                    ("A", "C", "E"),
                    ("A", "D", "F"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                manfs[0] += "set name=variant.num value=one value=two\n"
                manfs[0] += "set name=variant.foo value=bar value=baz\n"
                manfs[1] += "set name=variant.num value=one\n"
                manfs[1] += "set name=variant.foo value=bar\n"

                self.debug("The manifest for package B has been modified to "
                    "only apply when variant.num is one and variant.foo is "
                    "bar.")

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.debug("Deps:\n{0}".format("\n".join([
                    str(d) for d in pkg_deps[paths[0]]])))
                self.assertEqual(len(errs), 1)
                err = errs[0]
                self.assertTrue(isinstance(err,
                    dependencies.NeedConditionalRequireAny))
                self.assertEqual(len(err.conditionals), 1)
                self.assertEqualDiff(sorted(set([
                    frozenset([("variant.foo", "bar"),
                        ("variant.num", "one")])])),
                    sorted(err.conditionals[0][2].sat_set))
                # Check that the exception prints correctly.
                self.debug(err)

        def test_bug_19009_inexpressible_with_variants_3(self):
                """Check that when resolve a configuration of dependencies that
                can't be represented using the existing dependency types, an
                error occurs and that the right error happens when variants are
                involved."""

                chains = [
                    ("A", "B", "E"),
                    ("A", "C", "E"),
                    ("A", "D", "F"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                manfs[0] += "set name=variant.num value=one value=two\n"
                manfs[0] += "set name=variant.foo value=bar value=baz\n"
                manfs[1] += "set name=variant.num value=one\n"

                self.debug("The manifest for package B has been modified to "
                    "only apply when variant.num is one.")

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.debug("Deps:\n{0}".format("\n".join([
                    str(d) for d in pkg_deps[paths[0]]])))
                self.assertEqual(len(errs), 1)
                err = errs[0]
                self.assertTrue(isinstance(err,
                    dependencies.NeedConditionalRequireAny))
                self.assertEqual(len(err.conditionals), 1)
                expected_vars = set([
                    frozenset([("variant.foo", "bar"), ("variant.num", "one")]),
                    frozenset([("variant.foo", "baz"), ("variant.num", "one")])
                ])
                expected_but_not_seen = expected_vars - \
                    err.conditionals[0][2].sat_set
                seen_but_not_expected = err.conditionals[0][2].sat_set - \
                    expected_vars
                self.assertEqualDiff(expected_but_not_seen,
                    seen_but_not_expected)

                # Check that the exception prints correctly.
                self.debug(err)
                self.assertTrue("variant.foo" not in str(err))

        def test_bug_19009_no_links_one_variant(self):
                """Test that resolve correctly handles multiple packages
                delivering a file which is the target of a file dependency when
                variants are involved."""

                dep_manf_two_val = """\
set name=pkg.fmri value=test@1.0
set name=variant.num value=one value=two
depend type=require fmri=__TBD pkg.debug.depend.file=foo \
    pkg.debug.depend.reason=needs_foo pkg.debug.depend.type=elf
"""

                dep_manf_three_val = """\
set name=pkg.fmri value=test@1.0
set name=variant.num value=one value=two value=three
depend type=require fmri=__TBD pkg.debug.depend.file=foo \
    pkg.debug.depend.reason=needs_foo pkg.debug.depend.type=elf
"""

                res1_manf_1 = """\
set name=pkg.fmri value=res1@1.0
set name=variant.num value=one
file group=bin mode=0555 owner=root path=foo
"""

                res1_manf_13 = """\
set name=pkg.fmri value=res1@1.0
set name=variant.num value=one value=three
file group=bin mode=0555 owner=root path=foo
"""

                res2_manf_12 = """\
set name=pkg.fmri value=res2@1.0
set name=variant.num value=one value=two
file group=bin mode=0555 owner=root path=foo
"""

                res3_manf_3 = """\
set name=pkg.fmri value=res3@1.0
set name=variant.num value=three
file group=bin mode=0555 owner=root path=foo
"""

                res3_manf_23 = """\
set name=pkg.fmri value=res3@1.0
set name=variant.num value=two value=three
file group=bin mode=0555 owner=root path=foo
"""

                dep_path = self.make_manifest(dep_manf_two_val)
                res1_path = self.make_manifest(res1_manf_1)
                res2_path = self.make_manifest(res2_manf_12)

                # Check that one package delivering under all variants and one
                # delivering under a particular combination works.
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([dep_path, res1_path, res2_path],
                        self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[res1_path]), 0)
                self.assertEqual(len(pkg_deps[res2_path]), 0)
                self.assertEqual(len(pkg_deps[dep_path]), 2,
                    "Got wrong number of pkgdeps for the file package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[dep_path]])))
                have_req_any = False
                have_required = False
                for d in pkg_deps[dep_path]:
                        if d.attrs["type"] == "require-any" and \
                            set(d.attrs["fmri"]) == \
                            set(["pkg:/res1@1.0", "pkg:/res2@1.0"]) and \
                            d.attrs["variant.num"] == "one":
                                have_req_any = True
                        elif d.attrs["type"] == "require" and \
                            d.attrs["fmri"] == "pkg:/res2@1.0" and \
                            d.attrs["variant.num"] == "two":
                                have_required = True
                        else:
                                raise RuntimeError("Unexpected dependency:{0}"%
                                    d)
                self.assertTrue(have_req_any)
                self.assertTrue(have_required)

                # Check that three packages each delivering under two of three
                # variant values works.
                dep_path = self.make_manifest(dep_manf_three_val)
                res1_path = self.make_manifest(res1_manf_13)
                res2_path = self.make_manifest(res2_manf_12)
                res3_path = self.make_manifest(res3_manf_23)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [dep_path, res1_path, res2_path, res3_path],
                        self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[res1_path]), 0)
                self.assertEqual(len(pkg_deps[res2_path]), 0)
                self.assertEqual(len(pkg_deps[res3_path]), 0)
                self.assertEqual(len(pkg_deps[dep_path]), 3,
                    "Got wrong number of pkgdeps for the file package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[dep_path]])))
                var_one = False
                var_two = False
                var_three = False
                for d in pkg_deps[dep_path]:
                        self.assertEqual(d.attrs["type"], "require-any")
                        if set(d.attrs["fmri"]) == \
                            set(["pkg:/res1@1.0", "pkg:/res2@1.0"]) and \
                            d.attrs["variant.num"] == "one":
                                var_one = True
                        elif set(d.attrs["fmri"]) == \
                            set(["pkg:/res2@1.0", "pkg:/res3@1.0"]) and \
                            d.attrs["variant.num"] == "two":
                                var_two = True
                        elif set(d.attrs["fmri"]) == \
                            set(["pkg:/res1@1.0", "pkg:/res3@1.0"]) and \
                            d.attrs["variant.num"] == "three":
                                var_three = True
                        else:
                                raise RuntimeError(
                                    "Unexpected dependency:{0}".format(d))

        def test_bug_19009_no_links_unvarianted(self):
                """Test that resolve correctly handles multiple packages
                delivering a file which is the target of a file dependency."""

                dep_manf = """\
set name=pkg.fmri value=test@1.0
depend type=require fmri=__TBD pkg.debug.depend.file=foo \
    pkg.debug.depend.reason=needs_foo pkg.debug.depend.type=elf
"""

                res1_manf = """\
set name=pkg.fmri value=res1@1.0
file group=bin mode=0555 owner=root path=foo
"""

                res2_manf = """\
set name=pkg.fmri value=res2@1.0
file group=bin mode=0555 owner=root path=foo
"""

                res3_manf = """\
set name=pkg.fmri value=res3@1.0
file group=bin mode=0555 owner=root path=foo
"""

                dep_path = self.make_manifest(dep_manf)
                res1_path = self.make_manifest(res1_manf)
                res2_path = self.make_manifest(res2_manf)
                res3_path = self.make_manifest(res3_manf)

                # Check that resolving with two packages works...
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([dep_path, res1_path, res2_path],
                        self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[res1_path]), 0)
                self.assertEqual(len(pkg_deps[res2_path]), 0)
                self.assertEqual(len(pkg_deps[dep_path]), 1,
                    "Got wrong number of pkgdeps for the file package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[dep_path]])))
                d = pkg_deps[dep_path][0]
                self.assertEqual(d.attrs["type"], "require-any")
                self.assertEqual(set(d.attrs["fmri"]),
                    set(["pkg:/res1@1.0", "pkg:/res2@1.0"]))

                # And that three does as well.
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [dep_path, res1_path, res2_path, res3_path],
                        self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(pkg_deps), 4)
                self.assertEqual(len(pkg_deps[res1_path]), 0)
                self.assertEqual(len(pkg_deps[res2_path]), 0)
                self.assertEqual(len(pkg_deps[res3_path]), 0)
                self.assertEqual(len(pkg_deps[dep_path]), 1,
                    "Got wrong number of pkgdeps for the file package. "
                    "Deps were:\n{0}".format(
                    "\n".join([str(d) for d in pkg_deps[dep_path]])))
                d = pkg_deps[dep_path][0]
                self.assertEqual(d.attrs["type"], "require-any")
                self.assertEqual(set(d.attrs["fmri"]),
                    set(["pkg:/res1@1.0", "pkg:/res2@1.0", "pkg:/res3@1.0"]))

        def test_bug_19009_remove_paths_1(self):
                """Test that when a require dependency on one of the packages in
                the inferred require-any dependency exists, the path to that
                package is chosen by resolve."""

                chains = [
                    ("A", "B", "D"),
                    ("A", "C", "E"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                orig_a_manf = manfs[0]
                dep_line = "depend fmri=pkg:/D@2.0 type=require\n"

                self.debug("Adding the following line to the manifest for "
                    "A:\n:{0}".format(dep_line))

                new_a_manf = orig_a_manf + dep_line
                paths = [
                    self.make_manifest(m) for m in ([new_a_manf] + manfs[1:])
                ]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                expected_require_any = set()
                expected_conditionals = set()
                expected_require = set(["pkg:/D@2.0", "pkg:/B@1.0"])
                self.debug("Because of the additional dependency, there should "
                    "be two require dependencies and no conditional "
                    "dependencies.")
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 2)

        def test_bug_19009_remove_paths_2(self):
                """Test that when a require dependency on one of the packages in
                the inferred require-any dependency exists under some variant
                combinations, the path to that package is chosen by resolve only
                under those variant combinations."""

                chains = [
                    ("A", "B", "D"),
                    ("A", "C", "E"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                orig_a_manf = manfs[0]
                dep_line = """\
set name=variant.num value=one value=two
depend fmri=pkg:/D@2.0 type=require variant.num=one
"""
                self.debug("Adding the following lines to the manifest for "
                    "A:\n:{0}".format(dep_line))

                new_a_manf = orig_a_manf + dep_line
                paths = [
                    self.make_manifest(m) for m in ([new_a_manf] + manfs[1:])
                ]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)

                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(pkg_deps), len(paths))
                for p in paths[1:]:
                        self.assertEqual(len(pkg_deps[p]), 0, "Got unexpected "
                            "dependencies for {0}.  Dependencies are:\n{1}".format(
                            p, pkg_deps[p]))
                deps = pkg_deps[paths[0]]
                self.debug("Dependencies are:\n{0}".format("\n".join(
                    [str(d) for d in deps])))
                self.debug("Five dependencies are expected.  Two require "
                    "dependencies when variant.num=one, and three (one "
                    "require-any and two conditional) when variant.num=two.")
                expected_require = set(["pkg:/D@2.0", "pkg:/B@1.0"])
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 5)

                # Now check the the variants are set correctly on all the
                # dependencies.
                for d in deps:
                        if d.attrs["type"] in ("conditional", "require-any"):
                                self.assertEqual(
                                    d.attrs.get("variant.num", None), "two",
                                    "Bad dependency was:{0}".format(d))
                        else:
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs.get("variant.num", None), "one",
                                    "Bad dependency was:{0}".format(d))

        def test_bug_19009_remove_paths_3(self):
                """Test that when a require dependency on one of the packages in
                the inferred require-any dependency exists under some variant
                combinations, the path to that package is chosen by resolve only
                under those variant combinations."""

                chains = [
                    ("A", "B", "D", "F"),
                    ("A", "C", "E", "G"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                orig_a_manf = manfs[0]
                dep_line = """\
set name=variant.num value=one value=two
depend fmri=pkg:/F@2.0 type=require variant.num=one
"""
                self.debug("Adding the following lines to the manifest for "
                    "A:\n{0}".format(dep_line))
                new_a_manf = orig_a_manf + dep_line
                paths = [
                    self.make_manifest(m) for m in ([new_a_manf] + manfs[1:])
                ]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)

                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(pkg_deps), len(paths))
                for p in paths[1:]:
                        self.assertEqual(len(pkg_deps[p]), 0, "Got unexpected "
                            "dependencies for {0}.  Dependencies are:\n{1}".format(
                            p, pkg_deps[p]))
                deps = pkg_deps[paths[0]]
                self.debug("Dependencies are:\n{0}".format("\n".join(
                    [str(d) for d in deps])))
                expected_require = set(["pkg:/B@1.0", "pkg:/D@1.0",
                    "pkg:/F@2.0"])
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 8)

                # Now check the the variants are set correctly on all the
                # dependencies.
                for d in deps:
                        if d.attrs["type"] in ("conditional", "require-any"):
                                self.assertEqual(
                                    d.attrs.get("variant.num", None), "two",
                                    "Bad dependency was:{0}".format(d))
                        else:
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs.get("variant.num", None), "one",
                                    "Bad dependency was:{0}".format(d))

        def test_bug_19009_remove_paths_4(self):
                """Test that when a require dependency on one of the packages in
                the inferred require-any dependency exists under some variant
                combinations, the path to that package is chosen by resolve only
                under those variant combinations."""

                chains = [
                    ("A", "B", "D", "F"),
                    ("A", "C", "E", "G"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                orig_a_manf = manfs[0]
                dep_line = """\
set name=variant.num value=one value=two
depend fmri=pkg:/F@2.0 type=require variant.num=one
depend fmri=pkg:/G@2.0 type=require variant.num=two
"""
                self.debug("Adding the following lines to the manifest for "
                    "A:\n{0}".format(dep_line))
                new_a_manf = orig_a_manf + dep_line
                paths = [
                    self.make_manifest(m) for m in ([new_a_manf] + manfs[1:])
                ]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)

                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(pkg_deps), len(paths))
                for p in paths[1:]:
                        self.assertEqual(len(pkg_deps[p]), 0, "Got unexpected "
                            "dependencies for {0}.  Dependencies are:\n{1}".format(
                            p, pkg_deps[p]))
                deps = pkg_deps[paths[0]]
                self.debug("Dependencies are:\n{0}".format("\n".join(
                    [str(d) for d in deps])))
                self.debug("Six require dependencies are expected since all "
                    "conditional dependencies collapse to require dependencies "
                    "under one of the two variants.")
                expected_require_any = set()
                expected_conditionals = set()
                expected_require = set(["pkg:/B@1.0", "pkg:/C@1.0",
                    "pkg:/D@1.0", "pkg:/E@1.0", "pkg:/F@2.0", "pkg:/G@2.0"])
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 6)

                # Now check the the variants are set correctly on all the
                # dependencies.
                for d in deps:
                        if d.attrs["fmri"] in \
                            ("pkg:/B@1.0", "pkg:/D@1.0", "pkg:/F@2.0"):
                                self.assertEqual(
                                    d.attrs.get("variant.num", None), "one")
                        elif d.attrs["fmri"] in \
                            ("pkg:/C@1.0", "pkg:/E@1.0", "pkg:/G@2.0"):
                                self.assertEqual(
                                    d.attrs.get("variant.num", None), "two")
                        else:
                                raise RuntimeError("Unexpected fmri in "
                                    "dependency:{0}".format(d))

        def test_bug_19009_remove_paths_5(self):
                """Test that when a require dependency on the middle of a
                dependency chain exists under a particular variant combination,
                the right thing happens."""

                chains = [
                    ("A", "B", "D", "F"),
                    ("A", "C", "E", "G"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                orig_a_manf = manfs[0]
                dep_line = """\
set name=variant.num value=one value=two
depend fmri=pkg:/D@2.0 type=require variant.num=one
"""
                self.debug("Adding the following lines to the manifest for "
                    "A:\n{0}".format(dep_line))
                new_a_manf = orig_a_manf + dep_line
                paths = [
                    self.make_manifest(m) for m in ([new_a_manf] + manfs[1:])
                ]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)

                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(pkg_deps), len(paths))
                for p in paths[1:]:
                        self.assertEqual(len(pkg_deps[p]), 0, "Got unexpected "
                            "dependencies for {0}.  Dependencies are:\n{1}".format(
                            p, pkg_deps[p]))
                deps = pkg_deps[paths[0]]
                self.debug("Dependencies are:\n{0}".format("\n".join(
                    [str(d) for d in deps])))
                self.debug("Seven dependencies are expected:\ntwo require "
                    "dependencies (on B and D) when variant.num is one\nfour "
                    "conditional dependencies (B->D, D->F, C->E, E->G) when "
                    "variant.num is two\none require-any dependency on F and G "
                    "when variant.num is two")
                expected_require = set(["pkg:/B@1.0", "pkg:/D@2.0"])
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 7)

                # Now check the the variants are set correctly on all the
                # dependencies.
                for d in deps:
                        if d.attrs["fmri"] in ("pkg:/C@1.0", "pkg:/E@1.0"):
                                self.assertEqual(d.attrs["type"], "conditional")
                                self.assertTrue("variant.num" not in d.attrs)
                        elif d.attrs["fmri"] == "pkg:/B@1.0":
                                if d.attrs["type"] == "conditional":
                                        self.assertEqual(
                                            d.attrs.get("variant.num", None),
                                            "two")
                                else:
                                        self.assertEqual(d.attrs["type"],
                                            "require")
                                        self.assertEqual(
                                            d.attrs.get("variant.num", None),
                                            "one")
                        elif d.attrs["fmri"] == "pkg:/D@1.0":
                                self.assertEqual(d.attrs["type"], "conditional")
                                self.assertEqual(
                                    d.attrs.get("variant.num", None),
                                    "two")
                        elif d.attrs["fmri"] == "pkg:/D@2.0":
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertEqual(
                                    d.attrs.get("variant.num", None), "one")
                        else:
                                self.assertEqual(d.attrs["type"], "require-any")
                                self.assertEqual(set(d.attrs["fmri"]),
                                    set(["pkg:/F@1.0", "pkg:/G@1.0"]))
                                self.assertTrue("variant.num" not in d.attrs)

        def test_bug_19009_remove_paths_6(self):
                """Test that when a require dependency on the middle of a
                dependency chain exists, the right thing happens."""

                chains = [
                    ("A", "B", "D", "F"),
                    ("A", "C", "E", "G"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                orig_a_manf = manfs[0]
                dep_line = """\
set name=variant.num value=one value=two
depend fmri=pkg:/D@2.0 type=require
"""
                self.debug("Adding the following lines to the manifest for "
                    "A:\n{0}".format(dep_line))
                new_a_manf = orig_a_manf + dep_line
                paths = [
                    self.make_manifest(m) for m in ([new_a_manf] + manfs[1:])
                ]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)

                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e) for e in errs])))
                self.assertEqual(len(pkg_deps), len(paths))
                for p in paths[1:]:
                        self.assertEqual(len(pkg_deps[p]), 0, "Got unexpected "
                            "dependencies for {0}.  Dependencies are:\n{1}".format(
                            p, pkg_deps[p]))
                deps = pkg_deps[paths[0]]
                self.debug("Dependencies are:\n{0}".format("\n".join(
                    [str(d) for d in deps])))
                self.debug("Five dependencies are expected:\nrequire "
                    "dependencies on B and D\na require-any dependency on F "
                    "and G\nconditional dependencies from C to E and E to G.")
                expected_conditionals.remove(("pkg:/B@1.0", "pkg:/D@1.0"))
                expected_conditionals.remove(("pkg:/D@1.0", "pkg:/F@1.0"))
                expected_require = set(["pkg:/B@1.0", "pkg:/D@2.0"])
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 5)

                # Now check the the variants are set correctly on all the
                # dependencies.
                for d in deps:
                        if d.attrs["fmri"] in ("pkg:/C@1.0", "pkg:/E@1.0"):
                                self.assertEqual(d.attrs["type"], "conditional")
                                self.assertTrue("variant.num" not in d.attrs)
                        elif d.attrs["fmri"] == "pkg:/B@1.0":
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertTrue("variant.num" not in d.attrs)
                        elif d.attrs["fmri"] == "pkg:/D@2.0":
                                self.assertEqual(d.attrs["type"], "require")
                                self.assertTrue("variant.num" not in d.attrs)
                        else:
                                self.assertEqual(d.attrs["type"], "require-any")
                                self.assertEqual(set(d.attrs["fmri"]),
                                    set(["pkg:/F@1.0", "pkg:/G@1.0"]))
                                self.assertTrue("variant.num" not in d.attrs)

        def test_bug_19009_simple_1(self):
                """Check that resolve infers the correct dependencies when more
                than one package delivers a file which satisfies a file
                dependency."""

                chains = [
                    ("A", "B", "D"),
                    ("A", "C", "E"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 3)

        def test_bug_19009_simple_2(self):
                """Check that resolve infers the correct dependencies when more
                than one package delivers a file which satisfies a file
                dependency."""

                chains = [
                    ("A", "B", "E", "H"),
                    ("A", "C", "F", "I"),
                    ("A", "D", "G")
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 6)

        def test_bug_19009_simple_3(self):
                """Check that resolve infers the correct dependencies when more
                than one package delivers a file which satisfies a file
                dependency."""

                chains = [
                    ("A", "B", "D", "F"),
                    ("A", "C", "E", "G"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 5)

        def test_bug_19009_simple_4(self):
                """Check that resolve infers the correct dependencies when more
                than one package delivers a file which satisfies a file
                dependency."""

                chains = [
                    ("A", "B", "D", "F"),
                    ("A", "C", "E", "F"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 4)

        def test_bug_19009_simple_5(self):
                """Check that resolve infers the correct dependencies when more
                than one package delivers a file which satisfies a file
                dependency.  This test also tests bug 19037."""

                chains = [
                    ("A", "B", "D", "F"),
                    ("A", "B", "E", "G"),
                    ("A", "C", "H"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 6)

        def test_bug_19009_simple_6(self):
                """Check that resolve infers the correct dependencies when more
                than one package delivers a file which satisfies a file
                dependency."""

                chains = [
                    ("A", "B", "C", "E"),
                    ("A", "B", "D", "F"),
                ]

                manfs, expected_conditionals, expected_require_any, \
                    expected_require = self.__construct_19009_info(chains)

                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 5)

        def test_bug_19009_two_paths(self):
                """Test that multiple file dependencies don't interact
                improperly with each other when inferring dependencies."""

                a_manf = """\
set name=pkg.fmri value=A@1.0
depend type=require fmri=__TBD pkg.debug.depend.file=a \
    pkg.debug.depend.reason=needs_a pkg.debug.depend.type=elf
depend type=require fmri=__TBD pkg.debug.depend.file=a2 \
    pkg.debug.depend.reason=needs_a pkg.debug.depend.type=elf
"""
                b_manf = """\
set name=pkg.fmri value=B@1.0
link path=a target=b
"""
                c_manf = """\
set name=pkg.fmri value=C@1.0
link path=a target=c
link path=a2 target=c2
"""
                d_manf = """\
set name=pkg.fmri value=D@1.0
file path=d group=sys mode=0600 owner=root
link path=b target=d
"""
                e_manf = """\
set name=pkg.fmri value=E@1.0
file path=e group=sys mode=0600 owner=root
link path=c target=e
file path=e2 group=sys mode=0600 owner=root
link path=c2 target=e2
"""
                f_manf = """\
set name=pkg.fmri value=F@1.0
link path=a2 target=f2
"""
                g_manf = """\
set name=pkg.fmri value=G@1.0
file path=g2 group=sys mode=0600 owner=root
link path=f2 target=g2
"""

                manfs = [a_manf, b_manf, c_manf, d_manf, e_manf, f_manf, g_manf]
                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)

                expected_conditionals = set([("pkg:/B@1.0", "pkg:/D@1.0"),
                    ("pkg:/C@1.0", "pkg:/E@1.0"), ("pkg:/F@1.0", "pkg:/G@1.0")])
                expected_require = []
                expected_require_any = set([
                    frozenset(["pkg:/D@1.0", "pkg:/E@1.0"]),
                    frozenset(["pkg:/E@1.0", "pkg:/G@1.0"])])
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 5)

                a_req_d_manf = a_manf + "depend fmri=pkg:/D@1.0 type=require\n"
                manfs = [a_req_d_manf, b_manf, c_manf, d_manf, e_manf, f_manf,
                    g_manf]
                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)

                expected_conditionals = set([("pkg:/C@1.0", "pkg:/E@1.0"),
                    ("pkg:/F@1.0", "pkg:/G@1.0")])
                expected_require = set(["pkg:/B@1.0", "pkg:/D@1.0"])
                expected_require_any = set([
                    frozenset(["pkg:/E@1.0", "pkg:/G@1.0"])])
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 5)

                a_req_g_manf = a_manf + "depend fmri=pkg:/G@1.0 type=require\n"
                manfs = [a_req_g_manf, b_manf, c_manf, d_manf, e_manf, f_manf,
                    g_manf]
                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)

                expected_conditionals = set([("pkg:/C@1.0", "pkg:/E@1.0"),
                    ("pkg:/B@1.0", "pkg:/D@1.0")])
                expected_require = set(["pkg:/F@1.0", "pkg:/G@1.0"])
                expected_require_any = set([
                    frozenset(["pkg:/D@1.0", "pkg:/E@1.0"])])
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 5)

                a_req_e_manf = a_manf + "depend fmri=pkg:/E@1.0 type=require\n"
                manfs = [a_req_e_manf, b_manf, c_manf, d_manf, e_manf, f_manf,
                    g_manf]
                paths = [self.make_manifest(m) for m in manfs]
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(paths, self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)

                expected_conditionals = set()
                expected_require = set(["pkg:/C@1.0", "pkg:/E@1.0"])
                expected_require_any = set()
                self.__check_19009_results(pkg_deps, errs, paths,
                    expected_conditionals, expected_require_any,
                    expected_require, 2)

        def test_bug_19029(self):
                """Test that a package with an action which doesn't validate
                causes resolve to fail."""

                manf = """
set name=pkg.fmri value=foo@1.0,5.11-1
depend fmri=pkg:/a@0-1 type=conditional
"""
                manf_path = self.make_manifest(manf)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([manf_path], self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(errs), 1)
                self.assertTrue(isinstance(errs[0],
                    actions.InvalidActionAttributesError))

                manf = """
set name=pkg.fmri value=foo@1.0,5.11-1
depend fmri=pkg:/a@0-1 type=conditionalpredicate
"""
                manf_path = self.make_manifest(manf)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([manf_path], self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(errs), 1)
                self.assertTrue(isinstance(errs[0], actions.InvalidActionError))

        def test_duplicate_require_any(self):
                """Test that when one require-any dependency is the subset of
                the other require-any dependency, the superset is omitted."""

                manf = """
set name=pkg.fmri value=foo@1.0,5.11-1
set name=variant.foo value=i386
file NOHASH group=bin mode=0755 owner=root path=usr/bin/perl_app
depend fmri=__TBD pkg.debug.depend.file=perl pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=usr/bin/perl_app pkg.debug.depend.type=script type=require
depend fmri=__TBD pkg.debug.depend.file=perl pkg.debug.depend.path=usr/perl5/bin pkg.debug.depend.reason=usr/bin/perl_app pkg.debug.depend.type=script type=require
"""

                manual_dep = """
depend fmri=pkg:/perl-512@5.12.5-1 fmri=pkg:/perl-516@5.16.3-1 fmri=pkg:/perl-520@5.20.1-1 type=require-any
"""
                perl512_manf = """
set name=pkg.fmri value=pkg:/perl-512@5.12.5-1
set name=variant.foo value=i386
file tmp/foo group=bin mode=0755 owner=root path=usr/perl5/5.12/bin/perl
link path=usr/bin/perl target=../perl5/5.12/bin/perl
link path=usr/perl5/bin target=5.12/bin
"""
                # perl-516 doesn't deliver the link points to usr/perl5/bin,
                # which trigger this bug
                perl516_manf = """
set name=pkg.fmri value=pkg:/perl-516@5.16.3-1
set name=variant.foo value=i386
file tmp/foo group=bin mode=0755 owner=root path=usr/perl5/5.16/bin/perl
link path=usr/bin/perl target=../perl5/5.16/bin/perl
"""
                perl520_manf = """
set name=pkg.fmri value=pkg:/perl-520@5.20.1-1
set name=variant.foo value=i386
file tmp/foo group=bin mode=0755 owner=root path=usr/perl5/5.20/bin/perl
link path=usr/bin/perl target=../perl5/5.20/bin/perl
link path=usr/perl5/bin target=5.20/bin
"""
                dep_path = self.make_manifest(manf)
                perl512_path = self.make_manifest(perl512_manf)
                perl516_path = self.make_manifest(perl516_manf)
                perl520_path = self.make_manifest(perl520_manf)
                p1_name = "pkg:/perl-512@5.12.5-1"
                p2_name = "pkg:/perl-516@5.16.3-1"
                p3_name = "pkg:/perl-520@5.20.1-1"

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([dep_path, perl512_path,
                    perl516_path, perl520_path], self.api_obj, [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join(["{0}".format(e)
                            for e in errs])))
                # Verify that a warning is emitted.
                self.assertEqual(len(warnings), 1)
                self.assertTrue(isinstance(warnings[0],
                    dependencies.DropPackageWarning))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 4)
                # Ensure that only one require-any dependency is in the result.
                self.assertEqual(len(pkg_deps[dep_path]), 1)
                # Check that the subset is selected; the superset is omitted.
                fmris = []
                for f in pkg_deps[dep_path][0].attrs["fmri"]:
                        fmris.append(f)
                assert p1_name in fmris and p3_name in fmris

                # Verify that pkgdep resolve doesn't exit with error code 1.
                self.pkgdepend_resolve("{0} {1} {2} {3}".format(
                    dep_path, perl512_path, perl516_path, perl520_path))

                # Test that if a developer add a require-any dependency of
                # their own, we won't omit it.
                manual_path = self.make_manifest(manf + manual_dep)
                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([manual_path, perl512_path,
                    perl516_path, perl520_path], self.api_obj, [])
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 4)
                # Ensure the custom require-any dependency is in the result.
                self.assertEqual(len(pkg_deps[manual_path]), 2)
                fmris = []
                for f in pkg_deps[manual_path][0].attrs["fmri"]:
                        fmris.append(f)
                assert p1_name in fmris and p2_name in fmris and p3_name in fmris

                # Test that when one require-any dependency has the fmris that
                # is a subset of the other require-any dependency's fmris,
                # but if they are under different variant combinations, then the
                # first dependency is not treated as a subset, therefore the
                # superset could not be omitted.

                manf = """
set name=pkg.fmri value=foo@1.0,5.11-1
set name=variant.foo value=a value=b
file NOHASH group=bin mode=0755 owner=root path=usr/bin/perl_app
depend fmri=__TBD pkg.debug.depend.file=perl pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=usr/bin/perl_app pkg.debug.depend.type=script type=require variant.foo=a
depend fmri=__TBD pkg.debug.depend.file=perl pkg.debug.depend.path=usr/perl5/bin pkg.debug.depend.reason=usr/bin/perl_app pkg.debug.depend.type=script type=require variant.foo=b
"""
                perl512_manf = """
set name=pkg.fmri value=pkg:/perl-512@5.12.5-1
set name=variant.foo value=a value=b
file tmp/foo group=bin mode=0755 owner=root path=usr/perl5/5.12/bin/perl variant.foo=a variant.foo=b
link path=usr/bin/perl target=../perl5/5.12/bin/perl
link path=usr/perl5/bin target=5.12/bin
"""
                perl516_manf = """
set name=pkg.fmri value=pkg:/perl-516@5.16.3-1
set name=variant.foo value=a value=b
file tmp/foo group=bin mode=0755 owner=root path=usr/perl5/5.16/bin/perl variant.foo=a variant.foo=b
link path=usr/bin/perl target=../perl5/5.16/bin/perl
"""
                perl520_manf = """
set name=pkg.fmri value=pkg:/perl-520@5.20.1-1
set name=variant.foo value=a value=b
file tmp/foo group=bin mode=0755 owner=root path=usr/perl5/5.20/bin/perl variant.foo=a variant.foo=b
link path=usr/bin/perl target=../perl5/5.20/bin/perl
link path=usr/perl5/bin target=5.20/bin
"""
                dep_path = self.make_manifest(manf)
                perl512_path = self.make_manifest(perl512_manf)
                perl516_path = self.make_manifest(perl516_manf)
                perl520_path = self.make_manifest(perl520_manf)

                pkg_deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([dep_path, perl512_path,
                    perl516_path, perl520_path], self.api_obj, [])
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n{0}".format("\n".join([
                            "{0}".format(e,) for e in errs])))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(pkg_deps), 4)
                # Ensure that two require-any dependencies are in the result.
                self.assertEqual(len(pkg_deps[dep_path]), 2)
                for d in pkg_deps[dep_path]:
                        if d.attrs["variant.foo"] == "a":
                                self.assertTrue(p1_name in d.attrs["fmri"])
                                self.assertTrue(p2_name in d.attrs["fmri"])
                                self.assertTrue(p3_name in d.attrs["fmri"])
                        elif d.attrs["variant.foo"] == "b":
                                self.assertTrue(p1_name in d.attrs["fmri"])
                                self.assertTrue(p3_name in d.attrs["fmri"])

                # Verify that a warning is not emitted.
                self.pkgdepend_resolve("{0} {1} {2} {3}".format(
                    dep_path, perl512_path, perl516_path, perl520_path))
                self.assertTrue("WARNING: dropping dependency" not in self.output)

        def test_variant_empty_intersection(self):
                """Test that when two conditional depend actions have empty
                intersection, it should not report NeedConditionalRequireAny
                error because they actually refer to different packages under
                different variants."""

                manf_a = """
set name=pkg.fmri value=a@1.0
set name=variant.arch value=foo value=bar
depend fmri=pkg:/b@1.0 pkg.debug.depend.path-id=var/log/authlog predicate=pkg:/d@1.0 type=conditional variant.arch=foo
depend fmri=pkg:/c@1.0 pkg.debug.depend.path-id=var/log/authlog predicate=pkg:/d@1.0 type=conditional variant.arch=bar
"""
                res = """\
depend fmri=pkg:/b@1.0 predicate=pkg:/d@1.0 type=conditional variant.arch=foo
depend fmri=pkg:/c@1.0 predicate=pkg:/d@1.0 type=conditional variant.arch=bar
"""
                manf_a_p = self.make_manifest(manf_a)

                self.pkgdepend_resolve("{0}".format(manf_a_p))
                with open(manf_a_p + ".res", "r") as fh:
                        s = fh.read()
                self.assertEqual(res, s)


if __name__ == "__main__":
        unittest.main()
