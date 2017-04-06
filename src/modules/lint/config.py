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

#
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

# aspects of pkglint configuration

import os
import six
from collections import OrderedDict

from six.moves import configparser

defaults = {
    "log_level": "INFO",
    "do_pub_checks": "True",
    "ignore_different_publishers": "True",
    "info_classification_path":
        "/usr/share/lib/pkg/opensolaris.org.sections",
    "use_progress_tracker": "True",
    "pkglint.ext.opensolaris": "pkg.lint.opensolaris",
    "pkglint.ext.pkglint_actions": "pkg.lint.pkglint_action",
    "pkglint.ext.pkglint_manifests": "pkg.lint.pkglint_manifest",
    "pkglint.exclude": None,
    "version.pattern": "*,5.11-0."
    }

# Ensure the order of the items is the same.
defaults = OrderedDict(sorted(defaults.items(), key=lambda t: t[0]))

class PkglintConfigException(Exception):
        """An exception thrown when something fatal happens while reading the
        config.
        """
        pass

class PkglintConfig(object):
        def __init__(self, config_file=None):

                if config_file:
                        try:
                                # ConfigParser doesn't do a good job of
                                # error reporting, so we'll just try to open
                                # the file
                                open(config_file, "r").close()
                        except (EnvironmentError) as err:
                                raise PkglintConfigException(
                                    _("unable to read config file: {0} ").format(
                                    err))
                try:
                        if six.PY2:
                                self.config = configparser.SafeConfigParser(
                                    defaults)
                        else:
                                # SafeConfigParser has been renamed to
                                # ConfigParser in Python 3.2.
                                self.config = configparser.ConfigParser(
                                    defaults)
                        if not config_file:
                                if six.PY2:
                                        self.config.readfp(
                                            open("/usr/share/lib/pkg/pkglintrc"))
                                else:
                                        self.config.read_file(
                                            open("/usr/share/lib/pkg/pkglintrc"))
                                self.config.read(
                                    [os.path.expanduser("~/.pkglintrc")])
                        else:
                                self.config.read(config_file)

                        # sanity check our config by looking for a known key
                        self.config.get("pkglint", "log_level")
                except configparser.Error as err:
                        raise PkglintConfigException(
                            _("missing or corrupt pkglintrc file "
                            "{config_file}: {err}").format(**locals()))
