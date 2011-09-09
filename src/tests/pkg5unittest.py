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

# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.

#
# Define the basic classes that all test cases are inherited from.
# The currently defined test case classes are:
#
# CliTestCase
# ManyDepotTestCase
# Pkg5TestCase
# SingleDepotTestCase
# SingleDepotTestCaseCorruptImage
#

import baseline
import ConfigParser
import copy
import difflib
import errno
import gettext
import hashlib
import httplib
import json
import logging
import multiprocessing
import os
import pprint
import shutil
import signal
import simplejson as json
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import urllib2
import urlparse
import platform
import pwd
import re
import ssl
import StringIO
import textwrap

import pkg.client.api_errors as apx
import pkg.client.publisher as publisher
import pkg.portable as portable
import pkg.server.repository as sr
import M2Crypto as m2

from pkg.client.debugvalues import DebugValues

EmptyI = tuple()
EmptyDict = dict()

# relative to our proto area
path_to_pub_util = "../../src/util/publish"
path_to_distro_import_utils = "../../src/util/distro-import"

#
# These are initialized by pkg5testenv.setup_environment.
#
g_proto_area = "TOXIC"
# User's value for TEMPDIR
g_tempdir = "/tmp"

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
CLIENT_API_VERSION = 70

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
                self.next_free_port = None
                self.ident = None
                self.pkg_cmdpath = "TOXIC"
                self.debug_output = g_debug_output
                setup_logging(self)

        @property
        def methodName(self):
                return self._testMethodName

        @property
        def suite_name(self):
                return self.__suite_name

        def __str__(self):
                return "%s.py %s.%s" % (self.__class__.__module__,
                    self.__class__.__name__, self._testMethodName)

        def __set_base_port(self, port):
                if self.__base_port is not None or \
                    self.next_free_port is not None:
                        raise RuntimeError("Setting the base port twice isn't "
                            "allowed")
                self.__base_port = port
                self.next_free_port = port

        base_port = property(lambda self: self.__base_port, __set_base_port)

        def assertRaisesStringify(self, excClass, callableObj, *args, **kwargs):
                """Perform the same logic as assertRaises, but then verify that
                the exception raised can be stringified."""

                try:
                        callableObj(*args, **kwargs)
                except excClass, e:
                        str(e)
                        return
                else:
                        raise self.failureException, "%s not raised" % excClass

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

        def cmdline_run(self, cmdline, comment="", coverage=True, exit=0,
            handle=False, out=False, prefix="", raise_error=True, su_wrap=None,
            stderr=False, env_arg=None):
                wrapper = ""
                if coverage:
                        wrapper = self.coverage_cmd
                su_wrap, su_end = self.get_su_wrapper(su_wrap=su_wrap)

                cmdline = "%s%s%s %s%s" % (prefix, su_wrap, wrapper,
                    cmdline, su_end)
                self.debugcmd(cmdline)

                newenv = os.environ.copy()
                if coverage:
                        newenv.update(self.coverage_env)
                if env_arg:
                        newenv.update(env_arg)

                p = subprocess.Popen(cmdline,
                    env=newenv,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)

                if handle:
                        # Do nothing more.
                        return p
                self.output, self.errout = p.communicate()
                retcode = p.returncode
                self.debugresult(retcode, exit, self.output)
                if self.errout != "":
                        self.debug(self.errout)

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
                                print >> sys.stderr, "# %s" % x
                        self.__debug_buf += x + "\n"

        def debugcmd(self, cmdline):
                wrapper = textwrap.TextWrapper(initial_indent="$ ",
                    subsequent_indent="\t",
                    break_long_words=False,
                    break_on_hyphens=False)
                res = wrapper.wrap(cmdline.strip())
                self.debug(" \\\n".join(res))

        def debugfilecreate(self, content, path):
                lines = content.splitlines()
                if lines == []:
                        lines = [""]
                if len(lines) > 1:
                        ins = " [+%d lines...]" % (len(lines) - 1)
                else:
                        ins = ""
                self.debugcmd(
                    "echo '%s%s' > %s" % (lines[0], ins, path))

        def debugresult(self, retcode, expected, output):
                if output.strip() != "":
                        self.debug(output.strip())
                if not isinstance(expected, list):
                        expected = [expected]
                if retcode is None or retcode != 0 or \
                    retcode not in expected:
                        self.debug("[exited %s, expected %s]" %
                            (retcode, ", ".join(str(e) for e in expected)))

        def get_debugbuf(self):
                return self.__debug_buf

        def set_debugbuf(self, s):
                self.__debug_buf = s

        def get_su_wrapper(self, su_wrap=None):
                if su_wrap:
                        if su_wrap == True:
                                su_wrap = get_su_wrap_user()
                        cov_env = " ".join(
                            ("%s=%s" % e for e in self.coverage_env.items()))
                        su_wrap = "su %s -c 'LD_LIBRARY_PATH=%s %s " % \
                            (su_wrap, os.getenv("LD_LIBRARY_PATH", ""), cov_env)
                        su_end = "'"
                else:
                        su_wrap = ""
                        su_end = ""
                return su_wrap, su_end

        def getTeardownFunc(self):
                return (self, self.tearDown)

        def getSetupFunc(self):
                return (self, self.setUp)

        def setUp(self):
                assert self.ident is not None
                self.__test_root = os.path.join(g_tempdir,
                    "ips.test.%d" % self.__pid, "%d" % self.ident)
                self.__didtearDown = False
                try:
                        os.makedirs(self.__test_root, 0755)
                except OSError, e:
                        if e.errno != errno.EEXIST:
                                raise e
                test_relative = os.path.sep.join(["..", "..", "src", "tests"])
                test_src = os.path.join(g_proto_area, test_relative)
                if getattr(self, "need_ro_data", False):
                        shutil.copytree(os.path.join(test_src, "ro_data"),
                            self.ro_data_root)
                        self.path_to_certs = os.path.join(self.ro_data_root,
                            "signing_certs", "produced")
                        self.keys_dir = os.path.join(self.path_to_certs, "keys")
                        self.cs_dir = os.path.join(self.path_to_certs,
                            "code_signing_certs")

                #
                # TMPDIR affects the behavior of mkdtemp and mkstemp.
                # Setting this here should ensure that tests will make temp
                # files and dirs inside the test directory rather than
                # polluting /tmp.
                #
                os.environ["TMPDIR"] = self.__test_root
                tempfile.tempdir = self.__test_root
                setup_logging(self)

                self.configure_rcfile( "%s/usr/share/lib/pkg/pkglintrc" %
                    g_proto_area,
                    {"info_classification_path":
                    "%s/usr/share/lib/pkg/opensolaris.org.sections" %
                    g_proto_area}, self.test_root, section="pkglint")

                self.template_dir = "%s/etc/pkg/sysrepo" % g_proto_area
                self.make_misc_files(self.smf_cmds, prefix="smf_cmds",
                    mode=0755)
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
                        except Exception, e:
                                print >> sys.stderr, str(e)

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
                                self.debug("removing: %s" % path)
                                if os.path.isdir(path):
                                        shutil.rmtree(path)
                                else:
                                        os.remove(path)

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
                else:
                        self.coverage_cmd, self.coverage_env = "", {}
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
                        except TestSkippedException, err:
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
                        except OSError, e:
                                # If directory doesn't exist anymore it doesn't
                                # matter.
                                if e.errno != errno.ENOENT:
                                        raise

        #
        # The following are utility functions for use by testcases.
        #
        def c_compile(self, prog_text, opts, outputfile):
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
                if os.path.dirname(outputfile) != "":
                        try:
                                os.makedirs(os.path.dirname(outputfile))
                        except OSError, e:
                                if e.errno != errno.EEXIST:
                                        raise
                c_fd, c_path = tempfile.mkstemp(suffix=".c",
                    dir=self.test_root)
                c_fh = os.fdopen(c_fd, "w")
                c_fh.write(prog_text)
                c_fh.close()

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
                                            "Compile failed: %s --> %d\n%s" % \
                                            (cmd, rc, sout))
                                if rc == 127:
                                        self.debug("[%s not found]" % compiler)
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
                            "Tried: %s.  Try setting $CC to a valid"
                            "compiler." % compilers)

        def make_file(self, path, content, mode=0644):
                if not os.path.exists(os.path.dirname(path)):
                        os.makedirs(os.path.dirname(path), 0777)
                self.debugfilecreate(content, path)
                fh = open(path, 'wb')
                if isinstance(content, unicode):
                        content = content.encode("utf-8")
                fh.write(content)
                fh.close()
                os.chmod(path, mode)

        def make_misc_files(self, files, prefix=None, mode=0644):
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
                if isinstance(files, basestring):
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

                for f, content in files.items():
                        assert not f.startswith("/"), \
                            ("%s: misc file paths must be relative!" % f)
                        path = os.path.join(prefix, f)
                        self.make_file(path, content, mode)
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
                        t_fh.write("set name=pkg.fmri value=%s\n" % pfmri)
                t_fh.write(content)
                t_fh.close()
                self.debugfilecreate(content, t_path)
                return t_path

        @staticmethod
        def calc_pem_hash(pth):
                # Find the hash of pem representation the file.
                cert = m2.X509.load_cert(pth)
                return hashlib.sha1(cert.as_pem()).hexdigest()

        def reduceSpaces(self, string):
                """Reduce runs of spaces down to a single space."""
                return re.sub(" +", " ", string)

        def assertEqualDiff(self, expected, actual, bound_white_space=False,
            msg=""):
                """Compare two strings."""

                if not isinstance(expected, basestring):
                        expected = pprint.pformat(expected)
                if not isinstance(actual, basestring):
                        actual = pprint.pformat(actual)

                expected_lines = expected.splitlines()
                actual_lines = actual.splitlines()
                if bound_white_space:
                        expected_lines = ["'%s'" % l for l in expected_lines]
                        actual_lines = ["'%s'" % l for l in actual_lines]
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
                            "than was expected.\nExpected:\n%s\nSeen:\n%s" %
                            (" ".join(enames), " ".join(onames)))
                for ed in ev:
                        for od in ov:
                                if ed["image_name"] == od["image-name"]:
                                        self.assertEqualParsable(od, **ed)
                                        break

        def assertEqualParsable(self, output, activate_be=True,
            add_packages=EmptyI, affect_packages=EmptyI, affect_services=EmptyI,
            backup_be_name=None, be_name=None, boot_archive_rebuild=False,
            change_facets=EmptyI, change_packages=EmptyI,
            change_mediators=EmptyI, change_variants=EmptyI,
            child_images=EmptyI, create_backup_be=False, create_new_be=False,
            image_name=None, licenses=EmptyI, remove_packages=EmptyI,
            version=0):
                """Check that the parsable output in 'output' is what is
                expected."""

                if isinstance(output, basestring):
                        try:
                                outd = json.loads(output)
                        except Exception, e:
                                raise RuntimeError("JSON couldn't parse the "
                                    "output.\nError was: %s\nOutput was:\n%s" %
                                    (e, output))
                else:
                        self.assert_(isinstance(output, dict))
                        outd = output
                expected = locals()
                # It's difficult to check that space-available is correct in the
                # test suite.
                self.assert_("space-available" in outd)
                del outd["space-available"]
                # While we could check for space-required, it just means lots of
                # tests would need to be changed if we ever changed our size
                # measurement and other tests should be ensuring that the number
                # is correct.
                self.assert_("space-required" in outd)
                del outd["space-required"]
                # Add 3 to outd to take account of self, output, and outd.
                self.assertEqual(len(expected), len(outd) + 3, "Got a "
                    "different set of keys for expected and outd.  Those in "
                    "expected but not in outd:\n%s\nThose in outd but not in "
                    "expected:\n%s" % (
                        sorted(set([k.replace("_", "-") for k in expected]) -
                        set(outd)),
                        sorted(set(outd) -
                        set([k.replace("_", "-") for k in expected]))))
                for k in sorted(outd):
                        ek = k.replace("-", "_")
                        ev = expected[ek]
                        if ev == EmptyI:
                                ev = []
                        if ek == "child_images" and ev != []:
                                self.__compare_child_images(ev, outd[k])
                                continue
                        self.assertEqual(ev, outd[k], "In image %s, the value "
                            "of %s was expected to be\n%s but was\n%s" %
                            (image_name, k, ev, outd[k]))

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

                new_rcfile = file("%s/%s%s" % (test_root, os.path.basename(rcfile),
                    suffix), "w")

                conf = ConfigParser.SafeConfigParser()
                conf.readfp(open(rcfile))

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
                        self.stream.write("%s: %s\n" %
                            (flavour, test))
                        self.stream.write(self.separator2 + "\n")
                        self.stream.write("%s\n" % err)


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
                except Exception, e:
                        print >> sys.stderr, str(e)
                        pass

                if getattr(test, "persistent_setup", None):
                        try:
                                test.reallytearDown()
                        except Exception, e:
                                print >> sys.stderr, str(e)
                                pass

                if hasattr(inst, "killalldepots"):
                        try:
                                inst.killalldepots()
                        except Exception, e:
                                print >> sys.stderr, str(e)
                                pass
                raise TestStopException()

        def fmt_parseable(self, match, actual, expected):
                if match == baseline.BASELINE_MATCH:
                        mstr = "MATCH"
                else:
                        mstr = "MISMATCH"
                return "%s|%s|%s" % (mstr, actual, expected)


        @staticmethod
        def fmt_prefix_with(instr, prefix):
                res = ""
                for s in instr.splitlines():
                        res += "%s%s\n" % (prefix, s)
                return res

        @staticmethod
        def fmt_box(instr, title, prefix=""):
                trailingdashes = (50 - len(title)) * "-"
                res = "\n.---" + title + trailingdashes + "\n"
                for s in instr.splitlines():
                        if s.strip() == "":
                                continue
                        res += "| %s\n" % s
                res += "`---" + len(title) * "-" + trailingdashes
                return _Pkg5TestResult.fmt_prefix_with(res, prefix)

        def do_archive(self, test, info):
                assert self.archive_dir
                if not os.path.exists(self.archive_dir):
                        os.makedirs(self.archive_dir, mode=0755)

                archive_path = os.path.join(self.archive_dir,
                    "%d" % os.getpid())
                if not os.path.exists(archive_path):
                        os.makedirs(archive_path, mode=0755)
                archive_path = os.path.join(archive_path, test.id())
                if test.debug_output:
                        self.stream.write("# Archiving to %s\n" % archive_path)

                if os.path.exists(test.test_root):
                        shutil.copytree(test.test_root, archive_path,
                            symlinks=True)
                else:
                        # If the test has failed without creating its directory,
                        # make it manually, so that we have a place to write out
                        # ERROR_INFO.
                        os.makedirs(archive_path, mode=0755)

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
                                res = "MISMATCH pass (expected: %s)" % \
                                    expected
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
                                res += "\n# %s\n" % str(errval).strip()
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
                                res = "%s ERROR\n" % b
                                res += "#\t%s" % str(errval)
                        else:
                                res = "%s ERROR\n" % b
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
                                res = "MISMATCH FAIL (expected: %s)" % expected
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
                self.skips.append((test, err))

        def addPersistentSetupError(self, test, err):
                errtype, errval = err[:2]

                errinfo = self.format_output_and_exc(test, err)

                res = "# ERROR during persistent setup for %s\n" % test.id()
                res += "# As a result, all test cases in this class will " \
                    "result in errors."

                if errtype in ELIDABLE_ERRORS:
                        res += "#   " + str(errval)
                else:
                        res += self.fmt_box(errinfo, \
                            "Persistent Setup Error Information", "# ")
                self.stream.write(res + "\n")

        def addPersistentTeardownError(self, test, err):
                errtype, errval = err[:2]

                errinfo = self.format_output_and_exc(test, err)

                res = "# ERROR during persistent teardown for %s\n" % test.id()
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
                test.debug("Start:   %s" % \
                    self.getDescription(test))
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
                        self.stream.write("%s: %s\n" %
                            (flavour, self.getDescription(test)))
                        self.stream.write(self.separator2 + "\n")
                        self.stream.write("%s\n" % err)


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
                cov_env["COVERAGE_FILE"] += ".%s.%s" % (suite_name, i)
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

                        buf = StringIO.StringIO()
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
                        otw.timing = test_suite.timing.items()
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
                print >> stream, "Tests run for '%s' Suite, " \
                    "broken down by class:\n" % suite_name
                for secs, cname in class_list:
                        print >> stream, "%6.2f %s.%s" % \
                            (secs, suite_name, cname)
                        tot += secs
                        for secs, mcname, mname in method_list:
                                if mcname != cname:
                                        continue
                                print >> stream, \
                                    "    %6.2f %s" % (secs, mname)
                        print >> stream
                print >> stream, "%6.2f Total time\n" % tot
                print >> stream, "=" * 60
                print >> stream, "\nTests run for '%s' Suite, " \
                    "sorted by time taken:\n" % suite_name
                for secs, cname, mname in method_list:
                        print >> stream, "%6.2f %s %s" % (secs, cname, mname)
                print >> stream, "%6.2f Total time\n" % tot
                print >> stream, "=" * 60
                print >> stream, ""

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
                            / 2

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
                        c_avg = c_tot / max(c_cnt, 1)
                        time_estimates[suite_name][cname].setdefault(
                            "CLASS", c_avg)
                        time_estimates[suite_name][cname]["CLASS"] = \
                            (time_estimates[suite_name][cname]["CLASS"] +
                            c_avg) / 2

                # Calculate the average per test, regardless of which test class
                # or method is being run.
                tot_avg = total / max(m_cnt, 1)
                time_estimates[suite_name].setdefault("TOTAL", tot_avg)
                time_estimates[suite_name]["TOTAL"] = \
                    (time_estimates[suite_name]["TOTAL"] + tot_avg) / 2

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
                                with open(self.timing_history + ".tmp",
                                    "wb+") as fh:
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
                        fh = open(self.timing_file, "ab+")
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
                est = secs/max(min(procs, len(test_classes)), 1)
                return max(est, long_pole)

        def test_start_display(self, started_tests, remaining_time, p_dict,
            quiet):
                if quiet:
                        return
                print >> self.stream, "\n\n"
                print >> self.stream, "Tests in " \
                    "progress:"
                for p in sorted(started_tests.keys()):
                        print >> self.stream, "\t%s\t%s\t%s %s" % \
                            (p, p_dict[p].pid, started_tests[p][0],
                            started_tests[p][1])
                if remaining_time is not None:
                        print >> self.stream, "Estimated time remaining %d " \
                            "seconds" % round(remaining_time)

        def test_done_display(self, result, all_tests, finished_tests,
            started_tests, total_tests, quiet, remaining_time, output_text,
            comm):
                if quiet:
                        self.stream.write(output_text)
                        return
                if g_debug_output:
                        print >> sys.stderr, "\n%s" % comm[3].debug_buf
                print >> self.stream, "\n\n"
                print >> self.stream, "Finished %s %s in process %s" % \
                    (comm[1][0], comm[1][1], comm[2])
                print >> self.stream, "Total test classes:%s Finished test " \
                    "classes:%s Running tests:%s" % \
                    (len(all_tests), len(finished_tests), len(started_tests))
                print >> self.stream, "Total tests:%s Tests run:%s " \
                    "Errors:%s Failures:%s Skips:%s" % \
                    (total_tests, result.testsRun, len(result.errors),
                    len(result.failures), len(result.skips))
                if remaining_time and all_tests - finished_tests:
                        print >> self.stream, "Estimated time remaining %d " \
                            "seconds" % round(remaining_time)

        @staticmethod
        def __terminate_processes(jobs):
                """Terminate all processes in this process's task group.  This
                assumes that test suite is running in its own task group which
                run.py should ensure."""

                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                cmd = ["pkill", "-T", "0"]
                subprocess.call(cmd)
                print >> sys.stderr, "All spawned processes should be " \
                    "terminated, now cleaning up directories."
                shutil.rmtree("/tmp/ips.test.%s" % os.getpid())
                print >> sys.stderr, "Directories successfully removed."
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
                                        raise RuntimeError("tmp:%s mod:%s "
                                            "c:%s" % (tmp, mod, c))
                        all_tests.add((mod, c))
                        t.pkg_cmdpath = fakeroot_cmdpath
                        if jobs > 1:
                                t.debug_output = False
                        inq.put(t, block=True)
                        total_tests += len(t.tests)
                        test_map[(mod, c)] = t.tests

                result = _CombinedResult()
                if not all_tests:
                        shutil.rmtree("/tmp/ips.test.%s" % os.getpid())
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
                                                    "comm:%s" % (comm,))
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
                                            "communication:%s" % (comm,))
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

                                        print >> sys.stderr, "The following " \
                                            "processes have died, " \
                                            "terminating the others: %s" % \
                                            ",".join([
                                                str(p_dict[i].pid)
                                                for i in sorted(broken)
                                            ])
                                        raise TestStopException()
                        for i in range(0, jobs * 2):
                                inq.put("STOP")
                        for p in p_dict:
                                p_dict[p].join()
                except KeyboardInterrupt, TestStopException:
                        terminate = True
                except Exception, e:
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
                                        self.stream.write("\n# Ran %d test%s "
                                            "in %.3fs - skipped %d tests.\n" %
                                            (run, run != 1 and "s" or "",
                                            timeTaken, len(result.skips)))

                                        if result.wasSkipped() and \
                                            self.output == OUTPUT_VERBOSE:
                                                self.stream.write("Skipped "
                                                    "tests:\n")
                                                for test,reason in result.skips:
                                                        self.stream.write(
                                                            "%s: %s\n" %
                                                            (test, reason))
                                        self.stream.write("\n")
                                if not result.wasSuccessful():
                                        self.stream.write("FAILED (")
                                        success = result.num_successes
                                        mismatches = result.mismatches
                                        failed, errored = map(len,
                                            (result.failures, result.errors))
                                        self.stream.write("successes=%d, " %
                                            success)
                                        self.stream.write("failures=%d, " %
                                            failed)
                                        self.stream.write("errors=%d, " %
                                            errored)
                                        self.stream.write("mismatches=%d" %
                                            mismatches)
                                        self.stream.write(")\n")

                                self._do_timings(result, time_estimates)
                        finally:
                                if terminate:
                                        self.__terminate_processes(jobs)
                                shutil.rmtree("/tmp/ips.test.%s" % os.getpid())
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
                print >> sys.stderr, \
                    "\nCtrl-C: Attempting cleanup during %s" % info

                if hasattr(inst, "killalldepots"):
                        print >> sys.stderr, "Killing depots..."
                        inst.killalldepots()
                print >> sys.stderr, "Stopping tests..."
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
                default_utf8 = getattr(self._tests[0], "default_utf8", False)
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
                            ["# %s" % l for l in t.get_debugbuf().splitlines()])
                        res += "\n"
                return res


def get_su_wrap_user():
        for u in ["noaccess", "nobody"]:
                try:
                        pwd.getpwnam(u)
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
                str += "Log file: %s.\n" % self.__logfile
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

                str += "  Invoked: %s\n" % self.__command
                str += "  Expected exit status: %s.  Got: %d." % \
                    (self.__expected, self.__got)

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

        def setUp(self, image_count=1):
                Pkg5TestCase.setUp(self)

                self.__imgs_path = {}
                self.__imgs_index = -1

                for i in range(0, image_count):
                        path = os.path.join(self.test_root, "image%d" % i)
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

                self.debug("image %d selected: %s" % (ii, path))

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

        def get_img_api_obj(self, cmd_path=None, ii=None):
                progresstracker = pkg.client.progress.NullProgressTracker()
                if not cmd_path:
                        cmd_path = os.path.join(self.img_path(), "pkg")
                res = pkg.client.api.ImageInterface(self.img_path(ii=ii),
                    CLIENT_API_VERSION, progresstracker, lambda x: False,
                    PKG_CLIENT_NAME, cmdpath=cmd_path)
                return res

        def image_create(self, repourl=None, destroy=True, **kwargs):
                """A convenience wrapper for callers that only need basic image
                creation functionality.  This wrapper creates a full (as opposed
                to user) image using the pkg.client.api and returns the related
                API object."""

                if destroy:
                        self.image_destroy()
                mkdir_eexist_ok(self.img_path())

                self.debug("image_create %s" % self.img_path())
                progtrack = pkg.client.progress.NullProgressTracker()
                api_inst = pkg.client.api.image_create(PKG_CLIENT_NAME,
                    CLIENT_API_VERSION, self.img_path(),
                    pkg.client.api.IMG_TYPE_ENTIRE, False, repo_uri=repourl,
                    progtrack=progtrack,
                    **kwargs)
                return api_inst

        def pkg_image_create(self, repourl=None, prefix=None,
            additional_args="", exit=0):
                """Executes pkg(1) client to create a full (as opposed to user)
                image; returns exit code of client or raises an exception if
                exit code doesn't match 'exit' or equals 99.."""

                if repourl and prefix is None:
                        prefix = "test"

                self.image_destroy()
                os.mkdir(self.img_path())
                self.debug("pkg_image_create %s" % self.img_path())
                cmdline = "%s image-create -F " % self.pkg_cmdpath
                if repourl:
                        cmdline = "%s -p %s=%s " % (cmdline, prefix, repourl)
                cmdline += additional_args
                cmdline = "%s %s" % (cmdline, self.img_path())
                self.debugcmd(cmdline)

                p = subprocess.Popen(cmdline, shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT)
                output = p.stdout.read()
                retcode = p.wait()
                self.debugresult(retcode, 0, output)

                if retcode == 99:
                        raise TracebackException(cmdline, output)
                if retcode != exit:
                        raise UnexpectedExitCodeException(cmdline, 0,
                            retcode, output)
                return retcode

        def image_destroy(self):
                if os.path.exists(self.img_path()):
                        self.debug("image_destroy %s" % self.img_path())
                        # Make sure we're not in the image.
                        os.chdir(self.test_root)
                        shutil.rmtree(self.img_path())

        def pkg(self, command, exit=0, comment="", prefix="", su_wrap=None,
            out=False, stderr=False, cmd_path=None, use_img_root=True,
            debug_smf=True):
                if debug_smf and "smf_cmds_dir" not in command:
                        command = "--debug smf_cmds_dir=%s %s" % \
                            (DebugValues["smf_cmds_dir"], command)
                if use_img_root and "-R" not in command and \
                    "image-create" not in command and "version" not in command:
                        command = "-R %s %s" % (self.get_img_path(), command)
                if not cmd_path:
                        cmd_path = self.pkg_cmdpath
                cmdline = "%s %s" % (cmd_path, command)
                return self.cmdline_run(cmdline, exit=exit, comment=comment,
                    prefix=prefix, su_wrap=su_wrap, out=out, stderr=stderr)

        def pkgdepend_resolve(self, args, exit=0, comment="", su_wrap=False):
                ops = ""
                if "-R" not in args:
                        ops = "-R %s" % self.get_img_path()
                cmdline = "%s/usr/bin/pkgdepend %s resolve %s" % (
                    g_proto_area, ops, args)
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    su_wrap=su_wrap)

        def pkgdepend_generate(self, args, exit=0, comment="", su_wrap=False):
                cmdline = "%s/usr/bin/pkgdepend generate %s" % (g_proto_area,
                    args)
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    su_wrap=su_wrap)

        def pkgfmt(self, args, exit=0, su_wrap=False):
                cmd="%s/usr/bin/pkgfmt %s" % (g_proto_area, args)
                self.cmdline_run(cmd, exit=exit, su_wrap=su_wrap)

        def pkglint(self, args, exit=0, comment="", testrc=True):
                if testrc:
                        rcpath = "%s/pkglintrc" % self.test_root
                        cmdline = "%s/usr/bin/pkglint -f %s %s" % \
                            (g_proto_area, rcpath, args)
                else:
                        cmdline = "%s/usr/bin/pkglint %s" % (g_proto_area, args)
                return self.cmdline_run(cmdline, exit=exit, out=True,
                    comment=comment, stderr=True)

        def pkgrecv(self, server_url=None, command=None, exit=0, out=False,
            comment=""):
                args = []
                if server_url:
                        args.append("-s %s" % server_url)

                if command:
                        args.append(command)

                cmdline = "%s/usr/bin/pkgrecv %s" % (g_proto_area,
                    " ".join(args))
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    out=out)

        def pkgmerge(self, args, comment="", exit=0, su_wrap=False):
                cmdline = "%s/usr/bin/pkgmerge %s" % (g_proto_area, args)
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    su_wrap=su_wrap)

        def pkgrepo(self, command, comment="", exit=0, su_wrap=False):
                cmdline = "%s/usr/bin/pkgrepo %s" % (g_proto_area, command)
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    su_wrap=su_wrap)

        def pkgsign(self, depot_url, command, exit=0, comment=""):
                args = []
                if depot_url:
                        args.append("-s %s" % depot_url)

                if command:
                        args.append(command)

                cmdline = "%s/usr/bin/pkgsign %s" % (g_proto_area,
                    " ".join(args))
                return self.cmdline_run(cmdline, comment=comment, exit=exit)

        def pkgsend(self, depot_url="", command="", exit=0, comment="",
            allow_timestamp=False):
                args = []
                if allow_timestamp:
                        args.append("-D allow-timestamp")
                if depot_url:
                        args.append("-s " + depot_url)

                if command:
                        args.append(command)

                prefix = "cd %s;" % self.test_root
                cmdline = "%s/usr/bin/pkgsend %s" % (g_proto_area,
                    " ".join(args))

                retcode, out = self.cmdline_run(cmdline, comment=comment,
                    exit=exit, out=True, prefix=prefix, raise_error=False)
                errout = self.errout

                cmdop = command.split(' ')[0]
                if cmdop in ("open", "append") and retcode == 0:
                        out = out.rstrip()
                        assert out.startswith("export PKG_TRANS_ID=")
                        arr = out.split("=")
                        assert arr
                        out = arr[1]
                        os.environ["PKG_TRANS_ID"] = out
                        self.debug("$ export PKG_TRANS_ID=%s" % out)
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
                        raise TracebackException(cmdline, out, comment)

                if retcode != exit:
                        raise UnexpectedExitCodeException(cmdline, exit,
                            retcode, out + errout, comment)

                return retcode, published

        def pkgsend_bulk(self, depot_url, commands, exit=0, comment="",
            no_catalog=False, refresh_index=False):
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
                                        self.assert_(current_fmri != None,
                                            "Missing open in pkgsend string")
                                        accumulate.append(line[4:])
                                        continue

                                if current_fmri: # send any content seen so far (can be 0)
                                        fd, f_path = tempfile.mkstemp(dir=self.test_root)
                                        for l in accumulate:
                                                os.write(fd, "%s\n" % l)
                                        os.close(fd)
                                        try:
                                                cmd = "publish %s -d %s %s" % (
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
                                                    allow_timestamp=True)
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
                                                    "name=pkg.fmri value=%s" %
                                                    current_fmri)

                        if exit == 0 and refresh_index:
                                self.pkgrepo("-s %s refresh --no-catalog" %
                                    depot_url)
                except UnexpectedExitCodeException, e:
                        if e.exitcode != exit:
                                raise
                        retcode = e.exitcode

                if retcode != exit:
                        raise UnexpectedExitCodeException(line, exit, retcode,
                            self.output + self.errout)

                return plist

        def merge(self, args=EmptyI, exit=0):
                pub_utils = os.path.join(g_proto_area, path_to_pub_util)
                prog = os.path.join(pub_utils, "merge.py")
                cmd = "%s %s" % (prog, " ".join(args))
                self.cmdline_run(cmd, exit=exit)

        def sysrepo(self, args, exit=0, out=False, stderr=False, comment="",
            fill_missing_args=True):
                ops = ""
                if "-R" not in args:
                        args += " -R %s" % self.get_img_path()
                if "-c" not in args:
                        args += " -c %s" % os.path.join(self.test_root,
                            "sysrepo_cache")
                if "-l" not in args:
                        args += " -l %s" % os.path.join(self.test_root,
                            "sysrepo_logs")
                if "-p" not in args and fill_missing_args:
                        args += " -p %s" % self.next_free_port
                if "-r" not in args:
                        args += " -r %s" % os.path.join(self.test_root,
                            "sysrepo_runtime")
                if "-t" not in args:
                        args += " -t %s" % self.template_dir

                cmdline = "%s/usr/lib/pkg.sysrepo %s" % (
                    g_proto_area, args)
                e = {"PKG5_TEST_ENV": "1"}
                return self.cmdline_run(cmdline, comment=comment, exit=exit,
                    out=out, stderr=stderr, env_arg=e)

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
                os.makedirs(dest, mode=0755)

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
                                                    mode=0755)

                                        msrc = open(os.path.join(src_pkg_path,
                                            mname), "rb")
                                        mdest = open(os.path.join(dest_pkg_path,
                                            mname), "wb")
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
                        assert len(pubs) == 1
                        pfmri.publisher = pubs[0]
                return img.get_manifest_path(pfmri)

        def get_img_manifest(self, pfmri):
                """Retrieves the client's cached copy of the manifest for the
                given package FMRI and returns it as a string.  Callers are
                responsible for all error handling."""

                mpath = self.get_img_manifest_path(pfmri)
                with open(mpath, "rb") as f:
                        return f.read()

        def write_img_manifest(self, pfmri, mdata):
                """Overwrites the client's cached copy of the manifest for the
                given package FMRI using the provided string.  Callers are
                responsible for all error handling."""

                mpath = self.get_img_manifest_path(pfmri)
                mdir = self.get_img_manifest_cache_dir(pfmri)

                # Dump the manifest directory for the package to ensure any
                # cached information related to it is gone.
                shutil.rmtree(mdir, True)
                self.assert_(not os.path.exists(mdir))
                os.makedirs(mdir, mode=0755)

                # Finally, write the new manifest.
                with open(mpath, "wb") as f:
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
            options="-quiet -utf8"):
                cmdline = "tidy %s %s" % (options, fname)
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
                        self.debug("created repository %s" % repodir)
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

                self.debug("prep_depot: set depot port %d" % port)
                self.debug("prep_depot: set depot repository %s" % repodir)
                self.debug("prep_depot: set depot log to %s" % logpath)

                dc = depotcontroller.DepotController(
                    wrapper_start=self.coverage_cmd.split(),
                    env=self.coverage_env)
                dc.set_depotd_path(g_proto_area + "/usr/lib/pkg.depotd")
                dc.set_depotd_content_root(g_proto_area + "/usr/share/lib/pkg")
                for f in debug_features:
                        dc.set_debug_feature(f)
                dc.set_repodir(repodir)
                dc.set_logpath(logpath)
                dc.set_port(port)

                for section in properties:
                        for prop, val in properties[section].iteritems():
                                dc.set_property(section, prop, val)
                if refresh_index:
                        dc.set_refresh_index()

                if start:
                        # If the caller requested the depot be started, then let
                        # the depot process create the repository.
                        dc.start()
                        self.debug("depot on port %s started" % port)
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

        def importer(self, args=EmptyI, out=False, stderr=False, exit=0):
                distro_import_utils = os.path.join(g_proto_area,
                    path_to_distro_import_utils)
                prog = os.path.join(distro_import_utils, "importer.py")
                cmd = "%s %s" % (prog, " ".join(args))
                return self.cmdline_run(cmd, out=out, stderr=stderr, exit=exit)

        def _api_attach(self, api_obj, catch_wsie=True, **kwargs):
                self.debug("attach: %s" % str(kwargs))
                for pd in api_obj.gen_plan_attach(**kwargs):
                        continue
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_detach(self, api_obj, catch_wsie=True, **kwargs):
                self.debug("detach: %s" % str(kwargs))
                for pd in api_obj.gen_plan_detach(**kwargs):
                        continue
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_sync(self, api_obj, catch_wsie=True, **kwargs):
                self.debug("sync: %s" % str(kwargs))
                for pd in api_obj.gen_plan_sync(**kwargs):
                        continue
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_install(self, api_obj, pkg_list, catch_wsie=True, **kwargs):
                self.debug("install %s" % " ".join(pkg_list))
                for pd in api_obj.gen_plan_install(pkg_list, **kwargs):
                        continue
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_uninstall(self, api_obj, pkg_list, catch_wsie=True, **kwargs):
                self.debug("uninstall %s" % " ".join(pkg_list))
                for pd in api_obj.gen_plan_uninstall(pkg_list, **kwargs):
                        continue
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_update(self, api_obj, catch_wsie=True, **kwargs):
                self.debug("planning update")
                for pd in api_obj.gen_plan_update(**kwargs):
                        continue
                self._api_finish(api_obj, catch_wsie=catch_wsie)

        def _api_change_varcets(self, api_obj, catch_wsie=True, **kwargs):
                self.debug("change varcets: %s" % str(kwargs))
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

        def file_exists(self, path):
                """Assert the existence of a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                if not os.path.isfile(file_path):
                        self.assert_(False, "File %s does not exist" % path)

        def file_doesnt_exist(self, path):
                """Assert the non-existence of a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                if os.path.exists(file_path):
                        self.assert_(False, "File %s exists" % path)

        def file_remove(self, path):
                """Remove a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                portable.remove(file_path)

        def file_contains(self, path, string):
                """Assert the existence of a string in a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                try:
                        f = file(file_path)
                except:
                        self.assert_(False,
                            "File %s does not exist or contain %s" %
                            (path, string))

                for line in f:
                        if string in line:
                                f.close()
                                break
                else:
                        f.close()
                        self.assert_(False, "File %s does not contain %s" %
                            (path, string))

        def file_doesnt_contain(self, path, string):
                """Assert the non-existence of a string in a file in the
                image."""

                file_path = os.path.join(self.get_img_path(), path)
                f = file(file_path)
                for line in f:
                        if string in line:
                                f.close()
                                self.assert_(False, "File %s contains %s" %
                                    (path, string))
                else:
                        f.close()

        def file_append(self, path, string):
                """Append a line to a file in the image."""

                file_path = os.path.join(self.get_img_path(), path)
                with open(file_path, "a+") as f:
                        f.write("\n%s\n" % string)


class ManyDepotTestCase(CliTestCase):

        def __init__(self, methodName="runTest"):
                super(ManyDepotTestCase, self).__init__(methodName)
                self.dcs = {}

        def setUp(self, publishers, debug_features=EmptyI, start_depots=False,
            image_count=1):
                CliTestCase.setUp(self, image_count=image_count)

                self.debug("setup: %s" % self.id())
                self.debug("creating %d repo(s)" % len(publishers))
                self.debug("publishers: %s" % publishers)
                self.debug("debug_features: %s" % list(debug_features))
                self.dcs = {}

                for n, pub in enumerate(publishers):
                        i = n + 1
                        testdir = os.path.join(self.test_root)

                        try:
                                os.makedirs(testdir, 0755)
                        except OSError, e:
                                if e.errno != errno.EEXIST:
                                        raise e

                        depot_logfile = os.path.join(testdir,
                            "depot_logfile%d" % i)

                        props = { "publisher": { "prefix": pub } }

                        # We pick an arbitrary base port.  This could be more
                        # automated in the future.
                        repodir = os.path.join(testdir, "repo_contents%d" % i)
                        self.dcs[i] = self.prep_depot(self.next_free_port,
                            repodir,
                            depot_logfile, debug_features=debug_features,
                            properties=props, start=start_depots)
                        self.next_free_port += 1

        def check_traceback(self, logpath):
                """ Scan logpath looking for tracebacks.
                    Raise a DepotTracebackException if one is seen.
                """
                self.debug("check for depot tracebacks in %s" % logpath)
                logfile = open(logpath, "r")
                output = logfile.read()
                for line in output.splitlines():
                        if line.find("Traceback") > -1:
                                raise DepotTracebackException(logpath, output)

        def restart_depots(self):
                self.debug("restarting %d depot(s)" % len(self.dcs))
                for i in sorted(self.dcs.keys()):
                        dc = self.dcs[i]
                        self.debug("stopping depot at url: %s" % dc.get_depot_url())
                        dc.stop()
                        self.debug("starting depot at url: %s" % dc.get_depot_url())
                        dc.start()

        def killall_sighandler(self, signum, frame):
                print >> sys.stderr, \
                    "Ctrl-C: I'm killing depots, please wait.\n"
                print self
                self.signalled = True

        def killalldepots(self):
                self.signalled = False
                self.debug("killalldepots: %s" % self.id())

                oldhdlr = signal.signal(signal.SIGINT, self.killall_sighandler)

                try:
                        check_dc = []
                        for i in sorted(self.dcs.keys()):
                                dc = self.dcs[i]
                                if not dc.started:
                                        continue
                                check_dc.append(dc)
                                path = dc.get_repodir()
                                self.debug("stopping depot at url: %s, %s" % \
                                    (dc.get_depot_url(), path))

                                status = 0
                                try:
                                        status = dc.kill()
                                except Exception:
                                        pass

                                if status:
                                        self.debug("depot: %s" % status)

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
                self.debug("ManyDepotTestCase.tearDown: %s" % self.id())

                self.killalldepots()
                CliTestCase.tearDown(self)

        def run(self, result=None):
                if result is None:
                        result = self.defaultTestResult()
                CliTestCase.run(self, result)


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
                                cmdline = "pkg image-create -F -p %s=%s %s" % \
                                    (prefix, repourl, self.img_path())
                        elif s == ".org.opensolaris,pkg":
                                cmdline = "pkg image-create -U -p %s=%s %s" % \
                                    (prefix, repourl, self.img_path())
                        else:
                                raise RuntimeError("Got unknown subdir option:"
                                    "%s\n" % s)

                        self.debugcmd(cmdline)

                        # Run the command to actually create a good image
                        p = subprocess.Popen(cmdline, shell=True,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT)
                        output = p.stdout.read()
                        retcode = p.wait()
                        self.debugresult(retcode, 0, output)

                        if retcode == 99:
                                raise TracebackException(cmdline, output)
                        if retcode != 0:
                                raise UnexpectedExitCodeException(cmdline, 0,
                                    retcode, output)

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
                        print >> sys.stderr, "# %s" % x

def mkdir_eexist_ok(p):
        try:
                os.mkdir(p)
        except OSError, e:
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

        # always print out recursive linked image commands
        os.environ["PKG_DISP_LINKED_CMDS"] = "1"

        # Pretend that we're being run from the fakeroot image.
        assert pkg_cmdpath != "TOXIC"
        DebugValues["simulate_cmdpath"] = pkg_cmdpath

        # Update the path to smf commands
        for dv in dv_keep:
                DebugValues[dv] = dv_saved[dv]

        # always get detailed data from the solver
        DebugValues["plan"] = True

def fakeroot_create():

        test_root = os.path.join(g_tempdir, "ips.test.%d" % os.getpid())
        fakeroot = os.path.join(test_root, "fakeroot")
        cmd_path = os.path.join(fakeroot, "pkg")

        try:
                os.stat(cmd_path)
        except OSError, e:
                pass
        else:
                # fakeroot already exists
                raise RuntimeError("The fakeroot shouldn't already exist.")

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

        debug("fakeroot image create %s" % fakeroot)
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
        shutil.copy(os.path.join(g_proto_area, "usr", "bin", "pkg"),
            fakeroot_cmdpath)

        return fakeroot, fakeroot_cmdpath

def eval_assert_raises(ex_type, eval_ex_func, func, *args):
        try:
                func(*args)
        except ex_type, e:
                print str(e)
                if not eval_ex_func(e):
                        raise
        else:
                raise RuntimeError("Function did not raise exception.")

class SysrepoStateException(Exception):
        pass

class ApacheController(object):

        def __init__(self, conf, port, work_dir, testcase=None, https=False):
                """
                The 'conf' parameter is a path to a httpd.conf file.  The 'port'
                parameter is a port to run on.  The 'work_dir' is a temporary
                directory to store runtime state.  The 'testcase' parameter is
                the Pkg5TestCase to use when writing output.  The 'https'
                parameter is a boolean indicating whether this instance expects
                to be contacted via https or not.
                """

                self.apachectl = "/usr/apache2/2.2/bin/httpd"
                if not os.path.exists(work_dir):
                        os.makedirs(work_dir)
                self.__conf_path = os.path.join(work_dir, "sysrepo.conf")
                self.__port = port
                self.__repo_hdl = None
                self.__starttime = 0
                self.__state = None
                self.__tc = testcase
                prefix = "http"
                if https:
                        prefix = "https"
                self.__url = "%s://localhost:%d" % (prefix, self.__port)
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
                        urllib2.urlopen(self.__url)
                except urllib2.HTTPError, e:
                        if e.code == httplib.FORBIDDEN:
                                return True
                        return False
                except urllib2.URLError, e:
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
                if self._network_ping():
                        raise SysrepoStateException("A depot (or some " +
                            "other network process) seems to be " +
                            "running on port %d already!" % self.__port)
                cmdline = ["/usr/bin/setpgrp", self.apachectl, "-f",
                    self.__conf_path, "-k", "start", "-DFOREGROUND"]
                try:
                        self.__starttime = time.time()
                        self.debug(" ".join(cmdline))
                        self.__repo_hdl = subprocess.Popen(cmdline, shell=False,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
                        if self.__repo_hdl is None:
                                raise SysrepoStateException("Could not start "
                                    "sysrepo")
                        begintime = time.time()

                        check_interval = 0.20
                        contact = False
                        while (time.time() - begintime) <= 40.0:
                                rc = self.__repo_hdl.poll()
                                if rc is not None:
                                        raise SysrepoStateException("Sysrepo "
                                            "exited unexpectedly while "
                                            "starting (exit code %d)" % rc)

                                if self.is_alive():
                                        contact = True
                                        break
                                time.sleep(check_interval)

                        if contact == False:
                                self.stop()
                                raise SysrepoStateException("Sysrepo did not "
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
                print >> sys.stderr, \
                    "Ctrl-C: I'm killing depots, please wait.\n"
                print self
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
                    testcase=None, https=False)
                self.apachectl = "/usr/apache2/2.2/bin/64/httpd"

        def _network_ping(self):
                try:
                        urllib2.urlopen(urlparse.urljoin(self.url, "syspub/0"))
                except urllib2.HTTPError, e:
                        if e.code == httplib.FORBIDDEN:
                                return True
                        return False
                except urllib2.URLError:
                        return False
                return True
