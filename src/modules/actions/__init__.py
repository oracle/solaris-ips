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
# Copyright (c) 2007, 2016, Oracle and/or its affiliates. All rights reserved.
#

"""
package containing packaging action (file type) modules

This package contains modules describing packaging actions, or file types.  The
actions are dynamically discovered, so that new modules can be placed in this
package directory and they'll just be picked up.  The current package contents
can be seen in the section "PACKAGE CONTENTS", below.

This package has two data members:
  "types", a dictionary which maps the action names to the classes that
  represent them.

  "payload_types", a dictionary which maps action names that deliver payload
  to the classes that represent them.

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

# A dictionary of the action names in this package that deliver payload,
# according to the 'has_payload' member in each class. The dictionary is keyed
# by the action name, and has the action class as its values.
payload_types = {}

for modname in __all__:
        module = __import__("{0}.{1}".format(__name__, modname),
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
                if hasattr(cls, "name"):
                        types[cls.name] = cls
                if hasattr(cls, "has_payload") and cls.has_payload:
                        payload_types[cls.name] = cls

# Clean up after ourselves
del modname, module, nvlist, classes, cls


class ActionError(Exception):
        """Base exception class for Action errors."""

        def __str__(self):
                raise NotImplementedError()

class ActionRetry(ActionError):
        def __init__(self, *args):
                ActionError.__init__(self)
                self.actionstr = str(args[0])

        def __str__(self):
                return _("Need to try installing {action} again").format(
                    action=self.actionstr)

class UnknownActionError(ActionError):
        def __init__(self, *args):
                ActionError.__init__(self)
                self.actionstr = args[0]
                self.type = args[1]

        def __str__(self):
                if hasattr(self, "fmri") and self.fmri is not None:
                        return _("unknown action type '{type}' in package "
                            "'{fmri}' in action '{action}'").format(
                            type=self.type, fmri=self.fmri,
                            action=self.actionstr)
                return _("unknown action type '{type}' in action "
                    "'{action}'").format(type=self.type,
                    action=self.actionstr)

class MalformedActionError(ActionError):
        def __init__(self, *args):
                ActionError.__init__(self)
                self.actionstr = args[0]
                self.position = args[1]
                self.errorstr = args[2]

        def __str__(self):
                marker = " " * (4 + self.position) + "^"
                if hasattr(self, "fmri") and self.fmri is not None:
                        return _("Malformed action in package '{fmri}' at "
                            "position: {pos:d}: {error}:\n    {action}\n"
                            "{marker}").format(fmri=self.fmri,
                            pos=self.position, action=self.actionstr,
                            marker=marker, error=self.errorstr)
                return _("Malformed action at position: {pos:d}: {error}:\n    "
                    "{action}\n{marker}").format(pos=self.position,
                    action=self.actionstr, marker=marker,
                    error=self.errorstr)


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
                        return _("invalid action in package {fmri}: "
                            "{action}: {error}").format(fmri=self.fmri,
                            action=self.actionstr, error=self.errorstr)
                return _("invalid action, '{action}': {error}").format(
                        action=self.actionstr, error=self.errorstr)


class MissingKeyAttributeError(InvalidActionError):
        """Used to indicate that an action's key attribute is missing."""

        def __init__(self, *args):
                InvalidActionError.__init__(self, str(args[0]),
                    _("no value specified for key attribute '{0}'").format(
                    args[1]))


class KeyAttributeMultiValueError(InvalidActionError):
        """Used to indicate that an action's key attribute was specified
        multiple times for an action that expects it only once."""

        def __init__(self, *args):
                InvalidActionError.__init__(self, str(args[0]),
                    _("{0} attribute may only be specified once").format(
                    args[1]))


class InvalidPathAttributeError(InvalidActionError):
        """Used to indicate that an action's path attribute value was either
        empty, '/', or not a string."""

        def __init__(self, *args):
                InvalidActionError.__init__(self, str(args[0]),
                    _("Empty or invalid path attribute"))


class InvalidActionAttributesError(ActionError):
        """Used to indicate that one or more action attributes were invalid."""

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
                        return _("The action '{action}' in package "
                            "'{fmri}' has invalid attribute(s):\n"
                            "  {act_errors}").format(action=self.action,
                            fmri=self.fmri, act_errors=act_errors)
                return _("The action '{action}' has invalid attribute(s):\n"
                    "  {act_errors}").format(action=self.action,
                    act_errors=act_errors)


# This must be imported *after* all of the exception classes are defined as
# _actions module init needs the exception objects.
from ._actions import fromstr

def attrsfromstr(string):
        """Create an attribute dict given a string w/ key=value pairs.

        Raises MalformedActionError if the attributes have syntactic problems.
        """
        return fromstr("unknown {0}".format(string)).attrs

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
                raise UnknownActionError(("{0} {1}".format(atype,
                    " ".join(args))).strip(), atype)

        data = None

        if atype in ("file", "license"):
                data = args.pop(0)

        attrs = {}

        try:
                # list comprehension in Python 3 doesn't leak loop control
                # variable to surrounding variable, so use a regular loop
                for kv in args:
                        a, v = kv.split("=", 1)
                        if v == '' or a == '':
                                kvi = args.index(kv) + 1
                                p1 = " ".join(args[:kvi])
                                p2 = " ".join(args[kvi:])
                                raise MalformedActionError(
                                    "{0} {1} {2}".format(atype, p1, p2),
                                    len(p1) + 1,
                                    "attribute '{0}'".format(kv))

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
                raise MalformedActionError("{0} {1} {2}".format(atype, p1, p2),
                    len(p1) + 2, "attribute '{0}'".format(kv))

        # keys called 'data' cause problems due to the named parameter being
        # passed to the action constructor below. Check for these. Note that
        # _fromstr also checks for this.
        if "data" in attrs:
                astr = atype + " " + " ".join(args)
                raise InvalidActionError(astr,
                        "{0} action cannot have a 'data' attribute".format(
                        atype))

        action = types[atype](data, **attrs)
        if ahash:
                action.hash = ahash

        local_path, used_basedir = set_action_data(data, action,
            basedirs=basedirs)
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

        action = fromstr(string)

        if action.name not in ("file", "license") or not load_data:
                return action, None, None

        local_path, used_basedir = set_action_data(action.hash, action,
            basedirs=basedirs)
        return action, local_path, used_basedir

def set_action_data(payload, action, basedirs=None, bundles=None):
        """Sets the data field of an action using the information in the
        payload and returns the actual path used to set the data and the
        source used to find the data (this may be a path or a bundle
        object).

        The "payload" parameter is the representation of the data to assign to
        the action's data field. It can either be NOHASH or a path to the file.

        The "action" parameter is the action to modify.

        The "basedirs" parameter contains the directories to examine to find the
        payload in.

        The "bundles" parameter contains a list of bundle objects to find the
        payload in.

        "basedirs" and/or "bundles" must be specified.
        """

        if not payload:
                return None, None

        if payload == "NOHASH":
                try:
                        filepath = os.path.sep + action.attrs["path"]
                except KeyError:
                        raise InvalidPathAttributeError(action)
        else:
                filepath = payload

        if not basedirs:
                basedirs = []
        if not bundles:
                bundles = []

        # Attempt to find directory or bundle containing source of file data.
        data = None
        used_src = None
        path = filepath.lstrip(os.path.sep)
        for bd in basedirs:
                # look for file in specified dir
                npath = os.path.join(bd, path)
                if os.path.isfile(npath):
                        used_src = bd
                        data = npath
                        break
        else:
                for bundle in bundles:
                        act = bundle.get_action(path)
                        if act:
                                data = act.data
                                used_src = bundle
                                action.attrs["pkg.size"] = \
                                    act.attrs["pkg.size"]
                                break

                if not data and basedirs:
                        raise ActionDataError(_("Action payload '{name}' "
                            "was not found in any of the provided locations:"
                            "\n{basedirs}").format(name=filepath,
                            basedirs="\n".join(basedirs)), path=filepath)
                elif not data and bundles:
                        raise ActionDataError(_("Action payload '{name}' was "
                            "not found in any of the provided sources:"
                            "\n{sources}").format(name=filepath,
                            sources="\n".join(b.filename for b in bundles)),
                            path=filepath)
                elif not data:
                        # Only if no explicit sources were provided should a
                        # fallback to filepath be performed.
                        data = filepath

        # This relies on data having a value set by the code above so that an
        # ActionDataError will be raised if the file doesn't exist or is not
        # accessible.
        action.set_data(data)
        return data, used_src
