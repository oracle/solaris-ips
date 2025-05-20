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
# Copyright (c) 2010, 2025, Oracle and/or its affiliates.
#

# Some opensolaris distribution specific lint checks

from pkg.lint import base


class OpenSolarisActionChecker(base.ActionChecker):
    """An opensolaris.org-specific class to check actions."""

    name = "opensolaris.action"

    def __init__(self, config):
        self.description = _(
            "checks OpenSolaris packages for common action errors")
        super().__init__(config)

    # opensolaris.action001 is obsolete and should not be reused.


class OpenSolarisManifestChecker(base.ManifestChecker):
    """An opensolaris.org-specific class to check manifests."""

    name = "opensolaris.manifest"

    def __init__(self, config):
        self.description = _(
            "checks OpenSolaris packages for common errors")
        super().__init__(config)

    def missing_attrs(self, manifest, engine, pkglint_id="001"):
        """Warn when manifest doesn't have org.opensolaris.consolidation
        or info.classification attribute set."""
        if "pkg.renamed" in manifest:
            return

        if "pkg.obsolete" in manifest:
            return

        keys = ["org.opensolaris.consolidation", "info.classification"]
        for key in keys:
            if key not in manifest:
                engine.warning(_(
                    "Missing attribute '{key}' in "
                    "{pkg}").format(key=key, pkg=manifest.fmri),
                    msgid=f"{self.name}{pkglint_id}.1")

    missing_attrs.pkglint_desc = _(
        "Standard package attributes should be present.")

    def attrs_multiple_values(self, manifest, engine, pkglint_id="005"):
        """Make sure that org.opensolaris.consolidation isn't set
        to multiple values."""
        if "org.opensolaris.consolidation" in manifest:
            value = manifest["org.opensolaris.consolidation"]
            if isinstance(value, list) and len(value) != 1:
                engine.error(_(
                    "Multiple 'org.opensolaris.consolidation' values {value} "
                    "in {pkg}").format(value=value, pkg=manifest.fmri),
                    msgid=f"{self.name}{pkglint_id}.1")

    attrs_multiple_values.pkglint_desc = _(
        "org.opensolaris.consolidation shouldn't have multiple values.")

    # opensolaris.manifest001.2 is obsolete and should not be reused.
    # opensolaris.manifest002 is obsolete and should not be reused.
    # opensolaris.manifest003 is obsolete and should not be reused.
    # opensolaris.manifest004 is obsolete and should not be reused.
