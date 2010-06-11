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

# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import os.path
import pkg.fmri as fmri
import pkg.manifest as manifest
import shutil
import stat
import tempfile
import unittest
import urllib

from pkg import misc
from pkg.actions import fromstr
import pkg.portable as portable


class TestPkgsendBasics(pkg5unittest.SingleDepotTestCase):
        persistent_setup = False

        def setUp(self):
                # This test suite needs an actual depot.
                pkg5unittest.SingleDepotTestCase.setUp(self, start_depot=True)

        def __validate_bundle_dir_package(self, pfmri, expected):
                """Used to validate a package imported or generated using
                a DirectoryBundle.  Validation includes installing and
                verifying the specified package, as well as comparing
                the package manifest actions to the expected action data.
                Only dir, file, link, and hardlink actions are compared.

                'pfmri' is a package FMRI object for the package.

                'expected' is a string containing the raw action data to
                use to validate the package.  Only the attributes present
                on each action will be compared."""

                self.pkg("install %s" % pfmri)
                self.pkg("verify %s" % pfmri)

                m = manifest.Manifest()
                content = self.get_img_manifest(pfmri)
                m.set_content(content)

                # Now build action objects from expected data indexed by path.
                exp_actions = {}
                for entry in expected.splitlines():
                        a = fromstr(entry)

                        if a.attrs["path"] in exp_actions:
                                raise RuntimeError(a.attrs["path"])

                        exp_actions[a.attrs["path"]] = a

                # Number of actions should match number of expected entries.
                self.assertEqual(len(exp_actions), len(expected.splitlines()))

                # Number of expected actions should match number of actual.
                actual = [
                    a for a in m.gen_actions()
                    if a.name in ("dir", "file", "link", "hardlink")
                ]
                self.assertEqual(len(exp_actions), len(actual))

                # For each dir, file, link, or hardlink action, verify that the
                # attributes match expected.
                for a in actual:
                        exp = exp_actions[a.attrs["path"]]
                        for attr in exp.attrs:
                                self.assertEqual(exp.attrs[attr], a.attrs[attr])

                self.pkg("uninstall %s" % pfmri)

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
                junk_repo = os.path.join(self.test_root, "junk-repo")
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
                        self.pkgsend(url, "add file bin/ls path=/bin/ls",
                            exit=1)

        def test_4_bad_actions(self):
                """Verify that malformed or invalid actions are handled
                correctly.  This only checks a few cases as the pkg.action
                class itself should be handling the actual verification;
                the client just needs to handle the appropriate exceptions
                gracefully."""

                dhurl = self.dc.get_depot_url()
                dfurl = "file://%s" % self.dc.get_repodir()
                imaginary_file = os.path.join(self.test_root, "imaginary_file")

                # Must open transaction using HTTP url first so that transaction
                # will be seen by the depot server and when using file://.
                self.pkgsend(dhurl, "open foo@1.0")

                # Create a dummy file.
                self.make_misc_files("tmp/dummy1")

                for url in (dhurl, dfurl):
                        # Should fail because type attribute is missing.
                        self.pkgsend(url,
                            "add depend fmri=foo@1.0", exit=1)

                        # Should fail because type attribute is invalid.
                        self.pkgsend(url,
                            "add depend type=unknown fmri=foo@1.0", exit=1)

                        # Should fail because path attribute is missing.
                        self.pkgsend(url,
                            "add file bin/ls", exit=1)

                        # Should fail because mode attribute is missing.
                        self.pkgsend(url,
                            "add file tmp/dummy1 owner=root group=bin "
                            "path=/tmp/dummy1", exit=1)

                        # Should fail because mode attribute is invalid.
                        self.pkgsend(url,
                            """add file tmp/dummy1 owner=root group=bin """
                            """mode="" path=/tmp/dummy1""", exit=1)
                        self.pkgsend(url,
                            "add file tmp/dummy1 owner=root group=bin "
                            "mode=44755 path=/tmp/dummy1", exit=1)
                        self.pkgsend(url,
                            "add file tmp/dummy1 owner=root group=bin "
                            "mode=44 path=/tmp/dummy1", exit=1)
                        self.pkgsend(url,
                            """add file tmp/dummy1 owner=root group=bin """
                            """mode=???? path=/tmp/dummy1""", exit=1)

                        # Should fail because owner attribute is missing.
                        self.pkgsend(url,
                            "add file tmp/dummy1 group=bin "
                            "mode=0644 path=/tmp/dummy1", exit=1)

                        # Should fail because owner attribute is invalid.
                        self.pkgsend(url,
                            """add file tmp/dummy1 owner=" " group=bin """
                            """mode=0644 path=/tmp/dummy1""", exit=1)

                        # Should fail because group attribute is missing.
                        self.pkgsend(url,
                            "add file tmp/dummy1 owner=root "
                            "mode=0644 path=/tmp/dummy1", exit=1)

                        # Should fail because group attribute is invalid.
                        self.pkgsend(url,
                            """add file tmp/dummy1 owner=root group=" " """
                            """mode=0644 path=/tmp/dummy1""", exit=1)

                        # Should fail because path attribute is missing a value.
                        self.pkgsend(url,
                            "add file bin/ls path=", exit=1)

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

                        # Should fail because we never publish unknown actions.
                        self.pkgsend(url,
                             "add unknown path=foo", exit=1)

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
                rpath = os.path.join(self.test_root, "example_repo")

                # ensure we fail when presented with a file://host/path/example_repo
                # which includes a hostname, bug 14022
                self.pkgsend("file:/%s" % rpath, "create-repository"
                    " --set-property publisher.prefix=test", exit=1)

                # check that we can create a repository using URIs with varying
                # number of '/' characters and verify the repo was created.
                for slashes in [ "", "//", "///", "////" ]:
                        if os.path.exists(rpath):
                                shutil.rmtree(rpath)
                        self.pkgsend("file:%s%s" % (slashes, rpath), "create-repository"
                            " --set-property publisher.prefix=test")

                        # Now verify that the repository was created by starting the
                        # depot server in readonly mode using the target repository.
                        # If it wasn't, restart_depots should fail with an exception
                        # since the depot process will exit with a non-zero return
                        # code.
                        self.dc.set_repodir(rpath)
                        self.dc.set_readonly()
                        self.dc.start()
                        self.dc.stop()

                # Now verify that creation of a repository is rejected for all
                # schemes except file://.
                self.pkgsend("http://invalid.test1", "create-repository", exit=1)
                self.pkgsend("https://invalid.test2", "create-repository", exit=1)

        def test_8_bug_7908(self):
                """Verify that when provided the name of a symbolic link to a
                file, that publishing will still work as expected."""

                # First create our dummy data file.
                fd, fpath = tempfile.mkstemp(dir=self.test_root)
                fp = os.fdopen(fd, "wb")
                fp.write("foo")
                fp.close()

                # Then, create a link to it.
                lpath = os.path.join(self.test_root, "test_8_foo")
                os.symlink(fpath, lpath)

                # Next, publish it using both the real path and the linked path
                # but using different names.
                dhurl = self.dc.get_depot_url()
                self.pkgsend_bulk(dhurl,
                    """open testlinkedfile@1.0
                    add file %s mode=0755 owner=root group=bin path=/tmp/f.foo
                    add file %s mode=0755 owner=root group=bin path=/tmp/l.foo
                    close""" % (os.path.basename(fpath), os.path.basename(lpath)))

                # Finally, verify that both files were published.
                self.image_create(dhurl)
                self.pkg("contents -r -H -o action.raw -t file testlinkedfile |"
                   " grep 'f.foo.*pkg.size=3'")
                self.pkg("contents -r -H -o action.raw -t file testlinkedfile |"
                   " grep 'l.foo.*pkg.size=3'")
                self.image_destroy()

        def test_9_multiple_dirs(self):
                rootdir = self.test_root
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
                """Verify that import and generate of a directory bundle works
                as expected."""

                rootdir = self.test_root
                src_dir1 = os.path.join(rootdir, "foo")
                src_dir2 = os.path.join(rootdir, "bar")

                # Build a file tree under each source directory to test
                # import and generate functionality.  Tree should look like:
                #   src-foo/
                #       file-foo
                #       link-foo -> file-foo
                #       hardlink-foo -> file-foo
                #       dir-foo/
                #           subfile-foo
                #           sublink-foo -> ../file-foo
                #           subhardlink-foo -> ../file-foo
                #           subfilelink-foo -> subfile-foo
                #           subfilehardlink-foo -> subfile-foo
                #           subdir-foo/
                #               subdirfile-foo
                #
                #  Where 'foo' is replaced with 'bar' for the second source dir.

                cwd = os.getcwd()
                for src_dir in (src_dir1, src_dir2):
                        # Final component used as part of name for all entries.
                        name = os.path.basename(src_dir)

                        # File at top level in source directory.
                        top_file = os.path.join(src_dir, "file-%s" % name)
                        self.make_misc_files(os.path.relpath(top_file, src_dir),
                            prefix=name, mode=0644)

                        # Link at top level in source directory.
                        os.chdir(src_dir)
                        os.symlink(os.path.basename(top_file), "link-%s" % name)
                        os.chdir(cwd)

                        # Hard link at top level in source directory.
                        os.link(top_file, os.path.join(src_dir,
                            "hardlink-%s" % name))

                        # Directory at top level in source directory.
                        top_dir = os.path.join(src_dir, "dir-%s" % name)
                        os.mkdir(top_dir, 0755)

                        # File in top_dir.
                        top_dir_file = os.path.join(top_dir,
                            "subfile-%s" % name)
                        self.make_misc_files(os.path.relpath(top_dir_file,
                            src_dir), prefix=name, mode=0444)

                        # Link in top_dir to file in parent dir.
                        os.chdir(top_dir)
                        os.symlink(os.path.relpath(top_file, top_dir),
                            "sublink-%s" % name)
                        os.chdir(cwd)

                        # Link in top_dir to file in top_dir.
                        os.chdir(top_dir)
                        os.symlink(os.path.basename(top_dir_file),
                            "subfilelink-%s" % name)
                        os.chdir(cwd)

                        # Hard link in top_dir to file in parent dir.
                        os.link(top_file, os.path.join(top_dir,
                            "subhardlink-%s" % name))

                        # Hard link in top_dir to file in top_dir.
                        os.link(top_dir_file, os.path.join(top_dir,
                            "subfilehardlink-%s" % name))

                        # Directory in top_dir.
                        sub_dir = os.path.join(top_dir, "subdir-%s" % name)
                        os.mkdir(sub_dir, 0750)

                        # File in sub_dir.
                        sub_dir_file = os.path.join(sub_dir,
                            "subdirfile-%s" % name)
                        self.make_misc_files(os.path.relpath(sub_dir_file,
                            src_dir), prefix=name, mode=0400)

                # Pre-generated result used for package validation.
                expected = """\
dir group=bin mode=0755 owner=root path=dir-foo
file 4b5e791c627772d731d6c1623228a9c147a7dc3a chash=57ac66d45c0c4adb6d3626bd711c6f09f10fd286 group=bin mode=0644 owner=root path=file-foo
link path=link-foo target=file-foo
hardlink path=hardlink-foo target=file-foo
dir group=bin mode=0750 owner=root path=dir-foo/subdir-foo
file a10c7e788532fd2e7ee7eb9682733dd4e3fbe9de chash=aa3025ca5df3f9f6560db438b1b748d8155c9763 group=bin mode=0444 owner=root path=dir-foo/subfile-foo
link path=dir-foo/sublink-foo target=../file-foo
link path=dir-foo/subfilelink-foo target=subfile-foo
hardlink path=dir-foo/subhardlink-foo target=../file-foo
hardlink path=dir-foo/subfilehardlink-foo target=subfile-foo
file 7e810bfd0fddc15334ae8f8c5720417c19d26d65 chash=d4e6a65e17cad442857eea1885b909b09e96f40e group=bin mode=0400 owner=root path=dir-foo/subdir-foo/subdirfile-foo
dir group=bin mode=0755 owner=root path=dir-bar
file 994c33bbd9d77c3a54a1130d07f87f9d57c91d53 chash=98b4c123eefd676a472924e004dc293ddd44f73a group=bin mode=0644 owner=root path=file-bar
link path=link-bar target=file-bar
hardlink path=hardlink-bar target=file-bar
dir group=bin mode=0750 owner=root path=dir-bar/subdir-bar
file 1e4760226a169690da06b592e8eedb6d79c1b3a0 chash=71d14067e564c3c52261918788f353e99d249a87 group=bin mode=0444 owner=root path=dir-bar/subfile-bar
link path=dir-bar/sublink-bar target=../file-bar
link path=dir-bar/subfilelink-bar target=subfile-bar
hardlink path=dir-bar/subhardlink-bar target=../file-bar
hardlink path=dir-bar/subfilehardlink-bar target=subfile-bar
file 6a1ae3def902f5612a43f0c0836fe05bc4f237cf chash=be9c91959ec782acb0f081bf4bf16677cb09125e group=bin mode=0400 owner=root path=dir-bar/subdir-bar/subdirfile-bar"""

                # Test with and without trailing slash on import path.
                # This cannot be done using pkgsend_bulk, which doesn't
                # support import.
                url = self.dc.get_depot_url()
                self.pkgsend(url, "open foo@1.0")
                self.pkgsend(url, "import %s" % src_dir1)
                self.pkgsend(url, "import %s/" % src_dir2)
                ret, sfmri = self.pkgsend(url, "close")
                foo_fmri = fmri.PkgFmri(sfmri, "5.11")

                # Test with and without trailing slash on generate path.
                # This cannot be done using pkgsend_bulk, which doesn't
                # support generate.
                rc, out1 = self.pkgsend(url, "generate %s" % src_dir1)
                rc, out2 = self.pkgsend(url, "generate %s/" % src_dir2)

                # Test with non existing bundle
                non_existing_bundle = os.path.join(self.test_root,
                    "non_existing_bundle.tar")
                rc, out3 = self.pkgsend(url, "generate %s" % non_existing_bundle, exit=1)

                # Test with unknown bundle
                unknown_bundle = self.make_misc_files("tmp/unknown_file")
                rc, out3 = self.pkgsend(url, "generate %s" % unknown_bundle, exit=1)

                self.pkgsend(url, "open bar@1.0")
                mpath = self.make_misc_files({ "bar.mfst": out1 + out2 })[0]
                self.pkgsend(url, "include -d %s -d %s %s" % (src_dir1,
                    src_dir2, mpath))
                ret, sfmri = self.pkgsend(url, "close")
                bar_fmri = fmri.PkgFmri(sfmri, "5.11")

                self.image_create(url)

                # Perform actual validation; content should be identical
                # whether import or generate was used.
                for pfmri in (foo_fmri, bar_fmri):
                        self.__validate_bundle_dir_package(pfmri, expected)


        # A map used to create a SVR4 package, and check an installed pkg(5)
        # version of that package, created via 'pkgsend import'.  We map the
        # path name to
        # [ type, mode, user, group, digest ] initially setting the digest to None
        sysv_contents = {
            "foobar": [ "d", 0715, "nobody", "nobody", None ],
            "foobar/bar": [ "f", 0614, "root", "sys", None ],
            "foobar/baz": [ "f", 0644, "daemon", "adm", None ],
            "foobar/symlink": [ "s", None, "daemon", "adm", None ],
            "foobar/hardlink": [ "l", 0644, "daemon", "adm", None ],
            "copyright": [ "i", None, None, None, None ],
            # check that pkgsend doesn't generate an Action for "i" files
            "pkginfo": [ "i", None, None, None, None ],
            "myclass": [ "i", None, None, None, None ],
            "prototype": [ "i", None, None, None, None ],
            # pkgmap is not an "i" file, but we still want to
            # check that it is not installed in the image
            "pkgmap": [ "i", None, None, None, None ] }

        sysv_prototype = """i pkginfo
            i copyright
            d none foobar 0715 nobody nobody
            f none foobar/bar 0614 root sys
            f myclass foobar/baz 0644 daemon adm
            s none foobar/symlink=baz
            l none foobar/hardlink=baz
            i myclass"""

        sysv_pkginfo = 'PKG="nopkg"\n'\
            'NAME="No package"\n'\
            'ARCH="all"\n'\
            'CLASSES="none myclass"\n'\
            'CATEGORY="utility"\n'\
            'VENDOR="nobody"\n'\
            'PSTAMP="7thOct83"\n'\
            'ISTATES="S s 1 2 3"\n'\
            'RSTATES="S s 1 2 3"\n'\
            'BASEDIR="/"'

        def create_sysv_package(self, rootdir):
                """Create a SVR4 package at a given location using some predefined
                contents."""
                pkgroot = os.path.join(rootdir, "sysvpkg")
                os.mkdir(pkgroot)

                # create files and directories in our proto area
                for entry in self.sysv_contents:
                        ftype, mode  = self.sysv_contents[entry][:2]
                        if ftype in "fi":
                                dirname = os.path.dirname(entry)
                                try:
                                        os.makedirs(os.path.join(pkgroot, dirname))
                                except OSError, err: # in case the dir exists already
                                        if err.errno != os.errno.EEXIST:
                                                raise                                        
                                fpath = os.path.join(pkgroot, entry)
                                f = file(fpath, "wb")
                                f.write("test" + entry)
                                f.close()
                                # compute a digest of the file we just created, which
                                # we can use when validating later.
                                self.sysv_contents[entry][4] = \
                                    misc.get_data_digest(fpath)[0]

                        elif ftype == "d":
                                try:
                                        os.makedirs(os.path.join(pkgroot, entry), mode)
                                except OSError, err:
                                        if err.errno != os.errno.EEXIST:
                                                raise

                pkginfopath = os.path.join(pkgroot, "pkginfo")
                pkginfo = file(pkginfopath, "w")
                pkginfo.write(self.sysv_pkginfo)
                pkginfo.close()

                prototypepath = os.path.join(pkgroot, "prototype")
                prototype = file(prototypepath, "w")
                prototype.write(self.sysv_prototype)
                prototype.close()

                self.cmdline_run("pkgmk -o -r %s -d %s -f %s" %
                         (pkgroot, rootdir, prototypepath))

                shutil.rmtree(pkgroot)

        def test_11_bundle_sysv_dir(self):
                """ A SVR4 directory-format package can be imported, its contents
                published to a repo and installed to an image."""
                rootdir = self.test_root
                self.create_sysv_package(rootdir)
                url = self.dc.get_depot_url()

                self.pkgsend(url, "open nopkg@1.0")
                self.pkgsend(url, "import %s" % os.path.join(rootdir, "nopkg"))
                self.pkgsend(url, "close")

                self.image_create(url)
                self.pkg("install nopkg")
                self.validate_sysv_contents("nopkg")
                self.pkg("verify")
                self.image_destroy()

        def test_12_bundle_sysv_datastream(self):
                """ A SVR4 datastream package can be imported, its contents published to
                a repo and installed to an image."""
                rootdir = self.test_root
                self.create_sysv_package(rootdir)
                self.cmdline_run("pkgtrans -s %s %s nopkg" % (rootdir,
                        os.path.join(rootdir, "nopkg.pkg")))

                url = self.dc.get_depot_url()
                self.pkgsend(url, "open nopkg@1.0")
                self.pkgsend(url, "import %s" % os.path.join(rootdir, "nopkg"))
                self.pkgsend(url, "close")

                self.image_create(url)
                self.pkg("install nopkg")
                self.validate_sysv_contents("nopkg")
                self.pkg("verify")
                self.image_destroy()

        def validate_sysv_contents(self, pkgname):
                """ Check that the image contents correspond to the SVR4 package.
                The tests in t_pkginstall cover most of the below, however
                here we're interested in ensuring that pkgsend really did import
                and publish everything we expected from the sysv package.
                """

                # verify we have copyright text
                self.pkg("info --license %s" % pkgname)

                for entry in self.sysv_contents:
                        name = os.path.join(self.img_path, entry)
                        ftype, mode, user, group, digest = self.sysv_contents[entry]

                        if ftype in "fl":
                                self.assertTrue(os.path.isfile(name))
                        elif ftype == "d":
                                self.assertTrue(os.path.isdir(name))
                        elif ftype == "s":
                                self.assertTrue(os.path.islink(name))
                        elif ftype == "i":
                                # we should not have installed these
                                self.assertFalse(os.path.exists(name))
                                continue

                        if digest:
                                pkg5_digest = misc.get_data_digest(name)[0]
                                self.assertEqual(digest, pkg5_digest)

                        st = os.stat(os.path.join(self.img_path, name))
                        if mode is not None:
                                portable.assert_mode(name, stat.S_IMODE(mode))
                        self.assertEqual(portable.get_user_by_name(user,
                            self.img_path, use_file=True), st.st_uid)
                        self.assertEqual(portable.get_group_by_name(group,
                            self.img_path, use_file=True), st.st_gid)
    
        def test_13_pkgsend_indexcontrol(self):
                """Verify that "pkgsend close --no-index" suppresses
                indexing and that "pkgsend refresh-index" triggers
                indexing."""

                dhurl = self.dc.get_depot_url()
                dfurl = "file://%s" % urllib.pathname2url(self.dc.get_repodir())

                fd, fpath = tempfile.mkstemp(dir=self.test_root)

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
                junk_repo = os.path.join(self.test_root, "obs-junkrepo")
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
                fpath = os.path.join(self.test_root, "manifest")
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
                # check that modified times are the same before and after publication
                self.assertEqual(mtime, new_mtime)
                self.dc.set_add_content()

                self.dc.start()

                dhurl = self.dc.get_depot_url()
                self.dc.set_repodir(rpath)
                self.image_create(dhurl)
                self.pkg("list -a foo")
                self.image_destroy()

        def test_16_multiple_manifests(self):
                """Verify that when sending multiple manifests, the contents
                of all manifests are published."""

                # First create two dummy data files.
                test_files = ["dummy1", "dummy2"]
                self.make_misc_files(test_files)

                # create two manifests.
                for path in test_files:
                        manfpath = path + ".manifest"
                        self.make_misc_files({
                            manfpath:
                                "file %s mode=0644 owner=root group=bin "
                                "path=/foo%s" % (path, path)})

                # publish
                url = self.dc.get_depot_url()
                self.pkgsend(url, "open multiple_mf@1.0")
                manifests = " ".join([path + ".manifest" for path in test_files])
                self.pkgsend(url, "include " + manifests)
                self.pkgsend(url, "close")

                # Finally, verify that both files were published.
                self.image_create(url)
                for path in test_files:
                        self.pkg("contents -r -H -o action.raw -t file multiple_mf |"
                            " grep %s" % path)
                self.image_destroy()

        def test_17_include_errors(self):
                """Verify that pkgsend include handles error conditions
                gracefully."""

                url = self.dc.get_depot_url()

                # Start a transaction.
                self.pkgsend(url, "open foo@1.0")

                # Verify no such include file handled.
                self.pkgsend(url, "include nosuchfile", exit=1)

                # Verify files with invalid content handled.
                misc = self.make_misc_files({
                    "invalid": "!%^$%^@*&$ bobcat",
                    "empty": "",
                })
                self.pkgsend(url, "include %s" % " ".join(misc), exit=1)


if __name__ == "__main__":
        unittest.main()
