#!/usr/bin/python
# -*- coding: utf-8 -*-
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
# Copyright (c) 2011, 2025, Oracle and/or its affiliates.
#

from . import testutils
if __name__ == "__main__":
    testutils.setup_environment("../../../proto")
import pkg5unittest

import operator
import os
import itertools
import re
import shutil
import tempfile
import unittest
import sys

import pkg.actions
import pkg.client.image as image
import pkg.fmri as fmri

from pkg.client.pkgdefs import *


class TestPkgLinked(pkg5unittest.ManyDepotTestCase):
    # Only start/stop the depot once (instead of for every test)
    persistent_setup = True

    p_all = []
    p_sync1 = []
    p_foo1 = []
    p_vers = [
        "@1.2,5.11-145:19700101T000001Z",
        "@1.2,5.11-145:19700101T000000Z", # old time
        "@1.1,5.11-145:19700101T000000Z", # old ver
        "@1.1,5.11-144:19700101T000000Z", # old build
        "@1.0,5.11-144:19700101T000000Z", # oldest
    ]
    p_files = [
        "tmp/bar",
        "tmp/baz",
        "tmp/copyright",
    ]

    # generate packages that don't need to be synced
    pkgs = ["foo1" + ver for ver in p_vers]
    p_foo1_name = dict(zip(range(len(pkgs)), pkgs))
    for i in p_foo1_name:
        p_data = "open {0}\n".format(p_foo1_name[i])
        p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=foo_bär variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=foo_bäz variant.foo=baz
                    close\n"""
        p_foo1.append(p_data)

    pkgs = ["foo2" + ver for ver in p_vers]
    p_foo2_name = dict(zip(range(len(pkgs)), pkgs))
    for i in p_foo2_name:
        p_data = "open {0}\n".format(p_foo2_name[i])
        p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=foo_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=foo_baz variant.foo=baz
                    close\n"""
        p_all.append(p_data)

    # generate packages that do need to be synced
    pkgs = ["sync1" + ver for ver in p_vers]
    p_sync1_name = dict(zip(range(len(pkgs)), pkgs))
    for i in p_sync1_name:
        p_data = "open {0}\n".format(p_sync1_name[i])
        p_data += "add depend type=parent fmri={0}".format(
            pkg.actions.depend.DEPEND_SELF)
        p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=sync1_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=sync1_baz variant.foo=baz
                    add license tmp/copyright license=copyright_⌘⛷༂
                    close\n"""
        p_sync1.append(p_data)

    # generate packages that do need to be synced
    pkgs = ["sync2" + ver for ver in p_vers]
    p_sync2_name = dict(zip(range(len(pkgs)), pkgs))
    for i in p_sync2_name:
        p_data = "open {0}\n".format(p_sync2_name[i])
        p_data += "add depend type=parent fmri={0}".format(
            pkg.actions.depend.DEPEND_SELF)
        p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=sync2_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=sync2_baz variant.foo=baz
                    close\n"""
        p_all.append(p_data)

    group_pkgs = """
            open osnet-incorporation@0.5.11-0.151.0.1
            add set name=pkg.depend.install-hold value=core-os.osnet
            add depend fmri=ipfilter@0.5.11-0.151.0.1 type=incorporate
            close
            open osnet-incorporation@0.5.11-0.175.3.19.0.1.0
            add set name=pkg.depend.install-hold value=core-os.osnet
            add depend fmri=feature/package/dependency/self type=parent variant.opensolaris.zone=nonglobal
            add depend fmri=ipfilter@0.5.11,5.11-0.175.3.18.0.3.0 type=incorporate
            close
            open osnet-incorporation@0.5.11-0.175.3.20.0.0.0
            add set name=pkg.depend.install-hold value=core-os.osnet
            add depend fmri=feature/package/dependency/self type=parent variant.opensolaris.zone=nonglobal
            add depend fmri=ipfilter@0.5.11,5.11-0.175.3.18.0.3.0 type=incorporate
            close
            open ipfilter@0.5.11-0.151.0.1
            close
            open ipfilter@0.5.11,5.11-0.175.3.18.0.3.0
            add depend fmri=feature/package/dependency/self type=parent variant.opensolaris.zone=nonglobal
            close
            open solaris-small-server@0.5.11,5.11-0.175.3.11.0.4.0
            add depend fmri=ipfilter type=group
            close
        """

    def setUp(self):
        self.i_count = 5
        pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
            image_count=self.i_count)

        # create files that go in packages
        self.make_misc_files(self.p_files)

        # get repo url
        self.rurl1 = self.dcs[1].get_repo_url()

        # populate repository
        self.pkgsend_bulk(self.rurl1, self.p_all)
        self.s1_list = self.pkgsend_bulk(self.rurl1, self.p_sync1)
        self.foo1_list = self.pkgsend_bulk(self.rurl1, self.p_foo1)
        self.pkgsend_bulk(self.rurl1, self.group_pkgs)

        # setup image names and paths
        self.i_name = []
        self.i_path = []
        self.i_api = []
        self.i_api_reset = []
        for i in range(self.i_count):
            name = "system:img{0:d}".format(i)
            self.i_name.insert(i, name)
            self.i_path.insert(i, self.img_path(i))

    def __img_api_reset(self, i):
        """__img_api_reset() - reset the api object associated with an
        image if that object has been updated via a pkg(1) cli
        invocation."""

        if self.i_api_reset[i]:
            self.i_api[i].reset()
            self.i_api_reset[i] = False

    def __img_children_names(self, i):
        """__img_children_names() - find the children of an image and
        return their names"""

        self.__img_api_reset(i)
        return set([
                str(name)
                for name, rel, path in self.i_api[i].list_linked()
                if rel == "child"
        ])

    def __img_has_parent(self, i):
        """__img_has_parent() - check if an image has a parent"""

        self.__img_api_reset(i)
        return self.i_api[i].ischild()

    # public verification functions for use by test cases.
    def _v_has_children(self, i, cl):
        assert i not in cl

        cl_found = self.__img_children_names(i)
        cl_expected = set([self.i_name[j] for j in cl])
        self.assertEqual(cl_found, cl_expected,
            "error: image has unexpected children\n"
            "image: {0:d}, {1}, {2}\n"
            "expected children: {3}\n"
            "found children: {4}\n".format(
            i, self.i_name[i], self.i_path[i],
            str(cl_expected),
            str(cl_found)))

    def _v_no_children(self, il):
        for i in il:
            # make sure the we don't have any children
            cl_found = self.__img_children_names(i)
            self.assertEqual(set(), cl_found,
               "error: image has children\n"
               "image: {0:d}, {1}, {2}\n"
               "found children: {3}\n".format(
               i, self.i_name[i], self.i_path[i],
               str(cl_found)))

    def _v_has_parent(self, il):
        # make sure a child has a parent
        for i in il:
            self.assertEqual(True, self.__img_has_parent(i),
               "error: image has no parent\n"
               "image: {0:d}, {1}, {2}\n".format(
               i, self.i_name[i], self.i_path[i]))

    def _v_no_parent(self, il):
        for i in il:
            self.assertEqual(False, self.__img_has_parent(i),
               "error: image has a parent\n"
               "image: {0:d}, {1}, {2}\n".format(
               i, self.i_name[i], self.i_path[i]))

    def _v_not_linked(self, il):
        self._v_no_parent(il)
        self._v_no_children(il)

    # utility functions for use by test cases
    def _imgs_create(self, limit):
        variants = {
            "variant.foo": "bar",
            "variant.opensolaris.zone": "nonglobal",
        }

        for i in range(0, limit):
            self.set_image(i)
            self.i_api.insert(i, self.image_create(self.rurl1,
                variants=variants, destroy=True))
            self.i_api_reset.insert(i, False)

        del self.i_api[limit:]
        del self.i_api_reset[limit:]
        for i in range(limit, self.i_count):
            self.set_image(i)
            self.image_destroy()

        self.set_image(0)

    def _ccmd(self, args, rv=0):
        """Run a 'C' (or other non-python) command."""
        assert type(args) == str
        # Ensure 'coverage' is turned off-- it won't work.
        self.cmdline_run("{0}".format(args), exit=rv, coverage=False)

    def _pkg(self, il, cmd, args=None, rv=None, rvdict=None,
        output_cb=None, env_arg=None):
        assert type(il) == list
        assert type(cmd) == str
        assert args is None or type(args) == str
        assert rv is None or type(rv) == int
        assert rvdict is None or type(rvdict) == dict
        assert rv is None or rvdict is None

        if rv is None:
            rv = EXIT_OK
        if rvdict is None:
            rvdict = {}
            for i in il:
                rvdict[i] = rv
        assert (set(rvdict) | set(il)) == set(il)

        if args is None:
            args = ""

        # we're updating one or more images, so make sure to reset all
        # our api instances before using them.
        self.i_api_reset[:] = [True] * len(self.i_api_reset)

        for i in il:
            rv = rvdict.get(i, EXIT_OK)
            self.pkg("-R {0} {1} {2}".format(self.i_path[i], cmd, args),
                exit=rv, env_arg=env_arg)
            if output_cb:
                output_cb(self.output)

    def _pkg_child(self, i, cl, cmd, args=None, rv=None, rvdict=None):
        assert type(i) == int
        assert type(cl) == list
        assert i not in cl
        assert type(cmd) == str
        assert args is None or type(args) == str
        assert rv is None or type(rv) == int
        assert rvdict is None or type(rvdict) == dict
        assert rv is None or rvdict is None

        if rv is None:
            rv = EXIT_OK
        if rvdict is None:
            rvdict = {}
            for c in cl:
                rvdict[c] = rv
        assert (set(rvdict) | set(cl)) == set(cl)

        if args is None:
            args = ""

        # sync each child from parent
        for c in cl:
            rv = rvdict.get(c, EXIT_OK)
            self._pkg([i], "{0} -l {1}".format(cmd, self.i_name[c]),
                args=args, rv=rv)

    def _pkg_child_all(self, i, cmd, args=None, rv=EXIT_OK):
        assert type(i) == int
        assert type(cmd) == str
        assert args is None or type(args) == str
        assert type(rv) == int

        if args is None:
            args = ""
        self._pkg([i], "{0} -a {1}".format(cmd, args), rv=rv)

    def _attach_parent(self, il, p, args=None, rv=EXIT_OK):
        assert type(il) == list
        assert type(p) == int
        assert p not in il
        assert args is None or type(args) == str
        assert type(rv) == int

        if args is None:
            args = ""

        for i in il:
            self._pkg([i], "attach-linked -p {0} {1} {2}".format(
                args, self.i_name[i], self.i_path[p]), rv=rv)

    def _attach_child(self, i, cl, args=None, rv=None, rvdict=None):
        assert type(i) == int
        assert type(cl) == list
        assert i not in cl
        assert args is None or type(args) == str
        assert rvdict is None or type(rvdict) == dict
        assert rv is None or rvdict is None

        if rv is None:
            rv = EXIT_OK
        if rvdict is None:
            rvdict = {}
            for c in cl:
                rvdict[c] = rv
        assert (set(rvdict) | set(cl)) == set(cl)

        if args is None:
            args = ""

        # attach each child to parent
        for c in cl:
            rv = rvdict.get(c, EXIT_OK)
            self._pkg([i], "attach-linked -c {0} {1} {2}".format(
                args, self.i_name[c], self.i_path[c]),
                rv=rv)

    def _assertEqual_cb(self, output):
        return lambda x: self.assertEqual(output, x)


class TestPkgLinked1(TestPkgLinked):
    def test_not_linked(self):
        self._imgs_create(1)

        self._pkg([0], "list-linked")

        # operations that require a parent
        rv = EXIT_NOPARENT
        self._pkg([0], "detach-linked", rv=rv)
        self._pkg([0], "sync-linked", rv=rv)
        self._pkg([0], "audit-linked", rv=rv)

    def test_opts_1_invalid(self):
        self._imgs_create(3)

        # parent has one child
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # invalid options
        rv = EXIT_BADOPT

        args = "--foobar"
        self._pkg([0], "attach-linked", args=args, rv=rv)
        self._pkg([0], "detach-linked", args=args, rv=rv)
        self._pkg([0], "sync-linked", args=args, rv=rv)
        self._pkg([0], "audit-linked", args=args, rv=rv)
        self._pkg([0], "list-linked", args=args, rv=rv)
        self._pkg([0], "property-linked", args=args, rv=rv)
        self._pkg([0], "set-property-linked", args=args, rv=rv)

        # can't combine -a and -l
        args = "-a -l {0}".format(self.i_name[1])
        self._pkg([0], "detach-linked", args=args, rv=rv)
        self._pkg([0], "sync-linked", args=args, rv=rv)
        self._pkg([0], "audit-linked", args=args, rv=rv)

        # can't combine -I and -i
        args = "-I -i {0}".format(self.i_name[1])
        self._pkg([0], "detach-linked", args=args, rv=rv)
        self._pkg([0], "sync-linked", args=args, rv=rv)
        self._pkg([0], "audit-linked", args=args, rv=rv)
        self._pkg([0], "list-linked", args=args, rv=rv)

        # can't combine -i and -a
        args = "-a -i {0}".format(self.i_name[1])
        self._pkg([0], "detach-linked", args=args, rv=rv)
        self._pkg([0], "sync-linked", args=args, rv=rv)
        self._pkg([0], "audit-linked", args=args, rv=rv)

        # can't combine -I and -a
        args = "-I -a"
        self._pkg([0], "detach-linked", args=args, rv=rv)
        self._pkg([0], "sync-linked", args=args, rv=rv)
        self._pkg([0], "audit-linked", args=args, rv=rv)

        # can't combine -I and -l
        args = "-I -l {0}".format(self.i_name[1])
        self._pkg([0], "detach-linked", args=args, rv=rv)
        self._pkg([0], "sync-linked", args=args, rv=rv)
        self._pkg([0], "audit-linked", args=args, rv=rv)

        # can't combine -i and -l with same target
        args = "-i {0} -l {1}".format(self.i_name[1], self.i_name[1])
        self._pkg([0], "detach-linked", args=args, rv=rv)
        self._pkg([0], "sync-linked", args=args, rv=rv)
        self._pkg([0], "audit-linked", args=args, rv=rv)

        # doesn't accept -a
        args = "-a"
        self._pkg([0], "attach-linked", args=args, rv=rv)
        self._pkg([0], "list-linked", args=args, rv=rv)
        self._pkg([0], "property-linked", args=args, rv=rv)
        self._pkg([0], "set-property-linked", args=args, rv=rv)

        # doesn't accept -l
        args = "-l {0}".format(self.i_name[1])
        self._pkg([0], "attach-linked", args=args, rv=rv)
        self._pkg([0], "list-linked", args=args, rv=rv)

        # can't combine --no-parent-sync and --linked-md-only
        args = "--no-parent-sync --linked-md-only"
        self._pkg([0], "sync-linked -a", args=args, rv=rv)
        self._pkg([2], "sync-linked", args=args, rv=rv)

        # can't use --no-parent-sync when invoking from parent
        args = "--no-parent-sync"
        self._pkg([0], "sync-linked -a", args=args, rv=rv)
        self._pkg_child(0, [1], "sync-linked", args=args, rv=rv)

        # can't use be options when managing children
        for arg in ["--deny-new-be", "--require-new-be",
            "--be-name=foo"]:
            args = "-a {0}".format(arg)
            self._pkg([0], "sync-linked", args=args, rv=rv)

            args = "-l {0} {1}".format(self.i_name[1], arg)
            self._pkg([0], "sync-linked", args=args, rv=rv)
            self._pkg([0], "set-property-linked", args=args, rv=rv)

    def test_opts_2_invalid_bad_child(self):
        self._imgs_create(2)

        rv = EXIT_OOPS

        # try using an invalid child name
        self._pkg([0], "attach-linked -c foobar {0}".format(
            self.i_path[1]), rv=rv)

        for lin in ["foobar", self.i_name[1]]:
            # try using an invalid and unknown child name
            args = "-l {0}".format(lin)

            self._pkg([0], "sync-linked", args=args, rv=rv)
            self._pkg([0], "audit-linked", args=args, rv=rv)
            self._pkg([0], "property-linked", args=args, rv=rv)
            self._pkg([0], "set-property-linked", args=args, rv=rv)
            self._pkg([0], "detach-linked", args=args, rv=rv)

            # try to ignore invalid unknown children
            args = "-i {0}".format(lin)

            # operations on the parent image
            self._pkg([0], "sync-linked", args=args, rv=rv)
            self._pkg([0], "list-linked", args=args, rv=rv)
            self._pkg([0], "update", args=args, rv=rv)
            self._pkg([0], "install", args= \
                "-i {0} {1}".format(lin, self.p_foo1_name[1]), rv=rv)
            self._pkg([0], "change-variant", args= \
                "-i {0} -v variant.foo=baz".format(lin), rv=rv)
            # TODO: test change-facet

        rv = EXIT_BADOPT

        for op in ["update", "install", "uninstall"]:
            # -z and -Z can't be used together
            self._pkg([0], "{0} -r "
                "-z system:img1 -Z system:img1 foo".format(op), rv=rv)
            # check handling of valid but not existing child names
            self._pkg([0], "{0} -r -z system:foo {1}".format(
                op, self.p_foo1_name[1]), rv=rv)
            self._pkg([0], "{0} -r -Z system:foo {1}".format(
                op, self.p_foo1_name[1]), rv=rv)
            # check handling of valid but not existing zone names
            self._pkg([0], "{0} -r -z foo {1}".format(
                op, self.p_foo1_name[1]), rv=rv)
            self._pkg([0], "{0} -r -Z foo {1}".format(
                op, self.p_foo1_name[1]), rv=rv)
            # check handling of invalid child names
            self._pkg([0], "{0} -r -z :foo:&& {1}".format(
                op, self.p_foo1_name[1]), rv=rv)
            self._pkg([0], "{0} -r -Z :foo:&& {1}".format(
                op, self.p_foo1_name[1]), rv=rv)

    def test_opts_3_all(self):
        self._imgs_create(1)

        # the -a option is always valid
        self._pkg([0], "sync-linked -a")
        self._pkg([0], "audit-linked -a")
        self._pkg([0], "detach-linked -a")

    def test_opts_4_noop(self):
        self._imgs_create(4)

        # plan operations
        self._attach_child(0, [1, 2], args="-vn")
        self._attach_child(0, [1, 2], args="-vn")
        self._attach_parent([3], 0, args="-vn")
        self._attach_parent([3], 0, args="-vn")

        # do operations
        self._attach_child(0, [1, 2], args="-v")
        self._attach_parent([3], 0, args="-v")

        # plan operations
        self._pkg_child(0, [1, 2], "detach-linked", args="-vn")
        self._pkg_child(0, [1, 2], "detach-linked", args="-vn")
        self._pkg_child_all(0, "detach-linked", args="-vn")
        self._pkg_child_all(0, "detach-linked", args="-vn")
        self._pkg([3], "detach-linked", args="-vn")
        self._pkg([3], "detach-linked", args="-vn")

        # do operations
        self._pkg_child(0, [1], "detach-linked", args="-v")
        self._pkg_child_all(0, "detach-linked", args="-v")
        self._pkg([3], "detach-linked", args="-v")

    def test_attach_p2c_1(self):
        self._imgs_create(4)
        self._v_not_linked([0, 1, 2, 3])

        # link parents to children as follows:
        #     0 -> 1 -> 2
        #          1 -> 3

        # attach parent (0) to child (1), (0 -> 1)
        self._attach_child(0, [1], args="--parsable=0 -n")
        self.assertEqualParsable(self.output,
            child_images=[{"image_name": "system:img1"}])
        self._attach_child(0, [1], args="--parsable=0")
        self.assertEqualParsable(self.output,
            child_images=[{"image_name": "system:img1"}])
        self._v_has_children(0, [1])
        self._v_has_parent([1])
        self._v_not_linked([2, 3])

        # attach parent (1) to child (2), (1 -> 2)
        self._attach_child(1, [2])
        self._v_has_children(0, [1])
        self._v_has_children(1, [2])
        self._v_has_parent([1, 2])
        self._v_no_children([2])
        self._v_not_linked([3])

        # attach parent (1) to child (3), (1 -> 3)
        self._attach_child(1, [3])
        self._v_has_children(0, [1])
        self._v_has_children(1, [2, 3])
        self._v_has_parent([1, 2, 3])
        self._v_no_children([2, 3])

    def test_detach_p2c_1(self):
        self._imgs_create(4)

        # link parents to children as follows:
        #     0 -> 1 -> 2
        #          1 -> 3
        self._attach_child(0, [1])
        self._attach_child(1, [2, 3])

        # detach child (1) from parent (0)
        self._pkg_child(0, [1], "detach-linked")
        self._v_has_children(1, [2, 3])
        self._v_has_parent([2, 3])
        self._v_no_children([2, 3])
        self._v_not_linked([0])

        # detach child (3) from parent (1)
        self._pkg_child(1, [3], "detach-linked")
        self._v_has_children(1, [2])
        self._v_has_parent([2])
        self._v_no_children([2])
        self._v_not_linked([0, 3])

        # detach child (2) from parent (1)
        self._pkg_child(1, [2], "detach-linked")
        self._v_not_linked([0, 1, 2, 3])

    def test_detach_p2c_2(self):
        self._imgs_create(4)

        # link parents to children as follows:
        #     0 -> 1 -> 2
        #          1 -> 3
        self._attach_child(0, [1])
        self._attach_child(1, [2, 3])

        # detach child (1) from parent (0)
        self._pkg_child_all(0, "detach-linked", args="-n")
        self._pkg_child_all(0, "detach-linked")
        self._v_has_children(1, [2, 3])
        self._v_has_parent([2, 3])
        self._v_no_children([2, 3])
        self._v_not_linked([0])

        # detach child (3) and child (2) from parent (1)
        self._pkg_child_all(1, "detach-linked")
        self._v_not_linked([0, 1, 2, 3])

        # detach all children (there are none)
        self._pkg_child_all(0, "detach-linked")

    def test_attach_c2p_1(self):
        self._imgs_create(4)
        self._v_not_linked([0, 1, 2, 3])

        # link children to parents as follows:
        #     2 -> 1 -> 0
        #     3 -> 1

        # attach child (2) to parent (1), (2 -> 1)
        self._attach_parent([2], 1, args="--parsable=0 -n")
        self.assertEqualParsable(self.output)
        self._attach_parent([2], 1, args="--parsable=0")
        self.assertEqualParsable(self.output)
        self._v_has_parent([2])
        self._v_no_children([2])
        self._v_not_linked([0, 1, 3])

        # attach child (3) to parent (1), (3 -> 1)
        self._attach_parent([3], 1)
        self._v_has_parent([2, 3])
        self._v_no_children([2, 3])
        self._v_not_linked([0, 1])

        # attach child (1) to parent (0), (1 -> 0)
        self._attach_parent([1], 0)
        self._v_has_parent([1, 2, 3])
        self._v_no_children([1, 2, 3])
        self._v_not_linked([0])

    def test_detach_c2p_1(self):
        self._imgs_create(4)

        # link children to parents as follows:
        #     2 -> 1 -> 0
        #     3 -> 1
        self._attach_parent([2, 3], 1)
        self._attach_parent([1], 0)

        # detach parent (0) from child (1)
        self._pkg([1], "detach-linked -n")
        self._pkg([1], "detach-linked")
        self._v_has_parent([2, 3])
        self._v_no_children([2, 3])
        self._v_not_linked([0, 1])

        # detach parent (1) from child (3)
        self._pkg([3], "detach-linked")
        self._v_has_parent([2])
        self._v_no_children([2])
        self._v_not_linked([0, 1, 3])

        # detach parent (1) from child (2)
        self._pkg([2], "detach-linked")
        self._v_not_linked([0, 1, 2, 3])

    def test_attach_already_linked_1_err(self):
        self._imgs_create(4)
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        rv = EXIT_OOPS

        # try to link the parent image to a new child with a dup name
        self._pkg([0], "attach-linked -c {0} {1}".format(
            self.i_name[1], self.i_path[2]), rv=rv)

        # have a new parent try to link to the p2c child
        self._attach_child(3, [1], rv=rv)

        # have the p2c child try to link to a new parent
        self._attach_parent([1], 3, rv=rv)

        # have the c2p child try to link to a new parent
        self._attach_parent([2], 3, rv=rv)

    def test_attach_already_linked_2_relink(self):
        self._imgs_create(4)
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # have a new parent try to link to the p2c child
        self._attach_child(3, [1], args="--allow-relink")

        # have the p2c child try to link to a new parent
        self._attach_parent([1], 3, args="--allow-relink")

        # have the c2p child try to link to a new parent
        self._attach_parent([2], 3, args="--allow-relink")

    def test_zone_attach_detach(self):
        self._imgs_create(2)

        rv = EXIT_OOPS

        # by default we can't attach (p2c) zone image
        self._pkg([0], "attach-linked -v -c zone:foo {0}".format(
            self.i_path[1]), rv=rv)
        self._v_not_linked([0, 1])

        # force attach (p2c) zone image
        self._pkg([0], "attach-linked -v -f -c zone:foo {0}".format(
            self.i_path[1]))
        self._v_not_linked([0])
        self._v_has_parent([1])

        self._imgs_create(2)

        # by default we can't attach (c2p) zone image
        self._pkg([1], "attach-linked -v -p zone:foo {0}".format(
            self.i_path[0]), rv=rv)
        self._v_not_linked([0, 1])

        # force attach (c2p) zone image
        self._pkg([1], "attach-linked -v -f -p zone:foo {0}".format(
            self.i_path[0]))
        self._v_not_linked([0])
        self._v_has_parent([1])

        # by default we can't detach (c2p) zone image
        self._pkg([1], "detach-linked -v", rv=rv)
        self._v_not_linked([0])
        self._v_has_parent([1])

        # force detach (c2p) zone image
        self._pkg([1], "detach-linked -v -f")
        self._v_not_linked([0, 1])

    def test_parent_ops_error(self):
        self._imgs_create(2)

        # attach a child
        self._attach_child(0, [1])

        rv = EXIT_PARENTOP

        # some operations can't be done from a child when linked to
        # from a parent
        self._pkg([1], "detach-linked", rv=EXIT_PARENTOP)

        # TODO: enable this once we support set-property-linked
        #self._pkg([1], "set-property-linked", rv=EXIT_PARENTOP)

    def test_eaccess_1_parent(self):
        self._imgs_create(3)
        self._attach_parent([1], 0)

        rv = EXIT_EACCESS

        for i in [0, 1]:
            if i == 0:
                # empty the parent image
                self.set_image(0)
                self.image_destroy()
                self._ccmd("mkdir -p {0}".format(self.i_path[0]))
            if i == 1:
                # delete the parent image
                self.set_image(0)
                self.image_destroy()

            # operations that need to access the parent should fail
            self._pkg([1], "sync-linked", rv=rv)
            self._pkg([1], "audit-linked", rv=rv)
            self._pkg([1], "install {0}".format(self.p_foo1_name[1]), \
                rv=rv)
            self._pkg([1], "update", rv=rv)

            # operations that need to access the parent should fail
            self._attach_parent([2], 0, rv=rv)

        # detach should still work
        self._pkg([1], "detach-linked")

    def test_eaccess_1_child(self):
        self._imgs_create(2)
        self._attach_child(0, [1])

        outfile = os.path.join(self.test_root, "res")
        rv = EXIT_EACCESS

        for i in [0, 1, 2]:
            if i == 0:
                # corrupt the child image
                self._ccmd("mkdir -p "
                    "{0}/{1}".format(self.i_path[1],
                    image.img_user_prefix))
                self._ccmd("mkdir -p "
                    "{0}/{1}".format(self.i_path[1],
                    image.img_root_prefix))
            if i == 1:
                # delete the child image
                self.set_image(1)
                self.image_destroy()
                self._ccmd("mkdir -p {0}".format(self.i_path[1]))
            if i == 2:
                # delete the child image
                self.set_image(1)
                self.image_destroy()

            # child should still be listed
            self._pkg([0], "list-linked -H > {0}".format(outfile))
            self._ccmd("cat {0}".format(outfile))
            self._ccmd("egrep '^{0}[ 	]' {1}".format(
                self.i_name[1], outfile))

            # child should still be listed
            self._pkg([0], "property-linked -H -l {0} > {1}".format(
                self.i_name[1], outfile))
            self._ccmd("cat {0}".format(outfile))
            self._ccmd("egrep '^li-' {0}".format(outfile))

            # operations that need to access child should fail
            self._pkg_child(0, [1], "sync-linked", rv=rv)
            self._pkg_child_all(0, "sync-linked", rv=rv)

            self._pkg_child(0, [1], "audit-linked", rv=rv)
            self._pkg_child_all(0, "audit-linked", rv=rv)

            self._pkg_child(0, [1], "detach-linked", rv=rv)
            self._pkg_child_all(0, "detach-linked", rv=rv)

            # TODO: test more recursive ops here
            # update, install, uninstall, etc

    def test_ignore_1_no_children(self):
        self._imgs_create(1)
        outfile = os.path.join(self.test_root, "res")

        # it's ok to use -I with no children
        self._pkg([0], "list-linked -H -I > {0}".format(outfile))
        self._ccmd("cat {0}".format(outfile))
        self._ccmd("egrep '^$|.' {0}".format(outfile), rv=EXIT_OOPS)

    def test_ignore_2_ok(self):
        self._imgs_create(3)
        self._attach_child(0, [1, 2])
        outfile = os.path.join(self.test_root, "res")

        # ignore one child
        self._pkg([0], "list-linked -H -i {0} > {1}".format(
            self.i_name[1], outfile))
        self._ccmd("cat {0}".format(outfile))
        self._ccmd("egrep '^{0}[ 	]' {1}".format(
            self.i_name[1], outfile), rv=EXIT_OOPS)
        self._ccmd("egrep '^{0}[ 	]' {1}".format(
            self.i_name[2], outfile))

        # manually ignore all children
        self._pkg([0], "list-linked -H -i {0} -i {1} > {2}".format(
            self.i_name[1], self.i_name[2], outfile))
        self._ccmd("cat {0}".format(outfile))
        self._ccmd("egrep '^$|.' {0}".format(outfile), rv=EXIT_OOPS)

        # automatically ignore all children
        self._pkg([0], "list-linked -H -I > {0}".format(outfile))
        self._ccmd("cat {0}".format(outfile))
        self._ccmd("egrep '^$|.' {0}".format(outfile), rv=EXIT_OOPS)

    def test_no_pkg_updates_1_empty_via_attach(self):
        """test --no-pkg-updates with an empty image."""
        self._imgs_create(3)

        self._attach_child(0, [1], args="--no-pkg-updates")
        self._attach_parent([2], 0, args="--no-pkg-updates")

    def test_no_pkg_updates_1_empty_via_sync(self):
        """test --no-pkg-updates with an empty image."""
        self._imgs_create(4)

        # use --linked-md-only so we don't install constraints package
        self._attach_child(0, [1, 2], args="--linked-md-only")
        self._attach_parent([3], 0, args="--linked-md-only")

        self._pkg_child(0, [1], "sync-linked -v --no-pkg-updates",
            rv=EXIT_NOP)
        self._pkg_child_all(0, "sync-linked -v --no-pkg-updates",
            rv=EXIT_NOP)
        self._pkg([3], "sync-linked -v --no-pkg-updates",
            rv=EXIT_NOP)

    def test_no_pkg_updates_1_empty_via_set_property_linked_TODO(self):
        """test --no-pkg-updates with an empty image."""
        pass

    def test_no_pkg_updates_2_foo_via_attach(self):
        """test --no-pkg-updates with a non-empty image."""
        self._imgs_create(3)

        # install different un-synced packages into each image
        for i in [0, 1, 2]:
            self._pkg([i], "install -v {0}".format(self.p_foo1_name[i]))

        self._attach_child(0, [1], args="--no-pkg-updates")
        self._attach_parent([2], 0, args="--no-pkg-updates")

        # verify the un-synced packages
        for i in [0, 1, 2]:
            self._pkg([i], "list -v {0}".format(self.p_foo1_name[i]))

    def test_no_pkg_updates_2_foo_via_sync(self):
        """test --no-pkg-updates with a non-empty image."""
        self._imgs_create(4)

        # install different un-synced packages into each image
        for i in range(4):
            self._pkg([i], "install -v {0}".format(self.p_foo1_name[i]))

        # use --linked-md-only so we don't install constraints package
        self._attach_child(0, [1, 2], args="--linked-md-only")
        self._attach_parent([3], 0, args="--linked-md-only")

        self._pkg_child(0, [1], "sync-linked -v --no-pkg-updates",
            rv=EXIT_NOP)
        self._pkg_child_all(0, "sync-linked -v --no-pkg-updates",
            rv=EXIT_NOP)
        self._pkg([3], "sync-linked -v --no-pkg-updates",
            rv=EXIT_NOP)

        # verify the un-synced packages
        for i in range(4):
            self._pkg([i], "list -v {0}".format(self.p_foo1_name[i]))

    def test_no_pkg_updates_2_foo_via_set_property_linked_TODO(self):
        """test --no-pkg-updates with a non-empty image."""
        pass

    def test_no_pkg_updates_3_sync_via_attach(self):
        """test --no-pkg-updates with an in sync package"""
        self._imgs_create(3)

        # install the same synced packages into each image
        for i in range(3):
            self._pkg([i], "install -v {0}".format(self.p_sync1_name[1]))

        self._attach_child(0, [1], args="--no-pkg-updates")
        self._attach_parent([2], 0, args="--no-pkg-updates")

        # verify the synced packages
        for i in range(3):
            self._pkg([i], "list -v {0}".format(self.p_sync1_name[1]))

    def test_no_pkg_updates_3_sync_via_sync(self):
        """test --no-pkg-updates with an in sync package"""
        self._imgs_create(4)

        # install the same synced packages into each image
        for i in range(4):
            self._pkg([i], "install -v {0}".format(self.p_sync1_name[1]))

        # use --linked-md-only so we don't install constraints package
        self._attach_child(0, [1, 2], args="--linked-md-only")
        self._attach_parent([3], 0, args="--linked-md-only")

        # verify the synced packages
        for i in range(4):
            self._pkg([i], "list -v {0}".format(self.p_sync1_name[1]))

        self._pkg_child(0, [1], "sync-linked -v --no-pkg-updates",
            rv=EXIT_NOP)
        self._pkg_child_all(0, "sync-linked -v --no-pkg-updates",
            rv=EXIT_NOP)
        self._pkg([3], "sync-linked -v --no-pkg-updates",
            rv=EXIT_NOP)

    def test_no_pkg_updates_3_sync_via_set_property_linked_TODO(self):
        """test --no-pkg-updates with an in sync package"""
        pass

    def test_no_pkg_updates_3_fail_via_attach(self):
        """test --no-pkg-updates with an out of sync package"""
        self._imgs_create(3)

        # install different synced packages into each image
        for i in range(3):
            self._pkg([i], "install -v {0}".format(self.p_sync1_name[i+1]))

        self._attach_child(0, [1], args="--no-pkg-updates",
            rv=EXIT_OOPS)
        self._attach_parent([2], 0, args="--no-pkg-updates",
            rv=EXIT_OOPS)

        # verify packages
        for i in range(3):
            self._pkg([i], "list -v {0}".format(self.p_sync1_name[i+1]))

    def test_no_pkg_updates_3_fail_via_sync(self):
        """test --no-pkg-updates with an out of sync package"""
        self._imgs_create(4)

        # install different synced packages into each image
        for i in range(4):
            self._pkg([i], "install -v {0}".format(self.p_sync1_name[i+1]))

        # use --linked-md-only so we don't install constraints package
        self._attach_child(0, [1, 2], args="--linked-md-only")
        self._attach_parent([3], 0, args="--linked-md-only")

        self._pkg_child(0, [1], "sync-linked -v --no-pkg-updates",
            rv=EXIT_OOPS)
        self._pkg_child_all(0, "sync-linked -v --no-pkg-updates",
            rv=EXIT_OOPS)
        self._pkg([3], "sync-linked -v --no-pkg-updates",
            rv=EXIT_OOPS)

        # verify packages
        for i in range(3):
            self._pkg([i], "list -v {0}".format(self.p_sync1_name[i+1]))

    def test_no_pkg_updates_3_fail_via_set_property_linked_TODO(self):
        pass

    def test_audit_synced_1(self):
        self._imgs_create(4)

        # use --linked-md-only so we don't install constraints package
        self._attach_child(0, [1, 2], args="--linked-md-only")
        self._attach_parent([3], 0, args="--linked-md-only")

        # audit with empty parent and child
        self._pkg([1, 2, 3], "audit-linked")
        self._pkg_child(0, [1, 2], "audit-linked")
        self._pkg_child_all(0, "audit-linked")
        self._pkg_child_all(3, "audit-linked")

    def test_audit_synced_2(self):
        self._imgs_create(4)

        # install different un-synced packages into each image
        for i in [0, 1, 2, 3]:
            self._pkg([i], "install -v {0}".format(self.p_foo1_name[i]))

        # use --linked-md-only so we don't install constraints package
        self._attach_child(0, [1, 2, 3], args="--linked-md-only")

        self._pkg([1, 2, 3], "audit-linked")
        self._pkg_child(0, [1, 2, 3], "audit-linked")
        self._pkg_child_all(0, "audit-linked")

    def test_audit_synced_3(self):
        self._imgs_create(4)

        # install synced package into parent
        self._pkg([0], "install -v {0}".format(self.p_sync1_name[0]))

        # use --linked-md-only so we don't install constraints package
        self._attach_child(0, [1, 2, 3], args="--linked-md-only")

        self._pkg([1, 2, 3], "audit-linked")
        self._pkg_child(0, [1, 2, 3], "audit-linked")
        self._pkg_child_all(0, "audit-linked")

    def test_audit_synced_4(self):
        self._imgs_create(4)

        # install same synced packages into parent and some children
        for i in [0, 1, 2, 3]:
            self._pkg([i], "install -v {0}".format(self.p_sync1_name[0]))

        # use --linked-md-only so we don't install constraints package
        self._attach_child(0, [1, 2, 3], args="--linked-md-only")

        self._pkg([1, 2, 3], "audit-linked")
        self._pkg_child(0, [1, 2, 3], "audit-linked")
        self._pkg_child_all(0, "audit-linked")

    def test_audit_diverged_1(self):
        self._imgs_create(4)

        # install different synced package into some child images
        for i in [1, 3]:
            self._pkg([i], "install -v {0}".format(self.p_sync1_name[i]))

        # use --linked-md-only so we don't install constraints package
        self._attach_child(0, [1, 2, 3], args="--linked-md-only")

        rvdict = {1: EXIT_DIVERGED, 3: EXIT_DIVERGED}
        self._pkg([1, 2, 3], "audit-linked", rvdict=rvdict)
        self._pkg_child(0, [1, 2, 3], "audit-linked", rvdict=rvdict)
        self._pkg_child_all(0, "audit-linked", rv=EXIT_DIVERGED)

    def test_audit_diverged_2(self):
        self._imgs_create(4)

        # install different synced package into each image
        for i in range(4):
            self._pkg([i], "install -v {0}".format(self.p_sync1_name[i]))

        # use --linked-md-only so we don't install constraints package
        self._attach_child(0, [1, 2, 3], args="--linked-md-only")

        rv = EXIT_DIVERGED
        self._pkg([1, 2, 3], "audit-linked", rv=rv)
        self._pkg_child(0, [1, 2, 3], "audit-linked", rv=rv)
        self._pkg_child_all(0, "audit-linked", rv=rv)


class TestPkgLinked2(TestPkgLinked):
    """Class used solely to split up the test suite for parallelization."""

    def test_sync_fail(self):
        self._imgs_create(3)

        # install newer sync'ed package into child
        self._pkg([0], "install -v {0}".format(self.p_sync1_name[2]))
        self._pkg([1], "install -v {0}".format(self.p_sync1_name[1]))
        self._pkg([2], "install -v {0}".format(self.p_sync1_name[1]))

        # attach should fail
        self._attach_child(0, [1], args="-vn", rv=EXIT_OOPS)
        self._attach_child(0, [1], args="-v", rv=EXIT_OOPS)
        self._attach_parent([2], 0, args="-vn", rv=EXIT_OOPS)
        self._attach_parent([2], 0, args="-v", rv=EXIT_OOPS)

        # use --linked-md-only so we don't install constraints package
        # attach should succeed
        self._attach_child(0, [1], args="-vn --linked-md-only")
        self._attach_child(0, [1], args="-v --linked-md-only")
        self._attach_parent([2], 0, args="-vn --linked-md-only")
        self._attach_parent([2], 0, args="-v --linked-md-only")

        # trying to sync the child should fail
        self._pkg([1, 2], "sync-linked -vn", rv=EXIT_OOPS)
        self._pkg([1, 2], "sync-linked -v", rv=EXIT_OOPS)
        self._pkg_child(0, [1], "sync-linked -vn", rv=EXIT_OOPS)
        self._pkg_child(0, [1], "sync-linked -v", rv=EXIT_OOPS)

        # use --linked-md-only so we don't install constraints package
        # sync should succeed
        rv = EXIT_NOP
        self._pkg([1, 2], "sync-linked -vn --linked-md-only", rv=rv)
        self._pkg([1, 2], "sync-linked -v --linked-md-only", rv=rv)
        self._pkg_child(0, [1], "sync-linked -vn --linked-md-only",
            rv=rv)
        self._pkg_child(0, [1], "sync-linked -v --linked-md-only",
            rv=rv)

        # trying to sync via update should fail
        self._pkg([1, 2], "update -vn", rv=EXIT_OOPS)
        self._pkg([1, 2], "update -v", rv=EXIT_OOPS)

        # trying to sync via install should fail
        self._pkg([1, 2], "install -vn {0}", self.p_sync1_name[0],
            rv=EXIT_OOPS)
        self._pkg([1, 2], "install -v {0}", self.p_sync1_name[0],
            rv=EXIT_OOPS)

        # verify the child is still divereged
        rv = EXIT_DIVERGED
        self._pkg([1, 2], "audit-linked", rv=rv)

    def test_sync_1(self):
        self._imgs_create(5)

        # install different synced package into each image
        for i in [0, 1, 2, 3, 4]:
            self._pkg([i], "install -v {0}".format(self.p_sync1_name[i]))

        # install unsynced packages to make sure they aren't molested
        self._pkg([0], "install -v {0}".format(self.p_foo1_name[1]))
        self._pkg([1, 2, 3, 4], "install -v {0}".format(self.p_foo1_name[2]))

        # use --linked-md-only so we don't install constraints package
        self._attach_child(0, [1, 2, 3], args="--linked-md-only")
        self._attach_parent([4], 0, args="--linked-md-only")

        # everyone should be diverged
        self._pkg([1, 2, 3, 4], "audit-linked", rv=EXIT_DIVERGED)

        # plan sync (direct)
        self._pkg([1, 4], "sync-linked -vn")
        self._pkg([1, 2, 3, 4], "audit-linked", rv=EXIT_DIVERGED)

        # sync child (direct)
        self._pkg([1, 4], "sync-linked", args="--parsable=0 -n")
        self.assertEqualParsable(self.output,
            change_packages=[[self.s1_list[-1], self.s1_list[0]]])
        self._pkg([1, 4], "sync-linked", args="--parsable=0")
        self.assertEqualParsable(self.output,
            change_packages=[[self.s1_list[-1], self.s1_list[0]]])
        rvdict = {2: EXIT_DIVERGED, 3: EXIT_DIVERGED}
        self._pkg([1, 2, 3, 4], "audit-linked", rvdict=rvdict)
        self._pkg([1, 4], "sync-linked -v", rv=EXIT_NOP)

        # plan sync (indirectly via -l)
        self._pkg_child(0, [2], "sync-linked -vn")
        self._pkg([1, 2, 3], "audit-linked", rvdict=rvdict)

        # sync child (indirectly via -l)
        self._pkg_child(0, [2], "sync-linked", args="--parsable=0 -n")
        self.assertEqualParsable(self.output,
            child_images=[{
                "image_name": "system:img2",
                "change_packages": [[self.s1_list[2], self.s1_list[0]]]
            }])
        self._pkg_child(0, [2], "sync-linked", args="--parsable=0")
        self.assertEqualParsable(self.output,
            child_images=[{
                "image_name": "system:img2",
                "change_packages": [[self.s1_list[2], self.s1_list[0]]]
            }])
        rvdict = {3: EXIT_DIVERGED}
        self._pkg([1, 2, 3], "audit-linked", rvdict=rvdict)
        self._pkg_child(0, [2], "sync-linked -vn", rv=EXIT_NOP)

        # plan sync (indirectly via -a)
        self._pkg_child_all(0, "sync-linked -vn")
        self._pkg([1, 2, 3], "audit-linked", rvdict=rvdict)

        # sync child (indirectly via -a)
        self._pkg_child_all(0, "sync-linked -v")
        self._pkg([1, 2, 3], "audit-linked")
        self._pkg_child_all(0, "sync-linked -v", rv=EXIT_NOP)

        # check unsynced packages
        self._pkg([1, 2, 3, 4], "list -v {0}".format(self.p_foo1_name[2]))

    def test_sync_2_via_attach(self):
        self._imgs_create(3)

        # install different synced package into each image
        self._pkg([0], "install -v {0}".format(self.p_sync1_name[1]))
        self._pkg([1, 2], "install -v {0}".format(self.p_sync1_name[2]))

        # install unsynced packages to make sure they aren't molested
        self._pkg([0], "install -v {0}".format(self.p_foo1_name[1]))
        self._pkg([1, 2], "install -v {0}".format(self.p_foo1_name[2]))

        # attach children
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # check synced and unsynced packages
        self._pkg([1, 2], "list -v {0}".format(self.p_sync1_name[1]))
        self._pkg([1, 2], "list -v {0}".format(self.p_foo1_name[2]))

    def __test_linked_sync_via_child_op(self, op, op_args, **kwargs):
        """Verify that if we do a operation "op" on a child image, it
        automatically brings its packages in sync with its parent.

        We perform operation on three child images.  1 is a push
        child, 2 and 3 are pull children.  1 and 2 have their linked
        image metadata in sync with the parent.  3 has its metadata
        out of sync with the parent and is expected to sync its own
        metadata."""

        # create parent (0), push child (1), and pull child (2, 3)
        self._imgs_create(4)
        self._attach_child(0, [1])
        self._attach_parent([2, 3], 0)

        # install synced package into each image
        self._pkg([0, 1, 2, 3], "install -v {0}".format(self.p_sync1_name[2]))

        # install unsynced packages
        self._pkg([0], "install -v {0}".format(self.p_foo1_name[1]))
        self._pkg([1, 2, 3], "install -v {0}".format(self.p_foo1_name[2]))

        # update the parent image while ignoring the children (there
        # by putting them out of sync)
        self._pkg([0], "install -I -v {0}".format(self.p_sync1_name[1]))

        # explicitly sync metadata in children 1 and 2
        self._pkg([0], "sync-linked -a --linked-md-only")
        self._pkg([2], "sync-linked --linked-md-only")

        # plan op
        self._pkg([1, 2, 3], "{0} -nv {1}".format(op, op_args))

        # verify child images are still diverged
        self._pkg([1, 2, 3], "audit-linked", rv=EXIT_DIVERGED)
        self._pkg([0], "audit-linked -a", rv=EXIT_DIVERGED)

        # verify child 3 hasn't updated its metadata
        # (it still thinks it's in sync)
        self._pkg([3], "audit-linked --no-parent-sync")

        # execute op
        def output_cb(output):
            self.assertEqualParsable(output, **kwargs)
        self._pkg([1, 2, 3], "{0} --parsable=0 {1}".format(op, op_args),
            output_cb=output_cb)

        # verify sync via audit and sync (which should be a noop)
        self._pkg([1, 2, 3], "audit-linked")
        self._pkg([1, 2, 3], "sync-linked -v", rv=EXIT_NOP)
        self._pkg([0], "audit-linked -a")
        self._pkg([0], "sync-linked -a", rv=EXIT_NOP)

    def __test_linked_sync_via_parent_op(self, op, op_args,
        li_md_change=True, **kwargs):
        """Verify that if we do a operation "op" on a parent image, it
        recurses into its children and brings them into sync.

        We perform operation on two child images.  both are push
        children.  1 has its linked image metadata in sync with the
        parent.  2 has its linked image metadata out of in sync with
        the parent and that metadata should get updated during the
        operation.

        Note that if the metadata in a child image is in sync with its
        parent, a recursive operation that isn't changing that
        metadata will assume that the child is already in sync and
        that we don't need to recurse into it.  This optimization
        occurs regardless of if the child image is actually in sync
        with that metadata (a child can be out of sync with its
        stored metadata if we do a metadata only update)."""

        # create parent (0), push child (1, 2)
        self._imgs_create(3)
        self._attach_child(0, [1, 2])

        # install synced package into each image
        self._pkg([0, 1, 2], "install -v {0}".format(self.p_sync1_name[2]))

        # install unsynced packages
        self._pkg([0], "install -v {0}".format(self.p_foo1_name[1]))
        self._pkg([1, 2], "install -v {0}".format(self.p_foo1_name[2]))

        # update the parent image while ignoring the children (there
        # by putting them out of sync)
        self._pkg([0], "install -I -v {0}".format(self.p_sync1_name[1]))

        # explicitly sync metadata in child 1
        self._pkg([0], "sync-linked --linked-md-only -l {0}".format(
            self.i_name[1]))

        # plan op
        self._pkg([0], "{0} -nv {1}".format(op, op_args))

        # verify child images are still diverged
        self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)
        self._pkg([0], "audit-linked -a", rv=EXIT_DIVERGED)

        # verify child 2 hasn't updated its metadata
        # (it still thinks it's in sync)
        self._pkg([2], "audit-linked")

        # execute op
        def output_cb(output):
            self.assertEqualParsable(output, **kwargs)
        self._pkg([0], "{0} --parsable=0 {1}".format(op, op_args),
            output_cb=output_cb)

        # verify sync via audit and sync (which should be a noop)
        # if the linked image metadata was changed during this
        # operation we should have updated both children.  if linked
        # image metadata was not changed, we'll only have updated one
        # child.
        if li_md_change:
            synced_children = [1, 2]
        else:
            synced_children = [2]
        for i in synced_children:
            self._pkg([i], "audit-linked")
            self._pkg([i], "sync-linked", rv=EXIT_NOP)
            self._pkg([0], "audit-linked -l {0}".format(self.i_name[i]))
            self._pkg([0], "sync-linked -l {0}".format(self.i_name[i]),
                rv=EXIT_NOP)

    def test_linked_sync_via_update(self):
        """Verify that if we update child images to be in sync with
        their constraints when we do an update."""

        self.__test_linked_sync_via_child_op(
            "update", "",
            change_packages=[
                [self.foo1_list[2], self.foo1_list[0]],
                [self.s1_list[2], self.s1_list[1]]])

        self.__test_linked_sync_via_parent_op(
            "update", "",
            change_packages=[
                [self.foo1_list[1], self.foo1_list[0]],
                [self.s1_list[1], self.s1_list[0]]],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[0]]],
                }, {
                "image_name": "system:img2",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[0]]],
            }])

        # explicit recursion into all children
        self.__test_linked_sync_via_parent_op(
            "update -r", "",
            change_packages=[
                [self.foo1_list[1], self.foo1_list[0]],
                [self.s1_list[1], self.s1_list[0]]],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [
                    [self.foo1_list[2], self.foo1_list[0]],
                    [self.s1_list[2], self.s1_list[0]]],
                }, {
                "image_name": "system:img2",
                "change_packages": [
                    [self.foo1_list[2], self.foo1_list[0]],
                    [self.s1_list[2], self.s1_list[0]]],
            }])

    def test_linked_sync_via_update_pkg(self):
        """Verify that if we update child images to be in sync with
        their constraints when we do an update of a specific
        package."""

        self.__test_linked_sync_via_child_op(
            "update", self.p_foo1_name[3],
            change_packages=[
                [self.foo1_list[2], self.foo1_list[3]],
                [self.s1_list[2], self.s1_list[1]]])

        self.__test_linked_sync_via_parent_op(
            "update", self.p_foo1_name[3],
            change_packages=[
                [self.foo1_list[1], self.foo1_list[3]]],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
                }, {
                "image_name": "system:img2",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
            }])

        # explicit recursion into all children
        self.__test_linked_sync_via_parent_op(
            "update -r", self.p_foo1_name[3],
            change_packages=[
                [self.foo1_list[1], self.foo1_list[3]]],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [
                    [self.foo1_list[2], self.foo1_list[3]],
                    [self.s1_list[2], self.s1_list[1]]],
                }, {
                "image_name": "system:img2",
                "change_packages": [
                    [self.foo1_list[2], self.foo1_list[3]],
                    [self.s1_list[2], self.s1_list[1]]],
            }])

    def test_linked_sync_via_install(self):
        """Verify that if we update child images to be in sync with
        their constraints when we do an install."""

        self.__test_linked_sync_via_child_op(
            "install", self.p_foo1_name[1],
            change_packages=[
                [self.foo1_list[2], self.foo1_list[1]],
                [self.s1_list[2], self.s1_list[1]]])

        self.__test_linked_sync_via_parent_op(
            "install", self.p_foo1_name[0],
            change_packages=[
                [self.foo1_list[1], self.foo1_list[0]],
            ],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
                }, {
                "image_name": "system:img2",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
            }])

        # explicit recursion into all children
        self.__test_linked_sync_via_parent_op(
            "install -r ", self.p_foo1_name[0],
            change_packages=[
                [self.foo1_list[1], self.foo1_list[0]],
            ],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [
                    [self.foo1_list[2], self.foo1_list[0]],
                    [self.s1_list[2], self.s1_list[1]]],
                }, {
                "image_name": "system:img2",
                "change_packages": [
                    [self.foo1_list[2], self.foo1_list[0]],
                    [self.s1_list[2], self.s1_list[1]]],
            }])

    def test_linked_sync_via_sync(self):
        """Verify that if we update child images to be in sync with
        their constraints when we do a sync-linked."""

        self.__test_linked_sync_via_child_op(
            "sync-linked", "",
            change_packages=[
                [self.s1_list[2], self.s1_list[1]]])

        self.__test_linked_sync_via_parent_op(
            "sync-linked", "-a",
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
                }, {
                "image_name": "system:img2",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
            }])

    def test_linked_sync_via_change_variant(self):
        """Verify that if we update child images to be in sync with
        their constraints when we do a change-variant."""

        self.__test_linked_sync_via_child_op(
            "change-variant", "variant.foo=baz",
            change_packages=[
                [self.s1_list[2], self.s1_list[1]]],
            affect_packages=[
                self.foo1_list[2]],
            change_variants=[
                ['variant.foo', 'baz']])

        self.__test_linked_sync_via_parent_op(
            "change-variant", "variant.foo=baz",
            li_md_change=False,
            affect_packages=[
                self.foo1_list[1], self.s1_list[1]],
            change_variants=[
                ['variant.foo', 'baz']],
            child_images=[{
                "image_name": "system:img2",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
            }])

    def test_linked_sync_via_change_facet(self):
        """Verify that if we update child images to be in sync with
        their constraints when we do a change-facet."""

        self.__test_linked_sync_via_child_op(
            "change-facet", "facet.foo=True",
            change_packages=[
                [self.s1_list[2], self.s1_list[1]]],
            change_facets=[
                ['facet.foo', True, None, 'local', False, False]])

        self.__test_linked_sync_via_parent_op(
            "change-facet", "facet.foo=True",
            li_md_change=False,
            change_facets=[
                ['facet.foo', True, None, 'local', False, False]],
            child_images=[{
                "image_name": "system:img2",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
            }])

    def test_linked_sync_via_uninstall(self):
        """Verify that if we update child images to be in sync with
        their constraints when we do an uninstall."""

        self.__test_linked_sync_via_child_op(
            "uninstall", self.p_foo1_name[2],
            change_packages=[
                [self.s1_list[2], self.s1_list[1]]],
            remove_packages=[
                self.foo1_list[2]])

        self.__test_linked_sync_via_parent_op(
            "uninstall", self.foo1_list[1],
            remove_packages=[
                self.foo1_list[1]],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
                }, {
                "image_name": "system:img2",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
            }])

        # explicit recursion into all children
        self.__test_linked_sync_via_parent_op(
            "uninstall -r", self.foo1_list[1],
            remove_packages=[
                self.foo1_list[1]],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
                "remove_packages": [],
                }, {
                "image_name": "system:img2",
                "change_packages": [
                    [self.s1_list[2], self.s1_list[1]]],
            }])


class TestPkgLinked3(TestPkgLinked):
    """Class used solely to split up the test suite for parallelization."""

    def test_parent_sync_1_nosync(self):
        self._imgs_create(2)

        # install synced package into each image
        self._pkg([0, 1], "install -v {0}".format(self.p_sync1_name[1]))

        self._attach_parent([1], 0)

        # update parent image
        self._pkg([0], "install -v {0}".format(self.p_sync1_name[0]))

        # there should be no updates with --no-parent-sync
        self._pkg([1], "sync-linked -v --no-parent-sync", rv=EXIT_NOP)
        self._pkg([1], "change-variant -v --no-parent-sync "
            "variant.foo=bar", rv=EXIT_NOP)
        self._pkg([1], "change-facet -v --no-parent-sync "
            "facet.foo=False")
        self._pkg([1], "install -v --no-parent-sync {0}".format(
            self.p_foo1_name[1]))
        self._pkg([1], "update -v --no-parent-sync")
        self._pkg([1], "uninstall -v --no-parent-sync {0}".format(
            self.p_foo1_name[0]))

        # an audit without a parent sync should thingk we're in sync
        self._pkg([1], "audit-linked --no-parent-sync")

        # an full audit should realize we're not in sync
        self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)

        # the audit above should not have updated our image, so we
        # should still be out of sync.
        self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)

    def test_install_constrainted(self):
        self._imgs_create(3)

        # install synced package into parent
        self._pkg([0], "install -v {0}".format(self.p_sync1_name[1]))

        # attach children
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # try to install a different vers of synced package
        for i in [0, 2, 3, 4]:
            self._pkg([1, 2], "install -v {0}".format(
                self.p_sync1_name[i]), rv=EXIT_OOPS)

        # try to install a different synced package
        for i in [0, 1, 2, 3, 4]:
            self._pkg([1, 2], "install -v {0}".format(
                self.p_sync2_name[i]), rv=EXIT_OOPS)

        # install random un-synced package
        self._pkg([1, 2], "install -v {0}".format(self.p_foo1_name[0]))

        # install the same ver of a synced package in the child
        self._pkg([1, 2], "install -v {0}".format(self.p_sync1_name[1]))

    def test_install_group(self):
        self._imgs_create(2)

        # install synced package into parent
        self._pkg([0], "install -v osnet-incorporation@0.5.11-0.175.3.19.0.1.0")

        # attach children
        self._attach_child(0, [1])

        # install synced package into child
        self._pkg([1], "install -v osnet-incorporation@0.5.11-0.175.3.19.0.1.0")

        # verify group package can be installed into child even though
        # group package and its dependencies are not installed in parent
        self._pkg([1], "-D plan install solaris-small-server")

        # verify arbitrary un-synced package can be installed into child
        # even though group dependencies are active and cannot be
        # satisfied
        self._pkg([1], "-D plan install -nv {0}".format(self.p_foo1_name[0]))

        # verify parent and child can have parent-constraint package
        # updated even though child's group dependencies in
        # solaris-small-server are active and cannot be satisfied
        self._pkg([0], "-D plan update -nv")
        self._pkg([0], "-D plan update -v osnet-incorporation")

    def test_install_frozen(self):
        self._imgs_create(2)

        # install synced package into parent
        self._pkg([0], "install -v osnet-incorporation@0.5.11-0.175.3.19.0.1.0")

        # attach children
        self._attach_child(0, [1])

        # install synced package into child
        self._pkg([1], "install -v osnet-incorporation@0.5.11-0.175.3.19.0.1.0")

        # freeze synced package in parent
        self._pkg([0], "freeze osnet-incorporation")

        # verify that if synced package is frozen in parent, an update
        # in the child will result in 'nothing to do' instead of 'no
        # solution found' even though a newer version of synced package
        # is available; check both with and without arguments cases
        self._pkg([1], "-D plan update -nv", rv=EXIT_NOP)
        self._pkg([1], "-D plan update -nv osnet-incorporation", rv=EXIT_NOP)

        # verify that if synced package is frozen in parent, an attempt
        # to update in the child to the latest version will result in
        # graceful failure
        self._pkg([1], "-D plan update -nv osnet-incorporation@latest",
            rv=EXIT_OOPS)

        # verify that if synced package is frozen, arbitrary un-synced
        # package can be installed into child
        self._pkg([1], "-D plan install -nv {0}".format(self.p_foo1_name[0]))

        # unfreeze synced package in parent
        self._pkg([0], "unfreeze osnet-incorporation")

        # verify that if synced package is unfrozen in both parent and
        # child, an update in the child will result in 'nothing to do'
        # since it is parent-constrained; check both with and without
        # arguments cases
        self._pkg([1], "-D plan update -nv", rv=EXIT_NOP)
        self._pkg([1], "-D plan update -nv osnet-incorporation", rv=EXIT_NOP)

        # freeze synced package in child
        self._pkg([1], "freeze osnet-incorporation")

        # verify that if synced package is frozen in child, an update
        # in the parent will result in expected failure
        self._pkg([0], "-D plan update -nv", rv=EXIT_OOPS)

        # verify that if synced package is frozen in child, an update in
        # the child will still result in 'nothing to do'
        self._pkg([1], "-D plan update -nv", rv=EXIT_NOP)

        # verify that if synced package is frozen in child, an attempt
        # to update in the child to the latest version will result in
        # graceful failure
        self._pkg([1], "-D plan update -nv osnet-incorporation@latest",
            rv=EXIT_OOPS)

        # upgrade the parent using -I to ignore the children
        self._pkg([0],
            "-D plan update -I -v osnet-incorporation@latest")

        # explicitly sync metadata in child 1
        self._pkg([0], "sync-linked --linked-md-only -l {0}".format(
            self.i_name[1]))

        # verify that an update in the child fails due to out of sync
        # state, but can't get back into sync because of freeze; check
        # both with and without arguments cases
        self._pkg([1], "-D plan update -nv", rv=EXIT_OOPS)
        self._pkg([1], "-D plan update -nv osnet-incorporation@latest",
            rv=EXIT_OOPS)

        # unfreeze synced package in child
        self._pkg([1], "unfreeze osnet-incorporation")

        # verify that the child can be updated back to in-sync state
        # with the parent; check both with and without arguments cases
        self._pkg([1], "-D plan update -nv")
        self._pkg([1], "-D plan update -nv osnet-incorporation@latest")

    def test_verify(self):
        self._imgs_create(5)

        # install synced package into each image
        self._pkg([0, 1], "install -v {0}".format(self.p_sync1_name[1]))

        # test with a newer synced package
        self._pkg([2], "install -v {0}".format(self.p_sync1_name[0]))

        # test with an older synced package
        self._pkg([3], "install -v {0}".format(self.p_sync1_name[2]))

        # test with a different synced package
        self._pkg([4], "install -v {0}".format(self.p_sync2_name[2]))

        self._attach_parent([1], 0)
        self._attach_parent([2, 3, 4], 0, args="--linked-md-only")

        self._pkg([1], "verify")
        self._pkg([2, 3, 4], "verify", rv=EXIT_OOPS)

    def test_staged_noop(self):
        self._imgs_create(1)

        # test staged execution with an noop/empty plan
        self._pkg([0], "update --stage=plan", rv=EXIT_NOP)
        self._pkg([0], "update --stage=prepare")
        self._pkg([0], "update --stage=execute")

    def __test_missing_parent_pkgs_metadata(self,
        install="", audit_rv=EXIT_OK):
        """Verify that we can manipulate and update linked child
        images which are missing their parent package metadata.  Also
        verify that when we update those children the metadata gets
        updated correctly."""

        # create parent (0), push child (1), and pull child (2)
        self._imgs_create(3)
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # paths for the linked image metadata files
        md_files = [
                "{0}/var/pkg/linked/linked_ppkgs".format(self.i_path[i])
                for i in [1, 2]
        ]

        if install:
            for i in [0, 1, 2]:
                self._pkg([i], "install -v {0}".format(install))

        # delete linked image metadata files
        for f in md_files:
            self.file_exists(f)
            self._ccmd("rm {0}".format(f))

        # verify that audit-linked can handle missing metadata.
        self._pkg([0], "audit-linked -a")
        self._pkg([2], "audit-linked")
        self._pkg([1], "audit-linked", rv=audit_rv)
        self._pkg([2], "audit-linked --no-parent-sync", rv=audit_rv)

        # since we haven't modified the image, make sure the
        # facet metadata files weren't re-created.
        for f in md_files:
            self.file_doesnt_exist(f)

        # verify that sync-linked can handle missing metadata.
        # also verify that the operation will succeed and is
        # not a noop (since it needs to update the metadata).
        self._pkg([0], "sync-linked -a -n")
        self._pkg([2], "sync-linked -n")

        # since we haven't modified the image, make sure the
        # facet metadata files weren't re-created.
        for f in md_files:
            self.file_doesnt_exist(f)

        # do a sync and verify that the files get created
        self._pkg([0], "sync-linked -a")
        self._pkg([2], "sync-linked")
        for f in md_files:
            self.file_exists(f)

    def test_missing_parent_pkgs_metadata_1(self):
        """Verify that we can manipulate and update linked child
        images which are missing their parent package metadata.  Also
        verify that when we update those children the metadata gets
        updated correctly.

        Test when parent has no packages installed.  The children also
        have no packages installed so they are always in sync."""
        self.__test_missing_parent_pkgs_metadata()

    def test_missing_parent_pkgs_metadata_2(self):
        """Verify that we can manipulate and update linked child
        images which are missing their parent package metadata.  Also
        verify that when we update those children the metadata gets
        updated correctly.

        Test when parent and children have sync packages installed.
        This means the children are diverged if their parent package
        metadata is missing."""
        self.__test_missing_parent_pkgs_metadata(
            install=self.p_sync1_name[0], audit_rv=EXIT_DIVERGED)

    def __test_missing_parent_publisher_metadata(self,
        clear_pubs=False):
        """Verify that we can manipulate and update linked child
        images which are missing their parent publisher metadata.  Also
        verify that when we update those children the metadata gets
        updated correctly."""

        # create parent (0), push child (1), and pull child (2)
        self._imgs_create(3)
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # paths for the linked image metadata files
        md_files = [
                "{0}/var/pkg/linked/linked_ppubs".format(self.i_path[i])
                for i in [1, 2]
        ]

        if clear_pubs:
            self._pkg([0, 1, 2], "unset-publisher test")

        # delete linked image metadata files
        for f in md_files:
            self.file_exists(f)
            self._ccmd("rm {0}".format(f))

        # verify that audit-linked can handle missing metadata.
        self._pkg([0], "audit-linked -a")
        self._pkg([1, 2], "audit-linked")
        self._pkg([2], "audit-linked --no-parent-sync")

        # since we haven't modified the image, make sure the
        # facet metadata files weren't re-created.
        for f in md_files:
            self.file_doesnt_exist(f)

        # verify that sync-linked can handle missing metadata.
        # also verify that the operation will succeed and is
        # not a noop (since it needs to update the metadata).
        self._pkg([0], "sync-linked -a -n")
        self._pkg([2], "sync-linked -n")

        # since we haven't modified the image, make sure the
        # facet metadata files weren't re-created.
        for f in md_files:
            self.file_doesnt_exist(f)

        # do a sync and verify that the files get created
        self._pkg([0], "sync-linked -a")
        self._pkg([2], "sync-linked")
        for f in md_files:
            self.file_exists(f)

    def test_missing_parent_publisher_metadata_1(self):
        """Verify that we can manipulate and update linked child
        images which are missing their parent publisher metadata.  Also
        verify that when we update those children the metadata gets
        updated correctly.

        Test when parent has no publishers configured."""
        self.__test_missing_parent_publisher_metadata(
            clear_pubs=True)

    def test_missing_parent_publisher_metadata_2(self):
        """Verify that we can manipulate and update linked child
        images which are missing their parent publisher metadata.  Also
        verify that when we update those children the metadata gets
        updated correctly.

        Test when parent has publishers configured."""
        self.__test_missing_parent_publisher_metadata()


class TestPkgLinkedRecurse(TestPkgLinked):
    """Test explicitly requested recursion"""

    def _recursive_pkg(self, op, args, **kwargs):
        """Run recursive pkg operation, compare results."""

        def output_cb(output):
            self.assertEqualParsable(output, **kwargs)
        self._pkg([0], "{0} -r --parsable=0 {1}".format(op, args),
            output_cb=output_cb)

    def test_recursive_install(self):
        """Test recursive pkg install"""

        # create parent (0), push child (1, 2)
        self._imgs_create(3)
        self._attach_child(0, [1, 2])

        self._recursive_pkg("install", self.foo1_list[0],
            add_packages=[self.foo1_list[0]],
            child_images=[{
                "image_name": "system:img1",
                "add_packages": [self.foo1_list[0]]
            }, {
                "image_name": "system:img2",
                "add_packages": [self.foo1_list[0]]
            }
        ])

        # remove pkgs from children, leave parent alone, try again
        self._pkg([1, 2], "uninstall {0}".format(self.foo1_list[0]))

        self._recursive_pkg("install", self.foo1_list[0],
            add_packages=[],
            child_images=[{
                "image_name": "system:img1",
                "add_packages": [self.foo1_list[0]]
            }, {
                "image_name": "system:img2",
                "add_packages": [self.foo1_list[0]]
            }
        ])

        # remove pkgs from parent, leave children alone, try again
        self._pkg([0], "uninstall {0}".format(self.foo1_list[0]))

        self._recursive_pkg("install", self.foo1_list[0],
            add_packages=[self.foo1_list[0]],
            child_images=[{
                "image_name": "system:img1",
                "add_packages": []
            }, {
                "image_name": "system:img2",
                "add_packages": []
            }
        ])

    def test_recursive_uninstall(self):
        """Test recursive uninstall"""

        # create parent (0), push child (1)
        self._imgs_create(2)
        self._attach_child(0, [1])

        # install some packages to remove
        self._pkg([0, 1], "install {0}".format(self.foo1_list[0]))

        # uninstall package which is present in parent and child
        self._recursive_pkg("uninstall", self.foo1_list[0],
            remove_packages=[self.foo1_list[0]],
            child_images=[{
                "image_name": "system:img1",
                "remove_packages": [self.foo1_list[0]]
            }
        ])

        # install pkg back into child, leave parent alone, try again
        self._pkg([1], "install {0}".format(self.foo1_list[0]))
        self._recursive_pkg("uninstall", self.foo1_list[0],
            remove_packages=[],
            child_images=[{
                "image_name": "system:img1",
                "remove_packages": [self.foo1_list[0]]
            }
        ])

        # install pkg back into parent, leave child alone, try again
        self._pkg([0], "install {0}".format(self.foo1_list[0]))
        self._recursive_pkg("uninstall", self.foo1_list[0],
            remove_packages=[self.foo1_list[0]],
            child_images=[{
                "image_name": "system:img1",
                "remove_packages": []
            }
        ])

    def test_recursive_update(self):
        """Test recursive update"""

        # create parent (0), push child (1)
        self._imgs_create(2)
        self._attach_child(0, [1])

        # install some packages to update
        self._pkg([0, 1], "install {0}".format(self.foo1_list[0]))

        # update package which is present in parent and child
        self._recursive_pkg("update", self.foo1_list[3],
            change_packages=[[self.foo1_list[0], self.foo1_list[3]]],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [[
                    self.foo1_list[0],
                    self.foo1_list[3]
                ]]
            }
        ])

        # downgrade child, leave parent alone, try again
        self._pkg([1], "update {0}".format(self.foo1_list[0]))
        self._recursive_pkg("update", self.foo1_list[3],
            change_packages=[],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [[
                    self.foo1_list[0],
                    self.foo1_list[3]
                ]]
            }
        ])

        # downgrade parent, leave child alone, try again
        self._pkg([0], "update {0}".format(self.foo1_list[0]))
        self._recursive_pkg("update", self.foo1_list[3],
            change_packages=[[self.foo1_list[0], self.foo1_list[3]]],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": []
            }
        ])

    def test_recursive_variant(self):
        """Test recursive change-variant"""

        # create parent (0), push child (1)
        self._imgs_create(2)
        self._attach_child(0, [1])

        # install some packages
        self._pkg([0, 1], "install {0}".format(self.foo1_list[0]))

        # change variant in parent and child
        self._recursive_pkg("change-variant", "variant.foo=baz",
            change_variants=[["variant.foo", "baz"]],
            affect_packages=[self.foo1_list[0]],
            child_images=[{
                "image_name": "system:img1",
                "change_variants": [["variant.foo", "baz"]],
                "affect_packages": [self.foo1_list[0]]
            }
        ])

        # revert variant in child, leave parent alone, try again
        self._pkg([1], "change-variant -v variant.foo=bar")
        self._recursive_pkg("change-variant", "variant.foo=baz",
            change_variants=[],
            affect_packages=[],
            child_images=[{
                "image_name": "system:img1",
                "change_variants": [["variant.foo", "baz"]],
                "affect_packages": [self.foo1_list[0]]
            }
        ])

        # revert variant in parent, leave child alone, try again
        self._pkg([0], "change-variant -v variant.foo=bar")

        self._pkg([0], "audit-linked -a")
        self._recursive_pkg("change-variant", "variant.foo=baz",
            change_variants=[["variant.foo", "baz"]],
            affect_packages=[self.foo1_list[0]],
        )

    def test_recursive_facet(self):
        """Test recursive change-facet"""

        # create parent (0), push child (1)
        self._imgs_create(2)
        self._attach_child(0, [1])

        # set facet in parent and child
        self._recursive_pkg("change-facet", "facet.foo=True",
            change_facets=[["facet.foo", True, None, "local", False,
                False]],
            child_images=[{
                "image_name": "system:img1",
                "change_facets": [["facet.foo", True, None, "local",
                    False, False]],
            }
        ])

        # change facet in child, leave parent alone, try again
        self._pkg([1], "change-facet -v facet.foo=False")
        self._recursive_pkg("change-facet", "facet.foo=True",
            change_facets=[],
            child_images=[{
                "image_name": "system:img1",
                "change_facets": [["facet.foo", True, False, "local",
                    False, False]],
            }
        ])

        # remove facet in child, leave parent alone, try again
        self._pkg([1], "change-facet -v facet.foo=None")
        self._recursive_pkg("change-facet", "facet.foo=True",
            change_facets=[],
            child_images=[{
                "image_name": "system:img1",
                "change_facets": [["facet.foo", True, None, "local",
                    False, False]],
            }
        ])

        # change facet in parent, leave child alone, try again
        self._pkg([0], "change-facet -v facet.foo=False")
        self._recursive_pkg("change-facet", "facet.foo=True",
            change_facets=[["facet.foo", True, False, "local",
                False, False]],
        )

        # remove facet in parent, leave child alone, try again
        self._pkg([0], "change-facet -v facet.foo=None")
        self._recursive_pkg("change-facet", "facet.foo=True",
            change_facets=[["facet.foo", True, None, "local",
                False, False]],
        )

        # change facet in parent and child
        self._recursive_pkg("change-facet", "facet.foo=False",
            change_facets=[["facet.foo", False, True, "local",
                False, False]],
            child_images=[{
                "image_name": "system:img1",
                "change_facets": [["facet.foo", False, True, "local",
                    False, False]],
            }
        ])

        # remove facet in parent and child
        self._recursive_pkg("change-facet", "facet.foo=None",
            change_facets=[["facet.foo", None, False, "local",
                    False, False]],
            child_images=[{
                "image_name": "system:img1",
                "change_facets": [["facet.foo", None, False, "local",
                    False, False]],
            }
        ])

    def test_image_selection(self):
        """Test that explicit recursion into only the requested child
           images works as expected."""

        # We already tested that all the different operations which
        # support explicit recursion work in general so we only test
        # with install to see if the image selection works correctly.

        # create parent (0), push child (1,2,3)
        self._imgs_create(4)
        self._attach_child(0, [1, 2, 3])

        # We are only interested if the correct children are selected
        # for a certain operation so we make sure that operations on
        # the parent are always a nop.
        self._pkg([0], "install {0}".format(self.foo1_list[0]))

        # install into all children
        self._recursive_pkg("install", self.foo1_list[0],
            child_images=[{
                "image_name": "system:img1",
                "add_packages": [self.foo1_list[0]]
            }, {
                "image_name": "system:img2",
                "add_packages": [self.foo1_list[0]]
            }, {
                "image_name": "system:img3",
                "add_packages": [self.foo1_list[0]]
            }
        ])

        # install only into img1
        self._pkg([1, 2, 3], "uninstall {0}".format(self.foo1_list[0]))
        self._recursive_pkg("install -z system:img1", self.foo1_list[0],
            child_images=[{
                "image_name": "system:img1",
                "add_packages": [self.foo1_list[0]]
            }
        ])

        # install only into img1 and img3
        self._pkg([1], "uninstall {0}".format(self.foo1_list[0]))
        self._recursive_pkg("install -z system:img1 -z system:img3",
            self.foo1_list[0],
            child_images=[{
                "image_name": "system:img1",
                "add_packages": [self.foo1_list[0]]
            }, {
                "image_name": "system:img3",
                "add_packages": [self.foo1_list[0]]
            }
        ])

        # install into all but img1
        self._pkg([1, 3], "uninstall {0}".format(self.foo1_list[0]))
        self._recursive_pkg("install -Z system:img1", self.foo1_list[0],
            child_images=[{
                "image_name": "system:img2",
                "add_packages": [self.foo1_list[0]]
            }, {
                "image_name": "system:img3",
                "add_packages": [self.foo1_list[0]]
            }
        ])

        # install into all but img1 and img3
        self._pkg([2, 3], "uninstall {0}".format(self.foo1_list[0]))
        self._recursive_pkg("install -Z system:img1 -Z system:img3",
            self.foo1_list[0],
            child_images=[{
                "image_name": "system:img2",
                "add_packages": [self.foo1_list[0]]
            }
        ])

    def test_recursive_sync_install(self):
        """Test that child images not specified for explicit recursion
           are still getting synced when installing."""

        # create parent (0), push child (1,2)
        self._imgs_create(3)
        self._attach_child(0, [1, 2])

        # install synced package into each image
        self._pkg([0, 1, 2], "install -v {0}".format(self.p_sync1_name[2]))

        # install new version of synced pkg in parent and one child
        # explicitly, second child should get synced too
        self._recursive_pkg("install -z system:img1",
            self.p_sync1_name[1],
            change_packages=[[self.s1_list[2], self.s1_list[1]]],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [[self.s1_list[2], self.s1_list[1]]]
            }, {
                "image_name": "system:img2",
                "change_packages": [[self.s1_list[2], self.s1_list[1]]]
            }
        ])

    def test_recursive_sync_update(self):
        """Test that child images not specified for explicit recursion
           are still getting synced when updating."""

        # create parent (0), push child (1,2)
        self._imgs_create(3)
        self._attach_child(0, [1, 2])

        # install synced package into each image
        self._pkg([0, 1, 2], "install -v {0}".format(self.p_sync1_name[2]))

        # install new version of synced pkg in parent and one child
        # explicitly, second child should get synced too
        self._recursive_pkg("update -z system:img1", "",
            change_packages=[[self.s1_list[2], self.s1_list[0]]],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [[self.s1_list[2], self.s1_list[0]]]
            }, {
                "image_name": "system:img2",
                "change_packages": [[self.s1_list[2], self.s1_list[0]]]
            }
        ])

    def test_recursive_sync_update_pkg(self):
        """Test that child images not specified for explicit recursion
           are still getting synced when updating a particular pkg."""

        # create parent (0), push child (1,2)
        self._imgs_create(3)
        self._attach_child(0, [1, 2])

        # install synced package into each image
        self._pkg([0, 1, 2], "install -v {0}".format(self.p_sync1_name[2]))

        # install new version of synced pkg in parent and one child
        # explicitly, second child should get synced too
        self._recursive_pkg("update -z system:img1",
            self.p_sync1_name[1],
            change_packages=[[self.s1_list[2], self.s1_list[1]]],
            child_images=[{
                "image_name": "system:img1",
                "change_packages": [[self.s1_list[2], self.s1_list[1]]]
            }, {
                "image_name": "system:img2",
                "change_packages": [[self.s1_list[2], self.s1_list[1]]]
            }
        ])

    def test_recursive_uninstall_synced_pkg(self):
        """Test that we can uninstall a synced package from all images
           with -r."""

        # create parent (0), push child (1,2)
        self._imgs_create(3)
        self._attach_child(0, [1, 2])

        # install synced package into each image
        self._pkg([0, 1, 2], "install -v {0}".format(self.p_sync1_name[2]))

        # uninstall synced pkg from all images
        self._recursive_pkg("uninstall", self.p_sync1_name[2],
            remove_packages=[self.s1_list[2]],
            child_images=[{
                "image_name": "system:img1",
                "remove_packages": [self.s1_list[2]]
            }, {
                "image_name": "system:img2",
                "remove_packages": [self.s1_list[2]]
            }
        ])

    def test_recursive_idr_removal(self):
        """Test if IDR handling with linked images works as intended."""

        pkgs = (
                """
                            open kernel@1.0,5.11-0.1
                            add depend type=require fmri=pkg:/incorp
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open kernel@1.0,5.11-0.2
                            add depend type=require fmri=pkg:/incorp
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open network@1.0,5.11-0.1
                            add depend type=require fmri=pkg:/incorp
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open network@1.0,5.11-0.2
                            add depend type=require fmri=pkg:/incorp
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open incorp@1.0,5.11-0.1
                            add depend type=incorporate fmri=kernel@1.0,5.11-0.1
                            add depend type=incorporate fmri=network@1.0,5.11-0.1
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                 """
                            open incorp@1.0,5.11-0.2
                            add depend type=incorporate fmri=kernel@1.0,5.11-0.2
                            add depend type=incorporate fmri=network@1.0,5.11-0.2
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open kernel@1.0,5.11-0.1.1.0
                            add depend type=require fmri=pkg:/incorp
                            add depend type=require fmri=pkg:/idr1
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open kernel@1.0,5.11-0.1.1.1
                            add depend type=require fmri=pkg:/incorp
                            add depend type=require fmri=pkg:/idr1
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open kernel@1.0,5.11-0.1.2.0
                            add depend type=require fmri=pkg:/incorp
                            add depend type=require fmri=pkg:/idr2
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open network@1.0,5.11-0.1.1.0
                            add depend type=require fmri=pkg:/incorp
                            add depend type=require fmri=pkg:/idr1
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open network@1.0,5.11-0.1.1.1
                            add depend type=require fmri=pkg:/incorp
                            add depend type=require fmri=pkg:/idr1
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open network@1.0,5.11-0.1.2.0
                            add depend type=require fmri=pkg:/incorp
                            add depend type=require fmri=pkg:/idr2
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open idr1@1.0,5.11-0.1.1.0
                            add depend type=incorporate fmri=kernel@1.0,5.11-0.1.1.0
                            add depend type=incorporate fmri=network@1.0,5.11-0.1.1.0
                            add depend type=require fmri=idr1_entitlement
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open idr1@1.0,5.11-0.1.1.1
                            add depend type=incorporate fmri=kernel@1.0,5.11-0.1.1.1
                            add depend type=incorporate fmri=network@1.0,5.11-0.1.1.1
                            add depend type=require fmri=idr1_entitlement
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open idr2@1.0,5.11-0.1.2.0
                            add depend type=incorporate fmri=kernel@1.0,5.11-0.1.2.0
                            add depend type=incorporate fmri=network@1.0,5.11-0.1.2.0
                            add depend type=require fmri=idr2_entitlement
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open idr1_entitlement@1.0,5.11-0
                            add depend type=exclude fmri=no-idrs
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                """
                            open idr2_entitlement@1.0,5.11-0
                            add depend type=exclude fmri=no-idrs
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),

                # hack to prevent idrs from being installed from repo...

                """
                            open no-idrs@1.0,5.11-0
                            add depend type=parent fmri={0}
                            close """.format(pkg.actions.depend.DEPEND_SELF),
        )

        # publish additional idr packages
        self.pkgsend_bulk(self.rurl1, pkgs)

        # create parent (0), push child (1,2)
        self._imgs_create(3)
        self._attach_child(0, [1, 2])

        # install kernel pkg; remember version so we can reinstall it
        # later
        self._pkg([0, 1, 2], "install -v no-idrs")
        # install kernel package into all images
        self._pkg([0, 1 , 2], "install -v kernel@1.0,5.11-0.1")
        self._pkg([0], "list -Hv kernel@1.0,5.11-0.1 | "
            "/usr/bin/awk '{print $1}'")
        kernel_fmri = self.output.strip()
        # install network package only in parent and one child
        self._pkg([0, 1], "install -v network@1.0,5.11-0.1")
        self._pkg([0], "list -Hv network@1.0,5.11-0.1 | "
            "/usr/bin/awk '{print $1}'")
        network_fmri = self.output.strip()
        self._pkg([2], "list network", rv=EXIT_OOPS)

        # upgrade to next version w/o encountering idrs, children should
        # be updated automatically.
        self._pkg([0], "update -v")
        self._pkg([0, 1, 2], "list kernel@1.0,5.11-0.2")
        self._pkg([0, 1], "list network@1.0,5.11-0.2")
        self._pkg([2], "list network", rv=EXIT_OOPS)

        # try installing idr1; testing wild card support and -z as well
        self._pkg([0], "uninstall -r no-idrs")
        self._pkg([0], "install -r "
            "--reject 'k*' --reject 'i*' --reject network no-idrs")
        self._pkg([0], "install -r -v kernel@1.0,5.11-0.1")
        self._pkg([0], "install -v -r -z system:img1 "
            "network@1.0,5.11-0.1")

        self._pkg([0], "install -r -v --reject no-idrs "
            "idr1_entitlement")
        self._pkg([0], "install -r -v idr1@1.0,5.11-0.1.1.0")
        self._pkg([0], "update -r -v --reject idr2")
        self._pkg([0, 1, 2], "list idr1@1.0,5.11-0.1.1.1")

        # switch to idr2, which affects same package
        self._pkg([0], "install -r -v --reject idr1 --reject 'idr1_*' "
            "idr2 idr2_entitlement")

        # switch back to base version of kernel and network
        self._pkg([0], "update -v -r "
            "--reject idr2 --reject 'idr2_*' {0} {1}".format(kernel_fmri,
            network_fmri))

        # reinstall idr1, then update to version 2 of base kernel
        self._pkg([0], "install -r -v "
            "idr1@1.0,5.11-0.1.1.0 idr1_entitlement")
        self._pkg([0, 1, 2], "list kernel@1.0,5.11-0.1.1.0")
        self._pkg([0, 1], "list network@1.0,5.11-0.1.1.0")
        self._pkg([2], "list network", rv=EXIT_OOPS)

        # Wildcards are purposefully used here for both patterns to
        # ensure pattern matching works as expected for update.
        self._pkg([0], "update -r -v "
            "--reject 'idr1*' '*incorp@1.0-0.2'")
        self._pkg([0, 1, 2], "list kernel@1.0,5.11-0.2")
        self._pkg([0, 1], "list network@1.0,5.11-0.2")
        self._pkg([2], "list network", rv=EXIT_OOPS)


class TestPkgLinkedIncorpDowngrade(TestPkgLinked):
    """Test that incorporated pkgs can be downgraded if incorporation is
    updated."""

    pkgs = (
            """
                    open incorp@1.0,5.11-0.1
                    add depend type=incorporate fmri=A@2
                    add depend type=parent fmri={0}
                    close """.format(pkg.actions.depend.DEPEND_SELF),
            """
                    open incorp@2.0,5.11-0.1
                    add depend type=incorporate fmri=A@1
                    add depend type=parent fmri={0}
                    close """.format(pkg.actions.depend.DEPEND_SELF),
            """
                    open A@1.0,5.11-0.1
                    add depend type=require fmri=pkg:/incorp
                    close """,
            """
                    open A@2.0,5.11-0.1
                    add depend type=require fmri=pkg:/incorp
                    close """,
    )

    def setUp(self):
        self.i_count = 3
        pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
            image_count=self.i_count)

        # get repo url
        self.rurl1 = self.dcs[1].get_repo_url()

        # setup image names and paths
        self.i_name = []
        self.i_path = []
        self.i_api = []
        self.i_api_reset = []
        for i in range(self.i_count):
            name = "system:img{0:d}".format(i)
            self.i_name.insert(i, name)
            self.i_path.insert(i, self.img_path(i))

        self.pkgsend_bulk(self.rurl1, self.pkgs)

    def test_incorp_downgrade(self):
        """Test that incorporated pkgs can be downgraded if
        incorporation is updated."""

        # create parent (0), push child (1, 2)
        self._imgs_create(3)
        self._attach_child(0, [1, 2])

        self._pkg([0, 1, 2], "install -v incorp@1 A")
        self._pkg([0, 1, 2], "list A@2")
        self._pkg([0], "update -v incorp@2")
        self._pkg([0, 1, 2], "list A@1")


class TestFacetInheritance(TestPkgLinked):
    """Class to test facet inheritance between images.

    These tests focus specifically on facet propagation from parent to
    child images, masked facet handling, and facet reporting.  These tests
    do not attempt to verify that the packaging system correctly handles
    operations when facets and packages are changing at the same time."""

    p_files = [
        "tmp/foo1",
        "tmp/foo2",
        "tmp/foo3",
        "tmp/sync1",
        "tmp/sync2",
        "tmp/sync3",
    ]
    p_foo_template = """
            open foo@{ver:d}
            add file tmp/foo1 mode=0555 owner=root group=bin path=foo1_foo1 facet.foo1=true
            add file tmp/foo2 mode=0555 owner=root group=bin path=foo1_foo2 facet.foo2=true
            add file tmp/foo3 mode=0555 owner=root group=bin path=foo1_foo3 facet.foo3=true
            close"""
    p_sync1_template = """
            open sync1@{ver:d}
            add file tmp/sync1 mode=0555 owner=root group=bin path=sync1_sync1 facet.sync1=true
            add file tmp/sync2 mode=0555 owner=root group=bin path=sync1_sync2 facet.sync2=true
            add file tmp/sync3 mode=0555 owner=root group=bin path=sync1_sync3 facet.sync3=true
            add depend type=parent fmri=feature/package/dependency/self
            close"""
    p_sync2_template = """
            open sync2@{ver:d}
            add file tmp/sync1 mode=0555 owner=root group=bin path=sync2_sync1 facet.sync1=true
            add file tmp/sync2 mode=0555 owner=root group=bin path=sync2_sync2 facet.sync2=true
            add file tmp/sync3 mode=0555 owner=root group=bin path=sync2_sync3 facet.sync3=true
            add depend type=parent fmri=feature/package/dependency/self
            close"""
    p_inc1_template = """
            open inc1@{ver:d}
            add depend type=require fmri=sync1
            add depend type=incorporate fmri=sync1@{ver:d} facet.123456=true
            add depend type=parent fmri=feature/package/dependency/self
            close"""
    p_inc2_template = """
            open inc2@{ver:d}
            add depend type=require fmri=sync2
            add depend type=incorporate fmri=sync2@{ver:d} facet.456789=true
            add depend type=parent fmri=feature/package/dependency/self
            close"""

    p_data_template = [
        p_foo_template,
        p_sync1_template,
        p_sync2_template,
        p_inc1_template,
        p_inc2_template,
    ]
    p_data = []
    for i in range(2):
        for j in p_data_template:
            p_data.append(j.format(ver=(i + 1)))
    p_fmri = {}

    def setUp(self):
        self.i_count = 3
        pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
            image_count=self.i_count)

        # create files that go in packages
        self.make_misc_files(self.p_files)

        # get repo url
        self.rurl1 = self.dcs[1].get_repo_url()

        # populate repository
        for p in self.p_data:
            fmristr = self.pkgsend_bulk(self.rurl1, p)[0]
            f = fmri.PkgFmri(fmristr)
            pkgstr = "{0}@{1}".format(f.pkg_name, f.version.release)
            self.p_fmri[pkgstr] = fmristr

        # setup image names and paths
        self.i_name = []
        self.i_path = []
        self.i_api = []
        self.i_api_reset = []
        for i in range(self.i_count):
            name = "system:img{0:d}".format(i)
            self.i_name.insert(i, name)
            self.i_path.insert(i, self.img_path(i))

    def test_facet_inheritance(self):
        """Verify basic facet inheritance functionality for both push
        and pull children."""

        # create parent (0), push child (1), and pull child (2)
        self._imgs_create(3)
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # install packages with inheritable facets in all images
        self._pkg([0, 1, 2], "install -v {0}".format(self.p_fmri["inc1@2"]))
        self._pkg([0, 1, 2], "install -v {0}".format(self.p_fmri["inc2@2"]))

        # verify that there are no facets set in any images
        self._pkg([0, 1, 2], "facet -H -F tsv", \
            output_cb=self._assertEqual_cb(""))

        # set some random facets and make sure they aren't inherited
        # or affected by inherited facets
        output = {}
        for i in [0, 1, 2]:
            i2 = i + 1
            self._pkg([i], "change-facet "
                "sync{0:d}=False foo{1:d}=True".format(i2, i2))
        for i in [0, 1, 2]:
            i2 = i + 1
            output = \
                "facet.foo{0:d}\tTrue\tlocal\n".format(i2) + \
                "facet.sync{0:d}\tFalse\tlocal\n".format(i2)
            self._pkg([i], "facet -H -F tsv", \
                output_cb=self._assertEqual_cb(output))

        # disable an inheritable facet and verify it gets inherited
        self._pkg([0], "change-facet 123456=False")
        self._pkg([2], "sync-linked")
        for i in [1, 2]:
            i2 = i + 1
            output = \
                "facet.123456\tFalse\tparent\n" + \
                "facet.foo{0:d}\tTrue\tlocal\n".format(i2) + \
                "facet.sync{0:d}\tFalse\tlocal\n".format(i2)
            self._pkg([i], "facet -H -F tsv", \
                output_cb=self._assertEqual_cb(output))

        # enable an inheritable facet and verify it doesn't get
        # inherited
        self._pkg([0], "change-facet 123456=True")
        self._pkg([2], "sync-linked")
        for i in [1, 2]:
            i2 = i + 1
            output = \
                "facet.foo{0:d}\tTrue\tlocal\n".format(i2) + \
                "facet.sync{0:d}\tFalse\tlocal\n".format(i2)
            self._pkg([i], "facet -H -F tsv", \
                output_cb=self._assertEqual_cb(output))

        # clear an inheritable facet and verify it doesn't get
        # inherited
        self._pkg([0], "change-facet 123456=False")
        self._pkg([2], "sync-linked")
        self._pkg([0], "change-facet 123456=None")
        self._pkg([2], "sync-linked")
        for i in [1, 2]:
            i2 = i + 1
            output = \
                "facet.foo{0:d}\tTrue\tlocal\n".format(i2) + \
                "facet.sync{0:d}\tFalse\tlocal\n".format(i2)
            self._pkg([i], "facet -H -F tsv", \
                output_cb=self._assertEqual_cb(output))

    def test_facet_inheritance_globs(self):
        """Verify that all facet glob patterns which affect
        inheritable facets get propagated to children."""

        # create parent (0), push child (1)
        self._imgs_create(2)
        self._attach_child(0, [1])

        self._pkg([0], "change-facet" +
            " 123456=False" +
            " 456789=True" +
            " *456*=False" +
            " *789=True" +
            " 123*=True")

        # verify that no facets are inherited
        output = ""
        self._pkg([1], "facet -H -F tsv", \
            output_cb=self._assertEqual_cb(output))

        # install packages with inheritable facets in the parent
        self._pkg([0], "install -v {0}".format(self.p_fmri["inc1@2"]))

        # verify that three facets are inherited
        output = ""
        output += "facet.*456*\tFalse\tparent\n"
        output += "facet.123*\tTrue\tparent\n"
        output += "facet.123456\tFalse\tparent\n"
        self._pkg([1], "facet -H -F tsv", \
            output_cb=self._assertEqual_cb(output))

        # install packages with inheritable facets in the parent
        self._pkg([0], "install -v {0}".format(self.p_fmri["inc2@2"]))

        # verify that five facets are inherited
        output = ""
        output += "facet.*456*\tFalse\tparent\n"
        output += "facet.*789\tTrue\tparent\n"
        output += "facet.123*\tTrue\tparent\n"
        output += "facet.123456\tFalse\tparent\n"
        output += "facet.456789\tTrue\tparent\n"
        self._pkg([1], "facet -H -F tsv", \
            output_cb=self._assertEqual_cb(output))

        # remove packages with inheritable facets in the parent
        self._pkg([0], "uninstall -v {0}".format(self.p_fmri["inc1@2"]))

        # verify that three facets are inherited
        output = ""
        output += "facet.*456*\tFalse\tparent\n"
        output += "facet.*789\tTrue\tparent\n"
        output += "facet.456789\tTrue\tparent\n"
        self._pkg([1], "facet -H -F tsv", \
            output_cb=self._assertEqual_cb(output))

        # remove packages with inheritable facets in the parent
        self._pkg([0], "uninstall -v {0}".format(self.p_fmri["inc2@2"]))

        # verify that no facets are inherited
        output = ""
        self._pkg([1], "facet -H -F tsv", \
            output_cb=self._assertEqual_cb(output))

    def test_facet_inheritance_masked_system(self):
        """Test reporting of system facets."""

        # create image (0)
        self._imgs_create(1)

        # install a package with facets in the image
        self._pkg([0], "install -v {0}".format(self.p_fmri["foo@2"]))

        # set a facet
        self._pkg([0], "change-facet 'f*1'=False")

        # verify masked output
        output_am  = \
            "facet.f*1\tFalse\tlocal\tFalse\n" + \
            "facet.foo1\tFalse\tlocal\tFalse\n" + \
            "facet.foo2\tTrue\tsystem\tFalse\n" + \
            "facet.foo3\tTrue\tsystem\tFalse\n"
        output_im  = \
            "facet.foo1\tFalse\tlocal\tFalse\n" + \
            "facet.foo2\tTrue\tsystem\tFalse\n" + \
            "facet.foo3\tTrue\tsystem\tFalse\n"
        self._pkg([0], "facet -H -F tsv -m -a", \
            output_cb=self._assertEqual_cb(output_am))
        self._pkg([0], "facet -H -F tsv -m -i", \
            output_cb=self._assertEqual_cb(output_im))

    def test_facet_inheritance_masked_preserve(self):
        """Test handling for masked facets

        Verify that pre-existing local facet settings which get masked
        by inherited facets get restored when the inherited facets go
        away."""

        # create parent (0), push child (1), and pull child (2)
        self._imgs_create(3)
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # install a package with inheritable facets in the parent
        self._pkg([0], "install -v {0}".format(self.p_fmri["inc1@2"]))

        for fv in ["True", "False"]:

            # set inheritable facet locally in children
            self._pkg([1, 2], "change-facet 123456={0}".format(fv))

            # disable inheritable facet in parent
            self._pkg([0], "change-facet 123456=False")
            self._pkg([2], "sync-linked")

            # verify inheritable facet is disabled in children
            output = "facet.123456\tFalse\tparent\n"
            output_m = \
                "facet.123456\tFalse\tparent\tFalse\n" + \
                "facet.123456\t{0}\tlocal\tTrue\n".format(fv)
            for i in [1, 2]:
                self._pkg([i], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(output))
                self._pkg([i], "facet -H -F tsv -m", \
                    output_cb=self._assertEqual_cb(output_m))

            # clear inheritable facet in the parent
            self._pkg([0], "change-facet 123456=None")
            self._pkg([2], "sync-linked")

            # verify the local child setting is restored
            output = "facet.123456\t{0}\tlocal\n".format(fv)
            output_m = "facet.123456\t{0}\tlocal\tFalse\n".format(fv)
            for i in [1, 2]:
                self._pkg([i], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(output))
                self._pkg([i], "facet -H -F tsv -m", \
                    output_cb=self._assertEqual_cb(output_m))

    def test_facet_inheritance_masked_update(self):
        """Test handling for masked facets.

        Verify that local facet changes can be made while inherited
        facets masking the local settings exist."""

        # create parent (0), push child (1), and pull child (2)
        self._imgs_create(3)
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # install a package with inheritable facets in the parent
        self._pkg([0], "install -v {0}".format(self.p_fmri["inc1@2"]))

        # disable inheritable facet in parent
        self._pkg([0], "change-facet 123456=False")
        self._pkg([2], "sync-linked")

        # clear inheritable facet in children
        # the facet is not set in the child so this is a noop
        self._pkg([1, 2], "change-facet 123456=None", rv=EXIT_NOP)

        # verify inheritable facet is disabled in children
        output = "facet.123456\tFalse\tparent\n"
        output_m = "facet.123456\tFalse\tparent\tFalse\n"
        for i in [1, 2]:
            self._pkg([i], "facet -H -F tsv", \
                output_cb=self._assertEqual_cb(output))
            self._pkg([i], "facet -H -F tsv -m", \
                output_cb=self._assertEqual_cb(output_m))

        for fv in ["True", "False"]:

            # set inheritable facet locally in children
            self._pkg([1, 2], "change-facet 123456={0}".format(fv))

            # verify inheritable facet is disabled in children
            output = "facet.123456\tFalse\tparent\n"
            output_m = \
                "facet.123456\tFalse\tparent\tFalse\n" + \
                "facet.123456\t{0}\tlocal\tTrue\n".format(fv)
            for i in [1, 2]:
                self._pkg([i], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(output))
                self._pkg([i], "facet -H -F tsv -m", \
                    output_cb=self._assertEqual_cb(output_m))

            # re-set inheritable facet locall in children
            # this is a noop
            self._pkg([1, 2], "change-facet 123456={0}".format(fv),
                rv=EXIT_NOP)

            # clear inheritable facet in the parent
            self._pkg([0], "change-facet 123456=None")
            self._pkg([2], "sync-linked")

            # verify the local child setting is restored
            output = "facet.123456\t{0}\tlocal\n".format(fv)
            output_m = "facet.123456\t{0}\tlocal\tFalse\n".format(fv)
            for i in [1, 2]:
                self._pkg([i], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(output))
                self._pkg([i], "facet -H -F tsv -m", \
                    output_cb=self._assertEqual_cb(output_m))

            # disable inheritable facet in parent
            self._pkg([0], "change-facet 123456=False")
            self._pkg([2], "sync-linked")

        # clear inheritable facet locally in children
        self._pkg([1, 2], "change-facet 123456=None")

        # verify inheritable facet is disabled in children
        output = "facet.123456\tFalse\tparent\n"
        output_m = "facet.123456\tFalse\tparent\tFalse\n"
        for i in [1, 2]:
            self._pkg([i], "facet -H -F tsv", \
                output_cb=self._assertEqual_cb(output))
            self._pkg([i], "facet -H -F tsv -m", \
                output_cb=self._assertEqual_cb(output_m))

        # re-clear inheritable facet locally in children
        # this is a noop
        self._pkg([1, 2], "change-facet 123456=None", rv=EXIT_NOP)

        # clear inheritable facet in the parent
        self._pkg([0], "change-facet 123456=None")
        self._pkg([2], "sync-linked")

        # verify the local child setting is restored
        for i in [1, 2]:
            self._pkg([i], "facet -H -F tsv", \
                output_cb=self._assertEqual_cb(""))
            self._pkg([i], "facet -H -F tsv -m", \
                output_cb=self._assertEqual_cb(""))

    def __test_facet_inheritance_via_op(self, op):
        """Verify that if we do a an "op" operation, the latest facet
        data gets pushed/pulled to child images."""

        # create parent (0), push child (1), and pull child (2)
        self._imgs_create(3)
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # install synced incorporations
        self._pkg([0, 1, 2], "install -v {0} {1}".format(
            self.p_fmri["inc1@1"], self.p_fmri["foo@1"]))

        # disable a random facet in all images
        self._pkg([0, 1, 2], "change-facet -I foo=False")

        # disable an inheritable facet in the parent while ignoring
        # children.
        self._pkg([0], "change-facet -I 123456=False")

        # verify that the change hasn't been propagated to the child
        output = "facet.foo\tFalse\tlocal\n"
        self._pkg([1, 2], "facet -H -F tsv",
            output_cb=self._assertEqual_cb(output))

        # do "op" in the parent and verify the latest facet data was
        # pushed to the child
        self._pkg([0], op)
        output  = "facet.123456\tFalse\tparent\n"
        output += "facet.foo\tFalse\tlocal\n"
        self._pkg([1], "facet -H -F tsv",
            output_cb=self._assertEqual_cb(output))

        # do "op" in the child and verify the latest facet data was
        # pulled from the parent.
        self._pkg([2], op)
        output  = "facet.123456\tFalse\tparent\n"
        output += "facet.foo\tFalse\tlocal\n"
        self._pkg([2], "facet -H -F tsv",
            output_cb=self._assertEqual_cb(output))

    def test_facet_inheritance_via_noop_update(self):
        """Verify that if we do a noop update operation, the
        latest facet data still gets pushed/pulled to child images."""

        self.__test_facet_inheritance_via_op(
            "update")

    def test_facet_inheritance_via_noop_install(self):
        """Verify that if we do a noop install operation, the
        latest facet data still gets pushed/pulled to child images."""

        self.__test_facet_inheritance_via_op(
            "install -v {0}".format(self.p_fmri["inc1@1"]))

    def test_facet_inheritance_via_noop_change_facet(self):
        """Verify that if we do a noop change-facet operation on a
        parent image, the latest facet data still gets pushed out to
        child images."""

        self.__test_facet_inheritance_via_op(
            "change-facet foo=False")

    def test_facet_inheritance_via_uninstall(self):
        """Verify that if we do an uninstall operation on a
        parent image, the latest facet data still gets pushed out to
        child images."""

        self.__test_facet_inheritance_via_op(
            "uninstall -v {0}".format(self.p_fmri["foo@1"]))

    def test_facet_inheritance_cleanup_via_detach(self):
        """Verify that if we detach a child linked image, that any
        inherited facets go away."""

        # create parent (0), push child (1), and pull child (2)
        self._imgs_create(3)
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # install synced incorporations
        self._pkg([0, 1, 2], "install -v {0} {1}".format(
            self.p_fmri["inc1@1"], self.p_fmri["foo@1"]))

        # disable a random facet in all images
        self._pkg([0, 1, 2], "change-facet -I foo=False")

        # disable an inheritable facet in the parent and make sure the
        # change propagates to all children
        self._pkg([0], "change-facet 123456=False")
        self._pkg([2], "sync-linked")
        output  = "facet.123456\tFalse\tparent\n"
        output += "facet.foo\tFalse\tlocal\n"
        self._pkg([1, 2], "facet -H -F tsv",
            output_cb=self._assertEqual_cb(output))

        # simulate detaching children via metadata only
        # verify the inherited facets don't get removed
        self._pkg([0], "detach-linked --linked-md-only -n -l {0}".format(
            self.i_name[1]))
        self._pkg([2], "detach-linked --linked-md-only -n")
        self._pkg([1, 2], "facet -H -F tsv",
            output_cb=self._assertEqual_cb(output))

        # simulate detaching children
        # verify the inherited facets don't get removed
        self._pkg([0], "detach-linked -n -l {0}".format(self.i_name[1]))
        self._pkg([2], "detach-linked -n")
        self._pkg([1, 2], "facet -H -F tsv",
            output_cb=self._assertEqual_cb(output))

        # detach children via metadata only
        # verify the inherited facets don't get removed
        # (they can't get removed until we modify the image)
        self._pkg([0], "detach-linked --linked-md-only -l {0}".format(
            self.i_name[1]))
        self._pkg([2], "detach-linked --linked-md-only")
        self._pkg([1, 2], "facet -H -F tsv",
            output_cb=self._assertEqual_cb(output))

        # re-attach children and sanity check facets
        self._attach_child(0, [1])
        self._attach_parent([2], 0)
        self._pkg([1, 2], "facet -H -F tsv",
            output_cb=self._assertEqual_cb(output))

        # try to detach children with --no-pkg-updates
        # verify this fails
        # (removal of inherited facets is the equilivant of a
        # change-facet operation, which requires updating all
        # packages, but since we've specified no pkg updates this must
        # fail.)
        self._pkg([0], "detach-linked --no-pkg-updates -l {0}".format(
            self.i_name[1]), rv=EXIT_OOPS)
        self._pkg([2], "detach-linked --no-pkg-updates", rv=EXIT_OOPS)
        self._pkg([1, 2], "facet -H -F tsv",
            output_cb=self._assertEqual_cb(output))

        # detach children
        # verify the inherited facets get removed
        self._pkg([0], "detach-linked -l {0}".format(self.i_name[1]))
        self._pkg([2], "detach-linked")
        output = "facet.foo\tFalse\tlocal\n"
        self._pkg([1, 2], "facet -H -F tsv",
            output_cb=self._assertEqual_cb(output))

    def __test_missing_facet_inheritance_metadata(self, pfacets="",
        cfacet_output=""):
        """Verify that we can manipulate and update linked child
        images which are missing their parent facet metadata.  Also
        verify that when we update those children the metadata gets
        updated correctly."""

        # create parent (0), push child (1), and pull child (2)
        self._imgs_create(3)
        self._attach_child(0, [1])
        self._attach_parent([2], 0)

        # paths for the linked image metadata files
        md_files = [
                "{0}/var/pkg/linked/linked_pfacets".format(self.i_path[i])
                for i in [1, 2]
        ]

        # isntall foo into each image
        self._pkg([0], "install -v {0}".format(self.p_fmri["foo@1"]))

        # install synced incorporation and package
        self._pkg([0], "install -v {0}".format(self.p_fmri["inc1@1"]))
        self._pkg([2], "sync-linked")

        if pfacets:
            self._pkg([0], "change-facet {0}".format(pfacets))
            self._pkg([2], "sync-linked")

        # verify the child facet settings
        self._pkg([1, 2], "facet -H -F tsv", \
            output_cb=self._assertEqual_cb(cfacet_output))

        # verify that the child images are in sync.
        # verify that a sync-linked is a noop
        self._pkg([0], "audit-linked -a")
        self._pkg([1, 2], "audit-linked")
        self._pkg([0], "sync-linked -a -n", rv=EXIT_NOP)
        self._pkg([2], "sync-linked -n", rv=EXIT_NOP)

        # delete linked image metadata files
        for f in md_files:
            self.file_exists(f)
            self._ccmd("rm {0}".format(f))

        # verify the child facet settings
        self._pkg([1, 2], "facet -H -F tsv", \
            output_cb=self._assertEqual_cb(cfacet_output))

        # verify that audit-linked can handle missing metadata.
        self._pkg([0], "audit-linked -a")
        self._pkg([1, 2], "audit-linked")
        self._pkg([2], "audit-linked --no-parent-sync")

        # verify that sync-linked can handle missing metadata.
        # also verify that the operation will succeed and is
        # not a noop (since it needs to update the metadata).
        self._pkg([0], "sync-linked -a -n")
        self._pkg([2], "sync-linked -n")

        # since we haven't modified the image, make sure the
        # facet metadata files weren't re-created.
        for f in md_files:
            self.file_doesnt_exist(f)

        # do a sync and verify that the files get created
        self._pkg([0], "sync-linked -a")
        self._pkg([2], "sync-linked")
        for f in md_files:
            self.file_exists(f)

    def test_missing_facet_inheritance_metadata_1(self):
        """Verify that we can manipulate and update linked child
        images which are missing their parent facet metadata.  Also
        verify that when we update those children the metadata gets
        updated correctly.

        Test when there are no inherited facets present."""
        self.__test_missing_facet_inheritance_metadata()

    def test_missing_facet_inheritance_metadata_2(self):
        """Verify that we can manipulate and update linked child
        images which are missing their parent facet metadata.  Also
        verify that when we update those children the metadata gets
        updated correctly.

        Test with inherited facets present"""
        self.__test_missing_facet_inheritance_metadata(
            pfacets="123456=False",
            cfacet_output="facet.123456\tFalse\tparent\n")


class TestConcurrentFacetChange(TestPkgLinked):
    """Class to test that packaging operations work correctly when facets
    are changing concurrently.

    These tests do not focus on verifying that facets are propagated
    correctly from parent to child images."""

    p_misc = """
            open misc@1,5.11-0
            close"""
    p_common = """
            open common@1,5.11-0
            close"""
    p_AA_sync_template = """
            open AA-sync@{ver:d},5.11-0
            add set name=variant.foo value=bar value=baz
            add depend type=require fmri=common
            add depend type=require fmri=A-incorp-sync
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            close"""
    p_AB_sync_template = """
            open AB-sync@{ver:d},5.11-0
            add set name=variant.foo value=bar value=baz
            add depend type=require fmri=common
            add depend type=require fmri=A-incorp-sync
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            close"""
    p_BA_template = """
            open BA@{ver:d},5.11-0
            add depend type=require fmri=common
            add depend type=require fmri=B-incorp-sync
            close"""
    p_CA_template = """
            open CA@{ver:d},5.11-0
            add depend type=require fmri=common
            add depend type=require fmri=C-incorp
            close"""
    p_A_incorp_sync_template = """
            open A-incorp-sync@{ver:d},5.11-0
            add set name=variant.foo value=bar value=baz
            add depend type=incorporate fmri=AA-sync@{ver:d} facet.AA-sync=true
            add depend type=incorporate fmri=AB-sync@{ver:d} facet.AA-sync=true
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            close"""
    p_B_incorp_sync_template = """
            open B-incorp-sync@{ver:d},5.11-0
            add set name=variant.foo value=bar value=baz
            add depend type=incorporate fmri=BA@{ver:d} facet.BA=true
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            close"""
    p_C_incorp_template = """
            open C-incorp@{ver:d},5.11-0
            add depend type=incorporate fmri=CA@{ver:d} facet.CA=true
            close"""
    p_entire_sync_template = """
            open entire-sync@{ver:d},5.11-0
            add set name=variant.foo value=bar value=baz
            add depend type=require fmri=A-incorp-sync
            add depend type=incorporate fmri=A-incorp-sync@{ver:d} \
                facet.A-incorp-sync=true
            add depend type=require fmri=B-incorp-sync
            add depend type=incorporate fmri=B-incorp-sync@{ver:d} \
                facet.B-incorp-sync=true
            add depend type=require fmri=C-incorp
            add depend type=incorporate fmri=C-incorp@{ver:d} \
                facet.C-incorp=true
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            close"""

    p_data_template = [
        p_AA_sync_template,
        p_AB_sync_template,
        p_BA_template,
        p_CA_template,
        p_A_incorp_sync_template,
        p_B_incorp_sync_template,
        p_C_incorp_template,
        p_entire_sync_template,
    ]

    p_data = [p_misc, p_common]
    for i in range(4):
        for j in p_data_template:
            p_data.append(j.format(ver=(i + 1)))
    p_fmri = {}

    def setUp(self):
        self.i_count = 2
        pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
            image_count=self.i_count)

        # get repo url
        self.rurl1 = self.dcs[1].get_repo_url()

        # populate repository
        for p in self.p_data:
            fmristr = self.pkgsend_bulk(self.rurl1, p)[0]
            f = fmri.PkgFmri(fmristr)
            pkgstr = "{0}@{1}".format(f.pkg_name, f.version.release)
            self.p_fmri[pkgstr] = fmristr

        # setup image names and paths
        self.i_name = []
        self.i_path = []
        self.i_api = []
        self.i_api_reset = []
        for i in range(self.i_count):
            name = "system:img{0:d}".format(i)
            self.i_name.insert(i, name)
            self.i_path.insert(i, self.img_path(i))

    def __test_concurrent_facet_change_via_child_op(self,
        op, op_args, extra_child_pkgs=None, child_variants=None,
        child_pre_op_audit=True, **kwargs):
        """Verify that if we do a operation "op" on a child image, it
        automatically brings its packages in sync with its parent."""

        # create parent (0) and pull child (1)
        self._imgs_create(2)

        # setup the parent image
        parent_facets = [
            "facet.AA-sync=False",
            "facet.A-incorp-sync=False",
            "facet.BA=False",
        ]
        parent_pkgs = [
            "A-incorp-sync@3",
            "AA-sync@4",
            "B-incorp-sync@2",
            "BA@3",
            "C-incorp@2",
            "CA@2",
            "entire-sync@2",
        ]
        self._pkg([0], "change-facet -v {0}".format(" ".join(parent_facets)))
        self._pkg([0], "install -v {0}".format(" ".join(parent_pkgs)))

        # setup the child image
        child_facets = [
            "facet.C*=False",
        ]
        child_pkgs = [
            "A-incorp-sync@1",
            "AA-sync@1",
            "B-incorp-sync@1",
            "BA@1",
            "C-incorp@1",
            "CA@1",
            "entire-sync@1",
        ]
        self._pkg([1], "change-facet -v {0}".format(" ".join(child_facets)))
        if child_variants is not None:
            self._pkg([1], "change-variant -v {0}".format(
                " ".join(child_variants)))
        self._pkg([1], "install -v {0}".format(" ".join(child_pkgs)))
        if extra_child_pkgs:
            self._pkg([1], "install -v {0}".format(
                " ".join(extra_child_pkgs)))

        # attach the child but don't sync it
        self._attach_parent([1], 0, args="--linked-md-only")

        # verify the child image is still diverged
        if child_pre_op_audit:
            self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)

        # try and then execute op
        def output_cb(output):
            self.assertEqualParsable(output, **kwargs)
        self._pkg([1], "{0} -nv {1}".format(op, op_args))
        self._pkg([1], "{0} --parsable=0 {1}".format(op, op_args),
            output_cb=output_cb)

        # verify sync via audit and sync (which should be a noop)
        self._pkg([1], "audit-linked")
        self._pkg([1], "sync-linked -v", rv=EXIT_NOP)

    def __pkg_names_to_fmris(self, remove_packages):
        """Convert a list of pkg names to fmris"""
        rv = []
        for s in remove_packages:
            rv.append(self.p_fmri[s])
        return rv

    def __pkg_name_tuples_to_fmris(self, change_packages):
        """Convert a list of pkg name tuples to fmris"""
        rv = []
        for s, d in change_packages:
            rv.append([self.p_fmri[s], self.p_fmri[d]])
        return rv

    def test_concurrent_facet_change_via_update(self):
        """Verify that we can update and sync a child
        image while inherited facets are changing."""

        change_facets = [
            ['facet.A-incorp-sync',
                False, None, 'parent', False, False],
            ['facet.AA-sync', False, None, 'parent', False, False],
        ]
        remove_packages = self.__pkg_names_to_fmris([
            "AB-sync@1",
        ])
        change_packages = self.__pkg_name_tuples_to_fmris([
            ["A-incorp-sync@1", "A-incorp-sync@3"],
            ["AA-sync@1",       "AA-sync@4"],
            ["B-incorp-sync@1", "B-incorp-sync@2"],
            ["BA@1",            "BA@2"],
            ["C-incorp@1",      "C-incorp@4"],
            ["CA@1",            "CA@4"],
            ["entire-sync@1",   "entire-sync@2"],
        ])
        self.__test_concurrent_facet_change_via_child_op(
            "update", "--reject AB-sync",
            extra_child_pkgs=["AB-sync@1"],
            change_facets=change_facets,
            remove_packages=remove_packages,
            change_packages=change_packages)

    def test_concurrent_facet_change_via_update_pkg(self):
        """Verify that we can update a package and sync a child
        image while inherited facets are changing."""

        change_facets = [
            ['facet.A-incorp-sync',
                False, None, 'parent', False, False],
            ['facet.AA-sync', False, None, 'parent', False, False],
        ]
        remove_packages = self.__pkg_names_to_fmris([
            "AB-sync@1",
        ])
        change_packages = self.__pkg_name_tuples_to_fmris([
            ["A-incorp-sync@1", "A-incorp-sync@3"],
            ["AA-sync@1",       "AA-sync@4"],
            ["B-incorp-sync@1", "B-incorp-sync@2"],
            ["BA@1",            "BA@2"],
            ["entire-sync@1",   "entire-sync@2"],
        ])

        # verify update pkg
        self.__test_concurrent_facet_change_via_child_op(
            "update", "--reject AB-sync common",
            extra_child_pkgs=["AB-sync@1"],
            change_facets=change_facets,
            remove_packages=remove_packages,
            change_packages=change_packages)

    def test_concurrent_facet_change_via_install(self):
        """Verify that we can install a package and sync a child
        image while inherited facets are changing."""

        change_facets = [
            ['facet.A-incorp-sync',
                False, None, 'parent', False, False],
            ['facet.AA-sync', False, None, 'parent', False, False],
        ]
        remove_packages = self.__pkg_names_to_fmris([
            "AB-sync@1",
        ])
        add_packages = self.__pkg_names_to_fmris([
            "misc@1",
        ])
        change_packages = self.__pkg_name_tuples_to_fmris([
            ["A-incorp-sync@1", "A-incorp-sync@3"],
            ["AA-sync@1",       "AA-sync@4"],
            ["B-incorp-sync@1", "B-incorp-sync@2"],
            ["BA@1",            "BA@2"],
            ["entire-sync@1",   "entire-sync@2"],
        ])
        self.__test_concurrent_facet_change_via_child_op(
            "install", "--reject AB-sync misc",
            extra_child_pkgs=["AB-sync@1"],
            change_facets=change_facets,
            remove_packages=remove_packages,
            add_packages=add_packages,
            change_packages=change_packages)

    def test_concurrent_facet_change_via_sync(self):
        """Verify that we can sync a child
        image while inherited facets are changing."""

        change_facets = [
            ['facet.A-incorp-sync',
                False, None, 'parent', False, False],
            ['facet.AA-sync', False, None, 'parent', False, False],
        ]
        remove_packages = self.__pkg_names_to_fmris([
            "AB-sync@1",
        ])
        change_packages = self.__pkg_name_tuples_to_fmris([
            ["A-incorp-sync@1", "A-incorp-sync@3"],
            ["AA-sync@1",       "AA-sync@4"],
            ["B-incorp-sync@1", "B-incorp-sync@2"],
            ["BA@1",            "BA@2"],
            ["entire-sync@1",   "entire-sync@2"],
        ])
        self.__test_concurrent_facet_change_via_child_op(
            "sync-linked", "--reject AB-sync",
            extra_child_pkgs=["AB-sync@1"],
            change_facets=change_facets,
            remove_packages=remove_packages,
            change_packages=change_packages)

    def test_concurrent_facet_change_via_uninstall(self):
        """Verify that we can uninstall a package and sync a child
        image while inherited facets are changing."""

        change_facets = [
            ['facet.A-incorp-sync',
                False, None, 'parent', False, False],
            ['facet.AA-sync', False, None, 'parent', False, False],
        ]
        remove_packages = self.__pkg_names_to_fmris([
            "AB-sync@1",
        ])
        change_packages = self.__pkg_name_tuples_to_fmris([
            ["A-incorp-sync@1", "A-incorp-sync@3"],
            ["AA-sync@1",       "AA-sync@4"],
            ["B-incorp-sync@1", "B-incorp-sync@2"],
            ["BA@1",            "BA@2"],
            ["entire-sync@1",   "entire-sync@2"],
        ])
        self.__test_concurrent_facet_change_via_child_op(
            "uninstall", "AB-sync",
            extra_child_pkgs=["AB-sync@1"],
            change_facets=change_facets,
            remove_packages=remove_packages,
            change_packages=change_packages)

    def test_concurrent_facet_change_via_change_variant(self):
        """Verify that we can change variants and sync a child
        image while inherited facets are changing."""

        change_facets = [
            ["facet.A-incorp-sync",
                False, None, "parent", False, False],
            ["facet.AA-sync", False, None, "parent", False, False],
        ]
        change_variants = [
            ["variant.foo", "bar"]
        ]
        change_packages = self.__pkg_name_tuples_to_fmris([
            ["A-incorp-sync@1", "A-incorp-sync@3"],
            ["AA-sync@1",       "AA-sync@4"],
            ["B-incorp-sync@1", "B-incorp-sync@2"],
            ["BA@1",            "BA@2"],
            ["entire-sync@1",   "entire-sync@2"],
        ])
        self.__test_concurrent_facet_change_via_child_op(
            "change-variant", "variant.foo=bar",
            child_variants=["variant.foo=baz"],
            child_pre_op_audit=False,
            change_facets=change_facets,
            change_variants=change_variants,
            change_packages=change_packages)

    def test_concurrent_facet_change_via_change_facets(self):
        """Verify that we can change facets and sync a child
        image while inherited facets are changing."""

        change_facets = [
            ["facet.A-incorp-sync",
                False, None, "parent", False, False],
            ["facet.AA-sync", False, None, "parent", False, False],
            ["facet.C-incorp", True, None, "local", False, False],
        ]
        change_packages = self.__pkg_name_tuples_to_fmris([
            ["A-incorp-sync@1", "A-incorp-sync@3"],
            ["AA-sync@1",       "AA-sync@4"],
            ["B-incorp-sync@1", "B-incorp-sync@2"],
            ["BA@1",            "BA@2"],
            ["C-incorp@1",      "C-incorp@2"],
            ["entire-sync@1",   "entire-sync@2"],
        ])
        self.__test_concurrent_facet_change_via_child_op(
            "change-facet", "facet.C-incorp=True",
            change_facets=change_facets,
            change_packages=change_packages)

    def test_concurrent_facet_change_via_detach(self):
        """Verify that we can detach a child image which has inherited
        facets that when removed require updating the image."""

        # create parent (0) and pull child (1)
        self._imgs_create(2)

        # setup the parent image
        parent_facets = [
            "facet.AA-sync=False",
            "facet.A-incorp-sync=False",
        ]
        parent_pkgs = [
            "A-incorp-sync@2",
            "AA-sync@1",
            "B-incorp-sync@3",
            "BA@3",
            "C-incorp@3",
            "CA@3",
            "entire-sync@3",
        ]
        self._pkg([0], "change-facet -v {0}".format(" ".join(parent_facets)))
        self._pkg([0], "install -v {0}".format(" ".join(parent_pkgs)))

        # attach the child.
        self._attach_parent([1], 0)

        # setup the child image
        child_facets = [
            "facet.C*=False",
        ]
        child_pkgs = [
            "A-incorp-sync@2",
            "AA-sync@1",
            "B-incorp-sync@3",
            "BA@3",
            "C-incorp@2",
            "CA@2",
            "entire-sync@3",
        ]
        self._pkg([1], "change-facet -v {0}".format(" ".join(child_facets)))
        self._pkg([1], "install -v {0}".format(" ".join(child_pkgs)))

        # a request to detach the child without any package updates
        # should fail.
        self._pkg([1], "detach-linked -v --no-pkg-updates",
            rv=EXIT_OOPS)

        # detach the child
        self._pkg([1], "detach-linked -v")

        # verify the contents of the child image
        child_fmris = self.__pkg_names_to_fmris([
            "A-incorp-sync@3",
            "AA-sync@3",
            "B-incorp-sync@3",
            "BA@3",
            "C-incorp@2",
            "CA@2",
            "entire-sync@3",
        ])
        self._pkg([1], "list -v {0}".format(" ".join(child_fmris)))
        output  = "facet.C*\tFalse\tlocal\n"
        self._pkg([1], "facet -H -F tsv",
            output_cb=self._assertEqual_cb(output))


class TestLinkedInstallHoldRelax(TestPkgLinked):
    """Class to test automatic install-hold relaxing of constrained
    packages when doing different packaging operations.

    When performing packaging operations, any package that has an install
    hold, but also has dependency on itself in its parent, must have that
    install hold relaxed if we expect to be able to bring the image in
    sync with its parent."""

    # the "common" package exists because the solver ignores
    # install-holds unless the package containing them depends on a
    # specific version of another package.  so all our packages depend on
    # the "common" package.
    p_common = """
            open common@1,5.11-0
            close"""
    p_A_template = """
            open A@{ver:d},5.11-0
            add set name=pkg.depend.install-hold value=A
            add depend type=require fmri=common
            add depend type=incorporate fmri=common@1
            close"""
    p_B_template = """
            open B@{ver:d},5.11-0
            add set name=variant.foo value=bar value=baz
            add set name=pkg.depend.install-hold value=B
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            add depend type=require fmri=common
            add depend type=incorporate fmri=common@1
            close"""
    p_C_template = """
            open C@{ver:d},5.11-0
            add set name=pkg.depend.install-hold value=C
            add depend type=require fmri=common
            add depend type=incorporate fmri=common@1
            close"""
    p_BB_template = """
            open BB@{ver:d},5.11-0
            add depend type=require fmri=B
            add depend type=incorporate fmri=B@{ver:d}
            close"""
    p_BC_template = """
            open BC@{ver:d},5.11-0
            add depend type=require fmri=B
            add depend type=incorporate fmri=B@{ver:d}
            add depend type=require fmri=C
            add depend type=incorporate fmri=C@{ver:d}
            close"""

    p_data_template = [
        p_A_template,
        p_B_template,
        p_C_template,
        p_BB_template,
        p_BC_template,
    ]
    p_data = [p_common]
    for i in range(4):
        for j in p_data_template:
            p_data.append(j.format(ver=(i + 1)))
    p_fmri = {}

    def setUp(self):
        self.i_count = 2
        pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
            image_count=self.i_count)

        # get repo url
        self.rurl1 = self.dcs[1].get_repo_url()

        # populate repository
        for p in self.p_data:
            fmristr = self.pkgsend_bulk(self.rurl1, p)[0]
            f = fmri.PkgFmri(fmristr)
            pkgstr = "{0}@{1}".format(f.pkg_name, f.version.release)
            self.p_fmri[pkgstr] = fmristr

        # setup image names and paths
        self.i_name = []
        self.i_path = []
        self.i_api = []
        self.i_api_reset = []
        for i in range(self.i_count):
            name = "system:img{0:d}".format(i)
            self.i_name.insert(i, name)
            self.i_path.insert(i, self.img_path(i))

    def __test_linked_install_hold_relax(self, child_pkgs, op, op_args,
        op_rv=EXIT_OK, variant_out_parent_dep=False, **kwargs):
        """Verify that all install-holds get relaxed during
        sync-linked operations."""

        # create parent (0), and pull child (1)
        self._imgs_create(2)

        # install B@2 in the parent
        self._pkg([0], "install -v B@2")

        # install A@1 and B@1 in the child
        self._pkg([1], "install -v {0}".format(child_pkgs))

        # the parent dependency only exists under variant.foo=bar, if
        # we change variant.foo the parent dependency should go away.
        if variant_out_parent_dep:
            self._pkg([1], "change-variant variant.foo=baz")

        # link the two images without syncing packages
        self._attach_parent([1], 0, args="--linked-md-only")

        if variant_out_parent_dep:
            # verify the child is synced
            self._pkg([1], "audit-linked", rv=EXIT_OK)
        else:
            # verify the child is diverged
            self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)

        # execute op
        def output_cb(output):
            if op_rv == EXIT_OK:
                self.assertEqualParsable(output, **kwargs)
        self._pkg([1], "{0} --parsable=0 {1}".format(op, op_args),
            rv=op_rv, output_cb=output_cb)

    def test_linked_install_hold_relax_all(self):
        """Verify that all install-holds get relaxed during
        sync-linked operations."""

        # verify that sync-linked operation relaxes the install-hold
        # in B and syncs it.
        self.__test_linked_install_hold_relax(
            "A@1 B@1", "sync-linked", "",
            change_packages=[
                [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

        # if we remove the parent dependency in B it should no longer
        # change during sync-linked operation.
        self.__test_linked_install_hold_relax(
            "BC@1", "sync-linked", "", op_rv=EXIT_NOP,
            variant_out_parent_dep=True)

    def test_linked_install_hold_relax_constrained_1(self):
        """Verify that any install-holds which are associated with
        constrained packages (ie, packages with parent dependencies)
        get relaxed during install, uninstall and similar
        operations.

        In our child image we'll install 3 packages, A, B, C, all at
        version 1.  pkg A, B, and C, all have install holds.  pkg B
        has a parent dependency and is out of sync.

        We will modify the child image without touching pkg B directly
        and then verify that the install hold in B gets relaxed, there
        by allowing the image to be synced."""

        # verify install
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1", "install", "A@2",
            change_packages=[
                [self.p_fmri["A@1"], self.p_fmri["A@2"]],
                [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

        # verify update pkg
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1", "update", "A@2",
            change_packages=[
                [self.p_fmri["A@1"], self.p_fmri["A@2"]],
                [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

        # verify uninstall
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1", "uninstall", "A@1",
            remove_packages=[
                self.p_fmri["A@1"]],
            change_packages=[
                [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

        # verify change-variant
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1", "change-variant", "variant.haha=hoho",
            change_variants=[
                ['variant.haha', 'hoho']],
            change_packages=[
                [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

        # verify change-facet
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1", "change-facet", "facet.haha=False",
            change_facets=[
                ['facet.haha', False, None, 'local', False, False]],
            change_packages=[
                [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

    def test_linked_install_hold_relax_constrained_2(self):
        """Verify that any install-holds which are not associated with
        constrained packages (ie, packages with parent dependencies)
        don't get relaxed during install, uninstall and similar
        operations.

        In our child image we'll install 4 packages, A, B, C, and BC,
        all at version 1.  pkg A, B, and C, all have install holds.
        pkg B has a parent dependency and is out of sync.  pkg BC
        incorporates B and C and links their versions together.

        The child image is out of sync. we should be able to
        manipulate it, but we won't be able to bring it in sync
        because of the install hold in C."""

        # verify install
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1 BC@1", "install", "A@2",
            change_packages=[
                [self.p_fmri["A@1"], self.p_fmri["A@2"]]])

        # verify update pkg
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1 BC@1", "update", "A@2",
            change_packages=[
                [self.p_fmri["A@1"], self.p_fmri["A@2"]]])

        # verify uninstall
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1 BC@1", "uninstall", "A@1",
            remove_packages=[
                self.p_fmri["A@1"]])

        # verify change-variant
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1 BC@1", "change-variant", "variant.haha=hoho",
            change_variants=[
                ['variant.haha', 'hoho']])

        # verify change-facet
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1 BC@1", "change-facet", "facet.haha=False",
            change_facets=[
                ['facet.haha', False, None, 'local', False, False]])

    def test_linked_install_hold_relax_constrained_3(self):
        """Verify that any install-holds which are not associated with
        constrained packages (ie, packages with parent dependencies)
        don't get relaxed during install, uninstall and similar
        operations.

        In our child image we'll install 4 packages, A, B, C, and BC,
        all at version 1.  pkg A, B, and C, all have install holds.
        pkg B has a parent dependency and is out of sync.  pkg BC
        incorporates B and C and links their versions together.

        We'll try to update BC, which should fail because of the
        install hold in C."""

        # verify install
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1 BC@1", "install", "BC@2", op_rv=EXIT_OOPS)

        # verify update pkg
        self.__test_linked_install_hold_relax(
            "A@1 B@1 C@1 BC@1", "update", "BC@2", op_rv=EXIT_OOPS)

    def test_linked_install_hold_relax_constrained_4(self):
        """Verify that any install-holds which are not associated with
        constrained packages (ie, packages with parent dependencies)
        don't get relaxed during install, uninstall and similar
        operations.

        In our child image we'll install 1 package, B@1.  pkg B has an
        install hold and a parent dependency, but its parent
        dependency is disabled by a variant, so the image is in sync.

        We'll try to install package BC@2, which should fail because
        of the install hold in B."""

        # verify install
        self.__test_linked_install_hold_relax(
            "B@1", "install", "BC@2", op_rv=EXIT_OOPS,
            variant_out_parent_dep=True)


class TestPkgLinkedScale(pkg5unittest.ManyDepotTestCase):
    """Test the scalability of the linked image subsystem."""

    max_image_count = 32

    p_sync1 = []
    p_vers = [
        "@1.2,5.11-145:19700101T000001Z",
        "@1.2,5.11-145:19700101T000000Z", # old time
        "@1.1,5.11-145:19700101T000000Z", # old ver
        "@1.1,5.11-144:19700101T000000Z", # old build
        "@1.0,5.11-144:19700101T000000Z", # oldest
    ]
    p_files = [
        "tmp/bar",
        "tmp/baz",
    ]

    # generate packages that do need to be synced
    p_sync1_name_gen = "sync1"
    pkgs = ["sync1" + ver for ver in p_vers]
    p_sync1_name = dict(zip(range(len(pkgs)), pkgs))
    for i in p_sync1_name:
        p_data = "open {0}\n".format(p_sync1_name[i])
        p_data += "add depend type=parent fmri={0}".format(
            pkg.actions.depend.DEPEND_SELF)
        p_data += """
                    close\n"""
        p_sync1.append(p_data)

    def setUp(self):
        pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
            image_count=self.max_image_count)

        # create files that go in packages
        self.make_misc_files(self.p_files)

        # get repo url
        self.rurl1 = self.dcs[1].get_repo_url()

        # populate repository
        self.pkgsend_bulk(self.rurl1, self.p_sync1)

    def __req_phys_mem(self, phys_mem_req):
        """Verify that the current machine has a minimal amount of
        physical memory (in GB).  If it doesn't raise
        TestSkippedException."""

        psize = os.sysconf(os.sysconf_names["SC_PAGESIZE"])
        ppages = os.sysconf(os.sysconf_names["SC_PHYS_PAGES"])
        phys_mem = psize * ppages / 1024.0 / 1024.0 / 1024.0

        if phys_mem < phys_mem_req:
            raise pkg5unittest.TestSkippedException(
                "Not enough memory, "\
                "{0:f} GB required, {1:f} GB detected.\n".format(
                phys_mem_req, phys_mem))

    def pkg(self, *args, **kwargs):
        """This is a wrapper function to disable coverage for all
        tests in this class since these are essentially stress tests.
        we don't need the coverage data (since other functional tests
        should have already covered these code paths) and we don't
        want the added overhead of gathering coverage data (since we
        want to use all available resource for actually running the
        tests)."""

        kwargs["coverage"] = False
        return pkg5unittest.ManyDepotTestCase.pkg(self, *args,
            **kwargs)

    def test_li_scale(self):
        """Verify that we can operate on a large number of linked
        images in parallel.

        For parallel linked image operations, 256 images is high
        enough to cause file descriptor allocation to exceed
        FD_SETSIZE, which in turn can cause select.select() to fail if
        it's invoked.  In practice that's the only failure mode we've
        ever seen when people have tried to update a large number of
        zones in parallel.

        The maximum value successfully tested here has been 512.  I
        tried 1024 but it resulted in death by swapping on a u27 with
        12 GB of memory.

        Under Python 3, the maximum value successfully tested is 32.
        I tried 64 but it resulted in "too many open files" on s12_89 on
        a ThinkCentre M93p with 16 GB of memory.
        """

        # we will require at least 11 GB of memory to run this test.
        # This is a rough estimate of required memory based on
        # observing this test running on s12_20 on an x86 machine.  on
        # that machine i observed the peak RSS for pkg child process
        # was about 24 MB.  with 256 child processes this comes out to
        # about 6 GB of memory.  we require 11 GB so that the machine
        # doesn't get bogged down and other things can continue to
        # run.
        self.__req_phys_mem(11)

        limit = self.max_image_count

        # create an image with a synced package
        self.set_image(0)
        self.image_create(repourl=self.rurl1)
        self.pkg("install -v {0}".format(self.p_sync1_name[1]))

        # create copies of the image.
        for i in range(1, self.max_image_count):
            self.image_clone(i)

        # attach the copies as children of the original image
        for i in range(1, self.max_image_count):
            name = "system:img{0:d}".format(i)
            cmd = "attach-linked --linked-md-only -c {0} {1}".format(
                name, self.img_path(i))
            self.pkg(cmd)

        # update the parent image and all child images in parallel
        self.pkg("update -C0 -q")


class TestPkgLinkedPaths(pkg5unittest.ManyDepotTestCase):
    """Class to test linked image path management."""

    #
    # linked image types
    #
    T_NONE = "none"
    T_PUSH = "push"
    T_PULL = "pull"

    #
    # Linked image trees for testing.
    # All trees have an implicit parent node of type T_NONE.
    # Trees are defined by a vector with up to four elements:
    #     child 1: parented to root image
    #     child 2: parented to root image
    #     child 3: parented to child 1
    #     child 4: parented to child 1
    #
    t_vec_list = [
            [ T_PUSH ],
            [ T_PULL ],
            [ T_PUSH, T_PULL ],

            [ T_PUSH, T_NONE, T_PUSH ],
            [ T_PUSH, T_NONE, T_PULL ],
            [ T_PUSH, T_NONE, T_PUSH, T_PULL ],

            [ T_PULL, T_NONE, T_PUSH ],
            [ T_PULL, T_NONE, T_PULL ],
            [ T_PULL, T_NONE, T_PUSH, T_PULL ],
    ]

    #
    # Linked image child locations.
    #
    L_CNEST = "children are nested"
    L_CPARALLEL = "children are parallel to parent"
    L_CBELOW = "children are below parent, but not nested"
    L_CABOVE = "children are above parent, but not nested"
    l_list = [ L_CNEST, L_CPARALLEL, L_CBELOW, L_CABOVE ]

    #
    # Linked image directory location vectors.
    # Location vectors consist of 5 image locations:
    #       root image path
    #       child 1 path
    #       child 2 path
    #       child 3 path
    #       child 4 path
    #       child 5 path
    #
    l_vec_dict = {
        L_CNEST:     [ "./",     "d/",    "d1/",   "d/d/",     "d/d1/"    ],
        L_CPARALLEL: [ "d/",     "d1/",   "d2/",   "d3/",      "d4/"      ],
        L_CBELOW:    [ "d/",     "d1/d/", "d2/d/", "d3/d1/d/", "d3/d2/d/" ],
        L_CABOVE:    [ "d/d/d/", "d/d1/", "d/d2/", "d1/",      "d2/"      ],
    }

    path_start = "d1/p/p"
    path_tests = [
            # test directory moves down
            # (tests beadm mount <be> /a; pkg -R /a type behavior)
            "d1/p/p/a",
            "d1/p/p/d1/p/p",

            # test directory moves up
            "d1/p",
            "d1",

            # test parallel directory moves
            "d1/p/b",
            "d2/p/p",
            "d2/p",     # and up
            "d2/p/p/a", # and down
    ]

    p_sync1 = []
    p_vers = [
        "@1.2,5.11-145:19700101T000001Z",
        "@1.2,5.11-145:19700101T000000Z", # old time
        "@1.1,5.11-145:19700101T000000Z", # old ver
        "@1.1,5.11-144:19700101T000000Z", # old build
        "@1.0,5.11-144:19700101T000000Z", # oldest
    ]
    p_files = [
        "tmp/bar",
        "tmp/baz",
    ]

    # fake zonename binary used for testing
    zonename_sh = """
#!/bin/sh
echo global
exit 0""".strip("\n")

    # fake zoneadm binary used for testing
    zoneadm_sh = """
#!/bin/sh
while getopts "R:" OPT ; do
case $OPT in
        R )
                [[ "$OPTARG" != "$PKG_GZR/" ]] && exit 0
                ;;
esac
done
cat <<-EOF
0:global:running:$PKG_GZR/::solaris:shared:-:none:
-:z1:installed:$PKG_GZR/z1::solaris:excl:-::
-:z2:unavailable:$PKG_GZR/z21::solaris:excl:-::
-:z3:configured:$PKG_GZR/z3::solaris:excl:-::
-:z4:incomplete:$PKG_GZR/z4::solaris:excl:-::
-:kz:installed:$PKG_GZR/system/volatile/zones/kz1/zonepath::solaris-kz:excl:-:solaris-kz:
-:s10:installed:$PKG_GZR/s10::solaris10:excl:-::
EOF
exit 0""".strip("\n")

    # generate packages that do need to be synced
    p_sync1_name_gen = "sync1"
    pkgs = ["sync1" + ver for ver in p_vers]
    p_sync1_name = dict(zip(range(len(pkgs)), pkgs))
    for i in p_sync1_name:
        p_data = "open {0}\n".format(p_sync1_name[i])
        p_data += "add depend type=parent fmri={0}".format(
            pkg.actions.depend.DEPEND_SELF)
        p_data += """
                    close\n"""
        p_sync1.append(p_data)

    def setUp(self):
        self.i_count = 3
        pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
            image_count=self.i_count)

        # create files that go in packages
        self.make_misc_files(self.p_files)

        # get repo url
        self.rurl1 = self.dcs[1].get_repo_url()

        # populate repository
        self.pkgsend_bulk(self.rurl1, self.p_sync1)

        # setup image names and paths
        self.i_name = []
        self.i_path = []
        for i in range(self.i_count):
            name = "system:img{0:d}".format(i)
            self.i_name.insert(i, name)
            self.i_path.insert(i, self.img_path(i))

    def __mk_bin(self, path, txt):
        with open(path, "w+") as fobj:
            print(txt, file=fobj)
        self.cmdline_run("chmod a+x {0}".format(path), coverage=False)

    def __mk_zone_bins(self, base_path):

        # create a zonename binary
        bin_zonename = os.path.join(base_path, "zonename")
        self.__mk_bin(bin_zonename, self.zonename_sh)

        # create a zoneadm binary
        bin_zoneadm = os.path.join(base_path, "zoneadm")
        self.__mk_bin(bin_zoneadm, self.zoneadm_sh)

        return (bin_zonename, bin_zoneadm)

    def __attach_params(self, base_path, pdir, cdir):
        ppath = os.path.join(base_path, pdir)
        cpath = os.path.join(base_path, cdir)
        # generate child image name based on the child image dir
        cname = re.sub('[/]', '_', cdir.rstrip(os.sep))
        return ppath, cpath, cname

    def __attach_child(self, base_path, pdir, cdir, exit=EXIT_OK):
        ppath, cpath, cname = \
            self.__attach_params(base_path, pdir, cdir)
        self.pkg("-R {0} attach-linked -c system:{1} {2}".format(
            ppath, cname, cpath), exit=exit)

    def __attach_parent(self, base_path, cdir, pdir, exit=EXIT_OK):
        ppath, cpath, cname = \
            self.__attach_params(base_path, pdir, cdir)
        self.pkg("-R {0} attach-linked -p system:{1} {2}".format(
            cpath, cname, ppath), exit=exit)

    def __try_attach(self, base_path, i1, i2):
        self.__attach_child(base_path, i1, i2, exit=EXIT_OOPS)
        self.__attach_parent(base_path, i1, i2, exit=EXIT_OOPS)

    def __create_images(self, base_path, img_dirs, repos=None):
        """Create images (in directory order)"""
        for d in sorted(img_dirs):
            p = os.path.join(base_path, d)
            self.cmdline_run("mkdir -p {0}".format(p), coverage=False)
            self.image_create(self.rurl1, destroy=False, img_path=p)

    def __define_limages(self, base_path, types, locs):
        """Given a vector of linked image types and locations, return
        a list of linked images.  The format of returned list entries
        is:
                <image dir, image type, parent dir>
        """

        limages = []
        index = 0
        assert len(types) <= len(locs)

        # first image is always a parent
        limages.append([locs[0], self.T_NONE, None])

        for t in types:
            index += 1

            # determine child and parent paths
            cdir = locs[index]
            pdir = None
            if index in [1, 2]:
                pdir = locs[0]
            elif index in [3, 4]:
                pdir = locs[1]
            else:
                assert "invalid index: ", index
            assert pdir is not None

            # skip this image
            if t == self.T_NONE:
                continue

            # add image to the list
            limages.append([cdir, t, pdir])

        return limages

    def __create_limages(self, base_path, limages):
        """Create images (in directory order)"""
        img_dirs = [
                cdir
                for cdir, t, pdir in limages
        ]
        self.__create_images(base_path, img_dirs)

    def __attach_limages(self, base_path, limages):
        """Attach images"""
        for cdir, t, pdir in limages:
            if t == self.T_NONE:
                continue
            if t == self.T_PUSH:
                self.__attach_child(base_path, pdir, cdir)
                continue
            assert t == self.T_PULL
            self.__attach_parent(base_path, cdir, pdir)

    def __audit_limages(self, base_path, limages):
        """Audit images"""

        parents = set([
            pdir
            for cdir, t, pdir in limages
            if t == self.T_PUSH
        ])
        for pdir in parents:
            p = os.path.join(base_path, pdir)
            self.pkg("-R {0} audit-linked -a".format(p))

        children = set([
            cdir
            for cdir, t, pdir in limages
            if t != self.T_NONE
        ])
        for pdir in parents:
            p = os.path.join(base_path, limages[-1][0])
            self.pkg("-R {0} audit-linked".format(p))

    def __ccmd(self, args, rv=0):
        """Run a 'C' (or other non-python) command."""
        assert type(args) == str
        # Ensure 'coverage' is turned off-- it won't work.
        self.cmdline_run("{0}".format(args), exit=rv, coverage=False)

    def __list_linked_check(self, ipath, lipaths,
        bin_zonename, bin_zoneadm):
        """Given an image path (ipath), verify that pkg list-linked
        displays the expected linked image paths (lipaths).  The
        caller must specify paths to custom zonename and zoneadm
        binaries that will output from those commands."""

        outfile1 = os.path.join(ipath, "__list_linked_check")

        self.pkg("--debug zones_supported=1 "
            "--debug bin_zonename='{0}' "
            "--debug bin_zoneadm='{1}' "
            "-R {2} list-linked > {3}".format(
            bin_zonename, bin_zoneadm, ipath, outfile1))
        self.__ccmd("cat {0}".format(outfile1))
        for lipath in lipaths:
            self.__ccmd("egrep '[ 	]{0}[ 	]*$' {1}".format(
                lipath, outfile1))

    def __check_linked_props(self, ipath, liname, props,
        bin_zonename, bin_zoneadm):
        """Given an image path (ipath), verify that pkg
        property-linked displays the expected linked image properties.
        (props).  The caller must specify paths to custom zonename and
        zoneadm binaries that will output from those commands."""

        outfile1 = os.path.join(ipath, "__check_linked_props1")
        outfile2 = os.path.join(ipath, "__check_linked_props2")

        if liname:
            liname = "-l " + liname
        else:
            liname = ""

        self.pkg("--debug zones_supported=1 "
            "--debug bin_zonename='{0}' "
            "--debug bin_zoneadm='{1}' "
            "-R {2} property-linked {3} -H > {4}".format(
            bin_zonename, bin_zoneadm,
            ipath, liname, outfile1))
        self.__ccmd("cat {0}".format(outfile1))

        for p, v in props.items():
            if v is None:
                # verify property is not present
                self.__ccmd(
                    "grep \"^{0}[ 	]\" {1}".format(
                    p, outfile1), rv=1)
                continue

            # verify property and value
            self.__ccmd("grep \"^{0}[ 	]\" {1} > {2}".format(
                p, outfile1, outfile2))
            self.__ccmd("cat {0}".format(outfile2))
            # verify property and value
            self.__ccmd("grep \"[ 	]{0}[ 	]*$\" {1}".format(
                v, outfile2))

    def test_linked_paths_moves(self):
        """Create trees of linked images, with different relative path
        configurations.  Then move each tree to a different locations
        and see if the images within each tree can still find each
        other."""

        tmp_path = os.path.join(self.img_path(0), "tmp")
        base_path = os.path.join(self.img_path(0), "images")

        for t_vec, loc in itertools.product(
            self.t_vec_list, self.l_list):

            l_vec = self.l_vec_dict[loc]

            pcur = os.path.join(base_path, self.path_start)

            # create and link image tree
            limages = self.__define_limages(pcur, t_vec, l_vec)
            self.__create_limages(pcur, limages)
            self.__attach_limages(pcur, limages)

            for pnew in self.path_tests:

                assert limages
                assert pcur != pnew

                # determine the parent images new location
                pnew = os.path.join(base_path, pnew)

                # move the parent to a temporary location
                self.__ccmd("mv {0} {1}".format(pcur, tmp_path))

                # cleanup old directory, avoid "rm -rf"
                d = pcur
                while True:
                    d = os.path.dirname(d)
                    if len(d) <= len(base_path):
                        break
                    self.__ccmd("rmdir {0}".format(d))

                # move the parent to it's new location
                self.__ccmd(
                    "mkdir -p {0}".format(os.path.dirname(pnew)))
                self.__ccmd("mv {0} {1}".format(tmp_path, pnew))

                # verify that the images can find each other
                self.__audit_limages(pnew, limages)

                # save the parent images last location
                pcur = pnew

            # cleanup current image tree
            shutil.rmtree(base_path)

    def test_linked_paths_no_self_link(self):
        """You can't link images to themselves."""

        base_path = self.img_path(0)
        img_dirs = [ "./" ]
        self.__create_images(base_path, img_dirs)
        self.__try_attach(base_path, "./", "./")

    def test_linked_paths_no_nested_parent(self):
        """You can't link images if the parent image is nested within
        the child."""

        base_path = self.img_path(0)
        img_dirs = [ "./", "1/" ]

        self.__create_images(base_path, img_dirs)

        self.__attach_child(base_path, "1/", "./", exit=EXIT_OOPS)
        self.__attach_parent(base_path, "./", "1/", exit=EXIT_OOPS)

    def test_linked_paths_no_liveroot_child(self):
        """You can't link the liveroot image as a child."""

        base_path = self.img_path(0)
        img_dirs = [ "./", "1/" ]

        self.__create_images(base_path, img_dirs)

        ppath, cpath, cname = \
            self.__attach_params(base_path, "./", "1/")

        self.pkg("--debug simulate_live_root='{0}' "
            "-R {1} attach-linked -c system:{2} {3}".format(
            cpath, ppath, cname, cpath), exit=EXIT_OOPS)
        self.pkg("--debug simulate_live_root='{0}' "
            "-R {1} attach-linked -p system:{2} {3}".format(
            cpath, cpath, cname, ppath), exit=EXIT_OOPS)

    def test_linked_paths_no_intermediate_imgs(self):
        """You can't link images if there are intermediate image in
        between."""

        base_path = self.img_path(0)
        img_dirs = [ "./", "1/", "1/11/", "2/" ]

        self.__create_images(base_path, img_dirs)

        # can't link "./" and "1/11/" because "1/" is inbetween
        self.__try_attach(base_path, "./", "1/11/")

        # can't link "1/" and "2/" because "./" is in between
        self.__try_attach(base_path, "1/", "2/")

    def test_linked_paths_no_attach_in_temporary_location(self):
        """You can't link images if we're operating on already linked
        images in temporary locations."""

        base_path = os.path.join(self.img_path(0), "images1")
        img_dirs = [ "./",
            "p/",
            "p/1/", "p/2/", "p/3/",
            "p/1/11/", "p/2/22/"
        ]

        self.__create_images(base_path, img_dirs)
        self.__attach_child(base_path,  "p/", "p/1/")
        self.__attach_parent(base_path, "p/2/", "p/")

        # move the images
        pnew = os.path.join(self.img_path(0), "images2")
        self.__ccmd("mv {0} {1}".format(base_path, pnew))
        base_path = pnew

        self.__attach_parent(base_path, "p/",   "./",
            exit=EXIT_OOPS)
        self.__attach_child(base_path,  "p/",   "p/3/",
            exit=EXIT_OOPS)
        self.__attach_child(base_path,  "p/1/", "p/1/11/",
            exit=EXIT_OOPS)
        self.__attach_child(base_path,  "p/2/", "p/2/22/",
            exit=EXIT_OOPS)

    def test_linked_paths_staged(self):
        """Test path handling code with staged operation.  Make sure
        that we correctly handle images moving around between stages.
        This simulates normal pkg updates where we plan an update for
        "/", and then we clone "/", mount it at a  a temporarly
        location, and then update the clone."""

        tmp_path = os.path.join(self.img_path(0), "tmp")
        base_path = os.path.join(self.img_path(0), "images")

        t_vec = [ self.T_PUSH, self.T_NONE, self.T_PUSH, self.T_PULL ]
        l_vec = [ "", "d/", "d1/", "d/d/", "d/d1/"    ]
        limages = self.__define_limages(base_path, t_vec, l_vec)

        self.__create_limages(base_path, limages)
        for i in range(len(limages)):
            ipath = os.path.join(base_path, limages[i][0])
            self.pkg("-R {0} install sync1@1.0".format(ipath))
        self.__attach_limages(base_path, limages)

        for i in range(len(limages)):

            # It only makes sense to try and update T_NONE and
            # T_PULL images (T_PUSH images will be updated
            # implicitly via recursion).
            if limages[i][1] == self.T_PUSH:
                continue

            # plan update
            ipath = os.path.join(base_path, limages[i][0])
            self.pkg("-R {0} update --stage=plan".format(ipath))

            # move images to /a
            self.__ccmd("mv {0} {1}".format(base_path, tmp_path))
            new_path = os.path.join(base_path, "a")
            self.__ccmd("mkdir -p {0}".format(os.path.dirname(new_path)))
            self.__ccmd("mv {0} {1}".format(tmp_path, new_path))

            # finish update
            ipath = os.path.join(new_path, limages[i][0])
            self.pkg("-R {0} update --stage=prepare".format(ipath))
            self.pkg("-R {0} update --stage=execute".format(ipath))

            # move images back
            # cleanup old directory, avoid "rm -rf"
            self.__ccmd("mv {0} {1}".format(new_path, tmp_path))
            d = new_path
            while True:
                d = os.path.dirname(d)
                if len(d) < len(base_path):
                    break
                self.__ccmd("rmdir {0}".format(d))
            self.__ccmd("mkdir -p {0}".format(os.path.dirname(base_path)))
            self.__ccmd("mv {0} {1}".format(tmp_path, base_path))

    def test_linked_paths_staged_with_zones(self):
        """Simulate staged packaging operations involving zones."""

        tmp_path = os.path.join(self.img_path(0), "tmp")
        base_path = os.path.join(self.img_path(0), "images")

        # create a zone binaries
        bin_zonename, bin_zoneadm = self.__mk_zone_bins(self.test_root)

        # setup image paths
        img_dirs = [
            "", "z1/root"
        ]
        gzpath = os.path.join(base_path, img_dirs[0])
        ngzpath = os.path.join(base_path, img_dirs[1])
        os.environ["PKG_GZR"] = gzpath.rstrip(os.sep)

        # create images, install packages, and link them
        self.__create_images(base_path, img_dirs)
        self.pkg("-R {0} install sync1@1.1".format(gzpath))
        self.pkg("-R {0} install sync1@1.0".format(ngzpath))
        self.pkg("--debug zones_supported=1 "
            "--debug bin_zonename='{0}' --debug bin_zoneadm='{1}' "
            "-R {2} attach-linked -v -f -c zone:z1 {3}".format(
            bin_zonename, "/bin/true", gzpath, ngzpath))

        # plan update
        self.pkg("--debug zones_supported=1 "
            "--debug bin_zonename='{0}' --debug bin_zoneadm='{1}' "
            "-R {2} update -vvv --stage=plan".format(
            bin_zonename, bin_zoneadm, gzpath))

        # move images to /a
        self.__ccmd("mv {0} {1}".format(base_path, tmp_path))
        base_path = os.path.join(base_path, "a")
        gzpath = os.path.join(base_path, img_dirs[0])
        ngzpath = os.path.join(base_path, img_dirs[1])
        os.environ["PKG_GZR"] = gzpath.rstrip(os.sep)
        self.__ccmd("mkdir -p {0}".format(os.path.dirname(base_path)))
        self.__ccmd("mv {0} {1}".format(tmp_path, gzpath))

        # finish update
        self.pkg("--debug zones_supported=1 "
            "--debug bin_zonename='{0}' --debug bin_zoneadm='{1}' "
            "-R {2} update --stage=prepare".format(
            bin_zonename, bin_zoneadm, gzpath))
        self.pkg("--debug zones_supported=1 "
            "--debug bin_zonename='{0}' --debug bin_zoneadm='{1}' "
            "-R {2} update --stage=execute".format(
            bin_zonename, bin_zoneadm, gzpath))

        # verify that all the images got updated
        self.pkg("-R {0} list sync1@1.2".format(gzpath))
        self.pkg("-R {0} list sync1@1.2".format(ngzpath))

        del os.environ["PKG_GZR"]

    def test_linked_paths_list_and_props(self):
        """Verify that all linked image paths reported by list-linked
        and property-linked are correct before and after moving trees
        of images."""

        tmp_path = os.path.join(self.img_path(0), "tmp")
        base_path = os.path.join(self.img_path(0), "images")

        # create a zone binaries
        bin_zonename, bin_zoneadm = self.__mk_zone_bins(self.test_root)

        # setup image paths
        img_dirs = [
            "", "s1/", "s2/", "z1/root/"
        ]
        img_paths = [
                os.path.join(base_path, d)
                for d in img_dirs
        ]
        gzpath, s1path, s2path, ngzpath = img_paths
        os.environ["PKG_GZR"] = gzpath.rstrip(os.sep)

        # create images and link them
        self.__create_images(base_path, img_dirs)
        self.__attach_child(base_path, "", img_dirs[1])
        self.__attach_parent(base_path, img_dirs[2], "")
        self.pkg("--debug zones_supported=1 "
            "--debug bin_zonename='{0}' --debug bin_zoneadm='{1}' "
            "-R {2} attach-linked -v -f -c zone:z1 {3}".format(
            bin_zonename, "/bin/true", gzpath, ngzpath))

        # Make sure that list-linked displays the correct paths.
        for ipath, lipaths in [
                [ gzpath,  [ gzpath, s1path, ngzpath ]],
                [ s1path,  [ s1path ]],
                [ s2path,  [ gzpath, s2path ]],
                [ ngzpath, [ ngzpath ]],
            ]:
            self.__list_linked_check(ipath, lipaths,
                bin_zonename, bin_zoneadm)

        # Make sure that property-linked displays the correct paths.
        for ipath, liname, props in [
                [ gzpath, None, {
                    "li-current-parent": None,
                    "li-current-path": gzpath,
                    "li-parent": None,
                    "li-path": gzpath,
                    "li-path-transform": "('/', '/')",
                    }],
                [ gzpath, "system:s1", {
                    "li-current-parent": None,
                    "li-current-path": s1path,
                    "li-parent": None,
                    "li-path": s1path,
                    "li-path-transform": "('/', '/')",
                    }],
                [ gzpath, "zone:z1", {
                    "li-current-parent": None,
                    "li-current-path": ngzpath,
                    "li-parent": None,
                    "li-path": ngzpath,
                    "li-path-transform": "('/', '/')",
                    }],
                [ s1path, None, {
                    "li-current-parent": None,
                    "li-current-path": s1path,
                    "li-parent": None,
                    "li-path": s1path,
                    "li-path-transform": "('/', '/')",
                    }],
                [ s2path, None, {
                    "li-current-parent": gzpath,
                    "li-current-path": s2path,
                    "li-parent": gzpath,
                    "li-path": s2path,
                    "li-path-transform": "('/', '/')",
                    }],
                [ ngzpath, None, {
                    "li-current-parent": None,
                    "li-current-path": ngzpath,
                    "li-parent": None,
                    "li-path": "/",
                    "li-path-transform": "('/', '{0}')".format(ngzpath),
                    }],
            ]:
            self.__check_linked_props(ipath, liname, props,
                bin_zonename, bin_zoneadm)

        # save old paths
        ogzpath, os1path, os2path, ongzpath = img_paths

        # move images to /a
        self.__ccmd("mv {0} {1}".format(base_path, tmp_path))
        base_path = os.path.join(base_path, "a")
        self.__ccmd("mkdir -p {0}".format(os.path.dirname(base_path)))
        self.__ccmd("mv {0} {1}".format(tmp_path, base_path))

        # update paths
        img_paths = [
                os.path.join(base_path, d)
                for d in img_dirs
        ]
        gzpath, s1path, s2path, ngzpath = img_paths
        os.environ["PKG_GZR"] = gzpath.rstrip(os.sep)

        # Make sure that list-linked displays the correct paths.
        for ipath, lipaths in [
                [ gzpath,  [ gzpath, s1path, ngzpath ]],
                [ s1path,  [ s1path ]],
                [ s2path,  [ gzpath, s2path ]],
                [ ngzpath, [ ngzpath ]],
            ]:
            self.__list_linked_check(ipath, lipaths,
                bin_zonename, bin_zoneadm)

        # Make sure that property-linked displays the correct paths.
        for ipath, liname, props in [
                [ gzpath, None, {
                    "li-current-parent": None,
                    "li-current-path": gzpath,
                    "li-parent": None,
                    "li-path": ogzpath,
                    "li-path-transform": "('{0}', '{1}')".format(
                        ogzpath, gzpath)
                    }],
                [ gzpath, "system:s1", {
                    "li-current-parent": None,
                    "li-current-path": s1path,
                    "li-parent": None,
                    "li-path": os1path,
                    "li-path-transform": "('{0}', '{1}')".format(
                        ogzpath, gzpath)
                    }],
                [ gzpath, "zone:z1", {
                    "li-current-parent": None,
                    "li-current-path": ngzpath,
                    "li-parent": None,
                    "li-path": ongzpath,
                    "li-path-transform": "('{0}', '{1}')".format(
                        ogzpath, gzpath)
                    }],
                [ s1path, None, {
                    "li-current-parent": None,
                    "li-current-path": s1path,
                    "li-parent": None,
                    "li-path": os1path,
                    "li-path-transform": "('{0}', '{1}')".format(
                        ogzpath, gzpath)
                    }],
                [ s2path, None, {
                    "li-current-parent": gzpath,
                    "li-current-path": s2path,
                    "li-parent": ogzpath,
                    "li-path": os2path,
                    "li-path-transform": "('{0}', '{1}')".format(
                        ogzpath, gzpath)
                    }],
                [ ngzpath, None, {
                    "li-current-parent": None,
                    "li-current-path": ngzpath,
                    "li-parent": None,
                    "li-path": "/",
                    "li-path-transform": "('/', '{0}')".format(ngzpath),
                    }],
            ]:
            self.__check_linked_props(ipath, liname, props,
                bin_zonename, bin_zoneadm)

    def test_linked_paths_guess_path_transform(self):
        """If a parent image has no properties, then rather than
        throwing an exception (that a user has no way to fix), we try
        to fabricate some properties to run with.  To do this we ask
        each linked image plugin if it knows what the current path
        transform is (which would tell us what original root path was).
        Only the zones plugin implements this functionality, so test
        it here."""

        base_path = os.path.join(self.img_path(0), "images")

        # create a zone binaries
        bin_zonename, bin_zoneadm = self.__mk_zone_bins(self.test_root)

        # setup image paths
        img_dirs = [
            "", "z1/root/"
        ]
        img_paths = [
                os.path.join(base_path, d)
                for d in img_dirs
        ]
        gzpath, ngzpath = img_paths
        os.environ["PKG_GZR"] = gzpath.rstrip(os.sep)

        # create images and link them
        self.__create_images(base_path, img_dirs)
        self.pkg("--debug zones_supported=1 "
            "--debug bin_zonename='{0}' --debug bin_zoneadm='{1}' "
            "-R {2} attach-linked -v -f -c zone:z1 {3}".format(
            bin_zonename, "/bin/true", gzpath, ngzpath))

        # now delete the global zone linked image metadata
        self.__ccmd("rm {0}var/pkg/linked/*".format(gzpath))

        # Make sure that list-linked displays the correct paths.
        for ipath, lipaths in [
                [ gzpath,  [ gzpath, ngzpath ]],
                [ ngzpath, [ ngzpath ]],
            ]:
            self.__list_linked_check(ipath, lipaths,
                bin_zonename, bin_zoneadm)

        # now verify that the gz thinks it's in an alternate path
        for ipath, liname, props in [
                [ gzpath, None, {
                    "li-current-parent": None,
                    "li-current-path": gzpath,
                    "li-parent": None,
                    "li-path": "/",
                    "li-path-transform": "('/', '{0}')".format(gzpath),
                    }],
                [ gzpath, "zone:z1", {
                    "li-current-parent": None,
                    "li-current-path": ngzpath,
                    "li-parent": None,
                    "li-path": "/z1/root/",
                    "li-path-transform": "('/', '{0}')".format(gzpath),
                    }],
            ]:
            self.__check_linked_props(ipath, liname, props,
                bin_zonename, bin_zoneadm)

    def test_linked_paths_BE_cloning(self):
        """Test that image object plan execution and re-initialization
        works when the image is moving around.  This simulates an
        update that involves BE cloning."""

        # setup image paths
        image1 = os.path.join(self.img_path(0), "image1")
        image2 = os.path.join(self.img_path(0), "image2")
        img_dirs = [ "", "c/", ]

        # Create images, link them, and install packages.
        self.__create_images(image1, img_dirs)
        self.__attach_child(image1,  "", "c/")
        for d in img_dirs:
            p = os.path.join(image1, d)
            self.pkg("-R {0} install sync1@1.0".format(p))

        # Initialize an API object.
        api_inst = self.get_img_api_obj(
            cmd_path=pkg.misc.api_cmdpath(), img_path=image1)

        # Plan and prepare an update for the images.
        for pd in api_inst.gen_plan_install(["sync1@1.1"]):
            continue
        api_inst.prepare()

        # clone the current images to an alternate location
        self.__ccmd("mkdir -p {0}".format(image2))
        self.__ccmd("cd {0}; find . | cpio -pdm {1}".format(image1, image2))

        # Update the API object to point to the new location and
        # execute the udpate.
        api_inst._img.find_root(image2)
        api_inst.execute_plan()

        # Update the API object to point back to the old location.
        api_inst._img.find_root(image1)

    def test_pull_child_moving_and_parent_staying_fixed(self):
        """Test what happens if we have a pull child image that gets
        moved but the parent image doesn't move."""

        # Setup image paths
        img_dirs = [ "parent/", "child_foo/", ]

        # Create images, link them, and install packages.
        self.__create_images(self.img_path(0), img_dirs)
        self.__attach_parent(self.img_path(0),  "child_foo/", "parent/")

        # Move the child image
        foo_path = os.path.join(self.img_path(0), "child_foo/")
        bar_path = os.path.join(self.img_path(0), "child_bar/")
        self.__ccmd("mv {0} {1}".format(foo_path, bar_path))

        # sync the child image
        self.pkg("-R {0} sync-linked -v".format(bar_path),
            exit=EXIT_NOP)

    def test_linked_paths_bad_zoneadm_list_output(self):
        """Test that we emit an error message if we fail to parse
        zoneadm list -p output."""

        base_path = self.img_path(0).rstrip(os.sep) + os.sep
        gzpath = os.path.join(base_path, "gzpath/")
        self.__ccmd("mkdir -p {0}".format(gzpath))

        # fake zoneadm binary used for testing
        zoneadm_sh = """
#!/bin/sh
cat <<-EOF
this is invalid zoneadm list -p output.
EOF
exit 0""".strip("\n")

        # create a zonename binary
        bin_zonename = os.path.join(base_path, "zonename")
        self.__mk_bin(bin_zonename, self.zonename_sh)

        # create a zoneadm binary
        bin_zoneadm = os.path.join(base_path, "zoneadm")
        self.__mk_bin(bin_zoneadm, zoneadm_sh)

        self.image_create(self.rurl1, destroy=False, img_path=gzpath)

        self.pkg("--debug zones_supported=1 "
            "--debug bin_zonename='{0}' "
            "--debug bin_zoneadm='{1}' "
            "-R {2} list-linked".format(
            bin_zonename, bin_zoneadm, gzpath), exit=EXIT_OOPS)

        self.assertTrue(self.output == "")
        self.assertTrue("this is invalid zoneadm list -p output." in
            self.errout)

    def test_linked_paths_zone_paths_with_colon(self):
        """Test that we can correctly parse zone paths that have a
        colon in them."""

        base_path = self.img_path(0).rstrip(os.sep) + os.sep
        gzpath = os.path.join(base_path, "gzpath_with_a_:colon/")
        self.__ccmd("mkdir -p {0}".format(gzpath))

        os.environ["PKG_GZR"] = gzpath.rstrip(os.sep)

        # fake zoneadm binary used for testing
        zoneadm_sh = r"""
#!/bin/sh
while getopts "R:" OPT ; do
case $OPT in
        R )
                [[ "$OPTARG" != "$PKG_GZR/" ]] && exit 0
                ;;
esac
done
PKG_GZR=$(echo "$PKG_GZR" | sed 's-:-\\:-g')
cat <<-EOF
0:global:running:$PKG_GZR::solaris:shared:-:none:
-:z1:installed:$PKG_GZR/ngzzone_path_with_a\:colon::solaris:excl:-::
EOF
exit 0""".strip("\n")

        # create a zonename binary
        bin_zonename = os.path.join(base_path, "zonename")
        self.__mk_bin(bin_zonename, self.zonename_sh)

        # create a zoneadm binary
        bin_zoneadm = os.path.join(base_path, "zoneadm")
        self.__mk_bin(bin_zoneadm, zoneadm_sh)

        self.image_create(self.rurl1, destroy=False, img_path=gzpath)

        ngzpath = gzpath + "ngzzone_path_with_a:colon/root/"
        self.__list_linked_check(gzpath, [ngzpath],
            bin_zonename, bin_zoneadm)


if __name__ == "__main__":
    unittest.main()
