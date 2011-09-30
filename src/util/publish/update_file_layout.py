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

"""This program converts a directory structure from the V0layout to the
V1layout. pkg.file_layout.file_manager and pkg.file_layout.layout contain
more details about the nature of these structures and layouts."""

import gettext
import locale
import os
import sys
import traceback

import pkg
import pkg.file_layout.file_manager as file_manager
import pkg.misc as misc

from pkg.client import global_settings
from pkg.misc import emsg, PipeError, setlocale

logger = global_settings.logger

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if cmd:
                text = "%s: %s" % (cmd, text)
                pkg_cmd = "pkg.migrate "
        else:
                pkg_cmd = "pkg.migrate: "

                # If we get passed something like an Exception, we can convert
                # it down to a string.
                text = str(text)

        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        logger.error(ws + pkg_cmd + text_nows)

def main_func():
        if len(sys.argv) != 2:
                emsg(_("pkg.migrate takes a single directory as a paramter."))
                return 2
        
        dir_loc = os.path.abspath(sys.argv[1])

        if not os.path.isdir(dir_loc):
                emsg(_("The argument must be a directory to migrate from older "
                    "layouts to the current\npreferred layout."))
                return 2

        fm = file_manager.FileManager(root=dir_loc, readonly=False)
        try:
                for f in fm.walk():
                        # A non-readonly FileManager will move a file under a
                        # non-preferred layout to the preferred layout during a
                        # lookup.
                        fm.lookup(f)
        except file_manager.UnrecognizedFilePaths, e:
                emsg(e)
                return 1
        return 0


if __name__ == "__main__":
        setlocale(locale.LC_ALL, "")
        gettext.install("pkg", "/usr/share/locale")

        traceback_str = misc.get_traceback_message()

        try:
                # Out of memory errors can be raised as EnvironmentErrors with
                # an errno of ENOMEM, so in order to handle those exceptions
                # with other errnos, we nest this try block and have the outer
                # one handle the other instances.
                try:
                        __ret = main_func()
                except (MemoryError, EnvironmentError), __e:
                        if isinstance(__e, EnvironmentError) and \
                            __e.errno != errno.ENOMEM:
                                raise
                        if __img:
                                __img.history.abort(RESULT_FAILED_OUTOFMEMORY)
                        error("\n" + misc.out_of_memory())
                        __ret = 1
        except SystemExit, __e:
                raise
        except (PipeError, KeyboardInterrupt):
                if __img:
                        __img.history.abort(RESULT_CANCELED)
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                __ret = 1
        except:
                traceback.print_exc()
                error(traceback_str)
                __ret = 99
        sys.exit(__ret)
