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
# Copyright (c) 2008, 2020, Oracle and/or its affiliates. All rights reserved.
#

import os
import shlex
import signal
import six
import ssl
import sys
import time

from six.moves import http_client, range
from six.moves.urllib.error import HTTPError, URLError
from six.moves.urllib.request import pathname2url, urlopen
from six.moves.urllib.parse import urlunparse, urljoin

import pkg.pkgsubprocess as subprocess
import pkg.server.repository as sr

class DepotStateException(Exception):

        def __init__(self, reason):
                Exception.__init__(self, reason)

class DepotController(object):

        HALTED = 0
        STARTING = 1
        RUNNING = 2

        def __init__(self, wrapper_start=None, wrapper_end="", env=None):
                self.__add_content = False
                self.__auto_port = True
                self.__cfg_file = None
                self.__debug_features = {}
                self.__depot_handle = None
                self.__depot_path = "/usr/lib/pkg.depotd"
                self.__depot_content_root = None
                self.__dir = None
                self.__disable_ops = None
                self.__exit_ready = False
                self.__file_root = None
                self.__logpath = "/tmp/depot.log"
                self.__mirror = False
                self.__output = None
                self.__address = None
                self.__port = -1
                self.__props = {}
                self.__readonly = False
                self.__rebuild = False
                self.__refresh_index = False
                self.__state = self.HALTED
                self.__writable_root = None
                self.__sort_file_max_size = None
                self.__ssl_dialog = None
                self.__ssl_cert_file = None
                self.__ssl_key_file = None
                self.__starttime = 0
                self.__wrapper_start = []
                self.__wrapper_end = wrapper_end
                self.__env = {}
                self.__nasty = None
                self.__nasty_sleep = None
                if wrapper_start:
                        self.__wrapper_start = wrapper_start
                if env:
                        self.__env = env
                #
                # Enable special unit-test depot mode in which it doesn't
                # do its normal double-fork, providing us good control
                # over the process.
                #
                self.__env["PKGDEPOT_CONTROLLER"] = "1"
                return

        def get_wrapper(self):
                return self.__wrapper_start, self.__wrapper_end

        def set_wrapper(self, start, end):
                self.__wrapper_start = start
                self.__wrapper_end = end

        def unset_wrapper(self):
                self.__wrapper_start = []
                self.__wrapper_end = ""

        def set_depotd_path(self, path):
                self.__depot_path = path

        def set_depotd_content_root(self, path):
                self.__depot_content_root = path

        def get_depotd_content_root(self):
                return self.__depot_content_root

        def set_auto_port(self):
                self.__auto_port = True

        def set_address(self, address):
                self.__address = address

        def get_address(self):
                return self.__address

        def set_port(self, port):
                self.__auto_port = False
                self.__port = port

        def get_port(self):
                return self.__port

        def clear_property(self, section, prop):
                del self.__props[section][prop]

        def set_property(self, section, prop, value):
                self.__props.setdefault(section, {})
                self.__props[section][prop] = value

        def get_property(self, section, prop):
                return self.__props.get(section, {}).get(prop)

        def set_file_root(self, f_root):
                self.__file_root = f_root

        def get_file_root(self):
                return self.__file_root

        def set_repodir(self, repodir):
                self.__dir = repodir

        def get_repodir(self):
                return self.__dir

        def get_repo(self, auto_create=False):
                if auto_create:
                        try:
                                sr.repository_create(self.__dir)
                        except sr.RepositoryExistsError:
                                # Already exists, nothing to do.
                                pass
                return sr.Repository(cfgpathname=self.__cfg_file,
                    root=self.__dir, writable_root=self.__writable_root)

        def get_repo_url(self):
                return urlunparse(("file", "", pathname2url(
                    self.__dir), "", "", ""))

        def set_readonly(self):
                self.__readonly = True

        def set_readwrite(self):
                self.__readonly = False

        def set_mirror(self):
                self.__mirror = True

        def unset_mirror(self):
                self.__mirror = False

        def set_rebuild(self):
                self.__rebuild = True

        def set_norebuild(self):
                self.__rebuild = False

        def set_exit_ready(self):
                self.__exit_ready = True

        def set_add_content(self):
                self.__add_content = True

        def set_logpath(self, logpath):
                self.__logpath = logpath

        def get_logpath(self):
                return self.__logpath

        def set_refresh_index(self):
                self.__refresh_index = True

        def set_norefresh_index(self):
                self.__refresh_index = False

        def get_state(self):
                return self.__state

        def set_cfg_file(self, f):
                self.__cfg_file = f

        def get_cfg_file(self):
                return self.__cfg_file

        def get_depot_url(self):
                if self.__address:
                        host = self.__address
                        if ":" in host:
                                # Special syntax needed for IPv6 addresses.
                                host = "[{0}]".format(host)
                else:
                        host = "localhost"

                if self.__ssl_key_file:
                        scheme = "https"
                else:
                        scheme = "http"

                return "{0}://{1}:{2:d}".format(scheme, host, self.__port)

        def set_writable_root(self, wr):
                self.__writable_root = wr

        def get_writable_root(self):
                return self.__writable_root

        def set_sort_file_max_size(self, sort):
                self.__sort_file_max_size = sort

        def get_sort_file_max_size(self):
                return self.__sort_file_max_size

        def set_debug_feature(self, feature):
                self.__debug_features[feature] = True

        def unset_debug_feature(self, feature):
                del self.__debug_features[feature]

        def set_disable_ops(self, ops):
                self.__disable_ops = ops

        def unset_disable_ops(self):
                self.__disable_ops = None

        def set_nasty(self, nastiness):
                """Set the nastiness level of the depot.  Also works on
                running depots."""
                self.__nasty = nastiness
                if self.__depot_handle != None:
                        nastyurl = urljoin(self.get_depot_url(),
                            "nasty/{0:d}".format(self.__nasty))
                        url = urlopen(nastyurl)
                        url.close()

        def get_nasty(self):
                return self.__nasty

        def set_nasty_sleep(self, sleep):
                self.__nasty_sleep = sleep

        def get_nasty_sleep(self):
                return self.__nasty_sleep

        def enable_ssl(self, key_path=None, cert_path=None, dialog=None):
                self.__ssl_key_file = key_path
                self.__ssl_cert_file = cert_path
                self.__ssl_dialog = dialog

        def disable_ssl(self):
                self.__ssl_key_file = None
                self.__ssl_cert_file = None
                self.__ssl_dialog = None

        def __network_ping(self):
                try:
                        repourl = urljoin(self.get_depot_url(),
                            "versions/0")
                        # Disable SSL peer verification, we just want to check
                        # if the depot is running.
                        url = urlopen(repourl,
                            context=ssl._create_unverified_context())
                        url.close()
                except HTTPError as e:
                        # Server returns NOT_MODIFIED if catalog is up
                        # to date
                        if e.code == http_client.NOT_MODIFIED:
                                return True
                        else:
                                return False
                except URLError as e:
                        return False
                return True

        def is_alive(self):
                """ First, check that the depot process seems to be alive.
                    Then make a little HTTP request to see if the depot is
                    responsive to requests """

                if self.__depot_handle == None:
                        return False

                status = self.__depot_handle.poll()
                if status != None:
                        return False
                return self.__network_ping()

        @property
        def started(self):
                """ Return a boolean value indicating whether a depot process
                    has been started using this depotcontroller. """

                return self.__depot_handle != None

        def get_args(self):
                """ Return the equivalent command line invocation (as an
                    array) for the depot as currently configured. """

                args = []

                # The depot may fork off children of its own, so we place
                # them all together in a process group.  This allows us to
                # nuke everything later on.
                args.append("setpgrp")
                args.extend(self.__wrapper_start[:])
                args.append(sys.executable)
                args.append(self.__depot_path)
                if self.__depot_content_root:
                        args.append("--content-root")
                        args.append(self.__depot_content_root)
                if self.__address:
                        args.append("-a")
                        args.append("{0}".format(self.__address))
                if self.__port != -1:
                        args.append("-p")
                        args.append("{0:d}".format(self.__port))
                if self.__dir != None:
                        args.append("-d")
                        args.append(self.__dir)
                if self.__file_root != None:
                        args.append("--file-root={0}".format(self.__file_root))
                if self.__readonly:
                        args.append("--readonly")
                if self.__rebuild:
                        args.append("--rebuild")
                if self.__mirror:
                        args.append("--mirror")
                if self.__refresh_index:
                        args.append("--refresh-index")
                if self.__add_content:
                        args.append("--add-content")
                if self.__exit_ready:
                        args.append("--exit-ready")
                if self.__cfg_file:
                        args.append("--cfg-file={0}".format(self.__cfg_file))
                if self.__ssl_cert_file:
                        args.append("--ssl-cert-file={0}".format(self.__ssl_cert_file))
                if self.__ssl_key_file:
                        args.append("--ssl-key-file={0}".format(self.__ssl_key_file))
                if self.__ssl_dialog:
                        args.append("--ssl-dialog={0}".format(self.__ssl_dialog))
                if self.__debug_features:
                        args.append("--debug={0}".format(",".join(
                            self.__debug_features)))
                if self.__disable_ops:
                        args.append("--disable-ops={0}".format(",".join(
                            self.__disable_ops)))
                if self.__nasty:
                        args.append("--nasty {0:d}".format(self.__nasty))
                if self.__nasty_sleep:
                        args.append("--nasty-sleep {0:d}".format(self.__nasty_sleep))
                for section in self.__props:
                        for prop, val in six.iteritems(self.__props[section]):
                                args.append("--set-property={0}.{1}='{2}'".format(
                                    section, prop, val))
                if self.__writable_root:
                        args.append("--writable-root={0}".format(self.__writable_root))

                if self.__sort_file_max_size:
                        args.append("--sort-file-max-size={0}".format(self.__sort_file_max_size))

                # Always log access and error information.
                args.append("--log-access=stdout")
                args.append("--log-errors=stderr")
                args.append(self.__wrapper_end)

                return args

        def __initial_start(self):
                """'env_arg' can be a dictionary of additional os.environ
                entries to use when starting the depot."""

                if self.__state != self.HALTED:
                        raise DepotStateException("Depot already starting or "
                            "running")

                # XXX what about stdin and stdout redirection?
                args = self.get_args()

                if self.__network_ping():
                        raise DepotStateException("A depot (or some " +
                            "other network process) seems to be " +
                            "running on port {0:d} already!".format(self.__port))

                self.__state = self.STARTING

                # Unbuffer is only allowed in binary mode.
                self.__output = open(self.__logpath, "wb", 0)
                # Use shlex to re-parse args.
                pargs = shlex.split(" ".join(args))

                newenv = os.environ.copy()
                newenv.update(self.__env)
                self.__depot_handle = subprocess.Popen(pargs, env=newenv,
                    stdin=subprocess.PIPE,
                    stdout=self.__output,
                    stderr=self.__output,
                    close_fds=True)
                if self.__depot_handle == None:
                        raise DepotStateException("Could not start Depot")
                self.__starttime = time.time()
                self.__output.close()

        def start(self):

                try:
                        self.__initial_start()

                        if self.__refresh_index:
                                return

                        begintime = time.time()

                        sleeptime = 0.0
                        check_interval = 0.20
                        contact = False
                        while (time.time() - begintime) <= 40.0:
                                rc = self.__depot_handle.poll()
                                if rc is not None:
                                        err = ""
                                        with open(self.__logpath, "rb", 0) as \
                                            errf:
                                                err = errf.read()
                                        raise DepotStateException("Depot exited "
                                            "with exit code {0:d} unexpectedly "
                                            "while starting.  Output follows:\n"
                                            "{1}\n".format(rc, err))

                                if self.is_alive():
                                        contact = True
                                        break
                                time.sleep(check_interval)
                        if contact == False:
                                self.kill()
                                self.__state = self.HALTED
                                raise DepotStateException("Depot did not respond to "
                                    "repeated attempts to make contact")

                        self.__state = self.RUNNING
                except KeyboardInterrupt:
                        if self.__depot_handle:
                                self.kill(now=True)
                        raise

        def start_expected_fail(self, exit=2):
                try:
                        self.__initial_start()

                        sleeptime = 0.05
                        died = False
                        rc = None
                        while sleeptime <= 10.0:

                                rc = self.__depot_handle.poll()
                                if rc is not None:
                                        died = True
                                        break
                                time.sleep(sleeptime)
                                sleeptime *= 2

                        if died and rc == exit:
                                self.__state = self.HALTED
                                return True
                        else:
                                self.stop()
                                return False
                except KeyboardInterrupt:
                        if self.__depot_handle:
                                self.kill(now=True)
                        raise

        def refresh(self):
                if self.__depot_handle == None:
                        # XXX might want to remember and return saved
                        # exit status
                        return 0

                os.kill(self.__depot_handle.pid, signal.SIGUSR1)
                return self.__depot_handle.poll()

        def kill(self, now=False):
                """kill the depot; letting it live for
                a little while helps get reliable death"""

                if self.__depot_handle == None:
                        # XXX might want to remember and return saved
                        # exit status
                        return 0

                try:
                        lifetime = time.time() - self.__starttime
                        if now == False and lifetime < 1.0:
                                time.sleep(1.0 - lifetime)

                finally:
                        # By sticking in this finally: block we ensure that
                        # even if the kill gets ctrl-c'd, we'll at least take
                        # a good final whack at the depot by killing -9 its
                        # process group.
                        try:
                                os.kill(-1 * self.__depot_handle.pid,
                                    signal.SIGKILL)
                        except OSError:
                                pass
                        self.__state = self.HALTED
                        self.__depot_handle.wait()
                        self.__depot_handle = None

        def stop(self):
                if self.__state == self.HALTED:
                        raise DepotStateException("Depot already stopped")

                return self.kill()


def test_func(testdir):
        dc = DepotController()
        dc.set_port(22222)
        try:
                os.mkdir(testdir)
        except OSError:
                pass

        dc.set_repodir(testdir)

        for j in range(0, 10):
                print("{0:>4d}: Starting Depot... ({1})".format(
                    j, " ".join(dc.get_args())), end=" ")
                try:
                        dc.start()
                        print(" Done.    ", end=" ")
                        print("... Ping ", end=" ")
                        sys.stdout.flush()
                        time.sleep(0.2)
                        while dc.is_alive() == False:
                                pass
                        print("... Done.  ", end=" ")

                        print("Stopping Depot...", end=" ")
                        status = dc.stop()
                        if status is None:
                                print(" Result: Exited {0}".format(status), end=" ")
                        elif status == 0:
                                print(" Done.", end=" ")
                        elif status < 0:
                                print(" Result: Signal {0:d}".format(-1 * status), end=" ")
                        else:
                                print(" Result: Exited {0:d}".format(status), end=" ")
                        print()
                        f = open("/tmp/depot.log", "r")
                        print(f.read())
                        f.close()
                except KeyboardInterrupt:
                        print("\nKeyboard Interrupt: Cleaning up Depots...")
                        dc.stop()
                        raise

if __name__ == "__main__":
        __testdir = "/tmp/depotcontrollertest.{0:d}".format(os.getpid())
        try:
                test_func(__testdir)
        except KeyboardInterrupt:
                pass
        os.system("rm -fr {0}".format(__testdir))
        print("\nDone")

