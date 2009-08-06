#!/usr/bin/python2.4
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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""
package containing packaging action (file type) modules

This package contains modules describing packaging actions, or file types.  The
actions are dynamically discovered, so that new modules can be placed in this
package directory and they'll just be picked up.  The current package contents
can be seen in the section "PACKAGE CONTENTS", below.

This package has one data member: "types".  This is a dictionary which maps the
action names to the classes that represent them.

This package also has one function: "fromstr", which creates an action instance
based on a str() representation of an action.
"""

import inspect
import os

# All modules in this package (all python files except __init__.py with their
# extensions stripped off).
__all__ = [
        f[:-3]
            for f in os.listdir(__path__[0])
            if f.endswith(".py") and f != "__init__.py"
]

# A dictionary of all the types in this package, mapping to the classes that
# define them.
types = {}
for modname in __all__:
        module = __import__("%s.%s" % (__name__, modname),
            globals(), locals(), [modname])

        nvlist = inspect.getmembers(module, inspect.isclass)

        # Pull the class objects out of nvlist, keeping only those that are
        # actually defined in this package.
        classes = [
                c[1]
                    for c in nvlist
                    if '.'.join(c[1].__module__.split('.')[:-1]) == __name__
        ]
        for cls in classes:
                types[cls.name] = cls

# Clean up after ourselves
del f, modname, module, nvlist, classes, c, cls

class ActionError(Exception):
        """Base exception class for Action errors."""

        def __str__(self):
                raise NotImplementedError()

class UnknownActionError(ActionError):
        def __init__(self, *args):
                self.actionstr = args[0]
                self.type = args[1]

        def __str__(self):
                if hasattr(self, "fmri") and self.fmri is not None:
                        return _("unknown action type '%(type)s' in package "
                            "'%(fmri)s' in action '%(action)s'") % {
                            "type": self.type, "fmri": self.fmri,
                            "action": self.actionstr }
                return _("unknown action type '%(type)s' in action "
                    "'%(action)s'") % { "type": self.type,
                    "action": self.actionstr }

class MalformedActionError(ActionError):
        def __init__(self, *args):
                self.actionstr = args[0]
                self.position = args[1]
                self.errorstr = args[2]

        def __str__(self):
                marker = " " * (4 + self.position) + "^"
                if hasattr(self, "fmri") and self.fmri is not None:
                        return _("Malformed action in package '%(fmri)s' at "
                            "position: %(pos)d:\n    %(action)s\n"
                            "%(marker)s") % { "fmri": self.fmri,
                            "pos": self.position, "action": self.actionstr,
                            "marker": marker }
                return _("Malformed action at position: %(pos)d:\n    "
                    "%(action)s\n%(marker)s") % { "pos": self.position,
                    "action": self.actionstr, "marker": marker }


class ActionDataError(ActionError):
        """Used to indicate that a file-related error occuring during action
        initialization."""

        def __init__(self, *args):
                self.error = args[0]

        def __str__(self):
                return str(self.error)


class InvalidActionError(ActionError):
        """Used to indicate that attributes provided were invalid, or required
        attributes were missing for an action."""

        def __init__(self, *args):
                self.actionstr = args[0]
                self.errorstr = args[1]

        def __str__(self):
                if hasattr(self, "fmri") and self.fmri is not None:
                        return _("invalid action in package %(fmri)s: "
                            "%(action)s: %(error)s") % { "fmri": self.fmri,
                            "action": self.actionstr, "error": self.errorstr }
                return _("invalid action, '%(action)s': %(error)s") % {
                        "action": self.actionstr, "error": self.errorstr }


from _actions import _fromstr

def attrsfromstr(string):
        """Create an attribute dict given a string w/ key=value pairs.

        Raises MalformedActionError if the attributes have syntactic problems.
        """
        return _fromstr("bogus %s" % string)[2]

def fromstr(string, data=None):
        """Create an action instance based on a str() representation of an
        action.

        Raises UnknownActionError if the action type is unknown.
        Raises MalformedActionError if the action has other syntactic problems.
        """

        atype, ahash, attr_dict = _fromstr(string)

        if atype not in types:
                raise UnknownActionError(string, atype)

        action = types[atype](data=data, **attr_dict)

        ka = action.key_attr
        if ka is not None and (ka not in action.attrs or
            action.attrs[ka] is None):
                raise InvalidActionError(string, _("required attribute '%s' "
                    "was not provided.") % ka)

        if ahash:
                action.hash = ahash

        return action

def fromlist(type, args, hash=None, data=None):
        """Create an action instance based on a sequence of "key=value" strings.

        Raises MalformedActionError if the attribute strings are malformed.
        """

        if type not in types:
                raise UnknownActionError(("%s %s" % (type,
                    " ".join(args))).strip(), type)

        attrs = {}

        try:
                for a, v in [kv.split("=", 1) for kv in args]:
                        if v == '' or a == '':
                                kvi = args.index(kv) + 1
                                p1 = " ".join(args[:kvi])
                                p2 = " ".join(args[kvi:])
                                raise MalformedActionError(
                                    "%s %s %s" % (type, p1, p2), len(p1) + 1,
                                    "attribute '%s'" % kv)

                        # This is by far the common case-- an attribute with
                        # a single value.
                        if a not in attrs:
                                attrs[a] = v
                        else:
                                av = attrs[a]
                                if isinstance(av, list):
                                        attrs[a].append(v)
                                else:
                                        attrs[a] = [ av, v ]
        except ValueError:
                # We're only here if the for: statement above throws a
                # MalformedActionError.  That can happen if split yields a
                # single element, which is possible if e.g. an attribute lacks
                # an =.
                kvi = args.index(kv) + 1
                p1 = " ".join(args[:kvi])
                p2 = " ".join(args[kvi:])
                raise MalformedActionError("%s %s %s" % (type, p1, p2),
                    len(p1) + 2, "attribute '%s'" % kv)

        action = types[type](data=data, **attrs)

        ka = action.key_attr
        if ka is not None and (ka not in action.attrs or
            action.attrs[ka] is None):
                raise InvalidActionError(("%s %s" % (type,
                    " ".join(args))).strip(), _("required attribute, "
                    "'%s', was not provided.") % ka)

        if hash:
                action.hash = hash

        return action
