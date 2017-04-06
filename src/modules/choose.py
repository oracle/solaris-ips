#!/usr/bin/python
# Copyright (c) 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008 Python Software
# Foundation; All Rights Reserved
#
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import fnmatch
import re

def choose(names, pat, case_sensitive):
        """Return the subset of names that match pat. case_sensitive determines
        whether the regexp is compiled to be case sensitive or not.
        """
        # Derived from fnmatch.filter
        result = []
        flag = 0
        # Setting the flag to re.I makes the regexp match using case
        # insensitive rules.
        if not case_sensitive:
                flag = re.I
        match = re.compile(fnmatch.translate(pat), flag).match
        for name in names:
                if match(name):
                        result.append(name)
        return result
