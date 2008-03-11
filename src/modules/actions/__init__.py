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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
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

def fromstr(str):
        """Create an action instance based on a str() representation of an action.

        Raises KeyError if the action type is unknown.
        """
        type, str = str.split(" ", 1)

        if type not in types:
                raise KeyError, "Action '%s'" % type

        # That is, if the first attribute is a hash
        if 0 < str.find(" ") < str.find("="):
                hash, str = str.split(" ", 1)
        else:
                hash = None

        # Split the string on spaces, then reconstruct and dequote quoted
        # values.
        list = str.split(" ")

        # Simple state machine to reconnect the elements that shouldn't have
        # been split.  Put the results into a new list since we can't modify the
        # list we're iterating over.
        state = 0
        count = 0
        nlist = []
        for i in list:
                if '="' in i:
                        start = count
                        n = i.replace('="', '=')
                        state = 1
                elif i.endswith('"'):
                        n += " " + i[:-1]
                        nlist += [ n ]
                        state = 0
                elif state == 1:
                        n += " " + i
                else:
                        nlist += [ i ]

                count += 1

        return fromlist(type, nlist, hash)

def fromlist(type, args, hash = None):
        """Create an action instance based on a sequence of "key=value" strings.

        Raises ValueError if the attribute strings are malformed.
        """
        # Create a list of key/value lists
        args = [kv.split("=", 1) for kv in args]
        # Find malformed actions (key or value missing)
        noeq = [e[0] for e in args if len(e) != 2]
        if noeq:
                raise ValueError(
                    "Malformed action string (missing '=') in key or value: " +
                    ", ".join(noeq))
        # Remove attribute duplication
        attrset = set(zip(*args)[0])
        # Put values belonging to the same attribute into individual lists
        vallist = [[j[1] for j in args if j[0] == i] for i in attrset]
        # Create a dict from the two lists
        attrs = dict(zip(attrset, vallist))

        # Convert any single-valued attributes to simple strings.
        # attrs = dict(
        #     [ (k, v) for k, v in attrs.iteritems() if len(v) > 1 ] +
        #     [ (k, v[0]) for k, v in attrs.iteritems() if len(v) == 1 ]
        # )
        for a in attrs:
                if len(attrs[a]) == 1:
                        attrs[a] = attrs[a][0]

        action = types[type](**attrs)
        if hash:
                action.hash = hash

        return action
