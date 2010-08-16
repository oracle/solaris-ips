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
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.search_errors as se
import shutil
import tempfile
import time
import urllib
import urlparse
import unittest

class TestPkgRepo(pkg5unittest.CliTestCase):
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
                pkg5unittest.CliTestCase.setUp(self)

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

                # Verify an invalid URI causes an exit.  (For the moment,
                # only the file scheme is supported.)
                for baduri in ("file://not/valid", "http://localhost",
                    "http://not$valid"):
                        self.pkgrepo("-s %s" % baduri, exit=1)

        def test_01_create(self):
                """Verify pkgrepo create works as expected."""

                # Verify create without a destination exits.
                self.pkgrepo("create", exit=2)

                # Verify create with an invalid URI exits.  (For the moment,
                # only the file scheme is supported.)
                for baduri in ("file://not/valid", "http://localhost",
                    "http://not$valid"):
                        self.pkgrepo("create %s" % baduri, exit=1)

                # Verify create works whether -s is used to supply the location
                # of the new repository or it is passed as an operand.  Also
                # verify that either a path or URI can be used to provide the
                # repository's location.
                repo_path = os.path.join(self.test_root, "repo")
                repo_uri = "file:%s" % repo_path

                # Specify using global option and path.
                self.pkgrepo("-s %s create" % repo_path)
                # This will fail if a repository wasn't created.
                self.get_repo(repo_path)
                shutil.rmtree(repo_path)

                # Specify using operand and URI.
                self.pkgrepo("create %s" % repo_uri)
                # This will fail if a repository wasn't created.
                self.get_repo(repo_path)
                shutil.rmtree(repo_path)

        def test_02_property(self):
                """Verify pkgrepo property and set-property works as expected.
                """

                # Verify command without a repository exits.
                self.pkgrepo("property", exit=2)

                # Create a repository.
                repo_path = os.path.join(self.test_root, "repo")
                repo_uri = "file:%s" % repo_path
                self.assert_(not os.path.exists(repo_path))
                self.pkgrepo("-s %s create" % repo_path)

                # Verify property handles unknown properties gracefully.
                self.pkgrepo("-s %s property repository/unknown" % repo_uri,
                    exit=1)

                # Verify property returns partial failure if only some
                # properties cannot be found.
                self.pkgrepo("-s %s property repository/origins "
                    "repository/unknown" % repo_uri, exit=3)

                # Verify full default output.
                self.pkgrepo("-s %s property" % repo_uri)
                expected = """\
SECTION    PROPERTY           VALUE
feed       description        
feed       icon               web/_themes/pkg-block-icon.png
feed       id                 
feed       logo               web/_themes/pkg-block-logo.png
feed       name               package repository feed
feed       window             24
publisher  alias              
publisher  intermediate_certs []
publisher  prefix             
publisher  signing_ca_certs   []
repository collection_type    core
repository description        
repository detailed_url       
repository legal_uris         []
repository maintainer         
repository maintainer_url     
repository mirrors            []
repository name               package repository
repository origins            []
repository refresh_seconds    14400
repository registration_uri   
repository related_uris       []
"""
                self.assertEqualDiff(expected, self.output)

                # Verify full tsv output.
                self.pkgrepo("-s %s property -Ftsv" % repo_uri)
                expected = """\
SECTION\tPROPERTY\tVALUE
feed\tdescription\t
feed\ticon\tweb/_themes/pkg-block-icon.png
feed\tid\t
feed\tlogo\tweb/_themes/pkg-block-logo.png
feed\tname\tpackage repository feed
feed\twindow\t24
publisher\talias\t
publisher\tintermediate_certs\t[]
publisher\tprefix\t
publisher\tsigning_ca_certs\t[]
repository\tcollection_type\tcore
repository\tdescription\t
repository\tdetailed_url\t
repository\tlegal_uris\t[]
repository\tmaintainer\t
repository\tmaintainer_url\t
repository\tmirrors\t[]
repository\tname\tpackage repository
repository\torigins\t[]
repository\trefresh_seconds\t14400
repository\tregistration_uri\t
repository\trelated_uris\t[]
"""
                self.assertEqualDiff(expected, self.output)

                # Verify that -H omits headers for full output.
                self.pkgrepo("-s %s property -H" % repo_uri)
                self.assert_(self.output.find("SECTION") == -1)

                # Verify specific property default output and that
                # -H omits headers for specific property output.
                self.pkgrepo("-s %s property publisher/prefix" %
                    repo_uri)
                expected = """\
SECTION    PROPERTY           VALUE
publisher  prefix             
"""
                self.assertEqualDiff(expected, self.output)

                
                self.pkgrepo("-s %s property -H publisher/prefix "
                    "repository/origins" % repo_uri)
                expected = """\
publisher  prefix             
repository origins            []
"""
                self.assertEqualDiff(expected, self.output)

                # Verify specific property tsv output.
                self.pkgrepo("-s %s property -F tsv publisher/prefix" %
                    repo_uri)
                expected = """\
SECTION\tPROPERTY\tVALUE
publisher\tprefix\t
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("-s %s property -HF tsv publisher/prefix "
                    "repository/origins" % repo_uri)
                expected = """\
publisher\tprefix\t
repository\torigins\t[]
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set-property fails if no property is provided.
                self.pkgrepo("-s %s set-property" % repo_uri, exit=2)

                # Verify set-property gracefully handles bad property values.
                self.pkgrepo("-s %s set-property publisher/prefix=_invalid" %
                    repo_uri, exit=1)

                # Verify set-property can set single value properties.
                self.pkgrepo("-s %s set-property "
                    "publisher/prefix=opensolaris.org" % repo_uri)
                self.pkgrepo("-s %s property -HF tsv publisher/prefix" %
                    repo_uri)
                expected = """\
publisher\tprefix\topensolaris.org
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set-property can set multi-value properties.
                self.pkgrepo("-s %s set-property "
                    "'repository/origins=(http://pkg.opensolaris.org/dev "
                    "http://pkg-eu-2.opensolaris.org/dev)'" % repo_uri)
                self.pkgrepo("-s %s property -HF tsv repository/origins" %
                    repo_uri)
                expected = """\
repository\torigins\t['http://pkg.opensolaris.org/dev', 'http://pkg-eu-2.opensolaris.org/dev']
"""
                self.assertEqualDiff(expected, self.output)

                # Verify set-property can set unknown properties.
                self.pkgrepo("-s %s set-property 'foo/bar=value'" % repo_uri)
                self.pkgrepo("-s %s property -HF tsv foo/bar" % repo_uri)
                expected = """\
foo\tbar\tvalue
"""
                self.assertEqualDiff(expected, self.output)

        def test_03_publisher(self):
                """Verify pkgrepo publisher works as expected."""

                # Verify command without a repository exits.
                self.pkgrepo("publisher", exit=2)

                # Create a repository.
                repo_path = os.path.join(self.test_root, "repo")
                repo_uri = "file:%s" % repo_path
                self.assert_(not os.path.exists(repo_path))
                self.pkgrepo("-s %s create" % repo_path)

                # Verify subcommand behaviour for empty repository and -H
                # functionality.
                self.pkgrepo("-s %s publisher" % repo_uri)
                expected = """\
PUBLISHER                PACKAGES VERSIONS UPDATED
"""
                self.assertEqualDiff(expected, self.output)

                self.pkgrepo("-s %s publisher -H" % repo_uri)
                expected = """\
"""
                self.assertEqualDiff(expected, self.output)

                # Set a default publisher.
                self.pkgrepo("-s %s set-property publisher/prefix=test" %
                    repo_uri)

                # Publish some packages.
                self.pkgsend_bulk(repo_uri, (self.tree10, self.amber10,
                    self.amber20, self.truck10, self.truck20))

                # Verify publisher handles unknown publishers gracefully.
                self.pkgrepo("-s %s publisher unknown" % repo_uri, exit=1)

                # Verify publisher returns partial failure if only some
                # publishers cannot be found.
                self.pkgrepo("-s %s publisher test unknown" % repo_uri, exit=3)

                # Verify full default output.
                repo = self.get_repo(repo_path)
                self.pkgrepo("-s %s publisher -H" % repo_uri)
                expected = """\
test                     3        5        %sZ
""" % repo.catalog.last_modified.isoformat()
                self.assertEqualDiff(expected, self.output)

                # Verify full tsv output.
                self.pkgrepo("-s %s publisher -HF tsv" % repo_uri)
                expected = """\
test\t3\t5\t%sZ
""" % repo.catalog.last_modified.isoformat()
                self.assertEqualDiff(expected, self.output)

                # Verify specific publisher default output.
                self.pkgrepo("-s %s publisher -H test" % repo_uri)
                expected = """\
test                     3        5        %sZ
""" % repo.catalog.last_modified.isoformat()
                self.assertEqualDiff(expected, self.output)

                # Verify specific publisher tsv output.
                self.pkgrepo("-s %s publisher -HF tsv test" % repo_uri)
                expected = """\
test\t3\t5\t%sZ
""" % repo.catalog.last_modified.isoformat()
                self.assertEqualDiff(expected, self.output)

        def test_04_rebuild(self):
                """Verify pkgrepo rebuild works as expected."""

                # Verify create without a destination exits.
                self.pkgrepo("rebuild", exit=2)

                # Create a repository.
                repo_path = os.path.join(self.test_root, "repo")
                repo_uri = "file:%s" % repo_path
                self.assert_(not os.path.exists(repo_path))
                repo = self.create_repo(repo_path, properties={ "publisher": {
                    "prefix": "test" } })

                # Verify rebuild works for an empty repository.
                lm = repo.catalog.last_modified.isoformat()
                self.pkgrepo("-s %s rebuild" % repo_path)
                repo = self.get_repo(repo_path)
                self.assertNotEqual(lm, repo.catalog.last_modified.isoformat())

                # Publish some packages.
                plist = self.pkgsend_bulk(repo_uri, (self.amber10, self.tree10))

                # Check that the published packages are seen.
                repo = self.get_repo(repo_path)
                self.assertEqual(list(
                    str(f) for f in repo.catalog.fmris(ordered=True)
                ), plist)

                #
                # Verify rebuild will find all the packages again and that they
                # can be searched for.
                #

                # Destroy the catalog and index.
                repo.catalog.destroy()
                shutil.rmtree(repo.index_root)

                # Reload the repository object and verify no packages are known.
                repo = self.get_repo(repo_path)
                self.assertEqual(set(), repo.catalog.names())

                self.pkgrepo("-s %s rebuild" % repo_uri)
                repo = self.get_repo(repo_path)
                self.assertEqual(plist,
                    list(str(f) for f in repo.catalog.fmris(ordered=True)))

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
                repo.catalog.destroy()

                # Reload the repository object and verify no packages are known.
                repo = self.get_repo(repo_path)
                self.assertEqual(set(), repo.catalog.names())

                self.pkgrepo("-s %s rebuild --no-index" % repo_uri)
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqual(plist,
                    list(str(f) for f in repo.catalog.fmris(ordered=True)))

                query = Query("tree", False, Query.RETURN_PACKAGES, None, None)
                try:
                        result = list(
                            e for e in [
                                r for r in repo.search([query])
                            ][0]
                        )
                except Exception, e:
                        self.assert_(isinstance(e, se.NoIndexException))
                else:
                        raise RuntimeError("Expected NoIndexException")

        def test_05_refresh(self):
                """Verify pkgrepo refresh works as expected."""

                # Verify create without a destination exits.
                self.pkgrepo("refresh", exit=2)

                # Create a repository.
                repo_path = os.path.join(self.test_root, "repo")
                repo_uri = "file:%s" % repo_path
                self.assert_(not os.path.exists(repo_path))
                repo = self.create_repo(repo_path, properties={ "publisher": {
                    "prefix": "test" } })

                # Verify refresh doesn't fail for an empty repository.
                self.pkgrepo("-s %s refresh" % repo_path)

                # Publish some packages.
                plist = self.pkgsend_bulk(repo_uri, (self.amber10, self.tree10))

                # Check that the published packages are seen.
                repo = self.get_repo(repo_path)
                self.assertEqual(list(
                    str(f) for f in repo.catalog.fmris(ordered=True)
                ), plist)

                #
                # Verify refresh will find new packages and that they can be
                # searched for.
                #

                # Destroy the index.
                shutil.rmtree(repo.index_root)

                # Reload the repository object.
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqual(plist,
                    list(str(f) for f in repo.catalog.fmris(ordered=True)))

                self.pkgrepo("-s %s refresh" % repo_uri)
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqual(plist,
                    list(str(f) for f in repo.catalog.fmris(ordered=True)))

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
                plist.extend(self.pkgsend_bulk(repo_uri, self.truck10,
                    no_index=True))
                fmris.append(fmri.PkgFmri(plist[-1]).get_fmri(anarchy=True))

                self.pkgrepo("-s %s refresh --no-index" % repo_uri)
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqualDiff(plist,
                    list(str(f) for f in repo.catalog.fmris(ordered=True)))

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
                    no_catalog=True, no_index=True))
                fmris.append(fmri.PkgFmri(plist[-1]).get_fmri(anarchy=True))

                self.pkgrepo("-s %s refresh --no-catalog" % repo_uri)
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqual(plist[:-1], list(
                    str(f) for f in repo.catalog.fmris(ordered=True)
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
                self.pkgrepo("-s %s refresh" % repo_uri)
                repo = self.get_repo(repo_path, read_only=True)
                self.assertEqual(plist, list(
                    str(f) for f in repo.catalog.fmris(ordered=True)
                ))

        def test_06_version(self):
                """Verify pkgrepo version works as expected."""

                # Verify version exits with error if operands are provided.
                self.pkgrepo("version operand", exit=2)

                # Verify version exits with error if a repository location is
                # provided.
                self.pkgrepo("-s %s version" % self.test_root, exit=2)

                # Verify version output is sane.
                self.pkgrepo("version")
                self.assert_(self.output.find(pkg.VERSION) != -1)

        def test_07_certs(self):
                """Verify that certificate commands work as expected."""

                # Create a repository.
                repo_path = os.path.join(self.test_root, "repo")
                repo_uri = "file:%s" % repo_path
                self.assert_(not os.path.exists(repo_path))
                self.pkgrepo("-s %s create" % repo_path)

                ca3_pth = os.path.join(self.pub_cas_dir, "pubCA1_ta3_cert.pem")
                ca1_pth = os.path.join(self.pub_cas_dir, "pubCA1_ta1_cert.pem")
                
                self.pkgrepo("-s %s add-signing-ca-cert %s" %
                    (repo_uri, ca3_pth))
                self.pkgrepo("-s %s add-signing-ca-cert %s" %
                    (repo_uri, ca1_pth))

                ca1_hsh = self.calc_file_hash(ca1_pth)
                ca3_hsh = self.calc_file_hash(ca3_pth)

                self.pkgrepo("-s %s remove-signing-intermediate-cert %s" %
                    (repo_uri, ca1_hsh))
                self.pkgrepo("-s %s remove-signing-intermediate-cert %s" %
                    (repo_uri, ca3_hsh))
                self.pkgrepo("-s %s remove-signing-ca-cert %s" %
                    (repo_uri, ca1_hsh))
                self.pkgrepo("-s %s remove-signing-ca-cert %s" %
                    (repo_uri, ca3_hsh))

                self.pkgrepo("-s %s add-signing-intermediate-cert %s" %
                    (repo_uri, ca3_pth))
                self.pkgrepo("-s %s add-signing-intermediate-cert %s" %
                    (repo_uri, ca1_pth))

                ca1_hsh = self.calc_file_hash(ca1_pth)
                ca3_hsh = self.calc_file_hash(ca3_pth)

                self.pkgrepo("-s %s remove-signing-ca-cert %s" %
                    (repo_uri, ca1_hsh))
                self.pkgrepo("-s %s remove-signing-ca-cert %s" %
                    (repo_uri, ca3_hsh))
                self.pkgrepo("-s %s remove-signing-intermediate-cert %s" %
                    (repo_uri, ca1_hsh))
                self.pkgrepo("-s %s remove-signing-intermediate-cert %s" %
                    (repo_uri, ca3_hsh))

if __name__ == "__main__":
        unittest.main()
