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

# Copyright (c) 2008, 2021, Oracle and/or its affiliates.

#
# Define the basic classes that all test cases are inherited from.
# The currently defined test case classes are:
#
# ApacheDepotTestCase
# CliTestCase
# ManyDepotTestCase
# Pkg5TestCase
# SingleDepotTestCase
# SingleDepotTestCaseCorruptImage
#

from __future__ import division
import baseline
import copy
import difflib
import errno
import gettext
import grp
import hashlib
import locale
import logging
import multiprocessing
import os
import pprint
import shutil
import signal
import rapidjson as json
import six
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import operator
import platform
import pty
import pwd
import re
import ssl
import textwrap
import threading
import traceback

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
if sys.version_info[:2] >= (3, 4):
        from importlib import reload
else:
        from imp import reload
from six.moves import configparser, http_client
from six.moves.urllib.error import HTTPError, URLError
from six.moves.urllib.parse import urljoin
from six.moves.urllib.request import urlopen
from socket import error as socketerror

import pkg.client.api_errors as apx
import pkg.misc as misc
import pkg.client.publisher as publisher
import pkg.portable as portable
import pkg.server.repository as sr

from pkg.client.debugvalues import DebugValues

EmptyI = tuple()
EmptyDict = dict()

#
# These are initialized by pkg5testenv.setup_environment.
#
g_proto_area = "TOXIC"
g_proto_readable = False
# Location of root of test suite.
g_test_dir = "TOXIC"
# User's value for TEMPDIR
g_tempdir = "/tmp"
# Location of path of pkg bits.
g_pkg_path = "TOXIC"

g_debug_output = False
if "DEBUG" in os.environ:
        g_debug_output = True

#
# XXX?
#
gettext.install("pkg", "/usr/share/locale")

OUTPUT_DOTS = 0         # Dots ...
OUTPUT_VERBOSE = 1      # Verbose
OUTPUT_PARSEABLE = 2    # Machine readable

class TestStopException(Exception):
        """An exception used to signal that all testing should cease.
        This is a framework-internal exception that tests should not
        raise"""
        pass

class TestSkippedException(Exception):
        """An exception used to signal that a test was skipped.
        Should be initialized with a string giving a more detailed
        reason.  Test cases can raise this to the framework
        that some prerequisite of the test is unsatisfied.  A string
        explaining the error should be passed at construction.  """
        def __str__(self):
                return "Test Skipped: " + " ".join(self.args)



#
# Errors for which the traceback is likely not useful.
#
import pkg.depotcontroller as depotcontroller
import pkg.portable as portable
import pkg.client.api
import pkg.client.progress

from pkg.client.debugvalues import DebugValues

# Version test suite is known to work with.
PKG_CLIENT_NAME = "pkg"
CLIENT_API_VERSION = 82

ELIDABLE_ERRORS = [ TestSkippedException, depotcontroller.DepotStateException ]

class Pkg5CommonException(AssertionError):
        def __init__(self, com = ""):
                Pkg5TestCase.failureException.__init__(self, com)

        topdivider = \
        ",---------------------------------------------------------------------\n"
        botdivider = \
        "`---------------------------------------------------------------------\n"
        def format_comment(self, comment):
                if comment is not None:
                        comment = comment.expandtabs()
                        comm = ""
                        for line in comment.splitlines():
                                line = line.strip()
                                if line == "":
                                        continue
                                comm += "  " + line + "\n"
                        return comm + "\n"
                else:
                        return "<no comment>\n\n"

        def format_output(self, command, output):
                str = "  Output Follows:\n"
                str += self.topdivider
                if command is not None:
                        str += "| $ " + command + "\n"

                if output is None or output == "":
                        str += "| <no output>\n"
                else:
                        for line in output.split("\n"):
                                str += "| " + line.rstrip() + "\n"
                str += self.botdivider
                return str

        def format_debug(self, output):
                str = "  Debug Buffer Follows:\n"
                str += self.topdivider

                if output is None or output == "":
                        str += "| <no debug buffer>\n"
                else:
                        for line in output.split("\n"):
                                str += "| " + line.rstrip() + "\n"
                str += self.botdivider
                return str


class AssFailException(Pkg5CommonException):
        def __init__(self, comment = None, debug=None):
                Pkg5CommonException.__init__(self, comment)
                self.__comment = comment
                self.__debug = debug

        def __str__(self):
                str = ""
                if self.__comment is None:
                        str += Exception.__str__(self)
                else:
                        str += self.format_comment(self.__comment)
                if self.__debug is not None and self.__debug != "":
                        str += self.format_debug(self.__debug)
                return str


class DebugLogHandler(logging.Handler):
        """This class is a special log handler to redirect logger output to
        the test case class' debug() method.
        """

        def __init__(self, test_case):
                self.test_case = test_case
                logging.Handler.__init__(self)

        def emit(self, record):
                self.test_case.debug(record)

def setup_logging(test_case):
        # Ensure logger messages output by unit tests are redirected
        # to debug output so they are not shown by default.
        from pkg.client import global_settings
        log_handler = DebugLogHandler(test_case)
        global_settings.info_log_handler = log_handler
        global_settings.error_log_handler = log_handler


class Pkg5TestCase(unittest.TestCase):

        # Needed for compatibility
        failureException = AssertionError

        #
        # Some dns servers return results for unknown dns names to redirect
        # callers to a common landing page.  To avoid getting tripped up by
        # these stupid servers make sure that bogus_url actually contains an
        # syntactically invalid dns name so we'll never succeed at the lookup.
        #
        bogus_url = "test.0.invalid"
        __debug_buf = ""

        smf_cmds = { \
            "usr/bin/svcprop" : """\
#!/usr/bin/python

import sys

if __name__ == "__main__":
        sys.exit(1)
"""}

        def __init__(self, methodName='runTest'):
                super(Pkg5TestCase, self).__init__(methodName)
                self.__test_root = None
                self.__pid = os.getpid()
                self.__pwd = os.getcwd()
                self.__didteardown = False
                self.__base_port = None
                self.coverage_cmd = ""
                self.coverage_env = {}
                self.next_free_port = None
                self.ident = None
                self.pkg_cmdpath = "TOXIC"
                self.debug_output = g_debug_output
                setup_logging(self)
                global g_proto_readable
                if not g_proto_readable:
                        self.assertProtoReadable()
                        g_proto_readable = True

                locale.setlocale(locale.LC_ALL, 'C')

        @property
        def methodName(self):
                return self._testMethodName

        @property
        def suite_name(self):
                return self.__suite_name

        def __str__(self):
                return "{0}.py {1}.{2}".format(self.__class__.__module__,
                    self.__class__.__name__, self._testMethodName)

        def __set_base_port(self, port):
                if self.__base_port is not None or \
                    self.next_free_port is not None:
                        raise RuntimeError("Setting the base port twice isn't "
                            "allowed")
                self.__base_port = port
                self.next_free_port = port

        base_port = property(lambda self: self.__base_port, __set_base_port)

        def assertProtoReadable(self):
                """Ensure proto area is readable by unprivileged user."""
                try:
                        self.cmdline_run("dir {0}".format(g_proto_area),
                            su_wrap=True)
                except:
                        raise TestStopException("proto area '{0} is not "
                            "readable by unprivileged user {1}".format(
                                g_proto_area, get_su_wrap_user()))

        def assertRegexp(self, text, regexp):
                """Test that a regexp search matches text."""

                if re.search(regexp, text):
                        return
                raise self.failureException(
                    "\"{0}\" does not match \"{1}\"".format(regexp, text))

        def assertRaisesRegexp(self, excClass, regexp,
            callableObj, *args, **kwargs):
                """Perform the same logic as assertRaises, but then verify
                that the stringified version of the exception contains the
                regexp pattern.

                Introduced in in python 2.7"""

                try:
                        callableObj(*args, **kwargs)

                except excClass as e:
                        if re.search(regexp, str(e)):
                                return
                        raise self.failureException(
                            "\"{0}\" does not match \"{1}\"".format(regexp, str(e)))

                raise self.failureException("{0} not raised".format(excClass))

        def assertRaisesStringify(self, excClass, callableObj, *args, **kwargs):
                """Perform the same logic as assertRaises, but then verify that
                the exception raised can be stringified."""

                try:
                        callableObj(*args, **kwargs)
                except excClass as e:
                        str(e)
                        return
                else:
                        raise self.failureException("{0} not raised".format(excClass))

        #
        # Uses property() to implements test_root as a read-only attribute.
        #
        test_root = property(fget=lambda self: self.__test_root)

        def __get_ro_data_root(self):
                if not self.__test_root:
                        return None
                return os.path.join(self.__test_root, "ro_data")

        ro_data_root = property(fget=__get_ro_data_root)

        def persistent_setup_copy(self, orig):
                pass

        @staticmethod
        def ptyPopen(args, executable=None, env=None, shell=False):
                """Less featureful but inspired by subprocess.Popen.
                Runs subprocess in a pty"""
                #
                # Note: In theory the right answer here is to subclass Popen,
                # but we found that in practice we'd have to reimplement most
                # of that class, because its handling of file descriptors is
                # too brittle in its _execute_child() code.
                #
                def __drain(masterf, outlist):
                        # Use a list as a way to pass by reference
                        while True:
                                chunksz = 1024
                                termdata = masterf.read(chunksz)
                                outlist.append(termdata)
                                if len(termdata) < chunksz:
                                        # assume we hit EOF
                                        break

                # This is the arg handling protocol from Popen
                if isinstance(args, six.string_types):
                        args = [args]
                else:
                        args = list(args)

                if shell:
                        args = ["/bin/sh", "-c"] + args
                        if executable:
                                args[0] = executable

                if executable is None:
                        executable = args[0]

                pid,fd = pty.fork()
                if pid == 0:
                        try:
                                # Child
                                if env is None:
                                        os.execvp(executable, args)
                                else:
                                        os.execvpe(executable, args, env)
                        except:
                                traceback.print_exc()
                                os._exit(99)
                else:
                        masterf = os.fdopen(fd, "rb")
                        outlist = []
                        t = threading.Thread(target=__drain,
                            args=(masterf, outlist))
                        t.start()
                        waitedpid, retcode = os.waitpid(pid, 0)
                        retcode = retcode >> 8
                        t.join()
                return retcode, b"".join(outlist)

        def cmdline_run(self, cmdline, comment="", coverage=True, exit=0,
            handle=False, out=False, prefix="", raise_error=True, su_wrap=None,
            stdin=None, stderr=False, env_arg=None, usepty=False):

                self.assertFalse(usepty and stdin,
                    "usepty not supported with stdin")

                # If caller provides arguments as a string, the shell must
                # process them.
                shell = not isinstance(cmdline, list)

                wrapper = ""
                if coverage:
                        wrapper = self.coverage_cmd
                su_wrap, su_end = self.get_su_wrapper(su_wrap=su_wrap,
                    shell=shell)

                if isinstance(cmdline, list):
                        if wrapper:
                                # Coverage command must be split into arguments.
                                wrapper = wrapper.split()
                                while wrapper:
                                        cmdline.insert(0, wrapper.pop())
                        if su_wrap:
                                # This ensures that all parts of the command
                                # line to be passed to 'su -c' are passed as a
                                # single argument.
                                while su_wrap[-1] != "-c":
                                        cmdline.insert(0, su_wrap.pop())
                                cmdline = [" ".join(cmdline)]
                                while su_wrap:
                                        cmdline.insert(0, su_wrap.pop())
                        if prefix:
                                cmdline.insert(0, prefix)
                else:
                        # Space needed between su_wrap and wrapper.
                        cmdline = "{0}{1} {2} {3}{4}".format(prefix, su_wrap, wrapper,
                            cmdline, su_end)

                self.debugcmd(cmdline)

                newenv = os.environ.copy()
                if coverage:
                        newenv.update(self.coverage_env)
                if env_arg:
                        newenv.update(env_arg)
                if not usepty:
                        p = subprocess.Popen(cmdline,
                            env=newenv,
                            shell=shell,
                            stdin=stdin,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)

                        if handle:
                                # Do nothing more.
                                return p

                        self.output, self.errout = p.communicate()
                        retcode = p.returncode
                else:
                        retcode, self.output = self.ptyPopen(cmdline,
                            env=newenv, shell=True)
                        self.errout = ""

                # In Python 3, subprocess returns bytes, while our pkg CLI
                # utilites' standard output and error streams return
                # str (unicode). To mimic the behavior of CLI, we force the
                # output to be str. This is a no-op in Python 2.
                encoding = "utf-8"
                # For testing encoding other than utf-8, we need to pass the
                # encoding to force_str.
                if newenv.get("LC_ALL", None) not in (None, "en_US.utf-8"):
                        # locale is a form of "x.y" and we ignore the C locale
                        index = newenv["LC_ALL"].find(".")
                        if index > -1:
                                encoding = newenv["LC_ALL"][index + 1:]
                self.output = misc.force_str(self.output, encoding)
                self.errout = misc.force_str(self.errout, encoding)
                self.debugresult(retcode, exit, self.output + self.errout)

                if raise_error and retcode == 99:
                        raise TracebackException(cmdline, self.output +
                            self.errout, comment)

                if not isinstance(exit, list):
                        exit = [exit]

                if raise_error and retcode not in exit:
                        raise UnexpectedExitCodeException(cmdline,
                            exit, retcode, self.output + self.errout,
                            comment)

                if out:
                        if stderr:
                                return retcode, self.output, self.errout
                        return retcode, self.output
                return retcode

        def debug(self, s):
                s = str(s)
                for x in s.splitlines():
                        if self.debug_output:
                                print("# {0}".format(x), file=sys.stderr)
                        self.__debug_buf += x + "\n"

        def debugcmd(self, cmdline):
                wrapper = textwrap.TextWrapper(initial_indent="$ ",
                    subsequent_indent="\t",
                    break_long_words=False,
                    break_on_hyphens=False)
                if isinstance(cmdline, list):
                        res = wrapper.wrap(" ".join(cmdline).strip())
                else:
                        res = wrapper.wrap(cmdline.strip())
                self.debug(" \\\n".join(res))

        def debugfilecreate(self, content, path):
                lines = content.splitlines()
                if lines == []:
                        lines = [""]
                if len(lines) > 1:
                        ins = " [+{0:d} lines...]".format(len(lines) - 1)
                else:
                        ins = ""
                if isinstance(lines[0], six.text_type):
                        lines[0] = lines[0].encode("utf-8")
                self.debugcmd(
                    "echo '{0}{1}' > {2}".format(lines[0], ins, path))

        def debugresult(self, retcode, expected, output):
                if output.strip() != "":
                        self.debug(output.strip())
                if not isinstance(expected, list):
                        expected = [expected]
                if retcode is None or retcode != 0 or \
                    retcode not in expected:
                        self.debug("[exited {0}, expected {1}]".format(
                            retcode, ", ".join(str(e) for e in expected)))

        def get_debugbuf(self):
                return self.__debug_buf

        def set_debugbuf(self, s):
                self.__debug_buf = s

        def get_su_wrapper(self, su_wrap=None, shell=True):
                """If 'shell' is True, the wrapper will be returned as a tuple of
                strings of the form (su_wrap, su_end).  If 'shell' is False, the
                wrapper willbe returned as a tuple of (args, ignore) where
                'args' is a list of the commands and their arguments that should
                come before the command being executed."""

                if not su_wrap:
                        return "", ""

                if su_wrap == True:
                        su_user = get_su_wrap_user()
                else:
                        su_user = ""

                cov_env = [
                    "{0}={1}".format(*e)
                    for e in self.coverage_env.items()
                ]

                su_wrap = ["su"]

                if su_user:
                        su_wrap.append(su_user)

                if shell:
                        su_wrap.append("-c 'env LD_LIBRARY_PATH={0}".format(
                            os.getenv("LD_LIBRARY_PATH", "")))
                else:
                        # If this ever changes, cmdline_run must be updated.
                        su_wrap.append("-c")
                        su_wrap.append("env")
                        su_wrap.append("LD_LIBRARY_PATH={0}".format(
                            os.getenv("LD_LIBRARY_PATH", "")))

                su_wrap.extend(cov_env)

                if shell:
                        su_wrap = " ".join(su_wrap)
                        su_end = "'"
                else:
                        su_end = ""

                return su_wrap, su_end

        def getTeardownFunc(self):
                return (self, self.tearDown)

        def getSetupFunc(self):
                return (self, self.setUp)

        def setUp(self):
                assert self.ident is not None
                self.__test_root = os.path.join(g_tempdir,
                    "ips.test.{0:d}".format(self.__pid), "{0:d}".format(self.ident))
                self.__didtearDown = False
                try:
                        os.makedirs(self.__test_root, 0o755)
                except OSError as e:
                        if e.errno != errno.EEXIST:
                                raise e
                if getattr(self, "need_ro_data", False):
                        shutil.copytree(os.path.join(g_test_dir, "ro_data"),
                            self.ro_data_root)
                        self.path_to_certs = os.path.join(self.ro_data_root,
                            "signing_certs", "produced")
                        self.keys_dir = os.path.join(self.path_to_certs, "keys")
                        self.cs_dir = os.path.join(self.path_to_certs,
                            "code_signing_certs")
                        self.chain_certs_dir = os.path.join(self.path_to_certs,
                            "chain_certs")
                        self.raw_trust_anchor_dir = os.path.join(
                            self.path_to_certs, "trust_anchors")
                        self.crl_dir = os.path.join(self.path_to_certs, "crl")

                #
                # TMPDIR affects the behavior of mkdtemp and mkstemp.
                # Setting this here should ensure that tests will make temp
                # files and dirs inside the test directory rather than
                # polluting /tmp.
                #
                os.environ["TMPDIR"] = self.__test_root
                tempfile.tempdir = self.__test_root
                setup_logging(self)

                # Create a pkglintrc file that points to our info.classification
                # data, and doesn't exclude any shipped plugins.
                self.configure_rcfile(os.path.join(g_pkg_path,
                    "usr/share/lib/pkg/pkglintrc"),
                    {"info_classification_path":
                    os.path.join(g_pkg_path,
                    "usr/share/lib/pkg/opensolaris.org.sections"),
                    "pkglint.exclude": ""}, self.test_root, section="pkglint")

                self.sysrepo_template_dir = os.path.join(g_pkg_path,
                    "etc/pkg/sysrepo")
                self.depot_template_dir = os.path.join(g_pkg_path,
                    "etc/pkg/depot")
                self.make_misc_files(self.smf_cmds, prefix="smf_cmds",
                    mode=0o755)
                DebugValues["smf_cmds_dir"] = \
                    os.path.join(self.test_root, "smf_cmds")

        def impl_tearDown(self):
                # impl_tearDown exists so that we can ensure that this class's
                # teardown is actually called.  Sometimes, subclasses will
                # implement teardown but forget to call the superclass teardown.
                if self.__didteardown:
                        return
                self.__didteardown = True
                try:
                        os.chdir(self.__pwd)
                except OSError:
                        # working directory of last resort.
                        os.chdir(g_tempdir)

                #
                # Kill depots before blowing away test dir-- otherwise
                # the depot can race with the shutil.rmtree()
                #
                if hasattr(self, "killalldepots"):
                        try:
                                self.killalldepots()
                        except Exception as e:
                                print(str(e), file=sys.stderr)

                #
                # We have some sloppy subclasses which don't call the superclass
                # setUp-- in which case the dir might not exist.  Tolerate it.
                #
                # Also, avoid deleting our fakeroot since then we'd have to
                # keep re-creating it.
                #
                if self.__test_root is not None and \
                    os.path.exists(self.__test_root):
                        for d in os.listdir(self.__test_root):
                                path = os.path.join(self.__test_root, d)
                                self.debug("removing: {0}".format(path))
                                try:
                                        os.remove(path)
                                except OSError as e:
                                        if e.errno == errno.EPERM:
                                                shutil.rmtree(path)
                                        else:
                                                raise

        def tearDown(self):
                # In reality this call does nothing.
                unittest.TestCase.tearDown(self)

                self.impl_tearDown()

        def run(self, result=None):
                assert self.base_port is not None
                if result is None:
                        result = self.defaultTestResult()
                pwd = os.getcwd()
                result.startTest(self)
                testMethod = getattr(self, self._testMethodName)
                if getattr(result, "coverage", None) is not None:
                        self.coverage_cmd, self.coverage_env = result.coverage
                try:
                        needtodie = False
                        try:
                                self.setUp()
                        except KeyboardInterrupt:
                                # Try hard to make sure we've done a teardown.
                                try:
                                        self.tearDown()
                                except:
                                        pass
                                self.impl_tearDown()
                                raise TestStopException
                        except:
                                # teardown could fail too, esp. if setup failed...
                                try:
                                        self.tearDown()
                                except:
                                        pass
                                # Try hard to make sure we've done a teardown.
                                self.impl_tearDown()
                                result.addError(self, sys.exc_info())
                                return

                        ok = False
                        error_added = False
                        try:
                                testMethod()
                                ok = True
                        except self.failureException:
                                result.addFailure(self, sys.exc_info())
                        except KeyboardInterrupt:
                                # Try hard to make sure we've done a teardown.
                                needtodie = True
                        except TestSkippedException as err:
                                result.addSkip(self, err)
                        except:
                                error_added = True
                                result.addError(self, sys.exc_info())

                        try:
                                self.tearDown()
                        except KeyboardInterrupt:
                                needtodie = True
                        except:
                                # Try hard to make sure we've done a teardown.
                                self.impl_tearDown()
                                # Make sure we don't mark this error'd twice.
                                if not error_added:
                                        result.addError(self, sys.exc_info())
                                ok = False

                        if needtodie:
                                try:
                                        self.impl_tearDown()
                                except:
                                        pass
                                raise TestStopException

                        if ok:
                                result.addSuccess(self)
                finally:
                        result.stopTest(self)
                        # make sure we restore our directory if it still exists.
                        try:
                                os.chdir(pwd)
                        except OSError as e:
                                # If directory doesn't exist anymore it doesn't
                                # matter.
                                if e.errno != errno.ENOENT:
                                        raise

        #
        # The following are utility functions for use by testcases.
        #
        def c_compile(self, prog_text, opts, outputfile, obj_files=None):
                """Given a C program (as a string), compile it into the
                executable given by outputfile.  Outputfile should be
                given as a relative path, and will be located below the
                test prefix path.  Additional compiler options should be
                passed in 'opts'.  Suitable for compiling small test
                programs."""

                #
                # We use a series of likely compilers.  At present we support
                # this testing with SunStudio.
                #
                assert obj_files is not None or prog_text is not None
                assert obj_files is None or prog_text is None
                if os.path.dirname(outputfile) != "":
                        try:
                                os.makedirs(os.path.dirname(outputfile))
                        except OSError as e:
                                if e.errno != errno.EEXIST:
                                        raise
                if prog_text:
                        c_fd, c_path = tempfile.mkstemp(suffix=".c",
                            dir=self.test_root)
                        c_fh = os.fdopen(c_fd, "w")
                        c_fh.write(prog_text)
                        c_fh.close()
                else:
                        c_path = " ".join(obj_files)

                found = False
                outpath = os.path.join(self.test_root, outputfile)
                compilers = ["/usr/bin/cc", "cc", "$CC"]
                for compiler in compilers:
                        cmd = [compiler, "-o", outpath]
                        cmd.extend(opts)
                        cmd.append(c_path)
                        try:
                                # Make sure to use shell=True so that env.
                                # vars and $PATH are evaluated.
                                self.debugcmd(" ".join(cmd))
                                s = subprocess.Popen(" ".join(cmd),
                                    shell=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
                                sout, serr = s.communicate()
                                rc = s.returncode
                                if rc != 0 and rc != 127:
                                        try: os.remove(outpath)
                                        except OSError: pass
                                        try: os.remove(c_path)
                                        except OSError: pass
                                        raise RuntimeError(
                                            "Compile failed: {0} --> {1:d}\n{2}".format(
                                            cmd, rc, sout))
                                if rc == 127:
                                        self.debug("[{0} not found]".format(compiler))
                                        continue
                                # so rc == 0
                                found = True
                                break
                        except OSError:
                                continue
                try:
                        os.remove(c_path)
                except OSError:
                        pass
                if not found:
                        raise TestSkippedException(
                            "No suitable Sun Studio compiler found. "
                            "Tried: {0}.  Try setting $CC to a valid"
                            "compiler.".format(compilers))

        def make_file(self, path, content, mode=0o644, copy=False):
                if not os.path.exists(os.path.dirname(path)):
                        os.makedirs(os.path.dirname(path), 0o777)
                self.debugfilecreate(content, path)
                if six.PY2:
                        if isinstance(content, six.text_type):
                                content = content.encode("utf-8")
                        with open(path, "wb") as fh:
                                fh.write(content)
                else:
                        if copy:
                            shutil.copy(content, path)
                        else:
                            with open(path, "w", encoding="utf-8") as fh:
                                fh.write(content)
                os.chmod(path, mode)

        def make_misc_files(self, files, prefix=None, mode=0o644,
                            copy=False):
                """ Make miscellaneous text files.  Files can be a
                single relative pathname, a list of relative pathnames,
                or a hash mapping relative pathnames to specific contents.
                If file contents are not specified, the pathname of the
                file is placed into the file as default content. """

                outpaths = []
                #
                # If files is a string, make it a list.  Then, if it is
                # a list, simply turn it into a dict where each file's
                # contents is its own name, so that we get some uniqueness.
                #
                if isinstance(files, six.string_types):
                        files = [files]

                if isinstance(files, list):
                        nfiles = {}
                        for f in files:
                                nfiles[f] = f
                        files = nfiles

                if prefix is None:
                        prefix = self.test_root
                else:
                        assert(not prefix.startswith(os.pathsep))
                        prefix = os.path.join(self.test_root, prefix)

                # Ensure output paths are returned in consistent order.
                for f in sorted(files):
                        content = files[f]
                        assert not f.startswith("/"), \
                            ("{0}: misc file paths must be relative!".format(f))
                        path = os.path.join(prefix, f)
                        self.make_file(path, content, mode, copy)
                        outpaths.append(path)
                return outpaths

        def make_manifest(self, content, manifest_dir="manifests", pfmri=None):
                # Trim to ensure nice looking output.
                content = content.strip()

                # Place inside of test prefix.
                manifest_dir = os.path.join(self.test_root,
                    manifest_dir)

                if not os.path.exists(manifest_dir):
                        os.makedirs(manifest_dir)
                t_fd, t_path = tempfile.mkstemp(prefix="mfst.",
                    dir=manifest_dir)
                t_fh = os.fdopen(t_fd, "w")
                if pfmri:
                        t_fh.write("set name=pkg.fmri value={0}\n".format(pfmri))
                t_fh.write(content)
                t_fh.close()
                self.debugfilecreate(content, t_path)
                return t_path

        @staticmethod
        def calc_pem_hash(pth):
                """Find the hash of pem representation the file."""
                with open(pth, "rb") as f:
                        cert = x509.load_pem_x509_certificate(
                            f.read(), default_backend())
                return hashlib.sha1(
                    cert.public_bytes(serialization.Encoding.PEM)).hexdigest()

        def reduceSpaces(self, string):
                """Reduce runs of spaces down to a single space."""
                return re.sub(" +", " ", string)

        def assertEqualJSON(self, expected, actual, msg=""):
                """Compare two JSON-encoded strings."""
                je = json.loads(expected)
                ja = json.loads(actual)
                try:
                        misc.json_diff("test", je, ja, je, ja)
                except AssertionError as e:
                        if msg:
                                msg += "\n"
                        self.fail(msg + str(e))

        def assertEqualDiff(self, expected, actual, bound_white_space=False,
            msg=""):
                """Compare two strings."""

                if not isinstance(expected, six.string_types):
                        expected = pprint.pformat(expected)
                if not isinstance(actual, six.string_types):
                        actual = pprint.pformat(actual)

                expected_lines = expected.splitlines()
                actual_lines = actual.splitlines()
                if bound_white_space:
                        expected_lines = ["'{0}'".format(l) for l in expected_lines]
                        actual_lines = ["'{0}'".format(l) for l in actual_lines]
                if msg:
                        msg += "\n"
                self.assertEqual(expected, actual, msg +
                    "Actual output differed from expected output\n" + msg +
                    "\n".join(difflib.unified_diff(expected_lines, actual_lines,
                        "Expected output", "Actual output", lineterm="")))

        def __compare_child_images(self, ev, ov):
                """A helper function used to match child images with their
                expected values so that they can be checked."""

                enames = [d["image_name"] for d in ev]
                onames = [d["image-name"] for d in ov]
                if sorted(enames) != sorted(onames):
                        raise RuntimeError("Got a different set of image names "
                            "than was expected.\nExpected:\n{0}\nSeen:\n{1}".format(
                            " ".join(enames), " ".join(onames)))
                for ed in ev:
                        for od in ov:
                                if ed["image_name"] == od["image-name"]:
                                        self.assertEqualParsable(od, **ed)
                                        break

        def assertEqualParsable(self, output, activate_be=True,
            add_packages=EmptyI, affect_packages=EmptyI, affect_services=EmptyI,
            backup_be_name=None, be_name=None, boot_archive_rebuild=False,
            change_editables=EmptyI, change_facets=EmptyI,
            change_packages=EmptyI, change_mediators=EmptyI,
            change_variants=EmptyI, child_images=EmptyI, create_backup_be=False,
            create_new_be=False, image_name=None, licenses=EmptyI,
            remove_packages=EmptyI, release_notes=EmptyI, include=EmptyI,
            version=0):
                """Check that the parsable output in 'output' is what is
                expected."""

                if isinstance(output, six.string_types):
                        try:
                                outd = json.loads(output)
                        except Exception as e:
                                raise RuntimeError("JSON couldn't parse the "
                                    "output.\nError was: {0}\nOutput was:\n{1}".format(
                                    e, output))
                else:
                        self.assertTrue(isinstance(output, dict))
                        outd = output
                expected = locals()
                # It's difficult to check that space-available is correct in the
                # test suite.
                self.assertTrue("space-available" in outd)
                del outd["space-available"]
                # While we could check for space-required, it just means lots of
                # tests would need to be changed if we ever changed our size
                # measurement and other tests should be ensuring that the number
                # is correct.
                self.assertTrue("space-required" in outd)
                del outd["space-required"]
                # Do not check item-messages, since it will be checked
                # somewhere else.
                self.assertTrue("item-messages" in outd)
                del outd["item-messages"]
                # Add 4 to account for self, output, include, and outd.
                self.assertEqual(len(expected), len(outd) + 4, "Got a "
                    "different set of keys for expected and outd.  Those in "
                    "expected but not in outd:\n{0}\nThose in outd but not in "
                    "expected:\n{1}".format(
                        sorted(set([k.replace("_", "-") for k in expected]) -
                        set(outd)),
                        sorted(set(outd) -
                        set([k.replace("_", "-") for k in expected]))))

                seen = set()
                for k in sorted(outd):
                        seen.add(k)
                        if include and k not in include:
                                continue

                        ek = k.replace("-", "_")
                        ev = expected[ek]
                        if ev == EmptyI:
                                ev = []
                        if ek == "child_images" and ev != []:
                                self.__compare_child_images(ev, outd[k])
                                continue
                        self.assertEqual(ev, outd[k], "In image {0}, the value "
                            "of {1} was expected to be\n{2} but was\n{3}".format(
                            image_name, k, ev, outd[k]))

                if include:
                        # Assert all sections expicitly requested were matched.
                        self.assertEqualDiff(include, list(x for x in (seen &
                            set(include))))

        def configure_rcfile(self, rcfile, config, test_root, section="DEFAULT",
            suffix=""):
                """Reads the provided rcfile file, setting key/value
                pairs in the provided section those from the 'config'
                dictionary. The new config file is written to the supplied
                test_root, returning the name of that new file.

                Used to set keys to point to paths beneath our test_root,
                which would otherwise be shipped as hard-coded paths, relative
                to /.
                """

                with open("{0}/{1}{2}".format(test_root, os.path.basename(rcfile),
                    suffix), "w") as new_rcfile:

                        conf = configparser.RawConfigParser()
                        with open(rcfile) as f:
                                if six.PY2:
                                        conf.readfp(f)
                                else:
                                        conf.read_file(f)

                        for key in config:
                                conf.set(section, key, config[key])

                        conf.write(new_rcfile)
                        return new_rcfile.name


class _OverTheWireResults(object):
        """Class for passing test results between processes."""

        separator1 = '=' * 70
        separator2 = '-' * 70

        list_attrs = ["baseline_failures", "errors", "failures", "skips",
            "timing"]
        num_attrs = ["mismatches", "num_successes", "testsRun"]

        def __init__(self, res):
                self.errors = [(str(test), err) for  test, err in res.errors]
                self.failures = [(str(test), err) for test, err in res.failures]
                self.mismatches = len(res.mismatches)
                self.num_successes = len(res.success)
                self.skips = res.skips
                self.testsRun = res.testsRun
                self.timing = []
                self.text = ""
                self.baseline_failures = []
                self.debug_buf = ""

        def wasSuccessful(self):
                return self.mismatches == 0

        def wasSkipped(self):
                return len(self.skips) != 0

        def printErrors(self):
                self.stream.write("\n")
                self.printErrorList('ERROR', self.errors)
                self.printErrorList('FAIL', self.failures)

        def printErrorList(self, flavour, errors):
                for test, err in errors:
                        self.stream.write(self.separator1 + "\n")
                        self.stream.write("{0}: {1}\n".format(
                            flavour, test))
                        self.stream.write(self.separator2 + "\n")
                        self.stream.write("{0}\n".format(err))


class _CombinedResult(_OverTheWireResults):
        """Class for combining test results from different test cases."""

        def __init__(self):
                for l in self.list_attrs:
                        setattr(self, l, [])
                for n in self.num_attrs:
                        setattr(self, n, 0)

        def combine(self, o):
                for l in self.list_attrs:
                        v = getattr(self, l)
                        v.extend(getattr(o, l))
                        setattr(self, l, v)
                for n in self.num_attrs:
                        v = getattr(self, n)
                        v += getattr(o, n)
                        setattr(self, n, v)


class _Pkg5TestResult(unittest._TextTestResult):
        baseline = None
        machsep = "|"

        def __init__(self, stream, output, baseline, bailonfail=False,
            show_on_expected_fail=False, archive_dir=None):
                unittest.TestResult.__init__(self)
                self.stream = stream
                self.output = output
                self.baseline = baseline
                self.success = []
                self.mismatches = []
                self.bailonfail = bailonfail
                self.show_on_expected_fail = show_on_expected_fail
                self.archive_dir = archive_dir
                self.skips = []

        def collapse(self):
                return _OverTheWireResults(self)

        def getDescription(self, test):
                return str(test)

        # Override the unittest version of this so that success is
        # considered "matching the baseline"
        def wasSuccessful(self):
                return len(self.mismatches) == 0

        def wasSkipped(self):
                return len(self.skips) != 0

        def dobailout(self, test):
                """ Pull the ejection lever.  Stop execution, doing as
                much forcible cleanup as possible. """
                inst, tdf = test.getTeardownFunc()
                try:
                        tdf()
                except Exception as e:
                        print(str(e), file=sys.stderr)
                        pass

                if getattr(test, "persistent_setup", None):
                        try:
                                test.reallytearDown()
                        except Exception as e:
                                print(str(e), file=sys.stderr)
                                pass

                if hasattr(inst, "killalldepots"):
                        try:
                                inst.killalldepots()
                        except Exception as e:
                                print(str(e), file=sys.stderr)
                                pass
                raise TestStopException()

        def fmt_parseable(self, match, actual, expected):
                if match == baseline.BASELINE_MATCH:
                        mstr = "MATCH"
                else:
                        mstr = "MISMATCH"
                return "{0}|{1}|{2}".format(mstr, actual, expected)


        @staticmethod
        def fmt_prefix_with(instr, prefix):
                res = ""
                for s in instr.splitlines():
                        res += "{0}{1}\n".format(prefix, s)
                return res

        @staticmethod
        def fmt_box(instr, title, prefix=""):
                trailingdashes = (50 - len(title)) * "-"
                res = "\n.---" + title + trailingdashes + "\n"
                for s in instr.splitlines():
                        if s.strip() == "":
                                continue
                        res += "| {0}\n".format(s)
                res += "`---" + len(title) * "-" + trailingdashes
                return _Pkg5TestResult.fmt_prefix_with(res, prefix)

        def do_archive(self, test, info):
                assert self.archive_dir
                if not os.path.exists(self.archive_dir):
                        os.makedirs(self.archive_dir, mode=0o755)

                archive_path = os.path.join(self.archive_dir,
                    "{0:d}".format(os.getpid()))
                if not os.path.exists(archive_path):
                        os.makedirs(archive_path, mode=0o755)
                archive_path = os.path.join(archive_path, test.id())
                if test.debug_output:
                        self.stream.write("# Archiving to {0}\n".format(archive_path))

                if os.path.exists(test.test_root):
                        try:
                                misc.copytree(test.test_root, archive_path)
                        except socketerror as e:
                                pass
                else:
                        # If the test has failed without creating its directory,
                        # make it manually, so that we have a place to write out
                        # ERROR_INFO.
                        os.makedirs(archive_path, mode=0o755)

                f = open(os.path.join(archive_path, "ERROR_INFO"), "w")
                f.write("------------------DEBUG LOG---------------\n")
                f.write(test.get_debugbuf())
                if info is not None:
                        f.write("\n\n------------------EXCEPTION---------------\n")
                        f.write(info)
                f.close()

        def addSuccess(self, test):
                unittest.TestResult.addSuccess(self, test)

                # If we're debugging, we'll have had output since we
                # announced the name of the test, so restate it.
                if test.debug_output:
                        self.statename(test)

                errinfo = self.format_output_and_exc(test, None)

                bresult = self.baseline.handleresult(str(test), "pass")
                expected = self.baseline.expectedresult(str(test))
                if self.output == OUTPUT_PARSEABLE:
                        res = self.fmt_parseable(bresult, "pass", expected)

                elif self.output == OUTPUT_VERBOSE:
                        if bresult == baseline.BASELINE_MATCH:
                                res = "match pass"
                        else:
                                res = "MISMATCH pass (expected: {0})".format(
                                    expected)
                                res = self.fmt_box(errinfo,
                                    "Successful Test", "# ")
                else:
                        assert self.output == OUTPUT_DOTS
                        res = "."

                if self.output != OUTPUT_DOTS:
                        self.stream.write(res + "\n")
                else:
                        self.stream.write(res)
                self.success.append(test)

                if bresult == baseline.BASELINE_MISMATCH:
                        self.mismatches.append(test)

                if bresult == baseline.BASELINE_MISMATCH and self.archive_dir:
                        self.do_archive(test, None)

                # Bail out completely if the 'bail on fail' flag is set
                # but iff the result disagrees with the baseline.
                if self.bailonfail and bresult == baseline.BASELINE_MISMATCH:
                        self.dobailout(test)


        def addError(self, test, err):
                errtype, errval = err[:2]
                # for a few special exceptions, we delete the traceback so
                # as to elide it.  use only when the traceback itself
                # is not likely to be useful.
                if errtype in ELIDABLE_ERRORS:
                        unittest.TestResult.addError(self, test,
                            (err[0], err[1], None))
                else:
                        unittest.TestResult.addError(self, test, err)

                # If we're debugging, we'll have had output since we
                # announced the name of the test, so restate it.
                if test.debug_output:
                        self.statename(test)

                errinfo = self.format_output_and_exc(test, err)

                bresult = self.baseline.handleresult(str(test), "error")
                expected = self.baseline.expectedresult(str(test))
                if self.output == OUTPUT_PARSEABLE:
                        if errtype in ELIDABLE_ERRORS:
                                res = self.fmt_parseable(bresult, "ERROR", expected)
                                res += "\n# {0}\n".format(str(errval).strip())
                        else:
                                res = self.fmt_parseable(bresult, "ERROR", expected)
                                res += "\n"
                                if bresult == baseline.BASELINE_MISMATCH \
                                   or self.show_on_expected_fail:
                                        res += self.fmt_prefix_with(errinfo, "# ")

                elif self.output == OUTPUT_VERBOSE:
                        if bresult == baseline.BASELINE_MATCH:
                                b = "match"
                        else:
                                b = "MISMATCH"

                        if errtype in ELIDABLE_ERRORS:
                                res = "{0} ERROR\n".format(b)
                                res += "#\t{0}".format(str(errval))
                        else:
                                res = "{0} ERROR\n".format(b)
                                if bresult == baseline.BASELINE_MISMATCH \
                                   or self.show_on_expected_fail:
                                        res += self.fmt_box(errinfo,
                                            "Error Information", "# ")

                elif self.output == OUTPUT_DOTS:
                        if bresult == baseline.BASELINE_MATCH:
                                res = "e"
                        else:
                                res = "E"

                if self.output == OUTPUT_DOTS:
                        self.stream.write(res)
                else:
                        self.stream.write(res + "\n")

                if bresult == baseline.BASELINE_MISMATCH:
                        self.mismatches.append(test)

                # Check to see if we should archive this baseline mismatch.
                if bresult == baseline.BASELINE_MISMATCH and self.archive_dir:
                        self.do_archive(test, self._exc_info_to_string(err, test))

                # Bail out completely if the 'bail on fail' flag is set
                # but iff the result disagrees with the baseline.
                if self.bailonfail and bresult == baseline.BASELINE_MISMATCH:
                        self.dobailout(test)

        def format_output_and_exc(self, test, error):
                res = ""
                dbgbuf = test.get_debugbuf()
                if dbgbuf != "":
                        res += dbgbuf
                if error is not None:
                        res += self._exc_info_to_string(error, test)
                return res

        def addFailure(self, test, err):
                unittest.TestResult.addFailure(self, test, err)

                bresult = self.baseline.handleresult(str(test), "fail")
                expected = self.baseline.expectedresult(str(test))

                # If we're debugging, we'll have had output since we
                # announced the name of the test, so restate it.
                if test.debug_output:
                        self.statename(test)

                errinfo = self.format_output_and_exc(test, err)

                if self.output == OUTPUT_PARSEABLE:
                        res = self.fmt_parseable(bresult, "FAIL", expected)
                        res += "\n"
                        if bresult == baseline.BASELINE_MISMATCH \
                           or self.show_on_expected_fail:
                                res += self.fmt_prefix_with(errinfo, "# ")
                elif self.output == OUTPUT_VERBOSE:
                        if bresult == baseline.BASELINE_MISMATCH:
                                res = "MISMATCH FAIL (expected: {0})".format(expected)
                        else:
                                res = "match FAIL (expected: FAIL)"

                        if bresult == baseline.BASELINE_MISMATCH \
                           or self.show_on_expected_fail:
                                res += self.fmt_box(errinfo,
                                    "Failure Information", "# ")

                elif self.output == OUTPUT_DOTS:
                        if bresult == baseline.BASELINE_MATCH:
                                res = "f"
                        else:
                                res = "F"

                if self.output == OUTPUT_DOTS:
                        self.stream.write(res)
                else:
                        self.stream.write(res + "\n")

                if bresult == baseline.BASELINE_MISMATCH:
                        self.mismatches.append(test)

                # Check to see if we should archive this baseline mismatch.
                if bresult == baseline.BASELINE_MISMATCH and self.archive_dir:
                        self.do_archive(test, self._exc_info_to_string(err, test))

                # Bail out completely if the 'bail on fail' flag is set
                # but iff the result disagrees with the baseline.
                if self.bailonfail and bresult == baseline.BASELINE_MISMATCH:
                        self.dobailout(test)

        def addSkip(self, test, err):
                """Python 2.7 adds formal support for skipped tests in unittest
                For now, we'll record this as a success, but also save the
                reason why we wanted to skip this test"""
                self.addSuccess(test)
                self.skips.append((str(test), err))

        def addPersistentSetupError(self, test, err):
                errtype, errval = err[:2]

                errinfo = self.format_output_and_exc(test, err)

                res = "# ERROR during persistent setup for {0}\n".format(test.id())
                res += "# As a result, all test cases in this class will " \
                    "result in errors!\n#\n"

                if errtype in ELIDABLE_ERRORS:
                        res += "#   " + str(errval)
                else:
                        res += self.fmt_box(errinfo, \
                            "Persistent Setup Error Information", "# ")
                self.stream.write(res + "\n")

        def addPersistentTeardownError(self, test, err):
                errtype, errval = err[:2]

                errinfo = self.format_output_and_exc(test, err)

                res = "# ERROR during persistent teardown for {0}\n".format(test.id())
                if errtype in ELIDABLE_ERRORS:
                        res += "#   " + str(errval)
                else:
                        res += self.fmt_box(errinfo, \
                            "Persistent Teardown Error Information", "# ")
                self.stream.write(res + "\n")

        def statename(self, test, prefix=""):
                name = self.getDescription(test)
                if self.output == OUTPUT_VERBOSE:
                        name = name.ljust(65) + "  "
                elif self.output == OUTPUT_PARSEABLE:
                        name += "|"
                elif self.output == OUTPUT_DOTS:
                        return
                self.stream.write(name)

        def startTest(self, test):
                unittest.TestResult.startTest(self, test)
                test.debug("_" * 75)
                test.debug("Start:   {0}".format(
                    self.getDescription(test)))
                if test._testMethodDoc is not None:
                        docs = ["  " + x.strip() \
                            for x in test._testMethodDoc.splitlines()]
                        while len(docs) > 0 and docs[-1] == "":
                                del docs[-1]
                        for x in docs:
                                test.debug(x)
                test.debug("_" * 75)
                test.debug("")

                if not test.debug_output:
                        self.statename(test)

        def printErrors(self):
                self.stream.write("\n")
                self.printErrorList('ERROR', self.errors)
                self.printErrorList('FAIL', self.failures)

        def printErrorList(self, flavour, errors):
                for test, err in errors:
                        self.stream.write(self.separator1 + "\n")
                        self.stream.write("{0}: {1}\n".format(
                            flavour, self.getDescription(test)))
                        self.stream.write(self.separator2 + "\n")
                        self.stream.write("{0}\n".format(err))


def find_names(s):
        """Find the module and class names for the given test suite."""

        l = str(s).split()
        mod = l[0]
        c = l[1].split(".")[0]
        return mod, c

def q_makeResult(s, o, b, bail_on_fail, show_on_expected_fail, a, cov):
        """Construct a test result for use in the parallel test suite."""

        res = _Pkg5TestResult(s, o, b, bailonfail=bail_on_fail,
            show_on_expected_fail=show_on_expected_fail, archive_dir=a)
        res.coverage = cov
        return res

def q_run(inq, outq, i, o, baseline_filepath, bail_on_fail,
    show_on_expected_fail, a, cov, port, suite_name):
        """Function used to run the test suite in parallel.

        The 'inq' parameter is the queue to pull from to get test suites.

        The 'outq' parameter is the queue on which to post results."""

        # Set up the coverage environment if it's needed.
        cov_cmd, cov_env = cov
        cov_inst = None
        if cov_env:
                cov_env["COVERAGE_FILE"] += ".{0}.{1}".format(suite_name, i)
                import coverage
                cov_inst = coverage.coverage(
                    data_file=cov_env["COVERAGE_FILE"], data_suffix=True)
                cov_inst.start()
        cov = (cov_cmd, cov_env)
        try:
                while True:
                        # Get the next test suite to run.
                        test_suite = inq.get()
                        if test_suite == "STOP":
                                break

                        # Set up the test so that it plays nicely with tests
                        # running in other processes.
                        test_suite.parallel_init(port + i * 20, i, cov)
                        # Let the master process know that we have this test
                        # suite and we're about to start running it.
                        outq.put(("START", find_names(test_suite.tests[0]), i),
                            block=True)

                        buf = six.StringIO()
                        b = baseline.ReadOnlyBaseLine(
                            filename=baseline_filepath)
                        b.load()
                        # Build a _Pkg5TestResult object to use for this test.
                        result = q_makeResult(buf, o, b, bail_on_fail,
                            show_on_expected_fail, a, cov)
                        try:
                                test_suite.run(result)
                        except TestStopException:
                                pass
                        otw = result.collapse()
                        # Pull in the information stored in places other than
                        # the _Pkg5TestResult that we need to send back to the
                        # master process.
                        otw.timing = list(test_suite.timing.items())
                        otw.text = buf.getvalue()
                        otw.baseline_failures = b.getfailures()
                        if g_debug_output:
                                otw.debug_buf = test_suite.get_debug_bufs()
                        outq.put(
                            ("RESULT", find_names(test_suite.tests[0]), i, otw),
                            block=True)
        finally:
                if cov_inst:
                        cov_inst.stop()
                        cov_inst.save()


class Pkg5TestRunner(unittest.TextTestRunner):
        """TestRunner for test suites that we want to be able to compare
        against a result baseline."""
        baseline = None

        def __init__(self, baseline, stream=sys.stderr, output=OUTPUT_DOTS,
            timing_file=None, timing_history=None, bailonfail=False,
            coverage=None,
            show_on_expected_fail=False, archive_dir=None):
                """Set up the test runner"""
                # output is one of OUTPUT_DOTS, OUTPUT_VERBOSE, OUTPUT_PARSEABLE
                super(Pkg5TestRunner, self).__init__(stream)
                self.baseline = baseline
                self.output = output
                self.timing_file = timing_file
                self.timing_history = timing_history
                self.bailonfail = bailonfail
                self.coverage = coverage
                self.show_on_expected_fail = show_on_expected_fail
                self.archive_dir = archive_dir

        def _makeResult(self):
                return _Pkg5TestResult(self.stream, self.output, self.baseline,
                    bailonfail=self.bailonfail,
                    show_on_expected_fail=self.show_on_expected_fail,
                    archive_dir=self.archive_dir)

        @staticmethod
        def __write_timing_info(stream, suite_name, class_list, method_list):
                if not class_list and not method_list:
                        return
                tot = 0
                print("Tests run for '{0}' Suite, broken down by class:\n".format(
                    suite_name), file=stream)
                for secs, cname in class_list:
                        print("{0:>6.2f} {1}.{2}".format(
                            secs, suite_name, cname), file=stream)
                        tot += secs
                        for secs, mcname, mname in method_list:
                                if mcname != cname:
                                        continue
                                print("    {0:>6.2f} {1}".format(secs, mname), file=stream)
                        print(file=stream)
                print("{0:>6.2f} Total time\n".format(tot), file=stream)
                print("=" * 60, file=stream)
                print("\nTests run for '{0}' Suite, " \
                    "sorted by time taken:\n".format(suite_name), file=stream)
                for secs, cname, mname in method_list:
                        print("{0:>6.2f} {1} {2}".format(secs, cname, mname), file=stream)
                print("{0:>6.2f} Total time\n".format(tot), file=stream)
                print("=" * 60, file=stream)
                print("", file=stream)

        @staticmethod
        def __write_timing_history(stream, suite_name, method_list,
            time_estimates):

                assert suite_name
                total = 0

                time_estimates.setdefault(suite_name, {})

                # Calculate the new time estimates for each test suite method
                # run in the last run.
                for secs, cname, mname in method_list:
                        time_estimates[suite_name].setdefault(cname,
                            {}).setdefault(mname, secs)
                        time_estimates[suite_name][cname][mname] = \
                            (time_estimates[suite_name][cname][mname] + secs) \
                            / 2.0

                # For each test class, find the average time each test in the
                # class takes to run.
                total = 0
                m_cnt = 0
                for cname in time_estimates[suite_name]:
                # for c in class_tot:
                        if cname == "TOTAL":
                                continue
                        c_tot = 0
                        c_cnt = 0
                        for mname in time_estimates[suite_name][cname]:
                                if mname == "CLASS":
                                        continue
                                c_tot += \
                                    time_estimates[suite_name][cname][mname]
                                c_cnt += 1
                        total += c_tot
                        m_cnt += c_cnt
                        c_avg = c_tot // max(c_cnt, 1)
                        time_estimates[suite_name][cname].setdefault(
                            "CLASS", c_avg)
                        time_estimates[suite_name][cname]["CLASS"] = \
                            (time_estimates[suite_name][cname]["CLASS"] +
                            c_avg) // 2

                # Calculate the average per test, regardless of which test class
                # or method is being run.
                tot_avg = total // max(m_cnt, 1)
                time_estimates[suite_name].setdefault("TOTAL", tot_avg)
                time_estimates[suite_name]["TOTAL"] = \
                    (time_estimates[suite_name]["TOTAL"] + tot_avg) // 2

                # Save the estimates to disk.
                json.dump(("1", time_estimates), stream)

        def _do_timings(self, result, time_estimates):
                timing = {}
                lst = []
                suite_name = None

                for (sname, cname, mname), secs in result.timing:
                        lst.append((secs, cname, mname))
                        if cname not in timing:
                                timing[cname] = 0
                        timing[cname] += secs
                        suite_name = sname
                if not lst:
                        return
                lst.sort()
                clst = sorted((secs, cname) for cname, secs in timing.items())

                if self.timing_history:
                        try:
                                # simpleson module will produce str
                                # in Python 3, therefore fh.write()
                                # must support str input.
                                with open(self.timing_history + ".tmp",
                                    "w+") as fh:
                                        self.__write_timing_history(fh,
                                            suite_name, lst, time_estimates)
                                portable.rename(self.timing_history + ".tmp",
                                    self.timing_history)
                                os.chmod(self.timing_history, stat.S_IRUSR |
                                    stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP |
                                    stat.S_IROTH | stat.S_IWOTH)
                        except KeyboardInterrupt:
                                raise TestStopException()

                if not self.timing_file:
                        return
                try:
                        fh = open(self.timing_file, "a+")
                        opened = True
                except KeyboardInterrupt:
                        raise TestStopException()
                except Exception:
                        fh = sys.stderr
                        opened = False
                self.__write_timing_info(fh, suite_name, clst, lst)
                if opened:
                        fh.close()

        @staticmethod
        def estimate_method_time(time_estimates, suite_name, c, method_name):
                # If there's an estimate for the method, use it.  If no method
                # estimate is available, fall back to the average time each test
                # in this class takes, if it's available.  If not class estimate
                # is available, fall back to the average time for each test in
                # the test suite.

                if c in time_estimates[suite_name]:
                        return time_estimates[suite_name][c].get(
                            method_name,
                            time_estimates[suite_name][c]["CLASS"])
                return time_estimates[suite_name]["TOTAL"]

        @staticmethod
        def __calc_remaining_time(test_classes, test_map, time_estimates,
            procs, start_times):
                """Given the running and unfinished tests, estimate the amount
                of time remaining before the remaining tests finish."""

                secs = 0
                long_pole = 0
                for mod, c in test_classes:
                        suite_name = mod.split(".")[0]
                        if suite_name not in time_estimates:
                                return None
                        class_tot = 0
                        for test in test_map[(mod, c)]:
                                class_tot += \
                                    Pkg5TestRunner.estimate_method_time(
                                    time_estimates, suite_name, c,
                                    test.methodName)
                        # Some tests have been running for a while, adjust the
                        # remaining time using this info.
                        if (mod, c) in start_times:
                                class_tot -= time.time() - start_times[(mod, c)]
                        class_tot = max(class_tot, 0)
                        secs += class_tot
                        if class_tot > long_pole:
                                long_pole = class_tot
                est = secs//max(min(procs, len(test_classes)), 1)
                return max(est, long_pole)

        def test_start_display(self, started_tests, remaining_time, p_dict,
            quiet):
                if quiet:
                        return
                print("\n\n", file=self.stream)
                print("Tests in progress:", file=self.stream)
                for p in sorted(started_tests.keys()):
                        print("\t{0}\t{1}\t{2} {3}".format(
                            p, p_dict[p].pid, started_tests[p][0],
                            started_tests[p][1]), file=self.stream)
                if remaining_time is not None:
                        print("Estimated time remaining {0:d} " \
                            "seconds".format(int(round(remaining_time))),
                            file=self.stream)

        def test_done_display(self, result, all_tests, finished_tests,
            started_tests, total_tests, quiet, remaining_time, output_text,
            comm):
                if quiet:
                        self.stream.write(output_text)
                        return
                if g_debug_output:
                        print("\n{0}".format(comm[3].debug_buf), file=sys.stderr)
                print("\n\n", file=self.stream)
                print("Finished {0} {1} in process {2}".format(
                    comm[1][0], comm[1][1], comm[2]), file=self.stream)
                print("Total test classes:{0} Finished test "
                    "classes:{1} Running tests:{2}".format(
                    len(all_tests), len(finished_tests), len(started_tests)),
                    file=self.stream)
                print("Total tests:{0} Tests run:{1} "
                    "Errors:{2} Failures:{3} Skips:{4}".format(
                    total_tests, result.testsRun, len(result.errors),
                    len(result.failures), len(result.skips)),
                    file=self.stream)
                if remaining_time and all_tests - finished_tests:
                        print("Estimated time remaining {0:d} "
                            "seconds".format(int(round(remaining_time))), file=self.stream)

        @staticmethod
        def __terminate_processes(jobs):
                """Terminate all processes in this process's task.  This
                assumes that test suite is running in its own task which
                run.py should ensure."""

                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                cmd = ["pkill", "-T", "0"]
                subprocess.call(cmd)
                print("All spawned processes should be terminated, now "
                    "cleaning up directories.", file=sys.stderr)

                # Terminated test jobs may have mounted filesystems under their
                # images and not told us about them, so we catch EBUSY, unmount,
                # and keep trying.
                finished = False
                retry = 0

                while not finished and retry < 10:
                        try:
                                shutil.rmtree(os.path.join(g_tempdir,
                                    "ips.test.{0}".format(os.getpid())))
                        except OSError as e:
                                if e.errno == errno.ENOENT:
                                        #
                                        # seems to sporadically happen if we
                                        # race with e.g. something shutting
                                        # down which has a pid file; retry.
                                        #
                                        retry += 1
                                        continue
                                elif e.errno == errno.EBUSY:
                                        ret = subprocess.call(
                                            ["/usr/sbin/umount",
                                            e.filename])
                                        # if the umount failed, bump retry so
                                        # we won't be stuck doing this forever.
                                        if ret != 0:
                                                retry += 1
                                        continue
                                else:
                                        raise
                        else:
                                finished = True

                if not finished:
                        print("Not all directories removed!", file=sys.stderr)
                else:
                        print("Directories successfully removed.", file=sys.stderr)
                sys.exit(1)

        def run(self, suite_list, jobs, port, time_estimates, quiet,
            baseline_filepath):
                "Run the given test case or test suite."

                terminate = False

                all_tests = set()
                started_tests = {}
                finished_tests = set()
                total_tests = 0
                test_map = {}

                start_times = {}
                suite_name = None

                # test case setUp() may require running pkg commands
                # so setup a fakeroot to run them from.
                fakeroot, fakeroot_cmdpath = fakeroot_create()

                inq = multiprocessing.Queue(len(suite_list) + jobs)
                for t in suite_list:
                        if not t.tests:
                                continue
                        mod, c = find_names(t.tests[0])
                        for test in t.tests:
                                tmp = find_names(test)
                                if suite_name is None:
                                        suite_name = test.suite_name
                                else:
                                        assert suite_name == test.suite_name
                                if tmp[0] != mod or tmp[1] != c:
                                        raise RuntimeError("tmp:{0} mod:{1} "
                                            "c:{2}".format(tmp, mod, c))
                        all_tests.add((mod, c))
                        t.pkg_cmdpath = fakeroot_cmdpath
                        if jobs > 1:
                                t.debug_output = False
                        inq.put(t, block=True)
                        total_tests += len(t.tests)
                        test_map[(mod, c)] = t.tests

                result = _CombinedResult()
                if not all_tests:
                        try:
                                shutil.rmtree(os.path.join(g_tempdir,
                                    "ips.test.{0}".format(os.getpid())))
                        except OSError as e:
                                if e.errno != errno.ENOENT:
                                        raise
                        return result

                assert suite_name is not None

                startTime = time.time()
                outq = multiprocessing.Queue(jobs * 10)
                p_dict = {}
                try:
                        for i in range(0, jobs):
                                p_dict[i] = multiprocessing.Process(
                                    target=q_run,
                                    args=(inq, outq, i, self.output,
                                    baseline_filepath, self.bailonfail,
                                    self.show_on_expected_fail,
                                    self.archive_dir, self.coverage, port,
                                    suite_name))
                                p_dict[i].start()
                except KeyboardInterrupt:
                        self.__terminate_processes(jobs)
                try:
                        while all_tests - finished_tests:
                                comm = outq.get(block=True)
                                remaining_time = None
                                if time_estimates:
                                        remaining_time = \
                                            self.__calc_remaining_time(
                                            all_tests - finished_tests,
                                            test_map, time_estimates,
                                            jobs, start_times)

                                if comm[0] == "START":
                                        if comm[1] not in all_tests:
                                                raise RuntimeError("Got "
                                                    "unexpected start "
                                                    "comm:{0}".format(comm))
                                        started_tests[comm[2]] = comm[1]
                                        start_times[comm[1]] = time.time()
                                        self.test_start_display(started_tests,
                                            remaining_time, p_dict, quiet)
                                elif comm[0] == "RESULT":
                                        partial_result = comm[3]
                                        result.combine(partial_result)
                                        finished_tests.add(comm[1])
                                        for n, r in \
                                            partial_result.baseline_failures:
                                                self.baseline.handleresult(n, r)
                                        if started_tests[comm[2]] != comm[1]:
                                                raise RuntimeError("mismatch")
                                        del started_tests[comm[2]]
                                        del start_times[comm[1]]
                                        self.test_done_display(result,
                                            all_tests, finished_tests,
                                            started_tests, total_tests, quiet,
                                            remaining_time, partial_result.text,
                                            comm)
                                else:
                                        raise RuntimeError("unexpected "
                                            "communication:{0}".format(comm))
                                if self.bailonfail and \
                                    (result.errors or result.failures):
                                        raise TestStopException()
                                # Check to make sure that all processes are
                                # still running.
                                broken = set()
                                for i in p_dict:
                                        if not p_dict[i].is_alive():
                                                broken.add(i)
                                if broken:

                                        print("The following "
                                            "processes have died, "
                                            "terminating the others: {0}".format(
                                            ",".join([
                                                str(p_dict[i].pid)
                                                for i in sorted(broken)
                                            ])), file=sys.stderr)
                                        raise TestStopException()
                        for i in range(0, jobs * 2):
                                inq.put("STOP")
                        for p in p_dict:
                                p_dict[p].join()
                except (KeyboardInterrupt, TestStopException):
                        terminate = True
                except Exception as e:
                        print(e)
                        terminate = True
                        raise
                finally:
                        try:
                                result.stream = self.stream
                                stopTime = time.time()
                                timeTaken = stopTime - startTime

                                run = result.testsRun
                                if run > 0:
                                        if self.output != OUTPUT_VERBOSE:
                                                result.printErrors()
                                                self.stream.write("# " +
                                                    result.separator2 + "\n")
                                        self.stream.write("\n# Ran {0:d} test{1} "
                                            "in {2:>.3f}s - skipped {3:d} tests.\n".format(
                                            run, run != 1 and "s" or "",
                                            timeTaken, len(result.skips)))

                                        if result.wasSkipped() and \
                                            self.output == OUTPUT_VERBOSE:
                                                self.stream.write("Skipped "
                                                    "tests:\n")
                                                for test,reason in result.skips:
                                                        self.stream.write(
                                                            "{0}: {1}\n".format(
                                                            test, reason))
                                        self.stream.write("\n")
                                if not result.wasSuccessful():
                                        self.stream.write("FAILED (")
                                        success = result.num_successes
                                        mismatches = result.mismatches
                                        failed, errored = map(len,
                                            (result.failures, result.errors))
                                        self.stream.write("successes={0:d}, ".format(
                                            success))
                                        self.stream.write("failures={0:d}, ".format(
                                            failed))
                                        self.stream.write("errors={0:d}, ".format(
                                            errored))
                                        self.stream.write("mismatches={0:d}".format(
                                            mismatches))
                                        self.stream.write(")\n")

                                self._do_timings(result, time_estimates)
                        finally:
                                if terminate:
                                        self.__terminate_processes(jobs)
                                shutil.rmtree(os.path.join(g_tempdir,
                                    "ips.test.{0}".format(os.getpid())))
                return result


class Pkg5TestSuite(unittest.TestSuite):
        """Test suite that extends unittest.TestSuite to handle persistent
        tests.  Persistent tests are ones that are able to only call their
        setUp/tearDown functions once per class, instead of before and after
        every test case.  Aside from actually running the test it defers the
        majority of its work to unittest.TestSuite.

        To make a test class into a persistent one, add this class
        variable declaration:
                persistent_setup = True
        """

        def __init__(self, tests=()):
                unittest.TestSuite.__init__(self, tests)
                self.timing = {}
                self.__pid = os.getpid()
                self.pkg_cmdpath = "TOXIC"
                self.__debug_output = g_debug_output

                # The site module deletes the function to change the
                # default encoding so a forced reload of sys has to
                # be done at least once.
                reload(sys)

        def cleanup_and_die(self, inst, info):
                print("\nCtrl-C: Attempting cleanup during {0}".format(info),
                    file=sys.stderr)

                if hasattr(inst, "killalldepots"):
                        print("Killing depots...", file=sys.stderr)
                        inst.killalldepots()
                print("Stopping tests...", file=sys.stderr)
                raise TestStopException()

        def run(self, result):
                self.timing = {}
                inst = None
                tdf = None
                try:
                        persistent_setup = getattr(self._tests[0],
                            "persistent_setup", False)
                except IndexError:
                        # No tests; that's ok.
                        return

                # This is needed because the import of some modules (such as
                # pygtk or pango) causes the default encoding for Python to be
                # changed which can can cause tests to succeed when they should
                # fail due to unicode issues:
                #     https://bugzilla.gnome.org/show_bug.cgi?id=132040
                if six.PY2:
                        default_utf8 = getattr(self._tests[0], "default_utf8",
                            False)
                        if not default_utf8:
                                # Now reset to the default a standard Python
                                # distribution uses.
                                sys.setdefaultencoding("ascii")
                        else:
                                sys.setdefaultencoding("utf-8")

                def setUp_donothing():
                        pass

                def tearDown_donothing():
                        pass

                def setUp_dofail():
                        raise TestSkippedException(
                            "Persistent setUp Failed, skipping test.")

                env_sanitize(self.pkg_cmdpath)

                if persistent_setup:
                        setUpFailed = False

                        # Save a reference to the tearDown func and neuter
                        # normal per-test-function teardown.
                        inst, tdf = self._tests[0].getTeardownFunc()
                        inst.reallytearDown = tdf
                        inst.tearDown = tearDown_donothing

                        if result.coverage:
                                inst.coverage_cmd, inst.coverage_env = result.coverage
                        else:
                                inst.coverage_cmd, inst.coverage_env = "", {}

                        try:
                                inst.setUp()
                        except KeyboardInterrupt:
                                self.cleanup_and_die(inst, "persistent setup")
                        except:
                                result.addPersistentSetupError(inst, sys.exc_info())
                                setUpFailed = True
                                # XXX do cleanup?

                        # If the setUp function didn't work, then cause
                        # every test case to fail.
                        if setUpFailed:
                                inst.setUp = setUp_dofail
                        else:
                                inst.setUp = setUp_donothing

                for test in self._tests:
                        if result.shouldStop:
                                break
                        real_test_name = test._testMethodName
                        suite_name = test.suite_name
                        cname = test.__class__.__name__

                        #
                        # Update test environment settings. We redo this
                        # before running each test case since previously
                        # executed test cases may have messed with these
                        # environment settings.
                        #
                        env_sanitize(self.pkg_cmdpath, dv_keep=["smf_cmds_dir"])

                        # Populate test with the data from the instance
                        # already constructed, but update the method name.
                        # We need to do this so that we have all the state
                        # that the object is populated with when setUp() is
                        # called (depot controller list, etc).
                        if persistent_setup:
                                name = test._testMethodName
                                doc = test._testMethodDoc
                                buf = test.get_debugbuf()
                                rtest = copy.copy(inst)
                                rtest._testMethodName = name
                                rtest._testMethodDoc = doc
                                rtest.persistent_setup_copy(inst)
                                rtest.set_debugbuf(buf)
                                setup_logging(rtest)
                        else:
                                rtest = test

                        test_start = time.time()
                        rtest(result)
                        test_end = time.time()
                        self.timing[suite_name, cname, real_test_name] = \
                            test_end - test_start

                        # If rtest is a copy of test, then we need to copy
                        # rtest's buffer back to test's so that it has the
                        # output from the run.
                        if persistent_setup:
                                test.set_debugbuf(rtest.get_debugbuf())

                        for fs in getattr(rtest, "fs", ()):
                                subprocess.call(["/usr/sbin/umount", fs])

                if persistent_setup:
                        try:
                                inst.reallytearDown()
                        except KeyboardInterrupt:
                                self.cleanup_and_die(inst, "persistent teardown")
                        except:
                                result.addPersistentTeardownError(inst, sys.exc_info())

                # Try to ensure that all depots have been nuked.
                if hasattr(inst, "killalldepots"):
                        inst.killalldepots()

        def parallel_init(self, p, i, cov):
                for t in self._tests:
                        t.base_port = p
                        t.ident = i
                        t.coverage = cov
                        t.pkg_cmdpath = self.pkg_cmdpath

        def test_count(self):
                return len(self._tests)

        @property
        def tests(self):
                return [t for t in self._tests]

        def __set_debug_output(self, v):
                self.__debug_output = v
                for t in self._tests:
                        t.debug_output = v

        def __get_debug_output(self):
                return self.__debug_output

        debug_output = property(__get_debug_output, __set_debug_output)

        def get_debug_bufs(self):
                res = ""
                for t in self._tests:
                        res += "\n".join(
                            ["# {0}".format(l) for l in t.get_debugbuf().splitlines()])
                        res += "\n"
                return res


def get_su_wrap_user(uid_gid=False):
        for u in ["noaccess", "nobody"]:
                try:
                        pw = pwd.getpwnam(u)
                        if uid_gid:
                                return operator.attrgetter(
                                    'pw_uid', 'pw_gid')(pw)
                        return u
                except (KeyError, NameError):
                        pass
        raise RuntimeError("Unable to determine user for su.")


class DepotTracebackException(Pkg5CommonException):
        def __init__(self, logfile, output):
                Pkg5CommonException.__init__(self)
                self.__logfile = logfile
                self.__output = output

        def __str__(self):
                str = "During this test, a depot Traceback was detected.\n"
                str += "Log file: {0}.\n".format(self.__logfile)
                str += "Log file output is:\n"
                str += self.format_output(None, self.__output)
                return str

class TracebackException(Pkg5CommonException):
        def __init__(self, command, output=None, comment=None, debug=None):
                Pkg5CommonException.__init__(self)
                self.__command = command
                self.__output = output
                self.__comment = comment
                self.__debug = debug

        def __str__(self):
                if self.__comment is None and self.__output is None:
                        return (Exception.__str__(self))

                str = ""
                str += self.format_comment(self.__comment)
                str += self.format_output(self.__command, self.__output)
                if self.__debug is not None and self.__debug != "":
                        str += self.format_debug(self.__debug)
                return str

class UnexpectedExitCodeException(Pkg5CommonException):
        def __init__(self, command, expected, got, output=None, comment=None):
                Pkg5CommonException.__init__(self)
                self.__command = command
                self.__output = output
                self.__expected = expected
                self.__got = got
                self.__comment = comment

        def __str__(self):
                if self.__comment is None and self.__output is None:
                        return (Exception.__str__(self))

                str = ""
                str += self.format_comment(self.__comment)

                str += "  Invoked: {0}\n".format(self.__command)
                str += "  Expected exit status: {0}.  Got: {1:d}.".format(
                    self.__expected, self.__got)

                str += self.format_output(self.__command, self.__output)
                return str

        @property
        def exitcode(self):
                return self.__got

class PkgSendOpenException(Pkg5CommonException):
        def __init__(self, com = ""):
                Pkg5CommonException.__init__(self, com)

class CliTestCase(Pkg5TestCase):
        bail_on_fail = False

        image_files = []

        def setUp(self, image_count=1):
                Pkg5TestCase.setUp(self)

                self.__imgs_path = {}
                self.__imgs_index = -1

                for i in range(0, image_count):
                        path = os.path.join(self.test_root, "image{0:d}".format(i))
                        self.__imgs_path[i] = path

                self.set_image(0)

        def tearDown(self):
                Pkg5TestCase.tearDown(self)

        def persistent_setup_copy(self, orig):
                Pkg5TestCase.persistent_setup_copy(self, orig)
                self.__imgs_path = copy.copy(orig.__imgs_path)

        def set_image(self, ii):
                # ii is the image index
                if self.__imgs_index == ii:
                        return

                self.__imgs_index = ii
                path = self.__imgs_path[self.__imgs_index]
                assert path and path != "/"

                self.debug("image {0:d} selected: {1}".format(ii, path))

        def set_img_path(self, path):
                self.__imgs_path[self.__imgs_index] = path

        def img_index(self):
                return self.__imgs_index

        def img_path(self, ii=None):
                if ii != None:
                        return self.__imgs_path[ii]
                return self.__imgs_path[self.__imgs_index]

        def get_img_path(self):
                # for backward compatibilty
                return self.img_path()

        def get_img_file_path(self, relpath):
                """Given a path relative to root, return the absolute path of
                the item in the image."""

                return os.path.join(self.img_path(), relpath)

        def get_img_api_obj(self, cmd_path=None, ii=None, img_path=None):
                progresstracker = pkg.client.progress.NullProgressTracker()
                if not cmd_path:
                        cmd_path = os.path.join(self.img_path(), "pkg")
                if not img_path:
                        img_path = self.img_path(ii=ii)
                res = pkg.client.api.ImageInterface(img_path,
                    CLIENT_API_VERSION, progresstracker, lambda x: False,
                    PKG_CLIENT_NAME, cmdpath=cmd_path)
                return res

        def __setup_signing_files(self):
                if not getattr(self, "need_ro_data", False):
                        return
                # Set up the trust anchor directory
                self.ta_dir = os.path.join(self.img_path(), "etc/certs/CA")
                os.makedirs(self.ta_dir)
                for f in self.image_files:
                        with open(os.path.join(self.img_path(), f), "wb") as fh:
                                fh.close()

        def image_create(self, repourl=None, destroy=True, fs=(),
            img_path=None, **kwargs):
                """A convenience wrapper for callers that only need basic image
                creation functionality.  This wrapper creates a full (as opposed
                to user) image using the pkg.client.api and returns the related
                API object."""

                if img_path is None:
                        img_path = self.img_path()

                if destroy:
                        self.image_destroy(img_path=img_path)

                mkdir_eexist_ok(img_path)

                self.fs = set()

                force = False
                for path in fs:
                        full_path = os.path.join(img_path,
                            path.lstrip(os.path.sep))
                        os.makedirs(full_path)
                        self.cmdline_run("/usr/sbin/mount -F tmpfs swap " +
                            full_path, coverage=False)
                        self.fs.add(full_path)
                        if path.lstrip(os.path.sep) == "var":
                                force = True

                self.debug("image_create {0}".format(img_path))
                progtrack = pkg.client.progress.NullProgressTracker()
                api_inst = pkg.client.api.image_create(PKG_CLIENT_NAME,
                    CLIENT_API_VERSION, img_path,
                    pkg.client.api.IMG_TYPE_ENTIRE, False, repo_uri=repourl,
                    progtrack=progtrack, force=force,
                    **kwargs)
                self.__setup_signing_files()
                return api_inst

        def pkg_image_create(self, repourl=None, prefix=None,
            additional_args="", exit=0, env_arg=None):
                """Executes pkg(1) client to create a full (as opposed to user)
                image; returns exit code of client or raises an exception if
                exit code doesn't match 'exit' or equals 99."""

                if repourl and prefix is None:
                        prefix = "test"

                self.image_destroy()
                os.mkdir(self.img_path())
                cmdline = sys.executable + " {0} image-create -F ".format(
                    self.pkg_cmdpath)
                if repourl:
                        cmdline = "{0} -p {1}={2} ".format(cmdline, prefix, repourl)
                cmdline += additional_args
                cmdline = "{0} {1}".format(cmdline, self.img_path())

                retcode = self.cmdline_run(cmdline, exit=exit, env_arg=env_arg)

                self.__setup_signing_files()
                return retcode

        def image_clone(self, dst):

                # the currently selected image is the source
                src = self.img_index()
                src_path = self.img_path()

                # create an empty destination image
                self.set_image(dst)
                self.image_destroy()
                os.mkdir(self.img_path())
                dst_path = self.img_path()

                # reactivate the source image
                self.set_image(src)

                # populate the destination image
                cmdline = "cd {0}; find . | cpio -pdm {1}".format(src_path, dst_path)
                retcode = self.cmdline_run(cmdline, coverage=False)

        def image_destroy(self, img_path=None):

                if img_path is None:
                        img_path = self.img_path()

                if os.path.exists(img_path):
                        self.debug("image_destroy {0}".format(img_path))
                        # Make sure we're not in the image.
                        os.chdir(self.test_root)
                        for path in getattr(self, "fs", set()).copy():
                                self.cmdline_run("/usr/sbin/umount " + path,
				    coverage=False)
                                self.fs.remove(path)
                        shutil.rmtree(img_path)

        def pkg(self, command, exit=0, comment="", prefix="", su_wrap=None,
            out=False, stderr=False, cmd_path=None, use_img_root=True,
            debug_smf=True, env_arg=None, coverage=True, handle=False,
            assert_solution=True):

                if isinstance(command, list):
                        cmdstr = " ".join(command)
                else:
                        cmdstr = command

                cmdline = [sys.executable]

                if not cmd_path:
                        cmd_path = self.pkg_cmdpath

                cmdline.append(cmd_path)

                if (use_img_root and "-R" not in cmdstr and
                    "image-create" not in cmdstr):
                        cmdline.extend(("-R", self.get_img_path()))

                cmdline.extend(("-D", "plandesc_validate=1"))
                cmdline.extend(("-D", "manifest_validate=Always"))

                if debug_smf and "smf_cmds_dir" not in cmdstr:
                        cmdline.extend(("-D", "smf_cmds_dir={0}".format(
                            DebugValues["smf_cmds_dir"])))

                if not isinstance(command, list):
                        cmdline = "{0} {1}".format(" ".join(cmdline), command)
                else:
                        cmdline.extend(command)

                rval = self.cmdline_run(cmdline, exit=exit, comment=comment,
                    prefix=prefix, su_wrap=su_wrap, out=out, stderr=stderr,
                    env_arg=env_arg, coverage=coverage, handle=handle)

                if assert_solution:
                        # Ensure solver never fails with 'No solution' by
                        # default to prevent silent failures for the wrong
                        # reason.
                        for buf in (self.errout, self.output):
                                self.assertTrue("No solution" not in buf,
                                    msg="Solver could not find solution for "
                                    "operation; set assert_solution=False if "
                                    "this is expected when calling pkg().")

                return rval

        def pkg_verify(self, command, exit=0, comment="", prefix="",
            su_wrap=None, out=False, stderr=False, cmd_path=None,
            use_img_root=True, debug_smf=True, env_arg=None, coverage=True):
                """Wraps self.pkg(..) and checks that the 'verify' command run
                does not contain the string 'Unexpected Exception', indicating
                something has gone wrong during package verification."""

                cmd = "verify {0}".format(command)
                res = self.pkg(command=cmd, exit=exit, comment=comment,
                    prefix=prefix, su_wrap=su_wrap, out=out, stderr=stderr,
                    cmd_path=cmd_path, use_img_root=use_img_root,
                    debug_smf=debug_smf, env_arg=env_arg, coverage=coverage)
                if "Unexpected Exception" in self.output:
                        raise TracebackException(cmd, self.output,
                            "Unexpected errors encountered while verifying.")
                return res

        def pkgdepend_resolve(self, args, exit=0, comment="", su_wrap=False,
            env_arg=None):
                ops = ""
                if "-R" not in args:
                        ops = "-R {0}".format(self.get_img_path())
                cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/bin/pkgdepend {0} resolve {1}".format(ops, args))
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    su_wrap=su_wrap, env_arg=env_arg)

        def pkgdepend_generate(self, args, exit=0, comment="", su_wrap=False,
            env_arg=None):
                cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/bin/pkgdepend generate {0}".format(args))
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    su_wrap=su_wrap, env_arg=env_arg)

        def pkgdiff(self, command, comment="", exit=0, su_wrap=False,
            env_arg=None, stderr=False, out=False):
                cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/bin/pkgdiff {0}".format(command))
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    su_wrap=su_wrap, env_arg=env_arg, out=out, stderr=stderr)

        def pkgfmt(self, args, exit=0, su_wrap=False, env_arg=None):
                cmd= sys.executable + " " + \
                     os.path.join(g_pkg_path, "usr/bin/pkgfmt {0}".format(args))
                self.cmdline_run(cmd, exit=exit, su_wrap=su_wrap,
                    env_arg=env_arg)

        def pkglint(self, args, exit=0, comment="", testrc=True,
            env_arg=None):
                if testrc:
                        rcpath = "{0}/pkglintrc".format(self.test_root)
                        cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                            "usr/bin/pkglint -f {0} {1}".format(rcpath, args))
                else:
                        cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                            "usr/bin/pkglint {0}".format(args))
                return self.cmdline_run(cmdline, exit=exit, out=True,
                    comment=comment, stderr=True, env_arg=env_arg)

        def pkgrecv(self, server_url=None, command=None, exit=0, out=False,
            comment="", env_arg=None, su_wrap=False):
                args = []
                if server_url:
                        args.append("-s {0}".format(server_url))

                if command:
                        args.append(command)

                cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/bin/pkgrecv {0}".format(" ".join(args)))

                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    out=out, su_wrap=su_wrap, env_arg=env_arg)

        def pkgmerge(self, args, comment="", exit=0, su_wrap=False,
            env_arg=None):
                cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/bin/pkgmerge {0}".format(args))
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    su_wrap=su_wrap, env_arg=env_arg)

        def pkgrepo(self, command, comment="", exit=0, su_wrap=False,
            env_arg=None, stderr=False, out=False, debug_hash=None):
                if debug_hash:
                        debug_arg = "-D hash={0} ".format(debug_hash)
                else:
                        debug_arg = ""

                # Always add the current ignored_deps dir path.
                debug_arg += "-D ignored_deps={0} ".format(os.path.join(
                    g_pkg_path, "usr/share/pkg/ignored_deps"))
                cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/bin/pkgrepo {0}{1}".format(debug_arg, command))
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    su_wrap=su_wrap, env_arg=env_arg, out=out, stderr=stderr)

        def pkgsurf(self, command, comment="", exit=0, su_wrap=False,
            env_arg=None, stderr=False, out=False):
                cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/bin/pkgsurf {0}".format(command))
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    su_wrap=su_wrap, env_arg=env_arg, out=out, stderr=stderr)

        def pkgsign(self, depot_url, command, exit=0, comment="",
            env_arg=None, debug_hash=None):
                args = []
                if depot_url:
                        args.append("-s {0}".format(depot_url))

                if debug_hash:
                        args.append("-D hash={0}".format(debug_hash))

                if command:
                        args.append(command)

                cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/bin/pkgsign {0}".format(" ".join(args)))
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    env_arg=env_arg)

        def pkgsign_simple(self, depot_url, pkg_name, exit=0, env_arg=None,
            debug_hash=None):
                chain_cert_path = os.path.join(self.chain_certs_dir,
                    "ch1_ta3_cert.pem")
                sign_args = "-k {key} -c {cert} -i {ch1} {name}".format(
                    name=pkg_name,
                    key=os.path.join(self.keys_dir, "cs1_ch1_ta3_key.pem"),
                    cert=os.path.join(self.cs_dir, "cs1_ch1_ta3_cert.pem"),
                    ch1=chain_cert_path,
               )
                return self.pkgsign(depot_url, sign_args, exit=exit,
                    env_arg=env_arg, debug_hash=debug_hash)

        def pkgsend(self, depot_url="", command="", exit=0, comment="",
            allow_timestamp=False, env_arg=None, su_wrap=False,
            debug_hash=None):
                args = []
                if allow_timestamp:
                        args.append("-D allow-timestamp")
                if depot_url:
                        args.append("-s " + depot_url)

                # debug_hash lets us choose the type of hash attributes that
                # should be added to this package on publication. Valid values
                # are: sha1, sha256, sha1+sha256, sha512t_256, sha1+sha512t_256
                if debug_hash:
                        args.append("-D hash={0}".format(debug_hash))

                if command:
                        args.append(command)

                prefix = "cd {0};".format(self.test_root)
                cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/bin/pkgsend {0}".format(" ".join(args)))

                retcode, out = self.cmdline_run(cmdline, comment=comment,
                    exit=exit, out=True, prefix=prefix, raise_error=False,
                    env_arg=env_arg, su_wrap=su_wrap)
                errout = self.errout

                cmdop = command.split(' ')[0]
                if cmdop in ("open", "append") and retcode == 0:
                        out = out.rstrip()
                        assert out.startswith("export PKG_TRANS_ID=")
                        arr = out.split("=")
                        assert arr
                        out = arr[1]
                        os.environ["PKG_TRANS_ID"] = out
                        self.debug("$ export PKG_TRANS_ID={0}".format(out))
                        # retcode != 0 will be handled below

                published = None
                if (cmdop == "close" and retcode == 0) or cmdop == "publish":
                        os.environ["PKG_TRANS_ID"] = ""
                        self.debug("$ export PKG_TRANS_ID=")
                        for l in out.splitlines():
                                if l.startswith("pkg:/"):
                                        published = l
                                        break
                elif (cmdop == "generate" and retcode == 0):
                        published = out

                if retcode == 99:
                        raise TracebackException(cmdline, out + errout, comment)

                if retcode != exit:
                        raise UnexpectedExitCodeException(cmdline, exit,
                            retcode, out + errout, comment)

                return retcode, published

        def pkgsend_bulk(self, depot_url, commands, exit=0, comment="",
            no_catalog=False, refresh_index=False, su_wrap=False,
            debug_hash=None):
                """ Send a series of packaging commands; useful  for quickly
                    doing a bulk-load of stuff into the repo.  All commands are
                    expected to work; if not, the transaction is abandoned.  If
                    'exit' is set, then if none of the actions triggers that
                    exit code, an UnexpectedExitCodeException is raised.

                    A list containing the fmris of any packages that were
                    published as a result of the commands executed will be
                    returned; it will be empty if none were. """

                if isinstance(commands, (list, tuple)):
                        commands = "".join(commands)

                extra_opts = []
                if no_catalog:
                        extra_opts.append("--no-catalog")
                extra_opts = " ".join(extra_opts)

                plist = []
                try:
                        accumulate = []
                        current_fmri = None
                        retcode = None

                        for line in commands.split("\n"):
                                line = line.strip()

                                # pkgsend_bulk can't be used w/ import or
                                # generate.
                                assert not line.startswith("import"), \
                                    "pkgsend_bulk cannot be used with import"
                                assert not line.startswith("generate"), \
                                    "pkgsend_bulk cannot be used with generate"

                                if line == "":
                                        continue
                                if line.startswith("add"):
                                        self.assertTrue(current_fmri != None,
                                            "Missing open in pkgsend string")
                                        accumulate.append(line[4:])
                                        continue

                                if current_fmri: # send any content seen so far (can be 0)
                                        fd, f_path = tempfile.mkstemp(dir=self.test_root)
                                        for l in accumulate:
                                                os.write(fd, misc.force_bytes(
                                                    "{0}\n".format(l)))
                                        os.close(fd)
                                        if su_wrap:
                                                os.chown(f_path,
                                                    *get_su_wrap_user(
                                                    uid_gid=True))
                                        try:
                                                cmd = "publish {0} -d {1} {2}".format(
                                                    extra_opts, self.test_root,
                                                    f_path)
                                                current_fmri = None
                                                accumulate = []
                                                # Various tests rely on the
                                                # ability to specify version
                                                # down to timestamp for ease
                                                # of testing or because they're
                                                # actually testing timestamp
                                                # package behaviour.
                                                retcode, published = \
                                                    self.pkgsend(depot_url, cmd,
                                                    allow_timestamp=True,
                                                    su_wrap=su_wrap,
                                                    debug_hash=debug_hash)
                                                if retcode == 0 and published:
                                                        plist.append(published)
                                        except:
                                                os.remove(f_path)
                                                raise
                                        os.remove(f_path)
                                if line.startswith("open"):
                                        current_fmri = line[5:].strip()
                                        if commands.find("pkg.fmri") == -1:
                                                # If no explicit pkg.fmri set
                                                # action was found, add one.
                                                accumulate.append("set "
                                                    "name=pkg.fmri value={0}".format(
                                                    current_fmri))

                        if exit == 0 and refresh_index:
                                self.pkgrepo("-s {0} refresh --no-catalog".format(
                                    depot_url), su_wrap=su_wrap,
                                    debug_hash=debug_hash)
                except UnexpectedExitCodeException as e:
                        if e.exitcode != exit:
                                raise
                        retcode = e.exitcode

                if retcode != exit:
                        raise UnexpectedExitCodeException(line, exit, retcode,
                            self.output + self.errout)

                return plist

        def merge(self, args=EmptyI, exit=0):
                cmd = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/bin/pkgmerge {0}".format(" ".join(args)))
                self.cmdline_run(cmd, exit=exit)

        def sysrepo(self, args, exit=0, out=False, stderr=False, comment="",
            env_arg=None, fill_missing_args=True):
                ops = ""
                if "-R" not in args:
                        args += " -R {0}".format(self.get_img_path())
                if "-c" not in args:
                        args += " -c {0}".format(os.path.join(self.test_root,
                            "sysrepo_cache"))
                if "-l" not in args:
                        args += " -l {0}".format(os.path.join(self.test_root,
                            "sysrepo_logs"))
                if "-p" not in args and fill_missing_args:
                        args += " -p {0}".format(self.next_free_port)
                if "-r" not in args:
                        args += " -r {0}".format(os.path.join(self.test_root,
                            "sysrepo_runtime"))
                if "-t" not in args:
                        args += " -t {0}".format(self.sysrepo_template_dir)

                cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/lib/pkg.sysrepo {0}".format(args))
                if env_arg is None:
                        env_arg = {}
                env_arg["PKG5_TEST_ENV"] = "1"
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    out=out, stderr=stderr, env_arg=env_arg)

        def snooze(self, sleeptime=10800, show_stack=True):
                """A convenient method to cause test execution to pause for
                up to 'sleeptime' seconds, which can be helpful during testcase
                development.  sleeptime defaults to 3 hours."""
                self.debug("YAWN ... going to sleep now\n")
                if show_stack:
                        self.debug("\n\n\n")
                        self.debug("".join(traceback.format_stack()))
                time.sleep(sleeptime)

        def depotconfig(self, args, exit=0, out=False, stderr=False, comment="",
            env_arg=None, fill_missing_args=True, debug_smf=True):
                """Run pkg.depot-config, with command line arguments in args.
                If fill_missing_args is set, we use default settings for several
                arguments to point to template, logs, cache and proto areas
                within our test root."""

                if "-S" not in args and "-d " not in args and fill_missing_args:
                        args += " -S "
                if "-c " not in args and fill_missing_args:
                        args += " -c {0}".format(os.path.join(self.test_root,
                            "depot_cache"))
                if "-l" not in args:
                        args += " -l {0}".format(os.path.join(self.test_root,
                            "depot_logs"))
                if "-p" not in args and "-F" not in args and fill_missing_args:
                        args += " -p {0}".format(self.depot_port)
                if "-r" not in args:
                        args += " -r {0}".format(os.path.join(self.test_root,
                            "depot_runtime"))
                if "-T" not in args:
                        args += " -T {0}".format(self.depot_template_dir)

                if debug_smf and "smf_cmds_dir" not in args:
                        args += " --debug smf_cmds_dir={0}".format(
                            DebugValues["smf_cmds_dir"])

                cmdline = sys.executable + " " + os.path.join(g_pkg_path,
                    "usr/lib/pkg.depot-config {0}".format(args))
                if env_arg is None:
                        env_arg = {}
                env_arg["PKG5_TEST_PROTO"] = g_pkg_path
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    out=out, stderr=stderr, env_arg=env_arg)

        def copy_repository(self, src, dest, pub_map):
                """Copies the packages from the src repository to a new
                destination repository that will be created at dest.  In
                addition, any packages from the src_pub will be assigned
                to the dest_pub during the copy.  The new repository will
                not have a catalog or search indices, so a depot server
                pointed at the new repository must be started with the
                --rebuild option.
                """

                # Preserve destination repository's configuration if it exists.
                dest_cfg = os.path.join(dest, "pkg5.repository")
                dest_cfg_data = None
                if os.path.exists(dest_cfg):
                        with open(dest_cfg, "rb") as f:
                                dest_cfg_data = f.read()
                shutil.rmtree(dest, True)
                os.makedirs(dest, mode=0o755)

                # Ensure config is written back out.
                if dest_cfg_data:
                        with open(dest_cfg, "wb") as f:
                                f.write(dest_cfg_data)

                def copy_manifests(src_root, dest_root):
                        # Now copy each manifest and replace any references to
                        # the old publisher with that of the new publisher as
                        # they are copied.
                        src_pkg_root = os.path.join(src_root, "pkg")
                        dest_pkg_root = os.path.join(dest_root, "pkg")
                        for stem in os.listdir(src_pkg_root):
                                src_pkg_path = os.path.join(src_pkg_root, stem)
                                dest_pkg_path = os.path.join(dest_pkg_root,
                                    stem)
                                for mname in os.listdir(src_pkg_path):
                                        # Ensure destination manifest directory
                                        # exists.
                                        if not os.path.isdir(dest_pkg_path):
                                                os.makedirs(dest_pkg_path,
                                                    mode=0o755)

                                        msrc = open(os.path.join(src_pkg_path,
                                            mname), "r")
                                        mdest = open(os.path.join(dest_pkg_path,
                                            mname), "w")
                                        for l in msrc:
                                                if l.find("pkg://") == -1:
                                                        mdest.write(l)
                                                        continue
                                                nl = l
                                                for src_pub in pub_map:
                                                        nl = nl.replace(
                                                            src_pub,
                                                            pub_map[src_pub])
                                                mdest.write(nl)
                                        msrc.close()
                                        mdest.close()

                src_pub_root = os.path.join(src, "publisher")
                if os.path.exists(src_pub_root):
                        dest_pub_root = os.path.join(dest, "publisher")
                        for pub in os.listdir(src_pub_root):
                                if pub not in pub_map:
                                        continue
                                src_root = os.path.join(src_pub_root, pub)
                                dest_root = os.path.join(dest_pub_root,
                                    pub_map[pub])
                                for entry in os.listdir(src_root):
                                        # Skip the catalog, index, and pkg
                                        # directories as they will be copied
                                        # manually.
                                        if entry not in ("catalog", "index",
                                            "pkg", "tmp", "trans"):
                                                spath = os.path.join(src_root,
                                                    entry)
                                                dpath = os.path.join(dest_root,
                                                    entry)
                                                shutil.copytree(spath, dpath)
                                                continue
                                        if entry != "pkg":
                                                continue
                                        copy_manifests(src_root, dest_root)

        def get_img_manifest_cache_dir(self, pfmri, ii=None):
                """Returns the path to the manifest cache directory for the
                given fmri."""

                img = self.get_img_api_obj(ii=ii).img

                if not pfmri.publisher:
                        # Allow callers to not specify a fully-qualified FMRI
                        # if it can be asssumed which publisher likely has
                        # the package.
                        pubs = [
                            p.prefix
                            for p in img.gen_publishers(inc_disabled=True)
                        ]
                        if not pubs:
                                # Include prefixes of publishers of installed
                                # packages that are no longer configured.
                                pubs.extend(p for p in img.get_installed_pubs())
                        assert len(pubs) == 1
                        pfmri.publisher = pubs[0]
                return img.get_manifest_dir(pfmri)

        def get_img_manifest_path(self, pfmri):
                """Returns the path to the manifest for the given fmri."""

                img = self.get_img_api_obj().img

                if not pfmri.publisher:
                        # Allow callers to not specify a fully-qualified FMRI
                        # if it can be asssumed which publisher likely has
                        # the package.
                        pubs = [
                            p.prefix
                            for p in img.gen_publishers(inc_disabled=True)
                        ]
                        if not pubs:
                                # Include prefixes of publishers of installed
                                # packages that are no longer configured.
                                pubs.extend(p for p in img.get_installed_pubs())
                        assert len(pubs) == 1
                        pfmri.publisher = pubs[0]
                return img.get_manifest_path(pfmri)

        def get_img_manifest(self, pfmri):
                """Retrieves the client's cached copy of the manifest for the
                given package FMRI and returns it as a string.  Callers are
                responsible for all error handling."""

                mpath = self.get_img_manifest_path(pfmri)
                with open(mpath, "r") as f:
                        return f.read()

        def write_img_manifest(self, pfmri, mdata):
                """Overwrites the client's cached copy of the manifest for the
                given package FMRI using the provided string.  Callers are
                responsible for all error handling."""

                mpath = self.get_img_manifest_path(pfmri)
                mdir = os.path.dirname(mpath)
                mcdir = self.get_img_manifest_cache_dir(pfmri)

                # Dump the manifest directories for the package to ensure any
                # cached information related to it is gone.
                shutil.rmtree(mdir, True)
                shutil.rmtree(mcdir, True)
                self.assertTrue(not os.path.exists(mdir))
                self.assertTrue(not os.path.exists(mcdir))
                os.makedirs(mdir, mode=0o755)
                os.makedirs(mcdir, mode=0o755)

                # Finally, write the new manifest.
                with open(mpath, "w") as f:
                        f.write(mdata)

        def validate_fsobj_attrs(self, act, target=None):
                """Used to verify that the target item's mode, attrs, timestamp,
                etc. match as expected.  The actual"""

                if act.name not in ("file", "dir"):
                        return

                img_path = self.img_path()
                if not target:
                        target = act.attrs["path"]

                fpath = os.path.join(img_path, target)
                lstat = os.lstat(fpath)

                # Verify owner.
                expected = portable.get_user_by_name(act.attrs["owner"], None,
                    False)
                actual = lstat.st_uid
                self.assertEqual(expected, actual)

                # Verify group.
                expected = portable.get_group_by_name(act.attrs["group"], None,
                    False)
                actual = lstat.st_gid
                self.assertEqual(expected, actual)

                # Verify mode.
                expected = int(act.attrs["mode"], 8)
                actual = stat.S_IMODE(lstat.st_mode)
                self.assertEqual(expected, actual)

        def validate_html_file(self, fname, exit=0, comment="",
            options="--doctype strict -utf8 -quiet", drop_prop_attrs=False):
                """ Run a html file specified by fname through a html validator
                    (tidy). The drop_prop_attrs parameter can be used to ignore
                    proprietary attributes which would otherwise make tidy fail.
                """
                if drop_prop_attrs:
                        tfname = fname + ".tmp"
                        os.rename(fname, tfname)
                        moptions = options + " --drop-proprietary-attributes y"
                        cmdline = "tidy {0} {1} > {2}".format(moptions, tfname, fname)
                        self.cmdline_run(cmdline, comment=comment,
                            coverage=False, exit=exit, raise_error=False)
                        os.unlink(tfname)

                cmdline = "tidy {0} {1}".format(options, fname)
                return self.cmdline_run(cmdline, comment=comment,
                    coverage=False, exit=exit)

        def create_repo(self, repodir, properties=EmptyDict, version=None):
                """ Convenience routine to help subclasses create a package
                    repository.  Returns a pkg.server.repository.Repository
                    object. """

                # Note that this must be deferred until after PYTHONPATH
                # is set up.
                import pkg.server.repository as sr
                try:
                        repo = sr.repository_create(repodir,
                            properties=properties, version=version)
                        self.debug("created repository {0}".format(repodir))
                except sr.RepositoryExistsError:
                        # Already exists.
                        repo = sr.Repository(root=repodir,
                            properties=properties)
                return repo

        def get_repo(self, repodir, read_only=False):
                """ Convenience routine to help subclasses retrieve a
                    pkg.server.repository.Repository object for a given
                    path. """

                # Note that this must be deferred until after PYTHONPATH
                # is set up.
                import pkg.server.repository as sr
                return sr.Repository(read_only=read_only, root=repodir)

        def prep_depot(self, port, repodir, logpath, refresh_index=False,
            debug_features=EmptyI, properties=EmptyI, start=False):
                """ Convenience routine to help subclasses prepare
                    depots.  Returns a depotcontroller. """

                # Note that this must be deferred until after PYTHONPATH
                # is set up.
                import pkg.depotcontroller as depotcontroller

                self.debug("prep_depot: set depot port {0:d}".format(port))
                self.debug("prep_depot: set depot repository {0}".format(repodir))
                self.debug("prep_depot: set depot log to {0}".format(logpath))

                dc = depotcontroller.DepotController(
                    wrapper_start=self.coverage_cmd.split(),
                    env=self.coverage_env)
                dc.set_depotd_path(os.path.join(g_pkg_path,
                    "usr/lib/pkg.depotd"))
                dc.set_depotd_content_root(os.path.join(g_pkg_path,
                    "usr/share/lib/pkg"))
                for f in debug_features:
                        dc.set_debug_feature(f)
                dc.set_repodir(repodir)
                dc.set_logpath(logpath)
                dc.set_port(port)

                for section in properties:
                        for prop, val in six.iteritems(properties[section]):
                                dc.set_property(section, prop, val)
                if refresh_index:
                        dc.set_refresh_index()

                if start:
                        # If the caller requested the depot be started, then let
                        # the depot process create the repository.
                        self.debug("prep_depot: starting depot")
                        try:
                                dc.start()
                        except Exception as e:
                                self.debug("prep_depot: failed to start "
                                    "depot!: {0}".format(e))
                                raise
                        self.debug("depot on port {0} started".format(port))
                else:
                        # Otherwise, create the repository with the assumption
                        # that the caller wants that at the least, but doesn't
                        # need the depot server (yet).
                        self.create_repo(repodir, properties=properties)
                return dc

        def wait_repo(self, repodir, timeout=5.0):
                """Wait for the specified repository to complete its current
                operations before continuing."""

                check_interval = 0.20
                time.sleep(check_interval)

                begintime = time.time()
                ready = False
                while (time.time() - begintime) <= timeout:
                        status = self.get_repo(repodir).get_status()
                        rdata = status.get("repository", {})
                        repo_status = rdata.get("status", "")
                        if repo_status == "online":
                                for pubdata in rdata.get("publishers",
                                    {}).values():
                                        if pubdata.get("status", "") != "online":
                                                ready = False
                                                break
                                else:
                                        # All repository stores were ready.
                                        ready = True

                        if not ready:
                                time.sleep(check_interval)
                        else:
                                break

                if not ready:
                        raise RuntimeError("Repository readiness "
                            "timeout exceeded.")

        def _api_attach(self, api_obj, catch_wsie=True, **kwargs):
                self.debug("attach: {0}".format(str(kwargs)))
                for pd in api_obj.gen_plan_attach(**kwargs):
                        continue
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_detach(self, api_obj, catch_wsie=True, **kwargs):
                self.debug("detach: {0}".format(str(kwargs)))
                for pd in api_obj.gen_plan_detach(**kwargs):
                        continue
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_sync(self, api_obj, catch_wsie=True, **kwargs):
                self.debug("sync: {0}".format(str(kwargs)))
                for pd in api_obj.gen_plan_sync(**kwargs):
                        continue
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_install(self, api_obj, pkg_list, catch_wsie=True,
            show_licenses=False, accept_licenses=False, noexecute=False,
            **kwargs):
                self.debug("install {0}".format(" ".join(pkg_list)))

                plan = None
                for pd in api_obj.gen_plan_install(pkg_list,
                    noexecute=noexecute, **kwargs):

                        if plan is not None:
                                continue
                        plan = api_obj.describe()

                        # update license status
                        for pfmri, src, dest, accepted, displayed in \
                            plan.get_licenses():
                                api_obj.set_plan_license_status(pfmri,
                                    dest.license,
                                    displayed=show_licenses,
                                    accepted=accept_licenses)

                if noexecute:
                        return

                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_revert(self, api_obj, args, catch_wsie=True, noexecute=False,
            **kwargs):
                self.debug("revert {0}".format(" ".join(args)))
                for pd in api_obj.gen_plan_revert(args, **kwargs):
                        continue
                if noexecute:
                        return
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_dehydrate(self, api_obj, publishers=[], catch_wsie=True,
            noexecute=False, **kwargs):
                self.debug("dehydrate {0}".format(" ".join(publishers)))
                for pd in api_obj.gen_plan_dehydrate(publishers, **kwargs):
                        continue
                if noexecute:
                        return
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_rehydrate(self, api_obj, publishers=[], catch_wsie=True,
            noexecute=False, **kwargs):
                self.debug("rehydrate {0}".format(" ".join(publishers)))
                for pd in api_obj.gen_plan_rehydrate(publishers, **kwargs):
                        continue
                if noexecute:
                        return
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_fix(self, api_obj, args="", catch_wsie=True, noexecute=False,
            **kwargs):
                self.debug("planning fix")
                for pd in api_obj.gen_plan_fix(args, **kwargs):
                        continue
                if noexecute:
                        return
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_uninstall(self, api_obj, pkg_list, catch_wsie=True, **kwargs):
                self.debug("uninstall {0}".format(" ".join(pkg_list)))
                for pd in api_obj.gen_plan_uninstall(pkg_list, **kwargs):
                        continue
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_update(self, api_obj, catch_wsie=True, noexecute=False,
            **kwargs):
                self.debug("planning update")
                for pd in api_obj.gen_plan_update(noexecute=noexecute,
                    **kwargs):
                        continue
                if noexecute:
                        return
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_change_varcets(self, api_obj, catch_wsie=True, **kwargs):
                self.debug("change varcets: {0}".format(str(kwargs)))
                for pd in api_obj.gen_plan_change_varcets(**kwargs):
                        continue
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_finish(self, api_obj, catch_wsie=True):

                api_obj.prepare()
                try:
                        api_obj.execute_plan()
                except apx.WrapSuccessfulIndexingException:
                        if not catch_wsie:
                                raise
                api_obj.reset()

        def file_inode(self, path):
                """Return the inode number of a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                st = os.stat(file_path)
                return st.st_ino

        def file_size(self, path):
                """Return the size of a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                st = os.stat(file_path)
                return st.st_size

        def file_chmod(self, path, mode):
                """Change the mode of a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                os.chmod(file_path, mode)

        def file_chown(self, path, owner=None, group=None):
                """Change the ownership of a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                uid = pwd.getpwnam(owner).pw_uid
                gid = grp.getgrnam(group).gr_gid
                os.chown(file_path, uid, gid)

        def file_exists(self, path, mode=None, owner=None, group=None):
                """Assert the existence of a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                try:
                        st = os.stat(file_path)
                except OSError as e:
                        if e.errno == errno.ENOENT:
                                self.assertTrue(False,
                                    "File {0} does not exist".format(path))
                        else:
                                raise
                if mode is not None:
                        self.assertEqual(mode, stat.S_IMODE(st.st_mode))
                if owner is not None:
                        uid = pwd.getpwnam(owner).pw_uid
                        self.assertEqual(uid, st.st_uid)
                if group is not None:
                        gid = grp.getgrnam(group).gr_gid
                        self.assertEqual(gid, st.st_gid)

        def dir_exists(self, path, mode=None, owner=None, group=None):
                """Assert the existence of a directory in the image."""

                dir_path = os.path.join(self.get_img_path(), path)
                try:
                        st = os.stat(dir_path)
                except OSError as e:
                        if e.errno == errno.ENOENT:
                                self.assertTrue(False,
                                    "Directory {0} does not exist".format(path))
                        else:
                                raise
                if mode is not None:
                        self.assertEqual(mode, stat.S_IMODE(st.st_mode))
                if owner is not None:
                        uid = pwd.getpwnam(owner).pw_uid
                        self.assertEqual(uid, st.st_uid)
                if group is not None:
                        gid = grp.getgrnam(group).gr_gid
                        self.assertEqual(gid, st.st_gid)

        def file_doesnt_exist(self, path):
                """Assert the non-existence of a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                if os.path.exists(file_path):
                        self.assertTrue(False, "File {0} exists".format(path))

        def files_are_all_there(self, paths):
                """"Assert that files are there in the image."""
                for p in paths:
                        if p.endswith(os.path.sep):
                                file_path = os.path.join(self.get_img_path(), p)
                                if not os.path.isdir(file_path):
                                        if not os.path.exists(file_path):
                                                self.assertTrue(False,
                                                    "missing dir {0}".format(file_path))
                                        else:
                                                self.assertTrue(False,
                                                    "not dir: {0}".format(file_path))
                        else:
                                self.file_exists(p)

        def files_are_all_missing(self, paths):
                """Assert that files are all missing in the image."""
                for p in paths:
                        self.file_doesnt_exist(p)

        def file_remove(self, path):
                """Remove a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                portable.remove(file_path)

        def file_contains(self, path, strings, appearances=1):
                """Assert the existence of strings provided in a file in the
                image. The counting of appearances is line based. Repeated
                string on the same line will be count once."""

                if isinstance(strings, six.string_types):
                        strings = [strings]

                # Initialize a dict for counting appearances.
                sdict = {}
                for s in strings:
                        sdict[s] = appearances

                file_path = os.path.join(self.get_img_path(), path)
                try:
                        f = open(file_path)
                except:
                        self.assertTrue(False,
                            "File {0} does not exist or contain {1}".format(
                            path, strings))

                for line in f:
                        for k in sdict:
                                if k in line:
                                        sdict[k] -= 1
                        # If all counts become < 0, we know we have found all
                        # occurrences for all strings.
                        if all(v <= 0 for v in sdict.values()):
                                f.close()
                                break
                else:
                        f.close()
                        self.assertTrue(False, "File {0} does not contain {1} "
                            "{2}".format(path, appearances, strings))

        def file_doesnt_contain(self, path, strings):
                """Assert the non-existence of strings in a file in the image.
                """
                if isinstance(strings, six.string_types):
                        strings = [strings]

                file_path = os.path.join(self.get_img_path(), path)
                f = open(file_path)
                for line in f:
                        if any(s in line for s in strings):
                                f.close()
                                self.assertTrue(False, "File {0} contains any "
                                    "of {1}".format(path, strings))
                else:
                        f.close()

        def file_append(self, path, string):
                """Append a line to a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                with open(file_path, "a+") as f:
                        f.write("\n{0}\n".format(string))

        def seed_ta_dir(self, certs, dest_dir=None):
                if isinstance(certs, six.string_types):
                        certs = [certs]
                if not dest_dir:
                        dest_dir = self.ta_dir
                self.assertTrue(dest_dir)
                self.assertTrue(self.raw_trust_anchor_dir)
                for c in certs:
                        name = "{0}_cert.pem".format(c)
                        portable.copyfile(
                            os.path.join(self.raw_trust_anchor_dir, name),
                            os.path.join(dest_dir, name))

        def create_some_files(self, paths):
                ubin = portable.get_user_by_name("bin", None, False)
                groot = portable.get_group_by_name("root", None, False)
                for p in paths:
                        if p.startswith(os.path.sep):
                                p = p[1:]
                        file_path = os.path.join(self.get_img_path(), p)
                        dirpath = os.path.dirname(file_path)
                        if not os.path.exists(dirpath):
                                os.mkdir(dirpath)
                        if p.endswith(os.path.sep):
                                continue
                        with open(file_path, "a+") as f:
                                f.write("\ncontents\n")
                        os.chown(file_path, ubin, groot)
                        os.chmod(file_path, misc.PKG_RO_FILE_MODE)


class ManyDepotTestCase(CliTestCase):

        def __init__(self, methodName="runTest"):
                super(ManyDepotTestCase, self).__init__(methodName)
                self.dcs = {}

        def setUp(self, publishers, debug_features=EmptyI, start_depots=False,
            image_count=1):
                CliTestCase.setUp(self, image_count=image_count)

                self.debug("setup: {0}".format(self.id()))
                self.debug("creating {0:d} repo(s)".format(len(publishers)))
                self.debug("publishers: {0}".format(publishers))
                self.debug("debug_features: {0}".format(list(debug_features)))
                self.dcs = {}

                for n, pub in enumerate(publishers):
                        i = n + 1
                        testdir = os.path.join(self.test_root)

                        try:
                                os.makedirs(testdir, 0o755)
                        except OSError as e:
                                if e.errno != errno.EEXIST:
                                        raise e

                        depot_logfile = os.path.join(testdir,
                            "depot_logfile{0:d}".format(i))

                        props = { "publisher": { "prefix": pub } }

                        # We pick an arbitrary base port.  This could be more
                        # automated in the future.
                        repodir = os.path.join(testdir, "repo_contents{0:d}".format(i))
                        self.dcs[i] = self.prep_depot(self.next_free_port,
                            repodir,
                            depot_logfile, debug_features=debug_features,
                            properties=props, start=start_depots)
                        self.next_free_port += 1

        def check_traceback(self, logpath):
                """ Scan logpath looking for tracebacks.
                    Raise a DepotTracebackException if one is seen.
                """
                self.debug("check for depot tracebacks in {0}".format(logpath))
                logfile = open(logpath, "r")
                output = logfile.read()
                for line in output.splitlines():
                        if line.find("Traceback") > -1:
                                raise DepotTracebackException(logpath, output)
                logfile.close()

        def restart_depots(self):
                self.debug("restarting {0:d} depot(s)".format(len(self.dcs)))
                for i in sorted(self.dcs.keys()):
                        dc = self.dcs[i]
                        self.debug("stopping depot at url: {0}".format(dc.get_depot_url()))
                        dc.stop()
                        self.debug("starting depot at url: {0}".format(dc.get_depot_url()))
                        dc.start()

        def killall_sighandler(self, signum, frame):
                print("Ctrl-C: I'm killing depots, please wait.\n",
                    file=sys.stderr)
                print(self)
                self.signalled = True

        def killalldepots(self):
                self.signalled = False
                self.debug("killalldepots: {0}".format(self.id()))

                oldhdlr = signal.signal(signal.SIGINT, self.killall_sighandler)

                try:
                        check_dc = []
                        for i in sorted(self.dcs.keys()):
                                dc = self.dcs[i]
                                if not dc.started:
                                        continue
                                check_dc.append(dc)
                                path = dc.get_repodir()
                                self.debug("stopping depot at url: {0}, {1}".format(
                                    dc.get_depot_url(), path))

                                status = 0
                                try:
                                        status = dc.kill()
                                except Exception:
                                        pass

                                if status:
                                        self.debug("depot: {0}".format(status))

                        for dc in check_dc:
                                try:
                                        self.check_traceback(dc.get_logpath())
                                except Exception:
                                        pass
                finally:
                        signal.signal(signal.SIGINT, oldhdlr)

                self.dcs = {}
                if self.signalled:
                        raise KeyboardInterrupt("Ctrl-C while killing depots.")

        def tearDown(self):
                self.debug("ManyDepotTestCase.tearDown: {0}".format(self.id()))

                self.killalldepots()
                CliTestCase.tearDown(self)

        def run(self, result=None):
                if result is None:
                        result = self.defaultTestResult()
                CliTestCase.run(self, result)


class ApacheDepotTestCase(ManyDepotTestCase):
        """A TestCase that uses one or more Apache instances in the course of
        its work, along with potentially one or more DepotControllers.
        """

        def __init__(self, methodName="runTest"):
                super(ManyDepotTestCase, self).__init__(methodName)
                self.dcs = {}
                self.acs = {}

        def register_apache_controller(self, name, ac):
                """Registers an ApacheController with this TestCase.
                We include this method here to make it easier to kill any
                instances of Apache that were left floating around at the end
                of the test.

                We enforce the use of this method in
                <ApacheController>.start() by refusing to start instances until
                they are registered, which makes the test suite as a whole more
                resilient, when setting up and tearing down test classes."""

                if name in self.acs:
                        # registering an Apache controller that is already
                        # registered causes us to kill the existing controller
                        # first.
                        try:
                                self.acs[name].stop()
                        except Exception as e:
                                try:
                                        self.acs[name].kill()
                                except Exception as e:
                                        pass
                self.acs[name] = ac

        def __get_ac(self):
                """If we only use a single ApacheController, self.ac will
                return that controller, otherwise we return None."""
                if self.acs and len(self.acs) == 1:
                        return self.acs[list(self.acs.keys())[0]]
                else:
                        return None

        def killalldepots(self):
                try:
                        ManyDepotTestCase.killalldepots(self)
                finally:
                        for name, ac in self.acs.items():
                                self.debug("stopping apache controller {0}".format(
                                    name))
                                try:
                                        ac.stop()
                                except Exception as e :
                                        try:
                                                self.debug("killing apache "
                                                    "instance {0}".format(name))
                                                ac.kill()
                                        except Exception as e:
                                                self.debug("Unable to kill "
                                                    "apache instance {0}. This "
                                                    "could cause subsequent "
                                                    "tests to fail.".format(name))

        # ac is a readonly property which returns a registered ApacheController
        # provided there is exactly one registered, for convenience of writing
        # test cases.
        ac = property(fget=__get_ac)

class HTTPSTestClass(ApacheDepotTestCase):
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        def pkg(self, command, *args, **kwargs):
                # The value for ssl_ca_file is pulled from DebugValues because
                # ssl_ca_file needs to be set there so the api object calls work
                # as desired.
                command = "--debug ssl_ca_file={0} {1}".format(
                    DebugValues["ssl_ca_file"], command)
                return ApacheDepotTestCase.pkg(self, command,
                    *args, **kwargs)

        def pkgrecv(self, command, *args, **kwargs):
                # The value for ssl_ca_file is pulled from DebugValues because
                # ssl_ca_file needs to be set there so the api object calls work
                # as desired.
                command = "{0} --debug ssl_ca_file={1}".format(
                    command, DebugValues["ssl_ca_file"])
                return ApacheDepotTestCase.pkgrecv(self, command,
                    *args, **kwargs)

        def pkgsend(self, command, *args, **kwargs):
                # The value for ssl_ca_file is pulled from DebugValues because
                # ssl_ca_file needs to be set there so the api object calls work
                # as desired.
                command = "{0} --debug ssl_ca_file={1}".format(
                    command, DebugValues["ssl_ca_file"])
                return ApacheDepotTestCase.pkgsend(self, command,
                    *args, **kwargs)

        def pkgrepo(self, command, *args, **kwargs):
                # The value for ssl_ca_file is pulled from DebugValues because
                # ssl_ca_file needs to be set there so the api object calls work
                # as desired.
                command = "--debug ssl_ca_file={0} {1}".format(
                    DebugValues["ssl_ca_file"], command)
                return ApacheDepotTestCase.pkgrepo(self, command,
                    *args, **kwargs)

        def seed_ta_dir(self, certs, dest_dir=None):
                if isinstance(certs, six.string_types):
                        certs = [certs]
                if not dest_dir:
                        dest_dir = self.ta_dir
                self.assertTrue(dest_dir)
                self.assertTrue(self.raw_trust_anchor_dir)
                for c in certs:
                        name = "{0}_cert.pem".format(c)
                        portable.copyfile(
                            os.path.join(self.raw_trust_anchor_dir, name),
                            os.path.join(dest_dir, name))
                        DebugValues["ssl_ca_file"] = os.path.join(dest_dir,
                            name)

        def get_cli_cert(self, publisher):
                ta = self.pub_ta_map[publisher]
                return "cs1_ta{0:d}_cert.pem".format(ta)

        def get_cli_key(self, publisher):
                ta = self.pub_ta_map[publisher]
                return "cs1_ta{0:d}_key.pem".format(ta)

        def get_pub_ta(self, publisher):
                ta = self.pub_ta_map[publisher]
                return "ta{0:d}".format(ta)

        def setUp(self, publishers, start_depots=True):

                # We only have 5 usable CA certs and there are not many usecases
                # for setting up more than 5 different SSL-secured depots.
                assert len(publishers) < 6

                # Maintains a mapping of which TA is used for which publisher
                self.pub_ta_map = {}

                ApacheDepotTestCase.setUp(self, publishers,
                    start_depots=True)
                self.testdata_dir = os.path.join(self.test_root, "testdata")

                # Set up the directories that apache needs.
                self.apache_dir = os.path.join(self.test_root, "apache")
                os.makedirs(self.apache_dir)
                self.apache_log_dir = os.path.join(self.apache_dir,
                    "apache_logs")
                os.makedirs(self.apache_log_dir)
                self.apache_content_dir = os.path.join(self.apache_dir,
                    "apache_content")
                self.pidfile = os.path.join(self.apache_dir, "httpd.pid")
                self.common_config_dir = os.path.join(self.test_root,
                    "apache-serve")

                # Choose ports for apache to run on.
                self.https_port = self.next_free_port
                self.next_free_port += 1
                self.proxy_port = self.next_free_port
                self.next_free_port += 1
                self.bad_proxy_port = self.next_free_port
                self.next_free_port += 1

                # Set up the paths to the certificates that will be needed.
                self.path_to_certs = os.path.join(self.ro_data_root,
                    "signing_certs", "produced")
                self.keys_dir = os.path.join(self.path_to_certs, "keys")
                self.cs_dir = os.path.join(self.path_to_certs,
                    "code_signing_certs")
                self.chain_certs_dir = os.path.join(self.path_to_certs,
                    "chain_certs")
                self.pub_cas_dir = os.path.join(self.path_to_certs,
                    "publisher_cas")
                self.inter_certs_dir = os.path.join(self.path_to_certs,
                    "inter_certs")
                self.raw_trust_anchor_dir = os.path.join(self.path_to_certs,
                    "trust_anchors")
                self.crl_dir = os.path.join(self.path_to_certs, "crl")

                location_tags = ""
                # Usable CA certs are ta6 to ta11 with the exception of ta7.
                # We already checked that not more than 5 publishers have been
                # requested.
                count = 6
                for dc in self.dcs:
                        # Create a <Location> tag for each publisher. The server
                        # path is set to the publisher name.
                        if count == 7:
                                # TA7 needs password to unlock cert, don't use
                                count += 1
                        dc_pub = self.dcs[dc].get_property("publisher",
                            "prefix")
                        self.pub_ta_map[dc_pub] = count
                        loc_dict = {
                            "server-path":dc_pub,
                            "server-ca-taname":"ta{0:d}".format(count),
                            "ssl-special":"%{SSL_CLIENT_I_DN_OU}",
                            "proxied-server":self.dcs[dc].get_depot_url(),
                        }

                        location_tags += loc_tag.format(**loc_dict)
                        count += 1

                conf_dict = {
                    "common_log_format": "%h %l %u %t \\\"%r\\\" %>s %b",
                    "https_port": self.https_port,
                    "proxy_port": self.proxy_port,
                    "bad_proxy_port": self.bad_proxy_port,
                    "log_locs": self.apache_log_dir,
                    "pidfile": self.pidfile,
                    "port": self.https_port,
                    "serve_root": self.apache_content_dir,
                    "server-ssl-cert":os.path.join(self.cs_dir,
                        "cs1_ta7_cert.pem"),
                    "server-ssl-key":os.path.join(self.keys_dir,
                        "cs1_ta7_key.pem"),
                    "server-ca-cert":os.path.join(self.path_to_certs, "combined_cas.pem"),
                    "location-tags":location_tags,
                }

                self.https_conf_path = os.path.join(self.test_root,
                    "https.conf")
                with open(self.https_conf_path, "w") as fh:
                        fh.write(self.https_conf.format(**conf_dict))

                ac = ApacheController(self.https_conf_path,
                    self.https_port, self.common_config_dir, https=True,
                    testcase=self)
                self.register_apache_controller("default", ac)

        https_conf = r"""\
# Configuration and logfile names: If the filenames you specify for many
# of the server's control files begin with "/" (or "drive:/" for Win32), the
# server will use that explicit path.  If the filenames do *not* begin
# with "/", the value of ServerRoot is prepended -- so "logs/access_log"
# with ServerRoot set to "/usr/apache2/2.4" will be interpreted by the
# server as "/usr/apache2/2.4/logs/foo_log", whereas "/logs/access_log"
# will be interpreted as "/logs/access_log".

#
# ServerRoot: The top of the directory tree under which the server's
# configuration, error, and log files are kept.
#
# Do not add a slash at the end of the directory path.  If you point
# ServerRoot at a non-local disk, be sure to point the LockFile directive
# at a local disk.  If you wish to share the same ServerRoot for multiple
# httpd daemons, you will need to change at least LockFile and PidFile.
#
ServerRoot "/usr/apache2/2.4"

PidFile "{pidfile}"

#
# Listen: Allows you to bind Apache to specific IP addresses and/or
# ports, instead of the default. See also the <VirtualHost>
# directive.
#
# Change this to Listen on specific IP addresses as shown below to
# prevent Apache from glomming onto all bound IP addresses.
#
Listen 0.0.0.0:{https_port}

# We also make ourselves a general-purpose proxy. This is not needed for the
# SSL reverse-proxying to the pkg.depotd, but allows us to test that pkg(1)
# can communicate to HTTPS origins using a proxy.
Listen 0.0.0.0:{proxy_port}
Listen 0.0.0.0:{bad_proxy_port}

#
# Dynamic Shared Object (DSO) Support
#
# To be able to use the functionality of a module which was built as a DSO you
# have to place corresponding `LoadModule' lines at this location so the
# directives contained in it are actually available _before_ they are used.
# Statically compiled modules (those listed by `httpd -l') do not need
# to be loaded here.
#

LoadModule access_compat_module libexec/mod_access_compat.so
LoadModule alias_module libexec/mod_alias.so
LoadModule authn_core_module libexec/mod_authn_core.so
LoadModule authz_core_module libexec/mod_authz_core.so
LoadModule authz_host_module libexec/mod_authz_host.so
LoadModule cache_module libexec/mod_cache.so
LoadModule deflate_module libexec/mod_deflate.so
LoadModule dir_module libexec/mod_dir.so
LoadModule env_module libexec/mod_env.so
LoadModule filter_module libexec/mod_filter.so
LoadModule headers_module libexec/mod_headers.so
LoadModule log_config_module libexec/mod_log_config.so
LoadModule mime_module libexec/mod_mime.so
LoadModule mpm_worker_module libexec/mod_mpm_worker.so
LoadModule rewrite_module libexec/mod_rewrite.so
LoadModule ssl_module libexec/mod_ssl.so
LoadModule proxy_module libexec/mod_proxy.so
LoadModule proxy_connect_module libexec/mod_proxy_connect.so
LoadModule proxy_http_module libexec/mod_proxy_http.so
LoadModule unixd_module libexec/mod_unixd.so

<IfModule unixd_module>
#
# If you wish httpd to run as a different user or group, you must run
# httpd as root initially and it will switch.
#
# User/Group: The name (or #number) of the user/group to run httpd as.
# It is usually good practice to create a dedicated user and group for
# running httpd, as with most system services.
#
User webservd
Group webservd

</IfModule>

# 'Main' server configuration
#
# The directives in this section set up the values used by the 'main'
# server, which responds to any requests that aren't handled by a
# <VirtualHost> definition.  These values also provide defaults for
# any <VirtualHost> containers you may define later in the file.
#
# All of these directives may appear inside <VirtualHost> containers,
# in which case these default settings will be overridden for the
# virtual host being defined.
#

#
# ServerName gives the name and port that the server uses to identify itself.
# This can often be determined automatically, but we recommend you specify
# it explicitly to prevent problems during startup.
#
# If your host doesn't have a registered DNS name, enter its IP address here.
#
ServerName 127.0.0.1

#
# DocumentRoot: The directory out of which you will serve your
# documents. By default, all requests are taken from this directory, but
# symbolic links and aliases may be used to point to other locations.
#
DocumentRoot "/"

#
# Each directory to which Apache has access can be configured with respect
# to which services and features are allowed and/or disabled in that
# directory (and its subdirectories).
#
# First, we configure the "default" to be a very restrictive set of
# features.
#
<Directory />
    Options None
    AllowOverride None
    Require all denied
</Directory>

#
# Note that from this point forward you must specifically allow
# particular features to be enabled - so if something's not working as
# you might expect, make sure that you have specifically enabled it
# below.
#

#
# This should be changed to whatever you set DocumentRoot to.
#

#
# DirectoryIndex: sets the file that Apache will serve if a directory
# is requested.
#
<IfModule dir_module>
    DirectoryIndex index.html
</IfModule>

#
# The following lines prevent .htaccess and .htpasswd files from being
# viewed by Web clients.
#
<FilesMatch "^\.ht">
    Require all denied
</FilesMatch>

#
# ErrorLog: The location of the error log file.
# If you do not specify an ErrorLog directive within a <VirtualHost>
# container, error messages relating to that virtual host will be
# logged here.  If you *do* define an error logfile for a <VirtualHost>
# container, that host's errors will be logged there and not here.
#
ErrorLog "{log_locs}/error_log"

#
# LogLevel: Control the number of messages logged to the error_log.
# Possible values include: debug, info, notice, warn, error, crit,
# alert, emerg.
#
LogLevel debug



<IfModule log_config_module>
    #
    # The following directives define some format nicknames for use with
    # a CustomLog directive (see below).
    #
    LogFormat "{common_log_format}" common
    LogFormat "PROXY {common_log_format}" proxylog

    #
    # The location and format of the access logfile (Common Logfile Format).
    # If you do not define any access logfiles within a <VirtualHost>
    # container, they will be logged here.  Contrariwise, if you *do*
    # define per-<VirtualHost> access logfiles, transactions will be
    # logged therein and *not* in this file.
    #
    CustomLog "{log_locs}/access_log" common
</IfModule>

<IfModule mime_module>
    #
    # TypesConfig points to the file containing the list of mappings from
    # filename extension to MIME-type.
    #
    TypesConfig /etc/apache2/2.4/mime.types

    #
    # AddType allows you to add to or override the MIME configuration
    # file specified in TypesConfig for specific file types.
    #
    AddType application/x-compress .Z
    AddType application/x-gzip .gz .tgz

    # Add a new mime.type for .p5i file extension so that clicking on
    # this file type on a web page launches PackageManager in a Webinstall mode.
    AddType application/vnd.pkg5.info .p5i
</IfModule>

#
# Note: The following must must be present to support
#       starting without SSL on platforms with no /dev/random equivalent
#       but a statically compiled-in mod_ssl.
#
<IfModule ssl_module>
SSLRandomSeed startup builtin
SSLRandomSeed connect builtin
</IfModule>

<VirtualHost 0.0.0.0:{https_port}>
        AllowEncodedSlashes On
        ProxyRequests Off
        MaxKeepAliveRequests 10000

        SSLEngine On

        # Cert paths
        SSLCertificateFile {server-ssl-cert}
        SSLCertificateKeyFile {server-ssl-key}

        # Combined product CA certs for client verification
        SSLCACertificateFile {server-ca-cert}

	SSLVerifyClient require

        {location-tags}

</VirtualHost>

#
# We configure this Apache instance as a general-purpose HTTP proxy, accepting
# requests from localhost, and allowing CONNECTs to our HTTPS port
#
<VirtualHost 0.0.0.0:{proxy_port}>
        <Proxy *>
                Require local
        </Proxy>
        AllowCONNECT {https_port}
        ProxyRequests on
        CustomLog "{log_locs}/proxy_access_log" proxylog
</VirtualHost>

<VirtualHost 0.0.0.0:{bad_proxy_port}>
        <Proxy *>
                Require local
        </Proxy>
#  We purposely prevent this proxy from being able to connect to our SSL
#  port, making sure that when we point pkg(1) to this bad proxy, operations
#  will fail - the following line is commented out:
#        AllowCONNECT {https_port}
        ProxyRequests on
        CustomLog "{log_locs}/badproxy_access_log" proxylog

</VirtualHost>
"""

loc_tag = """
        <Location /{server-path}>
                SSLVerifyDepth 1

	        # The client's certificate must pass verification, and must have
	        # a CN which matches this repository.
                SSLRequire ( {ssl-special} =~ m/{server-ca-taname}/ )

                # set max to number of threads in depot
                ProxyPass {proxied-server} nocanon max=500
        </Location>
"""


class SingleDepotTestCase(ManyDepotTestCase):

        def setUp(self, debug_features=EmptyI, publisher="test",
            start_depot=False, image_count=1):
                ManyDepotTestCase.setUp(self, [publisher],
                    debug_features=debug_features, start_depots=start_depot,
                    image_count=image_count)

        def __get_dc(self):
                if self.dcs:
                        return self.dcs[1]
                else:
                        return None

        @property
        def durl(self):
                return self.dc.get_depot_url()

        @property
        def rurl(self):
                return self.dc.get_repo_url()

        # dc is a readonly property which is an alias for self.dcs[1],
        # for convenience of writing test cases.
        dc = property(fget=__get_dc)


class SingleDepotTestCaseCorruptImage(SingleDepotTestCase):
        """ A class which allows manipulation of the image directory that
        SingleDepotTestCase creates. Specifically, it supports removing one
        or more of the files or subdirectories inside an image (publisher,
        cfg_cache, etc...) in a controlled way.

        To add a new directory or file to be corrupted, it will be necessary
        to update corrupt_image_create to recognize a new option in config
        and perform the appropriate action (removing the directory or file
        for example).
        """

        def setUp(self, debug_features=EmptyI, publisher="test",
            start_depot=False):
                SingleDepotTestCase.setUp(self, debug_features=debug_features,
                    publisher=publisher, start_depot=start_depot)

                self.__imgs_path_backup = {}

        def tearDown(self):
                SingleDepotTestCase.tearDown(self)

        def backup_img_path(self, ii=None):
                if ii != None:
                        return self.__imgs_path_backup[ii]
                return self.__imgs_path_backup[self.img_index()]

        def corrupt_image_create(self, repourl, config, subdirs, prefix="test",
            destroy=True):
                """ Creates two levels of directories under the original image
                directory. In the first level (called bad), it builds a "corrupt
                image" which means it builds subdirectories the subdirectories
                specified by subdirs (essentially determining whether a user
                image or a full image will be built). It populates these
                subdirectories with a partial image directory stucture as
                specified by config. As another subdirectory of bad, it
                creates a subdirectory called final which represents the
                directory the command was actually run from (which is why
                img_path is set to that location). Existing image destruction
                was made optional to allow testing of two images installed next
                to each other (a user and full image created in the same
                directory for example). """

                ii = self.img_index()
                if ii not in self.__imgs_path_backup:
                        self.__imgs_path_backup[ii] = self.img_path()

                self.set_img_path(os.path.join(self.img_path(), "bad"))

                if destroy:
                        self.image_destroy()

                for s in subdirs:
                        if s == "var/pkg":
                                cmdline = "image-create -F -p {0}={1} {2}".format(
                                    prefix, repourl, self.img_path())
                        elif s == ".org.opensolaris,pkg":
                                cmdline = "image-create -U -p {0}={1} {2}".format(
                                    prefix, repourl, self.img_path())
                        else:
                                raise RuntimeError("Got unknown subdir option:"
                                    "{0}\n".format(s))

                        cmdline = sys.executable + " " + self.pkg_cmdpath + \
                            " " + cmdline
                        self.cmdline_run(cmdline, exit=0)

                        tmpDir = os.path.join(self.img_path(), s)

                        # This is where the actual corruption of the
                        # image takes place. A normal image was created
                        # above and this goes in and removes critical
                        # directories and files.
                        if "publisher_absent" in config or \
                           "publisher_empty" in config:
                                shutil.rmtree(os.path.join(tmpDir, "publisher"))
                        if "known_absent" in config or \
                           "known_empty" in config:
                                shutil.rmtree(os.path.join(tmpDir, "state",
                                    "known"))
                        if "known_empty" in config:
                                os.mkdir(os.path.join(tmpDir, "state", "known"))
                        if "publisher_empty" in config:
                                os.mkdir(os.path.join(tmpDir, "publisher"))
                        if "cfg_cache_absent" in config:
                                os.remove(os.path.join(tmpDir, "pkg5.image"))
                        if "index_absent" in config:
                                shutil.rmtree(os.path.join(tmpDir, "cache",
                                    "index"))

                # Make find root start at final. (See the doc string for
                # more explanation.)
                cmd_path = os.path.join(self.img_path(), "final")

                os.mkdir(cmd_path)
                return cmd_path

def debug(s):
        s = str(s)
        for x in s.splitlines():
                if g_debug_output:
                        print("# {0}".format(x), file=sys.stderr)

def mkdir_eexist_ok(p):
        try:
                os.mkdir(p)
        except OSError as e:
                if e.errno != errno.EEXIST:
                        raise e

def env_sanitize(pkg_cmdpath, dv_keep=None):
        if dv_keep == None:
                dv_keep = []

        dv_saved = {}
        for dv in dv_keep:
                # save some DebugValues settings
                dv_saved[dv] = DebugValues[dv]

        # clear any existing DebugValues settings
        DebugValues.clear()

        # clear misc environment variables
        for e in ["PKG_CMDPATH"]:
                if e in os.environ:
                        del os.environ[e]

        # Set image path to a path that's not actually an
        # image to force failure of tests that don't
        # explicitly provide an image root either through the
        # default behaviour of the pkg() helper routine or
        # another method.
        os.environ["PKG_IMAGE"] = g_tempdir

        # Test suite should never attempt to access the
        # live root image.
        os.environ["PKG_NO_LIVE_ROOT"] = "1"

        # Pkg interfaces should never know they are being
        # run from within the test suite.
        os.environ["PKG_NO_RUNPY_CMDPATH"] = "1"

        # verify PlanDescription serialization and that the PlanDescription
        # isn't modified while we're preparing to for execution.
        DebugValues["plandesc_validate"] = 1
        os.environ["PKG_PLANDESC_VALIDATE"] = "1"

        # Pretend that we're being run from the fakeroot image.
        assert pkg_cmdpath != "TOXIC"
        DebugValues["simulate_cmdpath"] = pkg_cmdpath

        # Update the path to smf commands
        for dv in dv_keep:
                DebugValues[dv] = dv_saved[dv]

        # always get detailed data from the solver
        DebugValues["plan"] = True

def fakeroot_create():

        test_root = os.path.join(g_tempdir, "ips.test.{0:d}".format(os.getpid()))
        fakeroot = os.path.join(test_root, "fakeroot")
        cmd_path = os.path.join(fakeroot, "pkg")

        try:
                os.stat(cmd_path)
        except OSError as e:
                pass
        else:
                # fakeroot already exists
                raise RuntimeError("The fakeroot shouldn't already exist.\n"
                    "Path is:{0}".format(cmd_path))

        # when creating the fakeroot we want to make sure pkg doesn't
        # touch the real root.
        env_sanitize(cmd_path)

        #
        # When accessing images via the pkg apis those apis will try
        # to access the image containing the command from which the
        # apis were invoked.  Normally when running the test suite the
        # command is run.py in a developers workspace, and that
        # workspace lives in the root image.  But accessing the root
        # image during a test suite run is verboten.  Hence, here we
        # create a temporary image from which we can run the pkg
        # command.
        #

        # create directories
        mkdir_eexist_ok(test_root)
        mkdir_eexist_ok(fakeroot)

        debug("fakeroot image create {0}".format(fakeroot))
        progtrack = pkg.client.progress.NullProgressTracker()
        api_inst = pkg.client.api.image_create(PKG_CLIENT_NAME,
            CLIENT_API_VERSION, fakeroot,
            pkg.client.api.IMG_TYPE_ENTIRE, False,
            progtrack=progtrack, cmdpath=cmd_path)

        #
        # put a copy of the pkg command in our fake root directory.
        # we do this because when recursive linked image commands are
        # run, the pkg interfaces may fork and exec additional copies
        # of pkg(1), and in this case we want them to run the copy of
        # pkg from the fake root.
        #
        fakeroot_cmdpath = os.path.join(fakeroot, "pkg")
        shutil.copy(os.path.join(g_pkg_path, "usr", "bin", "pkg"),
            fakeroot_cmdpath)

        return fakeroot, fakeroot_cmdpath

def eval_assert_raises(ex_type, eval_ex_func, func, *args):
        try:
                func(*args)
        except ex_type as e:
                print(str(e))
                if not eval_ex_func(e):
                        raise
        else:
                raise RuntimeError("Function did not raise exception.")

class ApacheStateException(Exception):
        pass

class ApacheController(object):

        def __init__(self, conf, port, work_dir, testcase=None, https=False):
                """
                The 'conf' parameter is a path to a httpd.conf file.  The 'port'
                parameter is a port to run on.  The 'work_dir' is a temporary
                directory to store runtime state.  The 'testcase' parameter is
                the ApacheDepotTestCase to use when writing output.  The 'https'
                parameter is a boolean indicating whether this instance expects
                to be contacted via https or not.
                """

                self.apachectl = "/usr/apache2/2.4/bin/apachectl"
                if not os.path.exists(work_dir):
                        os.makedirs(work_dir)
                self.__conf_path = os.path.join(work_dir, "httpd.conf")
                self.__port = port
                self.__repo_hdl = None
                self.__starttime = 0
                self.__state = "stopped"
                if not testcase:
                        raise RuntimeError("No testcase parameter specified")
                self.__tc = testcase
                prefix = "http"
                if https:
                        prefix = "https"
                self.__url = "{0}://localhost:{1:d}".format(prefix, self.__port)
                portable.copyfile(conf, self.__conf_path)

        def __set_conf(self, path):
                portable.copyfile(path, self.__conf_path)
                if self.__state == "started":
                        self.restart()

        def __get_conf(self):
                return self.__conf_path

        conf = property(__get_conf, __set_conf)

        def _network_ping(self):
                try:
                        urlopen(self.__url)
                except HTTPError as e:
                        if e.code == http_client.FORBIDDEN:
                                return True
                        return False
                except URLError as e:
                        if isinstance(e.reason, ssl.SSLError):
                                return True
                        return False
                return True

        def debug(self, msg):
                if self.__tc:
                        self.__tc.debug(msg)

        def debugresult(self, result, expected, msg):
                if self.__tc:
                        self.__tc.debugresult(result, expected, msg)

        def start(self):
                if self not in self.__tc.acs.values():
                        # An attempt to start an ApacheController that has not
                        # been registered can result in it not getting cleaned
                        # up properly when the test completes, which can cause
                        # other tests to fail. We don't allow that to happen.
                        raise RuntimeError(
                            "This ApacheController has not been registered with"
                            " the ApacheDepotTestCase {0} using "
                            "set_apache_controller(name, ac)".format(self.__tc))

                if self._network_ping():
                        raise ApacheStateException("A depot (or some " +
                            "other network process) seems to be " +
                            "running on port {0:d} already!".format(self.__port))
                cmdline = ["/usr/bin/setpgrp", self.apachectl, "-f",
                    self.__conf_path, "-k", "start", "-DFOREGROUND"]
                try:
                        self.__starttime = time.time()
                        # change the state so that we try to do work in
                        # self.stop() in the face of a False result from
                        # is_alive()
                        self.__state = "starting"
                        self.debug(" ".join(cmdline))
                        self.__repo_hdl = subprocess.Popen(cmdline, shell=False,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
                        if self.__repo_hdl is None:
                                self.__state = "stopped"
                                raise ApacheStateException("Could not start "
                                    "apache")
                        begintime = time.time()

                        check_interval = 0.20
                        contact = False
                        while (time.time() - begintime) <= 40.0:
                                rc = self.__repo_hdl.poll()
                                if rc is not None:
                                        self.__state = "stopped"
                                        raise ApacheStateException("Apache "
                                            "exited unexpectedly while "
                                            "starting (exit code {0:d})".format(rc))

                                if self.is_alive():
                                        contact = True
                                        break
                                time.sleep(check_interval)

                        if contact == False:
                                self.stop()
                                raise ApacheStateException("Apache did not "
                                    "respond to repeated attempts to make "
                                    "contact")
                        self.__state = "started"
                except KeyboardInterrupt:
                        if self.__repo_hdl:
                                self.kill(now=True)
                        raise

        def kill(self, now=False):
                if not self.__repo_hdl:
                        return
                try:
                        lifetime = time.time() - self.__starttime
                        if now == False and lifetime < 1.0:
                                time.sleep(1.0 - lifetime)
                finally:
                        try:
                                os.kill(-1 * self.__repo_hdl.pid,
                                    signal.SIGKILL)
                        except OSError:
                                pass
                        self.__repo_hdl.wait()
                        self.__state = "killed"

        def stop(self):
                if self.__state == "stopped":
                        return
                cmdline = [self.apachectl, "-f", self.__conf_path, "-k",
                    "stop"]

                try:
                        hdl = subprocess.Popen(cmdline, shell=False,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
                        stop_output, stop_errout = hdl.communicate()
                        stop_retcode = hdl.returncode

                        self.debugresult(stop_retcode, 0, stop_output)

                        if stop_errout != "":
                                self.debug(stop_errout)
                        if stop_output != "":
                                self.debug(stop_output)

                        if stop_retcode != 0:
                                self.kill(now=True)
                        else:
                                self.__state = "stopped"

                        # Ensure that the apache process gets shutdown
                        begintime = time.time()

                        check_interval = 0.20
                        stopped = False
                        while (time.time() - begintime) <= 40.0:
                                rc = self.__repo_hdl.poll()
                                if rc is not None:
                                        stopped = True
                                        break
                                time.sleep(check_interval)
                        if not stopped:
                                self.kill(now=True)

                        # retrieve output from the apache process we've just
                        # stopped
                        output, errout = self.__repo_hdl.communicate()
                        self.debug(errout)
                except KeyboardInterrupt:
                        self.kill(now=True)
                        raise

        def restart(self):
                self.stop()
                self.start()

        def chld_sighandler(self, signum, frame):
                pass

        def killall_sighandler(self, signum, frame):
                print("Ctrl-C: I'm killing depots, please wait.\n",
                    file=sys.stderr)
                print(self)
                self.signalled = True

        def is_alive(self):
                """ First, check that the depot process seems to be alive.
                    Then make a little HTTP request to see if the depot is
                    responsive to requests """

                if self.__repo_hdl == None:
                        return False

                status = self.__repo_hdl.poll()
                if status != None:
                        return False
                return self._network_ping()

        @property
        def url(self):
                return self.__url

class SysrepoController(ApacheController):

        def __init__(self, conf, port, work_dir, testcase=None, https=False):
                ApacheController.__init__(self, conf, port, work_dir,
                    testcase=testcase, https=https)
                self.apachectl = "/usr/apache2/2.4/bin/apachectl"

        def _network_ping(self):
                try:
                        urlopen(urljoin(self.url, "syspub/0"))
                except HTTPError as e:
                        if e.code == http_client.FORBIDDEN:
                                return True
                        return False
                except URLError:
                        return False
                return True


class HttpDepotController(ApacheController):

        def __init__(self, conf, port, work_dir, testcase=None, https=False):
                ApacheController.__init__(self, conf, port, work_dir,
                    testcase=testcase, https=https)
                self.apachectl = "/usr/apache2/2.4/bin/apachectl"

        def _network_ping(self):
                try:
                        # Ping the versions URL, rather than the default /
                        # so that we don't initialize the BUI code yet.
                        repourl = urljoin(self.url, "versions/0")
                        # Disable SSL peer verification, we just want to check
                        # if the depot is running.
                        urlopen(repourl,
                            context=ssl._create_unverified_context())
                except HTTPError as e:
                        if e.code == http_client.FORBIDDEN:
                                return True
                        return False
                except URLError:
                        return False
                return True

