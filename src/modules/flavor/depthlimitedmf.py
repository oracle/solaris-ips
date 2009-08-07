# Copyright (c) 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009 Python
# Software Foundation; All Rights Reserved
#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.


"""A version of ModuleFinder which limits the depth of exploration for loaded
modules."""

import dis
import imp
import marshal
import modulefinder
import os
import sys

python_path = "PYTHONPATH"

class DepthLimitedModuleFinder(modulefinder.ModuleFinder):
        
        def __init__(self, proto_dir, *args, **kwargs):
                """Produce a module finder that ignores PYTHONPATH and only
                reports the direct imports of a module."""

                # Check to see whether a python path has been set.
                if python_path in os.environ:
                        py_path = [
                            os.path.normpath(fp)
                            for fp in os.environ[python_path].split(os.pathsep)
                        ]
                else:
                        py_path = []

                # Remove any paths that start with the defined python paths.
                new_path = [
                    fp
                    for fp in sys.path
                    if not self.__startswith_path(fp, py_path)
                ]

                root_path = new_path[:]

                # Map the standard system paths into the proto area.
                new_path = [
                    os.path.join(proto_dir, fp.lstrip("/"))
                    for fp in new_path
                ]

                # Extend new path so the proto area is searched first, then the
                # rest of the system.
                new_path.extend(root_path)
                # Pass the modified search path for modules to the contructor of
                # the parent class.
                modulefinder.ModuleFinder.__init__(self, path=new_path,
                    *args, **kwargs)
                self.proto_dir = proto_dir
                self.depth = None

        @staticmethod
        def __startswith_path(path, lst):
                for l in lst:
                        if path.startswith(l):
                                return True
                return False

        def run_script(self, pathname, depth=None):
                self.depth = depth
                modulefinder.ModuleFinder.run_script(self, pathname)

        def load_module(self, fqname, fp, pathname, (suffix, mode, type)):
                """This code has been slightly modified from the function of
                the parent class. Specifically, it checks the current depth
                of the loading and halts if it exceeds the depth that was given
                to run_script."""

                self.msgin(2, "load_module", fqname, fp and "fp", pathname)
                if type == imp.PKG_DIRECTORY:
                        m = self.load_package(fqname, pathname)
                        self.msgout(2, "load_module ->", m)
                        return m
                if type == imp.PY_SOURCE:
                        co = compile(fp.read()+'\n', pathname, 'exec')
                elif type == imp.PY_COMPILED:
                        if fp.read(4) != imp.get_magic():
                                self.msgout(2,
                                    "raise ImportError: Bad magic number",
                                    pathname)
                                raise ImportError, "Bad magic number in %s" % \
                                    pathname
                        fp.read(4)
                        co = marshal.load(fp)
                else:
                        co = None
                m = self.add_module(fqname)
                m.__file__ = pathname
                if co:
                        if self.replace_paths:
                                co = self.replace_paths_in_code(co)
                        m.__code__ = co
                        if self.depth is not None and self.depth > 0:
                                self.depth = self.depth - 1
                                self.scan_code(co, m)
                                self.depth = self.depth + 1
                        elif self.depth is None:
                                self.scan_code(co, m)
                self.msgout(2, "load_module ->", m)
                return m
