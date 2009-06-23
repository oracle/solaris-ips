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

HTTP_PROXY_HOST='/system/http_proxy/host'
HTTP_PROXY_PORT='/system/http_proxy/port'
HTTP_PROXY_USE = "/system/http_proxy/use_http_proxy"
HTTP_PROXY_VARIABLE='http_proxy'
HTTPS_PROXY_VARIABLE='https_proxy'

import gconf
import os
import sys
import subprocess

def get_http_proxy():
        host= client.get_string(HTTP_PROXY_HOST)
        port = client.get_int(HTTP_PROXY_PORT)
        return 'http://' + host + ':' + str(port) + '/'

if __name__ == '__main__':
        client = gconf.client_get_default()
        use_http_proxy= client.get_bool(HTTP_PROXY_USE)
        if use_http_proxy:
                http_proxy = get_http_proxy()
                if os.getenv(HTTP_PROXY_VARIABLE) == None:
                        os.putenv(HTTP_PROXY_VARIABLE, http_proxy)
                if os.getenv(HTTPS_PROXY_VARIABLE) == None:
                        os.putenv(HTTPS_PROXY_VARIABLE, http_proxy)
        args = ''
        for i in range(1, len(sys.argv)):
                args = args + sys.argv[i]
                if i < len(sys.argv) - 1:
                        args = args + ' '
        command = subprocess.Popen(["/usr/bin/gksu", args], close_fds=True)
