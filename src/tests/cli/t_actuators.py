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

# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import pkg5unittest
import unittest

class TestPkgActuators(pkg5unittest.SingleDepotTestCase):
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
"""
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
                     mode=0755)

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
                self.file_contains(svcadm_output,
                    "svcadm restart svc:/system/test_multi_svc1:default "
                    "svc:/system/test_multi_svc2:default")

                # make it look like our test service is enabled
                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_enabled"

                self.pkg("install basics@1.9")
                self.pkg("verify")
                self.pkg("uninstall basics")
                self.file_contains(svcadm_output,
                    "svcadm disable -s svc:/system/test_multi_svc1:default "
                    "svc:/system/test_multi_svc2:default")
                os.unlink(svcadm_output)

if __name__ == "__main__":
        unittest.main()
