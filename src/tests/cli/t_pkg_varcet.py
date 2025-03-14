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

# Copyright (c) 2013, 2025, Oracle and/or its affiliates.

from . import testutils
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

import pkg.facet as facet
import pkg.variant as variant

from pkg.client.pkgdefs import EXIT_OOPS


class TestPkgVarcet(pkg5unittest.SingleDepotTestCase):

    # Don't discard repository or setUp() every test.
    persistent_setup = True

    pkg_foo = """
            open foo@1.0
            add file tmp/non-debug path=usr/bin/foo mode=0755 owner=root group=root
            add file tmp/man path=usr/man/man1/foo.1 mode=0444 owner=root group=root
            close
            open foo@2.0
            add set name=variant.icecream value=neapolitan value=strawberry
            add file tmp/debug path=usr/bin/foo mode=0755 owner=root group=root variant.debug.foo=true
            add file tmp/non-debug path=usr/bin/foo mode=0755 owner=root group=root variant.debug.foo=false
            add file tmp/neapolitan path=etc/icecream mode=0644 owner=root group=root variant.icecream=neapolitan
            add file tmp/strawberry path=etc/icecream mode=0644 owner=root group=root variant.icecream=strawberry
            add file tmp/man path=usr/man/man1/foo.1 mode=0444 owner=root group=root facet.doc.man=true
            add file tmp/doc path=usr/share/foo/README mode=0444 owner=root group=root facet.doc.txt=true
            add file tmp/pdf path=usr/share/foo/README.pdf mode=0444 owner=root group=root facet.doc.pdf=true
            open foo@3.0
            add set name=pkg.facet value=doc.man value=doc.txt value=doc.pdf
            add set name=pkg.variant value=icecream value=debug.foo
            add set name=variant.icecream value=neapolitan value=strawberry
            add file tmp/debug path=usr/bin/foo mode=0755 owner=root group=root variant.debug.foo=true
            add file tmp/non-debug path=usr/bin/foo mode=0755 owner=root group=root variant.debug.foo=false
            add file tmp/neapolitan path=etc/icecream mode=0644 owner=root group=root variant.icecream=neapolitan
            add file tmp/strawberry path=etc/icecream mode=0644 owner=root group=root variant.icecream=strawberry
            add file tmp/man path=usr/man/man1/foo.1 mode=0444 owner=root group=root facet.doc.man=true
            add file tmp/doc path=usr/share/foo/README mode=0444 owner=root group=root facet.doc.txt=true
            add file tmp/pdf path=usr/share/foo/README.pdf mode=0444 owner=root group=root facet.doc.pdf=true
            close """

    pkg_unknown = """
            open unknown@1.0
            add set name=variant.unknown value=bar value=foo
            add file tmp/non-debug path=usr/bin/bar mode=0755 owner=root group=root variant.unknown=bar
            add file tmp/non-debug path=usr/bin/foo mode=0755 owner=root group=root variant.unknown=foo
            close """

    pkg_need_foo = """
            open need_foo@1.0
            add depend type=require fmri=foo
            """

    pkg_user_facet = """
            open user_facet@1.0,5.11-0
            add dir path=etc mode=0755 owner=root group=sys
            add dir path=etc/ftpd mode=0755 owner=root group=sys
            add user username=root password=9EIfTNBp9elws uid=0 group=root home-dir=/root login-shell=/usr/bin/bash ftpuser=false group-list=other group-list=bin group-list=sys group-list=adm
            add group gid=0 groupname=root
            add group gid=3 groupname=sys
            add file empty path=etc/group mode=0644 owner=root group=sys preserve=true
            add file empty path=etc/passwd mode=0644 owner=root group=sys preserve=true
            add file empty path=etc/shadow mode=0400 owner=root group=sys preserve=true
            add file empty path=etc/ftpd/ftpusers mode=0644 owner=root group=sys preserve=true
            add group groupname=group12 gid=111112 facet.app.prod=true
            add user username=user12 group=group12 home-dir=/export/home/user12 login-shell=/bin/sh password=*LK* uid=11112 facet.app.prod=true
            close
            """

    pkg_group_var = """
            open group_var@1.0,5.11-0
            add dir path=etc mode=0755 owner=root group=sys
            add dir path=etc/ftpd mode=0755 owner=root group=sys
            add group gid=0 groupname=root
            add group gid=3 groupname=sys
            add file empty path=etc/group mode=0644 owner=root group=sys preserve=true
            add group gid=5555511 groupname=appadmin variant.rel=prod
            add group gid=5555522 groupname=appadmin variant.rel=dev
            add group gid=5555533 groupname=appadmin variant.rel=test
            close
            """

    misc_files = ["tmp/debug", "tmp/non-debug", "tmp/neapolitan",
        "tmp/strawberry", "tmp/doc", "tmp/man", "tmp/pdf"]

    empty_files = { "empty": ""}

    def setUp(self):
        pkg5unittest.SingleDepotTestCase.setUp(self)
        self.make_misc_files(self.misc_files)
        self.make_misc_files(self.empty_files)
        self.pkgsend_bulk(self.rurl, [
            getattr(self, p)
            for p in dir(self)
            if p.startswith("pkg_") and isinstance(getattr(self, p), str)
        ])

    def __assert_varcet_matches_default(self, cmd, expected, errout=None,
        exit=0, opts=misc.EmptyI, names=misc.EmptyI, su_wrap=False):
        if errout is None and exit != 0:
            # Assume there should be error output for non-zero exit
            # if not explicitly indicated.
            errout = True

        self.pkg("{0} {1} -H {2}".format(cmd, " ".join(opts), " ".join(names)),
            exit=exit, su_wrap=su_wrap)
        self.assertEqualDiff(expected, self.reduceSpaces(self.output))
        if errout:
            self.assertTrue(self.errout != "")
        else:
            self.assertEqualDiff("", self.errout)

    def __assert_varcet_matches_tsv(self, cmd, prefix, expected, errout=None,
        exit=0, opts=misc.EmptyI, names=misc.EmptyI, su_wrap=False):
        self.pkg("{0} {1} -H -F tsv {2}".format(cmd, " ".join(opts),
            " ".join(names)), exit=exit, su_wrap=su_wrap)
        expected = "".join(
                (prefix + l)
                for l in expected.splitlines(True)
        )
        self.assertEqualDiff(expected, self.output)
        if errout:
            self.assertTrue(self.errout != "")
        else:
            self.assertEqualDiff("", self.errout)

    def __assert_varcet_fails(self, cmd, operands, errout=True, exit=1,
        su_wrap=False):
        self.pkg("{0} {1}".format(cmd, operands), exit=exit, su_wrap=su_wrap)
        if errout:
            self.assertTrue(self.errout != "")
        else:
            self.assertEqualDiff("", self.errout)

    def __assert_facet_matches_default(self, *args, **kwargs):
        self.__assert_varcet_matches_default("facet", *args,
            **kwargs)

    def __assert_facet_matches_tsv(self, *args, **kwargs):
        self.__assert_varcet_matches_tsv("facet", "facet.", *args,
            **kwargs)

    def __assert_facet_matches(self, exp_def, **kwargs):
        exp_tsv = exp_def.replace(" ", "\t")
        self.__assert_varcet_matches_default("facet", exp_def,
            **kwargs)
        self.__assert_varcet_matches_tsv("facet", "facet.", exp_tsv,
            **kwargs)

    def __assert_facet_fails(self, *args, **kwargs):
        self.__assert_varcet_fails("facet", *args, **kwargs)

    def __assert_variant_matches_default(self, *args, **kwargs):
        self.__assert_varcet_matches_default("variant", *args,
            **kwargs)

    def __assert_variant_matches_tsv(self, *args, **kwargs):
        self.__assert_varcet_matches_tsv("variant", "", *args,
            **kwargs)

    def __assert_variant_matches(self, exp_def, **kwargs):
        exp_tsv = exp_def.replace(" ", "\t")
        self.__assert_varcet_matches_default("variant", exp_def,
            **kwargs)
        self.__assert_varcet_matches_tsv("variant", "variant.", exp_tsv,
            **kwargs)

    def __assert_variant_fails(self, *args, **kwargs):
        self.__assert_varcet_fails("variant", *args, **kwargs)

    def __test_foo_facet_upgrade(self, pkg):
        #
        # Next, verify output after upgrading package to faceted
        # version.
        #
        self.pkg("update {0}".format(pkg))

        # Verify output for no options and no patterns.
        exp_def = """\
doc.* False local
doc.html False local
doc.man False local
doc.txt True local
"""
        self.__assert_facet_matches(exp_def)

        # Matched because facet is implicitly set.
        exp_def = """\
doc.pdf False local
"""
        self.__assert_facet_matches(exp_def, names=["doc.pdf"])

        # Unmatched because facet is not explicitly set.
        self.__assert_facet_fails("'*pdf'")

        # Matched case for explicitly set.
        exp_def = """\
doc.* False local
doc.txt True local
"""
        names = ("'facet.doc.[*]'", "doc.txt")
        self.__assert_facet_matches(exp_def, names=names)

        # Verify -a output.
        exp_def = """\
doc.* False local
doc.html False local
doc.man False local
doc.pdf False local
doc.txt True local
"""
        opts = ("-a",)
        self.__assert_facet_matches(exp_def, opts=opts)

        # Matched case for explicitly set and those in packages.
        exp_def = """\
doc.* False local
doc.pdf False local
doc.txt True local
"""
        names = ("'facet.doc.[*]'", "*pdf", "facet.doc.txt")
        opts = ("-a",)
        self.__assert_facet_matches(exp_def, opts=opts, names=names)

        # Verify -i output.
        exp_def = """\
doc.man False local
doc.pdf False local
doc.txt True local
"""
        opts = ("-i",)
        self.__assert_facet_matches(exp_def, opts=opts)

        # Unmatched because facet is not used in package.
        self.__assert_facet_fails("-i doc.html")
        self.__assert_facet_fails("-i '*html'")

        # Matched case in packages.
        exp_def = """\
doc.man False local
doc.pdf False local
"""
        names = ("'facet.*[!t]'",)
        opts = ("-i",)
        self.__assert_facet_matches(exp_def, opts=opts, names=names)

        exp_def = """\
doc.pdf False local
"""
        names = ("'*pdf'",)
        opts = ("-i",)
        self.__assert_facet_matches(exp_def, opts=opts, names=names)

        # Now uninstall package and verify output (to ensure any
        # potentially cached information has been updated).
        self.pkg("uninstall foo")

        exp_def = """\
doc.* False local
doc.html False local
doc.man False local
doc.txt True local
"""

        # Output should be the same for both -a and default cases with
        # no packages installed.
        for opts in ((), ("-a",)):
            self.__assert_facet_matches(exp_def, opts=opts)

        # No output expected for -i.
        opts = ("-i",)
        self.__assert_facet_matches("", opts=opts)

    def test_00_facet(self):
        """Verify facet subcommand works as expected."""

        # create an image
        self.image_create(self.rurl)

        # Verify invalid options handled gracefully.
        self.__assert_facet_fails("-z", exit=2)
        self.__assert_facet_fails("-fi", exit=2)

        #
        # First, verify output before setting any facets or installing
        # any packages.
        #

        # Output should be the same for all cases with no facets set and
        # no packages installed.
        for opts in ((), ("-i",), ("-a",)):
            # No operands specified case.
            self.__assert_facet_matches("", opts=opts)

            # Unprivileged user case.
            self.__assert_facet_matches("", opts=opts, su_wrap=True)

        # Fails because not used by any installed package.
        self.__assert_facet_fails("-i bogus")

        # Succeeds because implicitly set in image.
        self.__assert_facet_matches_tsv("bogus\tTrue\tsystem\n",
            opts=("-a",), names=("bogus",))

        #
        # Next, verify output after setting facets.
        #

        # Set some facets.
        self.pkg("change-facet 'doc.*=False' doc.man=False "
            "facet.doc.html=False facet.doc.txt=True")

        exp_def = """\
doc.* False local
doc.html False local
doc.man False local
doc.txt True local
"""

        # Output should be the same for both -a and default cases with
        # no packages installed.
        for opts in ((), ("-a",)):
            self.__assert_facet_matches(exp_def, opts=opts)

        #
        # Next, verify output after installing unfaceted package.
        #
        self.pkg("install foo@1.0")

        # Verify output for no options and no patterns.
        exp_def = """\
doc.* False local
doc.html False local
doc.man False local
doc.txt True local
"""
        self.__assert_facet_matches(exp_def)

        # Verify -a output.
        opts = ("-a",)
        self.__assert_facet_matches(exp_def, opts=opts)

        # Verify -i output.
        opts = ("-i",)
        self.__assert_facet_matches("", opts=opts)

        # Test upgraded package that does not declare all
        # facets/variants.
        self.__test_foo_facet_upgrade("foo@2.0")

        # Reinstall and then retest with upgraded package that declares
        # all facets/variants.
        self.pkg("install foo@1.0")
        self.__test_foo_facet_upgrade("foo@3.0")

    def test_user_facet(self):
        """Verify that the user is present when the facet is true and
        that it is removed when the facet is set to false"""

        # create an image
        self.image_create(self.rurl)

        # Install package that deliver user/group with facet
        self.pkg("install user_facet@1.0")

        # Ensure the user is present because facets are true by default.
        self.assertTrue("user12" == \
            portable.get_name_by_uid(11112, self.get_img_path(), True))

        # Disable facets delivering user.
        self.pkg("change-facet facet.app.prod=False")

        # Verify that the user is removed due to the modified facet
        try:
            portable.get_name_by_uid(11112,
                self.get_img_path(), True)
        except KeyError:
            # Nothing to do, the user does not exist now
            pass

        exp_def = """\
app.prod False local
"""
        # Ensure that the o/p for facet is as expected
        opts = ("-i",)
        self.__assert_facet_matches(exp_def, opts=opts)

    def test_group_var(self):
        """Verify that the group IDs for a group changes correctly,
        as controlled by the variant tag associated with them."""

        # create an image which includes the variant to tested
        variants = { "variant.rel": "prod" }
        self.image_create(self.rurl, variants=variants)

        # Gather up all the variants now in the image
        api_obj = self.get_img_api_obj()
        variants = dict(v[:-1] for v in api_obj.gen_variants(
            api_obj.VARIANT_IMAGE))

        # Install package that deliver group with facet
        self.pkg("install group_var@1.0")

        # Ensure group is present and mapped to right GID
        self.assertTrue("appadmin" == \
            portable.get_name_by_gid(5555511, self.get_img_path(), True))

        # Change the variant linked with the user.
        self.pkg("change-variant variant.rel=dev")

        # Verify that the GID has changed due to the modified variant
        self.assertTrue("appadmin" == \
            portable.get_name_by_gid(5555522, self.get_img_path(), True))

        # Verify we have the variant set correctly
        exp_def = """\
arch {0[variant.arch]}
opensolaris.zone global
rel dev
""".format(variants)
        self.__assert_variant_matches(exp_def)

        # Change the variant again
        self.pkg("change-variant variant.rel=test")

        # Verify that the GID has changed due to the modified variant
        self.assertTrue("appadmin" == \
            portable.get_name_by_gid(5555533, self.get_img_path(), True))

        # Verify we have the variant set correctly
        exp_def = """\
arch {0[variant.arch]}
opensolaris.zone global
rel test
""".format(variants)
        self.__assert_variant_matches(exp_def)

    def __test_foo_variant_upgrade(self, pkg, variants):
        #
        # Next, verify output after upgrading package to varianted
        # version.
        #
        self.pkg("update {0}".format(pkg))

        # Verify output for no options and no patterns.
        exp_def = """\
arch {0[variant.arch]}
icecream strawberry
opensolaris.zone global
""".format(variants)
        self.__assert_variant_matches(exp_def)

        # Matched because variant is implicitly false.
        exp_def = """\
debug.foo false
""".format(variants)
        self.__assert_variant_matches(exp_def, names=["debug.foo"])

        # Matched because unknown variant is implicitly false.
        exp_def = """\
foobar false
"""
        self.__assert_variant_matches(exp_def, names=["foobar"])

        # Unmatched because variant is not explicitly set (wildcard
        # matching looks for explicit variants).
        self.__assert_variant_fails("'*foo'")

        # Matched case for explicitly set.
        exp_def = """\
arch {0[variant.arch]}
opensolaris.zone global
""".format(variants)
        names = ("arch", "'variant.*zone'")
        self.__assert_variant_matches(exp_def, names=names)

        # Verify -a output.
        exp_def = """\
arch {0[variant.arch]}
debug.foo false
icecream strawberry
opensolaris.zone global
""".format(variants)
        opts = ("-a",)
        self.__assert_variant_matches(exp_def, opts=opts)

        # Matched case for explicitly set and those in packages.
        exp_def = """\
arch {0[variant.arch]}
debug.foo false
opensolaris.zone global
""".format(variants)
        names = ("'variant.debug.*'", "arch", "'*zone'")
        opts = ("-a",)
        self.__assert_variant_matches(exp_def, opts=opts, names=names)

        # Verify -i output.
        exp_def = """\
debug.foo false
icecream strawberry
""".format(variants)
        opts = ("-i",)
        self.__assert_variant_matches(exp_def, opts=opts)

        # Unmatched because variant is not used in package.
        self.__assert_variant_fails("-i opensolaris.zone")
        self.__assert_variant_fails("-i '*arch'")

        # Verify -v and -av output.
        exp_def = """\
debug.foo false
debug.foo true
icecream neapolitan
icecream strawberry
"""
        for opts in (("-v",), ("-av",)):
            self.__assert_variant_matches(exp_def, opts=opts)

        exp_def = """\
icecream neapolitan
icecream strawberry
""".format(variants)
        names = ("'ice*'",)
        opts = ("-av",)
        self.__assert_variant_matches(exp_def, opts=opts, names=names)

        # Matched case in packages.
        exp_def = """\
icecream strawberry
""".format(variants)
        names = ("'variant.*[!o]'",)
        opts = ("-i",)
        self.__assert_variant_matches(exp_def, opts=opts, names=names)

        exp_def = """\
debug.foo false
""".format(variants)
        names = ("*foo",)
        opts = ("-i",)
        self.__assert_variant_matches(exp_def, opts=opts, names=names)

        # Now uninstall package and verify output (to ensure any
        # potentially cached information has been updated).
        self.pkg("uninstall foo")

        exp_def = """\
arch {0[variant.arch]}
icecream strawberry
opensolaris.zone global
""".format(variants)

        # Output should be the same for both -a and default cases with
        # no packages installed.
        for opts in ((), ("-a",)):
            self.__assert_variant_matches(exp_def, opts=opts)

        # No output expected for -v, -av, -i, or -iv.
        for opts in (("-v",), ("-av",), ("-i",), ("-iv",)):
            self.__assert_variant_matches("", opts=opts)

    def test_01_variant(self):
        """Verify variant subcommand works as expected."""

        # create an image
        self.image_create(self.rurl)

        # Get variant data.
        api_obj = self.get_img_api_obj()
        variants = dict(v[:-1] for v in api_obj.gen_variants(
            api_obj.VARIANT_IMAGE))

        # Verify invalid options handled gracefully.
        self.__assert_variant_fails("-z", exit=2)
        self.__assert_variant_fails("-ai", exit=2)
        self.__assert_variant_fails("-aiv", exit=2)

        # Verify valid output format values do not cause failure
        self.__assert_variant_fails("-F default", exit=0, errout=False)
        self.__assert_variant_fails("--output-format default", exit=0,
            errout=False)

        self.__assert_variant_fails("-F  json", exit=0, errout=False)
        self.__assert_variant_fails("--output-format  json", exit=0,
            errout=False)

        # Verify invalid output format values handled gracefully
        self.__assert_variant_fails("-F dummy", exit=2)
        self.__assert_variant_fails("--output-format dummy", exit=2)

        #
        # First, verify output before setting any variants or installing
        # any packages.
        #

        # Output should be the same for -a and default cases with no
        # variants set and no packages installed.
        exp_def = """\
arch {0[variant.arch]}
opensolaris.zone global
""".format(variants)

        for opts in ((), ("-a",)):
            # No operands specified case.
            self.__assert_variant_matches(exp_def, opts=opts)

            # Unprivileged user case.
            self.__assert_variant_matches(exp_def, opts=opts,
                su_wrap=True)

        # No output expected for with no variants set and no packages
        # installed for -v, -av, -i, and -iv.
        for opts in (("-v",), ("-av",), ("-i",), ("-iv",)):
            self.__assert_variant_matches("", opts=opts)

        #
        # Next, verify output after setting variants.
        #

        # Set some variants.
        self.pkg("change-variant variant.icecream=strawberry")

        exp_def = """\
arch {0[variant.arch]}
icecream strawberry
opensolaris.zone global
""".format(variants)

        # Output should be the same for both -a and default cases with
        # no packages installed.
        for opts in ((), ("-a",)):
            self.__assert_variant_matches(exp_def, opts=opts)

        #
        # Next, verify output after installing unvarianted package.
        #
        self.pkg("install foo@1.0")

        # Verify output for no options and no patterns.
        exp_def = """\
arch {0[variant.arch]}
icecream strawberry
opensolaris.zone global
""".format(variants)
        self.__assert_variant_matches(exp_def)

        # Verify -a output.
        opts = ("-a",)
        self.__assert_variant_matches(exp_def, opts=opts)

        # Verify -v, -av, -i, and -iv output.
        for opts in (("-v",), ("-av",), ("-i",), ("-iv",)):
            self.__assert_variant_matches("", opts=opts)

        # Test upgraded package that does not declare all
        # facets/variants.
        self.__test_foo_variant_upgrade("foo@2.0", variants)

        # Reinstall and then retest with upgraded package that declares
        # all facets/variants.
        self.pkg("install foo@1.0")
        self.__test_foo_variant_upgrade("foo@3.0", variants)

        # Next, verify output after installing package with unknown
        # variant.
        self.pkg("install unknown@1.0")

        # Verify output for no options and no patterns.
        exp_def = """\
arch {0[variant.arch]}
icecream strawberry
opensolaris.zone global
""".format(variants)
        self.__assert_variant_matches(exp_def)

        # Verify -a output.
        exp_def = """\
arch {0[variant.arch]}
icecream strawberry
opensolaris.zone global
unknown false
""".format(variants)
        self.__assert_variant_matches(exp_def, opts=("-a",))

        # Verify -i output.
        exp_def = """\
unknown false
""".format(variants)
        self.__assert_variant_matches(exp_def, opts=("-i",))

        # Verify -v, -av, and -iv output.
        for opts in (("-v",), ("-av",), ("-iv",)):
            exp_def = """\
unknown bar
unknown foo
""".format(variants)
            self.__assert_variant_matches(exp_def, opts=opts)

    def test_02_varcet_reject(self):
        """Verify that if we try to --reject packages that should get
        removed we invoke the solver."""

        # create an image
        variants = { "variant.icecream": "strawberry" }
        self.image_create(self.rurl, variants=variants)

        # install a package with a dependency
        self.pkg("install need_foo@1.0")

        # Set some facets/variant while rejecting a random package.
        self.pkg("change-facet --reject=nothing "
            "facet.doc.txt=True")
        self.pkg("change-variant --reject=nothing "
            "variant.icecream=neapolitan")

        # Reset the facets/variant to the same value (which would
        # normally be a noop) while rejecting a package and make sure
        # that package gets uninstalled.
        self.pkg("change-facet --reject=need_foo "
            "facet.doc.txt=True")
        self.pkg("install need_foo@1.0")
        self.pkg("change-variant --reject=need_foo "
            "variant.icecream=neapolitan")
        self.pkg("install need_foo@1.0")

        # Reset the facets/variant to the same value (which would
        # normally be a noop) while rejecting a package we can't
        # uninstall due to dependencies.  Make sure this fails.
        self.pkg("change-facet --reject=foo "
            "facet.doc.txt=True", exit=EXIT_OOPS)
        self.pkg("change-variant --reject=foo "
            "variant.icecream=neapolitan", exit=EXIT_OOPS)

    def test_03_variant_globbing(self):
        """Verify that change-variant fails as expected when globbing
        is used to refer to the variants."""

        self.image_create(self.rurl)
        self.pkg("install foo@2.0")

        self.pkg("change-variant 'variant.unknown=strawberry'")
        self.pkg("change-variant 'variant.unknown=strawberry*'")
        self.pkg("change-variant 'variant.unknown=strawberry?'")
        self.pkg("change-variant 'variant.*=strawberry'", exit=1)
        self.pkg("change-variant 'variant.*=strawberry' "
                "'variant.unknown=strawberry'", exit=1)
        self.pkg("change-variant 'variant?=strawberry'", exit=1)
        self.pkg("change-variant 'variant?=strawberry' "
                "'variant.unknown=strawberry'", exit=1)


class TestPkgVarcetErrors(pkg5unittest.Pkg5TestCase):
    """This test class verifies that errors raised while within the _varcet
    extension are handled gracefully and won't cause segmentation faults."""

    def test_01_facet_error_checking(self):
        """Verify that _allow_facet extension function has
        sufficient error checking."""

        class Inner:
            def __init__(self, problem):
                self.problem = problem

            def __str__(self):
                if self.problem == 0:
                    return "fine"
                elif self.problem == 1:  # Exception
                    raise ValueError
                elif self.problem == 2:  # BaseException
                    raise KeyboardInterrupt

        class Action:
            def __init__(self, problem, inproblem):
                if problem == 0:
                    self.attrs = {"facet.debug.test": Inner(inproblem)}
                elif problem == 1:
                    # Not an Unicode object
                    self.attrs = {b"facet.debug.test": Inner(inproblem)}

        facets = facet.Facets({"facet.debug.test": True})
        facets.allow_action(Action(0, 0), None)

        # attr encoding failure handling
        self.assertRaises(TypeError, facets.allow_action, Action(1, 0), None)

        # value encoding failure handling
        self.assertEqual(facets.allow_action(Action(0, 1), None), False)
        self.assertRaises(
            KeyboardInterrupt, facets.allow_action, Action(0, 2), None
        )

    def test_02_variant_error_checking(self):
        """Verify that _allow_variant extension function has
        sufficient error checking."""

        class Action:
            def __init__(self, problem):
                if problem == 0:
                    self.attrs = {"variant.icecream": "strawberry"}
                elif problem == 1:
                    # Non Unicode key
                    self.attrs = {b"variant.icecream": "strawberry"}
                elif problem == 2:
                    # Non Unicode value
                    self.attrs = {"variant.icecream": b"strawberry"}

        variants = variant.Variants({"variant.icecream": "strawberry"})
        variants.allow_action(Action(0), None)

        # attr and value encoding failure handling
        self.assertRaises(TypeError, variants.allow_action, Action(1), None)
        self.assertEqual(variants.allow_action(Action(2), None), False)

        # variant value encoding failure handling
        variants = variant.Variants({"variant.icecream": b"strawberry"})
        self.assertRaises(TypeError, variants.allow_action, Action(0), None)


if __name__ == "__main__":
    unittest.main()
