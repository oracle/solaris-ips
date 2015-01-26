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
# Copyright (c) 2010, 2015, Oracle and/or its affiliates. All rights reserved.
#

# Some opensolaris distribution specific lint checks

import pkg.lint.base as base

class OpenSolarisActionChecker(base.ActionChecker):
        """An opensolaris.org-specific class to check actions."""

        name = "opensolaris.action"

        def __init__(self, config):
                self.description = _(
                    "checks OpenSolaris packages for common action errors")
                super(OpenSolarisActionChecker, self).__init__(config)

        # opensolaris.action001 is obsolete and should not be reused.


class OpenSolarisManifestChecker(base.ManifestChecker):
        """An opensolaris.org-specific class to check manifests."""

        name = "opensolaris.manifest"

        def __init__(self, config):
                self.description = _(
                    "checks OpenSolaris packages for common errors")
                super(OpenSolarisManifestChecker, self).__init__(config)

        def missing_attrs(self, manifest, engine, pkglint_id="001"):
                """Warn when a package doesn't have an
                org.opensolaris.consolidation attribute.
                Warn when a package don't have an info.classification value
                """
                if "pkg.renamed" in manifest:
                        return

                if "pkg.obsolete" in manifest:
                        return

                keys = ["org.opensolaris.consolidation", "info.classification"]
                for key in keys:
                        if key not in manifest:
                                engine.warning(
                                    _("Missing attribute '{key}' in "
                                    "{pkg}").format(key=key, pkg=manifest.fmri),
                                    msgid="{0}{1}.1".format(self.name,
                                    pkglint_id))

        missing_attrs.pkglint_desc = _(
            "Standard package attributes should be present.")

        # opensolaris.manifest001.2 is obsolete and should not be reused.
        # opensolaris.manifest002 is obsolete and should not be reused.
        # opensolaris.manifest003 is obsolete and should not be reused.
        # opensolaris.manifest004 is obsolete and should not be reused.
