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
# Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.
#

# Some opensolaris distribution specific lint checks

import pkg.lint.base as base
import re
import os.path
import ConfigParser

class OpenSolarisActionChecker(base.ActionChecker):
        """An opensolaris.org-specific class to check actions."""

        name = "opensolaris.action"

        def __init__(self, config):
                self.description = _(
                    "checks OpenSolaris packages for common action errors")
                super(OpenSolarisActionChecker, self).__init__(config)

        def username_format(self, action, manifest, engine, pkglint_id="001"):
                """Checks username length, and format."""

                if action.name is not "user":
                        return

                username = action.attrs["username"]
                if len(username) > 8:
                        engine.error(
                            _("Username %(name)s in %(pkg)s > 8 chars") %
                            {"name": username,
                            "pkg": manifest.fmri},
                            msgid="%s%s.1" % (self.name, pkglint_id))

                if len(username) == 0 or not re.match("[a-z]", username[0]):
                        engine.error(
                            _("Username %(name)s in %(pkg)s does not have an "
                            "initial lower-case alphabetical character") %
                            {"name": username,
                            "pkg": manifest.fmri},
                            msgid="%s%s.2" % (self.name, pkglint_id))

                if not re.match("^[a-z]([a-zA-Z1-9._-])*$", username):
                        engine.error(
                            _("Username %(name)s in %(pkg)s is invalid - see "
                            "passwd(4)") %
                            {"name": username,
                            "pkg": manifest.fmri},
                            msgid="%s%s.3" % (self.name, pkglint_id))


class OpenSolarisManifestChecker(base.ManifestChecker):
        """An opensolaris.org-specific class to check manifests."""

        name = "opensolaris.manifest"

        def __init__(self, config):
                self.description = _(
                    "checks OpenSolaris packages for common errors")
                self.conf = None

                classifications = \
                    "/usr/share/package-manager/data/opensolaris.org.sections"
                if os.path.exists(classifications):
                        self.conf = ConfigParser.SafeConfigParser()
                        self.conf.readfp(open(classifications))

                super(OpenSolarisManifestChecker, self).__init__(config)

        def missing_attrs(self, manifest, engine, pkglint_id="001"):
                """Various checks for missing attributes
                * warn when a package doesn't have a pkg.description
                * error when a package doesn't have a pkg.summary
                * warn when a package doesn't have an org.opensolaris.consolidation
                * warn when a package doesn't have an info.classification'
                """
                if "pkg.renamed" in manifest:
                        return

                if "pkg.obsolete" in manifest:
                        return

                for key in ["pkg.description", "org.opensolaris.consolidation",
                    "info.classification"]:
                        if key not in manifest:
                                engine.warning(
                                    _("Missing key %(key)s from %(pkg)s") %
                                    {"key": key,
                                    "pkg": manifest.fmri},
                                    msgid="%s%s.1" % (self.name, pkglint_id))

                if "pkg.summary" not in manifest:
                        engine.error(_("Missing key pkg.summary from %s") %
                            manifest.fmri,
                            msgid="%s%s.2" % (self.name, pkglint_id))

        def print_fmri(self, manifest, engine, pkglint_id="002"):
                """For now, this is simply a convenient way to output
                the FMRI being checked.  We pkglint.exclude this check
                by default."""
                # Using the python logger attached to the engine rather than
                # emitting a lint message - this message is purely informational
                # and isn't a source of lint messages (which would otherwise
                # cause a non-zero exit from pkglint)
                engine.logger.info(" %s" % manifest.fmri)
