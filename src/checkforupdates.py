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
import gettext

import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress
import pkg.misc as misc
import pkg.gui.misc as gui_misc
from pkg.client import global_settings

UPDATES_AVAILABLE = 0
NO_UPDATES_AVAILABLE = 1
ERROR_OCCURRED = 2
PKG_CLIENT_NAME="updatemanagernotifier"


# Put _() in the global namespace
import __builtin__
__builtin__._ = gettext.gettext

def check_for_updates(image_directory):
        os.nice(20)
        global_settings.client_name = PKG_CLIENT_NAME
        pr = progress.NullProgressTracker()

        api_obj = gui_misc.get_api_object(image_directory, pr, None)
        api_obj.refresh()

        pkg_upgradeable = None
        for pkg, state in misc.get_inventory_list(api_obj.img, [],
           all_known=True, all_versions=False):
                if state["upgradable"] and state["state"] == "installed":
                        pkg_upgradeable = pkg
                        break
                
        if pkg_upgradeable != None:
                if debug:
                        print "Updates Available"
                sys.exit(UPDATES_AVAILABLE)
        else:
                if debug:
                        print "No updates Available"
                sys.exit(NO_UPDATES_AVAILABLE)

###############################################################################
#-----------------------------------------------------------------------------#
# Main
#-----------------------------------------------------------------------------#

def main(image_directory):
        check_for_updates(image_directory)
        return ERROR_OCCURRED

if __name__ == '__main__':
        debug = False
        if len(sys.argv) != 2:
                print "One argument, image directory must be specified"
                sys.exit(ERROR_OCCURRED)
        image_dir = sys.argv[1]
        main(image_dir)
