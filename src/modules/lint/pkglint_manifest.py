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

# Some pkg(5) specific lint manifest checks

from pkg.lint.engine import lint_fmri_successor
import pkg.fmri as fmri
import pkg.lint.base as base
import os.path

class PkgManifestChecker(base.ManifestChecker):
        """A class to check manifests."""

        name = "pkglint.manifest"

        def __init__(self, config):
                self.description = _(
                    "Checks for errors within the scope of a single manifest.")

                self.ref_lastnames = {}
                self.lint_lastnames = {}
                self.processed_lastnames = []
                super(PkgManifestChecker, self).__init__(config)

        def startup(self, engine):

                def update_names(pfmri, dic):
                        name = os.path.basename(pfmri.get_name())
                        if name in dic:
                                dic[name].append(pfmri)
                        else:
                                dic[name] = [pfmri]

                engine.logger.debug(
                    _("Seeding reference manifest duplicates dictionaries."))
                for manifest in engine.gen_manifests(engine.ref_api_inst,
                    release=engine.release):
                        if "pkg.renamed" in manifest or \
                            "pkg.obsolete" in manifest:
                                continue
                        update_names(manifest.fmri, self.ref_lastnames)

                engine.logger.debug(
                    _("Seeding lint manifest duplicates dictionaries."))
                for manifest in engine.gen_manifests(engine.lint_api_inst,
                    release=engine.release, pattern=engine.pattern):
                        if "pkg.renamed" in manifest \
                            or "pkg.obsolete" in manifest:
                                continue
                        update_names(manifest.fmri, self.lint_lastnames)

                for manifest in engine.lint_manifests:
                        if "pkg.renamed" in manifest \
                            or "pkg.obsolete" in manifest:
                                continue
                        update_names(manifest.fmri, self.lint_lastnames)
                self._merge_names(self.lint_lastnames, self.ref_lastnames)

        def obsoletion(self, manifest, engine, pkglint_id="001"):
                """Checks for correct package obsoletion.
                * error if obsoleted packages contain anything other than
                  set or signature actions
                * error if pkg.description or pkg.summary are set."""

                if "pkg.obsolete" not in manifest:
                        return

                for key in [ "pkg.description", "pkg.summary" ]:
                        if key in manifest:
                                engine.error(_("obsolete package %(pkg)s has "
                                    "%(key)s attribute") %
                                    {"pkg": manifest.fmri,
                                    "key": key},
                                    msgid="%s%s.1" % (self.name, pkglint_id))

                has_invalid_action = False
                for action in manifest.gen_actions():
                        if action.name not in ["set", "manifest"]:
                                has_invalid_action = True

                if has_invalid_action:
                        engine.error(
                            _("obsolete package %s contains actions other than "
                            "set or signature actions") % manifest.fmri,
                            msgid="%s%s.2" % (self.name, pkglint_id))

        obsoletion.pkglint_desc = _(
            "Obsolete packages should have valid contents.")

        def renames(self, manifest, engine, pkglint_id="002"):
                """Checks for correct package renaming.
                * error if renamed packages contain anything other than set,
                  signature and depend actions."""

                if "pkg.renamed" not in manifest:
                        return

                has_invalid_action = False
                for action in manifest.gen_actions():
                        if action.name not in [ "set", "depend", "signature"]:
                                has_invalid_action = True

                if has_invalid_action:
                        engine.error(_("renamed package %s contains actions "
                            "other than set, depend or signature actions") %
                            manifest.fmri, msgid="%s%s" %
                            (self.name, pkglint_id))

        renames.pkglint_desc = _("Renamed packages should have valid contents.")

        def variants(self, manifest, engine, pkglint_id="003"):
                """Checks for correct use of variant tags.
                * if variant tags present, matching variant descriptions
                  exist and are correctly specified
                * All manifests that deliver file actions of a given
                  architecture declare variant.arch

                These checks are only performed on published packages."""

                if not engine.do_pub_checks:
                        return

                unknown_variants = set()
                undefined_variants = set()
                has_arch_file = False

                for action in manifest.gen_actions():
                        if linted(action):
                                continue

                        if action.name == "file" and \
                            "elfarch" in action.attrs:
                                has_arch_file = True

                        for key in action.attrs:
                                if not key.startswith("variant"):
                                        continue
                                val = action.attrs[key]
                                if key not in manifest:
                                        undefined_variants.add(key)
                                else:
                                        descr = manifest[key]
                                        if val not in descr:
                                                unknown_variants.add(
                                                    "%s=%s" % (key, val))
                if len(undefined_variants) > 0:
                        engine.error(_("variant(s) %(vars)s not defined by "
                            "%(pkg)s") %
                            {"vars": " ".join([v for v in undefined_variants]),
                            "pkg": manifest.fmri},
                            msgid="%s%s.1" % (self.name, pkglint_id))

                if len(unknown_variants) > 0:
                        engine.error(_("variant(s) %(vars)s not in list of "
                            "known values for variants in %(pkg)s") %
                            {"vars": " ".join([v for v in unknown_variants]),
                            "pkg": manifest.fmri},
                            msgid="%s%s.2" % (self.name, pkglint_id))

                if has_arch_file and "variant.arch" not in manifest:
                        engine.error(_("variant.arch not declared in %s") %
                            manifest.fmri,
                            msgid="%s%s.3" % (self.name, pkglint_id))

        variants.pkglint_desc = _("Variants used by packages should be valid.")

        def naming(self, manifest, engine, pkglint_id="004"):
                """Warn when there's a namespace clash where the last component
                of the pkg name matches an existing one in the catalog."""

                lastname = os.path.basename(manifest.fmri.get_name())
                if lastname not in self.ref_lastnames:
                        return

                if lastname in self.processed_lastnames:
                        return

                fmris = self.ref_lastnames[lastname]

                if len(self.ref_lastnames[lastname]) > 1:
                        engine.warning(
                            _("last name component %(name)s in package name "
                            "clashes across %(pkgs)s") %
                            {"name": lastname,
                            "pkgs": " ".join([f.get_fmri() for f in fmris])},
                            msgid="%s%s" % (self.name, pkglint_id))

                self.processed_lastnames.append(lastname)

        naming.pkglint_desc = _(
            "Packages are encouraged to use unique leaf names.")

        def duplicate_deps(self, manifest, engine, pkglint_id="005"):
                """Checks for repeated dependencies, including package version
                substrings."""

                seen_deps = {}
                duplicates = []
                dup_msg = _(
                    "duplicate depend actions in %(pkg)s %(actions)s")
                duplicates = []
                for action in manifest.gen_actions_by_type("depend"):
                        if "require" not in action.attrs["type"]:
                                continue
                        if linted(action):
                                continue
                        if "fmri" not in action.attrs:
                                engine.critical(_("no fmri attribute in depend "
                                    "action in %s") % manifest.fmri,
                                    msgid="%s%s.1" % (self.name, pkglint_id))
                                continue

                        shortname = fmri.extract_pkg_name(action.attrs["fmri"])
                        if shortname not in seen_deps:
                                seen_deps[shortname] = [action]
                        else:
                                seen_deps[shortname].append(action)

                for key in seen_deps:
                        actions = seen_deps[key]
                        if len(actions) > 1:
                                has_conflict, conflict_vars = \
                                    self.conflicting_variants(actions)
                                if has_conflict:
                                        duplicates.append(key)

                if duplicates:
                        engine.error(dup_msg %
                            {"pkg": manifest.fmri,
                            "actions": " ".join([str(d) for d in duplicates])},
                            msgid="%s%s.2" % (self.name, pkglint_id))

        duplicate_deps.pkglint_desc = _(
            "Packages should not have duplicate 'depend' actions.")

        def duplicate_sets(self, manifest, engine, pkglint_id="006"):
                """Checks for duplicate set actions."""
                seen_sets = {}
                dup_set_msg = _("duplicate set actions on %(names)s in %(pkg)s")
                duplicates = []
                for action in manifest.gen_actions_by_type("set"):
                        if linted(action):
                                continue
                        if action.attrs["name"] not in seen_sets:
                                seen_sets[action.attrs["name"]] = [action]
                        else:
                                seen_sets[action.attrs["name"]].append(action)

                for key in seen_sets:
                        actions = seen_sets[key]
                        if len(actions) > 1:
                                has_conflict, conflict_vars = \
                                    self.conflicting_variants(actions)
                                if has_conflict:
                                        duplicates.append(key)

                if duplicates:
                        engine.error(dup_set_msg %
                            {"names": " ".join([str(a) for a in duplicates]),
                            "pkg": manifest.fmri},
                            msgid="%s%s" % (self.name, pkglint_id))

        duplicate_sets.pkglint_desc = _(
            "Packages should not have duplicate 'set' actions.")

        def _merge_names(self, src, target):
                """Merges the given src list into the target list"""

                for p in src:
                        if p not in target:
                                target[p] = src[p]
                                continue

                        src_lst = src[p]
                        targ_lst = target[p]

                        def remove_ancestors(pfmri, targ_list):
                                """Removes older versions of pfmri from
                                targ_list."""
                                removals = []
                                sname = pfmri.get_name()
                                for old in targ_list:
                                        tname = old.get_name()
                                        if lint_fmri_successor(pfmri, old):
                                             removals.append(old)
                                for i in removals:
                                        targ_list.remove(i)

                        for pfmri in src_lst:
                                remove_ancestors(pfmri, targ_lst)
                                targ_lst.append(pfmri)

                        target[p] = targ_lst
def linted(action):
        """Determines if a given action has been marked as linted."""

        return "pkg.linted" in action.attrs and \
            action.attrs["pkg.linted"].lower() == "true"
