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
# Copyright (c) 2008, 2015, Oracle and/or its affiliates. All rights reserved.
#

from pylint.interfaces import IAstroidChecker
from pylint.checkers import BaseChecker
from logilab.common.modutils import get_module_part

class MultiPlatformAPIChecker(BaseChecker):
    """
    This class implements a pylint extension which checks for the use
    of APIs which are not portable across operating systems.

    This class is a "Visitor" class which defines methods that are called
    during the static parsing of python source code that is being checked.
    These callbacks are called when the parser is visiting or leaving certain
    python language constructs.  In this case, we are interested when
    a CallFunc language element is visited (indicating a function call), and
    the follow-on calls to the GetAttr language element, and the Name
    element.  These abstractions are used to denote items in the python
    language syntax, and are defined at

    http://docs.python.org/lib/module-compiler.ast.html

    The callbacks in this class keep track of the names involved in the
    parsing, and when a complete function call is formed, and the
    "leave" callback is called (see the leave_callfunc method below), the
    fully-qualified method call is checked against the list of non-portable
    APIs.  If an API is called which is in this list, a pylint error is
    reported.

    Care is taken to allow for import statements which may re-define the
    python library module names within an importing module.  For example,
    if there is an import such as "import os as foo", then a call to
    foo.symlink, this would not be caught with a traditional 'grep'-style
    checker.  This is caught using this class. """

    #
    # The list of APIs that are not available on all modern, supported
    # platforms.
    #
    VERBOTEN = [
        'getpass.getuser', 'os.chown', 'os.chroot', 'os.confstr',
        'os.confstr_names', 'os.ctermid', 'os.fchdir',
        'os.fdatasync', 'os.fork', 'os.forkpty', 'os.fpathconf',
        'os.fstatvfs', 'os.ftruncate', 'os.getegid', 'os.geteuid',
        'os.getgid', 'os.getgroups', 'os.getlogin', 'os.getpgid',
        'os.getpgrp', 'os.getppid', 'os.getsid', 'os.getuid',
        'os.isatty', 'os.kill', 'os.killpg', 'os.lchown', 'os.link',
        'os.linkmknod', 'os.lstat', 'os.major', 'os.makedev',
        'os.minor', 'os.mkfifo', 'os.nice', 'os.openpty',
        'os.pathconf', 'os.pathconf_names', 'os.plock',
        'os.readlink', 'os.setegid', 'os.seteuid', 'os.setgid',
        'os.setgroups', 'os.setpgid', 'os.setpgrp', 'os.setregid',
        'os.setreuid', 'os.setsid', 'os.setuid', 'os.spawnl',
        'os.spawnle', 'os.spawnlp', 'os.spawnlpe', 'os.spawnv',
        'os.spawnve', 'os.spawnvp', 'os.spawnvpe', 'os.startfile',
        'os.statvfs', 'os.symlink', 'os.sysconf',
        'os.sysconf_names', 'os.tcgetpgrp', 'os.tcsetpgrp',
        'os.ttyname', 'os.uname', 'os.wait3', 'os.wait4',
        'signal.alarm', 'signal.getsignal', 'signal.signal',
        'socket.fromfd', 'socket.inet_ntop', 'socket.inet_pton',
        'socket.socketpair', 'sys.getdlopenflags',
        'sys.getwindowsversion', 'sys.setdlopenflags',
        'thread.stack_size', 'time.tzset', 'fcntl.fcntl', 'fcntl.ioctl',
        'fcntl.flock', 'fcntl.lockf',
    ]
    
    # The list of package prefixes that are allowed to call VERBOTEN APIs
    ALLOWED = [
        'pkg.portable',
    ]

    #
    # Messages to show when checking detects an error
    #
    msgs = {
    'E0900': ('Imported Non-Portable API (%s)' ,
              'imported non-portable api',
              'Used when a non-portable API is imported.'),
    'E0901': ('Non-portable API used (%s)',
              'non-portable api',
              'Used when a non-portable API is called.'),
    }

    __implements__ = IAstroidChecker
    name = 'multiplatform'
    options = ()

    imported_modules={}
    calledfuncname=[]
    calledfuncstack=[]

    # this is important so that your checker is executed before others
    priority = -1 

    def leave_getattr(self, node):
        self.calledfuncname.append(node.attrname)

    def leave_name(self, node):
        self.calledfuncname=[node.name]

    def visit_callfunc(self, node):
        self.calledfuncstack.append(self.calledfuncname)
        self.calledfuncname=[]

    def leave_callfunc(self, node):
        self._check_verboten_call(node, self.calledfuncname)
        self.calledfuncname=self.calledfuncstack.pop()

    def visit_import(self, node):
        """triggered when an import statement is seen"""
        for name, alias in node.names:
            if alias == None:
                alias = name
            self._check_verboten_import(node, name)
            self.imported_modules.update({alias: name})

    def visit_from(self, node):
        """triggered when an import statement is seen"""
        basename = node.modname
        for name, alias in node.names:
            fullname = '{0}.{1}'.format(basename, name)
            self._check_verboten_import(node, fullname)
            if fullname.find('.') > -1:
                try:
                    fullname = get_module_part(fullname,
                                               context_file=node.root().file)
                except ImportError as ex:
                    # this is checked elsewhere in pylint (F0401)
                    continue
            if alias == None:
                alias = fullname         
            self.imported_modules.update({alias: fullname})

    def _is_allowed(self, node):
        for p in self.ALLOWED:
            if node.root().name.startswith(p):
                return True
        return False

    def _check_verboten_import(self, node, name):
        if self._is_allowed(node):
            return
        if name in self.VERBOTEN:
            self.add_message('E0900', args=(name), node=node)

    def _unalias(self, name):
        for i,e in enumerate(name):
            fullname = '.'.join(name[:i])
            if fullname in self.imported_modules:
                alias = self.imported_modules.get(fullname)
                return alias.split('.') +  name[i:]
        return name

    def _check_verboten_call(self,node, name):
        if self._is_allowed(node):
            return
        name = self._unalias(name)
        for i,e in enumerate(name):
            fullname = '.'.join(name[:i + 1])
            if fullname in self.VERBOTEN:
                self.add_message('E0901', args=(fullname), node=node)

def register(linter):
    """required method to auto register this checker"""
    linter.register_checker(MultiPlatformAPIChecker(linter))

