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

import inspect

import pkg.variant as variant

class LintException(Exception):
        """An exception thrown when something fatal has gone wrong during
        the linting."""
        def __unicode__(self):
                # To workaround python issues 6108 and 2517, this provides a
                # a standard wrapper for this class' exceptions so that they
                # have a chance of being stringified correctly.
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

                # lists of lint methods
                self.included_checks = []
                self.excluded_checks = []

                excl = self.config.get("pkglint", "pkglint.exclude").split()
                for item in inspect.getmembers(self, inspect.ismethod):
                        method = item[1]
                        # register the methods in the object that correspond
                        # to lint checks
                        if "pkglint_id" in inspect.getargspec(method)[0]:
                                value = "%s.%s.%s" % (
                                    self.__module__,
                                    self.__class__.__name__, method.__name__)
                                if value not in excl:
                                        self.included_checks.append(method)
                                else:
                                        self.excluded_checks.append(method)

        def startup(self, engine):
                """Called to initialise a given checker using the supplied
                engine."""
                pass

        def shutdown(self, engine):
                pass

        def conflicting_variants(self, actions, pkg_vars):
                """Given a set of actions, determine that none of the actions
                have matching variant values for any variant."""

                conflicts = False
                conflict_vars = set()
                action_list = []

                for action in actions:
                        action_list.append(action)

                # compare every action in the list with every other,
                # determining what actions have conflicting variants
                # The comparison is commutative.
                for i in range(0, len(action_list)):
                        action = action_list[i]
                        var = action.get_variant_template()
                        # if we don't declare any variants on a given
                        # action, then it's automatically a conflict
                        if len(var) == 0:
                                conflicts = True
                        vc = variant.VariantCombinations(var, True)
                        for j in range(i + 1, len(action_list)):
                                cmp_action = action_list[j]
                                cmp_var = variant.VariantCombinations(
                                    cmp_action.get_variant_template(), True)
                                if vc.intersects(cmp_var):
                                        intersection = vc.intersection(cmp_var)
                                        intersection.simplify(pkg_vars,
                                            assert_on_different_domains=False)
                                        conflicts = True
                                        for k in intersection.sat_set:
                                                if len(k) != 0:
                                                        conflict_vars.add(k)
                return conflicts, conflict_vars

class ActionChecker(Checker):
        """A class to check individual actions."""

        def check(self, action, manifest, engine):
                """'action' is a pkg.actions.generic.Action
                'manifest' is a pkg.manifest.Manifest"""

                for func in self.included_checks:
                        func(action, manifest, engine)


class ManifestChecker(Checker):
        """A class to check manifests."""

        def check(self, manifest, engine):
                """'manifest' is a pkg.manifest.Manifest"""

                for func in self.included_checks:
                        func(manifest, engine)


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
