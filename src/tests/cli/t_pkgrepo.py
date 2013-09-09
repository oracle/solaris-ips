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
# Copyright (c) 2010, 2013, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

from pkg.server.query_parser import Query
import os
import pkg
import pkg.catalog
import pkg.depotcontroller as dc
import pkg.fmri as fmri
import pkg.pkggzip
import pkg.misc as misc
import pkg.server.repository as sr
import shutil
import tempfile
import time
import urllib
import urlparse
import unittest

class TestPkgRepo(pkg5unittest.SingleDepotTestCase):
        # Cleanup after every test.
        persistent_setup = False
        # Tests in this suite use the read only data directory.
        need_ro_data = True

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
            add depend fmri=pkg:/tree@1.0 type=require
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
                self.pkgrepo("-s %s" % self.test_root, exit=2)

                # Verify an invalid URI causes an exit 2.
                for baduri in ("file://not/valid", "http://not@$$_-^valid"):
                        self.pkgrepo("info -s %s" % baduri, exit=2)

        def test_01_create(self):
                """Verify pkgrepo create works as expected."""

                # Verify create without a destination exits.
                self.pkgrepo("create", exit=2)

                # Verify create with an invalid URI as an operand exits with 2.
                for baduri in ("file://not/valid", "http://not@$$_-^valid"):
                        self.pkgrepo("create %s" % baduri, exit=2)

                # Verify create works whether -s is used to supply the location
                # of the new repository or it is passed as an operand.  Also
                # verify that either a path or URI can be used to provide the
                # repository's location.
                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                repo_uri = self.dc.get_repo_url()

                # Specify using global option and path.
                self.pkgrepo("create -s %s" % repo_path)
                # This will fail if a repository wasn't created.
                self.dc.get_repo()
                shutil.rmtree(repo_path)

                # Specify using operand and URI.
                self.pkgrepo("create %s" % repo_uri)
                # This will fail if a repository wasn't created.
                self.get_repo(repo_path)
                shutil.rmtree(repo_path)

                # Verify create works for an empty, pre-existing directory.
                os.mkdir(repo_path)
                self.pkgrepo("create %s" % repo_path)
                # This will fail if a repository wasn't created.
                self.get_repo(repo_path)

                # Verify create fails for a non-empty, pre-existing directory.
                self.pkgrepo("create %s" % repo_path, exit=1)

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
                self.assert_(not os.path.exists(repo_path))
                self.pkgrepo("create -s %s --version=3" % repo_path)

                # Verify get handles unknown properties gracefully.
                self.pkgrepo("get -s %s repository/unknown" % repo_uri, exit=1)

                # Verify get returns partial failure if only some
                # properties cannot be found.
                self.pkgrepo("get -s %s repository/origins "
                    "repository/unknown" % repo_uri, exit=3)

                # Verify full default output for both network and file case.
                self.dc.start()
                for uri in (repo_uri, depot_uri):
                        self.pkgrepo("get -s %s" % uri)
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
                self.pkgrepo("get -s %s -Ftsv" % repo_uri)
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
                self.pkgrepo("get -s %s -H" % repo_uri)
                self.assert_(self.output.find("SECTION") == -1)

                # Verify specific get default output and that
                # -H omits headers for specific get output.
                self.pkgrepo("get -s %s publisher/prefix" %
                    repo_uri)
                expected = """\
SECTION    PROPERTY         VALUE
publisher  prefix           test
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("get -s %s -H publisher/prefix "
                    "repository/origins" % repo_uri)
                expected = """\
publisher  prefix           test
repository origins          ()
"""
                self.assertEqualDiff(expected, self.output)

                # Verify specific get tsv output.
                self.pkgrepo("get -s %s -F tsv publisher/prefix" %
                    repo_uri)
                expected = """\
SECTION\tPROPERTY\tVALUE
publisher\tprefix\ttest
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("get -s %s -HF tsv publisher/prefix "
                    "repository/origins" % repo_uri)
                expected = """\
publisher\tprefix\ttest
repository\torigins\t()
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set fails if no property is provided.
                self.pkgrepo("set -s %s" % repo_uri, exit=2)

                # Verify set gracefully handles bad property values.
                self.pkgrepo("set -s %s publisher/prefix=_invalid" %repo_uri,
                    exit=1)

                # Verify set can set single value properties.
                self.pkgrepo("set -s %s publisher/prefix=opensolaris.org" %
                    repo_uri)
                self.pkgrepo("get -s %s -HF tsv publisher/prefix" % repo_uri)
                expected = """\
publisher\tprefix\topensolaris.org
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set can set multi-value properties.
                self.pkgrepo("set -s %s "
                    "'repository/origins=(http://pkg.opensolaris.org/dev "
                    "http://pkg-eu-2.opensolaris.org/dev)'" % repo_uri)
                self.pkgrepo("get -s %s -HF tsv repository/origins" % repo_uri)
                expected = """\
repository\torigins\t(http://pkg.opensolaris.org/dev http://pkg-eu-2.opensolaris.org/dev)
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set can set unknown properties.
                self.pkgrepo("set -s %s 'foo/bar=value'" % repo_uri)
                self.pkgrepo("get -s %s -HF tsv foo/bar" % repo_uri)
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
                self.assert_(not os.path.exists(repo_path))
                self.pkgrepo("create -s %s --version=3" % repo_path)
                self.pkgrepo("set -s %s publisher/prefix=test" % repo_path)

                # Verify setting publisher properties fails for version 3
                # repositories.
                self.pkgrepo("set -s %s -p all "
                    "repository/origins=http://localhost" % repo_uri, exit=1)

                # Create version 4 repository.
                shutil.rmtree(repo_path)
                self.assert_(not os.path.exists(repo_path))
                self.create_repo(repo_path)

                # Verify get handles unknown publishers gracefully.
                self.pkgrepo("get -s %s -p test repository/origins" % repo_uri,
                    exit=1)

                # Add a publisher by setting properties for one that doesn't
                # exist yet.
                self.pkgrepo("set -s %s -p test "
                    "repository/name='package repository' "
                    "repository/refresh-seconds=7200" %
                    repo_uri)

                # Verify get handles unknown properties gracefully.
                self.pkgrepo("get -s %s -p test repository/unknown" % repo_uri,
                    exit=1)

                # Verify get returns partial failure if only some properties
                # cannot be found.
                self.pkgrepo("get -s %s -p all repository/origins "
                    "repository/unknown" % repo_uri, exit=3)

                # Verify full default output for both network and file case.
                self.dc.start()
                for uri in (repo_uri, depot_uri):
                        self.pkgrepo("get -s %s -p all" % uri)
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
                self.pkgrepo("get -s %s -p all -Ftsv" % repo_uri)
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
                self.pkgrepo("get -s %s -p all -H" % repo_uri)
                self.assert_(self.output.find("SECTION") == -1)

                # Verify specific get default output and that
                # -H omits headers for specific get output.
                self.pkgrepo("get -s %s -p all publisher/prefix" %
                    repo_uri)
                expected = """\
PUBLISHER SECTION    PROPERTY         VALUE
test      publisher  prefix           test
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("get -s %s -p all -H publisher/prefix "
                    "repository/origins" % repo_uri)
                expected = """\
test      publisher  prefix           test
test      repository origins          ()
"""
                self.assertEqualDiff(expected, self.output)

                # Verify specific get tsv output.
                self.pkgrepo("get -s %s -p all -F tsv publisher/prefix" %
                    repo_uri)
                expected = """\
PUBLISHER\tSECTION\tPROPERTY\tVALUE
test\tpublisher\tprefix\ttest
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("get -s %s -HF tsv -p all publisher/prefix "
                    "repository/origins" % repo_uri)
                expected = """\
test\tpublisher\tprefix\ttest
test\trepository\torigins\t()
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set fails if no property is provided.
                self.pkgrepo("set -s %s -p test" % repo_uri, exit=2)

                # Verify set gracefully handles bad property values and
                # properties that can't be set.
                self.pkgrepo("set -s %s -p test publisher/alias=_invalid" %
                    repo_uri, exit=1)
                self.pkgrepo("set -s %s -p test publisher/prefix=_invalid" %
                    repo_uri, exit=2)

                # Verify set can set single value properties.
                self.pkgrepo("set -s %s -p all publisher/alias=test1" %
                    repo_uri)
                self.pkgrepo("get -s %s -p all -HF tsv publisher/alias "
                    "publisher/prefix" % repo_uri)
                expected = """\
test\tpublisher\talias\ttest1
test\tpublisher\tprefix\ttest
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set can set multi-value properties.
                self.pkgrepo("set -s %s -p all "
                    "'repository/origins=(http://pkg.opensolaris.org/dev "
                    "http://pkg-eu-2.opensolaris.org/dev)'" % repo_uri)
                self.pkgrepo("get -s %s -p all -HF tsv repository/origins" %
                    repo_uri)
                expected = """\
test\trepository\torigins\t(http://pkg-eu-2.opensolaris.org/dev/ http://pkg.opensolaris.org/dev/)
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set can not set unknown properties.
                self.pkgrepo("set -s %s -p all 'foo/bar=value'" % repo_uri,
                    exit=2)

                # Add another publisher by setting a property for it.
                self.pkgrepo("set -p test2 -s %s publisher/alias=''" % repo_uri)

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
                self.pkgrepo("get -s %s -p all -HFtsv" % repo_uri)
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("get -s %s -p test -p test2 -HFtsv" % repo_uri)
                self.assertEqualDiff(expected, self.output)

                # Verify get can list multiple specific properties for
                # multiple specific publishers correctly.
                expected = """\
test\tpublisher\talias\ttest1
test2\tpublisher\talias\t""
"""
                self.pkgrepo("get -s %s -HFtsv -p test -p test2 "
                    "publisher/alias" % repo_uri)
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
                self.pkgrepo("get -s %s -p test -p bogus -HFtsv" % repo_uri,
                    exit=3)
                self.assertEqualDiff(expected, self.output)

                # Verify set can set multiple properties for all or specific
                # publishers when multiple publishers are known.
                self.pkgrepo("set -s %s -p all "
                    "repository/description='Support Repository'" % repo_uri)
                expected = """\
test\trepository\tdescription\tSupport\\ Repository
test2\trepository\tdescription\tSupport\\ Repository
"""
                self.pkgrepo("get -s %s -HFtsv -p all repository/description" %
                    repo_uri)
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("set -s %s -p test2 "
                    "repository/description='2nd Support Repository'" %
                        repo_uri)
                expected = """\
test\trepository\tdescription\tSupport\\ Repository
test2\trepository\tdescription\t2nd\\ Support\\ Repository
"""
                self.pkgrepo("get -s %s -HFtsv -p all repository/description" %
                    repo_uri)
                self.assertEqualDiff(expected, self.output)

        def __test_info(self, repo_path, repo_uri):
                """Private function to verify publisher subcommand behaviour."""

                # Verify subcommand behaviour for empty repository and -H
                # functionality.
                self.pkgrepo("info -s %s" % repo_uri)
                expected = """\
PUBLISHER PACKAGES STATUS           UPDATED
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("info -s %s -H" % repo_uri)
                expected = """\
"""
                self.assertEqualDiff(expected, self.output)

                # Set a default publisher.
                self.pkgrepo("set -s %s publisher/prefix=test" % repo_path)

                # If a depot is running, this will trigger a reload of the
                # configuration data.
                self.dc.refresh()

                # Publish some packages.
                self.pkgsend_bulk(repo_uri, (self.tree10, self.amber10,
                    self.amber20, self.truck10, self.truck20))

                # Verify info handles unknown publishers gracefully.
                self.pkgrepo("info -s %s -p unknown" % repo_uri, exit=1)

                # Verify info returns partial failure if only some publishers
                # cannot be found.
                self.pkgrepo("info -s %s -p test -p unknown" % repo_uri, exit=3)

                # Verify full default output.
                repo = self.get_repo(repo_path)
                self.pkgrepo("info -s %s -H" % repo_uri)
                cat = repo.get_catalog("test")
                cat_lm = cat.last_modified.isoformat()
                expected = """\
test      3        online           %sZ
""" % cat_lm
                self.assertEqualDiff(expected, self.output)

                # Verify full tsv output.
                self.pkgrepo("info -s %s -HF tsv" % repo_uri)
                expected = """\
test\t3\tonline\t%sZ
""" % cat_lm
                self.assertEqualDiff(expected, self.output)

                # Verify info specific publisher default output.
                self.pkgrepo("info -s %s -H -p test" % repo_uri)
                expected = """\
test      3        online           %sZ
""" % cat_lm
                self.assertEqualDiff(expected, self.output)

                # Verify info specific publisher tsv output.
                self.pkgrepo("info -s %s -HF tsv -p test" % repo_uri)
                expected = """\
test\t3\tonline\t%sZ
""" % cat_lm
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

                # Create a repository and verify http-based repository access.
                self.assert_(not os.path.exists(repo_path))
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
                self.pkgrepo("rebuild -s %s" % repo_uri)
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path)
                nlm = repo.get_catalog("test").last_modified.isoformat()
                self.assertNotEqual(lm, nlm)

                #
                # Verify rebuild --no-index works for an empty repository.
                #
                lm = repo.get_catalog("test").last_modified.isoformat()
                self.pkgrepo("rebuild -s %s --no-index" % repo_uri)
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path)
                nlm = repo.get_catalog("test").last_modified.isoformat()
                self.assertNotEqual(lm, nlm)

                #
                # Verify rebuild --no-catalog works for an empty repository,
                # and that the catalog itself does not change.
                #
                lm = repo.get_catalog("test").last_modified.isoformat()
                self.pkgrepo("rebuild -s %s --no-catalog" % repo_uri)
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path)
                nlm = repo.get_catalog("test").last_modified.isoformat()
                self.assertEqual(lm, nlm)

                #
                # Publish some packages and verify they are known afterwards.
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
                self.pkgrepo("rebuild -s %s --no-catalog" % repo_uri)
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
                self.pkgrepo("rebuild -s %s --no-catalog" % repo_uri)
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
                self.pkgrepo("rebuild -s %s" % repo_uri)
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
                        'set name=pkg.fmri value=%s\n' % plist[1]]]
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

                self.pkgrepo("rebuild -s %s --no-index" % repo_uri)
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
                except Exception, e:
                        self.debug("query exception: %s" % e)
                        self.assert_(isinstance(e,
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
                self.pkgrepo("create %s" % repo_path)
                self.pkgrepo("add-publisher -s %s test" % repo_path)
                repo = self.get_repo(repo_path, read_only=True)
                cat = repo.get_catalog(pub="test")
                cat.destroy()
                self.pkgrepo("rebuild -s %s" % repo_path)
                shutil.rmtree(repo_path)

                # Create a repository and verify network-based repository
                # access.
                self.assert_(not os.path.exists(repo_path))
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

                self.pkgrepo("rebuild -s %s -p test" % repo_uri)
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
                self.pkgrepo("rebuild -s %s" % repo_uri)
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
                self.assert_(not os.path.exists(repo_path))
                self.create_repo(repo_path)
                pfmri = self.pkgsend_bulk(repo_path, """
                    open pkg://test/foo@1.0
                    close
                    """)[0]
                repo = self.get_repo(repo_path, read_only=True)
                mdir = os.path.dirname(repo.manifest(pfmri))
                jpath = os.path.join(mdir, "junk")
                with open(jpath, "wb") as f:
                        f.write("random junk")
                self.assertTrue(os.path.exists(jpath))

                # Verify rebuild succeeds.
                self.pkgrepo("rebuild -s %s" % repo_path)

                # Verify junk file is still there.
                self.assertTrue(os.path.exists(jpath))

                # Verify expected package is still known.
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqualDiff([pfmri],
                    [str(f) for f in repo.get_catalog("test").fmris()])
 
        def __test_refresh(self, repo_path, repo_uri):
                """Private function to verify refresh subcommand behaviour."""

                # Verify refresh doesn't fail for an empty repository.
                self.pkgrepo("refresh -s %s" % repo_path)
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

                self.pkgrepo("refresh -s %s" % repo_uri)
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
                        'set name=pkg.fmri value=%s\n' % plist[1]]]
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

                self.pkgrepo("refresh -s %s --no-index" % repo_uri)
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

                self.pkgrepo("refresh -s %s --no-catalog" % repo_uri)
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
                self.pkgrepo("refresh -s %s" % repo_uri)
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
                self.pkgrepo("create %s" % repo_path)
                self.pkgrepo("add-publisher -s %s test" % repo_path)
                repo = self.get_repo(repo_path, read_only=True)
                cat = repo.get_catalog(pub="test")
                cat.destroy()
                self.pkgrepo("refresh -s %s" % repo_path)
                shutil.rmtree(repo_path)

                # Create a repository and verify network-based repository
                # access.
                self.assert_(not os.path.exists(repo_path))
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
                self.pkgrepo("set -s %s -p test2 publisher/alias=" % repo_path)
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

                self.pkgrepo("refresh -s %s -p test" % repo_uri)
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
                self.pkgrepo("refresh -s %s" % repo_uri)
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
                self.pkgrepo("version -s %s" % self.test_root, exit=2)

                # Verify version output is sane.
                self.pkgrepo("version")
                self.assert_(self.output.find(pkg.VERSION) != -1)

        def test_07_add_publisher(self):
                """Verify that add-publisher subcommand works as expected."""

                # Create a repository.
                repo_path = os.path.join(self.test_root, "repo")
                self.create_repo(repo_path)

                # Verify invalid publisher prefixes are rejected gracefully.
                self.pkgrepo("-s %s add-publisher !valid" % repo_path, exit=1)
                self.pkgrepo("-s %s add-publisher file:%s" % (repo_path,
                    repo_path), exit=1)
                self.pkgrepo("-s %s add-publisher valid !valid" % repo_path,
                    exit=1)

                # Verify that multiple publishers can be added at a time, and
                # that the first publisher named will be set as the default
                # publisher if a default was not already set.
                self.pkgrepo("-s %s add-publisher example.com example.net" %
                    repo_path)
                self.pkgrepo("-s %s get -p example.com -p example.net "
                    "publisher/alias" % repo_path)
                self.pkgrepo("get -s %s -HFtsv publisher/prefix" % repo_path)
                expected = """\
publisher\tprefix\texample.com
"""
                self.assertEqualDiff(expected, self.output)

                # Verify that add-publisher will exit with complete failure if
                # all publishers being added already exist.
                self.pkgrepo("-s %s add-publisher example.com example.net" %
                    repo_path, exit=1)

                # Verify that add-publisher will exit with partial failure if
                # only some publishers already exist.
                self.pkgrepo("-s %s add-publisher example.com example.org" %
                    repo_path, exit=3)

                # Now set a default publisher before adding a publisher for
                # the first time.
                shutil.rmtree(repo_path)
                self.create_repo(repo_path)
                self.pkgrepo("-s %s set publisher/prefix=example.net" %
                    repo_path)
                self.pkgrepo("-s %s add-publisher example.org" % repo_path)
                self.pkgrepo("get -s %s -HFtsv publisher/prefix" % repo_path)
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
                self.pkgrepo("set -s %s publisher/prefix=test" % src_repo)

                # Test that removing a package when no files have been published
                # works (bug 18424).
                published = self.pkgsend_bulk(src_repo, self.zoo10)
                self.pkgrepo("remove -s %s zoo" % src_repo)

                # Reset the src_repo for the rest of the test.
                shutil.rmtree(src_repo)
                self.create_repo(src_repo)
                self.pkgrepo("set -s %s publisher/prefix=test" % src_repo)

                published = self.pkgsend_bulk(src_repo, (self.tree10,
                    self.amber10, self.amber20, self.truck10, self.truck20,
                    self.zoo10))
                self.pkgrepo("set -s %s publisher/prefix=test2" % src_repo)
                published += self.pkgsend_bulk(src_repo, (self.tree10,
                    self.zoo10))

                # Restore repository for next test.
                dest_repo = os.path.join(self.test_root, "test-repo")
                shutil.copytree(src_repo, dest_repo)

                # Verify that specifying something other than a filesystem-
                # based repository fails.
                self.pkgrepo("remove -s %s tree" % self.durl, exit=2)

                # Verify that non-matching patterns result in error.
                self.pkgrepo("remove -s %s nosuchpackage" % dest_repo, exit=1)
                self.pkgrepo("remove -s %s tree nosuchpackage" % dest_repo,
                    exit=1)

                # Verify that -n works as expected.
                self.pkgrepo("remove -n -s %s zoo" % dest_repo)
                # Since package was not removed, this succeeds.
                self.pkgrepo("remove -n -s %s zoo" % dest_repo) 

                # Verify that -p works as expected.
                self.pkgrepo("remove -s %s -p nosuchpub zoo" % dest_repo,
                    exit=1)
                self.pkgrepo("remove -s %s -p test -p test2 zoo" % dest_repo)
                self.pkgrepo("remove -s %s -p test zoo" % dest_repo, exit=1)
                self.pkgrepo("remove -s %s -p test2 zoo" % dest_repo, exit=1)

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
                self.pkgrepo("remove -s %s truck@2.0" % dest_repo)

                # The manifest should no longer exist.
                self.assert_(not os.path.exists(mpath))

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
                self.pkgrepo("remove -s %s truck" % dest_repo)

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

                self.pkgrepo("remove -s %s tree truck" % dest_repo)

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
                        self.assert_(not os.path.exists(pdir))

                # Verify that entries for each package that was removed no
                # longer exist in the catalog, but do exist in the catalog's
                # updatelog.
                repo = self.get_repo(dest_repo)
                for pfx in ("test", "test2"):
                        c = repo.get_catalog(pub=pfx)
                        for f in c.fmris():
                                self.assert_(f.pkg_name not in ("tree",
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
                                f.startswith("pkg://%s/" % pfx)
                        )
                        self.assertEqualDiff(expected, removed)

                # Verify repository file_root is empty.
                for rstore in repo.rstores:
                        if not rstore.publisher:
                                continue
                        self.assert_(not os.listdir(rstore.file_root))

                # Cleanup.
                shutil.rmtree(src_repo)
                shutil.rmtree(dest_repo)

        def test_10_list(self):
                """Verify the list subcommand works as expected."""

                repo_path = self.dc.get_repodir()
                repo_uri = self.dc.get_repo_url()

                # Publish some packages.
                self.pkgsend_bulk(repo_uri, (self.tree10, self.amber10,
                    self.amber20, self.amber30, self.amber40))

                # Verify graceful exit if invalid or incomplete set of
                # options specified.
                self.pkgrepo("list", exit=2)
                self.pkgrepo("-s bogus://location list", exit=1)
                self.pkgrepo("list -s bogus://location list", exit=1)
                self.pkgrepo("list -s %s -F bad-format" % repo_uri, exit=2)

                # Verify graceful exit for bad repository.
                self.pkgrepo("list -s /no/such/repository", exit=1)

                # Verify graceful exit if invalid package name given.
                self.pkgrepo("list -s %s ^notvalid" % repo_path, exit=1)

                # Verify graceful exit if no matching package found.
                self.pkgrepo("list -s %s nosuchpackage" % repo_path, exit=1)

                # Verify default output when listing all packages for both
                # file and http cases:
                for src in (repo_path, repo_uri):
                        # json output.
                        self.pkgrepo("list -s %s -F json" % src)
                        expected = """\
[{"branch": "0", "build-release": "5.11", "name": "amber", "pkg.fmri": "pkg://test/amber@4.0,5.11-0:20110804T203458Z", "pkg.obsolete": [{"value": ["true"]}], "publisher": "test", "release": "4.0", "timestamp": "20110804T203458Z", "version": "4.0,5.11-0:20110804T203458Z"}, {"branch": "0", "build-release": "5.11", "name": "amber", "pkg.fmri": "pkg://test/amber@3.0,5.11-0:20110804T203458Z", "pkg.renamed": [{"value": ["true"]}], "publisher": "test", "release": "3.0", "timestamp": "20110804T203458Z", "version": "3.0,5.11-0:20110804T203458Z"}, {"branch": "0", "build-release": "5.11", "name": "amber", "pkg.fmri": "pkg://test/amber@2.0,5.11-0:20110804T203458Z", "publisher": "test", "release": "2.0", "timestamp": "20110804T203458Z", "version": "2.0,5.11-0:20110804T203458Z"}, {"branch": "0", "build-release": "5.11", "name": "amber", "pkg.fmri": "pkg://test/amber@1.0,5.11-0:20110804T203458Z", "pkg.human-version": [{"value": ["1.0a"]}], "pkg.summary": [{"value": ["Millenia old resin"]}], "publisher": "test", "release": "1.0", "timestamp": "20110804T203458Z", "version": "1.0,5.11-0:20110804T203458Z"}, {"branch": "0", "build-release": "5.11", "info.classification": [{"value": ["org.opensolaris.category.2008:System/Core"]}], "name": "tree", "pkg.fmri": "pkg://test/tree@1.0,5.11-0:20110804T203458Z", "pkg.summary": [{"value": ["Leafy i386 package"], "variant.arch": ["i386"]}, {"value": ["Leafy SPARC package"], "variant.arch": ["sparc"]}], "publisher": "test", "release": "1.0", "timestamp": "20110804T203458Z", "variant.arch": [{"value": ["i386", "sparc"]}], "version": "1.0,5.11-0:20110804T203458Z"}]"""
                        self.assertEqualDiff(expected, self.output)

                # Now verify list output in different formats but only using
                # file repository for test efficiency.

                # Human readable (default) output.
                self.pkgrepo("list -s %s" % src)
                expected = """\
PUBLISHER NAME                                          O VERSION
test      amber                                         o 4.0,5.11-0:20110804T203458Z
test      amber                                         r 3.0,5.11-0:20110804T203458Z
test      amber                                           2.0,5.11-0:20110804T203458Z
test      amber                                           1.0,5.11-0:20110804T203458Z
test      tree                                            1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # Human readable (default) output with no header.
                self.pkgrepo("list -s %s -H" % repo_path)
                expected = """\
test      amber                                         o 4.0,5.11-0:20110804T203458Z
test      amber                                         r 3.0,5.11-0:20110804T203458Z
test      amber                                           2.0,5.11-0:20110804T203458Z
test      amber                                           1.0,5.11-0:20110804T203458Z
test      tree                                            1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # tsv output.
                self.pkgrepo("list -s %s -F tsv" % repo_path)
                expected = """\
PUBLISHER	NAME	O	RELEASE	BUILD RELEASE	BRANCH	PACKAGING DATE	FMRI
test	amber	o	4.0	5.11	0	20110804T203458Z	pkg://test/amber@4.0,5.11-0:20110804T203458Z
test	amber	r	3.0	5.11	0	20110804T203458Z	pkg://test/amber@3.0,5.11-0:20110804T203458Z
test	amber		2.0	5.11	0	20110804T203458Z	pkg://test/amber@2.0,5.11-0:20110804T203458Z
test	amber		1.0	5.11	0	20110804T203458Z	pkg://test/amber@1.0,5.11-0:20110804T203458Z
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # json-formatted output.
                self.pkgrepo("list -s %s -F json-formatted" % src)
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
                self.assertEqualDiff(expected, self.output)

                # Verify ability to list specific packages.
                self.pkgrepo("list -s %s -H -F tsv tree amber@2.0" % repo_path)
                expected = """\
test	amber		2.0	5.11	0	20110804T203458Z	pkg://test/amber@2.0,5.11-0:20110804T203458Z
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("list -s %s -H -F tsv tree amber@4.0 amber@2.0" %
                    repo_path)
                expected = """\
test	amber	o	4.0	5.11	0	20110804T203458Z	pkg://test/amber@4.0,5.11-0:20110804T203458Z
test	amber		2.0	5.11	0	20110804T203458Z	pkg://test/amber@2.0,5.11-0:20110804T203458Z
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("list -s %s -H -F tsv amber@latest tree" %
                    repo_path)
                expected = """\
test	amber	o	4.0	5.11	0	20110804T203458Z	pkg://test/amber@4.0,5.11-0:20110804T203458Z
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # Verify exit with partial failure if one match fails.
                self.pkgrepo("list -s %s -H -F tsv tree bogus" % repo_path,
                    exit=3)
                expected = """\
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                #
                # Add packages for a different publisher.
                #
                self.pkgrepo("set -s %s publisher/prefix=test2" % repo_path)
                self.pkgsend_bulk(repo_path, (self.truck10, self.zoo10))

                # Verify list of all package includes all publishers.
                # tsv output.
                self.pkgrepo("list -s %s -H -F tsv" % repo_path)
                expected = """\
test	amber	o	4.0	5.11	0	20110804T203458Z	pkg://test/amber@4.0,5.11-0:20110804T203458Z
test	amber	r	3.0	5.11	0	20110804T203458Z	pkg://test/amber@3.0,5.11-0:20110804T203458Z
test	amber		2.0	5.11	0	20110804T203458Z	pkg://test/amber@2.0,5.11-0:20110804T203458Z
test	amber		1.0	5.11	0	20110804T203458Z	pkg://test/amber@1.0,5.11-0:20110804T203458Z
test	tree		1.0	5.11	0	20110804T203458Z	pkg://test/tree@1.0,5.11-0:20110804T203458Z
test2	truck		1.0	5.11	0	20110804T203458Z	pkg://test2/truck@1.0,5.11-0:20110804T203458Z
test2	zoo		1.0	5.11	0	20110804T203458Z	pkg://test2/zoo@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("list -s %s -H -F tsv -p all" % repo_path)
                self.assertEqualDiff(expected, self.output)

                # Verify that packages for a single publisher can be listed.
                self.pkgrepo("list -s %s -H -F tsv -p test2" % repo_path)
                expected = """\
test2	truck		1.0	5.11	0	20110804T203458Z	pkg://test2/truck@1.0,5.11-0:20110804T203458Z
test2	zoo		1.0	5.11	0	20110804T203458Z	pkg://test2/zoo@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # Verify that patterns matching packages only provided by one
                # publisher will not result in partial failure.
                self.pkgrepo("list -s %s -H -F tsv zoo" % repo_path)
                expected = """\
test2	zoo		1.0	5.11	0	20110804T203458Z	pkg://test2/zoo@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("list -s %s -H -F tsv '//test2/*'" % repo_path)
                expected = """\
test2	truck		1.0	5.11	0	20110804T203458Z	pkg://test2/truck@1.0,5.11-0:20110804T203458Z
test2	zoo		1.0	5.11	0	20110804T203458Z	pkg://test2/zoo@1.0,5.11-0:20110804T203458Z
"""
                self.assertEqualDiff(expected, self.output)

                # Verify that a package provided by no publisher will result
                # in graceful failure when multiple publishers are present.
                self.pkgrepo("list -s %s -H -F tsv nosuchpackage" % repo_path,
                    exit=1)

        def __get_mf_path(self, fmri_str):
                """Given an FMRI, return the path to its manifest in our
                repository."""

                path_comps = [self.dc.get_repodir(), "publisher",
                    "test", "pkg"]
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
                        assert_(False, "Invalid use of __inject_perm(..)!")

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
                with open(mpath, "ab+") as mf:
                        mf.write("set name=pkg.t_pkgrepo.bad_sig value=foo")
                return mpath

        def __repair_badsig(self, path):
                mpath_new = path + ".new"
                with open(path, "rb") as mf:
                        with open(mpath_new, "wb") as mf_new:
                                for line in mf.readlines():
                                        if not "pkg.t_pkgrepo.bad_sig" in line:
                                                mf_new.write(line)
                os.rename(mpath_new, path)

        def __inject_unknown(self):
                pass

        def test_11_verify_badhash(self):
                """Test that verify finds bad hashes and invalid gzip files."""

                repo_path = self.dc.get_repodir()
                repo_uri = self.dc.get_repo_url()

                # publish a single package and make sure the repository is clean
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                self.pkgrepo("-s %s verify" % repo_path, exit=0)

                # break a file in the repository and ensure we spot it
                bad_hash_path = self.__inject_badhash("tmp/truck1")

                self.pkgrepo("-s %s verify" % repo_path, exit=1)
                self.assert_(
                    self.output.count("ERROR: Invalid file hash") == 1)
                self.assert_(bad_hash_path in self.output)
                self.assert_(fmris[0] in self.output)

                # fix the file in the repository, and publish another package
                self.__repair_badhash("tmp/truck1")
                fmris += self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgrepo("-s %s verify" % repo_path, exit=0)
                self.assert_(bad_hash_path not in self.output)
                bad_hash_path = self.__inject_badhash("tmp/truck1")

                # verify we now get two errors when verifying the repository
                self.pkgrepo("-s %s verify" % repo_path, exit=1)
                self.assert_(
                    self.output.count("ERROR: Invalid file hash") == 2)
                for fmri in fmris:
                        self.assert_(fmri in self.output)
                self.assert_(bad_hash_path in self.output)
                # check we also print paths which deliver that corrupted file
                self.assert_("etc/truck1" in self.output)
                self.assert_("etc/trailer" in self.output)

                # finally, corrupt another file to see that we can also spot
                # files that aren't gzipped.
                fmris += self.pkgsend_bulk(repo_path, (self.truck20))
                bad_gzip_path = self.__inject_badhash("tmp/truck2",
                    valid_gzip=False)
                self.pkgrepo("-s %s verify" % repo_path, exit=1)
                # we should get 3 bad file hashes now, since we've added truck20
                # which also references etc/truck1, which is bad.
                self.assert_(
                    self.output.count("ERROR: Invalid file hash") == 3)
                self.assert_(
                    self.output.count("ERROR: Corrupted gzip file") == 1)
                self.assert_(bad_gzip_path in self.output)


        def test_12_verify_badmanifest(self):
                """Test that verify finds bad manifests."""
                repo_path = self.dc.get_repodir()

                # publish a single package
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))

                # corrupt a manifest and make sure pkglint agrees
                bad_mf = self.__inject_badmanifest(fmris[0])
                self.pkglint(bad_mf, exit=1)

                self.pkgrepo("-s %s verify" % repo_path, exit=1)
                self.assert_(bad_mf in self.output)
                self.assert_("Corrupt manifest." in self.output)

                # publish more packages, and verify we still get the one error
                fmris += self.pkgsend_bulk(repo_path, (self.truck10,
                    self.amber10))
                self.pkgrepo("-s %s verify" % repo_path, exit=1)
                self.assert_(
                    self.output.count("ERROR: Corrupt manifest.") == 1)

                # break another manifest, and check we get two errors
                another_bad_mf = self.__inject_badmanifest(fmris[-1])
                self.pkgrepo("-s %s verify" % repo_path, exit=1)
                self.assert_(another_bad_mf in self.output)
                self.assert_(bad_mf in self.output)
                self.assert_(
                    self.output.count("Corrupt manifest.") == 2)

        def test_13_verify_nofile(self):
                """Test that verify finds missing files."""

                repo_path = self.dc.get_repodir()

                # publish a single package and break it
                fmris = self.pkgsend_bulk(repo_path, (self.tree10))
                missing_file = self.__inject_nofile("tmp/truck1")

                self.pkgrepo("-s %s verify" % repo_path, exit=1)
                self.assert_(missing_file in self.output)
                self.assert_("ERROR: Missing file: %s" %
                    self.fhashes["tmp/truck1"] in self.output)
                self.assert_(fmris[0] in self.output)

                # publish another package that also delivers the file
                # and inject the error again, checking that both manifests
                # appear in the output
                fmris += self.pkgsend_bulk(repo_path, (self.truck10))
                self.__inject_nofile("tmp/truck1")

                self.pkgrepo("-s %s verify" % repo_path, exit=1)
                self.assert_(missing_file in self.output)
                self.assert_(self.output.count("ERROR: Missing file: %s" %
                    self.fhashes["tmp/truck1"]) == 2)
                for f in fmris:
                        self.assert_(f in self.output)

        def test_14_verify_permissions(self):
                """Check that we can find files and manifests in the
                repository that have invalid permissions."""

                repo_path = self.dc.get_repodir()

                shutil.rmtree(repo_path)
                os.mkdir(repo_path)
                os.chmod(repo_path, 0777)
                self.pkgrepo("create %s" % repo_path, su_wrap=True)
                self.pkgrepo("set -s %s publisher/prefix=test" % repo_path,
                    su_wrap=True)
                # publish a single package and break it
                fmris = self.pkgsend_bulk(repo_path, (self.truck10),
                    su_wrap=True)
                bad_path = self.__inject_perm(path="tmp/truck1")
                self.pkgrepo("-s %s verify" % repo_path, exit=1, su_wrap=True)
                self.assert_(bad_path in self.output)
                self.assert_("ERROR: Verification failure" in self.output)
                self.assert_(fmris[0] in self.output)
                self.__repair_perm(bad_path)

                # Just break the parent directory, we should still report the
                # hash file as unreadable
                bad_parent = self.__inject_perm(path="tmp/truck1", parent=True)
                self.pkgrepo("-s %s verify" % repo_path, exit=1, su_wrap=True)
                self.assert_(bad_path in self.output)
                self.assert_("ERROR: Verification failure" in self.output)
                self.assert_(fmris[0] in self.output)
                self.__repair_perm(bad_parent)
                # break some manifests
                fmris = self.pkgsend_bulk(repo_path, (self.truck20),
                    su_wrap=True)

                bad_mf_path = self.__inject_perm(fmri_str=fmris[0])
                self.pkgrepo("-s %s verify" % repo_path, exit=1, su_wrap=True)
                self.assert_(bad_mf_path in self.output)
                self.assert_("ERROR: Verification failure" in self.output)

                # this should cause both manifests to report errors
                bad_mf_path = self.__inject_perm(fmri_str=fmris[0], parent=True)
                self.pkgrepo("-s %s verify" % repo_path, exit=1, su_wrap=True)
                self.assert_(bad_mf_path in self.output)
                self.assert_("ERROR: Verification failure" in self.output)
                self.__repair_perm(bad_mf_path)

        def test_15_verify_badsig(self):
                repo_path = self.dc.get_repodir()

                # publish a single package and break it
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgsign(repo_path, "\*")
                self.pkgrepo("-s %s verify" % repo_path)
                bad_path = self.__inject_badsig(fmris[0])
                self.pkgrepo("-s %s verify" % repo_path, exit=1)
                self.assert_(bad_path in self.output)
                self.assert_("ERROR: Bad signature." in self.output)
                self.__repair_badsig(bad_path)
                self.pkgrepo("-s %s verify" % repo_path, exit=0)

                # now sign with a key, cert and chain cert and check we fail
                # to verify
                self.pkgsign_simple(repo_path, "\*")
                self.pkgrepo("-s %s verify" % repo_path, exit=1)
                self.assert_("ERROR: Bad signature." in self.output)

                # now set a trust anchor directory, and expect that pkgrepo
                # verify will now pass
                ta_dir = os.path.join(self.test_root,
                    "ro_data/signing_certs/produced/ta3")
                self.pkgrepo("-s %s set repository/trust-anchor-directory=%s" %
                    (repo_path, ta_dir))
                self.pkgrepo("-s %s verify" % repo_path, exit=0)

        def test_16_verify_warn_openperms(self):
                """Test that we emit a warning message when the repository is
                not world-readable."""

                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                os.chmod(self.test_root, 0700)
                self.pkgrepo("-s %s verify" % repo_path, exit=0)
                self.assert_("WARNING: " in self.output)
                self.assert_("svc:/application/pkg/system-repository" \
                    in self.output)
                self.assert_("ERROR: " not in self.output)
                os.chmod(self.test_root, 0755)
                self.pkgrepo("-s %s verify" % repo_path, exit=0)
                self.assert_("WARNING: " not in self.output)

        def test_17_verify_empty_pub(self):
                """Test that we can verify a repository that contains a
                publisher with no packages."""
                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgrepo("-s %s add-publisher empty" % repo_path)
                self.pkgrepo("-s %s verify -p empty" % repo_path)

        def test_18_verify_invalid_repos(self):
                """Test that we exit with a usage message for v3 repos and
                network repositories."""
                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                depot_uri = self.dc.get_depot_url()
                self.dc.start()
                self.pkgrepo("-s %s verify" % depot_uri, exit=2)
                self.dc.stop()
                shutil.rmtree(repo_path)
                self.pkgrepo("create --version=3 %s" % repo_path)
                self.pkgrepo("set -s %s publisher/prefix=test" % repo_path)
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgrepo("-s %s verify" % repo_path, exit=1)

        def __get_fhashes(self, repodir, pub):
                """Returns a list of file hashes for the publisher
                pub in a given repository."""
                fhashes = []
                files_dir = os.path.sep.join(["publisher", pub, "file"])
                for dirpath, dirs, files in os.walk(os.path.join(repodir,
                    files_dir)):
                        fhashes.extend(files)
                return fhashes

        def test_19_fix_brokenmanifest(self):
                """Test that fix operations correct a bad manifest in a file
                repo."""

                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgsign(repo_path, "\*")

                self.pkgrepo("-s %s fix" % repo_path)

                valid_hashes = self.__get_fhashes(repo_path, "test")
                self.debug(valid_hashes)
                bad_path = self.__inject_badsig(fmris[0])
                self.pkgrepo("-s %s fix" % repo_path)
                self.assert_(fmris[0] in self.output)
                self.assert_(not os.path.exists(bad_path))

                # check our quarantine dir has been created
                q_dir = os.path.sep.join([repo_path, "publisher", "test",
                    "pkg5-quarantine"])
                self.assert_(os.path.exists(q_dir))

                # check the broken manifest is in the quarantine dir
                mf_path_sub = bad_path.replace(
                    os.path.sep.join([repo_path, "publisher", "test"]), "")
                # quarantined items are stored in a new tmpdir per-session
                q_dir_tmp = os.listdir(q_dir)[0]
                q_mf_path = os.path.sep.join([q_dir, q_dir_tmp, mf_path_sub])
                self.assert_(os.path.exists(q_mf_path))

                # make sure the package no longer appears in the catalog
                self.pkgrepo("-s %s list -F tsv" % repo_path)
                self.assert_(fmris[0] not in self.output)

                # ensure that only the manifest was quarantined - file hashes
                # were left alone.
                remaining_hashes = self.__get_fhashes(repo_path, "test")
                self.assert_(set(valid_hashes) == set(remaining_hashes))

                # finally, ensure we can republish this package
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgrepo("-s %s list -F tsv" % repo_path)
                self.assert_(fmris[0] in self.output)

        def test_20_fix_brokenfile(self):
                """Test that operations that cause us to fix a file shared
                by several packages cause all of those packages to be
                quarantined.

                This also tests the -v option of pkg fix, which prints the
                pkgrepo verify output and prints details of which files are
                being quarantined.
                """

                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.tree10,
                    self.truck10))
                self.pkgrepo("-s %s fix" % repo_path)
                bad_file = self.__inject_badhash("tmp/truck1")

                old_hashes = self.__get_fhashes(repo_path, "test1")

                self.pkgrepo("-s %s fix -v" % repo_path)

                # since the file was shared by two manifests, we should get
                # the manifest name printed twice: once when we encounter the
                # broken file, then again when we print the summary of which
                # packages need to be republished.
                self.assert_(self.output.count(fmris[0]) == 2)
                self.assert_(self.output.count(fmris[1]) == 2)
                self.assert_(self.output.count("ERROR: Invalid file hash") == 2)

                # the bad file name gets printed 3 times, once for each time
                # a manifest references it and verify discovered the error,
                # and once when we report where the file was moved to.
                self.assert_(self.output.count(bad_file) == 3)

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
                self.assert_(os.path.exists(q_file_path))
                self.debug(q_file_path)
                self.assert_(q_file_path in self.output)

                remaining_hashes = self.__get_fhashes(repo_path, "test1")
                # check that we only quarantined the bad hash file
                self.assert_(set(remaining_hashes) == \
                    set(old_hashes) - set(os.path.basename(bad_file)))

                # Make sure the repository is now clean, and remains so even
                # after we republish the packages, and that all file content is
                # replaced.
                self.pkgrepo("-s %s fix" % repo_path)
                fmris = self.pkgsend_bulk(repo_path, (self.tree10,
                    self.truck10))
                new_hashes = self.__get_fhashes(repo_path, "test1")
                self.assert_(set(new_hashes) == set(old_hashes))
                self.pkgrepo("-s %s fix" % repo_path)

        def test_21_fix_brokenperm(self):
                """Tests that when running fix as an unpriviliged user that we
                fail to fix the repository."""

                repo_path = self.dc.get_repodir()

                shutil.rmtree(repo_path)
                os.mkdir(repo_path)
                os.chmod(repo_path, 0777)
                self.pkgrepo("create %s" % repo_path, su_wrap=True)
                self.pkgrepo("set -s %s publisher/prefix=test" % repo_path,
                    su_wrap=True)
                # publish a single package and break it
                fmris = self.pkgsend_bulk(repo_path, (self.truck10),
                    su_wrap=True)
                # this breaks the permissions of one of the manifests and
                # chowns is such that we shouldn't be able to quarantine it.
                bad_path = self.__inject_perm(fmri_str=fmris[0], chown=True)

                self.pkgrepo("-s %s fix" % repo_path, exit=1, stderr=True,
                    su_wrap=True)
                self.assert_(bad_path in self.errout)
                # the fix should succeed now, but not emit any output, because
                # it's running as root, and the permissions are fine according
                # to a root user
                self.pkgrepo("-s %s fix" % repo_path)
                # but we should still be able to warn about the bad path for
                # pkg5srv access.
                self.pkgrepo("-s %s verify" % repo_path)
                self.assert_("WARNING: " in self.output)

        def test_22_fix_unsupported_repo(self):
                """Tests that when running fix on a v3 repo fails"""

                repo_path = self.dc.get_repodir()
                shutil.rmtree(repo_path)
                self.pkgrepo("create --version=3 %s" % repo_path)
                self.pkgrepo("-s %s set publisher/prefix=test" % repo_path)
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgrepo("-s %s fix" % repo_path, exit=1)
                self.assert_("only version 4 repositories are supported." in
                    self.errout)

        def test_23_fix_empty_missing_pub(self):
                """Test that we can attempt to fix a repository that contains a
                publisher with no packages, and that we fail on missing pubs"""

                repo_path = self.dc.get_repodir()
                fmris = self.pkgsend_bulk(repo_path, (self.truck10))
                self.pkgrepo("-s %s add-publisher empty" % repo_path)
                self.pkgrepo("-s %s fix -p test" % repo_path)
                self.pkgrepo("-s %s fix -p missing" % repo_path, exit=1)
                self.assert_("no matching publishers" in self.errout)

        def test_24_invalid_repo(self):
                """Test that trying to open an invalid repository is handled
                correctly"""

                tmpdir = tempfile.mkdtemp(dir=self.test_root)

                with open(os.path.join(tmpdir, "pkg5.image"), "w") as f:
                    f.write("[image]\nversion = 2")

                self.assertRaises(sr.RepositoryInvalidError, sr.Repository, 
                    root=tmpdir)
                

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
                
                self.url = self.ac.url + "/%s" % pub

                # publish a simple test package
                self.srurl = self.dcs[1].get_repo_url()
                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.srurl, self.example_pkg10)

                #set permissions of tmp/verboten to make it non-readable
                self.verboten = os.path.join(self.test_root, "tmp/verboten")
                os.system("chmod 600 %s" % self.verboten) 
                

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
                self.pkgrepo("-s %(url)s info --key %(key)s --cert %(cert)s"
                    % arg_dict)

                # pkgrepo list
                self.pkgrepo("-s %(url)s list --key %(key)s --cert %(cert)s"
                    % arg_dict)

                # pkgrepo get
                self.pkgrepo("-s %(url)s get --key %(key)s --cert %(cert)s"
                    % arg_dict)

                # pkgrepo refresh
                self.pkgrepo("-s %(url)s refresh --key %(key)s --cert %(cert)s"
                    % arg_dict)

                # pkgrepo rebuild
                self.pkgrepo("-s %(url)s rebuild --key %(key)s --cert %(cert)s"
                    % arg_dict)

                # Try without key and cert (should fail)
                self.pkgrepo("-s %(url)s rebuild" % arg_dict, exit=1)

                # Make sure we don't traceback when credential files are invalid
                # Certificate option missing
                self.pkgrepo("-s %(url)s rebuild --key %(key)s" % arg_dict,
                    exit=1)

                # Key option missing
                self.pkgrepo("-s %(url)s rebuild --cert %(cert)s" % arg_dict,
                    exit=1)

                # Certificate not found
                self.pkgrepo("-s %(url)s rebuild --key %(key)s "
                    "--cert %(noexist)s" % arg_dict, exit=1)

                # Key not found
                self.pkgrepo("-s %(url)s rebuild --key %(noexist)s "
                    "--cert %(cert)s" % arg_dict, exit=1)

                # Certificate is empty file
                self.pkgrepo("-s %(url)s rebuild --key %(key)s "
                    "--cert %(empty)s" % arg_dict, exit=1)

                # Key is empty file
                self.pkgrepo("-s %(url)s rebuild --key %(empty)s "
                    "--cert %(cert)s" % arg_dict, exit=1)

                # No permissions to read certificate 
                self.pkgrepo("-s %(url)s rebuild --key %(key)s "
                    "--cert %(verboten)s" % arg_dict, su_wrap=True, exit=1)

                # No permissions to read key 
                self.pkgrepo("-s %(url)s rebuild --key %(verboten)s "
                    "--cert %(cert)s" % arg_dict, su_wrap=True, exit=1)


if __name__ == "__main__":
        unittest.main()
