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
# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.
#

import os
import sys
import time
import getopt
import gettext
import locale

import pkg.client.progress as progress
import pkg.client.api_errors as api_errors
import pkg.gui.misc_non_gui as nongui_misc
import pkg.gui.enumerations as enumerations
import pkg.misc as misc
from pkg.client import global_settings
from cPickle import UnpicklingError

PKG_CLIENT_NAME = "check_for_updates"
CACHE_VERSION =  3
CACHE_NAME = ".last_refresh_cache"

def __check_for_updates(image_directory, nice, silent):
        if nice:
                os.nice(20)
        global_settings.client_name = PKG_CLIENT_NAME
        pr = progress.NullProgressTracker()

        message = None
        try:
                api_obj = nongui_misc.get_api_object(image_directory, pr)
        except api_errors.VersionException, e:
                message = "Version mismatch: expected version %d, got version %d" % \
                    (e.expected_version, e.received_version)
        except api_errors.ImageNotFoundException, e:
                message = "%s is not an install image" % e.user_dir
        except api_errors.ApiException, e:
                message = "Unexpected exception: %s" % str(e)
        if message != None:
                if debug:
                        print "Failed to get Api object: %s" % message
                return enumerations.UPDATES_UNDETERMINED

        if api_obj == None:
                return enumerations.UPDATES_UNDETERMINED
        ret = __check_last_refresh(api_obj, silent)
        if ret != enumerations.UPDATES_UNDETERMINED:
                return ret
        elif debug:
                print "Updates undetermined in check_last_refresh"

        try:
                stuff_to_do, opensolaris_image = \
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

        __dump_updates_available(api_obj, stuff_to_do, silent)
        if stuff_to_do:
                if debug:
                        print "Updates Available"
                return enumerations.UPDATES_AVAILABLE
        else:
                if debug:
                        print "No updates Available"
                return enumerations.NO_UPDATES_AVAILABLE

def __check_last_refresh(api_obj, silent):
        cache_dir = nongui_misc.get_cache_dir(api_obj)
        if not cache_dir:
                return enumerations.UPDATES_UNDETERMINED
        try:
                info = nongui_misc.read_cache_file(os.path.join(
                    cache_dir, CACHE_NAME + '.cpl'))
                if len(info) == 0:
                        if debug:
                                print "No cache"
                        return enumerations.UPDATES_UNDETERMINED
                # pylint: disable-msg=E1103
                if info.get("version") != CACHE_VERSION:
                        if debug:
                                print "Cache version mismatch:", \
                                    info.get("version"), CACHE_VERSION
                        return enumerations.UPDATES_UNDETERMINED
                if info.get("os_release") != os.uname()[2]:
                        if debug:
                                print "OS release mismatch:", \
                                    info.get("os_release"), os.uname()[2]
                        return enumerations.UPDATES_UNDETERMINED
                if info.get("os_version") != os.uname()[3]:
                        if debug:
                                print "OS version mismatch:", \
                                    info.get("os_version"), os.uname()[3]
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
                n_updates = 0
                n_installs = 0
                n_removes = 0
                if info.get("updates_available"):
                        n_updates = info.get("updates")
                        n_installs = info.get("installs")
                        n_removes = info.get("removes")
                # pylint: enable-msg=E1103
                if not silent:
                        if n_updates > 0:
                                print "n_updates: ", n_updates
                        if n_installs > 0:
                                print "n_installs: ", n_installs
                        if n_removes > 0:
                                print "n_removes: ", n_removes
                if (n_updates + n_installs + n_removes) > 0:
                        return enumerations.UPDATES_AVAILABLE
                else:
                        return enumerations.NO_UPDATES_AVAILABLE

        except (UnpicklingError, IOError):
                return enumerations.UPDATES_UNDETERMINED

def __dump_updates_available(api_obj, stuff_to_do, silent):
        cache_dir = nongui_misc.get_cache_dir(api_obj)
        if not cache_dir:
                return
        publisher_list = {}
        for p in api_obj.get_publishers():
                if p.disabled:
                        continue
                publisher_list[p.prefix] = p.last_refreshed
        if debug:
                print "publisher_list:", publisher_list
        n_installs = 0
        n_removes = 0
        n_updates = 0
        plan_desc = api_obj.describe()
        if plan_desc:
                plan = plan_desc.get_changes()
                for pkg_plan in plan:
                        orig = pkg_plan[0]
                        dest = pkg_plan[1]
                        if orig and dest:
                                n_updates += 1
                        elif not orig and dest:
                                n_installs += 1
                        elif orig and not dest:
                                n_removes += 1
        dump_info = {}
        dump_info["version"] = CACHE_VERSION
        dump_info["os_release"] = os.uname()[2]
        dump_info["os_version"] = os.uname()[3]
        dump_info["updates_available"] = stuff_to_do
        dump_info["publishers"] = publisher_list
        dump_info["updates"] = n_updates
        dump_info["installs"] = n_installs
        dump_info["removes"] = n_removes
        if not silent:
                print "n_updates: ", n_updates
                print "n_installs: ", n_installs
                print "n_removes: ", n_removes

        try:
                nongui_misc.dump_cache_file(os.path.join(
                    cache_dir, CACHE_NAME + '.cpl'), dump_info)
        except IOError, e:
                if debug:
                        print "Failed to dump cache: %s" % str(e)

        return

###############################################################################
#-----------------------------------------------------------------------------#
# Main
#-----------------------------------------------------------------------------#

def main(image_directory, nice, silent):
        return __check_for_updates(image_directory, nice, silent)

if __name__ == '__main__':
        misc.setlocale(locale.LC_ALL, "")
        gettext.install("pkg", "/usr/share/locale")
        debug = False
        set_nice = False
        set_silent = False
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "ns", ["nice", "silent"])
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
                elif opt in ( "-s", "--silent"):
                        set_silent = True
        if debug:
                print "Start check_for_updates for: ", image_dir, set_nice, set_silent
                a = time.time()
        return_value = main(image_dir, set_nice, set_silent)
        if debug:
                print "time taken: ", time.time() - a
        sys.exit(return_value)
