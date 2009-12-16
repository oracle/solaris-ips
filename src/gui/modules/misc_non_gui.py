#!/usr/bin/python
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
import logging
import logging.handlers
import sys

import pkg.client.api as api
from pkg.client import global_settings

# The current version of the Client API the PM, UM and
# WebInstall GUIs have been tested against and are known to work with.
CLIENT_API_VERSION = 26

class _LogFilter(logging.Filter):
        def __init__(self, max_level=logging.CRITICAL):
                logging.Filter.__init__(self)
                self.max_level = max_level

        def filter(self, record):
                return record.levelno <= self.max_level


def setup_logging(client_name):
        # TBD: for now just put the logs in /var/tmp
        # GUI can consume and present them to the user
        log_path = os.path.join("/var/tmp", client_name)
        log_fmt = logging.Formatter(
            "%(asctime)s: %(levelname)s: " + client_name +
            ": %(filename)s: %(module)s: %(lineno)s: %(message)s")

        infolog_path = log_path + "_info.log"
        infolog_exists = False

        try:
                info_h = logging.handlers.RotatingFileHandler(infolog_path, backupCount=5)
                infolog_exists = os.path.exists(infolog_path)
        except IOError:
                info_h = logging.StreamHandler(sys.stdout)

        info_t = _LogFilter(logging.INFO)
        info_h.addFilter(info_t)
        info_h.setFormatter(log_fmt)
        info_h.setLevel(logging.INFO)
        if infolog_exists:
                info_h.doRollover()
        global_settings.info_log_handler = info_h

        errlog_path = log_path + "_error.log"
        errlog_exists = False

        try:
                err_h = logging.handlers.RotatingFileHandler(errlog_path, backupCount=5)
                errlog_exists = os.path.exists(errlog_path)
        except IOError:
                err_h = logging.StreamHandler(sys.stderr)

        err_h.setFormatter(log_fmt)
        err_h.setLevel(logging.WARNING)
        if errlog_exists:
                err_h.doRollover()
        global_settings.error_log_handler = err_h

def shutdown_logging():
        global_settings.reset_logging()
        logging.shutdown()

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
