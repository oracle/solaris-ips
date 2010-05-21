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
# Copyright (c) 2007, 2010, Oracle and/or its affiliates. All rights reserved.
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

        def __unicode__(self):
                # To workaround python issues 6108 and 2517, this provides a
                # a standard wrapper for this class' exceptions so that they
                # have a chance of being stringified correctly.
                return str(self)

        def __str__(self):
                raise NotImplementedError()

class UnknownActionError(ActionError):
        def __init__(self, *args):
                ActionError.__init__(self)
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
                ActionError.__init__(self)
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

        def __init__(self, *args, **kwargs):
                ActionError.__init__(self)
                self.error = args[0]
                self.path = kwargs.get("path", None)

        def __str__(self):
                return str(self.error)


class InvalidActionError(ActionError):
        """Used to indicate that attributes provided were invalid, or required
        attributes were missing for an action."""

        def __init__(self, *args):
                ActionError.__init__(self)
                self.actionstr = args[0]
                self.errorstr = args[1]

        def __str__(self):
                if hasattr(self, "fmri") and self.fmri is not None:
                        return _("invalid action in package %(fmri)s: "
                            "%(action)s: %(error)s") % { "fmri": self.fmri,
                            "action": self.actionstr, "error": self.errorstr }
                return _("invalid action, '%(action)s': %(error)s") % {
                        "action": self.actionstr, "error": self.errorstr }


class InvalidActionAttributesError(ActionError):
        """Used to indicate that one more action attributes were invalid."""

        def __init__(self, act, errors, fmri=None):
                """'act' is an Action (object or string).

                'errors' is a list of tuples of the form (name, error) where
                'name' is the action attribute name, and 'error' is a string
                indicating what attribute is invalid and why.

                'fmri' is an optional package FMRI (object or string)
                indicating what package contained the actions with invalid
                attributes."""

                ActionError.__init__(self)
                self.action = act
                self.errors = errors
                self.fmri = fmri

        def __str__(self):
                act_errors = "\n  ".join(err for name, err in self.errors)
                if self.fmri:
                        return _("The action '%(action)s' in package "
                            "'%(fmri)s' has invalid attribute(s):\n"
                            "  %(act_errors)s") % { "action": self.action,
                            "fmri": self.fmri, "act_errors": act_errors }
                return _("The action '%(action)s' has invalid attribute(s):\n"
                    "  %(act_errors)s") % { "action": self.action,
                    "act_errors": act_errors }


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

def internalizelist(atype, args, ahash=None, basedirs=None):
        """Create an action instance based on a sequence of "key=value" strings.
        This function also translates external representations of actions with
        payloads (like file and license which can use NOHASH or file paths to
        point to the payload) to an internal representation which sets the
        data field of the action returned.

        The "atype" parameter is the type of action to be built.

        The "args" parameter is the sequence of "key=value" strings.

        The "ahash" parameter is used to set the hash value for the action.

        The "basedirs" parameter is the list of directories to look in to find
        any payload for the action.

        Raises MalformedActionError if the attribute strings are malformed.
        """

        if atype not in types:
                raise UnknownActionError(("%s %s" % (atype,
                    " ".join(args))).strip(), atype)

        data = None

        if atype in ("file", "license"):
                data = args.pop(0)
        
        attrs = {}

        try:
                for a, v in [kv.split("=", 1) for kv in args]:
                        if v == '' or a == '':
                                kvi = args.index(kv) + 1
                                p1 = " ".join(args[:kvi])
                                p2 = " ".join(args[kvi:])
                                raise MalformedActionError(
                                    "%s %s %s" % (atype, p1, p2), len(p1) + 1,
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
                raise MalformedActionError("%s %s %s" % (atype, p1, p2),
                    len(p1) + 2, "attribute '%s'" % kv)

        # keys called 'data' cause problems due to the named parameter being
        # passed to the action constructor below. Check for these. Note that
        # _fromstr also checks for this.
        if "data" in attrs:
                astr = atype + " " + " ".join(args)
                raise InvalidActionError(astr,
                        "%s action cannot have a 'data' attribute" % atype)

        action = types[atype](data=None, **attrs)

        ka = action.key_attr
        if ka is not None and (ka not in action.attrs or
            action.attrs[ka] is None):
                raise InvalidActionError(("%s %s" % (atype,
                    " ".join(args))).strip(), _("required attribute, "
                    "'%s', was not provided.") % ka)

        if ahash:
                action.hash = ahash

        local_path, used_basedir = set_action_data(data, action, basedirs)
        return action, local_path

def internalizestr(string, basedirs=None, load_data=True):
        """Create an action instance based on a sequence of strings.
        This function also translates external representations of actions with
        payloads (like file and license which can use NOHASH or file paths to
        point to the payload) to an internal representation which sets the
        data field of the action returned.

        In general, each string should be in the form of "key=value". The
        exception is a payload for certain actions which should be the first
        item in the sequence.

        Raises MalformedActionError if the attribute strings are malformed.
        """

        string = string.strip()
        args = string.split()
        atype = args.pop(0)
        
        if atype not in types:
                raise UnknownActionError(("%s %s" % (atype,
                    " ".join(args))).strip(), atype)

        action = fromstr(string)

        if atype not in ("file", "license") or not load_data:
                return action, None, None

        local_path, used_basedir = set_action_data(args[0], action, basedirs)
        return action, local_path, used_basedir

def set_action_data(payload, action, basedirs):
        """Sets the data field of an action using the information in the
        payload and returns the actual path used to set the data and the basedir
        used to find the path to the data.

        The "payload" parameter is the representation of the data to assign to
        the action's data field. It can either be NOHASH or a path to the file.

        The "action" parameter is the action to modify.

        The "basedirs" parameter contains the directories to examine to find
        the payload in."""

        if not payload:
                return None, None

        if payload == "NOHASH":
                filepath = os.path.sep + action.attrs["path"]
        else:
                filepath = payload

        used_basedir = None
        if basedirs:
                path = filepath.lstrip(os.path.sep)
                # look for file in specified dirs
                for d in basedirs:
                        data = os.path.join(d, path)
                        if os.path.isfile(data):
                                used_basedir = d
                                break
        else:
                data = filepath

        action.set_data(data)
        return data, used_basedir
