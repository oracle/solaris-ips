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

# Some pkg(5) specific lint manifest checks

import os.path
import six
from six.moves import configparser

import pkg.fmri as fmri
import pkg.lint.base as base
from pkg.lint.engine import lint_fmri_successor


class PkgManifestChecker(base.ManifestChecker):
        """A class to check manifests."""

        name = "pkglint.manifest"

        def __init__(self, config):
                self.description = _(
                    "Checks for errors within the scope of a single manifest.")

                self.ref_lastnames = {}
                self.lint_lastnames = {}
                self.processed_lastnames = []

                # maps package names to a list of packages which depend on them.
                self.dependencies = {}

                super(PkgManifestChecker, self).__init__(config)

        def startup(self, engine):

                def seed_names_dict(manifest, dic):
                        if "pkg.renamed" in manifest or \
                            "pkg.obsolete" in manifest:
                                return
                        name = os.path.basename(manifest.fmri.get_name())
                        if name in dic:
                                dic[name].append(manifest.fmri)
                        else:
                                dic[name] = [manifest.fmri]

                def seed_depend_dict(mf, dic):
                        """Updates a dictionary of package names that declare
                        dependencies, keyed by the depend action fmri name.
                        We drop versions and consider all dependency types
                        except 'incorporate'."""

                        name = mf.fmri
                        for action in mf.gen_actions_by_type("depend"):
                                if action.attrs.get("type") == "incorporate":
                                        continue
                                dep = action.attrs["fmri"]
                                try:
                                        if isinstance(dep, six.string_types):
                                                f = fmri.PkgFmri(dep)
                                                dic.setdefault(
                                                    f.get_name(), []
                                                    ).append(name)
                                        elif isinstance(dep, list):
                                                for d in dep:
                                                        f = fmri.PkgFmri(d)
                                                        dic.setdefault(
                                                            f.get_name(), []
                                                            ).append(name)
                                # If we have a bad FMRI, this will be picked up
                                # by pkglint.action006 and pkglint.action009.
                                except fmri.FmriError:
                                        pass

                engine.logger.debug(
                    _("Seeding reference manifest dictionaries."))
                for manifest in engine.gen_manifests(engine.ref_api_inst,
                    release=engine.release):
                        seed_depend_dict(manifest, self.dependencies)
                        seed_names_dict(manifest, self.ref_lastnames)

                engine.logger.debug(
                    _("Seeding lint manifest dictionaries."))
                for manifest in engine.gen_manifests(engine.lint_api_inst,
                    release=engine.release, pattern=engine.pattern):
                        seed_depend_dict(manifest, self.dependencies)
                        seed_names_dict(manifest, self.lint_lastnames)

                for manifest in engine.lint_manifests:
                        seed_depend_dict(manifest, self.dependencies)
                        seed_names_dict(manifest, self.lint_lastnames)

                self._merge_names(self.lint_lastnames, self.ref_lastnames,
                    ignore_pubs=engine.ignore_pubs)

        def obsoletion(self, manifest, engine, pkglint_id="001"):
                """Checks for correct package obsoletion.
                * error if obsoleted packages contain anything other than
                  set or signature actions
                * error if pkg.description or pkg.summary are set.
                * warn if other packages have non-incorporate dependencies on
                  this package.
                """

                if manifest.get("pkg.obsolete", "false") != "true":
                        return

                for key in [ "pkg.description", "pkg.summary" ]:
                        if key in manifest:
                                action = engine.get_attr_action(key, manifest)
                                engine.advise_loggers(action=action,
                                    manifest=manifest)
                                engine.error(_("obsolete package {pkg} has "
                                    "{key} attribute").format(
                                    pkg=manifest.fmri,
                                    key=key),
                                    msgid="{0}{1}.1".format(self.name,
                                    pkglint_id))

                # the loggers are no longer concerned about actions
                engine.advise_loggers(manifest=manifest)

                has_invalid_action = False
                linted_action = None

                lint_id = "{0}{1}.2".format(self.name, pkglint_id)
                for action in manifest.gen_actions():
                        # since we only emit the error once, after iterating
                        # over all actions, we may lose the action that could
                        # contain the linted flag, so the logging
                        # subsystem will not be able to use it to print a
                        # "lint bypassed" message.  Save it here.
                        if engine.linted(action=action, manifest=manifest,
                            lint_id=lint_id):
                                linted_action = action
                                continue

                        if action.name not in ["set", "signature"]:
                                has_invalid_action = True

                if has_invalid_action:
                        engine.error(
                            _("obsolete package {0} contains actions other than "
                            "set or signature actions").format(manifest.fmri),
                            msgid=lint_id)

                # report that we bypassed a check
                if linted_action and not has_invalid_action:
                        engine.advise_loggers(action=linted_action,
                            manifest=manifest)
                        engine.error(
                            _("obsolete package {0} contains actions other than "
                            "set or signature actions").format(manifest.fmri),
                            msgid=lint_id)

                # determine whether other packages we know about have
                # dependencies on this obsolete package.
                obsolete_depends = set()
                lint_id = "{0}{1}.3".format(self.name, pkglint_id)

                depends = set(
                    self.dependencies.get(manifest.fmri.get_name(), []))
                if depends:
                        for depending_package in depends:
                                p = engine.get_manifest(str(depending_package),
                                    search_type=engine.LATEST_SUCCESSOR)
                                if p.get("pkg.obsolete", None) != "true":
                                        obsolete_depends.add(p.fmri)
                if obsolete_depends:
                        # this is only a warning, because at install-time the
                        # solver may still be able to find a non-obsolete
                        # version of a package.
                        engine.warning("obsolete package {pkg} is depended "
                            "upon by the following packages: "
                            "{deps}".format(pkg=manifest.fmri, deps=" ".join(
                            [str(fmri) for fmri in obsolete_depends])),
                            msgid=lint_id)

        obsoletion.pkglint_desc = _(
            "Obsolete packages should have valid contents.")

        def renames(self, manifest, engine, pkglint_id="002"):
                """Checks for correct package renaming.
                * error if renamed packages contain anything other than set,
                  signature and depend actions.
                * follows renames, ensuring they're not circular, and don't
                  end up at an obsolete package.
                """

                if "pkg.renamed" not in manifest:
                        return

                has_invalid_action = False
                seen_linted_action = False
                invalid_action_id = "{0}{1}.1".format(self.name, pkglint_id)
                count_depends = 0

                for action in manifest.gen_actions():
                        if action.name not in ["set", "depend", "signature"]:

                                if engine.linted(action=action,
                                    manifest=manifest,
                                    lint_id=invalid_action_id):
                                        seen_linted_action = action
                                        continue
                                has_invalid_action = True

                        if action.name == "depend":
                                if "incorporation" not in action.attrs["fmri"] or \
                                    action.attrs["type"] == "require":
                                        count_depends = count_depends + 1

                if has_invalid_action:
                        engine.error(_("renamed package {0} contains actions "
                            "other than set, depend or signature actions").format(
                            manifest.fmri), msgid=invalid_action_id)

                # if all actions in the manifest that would have caused errors
                # were marked as linted, we need to advise the logging mechanism
                # of at least one action that was marked as linted, then log the
                # error, ultimately resulting in an INFO level message.
                if seen_linted_action and not has_invalid_action:
                        engine.advise_loggers(action=seen_linted_action,
                            manifest=manifest)
                        engine.error(_("renamed package {0} contains actions "
                            "other than set, depend or signature actions").format(
                            manifest.fmri), msgid=invalid_action_id)

                if count_depends == 0:
                        engine.error(_("renamed package {0} does not declare a "
                            "'require' dependency indicating what it was "
                            "renamed to").format(
                            manifest.fmri), msgid="{0}{1}.2".format(
                            self.name, pkglint_id))

                try:
                        mf = engine.follow_renames(str(manifest.fmri),
                            old_mfs=[])
                        if not mf:
                                engine.warning(_("unable to follow renames for "
                                    "{0}: possible missing package").format(
                                    manifest.fmri), msgid="{0}{1}.3".format(
                                    self.name, pkglint_id))
                        else:
                                if "pkg.obsolete" not in mf:
                                        return
                                engine.error(_("package {pkg} was renamed "
                                    "to an obsolete package {obs}").format(
                                    pkg=manifest.fmri, obs=mf.fmri),
                                    msgid="{0}{1}.5".format(self.name,
                                    pkglint_id))

                except base.LintException as err:
                        engine.error(_("package renaming: {0}").format(str(err)),
                            msgid="{0}{1}.4".format(self.name, pkglint_id))

        renames.pkglint_desc = _("Renamed packages should have valid contents.")

        def variants(self, manifest, engine, pkglint_id="003"):
                """Checks for correct use of variant tags.
                * if variant tags present, matching variant descriptions
                  exist and are correctly specified, with the exception of
                  variant.debug.* variants
                * All manifests that deliver file actions of a given
                  architecture declare variant.arch

                These checks are only performed on published packages."""

                if not engine.do_pub_checks:
                        return

                unknown_variants = set()
                undefined_variants = set()
                has_arch_file = False

                pkg_vars = manifest.get_all_variants()

                undefined_lint_id = "{0}{1}.1".format(self.name, pkglint_id)
                unknown_lint_id = "{0}{1}.2".format(self.name, pkglint_id)
                missing_arch_lint_id = "{0}{1}.3".format(self.name, pkglint_id)

                def ignore_variant(varname):
                        """check whether we can ignore this variant."""
                        return varname.startswith("variant.debug")

                for action in manifest.gen_actions():
                        if engine.linted(action=action, manifest=manifest):
                                continue

                        if action.name == "file" and \
                            action.attrs.get("pkg.filetype") == "elf" or \
                            "elfarch" in action.attrs:
                                has_arch_file = True

                        vct = action.get_variant_template()
                        diff = vct.difference(pkg_vars)
                        for k in diff.type_diffs:
                                if not engine.linted(action=action,
                                    manifest=manifest,
                                    lint_id=undefined_lint_id):
                                        if ignore_variant(k):
                                                continue
                                        undefined_variants.add(k)
                        for k, v in diff.value_diffs:
                                if not engine.linted(action=action,
                                    manifest=manifest,
                                    lint_id=unknown_lint_id):
                                        if ignore_variant(k):
                                                continue
                                        unknown_variants.add("{0}={1}".format(k,
                                            v))

                if len(undefined_variants) > 0:
                        vlist = sorted((v for v in undefined_variants))
                        engine.error(_("variant(s) {vars} not defined by "
                            "{pkg}").format(
                            vars=" ".join(vlist),
                            pkg=manifest.fmri), msgid=undefined_lint_id)

                if len(unknown_variants) > 0:
                        vlist = sorted((v for v in unknown_variants))
                        engine.error(_("variant(s) {vars} not in list "
                            "of known values for variants in {pkg}").format(
                            vars=" ".join(vlist),
                            pkg=manifest.fmri), msgid=unknown_lint_id)

                if has_arch_file and "variant.arch" not in manifest and \
                    not engine.linted(manifest=manifest,
                    lint_id=missing_arch_lint_id):
                        engine.error(_("variant.arch not declared in {0}").format(
                            manifest.fmri), msgid=missing_arch_lint_id)

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

                # we ignored renamed or obsolete packages when building
                # ref_lastnames, so this package might not be there,
                # in which case, we can ignore this package too.
                if manifest.fmri not in fmris:
                        return

                if len(self.ref_lastnames[lastname]) > 1:
                        plist = sorted((f.get_fmri() for f in fmris))
                        engine.warning(
                            _("last name component {name} in package name "
                            "clashes across {pkgs}").format(
                            name=lastname,
                            pkgs=" ".join(plist)),
                            msgid="{0}{1}".format(self.name, pkglint_id))

                if not engine.linted(manifest=manifest,
                    lint_id="{0}{1}".format(self.name, pkglint_id)):
                        self.processed_lastnames.append(lastname)

        naming.pkglint_desc = _(
            "Packages are encouraged to use unique leaf names.")

        def duplicate_deps(self, manifest, engine, pkglint_id="005"):
                """Checks for repeated dependencies, including package version
                substrings."""

                seen_deps = {}
                duplicates = []
                dup_msg = _(
                    "duplicate depend actions in {pkg} {actions}")
                duplicates = []
                for action in manifest.gen_actions_by_type("depend"):
                        # this only checks require and require-any actions
                        if "require" not in action.attrs["type"]:
                                continue

                        if "fmri" not in action.attrs:
                                lint_id = "{0}{1}.1".format(self.name,
                                    pkglint_id)
                                if not engine.linted(action=action,
                                    manifest=manifest, lint_id=lint_id):
                                        engine.critical(
                                            _("no fmri attribute in depend "
                                            "action in {0}").format(
                                            manifest.fmri), msgid=lint_id)
                                continue

                        lint_id = "{0}{1}.2".format(self.name, pkglint_id)
                        if engine.linted(action=action, manifest=manifest,
                            lint_id=lint_id):
                                    continue

                        deps = action.attrs["fmri"]
                        if isinstance(deps, six.string_types):
                                deps = [deps]

                        for dep in deps:
                                shortname = fmri.extract_pkg_name(dep)
                                if shortname not in seen_deps:
                                        seen_deps[shortname] = [action]
                                else:
                                        seen_deps[shortname].append(action)

                for key in seen_deps:
                        actions = seen_deps[key]
                        if len(actions) > 1:
                                conflict_vars, conflict_actions = \
                                    self.conflicting_variants(actions,
                                        manifest.get_all_variants())
                                if conflict_actions:
                                        duplicates.append(key)

                if duplicates:
                        dlist = sorted((str(d) for d in duplicates))
                        engine.error(dup_msg.format(
                            pkg=manifest.fmri,
                            actions=" ".join(dlist)),
                            msgid="{0}{1}.2".format(self.name, pkglint_id))

        duplicate_deps.pkglint_desc = _(
            "Packages should not have duplicate 'depend' actions.")

        def duplicate_sets(self, manifest, engine, pkglint_id="006"):
                """Checks for duplicate set actions."""
                seen_sets = {}
                dup_set_msg = _("duplicate set actions on {names} in {pkg}")
                duplicates = []
                lint_id = "{0}{1}".format(self.name, pkglint_id)
                for action in manifest.gen_actions_by_type("set"):
                        lint_id = "{0}{1}".format(self.name, pkglint_id)
                        if engine.linted(action=action, manifest=manifest,
                            lint_id=lint_id):
                                continue
                        if action.attrs["name"] not in seen_sets:
                                seen_sets[action.attrs["name"]] = [action]
                        else:
                                seen_sets[action.attrs["name"]].append(action)

                for key in seen_sets:
                        actions = seen_sets[key]
                        if len(actions) > 1:
                                conflict_vars, conflict_actions = \
                                    self.conflicting_variants(actions,
                                        manifest.get_all_variants())
                                if conflict_actions:
                                        duplicates.append(key)

                if duplicates:
                        dlist = sorted((str(d) for d in duplicates))
                        engine.error(dup_set_msg.format(
                            names=" ".join(dlist),
                            pkg=manifest.fmri),
                            msgid=lint_id)

        duplicate_sets.pkglint_desc = _(
            "Packages should not have duplicate 'set' actions.")

        def linted(self, manifest, engine, pkglint_id="007"):
                """Logs an INFO message with the key/value pairs of all
                pkg.linted* attributes set on this manifest."""

                linted_attrs = [(key, manifest.attributes[key])
                    for key in sorted(manifest.attributes.keys())
                    if key.startswith("pkg.linted")]

                if linted_attrs:
                        engine.info(_("pkg.linted attributes detected for "
                            "{pkg}: {linted}").format(pkg=manifest.fmri,
                            linted=", ".join(["{0}={1}".format(key, val)
                             for key,val in linted_attrs])),
                             msgid="{0}{1}".format(self.name, pkglint_id),
                             ignore_linted=True)

        linted.pkglint_desc = _("Show manifests with pkg.linted attributes.")

        def info_classification(self, manifest, engine, pkglint_id="008"):
                """Checks that the info.classification attribute is valid."""

                if (not "info.classification" in manifest) or \
                    self.skip_classification_check:
                        return

                if not self.classification_data or \
                    not self.classification_data.sections():
                        engine.error(_("Unable to perform manifest checks "
                            "for info.classification attribute: {0}").format(
                            self.bad_classification_data),
                            msgid="{0}{1}.1".format(self.name, pkglint_id))
                        self.skip_classification_check = True
                        return

                action = engine.get_attr_action("info.classification", manifest)
                engine.advise_loggers(action=action, manifest=manifest)

                for item in action.attrlist("value"):
                        self._check_info_classification_value(engine, item,
                            manifest.fmri, "{0}{1}".format(self.name, pkglint_id))

        info_classification.pkglint_desc = _(
            "info.classification attribute should be valid.")

        def _check_info_classification_value(self, engine, value, fmri, msgid):

                prefix = "org.opensolaris.category.2008:"

                if not prefix in value:
                        engine.error(_("info.classification attribute "
                            "does not contain '{prefix}' for {fmri}").format(
                            **locals()), msgid="{0}.2".format(msgid))
                        return

                classification = value.replace(prefix, "")

                components = classification.split("/", 1)
                if len(components) != 2:
                        engine.error(_("info.classification value {value} "
                            "does not match "
                            "{prefix}<Section>/<Category> for {fmri}").format(
                            **locals()), msgid="{0}.3".format(msgid))
                        return

                # the data file looks like:
                # [Section]
                # category = Cat1,Cat2,Cat3
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
                except configparser.NoSectionError:
                        sections = self.classification_data.sections()
                        engine.error(_("info.classification value {value} "
                            "does not contain one of the valid sections "
                            "{ref_sections} for {fmri}.").format(
                            value=value,
                            ref_sections=", ".join(sorted(sections)),
                            fmri=fmri),
                            msgid="{0}.4".format(msgid))
                        return
                except configparser.NoOptionError:
                        engine.error(_("Invalid info.classification value for "
                            "{fmri}: data file {file} does not have a "
                            "'category' key for section {section}.").format(
                            file=self.classification_path,
                            section=section,
                            fmri=fmri),
                             msgid="{0}.5".format(msgid))
                        return

                if valid_value:
                        return

                ref_cats = self.classification_data.get(section, "category")
                engine.error(_("info.classification attribute in {fmri} "
                    "does not contain one of the values defined for the "
                    "section {section}: {ref_cats} from {path}").format(
                    section=section,
                    fmri=fmri,
                    path=self.classification_path,
                    ref_cats=ref_cats),
                    msgid="{0}.6".format(msgid))

        def bogus_description(self, manifest, engine, pkglint_id="009"):
                """Warns when a package has an empty summary or description,
                or a description which is identical to the summary."""

                desc = manifest.get("pkg.description", None)
                summ = manifest.get("pkg.summary", None)

                if desc == "":
                        action = engine.get_attr_action("pkg.description",
                            manifest)
                        engine.advise_loggers(action=action, manifest=manifest)
                        engine.warning(_("Empty pkg.description in {0}").format(
                            manifest.fmri),
                            msgid="{0}{1}.1".format(self.name, pkglint_id))

                if summ == "":
                        action = engine.get_attr_action("pkg.summary",
                            manifest)
                        engine.advise_loggers(action=action, manifest=manifest)
                        engine.warning(_("Empty pkg.summary in {0}").format(
                            manifest.fmri),
                            msgid="{0}{1}.3".format(self.name, pkglint_id))

                if desc == summ and desc:
                        action = engine.get_attr_action("pkg.summary", manifest)
                        engine.advise_loggers(action=action, manifest=manifest)
                        engine.warning(_("pkg.description matches pkg.summary "
                            "in {0}").format(manifest.fmri),
                            msgid="{0}{1}.2".format(self.name, pkglint_id))

        bogus_description.pkglint_desc = _(
            "A package's description should not match its summary.")

        def missing_attrs(self, manifest, engine, pkglint_id="010"):
                """Various checks for missing attributes
                * error when a package doesn't have a pkg.summary
                (pkg.fmri should be present too, but that would get caught
                before we get here)
                """
                if "pkg.renamed" in manifest:
                        return

                if "pkg.obsolete" in manifest:
                        return

                if "pkg.summary" not in manifest:
                        engine.error(
                            _("Missing attribute 'pkg.summary' in {0}").format(
                            manifest.fmri),
                            msgid="{0}{1}.2".format(self.name, pkglint_id))

        missing_attrs.pkglint_desc = _(
            "Standard package attributes should be present.")

        def missing_smf_fmri(self, manifest, engine, pkglint_id="011"):
                """If we deliver files to lib/svc/manifest or
                var/svc/manifest, we should include an org.opensolaris.smf.fmri
                attribute in the manifest.  This only reports a warning, because
                without pkglint content-checking support, we do not know whether
                the file actually contains any services or instances."""

                smf_manifests = []
                for action in manifest.gen_actions_by_type("file"):

                        if "path" not in action.attrs:
                                contine

                        path = action.attrs["path"]

                        if not path.endswith(".xml"):
                                continue

                        if not (path.startswith("lib/svc/manifest") or
                            path.startswith("var/svc/manifest")):
                                continue
                        smf_manifests.append(path)

                if not smf_manifests:
                        return

                if "org.opensolaris.smf.fmri" in manifest:
                        return

                engine.warning(
                    _("SMF manifests were delivered by {pkg}, but no "
                    "org.opensolaris.smf.fmri attribute was found. "
                    "Manifests found were: {manifests}").format(
                    manifests=" ".join(smf_manifests),
                    pkg=manifest.fmri),
                    msgid="{0}{1}".format(self.name, pkglint_id))

        missing_smf_fmri.pkglint_desc = _(
            "Packages delivering SMF services should have "
            "org.opensolaris.smf.fmri attributes.")

        def _merge_names(self, src, target, ignore_pubs=True):
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
                                        if lint_fmri_successor(pfmri, old,
                                            ignore_pubs=ignore_pubs):
                                                removals.append(old)
                                for i in removals:
                                        targ_list.remove(i)

                        for pfmri in src_lst:
                                remove_ancestors(pfmri, targ_lst)
                                targ_lst.append(pfmri)

                        target[p] = targ_lst
