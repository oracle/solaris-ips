#!/usr/bin/python2.4
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
#

import os
import sys
import signal
import time
import urllib2
import httplib
import pkg.pkgsubprocess as subprocess
from pkg.misc import versioned_urlopen

class DepotStateException(Exception):

        def __init__(self, reason):
                Exception.__init__(self, reason)

class DepotController(object):

        HALTED = 0
        STARTING = 1
        RUNNING = 2

        def __init__(self):
                self.__depot_path = "/usr/lib/pkg.depotd"
                self.__depot_content_root = None
                self.__auto_port = True
                self.__port = -1
                self.__dir = None
                self.__readonly = False
                self.__rebuild = False
                self.__refresh_index = False
                self.__mirror = False
                self.__logpath = "/tmp/depot.log"
                self.__output = None
                self.__depot_handle = None
                self.__cfg_file = None
                self.__writable_root = None
                self.__state = self.HALTED
                self.__debug_features = {}
                return

        def set_depotd_path(self, path):
                self.__depot_path = path

        def set_depotd_content_root(self, path):
                self.__depot_content_root = path

        def get_depotd_content_root(self):
                return self.__depot_content_root

        def set_auto_port(self):
                self.__auto_port = True

        def set_port(self, port):
                self.__auto_port = False
                self.__port = port

        def get_port(self):
                return self.__port

        def set_repodir(self, repodir):
                self.__dir = repodir

        def get_repodir(self):
                return self.__dir

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
                return "http://localhost:%d" % self.__port

        def set_writable_root(self, wr):
                self.__writable_root = wr

        def get_writable_root(self):
                return self.__writable_root

        def set_debug_feature(self, feature):
                self.__debug_features[feature] = True

        def unset_debug_feature(self, feature):
                del self.__debug_features[feature]

        def __network_ping(self):
                try:
                        c, v = versioned_urlopen(self.get_depot_url(),
                            "versions", [0])
                except urllib2.HTTPError, e:
                        # Server returns NOT_MODIFIED if catalog is up
                        # to date
                        if e.code == httplib.NOT_MODIFIED:
                                return True
                        else:
                                return False
                except urllib2.URLError:
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

        def get_args(self):
                """ Return the equivalent command line invocation (as an
                    array) for the depot as currently configured. """

                args = []
                if os.environ.has_key("PKGCOVERAGE"):
                        args.append("figleaf")
                args.append(self.__depot_path)
                if self.__depot_content_root:
                        args.append("--content-root")
                        args.append(self.__depot_content_root)
                if self.__port != -1:
                        args.append("-p")
                        args.append("%d" % self.__port)
                if self.__dir != None:
                        args.append("-d")
                        args.append(self.__dir)
                if self.__readonly:
                        args.append("--readonly")
                if self.__rebuild:
                        args.append("--rebuild")
                if self.__mirror:
                        args.append("--mirror")
                if self.__refresh_index:
                        args.append("--refresh-index")
                if self.__cfg_file:
                        args.append("--cfg-file=%s" % self.__cfg_file)
                if self.__debug_features:
                        args.append("--debug=%s" % ",".join(
                            self.__debug_features))
                if self.__writable_root:
                        args.append("--writable-root=%s" % self.__writable_root)
                return args

        def __initial_start(self):
                if self.__state != self.HALTED:
                        raise DepotStateException("Depot already starting or running")

                # XXX what about stdin and stdout redirection?
                args = self.get_args()

		if self.__network_ping():
			raise DepotStateException("A depot (or some " +
			    "other network process) seems to be " +
			    "running on port %d already!" % self.__port)

		self.__state = self.STARTING

		self.__output = open(self.__logpath, "w", 0)

		self.__depot_handle = subprocess.Popen(args = args,
                    stdin = subprocess.PIPE,
		    stdout = self.__output,
                    stderr = self.__output,
                    close_fds=True)
		if self.__depot_handle == None:
			raise DepotStateException("Could not start Depot")
                
        def start(self):
                self.__initial_start()

                if self.__refresh_index:
                        return
                
		sleeptime = 0.05
		contact = False
                while sleeptime <= 40.0:
                        rc = self.__depot_handle.poll()
                        if rc is not None:
                                raise DepotStateException("Depot exited "
                                    "unexpectedly while starting "
                                    "(exit code %d)" % rc)

			if self.is_alive():
				contact = True
				break
			time.sleep(sleeptime)
			sleeptime *= 2
		
		if contact == False:
			self.kill()
			self.__state = self.HALTED
			raise DepotStateException("Depot did not respond to "
                            "repeated attempts to make contact")

		self.__state = self.RUNNING

        def start_expected_fail(self):
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
                
                if died and rc == 2:
                        self.__state = self.HALTED
                        return True
                else:
                        self.stop()
                        return False
                        
        def refresh(self):
                if self.__depot_handle == None:
                        # XXX might want to remember and return saved
                        # exit status
                        return 0

                os.kill(self.__depot_handle.pid, signal.SIGUSR1)
                return self.__depot_handle.poll()

        def kill(self):

                if self.__depot_handle == None:
                        # XXX might want to remember and return saved
                        # exit status
                        return 0

                status = -1
                #
                # With sleeptime doubling every loop iter, and capped at
		# 10.0 secs, the cumulative time waited will be 10 secs.
                #
                sleeptime = 0.05
                firsttime = True

                while sleeptime <= 10.0:
                        status = self.__depot_handle.poll()
                        if status is not None:
				break

			#
			# No status, Depot process seems to be running
			# XXX could also check liveness with a kill.
			#
			if firsttime:
				# XXX porting issue
				os.kill(self.__depot_handle.pid, signal.SIGTERM)
				firsttime = False

			time.sleep(sleeptime)
			sleeptime *= 2
		else:
			assert status is None
                        print >> sys.stderr, \
                            "Depot did not shut down, trying kill -9 %d" % \
                            self.__depot_handle.pid
                        os.kill(self.__depot_handle.pid, signal.SIGKILL)
                        status = self.__depot_handle.wait()

                # XXX do something useful with status
                self.__state = self.HALTED
                self.__depot_handle = None
                return status

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
                print "%4d: Starting Depot... (%s)" % (j, " ".join(dc.get_args())),
                try:
                        dc.start()
                        print " Done.    ",
                        print "... Ping ",
                        sys.stdout.flush()
                        time.sleep(0.2)
                        while dc.is_alive() == False:
                                pass
                        print "... Done.  ",

                        print "Stopping Depot...",
                        status = dc.stop()
                        if status == 0:
                                print " Done.",
                        elif status < 0:
                                print " Result: Signal %d" % (-1 * status),
                        else:
                                print " Result: Exited %d" % status,
                        print
                        f = open("/tmp/depot.log", "r")
                        print f.read()
                        f.close()
                except KeyboardInterrupt:
                        print "\nKeyboard Interrupt: Cleaning up Depots..."
                        dc.stop()
                        raise

if __name__ == "__main__":
        testdir = "/tmp/depotcontrollertest.%d" % os.getpid()
        try:
                test_func(testdir)
        except KeyboardInterrupt:
                pass
        os.system("rm -fr %s" % testdir)
        print "\nDone"

