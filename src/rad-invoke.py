#!/usr/bin/python2.7
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
# Copyright (c) 2015, Oracle and/or its affiliates. All rights reserved.
#

import sys
import gettext
import getopt
import locale
import logging
import os
import pkg
import pkg.client.rad_pkg as entry
import pkg.misc as misc
import simplejson as json


class _InfoFilter(logging.Filter):
        def filter(self, rec):
                return rec.levelno <= logging.INFO

class _StreamHandler(logging.StreamHandler):
        """Simple subclass to ignore exceptions raised during logging output."""

        def handleError(self, record):
                # Ignore exceptions raised during output to stdout/stderr.
                return

ips_logger = None

def error(text):
        """Create error message."""

        if os.getenv("__IPS_INVOKE_IN_RAD") == "true":
                return {"status": entry.ERROR, "errors": [{"reason": text}]}
        ips_logger.error(text)
        sys.exit(1)

def __init_log():
        """Initialize logger."""

        global ips_logger

        ips_logger = logging.getLogger("__name__")
        ips_logger.propagate = 0
        ips_logger.setLevel(logging.INFO)

        handler = _StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)

        # If this script is used in RAD, only retrieve log levels <= INFO.
        if os.getenv("__IPS_INVOKE_IN_RAD") == "true":
                handler.addFilter(_InfoFilter())
        ips_logger.addHandler(handler)

def main_func():
        pkg_image = None
        pargs_json = None
        opts_json = None
        prog_delay = entry.PROG_DELAY
        if os.getenv("__IPS_INVOKE_IN_RAD") != "true":
                return error(_("This script can only be invoked by RAD"))
        script_path = os.path.realpath(__file__)
        try:
                opts, pargs = getopt.getopt(sys.argv[1:],
                    "hR:?", ["help", "pargs=", "opts=", "prog-delay="])
                for opt, arg in opts:
                        if opt == "--help" or opt == "-h":
                                error("This is a RAD only script.")
                        elif opt == "--pargs":
                                pargs_json = arg
                        elif opt == "--opts":
                                opts_json = arg
                        elif opt == "-R":
                                pkg_image = arg
                        elif opt == "--prog-delay":
                                prog_delay = float(arg)
                        else:
                                error(_("unknown option {0} in file: {1}"
                                    ).format(opt, script_path))
        except getopt.GetoptError as e:
                return error(_("illegal global option -- {0} in file: {1}"
                    ).format(e.opt, script_path))
        except ValueError as e:
                return error(_("invalid option argument: {0} in file: {1}"
                    ).format(str(e), script_path))
        if len(pargs) < 1:
                return error(_("missing argument in file: {0}").format(
                    script_path))
        return entry.rad_pkg(pargs[0], pargs_json=pargs_json,
            opts_json=opts_json, pkg_image=pkg_image,
            prog_delay=prog_delay)

if __name__ == "__main__":
        misc.setlocale(locale.LC_ALL, "")
        gettext.install("pkg", "/usr/share/locale",
            codeset=locale.getpreferredencoding())
        __init_log()
        ret_json = main_func()
        ips_logger.info(json.dumps(ret_json))
        try:
                logging.shutdown()
        except IOError:
                # Ignore python's spurious pipe problems.
                pass
        sys.exit(ret_json["status"])
