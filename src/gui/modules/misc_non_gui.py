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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import cPickle
import logging
import logging.handlers
import sys

import pkg
import pkg.client.api as api
from pkg.client import global_settings

# The current version of the Client API the PM, UM and
# WebInstall GUIs have been tested against and are known to work with.
CLIENT_API_VERSION = 37
LOG_DIR = "/var/tmp"
LOG_ERROR_EXT = "_error.log"
LOG_INFO_EXT = "_info.log"

def get_log_dir():
        return LOG_DIR

def get_log_error_ext():
        return LOG_ERROR_EXT

def get_log_info_ext():
        return LOG_INFO_EXT

class _LogFilter(logging.Filter):
        def __init__(self, max_level=logging.CRITICAL):
                logging.Filter.__init__(self)
                self.max_level = max_level

        def filter(self, record):
                return record.levelno <= self.max_level

def get_version():
        return pkg.VERSION

def setup_logging(client_name):
        log_path = os.path.join(LOG_DIR, client_name)
        log_fmt = logging.Formatter(
            "<b>%(levelname)s:</b> " + client_name + \
            "\n%(asctime)s: %(filename)s: %(module)s: %(lineno)s:\n%(message)s")

        infolog_path = log_path + LOG_INFO_EXT
        try:
                info_h = logging.handlers.RotatingFileHandler(infolog_path,
                    maxBytes=1000000, backupCount=1)
        except IOError:
                info_h = logging.StreamHandler(sys.stdout)

        info_t = _LogFilter(logging.INFO)
        info_h.addFilter(info_t)
        info_h.setFormatter(log_fmt)
        info_h.setLevel(logging.INFO)
        global_settings.info_log_handler = info_h

        errlog_path = log_path + LOG_ERROR_EXT
        try:
                err_h = logging.handlers.RotatingFileHandler(errlog_path,
                    maxBytes=1000000, backupCount=1)
        except IOError:
                err_h = logging.StreamHandler(sys.stderr)

        err_h.setFormatter(log_fmt)
        err_h.setLevel(logging.WARNING)
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
        data = []
        try:
                fh = open(file_path, 'r')
                data = cPickle.load(fh)
                fh.close()
        except:
                pass
        return data

def dump_cache_file(file_path, data):
        try:
                fh = open(file_path,"w")
                cPickle.dump(data, fh, True)
                fh.close()
        except:
                pass
