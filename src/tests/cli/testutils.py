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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import unittest
import os
import sys
import subprocess
import shutil
import errno
import platform
import tempfile
import time
try:
        import pwd
except ImportError:
        pass

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)

import pkg5unittest
from pkg.misc import EmptyI

g_proto_area=""

def setup_environment(path_to_proto):
        """ Set up environment for doing testing.

            We set PYTHONPATH and PATH so that they reference the proto
            area, and clear packaging related environment variables
            (every variable prefixed with PKG_).

            path_to_proto should be a relative path indicating a path
            to proto area of the workspace.  So, if your test case is
            three levels deep: ex. src/tests/cli/foo.py, this should be
            "../../../proto"

            This function looks at argv[0] to compute the ultimate
            path to the proto area; this is nice because you can then
            invoke test cases like normal commands; i.e.:
            "python cli/t_my_test_case.py" will just work.

        """

        global g_proto_area

        osname = platform.uname()[0].lower()
        proc = 'unknown'
        if osname == 'sunos':
                proc = platform.processor()
        elif osname == 'linux':
                proc = "linux_" + platform.machine()
        elif osname == 'windows':
                proc = osname
        elif osname == 'darwin':
                proc = osname
        elif osname == 'aix':
                proc = osname
        else:
                print "Unable to determine appropriate proto area location."
                print "This is a porting problem."
                sys.exit(1)

        # Figure out from where we're invoking the command
        cmddir, cmdname = os.path.split(sys.argv[0])
        cmddir = os.path.realpath(cmddir)

        if "ROOT" in os.environ:
                g_proto_area = os.environ["ROOT"]
        else:
                g_proto_area = "%s/%s/root_%s" % (cmddir, path_to_proto, proc)

        # Clean up relative ../../, etc. out of path to proto
        g_proto_area = os.path.realpath(g_proto_area)

        pkgs = "%s/usr/lib/python2.6/vendor-packages" % g_proto_area
        bins = "%s/usr/bin" % g_proto_area

        sys.path.insert(1, pkgs)

        #
        # Because subprocesses must also source from the proto area,
        # we need to set PYTHONPATH in the environment as well as
        # in sys.path.
        #
        if "PYTHONPATH" in os.environ:
                pypath = os.pathsep + os.environ["PYTHONPATH"]
        else:
                pypath = ""
        os.environ["PYTHONPATH"] = "." + os.pathsep + pkgs + pypath

        os.environ["PATH"] = bins + os.pathsep + os.environ["PATH"]

        # Use "keys"; otherwise we'll change dictionary size during iteration.
        for k in os.environ.keys():
                if k.startswith("PKG_"):
                        del os.environ[k]

        from pkg.client import global_settings
        global_settings.client_name = "pkg"


topdivider = \
",---------------------------------------------------------------------\n"
botdivider = \
"`---------------------------------------------------------------------\n"

def format_comment(comment):
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

def format_output(command, output):
        str = "  Output Follows:\n"
        str += topdivider
        if command is not None:
                str += "| $ " + command + "\n"

        if output is None or output == "":
                str += "| <no output>\n"
        else:
                for line in output.split("\n"):
                        str += "| " + line.rstrip() + "\n"
        str += botdivider
        return str

def format_debug(output):
        str = "  Debug Buffer Follows:\n"
        str += topdivider

        if output is None or output == "":
                str += "| <no debug buffer>\n"
        else:
                for line in output.split("\n"):
                        str += "| " + line.rstrip() + "\n"
        str += botdivider
        return str

def get_su_wrap_user():
        for u in ["noaccess", "nobody"]:
                try:
                        pwd.getpwnam(u)
                        return u
                except (KeyError, NameError):
                        pass
        raise RuntimeError("Unable to determine user for su.")

class DepotTracebackException(pkg5unittest.Pkg5TestCase.failureException):
        def __init__(self, logfile, output):
                Exception.__init__(self)
                self.__logfile = logfile
                self.__output = output

        def __str__(self):
                str = "During this test, a depot Traceback was detected.\n"
                str += "Log file: %s.\n" % self.__logfile
                str += "Log file output is:\n"
                str += format_output(None, self.__output)
                return str

class TracebackException(pkg5unittest.Pkg5TestCase.failureException):
        def __init__(self, command, output = None, comment = None,
            debug = None):
                Exception.__init__(self)
                self.__command = command
                self.__output = output
                self.__comment = comment
                self.__debug = debug

        def __str__(self):
                if self.__comment is None and self.__output is None:
                        return (Exception.__str__(self))

                str = ""
                str += format_comment(self.__comment)
                str += format_output(self.__command, self.__output)
                if self.__debug is not None and self.__debug != "":
                        str += format_debug(self.__debug)
                return str


class AssFailException(pkg5unittest.Pkg5TestCase.failureException):
        def __init__(self, comment = None, debug=None):
                Exception.__init__(self)
                self.__comment = comment
                self.__debug = debug

        def __str__(self):

                str = ""
                if self.__comment is None:
                        str += Exception.__str__(self)
                else:
                        str += format_comment(self.__comment)
                if self.__debug is not None and self.__debug != "":
                        str += format_debug(self.__debug)
                return str


class UnexpectedExitCodeException(pkg5unittest.Pkg5TestCase.failureException):
        def __init__(self, command, expected, got, output=None, comment=None,
            debug=None):
                Exception.__init__(self)
                self.__command = command
                self.__output = output
                self.__expected = expected
                self.__got = got
                self.__comment = comment
                self.__debug = debug

        def __str__(self):
                if self.__comment is None and self.__output is None:
                        return (Exception.__str__(self))

                str = ""
                str += format_comment(self.__comment)
                
                str += "  Expected exit status: %s.  Got: %d." % \
                    (self.__expected, self.__got)

                str += format_output(self.__command, self.__output)
                if self.__debug is not None and self.__debug != "":
                        str += format_debug(self.__debug)
                return str

        @property
        def exitcode(self):
                return self.__got


class PkgSendOpenException(pkg5unittest.Pkg5TestCase.failureException):
        def __init__(self, com = ""):
                Exception.__init__(self, com)

class CliTestCase(pkg5unittest.Pkg5TestCase):
        __debug = False
        __debug_buf = ""

        def in_debug_mode(self):
                return self.__debug

        def setUp(self):
                self.image_dir = None
                self.pid = os.getpid()
                self.pwd = os.getcwd()

                self.__test_prefix = os.path.join(tempfile.gettempdir(),
                    "ips.test.%d" % self.pid)
                self.img_path = os.path.join(self.__test_prefix, "image")
                os.environ["PKG_IMAGE"] = self.img_path

                if "TEST_DEBUG" in os.environ:
                        self.__debug = True

                try:
                        os.makedirs(self.__test_prefix, 0755)
                except OSError, e:
                        if e.errno != errno.EEXIST:
                                raise e

        def tearDown(self):
                self.image_destroy()

        # In the case of an assertion (not a pkg() failure)
        # raise an assertion so we can get the debug logs displayed
        def assert_(self, expr, msg=None):
                if not expr:
                        raise AssFailException(comment=msg,
                            debug=self.get_debugbuf())
 

        def get_img_path(self):
                return self.img_path

        def get_test_prefix(self):
                return self.__test_prefix

        def debug(self, s):
                s = str(s)
                if self.__debug:
                        print >> sys.stderr, s
                self.__debug_buf += s
                if not s.endswith("\n"):
                        self.__debug_buf += "\n"

        def debugcmd(self, cmdline):
                self.debug("$ %s" % cmdline)

        def debugresult(self, retcode, output):
                if output.strip() != "":
                        self.debug(output.strip())
                if retcode != 0:
                        self.debug("[returned %d]" % retcode)

        def get_debugbuf(self):
                return self.__debug_buf

        def image_create(self, repourl, prefix="test", additional_args=""):
                assert self.img_path
                assert self.img_path != "/"

                self.image_destroy()
                os.mkdir(self.img_path)
                cmdline = "pkg image-create -F -p %s=%s %s %s" % \
                    (prefix, repourl, additional_args, self.img_path)
                self.debugcmd(cmdline)

                p = subprocess.Popen(cmdline, shell = True,
                    stdout = subprocess.PIPE,
                    stderr = subprocess.STDOUT)
                retcode = p.wait()
                output = p.stdout.read()
                self.debugresult(retcode, output)

                if retcode == 99:
                        raise TracebackException(cmdline, output,
                            debug=self.get_debugbuf())
                if retcode != 0:
                        raise UnexpectedExitCodeException(cmdline, 0,
                            retcode, output, debug=self.get_debugbuf())

                return retcode

        def image_set(self, imgdir):
                self.debug("image_set: %s" % imgdir)
                self.img_path = imgdir
                os.environ["PKG_IMAGE"] = self.img_path

        def image_destroy(self):
                self.debug("image_destroy")
                os.chdir(self.pwd)

                
                if not self.in_debug_mode() and os.path.exists(self.img_path):
                        shutil.rmtree(self.img_path)

        def pkg(self, command, exit=0, comment="", prefix="", su_wrap=None):
                wrapper = self.coverage_cmd

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
                if prefix:
                        cmdline = "%s;%s%s %s/usr/bin/pkg %s%s" % (prefix,
                            su_wrap, wrapper, g_proto_area, command, su_end)
                else:
                        cmdline = "%s%s %s/usr/bin/pkg %s%s" % (su_wrap, wrapper,
                            g_proto_area, command, su_end)
                self.debugcmd(cmdline)

                newenv = os.environ.copy()
                newenv.update(self.coverage_env)
                p = subprocess.Popen(cmdline, shell=True, env=newenv,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

                self.output = p.stdout.read()
                retcode = p.wait()
                self.debugresult(retcode, self.output)

                if retcode == 99:
                        raise TracebackException(cmdline, self.output, comment,
                            debug=self.get_debugbuf())

                if not isinstance(exit, list):
                        exit = [exit]

                if retcode not in exit:
                        raise UnexpectedExitCodeException(cmdline,
                            exit, retcode, self.output, comment,
                            debug=self.get_debugbuf())

                return retcode

        def pkgdepend(self, command, proto=None, use_proto=True, exit=0,
            comment=""):
                wrapper = self.coverage_cmd

                if proto is None:
                        proto = g_proto_area

                if not use_proto:
                        proto = ""
                        
                cmdline = "%s %s/usr/bin/pkgdepend %s %s" % (wrapper, g_proto_area,
                    command, proto)
                self.debugcmd(cmdline)

                newenv = os.environ.copy()
                newenv.update(self.coverage_env)
                p = subprocess.Popen(cmdline, shell=True, env=newenv,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                self.output = p.stdout.read()
                self.errout = p.stderr.read()
                retcode = p.wait()
                self.debugresult(retcode, self.output)

                if retcode == 99:
                        raise TracebackException(cmdline, self.output, comment,
                            debug=self.errout)
                elif retcode != exit:
                        raise UnexpectedExitCodeException(cmdline,
                            exit, retcode, self.output, comment,
                            debug=self.errout)

                return retcode

        def pkgrecv(self, server_url=None, command=None, exit=0, out=False,
            comment=""):
                wrapper = self.coverage_cmd

                args = []
                if server_url:
                        args.append("-s %s" % server_url)

                if command:
                        args.append(command)

                cmdline = "%s %s/usr/bin/pkgrecv %s" % (wrapper,
                    g_proto_area, " ".join(args))
                self.debugcmd(cmdline)

                newenv = os.environ.copy()
                newenv.update(self.coverage_env)
                p = subprocess.Popen(cmdline, shell=True, env=newenv,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

                self.output = p.stdout.read()
                retcode = p.wait()
                self.debugresult(retcode, self.output)

                if retcode == 99:
                        raise TracebackException(cmdline, self.output, comment,
			    debug = self.get_debugbuf())
                elif retcode != exit:
                        raise UnexpectedExitCodeException(cmdline,
                            exit, retcode, self.output, comment,
			    debug = self.get_debugbuf())

                if out:
                        return retcode, self.output

                return retcode

        def pkgsend(self, depot_url="", command="", exit=0, comment="", retry400=True):
                wrapper = self.coverage_cmd

                args = []
                if depot_url:
                        args.append("-s " + depot_url)

                if command:
                        args.append(command)

                cmdline = "%s %s/usr/bin/pkgsend %s" % (wrapper, g_proto_area,
                    " ".join(args))
                self.debugcmd(cmdline)

                # XXX may need to be smarter.
                output = ""
                published = None
                newenv = os.environ.copy()
                newenv.update(self.coverage_env)
                if command.startswith("open "):
                        p = subprocess.Popen(cmdline, shell=True, env=newenv,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

                        out, err = p.communicate()
                        retcode = p.wait()
                        self.debugresult(retcode, out)
                        if retcode == 0:
                                out = out.rstrip()
                                assert out.startswith("export PKG_TRANS_ID=")
                                arr = out.split("=")
                                assert arr
                                out = arr[1]
                                os.environ["PKG_TRANS_ID"] = out

                        # retcode != 0 will be handled below

                else:
                        p = subprocess.Popen(cmdline, shell=True, env=newenv,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

                        output = p.stdout.read()
                        retcode = p.wait()
                        self.debugresult(retcode, output)
                        
                        if retcode != 0:
                                if retry400 and (command.startswith("publish") or \
                                    command.startswith("open")) and \
                                    "status '400'" in output:    
                                    # this may be error 400 - too quick to republish
                                    # try once more after sleeping
                                         time.sleep(1)
                                         return self.pkgsend(depot_url, command, 
                                             exit, comment, retry400=False)

                        elif command.startswith("close") or \
                            command.startswith("publish"):
                                os.environ["PKG_TRANS_ID"] = ""
                                for l in output.splitlines():
                                        if l.startswith("pkg:/"):
                                                published = l
                                                break                                        

                if retcode == 99:
                        raise TracebackException(cmdline, output, comment,
                            debug=self.get_debugbuf())

                if retcode != exit:
                        raise UnexpectedExitCodeException(cmdline, exit,
                            retcode, output, comment, debug=self.get_debugbuf())

                return retcode, published

        def pkgsend_bulk(self, depot_url, commands, exit=0, comment=""):
                """ Send a series of packaging commands; useful for quickly
                    doing a bulk-load of stuff into the repo.  All commands are
                    expected to work; if not, the transaction is abandoned.  If
                    'exit' is set, then if none of the actions triggers that
                    exit code, an UnexpectedExitCodeException is raised.

                    A list containing the fmris of any packages that were
                    published as a result of the commands executed will be
                    returned; it will be empty if none were. """

                plist = []
                retcode = None
                try:
                        accumulate = []
                        current_fmri = None

                        for line in commands.split("\n"):
                                line = line.strip()
                                if line == "":
                                        continue
                                if line.startswith("add"):
                                        accumulate.append(line[4:])
                                else:
                                        if current_fmri: # send any content seen so far (can be 0)
                                                self.assert_(current_fmri != None, 
                                                    "Missing open in pkgsend string")
                                                f = tempfile.NamedTemporaryFile(dir="/tmp")
                                                for l in accumulate:
                                                        f.write("%s\n" % l)
                                                f.flush()
                                                cmd = "publish -d / %s %s" % (current_fmri, f.name)
                                                current_fmri = None
                                                accumulate = []
                                                retcode, published = self.pkgsend(depot_url, cmd)
                                                if retcode == 0 and published:
                                                        plist.append(published)
                                                f.close()
                                        if line.startswith("open"):
                                                current_fmri = line[5:].strip()
                                        
                except UnexpectedExitCodeException, e:
                        if e.exitcode != exit:
                                raise
                        retcode = e.exitcode

                if retcode != exit:
                        raise UnexpectedExitCodeException(line, exit, retcode,
                            debug=self.get_debugbuf())

                return plist
                                                

        def cmdline_run(self, cmdline, exit=0):
                p = subprocess.Popen(cmdline,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT)

                output = p.stdout.read()
                retcode = p.wait()
                self.debugresult(retcode, output)
                if retcode != exit:
                        raise UnexpectedExitCodeException(cmdline, exit,
                            retcode, output, debug=self.get_debugbuf())

        def copy_repository(self, src, src_pub, dest, dest_pub):
                """Copies the packages from the src repository to a new
                destination repository that will be created at dest.  In
                addition, any packages from the src_pub will be assigned
                to the dest_pub during the copy.  The new repository will
                not have a catalog or search indices, so a depot server
                pointed at the new repository must be started with the
                --rebuild option."""

                shutil.rmtree(dest, True)
                os.makedirs(dest, mode=0755)

                for entry in os.listdir(src):
                        spath = os.path.join(src, entry)

                        # Skip the catalog, index, and pkg directories
                        # as they will be copied manually.  Also skip
                        # any unknown files in the repository directory.
                        if entry in ("catalog", "index", "pkg") or \
                            not os.path.isdir(spath):
                                continue
                        shutil.copytree(spath, os.path.join(dest, entry))

                # Now copy each manifest and replace any references to the old
                # publisher with that of the new publisher as they are copied.
                pkg_root = os.path.join(src, "pkg")
                for stem in os.listdir(pkg_root):
                        pkg_path = os.path.join(pkg_root, stem)
                        for mname in os.listdir(pkg_path):
                                # Ensure destination manifest directory exists.
                                dmdpath = os.path.join(dest, "pkg", stem)
                                if not os.path.isdir(dmdpath):
                                        os.makedirs(dmdpath, mode=0755)

                                msrc = open(os.path.join(pkg_path, mname), "rb")
                                mdest = open(os.path.join(dmdpath, mname), "wb")
                                for l in msrc:
                                        if l.find("pkg://") > -1:
                                                mdest.write(l.replace(src_pub,
                                                    dest_pub))
                                        else:
                                                mdest.write(l)
                                msrc.close()
                                mdest.close()

        def validate_html_file(self, fname, exit=0, comment="",
            options="-quiet -utf8"):
                cmdline = "tidy %s %s" % (options, fname)
                self.debugcmd(cmdline)

                output = ""
                p = subprocess.Popen(cmdline, shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

                output = p.stdout.read()
                retcode = p.wait()
                self.debugresult(retcode, output)

                if retcode == 99:
                        raise TracebackException(cmdline, output, comment,
                            debug=self.get_debugbuf())

                if retcode != exit:
                        raise UnexpectedExitCodeException(cmdline, exit,
                            retcode, output, comment, debug=self.get_debugbuf())

                return retcode

        def start_depot(self, port, depotdir, logpath, refresh_index=False,
            debug_features=EmptyI, properties=EmptyI):
                """ Convenience routine to help subclasses start
                    depots.  Returns a depotcontroller. """

                # Note that this must be deferred until after PYTHONPATH
                # is set up.
                import pkg.depotcontroller as depotcontroller

                self.debug("start_depot: depot listening on port %d" % port)
                self.debug("start_depot: depot data in %s" % depotdir)
                self.debug("start_depot: depot logging to %s" % logpath)

                dc = depotcontroller.DepotController(
                    wrapper=self.coverage_cmd.split(), env=self.coverage_env)
                dc.set_depotd_path(g_proto_area + "/usr/lib/pkg.depotd")
                dc.set_depotd_content_root(g_proto_area + "/usr/share/lib/pkg")
                for f in debug_features:
                        dc.set_debug_feature(f)
                dc.set_repodir(depotdir)
                dc.set_logpath(logpath)
                dc.set_port(port)
                for section in properties:
                        for prop, val in properties[section].iteritems():
                                dc.set_property(section, prop, val)
                if refresh_index:
                        dc.set_refresh_index()
                dc.start()
                return dc


class ManyDepotTestCase(CliTestCase):

        def setUp(self, publishers, debug_features=EmptyI):
                CliTestCase.setUp(self)

                self.debug("setup: %s" % self.id())
                self.debug("starting %d depot(s)" % len(publishers))
                self.debug("publishers: %s" % publishers)
                self.debug("debug_features: %s" % list(debug_features))
                self.dcs = {}

                for n, pub in enumerate(publishers):
                        i = n + 1
                        testdir = os.path.join(self.get_test_prefix(),
                            self.id())

                        depotdir = os.path.join(testdir,
                            "depot_contents%d" % i)

                        for dir in (testdir, depotdir):
                                try:
                                        os.makedirs(dir, 0755)
                                except OSError, e:
                                        if e.errno != errno.EEXIST:
                                                raise e

                        # We pick an arbitrary base port.  This could be more
                        # automated in the future.
                        depot_logfile = os.path.join(testdir,
                            "depot_logfile%d" % i)

                        props = { "publisher": { "prefix": pub } }
                        self.dcs[i] = self.start_depot(12000 + i,
                            depotdir, depot_logfile,
                            debug_features=debug_features,
                            properties=props)

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

        def tearDown(self):
                self.debug("teardown: %s" % self.id())

                for i in sorted(self.dcs.keys()):
                        dc = self.dcs[i]
                        dir = dc.get_repodir()
                        try:
                                self.check_traceback(dc.get_logpath())
                        finally:
                                status = dc.kill()
                                if status:
                                        self.debug("depot: %s" % status)
                                shutil.rmtree(dir)

                self.dcs = None
                CliTestCase.tearDown(self)

        def run(self, result=None):
                if result is None:
                        result = self.defaultTestResult()
                CliTestCase.run(self, result)


class SingleDepotTestCase(ManyDepotTestCase):

        def setUp(self, debug_features=EmptyI, publisher="test"):
                ManyDepotTestCase.setUp(self, [publisher],
                    debug_features=debug_features)
                self.dc = self.dcs[1]

        def tearDown(self):
                ManyDepotTestCase.tearDown(self)
                self.dc = None


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

        def setUp(self, debug_features=EmptyI, publisher="test"):
                self.backup_img_path = None
                SingleDepotTestCase.setUp(self, debug_features=debug_features,
                    publisher=publisher)

        def tearDown(self):
                self.__uncorrupt_img_path()
                SingleDepotTestCase.tearDown(self)

        def __uncorrupt_img_path(self):
                """ Function which restores the img_path back to the original
                level. """
                if self.backup_img_path:
                        self.img_path = self.backup_img_path

        def corrupt_image_create(self, repourl, config, subdirs, prefix = "test",
            destroy = True):
                """ Creates two levels of directories under the original image
                directory. In the first level (called bad), it builds a "corrupt
                image" which means it builds subdirectories the subdirectories
                speicified by subdirs (essentially determining whether a user
                image or a full image will be built). It populates these
                subdirectories with a partial image directory stucture as
                speicified by config. As another subdirectory of bad, it
                creates a subdirectory called final which represents the
                directory the command was actually run from (which is why
                img_path is set to that location). Exisintg image destruction
                was made optional to allow testing of two images installed next
                to each other (a user and full image created in the same
                directory for example). """
                if not self.backup_img_path:
                        self.backup_img_path = self.img_path
                self.img_path = os.path.join(self.img_path, "bad")
                assert self.img_path
                assert self.img_path and self.img_path != "/"

                if destroy:
                        self.image_destroy()

                for s in subdirs:
                        if s == "var/pkg":
                                cmdline = "pkg image-create -F -p %s=%s %s" % \
                                    (prefix, repourl, self.img_path)
                        elif s == ".org.opensolaris,pkg":
                                cmdline = "pkg image-create -U -p %s=%s %s" % \
                                    (prefix, repourl, self.img_path)
                        else:
                                raise RuntimeError("Got unknown subdir option:"
                                    "%s\n" % s)

                        self.debugcmd(cmdline)

                        # Run the command to actually create a good image
                        p = subprocess.Popen(cmdline, shell = True,
                                             stdout = subprocess.PIPE,
                                             stderr = subprocess.STDOUT)
                        retcode = p.wait()
                        output = p.stdout.read()
                        self.debugresult(retcode, output)

                        if retcode == 99:
                                raise TracebackException(cmdline, output,
                                    debug=self.get_debugbuf())
                        if retcode != 0:
                                raise UnexpectedExitCodeException(cmdline, 0,
                                    retcode, output, debug=self.get_debugbuf())

                        tmpDir = os.path.join(self.img_path, s)

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
                                os.remove(os.path.join(tmpDir, "cfg_cache"))
                        if "file_absent" in config:
                                shutil.rmtree(os.path.join(tmpDir, "file"))
                        if "pkg_absent" in config:
                                shutil.rmtree(os.path.join(tmpDir, "pkg"))
                        if "index_absent" in config:
                                shutil.rmtree(os.path.join(tmpDir, "index"))

                # Make find root start at final. (See the doc string for
                # more explanation.)
                cmd_path = os.path.join(self.img_path, "final")

                os.mkdir(cmd_path)
                return cmd_path

def eval_assert_raises(ex_type, eval_ex_func, func, *args):
        try:
                func(*args)
        except ex_type, e:
                print str(e)
                if not eval_ex_func(e):
                        raise
        else:
                raise RuntimeError("Function did not raise exception.")


if __name__ == "__main__":
        unittest.main()

