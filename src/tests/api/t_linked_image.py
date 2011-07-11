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
# Copyright (c) 2011, 2012, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import shutil
import sys
import traceback

import unittest

import pkg.actions
import pkg.client.api as api
import pkg.client.api_errors as apx
import pkg.client.linkedimage as li
import pkg.client.progress as progress
import pkg.client.publisher as publisher

from pkg.client.debugvalues import DebugValues
from pkg.client.pkgdefs import *

p_update_index = 0

def substring_verify(string, substring):
        if string.find(substring) == -1:
                raise RuntimeError("""
Expected "%s" to be contained in:
%s
"""
                % (substring, string))

def apx_verify(e, e_type, e_member=None):

        if e == None:
                raise RuntimeError("""
Expected %s exception.
Didn't get any exception.
"""
                % (str(e_type)))

        if type(e) != e_type:
                raise RuntimeError("""
Expected %s exception.
Got a %s exception:

%s
"""
                % (str(e_type),
                        str(type(e)), traceback.format_exc()))

        if e_member == None:
                return

        if not getattr(e, e_member):
                raise RuntimeError("""
Expected %s exception of type "%s".
Got a %s exception with a differnt type:

%s
"""
                    % (str(e_type), e_member,
                        str(type(e)), traceback.format_exc()))

def assertRaises(validate_cb, func, *args, **kwargs):
        (validate_func, validate_args) = validate_cb
        sys.exc_clear()

        e = None
        try:
                func(*args, **kwargs)
        except:
                e_type, e, e_tb = sys.exc_info()
                pass
        validate_func(e, **validate_args)
        return e


class TestLinkedImageName(pkg5unittest.Pkg5TestCase):

        def test_linked_name(self):

                # setup bad linked image names
                bad_name = []
                bad_name.append("too:many:colons")
                bad_name.append("notenoughcolons")
                bad_name.append(":img2")   # no type
                bad_name.append("system:")   # no name
                bad_name.append("badtype:img4")

                good_name = ["system:img1", "zone:img1"]

                for name in bad_name:
                        assertRaises(
                            (apx_verify, {
                                "e_type": apx.LinkedImageException,
                                "e_member": "lin_malformed"}),
                                li.LinkedImageName, name)

                for name in good_name:
                       li.LinkedImageName(name)

        def test_linked_zone_name(self):
                DebugValues["zone_name"] = ["/bin/false"]
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "cmd_failed"}),
                        li.zone._zonename)


class TestApiLinked(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pub1 = "bobcat"
        pub2 = "lolcat"
        pub3 = "pussycat"

        p_all = []
        vers = [
            "@1.2,5.11-145:19700101T000001Z",
            "@1.2,5.11-145:19700101T000000Z", # old time
            "@1.1,5.11-145:19700101T000000Z", # old ver
            "@1.1,5.11-144:19700101T000000Z", # old build
            "@1.0,5.11-144:19700101T000000Z", # oldest
        ]
        p_files1 = [
            "tmp/bar",
            "tmp/baz",
            "tmp/dricon2_da",
            "tmp/dricon_n2m",
        ]

        p_files2 = {
            "tmp/passwd": """\
root:x:0:0::/root:/usr/bin/bash
""",
            "tmp/shadow": """\
root:9EIfTNBp9elws:13817::::::
""",
            "tmp/group":
"""
root::0:
sys::3:root
adm::4:root
""",
            "tmp/license.txt": """
This is a license.
""",
        }

        # generate packages that don't need to be synced
        p_foo1_name_gen = "foo1"
        p_foo1_name = dict()
        for i, v in zip(range(len(vers)), vers):
                p_foo1_name[i] = p_foo1_name_gen + v
                p_data = "open %s\n" % p_foo1_name[i]
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=foo1_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=foo1_baz variant.foo=baz
                    close\n"""
                p_all.append(p_data)

        # generate packages that don't need to be synced
        p_foo2_name_gen = "foo2"
        p_foo2_name = dict()
        for i, v in zip(range(len(vers)), vers):
                p_foo2_name[i] = p_foo2_name_gen + v
                p_data = "open %s\n" % p_foo2_name[i]
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=foo2_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=foo2_baz variant.foo=baz
                    close\n"""
                p_all.append(p_data)

        p_foo_incorp_name_gen = "foo-incorp"
        p_foo_incorp_name = dict()
        for i, v in zip(range(len(vers)), vers):
                p_foo_incorp_name[i] = p_foo_incorp_name_gen + v
                p_data = "open %s\n" % p_foo_incorp_name[i]
                p_data += "add depend type=incorporate fmri=%s\n" % \
                    p_foo1_name[i]
                p_data += "add depend type=incorporate fmri=%s\n" % \
                    p_foo2_name[i]
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    close\n"""
                p_all.append(p_data)

        # generate packages that do need to be synced
        p_sync1_name_gen = "sync1"
        p_sync1_name = dict()
        for i, v in zip(range(len(vers)), vers):
                p_sync1_name[i] = p_sync1_name_gen + v
                p_data = "open %s\n" % p_sync1_name[i]
                p_data += "add depend type=parent fmri=%s" % \
                    pkg.actions.depend.DEPEND_SELF
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=sync1_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=sync1_baz variant.foo=baz
                    close\n"""
                p_all.append(p_data)

        # generate packages that do need to be synced
        p_sync2_name_gen = "sync2"
        p_sync2_name = dict()
        for i, v in zip(range(len(vers)), vers):
                p_sync2_name[i] = p_sync2_name_gen + v
                p_data = "open %s\n" % p_sync2_name[i]
                p_data += "add depend type=parent fmri=%s" % \
                    pkg.actions.depend.DEPEND_SELF
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=sync2_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=sync2_baz variant.foo=baz
                    close\n"""
                p_all.append(p_data)

        # generate packages that do need to be synced
        p_sync3_name_gen = "sync3"
        p_sync3_name = dict()
        for i, v in zip(range(len(vers)), vers):
                p_sync3_name[i] = p_sync3_name_gen + v
                p_data = "open %s\n" % p_sync3_name[i]
                p_data += "add depend type=parent fmri=%s" % \
                    pkg.actions.depend.DEPEND_SELF
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=sync3_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=sync3_baz variant.foo=baz
                    close\n"""
                p_all.append(p_data)

        # generate packages that do need to be synced
        p_sync4_name_gen = "sync4"
        p_sync4_name = dict()
        for i, v in zip(range(len(vers)), vers):
                p_sync4_name[i] = p_sync4_name_gen + v
                p_data = "open %s\n" % p_sync4_name[i]
                p_data += "add depend type=parent fmri=%s" % \
                    pkg.actions.depend.DEPEND_SELF
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=sync4_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=sync4_baz variant.foo=baz
                    close\n"""
                p_all.append(p_data)

        # create a fake zones package
        p_zones_name = "system/zones@0.5.11,5.11-0.169"
        p_data = "open %s\n" % p_zones_name
        p_data += """
            add dir mode=0755 owner=root group=bin path=etc
            close\n"""
        p_all.append(p_data)

        # generate packages that do need to be synced
        p_sync5_name_gen = "sync5"
        p_sync5_name = dict()
        for i, v in zip(range(len(vers)), vers):
                p_sync5_name[i] = p_sync5_name_gen + v
                p_data = "open %s\n" % p_sync5_name[i]
                p_data += "add depend type=parent fmri=%s\n" % \
                    pkg.actions.depend.DEPEND_SELF

                p_data += """
                    add dir path=etc mode=0755 owner=root group=root
                    add file tmp/group path=etc/group mode=0644 owner=root group=sys preserve=true
                    add file tmp/passwd path=etc/passwd mode=0644 owner=root group=sys preserve=true
                    add file tmp/shadow path=etc/shadow mode=0600 owner=root group=sys preserve=true
                    """

                if i != 1:
                        p_data += """
                            close\n"""
                        p_all.append(p_data)
                        continue

                # package 1 should contain one of every action type
                # (we already have a dependency action)
                p_data += """
                    add set name=variant.arch value=i386 value=sparc
                    add dir path=var mode=0755 owner=root group=root
                    add link path=var/run target=../system/volatile
                    add dir mode=0755 owner=root group=root path=system
                    add dir mode=0755 owner=root group=root path=system/volatile
                    add dir path=tmp mode=0755 owner=root group=root
                    add file tmp/dricon2_da path=etc/driver_aliases mode=0644 owner=root group=sys preserve=true
                    add file tmp/dricon_n2m path=etc/name_to_major mode=0644 owner=root group=sys preserve=true
                    add driver name=zigit alias=pci8086,1234
                    add hardlink path=etc/hardlink target=driver_aliases
                    add legacy arch=i386 category=system desc="core software for a specific instruction-set architecture" hotline="Please contact your local service provider" name="Core Solaris, (Usr)" pkg=SUNWcsu variant.arch=i386 vendor="Oracle Corporation" version=11.11,REV=2009.11.11

                    add group groupname=muppets
                    add user username=Kermit group=adm home-dir=/export/home/Kermit
                    add license license="Foo" path=tmp/license.txt must-display=True must-accept=True
                    close\n"""
                p_all.append(p_data)

        def setUp(self):
                self.i_count = 5
                pkg5unittest.ManyDepotTestCase.setUp(self,
                    [self.pub1, self.pub2, self.pub3],
                    image_count=self.i_count)

                # create files that go in packages
                self.make_misc_files(self.p_files1)
                self.make_misc_files(self.p_files2)

                # get repo urls
                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                self.rurl3 = self.dcs[3].get_repo_url()

                # populate repositories
                self.pkgsend_bulk(self.rurl1, self.p_all)

                # setup image names and paths
                self.i_path = []
                self.i_lin = []
                self.i_lin2index = {}
                for i in range(self.i_count):
                        lin = li.LinkedImageName("system:img%d" % i)
                        self.i_lin.insert(i, lin)
                        self.i_lin2index[lin] = i
                        self.set_image(i)
                        self.i_path.insert(i, self.img_path())
                self.set_image(0)

        def _cat_update(self):
                global p_update_index
                p_update_name = "update@%d.0,5.11-143:19700101T000000Z" % \
                    p_update_index
                p_update_index += 1

                p_data = "open %s\n" % p_update_name
                p_data += """
                    close\n"""

                self.pkgsend_bulk(self.rurl1, [p_data])

        def _list_inst_packages(self, apio):
                pkg_list = apio.get_pkg_list(api.ImageInterface.LIST_INSTALLED)
                return set(sorted([
                        "pkg://%s/%s@%s" % (pfmri[0], pfmri[1], pfmri[2])
                        for pfmri, summ, cats, states, attrs in pkg_list
                ]))

        def _list_all_packages(self, apio):
                pkg_list = apio.get_pkg_list(api.ImageInterface.LIST_ALL)
                return set(sorted([
                        "pkg://%s/%s@%s" % (pfmri[0], pfmri[1], pfmri[2])
                        for pfmri, summ, cats, states, attrs in pkg_list
                ]))

        # utility functions for use by test cases
        def _imgs_create(self, limit, variants=None, **ic_opts):
                if variants == None:
                        variants = {
                            "variant.foo": "bar",
                            "variant.opensolaris.zone": "nonglobal",
                        }

                rv = []

                for i in range(0, limit):
                        self.set_image(i)
                        api_obj = self.image_create(self.rurl1,
                            prefix=self.pub1, variants=variants, **ic_opts)
                        rv.insert(i, api_obj)

                for i in range(limit, self.i_count):
                        self.set_image(i)
                        self.image_destroy()

                self.set_image(0)
                self.api_objs = rv
                return rv

        def _parent_attach(self, i, cl, **args):
                assert i not in cl

                for c in cl:
                        self._api_attach(self.api_objs[c],
                            lin=self.i_lin[i], li_path=self.i_path[i], **args)

        def _children_attach(self, i, cl, rv=None, rvdict=None, **args):
                assert i not in cl
                assert rvdict == None or type(rvdict) == dict
                assert rv == None or rvdict == None

                if rv == None:
                        rv = EXIT_OK
                if rvdict == None:
                        rvdict = {}
                        for c in cl:
                                rvdict[c] = rv
                assert (set(rvdict) | set(cl)) == set(cl)

                # attach each child to parent
                for c in cl:
                        rv = rvdict.get(c, EXIT_OK)
                        (c_rv, c_err, p_dict) = \
                            self.api_objs[i].attach_linked_child(
                            lin=self.i_lin[c], li_path=self.i_path[c], **args)
                        self.assertEqual(rv, c_rv, """
Child attach returned unexpected error code.  Expected %d, got: %d.
Error output:
%s""" %
                                   (rv, c_rv, str(c_err)))
                        self.api_objs[c].reset()

        def _children_op(self, i, cl, op, rv=None, rvdict=None, **args):
                assert i not in cl
                assert type(op) == str
                assert rv == None or type(rv) == int
                assert rvdict == None or type(rvdict) == dict
                assert rv == None or rvdict == None

                if rv == None:
                        rv = EXIT_OK
                if rvdict == None:
                        rvdict = {}
                        for c in cl:
                                rvdict[c] = rv

                # sync each child from parent
                li_list = [self.i_lin[c] for c in cl]

                # get a pointer to the function we're invoking
                func = getattr(self.api_objs[i], op)
                c_rvdict = func(li_list=li_list, **args)

                # check that the actual return values match up with expected
                # return values in rvdict
                for c_lin, (c_rv, c_err, p_dict) in c_rvdict.items():
                        rv = rvdict.get(self.i_lin2index[c_lin], EXIT_OK)
                        self.assertEqual(c_rv, rv)

                if rvdict:
                        # make sure that we actually got a return value for
                        # each image that we're expecting a return value from
                        c_i = [self.i_lin2index[c_lin] for c_lin in c_rvdict]
                        self.assertEqual(sorted(c_i), sorted(rvdict))

        def _verify_pkg(self, api_objs, i, pfmri):
                apio = api_objs[i]
                progtrack = progress.NullProgressTracker()

                for act, err, warn, pinfo in apio.img.verify(pfmri, progtrack,
                    verbose=True):
                        self.assertEqual(len(err), 0, """
unexpected verification error for pkg: %s
action: %s
error: %s
warning: %s
pinfo: %s""" %
                            (pfmri, str(act), str(err), str(warn), str(pinfo)))


        def assertKnownPkgCount(self, api_objs, i, pl_init, offset=0):
                apio = api_objs[i]
                pl = self._list_all_packages(apio)

                pl_removed = pl_init - pl
                pl_added = pl - pl_init

                self.assertEqual(len(pl_init), len(pl) - offset, """
unexpected packages known in image[%d]: %s
packages removed:
    %s
packages added:
    %s
packages known:
    %s""" %
                    (i, self.i_path[i], "\n    ".join(pl_removed),
                    "\n    ".join(pl_added), "\n    ".join(pl)))

        def test_attach_err_link_to_self(self):
                api_objs = self._imgs_create(1)

                lin = self.i_lin[0]
                path = self.i_path[0]

                # Attach p2c, link to ourselves
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "link_to_self"}),
                    api_objs[0].attach_linked_child, lin=lin, li_path=path)

                # Attach c2p, link to ourselves
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "link_to_self"}),
                    lambda *args, **kwargs: list(
                        api_objs[0].gen_plan_attach(*args, **kwargs)),
                        lin=lin, li_path=path)

        def test_attach_err_liveroot_as_child(self):
                api_objs = self._imgs_create(2)

                lin = self.i_lin[1]
                path = self.i_path[1]

                #
                # The test harness will clear all DebugValues variables for
                # us after each test run.
                #

                # Attach p2c, child is liveroot
                DebugValues["simulate_live_root"] = self.i_path[1]
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "attach_root_as_child"}),
                    api_objs[0].attach_linked_child,
                        lin=lin, li_path=path)

                # Attach c2p, child is liveroot
                # We also need to temporarily disable PKG_NO_LIVE_ROOT.
                del os.environ["PKG_NO_LIVE_ROOT"]
                DebugValues["simulate_live_root"] = self.i_path[0]
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "attach_root_as_child"}),
                    lambda *args, **kwargs: list(
                        api_objs[0].gen_plan_attach(*args, **kwargs)),
                        lin=lin, li_path=path)

                os.environ["PKG_NO_LIVE_ROOT"] = "1"
                del DebugValues["simulate_live_root"]

        def test_linked_p2c_recurse_flags_1_no_refresh_via_attach(self):
                """test no-refresh option when no catalog is present"""

                # create images but don't cache any catalogs
                api_objs = self._imgs_create(3, refresh_allowed=False)

                # Attach p2c, 0 -> 1
                api_objs[0].attach_linked_child(
                    lin=self.i_lin[1], li_path=self.i_path[1],
                    refresh_catalogs=False)

                # Attach c2p, 2 -> 0
                self._api_attach(api_objs[2],
                    lin=self.i_lin[2], li_path=self.i_path[0],
                    refresh_catalogs=False)

                for i in range(3):
                        api_objs[i].reset()

                # make sure the parent didn't refresh
                # the parent doesn't know about any packages
                # the child only knows about the constraints package
                for i in range(3):
                        self.assertKnownPkgCount(api_objs, i, set())

        def test_linked_p2c_recurse_flags_1_no_refresh_via_sync(self):
                """test no-refresh option when no catalog is present"""

                # create images but don't cache any catalogs
                api_objs = self._imgs_create(3, refresh_allowed=False)

                # Attach p2c, 0 -> 1
                api_objs[0].attach_linked_child(
                    lin=self.i_lin[1], li_path=self.i_path[1],
                    refresh_catalogs=False, li_md_only=True)

                # Attach c2p, 2 -> 0
                self._api_attach(api_objs[2],
                    lin=self.i_lin[2], li_path=self.i_path[0],
                    refresh_catalogs=False, li_md_only=True)

                for i in range(3):
                        api_objs[i].reset()

                # Sync 1
                api_objs[0].sync_linked_children(li_list=[],
                    refresh_catalogs=False)

                # Sync 2
                self._api_sync(api_objs[2],
                    refresh_catalogs=False)

                for i in range(3):
                        api_objs[i].reset()

                # make sure the parent didn't refresh
                # the parent doesn't know about any packages
                # the child only knows about the constraints package
                for i in range(3):
                        self.assertKnownPkgCount(api_objs, i, set())

        def test_linked_p2c_recurse_flags_2_no_refresh_via_attach(self):
                """test no-refresh option when catalog is updated"""

                # create images
                api_objs = self._imgs_create(3)

                # get a list of all known packages
                pl_init = dict()
                for i in range(3):
                        pl_init[i] = self._list_all_packages(api_objs[i])

                # update the catalog with a new package
                self._cat_update()

                # Attach p2c, 0 -> 1
                api_objs[0].attach_linked_child(
                    lin=self.i_lin[1], li_path=self.i_path[1],
                    refresh_catalogs=False)

                # Attach c2p, 2 -> 0
                self._api_attach(api_objs[2],
                    lin=self.i_lin[2], li_path=self.i_path[0],
                    refresh_catalogs=False)

                for i in range(3):
                        api_objs[i].reset()

                # make sure the parent didn't refresh
                # the parent doesn't know about any packages
                # the child only knows about the constraints package
                for i in range(3):
                        self.assertKnownPkgCount(api_objs, i, pl_init[i])

                return (api_objs, pl_init)

        def test_linked_p2c_recurse_flags_2_no_refresh_via_other(self):
                """test no-refresh option when catalog is updated"""

                # don't need to test uninstall and change-varcets since
                # they don't accept the refresh_catalogs option

                # create images
                api_objs = self._imgs_create(3)

                # install different synced packages into each image
                for i in [0, 1, 2]:
                        self._api_install(api_objs[i],
                            [self.p_sync1_name[i + 2]])

                # Attach p2c, 0 -> 1
                api_objs[0].attach_linked_child(
                    lin=self.i_lin[1], li_path=self.i_path[1],
                    li_md_only=True)

                # Attach c2p, 2 -> 0
                self._api_attach(api_objs[2],
                    lin=self.i_lin[2], li_path=self.i_path[0],
                    li_md_only=True)

                for i in range(3):
                        api_objs[i].reset()

                # get a list of all known packages
                pl_init = dict()
                for i in range(3):
                        pl_init[i] = self._list_all_packages(api_objs[i])

                # update the catalog with a new package
                self._cat_update()

                # Sync 1
                api_objs[0].sync_linked_children(li_list=[],
                    refresh_catalogs=False)

                # Sync 2
                self._api_sync(api_objs[2],
                    refresh_catalogs=False)

                for i in range(3):
                        api_objs[i].reset()

                # make sure all the images are unaware of new packages
                for i in range(3):
                        self.assertKnownPkgCount(api_objs, i, pl_init[i])

                # Install newer package in 0 and 1
                self._api_install(api_objs[0], [self.p_sync1_name[1]],
                    refresh_catalogs=False)

                # Install newer package in 2
                self._api_install(api_objs[2], [self.p_sync1_name[1]],
                    refresh_catalogs=False)

                for i in range(3):
                        api_objs[i].reset()

                # make sure all the images are unaware of new packages
                for i in range(3):
                        self.assertKnownPkgCount(api_objs, i, pl_init[i])

                # Update to newest package in 0 and 1
                self._api_update(api_objs[0], refresh_catalogs=False)

                # Update to newest package in 2
                self._api_update(api_objs[2], refresh_catalogs=False)

                for i in range(3):
                        api_objs[i].reset()

                # make sure all the images are unaware of new packages
                for i in range(3):
                        self.assertKnownPkgCount(api_objs, i, pl_init[i])

                # change variant in 0
                self._api_change_varcets(api_objs[0],
                    variants={"variant.foo": "baz"},
                    refresh_catalogs=False)

                # change variant in 2
                self._api_change_varcets(api_objs[2],
                    variants={"variant.foo": "baz"},
                    refresh_catalogs=False)

                for i in range(3):
                        api_objs[i].reset()

                # make sure all the images are unaware of new packages
                for i in range(3):
                        self.assertKnownPkgCount(api_objs, i, pl_init[i])

        def test_err_toxic_pkg(self):
                # create images
                api_objs = self._imgs_create(2)

                # install a synced package into 1
                self._api_install(api_objs[1], [self.p_sync1_name[1]])

                # Attach c2p, 1 -> 0
                self._api_attach(api_objs[1],
                    lin=self.i_lin[1], li_path=self.i_path[0],
                    li_md_only=True)

                # try to modify image.
                # no version of synced package is in the parent
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_update(*args, **kwargs)))

                assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_sync(*args, **kwargs)))

                assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_change_varcets(*args, **kwargs)),
                        variants={"variant.foo": "baz"})

                assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_install(*args, **kwargs)),
                        [self.p_sync1_name[0]])

                # install a synced package into 1
                self._api_install(api_objs[0], [self.p_sync1_name[2]],
                    li_ignore=[])

                # try to modify image.
                # an older version of synced package is in the parent
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_update(*args, **kwargs)))

                assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_sync(*args, **kwargs)))

                assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_change_varcets(*args,
                            **kwargs)),
                        variants={"variant.foo": "baz"})

                assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_install(*args, **kwargs)),
                        [self.p_sync1_name[0]])

        def test_err_pubcheck(self):
                """Verify the linked image publisher sync check."""

                def configure_pubs1(self):
                        """change the publishers config in our images."""

                        # add pub 2 to image 0
                        self.api_objs[0].add_publisher(self.po2)

                        # add pubs 2 and 3 to image 1
                        self.api_objs[1].add_publisher(self.po2)
                        self.api_objs[1].add_publisher(self.po3)

                        # leave image 2 alone

                        # add pub 2 to image 3 and reverse the search order
                        self.api_objs[3].add_publisher(self.po2,
                            search_before=self.po1)

                        # add pub 2 to image 4 as non-sticky
                        self.api_objs[4].add_publisher(self.po4)

                # setup publisher objects
                repouri = publisher.RepositoryURI(self.rurl1)
                repo1 = publisher.Repository(origins=[repouri])
                self.po1 = publisher.Publisher(self.pub1, repository=repo1)

                repouri = publisher.RepositoryURI(self.rurl2)
                repo2 = publisher.Repository(origins=[repouri])
                self.po2 = publisher.Publisher(self.pub2, repository=repo2)

                repouri = publisher.RepositoryURI(self.rurl3)
                repo3 = publisher.Repository(origins=[repouri])
                self.po3 = publisher.Publisher(self.pub3, repository=repo3)

                self.po4 = publisher.Publisher(self.pub2, repository=repo2)
                self.po4.sticky = False

                # create images and update publishers
                api_objs = self._imgs_create(5)
                configure_pubs1(self)

                # Attach p2c, 0 -> 1 (sync ok)
                api_objs[0].attach_linked_child(
                    lin=self.i_lin[1], li_path=self.i_path[1])
                api_objs[0].detach_linked_children(li_list=[self.i_lin[1]])
                api_objs[1].reset()

                # Attach p2c, 0 -> 2 (sync error)
                (rv, err, p_dict) = api_objs[0].attach_linked_child(
                    lin=self.i_lin[2], li_path=self.i_path[2])
                self.assertEqual(rv, EXIT_OOPS)

                # Attach p2c, 0 -> 3 (sync error)
                (rv, err, p_dict) = api_objs[0].attach_linked_child(
                    lin=self.i_lin[3], li_path=self.i_path[3])
                self.assertEqual(rv, EXIT_OOPS)

                # Attach p2c, 0 -> 4 (sync error)
                (rv, err, p_dict) = api_objs[0].attach_linked_child(
                    lin=self.i_lin[4], li_path=self.i_path[4])
                self.assertEqual(rv, EXIT_OOPS)

                # Attach c2p, 1 -> 0 (sync ok)
                for pd in api_objs[1].gen_plan_attach(
                    lin=self.i_lin[0], li_path=self.i_path[0],
                    noexecute=True):
                        continue

                # Attach c2p, [2, 3, 4] -> 0 (sync error)
                for c in [2, 3, 4]:
                        assertRaises(
                            (apx_verify, {
                                "e_type": apx.PlanCreationException,
                                "e_member": "linked_pub_error"}),
                            lambda *args, **kwargs: list(
                                api_objs[c].gen_plan_attach(*args, **kwargs)),
                                lin=self.i_lin[0], li_path=self.i_path[0],
                                noexecute=True)

                # create images, attach one child (p2c), and update publishers
                api_objs = self._imgs_create(5)
                self._children_attach(0, [2])
                configure_pubs1(self)

                # test recursive parent operations
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "pkg_op_failed"}),
                    lambda *args, **kwargs: list(
                        api_objs[0].gen_plan_install(*args, **kwargs)),
                        [self.p_sync1_name[0]])
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "pkg_op_failed"}),
                    lambda *args, **kwargs: list(
                        api_objs[0].gen_plan_update(*args, **kwargs)))
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "pkg_op_failed"}),
                    lambda *args, **kwargs: list(
                        api_objs[0].gen_plan_change_varcets(*args, **kwargs)),
                        variants={"variant.foo": "baz"})
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "pkg_op_failed"}),
                    lambda *args, **kwargs: list(
                        api_objs[0].gen_plan_uninstall(*args, **kwargs)),
                        [self.p_sync1_name_gen])

                # create images, attach children (p2c), and update publishers
                api_objs = self._imgs_create(5)
                self._children_attach(0, [1, 2, 3, 4])
                configure_pubs1(self)

                # test recursive parent operations
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "lix_bundle"}),
                    lambda *args, **kwargs: list(
                        api_objs[0].gen_plan_install(*args, **kwargs)),
                        [self.p_sync1_name[0]])
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "lix_bundle"}),
                    lambda *args, **kwargs: list(
                        api_objs[0].gen_plan_update(*args, **kwargs)))
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "lix_bundle"}),
                    lambda *args, **kwargs: list(
                        api_objs[0].gen_plan_change_varcets(*args, **kwargs)),
                        variants={"variant.foo": "baz"})
                assertRaises(
                    (apx_verify, {
                        "e_type": apx.LinkedImageException,
                        "e_member": "lix_bundle"}),
                    lambda *args, **kwargs: list(
                        api_objs[0].gen_plan_uninstall(*args, **kwargs)),
                        [self.p_sync1_name_gen])

                # test operations on child nodes
                rvdict = {1: EXIT_NOP, 2: EXIT_OOPS, 3: EXIT_OOPS,
                    4: EXIT_OOPS}
                self._children_op(0, [], "sync_linked_children",
                    rvdict=rvdict)
                self._children_op(0, [1, 2, 3, 4], "sync_linked_children",
                    rvdict=rvdict)

                # no pub check during detach
                self._children_op(0, [], "detach_linked_children")

                # create images, attach children (c2p), and update publishers
                api_objs = self._imgs_create(5)
                self._parent_attach(0, [1, 2, 3, 4])
                configure_pubs1(self)

                # test sync
                self._api_sync(api_objs[1])
                for c in [2, 3, 4]:
                        assertRaises(
                            (apx_verify, {
                                "e_type": apx.PlanCreationException,
                                "e_member": "linked_pub_error"}),
                            lambda *args, **kwargs: list(
                                api_objs[c].gen_plan_sync(*args, **kwargs)))

                # test install
                self._api_install(api_objs[1], [self.p_foo1_name[1]])
                for c in [2, 3, 4]:
                        assertRaises(
                            (apx_verify, {
                                "e_type": apx.PlanCreationException,
                                "e_member": "linked_pub_error"}),
                            lambda *args, **kwargs: list(
                                api_objs[c].gen_plan_install(*args, **kwargs)),
                                [self.p_foo1_name[1]])

                # test update
                self._api_update(api_objs[1])
                for c in [2, 3, 4]:
                        assertRaises(
                            (apx_verify, {
                                "e_type": apx.PlanCreationException,
                                "e_member": "linked_pub_error"}),
                            lambda *args, **kwargs: list(
                                api_objs[c].gen_plan_update(*args, **kwargs)))

                # test change varcets
                self._api_change_varcets(api_objs[1],
                    variants={"variant.foo": "baz"})
                for c in [2, 3, 4]:
                        assertRaises(
                            (apx_verify, {
                                "e_type": apx.PlanCreationException,
                                "e_member": "linked_pub_error"}),
                            lambda *args, **kwargs: list(
                                api_objs[c].gen_plan_change_varcets(*args,
                                    **kwargs)),
                                variants={"variant.foo": "baz"})

                # test uninstall
                self._api_uninstall(api_objs[1], [self.p_foo1_name_gen])
                for c in [2, 3, 4]:
                        assertRaises(
                            (apx_verify, {
                                "e_type": apx.PlanCreationException,
                                "e_member": "linked_pub_error"}),
                            lambda *args, **kwargs: list(
                                api_objs[c].gen_plan_uninstall(*args,
                                    **kwargs)),
                                [self.p_foo1_name_gen])

                # no pub check during detach
                for c in [1, 2, 3, 4]:
                        self._api_detach(api_objs[c])

        def test_update_recursion(self):
                """Verify that update is recursive, but update with arguments
                is not."""

                api_objs = self._imgs_create(2)

                # install packages that don't need to be synced.
                self._api_install(api_objs[0], [self.p_foo1_name[2]])
                self._api_install(api_objs[1], [self.p_foo1_name[2]])

                # attach our images
                self._children_attach(0, [1])

                # update a specific package
                self._api_update(api_objs[0], pkgs_update=[self.p_foo1_name[1]])

                # the parent recursed into the child so make sure to reset the
                # child api object
                api_objs[1].reset()

                # verify that the child image hasn't changed
                pkg_list = list(api_objs[1].get_pkg_list(
                    api.ImageInterface.LIST_INSTALLED))
                self.assertEqual(len(pkg_list), 1)
                pfmri, summ, cats, states, attrs = pkg_list[0]
                pkg_installed = "%s@%s" % (pfmri[1], pfmri[2])
                self.assertEqual(pkg_installed, self.p_foo1_name[2])

                # update all packages
                self._api_update(api_objs[0])

                # the parent recursed into the child so make sure to reset the
                # child api object
                api_objs[1].reset()

                # verify that the child image was updated as well
                pkg_list = list(api_objs[1].get_pkg_list(
                    api.ImageInterface.LIST_INSTALLED))
                self.assertEqual(len(pkg_list), 1)
                pfmri, summ, cats, states, attrs = pkg_list[0]
                pkg_installed = "%s@%s" % (pfmri[1], pfmri[2])
                self.assertEqual(pkg_installed, self.p_foo1_name[0])


        def test_solver_err_aggregation(self):
                """Verify that when the solver reports errors on packages that
                can't be installed, those errors include information about
                all the proposed packages (and not a subset of the proposed
                packages)."""

                api_objs = self._imgs_create(2)
                self._parent_attach(0, [1])

                # since we're check the default output of the solver, disable
                # the collection of extended solver dependency errors.
                if "plan" in DebugValues:
                        del DebugValues["plan"]

                # install synced packages in the parent
                self._api_install(api_objs[0], [
                    self.p_sync3_name[1], self.p_sync4_name[1]])

                # install synced packages and an incorporation which
                # constrains the foo* packages in the child
                self._api_install(api_objs[1], [self.p_foo_incorp_name[1],
                    self.p_sync3_name[1], self.p_sync4_name[1]])

                # try to install packages that can't be installed
                e = assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_install(*args, **kwargs)),
                        [self.p_foo1_name[0], self.p_foo2_name[0]])

                # make sure the error message mentions both packages.
                substring_verify(str(e), self.p_foo1_name[0])
                substring_verify(str(e), self.p_foo2_name[0])

                # try to install packages with missing parent dependencies
                e = assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_install(*args, **kwargs)),
                        [self.p_sync1_name[0], self.p_sync2_name[0]])

                # make sure the error message mentions both packages.
                substring_verify(str(e), self.p_sync1_name[0])
                substring_verify(str(e), self.p_sync2_name[0])

                # uninstall synced packages in the parent
                self._api_uninstall(api_objs[0], [
                    self.p_sync3_name[1], self.p_sync4_name[1]])

                # try to install a newer version of the incorporation
                e = assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_install(*args, **kwargs)),
                        [self.p_foo_incorp_name[0]])

                # make sure the error message mentions both synced packages.
                substring_verify(str(e), self.p_sync3_name[1])
                substring_verify(str(e), self.p_sync4_name[1])

                # try to update
                e = assertRaises(
                    (apx_verify, {
                        "e_type": apx.PlanCreationException,
                        "e_member": "no_version"}),
                    lambda *args, **kwargs: list(
                        api_objs[1].gen_plan_update(*args, **kwargs)))

                # make sure the error message mentions both synced packages.
                substring_verify(str(e), self.p_sync3_name[1])
                substring_verify(str(e), self.p_sync4_name[1])


        def test_sync_nosolver(self):
                """Verify that the solver is not invoked when syncing in-sync
                images."""

                api_objs = self._imgs_create(2)

                # install a synced package into the images
                self._api_install(api_objs[0], [self.p_sync1_name[1]])
                self._api_install(api_objs[1], [self.p_sync1_name[1]])

                # install a random package into the image
                self._api_install(api_objs[1], [self.p_foo1_name[1]])

                # link the images
                self._parent_attach(0, [1])

                # raise an exception of the solver is invoked
                DebugValues["no_solver"] = 1

                # the child is in sync and we're not rejecting an installed
                # package, so a sync shound not invoke the solver.
                self._api_sync(api_objs[1])
                self._api_sync(api_objs[1], reject_list=[self.p_foo2_name[1]])

                # the child is in sync, but we're rejecting an installed
                # package, so a sync must invoke the solver.
                assertRaises(
                    (apx_verify, {"e_type": RuntimeError}),
                    self._api_sync, api_objs[1],
                    reject_list=[self.p_sync1_name[1]])
                assertRaises(
                    (apx_verify, {"e_type": RuntimeError}),
                    self._api_sync, api_objs[1],
                    reject_list=[self.p_sync1_name[1], self.p_foo2_name[1]])

        def test_corrupt_zone_metadata(self):
                """Verify that some corrupt zone metadata states are
                handled reasonably."""

                def __do_tests(li_count):
                        # if /etc/zones doesn't exists we don't have zones
                        # children and we don't run the zone commands.
                        api_objs[0].reset()
                        linked = api_objs[0].list_linked()
                        assert len(linked) == li_count

                        #
                        # an empty /etc/zones directory will cause the zone
                        # commands to fail which will cause linked image
                        # operations to fail.
                        #
                        os.mkdir(os.path.join(self.img_path(), "etc/zones"),
                            0755)
                        api_objs[0].reset()
                        assertRaises(
                            (apx_verify, {
                                "e_type": apx.LinkedImageException,
                                "e_member": "cmd_failed"}),
                            api_objs[0].list_linked)

                        # ignoring all linked children should allow the
                        # operation to succeed.
                        linked = api_objs[0].list_linked(li_ignore=[])
                        assert len(linked) == 0

                        # reset the image
                        os.rmdir(os.path.join(self.img_path(), "etc/zones"))

                #
                # create a global zone image and install a fake zones package
                # within the image.  this makes the linked image zones plugin
                # think it's dealing with an image that could have zone
                # children so it will invoke the zone tools on the image to
                # try and discover zones installed in the image.
                #
                api_objs = self._imgs_create(2)
                self._api_change_varcets(api_objs[0],
                    variants={"variant.opensolaris.zone": "global"})
                self._api_install(api_objs[0], [self.p_zones_name])

                # run tests
                __do_tests(0)

                # link a system image child to the image and run tests
                self._children_attach(0, [1])
                __do_tests(2)

                # remove linked image metadata from the parent and run tests
                shutil.rmtree(os.path.join(self.img_path(), "var/pkg/linked"))
                __do_tests(2)

        def test_attach_reject(self):
                """Verify that we can reject packages during attach."""

                api_objs = self._imgs_create(3)

                # install a random package into the image
                pkg = self.p_foo1_name_gen
                self._api_install(api_objs[1], [pkg])
                self._api_install(api_objs[2], [pkg])

                # attach c2p
                assert len(self._list_inst_packages(api_objs[1])) == 1
                self._parent_attach(0, [1], reject_list=[pkg])
                assert len(self._list_inst_packages(api_objs[1])) == 0

                # attach p2c
                assert len(self._list_inst_packages(api_objs[2])) == 1
                self._children_attach(0, [2], reject_list=[pkg])
                assert len(self._list_inst_packages(api_objs[2])) == 0

        def test_action_serialization(self):
                """Verify that all actions can be serialized to disk and
                reloaded successfully when updating a child image."""

                api_objs = self._imgs_create(2)

                # install an empty synced package into the images
                self._api_install(api_objs[0], [self.p_sync5_name[2]])
                self._api_install(api_objs[1], [self.p_sync5_name[2]])

                # link the images
                self._children_attach(0, [1])

                # update the synced package in the parent so it delivers some
                # content.  this will cause us to implicitly recurse into the
                # child and serialize the child update plans to disk, which
                # should serialize out all the new actions to disk (there by
                # verifying that they get serialized and re-loaded correctly.)
                self._api_install(api_objs[0], [self.p_sync5_name[1]],
                    show_licenses=True, accept_licenses=True)

                # update the synced package in the parent again so it delivers
                # no content.
                self._api_install(api_objs[0], [self.p_sync5_name[0]])

if __name__ == "__main__":
        unittest.main()
