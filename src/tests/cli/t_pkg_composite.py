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

# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.fmri as fmri
import pkg.portable as portable
import pkg.misc as misc
import pkg.p5p
import shutil
import stat
import tempfile
import unittest


class TestPkgCompositePublishers(pkg5unittest.ManyDepotTestCase):

        # Don't discard repository or setUp() every test.
        persistent_setup = True
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        foo_pkg = """
            open pkg://test/foo@1.0
            add set name=pkg.summary value="Example package foo."
            add dir mode=0755 owner=root group=bin path=lib
            add dir mode=0755 owner=root group=bin path=usr
            add dir mode=0755 owner=root group=bin path=usr/bin
            add dir mode=0755 owner=root group=bin path=usr/local
            add dir mode=0755 owner=root group=bin path=usr/local/bin
            add dir mode=0755 owner=root group=bin path=usr/share
            add dir mode=0755 owner=root group=bin path=usr/share/doc
            add dir mode=0755 owner=root group=bin path=usr/share/doc/foo
            add dir mode=0755 owner=root group=bin path=usr/share/man
            add dir mode=0755 owner=root group=bin path=usr/share/man/man1
            add file tmp/foo mode=0755 owner=root group=bin path=usr/bin/foo
            add file tmp/libfoo.so.1 mode=0755 owner=root group=bin path=lib/libfoo.so.1 variant.debug.foo=false
            add file tmp/libfoo_debug.so.1 mode=0755 owner=root group=bin path=lib/libfoo.so.1 variant.debug.foo=true
            add file tmp/foo.1 mode=0444 owner=root group=bin path=usr/share/man/man1/foo.1 facet.doc.man=true
            add file tmp/README mode=0444 owner=root group=bin path=/usr/share/doc/foo/README
            add link path=usr/local/bin/soft-foo target=usr/bin/foo
            add hardlink path=usr/local/bin/hard-foo target=/usr/bin/foo
            close """

        incorp_pkg = """
            open pkg://test/incorp@1.0
            add set name=pkg.summary value="Incorporation"
            add depend type=incorporate fmri=quux@0.1,5.11-0.1
            close
            open pkg://test/incorp@2.0
            add set name=pkg.summary value="Incorporation"
            add depend type=incorporate fmri=quux@1.0,5.11-0.2
            close """

        signed_pkg = """
            open pkg://test/signed@1.0
            add depend type=require fmri=foo@1.0
            add dir mode=0755 owner=root group=bin path=usr/bin
            add file tmp/quux mode=0755 owner=root group=bin path=usr/bin/quark
            add set name=authorized.species value=bobcat
            close """

        quux_pkg = """
            open pkg://test2/quux@0.1,5.11-0.1
            add set name=pkg.summary value="Example package quux."
            add depend type=require fmri=pkg:/incorp
            close
            open pkg://test2/quux@1.0,5.11-0.2
            add set name=pkg.summary value="Example package quux."
            add depend type=require fmri=pkg:/incorp
            add dir mode=0755 owner=root group=bin path=usr
            add dir mode=0755 owner=root group=bin path=usr/bin
            add file tmp/quux mode=0755 owner=root group=bin path=usr/bin/quux
            close """

        misc_files = ["tmp/foo", "tmp/libfoo.so.1", "tmp/libfoo_debug.so.1",
            "tmp/foo.1", "tmp/README", "tmp/LICENSE", "tmp/quux"]

        def __seed_ta_dir(self, certs, dest_dir=None):
                if isinstance(certs, basestring):
                        certs = [certs]
                if not dest_dir:
                        dest_dir = self.ta_dir
                self.assert_(dest_dir)
                self.assert_(self.raw_trust_anchor_dir)
                for c in certs:
                        name = "%s_cert.pem" % c
                        portable.copyfile(
                            os.path.join(self.raw_trust_anchor_dir, name),
                            os.path.join(dest_dir, name))

        def image_create(self, *args, **kwargs):
                pkg5unittest.ManyDepotTestCase.image_create(self,
                    *args, **kwargs)
                self.ta_dir = os.path.join(self.img_path(), "etc/certs/CA")
                os.makedirs(self.ta_dir)

        def __publish_packages(self, rurl):
                """Private helper function to publish packages needed for
                testing.
                """

                pkgs = "".join([self.foo_pkg, self.incorp_pkg, self.signed_pkg,
                    self.quux_pkg])

                # Publish packages needed for tests.
                plist = self.pkgsend_bulk(rurl, pkgs)

                # Sign the 'signed' package.
                r = self.get_repo(self.dcs[1].get_repodir())
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s -i %(i6)s %(pkg)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "ch1_ta1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_ta1_cert.pem"),
                      "i3": os.path.join(self.chain_certs_dir,
                          "ch3_ta1_cert.pem"),
                      "i4": os.path.join(self.chain_certs_dir,
                          "ch4_ta1_cert.pem"),
                      "i5": os.path.join(self.chain_certs_dir,
                          "ch5_ta1_cert.pem"),
                      "i6": os.path.join(self.chain_certs_dir,
                          "ch1_ta3_cert.pem"),
                      "pkg": plist[3]
                    }
                self.pkgsign(rurl, sign_args)

                # This is just a test assertion to verify that the
                # package was signed as expected.
                self.image_create(rurl, prefix=None)
                self.__seed_ta_dir("ta1")
                self.pkg("set-property signature-policy verify")
                self.pkg("install signed")
                self.image_destroy()

                return [
                    fmri.PkgFmri(sfmri)
                    for sfmri in plist
                ]

        def __archive_packages(self, arc_name, repo, plist):
                """Private helper function to archive packages needed for
                testing.
                """

                arc_path = os.path.join(self.test_root, arc_name)
                assert not os.path.exists(arc_path)

                arc = pkg.p5p.Archive(arc_path, mode="w")
                for pfmri in plist:
                        arc.add_repo_package(pfmri, repo)
                arc.close()

                return arc_path

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test", "test",
                    "test", "empty"])
                self.make_misc_files(self.misc_files)

                # First repository will contain all packages.
                self.all_rurl = self.dcs[1].get_repo_url()

                # Second repository will contain only foo.
                self.foo_rurl = self.dcs[2].get_repo_url()

                # Third repository will contain only signed.
                self.signed_rurl = self.dcs[3].get_repo_url()

                # Fourth will be empty.
                self.empty_rurl = self.dcs[4].get_repo_url()
                self.pkgrepo("refresh -s %s" % self.empty_rurl)

                # Setup base test paths.
                self.path_to_certs = os.path.join(self.ro_data_root,
                    "signing_certs", "produced")
                self.keys_dir = os.path.join(self.path_to_certs, "keys")
                self.cs_dir = os.path.join(self.path_to_certs,
                    "code_signing_certs")
                self.chain_certs_dir = os.path.join(self.path_to_certs,
                    "chain_certs")
                self.pub_cas_dir = os.path.join(self.path_to_certs,
                    "publisher_cas")
                self.inter_certs_dir = os.path.join(self.path_to_certs,
                    "inter_certs")
                self.raw_trust_anchor_dir = os.path.join(self.path_to_certs,
                    "trust_anchors")
                self.crl_dir = os.path.join(self.path_to_certs, "crl")

                # Publish packages.
                plist = self.__publish_packages(self.all_rurl)
                self.pkgrepo("refresh -s %s" % self.all_rurl)

                # Copy foo to second repository and build index.
                self.pkgrecv(self.all_rurl, "-d %s foo" % self.foo_rurl)
                self.pkgrepo("refresh -s %s" % self.foo_rurl)

                # Copy incorp and quux to third repository and build index.
                self.pkgrecv(self.all_rurl, "-d %s signed" % self.signed_rurl)
                self.pkgrepo("refresh -s %s" % self.signed_rurl)

                # Now create a package archive containing all packages, and
                # then one for each.
                repo = self.dcs[1].get_repo()
                self.all_arc = self.__archive_packages("all_pkgs.p5p", repo,
                    plist)

                for alist in ([plist[0]], [plist[1], plist[2]], [plist[3]],
                    [plist[4], plist[5]]):
                        arc_path = self.__archive_packages(
                            "%s.p5p" % alist[0].pkg_name, repo, alist)
                        setattr(self, "%s_arc" % alist[0].pkg_name, arc_path)

                self.ta_dir = None

                # Store FMRIs for later use.
                self.foo10 = plist[0]
                self.incorp10 = plist[1]
                self.incorp20 = plist[2]
                self.signed10 = plist[3]
                self.quux01 = plist[4]
                self.quux10 = plist[5]

        def test_00_list(self):
                """Verify that the list operation works as expected when
                compositing publishers.
                """

                # Create an image and verify no packages are known.
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("set-property signature-policy ignore")
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                self.pkg("list -a", exit=1)

                # Verify list output for multiple, disparate sources using
                # different combinations of archives and repositories.
                self.pkg("set-publisher -g %s -g %s test" % (self.signed_arc,
                    self.foo_rurl))
                self.pkg("list -afH ")
                expected = \
                    ("foo (test) 1.0 ---\n"
                    "signed (test) 1.0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                self.pkg("set-publisher -G %s -g %s test" % (self.foo_rurl,
                    self.foo_arc))
                self.pkg("set-publisher -g %s test" % self.incorp_arc)
                self.pkg("set-publisher -g %s test2" % self.quux_arc)
                self.pkg("list -afH")
                expected = \
                    ("foo (test) 1.0 ---\n"
                    "incorp (test) 2.0 ---\n"
                    "incorp (test) 1.0 ---\n"
                    "quux (test2) 1.0-0.2 ---\n"
                    "quux (test2) 0.1-0.1 ---\n"
                    "signed (test) 1.0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                self.pkg("set-publisher -G %s -g %s test" % (self.foo_arc,
                    self.foo_rurl))
                self.pkg("list -afH")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                self.pkg("set-publisher -G \* -g %s test" % self.all_arc)
                self.pkg("set-publisher -G %s -g %s -g %s test2" % (
                    self.quux_arc, self.all_arc, self.all_rurl))
                self.pkg("list -afH -g %s -g %s" % (self.all_arc,
                    self.all_rurl))
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Verify packages can be installed from disparate sources and
                # show in default list output.
                self.pkg("install incorp@1.0 quux signed")
                self.pkg("list -H")
                expected = \
                    ("foo (test) 1.0 i--\n"
                    "incorp (test) 1.0 i--\n"
                    "quux (test2) 0.1-0.1 i--\n"
                    "signed (test) 1.0 i--\n")

                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_01_info(self):
                """Verify that the info operation works as expected when
                compositing publishers.
                """

                # Create an image and verify no packages are known.
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("list -a", exit=1)

                # Verify info result for multiple disparate sources using
                # different combinations of archives and repositories.
                self.pkg("set-publisher -g %s -g %s test" % (self.signed_arc,
                    self.foo_rurl))
                self.pkg("info -r signed@1.0 foo@1.0")

                self.pkg("set-publisher -G %s -g %s -g %s test" %
                    (self.foo_rurl, self.foo_arc, self.incorp_arc))
                self.pkg("set-publisher -g %s test2" % self.quux_arc)
                self.pkg("info -r foo@1.0 incorp@1.0 signed@1.0 quux@0.1")

                self.pkg("set-publisher -G %s -g %s test" % (self.foo_arc,
                    self.foo_rurl))
                self.pkg("info -g %s -g %s -g %s -g %s foo@1.0 incorp@1.0 "
                    "signed@1.0 quux@0.1" % (
                    self.signed_arc, self.incorp_arc, self.quux_arc,
                    self.foo_rurl))

                self.pkg("set-publisher -G \* -g %s -g %s test" %
                    (self.all_arc, self.all_rurl))
                self.pkg("set-publisher -G \* -g %s -g %s test2" %
                    (self.all_arc, self.all_rurl))
                self.pkg("info -r foo@1.0 incorp@2.0 signed@1.0 quux@1.0")

                # Verify package installed from archive shows in default info
                # output.
                self.pkg("install foo@1.0")
                self.pkg("info")
                expected = """\
          Name: foo
       Summary: Example package foo.
         State: Installed
     Publisher: test
       Version: 1.0
 Build Release: 5.11
        Branch: None
Packaging Date: %(pkg_date)s
          Size: 41.00 B
          FMRI: %(pkg_fmri)s
""" % { "pkg_date": self.foo10.version.get_timestamp().strftime("%c"),
    "pkg_fmri": self.foo10 }
                self.assertEqualDiff(expected, self.output)

        def test_02_contents(self):
                """Verify that the contents operation works as expected when
                compositing publishers.
                """

                # Create an image and verify no packages are known.
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("list -a", exit=1)

                # Verify contents result for multiple disparate sources using
                # different combinations of archives and repositories.
                self.pkg("set-publisher -g %s -g %s test" % (self.signed_arc,
                    self.foo_rurl))
                self.pkg("contents -r signed@1.0 foo@1.0")

                self.pkg("set-publisher -G %s -g %s -g %s test" %
                    (self.foo_rurl, self.foo_arc, self.incorp_arc))
                self.pkg("set-publisher -g %s test2" % self.quux_arc)
                self.pkg("contents -r foo@1.0 incorp@1.0 signed@1.0 quux@0.1")

                self.pkg("set-publisher -G %s -g %s test" % (self.foo_arc,
                    self.foo_rurl))
                self.pkg("contents -r foo@1.0 incorp@1.0 signed@1.0 quux@0.1")

                self.pkg("set-publisher -G \* -g %s -g %s test" %
                    (self.all_arc, self.all_rurl))
                self.pkg("set-publisher -G \* -g %s -g %s test2" %
                    (self.all_arc, self.all_rurl))
                self.pkg("contents -r foo@1.0 incorp@2.0 signed@1.0 quux@1.0")

                # Verify package installed from archive can be used with
                # contents.
                self.pkg("install foo@1.0")
                self.pkg("contents foo")

        def test_03_install_update(self):
                """Verify that install and update work as expected when
                compositing publishers.
                """

                #
                # Create an image and verify no packages are known.
                #
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("set-property signature-policy ignore")
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                self.pkg("list -a", exit=1)

                # Verify that packages with dependencies can be installed when
                # using multiple, disparate sources.
                self.pkg("set-publisher -g %s -g %s test" % (self.foo_arc,
                    self.signed_arc))
                self.pkg("install signed")
                self.pkg("list foo signed")
                self.pkg("uninstall \*")

                # Verify publisher can be removed.
                self.pkg("unset-publisher test")

                #
                # Create an image using the signed archive.
                #
                self.image_create(misc.parse_uri(self.signed_arc), prefix=None)
                self.__seed_ta_dir("ta1")

                # Verify that signed package can be installed and the archive
                # configured for the publisher allows dependencies to be
                # satisfied.
                self.pkg("set-publisher -g %s test" % self.foo_arc)
                self.pkg("set-property signature-policy verify")
                self.pkg("publisher test")
                self.pkg("install signed")
                self.pkg("list foo signed")

                # Verify that removing all packages and the signed archive as
                # a source leaves only foo known.
                self.pkg("uninstall \*")
                self.pkg("set-publisher -G %s test" % self.signed_arc)
                self.pkg("list -aH")
                expected = \
                    ("foo 1.0 ---\n"
                    "signed 1.0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                #
                # Create an image and verify no packages are known.
                #
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("list -a", exit=1)

                # Install an older version of a known package.
                self.pkg("set-publisher -g %s test" % self.all_arc)
                self.pkg("set-publisher -g %s test2" % self.all_arc)
                self.pkg("install quux@0.1")
                self.pkg("list incorp@1.0 quux@0.1")

                # Verify that packages can be updated when using multiple,
                # disparate sources (that have some overlap).
                self.pkg("set-publisher -g %s test" % self.incorp_arc)
                self.pkg("update")
                self.pkg("list incorp@2.0 quux@1.0")

                #
                # Create an image using the signed archive.
                #
                self.image_create(misc.parse_uri(self.signed_arc), prefix=None)
                self.__seed_ta_dir("ta1")

                # Add the incorp archive as a source.
                self.pkg("set-publisher -g %s test" % self.incorp_arc)

                # Now verify that temporary package sources can be used during
                # package operations when multiple, disparate sources are
                # already configured for the same publisher.
                self.pkg("install -g %s incorp signed" % self.foo_rurl)
                self.pkg("list incorp foo signed")

        def test_04_search(self):
                """Verify that search works as expected when compositing
                publishers.
                """

                #
                # Create an image and verify no packages are known.
                #
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("list -a", exit=1)

                # Add multiple, different sources.
                self.pkg("set-publisher -g %s -g %s test" % (self.foo_rurl,
                    self.signed_rurl))

                # Verify a remote search that should only match one of the
                # sources works as expected.
                self.pkg("search -Hpr -o pkg.shortfmri /usr/bin/foo")
                expected = "pkg:/foo@1.0\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Verify a remote search for multiple terms that should match
                # each source works as expected.
                self.pkg("search -Hpr -o pkg.shortfmri /usr/bin/foo OR "
                    "/usr/bin/quark")
                expected = \
                    ("pkg:/foo@1.0\n"
                    "pkg:/signed@1.0\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Add a source that partially overlaps with the existing ones
                # (provides some of the same packages) and verify that some
                # of the results are duplicated (since search across sources
                # is a simple aggregation of all sources).
                self.pkg("set-publisher -g %s test" % self.all_rurl)
                self.pkg("search -Hpr -o pkg.shortfmri /usr/bin/foo OR "
                    "/usr/bin/quark OR Incorporation")
                expected = \
                    ("pkg:/foo@1.0\n"
                    "pkg:/incorp@1.0\n"
                    "pkg:/incorp@2.0\n"
                    "pkg:/signed@1.0\n"
                    "pkg:/foo@1.0\n"
                    "pkg:/signed@1.0\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Add a publisher with no origins and verify output still
                # matches expected (although it will currently exit 3).
                self.pkg("set-publisher no-origins")
                self.pkg("search -Hpr -o pkg.shortfmri /usr/bin/foo OR "
                    "/usr/bin/quark OR Incorporation", exit=3)
                output = self.reduceSpaces(self.output)

                # Elide error output from client to verify that search
                # results were returned despite error.
                output = output[:output.find("pkg: ")] + "\n"
                self.assertEqualDiff(expected, output)


if __name__ == "__main__":
        unittest.main()
