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
import time
import getopt

import pkg.client.progress as progress
import pkg.client.api_errors as api_errors
import pkg.gui.misc as gui_misc
import pkg.gui.enumerations as enumerations
from pkg.client import global_settings
from cPickle import UnpicklingError

PKG_CLIENT_NAME = "check_for_updates"
CACHE_VERSION =  1
CACHE_NAME = ".last_refresh_cache"

def __check_for_updates(image_directory, nice):
        if nice:
                os.nice(20)
        global_settings.client_name = PKG_CLIENT_NAME
        pr = progress.NullProgressTracker()

        api_obj = gui_misc.get_api_object(image_directory, pr, None)
        if api_obj == None:
                return enumerations.UPDATES_UNDETERMINED
        ret = __check_last_refresh(api_obj)
        if ret != enumerations.UPDATES_UNDETERMINED:
                return ret
        elif debug:
                print "Updates undetermined in check_last_refresh"

        try:
                stuff_to_do, opensolaris_image, cre = \
                    api_obj.plan_update_all(sys.argv[0],
                    refresh_catalogs = True,
                    noexecute = True, force = True, verbose = False) 
        except api_errors.ApiException, e:
                if debug:
                        print "Exception occurred: ", str(e)
                return enumerations.UPDATES_UNDETERMINED
        if debug:
                print "stuff_to_do: ", stuff_to_do
                print "opensolaris_image: ", opensolaris_image
                print "cre: ", cre

        if cre and not cre.succeeded:
                if debug:
                        print "Error occurred in plan_update_all"
                return enumerations.UPDATES_UNDETERMINED
        __dump_updates_available(api_obj, stuff_to_do)
        if stuff_to_do:
                if debug:
                        print "Updates Available"
                return enumerations.UPDATES_AVAILABLE
        else:
                if debug:
                        print "No updates Available"
                return enumerations.NO_UPDATES_AVAILABLE

def __check_last_refresh(api_obj):
        cache_dir = gui_misc.get_cache_dir(api_obj)
        if not cache_dir:
                return enumerations.UPDATES_UNDETERMINED
        try:
                info = gui_misc.read_cache_file(os.path.join(
                    cache_dir, CACHE_NAME + '.cpl'))
                if info.get("version") != CACHE_VERSION:
                        return enumerations.UPDATES_UNDETERMINED
                old_publishers = info.get("publishers")
                count = 0
                for p in api_obj.get_publishers():
                        if p.disabled:
                                continue
                        try:
                                if old_publishers[p.prefix] != p.last_refreshed:
                                        return enumerations.UPDATES_UNDETERMINED
                        except KeyError:
                                return enumerations.UPDATES_UNDETERMINED
                        count += 1

                if count != len(old_publishers):
                        return enumerations.UPDATES_UNDETERMINED
                if info.get("updates_available"):
                        return enumerations.UPDATES_AVAILABLE
                else:
                        return enumerations.NO_UPDATES_AVAILABLE

        except (UnpicklingError, IOError):
                return enumerations.UPDATES_UNDETERMINED

def __dump_updates_available(api_obj, stuff_to_do):
        cache_dir = gui_misc.get_cache_dir(api_obj)
        if not cache_dir:
                return
        publisher_list = {}
        for p in api_obj.get_publishers():
                if p.disabled:
                        continue
                publisher_list[p.prefix] = p.last_refreshed
        if debug:
                print "publisher_list:", publisher_list
        dump_info = {}
        dump_info["version"] = CACHE_VERSION
        dump_info["updates_available"] = stuff_to_do
        dump_info["publishers"] = publisher_list

        try:
                gui_misc.dump_cache_file(os.path.join(
                    cache_dir, CACHE_NAME + '.cpl'), dump_info)
        except IOError, e:
                if debug:
                        print "Failed to dump cache: %s" % str(e)

        return

###############################################################################
#-----------------------------------------------------------------------------#
# Main
#-----------------------------------------------------------------------------#

def main(image_directory, nice):
        return __check_for_updates(image_directory, nice)

if __name__ == '__main__':
        debug = False
        set_nice = False
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "n", ["nice"])
        except getopt.GetoptError, ex:
                print "Usage: illegal option -- %s" % ex.opt
                sys.exit(enumerations.UPDATES_UNDETERMINED)
        if len(pargs) != 1:
                print "Usage: One argument, image directory must be specified"
                sys.exit(enumerations.UPDATES_UNDETERMINED)
        image_dir = pargs[0]
        for opt, args in opts:
                if debug:
                        print "opt: ", opt
                        print "args: ", args
                if opt in ( "-n", "--nice"):
                        set_nice = True
        if debug:
                print "Start check_for_updates for: ", image_dir, set_nice
                a = time.time()
        return_value = main(image_dir, set_nice)
        if debug:
                print "time taken: ", time.time() - a
        sys.exit(return_value)
