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
# Copyright (c) 2015, Oracle and/or its affiliates. All rights reserved.
#

import pkg
import pkg.client.client_api as entry
import pkg.client.progress as progress

# progress delay.
PROG_DELAY   = 5.0

rad2pkg_cmds_mapping = {
    "list_packages": "list",
    "set_publisher": "set-publisher",
    "unset_publisher": "unset-publisher",
    "exact_install": "exact-install"
    }

def __init_prog_tracker(prog_event_handler, prog_delay):
        """Initialize progress tracker."""

        progresstracker = progress.RADProgressTracker(
            prog_event_handler=prog_event_handler,
            term_delay=prog_delay)
        return progresstracker

def __correspond_pkg_cmd(rad_operation):
        """Need to replace rad operation names with pkg subcommand."""

        if rad_operation in rad2pkg_cmds_mapping:
                pkg_cmd = rad2pkg_cmds_mapping[rad_operation]
        else:
                pkg_cmd = rad_operation
        return pkg_cmd

def rad_get_input_schema(operation):
        """Get the input schema for RAD operation."""

        pkg_cmd = __correspond_pkg_cmd(operation)
        return entry._get_pkg_input_schema(pkg_cmd, opts_mapping)

def rad_get_output_schema(operation):
        """Get the output schema for RAD operation."""

        pkg_cmd = __correspond_pkg_cmd(operation)
        return entry._get_pkg_output_schema(pkg_cmd)

def rad_get_progress_schema():
        return progress.RADProgressTracker.get_json_schema()

def rad_pkg(subcommand, pargs_json=None, opts_json=None, pkg_image=None,
    prog_event_handler=None, prog_delay=PROG_DELAY):
        """Perform pkg operation.

        subcommand: a string type pkg subcommand.

        pargs_json: a JSON blob containing a list of pargs.

        opts_json: a JSON blob containing a dictionary of pkg
        subcommand options.

        pkg_image: a string type alternate image path.
        """

        ret_json = None

        rad_prog_tracker = __init_prog_tracker(prog_event_handler, prog_delay)
        try:
                ret_json = entry._pkg_invoke(subcommand=subcommand,
                    pargs_json=pargs_json, opts_json=opts_json,
                    pkg_image=pkg_image, prog_delay=prog_delay,
                    opts_mapping=opts_mapping, prog_tracker=rad_prog_tracker)
                return ret_json
        except Exception as ex:
                if not ret_json:
                        ret_json = {"status": 99, "errors": [{"reason":
                            str(ex)}]}
                return ret_json

#
# Mapping of the internal option name to an alternate name that user provided
# via keyword argument.
#
# {option_name: alternate_name}
#
#
opts_mapping = {}
