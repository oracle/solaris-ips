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

# Copyright (c) 2011, 2016, Oracle and/or its affiliates. All rights reserved.

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
import six
import stat
import tempfile
import unittest


class TestPkgMediated(pkg5unittest.SingleDepotTestCase):

        # Don't discard repository or setUp() every test.
        persistent_setup = True

        pkg_sendmail = """
            open pkg://test/sendmail@0.5
            add set name=pkg.summary value="Example sendmail package"
            add file tmp/foosm path=/usr/bin/mailq owner=root group=root mode=0555
            add file tmp/foosm path=/usr/lib/sendmail owner=root group=root mode=2555
            add link path=/usr/sbin/newaliases target=../lib/sendmail
            add link path=/usr/sbin/sendmail target=../lib/sendmail
            close
            open pkg://test/sendmail@1.0
            add set name=pkg.summary value="Example sendmail package"
            add file tmp/foosm path=/usr/lib/sendmail-mta/sendmail owner=root group=root mode=2555
            add file tmp/foosm path=/usr/lib/sendmail-mta/mailq owner=root group=root mode=0555
            add link path=/usr/bin/mailq target=../lib/sendmail-mta/mailq mediator=mta mediator-implementation=sendmail
            add link path=/usr/lib/sendmail target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail
            add link path=/usr/sbin/newaliases target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail
            add link path=/usr/sbin/sendmail target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail
            close
            open pkg://test/sendmail@2.0
            add set name=pkg.summary value="Example sendmail vendor-priority package"
            add file tmp/foosm path=/usr/lib/sendmail-mta/sendmail owner=root group=root mode=2555
            add file tmp/foosm path=/usr/lib/sendmail-mta/mailq owner=root group=root mode=0555
            add link path=/usr/bin/mailq target=../lib/sendmail-mta/mailq mediator=mta mediator-implementation=sendmail mediator-priority=vendor
            add link path=/usr/lib/sendmail target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail mediator-priority=vendor
            add link path=/usr/sbin/newaliases target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail mediator-priority=vendor
            add link path=/usr/sbin/sendmail target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail mediator-priority=vendor
            close
            open pkg://test/sendmail@3.0
            add set name=pkg.summary value="Example sendmail target change package"
            add file tmp/foosm path=/usr/lib/sendmail3-mta/sendmail owner=root group=root mode=2555
            add file tmp/foosm path=/usr/lib/sendmail3-mta/mailq owner=root group=root mode=0555
            add link path=/usr/bin/mailq target=../lib/sendmail3-mta/mailq3 mediator=mta mediator-implementation=sendmail
            add link path=/usr/lib/sendmail target=../lib/sendmail3-mta/sendmail mediator=mta mediator-implementation=sendmail
            add link path=/usr/sbin/newaliases target=../lib/sendmail3-mta/sendmail mediator=mta mediator-implementation=sendmail
            add link path=/usr/sbin/sendmail target=../lib/sendmail3-mta/sendmail mediator=mta mediator-implementation=sendmail
            close """

        pkg_sendmail_links = """
            open pkg://test/sendmail-links@1.0
            add set name=pkg.summary value="Example sendmail package for verifying symlink refcounts behaviour"
            add link path=/usr/bin/mailq target=../lib/sendmail-mta/mailq mediator=mta mediator-implementation=sendmail
            add link path=/usr/lib/sendmail target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail
            add link path=/usr/sbin/newaliases target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail
            add link path=/usr/sbin/sendmail target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail
            close
            open pkg://test/sendmail-links@2.0
            add set name=pkg.summary value="Example sendmail package for verifying symlink refcounts behaviour"
            add hardlink path=/usr/bin/mailq target=../lib/sendmail-mta/mailq mediator=mta mediator-implementation=sendmail
            add hardlink path=/usr/lib/sendmail target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail
            add hardlink path=/usr/sbin/newaliases target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail
            add hardlink path=/usr/sbin/sendmail target=../lib/sendmail-mta/sendmail mediator=mta mediator-implementation=sendmail
            close """

        pkg_postfix = """
            open pkg://test/postfix@1.0
            add set name=pkg.summary value="Example postfix package"
            add file tmp/foopf path=/opt/postfix/sbin/sendmail owner=root group=root mode=2555
            add link path=/usr/bin/mailq target=../../opt/postfix/sbin/sendmail mediator=mta mediator-implementation=postfix
            add link path=/usr/lib/sendmail target=../../opt/postfix/sbin/sendmail mediator=mta mediator-implementation=postfix
            add link path=/usr/sbin/newaliases target=../../opt/postfix/sbin/sendmail mediator=mta mediator-implementation=postfix
            add link path=/usr/sbin/sendmail target=../../opt/postfix/sbin/sendmail mediator=mta mediator-implementation=postfix
            close
            open pkg://test/postfix@2.0
            add set name=pkg.summary value="Example postfix site-priority package"
            add file tmp/foopf path=/opt/postfix/sbin/sendmail owner=root group=root mode=2555
            add link path=/usr/bin/mailq target=../../opt/postfix/sbin/sendmail mediator=mta mediator-implementation=postfix mediator-priority=site
            add link path=/usr/lib/sendmail target=../../opt/postfix/sbin/sendmail mediator=mta mediator-implementation=postfix mediator-priority=site
            add link path=/usr/sbin/newaliases target=../../opt/postfix/sbin/sendmail mediator=mta mediator-implementation=postfix mediator-priority=site
            add link path=/usr/sbin/sendmail target=../../opt/postfix/sbin/sendmail mediator=mta mediator-implementation=postfix mediator-priority=site
            close """

        pkg_conflict_mta = """
            open pkg://test/conflict-mta@1.0
            add file tmp/foopf path=/opt/conflict-mta/sbin/sendmail owner=root group=root mode=2555
            add link path=/usr/bin/mailq target=../../opt/conflict-mta/sbin/sendmail mediator=mail mediator-implementation=conflict
            add link path=/usr/lib/sendmail target=../../opt/conflict-mta/sbin/sendmail mediator=mail mediator-implementation=conflict
            add link path=/usr/sbin/newaliases target=../../opt/conflict-mta/sbin/sendmail mediator=mail mediator-implementation=conflict
            add link path=/usr/sbin/sendmail target=../../opt/conflict-mta/sbin/sendmail mediator=mail mediator-implementation=conflict
            close """

        pkg_duplicate_mta = """
            open pkg://test/duplicate-mta@1.0
            add set name=pkg.summary value="Example mta package that provides duplicate mediation"
            add file tmp/food path=/usr/lib/duplicate-mta/sendmail owner=root group=root mode=2555
            add file tmp/food path=/usr/lib/duplicate-mta/mailq owner=root group=root mode=0555
            add link path=/usr/bin/mailq target=../lib/duplicate-mta/mailq mediator=mta mediator-implementation=sendmail
            add link path=/usr/lib/sendmail target=../lib/duplicate-mta/sendmail mediator=mta mediator-implementation=sendmail
            add link path=/usr/sbin/newaliases target=../lib/duplicate-mta/sendmail mediator=mta mediator-implementation=sendmail
            add link path=/usr/sbin/sendmail target=../lib/duplicate-mta/sendmail mediator=mta mediator-implementation=sendmail
            close
            open pkg://test/duplicate-mta@2.0
            add set name=pkg.summary value="Example mta package that provides duplicate hardlink mediation"
            add file tmp/food path=/usr/lib/duplicate-mta/sendmail owner=root group=root mode=2555
            add file tmp/food path=/usr/lib/duplicate-mta/mailq owner=root group=root mode=0555
            add hardlink path=/usr/bin/mailq target=../lib/duplicate-mta/mailq mediator=mta mediator-implementation=sendmail
            add hardlink path=/usr/lib/sendmail target=../lib/duplicate-mta/sendmail mediator=mta mediator-implementation=sendmail
            add hardlink path=/usr/sbin/newaliases target=../lib/duplicate-mta/sendmail mediator=mta mediator-implementation=sendmail
            add hardlink path=/usr/sbin/sendmail target=../lib/duplicate-mta/sendmail mediator=mta mediator-implementation=sendmail
            close """

        pkg_unmediated_mta = """
            open pkg://test/unmediated-mta@1.0
            add set name=pkg.summary value="Example unmediated mta package"
            add file tmp/foou path=/opt/unmediated/sbin/sendmail owner=root group=root mode=2555
            add link path=/usr/bin/mailq target=../../opt/unmediated/sbin/sendmail
            add link path=/usr/lib/sendmail target=../../opt/unmediated/sbin/sendmail
            add link path=/usr/sbin/newaliases target=../../opt/unmediated/sbin/sendmail
            add link path=/usr/sbin/sendmail target=../../opt/unmediated/sbin/sendmail
            close
            open pkg://test/unmediated-mta@2.0
            add set name=pkg.summary value="Example unmediated hardlink mta package"
            add file tmp/foou path=/opt/unmediated/sbin/sendmail owner=root group=root mode=2555
            add hardlink path=/usr/bin/mailq target=../../opt/unmediated/sbin/sendmail
            add hardlink path=/usr/lib/sendmail target=../../opt/unmediated/sbin/sendmail
            add hardlink path=/usr/sbin/newaliases target=../../opt/unmediated/sbin/sendmail
            add hardlink path=/usr/sbin/sendmail target=../../opt/unmediated/sbin/sendmail
            close """

        pkg_perl = """
            open pkg://test/runtime/perl-584@5.8.4
            add set name=pkg.summary value="Example perl package"
            add file tmp/foopl path=/usr/perl5/5.8.4/bin/perl5.8.4 owner=root group=bin mode=0555
            add hardlink path=/usr/perl5/5.8.4/bin/perl target=perl5.8.4
            add link path=/usr/bin/perl target=../perl5/5.8.4/bin/perl mediator=perl mediator-version=5.8.4
            close
            open pkg://test/runtime/perl-510@5.10.0
            add set name=pkg.summary value="Example perl package"
            add file tmp/foopl path=/usr/perl5/5.10.0/bin/perl5.10.0 owner=root group=bin mode=0555
            add hardlink path=/usr/perl5/5.10.0/bin/perl target=perl5.10.0
            add link path=/usr/bin/perl target=../perl5/5.10.0/bin/perl mediator=perl mediator-version=5.10.0
            close """

        pkg_python = """
            open pkg://test/runtime/python-27@2.7.0
            add set name=pkg.summary value="Example python package"
            add file tmp/foopy path=/usr/bin/python2.7 owner=root group=bin mode=0555
            add link path=/usr/bin/python target=python2.7 mediator=python mediator-version=2.7
            close
            open pkg://test/runtime/python-34@3.4.0
            add set name=pkg.summary value="Example python package"
            add file tmp/foopy path=/usr/bin/python3.4 owner=root group=bin mode=0555
            add link path=/usr/bin/python target=python3.4 mediator=python mediator-version=3.4
            close
            open pkg://test/runtime/python-unladen-swallow-27@2.7.0
            add set name=pkg.summary value="Example python implementation package"
            add file tmp/foopyus path=/usr/bin/python2.7-unladen-swallow owner=root group=bin mode=0555
            add link path=/usr/bin/python target=python2.7-unladen-swallow mediator=python mediator-version=2.7 mediator-implementation=unladen-swallow
            close
            open pkg://test/runtime/python-unladen-swallow-34@3.4.0
            add set name=pkg.summary value="Example python implementation package"
            add file tmp/foopyus path=/usr/bin/python3.4-unladen-swallow owner=root group=bin mode=0555
            add link path=/usr/bin/python target=python3.4-unladen-swallow mediator=python mediator-version=3.4 mediator-implementation=unladen-swallow
            close
            open pkg://test/runtime/python-unladen-swallow-35@3.5.0
            add set name=pkg.summary value="Example python versioned implementation package"
            add file tmp/foopyus path=/usr/bin/python3.5-unladen-swallow owner=root group=bin mode=0555
            add link path=/usr/bin/python target=python3.5-unladen-swallow mediator=python mediator-version=3.5 mediator-implementation=unladen-swallow@3.5
            close """

        pkg_multi_python = """
            open pkg://test/runtime/multi-impl-python-27@2.7.0
            add set name=pkg.summary value="Example python package with multiple implementations"
            add file tmp/foopy path=/usr/bin/python2.7 owner=root group=bin mode=0555
            add link path=/usr/bin/python target=python2.7 mediator=python mediator-implementation=cpython
            add file tmp/foopyus path=/usr/bin/python2.7-unladen-swallow owner=root group=bin mode=0555
            add link path=/usr/bin/python target=python2.7-unladen-swallow mediator=python mediator-implementation=unladen-swallow
            close
            open pkg://test/runtime/multi-impl-ver-python@3.4.0
            add set name=pkg.summary value="Example python implementation package with multiple implementations and versions"
            add file tmp/foopy path=/usr/bin/python2.7 owner=root group=bin mode=0555
            add link path=/usr/bin/python target=python2.7 mediator=python mediator-version=2.7
            add file tmp/foopyus path=/usr/bin/python2.7-unladen-swallow owner=root group=bin mode=0555
            add file tmp/foopy path=/usr/bin/python3.4 owner=root group=bin mode=0555
            add link path=/usr/bin/python target=python3.4 mediator=python mediator-version=3.4
            add link path=/usr/bin/python target=python2.7-unladen-swallow mediator=python mediator-version=2.7 mediator-implementation=unladen-swallow
            add file tmp/foopyus path=/usr/bin/python3.4-unladen-swallow owner=root group=bin mode=0555
            add link path=/usr/bin/python target=python3.4-unladen-swallow mediator=python mediator-version=3.4 mediator-implementation=unladen-swallow
            close
            """

        pkg_vi = """
            open pkg://test/editor/nvi@1.0
            add set name=pkg.summary value="Example nvi vendor priority package"
            add file tmp/foonvi path=/usr/bin/nvi owner=root group=bin mode=0555
            add hardlink path=/usr/bin/vi target=nvi mediator=vi mediator-implementation=nvi mediator-priority=vendor
            close
            open pkg://test/editor/svr4-vi@1.0
            add set name=pkg.summary value="Example vi package"
            add file tmp/foovi path=/usr/sunos/bin/edit owner=root group=bin mode=0555
            add hardlink path=/usr/bin/vi target=../sunos/bin/edit mediator=vi mediator-implementation=svr4
            close
            open pkg://test/editor/vim@1.0
            add set name=pkg.summary value="Example vim vi package"
            add file tmp/foovim path=/usr/bin/vim owner=root group=bin mode=0555
            add hardlink path=/usr/bin/vi target=vim mediator=vi mediator-implementation=vim facet.vi=true
            close
            open pkg://test/editor/vim@2.0
            add set name=pkg.summary value="Example vim vi site priority package"
            add file tmp/foovim path=/usr/bin/vim owner=root group=bin mode=0555
            add hardlink path=/usr/bin/vi target=vim mediator=vi mediator-implementation=vim mediator-priority=site facet.vi=true
            close """

        pkg_multi_ver = """
            open pkg://test/web/server/apache-22/module/apache-php52@5.2.5
            add set name=pkg.summary value="Example multiple version mod_php package"
            add file tmp/fooc path=usr/apache2/2.2/libexec/mod_php5.2.so owner=root group=bin mode=0555
            add link path=usr/apache2/2.2/libexec/mod_php5.so target=mod_php5.2.so mediator=php mediator-version=5.2
            add file tmp/food path=usr/apache2/2.2/libexec/mod_php5.2.5.so owner=root group=bin mode=0555
            add link path=usr/apache2/2.2/libexec/mod_php5.so target=mod_php5.2.5.so mediator=php mediator-version=5.2.5
            close """

        pkg_variant = """
            open pkg://test/multi-ver-variant@1.0
            add set name=pkg.summary value="Example mediated varianted package"
            add file tmp/fooc path=/usr/bin/foo-1-nd owner=root group=bin mode=0555
            add file tmp/food path=/usr/bin/foo-1-d owner=root group=bin mode=0555
            add hardlink path=usr/bin/foo target=foo-1-nd mediator=foo mediator-version=1 variant.debug.osnet=false
            add hardlink path=usr/bin/foo target=foo-1-d mediator=foo mediator-version=1 variant.debug.osnet=true
            add file tmp/fooc path=/usr/bin/foo-2-nd owner=root group=bin mode=0555
            add file tmp/food path=/usr/bin/foo-2-d owner=root group=bin mode=0555
            add hardlink path=usr/bin/foo target=foo-2-nd mediator=foo mediator-version=2 variant.debug.osnet=false
            add hardlink path=usr/bin/foo target=foo-2-d mediator=foo mediator-version=2 variant.debug.osnet=true
            close """

        misc_files = ["tmp/fooc", "tmp/food", "tmp/foopl", "tmp/foopy",
            "tmp/foopyus", "tmp/foosm", "tmp/foopf", "tmp/foou", "tmp/foonvi",
            "tmp/foovi", "tmp/foovim"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.rurl, [
                    getattr(self, p)
                    for p in dir(self)
                    if p.startswith("pkg_") and isinstance(getattr(self, p),
                        six.string_types)
                ])

        def __assert_mediation_matches(self, expected, mediators=misc.EmptyI):
                self.pkg("mediator -H -F tsv {0}".format(" ".join(mediators)))
                self.assertEqualDiff(expected, self.output)

        def __assert_available_mediation_matches(self, expected,
            mediators=misc.EmptyI, su_wrap=False):
                self.pkg("mediator -H -F tsv -a {0}".format(" ".join(mediators)),
                    su_wrap=su_wrap)
                self.assertEqualDiff(expected, self.output)

        def __assert_human_mediation_matches(self, expected):
                self.pkg("mediator")
                self.assertEqualDiff(expected, self.output)

        def test_00_mediator(self):
                """Verify set-mediator / unset-mediator function as expected
                when setting / unsetting values only.  Other tests verify
                mediation change behaviour.
                """

                self.image_create(self.rurl)

                # Verify lack of required input results in graceful failure for
                # set/unset-mediator.
                self.pkg("set-mediator", exit=2)
                self.pkg("set-mediator mta", exit=2)
                self.pkg("unset-mediator", exit=2)

                # Verify unsetting a mediator not set results in nothing to do.
                self.pkg("unset-mediator mta", exit=4)

                # Verify bad options or option input to set/unset-mediator
                # result in graceful failure.
                self.pkg("set-mediator -I not.valid mta", exit=2)
                self.pkg("set-mediator --nosuchoption -I sendmail mta", exit=2)
                self.pkg("set-mediator -I notvalid@a mta", exit=2)
                self.pkg("set-mediator -I notvalid@1.a mta", exit=2)
                self.pkg("set-mediator -I 'notvalid@$@^&@)' mta", exit=2)
                self.pkg("set-mediator -I @1.0 mta", exit=2)
                self.pkg("set-mediator -V not-valid mta", exit=2)
                self.pkg("set-mediator -I '' mta", exit=2)
                self.pkg("set-mediator -V '' mta", exit=2)
                self.pkg("unset-mediator --nosuchoption mta", exit=2)

                # Verify unprivileged user attempting set-mediator results in
                # graceful failure.
                self.pkg("set-mediator -vvv -I sendmail mta", exit=1,
                    su_wrap=True)

                # Verify mediation can be set and that the parsable output is
                # correct.
                self.pkg("set-mediator -n --parsable=0 -I sendmail mta")
                self.assertEqualParsable(self.output, change_mediators=[
                    ["mta",
                        [[None, None], [None, "system"]],
                        [[None, None], ["sendmail", "local"]]]])
                self.pkg("set-mediator --parsable=0 -I sendmail mta")
                self.assertEqualParsable(self.output, change_mediators=[
                    ["mta",
                        [[None, None], [None, "system"]],
                        [[None, None], ["sendmail", "local"]]]])
                self.__assert_mediation_matches("""\
mta\tsystem\t\tlocal\tsendmail\t
""")

                self.pkg("set-mediator -vvv -V 1.0 mta")
                self.__assert_mediation_matches("""\
mta\tlocal\t1.0\tlocal\tsendmail\t
""")
                self.pkg("set-mediator -vvv -V '' -I sendmail mta")
                self.__assert_mediation_matches("""\
mta\tsystem\t\tlocal\tsendmail\t
""")
                self.pkg("set-mediator -vvv -V 1.0 -I postfix@1.0 mta")
                self.__assert_mediation_matches("""\
mta\tlocal\t1.0\tlocal\tpostfix@1.0\t
""")

                # Verify unprilveged user attempting unset-mediator results in
                # graceful failure.
                self.pkg("unset-mediator -I mta", exit=1, su_wrap=True)

                # Verify individual components of mediation can be unset.
                self.pkg("unset-mediator -vvv -V mta")
                self.__assert_mediation_matches("""\
mta\tsystem\t\tlocal\tpostfix@1.0\t
""")
                # Test the parsable output of set-mediator.
                self.pkg("set-mediator --parsable=0 -V 1.0 mta")
                self.assertEqualParsable(self.output, change_mediators=[
                    ["mta",
                        [[None, "system"], ["1.0", "local"]],
                        [["postfix@1.0", "local"], ["postfix@1.0", "local"]]]])
                self.__assert_mediation_matches("""\
mta\tlocal\t1.0\tlocal\tpostfix@1.0\t
""")

                self.pkg("unset-mediator -n --parsable=0 -I mta")
                self.assertEqualParsable(self.output, change_mediators=[
                    ["mta",
                        [["1.0", "local"], ["1.0", "local"]],
                        [["postfix@1.0", "local"], [None, "system"]]]])
                self.pkg("unset-mediator --parsable=0 -I mta")
                self.assertEqualParsable(self.output, change_mediators=[
                    ["mta",
                        [["1.0", "local"], ["1.0", "local"]],
                        [["postfix@1.0", "local"], [None, "system"]]]])
                self.__assert_mediation_matches("""\
mta\tlocal\t1.0\tsystem\t\t
""")

                # Verify unsetting last component without installed package
                # results in completely removing mediation.
                self.pkg("unset-mediator -vvv -V mta")
                self.__assert_mediation_matches("""\
""")

                # Now install some packages to test the ability to list
                # available mediations.
                self.pkg("install -vvv \*/python\* \*perl\* \*vi\*")

                # Test listing all available mediations.
                self.__assert_available_mediation_matches("""\
perl\tsystem\t5.10.0\tsystem\t\t
perl\tsystem\t5.8.4\tsystem\t\t
python\tsystem\t3.5\tsystem\tunladen-swallow@3.5\t
python\tsystem\t3.4\tsystem\t\t
python\tsystem\t3.4\tsystem\tunladen-swallow\t
python\tsystem\t2.7\tsystem\t\t
python\tsystem\t2.7\tsystem\tunladen-swallow\t
vi\tsite\t\tsite\tvim\t
vi\tvendor\t\tvendor\tnvi\t
vi\tsystem\t\tsystem\tsvr4\t
""")

                # Dump image cache before continuing to verify the
                # information is re-generated and operations succeed.
                imgdir = self.get_img_api_obj().img.imgdir
                cdir = os.path.join(imgdir, "cache")
                assert os.path.exists(cdir)
                shutil.rmtree(cdir)

                # Test listing specific available mediations.
                self.__assert_available_mediation_matches("""\
perl\tsystem\t5.10.0\tsystem\t\t
perl\tsystem\t5.8.4\tsystem\t\t
vi\tsite\t\tsite\tvim\t
vi\tvendor\t\tvendor\tnvi\t
vi\tsystem\t\tsystem\tsvr4\t
""", ("perl", "vi"), su_wrap=True)
                self.__assert_available_mediation_matches("""\
vi\tsite\t\tsite\tvim\t
vi\tvendor\t\tvendor\tnvi\t
vi\tsystem\t\tsystem\tsvr4\t
""", ("vi",))

                # Set facet.vi=false and verify vim mediation is no longer
                # available but verify still passes.
                self.pkg("change-facet -vvv vi=false")
                self.__assert_available_mediation_matches("""\
vi\tvendor\t\tvendor\tnvi\t
vi\tsystem\t\tsystem\tsvr4\t
""", ("vi",))
                self.pkg("verify")

                # Set facet.vi=true and verify vim mediation is available again.
                self.pkg("change-facet -vvv vi=true")
                self.__assert_available_mediation_matches("""\
vi\tsite\t\tsite\tvim\t
vi\tvendor\t\tvendor\tnvi\t
vi\tsystem\t\tsystem\tsvr4\t
""", ("vi",))
                self.pkg("verify")

                # Verify exit 1 if no mediators matched.
                self.pkg("mediator no-match no-match2", exit=1)
                self.pkg("mediator -a no-match no-match2", exit=1)

                # Verify exit 3 (partial failure) if only some mediators match.
                self.pkg("mediator perl no-match", exit=3)
                self.pkg("mediator -a perl no-match", exit=3)

        def test_01_symlink_mediation(self):
                """Verify that package mediation works as expected for install,
                update, and uninstall with symbolic links.
                """

                self.image_create(self.rurl)

                def gen_mta_files():
                        for fname in ("mailq",):
                                fpath = os.path.join(self.img_path(), "usr",
                                    "bin", fname)
                                yield fpath

                        for fname in ("sendmail",):
                                fpath = os.path.join(self.img_path(), "usr",
                                    "lib", fname)
                                yield fpath

                def gen_mta_links():
                        for lname in ("mailq",):
                                lpath = os.path.join(self.img_path(), "usr",
                                    "bin", lname)
                                yield lpath

                        for lname in ("newaliases", "sendmail"):
                                lpath = os.path.join(self.img_path(), "usr",
                                    "sbin", lname)
                                yield lpath

                        for lname in ("sendmail",):
                                lpath = os.path.join(self.img_path(), "usr",
                                    "lib", lname)
                                yield lpath

                def gen_perl_links():
                        for lname in ("perl",):
                                lpath = os.path.join(self.img_path(), "usr",
                                    "bin", lname)
                                yield lpath

                def gen_php_links():
                        for lname in ("mod_php5.so",):
                                lpath = os.path.join(self.img_path(), "usr",
                                    "apache2", "2.2", "libexec", lname)
                                yield lpath

                def gen_python_links():
                        for lname in ("python",):
                                lpath = os.path.join(self.img_path(), "usr",
                                    "bin", lname)
                                yield lpath

                def check_files(files):
                        for fpath in files:
                                s = os.lstat(fpath)
                                self.assertTrue(stat.S_ISREG(s.st_mode))

                def check_target(links, target):
                        for lpath in links:
                                ltarget = os.readlink(lpath)
                                self.assertTrue(target in ltarget)

                def check_not_target(links, target):
                        for lpath in links:
                                ltarget = os.readlink(lpath)
                                self.assertTrue(target not in ltarget)

                def check_exists(links):
                        for lpath in links:
                                self.assertTrue(os.path.exists(lpath))

                def check_not_exists(links):
                        for lpath in links:
                                self.assertTrue(not os.path.exists(lpath))

                def remove_links(links):
                        for lpath in links:
                                portable.remove(lpath)

                # Some installs are done with extra verbosity to ease in
                # debugging tests when they fail.
                self.pkg("install -vvv sendmail@0.5")
                self.pkg("mediator") # If tests fail, this is helpful.

                # Verify that /usr/bin/mailq and /usr/lib/sendmail are files.
                check_files(gen_mta_files())
                self.pkg("verify -v")

                # Upgrading to 1.0 should transition the files to links.
                self.pkg("install -vvv sendmail@1")
                self.pkg("mediator") # If tests fail, this is helpful.
                self.pkg("verify -v")

                # Check that installed links point to sendmail and that
                # verify passes.
                check_target(gen_mta_links(), "sendmail-mta")
                self.pkg("verify")
                self.__assert_mediation_matches("""\
mta\tsystem\t\tsystem\tsendmail\t
""")

                # Upgrading to 3.0 should change the targets of every link.
                self.pkg("install -vvv sendmail@3")
                self.pkg("mediator") # If tests fail, this is helpful.
                check_target(gen_mta_links(), "sendmail3-mta")
                self.pkg("verify -v")

                # Downgrading to 0.5 should change sendmail and mailq links back
                # to a file.
                self.pkg("update -vvv sendmail@0.5")
                self.pkg("mediator") # If tests fail, this is helpful.
                check_files(gen_mta_files())
                self.pkg("verify -v")

                # Finally, upgrade to 1.0 again for remaining tests.
                self.pkg("update -vvv sendmail@1.0")
                self.pkg("mediator") # If tests fail, this is helpful.
                check_target(gen_mta_links(), "sendmail-mta")
                self.pkg("verify -v")

                # Install postfix (this should succeed even though sendmail is
                # already installed) and the links should be updated to point to
                # postfix, and verify should pass.
                self.pkg("install -vvv postfix@1")
                check_target(gen_mta_links(), "postfix")
                self.pkg("verify")
                self.__assert_mediation_matches("""\
mta\tsystem\t\tsystem\tpostfix\t
""")

                # Remove the links for postfix, and then check that verify
                # fails and that fix will restore the correct ones.
                remove_links(gen_mta_links())
                self.pkg("verify sendmail") # sendmail should be correct
                self.pkg("verify postfix", exit=1) # postfix links are missing
                self.pkg("fix")
                self.pkg("verify")
                check_target(gen_mta_links(), "postfix")

                # Verify that setting mediation to existing value results in
                # a change since mediation will now be marked as source
                # 'local'.
                self.pkg("set-mediator -vvv -I postfix mta")
                self.__assert_mediation_matches("""\
mta\tsystem\t\tlocal\tpostfix\t
""")

                # Verify that setting the same mediation again results in no
                # changes since mediation is already effective and marked as
                # source 'local'.
                self.pkg("set-mediator -vvv -I postfix mta", exit=4)

                # Now change mediation implementation to sendmail.
                self.pkg("set-mediator -vvv -I sendmail mta")
                self.__assert_mediation_matches("""\
mta\tsystem\t\tlocal\tsendmail\t
""")

                # Check that installed links point to sendmail and that verify
                # passes.
                check_target(gen_mta_links(), "sendmail-mta")
                self.pkg("verify")

                # Now change mediation to implementation not available.  All
                # mediated links should be removed, and verify should still
                # pass.
                self.pkg("set-mediator -vvv -I nosuchmta mta")
                check_not_exists(gen_mta_links())
                self.pkg("verify")
                self.__assert_mediation_matches("""\
mta\tsystem\t\tlocal\tnosuchmta\t
""")

                # Now uninstall all packages.
                self.pkg("uninstall -vvv \*")
                self.pkg("verify")
                check_not_exists(gen_mta_links())
                self.__assert_mediation_matches("""\
mta\tsystem\t\tlocal\tnosuchmta\t
""")

                # Now install both at the same time, since the bogus
                # implementation is still set, no links should be installed.
                self.pkg("install -vvv sendmail@1 postfix@1")
                self.pkg("verify")
                check_not_exists(gen_mta_links())

                # Now unset the mediation, postfix should be preferred since it
                # is first lexically, and verify should pass.
                self.pkg("unset-mediator -vvv -I mta")
                check_target(gen_mta_links(), "postfix")
                self.pkg("verify")
                self.__assert_mediation_matches("""\
mta\tsystem\t\tsystem\tpostfix\t
""")

                # Now uninstall all packages, then reinstall them and verify
                # that postfix was selected for initial install (since user did
                # not explicitly set a mediation) and that verify passes.
                self.pkg("uninstall \*")
                self.pkg("install -vvv sendmail@1 postfix@1")
                check_target(gen_mta_links(), "postfix")
                self.pkg("verify")
                self.__assert_mediation_matches("""\
mta\tsystem\t\tsystem\tpostfix\t
""")

                # Verify that an unmediated package can't be installed if it
                # conflicts with mediated packages that are installed.
                self.pkg("install unmediated-mta@1", exit=1)
                self.pkg("install unmediated-mta@2", exit=1)

                # Verify that a mediated package that delivers conflicting links
                # with the same mediation as an installed package cannot be
                # installed.
                self.pkg("install duplicate-mta@1", exit=1)
                self.pkg("install duplicate-mta@2", exit=1)

                # Verify that a mediated package with a conflicting mediator
                # can't be installed if it conflicts with mediated packages
                # that are installed.
                self.pkg("install conflict-mta", exit=1)

                # Verify that an unmediated package can be installed if the
                # mediated ones are removed.
                self.pkg("install -vvv --reject postfix --reject sendmail "
                    "unmediated-mta")
                self.pkg("verify")

                # Verify that mediated packages cannot be installed if an
                # unmediated, conflicting package is installed.
                self.pkg("install postfix", exit=1)

                # Remove all packages, then install both postfix and sendmail,
                # verify that postfix was selected, then remove postfix and
                # verify sendmail is selected (since the user didn't explicitly
                # set a mediation).
                self.pkg("uninstall \*")
                self.pkg("install -vvv postfix@1 sendmail@1")
                check_target(gen_mta_links(), "postfix")
                self.pkg("verify")
                self.pkg("uninstall -vvv postfix")
                check_target(gen_mta_links(), "sendmail-mta")
                self.pkg("verify")

                # Now explicitly set sendmail for the mediation, then remove
                # sendmail and install postfix, and verify links are not
                # present.
                self.pkg("mediator")
                self.pkg("set-mediator -vvv -I sendmail mta")
                self.pkg("verify")
                self.pkg("uninstall -vvv sendmail")
                self.pkg("verify")
                self.pkg("install -vvv postfix@1")
                check_not_exists(gen_mta_links())
                self.pkg("verify")

                # Install sendmail again and verify links point to sendmail.
                self.pkg("install -vvv sendmail@1")
                check_target(gen_mta_links(), "sendmail-mta")
                self.pkg("verify")

                # Remove and install postfix and verify links still point to
                # sendmail (since user explicitly set mediation to sendmail
                # previously).
                self.pkg("uninstall -vvv postfix")
                self.pkg("verify")
                self.pkg("install -vvv postfix@1")
                check_target(gen_mta_links(), "sendmail-mta")
                self.pkg("verify")

                # Verify that a package with an identical set of links for
                # sendmail can be installed and that verify passes.
                self.pkg("install -vvv sendmail-links@1")
                self.pkg("verify")

                # Verify that removing sendmail-links will not remove the links
                # since sendmail still delivers them and that verify
                # still passes.
                self.pkg("uninstall -vvv sendmail-links@1")
                check_target(gen_mta_links(), "sendmail-mta")
                self.pkg("verify")

                # Verify that a version of sendmail-links that delivers the
                # links as hardlinks conflicts even though mediation is the
                # the same.
                self.pkg("install -vvv sendmail-links@2", exit=1)

                # Now install sendmail-links again, and then remove both of them
                # and verify that the links are gone and verify passes.
                self.pkg("install -vvv sendmail-links@1")
                check_target(gen_mta_links(), "sendmail-mta")
                self.pkg("verify")
                self.pkg("uninstall -vvv sendmail sendmail-links")
                check_not_exists(gen_mta_links())
                self.pkg("verify")

                # Unset mediation for following tests.
                self.pkg("unset-mediator -vvv mta")
                self.pkg("verify")

                # Install sendmail@1 and postfix@1, then upgrade to sendmail@2
                # and verify that links point to sendmail due to vendor
                # priority, and then upgrade to postfix@2 and verify that links
                # point to postfix due to site priority.
                self.pkg("install -vvv sendmail@1 postfix@1")
                check_target(gen_mta_links(), "postfix")
                self.pkg("update -vvv sendmail@2")
                check_target(gen_mta_links(), "sendmail-mta")
                self.__assert_mediation_matches("""\
mta\tvendor\t\tvendor\tsendmail\t
""")
                self.pkg("verify")
                self.pkg("update -vvv postfix@2")
                check_target(gen_mta_links(), "postfix")
                self.__assert_mediation_matches("""\
mta\tsite\t\tsite\tpostfix\t
""")
                self.pkg("verify")

                # The mta packages are left installed to verify that the system
                # properly handles multiple mediators in an image.

                # Install perl5.8.4 and verify link targets point to 5.8.4
                # and verify passes.
                self.pkg("install -vvv perl-584")
                check_target(gen_perl_links(), "5.8.4")
                self.pkg("verify")

                # Install perl5.10.0 and verify link targets point to 5.10.0
                # and verify passes.
                self.pkg("install -vvv perl-510")
                check_target(gen_perl_links(), "5.10.0")
                self.pkg("verify")

                # Change mediation to 5.8.4 and verify link targets point to
                # 5.8.4 and verify passes.
                self.pkg("set-mediator -vvv -V 5.8.4 perl")
                check_target(gen_perl_links(), "5.8.4")
                self.__assert_mediation_matches("""\
mta\tsite\t\tsite\tpostfix\t
perl\tlocal\t5.8.4\tsystem\t\t
""")
                self.pkg("verify")

                # Remove perl5.8.4 and verify links no longer exist and verify
                # passes.
                self.pkg("uninstall -vvv perl-584")
                check_not_exists(gen_perl_links())
                self.__assert_mediation_matches("""\
mta\tsite\t\tsite\tpostfix\t
perl\tlocal\t5.8.4\tsystem\t\t
""")
                self.pkg("verify")

                # Unset mediation, verify links point to perl5.10.0,
                # remove perl-510, verify links do not exist, verify
                # passes, and mediation is unknown.
                self.pkg("unset-mediator -vvv perl")
                check_target(gen_perl_links(), "5.10.0")
                self.__assert_mediation_matches("""\
mta\tsite\t\tsite\tpostfix\t
perl\tsystem\t5.10.0\tsystem\t\t
""")
                self.pkg("uninstall -vvv perl-510")
                self.pkg("mediator perl", exit=1)
                self.__assert_mediation_matches("""\
mta\tsite\t\tsite\tpostfix\t
""")
                self.pkg("verify")

                # Install both perl5.8.4 and perl5.10.0, verify that 5.10.0 is
                # preferred for links as it has the greatest version, and that
                # verify passes.
                self.pkg("install -vvv perl-584 perl-510")
                check_target(gen_perl_links(), "5.10.0")
                self.__assert_mediation_matches("""\
mta\tsite\t\tsite\tpostfix\t
perl\tsystem\t5.10.0\tsystem\t\t
""")
                self.pkg("verify")
                self.pkg("uninstall -vvv \*")
                self.pkg("verify")

                # Install python and python-unladen-swallow at the same time,
                # verify that unladen-swallow is NOT selected.
                self.pkg("install python-27 python-unladen-swallow-27")
                self.__assert_mediation_matches("""\
python\tsystem\t2.7\tsystem\t\t
""")
                check_not_target(gen_python_links(), "unladen-swallow")
                self.pkg("verify")

                # Set only mediation version and verify unladen swallow is NOT
                # selected.
                self.pkg("set-mediator -vvv -V 2.7 python")
                self.__assert_mediation_matches("""\
python\tlocal\t2.7\tsystem\t\t
""")
                check_not_target(gen_python_links(), "unladen-swallow")
                self.pkg("verify")

                # Set mediation implementation to unladen swallow and verify it
                # was selected.
                self.pkg("set-mediator -vvv -I unladen-swallow python")
                self.__assert_mediation_matches("""\
python\tlocal\t2.7\tlocal\tunladen-swallow\t
""")
                check_target(gen_python_links(), "unladen-swallow")
                self.pkg("verify")

                # Unset only version mediation and verify unladen swallow is
                # still selected.
                self.pkg("unset-mediator -V python")
                self.__assert_mediation_matches("""\
python\tsystem\t2.7\tlocal\tunladen-swallow\t
""")
                check_target(gen_python_links(), "unladen-swallow")
                self.pkg("verify")

                # Install python-34 and verify unladen swallow is still
                # selected.
                self.pkg("install python-34")
                self.__assert_mediation_matches("""\
python\tsystem\t2.7\tlocal\tunladen-swallow\t
""")
                check_target(gen_python_links(), "unladen-swallow")
                self.pkg("verify")

                # Install python-unladen-swallow-34 and verify that version
                # is selected.
                self.pkg("install python-unladen-swallow-34")
                self.__assert_mediation_matches("""\
python\tsystem\t3.4\tlocal\tunladen-swallow\t
""")
                check_target(gen_python_links(), "python3.4-unladen-swallow")
                self.pkg("verify")

                # Set mediation version to 2.7 and verify that version of
                # unladen swallow is selected.
                self.pkg("set-mediator -vvv -V 2.7 python")
                self.__assert_mediation_matches("""\
python\tlocal\t2.7\tlocal\tunladen-swallow\t
""")
                check_target(gen_python_links(), "python2.7-unladen-swallow")
                self.pkg("verify")

                # Unset implementation mediation and verify unladen swallow
                # is NOT selected.
                self.pkg("unset-mediator -vvv -I python")
                self.__assert_mediation_matches("""\
python\tlocal\t2.7\tsystem\t\t
""")
                check_not_target(gen_python_links(), "unladen-swallow")
                self.pkg("verify")

                # Remove python-27 and python-34 and then verify unladen swallow
                # is selected.
                self.pkg("uninstall -vvv python-27 python-34")
                self.__assert_mediation_matches("""\
python\tlocal\t2.7\tsystem\tunladen-swallow\t
""")
                check_target(gen_python_links(), "python2.7-unladen-swallow")
                self.pkg("verify")

                # Set mediation implementation to None explicitly and verify
                # unladen swallow is NOT selected and link does not exist
                # since no package satisfied mediation.
                self.pkg("set-mediator -vvv -I None python")
                self.__assert_mediation_matches("""\
python\tlocal\t2.7\tlocal\t\t
""")
                check_not_exists(gen_python_links())
                self.pkg("verify")

                # Install unladen-swallow@3.5, then set mediation implementation
                # to unladen-swallow@3.5 and verify the 3.5 implementation is
                # selected.
                self.pkg("install -vvv python-unladen-swallow-35")
                check_not_exists(gen_python_links())
                self.pkg("verify")
                self.pkg("set-mediator -vvv "
                    "-V '' -I unladen-swallow@3.5 python")
                check_target(gen_python_links(), "python3.5-unladen-swallow")
                self.__assert_mediation_matches("""\
python\tsystem\t3.5\tlocal\tunladen-swallow@3.5\t
""")
                self.pkg("verify")

                # Set mediation to unladen-swallow and verify
                # unladen-swallow@3.5 remains selected.
                self.pkg("set-mediator -vvv -I unladen-swallow python")
                check_target(gen_python_links(), "python3.5-unladen-swallow")
                self.__assert_mediation_matches("""\
python\tsystem\t3.5\tlocal\tunladen-swallow\t3.5
""")
                self.pkg("verify")

                # Remove installed links and ensure verify fails, then fix and
                # ensure verify passes.
                remove_links(gen_python_links())
                self.pkg("verify -v python-unladen-swallow-27 "
                    "python-unladen-swallow-34")
                self.pkg("verify -v python-unladen-swallow-35", exit=1)
                self.pkg("fix")
                self.pkg("verify -v")

                # Human-readable output shows any version selected but not
                # explicitly requested in parentheses.
                self.__assert_human_mediation_matches("""\
MEDIATOR VER. SRC. VERSION IMPL. SRC. IMPLEMENTATION
python   system    3.5     local      unladen-swallow(@3.5)
""")

                # Set mediation to unladen-swallow@ and verify unladen-swallow
                # 3.4 is selected.
                self.pkg("set-mediator -vvv -I unladen-swallow@ python")
                check_target(gen_python_links(), "python3.4-unladen-swallow")
                self.__assert_mediation_matches("""\
python\tsystem\t3.4\tlocal\tunladen-swallow@\t
""")
                self.pkg("verify")

                # Remove links and ensure verify fails for for unladen-swallow
                # 3.4, but passes for 2.7 and 3.5, and that fix will allow
                # verify to pass again.
                remove_links(gen_python_links())
                self.pkg("verify -v python-unladen-swallow-27 "
                    "python-unladen-swallow-35")
                self.pkg("verify -v python-unladen-swallow-34", exit=1)
                self.pkg("fix")
                self.pkg("verify -v")

                # Remove all packages; then verify that installing a single
                # package that has multiple version mediations works as
                # expected.
                self.pkg("unset-mediator -I python")
                self.pkg("uninstall \*")

                # Install apache-php52; verify that php 5.2.5 is selected.
                self.pkg("install -vvv apache-php52")
                self.__assert_mediation_matches("""\
php\tsystem\t5.2.5\tsystem\t\t
""")
                check_target(gen_php_links(), "5.2.5")
                self.pkg("verify")

                # Test available mediations.
                self.__assert_available_mediation_matches("""\
php\tsystem\t5.2.5\tsystem\t\t
php\tsystem\t5.2\tsystem\t\t
""")

                # Set mediation version to 5.2 and verify 5.2.5 is NOT selected.
                self.pkg("set-mediator -vvv -V 5.2 php")
                self.__assert_mediation_matches("""\
php\tlocal\t5.2\tsystem\t\t
""")
                check_not_target(gen_php_links(), "5.2.5")
                self.pkg("verify")

                # Remove all packages; then verify that installing a single
                # package that has multiple mediation implementations works as
                # expected.
                self.pkg("uninstall \*")
                self.pkg("unset-mediator -V php")

                # Install multi-impl-python; verify that unladen swallow is NOT
                # selected.
                self.pkg("install -vvv multi-impl-python-27")
                self.__assert_mediation_matches("""\
python\tsystem\t\tsystem\tcpython\t
""")
                check_not_target(gen_python_links(), "unladen-swallow")
                self.pkg("verify")

                # Test available mediations.
                self.__assert_available_mediation_matches("""\
python\tsystem\t\tsystem\tcpython\t
python\tsystem\t\tsystem\tunladen-swallow\t
""")

                # Set mediation implementation to unladen swallow and verify it
                # was selected.
                self.pkg("set-mediator -vvv -I unladen-swallow python")
                self.__assert_mediation_matches("""\
python\tsystem\t\tlocal\tunladen-swallow\t
""")
                check_target(gen_python_links(), "unladen-swallow")
                self.pkg("verify")

                # Remove all packages; then verify that installing a single
                # package that has multiple mediation and version
                # implementations works as expected.
                self.pkg("uninstall \*")
                self.pkg("unset-mediator -I python")
                self.pkg("install -vvv multi-impl-ver-python")

                # Verify that the default implementation of Python 3.4 was
                # selected even though the package offers Python 2.7 and an
                # unladen swallow implemenation of each version of Python.
                self.__assert_mediation_matches("""\
python\tsystem\t3.4\tsystem\t\t
""")
                check_not_target(gen_python_links(), "unladen-swallow")
                self.pkg("verify")

                # Test available mediations.
                self.__assert_available_mediation_matches("""\
python\tsystem\t3.4\tsystem\t\t
python\tsystem\t3.4\tsystem\tunladen-swallow\t
python\tsystem\t2.7\tsystem\t\t
python\tsystem\t2.7\tsystem\tunladen-swallow\t
""")

        def test_02_hardlink_mediation(self):
                """Verify that package mediation works as expected for install,
                update, and uninstall with hardlinks.
                """

                self.image_create(self.rurl)

                def get_link_path(*parts):
                        return os.path.join(self.img_path(), *parts)

                def assert_target(link, target):
                        self.assertEqual(os.stat(link).st_ino,
                            os.stat(target).st_ino)

                def assert_exists(link):
                        self.assertTrue(os.path.exists(lpath))

                def assert_not_exists(link):
                        self.assertTrue(not os.path.exists(lpath))

                vi_path = get_link_path("usr", "bin", "vi")
                nvi_path = get_link_path("usr", "bin", "nvi")
                vim_path = get_link_path("usr", "bin", "vim")
                svr4_path = get_link_path("usr", "sunos", "bin", "edit")

                # Some installs are done with extra verbosity to ease in
                # debugging tests when they fail.
                self.pkg("install -vvv svr4-vi@1")
                self.pkg("mediator") # If tests fail, this is helpful.

                # Check that installed links point to svr4-vi and that
                # verify passes.
                assert_target(vi_path, svr4_path)
                self.pkg("verify")
                self.__assert_mediation_matches("""\
vi\tsystem\t\tsystem\tsvr4\t
""")

                # Install vim package and verify link still points to svr4-vi
                # and that verify passes.
                self.pkg("install -vvv vim@1")
                assert_target(vi_path, svr4_path)
                self.pkg("verify")
                self.__assert_mediation_matches("""\
vi\tsystem\t\tsystem\tsvr4\t
""")

                # Set mediation to use vim implementation of vi, and then
                # verify link points to that implementation.
                self.pkg("set-mediator -vvv -I vim vi")
                assert_target(vi_path, vim_path)
                self.pkg("verify")
                self.__assert_mediation_matches("""\
vi\tsystem\t\tlocal\tvim\t
""")

                # Remove vi link and then ensure verify fails, fix will fix it,
                # and then verify will succeed.
                portable.remove(vi_path)
                self.pkg("verify svr4-vi") # should pass, because of mediation
                self.pkg("verify", exit=1) # should fail, because link is gone
                self.pkg("fix")
                assert_target(vi_path, vim_path)
                self.pkg("verify") # should now pass

                # Unset mediation, verify mediation reverts to svr4-vi, then
                # uninstall svr4-vi and verify mediation reverts to vim.
                self.pkg("unset-mediator -vvv vi")
                assert_target(vi_path, svr4_path)
                self.__assert_mediation_matches("""\
vi\tsystem\t\tsystem\tsvr4\t
""")
                self.pkg("verify")
                self.pkg("uninstall -vvv svr4-vi")
                self.__assert_mediation_matches("""\
vi\tsystem\t\tsystem\tvim\t
""")
                self.pkg("verify")

                # Install nvi and verify mediation changes to nvi due to
                # mediator priority of vendor.
                self.pkg("install -vvv nvi@1")
                assert_target(vi_path, nvi_path)
                self.__assert_mediation_matches("""\
vi\tvendor\t\tvendor\tnvi\t
""")

                # Update to vim@2 and verify mediation changes to vim due to
                # mediator priority of site.
                self.pkg("update -vvv vim@2")
                assert_target(vi_path, vim_path)
                self.__assert_mediation_matches("""\
vi\tsite\t\tsite\tvim\t
""")

                # Install svr4-vi and verify mediation remains set to vim due to
                # mediator priority of site.
                self.pkg("install -vvv svr4-vi")
                assert_target(vi_path, vim_path)
                self.__assert_mediation_matches("""\
vi\tsite\t\tsite\tvim\t
""")

                # Uninstall all packages; then verify that a single package
                # containing multiple varianted, mediated hardlinks works as
                # expected.
                self.pkg("uninstall \*")

                foo_path = get_link_path("usr", "bin", "foo")
                foo_1_nd_path = get_link_path("usr", "bin", "foo-1-nd")
                foo_1_d_path = get_link_path("usr", "bin", "foo-1-d")
                foo_2_nd_path = get_link_path("usr", "bin", "foo-2-nd")
                foo_2_d_path = get_link_path("usr", "bin", "foo-2-d")

                # Install multi-ver-variant and verify version 2 non-debug is
                # selected.
                self.pkg("install -vvv multi-ver-variant")
                assert_target(foo_path, foo_2_nd_path)
                self.__assert_mediation_matches("""\
foo\tsystem\t2\tsystem\t\t
""")
                self.pkg("verify")

                # Set debug variant and verify version 2 debug is selected.
                self.pkg("change-variant -vvv debug.osnet=true")
                assert_target(foo_path, foo_2_d_path)
                self.__assert_mediation_matches("""\
foo\tsystem\t2\tsystem\t\t
""")
                self.pkg("verify")

                # Set mediator version to 1 and verify version 1 debug is
                # selected.
                self.pkg("set-mediator -vvv -V 1 foo")
                assert_target(foo_path, foo_1_d_path)
                self.__assert_mediation_matches("""\
foo\tlocal\t1\tsystem\t\t
""")
                self.pkg("verify")

                # Reset debug variant and verify version 1 non-debug is
                # selected.
                self.pkg("change-variant -vvv debug.osnet=false")
                self.pkg("verify")
                assert_target(foo_path, foo_1_nd_path)
                self.__assert_mediation_matches("""\
foo\tlocal\t1\tsystem\t\t
""")


if __name__ == "__main__":
        unittest.main()
