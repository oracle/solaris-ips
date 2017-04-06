#!/usr/bin/python
# -*- coding: utf-8
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

# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import six
import pkg5unittest
import unittest
import stat
from io import open
from pkg.misc import force_text

class TestPkgSMFActuators(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        smf_cmds = { \
                "usr/bin/svcprop" :
"""#!/bin/sh
cat $PKG_TEST_DIR/$PKG_SVCPROP_OUTPUT
exit $PKG_SVCPROP_EXIT_CODE
""",
                "usr/sbin/svcadm" : \
"""#!/bin/sh
echo $0 "$@" >> $PKG_TEST_DIR/svcadm_arguments
exit $PKG_SVCADM_EXIT_CODE
""",
                "usr/bin/svcs" : \
"""#!/bin/sh

# called from pkg.client.actuator using 'svcs -H -o fmri <string>'
# so $4 is the FMRI pattern that we're interested in resolving
RETURN=0

case $4 in
        svc:/system/test_refresh_svc:default)
                FMRI=$4
                ;;
        svc:/system/test_multi_svc?:default)
                FMRI=$4
                ;;
        # the following are too relaxed, eg. "svcs sys/foo/tZst_suspend_svc:defXX"
        # would match, but is sufficient for this test case as we only
        # ever resolve services that truely exist here.
        *sy*t?st_suspend_svc:def*)
                FMRI=svc:/system/test_suspend_svc:default
                ;;
        *test_disable_svc*)
                FMRI=svc:/system/test_disable_svc:default
                ;;
        *test_restart_svc*)
                FMRI=svc:/system/test_restart_svc:default
                ;;
        *)
                FMRI="ERROR - t_actuators.py svcs wrapper failed to match $4"
                RETURN=1
                ;;
esac
echo $FMRI
exit $RETURN
""",
                "bin_zlogin" : \
"""#!/bin/sh
# print full cmd line, then execute in gz what zlogin would execute in ngz
echo $0 "$@" >> $PKG_TEST_DIR/zlogin_arguments
shift
($*)
""",
                "bin_zoneadm" : \
"""#!/bin/sh
cat <<-EOF
0:global:running:/::solaris:shared:-:none:
1:z1:running:$PKG_TZR1::solaris:excl:-::
2:z2:installed:$PKG_TZR2::solaris:excl:-::
EOF
exit 0"""

}
        misc_files = { \
                "svcprop_enabled" :
"""general/enabled boolean true
general/entity_stability astring Unstable
general/single_instance boolean true
restarter/start_pid count 4172
restarter/start_method_timestamp time 1222382991.639687000
restarter/start_method_waitstatus integer 0
restarter/transient_contract count
restarter/auxiliary_state astring none
restarter/next_state astring none
restarter/state astring online
restarter/state_timestamp time 1222382991.644413000
restarter_actions/refresh integer
restarter_actions/maint_on integer
restarter_actions/maint_off integer
restarter_actions/restart integer
local-filesystems/entities fmri svc:/system/filesystem/local
local-filesystems/grouping astring require_all
local-filesystems/restart_on astring none
local-filesystems/type astring service
remote-filesystems/entities fmri svc:/network/nfs/client svc:/system/filesystem/autofs
remote-filesystems/grouping astring optional_all
remote-filesystems/restart_on astring none
remote-filesystems/type astring service
startd/duration astring transient
start/timeout_seconds count 0
start/type astring method
stop/exec astring :true
stop/timeout_seconds count 0
stop/type astring method
""",

                "svcprop_disabled" :
"""general/enabled boolean false
general/entity_stability astring Unstable
general/single_instance boolean true
restarter/start_pid count 4172
restarter/start_method_timestamp time 1222382991.639687000
restarter/start_method_waitstatus integer 0
restarter/transient_contract count
restarter/auxiliary_state astring none
restarter/next_state astring none
restarter/state astring disabled
restarter/state_timestamp time 1222992132.445811000
restarter_actions/refresh integer
restarter_actions/maint_on integer
restarter_actions/maint_off integer
restarter_actions/restart integer
local-filesystems/entities fmri svc:/system/filesystem/local
local-filesystems/grouping astring require_all
local-filesystems/restart_on astring none
local-filesystems/type astring service
remote-filesystems/entities fmri svc:/network/nfs/client svc:/system/filesystem/autofs
remote-filesystems/grouping astring optional_all
remote-filesystems/restart_on astring none
remote-filesystems/type astring service
startd/duration astring transient
start/timeout_seconds count 0
start/type astring method
stop/exec astring :true
stop/timeout_seconds count 0
stop/type astring method
""",

                "svcprop_temp_enabled" :
"""general/enabled boolean false
general/entity_stability astring Unstable
general/single_instance boolean true
restarter/start_pid count 7816
restarter/start_method_timestamp time 1222992237.506096000
restarter/start_method_waitstatus integer 0
restarter/transient_contract count
restarter/auxiliary_state astring none
restarter/next_state astring none
restarter/state astring online
restarter/state_timestamp time 1222992237.527408000
restarter_actions/refresh integer
restarter_actions/maint_on integer
restarter_actions/maint_off integer
restarter_actions/restart integer
general_ovr/enabled boolean true
local-filesystems/entities fmri svc:/system/filesystem/local
local-filesystems/grouping astring require_all
local-filesystems/restart_on astring none
local-filesystems/type astring service
remote-filesystems/entities fmri svc:/network/nfs/client svc:/system/filesystem/autofs
remote-filesystems/grouping astring optional_all
remote-filesystems/restart_on astring none
remote-filesystems/type astring service
startd/duration astring transient
start/timeout_seconds count 0
start/type astring method
stop/exec astring :true
stop/timeout_seconds count 0
stop/type astring method
""",
                "svcprop_temp_disabled" :
"""general/enabled boolean true
general/entity_stability astring Unstable
general/single_instance boolean true
restarter/start_pid count 7816
restarter/start_method_timestamp time 1222992237.506096000
restarter/start_method_waitstatus integer 0
restarter/transient_contract count
restarter/auxiliary_state astring none
restarter/next_state astring none
restarter/state astring disabled
restarter/state_timestamp time 1222992278.822335000
restarter_actions/refresh integer
restarter_actions/maint_on integer
restarter_actions/maint_off integer
restarter_actions/restart integer
general_ovr/enabled boolean false
local-filesystems/entities fmri svc:/system/filesystem/local
local-filesystems/grouping astring require_all
local-filesystems/restart_on astring none
local-filesystems/type astring service
remote-filesystems/entities fmri svc:/network/nfs/client svc:/system/filesystem/autofs
remote-filesystems/grouping astring optional_all
remote-filesystems/restart_on astring none
remote-filesystems/type astring service
startd/duration astring transient
start/timeout_seconds count 0
start/type astring method
stop/exec astring :true
stop/timeout_seconds count 0
stop/type astring method
""",

                "empty": "",
}

        testdata_dir = None

        def setUp(self):

                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.testdata_dir = os.path.join(self.test_root, "testdata")
                os.mkdir(self.testdata_dir)

                self.pkg_list = []

                self.pkg_list+= ["""
                    open basics@1.0,5.11-0
                    add file testdata/empty mode=0644 owner=root group=sys path=/test_restart restart_fmri=svc:/system/test_restart_svc:default
                    close """]

                self.pkg_list+= ["""
                    open basics@1.1,5.11-0
                    add file testdata/empty mode=0655 owner=root group=sys path=/test_restart restart_fmri=svc:/system/test_restart_svc:default
                    close """]

                self.pkg_list+= ["""
                    open basics@1.2,5.11-0
                    add file testdata/empty mode=0646 owner=root group=sys path=/test_restart restart_fmri=svc:/system/test_restart_svc:default
                    close """]

                self.pkg_list+= ["""
                    open basics@1.3,5.11-0
                    add file testdata/empty mode=0657 owner=root group=sys path=/test_restart refresh_fmri=svc:/system/test_refresh_svc:default
                    close """]

                self.pkg_list+= ["""
                    open basics@1.4,5.11-0
                    add file testdata/empty mode=0667 owner=root group=sys path=/test_restart suspend_fmri=svc:/system/test_suspend_svc:default
                    close """]

                self.pkg_list+= ["""
                    open basics@1.5,5.11-0
                    add file testdata/empty mode=0677 owner=root group=sys path=/test_restart suspend_fmri=svc:/system/test_suspend_svc:default disable_fmri=svc:/system/test_disable_svc:default
                    close """]

                # no fully specified FMRIs here
                self.pkg_list+= ["""
                    open basics@1.6,5.11-0
                    add file testdata/empty mode=0677 owner=root group=sys path=/test_restart restart_fmri=svc:/system/test_restart_svc suspend_fmri=svc:/system/test_suspend_svc disable_fmri=svc:/system/test_disable_svc
                    close """]

                # multiple FMRIs, some with globbing characters
                self.pkg_list+= ["""
                    open basics@1.7,5.11-0
                    add file testdata/empty mode=0677 owner=root group=sys path=/test_restart refresh_fmri=svc:/system/test_refresh_svc:default restart_fmri=svc:/system/test_restart_svc* suspend_fmri=svc:/sy*t?st_suspend_svc:def* disable_fmri=*test_disable_svc*
                    close """]

                self.pkg_list += ["""
                    open basics@1.8,5.11-0
                    add file testdata/empty mode=0677 owner=root group=sys path=/test_restart restart_fmri=svc:/system/test_multi_svc1:default restart_fmri=svc:/system/test_multi_svc2:default
                    close """]

                self.pkg_list += ["""
                    open basics@1.9,5.11-0
                    add file testdata/empty mode=0677 owner=root group=sys path=/test_restart disable_fmri=svc:/system/test_multi_svc1:default disable_fmri=svc:/system/test_multi_svc2:default
                    close """]

                self.make_misc_files(self.misc_files, prefix="testdata",
                     mode=0o755)

        def test_actuators(self):
                """test actuators"""

                rurl = self.dc.get_repo_url()
                plist = self.pkgsend_bulk(rurl, self.pkg_list)
                self.image_create(rurl)
                os.environ["PKG_TEST_DIR"] = self.testdata_dir
                os.environ["PKG_SVCADM_EXIT_CODE"] = "0"
                os.environ["PKG_SVCPROP_EXIT_CODE"] = "0"

                svcadm_output = os.path.join(self.testdata_dir,
                    "svcadm_arguments")

                # make it look like our test service is enabled
                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_enabled"

                # test to see if our test service is restarted on install
                self.pkg("install --parsable=0 basics@1.0")
                self.assertEqualParsable(self.output, add_packages=[plist[0]],
                    affect_services=[["restart_fmri",
                        "svc:/system/test_restart_svc:default"]
                    ])
                self.pkg("verify")

                self.file_contains(svcadm_output,
                    "svcadm restart svc:/system/test_restart_svc:default")
                os.unlink(svcadm_output)

                # test to see if our test service is restarted on upgrade
                self.pkg("install basics@1.1")
                self.pkg("verify")
                self.file_contains(svcadm_output,
                    "svcadm restart svc:/system/test_restart_svc:default")
                os.unlink(svcadm_output)

                # test to see if our test service is restarted on uninstall
                self.pkg("uninstall basics")
                self.pkg("verify")
                self.file_contains(svcadm_output,
                    "svcadm restart svc:/system/test_restart_svc:default")
                os.unlink(svcadm_output)

                # make it look like our test service is not enabled
                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_disabled"

                # test to see to make sure we don't restart disabled service
                self.pkg("install basics@1.2")
                self.pkg("verify")
                self.file_doesnt_exist(svcadm_output)

                # test to see if services that aren't installed are ignored
                os.environ["PKG_SVCPROP_EXIT_CODE"] = "1"
                self.pkg("uninstall basics")
                self.pkg("verify")
                self.pkg("install basics@1.2")
                self.pkg("verify")
                self.file_doesnt_exist(svcadm_output)
                os.environ["PKG_SVCPROP_EXIT_CODE"] = "0"

                # make it look like our test service(s) is/are enabled
                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_enabled"

                # test to see if refresh works as designed, along w/ restart
                self.pkg("install basics@1.3")
                self.pkg("verify")
                self.file_contains(svcadm_output,
                    "svcadm restart svc:/system/test_restart_svc:default")
                self.file_contains(svcadm_output,
                    "svcadm refresh svc:/system/test_refresh_svc:default")
                os.unlink(svcadm_output)

                # test if suspend works
                self.pkg("install basics@1.4")
                self.pkg("verify")
                self.file_contains(svcadm_output,
                    "svcadm disable -s -t svc:/system/test_suspend_svc:default")
                self.file_contains(svcadm_output,
                    "svcadm enable svc:/system/test_suspend_svc:default")
                os.unlink(svcadm_output)

                # test if suspend works properly w/ temp. enabled service
                # make it look like our test service(s) is/are temp enabled
                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_temp_enabled"
                self.pkg("install basics@1.5")
                self.pkg("verify")
                self.file_contains(svcadm_output,
                    "svcadm disable -s -t svc:/system/test_suspend_svc:default")
                self.file_contains(svcadm_output,
                    "svcadm enable -t svc:/system/test_suspend_svc:default")
                os.unlink(svcadm_output)

                # test if service is disabled on uninstall
                self.pkg("uninstall basics")
                self.pkg("verify")
                self.file_contains(svcadm_output,
                    "svcadm disable -s svc:/system/test_disable_svc:default")
                os.unlink(svcadm_output)

                # make it look like our test service(s) is/are enabled
                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_enabled"
                os.environ["PKG_SVCPROP_EXIT_CODE"] = "0"

                # test that we do nothing for FMRIs with no instance specified
                self.pkg("install basics@1.6")
                self.pkg("verify")
                self.file_doesnt_exist(svcadm_output)
                self.pkg("uninstall basics")
                self.file_doesnt_exist(svcadm_output)

                # test that we do the right thing for multiple FMRIs with
                # globbing chars
                self.pkg("install basics@1.6")
                self.pkg("install basics@1.7")
                self.pkg("verify")

                for text in [ "svcadm refresh svc:/system/test_refresh_svc:default",
                   "svcadm refresh svc:/system/test_refresh_svc:default",
                   "svcadm restart svc:/system/test_restart_svc:default",
                   "svcadm disable -s -t svc:/system/test_suspend_svc:default",
                   "svcadm enable svc:/system/test_suspend_svc:default" ]:
                           self.file_contains(svcadm_output, text)

                # Next test will get muddled if prior actuators get
                # run too, so we test removal here.
                self.pkg("uninstall basics")
                self.file_contains(svcadm_output,
                    "svcadm disable -s svc:/system/test_disable_svc:default")
                os.unlink(svcadm_output)

                # Test with multi-valued actuators
                self.pkg("install basics@1.8")
                self.pkg("verify")
                if six.PY2:
                        self.file_contains(svcadm_output,
                            "svcadm restart svc:/system/test_multi_svc1:default "
                            "svc:/system/test_multi_svc2:default")
                else:
                        # output order is not stable in Python 3
                        self.file_contains(svcadm_output, ["svcadm restart",
                            "svc:/system/test_multi_svc1:default",
                            "svc:/system/test_multi_svc2:default"])

                # Test synchronous options
                # synchronous restart
                self.pkg("uninstall basics")
                self.pkg("install --sync-actuators basics@1.1")
                self.pkg("verify")
                self.file_contains(svcadm_output,
                    "svcadm restart -s svc:/system/test_restart_svc:default")
                os.unlink(svcadm_output)

                # synchronous restart with timeout
                self.pkg("uninstall basics")
                self.pkg("install --sync-actuators --sync-actuators-timeout 20 basics@1.1")
                self.pkg("verify")
                self.file_contains(svcadm_output,
                    "svcadm restart -s -T 20 svc:/system/test_restart_svc:default")
                os.unlink(svcadm_output)

                # synchronous suspend
                self.pkg("install --sync-actuators basics@1.4")
                self.pkg("verify")
                self.file_contains(svcadm_output,
                    "svcadm disable -s -t svc:/system/test_suspend_svc:default")
                self.file_contains(svcadm_output,
                    "svcadm enable -s svc:/system/test_suspend_svc:default")
                os.unlink(svcadm_output)

                # synchronous suspend with timeout
                self.pkg("uninstall basics")
                self.pkg("install basics@1.1")
                self.pkg("install --sync-actuators --sync-actuators-timeout 10 basics@1.4")
                self.pkg("verify")
                self.file_contains(svcadm_output,
                    "svcadm disable -s -t svc:/system/test_suspend_svc:default")
                self.file_contains(svcadm_output,
                    "svcadm enable -s -T 10 svc:/system/test_suspend_svc:default")
                os.unlink(svcadm_output)

                # make it look like our test service is enabled
                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_enabled"

                self.pkg("install basics@1.9")
                self.pkg("verify")
                self.pkg("uninstall basics")
                if six.PY2:
                        self.file_contains(svcadm_output,
                            "svcadm disable -s svc:/system/test_multi_svc1:default "
                            "svc:/system/test_multi_svc2:default")
                else:
                        # output order is not stable in Python 3
                        self.file_contains(svcadm_output, ["svcadm disable -s",
                            "svc:/system/test_multi_svc1:default",
                            "svc:/system/test_multi_svc2:default"])
                os.unlink(svcadm_output)

        def test_actuator_plan_display(self):
                """Test that the actuators are correct in plan display for different
                pkg operations."""

                rurl = self.dc.get_repo_url()
                plist = self.pkgsend_bulk(rurl, self.pkg_list)
                self.image_create(rurl)

                self.pkg("install -v basics@1.0")
                self.assertTrue("restart_fmri" in self.output)

                self.pkg("update -v basics@1.5")
                self.assertTrue("suspend_fmri" in self.output
                    and "disable_fmri" not in self.output)

                self.pkg("uninstall -v basics")
                self.assertTrue("suspend_fmri" not in self.output
                    and "disable_fmri" in self.output)

                self.pkg("install -v basics@1.5")
                self.assertTrue("suspend_fmri" not in self.output and
                    "disable_fmri" not in self.output)
                self.pkg("uninstall basics")

                self.pkg("install -v basics@1.7")
                self.assertTrue("restart_fmri" in self.output and
                    "refresh_fmri" in self.output and
                    "suspend_fmri" not in self.output and
                    "disable_fmri" not in self.output)

        def __create_zone(self, zname, rurl):
                """Create a fake zone linked image and attach to parent."""

                zone_path = os.path.join(self.img_path(0), zname)
                os.mkdir(zone_path)
                # zone images are rooted at <zonepath>/root
                zimg_path = os.path.join(zone_path, "root")
                self.image_create(repourl=rurl, img_path=zimg_path)
                self.pkg("-R {0} attach-linked -c system:{1} {2}".format(
                    self.img_path(0), zname, zimg_path))

                return zone_path

        def test_zone_actuators(self):
                """test zone actuators"""

                rurl = self.dc.get_repo_url()
                plist = self.pkgsend_bulk(rurl, self.pkg_list)
                self.image_create(rurl)

                # Create fake zone images.
                # We have one "running" zone (z1) and one "installed" zone (z2).
                # The zone actuators should only be run in the running zone.

                # set env variable for fake zoneadm to print correct zonepaths
                os.environ["PKG_TZR1"] = self.__create_zone("z1", rurl)
                os.environ["PKG_TZR2"] = self.__create_zone("z2", rurl)

                os.environ["PKG_TEST_DIR"] = self.testdata_dir
                os.environ["PKG_SVCADM_EXIT_CODE"] = "0"
                os.environ["PKG_SVCPROP_EXIT_CODE"] = "0"

                # Prepare fake zone and smf cmds.
                svcadm_output = os.path.join(self.testdata_dir,
                    "svcadm_arguments")
                zlogin_output = os.path.join(self.testdata_dir,
                    "zlogin_arguments")
                bin_zlogin = os.path.join(self.test_root,
                    "smf_cmds", "bin_zlogin")
                bin_zoneadm = os.path.join(self.test_root,
                    "smf_cmds", "bin_zoneadm")

                # make it look like our test service is enabled
                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_enabled"

                # test to see if our test service is restarted on install
                self.pkg("--debug bin_zoneadm='{0}' "
                    "--debug bin_zlogin='{1}' "
                    "install -rv basics@1.0".format(bin_zoneadm, bin_zlogin))
                # test that actuator in global zone and z2 is run
                self.file_contains(svcadm_output,
                    "svcadm restart svc:/system/test_restart_svc:default",
                    appearances=2)
                os.unlink(svcadm_output)
                # test that actuator in non-global zone is run
                self.file_contains(zlogin_output,
                    "zlogin z1")
                self.file_doesnt_contain(zlogin_output,
                    "zlogin z2")
                self.file_contains(zlogin_output,
                    "svcadm restart svc:/system/test_restart_svc:default")
                os.unlink(zlogin_output)

class TestPkgReleaseNotes(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo10 = """
            open foo@1.0,5.11-0
            add file tmp/release-note-1 mode=0644 owner=root group=bin path=/usr/share/doc/release-notes/release-note-1 release-note=feature/pkg/self@0
            close """

        foo11 = """
            open foo@1.1,5.11-0
            add file tmp/release-note-2 mode=0644 owner=root group=root path=/usr/share/doc/release-notes/release-note-2 release-note=feature/pkg/self@1.0.1
            close """

        foo12 = """
            open foo@1.2,5.11-0
            add file tmp/release-note-3 mode=0644 owner=root group=root path=/usr/share/doc/release-notes/release-note-3 release-note=feature/pkg/self@1.1.1 must-display=true
            close """

        foo13 = """
            open foo@1.3,5.11-0
            add file tmp/release-note-4 mode=0644 owner=root group=root path=/usr/share/doc/release-notes/release-note-4 release-note=feature/pkg/self@1.1
            close """

        bar10 = """
            open bar@1.0,5.11-0
            add dir path=/usr mode=0755 owner=root group=root release-note=feature/pkg/self@0
            close """

        bar11 = """
            open bar@1.1,5.11-0
            close """

        baz10 = """
            open baz@1.0,5.11-0
            add file tmp/release-note-5 mode=0644 owner=root group=root path=/usr/share/doc/release-notes/release-note-5 release-note=bar@1.1
            close """

        hovercraft = """
            open hovercraft@1.0,5.10-0
            add file tmp/release-note-6 mode=0644 owner=root group=root path=/usr/share/doc/release-notes/release-note-6 release-note=feature/pkg/self@0
            close """

        multi_unicode = u"Eels are best smoked\nМоё судно на воздушной подушке полно угрей\nHovercraft can be smoked, too.\n"
        multi_ascii = "multi-line release notes\nshould work too,\nwe'll see if they do.\n"
        misc_files = {
                "tmp/release-note-1":"bobcats are fun!",
                "tmp/release-note-2":"wombats are fun!",
                "tmp/release-note-3":"no animals were hurt...",
                "tmp/release-note-4":"no vegetables were hurt...",
                "tmp/release-note-5":multi_ascii,
                "tmp/release-note-6":multi_unicode
                }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.rurl, self.foo10 + self.foo11 +
                    self.foo12 + self.foo13 + self.bar10 + self.bar11 + self.baz10 +
                    self.hovercraft)
                self.image_create(self.rurl)

        def test_release_note_1(self):
                # make sure release note gets printed on original install
                self.pkg("install -v foo@1.0")
                self.output.index("bobcats are fun!")
                # check update case
                self.pkg("update -v foo@1.1")
                self.output.index("wombats are fun!")
                # check must display case
                self.pkg("update foo@1.2")
                self.output.index("no animals")
                # check that no output is seen w/o must-display and -v,
                # but that user is prompted that notes are available.
                self.pkg("update foo@1.3")
                assert self.output.find("no vegetables") == -1
                self.pkg("uninstall '*'")

        def test_release_note_2(self):
                # check that release notes are printed with just -n
                self.pkg("install -vn foo@1.0")
                self.output.index("bobcats are fun!")
                # retrieve release notes with pkg history after actual install
                self.pkg("install foo@1.0")
                # make sure we note that release notes are available
                self.output.index("Release notes")
                # check that we list them in the -l output
                self.pkg("history -n 1 -l")
                self.output.index("Release Notes")
                # retrieve notes and look for felines
                self.pkg("history -n 1 -N")
                self.output.index("bobcats are fun!")
                # check that we say yes that release notes are available
                self.pkg("history -Hn 1 -o release_notes")
                self.output.index("Yes")
                self.pkg("uninstall '*'")

        def test_release_note_3(self):
                # check that release notes are printed properly
                # when needed and dependency is on other pkg
                self.pkg("install bar@1.0")
                self.pkg("install -v baz@1.0")
                self.output.index("multi-line release notes")
                self.output.index("should work too,")
                self.output.index("we'll see if they do.")
                # should not see notes again
                self.pkg("update -v bar")
                assert self.output.find("Release notes") == -1
                self.pkg("uninstall '*'")
                # no output expected here since baz@1.0 isn't part of original image.
                self.pkg("install bar@1.0 baz@1.0")
                assert self.output.find("multi-line release notes") == -1
                self.pkg("uninstall '*'")

        def test_release_note_4(self):
                # make sure that parseable option works properly
                self.pkg("install bar@1.0")
                self.pkg("install --parsable 0 baz@1.0")
                self.output.index("multi-line release notes")
                self.output.index("should work too,")
                self.output.index("we'll see if they do.")
                self.pkg("uninstall '*'")

        def test_release_note_5(self):
                # test unicode character in release notes
                self.pkg("install -n hovercraft@1.0")
                force_text(self.output, "utf-8").index(u"Моё судно на воздушной подушке полно угрей")
                force_text(self.output, "utf-8").index(u"Eels are best smoked")
                self.pkg("install -v hovercraft@1.0")
                force_text(self.output, "utf-8").index(u"Моё судно на воздушной подушке полно угрей")
                force_text(self.output, "utf-8").index(u"Eels are best smoked")
                self.pkg("uninstall '*'")

        def test_release_note_6(self):
                # test parsable unicode
                self.pkg("install --parsable 0 hovercraft@1.0")
                self.pkg("history -n 1 -N")
                force_text(self.output, "utf-8").index(u"Моё судно на воздушной подушке полно угрей")
                force_text(self.output, "utf-8").index(u"Eels are best smoked")
                self.pkg("uninstall '*'")

        def test_release_note_7(self):
                # check that multiple release notes are composited properly
                self.pkg("install bar@1.0")
                self.pkg("install -v hovercraft@1.0 baz@1.0")
                uni_out = force_text(self.output, "utf-8")
                # we indent the release notes for readability, so a strict
                # index or compare won't work unless we remove indenting
                # this works for our test cases since they have no leading
                # spaces

                # removing indent
                uni_out = "\n".join((n.lstrip() for n in uni_out.split("\n")))

                uni_out.index(self.multi_unicode)
                uni_out.index(self.multi_ascii)

                # repeat test using history to make sure everything is there.
                # do as unpriv. user

                self.pkg("history -n 1 -HN", su_wrap=True)
                uni_out = force_text(self.output, "utf-8")
                # we indent the release notes for readability, so a strict
                # index or compare won't work unless we remove indenting
                # this works for our test cases since they have no leading
                # spaces

                # removing indent
                uni_out = "\n".join((n.lstrip() for n in uni_out.split("\n")))

                uni_out.index(self.multi_unicode)
                uni_out.index(self.multi_ascii)

                self.pkg("uninstall '*'")

        def test_release_note_8(self):
                # verify that temporary file is correctly written with /n characters
                self.pkg("-D GenerateNotesFile=1 install hovercraft@1.0")
                # find name of file containing release notes in output.
                for field in force_text(self.output, "utf-8").split(u" "):
                        try:
                                if field.index(u"release-note"):
                                        break
                        except:
                                pass
                else:
                        assert "output file not found" == 0

                # make sure file is readable by everyone
                assert(stat.S_IMODE(os.stat(field).st_mode) == 0o644)

                # read release note file and check to make sure
                # entire contents are there verbatim
                with open(field, encoding="utf-8") as f:
                        release_note = force_text(f.read())
                assert self.multi_unicode == release_note
                self.pkg("uninstall '*'")


if __name__ == "__main__":
        unittest.main()
