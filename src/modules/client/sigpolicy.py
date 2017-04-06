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

import six
import pkg.client.api_errors as apx
from functools import total_ordering

@total_ordering
class Policy(object):
        """Abstract base Policy class.  It defines the interface all subclasses
        must provide.

        Each subclass must also define its "strictness".
        Strictness is a positive integer and is relative to the other
        subclasses in existence.  More than one subclass may have the same
        strictness level.  In the abscence of other information, when combining
        two policies, the result is the stricter policy."""

        _policies = {}

        def __init__(self, *args, **kwargs):
                # This method exists to provide a consistent __init__ method
                # for the factory below.
                object.__init__(self)

        def process_signatures(self, sigs, acts, pub, trust_anchors,
            use_crls):
                """Check that the signatures ("sigs") verify against the actions
                ("acts") using the publisher ("pub") as the repository for
                certificates and "trust_anchors" as the dictionary of trust
                anchors.

                Not implemented in the base class."""
                raise NotImplementedError()

        def __lt__(self, other):
                return self.strictness < other.strictness

        def __eq__(self, other):
                return self.strictness == other.strictness

        __hash__ = None

        def combine(self, other):
                """If the other signature policy is more strict than this
                policy, use the other policy.  Otherwise, use this policy."""

                if self > other:
                        return self
                return other

        def __str__(self):
                return self.name

        @staticmethod
        def policies():
                """Return the names of the signature policies available."""

                return set(Policy._policies.keys())

        @staticmethod
        def policy_factory(name, *args, **kwargs):
                """Given the name of a policy, return a new policy object of
                that type."""

                assert name in Policy._policies
                return Policy._policies[name](*args, **kwargs)


class Ignore(Policy):
        """This policy ignores all signatures except to attempt to retrieve
        any certificates that might be needed if the policy changes."""

        strictness = 1
        name = "ignore"

        def process_signatures(self, sigs, acts, pub, trust_anchors,
            use_crls):
                """Since this policy ignores signatures, only download the
                certificates that might be needed so that they're present if
                the policy changes later."""

                for s in sigs:
                        s.retrieve_chain_certs(pub)

Policy._policies[Ignore.name] = Ignore


class Verify(Policy):
        """This policy verifies that all signatures present are valid but
        doesn't require that a signature be present."""

        strictness = 2
        name = "verify"

        def process_signatures(self, sigs, acts, pub, trust_anchors,
            use_crls):
                """Check that all signatures present are valid signatures."""

                # Ensure that acts can be iterated over repeatedly.
                acts = list(acts)
                for s in sigs:
                        s.verify_sig(acts, pub, trust_anchors, use_crls)

Policy._policies[Verify.name] = Verify

class RequireSigs(Policy):
        """This policy that all signatures present are valid and insists that
        at least one signature is seen with each package."""

        strictness = 3
        name = "require-signatures"

        def process_signatures(self, sigs, acts, pub, trust_anchors,
            use_crls):
                """Check that all signatures present are valid signatures and
                at least one signature action which has been signed with a
                private key is present."""

                # Ensure that acts can be iterated over repeatedly.
                acts = list(acts)
                verified = False
                for s in sigs:
                        verified |= \
                            bool(s.verify_sig(acts, pub, trust_anchors,
                                use_crls)) and \
                            s.is_signed()
                if not verified:
                        raise apx.RequiredSignaturePolicyException(pub)

Policy._policies[RequireSigs.name] = RequireSigs


class RequireNames(Policy):
        """This policy that all signatures present are valid and insists that
        at least one signature is seen with each package.  In addition, it has
        a set of names that must seen as CN's in the chain of trust."""

        strictness = 4
        name = "require-names"
        def __init__(self, req_names, *args, **kwargs):
                assert req_names, "RequireNames requires at least one name " \
                    "to be passed to the constructor."
                Policy.__init__(self, *args, **kwargs)
                if isinstance(req_names, six.string_types):
                        req_names = [req_names]
                self.required_names = frozenset(req_names)

        def process_signatures(self, sigs, acts, pub, trust_anchors,
            use_crls):
                acts = list(acts)
                missing_names = set(self.required_names)
                verified = False
                for s in sigs:
                        verified |= bool(s.verify_sig(acts, pub, trust_anchors,
                            use_crls, missing_names)) and \
                            s.is_signed()
                if missing_names:
                        raise apx.MissingRequiredNamesException(pub,
                            missing_names)

        def combine(self, other):
                """Determines how RequireNames policies combine with another
                policy.  If the other policy is also a RequireNames policy,
                the result is a policy which requires the union of both policies
                required names."""

                if self > other:
                        return self
                if other > self:
                        return other
                return RequireNames(self.required_names | other.required_names)

Policy._policies[RequireNames.name] = RequireNames

DEFAULT_POLICY = "verify"

