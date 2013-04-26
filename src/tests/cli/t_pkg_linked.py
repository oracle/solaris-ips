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
# Copyright (c) 2011, 2013, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import difflib
import os
import re
import shutil
import tempfile
import unittest
import sys

import pkg.actions
import pkg.client.image as image

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
        ]

        # generate packages that don't need to be synced
        p_foo1_name_gen = "foo1"
        pkgs = [p_foo1_name_gen + ver for ver in p_vers]
        p_foo1_name = dict(zip(range(len(pkgs)), pkgs))
        for i in p_foo1_name:
                p_data = "open %s\n" % p_foo1_name[i]
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=foo_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=foo_baz variant.foo=baz
                    close\n"""
                p_foo1.append(p_data)

        p_foo2_name_gen = "foo2"
        pkgs = [p_foo2_name_gen + ver for ver in p_vers]
        p_foo2_name = dict(zip(range(len(pkgs)), pkgs))
        for i in p_foo2_name:
                p_data = "open %s\n" % p_foo2_name[i]
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=foo_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=foo_baz variant.foo=baz
                    close\n"""
                p_all.append(p_data)

        # generate packages that do need to be synced
        p_sunc1_name_gen = "sync1"
        pkgs = [p_sunc1_name_gen + ver for ver in p_vers]
        p_sync1_name = dict(zip(range(len(pkgs)), pkgs))
        for i in p_sync1_name:
                p_data = "open %s\n" % p_sync1_name[i]
                p_data += "add depend type=parent fmri=%s" % \
                    pkg.actions.depend.DEPEND_SELF
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=sync1_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=sync1_baz variant.foo=baz
                    close\n"""
                p_sync1.append(p_data)

        # generate packages that do need to be synced
        p_sync2_name_gen = "sync2"
        pkgs = [p_sync2_name_gen + ver for ver in p_vers]
        p_sync2_name = dict(zip(range(len(pkgs)), pkgs))
        for i in p_sync2_name:
                p_data = "open %s\n" % p_sync2_name[i]
                p_data += "add depend type=parent fmri=%s" % \
                    pkg.actions.depend.DEPEND_SELF
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=sync2_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=sync2_baz variant.foo=baz
                     close\n"""
                p_all.append(p_data)

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

                # setup image names and paths
                self.i_name = []
                self.i_path = []
                self.i_api = []
                self.i_api_reset = []
                for i in range(self.i_count):
                        name = "system:img%d" % i
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
                    "image: %d, %s, %s\n"
                    "expected children: %s\n"
                    "found children: %s\n" %
                    (i, self.i_name[i], self.i_path[i],
                    str(cl_expected),
                    str(cl_found)))

        def _v_no_children(self, il):
                for i in il:
                        # make sure the we don't have any children
                        cl_found = self.__img_children_names(i)
                        self.assertEqual(set(), cl_found,
                           "error: image has children\n"
                           "image: %d, %s, %s\n"
                           "found children: %s\n" %
                           (i, self.i_name[i], self.i_path[i],
                           str(cl_found)))

        def _v_has_parent(self, il):
                # make sure a child has a parent
                for i in il:
                        self.assertEqual(True, self.__img_has_parent(i),
                           "error: image has no parent\n"
                           "image: %d, %s, %s\n" %
                           (i, self.i_name[i], self.i_path[i]))

        def _v_no_parent(self, il):
                for i in il:
                        self.assertEqual(False, self.__img_has_parent(i),
                           "error: image has a parent\n"
                           "image: %d, %s, %s\n" %
                           (i, self.i_name[i], self.i_path[i]))

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
                self.cmdline_run("%s" % args, exit=rv, coverage=False)

        def _pkg(self, il, cmd, args=None, rv=None, rvdict=None):
                assert type(il) == list
                assert type(cmd) == str
                assert args == None or type(args) == str
                assert rv == None or type(rv) == int
                assert rvdict == None or type(rvdict) == dict
                assert rv == None or rvdict == None

                if rv == None:
                        rv = EXIT_OK
                if rvdict == None:
                        rvdict = {}
                        for i in il:
                                rvdict[i] = rv
                assert (set(rvdict) | set(il)) == set(il)

                if args == None:
                        args = ""

                # we're updating one or more images, so make sure to reset all
                # our api instances before using them.
                self.i_api_reset[:] = [True] * len(self.i_api_reset)

                for i in il:
                        rv = rvdict.get(i, EXIT_OK)
                        self.pkg("-R %s %s %s" % (self.i_path[i], cmd, args),
                            exit=rv)

        def _pkg_child(self, i, cl, cmd, args=None, rv=None, rvdict=None):
                assert type(i) == int
                assert type(cl) == list
                assert i not in cl
                assert type(cmd) == str
                assert args == None or type(args) == str
                assert rv == None or type(rv) == int
                assert rvdict == None or type(rvdict) == dict
                assert rv == None or rvdict == None

                if rv == None:
                        rv = EXIT_OK
                if rvdict == None:
                        rvdict = {}
                        for c in cl:
                                rvdict[c] = rv
                assert (set(rvdict) | set(cl)) == set(cl)

                if args == None:
                        args = ""

                # sync each child from parent
                for c in cl:
                        rv = rvdict.get(c, EXIT_OK)
                        self._pkg([i], "%s -l %s" % (cmd, self.i_name[c]),
                            args=args, rv=rv)

        def _pkg_child_all(self, i, cmd, args=None, rv=EXIT_OK):
                assert type(i) == int
                assert type(cmd) == str
                assert args == None or type(args) == str
                assert type(rv) == int

                if args == None:
                        args = ""
                self._pkg([i], "%s -a %s" % (cmd, args), rv=rv)

        def _attach_parent(self, il, p, args=None, rv=EXIT_OK):
                assert type(il) == list
                assert type(p) == int
                assert p not in il
                assert args == None or type(args) == str
                assert type(rv) == int

                if args == None:
                        args = ""

                for i in il:
                        self._pkg([i], "attach-linked -p %s %s %s" %
                            (args, self.i_name[i], self.i_path[p]), rv=rv)

        def _attach_child(self, i, cl, args=None, rv=None, rvdict=None):
                assert type(i) == int
                assert type(cl) == list
                assert i not in cl
                assert args == None or type(args) == str
                assert rvdict == None or type(rvdict) == dict
                assert rv == None or rvdict == None

                if rv == None:
                        rv = EXIT_OK
                if rvdict == None:
                        rvdict = {}
                        for c in cl:
                                rvdict[c] = rv
                assert (set(rvdict) | set(cl)) == set(cl)

                if args == None:
                        args = ""

                # attach each child to parent
                for c in cl:
                        rv = rvdict.get(c, EXIT_OK)
                        self._pkg([i], "attach-linked -c %s %s %s" %
                            (args, self.i_name[c], self.i_path[c]),
                            rv=rv)


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
                args = "-a -l %s" % self.i_name[1]
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)

                # can't combine -I and -i
                args = "-I -i %s" % self.i_name[1]
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)
                self._pkg([0], "list-linked", args=args, rv=rv)

                # can't combine -i and -a
                args = "-a -i %s" % self.i_name[1]
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)

                # can't combine -I and -a
                args = "-I -a"
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)

                # can't combine -I and -l
                args = "-I -l %s" % self.i_name[1]
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)

                # can't combine -i and -l with same target
                args = "-i %s -l %s" % (self.i_name[1], self.i_name[1])
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
                args = "-l %s" % self.i_name[1]
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
                        args = "-a %s" % arg
                        self._pkg([0], "sync-linked", args=args, rv=rv)

                        args = "-l %s %s" % (self.i_name[1], arg)
                        self._pkg([0], "sync-linked", args=args, rv=rv)
                        self._pkg([0], "set-property-linked", args=args, rv=rv)

        def test_opts_2_invalid_bad_child(self):
                self._imgs_create(2)

                rv = EXIT_OOPS

                # try using an invalid child name
                self._pkg([0], "attach-linked -c foobar %s" % \
                    self.i_path[1], rv=rv)

                for lin in ["foobar", self.i_name[1]]:
                        # try using an invalid and unknown child name
                        args = "-l %s" % lin

                        self._pkg([0], "sync-linked", args=args, rv=rv)
                        self._pkg([0], "audit-linked", args=args, rv=rv)
                        self._pkg([0], "property-linked", args=args, rv=rv)
                        self._pkg([0], "set-property-linked", args=args, rv=rv)
                        self._pkg([0], "detach-linked", args=args, rv=rv)

                        # try to ignore invalid unknown children
                        args = "-i %s" % lin

                        # operations on the parent image
                        self._pkg([0], "sync-linked", args=args, rv=rv)
                        self._pkg([0], "list-linked", args=args, rv=rv)
                        self._pkg([0], "update", args=args, rv=rv)
                        self._pkg([0], "install", args= \
                            "-i %s %s" % (lin, self.p_foo1_name[1]), rv=rv)
                        self._pkg([0], "change-variant", args= \
                            "-i %s -v variant.foo=baz" % lin, rv=rv)
                        # TODO: test change-facet

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
                self._pkg([0], "attach-linked -c %s %s" %
                    (self.i_name[1], self.i_path[2]), rv=rv)

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
                self._pkg([0], "attach-linked -v -c zone:foo %s" %
                    self.i_path[1], rv=rv)
                self._v_not_linked([0, 1])

                # force attach (p2c) zone image
                self._pkg([0], "attach-linked -v -f -c zone:foo %s" %
                    self.i_path[1])
                self._v_not_linked([0])
                self._v_has_parent([1])

                self._imgs_create(2)

                # by default we can't attach (c2p) zone image
                self._pkg([1], "attach-linked -v -p zone:foo %s" %
                    self.i_path[0], rv=rv)
                self._v_not_linked([0, 1])

                # force attach (c2p) zone image
                self._pkg([1], "attach-linked -v -f -p zone:foo %s" %
                    self.i_path[0])
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
                                self._ccmd("mkdir -p %s" % self.i_path[0])
                        if i == 1:
                                # delete the parent image
                                self.set_image(0)
                                self.image_destroy()

                        # operations that need to access the parent should fail
                        self._pkg([1], "sync-linked", rv=rv)
                        self._pkg([1], "audit-linked", rv=rv)
                        self._pkg([1], "install %s" % self.p_foo1_name[1], \
                            rv=rv)
                        self._pkg([1], "image-update", rv=rv)

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
                                    "%s/%s" % (self.i_path[1],
                                    image.img_user_prefix))
                                self._ccmd("mkdir -p "
                                    "%s/%s" % (self.i_path[1],
                                    image.img_root_prefix))
                        if i == 1:
                                # delete the child image
                                self.set_image(1)
                                self.image_destroy()
                                self._ccmd("mkdir -p %s" % self.i_path[1])
                        if i == 2:
                                # delete the child image
                                self.set_image(1)
                                self.image_destroy()


                        # child should still be listed
                        self._pkg([0], "list-linked -H > %s" % outfile)
                        self._ccmd("cat %s" % outfile)
                        self._ccmd("egrep '^%s[ 	]' %s" %
                            (self.i_name[1], outfile))

                        # child should still be listed
                        self._pkg([0], "property-linked -H -l %s > %s" %
                            (self.i_name[1], outfile))
                        self._ccmd("cat %s" % outfile)
                        self._ccmd("egrep '^li-' %s" % outfile)

                        # operations that need to access child should fail
                        self._pkg_child(0, [1], "sync-linked", rv=rv)
                        self._pkg_child_all(0, "sync-linked", rv=rv)

                        self._pkg_child(0, [1], "audit-linked", rv=rv)
                        self._pkg_child_all(0, "audit-linked", rv=rv)

                        self._pkg_child(0, [1], "detach-linked", rv=rv)
                        self._pkg_child_all(0, "detach-linked", rv=rv)

                        # TODO: test more recursive ops here
                        # image-update, install, uninstall, etc

        def test_ignore_1_no_children(self):
                self._imgs_create(1)
                outfile = os.path.join(self.test_root, "res")

                # it's ok to use -I with no children
                self._pkg([0], "list-linked -H -I > %s" % outfile)
                self._ccmd("cat %s" % outfile)
                self._ccmd("egrep '^$|.' %s" % outfile, rv=EXIT_OOPS)

        def test_ignore_2_ok(self):
                self._imgs_create(3)
                self._attach_child(0, [1, 2])
                outfile = os.path.join(self.test_root, "res")

                # ignore one child
                self._pkg([0], "list-linked -H -i %s > %s" %
                    (self.i_name[1], outfile))
                self._ccmd("cat %s" % outfile)
                self._ccmd("egrep '^%s[ 	]' %s" %
                    (self.i_name[1], outfile), rv=EXIT_OOPS)
                self._ccmd("egrep '^%s[ 	]' %s" %
                    (self.i_name[2], outfile))

                # manually ignore all children
                self._pkg([0], "list-linked -H -i %s -i %s > %s" %
                    (self.i_name[1], self.i_name[2], outfile))
                self._ccmd("cat %s" % outfile)
                self._ccmd("egrep '^$|.' %s" % outfile, rv=EXIT_OOPS)

                # automatically ignore all children
                self._pkg([0], "list-linked -H -I > %s" % outfile)
                self._ccmd("cat %s" % outfile)
                self._ccmd("egrep '^$|.' %s" % outfile, rv=EXIT_OOPS)

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
                        self._pkg([i], "install -v %s" % self.p_foo1_name[i])

                self._attach_child(0, [1], args="--no-pkg-updates")
                self._attach_parent([2], 0, args="--no-pkg-updates")

                # verify the un-synced packages
                for i in [0, 1, 2]:
                        self._pkg([i], "list -v %s" % self.p_foo1_name[i])

        def test_no_pkg_updates_2_foo_via_sync(self):
                """test --no-pkg-updates with a non-empty image."""
                self._imgs_create(4)

                # install different un-synced packages into each image
                for i in range(4):
                        self._pkg([i], "install -v %s" % self.p_foo1_name[i])

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
                        self._pkg([i], "list -v %s" % self.p_foo1_name[i])

        def test_no_pkg_updates_2_foo_via_set_property_linked_TODO(self):
                """test --no-pkg-updates with a non-empty image."""
                pass

        def test_no_pkg_updates_3_sync_via_attach(self):
                """test --no-pkg-updates with an in sync package"""
                self._imgs_create(3)

                # install the same synced packages into each image
                for i in range(3):
                        self._pkg([i], "install -v %s" % self.p_sync1_name[1])

                self._attach_child(0, [1], args="--no-pkg-updates")
                self._attach_parent([2], 0, args="--no-pkg-updates")

                # verify the synced packages
                for i in range(3):
                        self._pkg([i], "list -v %s" % self.p_sync1_name[1])

        def test_no_pkg_updates_3_sync_via_sync(self):
                """test --no-pkg-updates with an in sync package"""
                self._imgs_create(4)

                # install the same synced packages into each image
                for i in range(4):
                        self._pkg([i], "install -v %s" % self.p_sync1_name[1])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2], args="--linked-md-only")
                self._attach_parent([3], 0, args="--linked-md-only")

                # verify the synced packages
                for i in range(4):
                        self._pkg([i], "list -v %s" % self.p_sync1_name[1])

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
                        self._pkg([i], "install -v %s" % self.p_sync1_name[i+1])

                self._attach_child(0, [1], args="--no-pkg-updates",
                    rv=EXIT_OOPS)
                self._attach_parent([2], 0, args="--no-pkg-updates",
                    rv=EXIT_OOPS)

                # verify packages
                for i in range(3):
                        self._pkg([i], "list -v %s" % self.p_sync1_name[i+1])

        def test_no_pkg_updates_3_fail_via_sync(self):
                """test --no-pkg-updates with an out of sync package"""
                self._imgs_create(4)

                # install different synced packages into each image
                for i in range(4):
                        self._pkg([i], "install -v %s" % self.p_sync1_name[i+1])

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
                        self._pkg([i], "list -v %s" % self.p_sync1_name[i+1])

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
                        self._pkg([i], "install -v %s" % self.p_foo1_name[i])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2, 3], args="--linked-md-only")

                self._pkg([1, 2, 3], "audit-linked")
                self._pkg_child(0, [1, 2, 3], "audit-linked")
                self._pkg_child_all(0, "audit-linked")

        def test_audit_synced_3(self):
                self._imgs_create(4)

                # install synced package into parent
                self._pkg([0], "install -v %s" % self.p_sync1_name[0])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2, 3], args="--linked-md-only")

                self._pkg([1, 2, 3], "audit-linked")
                self._pkg_child(0, [1, 2, 3], "audit-linked")
                self._pkg_child_all(0, "audit-linked")

        def test_audit_synced_4(self):
                self._imgs_create(4)

                # install same synced packages into parent and some children
                for i in [0, 1, 2, 3]:
                        self._pkg([i], "install -v %s" % self.p_sync1_name[0])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2, 3], args="--linked-md-only")

                self._pkg([1, 2, 3], "audit-linked")
                self._pkg_child(0, [1, 2, 3], "audit-linked")
                self._pkg_child_all(0, "audit-linked")


class TestPkgLinked2(TestPkgLinked):
        """Class used solely to split up the test suite for parallelization."""

        def test_audit_diverged_1(self):
                self._imgs_create(4)

                # install different synced package into some child images
                for i in [1, 3]:
                        self._pkg([i], "install -v %s" % self.p_sync1_name[i])

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
                        self._pkg([i], "install -v %s" % self.p_sync1_name[i])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2, 3], args="--linked-md-only")

                rv = EXIT_DIVERGED
                self._pkg([1, 2, 3], "audit-linked", rv=rv)
                self._pkg_child(0, [1, 2, 3], "audit-linked", rv=rv)
                self._pkg_child_all(0, "audit-linked", rv=rv)

        def test_sync_fail(self):
                self._imgs_create(3)

                # install newer sync'ed package into child
                self._pkg([0], "install -v %s" % self.p_sync1_name[2])
                self._pkg([1], "install -v %s" % self.p_sync1_name[1])
                self._pkg([2], "install -v %s" % self.p_sync1_name[1])

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

                # trying to sync via image-update should fail
                self._pkg([1, 2], "image-update -vn", rv=EXIT_OOPS)
                self._pkg([1, 2], "image-update -v", rv=EXIT_OOPS)

                # trying to sync via install should fail
                self._pkg([1, 2], "install -vn %s", self.p_sync1_name[0],
                    rv=EXIT_OOPS)
                self._pkg([1, 2], "install -v %s", self.p_sync1_name[0],
                    rv=EXIT_OOPS)

                # verify the child is still divereged
                rv = EXIT_DIVERGED
                self._pkg([1, 2], "audit-linked", rv=rv)

        def test_sync_1(self):
                self._imgs_create(5)

                # install different synced package into each image
                for i in [0, 1, 2, 3, 4]:
                        self._pkg([i], "install -v %s" % self.p_sync1_name[i])

                # install unsynced packages to make sure they aren't molested
                self._pkg([0], "install -v %s" % self.p_foo1_name[1])
                self._pkg([1, 2, 3, 4], "install -v %s" % self.p_foo1_name[2])

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
                self._pkg([1, 2, 3, 4], "list -v %s" % self.p_foo1_name[2])

        def test_sync_2_via_attach(self):
                self._imgs_create(3)

                # install different synced package into each image
                self._pkg([0], "install -v %s" % self.p_sync1_name[1])
                self._pkg([1, 2], "install -v %s" % self.p_sync1_name[2])

                # install unsynced packages to make sure they aren't molested
                self._pkg([0], "install -v %s" % self.p_foo1_name[1])
                self._pkg([1, 2], "install -v %s" % self.p_foo1_name[2])

                # attach children
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # check synced and unsynced packages
                self._pkg([1, 2], "list -v %s" % self.p_sync1_name[1])
                self._pkg([1, 2], "list -v %s" % self.p_foo1_name[2])

        def test_sync_2_via_image_update(self):
                self._imgs_create(3)

                # install different synced package into each image
                self._pkg([0], "install -v %s" % self.p_sync1_name[1])
                self._pkg([1, 2], "install -v %s" % self.p_sync1_name[2])

                # install unsynced packages to make sure they are updated
                self._pkg([0], "install -v %s" % self.p_foo1_name[1])
                self._pkg([1, 2], "install -v %s" % self.p_foo1_name[2])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1], args="--linked-md-only")
                self._attach_parent([2], 0, args="--linked-md-only")

                # plan sync
                self._pkg([1, 2], "image-update -vn")
                self._pkg([1, 2], "audit-linked", rv=EXIT_DIVERGED)

                # sync child
                self._pkg([1, 2], "image-update --parsable=0")
                self.assertEqualParsable(self.output, change_packages=[
                    [self.foo1_list[2], self.foo1_list[0]],
                    [self.s1_list[2], self.s1_list[1]]])
                self._pkg([1, 2], "audit-linked")
                self._pkg([1, 2], "image-update -v", rv=EXIT_NOP)
                self._pkg([1, 2], "sync-linked -v", rv=EXIT_NOP)

                # check unsynced packages
                self._pkg([1, 2], "list -v %s" % self.p_foo1_name[0])

        def test_sync_2_via_install(self):
                self._imgs_create(3)

                # install different synced package into each image
                self._pkg([0], "install -v %s" % self.p_sync1_name[1])
                self._pkg([1, 2], "install -v %s" % self.p_sync1_name[2])

                # install unsynced packages to make sure they aren't molested
                self._pkg([0], "install -v %s" % self.p_foo1_name[1])
                self._pkg([1, 2], "install -v %s" % self.p_foo1_name[2])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1], args="--linked-md-only")
                self._attach_parent([2], 0, args="--linked-md-only")

                # plan sync
                self._pkg([1, 2], "install -vn %s" % self.p_sync1_name[1])
                self._pkg([1, 2], "audit-linked", rv=EXIT_DIVERGED)

                # sync child
                self._pkg([1, 2], "install -v %s" % self.p_sync1_name[1])
                self._pkg([1, 2], "audit-linked")
                self._pkg([1, 2], "install -v %s" % self.p_sync1_name[1],
                    rv=EXIT_NOP)
                self._pkg([1, 2], "sync-linked -v", rv=EXIT_NOP)

                # check unsynced packages
                self._pkg([1, 2], "list -v %s" % self.p_foo1_name[2])

        def test_no_sync_2_via_change_variant(self):
                self._imgs_create(3)

                # install different synced package into each image
                self._pkg([0], "install -v %s" % self.p_sync1_name[1])
                self._pkg([1, 2], "install -v %s" % self.p_sync1_name[2])

                # install unsynced packages to make sure they aren't molested
                self._pkg([0], "install -v %s" % self.p_foo1_name[1])
                self._pkg([1, 2], "install -v %s" % self.p_foo1_name[2])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1], args="--linked-md-only")
                self._attach_parent([2], 0, args="--linked-md-only")

                # plan sync
                self._pkg([1, 2], "change-variant -vn variant.foo=baz")
                self._pkg([1, 2], "audit-linked", rv=EXIT_DIVERGED)

                # sync child
                self._pkg([1, 2], "change-variant -v variant.foo=baz")
                self._pkg([1, 2], "audit-linked", rv=EXIT_DIVERGED)
                self._pkg([1, 2], "change-variant -v variant.foo=baz",
                    rv=EXIT_NOP)

                # check unsynced packages
                self._pkg([1, 2], "list -v %s" % self.p_foo1_name[2])


class TestPkgLinked3(TestPkgLinked):
        """Class used solely to split up the test suite for parallelization."""

        def test_parent_sync_1_nosync(self):
                self._imgs_create(2)

                # install synced package into each image
                self._pkg([0, 1], "install -v %s" % self.p_sync1_name[1])

                self._attach_parent([1], 0)

                # update parent image
                self._pkg([0], "install -v %s" % self.p_sync1_name[0])

                # there should be no updates with --no-parent-sync
                self._pkg([1], "sync-linked -v --no-parent-sync", rv=EXIT_NOP)
                self._pkg([1], "image-update -v --no-parent-sync", rv=EXIT_NOP)
                self._pkg([1], "install -v --no-parent-sync %s" % \
                    self.p_sync1_name[1], rv=EXIT_NOP)
                self._pkg([1], "change-variant -v --no-parent-sync "
                    "variant.foo=bar", rv=EXIT_NOP)
                # TODO: test set-property-linked

                # an audit without a parent sync should thingk we're in sync
                self._pkg([1], "audit-linked --no-parent-sync")

                # an full audit should realize we're not in sync
                self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)

                # the audit above should not have updated our image, so we
                # should still be out of sync.
                self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)

        def test_parent_sync_2_via_sync(self):
                self._imgs_create(2)

                # install synced package into each image
                self._pkg([0, 1], "install -v %s" % self.p_sync1_name[1])

                self._attach_parent([1], 0)

                # update parent image
                self._pkg([0], "install -v %s" % self.p_sync1_name[0])

                # verify that pkg operations sync parent metadata
                self._pkg([1], "sync-linked -v -n")
                self._pkg([1], "sync-linked -v")
                self._pkg([1], "sync-linked -v", rv=EXIT_NOP)
                self._pkg([1], "audit-linked")

        def test_parent_sync_2_via_image_update(self):
                self._imgs_create(2)

                # install synced package into each image
                self._pkg([0, 1], "install -v %s" % self.p_sync1_name[1])

                self._attach_parent([1], 0)

                # update parent image
                self._pkg([0], "install -v %s" % self.p_sync1_name[0])

                # verify that pkg operations sync parent metadata
                self._pkg([1], "image-update -v -n")
                self._pkg([1], "image-update -v")
                self._pkg([1], "image-update -v", rv=EXIT_NOP)
                self._pkg([1], "audit-linked")

        def test_parent_sync_2_via_install(self):
                self._imgs_create(2)

                # install synced package into each image
                self._pkg([0, 1], "install -v %s" % self.p_sync1_name[1])

                self._attach_parent([1], 0)

                # update parent image
                self._pkg([0], "install -v %s" % self.p_sync1_name[0])

                # verify that pkg operations sync parent metadata
                self._pkg([1], "install -v -n %s" % self.p_sync1_name[0])
                self._pkg([1], "install -v %s" % self.p_sync1_name[0])
                self._pkg([1], "install -v %s" % self.p_sync1_name[0],
                    rv=EXIT_NOP)
                self._pkg([1], "audit-linked")

        def test_parent_no_sync_2_via_change_variant(self):
                self._imgs_create(2)

                # install synced package into each image
                self._pkg([0, 1], "install -v %s" % self.p_sync1_name[1])

                self._attach_parent([1], 0)

                # update parent image
                self._pkg([0], "install -v %s" % self.p_sync1_name[0])

                # verify that pkg operations sync parent metadata
                self._pkg([1], "change-variant -v -n variant.foo=baz")
                self._pkg([1], "change-variant -v variant.foo=baz")
                self._pkg([1], "change-variant -v variant.foo=baz", rv=EXIT_NOP)
                self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)

        def test_install_constrainted(self):
                self._imgs_create(3)

                # install synced package into parent
                self._pkg([0], "install -v %s" % self.p_sync1_name[1])

                # attach children
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # try to install a different vers of synced package
                for i in [0, 2, 3, 4]:
                        self._pkg([1, 2], "install -v %s" % \
                            self.p_sync1_name[i], rv=EXIT_OOPS)

                # try to install a different synced package
                for i in [0, 1, 2, 3, 4]:
                        self._pkg([1, 2], "install -v %s" % \
                            self.p_sync2_name[i], rv=EXIT_OOPS)

                # install random un-synced package
                self._pkg([1, 2], "install -v %s" % self.p_foo1_name[0])

                # install the same ver of a synced package in the child
                self._pkg([1, 2], "install -v %s" % self.p_sync1_name[1])

        def test_p2c_recurse_1_image_update(self):
                self._imgs_create(3)

                # install different synced package into each image
                for i in [0, 1]:
                        self._pkg([i], "install -v %s" % self.p_sync1_name[1])
                for i in [2]:
                        self._pkg([i], "install -v %s" % self.p_sync1_name[2])

                # attach --linked-md-only doesn't install constraints package
                self._attach_child(0, [1])
                self._attach_child(0, [2], args="--linked-md-only")

                self._pkg([0], "image-update -v -n")
                self._pkg([0], "image-update --parsable=0")
                self.assertEqualParsable(self.output,
                    change_packages=[[self.s1_list[1], self.s1_list[0]]],
                    child_images=[{
                        "image_name": "system:img1",
                        "change_packages": [[self.s1_list[1], self.s1_list[0]]],
                    },
                    {
                        "image_name": "system:img2",
                        "change_packages": [[self.s1_list[2], self.s1_list[0]]],
                    }])
                self._pkg([0], "image-update -v", rv=EXIT_NOP)

                # make sure the latest synced packaged is in every image
                for i in [0, 1, 2]:
                        self._pkg([i], "list -v %s " % self.p_sync1_name[0])

                # children should be synced
                self._pkg([1, 2], "audit-linked")

        def test_p2c_recurse_1_install_1(self):
                self._imgs_create(3)

                # install different synced package into each image
                for i in [0, 1]:
                        self._pkg([i], "install -v %s" % self.p_sync1_name[1])
                for i in [2]:
                        self._pkg([i], "install -v %s" % self.p_sync1_name[2])

                # attach --linked-md-only doesn't install constraints package
                self._attach_child(0, [1])
                self._attach_child(0, [2], args="--linked-md-only")

                self._pkg([0], "install -v -n %s" % self.p_sync1_name[0])
                self._pkg([0], "install --parsable=0 %s" % self.p_sync1_name[0])
                self.assertEqualParsable(self.output,
                    change_packages=[[self.s1_list[1], self.s1_list[0]]],
                    child_images=[{
                        "image_name": "system:img1",
                        "change_packages": [[self.s1_list[1], self.s1_list[0]]],
                    },
                    {
                        "image_name": "system:img2",
                        "change_packages": [[self.s1_list[2], self.s1_list[0]]],
                    }])
                self._pkg([0], "install -v %s" % self.p_sync1_name[0],
                    rv=EXIT_NOP)

                # make sure the latest synced packaged is in every image
                for i in [0, 1, 2]:
                        self._pkg([i], "list -v %s " % self.p_sync1_name[0])

                # children should be synced
                self._pkg([1, 2], "audit-linked")

        def test_verify(self):
                self._imgs_create(5)

                # install synced package into each image
                self._pkg([0, 1], "install -v %s" % self.p_sync1_name[1])

                # test with a newer synced package
                self._pkg([2], "install -v %s" % self.p_sync1_name[0])

                # test with an older synced package
                self._pkg([3], "install -v %s" % self.p_sync1_name[2])

                # test with a different synced package
                self._pkg([4], "install -v %s" % self.p_sync2_name[2])

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


class TestPkgLinkedScale(pkg5unittest.ManyDepotTestCase):
        """Test the scalability of the linked image subsystem."""

        max_image_count = 256

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
        p_sunc1_name_gen = "sync1"
        pkgs = [p_sunc1_name_gen + ver for ver in p_vers]
        p_sync1_name = dict(zip(range(len(pkgs)), pkgs))
        for i in p_sync1_name:
                p_data = "open %s\n" % p_sync1_name[i]
                p_data += "add depend type=parent fmri=%s" % \
                    pkg.actions.depend.DEPEND_SELF
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
                            "%d GB required, %d GB detected.\n" %
                            (phys_mem_req, phys_mem))

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
                    **kwargs);

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
                12 GB of memory."""

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
                self.pkg("install -v %s" % self.p_sync1_name[1])

                # create copies of the image.
                for i in range(1, self.max_image_count):
                        self.image_clone(i)

                # attach the copies as children of the original image
                for i in range(1, self.max_image_count):
                        name = "system:img%d" % i
                        cmd = "attach-linked --linked-md-only -c %s %s" % (
                            name, self.img_path(i))
                        self.pkg(cmd)

                # update the parent image and all child images in parallel
                self.pkg("update -C0 -q")

if __name__ == "__main__":
        unittest.main()
