#!/usr/bin/python
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at LICENSE.txt
# or https://oss.oracle.com/licenses/.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at LICENSE.txt.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

# Copyright (c) 2010, 2026, Oracle and/or its affiliates.

from . import testutils
if __name__ == "__main__":
    testutils.setup_environment("../../../proto")
import pkg5unittest

import importlib
import unittest
import os
import sys
import unittest.mock
from types import SimpleNamespace
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.client_api as client_api
from pkg.client import pkgdefs
import pkg.client.bootenv as bootenv


class TestBootEnv(pkg5unittest.Pkg5TestCase):

    def test_api_consistency(self):
        """Make sure every public method in BootEnv exists in
        BootEnvNull and the other way around.
        """

        nullm = set(d for d in dir(bootenv.BootEnvNull)
            if not d.startswith("_"))
        bem = set(d for d in dir(bootenv.BootEnv)
            if not d.startswith("_"))

        be_missing = nullm - bem
        null_missing = bem - nullm

        estr = ""
        if be_missing:
            estr += "The following methods were missing from " \
                "BootEnv:\n" + \
                "\n".join("\t{0}".format(s) for s in be_missing)
        if null_missing:
            estr += "The following methods were missing from " \
                "BootEnvNull:\n" + \
                "\n".join("\t{0}".format(s) for s in null_missing)
        self.assertTrue(not estr, estr)

    def test_bootenv(self):
        """All other test suite tests test the BootEnv class with,
        PKG_NO_LIVE_ROOT set in the environment, see the run() and
        env_santize(..) methods in Pkg5TestSuite.  That environment
        variable means that BootEnv.get_be_list will always return an
        empty list.  While we want to generally avoid touching the live
        image root at all, making an exception here seems the best
        reasonable way to test some of the non-modifying BootEnv code.
        To that end, this test clears the relevant environment variable.
        """

        # For BE related functionality, bemgmt library must be available.
        bemgmt_spec = importlib.util.find_spec("bemgmt")
        if bemgmt_spec is None:
            raise pkg5unittest.TestSkippedException(
                "bemgmt library is not available.")

        del os.environ["PKG_NO_LIVE_ROOT"]
        self.assertTrue(bootenv.BootEnv.libbe_exists())
        self.assertTrue(bootenv.BootEnv.check_verify())
        self.assertTrue(isinstance(
            bootenv.BootEnv.get_be_list(raise_error=False), list))
        self.assertTrue(isinstance(
            bootenv.BootEnv.get_be_list(raise_error=True), list))

        bootenv.BootEnv.get_be_name("/")
        self.assertTrue(
            isinstance(bootenv.BootEnv.get_uuid_be_dic(), dict))
        bootenv.BootEnv.get_activated_be_name()
        bootenv.BootEnv.get_active_be_name()
        # This assumes that a1b2c3d4e5f6g7h8i9j0 is highly unlikely to
        # be an existing BE on the system.
        bootenv.BootEnv.check_be_name("a1b2c3d4e5f6g7h8i9j0")

        self.assertRaises(api_errors.InvalidBENameException,
            bootenv.BootEnv.check_be_name,
            "rpool/ROOT/a1b2c3d4e5f6g7h8i9j0")


class TestBootEnvActivation(pkg5unittest.Pkg5TestCase):
    def _check_activation_failure(self, backend, activate, unmount):
        backend.img = unittest.mock.Mock()
        backend.img.locked = False
        backend.is_live_BE = True
        backend.progress_tracker = None
        backend.clone_dir = "/mounted/clone"

        with unittest.mock.patch.object(backend, "_store_image_state"), \
            unittest.mock.patch.object(backend, "_reset_image_state") as reset:
            with self.assertRaises(api_errors.UnableToActivateBE) as caught:
                backend.activate_image()

        self.assertIn("beadm activate new-be", str(caught.exception))
        activate.assert_called_once()
        unmount.assert_not_called()
        backend.img.history.log_operation_end.assert_not_called()
        backend.img.history.log_operation_error.assert_not_called()
        reset.assert_called_once_with(failure=caught.exception)

    def test_bemgmt_activation_failure(self):
        backend = object.__new__(bootenv.BeadmV2BootEnv)
        backend.be_clone = SimpleNamespace(name="new-be", fmri="new-fmri")
        backend.bemgr = unittest.mock.Mock()
        backend.bemgr.activate.side_effect = RuntimeError("activation failed")
        self._check_activation_failure(backend, backend.bemgr.activate,
            backend.bemgr.unmount)

    def test_bemgmt_activation_disabled(self):
        backend = object.__new__(bootenv.BeadmV2BootEnv)
        backend.be_clone = SimpleNamespace(
            name="new-be", fmri="new-fmri", uuid="new-uuid")
        backend.be_name = "old-be"
        backend.be_name_clone = "new-be"
        backend.clone_dir = "/mounted/clone"
        backend.img = unittest.mock.Mock()
        backend.img.locked = False
        backend.is_live_BE = True
        backend.progress_tracker = None
        backend.bemgr = unittest.mock.Mock()

        with unittest.mock.patch.object(backend, "_store_image_state"), \
            unittest.mock.patch.object(backend, "_reset_image_state"), \
            unittest.mock.patch.object(bootenv.os, "rmdir"):
            backend.activate_image(set_active=False)

        backend.bemgr.activate.assert_not_called()
        backend.bemgr.unmount.assert_called_once_with(fmri="new-fmri")
        backend.img.history.log_operation_end.assert_called_once()

    def test_libbe_activation_failure(self):
        backend = object.__new__(bootenv.BeadmV1BootEnv)
        backend.be_name_clone = "new-be"
        with unittest.mock.patch.object(bootenv, "be", create=True) as libbe:
            libbe.beActivate.return_value = 1
            self._check_activation_failure(backend, libbe.beActivate,
                libbe.beUnmount)

    def test_libbe_activation_exception(self):
        backend = object.__new__(bootenv.BeadmV1BootEnv)
        backend.be_name_clone = "new-be"
        with unittest.mock.patch.object(bootenv, "be", create=True) as libbe:
            libbe.beActivate.side_effect = RuntimeError("activation failed")
            self._check_activation_failure(backend, libbe.beActivate,
                libbe.beUnmount)

    def test_api_records_activation_failure(self):
        failure = api_errors.UnableToActivateBE("new-be")
        image = unittest.mock.Mock()
        image.imageplan.state = api.plandesc.EXECUTED_OK
        api_inst = SimpleNamespace(_img=image,
            _ImageInterface__new_be=True,
            _ImageInterface__be_activate=True,
            log_operation_end=unittest.mock.Mock())
        backend = unittest.mock.Mock()
        backend.activate_image.side_effect = failure

        with self.assertRaises(api_errors.UnableToActivateBE):
            api.ImageInterface._ImageInterface__finished_execution(
                api_inst, backend)

        api_inst.log_operation_end.assert_called_once_with(error=failure)
        image.cleanup_cached_content.assert_not_called()

    def test_json_api_activation_status(self):
        failure = api_errors.UnableToActivateBE("new-be")
        api_inst = unittest.mock.Mock()
        api_inst.execute_plan.side_effect = failure
        api_inst.describe.return_value = SimpleNamespace(
            salvaged=[], new_be=True)

        result = getattr(client_api, "__api_execute_plan")(
            "update", api_inst)

        self.assertEqual(result["status"], pkgdefs.EXIT_BE)
        self.assertIn("new-be", result["errors"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
