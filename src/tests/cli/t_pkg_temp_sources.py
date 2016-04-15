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
# Copyright (c) 2011, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import json
import os
import pkg.catalog as catalog
import pkg.fmri as fmri
import pkg.portable as portable
import pkg.misc as misc
import pkg.p5p
import shutil
import six
import stat
import tempfile
import unittest


class TestPkgTempSources(pkg5unittest.ManyDepotTestCase):

        # Don't discard repository or setUp() every test.
        persistent_setup = True
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        foo_pkg = """
            open pkg://test/foo@1.0
            add set name=pkg.summary value="Example package foo."
            add set name=variant.debug.foo value=true value=false
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

        licensed_pkg = """
            open pkg://test2/licensed@1.0
            add license tmp/LICENSE license=sample_license
            close """

        licensed_pkg_2 = """
            open pkg://test2/licensed@2.0
            add license tmp/LICENSE2 license=sample_license
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
            "tmp/foo.1", "tmp/README", "tmp/LICENSE", "tmp/LICENSE2", "tmp/quux"]

        def __seed_ta_dir(self, certs, dest_dir=None):
                if isinstance(certs, six.string_types):
                        certs = [certs]
                if not dest_dir:
                        dest_dir = self.ta_dir
                self.assertTrue(dest_dir)
                self.assertTrue(self.raw_trust_anchor_dir)
                for c in certs:
                        name = "{0}_cert.pem".format(c)
                        portable.copyfile(
                            os.path.join(self.raw_trust_anchor_dir, name),
                            os.path.join(dest_dir, name))

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
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5} -i {i6} {pkg}".format(
                      key=os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      i1=os.path.join(self.chain_certs_dir,
                          "ch1_ta1_cert.pem"),
                      i2=os.path.join(self.chain_certs_dir,
                          "ch2_ta1_cert.pem"),
                      i3= os.path.join(self.chain_certs_dir,
                          "ch3_ta1_cert.pem"),
                      i4=os.path.join(self.chain_certs_dir,
                          "ch4_ta1_cert.pem"),
                      i5=os.path.join(self.chain_certs_dir,
                          "ch5_ta1_cert.pem"),
                      i6=os.path.join(self.chain_certs_dir,
                          "ch1_ta3_cert.pem"),
                      pkg=plist[3]
                    )
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
                    "empty", "test2"])
                self.make_misc_files(self.misc_files)

                # First repository will contain all packages.
                self.all_rurl = self.dcs[1].get_repo_url()

                # Second repository will contain only foo.
                self.foo_rurl = self.dcs[2].get_repo_url()

                # Third will be empty.
                self.empty_rurl = self.dcs[3].get_repo_url()

                # Fourth will be for license packages only.
                self.licensed_rurl = self.dcs[4].get_repo_url()

                # Setup base test paths.
                self.path_to_certs = os.path.join(self.ro_data_root,
                    "signing_certs", "produced")
                self.keys_dir = os.path.join(self.path_to_certs, "keys")
                self.cs_dir = os.path.join(self.path_to_certs,
                    "code_signing_certs")
                self.chain_certs_dir = os.path.join(self.path_to_certs,
                    "chain_certs")
                self.raw_trust_anchor_dir = os.path.join(self.path_to_certs,
                    "trust_anchors")
                self.crl_dir = os.path.join(self.path_to_certs, "crl")

                # Publish packages.
                plist = self.__publish_packages(self.all_rurl)

                # Copy foo to second repository.
                self.pkgrecv(self.all_rurl, "-d {0} foo".format(self.foo_rurl))

                # Now create a package archive containing all packages, and
                # then one for each.
                repo = self.dcs[1].get_repo()
                self.all_arc = self.__archive_packages("all_pkgs.p5p", repo,
                    plist)

                for alist in ([plist[0]], [plist[1], plist[2]], [plist[3]],
                    [plist[4], plist[5]]):
                        arc_path = self.__archive_packages(
                            "{0}.p5p".format(alist[0].pkg_name), repo, alist)
                        setattr(self, "{0}_arc".format(alist[0].pkg_name), arc_path)

                self.ta_dir = None

                # Copy an archive and set its permissions to 0000 for testing
                # unprivileged user access attempts.
                self.perm_arc = os.path.join(self.test_root, "noaccess.p5p")
                portable.copyfile(self.foo_arc, self.perm_arc)
                os.chmod(self.perm_arc, 0)

                # Create an empty archive.
                arc_path = os.path.join(self.test_root, "empty.p5p")
                arc = pkg.p5p.Archive(arc_path, mode="w")
                arc.close()
                self.empty_arc = arc_path

                # Store FMRIs for later use.
                self.foo10 = plist[0]
                self.incorp10 = plist[1]
                self.incorp20 = plist[2]
                self.signed10 = plist[3]
                self.quux01 = plist[4]
                self.quux10 = plist[5]

                # Handle license package specially.
                self.licensed10 = self.pkgsend_bulk(self.licensed_rurl,
                    self.licensed_pkg)[0]
                self.licensed20 = self.pkgsend_bulk(self.licensed_rurl,
                    self.licensed_pkg_2)[0]

        def test_00_list(self):
                """Verify that the list operation works as expected for
                temporary origins.
                """

                # Create an image and verify no packages are known.
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("list -a", exit=1)

                # Verify graceful failure for an empty source alone or in
                # combination with another temporary source.
                self.pkg("list -H -g {0}".format(self.empty_arc), exit=1)
                self.pkg("list -H -g {0} -g {1}".format(self.empty_arc,
                    self.foo_arc), exit=1)

                # Verify graceful failure if source doesn't exist.
                self.pkg("list -H -g {0}".format(self.foo_arc + ".nosuchpkg"),
                    exit=1)

                # Verify graceful failure if user doesn't have permission to
                # access temporary source.
                self.pkg("list -H -g {0}".format(self.perm_arc), su_wrap=True, exit=1)

                # Verify graceful list failure if -u is used with -g.
                self.pkg("list -H -u -g {0}".format(self.foo_arc), exit=2)

                # Verify list output for a single package temporary source.
                # -a is used here to verify that even though -a is implicit,
                # it is not an error to specify it.
                self.pkg("list -aH -g {0}".format(self.foo_arc))
                expected = "foo (test) 1.0 ---\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Note that -a is implicit when -g is used, so all of
                # the following tests purposefully omit it.

                # Verify list output for a multiple package temporary source
                # as an unprivileged user.
                self.pkg("list -fH -g {0}".format(self.all_arc), su_wrap=True)
                expected = \
                    ("foo (test) 1.0 ---\n"
                    "incorp (test) 2.0 ---\n"
                    "incorp (test) 1.0 ---\n"
                    "quux (test2) 1.0-0.2 ---\n"
                    "quux (test2) 0.1-0.1 ---\n"
                    "signed (test) 1.0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Verify list output for a multiple package temporary source.
                self.pkg("list -fH -g {0}".format(self.all_arc))
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Verify list output for multiple temporary sources using
                # different combinations of archives and repositories.
                self.pkg("list -fH -g {0} -g {1}".format(self.signed_arc,
                    self.foo_rurl))
                expected = \
                    ("foo (test) 1.0 ---\n"
                    "signed (test) 1.0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                self.pkg("list -fH -g {0} -g {1} -g {2} -g {3}".format(self.signed_arc,
                    self.incorp_arc, self.quux_arc, self.foo_arc))
                expected = \
                    ("foo (test) 1.0 ---\n"
                    "incorp (test) 2.0 ---\n"
                    "incorp (test) 1.0 ---\n"
                    "quux (test2) 1.0-0.2 ---\n"
                    "quux (test2) 0.1-0.1 ---\n"
                    "signed (test) 1.0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                self.pkg("list -fH -g {0} -g {1} -g {2} -g {3}".format(self.signed_arc,
                    self.quux_arc, self.incorp_arc, self.foo_rurl))
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                self.pkg("list -fH -g {0} -g {1}".format(self.all_arc,
                    self.all_rurl))
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Verify list -g without -f.
                self.pkg("list -H -g {0} -g {1} -g {2} -g {3}".format(self.signed_arc,
                    self.quux_arc, self.incorp_arc, self.foo_rurl))
                expected = \
                    ("foo (test) 1.0 ---\n"
                    "incorp (test) 2.0 ---\n"
                    "quux (test2) 1.0-0.2 ---\n"
                    "signed (test) 1.0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Verify package installed from archive shows in default list
                # output.
                self.pkg("install -g {0} incorp@1.0".format(self.incorp_arc))
                self.pkg("list -H")
                expected = "incorp (test) 1.0 i--\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Verify list -g with an incorp installed without -f.
                self.pkg("list -H -g {0} -g {1} -g {2} -g {3}".format(self.signed_arc,
                    self.quux_arc, self.incorp_arc, self.foo_rurl))
                expected = \
                    ("foo (test) 1.0 ---\n"
                    "incorp (test) 1.0 i--\n"
                    "quux (test2) 0.1-0.1 ---\n"
                    "signed (test) 1.0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Verify output again as unprivileged user.
                self.pkg("list -H -g {0} -g {1} -g {2} -g {3}".format(self.signed_arc,
                    self.quux_arc, self.incorp_arc, self.foo_rurl),
                    su_wrap=True)
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Verify list -g with an incorp installed with -f.
                self.pkg("list -fH -g {0} -g {1} -g {2} -g {3}".format(self.signed_arc,
                    self.quux_arc, self.incorp_arc, self.foo_rurl))
                expected = \
                    ("foo (test) 1.0 ---\n"
                    "incorp (test) 2.0 ---\n"
                    "incorp (test) 1.0 i--\n"
                    "quux (test2) 1.0-0.2 ---\n"
                    "quux (test2) 0.1-0.1 ---\n"
                    "signed (test) 1.0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Verify list -g with an incorp installed and -n.
                self.pkg("list -nH -g {0} -g {1} -g {2} -g {3}".format(self.signed_arc,
                    self.quux_arc, self.incorp_arc, self.foo_rurl))
                expected = \
                    ("foo (test) 1.0 ---\n"
                    "incorp (test) 2.0 ---\n"
                    "quux (test2) 1.0-0.2 ---\n"
                    "signed (test) 1.0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Uninstall all packages and verify there are no known packages.
                self.pkg("uninstall \*")
                self.pkg("list -af", exit=1)

                # Cleanup.
                self.image_destroy()

        def test_01_info(self):
                """Verify that the info operation works as expected for
                temporary origins.
                """
                # because we compare date strings we must run this in
                # a consistent locale, which we made 'C'

                os.environ['LC_ALL'] = 'C'

                # Create an image and verify no packages are known.
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("list -a", exit=1)

                # Verify graceful failure for an empty source alone or in
                # combination with another temporary source.
                self.pkg("info -g {0} \*".format(self.empty_arc), exit=1)
                self.pkg("info -g {0} -g {1} foo".format(self.empty_arc,
                    self.foo_arc), exit=1)

                # Verify graceful failure if source doesn't exist.
                self.pkg("info -g {0} foo".format(self.foo_arc + ".nosuchpkg"),
                    exit=1)

                # Verify graceful failure if user doesn't have permission to
                # access temporary source.
                self.pkg("info -g {0} foo".format(self.perm_arc), su_wrap=True, exit=1)

                # Verify graceful failure if -l is used with -g.
                self.pkg("info -l -g {0} foo".format(self.foo_arc), exit=2)

                # Verify output for a single package temporary source.
                # -r is used here to verify that even though -r is implicit,
                # it is not an error to specify it.
                def pd(pfmri):
                        return pfmri.version.get_timestamp().strftime("%c")

                self.pkg("info -r -g {0} foo".format(self.foo_arc), su_wrap=True)
                expected = """\
          Name: foo
       Summary: Example package foo.
         State: Not installed
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: {pkg_date}
          Size: 41.00 B
          FMRI: {pkg_fmri}
""".format(pkg_date=pd(self.foo10), pkg_fmri=self.foo10.get_fmri(
    include_build=False))
                self.assertEqualDiff(expected, self.output)

                # Again, as prvileged user.
                self.pkg("info -r -g {0} foo".format(self.foo_arc))
                self.assertEqualDiff(expected, self.output)

                # Note that -r is implicit when -g is used, so all of
                # the following tests purposefully omit it.

                # Verify info output for a multiple package temporary source
                # as an unprivileged user.
                self.pkg("info -g {0} \*".format(self.all_arc), su_wrap=True)
                expected = """\
          Name: foo
       Summary: Example package foo.
         State: Not installed
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: {foo10_pkg_date}
          Size: 41.00 B
          FMRI: {foo10_pkg_fmri}

          Name: incorp
       Summary: Incorporation
         State: Not installed
     Publisher: test
       Version: 2.0
        Branch: None
Packaging Date: {incorp20_pkg_date}
          Size: 0.00 B
          FMRI: {incorp20_pkg_fmri}

          Name: quux
       Summary: Example package quux.
         State: Not installed
     Publisher: test2
       Version: 1.0
        Branch: 0.2
Packaging Date: {quux10_pkg_date}
          Size: 8.00 B
          FMRI: {quux10_pkg_fmri}

          Name: signed
         State: Not installed
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: {signed10_pkg_date}
          Size: 10.05 kB
          FMRI: {signed10_pkg_fmri}
""".format(**{"foo10_pkg_date": pd(self.foo10), "foo10_pkg_fmri": \
        self.foo10.get_fmri(include_build=False),
    "incorp20_pkg_date": pd(self.incorp20), "incorp20_pkg_fmri": \
        self.incorp20.get_fmri(include_build=False),
    "quux10_pkg_date": pd(self.quux10), "quux10_pkg_fmri": \
        self.quux10.get_fmri(include_build=False),
    "signed10_pkg_date": pd(self.signed10), "signed10_pkg_fmri": \
        self.signed10.get_fmri(include_build=False),
    })
                self.assertEqualDiff(expected, self.output)

                # Verify info output for a multiple package temporary source.
                self.pkg("info -g {0} foo@1.0 incorp@2.0 signed@1.0 "
                    "quux@1.0".format(self.all_arc))
                self.assertEqualDiff(expected, self.output)

                # Verify info result for multiple temporary sources using
                # different combinations of archives and repositories.
                self.pkg("info -g {0} -g {1} signed@1.0 foo@1.0 signed@1.0".format(
                    self.signed_arc, self.foo_rurl))

                self.pkg("info -g {0} -g {1} -g {2} -g {3} foo@1.0 incorp@1.0 "
                    "signed@1.0 quux@0.1".format(
                    self.signed_arc, self.incorp_arc, self.quux_arc,
                    self.foo_arc))

                self.pkg("info -g {0} -g {1} -g {2} -g {3} foo@1.0 incorp@1.0 "
                    "signed@1.0 quux@0.1".format(
                    self.signed_arc, self.incorp_arc, self.quux_arc,
                    self.foo_rurl))

                self.pkg("info -g {0} -g {1} foo@1.0 incorp@2.0 signed@1.0 "
                    "quux@1.0".format(self.all_arc, self.all_rurl))

                # Verify package installed from archive shows in default info
                # output.
                self.pkg("install -g {0} foo@1.0".format(self.foo_arc))
                self.pkg("info")

                os.environ["LC_ALL"] = "C"
                path = os.path.join(self.img_path(),
                    "var/pkg/state/installed/catalog.base.C")
                entry = json.load(open(path))["test"]["foo"][0]["metadata"]
                pkg_install = catalog.basic_ts_to_datetime(
                    entry["last-install"]).strftime("%c")

                expected = """\
             Name: foo
          Summary: Example package foo.
            State: Installed
        Publisher: test
          Version: 1.0
           Branch: None
   Packaging Date: {pkg_date}
Last Install Time: {pkg_install}
             Size: 41.00 B
             FMRI: {pkg_fmri}
""".format(pkg_date=pd(self.foo10), pkg_fmri=self.foo10.get_fmri(
    include_build=False), pkg_install=pkg_install)
                self.assertEqualDiff(expected, self.output)

                # Verify that when showing package info from archive that
                # package shows as installed if it matches the installed one.
                self.pkg("info -g {0} foo".format(self.foo_arc))
                self.assertEqualDiff(expected, self.output)

                # Uninstall all packages and verify there are no known packages.
                self.pkg("uninstall \*")
                self.pkg("info -r \*", exit=1)

                # Verify that --license works as expected with -g.
                self.pkg("info -g {0} --license licensed@1.0".format(
                    self.licensed_rurl))
                self.assertEqualDiff("tmp/LICENSE\n", self.output)
                self.pkg("info -g {0} --license licensed".format(
                    self.licensed_rurl))
                self.assertEqualDiff("tmp/LICENSE2\n", self.output)

                # Cleanup.
                self.image_destroy()
                # Change locale back to 'UTF-8' to not affect other test cases.
                if six.PY3:
                        os.environ["LC_ALL"] = "en_US.UTF-8"

        def test_02_contents(self):
                """Verify that the contents operation works as expected for
                temporary origins.
                """

                # Create an image and verify no packages are known.
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("list -a", exit=1)

                # Verify graceful failure for an empty source alone or in
                # combination with another temporary source.
                self.pkg("contents -g {0} \*".format(self.empty_arc), exit=1)
                self.pkg("contents -g {0} -g {1} foo".format(self.empty_arc,
                    self.foo_arc), exit=1)

                # Verify graceful failure if source doesn't exist.
                self.pkg("contents -g {0} foo".format(self.foo_arc + ".nosuchpkg"),
                    exit=1)

                # Verify graceful failure if user doesn't have permission to
                # access temporary source.
                self.pkg("contents -g {0} foo".format(self.perm_arc), su_wrap=True,
                    exit=1)

                # Verify output for a single package temporary source.
                # -r is used here to verify that even though -r is implicit,
                # it is not an error to specify it.
                def pd(pfmri):
                        return pfmri.version.get_timestamp().strftime("%c")

                self.pkg("contents -mr -g {0} foo".format(self.foo_arc), su_wrap=True)
                expected = """\
set name=pkg.fmri value={0}
set name=pkg.summary value="Example package foo."
set name=variant.debug.foo value=true value=false
dir group=bin mode=0755 owner=root path=lib
dir group=bin mode=0755 owner=root path=usr
dir group=bin mode=0755 owner=root path=usr/bin
dir group=bin mode=0755 owner=root path=usr/local
dir group=bin mode=0755 owner=root path=usr/local/bin
dir group=bin mode=0755 owner=root path=usr/share
dir group=bin mode=0755 owner=root path=usr/share/doc
dir group=bin mode=0755 owner=root path=usr/share/doc/foo
dir group=bin mode=0755 owner=root path=usr/share/man
dir group=bin mode=0755 owner=root path=usr/share/man/man1
file 0acf1107d31f3bab406f8611b21b8fade78ac874 chash=20db00fbd7c9fb551e54c5b424bf24d48cf81b7a facet.doc.man=true group=bin mode=0444 owner=root path=usr/share/man/man1/foo.1 pkg.csize=29 pkg.size=9
file b265f2ec87c4a55eb2b6b4c926e7c65f7247a27e chash=5ae38559680146c49d647163ac2f60cdf43e20d8 group=bin mode=0755 owner=root path=usr/bin/foo pkg.csize=27 pkg.size=7
file 4ea0699d20b99238a877051e50406687fd4fe163 chash=7a23120f5a4f1eae2829a707020d0cdbab10e9a2 group=bin mode=0755 owner=root path=lib/libfoo.so.1 pkg.csize=41 pkg.size=21 variant.debug.foo=true
file a285ada5f3cae14ea00e97a8d99bd3e357cb0dca chash=97a09a2356d068d8dbe418de90012908c095d3e2 group=bin mode=0755 owner=root path=lib/libfoo.so.1 pkg.csize=35 pkg.size=15 variant.debug.foo=false
file dc84bd4b606fe43fc892eb245d9602b67f8cba38 chash=e1106f9505253dfe46aa48c353740f9e1896a844 group=bin mode=0444 owner=root path=usr/share/doc/foo/README pkg.csize=30 pkg.size=10
hardlink path=usr/local/bin/hard-foo target=/usr/bin/foo
link path=usr/local/bin/soft-foo target=usr/bin/foo
""".format(self.foo10)

                # Again, as prvileged user.
                self.pkg("contents -mr -g {0} foo".format(self.foo_arc))
                self.assertEqualDiff(sorted(expected.splitlines()),
                    sorted(self.output.splitlines()))

                # Note that -r is implicit when -g is used, so all of
                # the following tests purposefully omit it.

                # Verify contents result for multiple temporary sources using
                # different combinations of archives and repositories.
                self.pkg("contents -g {0} -g {1} signed@1.0 foo@1.0 "
                    "signed@1.0".format(self.signed_arc, self.foo_rurl))

                self.pkg("contents -g {0} -g {1} -g {2} -g {3} foo@1.0 incorp@1.0 "
                    "signed@1.0 quux@0.1".format(self.signed_arc, self.incorp_arc,
                    self.quux_arc, self.foo_arc))

                self.pkg("contents -g {0} -g {1} -g {2} -g {3} foo@1.0 incorp@1.0 "
                    "signed@1.0 quux@0.1".format(self.signed_arc, self.incorp_arc,
                    self.quux_arc, self.foo_rurl))

                self.pkg("contents -g {0} -g {1} foo@1.0 incorp@2.0 signed@1.0 "
                    "quux@1.0".format(self.all_arc, self.all_rurl))

                # Verify package installed from archive can be used with
                # contents.
                self.pkg("install -g {0} foo@1.0".format(self.foo_arc))
                self.pkg("contents foo")

                # Uninstall all packages and verify there are no known packages.
                self.pkg("uninstall \*")
                self.pkg("contents -r \*", exit=1)

                # Cleanup.
                self.image_destroy()

        def test_03_install_update(self):
                """Verify that install and update work as expected for temporary
                origins.
                """

                #
                # Create an image with no configured package sources, and
                # verify that a package can be installed from a temporary
                # source.
                #
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("set-property signature-policy ignore")
                self.pkg("list -a", exit=1)
                self.pkg("install -g {0} foo".format(self.foo_arc))

                #
                # Create an image with a network-based source, then make that
                # source unreachable and verify that a package can be installed
                # from a temporary source.
                #
                self.dcs[4].start()
                self.image_create(self.dcs[4].get_depot_url(), prefix=None)
                self.dcs[4].stop()
                self.pkg("set-property signature-policy ignore")
                self.pkg("list -a")
                # --no-refresh is required for now because -g combines temporary
                # sources with configured soures and pkg(5) currently treats
                # refresh failure as fatal.  See bug 18323.
                self.pkg("install --no-refresh -g {0} foo".format(self.foo_arc))

                #
                # Create an image and verify no packages are known.
                #
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("set-property signature-policy ignore")
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                self.pkg("list -a", exit=1)

                # Verify graceful failure if source doesn't exist.
                self.pkg("install -g {0} foo".format(self.foo_arc + ".nosuchpkg"),
                    exit=1)

                # Verify graceful failure if user doesn't have permission to
                # access temporary source.
                self.pkg("install -g {0} foo".format(self.perm_arc), su_wrap=True,
                    exit=1)

                # Verify attempting to install a package with a missing
                # dependency fails gracefully.
                self.pkg("install -g {0} signed".format(self.signed_arc), exit=1)

                # Verify a package from a publisher not already configured can
                # be installed using temporary origins.  Installing a package
                # in this scenario will result in the publisher being added
                # but without any origin information.
                self.pkg("install -g {0} foo".format(self.foo_arc))
                self.pkg("list foo")

                # Verify that publisher exists now (without origin information)
                # and is enabled and sticky (-n omits disabled publishers).
                self.pkg("publisher -nH")
                expected = """\
empty origin online F {0}/
test 
""".format(self.empty_rurl)
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Verify that signed package can now be installed since
                # dependency was satisfied.
                self.pkg("install -g {0} signed".format(self.signed_arc))
                self.pkg("list foo signed")

                # Verify that removing all packages leaves no packages known
                # even though publisher remains configured.
                self.pkg("uninstall \*")
                self.pkg("list -af", exit=1)

                # Verify publisher can be removed.
                self.pkg("unset-publisher test")

                #
                # Create an image using the foo archive.
                #
                self.image_create(misc.parse_uri(self.foo_arc), prefix=None)
                self.__seed_ta_dir("ta1")

                # Verify that signed package can be installed and the archive
                # configured for the publisher allows dependencies to be
                # satisfied.
                self.pkg("set-property signature-policy verify")
                self.pkg("install -g {0} signed".format(self.signed_arc))
                self.pkg("list foo signed")

                # Verify that removing all packages leaves only foo known.
                self.pkg("uninstall \*")
                self.pkg("list -aH")
                expected = "foo 1.0 ---\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                #
                # Create an image and verify no packages are known.
                #
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("list -a", exit=1)

                # Install an older version of a known package.
                self.pkg("install -g {0} quux@0.1".format(self.all_arc))
                self.pkg("list incorp@1.0 quux@0.1")

                # Verify graceful failure if source doesn't exist.
                self.pkg("update -g {0} foo".format(self.foo_arc + ".nosuchpkg"),
                    exit=1)

                # Verify graceful failure if user doesn't have permission to
                # access temporary source.
                self.pkg("update -g {0} foo".format(self.perm_arc), su_wrap=True,
                    exit=1)

                # Verify that packages can be updated using temporary origins.
                self.pkg("update -g {0} -g {1}".format(self.incorp_arc,
                    self.quux_arc))
                self.pkg("list incorp@2.0 quux@1.0")

                # Verify that both test and test2 are configured without
                # origins.
                self.pkg("publisher -H")
                expected = """\
empty origin online F {0}/
test 
test2 
""".format(self.empty_rurl)
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_04_change_varcets(self):
                """Verify that change-facet and change-variant work as expected
                for temporary origins.
                """

                #
                # Create an image and verify no packages are known.
                #
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("list -a", exit=1)

                # Install a package from an archive.
                self.pkg("install -g {0} foo".format(self.foo_arc))

                #
                # Verify change-facet can use temporary origins.
                #
                fpath = os.path.join(self.img_path(),
                    "usr/share/man/man1/foo.1")
                assert os.path.exists(fpath)

                # Now set facet.doc.man to false and verify faceted item is
                # gone.
                self.pkg("change-facet facet.doc.man=false")
                assert not os.path.exists(fpath)

                # Now attempt to set the facet to true again; this should
                # fail.
                self.pkg("change-facet facet.doc.man=true", exit=1)

                # Verify graceful failure if source doesn't exist.
                self.pkg("change-facet -g {0} facet.doc.man=true".format(
                    self.foo_arc + ".nosuchpkg"), exit=1)

                # Verify graceful failure if user doesn't have permission to
                # access temporary source.
                self.pkg("change-facet -g {0} facet.doc.man=true".format(
                    self.perm_arc), su_wrap=True, exit=1)

                # Verify that if the original archive is provided, the operation
                # will succeed.
                self.pkg("change-facet -g {0} facet.doc.man=True".format(self.foo_arc))
                assert os.path.exists(fpath)

                #
                # Verify change-variant can use temporary origins.
                #
                vpath = os.path.join(self.img_path(),
                    "lib/libfoo.so.1")
                assert os.path.exists(vpath)
                self.assertEqual(os.stat(vpath).st_size, 15)

                # Now attempt to change the debug variant; this should fail.
                self.pkg("change-variant -vv variant.debug.foo=true", exit=1)

                # Verify graceful failure if source doesn't exist.
                self.pkg("change-variant -vvg {0} variant.debug.foo=true".format(
                    self.foo_arc + ".nosuchpkg"), exit=1)

                # Verify graceful failure if user doesn't have permission to
                # access temporary source.
                self.pkg("change-variant -vvg {0} variant.debug.foo=true".format(
                    self.perm_arc), su_wrap=True, exit=1)

                # Verify that if the original archive is provided, the operation
                # will succeed.
                self.pkg("change-variant -vvg {0} variant.debug.foo=true".format(
                    self.foo_arc))
                assert os.path.exists(vpath)
                self.assertEqual(os.stat(vpath).st_size, 21)

        def test_05_staged_execution(self):
                """Verify that staged execution works with temporary
                origins."""

                # Create an image and verify no packages are known.
                self.image_create(self.empty_rurl, prefix=None)
                self.pkg("list -a", exit=1)

                # Install an older version of a known package.
                self.pkg("install -g {0} quux@0.1".format(self.all_arc))
                self.pkg("list incorp@1.0 quux@0.1")

                # Verify that packages can be updated using temporary origins.
                self.pkg("update --stage=plan -g {0} -g {1}".format(
                    self.incorp_arc, self.quux_arc))
                self.pkg("update --stage=prepare -g {0} -g {1}".format(
                    self.incorp_arc, self.quux_arc))
                self.pkg("update --stage=execute -g {0} -g {1}".format(
                    self.incorp_arc, self.quux_arc))
                self.pkg("list incorp@2.0 quux@1.0")

        def test_06_appropriate_license_files(self):
                """Verify that the correct license file is displayed."""

                self.image_create()

                self.pkg("info -g {0} --license licensed".format(self.licensed_rurl))
                self.assertEqual("tmp/LICENSE2\n", self.output)
                self.pkg("info -g {0} --license licensed@1.0".format(
                    self.licensed_rurl))
                self.assertEqual("tmp/LICENSE\n", self.output)

                self.pkg("install -g {0} --licenses licensed@1.0".format(
                    self.licensed_rurl))
                self.assertTrue("tmp/LICENSE" in self.output, "Expected "
                    "tmp/LICENSE to be in the output of the install. Output "
                    "was:\n{0}".format(self.output))
                self.pkg("info -g {0} --license licensed".format(self.licensed_rurl))
                self.assertEqual("tmp/LICENSE2\n", self.output)
                self.pkg("info -g {0} --license licensed@2.0".format(
                    self.licensed_rurl))
                self.assertEqual("tmp/LICENSE2\n", self.output)

                self.pkg("update -g {0} --licenses licensed@2.0".format(
                    self.licensed_rurl))
                self.assertTrue("tmp/LICENSE2" in self.output, "Expected "
                    "tmp/LICENSE2 to be in the output of the install. Output "
                    "was:\n{0}".format(self.output))
                self.pkg("info -g {0} --license licensed".format(self.licensed_rurl))
                self.assertEqual("tmp/LICENSE2\n", self.output)
                self.pkg("info -g {0} --license licensed@1.0".format(
                    self.licensed_rurl))
                self.assertEqual("tmp/LICENSE\n", self.output)


if __name__ == "__main__":
        unittest.main()
