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
# Copyright (c) 2010, 2011 Oracle and/or its affiliates. All rights reserved.
#

import inspect

import pkg.variant as variant
import traceback

class LintException(Exception):
        """An exception thrown when something fatal has gone wrong during
        the linting."""
        def __unicode__(self):
                # To workaround python issues 6108 and 2517, this provides a
                # a standard wrapper for this class' exceptions so that they
                # have a chance of being stringified correctly.
                return str(self)

class DuplicateLintedAttrException(Exception):
        """An exception thrown when we've found duplicate pkg.linted* keys."""
        def __unicode__(self):
                return str(self)

class Checker(object):
        """A base class for all lint checks.  pkg.lint.engine discovers classes
        to create these objects according to a configuration file.  Methods that
        implement lint checks within each Checker object must be given a
        'pkglint_id' keyword argument so that the system can discover and
        invoke these methods during lint runs.

        The 'pkglint_id' is used as a short-form identifier for the lint
        check implemented by each method when paired with the checker
        'name' attribute.

        Subclasses define the method signature for the check(..) method called
        from pkg.lint.engine.LintEngine.execute() on instances of that
        subclass.  Subclasses not implementing a new type of lint Checker,
        likely those outside this base module, should not override check(..)
        defined in ActionChecker or ManifestChecker.

        Attributes for each Checker subclass include:

        'name' is an abbreviated name used by the checker
        'description' is a short (one sentence) description of the class."""

        name = "unnamed.checker"
        description = "No description."

        def __init__(self, config):
                """'config' is a ConfigParser object, see pkg.lint.engine for
                documentation on the keys we expect it to contain."""
                self.config = config

                # lists of (lint method, pkglint_id) tuples
                self.included_checks = []
                self.excluded_checks = []

                def get_pkglint_id(method):
                        """Inspects a given checker method to find the
                        'pkglint_id' keyword argument default and returns it."""

                        # the short name for this checker class, Checker.name
                        name = method.im_class.name

                        arg_spec = inspect.getargspec(method)

                        # arg_spec.args is a tuple of the method args,
                        # populating the tuple with both arg values for
                        # non-keyword arguments, and keyword arg names
                        # for keyword args
                        c = len(arg_spec.args) - 1
                        try:
                                i = arg_spec.args.index("pkglint_id")
                        except ValueError:
                                return "%s.?" % name
                        # arg_spec.defaults are the default values for
                        # any keyword args, in order.
                        return "%s%s" % (name, arg_spec.defaults[c - i])

                excl = self.config.get("pkglint", "pkglint.exclude").split()
                for item in inspect.getmembers(self, inspect.ismethod):
                        method = item[1]
                        # register the methods in the object that correspond
                        # to lint checks
                        if "pkglint_id" in inspect.getargspec(method)[0]:
                                value = "%s.%s.%s" % (
                                    self.__module__,
                                    self.__class__.__name__, method.__name__)
                                pkglint_id = get_pkglint_id(method)
                                if value not in excl:
                                        self.included_checks.append(
                                            (method, pkglint_id))
                                else:
                                        self.excluded_checks.append(
                                            (method, pkglint_id))

        def startup(self, engine):
                """Called to initialise a given checker using the supplied
                engine."""
                pass

        def shutdown(self, engine):
                pass

        def conflicting_variants(self, actions, pkg_vars):
                """Given a set of actions, determine that none of the actions
                have matching variant values for any variant.

                We return a list of variants that conflict, and a list of the
                actions involved.
                """

                conflict_vars = set()
                conflict_actions = set()
                action_list = list(actions)

                # compare every action in the list with every other,
                # determining what actions have conflicting variants
                # The comparison is commutative.
                for i in range(0, len(action_list)):
                        action = action_list[i]
                        var = action.get_variant_template()
                        # if we don't declare any variants on a given
                        # action, then it's automatically a conflict
                        if len(var) == 0:
                                conflict_actions.add(action)

                        vc = variant.VariantCombinations(var, True)
                        for j in range(i + 1, len(action_list)):
                                cmp_action = action_list[j]
                                cmp_var = variant.VariantCombinations(
                                    cmp_action.get_variant_template(), True)
                                if vc.intersects(cmp_var):
                                        intersection = vc.intersection(cmp_var)
                                        intersection.simplify(pkg_vars,
                                            assert_on_different_domains=False)
                                        conflict_actions.add(action)
                                        conflict_actions.add(cmp_action)
                                        for k in intersection.sat_set:
                                                if len(k) != 0:
                                                        conflict_vars.add(k)
                return conflict_vars, list(conflict_actions)


class ActionChecker(Checker):
        """A class to check individual actions."""

        def check(self, action, manifest, engine):
                """'action' is a pkg.actions.generic.Action subclass
                'manifest' is a pkg.manifest.Manifest"""

                for func, pkglint_id in self.included_checks:
                        engine.advise_loggers(action=action, manifest=manifest)
                        try:
                                func(action, manifest, engine)
                        except Exception, err:
                                # Checks are still run on actions that are
                                # marked as pkg.linted. If one of those checks
                                # results in an exception, we need to handle
                                # that to avoid one bad Checker crashing
                                # lint session.
                                if engine.linted(action=action,
                                    manifest=manifest, lint_id=pkglint_id):
                                        engine.info("Checker exception ignored "
                                            "from %(check)s on linted action "
                                            "%(action)s in %(mf)s: %(err)s" %
                                            {"check": pkglint_id,
                                            "action": action,
                                            "mf": manifest.fmri,
                                            "err": err},
                                            msgid="pkglint001.3")
                                else:
                                        engine.error("Checker exception from "
                                            "%(check)s on action "
                                            "%(action)s in %(mf)s: %(err)s"
                                            % {"check": pkglint_id,
                                            "action": action,
                                            "mf": manifest.fmri,
                                            "err": err}, msgid="lint.error")
                                        engine.debug(traceback.format_exc(err),
                                            msgid="lint.error")


class ManifestChecker(Checker):
        """A class to check manifests.

        In order for proper 'pkg.linted.*' functionality, checker methods that
        examine individual manifest attributes, should obtain the original 'set'
        action that was the origin of the manifest attribute, advising the
        logging system of the attributes being examined, then examining the
        attribute, before advising the logging system that subsequent
        lint errors on other attributes are no longer related to that action.

        For example, when looking at the pkg.summary attribute, a checker
        method would do:

        action = engine.get_attr_action("pkg.summary", manifest)
        engine.advise_loggers(action=action, manifest=manifest)
        .
        . [ perform checks on the attribute ]
        .
        engine.advise_loggers(manifest=manifest)

        """

        def check(self, manifest, engine):
                """'manifest' is a pkg.manifest.Manifest"""

                for func, pkglint_id in self.included_checks:
                        engine.advise_loggers(manifest=manifest)
                        try:
                                func(manifest, engine)
                        except Exception, err:
                                # see ActionChecker.check(..)
                                if engine.linted(manifest=manifest,
                                    lint_id=pkglint_id):
                                        engine.info("Checker exception ignored "
                                            "from %(check)s on linted manifest "
                                            "%(mf)s: %(err)s" %
                                            {"check": pkglint_id,
                                            "mf": manifest.fmri,
                                            "err": err},
                                            msgid="pkglint001.3")
                                else:
                                        engine.error("Checker exception from "
                                            "%(check)s on %(mf)s: %(err)s"
                                            % {"check": pkglint_id,
                                            "mf": manifest.fmri,
                                            "err": err}, msgid="lint.error")
                                        engine.debug(traceback.format_exc(err),
                                            msgid="lint.error")


def get_checkers(module, config):
        """Return a tuple of a list of Checker objects found in module,
        instantiating each object with the 'config' ConfigParser object, and a
        list of excluded Checker objects."""

        checkers = []
        excluded_checkers = []

        exclude = config.get("pkglint", "pkglint.exclude").split()
        for cl in inspect.getmembers(module, inspect.isclass):
                myclass = cl[1]
                if issubclass(myclass, Checker):
                        obj = myclass(config)
                        name = "%s.%s" % (myclass.__module__, myclass.__name__)
                        if not (name in exclude or
                            myclass.__module__ in exclude):
                                checkers.append(obj)
                        else:
                                excluded_checkers.append(obj)

        return (checkers, excluded_checkers)

def linted(manifest=None, action=None, lint_id=None):
        """Determine whether a given action or manifest is marked as linted.
        We check for manifest or action attributes set to "true" where
        the attribute starts with "pkg.linted" and is a substring of
        pkg.linted.<lint_id> anchored at the start of the string.

        So, pkg.linted.foo  matches checks for foo, foo001 foo004.5, etc.

        pkglint Checker methods should use
        pkg.lint.engine.<LintEngine>.linted() instead of this method."""

        if manifest and action:
                return _linted_action(action, lint_id) or \
                    _linted_manifest(manifest, lint_id)
        if manifest:
                return _linted_manifest(manifest, lint_id)
        if action:
                return _linted_action(action, lint_id)
        return False

def _linted_action(action, lint_id):
        """Determine whether a given action is marked as linted"""
        linted = "pkg.linted.%s" % lint_id
        for key in action.attrs.keys():
                if key.startswith("pkg.linted") and linted.startswith(key):
                        val = action.attrs.get(key, "false")
                        if isinstance(val, basestring):
                                if val.lower() == "true":
                                        return True
                        else:
                                raise DuplicateLintedAttrException(
                                    _("Multiple values for %(key)s "
                                    "in %(actions)s") % {"key": key,
                                    "action": str(action)})
        return False

def _linted_manifest(manifest, lint_id):
        """Determine whether a given manifest is marked as linted"""
        linted = "pkg.linted.%s" % lint_id
        for key in manifest.attributes.keys():
                if key.startswith("pkg.linted") and linted.startswith(key):
                        val = manifest.attributes.get(key, "false")
                        if isinstance(val, basestring):
                                if val.lower() == "true":
                                        return True
                        else:
                                raise DuplicateLintedAttrException(
                                    _("Multiple values for %(key)s "
                                    "in %(manifest)s") % {"key": key,
                                    "manifest": manifest.fmri})
        return False
