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

# Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import ConfigParser
import os.path
import shutil
import unittest
import tempfile

import pkg.lint.engine as engine
import pkg.lint.log as log
import pkg.fmri as fmri
import pkg.manifest

import logging
log_fmt_string = "%(asctime)s - %(levelname)s - %(message)s"

logger = logging.getLogger("pkglint")
if not logger.handlers:
        logger.setLevel(logging.WARNING)
        ch = logging.StreamHandler()
        formatter = logging.Formatter(log_fmt_string)
        ch.setFormatter(formatter)
        ch.setLevel(logging.WARNING)
        logger.addHandler(ch)

pkglintrcfile = "%s/usr/share/lib/pkg/pkglintrc" % pkg5unittest.g_proto_area
broken_manifests = {}
expected_failures = {}

# WARNING pkglint.action002.2       unusual mode 2755 in usr/sbin/prtdiag  delivered by
#                                   pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
expected_failures["combo_variants.mf"] = ["pkglint.action002.2"]
broken_manifests["combo_variants.mf"] = \
"""
#
#
# We deliver prtdiag as a link on one platform, as a file on another
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
hardlink path=usr/sbin/prtdiag target=../../usr/lib/platexec variant.arch=sparc
file 1d5eac1aab628317f9c088d21e4afda9c754bb76 chash=43dbb3e0bc142f399b61d171f926e8f91adcffe2 elfarch=i386 elfbits=32 elfhash=64c67b16be970380cd5840dd9753828e0c5ada8c group=sys mode=2755 owner=root path=usr/sbin/prtdiag pkg.csize=5490 pkg.size=13572 variant.arch=i386
"""

# The errors for this check are pretty unpleasant
# ERROR pkglint.dupaction008        path usr/sbin/prtdiag is delivered by multiple action types
#                                   across pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
# ERROR pkglint.dupaction007        path usr/sbin/prtdiag is reference-counted but has different
#                                   attributes across 2 duplicates: group: sys -> system/kernel
#                                   elfarch: i386 -> system/kernel pkg.csize: 5490 -> system/kernel
#                                   chash: 43dbb3e0bc142f399b61d171f926e8f91adcffe2 -> system/kernel
#                                   mode: 2755 -> system/kernel pkg.size: 13572 -> system/kernel
#                                   owner: root -> system/kernel
#                                   elfhash: 64c67b16be970380cd5840dd9753828e0c5ada8c -> system/kernel
#                                   elfbits: 32 -> system/kernel
# WARNING pkglint.action002.2       unusual mode 2755 in usr/sbin/prtdiag  delivered by
#                                   pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
# ERROR pkglint.dupaction001.2      path usr/sbin/prtdiag is a duplicate delivered by
#                                   pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
#                                   declaring overlapping variants variant.arch
expected_failures["combo_variants_broken.mf"] = ["pkglint.dupaction008",
    "pkglint.dupaction007", "pkglint.action002.2", "pkglint.dupaction001.2"]
broken_manifests["combo_variants_broken.mf"] = \
"""
#
#
# We deliver prtdiag as a link on one platform, as a file on another
# but have forgotten to set the variant properly on the file action
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
hardlink path=usr/sbin/prtdiag target=../../usr/lib/platexec variant.arch=sparc
file 1d5eac1aab628317f9c088d21e4afda9c754bb76 chash=43dbb3e0bc142f399b61d171f926e8f91adcffe2 elfarch=i386 elfbits=32 elfhash=64c67b16be970380cd5840dd9753828e0c5ada8c group=sys mode=2755 owner=root path=usr/sbin/prtdiag pkg.csize=5490 pkg.size=13572 variant.arch=sparc
"""

expected_failures["dup-clashing-vars.mf"] = ["pkglint.dupaction001.2"]
broken_manifests["dup-clashing-vars.mf"] = \
"""
#
# we try to deliver usr/sbin/fsadmin twice with the same variant value
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.other value=carrots
set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
dir group=bin mode=0755 owner=root path=usr/lib/X11
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=953 pkg.size=1572 variant.other=carrots
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=1234 pkg.size=1234 variant.other=carrots
file nohash group=sys mode=0444 owner=root path=var/svc/manifest/application/x11/xfs.xml pkg.csize=1649 pkg.size=3534 restart_fmri=svc:/system/manifest-import:default
file nohash elfarch=i386 elfbits=32 elfhash=2d5abc9b99e65c52c1afde443e9c5da7a6fcdb1e group=bin mode=0755 owner=root path=usr/bin/xfs pkg.csize=68397 pkg.size=177700 variant.arch=i386
"""

expected_failures["dup-depend-vars.mf"] = ["pkglint.manifest005.2",
    "pkglint.action005.1", "pkglint.action005.1",
    "pkglint.action005.1"]
broken_manifests["dup-depend-vars.mf"] = \
"""
#
# we declare dependencies on the same package name twice, with variants
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWzsh@4.3.9,5.11-0.133:20100216T103302Z
set name=org.opensolaris.consolidation value=sfw
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=sparc value=i386
set name=variant.foo value=bar value=baz
depend fmri=shell/zsh@4.3.9-0.133 type=require variant.foo=bar
depend fmri=consolidation/sfw/sfw-incorporation type=require
depend fmri=shell/zsh@4.3.9-0.133 type=require variant.foo=bar
depend fmri=shell/zsh/redherring@4.3.9-0.133 type=require variant.foo=bar
"""

expected_failures["dup-depend-incorp.mf"] = ["pkglint.action005.1"]
broken_manifests["dup-depend-incorp.mf"] = \
"""
#
# There are 2 dependencies on sfw-incorporation, but only one is a require
# incorporation, so this should not generate errors, other than us not being
# able to find the dependency warning.
#
set name=pkg.fmri value=pkg://opensolaris.org/entire@0.5.11,5.11-0.145:20100730T013044Z
set name=pkg.depend.install-hold value=core-os
set name=pkg.description value="This package constrains system package versions to the same build.  WARNING: Proper system update and correct package selection depend on the presence of this incorporation.  Removing this package will result in an unsupported system."
set name=description value="incorporation to lock all system packages to same build"
set name=pkg.summary value="incorporation to lock all system packages to same build"
set name=variant.arch value=sparc value=i386
set name=org.opensolaris.consolidation value=None
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
depend fmri=consolidation/sfw/sfw-incorporation type=require
depend fmri=consolidation/sfw/sfw-incorporation@0.5.11-0.145 type=incorporate
"""

expected_failures["dup-depend-versions.mf"] = ["pkglint.action005.1",
    "pkglint.action005.1", "pkglint.action005.1"]
broken_manifests["dup-depend-versions.mf"] = \
"""
#
# as we're declaring complimentary variants, we shouldn't report errors,
# other than the 3 lint warnings for the missing dependencies
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWzsh@4.3.9,5.11-0.133:20100216T103302Z
set name=org.opensolaris.consolidation value=sfw
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=sparc value=i386
set name=variant.other value=other value=thing
set name=variant.foo value=bar value=baz
depend fmri=shell/zsh@4.3.9-0.133 type=require variant.foo=bar
depend fmri=consolidation/sfw/sfw-incorporation type=require
depend fmri=shell/zsh@4.3.9-0.134 type=require variant.foo=baz
"""

expected_failures["dup-no-vars.mf"] = ["pkglint.dupaction001.1"]
broken_manifests["dup-no-vars.mf"] = \
"""
#
# We try to deliver usr/sbin/fsadmin twice without specifying any variants
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
dir group=bin mode=0755 owner=root path=usr/lib/X11
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=953 pkg.size=1572
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=1234 pkg.size=1234
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=1234 pkg.size=1234
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=1234 pkg.size=1234
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=1234 pkg.size=1234
file nohash group=sys mode=0444 owner=root path=var/svc/manifest/application/x11/xfs.xml pkg.csize=1649 pkg.size=3534 restart_fmri=svc:/system/manifest-import:default
file nohash elfarch=i386 elfbits=32 elfhash=2d5abc9b99e65c52c1afde443e9c5da7a6fcdb1e group=bin mode=0755 owner=root path=usr/bin/xfs pkg.csize=68397 pkg.size=177700 variant.arch=i386
"""


expected_failures["dup-refcount-diff-attrs.mf"] = ["pkglint.dupaction007"]
broken_manifests["dup-refcount-diff-attrs.mf"] = \
"""
#
# we deliver some duplicate ref-counted actions (dir, link, hardlink) with differing
# attributes
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.other value=carrots
set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
dir group=bin mode=0755 owner=root path=usr/lib/X11
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs
dir group=sys mode=0755 owner=root path=/usr/lib/X11
"""

# 3 errors get reported for this manifest:
# usr/sbin/fsadmin is delivered by multiple action types across ['pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z']
# usr/sbin/fsadmin is ref-counted but has different attributes across duplicates in [<pkg.fmri.PkgFmri 'pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z' at 0x8733e2c>]
# usr/sbin/fsadmin delivered by [<pkg.fmri.PkgFmri 'pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z' at 0x8733e2c>] is a duplicate, declaring overlapping variants ['variant.other']
expected_failures["dup-types-clashing-vars.mf"] = ["pkglint.dupaction008",
    "pkglint.dupaction007", "pkglint.dupaction001.2"]
broken_manifests["dup-types-clashing-vars.mf"] = \
"""
#
# we try to deliver usr/sbin/fsadmin with different action types, declaring a variant on one.
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=i386 value=sparc
set name=variant.other value=carrots
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
dir group=bin mode=0755 owner=root path=usr/lib/X11
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs
dir group=bin mode=0755 owner=root path=usr/sbin/fsadmin variant.other=carrots
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=1234 pkg.size=1234 variant.other=carrots
file nohash group=sys mode=0444 owner=root path=var/svc/manifest/application/x11/xfs.xml pkg.csize=1649 pkg.size=3534 restart_fmri=svc:/system/manifest-import:default
file nohash elfarch=i386 elfbits=32 elfhash=2d5abc9b99e65c52c1afde443e9c5da7a6fcdb1e group=bin mode=0755 owner=root path=usr/bin/xfs pkg.csize=68397 pkg.size=177700 variant.arch=i386
"""

# 2 errors here
# usr/lib/X11/fs is delivered by multiple action types across ['pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z']
# path usr/lib/X11/fs is ref-counted but has different attributes across duplicates in [<pkg.fmri.PkgFmri 'pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z' at 0x87369ec>]
expected_failures["dup-types.mf"] = ["pkglint.dupaction008",
    "pkglint.dupaction007"]
broken_manifests["dup-types.mf"] = \
"""
#
# we deliver usr/lib/X11/fs as several action types
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
dir group=bin mode=0755 owner=root path=usr/lib/X11
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs
link group=bin mode=0755 alt=foo owner=foor path=usr/lib/X11/fs target=bar
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=1234 pkg.size=1234
file nohash group=sys mode=0444 owner=root path=var/svc/manifest/application/x11/xfs.xml pkg.csize=1649 pkg.size=3534 restart_fmri=svc:/system/manifest-import:default
file nohash elfarch=i386 elfbits=32 elfhash=2d5abc9b99e65c52c1afde443e9c5da7a6fcdb1e group=bin mode=0755 owner=root path=usr/bin/xfs pkg.csize=68397 pkg.size=177700 variant.arch=i386
"""


expected_failures["duplicate_sets.mf"] = ["pkglint.manifest006"]
broken_manifests["duplicate_sets.mf"] = \
"""
#
# We try to deliver the same set action twice
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
set name=test value=i386
set name=test value=i386
"""

expected_failures["duplicate_sets_allowed_vars.mf"] = []
broken_manifests["duplicate_sets_allowed_vars.mf"] = \
"""
#
# We try to deliver the same set action twice, with different variants
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
set name=test value=i386 variant.arch=sparc
set name=test value=i386 variant.arch=i386
"""

expected_failures["duplicate_sets_variants.mf"] = ["pkglint.manifest006"]
broken_manifests["duplicate_sets_variants.mf"] = \
"""
#
# We try to deliver the same set action twice, with variants
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
set name=test value=i386 variant.arch=sparc
set name=test value=i386 variant.arch=sparc
"""

expected_failures["info_class_valid.mf"] = []
broken_manifests["info_class_valid.mf"] = \
"""
#
# A perfectly valid manifest with a correct info.classification key
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.149:20100917T003411Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=description value="Pkglint test package"
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=i386 value=sparc
"""

expected_failures["info_class_missing.mf"] = ["opensolaris.manifest001.1"]
broken_manifests["info_class_missing.mf"] = \
"""
#
# we deliver package with no info.classification key
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.149:20100917T003411Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=i386 value=sparc
"""

expected_failures["info_class_many_values.mf"] = ["opensolaris.manifest003.6"]
broken_manifests["info_class_many_values.mf"] = \
"""
#
# we deliver a directory with multiple info.classification keys, one of which
# is wrong
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.149:20100917T003411Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Noodles value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=i386 value=sparc
"""

expected_failures["info_class_wrong_prefix.mf"] = ["opensolaris.manifest003.2"]
broken_manifests["info_class_wrong_prefix.mf"] = \
"""
#
# we deliver a directory with an incorrect info.classification key
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.149:20100917T003411Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2010:System/Core
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=i386 value=sparc
"""

expected_failures["info_class_no_category.mf"] = ["opensolaris.manifest003.3"]
broken_manifests["info_class_no_category.mf"] = \
"""
#
# we deliver a directory with an incorrect info.classification key,
# with no category value
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.149:20100917T003411Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=i386 value=sparc
"""

expected_failures["info_class_wrong_category.mf"] = ["opensolaris.manifest003.4"]
broken_manifests["info_class_wrong_category.mf"] = \
"""
#
# we deliver a directory with incorrect info.classification section/category
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.149:20100917T003411Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:Rubbish/Packaging
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=i386 value=sparc
"""

expected_failures["invalid_usernames.mf"] = ["opensolaris.action001.2",
    "opensolaris.action001.3", "opensolaris.action001.2",
    "opensolaris.action001.3", "opensolaris.action001.1",
    "opensolaris.action001.3"]
broken_manifests["invalid_usernames.mf"] = \
"""
#
# We try to deliver a series of invalid usernames, some result in multiple
# lint messages
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
user gcos-field="pkg(5) server UID" group=pkg5srv uid=97 username=""
user gcos-field="pkg(5) server UID" group=pkg5srv uid=98 username=1pkg5srv
user gcos-field="pkg(5) server UID" group=pkg5srv uid=99 username=pkg5srvZZ
user gcos-field="pkg(5) server UID" group=pkg5srv uid=100 username=pkg5s:v
user gcos-field="pkg(5) server UID" group=pkg5srv uid=101 username=pkg5-_.
"""

expected_failures["license-has-path.mf"] = ["pkglint.action005"]
broken_manifests["license-has-path.mf"] = \
"""
#
# We deliver a license action that also specifies a path
#
set name=variant.arch value=i386 value=sparc
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=org.opensolaris.consolidation value=osnet
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
license license="Foo" path=usr/share/lib/legalese.txt
"""

# We actually emit 4 messages here in testing, 2 for the legitmate errors,
# 2 for the "linted"-handling code, saying that we're not linting these actions
#
expected_failures["linted-action.mf"] = ["pkglint001.2", "pkglint001.2",
    "pkglint.action002.2", "pkglint.dupaction003.2"]
broken_manifests["linted-action.mf"] = \
"""
#
# we deliver some duplicate ref-counted actions (dir, link, hardlink) with differing
# attributes, but since they're marked as linted, we should get no output, we should
# still get the duplicate user though, as well as the unusual mode check for the
# version of the path that's 0751
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/TIMFtest@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.other value=carrots
set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
dir group=bin mode=0755 owner=root path=usr/lib/X11 pkg.linted=True
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs pkg.linted=True
dir group=staff mode=0751 owner=root path=/usr/lib/X11
user ftpuser=false gcos-field="Network Configuration Admin" group=netadm uid=17 username=netcfg
user ftpuser=false gcos-field="Network Configuration Admin" group=netadm uid=19 username=netcfg
"""

# We'll actually report one lint message here, that we're not
# doing any linting for this manifest because of pkg.linted
# - the default log handler used by the pkglint CLI only marks
# a failure if it's > level.INFO, but for testing, we record all
# messages
expected_failures["linted-manifest.mf"] = ["pkglint001.1"]
broken_manifests["linted-manifest.mf"] = \
"""
#
# This manifest is marked as pkg.linted, and should not have manifest
# checks run on it.  In particular, we should not complain about the lack
# of variant.arch nor the unusual permission, 0751
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/TIMFtest@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.other value=carrots
# set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
set name=pkg.linted value=True
dir group=bin mode=0755 owner=root path=usr/lib/X11
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs
dir group=staff mode=0751 owner=root path=/usr/lib/X11
user ftpuser=false gcos-field="Network Configuration Admin" group=netadm uid=17 username=netcfg
user ftpuser=false gcos-field="Network Configuration Admin" group=netadm uid=19 username=netcfg
"""

expected_failures["no_desc-legacy.mf"] = ["pkglint.action003.1"]
broken_manifests["no_desc-legacy.mf"] = \
"""
#
# We deliver a legacy actions without a required attribute, "desc". Since we
# can't find the package pointed to by the legacy 'pkg' attribute, we should
# not complain about those.
# This package also has no variant.arch attribute, which should be fine since
# we're not delivering any content with an elfarch attribute, and we're
# omitting the variant.arch from the legacy actions.
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
# set name=variant.arch value=i386 value=sparc
set name=org.opensolaris.consolidation value=osnet
legacy arch=i386 category=system hotline="Please contact your local service provider" name="Core Solaris Kernel (Root)" pkg=SUNWckr vendor="Sun Microsystems, Inc." version=11.11,REV=2009.11.11
legacy arch=sparc category=system desc="core kernel software for a specific instruction-set architecture" hotline="Please contact your local service provider" name="Core Solaris Kernel (Root)" pkg=SUNWckr vendor="Sun Microsystems, Inc." version=11.11,REV=2009.11.11
"""

expected_failures["no_dup-allowed-vars.mf"] = []
broken_manifests["no_dup-allowed-vars.mf"] = \
"""
#
# we try to deliver usr/sbin/fsadmin twice with the same variant value
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=i386 value=sparc
set name=variant.other value="carrots" value="turnips"
dir group=bin mode=0755 owner=root path=usr/lib/X11
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=953 pkg.size=1572 variant.other=carrots
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=1234 pkg.size=1234 variant.other=turnips
file nohash group=sys mode=0444 owner=root path=var/svc/manifest/application/x11/xfs.xml pkg.csize=1649 pkg.size=3534 restart_fmri=svc:/system/manifest-import:default
file nohash elfarch=i386 elfbits=32 elfhash=2d5abc9b99e65c52c1afde443e9c5da7a6fcdb1e group=bin mode=0755 owner=root path=usr/bin/xfs pkg.csize=68397 pkg.size=177700 variant.arch=i386
"""

expected_failures["no_dup-types-different-vars.mf"] = []
broken_manifests["no_dup-types-different-vars.mf"] = \
"""
#
# we declare allowed variants for usr/lib/X11/fs, despite them
# delivering to the same path name.  Ref-counted actions, but
# different variants, this should not be reported as an error
# We also check that the 'target' difference in the link /usr/lib/foo
# doesn't result in lint errors.
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=i386 value=sparc
set name=variant.bar value=other value=foo
link path=usr/lib/foo target=usr/sparc-sun-solaris2.11/lib/foo variant.arch=sparc
link path=usr/lib/foo target=usr/i386-pc-solaris2.11/lib/foo variant.arch=i386
dir group=bin mode=0755 owner=root path=usr/lib/X11
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs variant.bar=other
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs variant.bar=foo
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=1234 pkg.size=1234
file nohash group=sys mode=0444 owner=root path=var/svc/manifest/application/x11/xfs.xml pkg.csize=1649 pkg.size=3534 restart_fmri=svc:/system/manifest-import:default
file nohash elfarch=i386 elfbits=32 elfhash=2d5abc9b99e65c52c1afde443e9c5da7a6fcdb1e group=bin mode=0755 owner=root path=usr/bin/xfs pkg.csize=68397 pkg.size=177700 variant.arch=i386
"""

# our obsolete depend lint check should complain about not being able to find
# manifests, but we shouldn't trigger the duplicate dependency error
expected_failures["nodup-depend-okvars.mf"] = ["pkglint.action005.1",
    "pkglint.action005.1", "pkglint.action005.1"]
broken_manifests["nodup-depend-okvars.mf"] = \
"""
#
# as we're declaring complimentary variants, we shouldn't report errors
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWzsh@4.3.9,5.11-0.133:20100216T103302Z
set name=org.opensolaris.consolidation value=sfw
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=sparc value=i386
set name=variant.other value=other value=thing
set name=variant.foo value=bar value=baz
depend fmri=shell/zsh@4.3.9-0.133 type=require variant.foo=bar
depend fmri=consolidation/sfw/sfw-incorporation type=require
depend fmri=shell/zsh@4.3.9-0.134 type=require variant.foo=baz
"""

expected_failures["novariant_arch.mf"] = ["pkglint.manifest003.3",
    "pkglint.action005.1", "pkglint.action005.1"]
broken_manifests["novariant_arch.mf"] = \
"""
#
# we don't have a variant.arch attribute set, and are delivering a file with
# an elfarch attribute
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWzsh@4.3.9,5.11-0.133:20100216T103302Z
set name=org.opensolaris.consolidation value=sfw
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
set name=variant.other value=other value=thing
set name=variant.foo value=bar value=baz
depend fmri=shell/zsh@4.3.9-0.133 type=require variant.foo=bar
depend fmri=consolidation/sfw/sfw-incorporation type=require
file nohash elfarch=i386 elfbits=32 elfhash=2d5abc9b99e65c52c1afde443e9c5da7a6fcdb1e group=bin mode=0755 owner=root path=usr/bin/xfs pkg.csize=68397 pkg.size=177700
"""

expected_failures["obsolete-has-description.mf"] = ["pkglint.manifest001.1"]
broken_manifests["obsolete-has-description.mf"] = \
"""
#
# We deliver an obsolete package that has a pkg.description
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWaspell@0.5.11,5.11-0.130:20091218T222625Z
set name=pkg.obsolete value=true variant.arch=i386
set name=pkg.description value="This is a package description"
set name=variant.opensolaris.zone value=global value=nonglobal variant.arch=i386
set name=variant.arch value=i386
"""

expected_failures["obsolete-more-actions.mf"] = ["pkglint.manifest001.2"]
broken_manifests["obsolete-more-actions.mf"] = \
"""
#
# We deliver an obsolete package that has actions other than 'set'.
# (bogus signature on this manifest, just for testing)
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWaspell@0.5.11,5.11-0.130:20091218T222625Z
set name=pkg.obsolete value=true variant.arch=i386
set name=variant.opensolaris.zone value=global value=nonglobal variant.arch=i386
set name=variant.arch value=i386
dir mode=0555 owner=root group=sys path=/usr/bin
signature algorithm=sha256 value=75b662e14a4ea8f0fa0507d40133b0347a36bc1f63112487f4738073edf4455d version=0
"""

expected_failures["obsolete.mf"] = []
broken_manifests["obsolete.mf"] = \
"""
#
# This is a perfectly valid example of an obsolete package
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWaspell@0.5.11,5.11-0.130:20091218T222625Z
set name=pkg.obsolete value=true variant.arch=i386
set name=variant.opensolaris.zone value=global value=nonglobal variant.arch=i386
set name=variant.arch value=i386
"""

expected_failures["renamed-more-actions.mf"] = ["pkglint.manifest002",
    "pkglint.action005.1", "pkglint.action005.1"]
broken_manifests["renamed-more-actions.mf"] = \
"""
#
# We've reported a package as having been renamed, yet try to deliver
# actions other than 'set' and 'depend'
# (bogus signature on this manifest, just for testing)
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWzsh@4.3.9,5.11-0.133:20100216T103302Z
set name=org.opensolaris.consolidation value=sfw
set name=pkg.renamed value=true
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=sparc value=i386
depend fmri=shell/zsh@4.3.9-0.133 type=require
depend fmri=consolidation/sfw/sfw-incorporation type=require
dir mode=0555 owner=root group=sys path=/usr/bin
signature algorithm=sha256 value=75b662e14a4ea8f0fa0507d40133b0347a36bc1f63112487f4738073edf4455d version=0
"""

expected_failures["renamed.mf"] = ["pkglint.action005.1",
    "pkglint.action005.1"]
broken_manifests["renamed.mf"] = \
"""
#
# This is a perfectly valid example of a renamed package
# (bogus signature on this manifest, just for testing)
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWzsh@4.3.9,5.11-0.133:20100216T103302Z
set name=org.opensolaris.consolidation value=sfw
set name=pkg.renamed value=true
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=sparc value=i386
depend fmri=shell/zsh@4.3.9-0.133 type=require
depend fmri=consolidation/sfw/sfw-incorporation type=require
signature algorithm=sha256 value=75b662e14a4ea8f0fa0507d40133b0347a36bc1f63112487f4738073edf4455d version=0
"""

expected_failures["undescribed-variant.mf"] = ["pkglint.manifest003.1"]
broken_manifests["undescribed-variant.mf"] = \
"""
#
# we try to set a variant we've never described in the manifest
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
dir group=bin mode=0755 owner=root path=usr/lib/X11
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs
file nohash group=sys mode=0444 owner=root path=var/svc/manifest/application/x11/xfs.xml pkg.csize=1649 pkg.size=3534 restart_fmri=svc:/system/manifest-import:default variant.noodles=singapore
file nohash elfarch=i386 elfbits=32 elfhash=2d5abc9b99e65c52c1afde443e9c5da7a6fcdb1e group=bin mode=0755 owner=root path=usr/bin/xfs pkg.csize=68397 pkg.size=177700 variant.arch=i386
"""

expected_failures["unknown-variant.mf"] = ["pkglint.manifest003.2"]
broken_manifests["unknown-variant.mf"] = \
"""
#
# we try to deliver an action with a variant value we haven't described
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
dir group=bin mode=0755 owner=root path=usr/lib/X11
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs
file nohash group=sys mode=0444 owner=root path=var/svc/manifest/application/x11/xfs.xml pkg.csize=1649 pkg.size=3534 restart_fmri=svc:/system/manifest-import:default variant.opensolaris.zone=foo
file nohash elfarch=i386 elfbits=32 elfhash=2d5abc9b99e65c52c1afde443e9c5da7a6fcdb1e group=bin mode=0755 owner=root path=usr/bin/xfs pkg.csize=68397 pkg.size=177700 variant.arch=i386
"""

expected_failures["unknown.mf"] = ["pkglint.action004"]
broken_manifests["unknown.mf"] = \
"""
#
# We try to deliver an 'unknown' action
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
set name=org.opensolaris.consolidation value=osnet
unknown name="no idea"
"""

expected_failures["unusual_mode_noexecdir.mf"] = ["pkglint.action002.1",
    "pkglint.action002.2"]
broken_manifests["unusual_mode_noexecdir.mf"] = \
"""
#
# we deliver a directory with an unexecutable mode 0422
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=i386 value=sparc
dir group=bin mode=0424 owner=root path=usr/lib/X11
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs
file nohash group=bin mode=0755 owner=root path=usr/sbin/fsadmin pkg.csize=1234 pkg.size=1234
file nohash group=sys mode=0444 owner=root path=var/svc/manifest/application/x11/xfs.xml pkg.csize=1649 pkg.size=3534 restart_fmri=svc:/system/manifest-import:default
file nohash elfarch=i386 elfbits=32 elfhash=2d5abc9b99e65c52c1afde443e9c5da7a6fcdb1e group=bin mode=0755 owner=root path=usr/bin/xfs pkg.csize=68397 pkg.size=177700 variant.arch=i386
"""

class TestLogFormatter(log.LogFormatter):
        """Records log messages to a buffer"""
        def __init__(self):
                self.messages = []
                self.ids = []
                super(TestLogFormatter, self).__init__()

        def format(self, msg):
                if isinstance(msg, log.LintMessage):
                        if msg.level >= self.level:
                                self.messages.append("%s\t%s" %
                                    (msg.msgid, str(msg)))
                                self.ids.append(msg.msgid)

        def close(self):
                self.messages = []
                self.ids = []

class TestLintEngine(pkg5unittest.Pkg5TestCase):

        def test_lint_checks(self):
                """Ensure that lint checks are functioning."""

                paths = self.make_misc_files(broken_manifests)
                paths.sort()

                for manifest in paths:
                        basename = os.path.basename(manifest)
                        lint_logger = TestLogFormatter()
                        lint_engine = engine.LintEngine(lint_logger,
                            config_file=os.path.join(self.test_root,
                            "pkglintrc"), use_tracker=False)

                        manifests = read_manifests([manifest], lint_logger)
                        lint_engine.setup(lint_manifests=manifests)

                        lint_engine.execute()
                        lint_engine.teardown()

                        expected = len(expected_failures[basename])
                        actual = len(lint_logger.messages)
                        if (actual != expected):
                                self.debug("\n".join(lint_logger.messages))
                                self.assert_(actual == expected,
                                    "Expected %s failures for %s, got %s: %s" %
                                    (expected, basename, actual,
                                    "\n".join(lint_logger.messages)))
                        else:
                                reported = lint_logger.ids
                                known = expected_failures[basename]
                                reported.sort()
                                known.sort()
                                for i in range(0, len(reported)):
                                        self.assert_(reported[i] == known[i],
                                            "Differences in reported vs. "
                                            "expected lint ids for %s: "
                                            "%s vs. %s" %
                                            (basename, str(reported),
                                            str(known)))
                        lint_logger.close()

        def test_info_classification_data(self):
                """info.classification check can deal with bad data files."""

                paths = self.make_misc_files(
                    {"info_class_valid.mf":
                    broken_manifests["info_class_valid.mf"]})

                empty_file = "%s/empty_file" % self.test_root
                open(empty_file, "w").close()

                bad_file = "%s/bad_file" % self.test_root
                f = open(bad_file, "w")
                f.write("nothing here")
                f.close()

                mf_path = paths.pop()

                lint_logger = TestLogFormatter()
                manifests = read_manifests([mf_path], lint_logger)

                for classification_path in ["/dev/null", "/", empty_file,
                    bad_file]:

                        rcfile = self.configure_rcfile(
                            os.path.join(self.test_root, "pkglintrc"),
                            {"info_classification_path": classification_path},
                            self.test_root, section="pkglint", suffix=".tmp")

                        lint_engine = engine.LintEngine(lint_logger,
                            config_file=rcfile,
                            use_tracker=False)

                        lint_engine.setup(lint_manifests=manifests)
                        lint_engine.execute()
                        self.assert_(
                            lint_logger.ids == ["opensolaris.manifest003.1"],
                            "Unexpected errors encountered: %s" %
                            lint_logger.messages)
                        lint_logger.close()

class TestLintEngineDepot(pkg5unittest.ManyDepotTestCase):
        """Tests that exercise reference vs. lint repository checks
        and test linting of multiple packages at once."""

        ref_mf = {}

        ref_mf["ref-ancient-sample1.mf"] = """
#
# A sample package which delivers several actions, to an earlier release than
# 0.140. This manifest has an intentional error, which we should detect when
# linting against build 139.
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.139
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/passwd path=etc/passwd group=sys mode=0644 owner=root preserve=true
file /etc/passwd path=etc/passwd group=sys mode=0644 owner=root preserve=true
dir group=sys mode=0755 owner=root path=etc
"""

        ref_mf["ref-old-sample1.mf"] = """
#
# A sample package which delivers several actions, to an earlier release than
# 0.141
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.140
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/passwd path=etc/passwd group=sys mode=0644 owner=root preserve=true
dir group=sys mode=0755 owner=root path=etc
"""
        ref_mf["ref-sample1.mf"] = """
#
# A sample package which delivers several actions, to 0.141
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/passwd path=etc/passwd group=sys mode=0644 owner=root preserve=true
dir group=sys mode=0755 owner=root path=etc
"""

        ref_mf["ref-sample2.mf"] = """
#
# A sample package which delivers several actions
#
set name=pkg.fmri value=pkg://opensolaris.org/system/additional@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/motd group=sys mode=0644 owner=root path=etc/motd
dir group=sys mode=0755 owner=root path=etc
dir group=sys mode=0755 owner=root path=etc
"""

        ref_mf["ref-sample3.mf"] = """
#
# A sample package which delivers several actions
#
set name=pkg.fmri value=pkg://opensolaris.org/system/more@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/group group=sys mode=0644 owner=root path=etc/group
dir group=sys mode=0755 owner=root path=etc
"""

        ref_mf["ref-sample4-not-obsolete"] = """
#
# This is not an obsolete package - used to check versioning
#
set name=pkg.fmri value=pkg://opensolaris.org/system/obsolete@0.5.11,5.11-0.140
set name=variant.opensolaris.zone value=global value=nonglobal variant.arch=i386
set name=variant.arch value=i386
"""

        ref_mf["ref-sample4-obsolete"] = """
#
# This is a perfectly valid example of an obsolete package
#
set name=pkg.fmri value=pkg://opensolaris.org/system/obsolete@0.5.11,5.11-0.141
set name=pkg.obsolete value=true variant.arch=i386
set name=variant.opensolaris.zone value=global value=nonglobal variant.arch=i386
set name=variant.arch value=i386
"""

        ref_mf["dummy-ancestor.mf"] = """
#
# This is a dummy package designed trip a lint of no-ancestor-legacy.mf
# we don't declare a dependency on the FMRI delivered by it.
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWckr@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
"""

        # A set of manifests to be linted. Note that these are all self
        # consistent, passing all lint checks on their own.
        # Errors are designed to show up when linted against the ref_*
        # manifests, as imported to our reference repository.
        lint_mf = {}
        expected_failures = {}

        expected_failures["deliver-old-sample1.mf"] = ["pkglint.dupaction001.1",
            "pkglint.manifest004"]
        lint_mf["deliver-old-sample1.mf"] = """
#
# We deliver something a package older version than our ref_repo has,
# 0.140 instead of 0.141, this should cause errors unless we're
# linting against the 0.140 build in the repository.
# (the errors being, a name clash for system/kernel and a path clash
# for etc/passwd - essentially pkglint sees the 0.140 package being a
# duplicate of the 0.141 package)
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.140
set name=pkg.description value="core kernel"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/passwd path=etc/passwd group=sys mode=0644 owner=root preserve=true
dir group=sys mode=0755 owner=root path=etc
"""

        expected_failures["deliver-new-sample1.mf"] = []
        lint_mf["deliver-new-sample1.mf"] = """
#
# We deliver a newer version than our reference repo has
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
set name=pkg.description value="core kernel"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/passwd path=etc/passwd group=sys mode=0644 owner=root preserve=true
dir group=sys mode=0755 owner=root path=etc
"""

        expected_failures["deliver-new-sample1-duplicate.mf"] = \
            ["pkglint.dupaction001.1"]
        lint_mf["deliver-new-sample1-duplicate.mf"] = """
#
# We deliver a newer version than our reference repo has, intentionally
# duplicating a file our reference repository has in sample3
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.142
set name=pkg.description value="core kernel"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/passwd path=etc/passwd group=sys mode=0644 owner=root preserve=true
file /etc/group path=etc/group group=sys mode=0644 owner=root preserve=true
dir group=sys mode=0755 owner=root path=etc
"""

        expected_failures["no-ancestor-legacy.mf"] = ["pkglint.action003.2"]
        lint_mf["no-ancestor-legacy.mf"] = \
"""
#
# We deliver a legacy action, but declare a package in the legacy action pkg=
# field from the ref repo which doesn't depend on us.  Only one failure,
# because the 2nd legacy action below points to a non-existent package.
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
set name=pkg.description value="core kernel"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
set name=org.opensolaris.consolidation value=osnet
legacy arch=i386 category=system desc="core kernel software for a specific instruction-set architecture" hotline="Please contact your local service provider" name="Core Solaris Kernel (Root)" pkg=SUNWckr variant.arch=i386 vendor="Sun Microsystems, Inc." version=11.11,REV=2009.11.11
legacy arch=sparc category=system desc="core kernel software for a specific instruction-set architecture" hotline="Please contact your local service provider" name="Core Solaris Kernel (Root)" pkg=SUNWthisdoesnotexist variant.arch=sparc vendor="Sun Microsystems, Inc." version=11.11,REV=2009.11.11
"""

        expected_failures["unversioned-dep-obsolete.mf"] = ["pkglint.action005"]
        lint_mf["unversioned-dep-obsolete.mf"] = """
#
# We declare a dependency without a version number, on an obsolete package
# this should result in a lint error
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
set name=pkg.description value="core kernel"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
depend fmri=pkg:/system/obsolete type=require
        """

        expected_failures["versioned-dep-obsolete.mf"] = ["pkglint.action005"]
        lint_mf["versioned-dep-obsolete.mf"] = """
#
# We declare a dependency on a version known to be obsolete
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
set name=pkg.description value="core kernel"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
depend fmri=pkg://opensolaris.org/system/obsolete@0.5.11,5.11-0.141 type=require
        """

        expected_failures["versioned-older-obsolete.mf"] = ["pkglint.action005"]
        lint_mf["versioned-older-obsolete.mf"] = """
#
# We have dependency on an older version of the packages which was recently
# made obsolete. Even though we declared the dependency on the non-obsolete
# version, because we published a later, obsoleted version of that package,
# we should get the lint warning.
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
set name=pkg.description value="core kernel"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
depend fmri=system/obsolete@0.5.11-0.140 type=require
        """

        def setUp(self):

                pkg5unittest.ManyDepotTestCase.setUp(self,
                    ["opensolaris.org", "opensolaris.org", "opensolaris.org"],
                    start_depots=True)

                self.ref_uri = self.dcs[1].get_depot_url()
                self.lint_uri = self.dcs[2].get_depot_url()
                self.empty_lint_uri = self.dcs[3].get_depot_url()
                self.cache_dir = tempfile.mkdtemp("pkglint-cache", "",
                    self.test_root)

                paths = self.make_misc_files(self.ref_mf)

                for item in paths:
                        self.pkgsend(depot_url=self.ref_uri,
                            command="publish --fmri-in-manifest %s" % item)
                self.pkgsend(depot_url=self.ref_uri,
                            command="refresh-index")

                paths = self.make_misc_files(self.lint_mf)
                for item in paths:
                        self.pkgsend(depot_url=self.lint_uri,
                            command="publish --fmri-in-manifest %s" % item)
                self.pkgsend(depot_url=self.lint_uri,
                            command="refresh-index")

        def test_lint_repo_basics(self):
                """Test basic handling of repo URIs with the lint engine,
                reference repo is error free, cache dir torn down appropriately.
                """
                if not os.path.exists(self.cache_dir):
                        os.makedirs(self.cache_dir)

                lint_logger = TestLogFormatter()
                lint_engine = engine.LintEngine(lint_logger, use_tracker=False,
                    config_file=os.path.join(self.test_root, "pkglintrc"))

                lint_engine.setup(cache=self.cache_dir,
                    lint_uris=[self.ref_uri])
                lint_engine.execute()

                self.assert_(len(lint_logger.messages) == 0,
                    "Unexpected lint errors messages reported against "
                    "reference repo: %s" %
                    "\n".join(lint_logger.messages))
                lint_logger.close()

                lint_engine.teardown()
                self.assert_(os.path.exists(self.cache_dir),
                    "Cache dir does not exist after teardown!")
                self.assert_(os.path.exists(
                    os.path.join(self.cache_dir, "lint_image")),
                    "lint image dir still existed after teardown!")

                # This shouldn't appear when we're not using a reference repo
                self.assertFalse(os.path.exists(
                    os.path.join(self.cache_dir, "ref_image")),
                    "ref image dir existed!")
                lint_engine.teardown(clear_cache=True)
                self.assertFalse(os.path.exists(self.cache_dir),
                    "Cache dir was not torn down as expected")

        def test_empty_lint_repo(self):
                """Ensure we can lint an empty repository"""

                paths = self.make_misc_files(self.lint_mf)
                if not os.path.exists(self.cache_dir):
                        os.makedirs(self.cache_dir)

                lint_logger = TestLogFormatter()
                lint_engine = engine.LintEngine(lint_logger, use_tracker=False,
                        config_file=os.path.join(self.test_root, "pkglintrc"))

                lint_engine.setup(cache=self.cache_dir,
                    lint_uris=[self.ref_uri])
                lint_engine.execute()

                lint_msgs = []
                # prune out the missing dependency warnings
                for msg in lint_logger.messages:
                        if "pkglint.action005.1" not in msg:
                                lint_msgs.append(msg)

                self.assertFalse(lint_msgs,
                    "Lint messages reported from a clean reference repository.")
                lint_engine.teardown(clear_cache=True)

                # this should be an empty test: we have no packages in the
                # lint repository, so we end up doing nothing
                lint_logger = TestLogFormatter()
                lint_engine.setup(cache=self.cache_dir,
                    lint_uris=[self.empty_lint_uri])
                lint_engine.execute()
                lint_engine.teardown(clear_cache=True)
                self.assertFalse(lint_logger.messages,
                    "Lint messages reported from a empty lint repository.")

        def test_versioning(self):
                """Package version handling during lint runs.
                In particular, it verifies that packages for linting are merged
                correctly into pkglint's view of what the ref repository would
                look like, were the lint package to be published to the
                reference repository."""

                paths = self.make_misc_files(self.lint_mf)
                paths.sort()

                for manifest in paths:
                        basename = os.path.basename(manifest)
                        lint_logger = TestLogFormatter()
                        lint_engine = engine.LintEngine(lint_logger,
                            use_tracker=False,
                            config_file=os.path.join(self.test_root,
                            "pkglintrc"))

                        manifests = read_manifests([manifest], lint_logger)
                        lint_engine.setup(cache=self.cache_dir,
                            ref_uris=[self.ref_uri],
                            lint_manifests=manifests)

                        lint_engine.execute()
                        lint_engine.teardown(clear_cache=True)

                        expected = len(self.expected_failures[basename])
                        actual = len(lint_logger.messages)
                        if (actual != expected):
                                self.debug("\n".join(lint_logger.messages))
                                self.assert_(actual == expected,
                                    "Expected %s failures for %s, got %s: %s" %
                                    (expected, basename, actual,
                                    "\n".join(lint_logger.messages)))
                        else:
                                reported = lint_logger.ids
                                known = self.expected_failures[basename]
                                reported.sort()
                                known.sort()
                                for i in range(0, len(reported)):
                                        self.assert_(reported[i] == known[i],
                                            "Differences in reported vs. expected"
                                            " lint ids for %s: %s vs. %s" %
                                            (basename, str(reported),
                                            str(known)))
                        lint_logger.close()

                # this manifest should report duplicates when
                # linted against a 0.141 repository, but none
                # when linted against a 0.140 repository. The duplicates
                # were tested when 'deliver-old-sample1.mf' was linted
                # above - this time, we lint against 0.140 and expect
                # no errors.
                lint_logger = TestLogFormatter()
                lint_engine = engine.LintEngine(lint_logger, use_tracker=False,
                    config_file=os.path.join(self.test_root, "pkglintrc"))

                path = os.path.join(self.test_root, "deliver-old-sample1.mf")
                manifests = read_manifests([path], lint_logger)

                lint_engine.setup(cache=self.cache_dir,
                    ref_uris=[self.ref_uri],
                    lint_manifests=manifests, release="140")
                lint_engine.execute()
                lint_engine.teardown(clear_cache=True)

                self.assertFalse(lint_logger.messages,
                    "Unexpected lint messages when linting against old "
                    "version of reference repo: %s" %
                    "\n".join(lint_logger.messages))

                # ensure we detect the error when linting against the reference
                # 0.139 repository
                lint_logger = TestLogFormatter()
                lint_engine = engine.LintEngine(lint_logger, use_tracker=False,
                    config_file=os.path.join(self.test_root, "pkglintrc"))
                lint_engine.setup(cache=self.cache_dir,
                    ref_uris=[self.ref_uri],
                    lint_uris=[self.ref_uri], release="139")
                lint_engine.execute()
                lint_engine.teardown(clear_cache=True)

                if not lint_logger.ids:
                        self.assert_(False,
                            "No lint messages produced when linting the "
                            "contents of an old repository")
                elif len(lint_logger.ids) != 1:
                        self.assert_(False,
                            "Expected exactly 1 lint message when linting the "
                            "contents of an old repository, got %s" %
                            len(lint_logger.ids))
                elif lint_logger.ids[0] != "pkglint.dupaction001.1":
                        self.assert_(False,
                            "Expected pkglint.dupaction001.1 message when "
                            "linting the contents of an old repository, got "
                            "%s" % lint_logger.ids[0])


        def test_lint_mf_baseline(self):
                """The lint manifests in this test class should be lint-clean
                themselves - they should only report errors when linting against
                our reference repository."""

                paths = self.make_misc_files(self.lint_mf)
                paths.sort()

                for manifest in paths:
                        basename = os.path.basename(manifest)
                        lint_logger = TestLogFormatter()
                        lint_engine = engine.LintEngine(lint_logger,
                            use_tracker=False,
                            config_file=os.path.join(self.test_root,
                            "pkglintrc"))

                        manifests = read_manifests([manifest], lint_logger)
                        lint_engine.setup(lint_manifests=manifests)

                        lint_engine.execute()
                        lint_engine.teardown()

                        # prune missing dependency warnings
                        lint_msgs = []
                        for msg in lint_logger.messages:
                                if "pkglint.action005.1" not in msg:
                                        lint_msgs.append(msg)

                        self.assertFalse(lint_msgs,
                            "Unexpected lint messages when linting individual "
                            "manifests that should contain no errors: %s %s" %
                            (basename, "\n".join(lint_msgs)))

def read_manifests(names, lint_logger):
        "Read a list of filenames, return a list of Manifest objects"
        manifests = []
        for filename in names:
                data = None
                # borrowed code from publish.py
                lines = []      # giant string of all input lines
                linecnts = []   # tuples of starting line no., ending line no
                linecounter = 0 # running total
                try:
                        data = file(filename).read()
                except IOError, e:
                        lint_logger.error("Unable to read manifest file %s" %
                            filename, msgid="lint.manifest001")
                        continue
                lines.append(data)
                linecnt = len(data.splitlines())
                linecnts.append((linecounter, linecounter + linecnt))
                linecounter += linecnt

                manifest = pkg.manifest.Manifest()
                try:
                        manifest.set_content("\n".join(lines))
                except pkg.actions.ActionError, e:
                        lineno = e.lineno
                        for i, tup in enumerate(linecnts):
                                if lineno > tup[0] and lineno <= tup[1]:
                                        lineno -= tup[0]
                                        break;
                        else:
                                lineno = "???"

                        lint_logger.error(
                            "Problem reading manifest %s line: %s: %s " %
                            (filename, lineno, e), "lint.manifest002")
                        continue

                if "pkg.fmri" in manifest:
                        manifest.fmri = fmri.PkgFmri(
                            manifest["pkg.fmri"])
                        manifests.append(manifest)
                else:
                        lint_logger.error(
                            "Manifest %s does not declare fmri." % filename,
                            "lint.manifest003")
        return manifests

if __name__ == "__main__":
        unittest.main()
