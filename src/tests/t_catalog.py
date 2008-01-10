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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import unittest
import shutil
import tempfile
import os
import datetime

import pkg.fmri as fmri
import pkg.catalog as catalog
import pkg.updatelog as updatelog

class TestCatalog(unittest.TestCase):
        def setUp(self):
                self.cpath = tempfile.mkdtemp()
                self.c = catalog.Catalog(self.cpath)
                self.npkgs = 0

                for f in [
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1:20000101T120000Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1:20000101T120010Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1.1:20000101T120020Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1.2:20000101T120030Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-2:20000101T120040Z", None),
                    fmri.PkgFmri("pkg:/test@1.1,5.11-1:20000101T120040Z", None),
                    fmri.PkgFmri("pkg:/apkg@1.0,5.11-1:20000101T120040Z", None),
                    fmri.PkgFmri("pkg:/zpkg@1.0,5.11-1:20000101T120040Z", None)
                ]:
                        self.c.add_fmri(f)
                        self.npkgs += 1

        def tearDown(self):
                shutil.rmtree(self.cpath)

        def testnpkgs(self):
                self.assert_(self.npkgs == self.c.npkgs())

        def testcatalogfmris1(self):
                cf = fmri.PkgFmri("pkg:/test@1.0,5.10-1:20070101T120000Z")
                cl = self.c.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 4)

        def testcatalogfmris2(self):
                cf = fmri.PkgFmri("pkg:/test@1.0,5.11-1:20061231T120000Z")
                cl = self.c.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 4)

        def testcatalogfmris3(self):
                cf = fmri.PkgFmri("pkg:/test@1.0,5.11-2")
                cl = self.c.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 2)

        def testcatalogfmris4(self):
                cf = fmri.PkgFmri("pkg:/test@1.0,5.11-3")
                cl = self.c.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 1)

        def testcatalogregex1(self):
                cl = self.c.get_matching_fmris("flob",
                    matcher = fmri.regex_match)

                self.assert_(len(cl) == 0)

class TestEmptyCatalog(unittest.TestCase):
        def setUp(self):
                self.cpath = tempfile.mkdtemp()
                self.c = catalog.Catalog(self.cpath)
                # XXX How do we do this on Windows?
                self.nullf = file("/dev/null", "w")

        def tearDown(self):
                shutil.rmtree(self.cpath)
                self.nullf.close()

        def testmatchingfmris(self):
                cf = fmri.PkgFmri("pkg:/test@1.0,5.11-1:20061231T120000Z")
                cl = self.c.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 0)

        def testfmris(self):
                r = []

                for f in self.c.fmris():
                        r.append(f)

                self.assert_(len(r) == 0)

        def testloadattrs(self):
                self.c.load_attrs()

        def testsend(self):
                self.c.send(self.nullf)

class TestUpdateLog(unittest.TestCase):
        def setUp(self):
                self.cpath = tempfile.mkdtemp()
                self.c = catalog.Catalog(self.cpath)
                self.upath = tempfile.mkdtemp()
                self.ul = updatelog.UpdateLog(self.upath, self.c)
                self.npkgs = 0

                for f in [
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1:20000101T120000Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1:20000101T120010Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1.1:20000101T120020Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1.2:20000101T120030Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-2:20000101T120040Z", None),
                    fmri.PkgFmri("pkg:/test@1.1,5.11-1:20000101T120040Z", None),
                    fmri.PkgFmri("pkg:/apkg@1.0,5.11-1:20000101T120040Z", None),
                    fmri.PkgFmri("pkg:/zpkg@1.0,5.11-1:20000101T120040Z", None)
                ]:
                        self.ul.add_package(f)
                        self.npkgs += 1

                delta = datetime.timedelta(seconds = 1)
                self.ts1 = self.ul.first_update - delta
                self.ts2 = datetime.datetime.now()


        def tearDown(self):
                shutil.rmtree(self.upath)
                shutil.rmtree(self.cpath)

        def testnohist(self):
                self.failIf(self.ul.enough_history(self.ts1))
                self.assert_(self.ul.enough_history(self.ts2))

        def testnotuptodate(self):
                self.assert_(self.ul.up_to_date(self.ts2))
                self.failIf(self.ul.up_to_date(self.ts1))

        def testoneupdate(self):
                # Create new catalog
                cnp = tempfile.mkdtemp()
                cfd, cfpath = tempfile.mkstemp()
                cfp = os.fdopen(cfd, "w")

                # send original catalog
                self.c.send(cfp)
                cfp.close()
                # recv the sent catalog
                cfp = file(cfpath, "r")
                catalog.recv(cfp, cnp)
                # Cleanup cfp
                cfp.close()
                cfp = None
                cfd = None
                os.remove(cfpath)
                cfpath = None

                # Instantiate Catalog object based upon recd. catalog
                cnew = catalog.Catalog(cnp)

                # Verify original packages present
                cf = fmri.PkgFmri("pkg:/test@1.0,5.10-1:20070101T120000Z")
                cl = cnew.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 4)

                # Add new FMRI
                fnew = fmri.PkgFmri("pkg:/test@1.0,5.11-3:20000101T120040Z")
                self.ul.add_package(fnew)

                # Send an update
                cfd, cfpath = tempfile.mkstemp()
                cfp = os.fdopen(cfd, "w")

                lastmod = catalog.ts_to_datetime(cnew.last_modified())
                self.ul._send_updates(lastmod, cfp)
                cfp.close()

                # Recv the update
                cfp = file(cfpath, "r")
                updatelog.UpdateLog._recv_updates(cfp, cnp, cnew.last_modified())
                cfp.close()
                cfp = None
                cfd = None
                os.remove(cfpath)
                cfpath = None

                # Reload the catalog
                cnew = catalog.Catalog(cnp)

                # Verify new package present
                cf = fmri.PkgFmri("pkg:/test@1.0,5.11-3:20000101T120040Z")
                cl = cnew.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 2)

                # Cleanup new catalog
                shutil.rmtree(cnp)

        def testsequentialupdate(self):
                # Create new catalog
                cnp = tempfile.mkdtemp()
                cfd, cfpath = tempfile.mkstemp()
                cfp = os.fdopen(cfd, "w")

                # send original catalog
                self.c.send(cfp)
                cfp.close()
                # recv the sent catalog
                cfp = file(cfpath, "r")
                catalog.recv(cfp, cnp)
                # Cleanup cfp
                cfp.close()
                cfp = None
                cfd = None
                os.remove(cfpath)
                cfpath = None

                # Instantiate Catalog object based upon recd. catalog
                cnew = catalog.Catalog(cnp)

                # Verify original packages present
                cf = fmri.PkgFmri("pkg:/test@1.0,5.10-1:20070101T120000Z")
                cl = cnew.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 4)

                # Add new FMRI
                fnew = fmri.PkgFmri("pkg:/bpkg@1.0,5.11-3:20000101T120040Z")
                self.ul.add_package(fnew)

                # Send an update
                cfd, cfpath = tempfile.mkstemp()
                cfp = os.fdopen(cfd, "w")

                lastmod = catalog.ts_to_datetime(cnew.last_modified())
                self.ul._send_updates(lastmod, cfp)
                cfp.close()

                # Recv the update
                cfp = file(cfpath, "r")
                updatelog.UpdateLog._recv_updates(cfp, cnp, cnew.last_modified())
                cfp.close()
                cfp = None
                cfd = None
                os.remove(cfpath)
                cfpath = None

                # Reload the catalog
                cnew = catalog.Catalog(cnp)

                # Verify new package present
                cf = fmri.PkgFmri("pkg:/bpkg@1.0,5.11-3:20000101T120040Z")
                cl = cnew.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 1)

                # Add a pair of FMRIs
                f2 = fmri.PkgFmri("pkg:/cpkg@1.0,5.11-3:20000101T120040Z")
                f3 = fmri.PkgFmri("pkg:/dpkg@1.0,5.11-3:20000101T120040Z")
                self.ul.add_package(f2)
                self.ul.add_package(f3)

                # Send another update
                cfd, cfpath = tempfile.mkstemp()
                cfp = os.fdopen(cfd, "w")

                lastmod = catalog.ts_to_datetime(cnew.last_modified())
                self.ul._send_updates(lastmod, cfp)
                cfp.close()

                # Recv the update
                cfp = file(cfpath, "r")
                updatelog.UpdateLog._recv_updates(cfp, cnp, cnew.last_modified())
                cfp.close()
                cfp = None
                cfd = None
                os.remove(cfpath)
                cfpath = None

                # Reload catalog
                cnew = catalog.Catalog(cnp)

                # Verify New packages present
                cf = fmri.PkgFmri("pkg:/cpkg@1.0,5.11-3:20000101T120040Z")
                cl = cnew.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 1)

                cf = fmri.PkgFmri("pkg:/dpkg@1.0,5.11-3:20000101T120040Z")
                cl = cnew.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 1)

                # Cleanup new catalog
                shutil.rmtree(cnp)

        def testrolllogfiles(self):
                # Write files with out-of-date timestamps into the updatelog
                # directory

                for i in range(2001010100, 2001010111, 1):
                        f = file(os.path.join(self.upath, "%s" % i), "w")
                        f.close()

                # Reload UpdateLog with maxfiles set to 1
                self.ul = updatelog.UpdateLog(self.upath, self.c, 1)

                # Adding a package should open a new logfile, and remove the
                # extra old ones
                cf = fmri.PkgFmri("pkg:/cpkg@1.0,5.11-3:20000101T120040Z")
                self.ul.add_package(cf)

                # Check that only one file remains in the directory
                dl = os.listdir(self.upath)
                self.assert_(len(dl) == 1)

if __name__ == "__main__":
        unittest.main()
