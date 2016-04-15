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

# Copyright (c) 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import unittest

class TestPkgModified(pkg5unittest.SingleDepotTestCase):
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        foo10 = """
            open foo@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file tmp/cat mode=0644 owner=root group=bin path=etc/motd
            close """

        misc_files = ["tmp/cat"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

        def __assert_image_modified(self, api_inst, omtime, modified):
                mfpath = os.path.join(api_inst.img.imgdir, "modified")
                nmtime = os.stat(mfpath).st_mtime
                if modified:
                        self.assertNotEqual(omtime, nmtime)
                else:
                        self.assertEqual(omtime, nmtime)
                return nmtime

        def test_modified(self):
                """Verify that $IMGDIR/modified is updated whenever an
                image-modifying operation is completed."""

                api_inst = self.image_create(self.rurl)
                mfpath = os.path.join(api_inst.img.imgdir, "modified")

                # Assert /var/pkg/modified exists.
                self.file_exists(mfpath)
                omtime = os.stat(mfpath).st_mtime

                self.pkgsend_bulk(self.rurl, self.foo10)

                # Now perform various operations and assert the image was marked
                # as modified or not depending on operation.
                self.__assert_image_modified(api_inst, omtime, False)

                self.pkg("refresh")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                #
                # Operations that should not mark image as modified.
                #
                for op, op_ret in (
                    ("facet", 0),
                    ("contents", 1),
                    ("history", 0),
                    ("info", 1),
                    ("info -r \*", 0),
                    ("list", 1),
                    ("mediator", 0),
                    ("property", 0),
                    ("unset-property no-such-property", 1),
                    ("publisher", 0),
                    ("refresh no-such-publisher", 1),
                    ("variant", 0)
                ):
                        self.pkg(op, exit=op_ret)
                        self.__assert_image_modified(api_inst, omtime, False)

                self.pkg("version", use_img_root=False)
                self.__assert_image_modified(api_inst, omtime, False)

                #
                # Now perform various combos of operations testing modification.
                #
                self.pkg("refresh")
                omtime = self.__assert_image_modified(api_inst, omtime, False)

                self.pkg("install -nv foo")
                omtime = self.__assert_image_modified(api_inst, omtime, False)

                self.pkg("install --reject foo foo", exit=1)
                omtime = self.__assert_image_modified(api_inst, omtime, False)

                self.pkg("install foo")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("set-mediator -I postfix sendmail")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("unset-mediator -I sendmail")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("unset-mediator -I sendmail", exit=4)
                omtime = self.__assert_image_modified(api_inst, omtime, False)

                # this should not register a modification; compliance tool
                # relies on that
                self.pkg("verify foo")
                omtime = self.__assert_image_modified(api_inst, omtime, False)

                self.pkg("fix foo", exit=4)
                omtime = self.__assert_image_modified(api_inst, omtime, False)

                # this should not register a modification; compliance tool
                # relies on that
                self.pkg("revert -n /etc/motd", exit=4)
                omtime = self.__assert_image_modified(api_inst, omtime, False)

                # modify etc/motd; fix should register modification
                self.file_append("etc/motd", "foo")
                self.pkg("fix foo")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                # modify etc/motd; revert should register modification
                self.file_append("etc/motd", "foo")
                self.pkg("revert /etc/motd")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("revert /etc/motd", exit=4)
                omtime = self.__assert_image_modified(api_inst, omtime, False)

                self.pkg("fix foo", exit=4)
                omtime = self.__assert_image_modified(api_inst, omtime, False)

                self.pkg("freeze foo")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("unfreeze foo")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("uninstall foo")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("avoid foo")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("unavoid foo")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("set-property be-policy always-new")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("unset-property be-policy")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("change-facet wombat=false")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("change-facet wombat=None")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("change-variant osnet.debug=true")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("change-variant osnet.debug=None")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                # Remove the last_refreshed file for one of the publishers so
                # that it will be seen as needing refresh.
                pub = api_inst.get_publisher("test")
                os.remove(os.path.join(pub.meta_root, "last_refreshed"))
                self.pkgsend_bulk(self.rurl, self.foo10)
                self.pkg("list -a")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                # Add, remove, and modify publishers.
                self.pkg("unset-publisher test")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("set-publisher -p {0}".format(self.rurl))
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("set-publisher -G {0} test".format(self.rurl))
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("set-publisher -g {0} test".format(self.rurl))
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("set-publisher --sticky test")
                omtime = self.__assert_image_modified(api_inst, omtime, True)

                self.pkg("set-publisher --non-sticky test")
                omtime = self.__assert_image_modified(api_inst, omtime, True)


if __name__ == "__main__":
        unittest.main()
