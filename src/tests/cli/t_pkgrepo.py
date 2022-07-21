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
# Copyright (c) 2010, 2022, Oracle and/or its affiliates.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

from pkg.server.query_parser import Query
import os
import pkg
import pkg.catalog
import pkg.manifest
import pkg.depotcontroller as dc
import pkg.fmri as fmri
import pkg.pkggzip
import pkg.misc as misc
import pkg.server.repository as sr
import pkg.client.api_errors as apx
import pkg.p5p
import shutil
import rapidjson as json
import six
import subprocess
import tempfile
import time
import unittest

try:
        import pkg.sha512_t
        sha512_supported = True
except ImportError:
        sha512_supported = False

class TestPkgRepo(pkg5unittest.SingleDepotTestCase):
        # Cleanup after every test.
        persistent_setup = False
        # Tests in this suite use the read only data directory.
        need_ro_data = True
        maxDiff = None

        tree10 = """
            open tree@1.0,5.11-0:20110804T203458Z
            add file tmp/empty mode=0555 owner=root group=bin path=/etc/empty
            add file tmp/truck1 mode=0444 owner=root group=bin path=/etc/trailer
            add set name=info.classification value=org.opensolaris.category.2008:System/Core
            add set name=pkg.summary value="Leafy SPARC package" variant.arch=sparc
            add set name=pkg.summary value="Leafy i386 package" variant.arch=i386
            add set name=variant.arch value=i386 value=sparc
            close
        """

        amber10 = """
            open amber@1.0,5.11-0:20110804T203458Z
            add depend fmri=pkg:/tree@1.0,5.11-0:20110804T203458Z type=require
            add set name=pkg.summary value="Millenia old resin"
            add set name=pkg.human-version value="1.0a"
            close
        """

        amber20 = """
            open amber@2.0,5.11-0:20110804T203458Z
            add depend fmri=pkg:/tree@1.0 type=require
            close
        """

        amber30 = """
            open amber@3.0,5.11-0:20110804T203458Z
            add set name=pkg.renamed value=true
            add depend fmri=pkg:/bronze@1.0 type=require
            close
        """

        amber35 = """
            open amber@3.5,5.11-0:20110804T203458Z
            add set name=pkg.legacy value=true
            close
        """

        amber40 = """
            open amber@4.0,5.11-0:20110804T203458Z
            add set name=pkg.obsolete value=true
            close
        """

        truck10 = """
            open truck@1.0,5.11-0:20110804T203458Z
            add file tmp/empty mode=0555 owner=root group=bin path=/etc/NOTICES/empty
            add file tmp/truck1 mode=0444 owner=root group=bin path=/etc/truck1
            add depend fmri=pkg:/amber@1.0 type=require
            close
        """

        trucknd10 = """
            open trucknd@1.0,5.11-0:20110804T203458Z
            add file tmp/empty mode=0555 owner=root group=bin path=/etc/NOTICES/empty
            add file tmp/truck1 mode=0444 owner=root group=bin path=/etc/truck1
            close
        """

        truck20 = """
            open truck@2.0,5.11-0:20110804T203458Z
            add file tmp/empty mode=0555 owner=root group=bin path=/etc/NOTICES/empty
            add file tmp/truck1 mode=0444 owner=root group=bin path=/etc/truck1
            add file tmp/truck2 mode=0444 owner=root group=bin path=/etc/truck2
            add depend fmri=pkg:/amber@2.0 type=require
            close
        """

        zoo10 = """
            open zoo@1.0,5.11-0:20110804T203458Z
            close
        """

        refuse10 = """
            open refuse@1.0,5.11-0:20110804T203458Z
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other
            add depend fmri=pkg:/amber@2.0 type=exclude
            close
        """

        illegaldep10 = """
            open illegaldep@1.0,5.11-0:20110804T203458Z
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other1
            close
        """

        wtinstallhold10 = """
            open wtinstallhold@1.0,5.11-0:20110804T203458Z
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other1
            add depend fmri=pkg:/amber@1.0 type=require
            close
        """

        wtinstallhold20 = """
            open wtinstallhold@2.0,5.11-0:20110804T203458Z
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other1
            add depend fmri=pkg:/amber@2.0 type=require
            close
        """

        withpub1_10 = """
            open pkg://test1/withpub1@1.0,5.11-0:20110804T203458Z
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other1
            add depend fmri=pkg:/amber@1.0 type=require
            close
        """

        withpub1_20 = """
            open pkg://test2/withpub1@2.0,5.11-0:20110804T203458Z
            add set name=pkg.depend.install-hold value=test
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other1
            add depend fmri=pkg:/amber@1.0 type=require
            close
        """

        withpub2_10 = """
            open pkg://test2/withpub2@1.0,5.11-0:20110804T203458Z
            add set name=pkg.depend.install-hold value=test
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other1
            add depend fmri=pkg:/amber@2.0 type=require
            close
        """

        incorp10 = """
            open incorp@1.0,5.11-0:20110804T203458Z
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other1
            close
        """

        require_any10 = """
            open requireany@1.0,5.11-0:20110804T203458Z
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other1
            add depend fmri=pkg:/amber@1.0 fmri=pkg:/amber@2.0 type=require-any
            close
        """

        depchecktag10 = """
            open depchecktag@1.0,5.11-0:20110804T203458Z
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other1
            add depend fmri=pkg:/depcheckdep@1.0 type=require
            close
        """

        depcheckdep10 = """
            open depcheckdep@1.0,5.11-0:20110804T203458Z
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other1
            close
        """

        optionalpkg10 = """
            open optionalpkg@1.0,5.11-0:20110804T203458Z
            add file tmp/other mode=0444 owner=root group=bin path=/etc/other1
            add depend fmri=pkg:/zoo@2.0 type=optional
            close
        """
        # These hashes should remain as SHA-1 until such time as we bump the
        # least-preferred hash for actions.
        fhashes = {
             "tmp/empty": "5f5fb715934e0fa2bfb5611fd941d33228027006",
             "tmp/truck1": "c9e257b659ace6c3fbc4d334f49326b3889fd109",
             "tmp/truck2": "c07fd27b5b57f8131f42e5f2c719a469d9fc71c5",
        }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(["tmp/empty", "tmp/truck1", "tmp/truck2",
                    "tmp/other"])

        def test_00_base(self):
                """Verify pkgrepo handles basic option and subcommand parsing
                as expected.
                """

                # --help, -? should exit with 0.
                self.pkgrepo("--help", exit=0)
                self.pkgrepo("'-?'", exit=0)

                # unknown options should exit with 2.
                self.pkgrepo("-U", exit=2)
                self.pkgrepo("--unknown", exit=2)

                # unknown subcommands should exit with 2.
                self.pkgrepo("unknown_subcmd", exit=2)

                # no subcommand should exit with 2.
                self.pkgrepo("", exit=2)

                # global option with no subcommand should exit with 2.
                self.pkgrepo("-s {0}".format(self.test_root), exit=2)

                # Verify an invalid URI causes an exit 2.
                for baduri in ("file://not/valid", "http://not@$$_-^valid"):
                        self.pkgrepo("info -s {0}".format(baduri), exit=2)

        def test_01_create(self):
                """Verify pkgrepo create works as expected."""

                # Verify create without a destination exits.
                self.pkgrepo("create", exit=2)

                # Verify create with an invalid URI as an operand exits with 2.
                for baduri in ("file://not/valid", "http://not@$$_-^valid"):
                        self.pkgrepo("create {0}".format(baduri), exit=2)

                # Verify create works whether -s is used to supply the location
                # of the new repository or it is passed as an operand.  Also
                # verify that either a path or URI can be used to provide the
                # repository's location.
                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                repo_uri = self.dc.get_repo_url()

                # Specify using global option and path.
                self.pkgrepo("create -s {0}".format(repo_path))
                # This will fail if a repository wasn't created.
                self.dc.get_repo()
                shutil.rmtree(repo_path)

                # Specify using operand and URI.
                self.pkgrepo("create {0}".format(repo_uri))
                # This will fail if a repository wasn't created.
                self.get_repo(repo_path)
                shutil.rmtree(repo_path)

                # Verify create works for an empty, pre-existing directory.
                os.mkdir(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                # This will fail if a repository wasn't created.
                self.get_repo(repo_path)

                # Verify create fails for a non-empty, pre-existing directory.
                self.pkgrepo("create {0}".format(repo_path), exit=1)

        def test_02_get_set_property(self):
                """Verify pkgrepo get and set works as expected."""

                # Verify command without a repository exits.
                self.pkgrepo("get", exit=2)

                # Create a repository (a version 3 one is needed for these
                # tests).
                repo_path = self.dc.get_repodir()
                repo_uri = self.dc.get_repo_url()
                depot_uri = self.dc.get_depot_url()
                shutil.rmtree(repo_path)
                self.assertTrue(not os.path.exists(repo_path))
                self.pkgrepo("create -s {0} --version=3".format(repo_path))

                # Verify get handles unknown properties gracefully.
                self.pkgrepo("get -s {0} repository/unknown".format(repo_uri), exit=1)

                # Verify get returns partial failure if only some
                # properties cannot be found.
                self.pkgrepo("get -s {0} repository/origins "
                    "repository/unknown".format(repo_uri), exit=3)

                # Verify full default output for both network and file case.
                self.dc.start()
                for uri in (repo_uri, depot_uri):
                        self.pkgrepo("get -s {0}".format(uri))
                        expected = """\
SECTION    PROPERTY         VALUE
feed       description      ""
feed       icon             web/_themes/pkg-block-icon.png
feed       id               ""
feed       logo             web/_themes/pkg-block-logo.png
feed       name             package\ repository\ feed
feed       window           24
publisher  alias            ""
publisher  prefix           test
repository collection_type  core
repository description      ""
repository detailed_url     ""
repository legal_uris       ()
repository maintainer       ""
repository maintainer_url   ""
repository mirrors          ()
repository name             package\ repository
repository origins          ()
repository refresh_seconds  14400
repository registration_uri ""
repository related_uris     ()
repository version          3
"""
                        self.assertEqualDiff(expected, self.output)
                self.dc.stop()

                # Verify full tsv output.
                self.pkgrepo("get -s {0} -Ftsv".format(repo_uri))
                expected = """\
SECTION\tPROPERTY\tVALUE
feed\tdescription\t""
feed\ticon\tweb/_themes/pkg-block-icon.png
feed\tid\t""
feed\tlogo\tweb/_themes/pkg-block-logo.png
feed\tname\tpackage\ repository\ feed
feed\twindow\t24
publisher\talias\t""
publisher\tprefix\ttest
repository\tcollection_type\tcore
repository\tdescription\t""
repository\tdetailed_url\t""
repository\tlegal_uris\t()
repository\tmaintainer\t""
repository\tmaintainer_url\t""
repository\tmirrors\t()
repository\tname\tpackage\ repository
repository\torigins\t()
repository\trefresh_seconds\t14400
repository\tregistration_uri\t""
repository\trelated_uris\t()
repository\tversion\t3
"""
                self.assertEqualDiff(expected, self.output)

                # Verify that -H omits headers for full output.
                self.pkgrepo("get -s {0} -H".format(repo_uri))
                self.assertTrue(self.output.find("SECTION") == -1)

                # Verify specific get default output and that
                # -H omits headers for specific get output.
                self.pkgrepo("get -s {0} publisher/prefix".format(
                    repo_uri))
                expected = """\
SECTION    PROPERTY         VALUE
publisher  prefix           test
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("get -s {0} -H publisher/prefix "
                    "repository/origins".format(repo_uri))
                expected = """\
publisher  prefix           test
repository origins          ()
"""
                self.assertEqualDiff(expected, self.output)

                # Verify specific get tsv output.
                self.pkgrepo("get -s {0} -F tsv publisher/prefix".format(
                    repo_uri))
                expected = """\
SECTION\tPROPERTY\tVALUE
publisher\tprefix\ttest
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("get -s {0} -HF tsv publisher/prefix "
                    "repository/origins".format(repo_uri))
                expected = """\
publisher\tprefix\ttest
repository\torigins\t()
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set fails if no property is provided.
                self.pkgrepo("set -s {0}".format(repo_uri), exit=2)

                # Verify set gracefully handles bad property values.
                self.pkgrepo("set -s {0} publisher/prefix=_invalid".format(repo_uri),
                    exit=1)

                # Verify set can set single value properties.
                self.pkgrepo("set -s {0} publisher/prefix=opensolaris.org".format(
                    repo_uri))
                self.pkgrepo("get -s {0} -HF tsv publisher/prefix".format(repo_uri))
                expected = """\
publisher\tprefix\topensolaris.org
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set can set multi-value properties.
                self.pkgrepo("set -s {0} "
                    "'repository/origins=(http://pkg.opensolaris.org/dev "
                    "http://pkg-eu-2.opensolaris.org/dev)'".format(repo_uri))
                self.pkgrepo("get -s {0} -HF tsv repository/origins".format(repo_uri))
                expected = """\
repository\torigins\t(http://pkg.opensolaris.org/dev http://pkg-eu-2.opensolaris.org/dev)
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set can set unknown properties.
                self.pkgrepo("set -s {0} 'foo/bar=value'".format(repo_uri))
                self.pkgrepo("get -s {0} -HF tsv foo/bar".format(repo_uri))
                expected = """\
foo\tbar\tvalue
"""
                self.assertEqualDiff(expected, self.output)

                # Create a repository (a version 3 one is needed for this
                # test).
                repo_path = self.dc.get_repodir()
                repo_uri = self.dc.get_repo_url()
                depot_uri = self.dc.get_depot_url()
                shutil.rmtree(repo_path)
                self.assertTrue(not os.path.exists(repo_path))
                self.pkgrepo("create -s {0} --version=3".format(repo_path))
                self.pkgrepo("set -s {0} publisher/prefix=test".format(repo_path))

                # Verify setting publisher properties fails for version 3
                # repositories.
                self.pkgrepo("set -s {0} -p all "
                    "repository/origins=http://localhost".format(repo_uri), exit=1)

                # Create version 4 repository.
                shutil.rmtree(repo_path)
                self.assertTrue(not os.path.exists(repo_path))
                self.create_repo(repo_path)

                # Verify get handles unknown publishers gracefully.
                self.pkgrepo("get -s {0} -p test repository/origins".format(repo_uri),
                    exit=1)

                # Add a publisher by setting properties for one that doesn't
                # exist yet.
                self.pkgrepo("set -s {0} -p test "
                    "repository/name='package repository' "
                    "repository/refresh-seconds=7200".format(
                    repo_uri))

                # Verify get handles unknown properties gracefully.
                self.pkgrepo("get -s {0} -p test repository/unknown".format(repo_uri),
                    exit=1)

                # Verify get returns partial failure if only some properties
                # cannot be found.
                self.pkgrepo("get -s {0} -p all repository/origins "
                    "repository/unknown".format(repo_uri), exit=3)

                # Verify full default output for both network and file case.
                self.dc.start()
                for uri in (repo_uri, depot_uri):
                        self.pkgrepo("get -s {0} -p all".format(uri))
                        expected = """\
PUBLISHER SECTION    PROPERTY         VALUE
test      publisher  alias            
test      publisher  prefix           test
test      repository collection-type  core
test      repository description      
test      repository legal-uris       ()
test      repository mirrors          ()
test      repository name             package\ repository
test      repository origins          ()
test      repository refresh-seconds  7200
test      repository registration-uri ""
test      repository related-uris     ()
"""
                        self.assertEqualDiff(expected, self.output)
                self.dc.stop()

                # Verify full tsv output.
                self.pkgrepo("get -s {0} -p all -Ftsv".format(repo_uri))
                expected = """\
PUBLISHER\tSECTION\tPROPERTY\tVALUE
test\tpublisher\talias\t
test\tpublisher\tprefix\ttest
test\trepository\tcollection-type\tcore
test\trepository\tdescription\t
test\trepository\tlegal-uris\t()
test\trepository\tmirrors\t()
test\trepository\tname\tpackage\ repository
test\trepository\torigins\t()
test\trepository\trefresh-seconds\t7200
test\trepository\tregistration-uri\t""
test\trepository\trelated-uris\t()
"""
                self.assertEqualDiff(expected, self.output)

                # Verify that -H omits headers for full output.
                self.pkgrepo("get -s {0} -p all -H".format(repo_uri))
                self.assertTrue(self.output.find("SECTION") == -1)

                # Verify specific get default output and that
                # -H omits headers for specific get output.
                self.pkgrepo("get -s {0} -p all publisher/prefix".format(
                    repo_uri))
                expected = """\
PUBLISHER SECTION    PROPERTY         VALUE
test      publisher  prefix           test
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("get -s {0} -p all -H publisher/prefix "
                    "repository/origins".format(repo_uri))
                expected = """\
test      publisher  prefix           test
test      repository origins          ()
"""
                self.assertEqualDiff(expected, self.output)

                # Verify specific get tsv output.
                self.pkgrepo("get -s {0} -p all -F tsv publisher/prefix".format(
                    repo_uri))
                expected = """\
PUBLISHER\tSECTION\tPROPERTY\tVALUE
test\tpublisher\tprefix\ttest
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("get -s {0} -HF tsv -p all publisher/prefix "
                    "repository/origins".format(repo_uri))
                expected = """\
test\tpublisher\tprefix\ttest
test\trepository\torigins\t()
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set fails if no property is provided.
                self.pkgrepo("set -s {0} -p test".format(repo_uri), exit=2)

                # Verify set gracefully handles bad property values and
                # properties that can't be set.
                self.pkgrepo("set -s {0} -p test publisher/alias=_invalid".format(
                    repo_uri), exit=1)
                self.pkgrepo("set -s {0} -p test publisher/prefix=_invalid".format(
                    repo_uri), exit=2)

                # Verify set can set single value properties.
                self.pkgrepo("set -s {0} -p all publisher/alias=test1".format(
                    repo_uri))
                self.pkgrepo("get -s {0} -p all -HF tsv publisher/alias "
                    "publisher/prefix".format(repo_uri))
                expected = """\
test\tpublisher\talias\ttest1
test\tpublisher\tprefix\ttest
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set can set multi-value properties.
                self.pkgrepo("set -s {0} -p all "
                    "'repository/origins=(http://pkg.opensolaris.org/dev "
                    "http://pkg-eu-2.opensolaris.org/dev)'".format(repo_uri))
                self.pkgrepo("get -s {0} -p all -HF tsv repository/origins".format(
                    repo_uri))
                expected = """\
test\trepository\torigins\t(http://pkg-eu-2.opensolaris.org/dev/ http://pkg.opensolaris.org/dev/)
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set can not set unknown properties.
                self.pkgrepo("set -s {0} -p all 'foo/bar=value'".format(repo_uri),
                    exit=2)

                # Add another publisher by setting a property for it.
                self.pkgrepo("set -p test2 -s {0} publisher/alias=''".format(repo_uri))

                # Verify get returns properties for multiple publishers.
                expected = """\
test\tpublisher\talias\ttest1
test\tpublisher\tprefix\ttest
test\trepository\tcollection-type\tcore
test\trepository\tdescription\t
test\trepository\tlegal-uris\t()
test\trepository\tmirrors\t()
test\trepository\tname\tpackage\ repository
test\trepository\torigins\t(http://pkg-eu-2.opensolaris.org/dev/ http://pkg.opensolaris.org/dev/)
test\trepository\trefresh-seconds\t7200
test\trepository\tregistration-uri\t""
test\trepository\trelated-uris\t()
test2\tpublisher\talias\t""
test2\tpublisher\tprefix\ttest2
test2\trepository\tcollection-type\tcore
test2\trepository\tdescription\t""
test2\trepository\tlegal-uris\t()
test2\trepository\tmirrors\t()
test2\trepository\tname\t""
test2\trepository\torigins\t()
test2\trepository\trefresh-seconds\t""
test2\trepository\tregistration-uri\t""
test2\trepository\trelated-uris\t()
"""
                self.pkgrepo("get -s {0} -p all -HFtsv".format(repo_uri))
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("get -s {0} -p test -p test2 -HFtsv".format(repo_uri))
                self.assertEqualDiff(expected, self.output)

                # Verify get can list multiple specific properties for
                # multiple specific publishers correctly.
                expected = """\
test\tpublisher\talias\ttest1
test2\tpublisher\talias\t""
"""
                self.pkgrepo("get -s {0} -HFtsv -p test -p test2 "
                    "publisher/alias".format(repo_uri))
                self.assertEqualDiff(expected, self.output)

                # Verify get has correct output even when some publishers
                # can't be found (and exits with partial failure).
                expected = """\
test\tpublisher\talias\ttest1
test\tpublisher\tprefix\ttest
test\trepository\tcollection-type\tcore
test\trepository\tdescription\t
test\trepository\tlegal-uris\t()
test\trepository\tmirrors\t()
test\trepository\tname\tpackage\ repository
test\trepository\torigins\t(http://pkg-eu-2.opensolaris.org/dev/ http://pkg.opensolaris.org/dev/)
test\trepository\trefresh-seconds\t7200
test\trepository\tregistration-uri\t""
test\trepository\trelated-uris\t()
"""
                self.pkgrepo("get -s {0} -p test -p bogus -HFtsv".format(repo_uri),
                    exit=3)
                self.assertEqualDiff(expected, self.output)

                # Verify set can set multiple properties for all or specific
                # publishers when multiple publishers are known.
                self.pkgrepo("set -s {0} -p all "
                    "repository/description='Support Repository'".format(repo_uri))
                expected = """\
test\trepository\tdescription\tSupport\\ Repository
test2\trepository\tdescription\tSupport\\ Repository
"""
                self.pkgrepo("get -s {0} -HFtsv -p all repository/description".format(
                    repo_uri))
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("set -s {0} -p test2 "
                    "repository/description='2nd Support Repository'".format(
                        repo_uri))
                expected = """\
test\trepository\tdescription\tSupport\\ Repository
test2\trepository\tdescription\t2nd\\ Support\\ Repository
"""
                self.pkgrepo("get -s {0} -HFtsv -p all repository/description".format(
                    repo_uri))
                self.assertEqualDiff(expected, self.output)

        def __test_info(self, repo_path, repo_uri):
                """Private function to verify publisher subcommand behaviour."""

                # Verify subcommand behaviour for empty repository and -H
                # functionality.
                self.pkgrepo("info -s {0}".format(repo_uri))
                expected = """\
PUBLISHER PACKAGES STATUS           UPDATED
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("info -s {0} -H".format(repo_uri))
                expected = """\
"""
                self.assertEqualDiff(expected, self.output)

                # Set a default publisher.
                self.pkgrepo("set -s {0} publisher/prefix=test".format(repo_path))

                # If a depot is running, this will trigger a reload of the
                # configuration data.
                self.dc.refresh()

                # Publish some packages.
                self.pkgsend_bulk(repo_uri, (self.tree10, self.amber10,
                    self.amber20, self.truck10, self.truck20))

                # Verify info handles unknown publishers gracefully.
                self.pkgrepo("info -s {0} -p unknown".format(repo_uri), exit=1)

                # Verify info returns partial failure if only some publishers
                # cannot be found.
                self.pkgrepo("info -s {0} -p test -p unknown".format(repo_uri), exit=3)

                # Verify full default output.
                repo = self.get_repo(repo_path)
                self.pkgrepo("info -s {0} -H".format(repo_uri))
                cat = repo.get_catalog("test")
                cat_lm = cat.last_modified.isoformat()
                expected = """\
test      3        online           {0}Z
""".format(cat_lm)
                self.assertEqualDiff(expected, self.output)

                # Verify full tsv output.
                self.pkgrepo("info -s {0} -HF tsv".format(repo_uri))
                expected = """\
test\t3\tonline\t{0}Z
""".format(cat_lm)
                self.assertEqualDiff(expected, self.output)

                # Verify info specific publisher default output.
                self.pkgrepo("info -s {0} -H -p test".format(repo_uri))
                expected = """\
test      3        online           {0}Z
""".format(cat_lm)
                self.assertEqualDiff(expected, self.output)

                # Verify info specific publisher tsv output.
                self.pkgrepo("info -s {0} -HF tsv -p test".format(repo_uri))
                expected = """\
test\t3\tonline\t{0}Z
""".format(cat_lm)
                self.assertEqualDiff(expected, self.output)

        def test_03_info(self):
                """Verify pkgrepo info works as expected."""

                # Verify command without a repository exits.
                self.pkgrepo("info", exit=2)

                # Create a repository, verify file-based repository access,
                # and then discard the repository.
                repo_path = self.dc.get_repodir()
                repo_uri = self.dc.get_repo_url()
                shutil.rmtree(repo_path)
                self.create_repo(repo_path)
                self.__test_info(repo_path, repo_uri)
                shutil.rmtree(repo_path)

                # Create a repository.
                repo_path = self.dc.get_repodir()
                self.create_repo(repo_path)
                # Set a default publisher.
                self.pkgrepo("set -s {0} publisher/prefix=test".format(repo_path))
                plist = self.pkgsend_bulk(self.rurl, (self. tree10,
                    self.amber10, self.amber20))
                tree10 = fmri.PkgFmri(plist[0])
                amber10 = fmri.PkgFmri(plist[1])
                amber20 = fmri.PkgFmri(plist[2])

                # Add a new publisher and set it as default.
                self.pkgrepo("add-publisher -s {0} test1".format(repo_path))
                self.pkgrepo("set -s {0} publisher/prefix=test1".format(
                    repo_uri))
                repo = self.get_repo(self.dc.get_repodir())
                plist = self.pkgsend_bulk(self.rurl, self.zoo10)
                zoo10 = fmri.PkgFmri(plist[0])

                # Prep the archive.
                arc_path = os.path.join(self.test_root,
                    "test_info_empty_archive.p5p")
                arc = pkg.p5p.Archive(arc_path, mode="w")
                arc.close()

                # pkg info on empty archive will not print anything.
                self.pkgrepo("info -s {0} -HF tsv".format(arc_path))
                self.assertEqualDiff("", self.output)

                # Archive with one publisher and 2 packages. One of the
                # package has two versions
                arc_path = os.path.join(self.test_root,
                    "test_info_1pub_archive.p5p")
                arc = pkg.p5p.Archive(arc_path, mode="w")
                # Create an archive with packages.
                arc.add_repo_package(tree10, repo)
                arc.add_repo_package(amber10, repo)
                arc.add_repo_package(amber20, repo)
                arc.close()
                self.pkgrepo("info -s {0} -HF tsv".format(arc_path))
                expected="""\
test\t2\tonline\t2011-08-04T20:34:58Z
"""
                self.assertEqualDiff(expected, self.output)

                # Archive with two publishers.
                arc_path = os.path.join(self.test_root,
                    "test_info_2pub_archive.p5p")
                arc = pkg.p5p.Archive(arc_path, mode="w")
                arc.add_repo_package(tree10, repo)
                arc.add_repo_package(amber10, repo)
                arc.add_repo_package(amber20, repo)
                arc.add_repo_package(zoo10, repo)
                arc.close()
                self.pkgrepo("info -s {0} -HF tsv".format(arc_path))
                expected="""\
test\t2\tonline\t2011-08-04T20:34:58Z
test1\t1\tonline\t2011-08-04T20:34:58Z
"""
                self.assertEqualDiff(expected, self.output)
                shutil.rmtree(repo_path)

                # Create a repository and verify http-based repository access.
                self.assertTrue(not os.path.exists(repo_path))
                self.create_repo(repo_path)
                self.dc.clear_property("publisher", "prefix")
                self.dc.start()
                repo_uri = self.dc.get_depot_url()
                self.__test_info(repo_path, repo_uri)
                self.dc.stop()

        def __test_rebuild(self, repo_path, repo_uri):
                """Private function to verify rebuild subcommand behaviour."""

                #
                # Verify rebuild works for an empty repository.
                #
                repo = self.get_repo(repo_path)
                lm = repo.get_catalog("test").last_modified.isoformat()
                self.pkgrepo("rebuild -s {0}".format(repo_uri))
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path)
                nlm = repo.get_catalog("test").last_modified.isoformat()
                self.assertNotEqual(lm, nlm)

                #
                # Verify rebuild --no-index works for an empty repository.
                #
                lm = repo.get_catalog("test").last_modified.isoformat()
                self.pkgrepo("rebuild -s {0} --no-index".format(repo_uri))
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path)
                nlm = repo.get_catalog("test").last_modified.isoformat()
                self.assertNotEqual(lm, nlm)

                #
                # Verify rebuild --no-catalog works for an empty repository,
                # and that the catalog itself does not change.
                #
                lm = repo.get_catalog("test").last_modified.isoformat()
                self.pkgrepo("rebuild -s {0} --no-catalog".format(repo_uri))
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path)
                nlm = repo.get_catalog("test").last_modified.isoformat()
                self.assertEqual(lm, nlm)

                #
                # Publish some packages and verify they are known afterward.
                #
                plist = self.pkgsend_bulk(repo_uri, (self.amber10, self.tree10))
                repo = self.get_repo(repo_path)
                self.assertEqual(list(
                    str(f) for f in repo.get_catalog("test").fmris(ordered=True)
                ), plist)

                #
                # Verify that rebuild --no-catalog works for a repository with
                # packages.
                #

                # Now rebuild and verify packages are still known and catalog
                # remains unchanged.
                lm = repo.get_catalog("test").last_modified.isoformat()
                self.pkgrepo("rebuild -s {0} --no-catalog".format(repo_uri))
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path)
                self.assertEqual(plist,
                    list(str(f) for f in repo.get_catalog("test").fmris(
                    ordered=True)))
                nlm = repo.get_catalog("test").last_modified.isoformat()
                self.assertEqual(lm, nlm)

                # Destroy the catalog.
                repo.get_catalog("test").destroy()

                # Reload the repository object and verify no packages are known.
                repo = self.get_repo(repo_path)
                self.assertEqual(set(), repo.get_catalog("test").names())

                # Now rebuild and verify packages are still unknown and catalog
                # remains unchanged.
                lm = repo.get_catalog("test").last_modified.isoformat()
                self.pkgrepo("rebuild -s {0} --no-catalog".format(repo_uri))
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path)
                self.assertEqual(set(), repo.get_catalog("test").names())
                nlm = repo.get_catalog("test").last_modified.isoformat()
                self.assertEqual(lm, nlm)

                #
                # Verify rebuild will find all the packages again and that they
                # can be searched for.
                #

                # Destroy the catalog.
                repo.get_catalog("test").destroy()

                # Reload the repository object and verify no packages are known.
                repo = self.get_repo(repo_path)
                self.assertEqual(set(), repo.get_catalog("test").names())

                # Now rebuild and verify packages are known and can be searched
                # for.
                self.pkgrepo("rebuild -s {0}".format(repo_uri))
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path)
                self.assertEqual(plist,
                    list(str(f) for f in repo.get_catalog("test").fmris(
                    ordered=True)))

                query = Query("tree", False, Query.RETURN_PACKAGES, None, None)
                result = list(e for e in [r for r in repo.search([query])][0])
                fmris = [fmri.PkgFmri(f).get_fmri(anarchy=True) for f in plist]
                expected = [
                    [1, 2, [fmris[0], 'require',
                        'depend fmri=pkg:/tree@1.0 type=require\n']],
                    [1, 2, [fmris[1], 'test/tree',
                        'set name=pkg.fmri value={0}\n'.format(plist[1])]]
                ]

                # To ensure comparison works, the actual FMRI object in the
                # result has to be stringified.
                result = [list(e) for e in expected]
                for e in result:
                        e[2] = list(e[2])
                        e[2][0] = str(e[2][0])
                self.assertEqualDiff(expected, result)

                #
                # Now rebuild again, but with --no-index, and verify that
                # search data is gone.
                #

                # Destroy the catalog only (to verify that rebuild destroys
                # the index).
                repo.get_catalog("test").destroy()

                # Reload the repository object and verify no packages are known.
                repo = self.get_repo(repo_path)
                self.assertEqual(set(), repo.get_catalog("test").names())

                self.pkgrepo("rebuild -s {0} --no-index".format(repo_uri))
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqual(plist,
                    list(str(f) for f in repo.get_catalog("test").fmris(
                    ordered=True)))

                query = Query("tree", False, Query.RETURN_PACKAGES, None, None)
                try:
                        result = list(
                            e for e in [
                                r for r in repo.search([query])
                            ][0]
                        )
                except Exception as e:
                        self.debug("query exception: {0}".format(e))
                        self.assertTrue(isinstance(e,
                            sr.RepositorySearchUnavailableError))
                else:
                        raise RuntimeError("Expected "
                            "RepositorySearchUnavailableError")

        def test_04_rebuild(self):
                """Verify pkgrepo rebuild works as expected."""

                # Verify rebuild without a target exits.
                self.pkgrepo("rebuild", exit=2)

                # Create a repository, verify file-based repository access,
                # and then discard the repository.
                repo_path = self.dc.get_repodir()
                repo_uri = self.dc.get_repo_url()
                self.__test_rebuild(repo_path, repo_uri)
                shutil.rmtree(repo_path)

                # Create a repository, add a publisher, remove its catalog,
                # and then verify rebuild still works.
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("add-publisher -s {0} test".format(repo_path))
                repo = self.get_repo(repo_path, read_only=True)
                cat = repo.get_catalog(pub="test")
                cat.destroy()
                self.pkgrepo("rebuild -s {0}".format(repo_path))
                shutil.rmtree(repo_path)

                # Create a repository and verify network-based repository
                # access.
                self.assertTrue(not os.path.exists(repo_path))
                self.create_repo(repo_path, properties={ "publisher": {
                    "prefix": "test" } })
                self.dc.clear_property("publisher", "prefix")
                self.dc.start()
                repo_uri = self.dc.get_depot_url()
                self.__test_rebuild(repo_path, repo_uri)

                # Verify rebuild only rebuilds package data for specified
                # publisher in the case that the repository contains package
                # data for multiple publishers.
                self.pkgsend_bulk(repo_uri, """
                    open pkg://test2/foo@1.0
                    close
                    """)

                repo = self.get_repo(repo_path, read_only=True)
                cat = repo.get_catalog(pub="test")
                test_cts = cat.created
                cat = repo.get_catalog(pub="test2")
                test2_cts = cat.created

                self.pkgrepo("rebuild -s {0} -p test".format(repo_uri))
                self.wait_repo(repo_path)

                # Now compare creation timestamps of each publisher's
                # catalog to verify only test's catalog was rebuilt.
                repo = self.get_repo(repo_path, read_only=True)
                cat = repo.get_catalog(pub="test")
                self.assertNotEqual(cat.created, test_cts)
                test_cts = cat.created
                cat = repo.get_catalog(pub="test2")
                self.assertEqual(cat.created, test2_cts)
                test2_cts = cat.created

                # Verify rebuild without specifying a publisher
                # will rebuild the catalogs for all publishers.
                self.pkgrepo("rebuild -s {0}".format(repo_uri))
                self.wait_repo(repo_path)
                self.dc.stop()

                # Now compare creation timestamps of each publisher's
                # catalog to verify all catalogs were rebuilt.
                repo = self.get_repo(repo_path, read_only=True)
                cat = repo.get_catalog(pub="test")
                self.assertNotEqual(cat.created, test_cts)
                cat = repo.get_catalog(pub="test2")
                self.assertNotEqual(cat.created, test2_cts)
                shutil.rmtree(repo_path)

                # Now create a repository, publish a package, and deposit a
                # junk file in the manifest directory.
                self.assertTrue(not os.path.exists(repo_path))
                self.create_repo(repo_path)
                pfmri = self.pkgsend_bulk(repo_path, """
                    open pkg://test/foo@1.0
                    close
                    """)[0]
                repo = self.get_repo(repo_path, read_only=True)
                mdir = os.path.dirname(repo.manifest(pfmri))
                jpath = os.path.join(mdir, "junk")
                with open(jpath, "w") as f:
                        f.write("random junk")
                self.assertTrue(os.path.exists(jpath))

                # Verify rebuild succeeds.
                self.pkgrepo("rebuild -s {0}".format(repo_path))

                # Verify junk file is still there.
                self.assertTrue(os.path.exists(jpath))

                # Verify expected package is still known.
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqualDiff([pfmri],
                    [str(f) for f in repo.get_catalog("test").fmris()])

                # Now verify that 'pkgrepo rebuild' will still work
                # (filesystem-based repos only) if the catalog is corrupted.
                cat = repo.get_catalog("test")
                part = cat.get_part("catalog.attrs")
                apath = part.pathname

                with open(apath, "r+b") as cfile:
                        cfile.truncate(4)
                        cfile.close()

                # Should fail, since catalog is corrupt.
                self.pkgrepo("refresh -s {0}".format(repo_path), exit=1)

                # Should fail, because --no-catalog was specified.
                self.pkgrepo("rebuild -s {0} --no-catalog".format(repo_path), exit=1)

                # Should succeed.
                self.pkgrepo("rebuild -s {0} --no-index".format(repo_path))

                # Should succeed now that catalog is valid.
                self.pkgrepo("refresh -s {0}".format(repo_path))

                # Verify expected package is still known.
                self.assertEqualDiff([pfmri],
                    [str(f) for f in repo.get_catalog("test").fmris()])

        def __test_refresh(self, repo_path, repo_uri):
                """Private function to verify refresh subcommand behaviour."""

                # Verify refresh doesn't fail for an empty repository.
                self.pkgrepo("refresh -s {0}".format(repo_path))
                self.wait_repo(repo_path)

                # Publish some packages.
                plist = self.pkgsend_bulk(repo_uri, (self.amber10, self.tree10))

                #
                # Verify refresh will find new packages and that they can be
                # searched for.
                #

                # Reload the repository object and verify published packages
                # are known.
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqual(plist,
                    list(str(f) for f in repo.get_catalog("test").fmris(
                    ordered=True)))

                self.pkgrepo("refresh -s {0}".format(repo_uri))
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqual(plist,
                    list(str(f) for f in repo.get_catalog("test").fmris(
                    ordered=True)))

                query = Query("tree", False, Query.RETURN_PACKAGES, None, None)
                result = list(e for e in [r for r in repo.search([query])][0])
                fmris = [fmri.PkgFmri(f).get_fmri(anarchy=True) for f in plist]
                expected = [
                    [1, 2, [fmris[0], 'require',
                        'depend fmri=pkg:/tree@1.0 type=require\n']],
                    [1, 2, [fmris[1], 'test/tree',
                        'set name=pkg.fmri value={0}\n'.format(plist[1])]]
                ]

                # To ensure comparison works, the actual FMRI object in the
                # result has to be stringified.
                result = [list(e) for e in expected]
                for e in result:
                        e[2] = list(e[2])
                        e[2][0] = str(e[2][0])
                self.assertEqualDiff(expected, result)

                #
                # Now publish a new package and refresh again with --no-index,
                # and verify that search data doesn't include the new package.
                #
                plist.extend(self.pkgsend_bulk(repo_uri, self.truck10))
                fmris.append(fmri.PkgFmri(plist[-1]).get_fmri(anarchy=True))

                self.pkgrepo("refresh -s {0} --no-index".format(repo_uri))
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqualDiff(plist,
                    list(str(f) for f in repo.get_catalog("test").fmris(
                    ordered=True)))

                query = Query("truck", False, Query.RETURN_PACKAGES, None, None)
                result = list(e for e in [r for r in repo.search([query])][0])
                self.assertEqualDiff([], result)

                #
                # Now publish a new package and refresh again with --no-catalog,
                # the package above should now be returned by search, but the
                # just published package shouldn't be found in the catalog or
                # search.
                #
                plist.extend(self.pkgsend_bulk(repo_uri, self.zoo10,
                    no_catalog=True))
                fmris.append(fmri.PkgFmri(plist[-1]).get_fmri(anarchy=True))

                self.pkgrepo("refresh -s {0} --no-catalog".format(repo_uri))
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqual(plist[:-1], list(
                    str(f) for f in repo.get_catalog("test").fmris(ordered=True)
                ))

                query = Query("truck", False, Query.RETURN_PACKAGES, None, None)
                result = list(e for e in [r for r in repo.search([query])][0])
                fmris = [fmri.PkgFmri(f).get_fmri(anarchy=True) for f in plist]
                expected = [
                ]

                query = Query("zoo", False, Query.RETURN_PACKAGES, None, None)
                result = list(e for e in [r for r in repo.search([query])][0])
                self.assertEqualDiff([], result)

                # Store time all packages in catalog were added.
                cat = repo.get_catalog("test")
                uname = [part for part in cat.updates][0]
                ulog = pkg.catalog.CatalogUpdate(uname, meta_root=cat.meta_root)
                expected = set()
                for pfmri, op_type, op_time, metadata in ulog.updates():
                        expected.add((str(pfmri), op_time))

                # Finally, run refresh once more and verify that all packages
                # are now visible in the catalog and that refresh was
                # incremental.
                self.pkgrepo("refresh -s {0}".format(repo_uri))
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqual(plist, list(
                    str(f) for f in repo.get_catalog("test").fmris(ordered=True)
                ))

                # Get time all packages in catalog were added.
                cat = repo.get_catalog("test")
                uname = [part for part in cat.updates][0]
                ulog = pkg.catalog.CatalogUpdate(uname, meta_root=cat.meta_root)
                returned = set()
                for pfmri, op_type, op_time, metadata in ulog.updates():
                        if pfmri.pkg_name == "zoo":
                                continue
                        returned.add((str(pfmri), op_time))

                # Entries for all packages (except zoo) should have the same
                # operation timestamp (when they were added) before the pkgrepo
                # refresh in update log.
                self.assertEqualDiff(expected, returned)

        def test_05_refresh(self):
                """Verify pkgrepo refresh works as expected."""

                # Verify create without a destination exits.
                self.pkgrepo("refresh", exit=2)

                # Create a repository, verify file-based repository access,
                # and then discard the repository.
                repo_path = self.dc.get_repodir()
                repo_uri = self.dc.get_repo_url()
                self.__test_refresh(repo_path, repo_uri)
                shutil.rmtree(repo_path)

                # Create a repository, add a publisher, remove its catalog,
                # and then verify refresh still works.
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("add-publisher -s {0} test".format(repo_path))
                repo = self.get_repo(repo_path, read_only=True)
                cat = repo.get_catalog(pub="test")
                cat.destroy()
                self.pkgrepo("refresh -s {0}".format(repo_path))
                shutil.rmtree(repo_path)

                # Create a repository and verify network-based repository
                # access.
                self.assertTrue(not os.path.exists(repo_path))
                self.create_repo(repo_path, properties={ "publisher": {
                    "prefix": "test" } })
                self.dc.clear_property("publisher", "prefix")
                self.dc.start()
                repo_uri = self.dc.get_depot_url()
                self.__test_refresh(repo_path, repo_uri)

                # Verify refresh only refreshes package data for specified
                # publisher in the case that the repository contains package
                # data for multiple publishers.

                # This is needed to ensure test2 exists as a publisher before
                # the package ever is created.
                self.pkgrepo("set -s {0} -p test2 publisher/alias=".format(repo_path))
                self.dc.stop()
                self.dc.start()

                repo = self.get_repo(repo_path, read_only=True)
                cat = repo.get_catalog(pub="test")
                test_plist = [str(f) for f in cat.fmris()]
                cat = repo.get_catalog(pub="test2")
                test2_plist = [str(f) for f in cat.fmris()]

                self.pkgsend_bulk(repo_uri, """
                    open pkg://test/refresh@1.0
                    close
                    open pkg://test2/refresh@1.0
                    close
                    """, no_catalog=True)

                self.pkgrepo("refresh -s {0} -p test".format(repo_uri))
                self.wait_repo(repo_path)

                # Now compare package lists to ensure new package is only seen
                # for 'test' publisher.
                repo = self.get_repo(repo_path, read_only=True)
                cat = repo.get_catalog(pub="test")
                self.assertNotEqual([str(f) for f in cat.fmris()], test_plist)
                test_plist = [str(f) for f in cat.fmris()]
                cat = repo.get_catalog(pub="test2")
                self.assertEqual([str(f) for f in cat.fmris()], test2_plist)
                test2_plist = [str(f) for f in cat.fmris()]

                # Verify refresh without specifying a publisher will refresh the
                # the catalogs for all publishers.
                self.pkgrepo("refresh -s {0}".format(repo_uri))
                self.wait_repo(repo_path)

                # Now compare package lists to ensure new package is seen for
                # all publishers.
                repo = self.get_repo(repo_path, read_only=True)
                cat = repo.get_catalog(pub="test")
                self.assertEqual([str(f) for f in cat.fmris()], test_plist)
                cat = repo.get_catalog(pub="test2")
                self.assertNotEqual([str(f) for f in cat.fmris()], test2_plist)

                self.dc.stop()

        def test_06_version(self):
                """Verify pkgrepo version works as expected."""

                # Verify version exits with error if operands are provided.
                self.pkgrepo("version operand", exit=2)

                # Verify version exits with error if a repository location is
                # provided.
                self.pkgrepo("version -s {0}".format(self.test_root), exit=2)

                # Verify version output is sane.
                self.pkgrepo("version")
                self.assertTrue(self.output.find(pkg.VERSION) != -1)

        def test_07_add_publisher(self):
                """Verify that add-publisher subcommand works as expected."""

                # Create a repository.
                repo_path = os.path.join(self.test_root, "repo")
                self.create_repo(repo_path)

                # Verify invalid publisher prefixes are rejected gracefully.
                self.pkgrepo("-s {0} add-publisher !valid".format(repo_path), exit=1)
                self.pkgrepo("-s {0} add-publisher file:{1}".format(repo_path,
                    repo_path), exit=1)
                self.pkgrepo("-s {0} add-publisher valid !valid".format(repo_path),
                    exit=1)

                # Verify that multiple publishers can be added at a time, and
                # that the first publisher named will be set as the default
                # publisher if a default was not already set.
                self.pkgrepo("-s {0} add-publisher example.com example.net".format(
                    repo_path))
                self.pkgrepo("-s {0} get -p example.com -p example.net "
                    "publisher/alias".format(repo_path))
                self.pkgrepo("get -s {0} -HFtsv publisher/prefix".format(repo_path))
                expected = """\
publisher\tprefix\texample.com
"""
                self.assertEqualDiff(expected, self.output)

                # Verify that add-publisher will exit with complete failure if
                # all publishers being added already exist.
                self.pkgrepo("-s {0} add-publisher example.com example.net".format(
                    repo_path), exit=1)

                # Verify that add-publisher will exit with partial failure if
                # only some publishers already exist.
                self.pkgrepo("-s {0} add-publisher example.com example.org".format(
                    repo_path), exit=3)

                # Now set a default publisher before adding a publisher for
                # the first time.
                shutil.rmtree(repo_path)
                self.create_repo(repo_path)
                self.pkgrepo("-s {0} set publisher/prefix=example.net".format(
                    repo_path))
                self.pkgrepo("-s {0} add-publisher example.org".format(repo_path))
                self.pkgrepo("get -s {0} -HFtsv publisher/prefix".format(repo_path))
                expected = """\
publisher\tprefix\texample.net
"""
                self.assertEqualDiff(expected, self.output)

        def test_09_remove_packages(self):
                """Verify that remove subcommand works as expected."""

                # Create a repository and then copy it somewhere for testing
                # to make it easy to restore the original as needed.
                src_repo = os.path.join(self.test_root, "remove-repo")

                self.create_repo(src_repo)
                self.pkgrepo("set -s {0} publisher/prefix=test".format(src_repo))

                # Test that removing a package when no files have been published
                # works (bug 18424).
                published = self.pkgsend_bulk(src_repo, self.zoo10)
                self.pkgrepo("remove -s {0} zoo".format(src_repo))

                # Reset the src_repo for the rest of the test.
                shutil.rmtree(src_repo)
                self.create_repo(src_repo)
                self.pkgrepo("set -s {0} publisher/prefix=test".format(src_repo))

                published = self.pkgsend_bulk(src_repo, (self.tree10,
                    self.amber10, self.amber20, self.truck10, self.truck20,
                    self.zoo10))
                self.pkgrepo("set -s {0} publisher/prefix=test2".format(src_repo))
                published += self.pkgsend_bulk(src_repo, (self.tree10,
                    self.zoo10))

                # Restore repository for next test.
                dest_repo = os.path.join(self.test_root, "test-repo")
                shutil.copytree(src_repo, dest_repo)

                # Verify that specifying something other than a filesystem-
                # based repository fails.
                self.pkgrepo("remove -s {0} tree".format(self.durl), exit=2)

                # Verify that non-matching patterns result in error.
                self.pkgrepo("remove -s {0} nosuchpackage".format(dest_repo), exit=1)
                self.pkgrepo("remove -s {0} tree nosuchpackage".format(dest_repo),
                    exit=1)

                # Verify that -n works as expected.
                self.pkgrepo("remove -n -s {0} zoo".format(dest_repo))
                # Since package was not removed, this succeeds.
                self.pkgrepo("remove -n -s {0} zoo".format(dest_repo))

                # Verify that -p works as expected.
                self.pkgrepo("remove -s {0} -p nosuchpub zoo".format(dest_repo),
                    exit=1)
                self.pkgrepo("remove -s {0} -p test -p test2 zoo".format(dest_repo))
                self.pkgrepo("remove -s {0} -p test zoo".format(dest_repo), exit=1)
                self.pkgrepo("remove -s {0} -p test2 zoo".format(dest_repo), exit=1)

                # Restore repository for next test.
                shutil.rmtree(dest_repo)
                shutil.copytree(src_repo, dest_repo)

                # Verify a single version of a package can be removed and that
                # package files will not be removed since older versions still
                # reference them.  (This also tests that packages that only
                # exist for one publisher in a multi-publisher repository can
                # be removed.)
                repo = self.get_repo(dest_repo)
                mpath = repo.manifest(published[4])
                self.pkgrepo("remove -s {0} truck@2.0".format(dest_repo))

                # The manifest should no longer exist.
                self.assertTrue(not os.path.exists(mpath))

                # These two files are in use by other packages so should still
                # exist.
                repo.file(self.fhashes["tmp/empty"])
                repo.file(self.fhashes["tmp/truck1"])

                # This file was only referenced by truck@2.0 so should be gone.
                self.assertRaises(sr.RepositoryFileNotFoundError, repo.file,
                    self.fhashes["tmp/truck2"])

                # Restore repository for next test.
                shutil.rmtree(dest_repo)
                shutil.copytree(src_repo, dest_repo)

                # Verify that all versions of a specific package can be removed
                # and that only files not referenced by other packages are
                # removed.
                self.pkgrepo("remove -s {0} truck".format(dest_repo))

                # This file is still in use by other packages.
                repo = self.get_repo(dest_repo)
                repo.file(self.fhashes["tmp/empty"])
                repo.file(self.fhashes["tmp/truck1"])

                # These files should have been removed since other packages
                # don't reference them.
                self.assertRaises(sr.RepositoryFileNotFoundError, repo.file,
                    self.fhashes["tmp/truck2"])

                # Restore repository for next test.
                shutil.rmtree(dest_repo)
                shutil.copytree(src_repo, dest_repo)

                # Verify that removing all packages that reference files
                # results in all files being removed and an empty file_root
                # for the repository.
                repo = self.get_repo(dest_repo)
                mpaths = []
                for f in published:
                        if "tree" in f or "truck" in f:
                                mpaths.append(repo.manifest(f))

                self.pkgrepo("remove -s {0} tree truck".format(dest_repo))

                self.assertRaises(sr.RepositoryFileNotFoundError, repo.file,
                    self.fhashes["tmp/empty"])
                self.assertRaises(sr.RepositoryFileNotFoundError, repo.file,
                    self.fhashes["tmp/truck1"])
                self.assertRaises(sr.RepositoryFileNotFoundError, repo.file,
                    self.fhashes["tmp/truck2"])

                # Verify that directories for manifests no longer exist since
                # all versions were removed.
                for mpath in mpaths:
                        pdir = os.path.dirname(mpath)
                        self.assertTrue(not os.path.exists(pdir))

                # Verify that entries for each package that was removed no
                # longer exist in the catalog, but do exist in the catalog's
                # updatelog.
                repo = self.get_repo(dest_repo)
                for pfx in ("test", "test2"):
                        c = repo.get_catalog(pub=pfx)
                        for f in c.fmris():
                                self.assertTrue(f.pkg_name not in ("tree",
                                    "truck"))

                        removed = set()
                        for name in c.updates:
                                ulog = pkg.catalog.CatalogUpdate(name,
                                    meta_root=c.meta_root, sign=False)

                                for pfmri, op_type, op_time, md in ulog.updates():
                                        if op_type == ulog.REMOVE:
                                                removed.add(str(pfmri))

                        expected = set(
                            f
                            for f in published
                            if ("tree" in f or "truck" in f) and \
                                f.startswith("pkg://{0}/".format(pfx))
                        )
                        self.assertEqualDiff(expected, removed)

                # Verify repository file_root is empty.
                for rstore in repo.rstores:
                        if not rstore.publisher:
                                continue
                        self.assertTrue(not os.listdir(rstore.file_root))

                hash_alg_list = ["sha256"]
                if sha512_supported:
                        hash_alg_list.append("sha512t_256")
                for hash_alg in hash_alg_list:
                        # Reset the src_repo for the rest of the test.
                        shutil.rmtree(src_repo)
                        self.create_repo(src_repo)
                        self.pkgrepo("set -s {0} publisher/prefix=test".format(
                            src_repo))
                        published = self.pkgsend_bulk(src_repo, (self.tree10),
                            debug_hash="sha1+{0}".format(hash_alg))

                        # Verify that we only have SHA-1 hashes in the rstore
                        repo = self.get_repo(src_repo)
                        known_hashes = self.fhashes.values()
                        for rstore in repo.rstores:
                                if not rstore.publisher:
                                        continue
                                for dir, dnames, fnames in \
                                    os.walk(rstore.file_root):
                                        for f in fnames:
                                                if f not in known_hashes:
                                                        self.assertTrue(False,
                                                            "Unexpected content "
                                                            "in repodir: {0}".format(f))

                        # Verify that when a repository has been published with
                        # multiple hashes, on removal, we only attempt to remove
                        # files using the least-preferred hash.
                        self.pkgrepo("remove -s {0} tree".format(src_repo))

                        # Verify repository file_root is empty.
                        for rstore in repo.rstores:
                                if not rstore.publisher:
                                        continue
                                self.assertTrue(not os.listdir(rstore.file_root))

                # Verify that removing a package does not fail if some files are
                # already removed/missing.
                repo_path = self.dc.get_repodir()
                published = self.pkgsend_bulk(repo_path, (self.tree10))
                missing_file = self.__inject_nofile("tmp/truck1")
                tree = fmri.PkgFmri(published[0])

                self.pkgrepo("remove -s {0} tree".format(repo_path))

                # Cleanup.
                shutil.rmtree(src_repo)
                shutil.rmtree(dest_repo)

        def test_10_list(self):
                """Verify the list subcommand works as expected."""

                repo_path = self.dc.get_repodir()
                repo_uri = self.dc.get_repo_url()

                # Publish some packages.
                self.pkgsend_bulk(repo_uri, (self.tree10, self.amber10,
                    self.amber20, self.amber30, self.amber35, self.amber40))

                # Verify graceful exit if invalid or incomplete set of
                # options specified.
                self.pkgrepo("list", exit=2)
                self.pkgrepo("-s bogus://location list", exit=1)
                self.pkgrepo("list -s bogus://location list", exit=1)
                self.pkgrepo("list -s {0} -F bad-format".format(repo_uri), exit=2)

                # Verify graceful exit for bad repository.
                self.pkgrepo("list -s /no/such/repository", exit=1)

                # Verify graceful exit if invalid package name given.
                self.pkgrepo("list -s {0} ^notvalid".format(repo_path), exit=1)

                # Verify graceful exit if no matching package found.
                self.pkgrepo("list -s {0} nosuchpackage".format(repo_path), exit=1)

                # Verify default output when listing all packages for both
                # file and http cases:
                for src in (repo_path, repo_uri):
                        # json output.
                        self.pkgrepo("list -s {0} -F json".format(src))
                        expected = """\
[{"branch":"0","build-release":"5.11","name":"amber",\
"pkg.fmri":"pkg://test/amber@4.0,5.11-0:20110804T203458Z",\
"pkg.obsolete":[{"value":["true"]}],"publisher":"test",\
"release":"4.0","timestamp":"20110804T203458Z",\
"version":"4.0,5.11-0:20110804T203458Z"},\
{"branch":"0","build-release":"5.11","name":"amber",\
"pkg.fmri":"pkg://test/amber@3.5,5.11-0:20110804T203458Z",\
"pkg.legacy":[{"value":["true"]}],"publisher":"test",\
"release":"3.5","timestamp":"20110804T203458Z",\
"version":"3.5,5.11-0:20110804T203458Z"},\
{"branch":"0","build-release":"5.11","name":"amber",\
"pkg.fmri":"pkg://test/amber@3.0,5.11-0:20110804T203458Z",\
"pkg.renamed":[{"value":["true"]}],"publisher":"test",\
"release":"3.0","timestamp":"20110804T203458Z",\
"version":"3.0,5.11-0:20110804T203458Z"},\
{"branch":"0","build-release":"5.11","name":"amber",\
"pkg.fmri":"pkg://test/amber@2.0,5.11-0:20110804T203458Z",\
"publisher":"test","release":"2.0","timestamp":"20110804T203458Z",\
"version":"2.0,5.11-0:20110804T203458Z"},\
{"branch":"0","build-release":"5.11","name":"amber",\
"pkg.fmri":"pkg://test/amber@1.0,5.11-0:20110804T203458Z",\
"pkg.human-version":[{"value":["1.0a"]}],\
"pkg.summary":[{"value":["Millenia old resin"]}],\
"publisher":"test","release":"1.0","timestamp":"20110804T203458Z",\
"version":"1.0,5.11-0:20110804T203458Z"},\
{"branch":"0","build-release":"5.11",\
"info.classification":[{"value":["org.opensolaris.category.2008:System/Core"]}],\
"name":"tree","pkg.fmri":"pkg://test/tree@1.0,5.11-0:20110804T203458Z",\
"pkg.summary":[{"value":["Leafy SPARC package"],"variant.arch":["sparc"]},\
{"value":["Leafy i386 package"],"variant.arch":["i386"]}],\
"publisher":"test","release":"1.0","timestamp":"20110804T203458Z",\
"variant.arch":[{"value":["i386","sparc"]}],\
"version":"1.0,5.11-0:20110804T203458Z"}]"""
                        self.assertEqualDiff(expected, self.output)

                # Now verify list output in different formats but only using
                # file repository for test efficiency.

                # Human readable (default) output.
                self.pkgrepo("list -s {0}".format(src))
                expected = """\
PUBLISHER NAME                                          O VERSION
test      amber                                         o 4.0-0:20110804T203458Z
test      amber                                         l 3.5-0:20110804T203458Z
test      amber                                         r 3.0-0:20110804T203458Z
test      amber                                           2.0-0:20110804T203458Z
test      amber                                           1.0-0:20110804T203458Z
test      tree                                            1.0-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # Human readable (default) output with no header.
                self.pkgrepo("list -s {0} -H".format(repo_path))
                expected = """\
test      amber                                         o 4.0-0:20110804T203458Z
test      amber                                         l 3.5-0:20110804T203458Z
test      amber                                         r 3.0-0:20110804T203458Z
test      amber                                           2.0-0:20110804T203458Z
test      amber                                           1.0-0:20110804T203458Z
test      tree                                            1.0-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # tsv output.
                self.pkgrepo("list -s {0} -F tsv".format(repo_path))
                expected = """\
PUBLISHER	NAME	O	RELEASE	BUILD RELEASE	BRANCH	PACKAGING DATE	FMRI
test	amber	o	4.0	5.11	0	20110804T203458Z	pkg://test/amber@4.0,5.11-0:20110804T203458Z
test	amber	l	3.5	5.11	0	20110804T203458Z	pkg://test/amber@3.5,5.11-0:20110804T203458Z
test	amber	r	3.0	5.11	0	20110804T203458Z	pkg://test/amber@3.0,5.11-0:20110804T203458Z
test	amber		2.0	5.11	0	20110804T203458Z	pkg://test/amber@2.0,5.11-0:20110804T203458Z
test	amber		1.0	5.11	0	20110804T203458Z	pkg://test/amber@1.0,5.11-0:20110804T203458Z
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # json-formatted output.
                self.pkgrepo("list -s {0} -F json-formatted".format(src))
                expected = """\
[
  {
    "branch": "0",
    "build-release": "5.11",
    "name": "amber",
    "pkg.fmri": "pkg://test/amber@4.0,5.11-0:20110804T203458Z",
    "pkg.obsolete": [
      {
        "value": [
          "true"
        ]
      }
    ],
    "publisher": "test",
    "release": "4.0",
    "timestamp": "20110804T203458Z",
    "version": "4.0,5.11-0:20110804T203458Z"
  },
  {
    "branch": "0",
    "build-release": "5.11",
    "name": "amber",
    "pkg.fmri": "pkg://test/amber@3.5,5.11-0:20110804T203458Z",
    "pkg.legacy": [
      {
        "value": [
          "true"
        ]
      }
    ],
    "publisher": "test",
    "release": "3.5",
    "timestamp": "20110804T203458Z",
    "version": "3.5,5.11-0:20110804T203458Z"
  },
  {
    "branch": "0",
    "build-release": "5.11",
    "name": "amber",
    "pkg.fmri": "pkg://test/amber@3.0,5.11-0:20110804T203458Z",
    "pkg.renamed": [
      {
        "value": [
          "true"
        ]
      }
    ],
    "publisher": "test",
    "release": "3.0",
    "timestamp": "20110804T203458Z",
    "version": "3.0,5.11-0:20110804T203458Z"
  },
  {
    "branch": "0",
    "build-release": "5.11",
    "name": "amber",
    "pkg.fmri": "pkg://test/amber@2.0,5.11-0:20110804T203458Z",
    "publisher": "test",
    "release": "2.0",
    "timestamp": "20110804T203458Z",
    "version": "2.0,5.11-0:20110804T203458Z"
  },
  {
    "branch": "0",
    "build-release": "5.11",
    "name": "amber",
    "pkg.fmri": "pkg://test/amber@1.0,5.11-0:20110804T203458Z",
    "pkg.human-version": [
      {
        "value": [
          "1.0a"
        ]
      }
    ],
    "pkg.summary": [
      {
        "value": [
          "Millenia old resin"
        ]
      }
    ],
    "publisher": "test",
    "release": "1.0",
    "timestamp": "20110804T203458Z",
    "version": "1.0,5.11-0:20110804T203458Z"
  },
  {
    "branch": "0",
    "build-release": "5.11",
    "info.classification": [
      {
        "value": [
          "org.opensolaris.category.2008:System/Core"
        ]
      }
    ],
    "name": "tree",
    "pkg.fmri": "pkg://test/tree@1.0,5.11-0:20110804T203458Z",
    "pkg.summary": [
      {
        "value": [
          "Leafy i386 package"
        ],
        "variant.arch": [
          "i386"
        ]
      },
      {
        "value": [
          "Leafy SPARC package"
        ],
        "variant.arch": [
          "sparc"
        ]
      }
    ],
    "publisher": "test",
    "release": "1.0",
    "timestamp": "20110804T203458Z",
    "variant.arch": [
      {
        "value": [
          "i386",
          "sparc"
        ]
      }
    ],
    "version": "1.0,5.11-0:20110804T203458Z"
  }
]
"""
                self.assertEqualJSON(expected, self.output)

                # Verify ability to list specific packages.
                self.pkgrepo("list -s {0} -H -F tsv tree amber@2.0".format(repo_path))
                expected = """\
test	amber		2.0	5.11	0	20110804T203458Z	pkg://test/amber@2.0,5.11-0:20110804T203458Z
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("list -s {0} -H -F tsv tree amber@4.0 amber@2.0".format(
                    repo_path))
                expected = """\
test	amber	o	4.0	5.11	0	20110804T203458Z	pkg://test/amber@4.0,5.11-0:20110804T203458Z
test	amber		2.0	5.11	0	20110804T203458Z	pkg://test/amber@2.0,5.11-0:20110804T203458Z
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("list -s {0} -H -F tsv amber@latest tree".format(
                    repo_path))
                expected = """\
test	amber	o	4.0	5.11	0	20110804T203458Z	pkg://test/amber@4.0,5.11-0:20110804T203458Z
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # Verify exit with partial failure if one match fails.
                self.pkgrepo("list -s {0} -H -F tsv tree bogus".format(repo_path),
                    exit=3)
                expected = """\
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                #
                # Add packages for a different publisher.
                #
                self.pkgrepo("set -s {0} publisher/prefix=test2".format(repo_path))
                self.pkgsend_bulk(repo_path, (self.truck10, self.zoo10))

                # Verify list of all package includes all publishers.
                # tsv output.
                self.pkgrepo("list -s {0} -H -F tsv".format(repo_path))
                expected = """\
test	amber	o	4.0	5.11	0	20110804T203458Z	pkg://test/amber@4.0,5.11-0:20110804T203458Z
test	amber	l	3.5	5.11	0	20110804T203458Z	pkg://test/amber@3.5,5.11-0:20110804T203458Z
test	amber	r	3.0	5.11	0	20110804T203458Z	pkg://test/amber@3.0,5.11-0:20110804T203458Z
test	amber		2.0	5.11	0	20110804T203458Z	pkg://test/amber@2.0,5.11-0:20110804T203458Z
test	amber		1.0	5.11	0	20110804T203458Z	pkg://test/amber@1.0,5.11-0:20110804T203458Z
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
test2	truck		1.0	5.11	0	20110804T203458Z	pkg://test2/truck@1.0,5.11-0:20110804T203458Z
test2	zoo		1.0	5.11	0	20110804T203458Z	pkg://test2/zoo@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("list -s {0} -H -F tsv -p all".format(repo_path))
                self.assertEqualDiff(expected, self.output)

                # Verify that packages for a single publisher can be listed.
                self.pkgrepo("list -s {0} -H -F tsv -p test2".format(repo_path))
                expected = """\
test2	truck		1.0	5.11	0	20110804T203458Z	pkg://test2/truck@1.0,5.11-0:20110804T203458Z
test2	zoo		1.0	5.11	0	20110804T203458Z	pkg://test2/zoo@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # Verify that patterns matching packages only provided by one
                # publisher will not result in partial failure.
                self.pkgrepo("list -s {0} -H -F tsv zoo".format(repo_path))
                expected = """\
test2	zoo		1.0	5.11	0	20110804T203458Z	pkg://test2/zoo@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("list -s {0} -H -F tsv '//test2/*'".format(repo_path))
                expected = """\
test2	truck		1.0	5.11	0	20110804T203458Z	pkg://test2/truck@1.0,5.11-0:20110804T203458Z
test2	zoo		1.0	5.11	0	20110804T203458Z	pkg://test2/zoo@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # Verify that a package provided by no publisher will result
                # in graceful failure when multiple publishers are present.
                self.pkgrepo("list -s {0} -H -F tsv nosuchpackage".format(repo_path),
                    exit=1)

        def __get_mf_path(self, fmri_str, pub=None):
                """Given an FMRI, return the path to its manifest in our
                repository."""

                usepub = "test"
                if pub:
                        usepub = pub
                path_comps = [self.dc.get_repodir(), "publisher",
                    usepub, "pkg"]
                pfmri = pkg.fmri.PkgFmri(fmri_str)
                path_comps.append(pfmri.get_name())
                path_comps.append(pfmri.get_link_path().split("@")[1])
                return os.path.sep.join(path_comps)

        def __get_file_path(self, path):
                """Returns the path to a file in the repository. The path name
                must be present in self.fhashes."""

                fpath = os.path.sep.join([self.dc.get_repodir(), "publisher",
                    "test", "file"])
                fhash = self.fhashes[path]
                return os.path.sep.join([fpath, fhash[0:2], fhash])

        def __get_manifest_contents(self, fmri_str):
                """Given an FMRI, return the unsorted manifest contents from our
                repository as a string."""

                mpath = self.__get_mf_path(fmri_str)
                mf = pkg.manifest.Manifest()
                mf.set_content(pathname=mpath)
                return mf.tostr_unsorted()

        def __inject_depend(self, fmri_str, depend_str, pub=None):
                mpath = self.__get_mf_path(fmri_str, pub=pub)
                with open(mpath, "a+") as mf:
                        mf.write(depend_str)
                return mpath

        def __inject_badhash(self, path, valid_gzip=True):
                """Corrupt a file in the repository with the given path, where
                that path is a key in self.fhashes, returning the repository
                path of the file that was corrupted.  If valid_gzip is set,
                we write a gzip file into the repository, otherwise the file
                contains plaintext."""

                corrupt_path = self.__get_file_path(path)
                other_path = os.path.join(self.test_root, "tmp/other")

                with open(other_path, "rb") as other:
                        with open(corrupt_path, "wb") as corrupt:
                                if valid_gzip:
                                        gz = pkg.pkggzip.PkgGzipFile(
                                            fileobj=corrupt)
                                        gz.write(other.read())
                                        gz.close()
                                else:
                                        corrupt.write(other.read())
                return corrupt_path

        def __repair_badhash(self, path):
                """Fix a file in the repository that corresponds to this path.
                """
                fpath = self.__get_file_path(path)
                fixed_path = os.path.join(self.test_root, path)
                with open(fixed_path, "rb") as fixed:
                        with open(fpath, "wb") as broken:
                                gz = pkg.pkggzip.PkgGzipFile(
                                    fileobj=broken)
                                gz.write(fixed.read())
                                gz.close()

        def __inject_badmanifest(self, fmri_str):
                """Corrupt a manifest in the repository for the given fmri,
                returning the path to that FMRI."""
                mpath = self.__get_mf_path(fmri_str)
                other_path = os.path.join(self.test_root, "tmp/other")

                with open(other_path, "r") as other:
                        with open(mpath, "a") as mf:
                                mf.write(other.read())
                return mpath

        def __inject_dir_for_manifest(self, fmri_str):
                """Put a dir in place of a manifest."""
                mpath = self.__get_mf_path(fmri_str)
                os.remove(mpath)
                os.mkdir(mpath)
                return mpath

        def __inject_nofile(self, path):
                fpath = self.__get_file_path(path)
                os.remove(fpath)
                return fpath

        def __inject_perm(self, path=None, fmri_str=None, parent=False,
            chown=False):
                """Set restrictive file permissions on the given path or fmri in
                the repository. If 'parent' is set to True, we change
                permissions on the parent directory of the file or fmri.
                If chown is set, we chown the file and its parent dir to root.
                """
                if path:
                        fpath = self.__get_file_path(path)
                        if parent:
                                fpath = os.path.dirname(fpath)
                        os.chmod(fpath, 0000)
                        if chown:
                                os.chown(fpath, 0, 0)
                                os.chown(os.path.dirname(mpath), 0, 0)
                        return fpath
                elif fmri_str:
                        mpath = self.__get_mf_path(fmri_str)
                        if parent:
                                mpath = os.path.dirname(mpath)
                        os.chmod(mpath, 0000)
                        if chown:
                                os.chown(mpath, 0, 0)
                                os.chown(os.path.dirname(mpath), 0, 0)
                        return mpath
                else:
                        assertTrue(False, "Invalid use of __inject_perm(..)!")

        def __repair_perm(self, path, parent=False):
                """Repair errors introduced by __inject_perm."""
                if parent:
                        fpath = os.path.dirname(path)
                else:
                        fpath = path
                if os.path.isdir(fpath):
                        os.chmod(fpath, misc.PKG_DIR_MODE)
                elif os.path.isfile(fpath):
                        os.chmod(fpath, misc.PKG_FILE_MODE)

        def __inject_badsig(self, fmri_str):
                mpath = self.__get_mf_path(fmri_str)
                with open(mpath, "a+") as mf:
                        mf.write("set name=pkg.t_pkgrepo.bad_sig value=foo")
                return mpath

        def __repair_badsig(self, path):
                mpath_new = path + ".new"
                with open(path, "r") as mf:
                        with open(mpath_new, "w") as mf_new:
                                for line in mf.readlines():
                                        if "pkg.t_pkgrepo.bad_sig" not in line:
                                                mf_new.write(line)
                os.rename(mpath_new, path)

        def __inject_badchain(self, fmri_str):
                """Given an fmri with a signature action, locate the chain
                hashes used by that signature action in that package, and
                remove the corresponding file from the repository. If the chain
                references more one file, those subsequent files are
                corrupted."""

                mpath = self.__get_mf_path(fmri_str)
                mf = pkg.manifest.Manifest()
                mf.set_content(pathname=mpath)
                fpath = os.path.sep.join([self.dc.get_repodir(), "publisher",
                    "test", "file"])

                bad_paths = []
                removed_file = False
                corrupted_file = False
                for ac in mf.gen_actions_by_type("signature"):
                        for chain in ac.attrs["chain"].split():
                                cpath = os.path.join(fpath, chain[0:2], chain)
                                if not removed_file:
                                        os.unlink(cpath)
                                        removed_file = True
                                elif not corrupted_file:
                                        with open(cpath, "w") as f:
                                            f.write("noodles")
                                        corrupted_file = True
                                else:
                                        with open(cpath, "wb") as badfile:
                                                gz = pkg.pkggzip.PkgGzipFile(
                                                    fileobj=badfile)
                                                gz.write(b"noodles")
                                                gz.close()
                                bad_paths.append(cpath)
                return bad_paths

        def __inject_unknown(self):
                pass

        def test_11_verify_badhash(self):
                """Test that verify finds bad hashes and invalid gzip files."""

                repo_path = self.dc.get_repodir()
                repo_uri = self.dc.get_repo_url()

                # publish a single package and make sure the repository is clean
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                self.pkgrepo("-s {0} verify".format(repo_path), exit=0)

                # break a file in the repository and ensure we spot it
                bad_hash_path = self.__inject_badhash("tmp/truck1")

                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.assertTrue(
                    self.output.count("ERROR: Invalid file hash") == 1)
                self.assertTrue(bad_hash_path in self.output)
                self.assertTrue(fmris[0] in self.output)

                # fix the file in the repository, and publish another package
                self.__repair_badhash("tmp/truck1")
                self.pkgsend_bulk(repo_path, (self.amber20))
                fmris += self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgrepo("-s {0} verify".format(repo_path), exit=0)
                self.assertTrue(bad_hash_path not in self.output)
                bad_hash_path = self.__inject_badhash("tmp/truck1")

                # verify we now get two errors when verifying the repository
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.assertTrue(
                    self.output.count("ERROR: Invalid file hash") == 2)
                for fmri in fmris:
                        self.assertTrue(fmri in self.output)
                self.assertTrue(bad_hash_path in self.output)
                # check we also print paths which deliver that corrupted file
                self.assertTrue("etc/truck1" in self.output)
                self.assertTrue("etc/trailer" in self.output)

                # Corrupt another file to see that we can also spot files that
                # aren't gzipped.
                fmris += self.pkgsend_bulk(repo_path, (self.truck20))
                bad_gzip_path = self.__inject_badhash("tmp/truck2",
                    valid_gzip=False)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                # we should get 3 bad file hashes now, since we've added truck20
                # which also references etc/truck1, which is bad.
                self.assertTrue(
                    self.output.count("ERROR: Invalid file hash") == 3)
                self.assertTrue(
                    self.output.count("ERROR: Corrupted gzip file") == 1)
                self.assertTrue(bad_gzip_path in self.output)

                # Check that when verifying content, we always use the most
                # preferred hash.
                hash_alg_list = ["sha256"]
                if sha512_supported:
                        hash_alg_list.append("sha512t_256")
                for hash_alg in hash_alg_list:
                        # Remove all existing packages first.
                        self.pkgrepo("-s {0} remove {1}".format(repo_path,
                            " ".join(fmris)))
                        fmris = self.pkgsend_bulk(repo_path, (self.tree10),
                            debug_hash="sha1+{0}".format(hash_alg))
                        self.pkgrepo("-s {0} verify".format(repo_path), exit=0)

                        # break a file in the repository and ensure we spot it.
                        bad_hash_path = self.__inject_badhash("tmp/truck1")
                        bad_basename = os.path.basename(bad_hash_path)

                        self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                        self.assertTrue(
                            self.output.count("ERROR: Invalid file hash") == 1)

                        # We should be verifying using the SHA-2 hash, and so we
                        # should only see the SHA-1 value in the output once,
                        # when printing the path to the file in the repository,
                        # not when reporting the computed or expected hash.
                        self.assertTrue(self.output.count(bad_basename) == 1)

                        # Verify that when we publish using SHA-1 only, that we
                        # get the SHA-1 value printed twice: once when printing
                        # the path to the file in the repository, and once when
                        # printing the expected hash.
                        self.pkgrepo("-s {0} remove {1}".format(repo_path,
                            " ".join(fmris)))
                        fmris = self.pkgsend_bulk(repo_path, (self.tree10),
                            debug_hash="sha1")
                        self.__inject_badhash("tmp/truck1")

                        self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                        self.assertTrue(self.output.count(bad_basename) == 2)

        def test_12_verify_badmanifest(self):
                """Test that verify finds bad manifests."""
                repo_path = self.dc.get_repodir()

                # publish a single package
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))

                # corrupt a manifest and make sure pkglint agrees
                bad_mf = self.__inject_badmanifest(fmris[0])
                self.pkglint(bad_mf, exit=1)

                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.assertTrue(bad_mf in self.output)
                self.assertTrue("Corrupt manifest." in self.output)

                # publish more packages, and verify we still get the one error
                fmris += self.pkgsend_bulk(repo_path, (self.truck10,
                    self.amber10))
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.assertTrue(
                    self.output.count("ERROR: Corrupt manifest.") == 1)

                # break another manifest, and check we get two errors
                another_bad_mf = self.__inject_badmanifest(fmris[-1])
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.assertTrue(another_bad_mf in self.output)
                self.assertTrue(bad_mf in self.output)
                self.assertTrue(
                    self.output.count("Corrupt manifest.") == 2)

        def test_13_verify_nofile(self):
                """Test that verify finds missing files."""

                repo_path = self.dc.get_repodir()

                # publish a single package and break it
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                missing_file = self.__inject_nofile("tmp/truck1")

                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.assertTrue(missing_file in self.output)
                self.assertTrue("ERROR: Missing file: {0}".format(
                    self.fhashes["tmp/truck1"] in self.output))
                self.assertTrue(fmris[0] in self.output)

                # publish another package that also delivers the file
                # and inject the error again, checking that both manifests
                # appear in the output
                fmris += self.pkgsend_bulk(repo_path, (self.truck10))
                self.__inject_nofile("tmp/truck1")

                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.assertTrue(missing_file in self.output)
                self.assertTrue(self.output.count("ERROR: Missing file: {0}".format(
                    self.fhashes["tmp/truck1"])) == 2)
                for f in fmris:
                        self.assertTrue(f in self.output)

        def test_14_verify_permissions(self):
                """Check that we can find files and manifests in the
                repository that have invalid permissions."""

                repo_path = self.dc.get_repodir()

                shutil.rmtree(repo_path)
                os.mkdir(repo_path)
                os.chmod(repo_path, 0o777)
                self.pkgrepo("create {0}".format(repo_path), su_wrap=True)
                self.pkgrepo("set -s {0} publisher/prefix=test".format(repo_path),
                    su_wrap=True)
                # publish a single package and break it
                fmris = self.pkgsend_bulk(repo_path, (self.truck10),
                    su_wrap=True)
                bad_path = self.__inject_perm(path="tmp/truck1")
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1, su_wrap=True)
                self.assertTrue(bad_path in self.output)
                self.assertTrue("ERROR: Verification failure" in self.output)
                self.assertTrue(fmris[0] in self.output)
                self.__repair_perm(bad_path)

                # Just break the parent directory, we should still report the
                # hash file as unreadable
                bad_parent = self.__inject_perm(path="tmp/truck1", parent=True)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1, su_wrap=True)
                self.assertTrue(bad_path in self.output)
                self.assertTrue("ERROR: Verification failure" in self.output)
                self.assertTrue(fmris[0] in self.output)
                self.__repair_perm(bad_parent)
                # break some manifests
                fmris = self.pkgsend_bulk(repo_path, (self.truck20),
                    su_wrap=True)

                bad_mf_path = self.__inject_perm(fmri_str=fmris[0])
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1, su_wrap=True)
                self.assertTrue(bad_mf_path in self.output)
                self.assertTrue("ERROR: Verification failure" in self.output)

                # this should cause both manifests to report errors
                bad_mf_path = self.__inject_perm(fmri_str=fmris[0], parent=True)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1, su_wrap=True)
                self.assertTrue(bad_mf_path in self.output)
                self.assertTrue("ERROR: Verification failure" in self.output)
                self.__repair_perm(bad_mf_path)

        def test_15_verify_badsig(self):
                repo_path = self.dc.get_repodir()

                # publish a single package and break it
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                self.pkgsign(repo_path, "\*")
                self.pkgrepo("-s {0} verify".format(repo_path))
                bad_path = self.__inject_badsig(fmris[0])
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.assertTrue(bad_path in self.output)
                self.assertTrue("ERROR: Bad signature." in self.output)
                self.__repair_badsig(bad_path)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=0)

                # now sign with a key, cert and chain cert and check we fail
                # to verify
                self.pkgsign_simple(repo_path, "\*")
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.assertTrue("ERROR: Bad signature." in self.output)

                # now set a trust anchor directory, and expect that pkgrepo
                # verify will now pass
                ta_dir = os.path.join(self.test_root,
                    "ro_data/signing_certs/produced/ta3")
                self.pkgrepo("-s {0} set repository/trust-anchor-directory={1}".format(
                    repo_path, ta_dir))
                self.pkgrepo("-s {0} verify".format(repo_path), exit=0)

                # remove the old package and republish it so it can be signed
                # again.
                self.pkgrepo("-s {0} remove {1}".format(repo_path, fmris[0]))
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))

                # Create an image, setup its trust-anchor dir, then use that
                # for our repository so that pkgrepo verify can perform
                # signature verification against it.
                self.image_create()
                self.seed_ta_dir("ta1")
                self.pkgrepo("-s {0} set repository/trust-anchor-directory={1}".format(
                    repo_path, self.raw_trust_anchor_dir))

                # We sign with several certs so that we get a 'chain' attribute
                # that contains several hashes.
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5}".format(
                      key=os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      i1=os.path.join(self.chain_certs_dir,
                          "ch1_ta1_cert.pem"),
                      i2=os.path.join(self.chain_certs_dir,
                          "ch2_ta1_cert.pem"),
                      i3=os.path.join(self.chain_certs_dir,
                          "ch3_ta1_cert.pem"),
                      i4=os.path.join(self.chain_certs_dir,
                          "ch4_ta1_cert.pem"),
                      i5=os.path.join(self.chain_certs_dir,
                          "ch5_ta1_cert.pem")
                    )

                self.pkgsign(repo_path, "{0} \*".format(sign_args))
                self.pkgrepo("-s {0} verify".format(repo_path))

                bad_paths = self.__inject_badchain(fmris[0])
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                for bad_path in bad_paths:
                        self.assertTrue(bad_path in self.output)

        def test_16_verify_warn_openperms(self):
                """Test that we emit a warning message when the repository is
                not world-readable."""

                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                os.chmod(self.test_root, 0o700)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=0)
                self.assertTrue("WARNING: " in self.output)
                self.assertTrue("svc:/application/pkg/system-repository" \
                    in self.output)
                self.assertTrue("ERROR: " not in self.output)
                os.chmod(self.test_root, 0o755)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=0)
                self.assertTrue("WARNING: " not in self.output)

        def test_17_verify_empty_pub(self):
                """Test that we can verify a repository that contains a
                publisher with no packages."""
                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgrepo("-s {0} add-publisher empty".format(repo_path))
                self.pkgrepo("-s {0} verify -p empty".format(repo_path))

        def test_18_verify_invalid_repos(self):
                """Test that we exit with a usage message for v3 repos and
                network repositories."""
                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                depot_uri = self.dc.get_depot_url()
                self.dc.start()
                self.pkgrepo("-s {0} verify".format(depot_uri), exit=2)
                self.dc.stop()
                shutil.rmtree(repo_path)
                self.pkgrepo("create --version=3 {0}".format(repo_path))
                self.pkgrepo("set -s {0} publisher/prefix=test".format(repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)

        def test_19_verify_valid_dependency(self):
                """Test package with valid dependency will not cause verify
                failure."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                self.pkgsend_bulk(repo_path, (self.truck10, self.truck20,
                    self.amber10, self.amber20, self.tree10))
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

        def test_20_verify_missing_nonincorp_dependency(self):
                """Test that we can verify which dependency is missing from
                a repository."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                # Test that missing dependency will be reported in -d mode.
                self.pkgsend_bulk(repo_path, (self.wtinstallhold10,
                    self.wtinstallhold20))
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                # Test that it will also be reported without -d.
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                # Test that disabling dependency check works.
                self.pkgrepo("-s {0} verify --disable dependency".format(repo_path))
                self.pkgrepo("-s {0} verify --disable dependency "
                    "--disable dependency".format(repo_path))
                # Test that disabling unknown check fails.
                self.pkgrepo("-s {0} verify --disable unknown".format(repo_path),
                    exit=2)
                # Test that disabling dependency check will disallow -i or -d
                # option
                self.pkgrepo("-s {0} verify --disable dependency -i file".format(
                    repo_path), exit=2)
                self.pkgrepo("-s {0} verify --disable dependency -d".format(
                    repo_path), exit=2)
                # Test that complete dependency will pass verification and
                # miner version dependency will be used if the exact version
                # required is missing.
                self.pkgsend_bulk(repo_path, (self.amber20,
                    self.tree10))
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))
                self.pkgsend_bulk(repo_path, self.optionalpkg10)
                # Should be no problem for completely missing optional
                # dependency.
                self.pkgrepo("-s {0} verify".format(repo_path))
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgsend_bulk(repo_path, (self.zoo10))
                # Should fail this time.
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)

        def test_21_verify_exclude_dependency(self):
                """Test that exclude dependency does not cause failure."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                self.pkgsend_bulk(repo_path, (self.refuse10))
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

        def test_22_verify_illegal_dependency(self):
                """Test illegal dependency will cause verification errors."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.illegaldep10))

                # Test bad depend version number causes reporting error.
                badversion = "depend fmri=pkg:/amber@1.x type=require"
                self.__inject_depend(fmris[0], badversion)
                self.pkgrepo("-s {0} rebuild".format(repo_path))
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)

                # Test bad depend package name causes reporting error.
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.illegaldep10))
                badname = "depend fmri=pkg:/_amber@1.0 type=require"
                self.__inject_depend(fmris[0], badname)
                self.pkgrepo("-s {0} rebuild".format(repo_path))
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)

        def test_23_verify_no_install_hold(self):
                """Test if there is no install-hold, then dependency check will
                still run with or without -d."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                self.pkgsend_bulk(repo_path, (self.truck10, self.truck20))
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                # Sending amber@1.0 without tree@1.0 still fail.
                self.pkgsend_bulk(repo_path, (self.amber10))
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                # Sending amber@2.0 still fail.
                self.pkgsend_bulk(repo_path, (self.amber20))
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                # Finally send tree@1.0 to make the repo complete.
                self.pkgsend_bulk(repo_path, (self.tree10))
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

        def test_24_verify_provided_publisher(self):
                """Test verifying only the dependencies of provided publisher
                by -p option."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test1".format(
                    repo_path))
                self.pkgrepo("-s {0} add-publisher test2".format(repo_path))
                self.pkgsend_bulk(repo_path, (self.withpub1_10,
                    self.withpub2_10))
                #This should fail, because dependency amber@1.0 is missing
                # for withpub1@1.0 under test1.
                self.pkgrepo("-s {0} verify -p test1 -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify -p test1".format(repo_path), exit=1)
                # Send the missing dependency should lead to verifaction
                # success.
                self.pkgsend_bulk(repo_path, (self.amber10, self.tree10))
                self.pkgrepo("-s {0} verify -p test1 -d".format(repo_path))
                self.pkgrepo("-s {0} verify -p test1".format(repo_path))
                # Package withpub2 under test2 should still fail on
                # verification.
                self.pkgrepo("-s {0} verify -p test2 -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify -p test2".format(repo_path), exit=1)

        def __make_repo_incorp(self, repo_path, dep_inj):
                """Create a repository with incorporation dependency."""

                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.incorp10,
                    self.amber10, self.tree10))
                self.__inject_depend(fmris[0], dep_inj)
                self.pkgrepo("-s {0} rebuild".format(repo_path))

        def test_25_verify_missing_incorp_dependency(self):
                """Test missing incorporate dependency will cause verify
                failure."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.incorp10,
                    self.amber10, self.tree10))
                # Test just specifying same release number will not cause
                # verify failure.
                verrel = "depend fmri=pkg:/amber@1.0 type=incorporate"
                self.__make_repo_incorp(repo_path, verrel)
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

                # Shorter release number will work.
                verrel = "depend fmri=pkg:/amber@1 type=incorporate"
                self.__make_repo_incorp(repo_path, verrel)
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

                # Test specifying different release version will cause verify
                # failure.
                verrel = "depend fmri=pkg:/amber@2.0 type=incorporate"
                self.__make_repo_incorp(repo_path, verrel)
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)

                verrel = "depend fmri=pkg:/amber@0.8 type=incorporate"
                self.__make_repo_incorp(repo_path, verrel)
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)

                # Test specifying same release and build version will not lead
                # to fail.
                version = "depend fmri=pkg:/amber@1.0,5.11 type=incorporate"
                self.__make_repo_incorp(repo_path, version)
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

                # Test specifying same release and different build version
                # will not cause verify failure, simply because the build
                # version is ignored.
                version = "depend fmri=pkg:/amber@1.0,5.10 type=incorporate"
                self.__make_repo_incorp(repo_path, version)
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

                version = "depend fmri=pkg:/amber@1.0,5.12 type=incorporate"
                self.__make_repo_incorp(repo_path, version)
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

                # Test specifying same release, build and branch version will
                # not cause verify failure.
                version = "depend fmri=pkg:/amber@1.0,5.11-0 type=incorporate"
                self.__make_repo_incorp(repo_path, version)
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

                # Test specifying same release and build version but different
                # branch version will cause verify failure.
                version = "depend fmri=pkg:/amber@1.0,5.11-1 type=incorporate"
                self.__make_repo_incorp(repo_path, version)
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)

                version = "depend fmri=pkg:/amber@1.0,5.11-0.1 " \
                    "type=incorporate"
                self.__make_repo_incorp(repo_path, version)
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                # Test specifying same release, build, branch version and time
                # stamp will not cause verify failure.
                version = \
                    "depend fmri=pkg:/amber@1.0,5.11-0:20110804T203458Z " \
                    "type=incorporate"
                self.__make_repo_incorp(repo_path, version)
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

                # Test specifying same release, build and branch version but
                # different time stamp will cause verify failure.
                version = \
                    "depend fmri=pkg:/amber@1.0,5.11-0:20100804T203458Z " \
                    "type=incorporate"
                self.__make_repo_incorp(repo_path, version)
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)

                version = \
                    "depend fmri=pkg:/amber@1.0,5.11-0:20120804T203458Z " \
                    "type=incorporate"
                self.__make_repo_incorp(repo_path, version)
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)

                version = \
                    "depend fmri=pkg:/amber@1.0,5.11-0:20120804 " \
                    "type=incorporate"
                self.__make_repo_incorp(repo_path, version)
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)

        def test_26_verify_require_any_dependency(self):
                """Test require-any dependency verification."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                self.pkgsend_bulk(repo_path, (self.require_any10, self.tree10))
                # Test missing dependency will cause verify failure.
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                # Test sending one of the require-any dependency still cause
                # verify failed.
                self.pkgsend_bulk(repo_path, (self.amber10))
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                # Test sending all of the require-any dependency lead
                # to success.
                self.pkgsend_bulk(repo_path, (self.amber20))
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

        def test_27_verify_publisher_merge(self):
                """Test packages with same package, different version and
                different publisher are merged together for verification."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test1".format(
                    repo_path))
                self.pkgrepo("-s {0} add-publisher test2".format(repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.incorp10,
                    self.withpub1_10, self.withpub1_20, self.amber10,
                    self.tree10))

                dep_str = "depend fmri=pkg:/withpub1@2.0 type=require"
                self.__inject_depend(fmris[0], dep_str, pub="test1")
                self.pkgrepo("-s {0} rebuild".format(repo_path))
                self.pkgrepo("-s {0} verify -d".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))

        def test_28_verify_ignore_dep_attr(self):
                """Test whether ignore-check tag works as expected."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.depchecktag10))
                # Missing unignored dependency causes failure.
                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)
                # Sending missing dependency leads to success.
                fmris = self.pkgsend_bulk(repo_path, (self.depcheckdep10))
                self.pkgrepo("-s {0} verify".format(repo_path))
                self.pkgrepo("-s {0} verify -d".format(repo_path))

                # Check if Ignore check label works.
                dep_str = "depend fmri=tree@1.0 type=require " \
                    "ignore-check=\"external\"\n"
                self.__inject_depend(fmris[0], dep_str)
                self.pkgrepo("-s {0} rebuild".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)

                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                dep_str = "depend fmri=incorp@1.0 type=require " \
                    "ignore-check=\"excluded\"\n"
                self.__inject_depend(fmris[0], dep_str)
                self.pkgrepo("-s {0} rebuild".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))
                self.pkgrepo("-s {0} verify -d".format(repo_path), exit=1)

        def test_29_verify_parent_and_special_dep(self):
                """Test parent dependency and special dependency are handled
                properly."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                dep_str = "depend fmri=incorp@1.0 type=parent\n"
                self.__inject_depend(fmris[0], dep_str)
                self.pkgrepo("-s {0} rebuild".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))
                self.pkgrepo("-s {0} verify -d".format(repo_path))

                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                dep_str = "depend fmri=feature/test/magic@1.0 type=require\n"
                self.__inject_depend(fmris[0], dep_str)
                self.pkgrepo("-s {0} rebuild".format(repo_path))
                self.pkgrepo("-s {0} verify".format(repo_path))
                self.pkgrepo("-s {0} verify -d".format(repo_path))

        def __make_repo_ignore_dep(self, repo_path, dep_inj):
                """Create a repository with incorporation dependency."""

                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.incorp10))
                self.__inject_depend(fmris[0], dep_inj)
                self.pkgrepo("-s {0} rebuild".format(repo_path))

        def __run_verify_with_ignore_file(self, repo_path, ientry, ifpath,
            exit1=0, exit2=0):
                """Run pkgrepo verify with ignored dep files."""

                with open(ifpath, "w") as iff:
                        iff.write(ientry)
                self.pkgrepo("-s {0} verify -i {1}".format(repo_path, ifpath),
                    exit=exit1)
                self.pkgrepo("-s {0} verify -i {1} -d".format(repo_path, ifpath),
                    exit=exit2)

        def test_30_verify_ignore_pkgs(self):
                """Test if supplied ignored packages in ignored dep files are
                handled properly."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test1".format(
                    repo_path))
                self.pkgsend_bulk(repo_path, (self.amber10, self.amber20))
                ifpath = os.path.join(self.test_root, "tmp",
                    "ignored_dep_file")

                # Test invalid entry causes failure.
                ientry = "tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                ientry = "pkg=tree@x.1"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                ientry = "pkg=amber depend=tree@x.1"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                ientry = "pkg=amber min_ver=4abc* depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                ientry = "pkg=amber max_ver=x.1 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                ientry = "pkg=tree@x.1 unknown=2"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                ientry = "pkg=tree@x.1 unknown1=2, unknown2=\"u\""
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                # Test bad file path causes failure.
                badifpath = os.path.join(self.test_root, "tmp",
                    "bad_ignored_dep_file")
                self.pkgrepo("-s {0} verify -i {1}".format(repo_path, badifpath),
                    exit=1)
                self.pkgrepo("-s {0} verify -i {1} -d".format(repo_path, badifpath),
                    exit=1)

                # Test file with arbitary new line or other space symbols does
                # not cause failure.
                ientry = "   pkg=amber   \t\t depend=tree   \n\t\r\n\n"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                # Test with comment line
                ientry = " # this comments test \npkg=amber depend=tree\n"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                # Test duplicate entries will not cause problem.
                ientry = "pkg=amber   depend=tree\npkg=amber   depend=tree"
                with open(ifpath, "w") as iff:
                        iff.write(ientry)
                self.pkgrepo("-s {0} verify -i {1}".format(repo_path, ifpath))
                # Test in -d mode, ignored_dep_file will not be used.
                self.pkgrepo("-s {0} verify -i {1} -d".format(repo_path, ifpath),
                    exit=1)

                # Test min version bound
                ientry = "pkg=amber min_ver=1.0 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber min_ver=1 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber min_ver=0.9.1 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber min_ver=1.0-0:20110804T203458Z depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber min_ver=1.0-1:20110804T203458Z depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                ientry = "pkg=amber min_ver=1.0-0:20110804T203459Z depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                ientry = "pkg=amber min_ver=0.5 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber min_ver=0.5-2 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber min_ver=2.0 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                ientry = "pkg=amber min_ver=2.5 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                # Test max version bound
                ientry = "pkg=amber max_ver=2 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber max_ver=2.0 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber max_ver=2.0.1 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber max_ver=1.9.1 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                ientry = "pkg=amber max_ver=2.0-0 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber max_ver=2.0-0:20110804T203458Z " \
                    "depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber max_ver=2.0-0:20110804T203457Z " \
                    "depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                ientry = "pkg=amber max_ver=2.5-0:20110804T203457Z " \
                    "depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber max_ver=2.5 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=amber max_ver=1.0 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                # Test combination of max and min bound.
                ientry = "pkg=amber min_ver=1.0 max_ver=2.0 depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                # Test with publisher specified.
                ientry = "pkg=pkg://test1/amber depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=pkg://test2/amber depend=tree"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                # Test gaps between two pairs of min and max version bounds.
                self.pkgsend_bulk(repo_path, (self.amber30))
                ientry = "pkg=amber min_ver=1.0 max_ver=1.0 depend=tree\n" \
                    "pkg=amber min_ver=3.0 max_ver=3.5 depend=bronze\n"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

        def test_31_verify_ignore_deps(self):
                """ Test if dependencies specified in ignored dep files are
                handled correctly."""

                repo_path = self.dc.get_repodir()
                ifpath = os.path.join(self.test_root, "tmp",
                    "ignored_dep_file")
                dep_inj = "depend fmri=tree type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "pkg=incorp@1.0 depend=tree"
                with open(ifpath, "w") as iff:
                        iff.write(ientry)
                self.pkgrepo("-s {0} verify -i {1}".format(repo_path, ifpath))
                self.pkgrepo("-s {0} verify -i {1} -d".format(repo_path, ifpath),
                    exit=1)

                dep_inj = "depend fmri=tree@1.0-1.1:20110804T203458Z " \
                    "type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "pkg=incorp depend=tree@1.0"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=incorp depend=tree@1.0-1"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=incorp depend=tree@1.0-1.1"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "pkg=incorp depend=tree@1.0-1.1:20110804T203458Z"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                dep_inj = "depend fmri=tree@1.0 type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "pkg=incorp depend=tree@1.0,5.11"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                dep_inj = "depend fmri=tree@1.0 type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "depend=tree@1.0,5.11-0 pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                dep_inj = "depend fmri=tree@1.0 type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "depend=tree@1.0,5.11-0:20110804T203458Z pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                # Test multiple ignore entries or multiple dependency actions.
                dep_inj = "depend fmri=tree@1.0 type=require\n" \
                    "depend fmri=forest@1.0 type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "depend=tree@1.0 depend=forest@1.0 pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                ientry = "depend=tree@1.0 pkg=incorp\n"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                dep_inj = "depend fmri=tree@1.0 type=require\n" \
                    "depend fmri=tree@1.1 type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "depend=tree@1 pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                dep_inj = "depend fmri=tree type=require\n"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "pkg=incorp depend=tree@1.0\npkg=incorp depend=tree\n"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                # Test multiple files input.
                dep_inj = "depend fmri=tree@1.0 type=require\n" \
                    "depend fmri=forest@1.0 type=require\n"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                i1entry = "depend=tree@1.0 pkg=incorp\n"
                with open(ifpath, "w") as iff:
                        iff.write(i1entry)
                i2entry = "depend=forest@1.0 pkg=incorp\n"
                if2path = os.path.join(self.test_root, "tmp",
                    "ignored_dep_file2")
                with open(if2path, "w") as iff:
                        iff.write(i2entry)
                self.pkgrepo("-s {0} verify -i {1} -i {2}".format(repo_path, ifpath,
                    if2path))
                self.pkgrepo("-s {0} verify -i {1} -i {2} -d".format(repo_path, ifpath,
                    if2path), exit=1)

                # Test if there is no version limit for dependency, then it
                # should not be ignored unless user specifies an ignored
                # package without version as well.
                dep_inj = "depend fmri=tree type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "depend=tree@1.0 pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                # Test more wrong versions.
                dep_inj = "depend fmri=tree@1 type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "depend=tree@1.0 pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                dep_inj = "depend fmri=tree@1.0,5.11-0 type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "depend=tree@1.0,5.11-1:20110804T203458Z pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                dep_inj = "depend fmri=tree@1.0,5.11-0:20120804T203458Z " \
                    "type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "depend=tree@1.0,5.11-1:20110804T203458Z pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

                # Test giving publisher for both dependency and ignored pkg
                # works.
                dep_inj = "depend fmri=pkg://test/tree@1.0 type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "depend=pkg://test/tree@1.0 pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                # Test giving publisher for only dependency works.
                ientry = "depend=tree@1.0 pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                # Test giving publisher for ignored pkg works.
                dep_inj = "depend fmri=tree@1.0 type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "depend=pkg://test/tree@1.0 pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit2=1)

                # Test wrong publisher will not work.
                dep_inj = "depend fmri=pkg://test/tree@1.0 type=require"
                self.__make_repo_ignore_dep(repo_path, dep_inj)
                ientry = "depend=pkg://test1/tree@1.0 pkg=incorp"
                self.__run_verify_with_ignore_file(repo_path, ientry, ifpath,
                    exit1=1, exit2=1)

        def test_verify_ignore_non_certificate_file_or_directory(self):
                """Ensure that invalid certificate files and directories
                are ignored."""
                repo_path = self.dc.get_repodir()
                repo = self.dc.get_repo()
                trust_anchor_dir = repo.cfg.get_property("repository",
                    "trust-anchor-directory")
                cert_path = os.path.join(trust_anchor_dir, "foo.pem")
                cert_dir = os.path.join(trust_anchor_dir, "foo")
                file_created = False
                dir_created = False

                # Test certificate load will not fail with a directoy in
                # the trust anchor directory
                if not os.path.exists(cert_dir):
                        dir_created = True
                        os.makedirs(cert_dir)
                self.pkgrepo("-s {0} verify".format(repo_path))
                if dir_created:
                        os.rmdir(cert_dir)

                # Test certificate load will not fail with an invalid 
                # certificate file in the trust anchor directory
                if not os.path.exists(cert_path):
                        file_created = True
                        open(cert_path, 'w').close()
                self.pkgrepo("-s {0} verify".format(repo_path))
                if file_created:
                        os.remove(cert_path)

        def __inject_truncate_file(self, path):
                fpath = self.__get_file_path(path)
                self.cmdline_run("/usr/bin/truncate --size 5 {path}".format(
                    path=fpath), coverage=False)
                return fpath

        def test_verify_truncated_file(self):
                """Test that verify handles the case of truncated files."""

                repo_path = self.dc.get_repodir()

                # publish a single package and truncate a file in it
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                truncate_file = self.__inject_truncate_file("tmp/truck1")

                self.pkgrepo("-s {0} verify".format(repo_path), exit=1)
                self.assertTrue(truncate_file in self.output)
                self.assertTrue(
                    self.output.count("ERROR: Corrupted gzip file") == 1)                

        def __get_fhashes(self, repodir, pub):
                """Returns a list of file hashes for the publisher
                pub in a given repository."""
                fhashes = []
                files_dir = os.path.sep.join(["publisher", pub, "file"])
                for dirpath, dirs, files in os.walk(os.path.join(repodir,
                    files_dir)):
                        fhashes.extend(files)
                return fhashes

        def test_32_fix_brokenmanifest(self):
                """Test that fix operations correct a bad manifest in a file
                repo."""

                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                self.pkgsign(repo_path, "\*")

                self.pkgrepo("-s {0} fix".format(repo_path))

                valid_hashes = self.__get_fhashes(repo_path, "test")
                self.debug(valid_hashes)
                bad_path = self.__inject_badsig(fmris[0])
                self.pkgrepo("-s {0} fix".format(repo_path))
                self.assertTrue(fmris[0] in self.output)
                self.assertTrue(not os.path.exists(bad_path))

                # check our quarantine dir has been created
                q_dir = os.path.sep.join([repo_path, "publisher", "test",
                    "pkg5-quarantine"])
                self.assertTrue(os.path.exists(q_dir))

                # check the broken manifest is in the quarantine dir
                mf_path_sub = bad_path.replace(
                    os.path.sep.join([repo_path, "publisher", "test"]), "")
                # quarantined items are stored in a new tmpdir per-session
                q_dir_tmp = os.listdir(q_dir)[0]
                q_mf_path = os.path.sep.join([q_dir, q_dir_tmp, mf_path_sub])
                self.assertTrue(os.path.exists(q_mf_path))

                # make sure the package no longer appears in the catalog
                self.pkgrepo("-s {0} list -F tsv".format(repo_path))
                self.assertTrue(fmris[0] not in self.output)

                # ensure that only the manifest was quarantined - file hashes
                # were left alone.
                remaining_hashes = self.__get_fhashes(repo_path, "test")
                self.assertTrue(set(valid_hashes) == set(remaining_hashes))

                # finally, ensure we can republish this package
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                self.pkgrepo("-s {0} list -F tsv".format(repo_path))
                self.assertTrue(fmris[0] in self.output)

        def test_33_fix_brokenfile(self):
                """Test that operations that cause us to fix a file shared
                by several packages cause all of those packages to be
                quarantined.

                This also tests the -v option of pkg fix, which prints the
                pkgrepo verify output and prints details of which files are
                being quarantined.
                """

                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.tree10,
                    self.trucknd10))
                self.pkgrepo("-s {0} fix".format(repo_path))
                bad_file = self.__inject_badhash("tmp/truck1")

                old_hashes = self.__get_fhashes(repo_path, "test1")

                self.pkgrepo("-s {0} fix -v".format(repo_path))

                # since the file was shared by two manifests, we should get
                # the manifest name printed twice: once when we encounter the
                # broken file, then again when we print the summary of which
                # packages need to be republished.
                self.assertTrue(self.output.count(fmris[0]) == 2)
                self.assertTrue(self.output.count(fmris[1]) == 2)
                self.assertTrue(self.output.count("ERROR: Invalid file hash") == 2)

                # the bad file name gets printed 3 times, once for each time
                # a manifest references it and verify discovered the error,
                # and once when we report where the file was moved to.
                self.assertTrue(self.output.count(bad_file) == 3)

                # check the broken file is in the quarantine dir and that
                # we printed where it moved to
                bad_file_sub = bad_file.replace(
                    os.path.sep.join([repo_path, "publisher", "test"]), "")
                # quarantined items are stored in a new tmpdir per-session
                q_dir = os.path.sep.join([repo_path, "publisher", "test",
                    "pkg5-quarantine"])
                q_dir_tmp = os.listdir(q_dir)[0]
                q_file_path = os.path.normpath(
                    os.path.sep.join([q_dir, q_dir_tmp, bad_file_sub]))
                self.assertTrue(os.path.exists(q_file_path))
                self.debug(q_file_path)
                self.assertTrue(q_file_path in self.output)

                remaining_hashes = self.__get_fhashes(repo_path, "test1")
                # check that we only quarantined the bad hash file
                self.assertTrue(set(remaining_hashes) == \
                    set(old_hashes) - set(os.path.basename(bad_file)))

                # Make sure the repository is now clean, and remains so even
                # after we republish the packages, and that all file content is
                # replaced.
                self.pkgrepo("-s {0} fix".format(repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.tree10,
                    self.trucknd10))
                new_hashes = self.__get_fhashes(repo_path, "test1")
                self.assertTrue(set(new_hashes) == set(old_hashes))
                self.pkgrepo("-s {0} fix".format(repo_path))

        def test_34_fix_brokenperm(self):
                """Tests that when running fix as an unpriviliged user that we
                fail to fix the repository."""

                repo_path = self.dc.get_repodir()

                shutil.rmtree(repo_path)
                os.mkdir(repo_path)
                os.chmod(repo_path, 0o777)
                self.pkgrepo("create {0}".format(repo_path), su_wrap=True)
                self.pkgrepo("set -s {0} publisher/prefix=test".format(repo_path),
                    su_wrap=True)
                # publish a single package and break it
                fmris = self.pkgsend_bulk(repo_path, (self.truck10),
                    su_wrap=True)
                # this breaks the permissions of one of the manifests and
                # chowns is such that we shouldn't be able to quarantine it.
                bad_path = self.__inject_perm(fmri_str=fmris[0], chown=True)

                self.pkgrepo("-s {0} fix".format(repo_path), exit=1, stderr=True,
                    su_wrap=True)
                self.assertTrue(bad_path in self.errout)
                # the fix should succeed now, but not emit any output, because
                # it's running as root, and the permissions are fine according
                # to a root user
                self.pkgrepo("-s {0} fix".format(repo_path))
                # but we should still be able to warn about the bad path for
                # pkg5srv access.
                self.pkgrepo("-s {0} verify".format(repo_path))
                self.assertTrue("WARNING: " in self.output)

        def test_35_fix_unsupported_repo(self):
                """Tests that when running fix on a v3 repo fails"""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create --version=3 {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgrepo("-s {0} fix".format(repo_path), exit=1)
                self.assertTrue("only version 4 repositories are supported." in
                    self.errout)

        def test_36_fix_empty_missing_pub(self):
                """Test that we can attempt to fix a repository that contains a
                publisher with no packages, and that we fail on missing pubs"""

                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                self.pkgrepo("-s {0} add-publisher empty".format(repo_path))
                self.pkgrepo("-s {0} fix -p test".format(repo_path))
                self.pkgrepo("-s {0} fix -p missing".format(repo_path), exit=1)
                self.assertTrue("no matching publishers" in self.errout)

        def test_37_fix_dependency(self):
                """Test with dependency errors, fix will fail."""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                self.pkgsend_bulk(repo_path, (self.wtinstallhold20,
                    self.amber10))
                self.dc.start()
                self.pkgrepo("-s {0} fix -v".format(repo_path), exit=1)

                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.illegaldep10))

                # Test bad depend version number causes reporting error.
                badversion = "depend fmri=pkg:/amber@1.x type=require"
                self.__inject_depend(fmris[0], badversion)
                self.pkgrepo("-s {0} rebuild".format(repo_path))
                self.pkgrepo("-s {0} fix -v".format(repo_path), exit=1)

                # Test bad depend package name causes reporting error.
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} set publisher/prefix=test".format(
                    repo_path))
                fmris = self.pkgsend_bulk(repo_path, (self.illegaldep10))
                badname = "depend fmri=pkg:/_amber@1.0 type=require"
                self.__inject_depend(fmris[0], badname)
                self.pkgrepo("-s {0} rebuild".format(repo_path))
                self.pkgrepo("-s {0} fix".format(repo_path), exit=1)

        def test_38_invalid_repo(self):
                """Test that trying to open an invalid repository is handled
                correctly"""

                tmpdir = tempfile.mkdtemp(dir=self.test_root)

                with open(os.path.join(tmpdir, "pkg5.image"), "w") as f:
                    f.write("[image]\nversion = 2")

                self.assertRaises(sr.RepositoryInvalidError, sr.Repository, 
                    root=tmpdir)

        def test_39_remove_publisher(self):
                """Verify that remove-publisher subcommand works as expected."""

                # Create a repository.
                repo_path = os.path.join(self.test_root, "repo")
                self.create_repo(repo_path)

                # Verify invalid publisher prefixes are rejected gracefully.
                self.pkgrepo("-s {0} remove-publisher !valid".format(repo_path), exit=1)
                self.pkgrepo("-s {0} remove-publisher file:{1}".format(repo_path,
                    repo_path), exit=1)
                self.pkgrepo("-s {0} remove-publisher valid !valid".format(repo_path),
                    exit=1)

                # Verify that remove-publisher will exit with complete failure
                # if no publisher in the repo.
                self.pkgrepo("-s {0} remove-publisher example.com".format(
                    repo_path), exit=1)

                # Verify that single publisher can be removed at a time, and
                # if it is default publisher, the prefix field is unset.
                self.pkgrepo("-s {0} add-publisher example.com".format(
                    repo_path))

                # If a depot is running, this will trigger a reload of the
                # configuration data.
                self.dc.refresh()

                # Publish some packages.
                self.pkgsend_bulk(repo_path, (self.tree10, self.amber10,
                    self.amber20, self.truck10, self.truck20))
                self.pkgrepo("-s {0} remove-publisher example.com".format(
                    repo_path))
                self.assertTrue("has been unset" in self.output)
                self.pkgrepo("get -s {0} -HFtsv publisher/prefix".format(repo_path))
                expected = """\
publisher\tprefix\t""
"""
                self.assertEqualDiff(expected, self.output)
                pdir = os.path.join(repo_path, "publisher", "example.com")
                self.assertTrue(not os.path.exists(pdir))

                # Verify that multiple publishers can be removed at a time
                # if there is a default one, the prefix field in repo con-
                # figuration file will be set to empty
                self.pkgrepo("-s {0} add-publisher example.com example.net".format(
                    repo_path))
                self.pkgrepo("-s {0} remove-publisher example.com example.net".format(
                    repo_path))
                self.assertTrue("has been unset"
                    in self.output)
                self.pkgrepo("get -s {0} -HFtsv publisher/prefix".format(repo_path))
                expected = """\
publisher\tprefix\t""
"""
                self.assertEqualDiff(expected, self.output)
                pdir = os.path.join(repo_path, "publisher", "example.com")
                self.assertTrue(not os.path.exists(pdir))
                pdir = os.path.join(repo_path, "publisher", "example.net")
                self.assertTrue(not os.path.exists(pdir))

                # Verify that if one publisher is removed and only one left
                # if the removed one a default one, the prefix field in repo con-
                # figuration file will be set to the one left
                self.pkgrepo("-s {0} add-publisher example.com example.net".format(
                    repo_path))
                self.pkgrepo("-s {0} remove-publisher example.com".format(
                    repo_path))
                self.assertTrue("the only publisher left" in self.output)
                self.pkgrepo("get -s {0} -HFtsv publisher/prefix".format(repo_path))
                expected = """\
publisher\tprefix\texample.net
"""
                self.assertEqualDiff(expected, self.output)
                pdir = os.path.join(repo_path, "publisher", "example.com")
                self.assertTrue(not os.path.exists(pdir))
                pdir = os.path.join(repo_path, "publisher", "example.net")
                self.assertTrue(os.path.exists(pdir))

                # Verify that remove-publisher will exit with complete failure
                # if all publishers do not exist.
                self.pkgrepo("-s {0} remove-publisher example.some example.what".format(
                    repo_path), exit=1)

                # Verify that remove-publisher will exit with complete failure if
                # only some publishers already exist.
                self.pkgrepo("-s {0} remove-publisher example.net example.org".format(
                    repo_path), exit=1)
                pdir = os.path.join(repo_path, "publisher", "example.net")
                self.assertTrue(os.path.exists(pdir))
                self.pkgrepo("get -s {0} -HFtsv publisher/prefix".format(repo_path))
                expected = """\
publisher\tprefix\texample.net
"""
                self.assertEqualDiff(expected, self.output)

                # Verify that dry-run will not remove anything, and print correct
                # message
                # First publish some packages
                self.pkgsend_bulk(repo_path, (self.tree10, self.amber10,
                    self.amber20, self.truck10, self.truck20))

                # Secondly copy the whole publisher folder into a tmp folder
                dry_pubpath = os.path.join(repo_path, "tmp_dry", "example.net")
                pubpath = os.path.join(repo_path, "publisher", "example.net")
                misc.copytree(pubpath, dry_pubpath)
                self.pkgrepo("-s {0} remove-publisher -n example.net".format(
                    repo_path))
                expected = """\
Removing publisher(s)\n\
\'example.net\'\t(3 package(s))
"""
                self.assertEqualDiff(expected, self.output)

                # Thirdly check whether two folders are identical
                self.cmdline_run("/usr/bin/gdiff {pub_path} {dry_path}".format(
                    pub_path=pubpath, dry_path=dry_pubpath),
                    coverage=False)

                self.pkgrepo("get -s {0} -HFtsv publisher/prefix".format(repo_path))
                expected = """\
publisher\tprefix\texample.net
"""
                self.assertEqualDiff(expected, self.output)

                # Verify that if one publisher is removed and there are
                # more than one left, and one of the removed publishers
                # was the default publisher, that we unset the publisher/prefix
                # property.
                self.pkgrepo("-s {0} add-publisher example.com example.org".format(
                    repo_path))
                self.pkgrepo("-s {0} remove-publisher example.net".format(
                    repo_path))
                self.assertTrue("has been unset" in self.output)
                self.pkgrepo("get -s {0} -HFtsv publisher/prefix".format(repo_path))
                expected = """\
publisher\tprefix\t""
"""
                self.assertEqualDiff(expected, self.output)
                pdir = os.path.join(repo_path, "publisher", "example.net")
                self.assertTrue(not os.path.exists(pdir))

                # Verify that inaccessible publishers are handled correctly
                shutil.rmtree(repo_path)
                os.system("chown noaccess {0}".format(self.test_root))
                self.pkgrepo("create {0}".format(repo_path), su_wrap=True)
                self.pkgrepo("-s {0} add-publisher example.com".format(repo_path))
                self.pkgrepo("-s {0} remove-publisher example.com".format(repo_path),
                    su_wrap=True, exit=1)
                os.system("chown root {0}".format(self.test_root))

                # Verify that synchronous option works as specified.
                shutil.rmtree(repo_path)
                self.pkgrepo("create {0}".format(repo_path))
                self.pkgrepo("-s {0} add-publisher example.com".format(repo_path))
                self.pkgsend_bulk(repo_path, (self.tree10, self.amber10,
                    self.amber20, self.truck10, self.truck20))
                self.pkgrepo("-s {0} remove-publisher --synchronous example.com"
                   .format(repo_path))
                repo_tmp_path = os.path.join(repo_path, "tmp")
                self.assertTrue(os.listdir(repo_tmp_path) == [])
                self.pkgrepo("get -s {0} -HFtsv publisher/prefix".format(repo_path))
                expected = """\
publisher\tprefix\t""
"""
                self.assertEqualDiff(expected, self.output)
                pdir = os.path.join(repo_path, "publisher", "example.com")
                self.assertTrue(not os.path.exists(pdir))

        def test_40_contents(self):
                """Verify that contents subcommand works as expected."""

                repo_path = self.dc.get_repodir()
                repo_uri = self.dc.get_repo_url()

                # Publish some packages.
                plist = self.pkgsend_bulk(repo_uri, (self.tree10, self.amber10,
                    self.amber20))

                # Verify graceful exit if invalid or incomplete set of
                # options specified.
                self.pkgrepo("contents", exit=2)
                self.pkgrepo("contents -s bogus://location list", exit=1)

                # Verify graceful exit for bad repository.
                self.pkgrepo("contents -s /no/such/repository", exit=1)

                # Verify graceful exit if invalid package name given.
                self.pkgrepo("contents -s {0} ^notvalid".format(repo_path), exit=1)

                # Verify graceful exit if no matching package found.
                self.pkgrepo("contents -s {0} nosuchpackage".format(repo_path), exit=1)

                # Verify default output when listing all packages for both
                # file and http cases:
                for src in (repo_path, repo_uri):
                        self.pkgrepo("contents -s {0}".format(src))
                        for p in plist:
                                self.assertTrue(self.__get_manifest_contents(p)
                                    in self.output)

                # Verify ability to display specific packages but only using
                # file repository for test efficiency.

                # Verify ability to display specific packages.
                self.pkgrepo("contents -s {0} amber@2.0".format(repo_path))
                self.assertEqualDiff(self.__get_manifest_contents(plist[2]),
                    self.output)

                # Verify ability to display multiple packages.
                self.pkgrepo("contents -s {0} tree amber@1.0".format(repo_path))
                for i in range(2):
                        self.assertTrue(self.__get_manifest_contents(plist[i]) in
                            self.output)

                # Verify -m option works fine.
                self.pkgrepo("contents -m -s {0} amber@2.0".format(repo_path))
                self.assertEqualDiff(self.__get_manifest_contents(plist[2]),
                    self.output)

                # Verify -t option works fine.
                self.pkgrepo("contents -s {0} -t set tree".format(repo_path))
                self.assertTrue("set" in self.output and "file" not in self.output)

                # Verify graceful exit if no matching action type specified.
                self.pkgrepo("contents -s {0} -t nosuchtype tree".format(repo_path),
                    exit=1)

                # Add packages for a different publisher.
                self.pkgrepo("set -s {0} publisher/prefix=test2".format(repo_path))
                self.pkgsend_bulk(repo_path, (self.truck10, self.zoo10))

                # Verify that patterns matching packages only provided by one
                # publisher will not result in partial failure.
                self.pkgrepo("contents -s {0} zoo".format(repo_path))


class TestPkgrepoMultiRepo(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo10 = """
            open foo@1.0,5.11-0:20110804T203458Z
            close"""

        foo20t1 = """
            open foo@2.0,5.11-0:20120804T203458Z
            close"""

        foo20t2 = """
            open foo@2.0,5.11-0:20130804T203458Z
            close"""

        bar10 = """
            open bar@1.0,5.11-0:20130804T203458Z
            close"""

        moo10 = """
            open moo@1.0,5.11-0:20130804T203458Z
            close"""

        noo10 = """
            open noo@1.0,5.11-0:20130804T203458Z
            close"""

        def setUp(self):
                """Create four repositories. Three with the same publisher name
                and one with a different publisher name.
                """

                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test1", "test1", "test1"])

                self.rurl1 = self.dcs[1].get_repo_url()
                self.durl1 = self.dcs[1].get_depot_url()
                self.rdir1 = self.dcs[1].get_repodir()

                self.rurl2 = self.dcs[2].get_repo_url()
                self.durl2 = self.dcs[2].get_depot_url()
                self.rdir2 = self.dcs[2].get_repodir()

                self.rurl3 = self.dcs[3].get_repo_url()
                self.durl3 = self.dcs[3].get_depot_url()
                self.rdir3 = self.dcs[3].get_repodir()

                self.rurl4 = self.dcs[4].get_repo_url()
                self.rdir4 = self.dcs[4].get_repodir()
                self.pkgsend_bulk(self.rurl4, (self.moo10, self.noo10))

                self.rurl5 = self.dcs[5].get_repo_url()
                self.rdir5 = self.dcs[5].get_repodir()

        def test_01_diff(self):
                """Verify that diff subcommand works as expected."""

                # Verify invalid input will cause failure.
                self.pkgrepo("diff".format(self.rurl1), exit=2)
                self.pkgrepo("diff -s {0}".format(self.rurl1), exit=2)
                self.pkgrepo("diff {0}".format(self.rurl1), exit=2)
                self.pkgrepo("diff --unknown -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=2)
                self.pkgrepo("diff --unknown -s {0} -s {1} -s {2}".format(
                    self.rurl1, self.rurl2, self.rurl3), exit=2)
                self.pkgrepo("diff --!invalid -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=2)
                self.pkgrepo("diff -s {0} -s {1} invalidarg".format(self.rurl1,
                    self.rurl2), exit=2)
                self.pkgrepo("diff -p +faf -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=1)
                self.pkgrepo("diff -s {0} -s {1}".format(self.rurl1,
                    "+++1a"), exit=1)
                self.pkgrepo("diff -qv -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=2)

                self.dcs[1].start()
                self.dcs[2].start()
                self.dcs[3].start()
                # Verify empty repos comparison with just publisher names.
                self.pkgrepo("diff -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=10)
                self.assertTrue("test1" in self.output and "test2" in
                    self.output)
                self.pkgrepo("diff -s {0} -s {1}".format(self.rurl1,
                    self.rurl3))
                self.pkgrepo("diff -s {0} -s {1}".format(self.durl1,
                    self.durl3))
                self.assertTrue(not self.output)
                self.pkgrepo("diff -p test1 -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=1)
                self.pkgrepo("diff -s {0} -s {1}".format(self.durl1,
                    self.durl2), exit=10)
                self.pkgrepo("diff -p test2 -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=1)
                self.pkgrepo("diff -p test2 -s {0} -s {1}".format(self.durl1,
                    self.durl2), exit=1)
                self.pkgrepo("diff -p test1 -s {0} -s {1}".format(self.rurl1,
                    self.rurl3))

                # Publish some pkgs.
                self.pkgsend_bulk(self.rurl1, (self.foo10))
                self.pkgsend_bulk(self.rurl2, (self.foo10))
                self.pkgsend_bulk(self.rurl3, (self.foo10))
                self.pkgrepo("diff -s {0} -s {1}".format(self.rurl1,
                    self.rurl3))
                self.assertTrue(not self.output)
                self.pkgrepo("diff -v -s {0} -s {1}".format(self.rurl1,
                    self.rurl3))
                self.assertTrue(not self.output)
                self.pkgrepo("diff -v -s {0} -s {1}".format(self.durl1,
                    self.durl3))
                self.pkgrepo("diff -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=10)
                self.assertTrue("test1" in self.output and "test2" in
                    self.output)

                # Test -q option.
                self.pkgrepo("diff -q -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=10)
                self.assertTrue(not self.output)
                self.pkgrepo("diff -q -s {0} -s {1}".format(self.rurl1,
                    self.rurl3))
                self.assertTrue(not self.output)

                self.pkgsend_bulk(self.rurl1, (self.foo20t1))
                self.pkgsend_bulk(self.rurl2, (self.foo20t1))
                self.pkgsend_bulk(self.rurl3, (self.foo20t2))
                self.pkgrepo("diff -s {0} -s {1}".format(self.rurl1,
                    self.rurl3), exit=10)
                self.assertTrue("test1" in self.output)
                self.pkgrepo("diff -v -s {0} -s {1}".format(self.rurl1,
                    self.rurl3), exit=10)
                self.assertTrue("- pkg://test1/foo@2.0,5.11-0:20120804T203458Z" in
                    self.output)
                self.assertTrue("+ pkg://test1/foo@2.0,5.11-0:20130804T203458Z" in
                    self.output)
                self.assertTrue("(1 pkg(s) with 1 version(s) are in both "
                    "repositories.)" in self.output)
                self.assertTrue("test1" in self.output)

                # Test --strict option.
                self.pkgrepo("diff --strict -s {0} -s {1}".format(self.rurl1,
                    self.rurl3), exit=10)
                self.assertTrue("catalog" in self.output)

                self.pkgrepo("diff --strict -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=10)

                # Make repo1 has publishers: test1, test2
                # repo2 has publishers: test2, test3
                # repo3 has publishers: test1, test2
                self.pkgrepo("-s {0} add-publisher test2".format(
                    self.rurl1))
                self.pkgrepo("-s {0} add-publisher test2".format(
                    self.rurl3))
                self.pkgrepo("-s {0} add-publisher test3".format(
                    self.rurl2))
                self.pkgrepo("set -s {0} publisher/prefix=test2".format(
                    self.rurl1))
                self.pkgrepo("set -s {0} publisher/prefix=test3".format(
                    self.rurl2))
                self.pkgrepo("set -s {0} publisher/prefix=test2".format(
                    self.rurl3))
                # Make repo1 test2 the same as repo2 test2
                self.pkgsend_bulk(self.rurl1, (self.foo10, self.foo20t1))
                # Make repo3 test2 the same as repo2 test2
                self.pkgsend_bulk(self.rurl3, (self.foo10, self.foo20t1))

                self.pkgsend_bulk(self.rurl2, (self.bar10, self.moo10))
                # repo1 and repo3 contain same pkgs, but one pkg has different
                # timestamps.
                self.pkgrepo("diff -s {0} -s {1}".format(self.rurl1,
                    self.rurl3), exit=10)
                self.assertTrue("test1" in self.output)
                self.assertTrue("test2" not in self.output)
                self.pkgrepo("diff -q -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=10)
                self.assertTrue(not self.output)

                self.pkgrepo("diff -v -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=10)
                self.assertTrue("- test1" in self.output and "test2" not in
                    self.output and "+ test3" in self.output)
                self.pkgrepo("diff -q -s {0} -s {1}".format(self.rurl1,
                    self.rurl2), exit=10)
                self.assertTrue(not self.output)
                self.pkgrepo("diff --parsable --strict -s {0} -s {1}".format(
                    self.rurl1, self.rurl2), exit=10)
                expected = {
"table_header": ["Publisher", "Repo1 only", "Repo2 only", "In both", "Total"],
"table_data": [["test1", {"packages": 1, "versions": 2},
                None, {"packages": 0, "versions": 0},
                {"packages": 1, "versions": 2}],
                ["test3", None, {"packages": 2, "versions": 2},
    {"packages": 0, "versions": 0}, {"packages": 2, "versions": 2}]],
"table_legend": [["Repo1", self.rurl1],
                 ["Repo2", self.rurl2]],
"nonstrict_pubs": ["test2"]}
                self.assertEqualJSON(json.dumps(expected), self.output)
                self.pkgrepo("diff --parsable --strict -vs {0} -s {1}".format(
                    self.rurl1, self.rurl2), exit=10)
                expected = {
"common_pubs": [{"publisher": "test2", "+": [], "-": [],
    "catalog": {"+": "replaced",
                "-": "replaced"}}],
"minus_pubs": [{"publisher": "test1", "packages": 1, "versions": 2}],
"plus_pubs": [{"publisher": "test3", "packages": 2, "versions": 2}]}
                output = json.loads(self.output)
                self.assertTrue("common_pubs" in output)
                output["common_pubs"][0]["catalog"]["+"] = "replaced"
                output["common_pubs"][0]["catalog"]["-"] = "replaced"
                self.assertEqualJSON(json.dumps(expected),
                    json.dumps(output))
                # Test -p option.
                self.pkgrepo("diff -vp test2 -s {0} -s {1}".format(self.rurl1,
                    self.rurl2))
                self.assertTrue(not self.output)
                # Enable strict check.
                self.pkgrepo("diff -vp test2 --strict -s {0} -s {1}".format(
                    self.rurl1, self.rurl2), exit=10)
                self.assertTrue("test2" in self.output)
                self.pkgrepo("diff -p test2 --strict -s {0} -s {1}".format(
                    self.rurl1, self.rurl2), exit=10)
                self.assertTrue("test2" in self.output)
                self.assertTrue("Repo1:" not in self.output)

                # Test set relationship.
                self.pkgsend_bulk(self.rurl1, (self.bar10))
                self.pkgrepo("diff -s {0} -s {1}".format(self.rurl1,
                    self.rurl3), exit=10)
                self.assertTrue("test1" in self.output)
                self.assertTrue("test2" in self.output and "0 [0]" in \
                    self.output)
                self.pkgrepo("diff --parsable -s {0} -s {1}".format(self.rurl1,
                    self.rurl3), exit=10)
                output = json.loads(self.output)
                # test2 in repo1 is the superset of test2 in repo2.
                self.assertTrue(output["table_data"][1][2]["packages"] == 0)
                self.assertTrue(output["table_data"][1][2]["versions"] == 0)

                self.pkgrepo("diff --parsable -v -s {0} -s {1}".format(
                    self.rurl1, self.rurl3), exit=10)
                output = json.loads(self.output)
                # test2 in repo1 is the superset of test2 in repo2.
                self.assertTrue(output["common_pubs"][1]["-"])
                self.assertTrue(not output["common_pubs"][1]["+"])
                self.assertTrue("common" in output["common_pubs"][1])

                self.pkgsend_bulk(self.rurl3, (self.bar10, self.moo10))
                self.pkgrepo("diff -s {0} -s {1}".format(self.rurl1,
                    self.rurl3), exit=10)
                self.assertTrue("test1" in self.output)
                self.assertTrue("test2" in self.output and "0 [0]" in \
                    self.output)
                self.pkgrepo("diff --parsable -s {0} -s {1}".format(self.rurl1,
                    self.rurl3), exit=10)
                output = json.loads(self.output)
                # test2 in repo1 is the subset of test2 in repo2.
                self.assertTrue(output["table_data"][1][1]["packages"] == 0)
                self.assertTrue(output["table_data"][1][1]["versions"] == 0)

                self.pkgrepo("diff --parsable -v -s {0} -s {1}".format(
                    self.rurl1, self.rurl3), exit=10)
                output = json.loads(self.output)
                # test2 in repo1 is the superset of test2 in repo2.
                self.assertTrue(not output["common_pubs"][1]["-"])
                self.assertTrue(output["common_pubs"][1]["+"])

                self.pkgrepo("diff -s {0} -s {1}".format(self.rurl1,
                    self.rurl4), exit=10)
                self.assertTrue("test2" in self.output)
                self.assertTrue("test1" in self.output and "-" in \
                    self.output and "0 [0]" in self.output)
                self.pkgrepo("diff --parsable -s {0} -s {1}".format(self.rurl1,
                    self.rurl4), exit=10)
                output = json.loads(self.output)
                # test1 in repo4 contains completely different fmris for the
                # the one in repo1.
                self.assertTrue(output["table_data"][0][3]["packages"] == 0)
                self.assertTrue(output["table_data"][0][3]["versions"] == 0)

                # Test clone repositories are exactly the same as the
                # originals.
                self.pkgrecv(self.rurl4, "--clone -d {0}".format(self.rdir5))
                ret = subprocess.call(["/usr/bin/gdiff", "-Naur", "-x",
                    "index", "-x", "trans", self.rdir4, self.rdir5])
                self.assertTrue(ret==0)
                self.pkgrepo("diff -v --strict -s {0} -s {1}".format(
                    self.rurl4, self.rurl5))
                self.assertTrue(not self.output)

                # Test that clone removes all the packages if the source catalog
                # does not exist.
                # Source and destination have the same publishers.
                self.pkgrepo("remove -s {0} -p test1 '*'".format(self.rdir4))
                # Delete the catlog
                repo = self.get_repo(self.rdir4)
                repo.get_catalog('test1').destroy()
                self.pkgrecv(self.rdir4, "--clone -d {0} -p test1".
                        format(self.rdir3))
                expected = "The source catalog 'test1' is empty"
                self.assertTrue(expected in self.output, self.output)

                # Mention all the publishers while cloning
                self.pkgrepo("remove -s {0} '*'".format(self.rdir2))
                repo = self.get_repo(self.rdir2)
                # Delete the catalog
                repo.get_catalog('test2').destroy()
                self.pkgrecv(self.rdir2, "--clone -d {0} -p '*'".
                        format(self.rdir1))
                expected = "The source catalog 'test2' is empty"
                self.assertTrue(expected in self.output, self.output)


class TestPkgrepoHTTPS(pkg5unittest.HTTPSTestClass):

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add file tmp/example_file mode=0555 owner=root group=bin path=/usr/bin/example_path
            close"""

        misc_files = ["tmp/example_file", "tmp/empty", "tmp/verboten"]

        def setUp(self):
                pub = "test"

                pkg5unittest.HTTPSTestClass.setUp(self, [pub],
                    start_depots=True)

                self.url = self.ac.url + "/{0}".format(pub)

                # publish a simple test package
                self.srurl = self.dcs[1].get_repo_url()
                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.srurl, self.example_pkg10)

                #set permissions of tmp/verboten to make it non-readable
                self.verboten = os.path.join(self.test_root, "tmp/verboten")
                os.system("chmod 600 {0}".format(self.verboten))


        def test_01_basics(self):
                """Test that running pkgrepo on an SSL-secured repo works for
                all operations which are valid for network repos"""

                self.ac.start()

                arg_dict = {
                    "cert": os.path.join(self.cs_dir,
                    self.get_cli_cert("test")),
                    "key": os.path.join(self.keys_dir,
                    self.get_cli_key("test")),
                    "url": self.url,
                    "srurl": self.srurl,
                    "empty": os.path.join(self.test_root, "tmp/empty"),
                    "noexist": os.path.join(self.test_root, "octopus"),
                    "verboten": self.verboten,
                }

                # We need an image for seed_ta_dir() to work.
                # TODO: there might be a cleaner way of doing this
                self.image_create()
                # Add the trust anchor needed to verify the server's identity.
                self.seed_ta_dir("ta7")

                # Try all pkgrepo operations which are valid for network repos.
                # pkgrepo info
                self.pkgrepo("-s {url} info --key {key} --cert {cert}"
                   .format(**arg_dict))

                # pkgrepo list
                self.pkgrepo("-s {url} list --key {key} --cert {cert}"
                   .format(**arg_dict))

                # pkgrepo get
                self.pkgrepo("-s {url} get --key {key} --cert {cert}"
                   .format(**arg_dict))

                # pkgrepo refresh
                self.pkgrepo("-s {url} refresh --key {key} --cert {cert}"
                   .format(**arg_dict))

                # pkgrepo rebuild
                self.pkgrepo("-s {url} rebuild --key {key} --cert {cert}"
                   .format(**arg_dict))

                # pkgrepo contents
                self.pkgrepo("-s {url} contents --key {key} --cert {cert}"
                   .format(**arg_dict))

                # pkgrepo diff.
                self.pkgrepo("-s {url} diff --key {key} --cert {cert}"
                   " -s {url} --key {key} --cert {cert}".format(**arg_dict))

                self.pkgrepo("diff --key {key} --cert {cert} -s {url}"
                   " -s {url} --key {key} --cert {cert}".format(**arg_dict),
                   exit=2)

                # Test only provides key and cert to the first repo.
                self.pkgrepo("-s {url} diff --key {key} --cert {cert} "
                    "-s {srurl}".format(**arg_dict))

                self.pkgrepo("-s {url} diff --key {key} --cert {cert} "
                    "-s {url}".format(**arg_dict), exit=1)

                # Test only provides key and cert to the second repo.
                self.pkgrepo("-s {srurl} diff -s {url} --key {key} "
                    "--cert {cert}".format(**arg_dict))

                self.pkgrepo("-s {url} diff -s {url} --key {key} "
                    "--cert {cert}".format(**arg_dict), exit=1)

                # Try without key and cert (should fail)
                self.pkgrepo("-s {url} rebuild".format(**arg_dict), exit=1)

                # Make sure we don't traceback when credential files are invalid
                # Certificate option missing
                self.pkgrepo("-s {url} rebuild --key {key}".format(**arg_dict),
                    exit=1)

                # Key option missing
                self.pkgrepo("-s {url} rebuild --cert {cert}".format(**arg_dict),
                    exit=1)

                # Certificate not found
                self.pkgrepo("-s {url} rebuild --key {key} "
                    "--cert {noexist}".format(**arg_dict), exit=1)

                # Key not found
                self.pkgrepo("-s {url} rebuild --key {noexist} "
                    "--cert {cert}".format(**arg_dict), exit=1)

                # Certificate is empty file
                self.pkgrepo("-s {url} rebuild --key {key} "
                    "--cert {empty}".format(**arg_dict), exit=1)

                # Key is empty file
                self.pkgrepo("-s {url} rebuild --key {empty} "
                    "--cert {cert}".format(**arg_dict), exit=1)

                # No permissions to read certificate 
                self.pkgrepo("-s {url} rebuild --key {key} "
                    "--cert {verboten}".format(**arg_dict), su_wrap=True, exit=1)

                # No permissions to read key 
                self.pkgrepo("-s {url} rebuild --key {verboten} "
                    "--cert {cert}".format(**arg_dict), su_wrap=True, exit=1)


if __name__ == "__main__":
        unittest.main()
