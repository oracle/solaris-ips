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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import errno
import os
import sys
import signal
import time
import subprocess
import socket


class DepotStateException(Exception):

        def __init__(self, reason):
                Exception.__init__(self, reason)

class DepotController(object):

        HALTED = 0
        STARTING = 1
        RUNNING = 2

        def __init__(self):
                self.__depot_path = "/usr/lib/pkg.depotd"
                self.__auto_port = True
                self.__port = -1
                self.__dir = None
                self.__readonly = False
                self.__rebuild = False
                self.__logpath = "/tmp/depot.log"
                self.__output = None
                self.__depot_handle = None
                self.__state = self.HALTED
                return

        def set_depotd_path(self, path):
                self.__depot_path = path

        def set_auto_port(self):
                self.__auto_port = True

        def set_port(self, port):
                self.__auto_port = False
                self.__port = port

        def get_port(self):
                return self.__port

        def set_repodir(self, dir):
                self.__dir = dir

        def get_repodir(self):
                return self.__dir

        def set_readonly(self):
                self.__readonly = True

        def set_readwrite(self):
                self.__readonly = False

        def set_rebuild(self):
                self.__rebuild = True

        def set_norebuild(self):
                self.__rebuild = False

        def set_logpath(self, logpath):
                self.__logpath = logpath

        def get_logpath(self):
                return self.__logpath

        def get_state(self):
                return self.__state

        def get_depot_url(self):
                return "http://localhost:%d" % self.__port

        def __network_ping(self):
                sock = None
		#
		# Any failure here is treated as an indication that the
		# depot is not alive.  Hence we just wrap all exceptions
		# and return false.
		#
                try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.connect(("localhost", self.__port))
                        sock.send("GET / HTTP/1.0\r\n\r\n")
                        buf = sock.recv(1024)
                        sock.close()
                except:
                        if sock:
                                sock.close()
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

                args =  [ self.__depot_path ]
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
                return args
                
        def start(self):
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

		self.__depot_handle = subprocess.Popen(args = args, \
		    stdout = self.__output, stderr = self.__output)
		if self.__depot_handle == None:
			raise DepotStateException("Could not start Depot")
		
		sleeptime = 0.05
		contact = False
		while sleeptime <= 4.0:
			if self.is_alive():
				contact = True
				break
			time.sleep(sleeptime)
			sleeptime *= 2
		
		if contact == False:
			self.kill()
			self.__state = self.HALTED
			raise DepotStateException("Depot did not respond to repeated attempts to make contact")

		self.__state = self.RUNNING


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


        def stop(self, force = False):
                if self.__state == self.HALTED:
                        raise DepotStateException("Depot already stopped")

                return self.kill()


if __name__ == "__main__":
        dc = DepotController()
        dc.set_port(12000)
        try:
                os.mkdir("/tmp/fooz")
        except:
                pass

        dc.set_repodir("/tmp/fooz")

        for j in range(0, 100):
                print "%4d: Starting Depot... (%s)" % (j, " ".join(dc.get_args())),
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
		file = open("/tmp/depot.log", "r")
		print file.read()
		file.close

