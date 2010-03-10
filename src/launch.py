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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

HTTP_PROXY_HOST = "/system/http_proxy/host"
HTTP_PROXY_PORT = "/system/http_proxy/port"
HTTP_PROXY_USE = "/system/http_proxy/use_http_proxy"
HTTP_PROXY_USER = "/system/http_proxy/authentication_user"
HTTP_PROXY_PASS = "/system/http_proxy/authentication_password"
HTTP_PROXY_AUTH = "/system/http_proxy/use_authentication"
HTTP_PROXY_VARIABLE = "http_proxy"
HTTPS_PROXY_VARIABLE = "https_proxy"

PM_OPEN_CMD = "pm-launch: OPEN:"

import gconf
import gnome
import os
import select
import sys
import pkg.pkgsubprocess as subprocess
import pkg.portable as portable

def get_http_proxy():
        host = client.get_string(HTTP_PROXY_HOST)
        port = client.get_int(HTTP_PROXY_PORT)
        pauth = client.get_bool(HTTP_PROXY_AUTH)
        if pauth:
                puser = client.get_string(HTTP_PROXY_USER)
                ppass = client.get_string(HTTP_PROXY_PASS)
                authstring = puser + ':' + ppass + "@"
                return "http://" + authstring + host + ":" + str(port) + "/"
        return "http://" + host + ":" + str(port) + "/"

if __name__ == "__main__":
        client = gconf.client_get_default()
        use_http_proxy = client.get_bool(HTTP_PROXY_USE)
        if use_http_proxy:
                http_proxy = get_http_proxy()
                if os.getenv(HTTP_PROXY_VARIABLE) == None:
                        os.putenv(HTTP_PROXY_VARIABLE, http_proxy)
                if os.getenv(HTTPS_PROXY_VARIABLE) == None:
                        os.putenv(HTTPS_PROXY_VARIABLE, http_proxy)
        args = ""
        for i in range(1, len(sys.argv)):
                args = args + sys.argv[i]
                if i < len(sys.argv) - 1:
                        args = args + " "

        allow_links = False
        args = ["/usr/bin/gksu", args]

        # If /usr/bin/packagemanager was checked for instead, that would make
        # testing (especially automated) impossible for web links.
        if args[1].find("packagemanager") != -1 and not portable.is_admin():
                allow_links = True
                args[1] += " --allow-links "

        proc = subprocess.Popen(args, stdout=subprocess.PIPE,
            close_fds=True)

        # Reap the defunct gksu now rather than wait for kernel to do it.
        proc.wait()

        if not allow_links:
                # Nothing to do for other programs.
                sys.exit()

        # XXX PackageManager should not run as a privileged process!
        # This rather convoluted solution allows packagemanager to open links
        # as the original user that launched the packagemanager instead of as
        # a privileged user.  It does this by using select to poll the output
        # of the packagemanager, and open links as it requests them.  Once
        # the packagemanager has exited, the pipe is broken and pm-launch will
        # exit as well.
        p = select.poll()
        p.register(proc.stdout,
            select.POLLIN|select.POLLERR|select.POLLHUP|select.POLLNVAL)

        # XXX This probably only works on Solaris.
        exit_now = False
        while not exit_now:
                events = p.poll()
                for fd, event in events:
                        if fd != proc.stdout.fileno():
                                continue
                        if not (event & select.POLLIN):
                                # Child likely exited.
                                exit_now = True
                                break

                        # Use os.read() here (as opposed to proc.stdout.read())
                        # to avoid blocking.  Attempt to cycle until EOF or
                        # newline is encountered.
                        output = []
                        data = ""
                        while 1:
                                data += os.read(proc.stdout.fileno(),
                                    8192)
                                if data == "" or data.endswith("\n"):
                                        output = data.splitlines()
                                        del data
                                        break

                        opened = 0
                        for line in output:
                                l = line
                                if l.startswith(PM_OPEN_CMD):
                                        uri = l.replace(PM_OPEN_CMD, "")
                                        try:
                                                gnome.url_show(uri)
                                                opened += 1
                                        except Exception, e:
                                                fail_msg = "OPEN: FAILURE: " \
                                                    "%s: %s" % (uri, e)
                                                # For xsession-errors.
                                                print >> sys.stderr, fail_msg
                                else:
                                        # Passthrough any other data.
                                        print line
        # Nothing more to do.
        sys.exit()
