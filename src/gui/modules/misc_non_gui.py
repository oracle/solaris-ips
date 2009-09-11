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
import cPickle

import pkg.client.api as api
from pkg.client import global_settings

#The current version of the Client API the PM, UM and
#WebInstall GUIs have been tested against and are known to work with.
CLIENT_API_VERSION = 21

def get_cache_dir(api_object):
        img = api_object.img
        cache_dir = os.path.join(img.imgdir, "gui_cache")
        try:
                __mkdir(cache_dir)
        except OSError:
                cache_dir = None
        return cache_dir

def __mkdir(directory_path):
        if not os.path.isdir(directory_path):
                os.makedirs(directory_path)

def get_api_object(img_dir, progtrack):
        api_o = None
        api_o = api.ImageInterface(img_dir,
            CLIENT_API_VERSION,
            progtrack, None, global_settings.client_name)
        return api_o

def read_cache_file(file_path):
        fh = open(file_path, 'r')
        data = cPickle.load(fh)
        fh.close()
        return data

def dump_cache_file(file_path, data):
        fh = open(file_path,"w")
        cPickle.dump(data, fh, True)
        fh.close()
