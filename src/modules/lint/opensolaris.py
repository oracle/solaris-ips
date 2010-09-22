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
                self.classification_data = None

                self.classification_path = config.get(
                    "pkglint", "info_classification_path")
                self.skip_classification_check = False

                # a default error message used if we've parsed the
                # data file, but haven't thrown any exceptions
                self.bad_classification_data = _("no sections found in data "
                    "file %s") % self.classification_path

                if os.path.exists(self.classification_path):
                        try:
                                self.classification_data = \
                                    ConfigParser.SafeConfigParser()
                                self.classification_data.readfp(
                                    open(self.classification_path))
                        except Exception, err:
                                # any exception thrown here results in a null
                                # classification_data object.  We deal with that
                                # later.
                                self.bad_classification_data = _(
                                    "unable to parse data file %(path)s: "
                                    "%(err)s") % \
                                    {"path": self.classification_path,
                                    "err": err}
                                pass
                else:
                        self.bad_classification_data = _("missing file %s") % \
                            self.classification_path

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

        def info_classification(self, manifest, engine, pkglint_id="003"):
                """Checks that the info.classification attribute is valid."""

                if (not "info.classification" in manifest) or \
                    self.skip_classification_check:
                        return

                if not self.classification_data or \
                    not self.classification_data.sections():
                        engine.error(_("Unable to perform manifest checks "
                            "for info.classification attribute: %s") %
                            self.bad_classification_data,
                            msgid="%s%s.1" % (self.name, pkglint_id))
                        self.skip_classification_check = True
                        return

                value = manifest["info.classification"]

                # we allow multiple values for info.classification
                if isinstance(value, list):
                        for item in value:
                                self._check_info_classification_value(
                                    engine, item, manifest.fmri,
                                    "%s%s" % (self.name, pkglint_id))
                else:
                        self._check_info_classification_value(engine, value,
                            manifest.fmri, "%s%s" % (self.name, pkglint_id))

        def _check_info_classification_value(self, engine, value, fmri, msgid):

                prefix = "org.opensolaris.category.2008:"

                if not prefix in value:
                        engine.error(_("info.classification attribute "
                            "does not contain '%(prefix)s' for %(fmri)s") %
                            locals(), msgid="%s.2" % msgid)
                        return

                classification = value.replace(prefix, "")

                components = classification.split("/", 1)
                if len(components) != 2:
                        engine.error(_("info.classification value %(value)s "
                            "does not match "
                            "%(prefix)s<Section>/<Category> for %(fmri)s") %
                            locals(), msgid="%s.3" % msgid)
                        return

                # the data file looks like:
                # [Section]
                # categtory = Cat1,Cat2,Cat3
                #
                # We expect the info.classification action to look like:
                # org.opensolaris.category.2008:Section/Cat2
                #
                section, category = components
                valid_value = True
                ref_categories = []
                try:
                        ref_categories = self.classification_data.get(section,
                            "category").split(",")
                        if category not in ref_categories:
                                valid_value = False
                except ConfigParser.NoSectionError:
                        engine.error(_("info.classification value %(value)s "
                            "does not contain one of the valid sections "
                            "%(ref_sections)s for %(fmri)s.") %
                            {"value": value,
                            "ref_sections":
                            ", ".join(self.classification_data.sections()),
                            "fmri": fmri},
                            msgid="%s.4" % msgid)
                        return

                except ConfigParser.NoOptionError:
                        engine.error(_("Invalid info.classification value for "
                            "%(fmri)s: data file %(file)s does not have a "
                            "'category' key for section %(section)s.") %
                            {"file": self.classification_path,
                            "section": section,
                            "fmri": fmri},
                             msgid="%s.5" % msgid)
                        return

                if valid_value:
                        return

                ref_cats = self.classification_data.get(section,"category")
                engine.error(_("info.classification attribute in %(fmri)s "
                    "does not contain one of the values defined for the "
                    "section %(section)s: %(ref_cats)s from %(path)s") %
                    {"section": section,
                    "fmri": fmri,
                    "path": self.classification_path,
                    "ref_cats": ref_cats },
                    msgid="%s.6" % msgid)
