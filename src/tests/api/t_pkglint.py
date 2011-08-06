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

# Copyright (c) 2010, 2011, Oracle and/or its affiliates. All rights reserved.

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

from pkg.lint.engine import lint_fmri_successor
from pkg.lint.base import linted, DuplicateLintedAttrException

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

expected_failures["unusual_perms.mf"] = ["pkglint.action002.2",
    "pkglint.action002.1", "pkglint.action002.4", "pkglint.action002.4",
    # 5 errors corresponding to the broken group checks above
    "pkglint.action002.3", "pkglint.action009", "pkglint.action009",
    "pkglint.action009", "pkglint.action009"]
broken_manifests["unusual_perms.mf"] = \
"""
#
#
# We deliver prtdiag as a link on one platform, as a file on another, which is
# allowed, testing variant combinations, the unusual permissions are not.
# they being, broken mode 991, a mode where we have more access as the group and
# world than we have as the user, and an underspecified mode
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
hardlink path=usr/sbin/prtdiag target=../../usr/lib/platexec variant.arch=sparc
file 1d5eac1aab628317f9c088d21e4afda9c754bb76 chash=43dbb3e0bc142f399b61d171f926e8f91adcffe2 elfarch=i386 elfbits=32 elfhash=64c67b16be970380cd5840dd9753828e0c5ada8c group=sys mode=2755 owner=root path=usr/sbin/prtdiag pkg.csize=5490 pkg.size=13572 variant.arch=i386
# invalid modes
dir path=usr mode=991
dir path=usr/foo mode=457
dir path=usr/foo/other mode=222
file NOHASH path=usr/foo/file mode=0112 owner=root group=staff
file NOHASH path=usr/foo/bar mode=01 owner=root group=staff
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
# ERROR pkglint.dupaction001.2      path usr/sbin/prtdiag is a duplicate delivered by
#                                   pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
#                                   declaring overlapping variants variant.arch
expected_failures["combo_variants_broken.mf"] = ["pkglint.dupaction008",
    "pkglint.dupaction007", "pkglint.dupaction001.2"]
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

expected_failures["dup-clashing-vars.mf"] = ["pkglint.dupaction001.1"]
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
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
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

expected_failures["dup-depend-linted.mf"] = ["pkglint.action005.1",
    "pkglint.action008"]
broken_manifests["dup-depend-linted.mf"] = \
"""
#
# We deliver duplicate dependencies, one coming from a require-any dep
#
set name=variant.arch value=i386 value=sparc
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=org.opensolaris.consolidation value=osnet
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
depend fmri=foo/bar type=require pkg.linted.pkglint.manifest005.2=True
depend fmri=foo/bar fmri=foo/baz type=require-any
"""

expected_failures["dup-depend-require-any.mf"] = ["pkglint.manifest005.2",
    "pkglint.action005.1"]
broken_manifests["dup-depend-require-any.mf"] = \
"""
#
# We deliver duplicate dependencies, one coming from a require-any dep
#
set name=variant.arch value=i386 value=sparc
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=org.opensolaris.consolidation value=osnet
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
depend fmri=foo/bar type=require
depend fmri=foo/bar fmri=foo/baz type=require-any
"""

expected_failures["license-has-path.mf"] = ["pkglint.action007"]
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
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
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
    "pkglint.dupaction007", "pkglint.dupaction001.1"]
broken_manifests["dup-types-clashing-vars.mf"] = \
"""
#
# we try to deliver usr/sbin/fsadmin with different action types, declaring a
# variant on both.
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=i386 value=sparc
set name=variant.other value=carrots
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
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

expected_failures["duplicate_sets-linted.mf"] = ["pkglint.manifest006",
    "pkglint.action008"]
broken_manifests["duplicate_sets-linted.mf"] = \
"""
#
# We try to deliver the same set action twice, the second time we do this,
# we mark one of the actions as linted
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
set name=test value=i386
set name=test value=i386
set name=foo value=bar pkg.linted.pkglint.manifest006=True
set name=foo value=bar
"""


expected_failures["duplicate_sets-not-enough-lint.mf"] = ["pkglint.manifest006",
    "pkglint.action008"]
broken_manifests["duplicate_sets-not-enough-lint.mf"] = \
"""
#
# We try to deliver the same set action twice, the second time we do this,
# we mark one of the actions as linted, but still should have a broken manifest
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
set name=test value=i386
set name=foo value=bar pkg.linted.pkglint.manifest006=True
set name=foo value=bar
set name=foo value=bar
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
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
set name=description value="Pkglint test package"
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=i386 value=sparc
"""

expected_failures["silly_description.mf"] = ["opensolaris.manifest004.2"]
broken_manifests["silly_description.mf"] = \
"""
#
# we deliver package where the description is the same as the summary
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.149:20100917T003411Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
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
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:Rubbish/Packaging
set name=pkg.summary value="Pkglint test package"
set name=variant.arch value=i386 value=sparc
"""

expected_failures["invalid_fmri.mf"] = ["pkglint.action006",
    "pkglint.action006", "pkglint.action009", "pkglint.action009"]
broken_manifests["invalid_fmri.mf"] = \
"""
#
# We deliver some broken fmri values
#
set name=variant.arch value=i386 value=sparc
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=org.opensolaris.consolidation value=osnet
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
depend fmri=foo/bar@@134 type=require
depend fmri=foo/bar fmri="" type=require-any
"""

expected_failures["invalid_linted.mf"] = ["pkglint.action006",
    "pkglint.action006", "pkglint001.6", "pkglint001.6", "pkglint.manifest007",
    "pkglint.action009", "pkglint.action009"]
broken_manifests["invalid_linted.mf"] = \
"""
#
# We have a broken pkg.linted action, so we report both broken depend actions
# due to the corrupt FMRI values.  We also report two failed attempts
# to use the pkg.linted.pkglint.action006 value, as well as the existence of a
# pkg.linted value.
#
set name=variant.arch value=i386 value=sparc
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=org.opensolaris.consolidation value=osnet
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=pkg.linted.pkglint.action006 value=True value=False
depend fmri=foo/bar@@134 type=require
depend fmri=foo/bar fmri="" type=require-any
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

expected_failures["license-has-path.mf"] = ["pkglint.action007"]
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

# We actually emit 10 messages here in testing, 3 for the legitmate errors,
# 5 saying that we've found pkg.linted attributes in these actions, and 2
# for the errors that would be thrown were they not marked as linted.
#
expected_failures["linted-action.mf"] = ["pkglint.action001.2",
    "pkglint.dupaction003.1", "pkglint.dupaction007",
    "pkglint.action008", "pkglint.action008", "pkglint.action008",
    "pkglint.action008", "pkglint.action008", "pkglint001.5", "pkglint001.5"]
broken_manifests["linted-action.mf"] = \
"""
#
# we deliver some duplicate ref-counted actions (dir, link, hardlink) with
# differing attributes, but since they're marked as linted, we should get no
# output, we should still get the duplicate user though.
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/TIMFtest@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.other value=carrots
set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Description of pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Pkglint test package"

# underscores in the name and another attr, but only bypassing the name check
set name=here_be_underscores value=nothing underscore_attr=Foo pkg.linted.pkglint.action001.1=True

# completely linting these actions.  No errors for the first, because
# the other duplicate paths are linted.  The second will result in us logging
# a message saying we're ignoring the strange mode.
dir group=bin mode=0755 owner=root path=usr/lib/X11 pkg.linted=True
dir group=bin mode=0155 alt=foo owner=root path=usr/lib/X11/fs pkg.linted=True

# only linting this action against a specific dupaction check
dir group=staff mode=0751 owner=root path=/usr/lib/X11 pkg.linted.pkglint.dupaction007=True

# only linting this action against the dupaction group
dir group=staff mode=0751 owner=root path=/usr/lib/X11 pkg.linted.pkglint.dupaction=True

# we should still report this error:
dir group=bin mode=0755 alt=foo owner=root path=usr/lib/X11/fs
dir group=bin mode=0755 alt=bar owner=root path=usr/lib/X11/fs

user ftpuser=false gcos-field="Network Configuration Admin" group=netadm uid=17 username=netcfg
user ftpuser=false gcos-field="Network Configuration Admin" group=netadm uid=19 username=netcfg
"""

# We'll actually report two lint messages here, the existence of the
# pkg.linted attribute in the manifest, and the message bypassing
# the duplicate user action error.
# - the default log handler used by the pkglint CLI only marks
# a failure if it's > level.INFO, but for testing, we record all
# messages
expected_failures["linted-manifest.mf"] = ["pkglint001.5",
    "pkglint.manifest007"]
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
set name=pkg.description value="Description of pkglint test package"
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

expected_failures["linted-manifest-check.mf"] = ["pkglint001.5",
    "pkglint.manifest007", "pkglint.action008"]
broken_manifests["linted-manifest-check.mf"] = \
"""
#
# This manifest is delivers a weird info.classification value
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/TIMFtest@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.other value=carrots
# set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Description of pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Noodles pkg.linted.opensolaris.manifest003.6=True
set name=pkg.summary value="Pkglint test package"
set name=pkg.linted value=True
dir group=bin mode=0755 owner=root path=usr/lib/X11
"""

expected_failures["linted-manifest-check2.mf"] = ["pkglint001.5",
    "pkglint001.5", "pkglint001.5", "pkglint.manifest007", "pkglint.action008"]
broken_manifests["linted-manifest-check2.mf"] = \
"""
#
# This manifest delivers actions with underscores in attribute names
# and values, but they're all marked linted because we have a manifest-level
# pkg.linted key that covers just that check.  This produces info messages
# for each action that we're not running the pkglint.action001 check on.

# So we report 3 linted actions INFO messages, and INFO messages about the
# presence of pkg.linted attributes in one action and the manifest.
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/TIMFtest@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
# an underscore in they key "under_score", linted
set name=variant.other value=carrots under_score=oh_yes
# set name=variant.arch value=i386 value=sparc
set name=pkg.linted.pkglint.action001 value=True
set name=pkg.description value="Description of pkglint test package"
set name=description value="Pkglint test package"
# this is linted due to our our action attribute
set name=info.classification value=org.opensolaris.category.2008:System/Noodles pkg.linted.opensolaris.manifest003.6=True
# an underscore the key "foo_name"
set name=pkg.summary value="Pkglint test package" foo_name=bar
# this action is ok, underscores in attribute values are fine
dir group=bin mode=0755 owner=root path=usr/lib/X11 bar=has_underscore
"""

expected_failures["linted-manifest-check3.mf"] = ["pkglint.action008",
    "pkglint.manifest007", "pkglint.action001.1", "pkglint.action001.1",
    "pkglint001.5", "pkglint001.5"]
broken_manifests["linted-manifest-check3.mf"] = \
"""
#
# This manifest delivers lots of actions with underscores in attribute names
# and values, but we have a manifest-level check that bypasses only one
# of the checks within that method.  We should still catch the errors for
# underscores in 'set' action 'name' values, but not in other attribute names
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/TIMFtest@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.other value=carrots under_score=oh_yes
# set name=variant.arch value=i386 value=sparc
set name=pkg.linted.pkglint.action001.2 value=True
set name=pkg.description value="Description of pkglint test package"
set name=description value="Pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Noodles pkg.linted.opensolaris.manifest003.6=True
set name=pkg.summary value="Pkglint test package" foo_name=bar
set name=foo_bar value=baz
dir group=bin mode=0755 owner=root path=usr/lib/X11 bar=has_underscore
"""

expected_failures["linted-missing-summary.mf"] = ["pkglint001.5",
    "pkglint.manifest007"]
broken_manifests["linted-missing-summary.mf"] = \
"""
# We don't care we don't have a summary
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/TIMFtest@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.linted.opensolaris.manifest001.2 value=True
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Description of pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
"""

expected_failures["linted-desc-match-summary.mf"] = ["pkglint001.5", "pkglint.action008"]
broken_manifests["linted-desc-match-summary.mf"] = \
"""
# We don't care that the description matches the summary
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/TIMFtest@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=i386 value=sparc
set name=pkg.description value="Description of pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.summary value="Description of pkglint test package" pkg.linted.opensolaris.manifest004.2=True
"""

expected_failures["linted-dup-path-types.mf"] = ["pkglint.dupaction001.1",
    "pkglint.action008", "pkglint.manifest007"]
broken_manifests["linted-dup-path-types.mf"] = \
"""
# We don't care that usr/bin/ls is a different type across two actions, but
# make sure we still complain about the duplicate path attribute
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/TIMFtest@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=i386 value=sparc
set name=pkg.linted.opensolaris.manifest001.2 value=True
set name=pkg.summary value="Summary of pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
file path=usr/bin/ls owner=root group=staff mode=755 pkg.linted.pkglint.dupaction008=True
dir path=usr/bin/ls owner=root group=staff mode=755
"""

# three messages: saying we're linting the duplicate attribute path, that we've
# got a manifest with linted attributes, and an action with a linted attribute.
expected_failures["linted-dup-attrs.mf"] = ["pkglint001.5", "pkglint.action008",
    "pkglint.manifest007"]
broken_manifests["linted-dup-attrs.mf"] = \
"""
# We don't care that usr/bin/ls about the duplicate path attribute
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/TIMFtest@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=i386 value=sparc
set name=pkg.linted.opensolaris.manifest001.2 value=True
set name=pkg.summary value="Summary of pkglint test package"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
file path=usr/bin/ls owner=root group=staff mode=755 pkg.linted.pkglint.dupaction001.1=True
file path=usr/bin/ls owner=root group=staff mode=755
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
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
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
signature algorithm=sha256 value=75b662e14a4ea8f0fa0507d40133b0347a36bc1f63112487f4738073edf4455d version=0
"""

expected_failures["obsolete-has-description-linted.mf"] = ["pkglint001.5", "pkglint.action008"]
broken_manifests["obsolete-has-description-linted.mf"] = \
"""
#
# We deliver an obsolete package that has a pkg.description
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWaspell@0.5.11,5.11-0.130:20091218T222625Z
set name=pkg.obsolete value=true variant.arch=i386
set name=pkg.description value="This is a package description" pkg.linted.pkglint.manifest001.1=True
set name=variant.opensolaris.zone value=global value=nonglobal variant.arch=i386
set name=variant.arch value=i386
"""

expected_failures["obsolete-more-actions-linted.mf"] = ["pkglint.manifest001.2","pkglint.action008"]
broken_manifests["obsolete-more-actions-linted.mf"] = \
"""
#
# We deliver an obsolete package that has actions other than 'set'.
# (bogus signature on this manifest, just for testing)
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWaspell@0.5.11,5.11-0.130:20091218T222625Z
set name=pkg.obsolete value=true variant.arch=i386
set name=variant.opensolaris.zone value=global value=nonglobal variant.arch=i386
set name=variant.arch value=i386
dir mode=0555 owner=root group=sys path=/usr/bin pkg.linted.pkglint.action005.1=True
signature algorithm=sha256 value=75b662e14a4ea8f0fa0507d40133b0347a36bc1f63112487f4738073edf4455d version=0
"""

expected_failures["overlay-valid-many-overlays-valid-mismatch.mf"] = []
broken_manifests["overlay-valid-many-overlays-valid-mismatch.mf"] = \
"""
#
# This manifest declares multiple overlay=true action, each under a different
# variant, and multiple overlay=allow actions, one of our variants declares a
# different mode, which here, should be ok.
#
set name=pkg.fmri value=foo
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc
set name=variant.bar value=other value=new value=baz
set name=org.opensolaris.consolidation value=pkg
file NOHASH group=staff mode=0755 overlay=allow owner=timf path=foo preserve=true variant.arch=sparc
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386 variant.bar=other
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386 variant.bar=new
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386 variant.bar=baz
file NOHASH group=staff mode=0755 overlay=true owner=timf path=foo variant.arch=sparc
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.arch=i386
"""

expected_failures["overlay-valid-many-overlays.mf"] = []
broken_manifests["overlay-valid-many-overlays.mf"] = \
"""
#
# This manifest declares multiple overlay=true action, each under a different
# variant, and multiple overlay=allow actions.
#
set name=pkg.fmri value=foo
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc
set name=variant.bar value=other value=new value=baz
set name=org.opensolaris.consolidation value=pkg
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386 variant.bar=other
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386 variant.bar=new
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386 variant.bar=baz
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=sparc
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.arch=i386
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.arch=sparc
"""

expected_failures["overlay-valid-no-allow-overlay-variant.mf"] = []
broken_manifests["overlay-valid-no-allow-overlay-variant.mf"] = \
"""
#
# We have an overlay attribute, but no overlay=allow attribute on the 2nd
# action, but since we use use variants, the first action never needs to overlay
# another action.
#
set name=pkg.fmri value=foo
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc
set name=variant.bar value=other value=new
set name=org.opensolaris.consolidation value=pkg

file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.arch=i386 variant.bar=other

"""

expected_failures["overlay-valid-simple-no-overlay.mf"] = []
broken_manifests["overlay-valid-simple-no-overlay.mf"] = \
"""
#
# A valid manifest which declares two overlay=allow actions across different
# variants.
#
set name=pkg.fmri value=foo
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc
set name=variant.bar value=other value=new
set name=org.opensolaris.consolidation value=pkg

file NOHASH group=staff mode=0655 overlay=allow owner=timf path=foo preserve=true variant.arch=sparc
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.arch=i386
"""

expected_failures["overlay-valid-simple-overlay-true.mf"] = []
broken_manifests["overlay-valid-simple-overlay-true.mf"] = \
"""
#
# A valid manifest which just declares an overlay=true action
#
set name=pkg.fmri value=foo
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc
set name=org.opensolaris.consolidation value=pkg

file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386
"""

expected_failures["overlay-valid-simple-overlay.mf"] = []
broken_manifests["overlay-valid-simple-overlay.mf"] = \
"""
#
# A basic valid manifest that uses overlays
#
set name=pkg.fmri value=foo
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc
set name=variant.bar value=other value=new
set name=org.opensolaris.consolidation value=pkg

file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo
file NOHASH group=staff mode=0644 overlay=allow preserve=true owner=timf path=foo
"""

expected_failures["overlay-valid-triple-allowed.mf"] = []
broken_manifests["overlay-valid-triple-allowed.mf"] = \
"""
#
# A valid manifest which has a single overlay=true action, and multiple
# overlay=allow actions, each in a different variant.
#
set name=pkg.fmri value=foo
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386
set name=variant.bar value=other value=new value=baz
set name=org.opensolaris.consolidation value=pkg

file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.bar=other
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.bar=new
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.bar=baz

"""

expected_failures["overlay-valid-triple-true.mf"] = []
broken_manifests["overlay-valid-triple-true.mf"] = \
"""
#
# This manifest declares multiple overlay=true attributes, each under a
# different variant.
#
set name=pkg.fmri value=foo
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc
set name=variant.bar value=other value=new value=baz
set name=org.opensolaris.consolidation value=pkg

file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386 variant.bar=other
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386 variant.bar=new
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386 variant.bar=baz
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.arch=i386
"""

expected_failures["overlay-valid-mismatch-attrs.mf"] = []
broken_manifests["overlay-valid-mismatch-attrs.mf"] = \
"""
#
# We declare overlays, but have mismatching attributes between them
# blah=foo differs, but shouldn't matter.
#
set name=pkg.fmri value=bar
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc value=ppc
set name=variant.timf value=foo value=bar
set name=org.opensolaris.consolidation value=pkg
file NOHASH group=staff mode=0755 overlay=true owner=timf path=foo variant.arch=ppc variant.timf=foo blah=foo
file NOHASH group=staff mode=0755 overlay=allow owner=timf path=foo preserve=rename variant.arch=ppc variant.timf=foo
"""

# more overlay checks
expected_failures["overlay-invalid-broken-attrs.mf"] = ["pkglint.dupaction009.6"]
broken_manifests["overlay-invalid-broken-attrs.mf"] = \
"""
#
# We declare overlays, but have mismatching attributes between them
#
set name=pkg.fmri value=bar
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc value=ppc
set name=variant.timf value=foo value=bar
set name=org.opensolaris.consolidation value=pkg
file NOHASH group=staff mode=0755 overlay=true owner=timf path=foo variant.arch=ppc variant.timf=foo blah=foo
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=rename variant.arch=ppc variant.timf=foo
"""

expected_failures["overlay-invalid-duplicate-allows.mf"] = \
    ["pkglint.dupaction009.3"]
broken_manifests["overlay-invalid-duplicate-allows.mf"] = \
"""
#
# Duplicate overlay=allow actions, with no overlay=true action.
#
set name=pkg.fmri value=bar
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc value=ppc
set name=variant.timf value=foo value=bar
set name=org.opensolaris.consolidation value=pkg
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=rename variant.arch=ppc
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=rename variant.arch=ppc
"""

expected_failures["overlay-invalid-duplicate-overlays.mf"] = \
    ["pkglint.dupaction009.2"]
broken_manifests["overlay-invalid-duplicate-overlays.mf"] = \
"""
# We have duplicate overlay actions

set name=pkg.fmri value=bar
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc value=ppc
set name=variant.timf value=foo value=bar
set name=org.opensolaris.consolidation value=pkg
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=ppc
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=ppc
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=rename variant.arch=ppc
"""

expected_failures["overlay-invalid-duplicate-pairs.mf"] = \
    ["pkglint.dupaction009.4", "pkglint.dupaction009.2"]
broken_manifests["overlay-invalid-duplicate-pairs.mf"] = \
"""
# ensure that depite complimentary pairs of overlay actions,
# we still catch the duplicate one

set name=pkg.fmri value=bar
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc value=ppc
set name=variant.timf value=foo value=bar
set name=org.opensolaris.consolidation value=pkg
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=ppc
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=rename variant.arch=ppc
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=ppc
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=rename variant.arch=ppc
"""

expected_failures["overlay-invalid-no-allow-overlay.mf"] = \
    ["pkglint.dupaction001.2", "pkglint.dupaction009.7",
    "pkglint.dupaction009.5"]
broken_manifests["overlay-invalid-no-allow-overlay.mf"] = \
"""
# we have an overlay attribute, but no overlay=allow attribute
# on the 2nd action
set name=pkg.fmri value=foo
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc
set name=variant.bar value=other value=new
set name=org.opensolaris.consolidation value=pkg

file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386
file NOHASH group=staff mode=0644 owner=timf path=foo preserve=true variant.arch=i386
"""

expected_failures["overlay-invalid-no-overlay-allow.mf"] = \
    ["pkglint.dupaction001.1", "pkglint.dupaction009.7",
    "pkglint.dupaction009.5"]
broken_manifests["overlay-invalid-no-overlay-allow.mf"] = \
"""
set name=pkg.fmri value=bar
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386
set name=org.opensolaris.consolidation value=pkg
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo
file NOHASH group=staff mode=0644 owner=timf path=foo preserve=rename
"""

expected_failures["overlay-invalid-no-overlay-preserve.mf"] = \
    ["pkglint.dupaction009.1", "pkglint.dupaction009.5"]
broken_manifests["overlay-invalid-no-overlay-preserve.mf"] = \
"""
# we don't delcare a 'preserve' attribute on our overlay=allow action
#
set name=pkg.fmri value=bar
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc value=ppc
set name=org.opensolaris.consolidation value=pkg
file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo
"""

expected_failures["overlay-invalid-no-overlay-true.mf"] = \
    ["pkglint.dupaction001.1", "pkglint.dupaction009.7"]
broken_manifests["overlay-invalid-no-overlay-true.mf"] = \
"""
# we're missing an overlay=true action, resulting in a duplicate
set name=pkg.fmri value=bar
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=org.opensolaris.consolidation value=ips
set name=variant.arch value=i386
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true
file NOHASH group=staff mode=0644 owner=timf path=foo preserve=rename
"""

expected_failures["overlay-invalid-triple-broken-variants.mf"] = \
    ["pkglint.dupaction009.4"]
broken_manifests["overlay-invalid-triple-broken-variants.mf"] = \
"""
# this package declares overlay actions, but we have duplicate
# overlay='allow' attributes for variant.foo=foo1

set name=pkg.fmri value=foo
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386
set name=variant.bar value=other value=new value=baz
set name=variant.foo value=foo1 value=foo2
set name=org.opensolaris.consolidation value=pkg

file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.bar=other
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.bar=new variant.foo=foo1
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.bar=new variant.foo=foo2
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.arch=i386 variant.bar=new variant.foo=foo1
"""

expected_failures["overlay-invalid-triple-broken.mf"] = \
    ["pkglint.dupaction009.4"]
broken_manifests["overlay-invalid-triple-broken.mf"] = \
"""
# this manifest has multiple overlay=allow variants, but the last is
# duplicated across variant.bar variants
set name=pkg.fmri value=foo
set name=pkg.summary value="Image Packaging System"
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
set name=pkg.description value="overlay checks"
set name=variant.arch value=i386 value=sparc
set name=variant.bar value=other value=new value=baz
set name=org.opensolaris.consolidation value=pkg

file NOHASH group=staff mode=0644 overlay=true owner=timf path=foo variant.arch=i386
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.arch=i386 variant.bar=other
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.arch=i386 variant.bar=new
file NOHASH group=staff mode=0644 overlay=allow owner=timf path=foo preserve=true variant.arch=i386
"""

expected_failures["renamed-more-actions.mf"] = ["pkglint.manifest002.1",
    "pkglint.manifest002.3"]
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

expected_failures["renamed-more-actions-linted.mf"] = ["pkglint.manifest002.3",
    "pkglint.action008", "pkglint001.5"]
broken_manifests["renamed-more-actions-linted.mf"] = \
"""
#
# We've reported a package as having been renamed, yet try to deliver
# actions other than 'set' and 'depend'.  The additional actions are marked
# as linted.
# (bogus signature on this manifest, just for testing)
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWzsh@4.3.9,5.11-0.133:20100216T103302Z
set name=org.opensolaris.consolidation value=sfw
set name=pkg.renamed value=true
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=sparc value=i386
depend fmri=shell/zsh@4.3.9-0.133 type=require
depend fmri=consolidation/sfw/sfw-incorporation type=require
dir mode=0555 owner=root group=sys path=/usr/bin pkg.linted.pkglint.manifest002.1=True
signature algorithm=sha256 value=75b662e14a4ea8f0fa0507d40133b0347a36bc1f63112487f4738073edf4455d version=0
"""

expected_failures["renamed-more-actions-not-all-linted.mf"] = \
    ["pkglint.manifest002.1", "pkglint.manifest002.3", "pkglint.action008"]
broken_manifests["renamed-more-actions-not-all-linted.mf"] = \
"""
#
# We've reported a package as having been renamed, yet try to deliver
# actions other than 'set' and 'depend'.  One of these additional actions
# is linted, but not all of them, so we still throw pkglint.manifest002.1
# (bogus signature on this manifest, just for testing)
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWzsh@4.3.9,5.11-0.133:20100216T103302Z
set name=org.opensolaris.consolidation value=sfw
set name=pkg.renamed value=true
set name=variant.opensolaris.zone value=global value=nonglobal
set name=variant.arch value=sparc value=i386
depend fmri=shell/zsh@4.3.9-0.133 type=require
depend fmri=consolidation/sfw/sfw-incorporation type=require
dir mode=0555 owner=root group=sys path=/usr/bin pkg.linted.pkglint.manifest002.1=True
dir mode=0555 owner=root group=sys path=/usr/lib
signature algorithm=sha256 value=75b662e14a4ea8f0fa0507d40133b0347a36bc1f63112487f4738073edf4455d version=0
"""

expected_failures["renamed.mf"] = ["pkglint.manifest002.3"]
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

expected_failures["underscores.mf"] = ["pkglint.action001.1",
    "pkglint.action001.3", "pkglint.action001.2"]
broken_manifests["underscores.mf"] = \
"""
#
# We try to deliver attributes with underscores.
#
set name=pkg.fmri value=pkg://opensolaris.org/system/underscores@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
set name=test value=i386 variant.arch=sparc
set name=this_underscore_check value=i386 another_attribute=False
set name=info.source_url value=http://www.sun.com
dir group=bin mode=0755 owner=root path=usr/lib/X11 reboot_needed=False
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
set name=pkg.description value="Description of pkglint test package"
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
set name=pkg.description value="Description of pkglint test package"
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
    "pkglint.action002.4"]
broken_manifests["unusual_mode_noexecdir.mf"] = \
"""
#
# we deliver a directory with an unexecutable mode 0422
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.1.0,5.11-0.141:20100604T143737Z
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="Description of pkglint test package"
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

expected_failures["action_validation.mf" ] = ["pkglint.action009"]
broken_manifests["action_validation.mf" ] = \
"""
#
# We deliver an intentionally broken file action
#
set name=pkg.fmri value=pkg://opensolaris.org/pkglint/test@1.0,1.0
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.description value="A pkglint test"
set name=pkg.summary value="Yet another test"
set name=variant.arch value=i386 value=sparc
set name=info.classification value=org.opensolaris.category.2008:System/Packaging
file nohash path=/dev/null
"""

expected_failures["whitelist_action_missing_dep.mf"] = []
broken_manifests["whitelist_action_missing_dep.mf"] = \
"""
#
#
# We declare a pkg.lint.pkglint.action005.1 parameter to a depend action that
# tells the check to ignore any missing dependencies, as part of its package
# obsoletion test
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
depend type=require fmri=test/package pkg.lint.pkglint.action005.1.missing-deps=pkg:/test/package
"""

expected_failures["whitelist_mf_missing_dep.mf"] = []
broken_manifests["whitelist_mf_missing_dep.mf"] = \
"""
#
# We declare a pkg.lint.pkglint.action005.1 parameter that tells the check to
# ignore any missing dependencies, as part of its package obsoletion test
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
set name=pkg.lint.pkglint.action005.1.missing-deps value=pkg:/test/package value=pkg:/other/package
depend type=require fmri=test/package
"""

expected_failures["okay_underscores.mf"] = []
broken_manifests["okay_underscores.mf"] = \
"""
#
# Underscores in attribute names generate warnings, except for a few that are
# grandfathered in, locale facets, which have locale names in them, and
# version-lock facets, which take package names.
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=org.opensolaris.consolidation value=osnet
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=variant.arch value=i386 value=sparc
depend type=incorporate fmri=system/blah_blah@0.5.11-0.172 facet.version-lock.system/blah_blah=true
link path=usr/lib/locale/en_US.UTF-8/foo.mo target=bar.mo facet.locale.en_US=true
link path=usr/bin/foo1 target=bar restart_fmri=true
link path=usr/bin/foo2 target=bar refresh_fmri=true
link path=usr/bin/foo3 target=bar suspend_fmri=true
link path=usr/bin/foo4 target=bar disable_fmri=true
link path=usr/bin/foo5 target=bar reboot_needed=true
link path=usr/bin/foo6 target=bar clone_perms="* 0666 root root"
link path=usr/bin/foo7 target=bar original_name=SUNWcar:usr/bin/wazaap
"""

class TestLogFormatter(log.LogFormatter):
        """Records log messages to a buffer"""
        def __init__(self):
                self.messages = []
                self.ids = []
                super(TestLogFormatter, self).__init__()

        def format(self, msg, ignore_linted=False):
                if isinstance(msg, log.LintMessage):
                        linted_flag = False
                        try:
                                linted_flag = linted(action=self.action,
                                    manifest=self.manifest, lint_id=msg.msgid)
                        except DuplicateLintedAttrException, err:
                                self.messages.append("%s\t%s" %
                                    ("pkglint001.6", "Logging error: %s" % err))
                                self.ids.append("pkglint001.6")

                        if linted_flag and not ignore_linted:
                                linted_msg = (
                                    "Linted message: %(id)s  %(msg)s") % \
                                    {"id": msg.msgid, "msg": msg}
                                self.messages.append("%s\t%s" %
                                        ("pkglint001.5", linted_msg))
                                self.ids.append("pkglint001.5")
                                return

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
                        self.debug("running lint checks on %s" % manifest)
                        basename = os.path.basename(manifest)
                        lint_logger = TestLogFormatter()
                        lint_engine = engine.LintEngine(lint_logger,
                            config_file=os.path.join(self.test_root,
                            "pkglintrc"), use_tracker=False)

                        manifests = read_manifests([manifest], lint_logger)
                        lint_engine.setup(lint_manifests=manifests)

                        lint_engine.execute()
                        lint_engine.teardown()

                        # look for pkglint001.3 in the output, regardless
                        # of whether we marked that as linted, since it
                        # indicates we caught an exception in one of the
                        # Checker methods.
                        for message in lint_logger.messages:
                                self.assert_("pkglint001.3" not in message,
                                    "Checker exception thrown for %s: %s" %
                                    (basename, message))

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
                                            "%s vs. %s\n%s" %
                                            (basename, str(reported),
                                            str(known),
                                            "\n".join(lint_logger.messages)))
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
# we don't declare a dependency on the package delivering the legacy action.
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWckr@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=pkg.renamed value=true
set name=variant.arch value=i386 value=sparc
depend fmri=system/more type=require
"""

        ref_mf["twovar.mf"] = """
#
# This package shares the kernel/strmod path with onevar.mf but has a different
# set of variants for both the action and the package.  This should not cause
# an assertion to be raised.
#
set name=variant.arch value=sparc value=i386
set name=pkg.summary value="A packge with two variant values"
set name=pkg.description value="A package with two values for variant.arch."
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=org.opensolaris.consolidation value=osnet
set name=variant.opensolaris.zone value=global value=nonglobal
set name=pkg.fmri value=pkg://opensolaris.org/variant/twovar@0.5.11,5.11-0.148:20100910T211706Z
dir group=sys mode=0755 owner=root path=kernel/strmod variant.opensolaris.zone=global
"""
        ref_mf["no_rename-dummy-ancestor.mf"] = """
#
# This is a dummy package designed trip a lint of no-ancestor-legacy.mf
# we don't declare a dependency on the FMRI delivered by it.
#
set name=pkg.fmri value=pkg://opensolaris.org/SUNWckr-norename@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
depend fmri=system/kernel type=require
"""

        ref_mf["legacy-uses-renamed-ancestor.mf"] = """
#
# A package with a legacy action that points to a renamed ancestor
#
set name=pkg.fmri value=pkg://opensolaris.org/legacy-uses-renamed-ancestor@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
legacy pkg="renamed-ancestor-old" desc="core kernel software for a specific instruction-set architecture" arch=i386 category=system hotline="Please contact your local service provider" name="Core Solaris Kernel (Root)" vendor="Sun Microsystems, Inc." version=11.11,REV=2009.11.11
"""

        ref_mf["renamed-ancestor-old.mf"] = """
#
# The ancestor referred to above, but we've renamed it
#
set name=pkg.fmri value=pkg://opensolaris.org/renamed-ancestor-old@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
set name=pkg.renamed value=true
depend fmri=renamed-ancestor-new type=require
"""
        ref_mf["renamed-ancestor-new.mf"] = """
#
# The renamed legacy ancestor - this correctly depends on the latest
# named version
#
set name=pkg.fmri value=pkg://opensolaris.org/renamed-ancestor-new@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
set name=pkg.renamed value=true
depend fmri=legacy-uses-renamed-ancestor type=require
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

        expected_failures["onevar.mf"] = []
        lint_mf["onevar.mf"] = """
#
# Test that a package which is only published against one variant value doesn't
# cause an assertion failure when it shares an action with another package.
# In this case, ketnel/strmod is shared between this package and the reference
# package twovar.
#
set name=pkg.summary value="A package with one variant" variant.arch=i386
set name=org.opensolaris.consolidation value=osnet variant.arch=i386
set name=info.classification value="org.opensolaris.category.2008:Drivers/Other Peripherals" variant.arch=i386
set name=variant.arch value=i386
set name=variant.opensolaris.zone value=global value=nonglobal variant.arch=i386
set name=pkg.fmri value=pkg://opensolaris.org/variants/onevar@0.5.11,5.11-0.148:20100910T195826Z
set name=pkg.description value="A package published against only one variant value" variant.arch=i386
dir group=sys mode=0755 owner=root path=kernel/strmod variant.arch=i386 variant.opensolaris.zone=global
"""

        expected_failures["broken-renamed-ancestor-new.mf"] = \
            ["pkglint.manifest002.3"]
        lint_mf["broken-renamed-ancestor-new.mf"] = """
#
# A new version of one of the packages in the rename chain for
# legacy-has-renamed-ancestor, which should result in an error.
# When tested on its own, this package results in just the 'missing rename'
# error, pkglint.manifest002.3  When tested as part of a checking a legacy
# action which has a pkg attribute pointing to an old package that gets renamed,
# we should get pkglint.action003.4
#
set name=pkg.fmri value=pkg://opensolaris.org/renamed-ancestor-new@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
set name=pkg.renamed value=true
depend fmri=renamed-ancestor-missing type=require
"""

        expected_failures["self-depend-renamed-ancestor-new.mf"] = ["pkglint.manifest002.4"]
        lint_mf["self-depend-renamed-ancestor-new.mf"] = """
#
# A new version of one of the packages in the rename chain for
# legacy-has-renamed-ancestor, which should result in an error.
# When tested on its own, this package results in the 'looping rename'
# error, pkglint.manifest002.4  When tested as part of a checking a legacy action
# which has a pkg attribute point to an old package that gets renamed,
# we should get pkglint.action003.5, since we're trying to depend on ourselves
#
set name=pkg.fmri value=pkg://opensolaris.org/renamed-ancestor-new@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
set name=pkg.renamed value=true
depend fmri=renamed-ancestor-new type=require
"""

        lint_move_mf = {}
        lint_move_mf["move-sample1.mf"] = """
#
# A sample package which delivers several actions, to 0.161. We no longer
# deliver etc/passwd, moving that to the package in move-sample2.mf below.
#
set name=pkg.fmri value=pkg://foo.org/system/kernel@0.5.11,5.11-0.161
set name=pkg.description value="we remove etc/passwd from this package"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
dir group=sys mode=0755 owner=root path=etc
"""

        lint_move_mf["move-sample2.mf"] = """
#
# A sample package which delivers several actions, we now deliver etc/passwd
# also.
#
set name=pkg.fmri value=pkg://foo.org/system/additional@0.5.11,5.11-0.161
set name=pkg.description value="this manifest now gets etc/passwd too"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="additional content"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/motd group=sys mode=0644 owner=root path=etc/motd
file /etc/passwd path=etc/passwd group=sys mode=0644 owner=root preserve=true
dir group=sys mode=0755 owner=root path=etc
dir group=sys mode=0755 owner=root path=etc
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
                            command="publish %s" % item)
                self.pkgsend(depot_url=self.ref_uri,
                            command="refresh-index")

                paths = self.make_misc_files(self.lint_mf)
                for item in paths:
                        self.pkgsend(depot_url=self.lint_uri,
                            command="publish %s" % item)
                self.pkgsend(depot_url=self.lint_uri,
                            command="refresh-index")
                # we should sign the repositories for additional coverage
                self.pkgsign(self.lint_uri, "'*'")
                self.pkgsign(self.ref_uri, "'*'")

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
                        self.debug("running lint checks on %s" % manifest)
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

                        # prune missing dependency and missing rename warnings
                        lint_msgs = []
                        for msg in lint_logger.messages:
                                if "pkglint.manifest002.3" in msg or \
                                    "pkglint.manifest002.4" in msg or \
                                    "pkglint.action005.1" in msg:
                                        pass
                                else:
                                        lint_msgs.append(msg)

                        self.assertFalse(lint_msgs,
                            "Unexpected lint messages when linting individual "
                            "manifests that should contain no errors: %s %s" %
                            (basename, "\n".join(lint_msgs)))

        def test_broken_legacy_rename(self):
                """Tests that linting a package where we break the renaming
                of a legacy package, we'll get an error."""

                paths = self.make_misc_files(self.lint_mf)
                paths.extend(self.make_misc_files(self.ref_mf))
                rcfile = os.path.join(self.test_root, "pkglintrc")

                legacy = os.path.join(self.test_root,
                    "legacy-uses-renamed-ancestor.mf")
                renamed_new = os.path.join(self.test_root,
                    "broken-renamed-ancestor-new.mf")
                renamed_self_depend = os.path.join(self.test_root,
                    "self-depend-renamed-ancestor-new.mf")

                # look for a rename that didn't ultimately resolve to the
                # package that contained the legacy action
                lint_logger = TestLogFormatter()
                manifests = read_manifests([legacy, renamed_new], lint_logger)

                lint_engine = engine.LintEngine(lint_logger, use_tracker=False,
                    config_file=rcfile)
                lint_engine.setup(cache=self.cache_dir,
                    ref_uris=[self.ref_uri], lint_manifests=manifests)
                lint_engine.execute()
                lint_engine.teardown(clear_cache=True)

                lint_msgs = []
                for msg in lint_logger.messages:
                        if "pkglint.action005.1" not in msg:
                                lint_msgs.append(msg)

                self.assert_(len(lint_msgs) == 2, "Unexpected lint messages "
                    "%s produced when linting broken renaming with legacy "
                    "pkgs" % lint_msgs)

                seen_2_3 = False
                seen_3_4 = False
                for i in lint_logger.ids:
                        if i == "pkglint.manifest002.3":
                                seen_2_3 = True
                        if i == "pkglint.action003.4":
                                seen_3_4 = True

                self.assert_(seen_2_3 and seen_3_4,
                    "Missing expected broken renaming legacy errors, "
                    "got %s" % lint_msgs)

                # make sure we spot renames that depend upon themselves
                lint_logger = TestLogFormatter()
                manifests = read_manifests([legacy, renamed_self_depend],
                    lint_logger)

                lint_engine = engine.LintEngine(lint_logger, use_tracker=False,
                    config_file=rcfile)
                lint_engine.setup(cache=self.cache_dir,
                    ref_uris=[self.ref_uri], lint_manifests=manifests)
                lint_engine.execute()
                lint_engine.teardown(clear_cache=True)

                lint_msgs = []
                for msg in lint_logger.messages:
                        # if "pkglint.action005.1" not in msg:
                        lint_msgs.append(msg)

                self.assert_(len(lint_msgs) == 2, "Unexpected lint messages "
                    "produced when linting broken self-dependent renaming with "
                    "legacy pkgs")
                seen_2_4 = False
                seen_3_5 = False
                for i in lint_logger.ids:
                        if i == "pkglint.manifest002.4":
                                seen_2_4 = True
                        if i == "pkglint.action003.5":
                                seen_3_5 = True
                self.assert_(seen_2_3 and seen_3_4,
                    "Missing expected broken renaming self-dependent errors "
                    "with legacy pkgs. Got %s" % lint_msgs)

        def test_relative_path(self):
                """The engine can start with a relative path to its cache."""
                lint_logger = TestLogFormatter()
                lint_engine = engine.LintEngine(lint_logger,
                    use_tracker=False,
                    config_file=os.path.join(self.test_root,
                    "pkglintrc"))

                lint_engine.setup(cache=self.cache_dir,
                    lint_uris=[self.ref_uri])

                lint_engine.execute()
                lint_engine.teardown()

                relative = os.path.join("..", os.path.basename(self.cache_dir))
                cache = os.path.join(self.cache_dir, relative)
                lint_engine.setup(cache=cache)
                lint_engine.execute()
                lint_engine.teardown(clear_cache=True)

        def test_ref_file_move(self):
                """The dupaction checks can cope with a file that moves between
                packages, where the old package was delivered in our reference
                repository and we're linting both new packages: the package
                from which the file was moved, as well as the package to which
                the file is moving.

                It should report an error when we only lint the new version
                of the package to which the file is moving, but not the new
                version of package from which the file was moved."""

                paths = self.make_misc_files(self.lint_move_mf)
                paths.sort()
                rcfile = os.path.join(self.test_root, "pkglintrc")

                move_src = os.path.join(self.test_root, "move-sample1.mf")
                move_dst = os.path.join(self.test_root, "move-sample2.mf")

                lint_logger = TestLogFormatter()

                # first check that file moves work properly, that is,
                # we should report no errors here.
                manifests = read_manifests([move_src, move_dst], lint_logger)
                lint_engine = engine.LintEngine(lint_logger, use_tracker=False,
                    config_file=rcfile)
                lint_engine.setup(cache=self.cache_dir,
                    ref_uris=[self.ref_uri], lint_manifests=manifests)
                lint_engine.execute()
                lint_engine.teardown(clear_cache=True)

                lint_msgs = []
                for msg in lint_logger.messages:
                        lint_msgs.append(msg)

                self.assert_(lint_msgs == [], "Unexpected errors during file "
                    "movement between packages: %s" % "\n".join(lint_msgs))

                # next check that when delivering only the moved-to package,
                # we report a duplicate error.
                manifests = read_manifests([move_dst], lint_logger)
                lint_engine = engine.LintEngine(lint_logger, use_tracker=False,
                    config_file=rcfile)
                lint_engine.setup(cache=self.cache_dir,
                    ref_uris=[self.ref_uri], lint_manifests=manifests)
                lint_engine.execute()
                lint_engine.teardown(clear_cache=True)

                lint_msgs = []
                for msg in lint_logger.messages:
                        lint_msgs.append(msg)

                self.assert_(len(lint_msgs) == 1, "Expected duplicate path "
                    "error not seen when moving file between packages, but "
                    "omitting new source package: %s" % "\n".join(lint_msgs))
                self.assert_(lint_logger.ids[0] == "pkglint.dupaction001.1",
                    "Expected pkglint.dupaction001.1, got %s" %
                    lint_logger.ids[0])

class TestLintEngineInternals(pkg5unittest.Pkg5TestCase):

        def test_lint_fmri_successor(self):
            """lint_fmri_successor reports lint successors correctly.

            The lint fmri_successor check has a biase for new FMRIs  and
            acts differently to the pkg.fmri.PkgFmri is_successor check,
            favouring the new fmri if it is missing information not present
            in the old fmri.

            We also include some tests for the standard is_successor
            check, which is used in the implementation of
            lint_fmri_successor."""

            class FmriPair():
                    def __init__(self, new, old):
                            self.new = new
                            self.old = old

                    def __repr__(self):
                            return "FmriPair(%s, %s) " % (self.new, self.old)

            def is_successor(pair):
                    """baseline the standard fmri.is_successor check"""
                    new = fmri.PkgFmri(pair.new)
                    old = fmri.PkgFmri(pair.old)
                    return new.is_successor(old)

            def commutative(pair, ignore_pubs=True):
                    """test that new succeeds old and old succeeds new."""
                    new = fmri.PkgFmri(pair.new)
                    old = fmri.PkgFmri(pair.old)
                    return lint_fmri_successor(new, old,
                        ignore_pubs=ignore_pubs) and \
                        lint_fmri_successor(old, new, ignore_pubs=ignore_pubs)

            def newer(pair, ignore_pubs=True, ignore_timestamps=True):
                    """test that new succeeds old, but old does not succeed new"""
                    new = fmri.PkgFmri(pair.new)
                    old = fmri.PkgFmri(pair.old)
                    return lint_fmri_successor(new, old,
                        ignore_pubs=ignore_pubs,
                        ignore_timestamps=ignore_timestamps) and \
                        not lint_fmri_successor(old, new,
                        ignore_pubs=ignore_pubs,
                        ignore_timestamps=ignore_timestamps)

            # messages used in assertions
            fail_msg = "%s do not pass %s check"
            fail_msg_pubs = "%s do not pass %s check, ignoring publishers"
            fail_msg_ts = "%s do not pass %s check, ignoring timestamps"

            fail_comm = fail_msg % ("%s", "commutative")
            fail_comm_pubs = fail_msg_pubs % ("%s", "commutative")
            fail_newer = fail_msg % ("%s", "newer")
            fail_newer_pubs = fail_msg_pubs % ("%s", "newer")
            fail_newer_ts = fail_msg_ts % ("%s", "newer timestamp-sensitive")
            fail_successor = fail_msg % ("%s", "is_successor")

            # 1 identical everything
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.120:20101003T222523Z",
                "pkg://foo.org/tst@1.0,5.11-0.120:20101003T222523Z")
            self.assert_(commutative(pair), fail_comm % pair)
            self.assert_(commutative(pair, ignore_pubs=False),
                fail_comm_pubs % pair)
            self.assert_(is_successor(pair), fail_successor % pair)

            # 2 identical versions
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.120",
                "pkg://foo.org/tst@1.0,5.11-0.120")
            self.assert_(commutative(pair), fail_comm % pair)
            self.assert_(commutative(pair, ignore_pubs=False),
                fail_comm_pubs % pair)
            self.assert_(is_successor(pair), fail_successor % pair)


            # 3 identical names
            pair = FmriPair("pkg://foo.org/tst",
                "pkg://foo.org/tst")
            self.assert_(commutative(pair), fail_comm % pair)
            self.assert_(commutative(pair, ignore_pubs=False),
                fail_comm_pubs % pair)
            self.assert_(is_successor(pair), fail_successor % pair)


            # 4 differing timestamps, same version (identical, in pkglint's view)
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.120:20101003T222523Z",
                "pkg://foo.org/tst@1.0,5.11-0.120:20311003T222559Z")
            self.assert_(commutative(pair), fail_comm % (pair))
            self.assert_(commutative(pair, ignore_pubs=False),
                fail_comm_pubs % pair)
            self.assert_(not is_successor(pair), fail_successor % pair)
            self.assert_(not newer(pair, ignore_timestamps=False),
                fail_newer_ts % pair)

            # 5 missing timestamps, same version
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.120",
                "pkg://foo.org/tst@1.0,5.11-0.120:20101003T222523Z")
            self.assert_(commutative(pair), fail_comm % (pair))
            self.assert_(commutative(pair, ignore_pubs=False),
                fail_comm_pubs % pair)

            # 6 missing timestamps, different version
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.121",
                "pkg://foo.org/tst@1.0,5.11-0.120:20101003T222523Z")
            self.assert_(newer(pair), fail_newer % pair)
            self.assert_(newer(pair, ignore_pubs=False),
                fail_newer_pubs % pair)

            # 7 different versions
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.121:20101003T222523Z",
                "pkg://foo.org/tst@1.0,5.11-0.120:20101003T222523Z")
            self.assert_(newer(pair), fail_newer % pair)
            self.assert_(newer(pair, ignore_pubs=False),
                fail_newer_pubs % pair)

            # 8 different versions (where string comparisons won't work since
            # with string comparisons, '0.133' < '0.99' which is not desired
            pair = FmriPair("pkg://opensolaris.org/SUNWfcsm@0.5.11,5.11-0.133:20100216T065435Z",
            "pkg://opensolaris.org/SUNWfcsm@0.5.11,5.11-0.99:20100216T065435Z")
            self.assert_(newer(pair), fail_newer % pair)
            self.assert_(newer(pair, ignore_pubs=False),
                fail_newer_pubs % pair)

            #  Now the same set of tests, this time with different publishers
            # 1.1 identical everything
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.120:20101003T222523Z",
                "pkg://bar.org/tst@1.0,5.11-0.120:20101003T222523Z")
            self.assert_(commutative(pair), fail_comm % pair)
            self.assert_(not newer(pair, ignore_pubs=False),
                fail_newer_pubs % pair)
            self.assert_(is_successor(pair), fail_successor % pair)

             # 2.1 identical versions
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.120",
                "pkg://bar.org/tst@1.0,5.11-0.120")
            self.assert_(commutative(pair), fail_comm % pair)
            self.assert_(not commutative(pair, ignore_pubs=False),
                fail_comm_pubs % pair)
            self.assert_(is_successor(pair), fail_successor % pair)

            # 3.1 identical names
            pair = FmriPair("pkg://foo.org/tst",
                "pkg://bar.org/tst")
            self.assert_(commutative(pair), fail_comm % pair)
            self.assert_(not commutative(pair, ignore_pubs=False),
                fail_comm_pubs % pair)
            self.assert_(is_successor(pair), fail_successor % pair)

            # 4.1 differing timestamps, same version (identical, in pkglint's
            # view unless we specifically look at the timestamp)
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.120:20101003T222523Z",
                "pkg://bar.org/tst@1.0,5.11-0.120:20311003T222559Z")
            self.assert_(commutative(pair), fail_comm % (pair))
            self.assert_(not commutative(pair, ignore_pubs=False),
                fail_comm_pubs % pair)
            self.assert_(not is_successor(pair), fail_successor % pair)
            self.assert_(not newer(pair, ignore_timestamps=False),
                fail_newer_ts % pair)

            # 5.1 missing timestamps, same version
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.120",
                "pkg://bar.org/tst@1.0,5.11-0.120:20101003T222523Z")
            self.assert_(commutative(pair), fail_comm % (pair))
            self.assert_(not commutative(pair, ignore_pubs=False),
                fail_comm_pubs % pair)
            self.assert_(not is_successor(pair), fail_successor % pair)

            # 6.1 missing timestamps, different version
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.121",
                "pkg://bar.org/tst@1.0,5.11-0.120:20101003T222523Z")
            self.assert_(newer(pair), fail_newer % pair)
            self.assert_(not newer(pair, ignore_pubs=False),
                fail_newer_pubs % pair)
            self.assert_(is_successor(pair), fail_successor % pair)

            # 7.1 different versions
            pair = FmriPair("pkg://foo.org/tst@1.0,5.11-0.121:20101003T222523Z",
                "pkg://bar.org/tst@1.0,5.11-0.120:20101003T222523Z")
            self.assert_(newer(pair), fail_newer % pair)
            self.assert_(not newer(pair, ignore_pubs=False),
                fail_newer_pubs % pair)
            self.assert_(is_successor(pair), fail_successor % pair)

            # 8.1 different versions (where string comparisons won't work
            # with string comparisons, '0.133' < '0.99' which is not desired
            pair = FmriPair("pkg://opensolaris.org/SUNWfcsm@0.5.11,5.11-0.133:20100216T065435Z",
            "pkg://solaris/SUNWfcsm@0.5.11,5.11-0.99:20100216T065435Z")
            self.assert_(newer(pair), fail_newer % pair)
            self.assert_(not newer(pair, ignore_pubs=False),
                fail_newer_pubs % pair)

            # missing publishers
            pair = FmriPair("pkg:/tst", "pkg://foo.org/tst")
            self.assert_(commutative(pair), fail_newer % pair)
            self.assert_(not newer(pair, ignore_pubs=False),
                fail_newer_pubs % pair)
            self.assert_(is_successor(pair), fail_successor % pair)

            # different publishers
            pair = FmriPair("pkg://bar.org/tst", "pkg://foo.org/tst")
            self.assert_(commutative(pair), fail_newer % pair)
            self.assert_(not newer(pair, ignore_pubs=False),
                fail_newer_pubs % pair)
            self.assert_(is_successor(pair), fail_successor % pair)

            # different publishers, missing timestmap, same version
            pair = FmriPair("pkg://bar.org/tst@1.0,5.11-0.121",
                "pkg://foo.org/tst@1.0,5.11-0.121:20101003T222523Z")
            self.assert_(commutative(pair), fail_newer % pair)
            self.assert_(not newer(pair, ignore_pubs=False),
                fail_newer_pubs % (pair))
            self.assert_(not is_successor(pair), fail_successor % pair)

            # different publishers, missing timestmap
            pair = FmriPair("pkg://bar.org/tst@1.0,5.11-0.122",
                "pkg://foo.org/tst@1.0,5.11-0.121:20101003T222523Z")
            self.assert_(newer(pair), fail_newer % pair)
            self.assert_(not newer(pair, ignore_pubs=False),
                fail_newer_pubs % pair)
            self.assert_(is_successor(pair), fail_successor % pair)

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
