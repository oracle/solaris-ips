#!/usr/bin/python2.6
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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import getopt
import gettext
import os
import re
import shlex
import sys
import pkg.actions
from pkg.misc import PipeError


macros  = {}
includes = []
appends  = []
transforms = []
printinfo = []



def usage(errmsg="", exitcode=2):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if errmsg:
                print >> sys.stderr, "pkgmogrify: %s" % errmsg
        
        print _(
            "/usr/bin/pkgmogrify [-v] [-I includedir ...] [-D macro=value ...] "
            "[-O outputfile] [-P printfile] [inputfile ...]")
        sys.exit(exitcode)

def add_transform(transform, filename, lineno):
        """This routine adds a transform tuple to the list used
        to process actions."""

        # strip off transform
        s = transform[8:]
        # make error messages familiar
        transform = "<" + transform + ">"

        try:
                index = s.index("->")
        except ValueError:
                raise RuntimeError, _("Missing -> in transform")
        matching = s[0:index].strip().split()
        types = [a for a in matching if "=" not in a]
        attrdict = pkg.actions.attrsfromstr(" ".join([a for a in matching if "=" in a]))
        for a in attrdict:
                try:
                        attrdict[a] = re.compile(attrdict[a])
                except re.error, e:
                        raise RuntimeError, \
                            _("transform (%s) has regexp error (%s) in matching clause"
                            ) % (transform, e)

        op = s[index+2:].strip().split(" ", 1)

        # use closures to encapsulate desired operation

        if op[0] == "drop":
                if len(op) > 1:
                        raise RuntimeError, \
                            _("transform (%s) has 'drop' operation syntax error"
                            ) % transform
                operation = lambda a: None

        if op[0] == "set":
                try:
                        attr, value = shlex.split(op[1])
                except ValueError:
                        raise RuntimeError, \
                            _("transform (%s) has 'set' operation syntax error"
                            ) % transform
                def set_func(action):
                        action.attrs[attr] = value
                        return action
                operation = set_func

        if op[0] == "default":
                try:
                        attr, value = shlex.split(op[1])
                except ValueError:
                        raise RuntimeError, \
                            _("transform (%s) has 'default' operation syntax error"
                            ) % transform

                def default_func(action):
                        if attr not in action.attrs:
                                action.attrs[attr] = value
                        return action
                operation = default_func

        if op[0] == "abort":
            if len(op) > 1:
                raise RuntimeError, \
                    _("transform (%s) has 'abort' operation syntax error"
                    ) % transform
            def abort_func(action):
                sys.exit(0)
            operation = abort_func

        if op[0] == "add":
                try:
                        attr, value = shlex.split(op[1])
                except ValueError:
                        raise RuntimeError, \
                            _("transform (%s)has 'add' operation syntax error"
                            ) % transform

                def add_func(action):
                        if attr in action.attrs:
                                av = action.attrs[attr]
                                if isinstance(av, list):
                                        action.attrs[attr].append(value)
                                else:
                                        action.attrs[attr] = [ av, value ] 
                        else:
                                action.attrs[attr] = value
                        return action
                operation = add_func

        if op[0] == "edit":
                args = shlex.split(op[1])
                if len(args) not in [2, 3]:
                        raise RuntimeError, \
                            _("transform (%s) has 'edit' operation syntax error"
                            ) % transform
                attr = args[0]

                try:
                        regexp = re.compile(args[1])
                except re.error, e:
                        raise RuntimeError, \
                            _("transform (%s) has 'edit' operation with malformed" 
                              "regexp (%s)") % (transform, e)
                if len(args) == 3:
                        replace = args[2]
                else:
                        replace = ""

                def replace_func(action):
                        val = attrval_as_list(action.attrs, attr)
                        if not val:
                                return action
                        try:
                                action.attrs[attr] = [
                                        regexp.sub(replace, v)
                                        for v in val
                                        ]
                        except re.error, e:
                                raise RuntimeError, \
                                    _("transform (%s) has edit operation with replacement"
                                      "string regexp error %e") % (transform, e)
                        return action

                operation = replace_func

        if op[0] == "delete":
                args = shlex.split(op[1])
                if len(args) != 2:
                        raise RuntimeError, \
                            _("transform (%s) has 'delete' operation syntax error"
                            ) % transform
                attr = args[0]

                try:
                        regexp = re.compile(args[1])
                except re.error, e:
                        raise RuntimeError, \
                            _("transform (%s) has 'edit' operation with malformed" 
                            "regexp (%s)") % (transform, e)

                def delete_func(action):
                        val = attrval_as_list(action.attrs, attr)
                        if not val:
                                return action
                        try:
                                new_val = [
                                        v
                                        for v in val
                                        if not regexp.search(v)
                                        ]

                                if new_val:
                                        action.attrs[attr] = new_val
                                else:
                                        del action.attrs[attr]
                        except re.error, e:
                                raise RuntimeError, \
                                    _("transform (%s)has edit operation with replacement" 
                                      "string regexp error %e") % (transform, e)
                        return action

                operation = delete_func

        if op[0] == "print":
            if len(op) != 2:
                raise RuntimeError, \
                    _("transform (%s) has 'print' operation syntax error"
                    ) % transform
            msg = op[1]
            def print_func(action):
                printinfo.append("%s" % msg)
                return action
            operation = print_func

        transforms.append((types, attrdict, operation, filename, lineno, transform))

def attrval_as_list(attrdict, key):
        """Return specified attribute as list;
        an empty list if no such attribute exists"""
        if key not in attrdict:
                return []
        val = attrdict[key]
        if not isinstance(val, list):
                val = [val]
        return val

def apply_transforms(action, verbose):
        """Apply all transforms to action, returning modified action
        or None if action is dropped"""
        comments = []
        if verbose:
                comments.append("#  Action: %s" % action)
        for types, attrdict, operation, filename, lineno, transform in transforms:
                # skip if types are specified and none match
                if types and action.name not in types:
                        continue
                # skip if some attrs don't exist
                if set(attrdict.keys()) - set(action.attrs.keys()):
                        continue

                # check to make sure all matching attrs actually match
                if False in [
                        attrdict[key].match(attrval) != None
                        for key in attrdict
                        for attrval in attrval_as_list(action.attrs, key)
                       ]:
                        continue
                # time to apply transform operation
                try:
                        if verbose:
                                orig_attrs = action.attrs.copy()
                        action = operation(action)
                except RuntimeError, e:
                        raise RuntimeError, \
                            "Transform specified in file %s, line %s reports %s" % (
                            filename, lineno, e)
                if verbose:
                        if not action or orig_attrs != action.attrs:
                                comments.append("# Applied: %s (file %s line %s)" % (
                                    transform, filename, lineno))                                
                                comments.append("#  Result: %s" % action)
                if not action:
                        break

        if len(comments) == 1:
                comments = []
        
        return (comments, action)
                
                
def searching_open(filename, try_cwd=False):
        """ implement include hierarchy """

        if filename.startswith("/") or try_cwd == True and \
            os.path.exists(filename):
                try:
                        return filename, file(filename)            
                except IOError, e:
                        raise RuntimeError, _("Cannot open file: %s") % e

        for i in includes:
                f = os.path.join(i, filename)
                if os.path.exists(f):
                        try:
                                return f, file(f)
                        except IOError, e:
                                raise RuntimeError, _("Cannot open file: %s") % e

        raise RuntimeError, _("File not found: \'%s\'") % filename

def apply_macros(s):
        """Apply macro subs defined on command line... keep applying
        macros until no translations are found."""
        while s and "$(" in s:
                for key in macros.keys():
                        if key in s:
                                value = macros[key]
                                s = s.replace(key, value)
                                break # look for more substitutions
                else:
                        break # no more substitutable tokens
        return s

def read_file(tp):
        """ return the lines in the file as a list of 
        tuples containing (line, filename line number);
        handle continuation and <include "path">"""
        ret = []
        filename, f = tp

        accumulate = ""
        for lineno, line in enumerate(f):
                lineno = lineno + 1 # number from 1
                line = line.strip()
                if line.endswith("\\"):
                        accumulate += line[0:-1]
                        continue
                elif accumulate:
                        line = accumulate + line
                        accumulate = ""
                              
                if line:
                        line = apply_macros(line)

                line = line.strip()

                if not line or line[0] == '#':
                        continue

                try:
                        if line.startswith("<") and line.endswith(">"):
                                line = line[1:-1]
                                if line.startswith("include"):
                                        line = line[7:].strip()
                                        line = line.strip('"')
                                        ret.extend(read_file(searching_open(line)))
                                elif line.startswith("transform"):
                                        add_transform(line, filename, lineno)
                                else:
                                        raise RuntimeError, _("unknown command %s") % (
                                                line)
                        else:
                                ret.append((line, filename, lineno))             
                except RuntimeError, e:
                        error(_("File %s, line %d: %s" % (filename, lineno, e)), 
                            exitcode=None)
                        raise RuntimeError, "<included from>"
          
        return ret

def error(text, exitcode=1):
        """Emit an error message prefixed by the command name """

        print >> sys.stderr, "pkgmogrify: %s" % text

        if exitcode != None:
                sys.exit(exitcode)

def main_func():
        # /usr/lib/locale is OpenSolaris-specific.
        gettext.install("pkgmogrify", "/usr/lib/locale")

        outfilename = None
        printfilename = None
        verbose = False

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "vD:I:O:P:?", ["help"])
                for opt, arg in opts:
                        if opt == "-D":
                                if "=" not in arg:
                                        error(_("macros must be of form name=value"))
                                a = arg.split("=", 1)
                                if a[0] == "":
                                        error(_("macros must be of form name=value"))
                                macros.update([("$(%s)" % a[0], a[1])])
                        if opt == "-I":
                                includes.append(arg)
                        if opt == "-O":
                                outfilename = arg
                        if opt == "-P":
                                printfilename = arg
                        if opt == "-v":                                
                                verbose = True

                        if opt in ("--help", "-?"):
                                usage(exitcode=0)

        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)
                
        try:
                if pargs:
                        infiles = [ searching_open(f, try_cwd=True) for f in pargs ]
                else:
                        infiles =  [("<stdin>", sys.stdin)]

                lines = []
        except RuntimeError, e:
                error(_("Error processing input arguments: %s" % e))
        try:
                for f in infiles:
                        lines.extend(read_file(f))
        except RuntimeError, e:
                sys.exit(1)

        output = []

        for line, filename, lineno in lines:
                try:
                        act = pkg.actions.fromstr(line)
                except (pkg.actions.MalformedActionError,
                    pkg.actions.UnknownActionError,
                    pkg.actions.InvalidActionError), e:
                        error("File %s line %d: %s" % (filename, lineno, e))
                try:
                        a = apply_transforms(act, verbose)
                        output.append(a)

                except RuntimeError, e:
                        error("File %s line %d: %s" % (filename, lineno, e))

        try:
                if printfilename == None:
                        printfile = sys.stdout
                else:
                        printfile = file(printfilename, "w")

                for p in printinfo:
                    print >> printfile, "%s" % p
        except IOError, e:
                error(_("Cannot write extra data %s") % e)

        try:
                if outfilename == None:
                        outfile = sys.stdout
                else:
                        outfile = file(outfilename, "w")
                        
                for comment, action in output:
                        if comment:
                                for l in comment:
                                        print >> outfile, "%s" % l
                        if action:
                                print >> outfile, "%s" % action
        except IOError, e:
                error(_("Cannot write output %s") % e)
                
        return 0

if __name__ == "__main__":
        try:
                exit_code = main_func()        
        except (PipeError, KeyboardInterrupt):
                exit_code = 1
        except SystemExit, __e:
                exit_code = __e
        except Exception, __e: 
                print >> sys.stderr, "pkgmogrify: caught %s, %s" % (Exception, __e)
                exit_code = 99

        sys.exit(exit_code)
