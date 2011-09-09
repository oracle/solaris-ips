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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#

import os
import socket
import urlparse
import urllib2
import cPickle
import logging
import logging.handlers
import platform
import sys

import pkg
import pkg.portable as portable
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.transport.exception as transport
from pkg.client import global_settings

# The current version of the Client API the PM, UM and
# WebInstall GUIs have been tested against and are known to work with.
CLIENT_API_VERSION = 70
LOG_DIR = "/var/tmp"
LOG_ERROR_EXT = "_error.log"
LOG_INFO_EXT = "_info.log"
PKG_CLIENT_NAME_UM = "updatemanager"
IMAGE_DIRECTORY_DEFAULT = "/"   # Image default directory
IMAGE_DIR_COMMAND = "svcprop -p update/image_dir svc:/application/pkg/update"


def get_image_path():
        try:
                image_directory = os.environ["PKG_IMAGE"]
        except KeyError:
                image_directory = \
                    os.popen(IMAGE_DIR_COMMAND).readline().rstrip()
                if len(image_directory) == 0:
                        image_directory = IMAGE_DIRECTORY_DEFAULT
        return image_directory

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

def get_os_version_and_build():
        os_ver = portable.util.get_os_release()
        os_name = portable.util.get_canonical_os_name()
        if os_name == 'sunos':
                os_ver += " (" + platform.uname()[3] + ")"
        return os_ver

def setup_logging(client_name):
        normal_setup = True
        log_path = os.path.join(LOG_DIR, client_name)
        err_str = ""

        infolog_path = log_path + LOG_INFO_EXT
        try:
                info_h = logging.handlers.RotatingFileHandler(infolog_path,
                    maxBytes=1000000, backupCount=1)
        except IOError, e:
                err_str = _("WARNING: %s\nUnable to setup log:\n ") % client_name
                err_str += str(e)
                err_str += _("\n  All info messages will be logged to stdout")
                normal_setup = False

        errlog_path = log_path + LOG_ERROR_EXT
        try:
                err_h = logging.handlers.RotatingFileHandler(errlog_path,
                    maxBytes=1000000, backupCount=1)
        except IOError, e:
                if err_str == "":
                        err_str =  _("WARNING: %s\nUnable to setup log:\n ") % \
                                client_name
                else:
                        err_str +=  _("\n ")
                err_str += str(e)
                err_str += _("\n  All errors and warnings will be logged to stderr")
                normal_setup = False

        if  normal_setup:
                log_fmt = logging.Formatter(
                    "<b>%(levelname)s:</b> " + client_name + \
                    "\n%(asctime)s: %(filename)s: %(module)s: "
                    "%(lineno)s:\n%(message)s")
        else:
                if client_name != PKG_CLIENT_NAME_UM and err_str != "":
                        print err_str
                log_fmt = logging.Formatter(
                    "%(levelname)s: " + client_name + \
                    "\n%(asctime)s: %(filename)s: %(module)s: "
                    "%(lineno)s:\n%(message)s")
                info_h = logging.StreamHandler(sys.stdout)
                err_h = logging.StreamHandler(sys.stderr)

        info_t = _LogFilter(logging.INFO)
        info_h.addFilter(info_t)
        info_h.setFormatter(log_fmt)
        info_h.setLevel(logging.INFO)
        global_settings.info_log_handler = info_h

        err_h.setFormatter(log_fmt)
        err_h.setLevel(logging.WARNING)
        global_settings.error_log_handler = err_h
        
        return normal_setup

def shutdown_logging():
        try:
                global_settings.reset_logging()
                logging.shutdown()
        except IOError:
                pass

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
        except IOError:
                pass
        except:
                pass
        return data

def dump_cache_file(file_path, data):
        try:
                fh = open(file_path,"w")
                cPickle.dump(data, fh, True)
                fh.close()
        except IOError:
                pass
        except:
                pass

def get_um_name():
        return PKG_CLIENT_NAME_UM

def get_catalogrefresh_exception_msg(cre):
        framework_error = False
        if not isinstance(cre, api_errors.CatalogRefreshException):
                return ("", False)
        msg = _("Catalog refresh error:\n")
        if cre.succeeded < cre.total:
                msg += _(
                    "Only %(suc)s out of %(tot)s catalogs successfully updated.\n") % \
                    {"suc": cre.succeeded, "tot": cre.total}

        for pub, err in cre.failed:
                if isinstance(err, urllib2.HTTPError):
                        msg += "%s: %s - %s" % \
                            (err.filename, err.code, err.msg)
                elif isinstance(err, urllib2.URLError):
                        if err.args[0][0] == 8:
                                msg += "%s: %s" % \
                                    (urlparse.urlsplit(
                                        pub["origin"])[1].split(":")[0],
                                    err.args[0][1])
                        else:
                                if isinstance(err.args[0], socket.timeout):
                                        msg += "%s: %s" % \
                                            (pub["origin"], "timeout")
                                else:
                                        msg += "%s: %s" % \
                                            (pub["origin"], err.args[0][1])
                else:
                        framework_error = is_frameworkerror(err)
                        msg += str(err)

        if cre.errmessage:
                msg += cre.errmessage

        return (msg, framework_error)

def is_frameworkerror(err):
        if isinstance(err, transport.TransportFailures):
                for exp in err.exceptions:
                        if isinstance(exp, transport.TransportFrameworkError) and \
                            exp.code == 56:
                                return True
        return False
            
