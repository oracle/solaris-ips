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

# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import pkg5unittest
import unittest

import pkg.smf as smf

class TestSMF(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        smf_cmds = { \
            "usr/bin/svcprop" : """\
#!/usr/bin/python

import getopt
import os
import sys

if __name__ == "__main__":
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "cp:")
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        found_c = False
        prop = None
        for opt, arg in opts:
                if opt == "-c":
                        found_c = True
                elif opt == "-p":
                        prop = arg
        with open(os.path.join(os.environ["PKG_TEST_DIR"],
            os.environ["PKG_SVCPROP_OUTPUT"]), "rb") as fh:
                s = fh.read()
        if prop:
                prop_dict = {}
                for l in s.splitlines():
                        t = l.split(None, 2)
                        if len(t) == 3:
                                prop_dict[t[0]] = t[2]
                prop = prop_dict.get(prop, None)
                if not found_c or not prop:
                        sys.exit(1)
                print prop
                sys.exit(0)
        print s
        sys.exit(0)
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
        # the following are too relaxed, eg.
        # "svcs sys/foo/tZst_suspend_svc:defXX"
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
stop/type astring method""",

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
stop/type astring method""",

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
stop/type astring method""",

                "svcprop_temp_enabled2" :
"""general/enabled boolean true
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
stop/type astring method""",

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
stop/type astring method""",

                "svcprop_temp_disabled2" :
"""general/enabled boolean false
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
stop/type astring method""",

                "svcprop_maintenance":
"""general/enabled boolean true
general/entity_stability astring Unstable
general/single_instance boolean true
restarter/start_pid count 4172
restarter/start_method_timestamp time 1222382991.639687000
restarter/start_method_waitstatus integer 0
restarter/transient_contract count
restarter/auxiliary_state astring none
restarter/next_state astring none
restarter/state astring maintenance
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
stop/type astring method""",


                "empty": "",
}
        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files, prefix="testdata")

        def test_smf(self):
                """Test that the smf interface performs as expected."""

                testdata_dir = os.path.join(self.test_root, "testdata")
                svcadm_output = os.path.join(testdata_dir,
                    "svcadm_arguments")
                os.environ["PKG_TEST_DIR"] = testdata_dir
                os.environ["PKG_SVCADM_EXIT_CODE"] = "0"
                os.environ["PKG_SVCPROP_EXIT_CODE"] = "0"

                smf.restart("svc:/system/test_restart_svc:default")
                self.file_contains(svcadm_output,
                    "svcadm restart svc:/system/test_restart_svc:default")
                os.unlink(svcadm_output)

                smf.refresh("svc:/system/test_refresh_svc:default")
                self.file_contains(svcadm_output,
                    "svcadm refresh svc:/system/test_refresh_svc:default")
                os.unlink(svcadm_output)

                smf.mark("maintenance", "svc:/system/test_mark_svc:default")
                self.file_contains(svcadm_output,
                    "svcadm mark maintenance svc:/system/test_mark_svc:default")
                os.unlink(svcadm_output)

                smf.mark("degraded", "svc:/system/test_mark_svc:default")
                self.file_contains(svcadm_output,
                    "svcadm mark degraded svc:/system/test_mark_svc:default")
                os.unlink(svcadm_output)

                smf.disable("svc:/system/test_disable_svc:default")
                self.file_contains(svcadm_output,
                    "svcadm disable -s svc:/system/test_disable_svc:default")
                os.unlink(svcadm_output)

                smf.disable("svc:/system/test_disable_svc:default",
                    temporary=True)
                self.file_contains(svcadm_output,
                    "svcadm disable -s -t svc:/system/test_disable_svc:default")
                os.unlink(svcadm_output)

                smf.enable("svc:/system/test_enable_svc:default")
                self.file_contains(svcadm_output,
                    "svcadm enable svc:/system/test_enable_svc:default")
                os.unlink(svcadm_output)

                smf.enable("svc:/system/test_enable_svc:default",
                    temporary=True)
                self.file_contains(svcadm_output,
                    "svcadm enable -t svc:/system/test_enable_svc:default")
                os.unlink(svcadm_output)

                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_enabled"
                self.assertEqual(smf.get_prop("foo", "start/timeout_seconds"),
                    "0")
                self.assertEqual(smf.get_prop("foo", "stop/exec"), ":true")

                p = smf.get_props("foo")
                self.assert_("start/timeout_seconds" in p)
                self.assert_("0" in p["start/timeout_seconds"])
                self.assert_("stop/exec" in p)
                self.assert_("true" in p["stop/exec"])

                # "a" should be removed from the list of fmris since it's not
                # an instance.
                fmris = smf.check_fmris("foo", set(["a"]))
                self.assertEqual(fmris, set([]))

                fmris = smf.check_fmris("foo",
                    set(["test_disable_svc:default"]))
                self.assertEqual(fmris, set(["test_disable_svc:default"]))

                fmris = smf.check_fmris("foo", set(["test_disable_svc*"]))
                self.assertEqual(fmris,
                    set(["svc:/system/test_disable_svc:default"]))

                self.assertEqual(smf.get_state("foo"), smf.SMF_SVC_ENABLED)
                self.assert_(not smf.is_disabled("foo"))

                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_disabled"
                self.assertEqual(smf.get_state("foo"), smf.SMF_SVC_DISABLED)
                self.assert_(smf.is_disabled("foo"))

                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_temp_enabled"
                self.assertEqual(smf.get_state("foo"), smf.SMF_SVC_TMP_ENABLED)
                self.assert_(not smf.is_disabled("foo"))

                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_temp_enabled2"
                self.assertEqual(smf.get_state("foo"), smf.SMF_SVC_TMP_ENABLED)
                self.assert_(not smf.is_disabled("foo"))

                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_temp_disabled"
                self.assertEqual(smf.get_state("foo"), smf.SMF_SVC_TMP_DISABLED)
                self.assert_(smf.is_disabled("foo"))

                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_temp_disabled2"
                self.assertEqual(smf.get_state("foo"), smf.SMF_SVC_TMP_DISABLED)
                self.assert_(smf.is_disabled("foo"))

                os.environ["PKG_SVCPROP_OUTPUT"] = "svcprop_maintenance"
                self.assertEqual(smf.get_state("foo"), smf.SMF_SVC_MAINTENANCE)
                self.assert_(smf.is_disabled("foo"))
