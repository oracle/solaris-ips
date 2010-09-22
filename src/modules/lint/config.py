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
# Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.
#

# aspects of pkglint configuration

import ConfigParser
import os

defaults = {
    "log_level": "INFO",
    "do_pub_checks": "True",
    "info_classification_path":
        "/usr/share/package-manager/data/opensolaris.org.sections",
    "use_progress_tracker": "True",
    "pkglint.ext.opensolaris": "pkg.lint.opensolaris",
    "pkglint.ext.pkglint_actions": "pkg.lint.pkglint_action",
    "pkglint.ext.pkglint_manifests": "pkg.lint.pkglint_manifest",
    "pkglint.exclude": None,
    "version.pattern": "*,5.11-0."
    }

class PkglintConfig(object):
        def __init__(self, config_file=None):

                self.config = ConfigParser.SafeConfigParser(defaults)
                if not config_file:
                        self.config.readfp(open("/usr/share/lib/pkg/pkglintrc"))
                        self.config.read([os.path.expanduser("~/.pkglintrc")])
                else:
                        self.config.read(config_file)
