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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import shutil
import tempfile
import unittest
import urllib

from pkg import misc

class TestPkgsendBasics(testutils.SingleDepotTestCase):
        persistent_depot = False

        def test_0_pkgsend_bad_opts(self):
                """Verify that non-existent or invalid option combinations
                cannot be specified."""

                durl = self.dc.get_depot_url()
                self.pkgsend(durl, "-@ open foo@1.0,5.11-0", exit=2)
                self.pkgsend(durl, "close -@", exit=2)

                # The -e and -n options are opposites and cannot be combined.
                self.pkgsend(durl, "open -en foo@1.0", exit=2)
                self.pkgsend(durl, "open -ne foo@1.0", exit=2)

        def test_1_pkgsend_abandon(self):
                """Verify that an abandoned tranasaction is not published."""

                dhurl = self.dc.get_depot_url()
                dfurl = "file://%s" % self.dc.get_repodir()

                for url in (dhurl, dfurl):
                        for line in \
                            """open shouldnotexist@1.0,5.11-0
                            add dir mode=0755 owner=root group=bin path=/bin
                            close -A""".splitlines():
                                self.pkgsend(url, line)

                        if url == dfurl:
                                # Must restart pkg.depotd so it will pickup the
                                # changes to the catalog.
                                self.restart_depots()

                        # For now, the pkg(1) client only supports http, so use
                        # the http url always.
                        self.image_create(dhurl)
                        self.pkg("list -a shouldnotexist", exit=1)
                        self.image_destroy()

        def test_2_invalid_url(self):
                """Verify that an invalid repository URL will result in an
                error."""

                # Verify that specifying a malformed or incomplete URL fails
                # gracefully for every known scheme and a few bogus schemes.
                for scheme in ("bogus", "file", "http", "https", "null"):
                        # The first two cases should succeed for 'null'
                        self.pkgsend(scheme + "://", "open notarepo@1.0",
                            exit=scheme != "null")
                        self.pkgsend(scheme + ":", "open notarepo@1.0",
                            exit=scheme != "null")
                        self.pkgsend(scheme, "open notarepo@1.0", exit=1)

                # Create an empty directory to abuse as a repository.
                junk_repo = os.path.join(self.get_test_prefix(), "junk-repo")
                os.makedirs(junk_repo, misc.PKG_DIR_MODE)

                # Point at a valid directory that does not contain a repository.
                dfurl = "file://" + junk_repo

                # Verify that specifying a non-existent directory for a file://
                # repository fails gracefully.
                self.pkgsend(os.path.join(dfurl, "nochance"),
                    "open nosuchdir@1.0", exit=1)

                # Verify that specifying a directory that is not a file://
                # repository fails gracefully.
                self.pkgsend(dfurl, "open notarepo@1.0", exit=1)

                # Point at a non-existent http(s) repository; port 1 is an
                # unassigned port that nothing should use.
                dhurl = "http://localhost:1"
                dshurl = "http://localhost:1"

                # Verify that specifying a non-existent (i.e. unable to connect
                # to) http:// repository fails gracefully.
                self.pkgsend(dhurl, "open nosuchdir@1.0", exit=1)
                self.pkgsend(dshurl, "open nosuchdir@1.0", exit=1)

        def test_3_bad_transaction(self):
                """Verify that invalid Transaction IDs are handled correctly."""

                dhurl = self.dc.get_depot_url()
                dfurl = "file://%s" % self.dc.get_repodir()

                os.environ["PKG_TRANS_ID"] = "foobarbaz"

                for url in (dfurl, dhurl):
                        self.pkgsend(url, "add file /bin/ls path=/bin/ls",
                            exit=1)

        def test_4_bad_actions(self):
                """Verify that malformed or invalid actions are handled
                correctly.  This only checks a few cases as the pkg.action
                class itself should be handling the actual verification;
                the client just needs to handle the appropriate exceptions
                gracefully."""

                dhurl = self.dc.get_depot_url()
                dfurl = "file://%s" % self.dc.get_repodir()
                test_dir = self.get_test_prefix()
                imaginary_file = os.path.join(test_dir, "imaginary_file")

                # Must open transaction using HTTP url first so that transaction
                # will be seen by the depot server and when using file://.
                self.pkgsend(dhurl, "open foo@1.0")

                for url in (dhurl, dfurl):
                        # Should fail because type attribute is missing.
                        self.pkgsend(url,
                            "add depend fmri=foo@1.0", exit=1)

                        # Should fail because type attribute is invalid.
                        self.pkgsend(url,
                            "add depend type=unknown fmri=foo@1.0", exit=1)

                        # Should fail because path attribute is missing.
                        self.pkgsend(url,
                            "add file /bin/ls", exit=1)

                        # Should fail because path attribute is missing a value.
                        self.pkgsend(url,
                            "add file /bin/ls path=", exit=1)

                        # Should fail because the file does not exist.
                        self.pkgsend(url,
                            "add file %s path=/bin/ls" % imaginary_file, exit=1)

                        # Should fail because path=/bin/ls will be interpreted
                        # as the filename and is not a valid file.
                        self.pkgsend(url,
                            "add file path=/bin/ls", exit=1)

                        # Should fail because the action is unknown.
                        self.pkgsend(url,
                            "add bogusaction", exit=1)

        def test_5_bad_open(self):
                """Verify that a bad open is handled properly.  This could be
                because of an invalid FMRI that was specified, or many other
                reasons."""

                dhurl = self.dc.get_depot_url()
                dfurl = "file://%s" % self.dc.get_repodir()

                for url in (dhurl, dfurl):
                        # Should fail because no fmri was specified.
                        self.pkgsend(url, "open", exit=2)

                        # Should fail because an invalid fmri was specified.
                        self.pkgsend(url, "open foo@1.a", exit=1)

                # Should fail because repository does not exist.
                self.pkgsend(dfurl + "junk", "open foo@1.a", exit=1)

        def test_6_help(self):
                """Verify that help works as expected."""

                self.pkgsend(command="-?")
                self.pkgsend(command="--help")

                self.pkgsend(command="-? bobcat")
                self.pkgsend(command="--help bobcat")

                # Specifying no commands should result in usage error.
                self.pkgsend(exit=2)

        def test_7_create_repo(self):
                """Verify that create-repository works as expected."""

                self.dc.stop()
                rpath = os.path.join(self.get_test_prefix(), "example_repo")
                self.pkgsend("file://%s" % rpath,
                    "create-repository --set-property publisher.prefix=test")

                # Now verify that the repository was created by starting the
                # depot server in readonly mode using the target repository.
                # If it wasn't, restart_depots should fail with an exception
                # since the depot process will exit with a non-zero return
                # code.
                self.dc.set_repodir(rpath)
                self.dc.set_readonly()
                self.dc.start()

                # Now verify that creation of a repository is rejected for all
                # schemes execpt file://.
                self.pkgsend("http://invalid.test1", "create-repository", exit=1)
                self.pkgsend("https://invalid.test2", "create-repository", exit=1)

        def test_8_bug_7908(self):
                """Verify that when provided the name of a symbolic link to a
                file, that publishing will still work as expected."""

                # First create our dummy data file.
                fd, fpath = tempfile.mkstemp(dir=self.get_test_prefix())
                fp = os.fdopen(fd, "wb")
                fp.write("foo")
                fp.close()

                # Then, create a link to it.
                lpath = os.path.join(self.get_test_prefix(), "test_8_foo")
                os.symlink(fpath, lpath)

                # Next, publish it using both the real path and the linked path
                # but using different names.
                dhurl = self.dc.get_depot_url()
                self.pkgsend_bulk(dhurl,
                    """open testlinkedfile@1.0
                    add file %s mode=0755 owner=root group=bin path=/tmp/f.foo
                    add file %s mode=0755 owner=root group=bin path=/tmp/l.foo
                    close""" % (fpath, lpath))

                # Finally, verify that both files were published.
                self.image_create(dhurl)
                self.pkg("contents -r -H -o action.raw -t file testlinkedfile |"
                   " grep 'f.foo.*pkg.size=3'")
                self.pkg("contents -r -H -o action.raw -t file testlinkedfile |"
                   " grep 'l.foo.*pkg.size=3'")
                self.image_destroy()

        def test_9_multiple_dirs(self):
                rootdir = self.get_test_prefix()
                dir_1 = os.path.join(rootdir, "dir_1")
                dir_2 = os.path.join(rootdir, "dir_2")
                os.mkdir(dir_1)
                os.mkdir(dir_2)
                file(os.path.join(dir_1, "A"), "wb").close()
                file(os.path.join(dir_2, "B"), "wb").close()
                mfpath = os.path.join(rootdir, "manifest_test")
                mf = file(mfpath, "w")
                # test omission of set action by having illegal fmri value
                mf.write("""file NOHASH mode=0755 owner=root group=bin path=/A
                    file NOHASH mode=0755 owner=root group=bin path=/B
                    set name="fmri" value="totally_bogus"
                    """)
                mf.close()
                dhurl = self.dc.get_depot_url()
                self.pkgsend(dhurl,
                    """publish -d %s -d %s testmultipledirs@1.0 < %s"""
                    % (dir_1, dir_2, mfpath))
                self.image_create(dhurl)
                self.pkg("install testmultipledirs")
                self.pkg("verify")
                self.image_destroy()

        def test_10_bundle_dir(self):
                rootdir = self.get_test_prefix()
                dir1 = os.path.join(rootdir, "foo")
                os.mkdir(dir1)
                file(os.path.join(dir1, "bar"), "wb").close()
                url = self.dc.get_depot_url()
                self.pkgsend_bulk(url,
                """open foo@1.0
                import %s
                close""" % dir1 )
                self.image_create(url)
                self.pkg("install foo")
                self.image_destroy()

        def test_11_bundle_sysv_dir(self):
                rootdir = self.get_test_prefix()
                dir1 = os.path.join(rootdir, "foobar")
                os.mkdir(dir1)
                file(os.path.join(dir1, "bar"), "wb").close()
                pkginfopath = os.path.join(rootdir, "pkginfo")
                pkginfo = file(pkginfopath, "w")
                pkginfo.write('PKG="nopkg"\n'\
                              'NAME="No package"\n'\
                              'ARCH="all"\n'\
                              'CLASSES="none"\n'\
                              'CATEGORY="utility"\n'\
                              'VENDOR="nobody"\n'\
                              'PSTAMP="7thOct83"\n'\
                              'ISTATES="S s 1 2 3"\n'\
                              'RSTATES="S s 1 2 3"\n'\
                              'BASEDIR="/"')
                pkginfo.close()
                prototypepath = os.path.join(rootdir, "Prototype")
                prototype = file(prototypepath, "w")
                prototype.write("""i pkginfo
                d none foobar 0755 nobody nobody
                f none foobar/bar 0644 nobody nobody""")
                prototype.close()
                self.cmdline_run("pkgmk -o -r %s -d %s -f %s" %
                         (rootdir, rootdir, prototypepath))
                url = self.dc.get_depot_url()
                self.pkgsend_bulk(url,
                """open nopkg@1.0
                import %s
                close""" % (os.path.join(rootdir, "nopkg")) )
                os.remove(os.path.join(dir1, "bar"))
                os.rmdir(dir1)
                self.image_create(url)
                self.pkg("install nopkg")
                self.image_destroy()


        def test_12_bundle_sysv_datastream(self):
                rootdir = self.get_test_prefix()
                dir1 = os.path.join(rootdir, "foobar")
                os.mkdir(dir1)
                file(os.path.join(dir1, "bar"), "wb").close()
                pkginfopath = os.path.join(rootdir, "pkginfo")
                pkginfo = file(pkginfopath, "w")
                pkginfo.write('PKG="nopkg"\n'\
                              'NAME="No package"\n'\
                              'ARCH="all"\n'\
                              'CLASSES="none"\n'\
                              'CATEGORY="utility"\n'\
                              'VENDOR="nobody"\n'\
                              'PSTAMP="7thOct83"\n'\
                              'ISTATES="S s 1 2 3"\n'\
                              'RSTATES="S s 1 2 3"\n'\
                              'BASEDIR="/"')
                pkginfo.close()
                prototypepath = os.path.join(rootdir, "Prototype")
                prototype = file(prototypepath, "w")
                prototype.write("""i pkginfo
                d none foobar 0755 nobody nobody
                f none foobar/bar 0644 nobody nobody""")
                prototype.close()
                self.cmdline_run("pkgmk -o -r %s -d %s -f %s" %
                         (rootdir, rootdir, prototypepath))
                self.cmdline_run("pkgtrans -s %s %s nopkg" % (rootdir,
                        os.path.join(rootdir, "nopkg.pkg")))
                url = self.dc.get_depot_url()
                self.pkgsend_bulk(url,
                """open nopkg@1.0
                import %s
                close""" % os.path.join(rootdir, "nopkg.pkg") )
                os.remove(os.path.join(dir1, "bar"))
                os.rmdir(dir1)
                self.image_create(url)
                self.pkg("install nopkg")
                self.image_destroy()

        def test_13_pkgsend_indexcontrol(self):
                """Verify that "pkgsend close --no-index" suppresses
                indexing and that "pkgsend refresh-index" triggers
                indexing."""

                dhurl = self.dc.get_depot_url()
                dfurl = "file://%s" % urllib.pathname2url(self.dc.get_repodir())

                fd, fpath = tempfile.mkstemp(dir=self.get_test_prefix())

                self.image_create(dhurl)

                self.dc.stop()
                self.dc.set_readonly()

                self.pkgsend(dfurl, "open file@1.0")
                self.pkgsend(dfurl, "add file %s %s path=/tmp/f.foo" \
                    % ( fpath, "mode=0755 owner=root group=bin" ))
                self.pkgsend(dfurl, "close --no-index")

                self.dc.start()
                self.pkg("search file:::", exit=1)

                self.dc.stop()
                self.pkgsend(dfurl, "refresh-index")
                self.dc.start()
                self.pkg("search file:::")

                self.dc.stop()
                self.dc.set_readwrite()
                self.dc.start()

                self.pkgsend(dhurl, "open http@1.0")
                self.pkgsend(dhurl, "add file %s %s path=/tmp/f.foo" \
                    % ( fpath, "mode=0755 owner=root group=bin" ))
                self.pkgsend(dhurl, "close --no-index")

                self.pkg("search http:::", exit=1)

                self.pkgsend(dhurl, "refresh-index")

                self.pkg("search http:::")

                self.image_destroy()
                os.close(fd)
                os.unlink(fpath)

        def test_14_obsolete(self):
                """Obsolete and renamed packages can only have very specific
                content."""

                # Obsolete packages can't have contents
                badobs1 = """
                    open badobs@<ver>
                    add dir path=usr mode=0755 owner=root group=root
                    add set name=pkg.obsolete value=true
                    close
                """

                # Obsolete packages can't have contents (reordered)
                badobs2 = """
                    open badobs@<ver>
                    add set name=pkg.obsolete value=true
                    add dir path=usr mode=0755 owner=root group=root
                    close
                """

                # Renamed packages can't have contents
                badren1 = """
                    open badren@<ver>
                    add set name=pkg.renamed value=true
                    add dir path=usr mode=0755 owner=root group=root
                    add depend fmri=otherpkg type=require
                    close
                """

                # Renamed packages must have dependencies
                badren2 = """
                    open badren@<ver>
                    add set name=pkg.renamed value=true
                    close
                """

                # A package can't be marked both obsolete and renamed
                badrenobs1 = """
                    open badrenobs@<ver>
                    add set name=pkg.obsolete value=true
                    add set name=pkg.renamed value=true
                    close
                """

                # Obsolete packages can have metadata
                bob = """
                    open bobsyeruncle@<ver>
                    add set name=pkg.obsolete value=true
                    add set name=pkg.summary value="A test package"
                    close
                """

                # Package contents and line number where it should fail.
                pkgs = [
                    (badobs1, 3),
                    (badobs2, 3),
                    (badren1, 3),
                    (badren2, 3),
                    (badrenobs1, 3),
                    (bob, -1)
                ]
                dhurl = self.dc.get_depot_url()
                junk_repo = os.path.join(self.get_test_prefix(), "obs-junkrepo")
                dfurl = "file://" + junk_repo
                self.pkgsend(dfurl,
                    "create-repository --set-property publisher.prefix=test")

                ver = 0
                for p, line in pkgs:
                        for url in (dhurl, dfurl):
                                # Try a bulk pkgsend first
                                exit = int(line >= 0)
                                # We publish fast enough that we can end up
                                # publishing the same package version twice
                                # within the same second, so force the version
                                # to be incremented.
                                p2 = p.replace("<ver>", str(ver))
                                self.pkgsend_bulk(url, p2, exit=exit)
                                #if exit:
                                #        self.pkgsend(url, "close -A")

                                # Then do it line-by-line
                                for i, l in enumerate(p.splitlines()):
                                        if not l.strip():
                                                continue
                                        exit = int(i == line)
                                        l = l.replace("<ver>", str(ver + 1))
                                        self.pkgsend(url, l.strip(), exit=exit)
                                        if exit:
                                                self.pkgsend(url, "close -A")
                                                break
                                ver += 2

        def test_15_test_no_catalog_option(self):
                """Verify that --no-catalog works as expected.  Also exercise
                --fmri-in-manifest"""
                pkg_manifest = \
"""set name=pkg.fmri value=foo@0.5.11,5.11-0.129
dir path=foo mode=0755 owner=root group=bin
dir path=foo/bar mode=0755 owner=root group=bin
"""
                self.dc.stop()
                rpath = self.dc.get_repodir()
                fpath = os.path.join(self.get_test_prefix(), "manifest")
                f = file(fpath, "w")
                f.write(pkg_manifest)
                f.close()
                self.pkgsend("file://%s" % rpath,
                    "create-repository --set-property publisher.prefix=test")
                cat_path = os.path.join(rpath, "catalog/catalog.attrs")
                mtime = os.stat(cat_path).st_mtime                
                self.pkgsend("file://%s publish --fmri-in-manifest --no-catalog %s" % (
                                rpath, fpath))
                new_mtime = os.stat(cat_path).st_mtime
                assert(mtime == new_mtime, "modified times not the same before and after publication")
                self.dc.set_add_content()
                
                self.dc.start()
                
                dhurl = self.dc.get_depot_url()
                self.dc.set_repodir(rpath)
                self.image_create(dhurl)
                self.pkg("list -a foo")
                self.image_destroy()

if __name__ == "__main__":
        unittest.main()
