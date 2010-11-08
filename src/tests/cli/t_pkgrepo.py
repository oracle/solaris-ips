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
# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

from pkg.server.query_parser import Query
import os
import pkg
import pkg.depotcontroller as dc
import pkg.fmri as fmri
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

        tree10 = """
            open tree@1.0,5.11-0
            close
        """

        amber10 = """
            open amber@1.0,5.11-0
            add depend fmri=pkg:/tree@1.0 type=require
            close
        """

        amber20 = """
            open amber@2.0,5.11-0
            add depend fmri=pkg:/tree@1.0 type=require
            close
        """

        truck10 = """
            open truck@1.0,5.11-0
            add file tmp/empty mode=0555 owner=root group=bin path=/etc/NOTICES/empty
            add file tmp/truck1 mode=0444 owner=root group=bin path=/etc/truck1
            add depend fmri=pkg:/amber@1.0 type=require
            close
        """

        truck20 = """
            open truck@2.0,5.11-0
            add file tmp/empty mode=0555 owner=root group=bin path=/etc/NOTICES/empty
            add file tmp/truck1 mode=0444 owner=root group=bin path=/etc/truck1
            add file tmp/truck2 mode=0444 owner=root group=bin path=/etc/truck2
            add depend fmri=pkg:/amber@2.0 type=require
            close
        """

        zoo10 = """
            open zoo@1.0,5.11-0
            close
        """

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(["tmp/empty", "tmp/truck1",
                    "tmp/truck2"])

                self.path_to_certs = os.path.join(self.ro_data_root,
                    "signing_certs", "produced")
                self.pub_cas_dir = os.path.join(self.path_to_certs,
                    "publisher_cas")
                self.inter_certs_dir = os.path.join(self.path_to_certs,
                    "inter_certs")

        def test_00_base(self):
                """Verify pkgrepo handles basic option and subcommand parsing
                as expected.
                """

                # --help, -? should exit with 0.
                self.pkgrepo("--help", exit=0)
                self.pkgrepo("-?", exit=0)

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
SECTION    PROPERTY           VALUE
feed       description        ""
feed       icon               web/_themes/pkg-block-icon.png
feed       id                 ""
feed       logo               web/_themes/pkg-block-logo.png
feed       name               package\ repository\ feed
feed       window             24
publisher  alias              ""
publisher  intermediate_certs ()
publisher  prefix             test
publisher  signing_ca_certs   ()
repository collection_type    core
repository description        ""
repository detailed_url       ""
repository legal_uris         ()
repository maintainer         ""
repository maintainer_url     ""
repository mirrors            ()
repository name               package\ repository
repository origins            ()
repository refresh_seconds    14400
repository registration_uri   ""
repository related_uris       ()
repository version            3
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
publisher\tintermediate_certs\t()
publisher\tprefix\ttest
publisher\tsigning_ca_certs\t()
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
SECTION    PROPERTY           VALUE
publisher  prefix             test
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("get -s %s -H publisher/prefix "
                    "repository/origins" % repo_uri)
                expected = """\
publisher  prefix             test
repository origins            ()
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

                # Now compare creation timestamps of each publisher's
                # catalog to verify all catalogs were rebuilt.
                repo = self.get_repo(repo_path, read_only=True)
                cat = repo.get_catalog(pub="test")
                self.assertNotEqual(cat.created, test_cts)
                cat = repo.get_catalog(pub="test2")
                self.assertNotEqual(cat.created, test2_cts)

                self.dc.stop()

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

                # Finally, run refresh once more and verify that all packages
                # are now visible in the catalog.
                self.pkgrepo("refresh -s %s" % repo_uri)
                self.wait_repo(repo_path)
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqual(plist, list(
                    str(f) for f in repo.get_catalog("test").fmris(ordered=True)
                ))

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

        def __test_add_remove_certs(self, repo_uri, pubs=[]):
                """Private helper method to test certificate add and remove
                for default publisher case."""

                pub_opt = "".join(" -p %s " % p for p in pubs)
                exit = 0
                if "nosuchpub" in pubs:
                        if len(pubs) > 1:
                                # Expect partial in this case.
                                exit = 3
                        else:
                                # Expect failure in this case.
                                exit = 1

                ca3_pth = os.path.join(self.pub_cas_dir, "pubCA1_ta3_cert.pem")
                ca1_pth = os.path.join(self.pub_cas_dir, "pubCA1_ta1_cert.pem")

                ca1_hsh = self.calc_file_hash(ca1_pth)
                ca3_hsh = self.calc_file_hash(ca3_pth)

                self.pkgrepo("add-signing-ca-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca3_pth), exit=exit)
                self.pkgrepo("add-signing-ca-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca1_pth), exit=exit)

                self.pkgrepo("remove-signing-intermediate-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca1_hsh), exit=exit)
                self.pkgrepo("remove-signing-intermediate-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca3_hsh), exit=exit)
                self.pkgrepo("remove-signing-ca-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca1_hsh), exit=exit)
                self.pkgrepo("remove-signing-ca-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca3_hsh), exit=exit)

                self.pkgrepo("add-signing-intermediate-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca3_pth), exit=exit)
                self.pkgrepo("add-signing-intermediate-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca1_pth), exit=exit)

                self.pkgrepo("remove-signing-ca-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca1_hsh), exit=exit)
                self.pkgrepo("remove-signing-ca-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca3_hsh), exit=exit)
                self.pkgrepo("remove-signing-intermediate-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca1_hsh), exit=exit)
                self.pkgrepo("remove-signing-intermediate-cert -s %s %s%s" %
                    (repo_uri, pub_opt, ca3_hsh), exit=exit)

        def test_07_certs(self):
                """Verify that certificate commands work as expected."""

                # Create a repository.
                repo_path = os.path.join(self.test_root, "repo")
                repo_uri = "file:%s" % repo_path
                self.create_repo(repo_path)

                ca3_pth = os.path.join(self.pub_cas_dir, "pubCA1_ta3_cert.pem")
                ca1_pth = os.path.join(self.pub_cas_dir, "pubCA1_ta1_cert.pem")

                ca1_hsh = self.calc_file_hash(ca1_pth)
                ca3_hsh = self.calc_file_hash(ca3_pth)

                # Verify that signing commands will fail gracefully if no
                # default publisher has been set and a publisher was not
                # specified.
                self.pkgrepo("-s %s add-signing-ca-cert %s" % (repo_uri,
                    ca3_pth), exit=1)
                self.pkgrepo("-s %s add-signing-intermediate-cert %s" %
                    (repo_uri, ca3_pth), exit=1)
                self.pkgrepo("-s %s remove-signing-intermediate-cert %s" %
                    (repo_uri, ca3_hsh), exit=1)
                self.pkgrepo("-s %s remove-signing-ca-cert %s" %
                    (repo_uri, ca1_hsh), exit=1)

                # Now verify that add / remove work as expected for a
                # repository.

                # Test default publisher case.
                self.pkgrepo("set -s %s publisher/prefix=test" % repo_path)
                self.__test_add_remove_certs(repo_uri)

                # Test specific publisher case.
                shutil.rmtree(repo_path)
                self.create_repo(repo_path)
                self.pkgrepo("set -s %s publisher/prefix=test" % repo_path)
                self.__test_add_remove_certs(repo_uri, ["test"])
                self.__test_add_remove_certs(repo_uri, ["nosuchpub"])

                # Test multiple publisher case.
                shutil.rmtree(repo_path)
                self.create_repo(repo_path)
                self.pkgrepo("set -s %s -p test publisher/alias=test" %
                    repo_path)
                self.pkgrepo("set -s %s -p test2 publisher/alias=test2" %
                    repo_path)
                self.__test_add_remove_certs(repo_uri, ["test", "test2"])
                self.__test_add_remove_certs(repo_uri, ["test", "test2",
                    "nosuchpub"])

                # Last, verify that add/remove works for a v3 repository.
                shutil.rmtree(repo_path)
                self.create_repo(repo_path, version=3)
                self.pkgrepo("set -s %s publisher/prefix=test" % repo_path)
                self.__test_add_remove_certs(repo_uri, ["test"])
                self.__test_add_remove_certs(repo_uri)
                self.__test_add_remove_certs(repo_uri, ["nosuchpub"])


if __name__ == "__main__":
        unittest.main()
