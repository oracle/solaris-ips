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

# Copyright (c) 2014, Oracle and/or its affiliates. All rights reserved.

import os

import pkg.client.pkgdefs as pkgdefs
import pkg.client.linkedimage as li
import pkg.misc as misc

from pkg.client.api_errors import InvalidOptionError
from pkg.client import global_settings

_orig_cwd = None

# List of available options for common option processing.
ACCEPT                = "accept"
ALLOW_RELINK          = "allow_relink"
ATTACH_CHILD          = "attach_child"
ATTACH_PARENT         = "attach_parent"
BACKUP_BE             = "backup_be"
BACKUP_BE_NAME        = "backup_be_name"
BE_ACTIVATE           = "be_activate"
BE_NAME               = "be_name"
CONCURRENCY           = "concurrency"
DENY_NEW_BE           = "deny_new_be"
FORCE                 = "force"
LI_IGNORE             = "li_ignore"
LI_IGNORE_ALL         = "li_ignore_all"
LI_IGNORE_LIST        = "li_ignore_list"
LI_MD_ONLY            = "li_md_only"
LI_NAME               = "li_name"
LI_PARENT_SYNC        = "li_parent_sync"
LI_PKG_UPDATES        = "li_pkg_updates"
LI_PROPS              = "li_props"
LI_TARGET_ALL         = "li_target_all"
LI_TARGET_LIST        = "li_target_list"
LIST_ALL              = "list_all"
LIST_INSTALLED_NEWEST = "list_installed_newest"
LIST_NEWEST           = "list_newest"
LIST_UPGRADABLE       = "list_upgradable"
MED_IMPLEMENTATION    = "med_implementation"
MED_VERSION           = "med_version"
NEW_BE                = "new_be"
NO_BACKUP_BE          = "no_backup_be"
NOEXECUTE             = "noexecute"
OMIT_HEADERS          = "omit_headers"
ORIGINS               = "origins"
PARSABLE_VERSION      = "parsable_version"
QUIET                 = "quiet"
REFRESH_CATALOGS      = "refresh_catalogs"
REJECT_PATS           = "reject_pats"
REQUIRE_BACKUP_BE     = "require_backup_be"
REQUIRE_NEW_BE        = "require_new_be"
SHOW_LICENSES         = "show_licenses"
STAGE                 = "stage"
SUMMARY               = "summary"
TAGGED                = "tagged"
UPDATE_INDEX          = "update_index"
VERBOSE               = "verbose"
SYNC_ACT              = "sync_act"
ACT_TIMEOUT           = "act_timeout"



def opts_table_cb_beopts(api_inst, opts, opts_new):

        # synthesize require_new_be and deny_new_be into new_be
        del opts_new[REQUIRE_NEW_BE]
        del opts_new[DENY_NEW_BE]
        opts_new[NEW_BE] = None

        if (opts[BE_NAME] or opts[REQUIRE_NEW_BE]) and opts[DENY_NEW_BE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [REQUIRE_NEW_BE, DENY_NEW_BE])

        # create a new key called BACKUP_BE in the options array
        if opts[REQUIRE_NEW_BE] or opts[BE_NAME]:
                opts_new[NEW_BE] = True
        if opts[DENY_NEW_BE]:
                opts_new[NEW_BE] = False

        # synthesize require_backup_be and no_backup_be into backup_be
        del opts_new[REQUIRE_BACKUP_BE]
        del opts_new[NO_BACKUP_BE]
        opts_new[BACKUP_BE] = None

        if (opts[REQUIRE_BACKUP_BE] or opts[BACKUP_BE_NAME]) and \
            opts[NO_BACKUP_BE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [REQUIRE_BACKUP_BE, NO_BACKUP_BE])

        if (opts[REQUIRE_BACKUP_BE] or opts[BACKUP_BE_NAME]) and \
            (opts[REQUIRE_NEW_BE] or opts[BE_NAME]):
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [REQUIRE_BACKUP_BE, REQUIRE_NEW_BE])

        # create a new key called BACKUP_BE in the options array
        if opts[REQUIRE_BACKUP_BE] or opts[BACKUP_BE_NAME]:
                opts_new[BACKUP_BE] = True
        if opts[NO_BACKUP_BE]:
                opts_new[BACKUP_BE] = False

def opts_table_cb_li_ignore(api_inst, opts, opts_new):

        # synthesize li_ignore_all and li_ignore_list into li_ignore
        del opts_new[LI_IGNORE_ALL]
        del opts_new[LI_IGNORE_LIST]
        opts_new[LI_IGNORE] = None

        # check if there's nothing to ignore
        if not opts[LI_IGNORE_ALL] and not opts[LI_IGNORE_LIST]:
                return

        if opts[LI_IGNORE_ALL]:

                # can't ignore all and specific images
                if opts[LI_IGNORE_LIST]:
                        raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                            [LI_IGNORE_ALL, LI_IGNORE_LIST])

                # can't ignore all and target anything.
                if LI_TARGET_ALL in opts and opts[LI_TARGET_ALL]:
                        raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                            [LI_IGNORE_ALL, LI_TARGET_ALL])
                if LI_TARGET_LIST in opts and opts[LI_TARGET_LIST]:
                        raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                            [LI_IGNORE_ALL, LI_TARGET_LIST])
                if LI_NAME in opts and opts[LI_NAME]:
                        raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                            [LI_IGNORE_ALL, LI_NAME])
                opts_new[LI_IGNORE] = []
                return

        assert opts[LI_IGNORE_LIST]

        # it doesn't make sense to specify images to ignore if the
        # user is already specifying images to operate on.
        if LI_TARGET_ALL in opts and opts[LI_TARGET_ALL]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [LI_IGNORE_LIST, LI_TARGET_ALL])
        if LI_TARGET_LIST in opts and opts[LI_TARGET_LIST]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [LI_IGNORE_LIST, LI_TARGET_LIST])
        if LI_NAME in opts and opts[LI_NAME]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [LI_IGNORE_LIST, LI_NAME])

        li_ignore = []
        for li_name in opts[LI_IGNORE_LIST]:
                # check for repeats
                if li_name in li_ignore:
                        raise InvalidOptionError(
                            InvalidOptionError.ARG_REPEAT, [li_name,
                            LI_IGNORE_LIST])
                # add to ignore list
                li_ignore.append(li_name)

        opts_new[LI_IGNORE] = api_inst.parse_linked_name_list(li_ignore)

def opts_table_cb_li_no_psync(api_inst, opts, opts_new):
        # if a target child linked image was specified, the no-parent-sync
        # option doesn't make sense since we know that both the parent and
        # child image are accessible

        if LI_TARGET_ALL not in opts:
                # we don't accept linked image target options
                assert LI_TARGET_LIST not in opts
                return

        if opts[LI_TARGET_ALL] and not opts[LI_PARENT_SYNC]:
                raise InvalidOptionError(InvalidOptionError.REQUIRED,
                    [LI_TARGET_ALL, LI_PARENT_SYNC])

        if opts[LI_TARGET_LIST] and not opts[LI_PARENT_SYNC]:
                raise InvalidOptionError(InvalidOptionError.REQUIRED,
                    [LI_TARGET_LIST, LI_PARENT_SYNC])


def __parse_linked_props(args):
        """"Parse linked image property options that were specified on the
        command line into a dictionary.  Make sure duplicate properties were
        not specified."""

        linked_props = dict()
        for pv in args:
                try:
                        p, v = pv.split("=", 1)
                except ValueError:
                        raise InvalidOptionError(msg=_("linked image "
                            "property arguments must be of the form "
                            "'<name>=<value>'."))

                if p not in li.prop_values:
                        raise InvalidOptionError(msg=_("invalid linked "
                        "image property: '%s'.") % p)

                if p in linked_props:
                        raise InvalidOptionError(msg=_("linked image "
                            "property specified multiple times: '%s'.") % p)

                linked_props[p] = v

        return linked_props

def opts_table_cb_li_props(api_inst, opts, opts_new):
        """convert linked image prop list into a dictionary"""

        opts_new[LI_PROPS] = __parse_linked_props(opts[LI_PROPS])

def opts_table_cb_li_target(api_inst, opts, opts_new):
        # figure out which option the user specified
        if opts[LI_TARGET_ALL] and opts[LI_TARGET_LIST]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [LI_TARGET_ALL, LI_TARGET_LIST])
        elif opts[LI_TARGET_ALL]:
                arg1 = LI_TARGET_ALL
        elif opts[LI_TARGET_LIST]:
                arg1 = LI_TARGET_LIST
        else:
                return

        if BE_ACTIVATE in opts and not opts[BE_ACTIVATE]:
                raise InvalidOptionError(InvalidOptionError.REQUIRED,
                    [arg1, BE_ACTIVATE])
        if BE_NAME in opts and opts[BE_NAME]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, BE_NAME])
        if DENY_NEW_BE in opts and opts[DENY_NEW_BE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, DENY_NEW_BE])
        if REQUIRE_NEW_BE in opts and opts[REQUIRE_NEW_BE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, REQUIRE_NEW_BE])
        if REJECT_PATS in opts and opts[REJECT_PATS]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, REJECT_PATS])
        if ORIGINS in opts and opts[ORIGINS]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, ORIGINS])

        # validate linked image name
        li_target_list = []
        for li_name in opts[LI_TARGET_LIST]:
                # check for repeats
                if li_name in li_target_list:
                        raise InvalidOptionError(
                            InvalidOptionError.ARG_REPEAT, [li_name,
                            LI_TARGET_LIST])
                # add to ignore list
                li_target_list.append(li_name)

        opts_new[LI_TARGET_LIST] = \
            api_inst.parse_linked_name_list(li_target_list)

def opts_table_cb_li_target1(api_inst, opts, opts_new):
        # figure out which option the user specified
        if opts[LI_NAME]:
                arg1 = LI_NAME
        else:
                return

        if BE_ACTIVATE in opts and not opts[BE_ACTIVATE]:
                raise InvalidOptionError(InvalidOptionError.REQUIRED,
                    [arg1, BE_ACTIVATE])
        if BE_NAME in opts and opts[BE_NAME]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, BE_NAME])
        if DENY_NEW_BE in opts and opts[DENY_NEW_BE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, DENY_NEW_BE])
        if REQUIRE_NEW_BE in opts and opts[REQUIRE_NEW_BE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, REQUIRE_NEW_BE])
        if REJECT_PATS in opts and opts[REJECT_PATS]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, REJECT_PATS])
        if ORIGINS in opts and opts[ORIGINS]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, ORIGINS])

def opts_table_cb_no_headers_vs_quiet(api_inst, opts, opts_new):
        # check if we accept the -q option
        if QUIET not in opts:
                return

        # -q implies -H
        if opts[QUIET]:
                opts_new[OMIT_HEADERS] = True

def opts_table_cb_q(api_inst, opts, opts_new):
        # Be careful not to overwrite global_settings.client_output_quiet
        # because it might be set "True" from elsewhere, e.g. in
        # opts_table_cb_parsable.
        if opts[QUIET] is True:
                global_settings.client_output_quiet = True

def opts_table_cb_v(api_inst, opts, opts_new):
        global_settings.client_output_verbose = opts[VERBOSE]

def opts_table_cb_nqv(api_inst, opts, opts_new):
        if opts[VERBOSE] and opts[QUIET]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [VERBOSE, QUIET])

def opts_table_cb_parsable(api_inst, opts, opts_new):
        if opts[PARSABLE_VERSION] and opts.get(VERBOSE, False):
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [VERBOSE, PARSABLE_VERSION])
        if opts[PARSABLE_VERSION]:
                try:
                        opts_new[PARSABLE_VERSION] = int(
                            opts[PARSABLE_VERSION])
                except ValueError:
                        raise InvalidOptionError(
                            options=[PARSABLE_VERSION],
                            msg=_("integer argument expected"))

                global_settings.client_output_parsable_version = \
                    opts_new[PARSABLE_VERSION]
                opts_new[QUIET] = True
                global_settings.client_output_quiet = True

def opts_table_cb_origins(api_inst, opts, opts_new):
        origins = set()
        for o in opts[ORIGINS]:
                origins.add(misc.parse_uri(o, cwd=_orig_cwd))
        opts_new[ORIGINS] = origins

def opts_table_cb_stage(api_inst, opts, opts_new):
        if opts[STAGE] == None:
                opts_new[STAGE] = pkgdefs.API_STAGE_DEFAULT
                return

        if opts_new[STAGE] not in pkgdefs.api_stage_values:
                raise InvalidOptionError(msg=_("invalid operation stage: "
                    "'%s'") % opts[STAGE])

def opts_cb_li_attach(api_inst, opts, opts_new):
        if opts[ATTACH_PARENT] and opts[ATTACH_CHILD]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [ATTACH_PARENT, ATTACH_CHILD])

        if not opts[ATTACH_PARENT] and not opts[ATTACH_CHILD]:
                raise InvalidOptionError(InvalidOptionError.XOR,
                    [ATTACH_PARENT, ATTACH_CHILD])

        if opts[ATTACH_CHILD]:
                # if we're attaching a new child then that doesn't affect
                # any other children, so ignoring them doesn't make sense.
                if opts[LI_IGNORE_ALL]:
                        raise InvalidOptionError(
                            InvalidOptionError.INCOMPAT,
                            [ATTACH_CHILD, LI_IGNORE_ALL])
                if opts[LI_IGNORE_LIST]:
                        raise InvalidOptionError(
                            InvalidOptionError.INCOMPAT,
                            [ATTACH_CHILD, LI_IGNORE_LIST])

def opts_table_cb_md_only(api_inst, opts, opts_new):
        # if the user didn't specify linked-md-only we're done
        if not opts[LI_MD_ONLY]:
                return

        # li_md_only implies no li_pkg_updates
        if LI_PKG_UPDATES in opts:
                opts_new[LI_PKG_UPDATES] = False

        #
        # if li_md_only is false that means we're not updating any packages
        # within the current image so there are a ton of options that no
        # longer apply to the current operation, and hence are incompatible
        # with li_md_only.
        #
        arg1 = LI_MD_ONLY
        if BE_NAME in opts and opts[BE_NAME]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, BE_NAME])
        if DENY_NEW_BE in opts and opts[DENY_NEW_BE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, DENY_NEW_BE])
        if REQUIRE_NEW_BE in opts and opts[REQUIRE_NEW_BE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, REQUIRE_NEW_BE])
        if LI_PARENT_SYNC in opts and not opts[LI_PARENT_SYNC]:
                raise InvalidOptionError(InvalidOptionError.REQUIRED,
                    [arg1, LI_PARENT_SYNC])
        if REJECT_PATS in opts and opts[REJECT_PATS]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [arg1, REJECT_PATS])

def opts_cb_list(api_inst, opts, opts_new):
        if opts_new[ORIGINS] and opts_new[LIST_UPGRADABLE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [ORIGINS, LIST_UPGRADABLE])

        if opts_new[ORIGINS] and not opts_new[LIST_NEWEST]:
                # Use of -g implies -a unless -n is provided.
                opts_new[LIST_INSTALLED_NEWEST] = True

        if opts_new[LIST_ALL] and not opts_new[LIST_INSTALLED_NEWEST]:
                raise InvalidOptionError(InvalidOptionError.REQUIRED,
                    [LIST_ALL, LIST_INSTALLED_NEWEST])

        if opts_new[LIST_INSTALLED_NEWEST] and opts_new[LIST_NEWEST]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [LIST_INSTALLED_NEWEST, LIST_NEWEST])

        if opts_new[LIST_INSTALLED_NEWEST] and opts_new[LIST_UPGRADABLE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [LIST_INSTALLED_NEWEST, LIST_UPGRADABLE])

        if opts_new[SUMMARY] and opts_new[VERBOSE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [SUMMARY, VERBOSE])

        if opts_new[QUIET] and opts_new[VERBOSE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [QUIET, VERBOSE])

def opts_cb_int(k, api_inst, opts, opts_new, minimum=None):

        if k not in opts or opts[k] == None:
                err = _("missing required parameter")
                raise InvalidOptionError(msg=err, options=[k])

        # get the original argument value
        v = opts[k]

        # make sure it is an integer
        try:
                v = int(v)
        except (ValueError, TypeError):
                # not a valid integer
                err = _("value '%s' invalid") % (v)
                raise InvalidOptionError(msg=err, options=[k])

        # check the minimum bounds
        if minimum is not None and v < minimum:
                err = _("value must be >= %d") % (minimum)
                raise InvalidOptionError(msg=err, options=[k])

        # update the new options array to make the value an integer
        opts_new[k] = v

def opts_cb_fd(k, api_inst, opts, opts_new):
        opts_cb_int(k, api_inst, opts, opts_new, minimum=0)

        err = _("value '%s' invalid") % (opts_new[k])
        try:
                os.fstat(opts_new[k])
        except OSError:
                # not a valid file descriptor
                raise InvalidOptionError(msg=err, options=[k])

def opts_table_cb_concurrency(api_inst, opts, opts_new):
        if opts[CONCURRENCY] is None:
                # remove concurrency from parameters dict
                del opts_new[CONCURRENCY]
                return

        # make sure we have an integer
        opts_cb_int(CONCURRENCY, api_inst, opts, opts_new)

        # update global concurrency setting
        global_settings.client_concurrency = opts_new[CONCURRENCY]
        global_settings.client_concurrency_set = True

        # remove concurrency from parameters dict
        del opts_new[CONCURRENCY]

def opts_table_cb_actuators(api_inst, opts, opts_new):

        del opts_new[ACT_TIMEOUT]
        del opts_new[SYNC_ACT]

        if opts[ACT_TIMEOUT]:
                # make sure we have an integer
                opts_cb_int(ACT_TIMEOUT, api_inst, opts, opts_new)
        elif opts[SYNC_ACT]:
                # -1 is no timeout
                opts_new[ACT_TIMEOUT] = -1
        else:
                # 0 is no sync actuators are used (timeout=0)
                opts_new[ACT_TIMEOUT] = 0

#
# options common to multiple pkg(1) operations.  The format for specifying
# options is a list which can contain:
#
# - Tuples formatted as:
#       (k, v)
#   where the values are:
#       k: the key value for the options dictionary
#       v: the default value. valid values are: True/False, None, [], 0
#


opts_table_beopts = [
    opts_table_cb_beopts,
    (BACKUP_BE_NAME,     None),
    (BE_NAME,            None),
    (DENY_NEW_BE,        False),
    (NO_BACKUP_BE,       False),
    (BE_ACTIVATE,        True),
    (REQUIRE_BACKUP_BE,  False),
    (REQUIRE_NEW_BE,     False),
]

opts_table_concurrency = [
    opts_table_cb_concurrency,
    (CONCURRENCY,        None),
]

opts_table_force = [
    (FORCE,                False),
]

opts_table_li_ignore = [
    opts_table_cb_li_ignore,
    (LI_IGNORE_ALL,        False),
    (LI_IGNORE_LIST,       []),
]

opts_table_li_md_only = [
    opts_table_cb_md_only,
    (LI_MD_ONLY,         False),
]

opts_table_li_no_pkg_updates = [
    (LI_PKG_UPDATES,       True),
]

opts_table_li_no_psync = [
    opts_table_cb_li_no_psync,
    (LI_PARENT_SYNC,       True),
]

opts_table_li_props = [
    opts_table_cb_li_props,
    (LI_PROPS,             []),
]

opts_table_li_target = [
    opts_table_cb_li_target,
    (LI_TARGET_ALL,        False),
    (LI_TARGET_LIST,       []),
]

opts_table_li_target1 = [
    opts_table_cb_li_target1,
    (LI_NAME,              None),
]

opts_table_licenses = [
    (ACCEPT,               False),
    (SHOW_LICENSES,        False),
]

opts_table_no_headers = [
    opts_table_cb_no_headers_vs_quiet,
    (OMIT_HEADERS,         False),
]

opts_table_no_index = [
    (UPDATE_INDEX,         True),
]

opts_table_no_refresh = [
    (REFRESH_CATALOGS,     True),
]

opts_table_reject = [
    (REJECT_PATS,          []),
]

opts_table_verbose = [
    opts_table_cb_v,
    (VERBOSE,              0),
]

opts_table_quiet = [
    opts_table_cb_q,
    (QUIET,                False),
]

opts_table_parsable = [
    opts_table_cb_parsable,
    (PARSABLE_VERSION,     None),
]

opts_table_nqv = \
    opts_table_quiet + \
    opts_table_verbose + \
    [
    opts_table_cb_nqv,
    (NOEXECUTE,            False),
]

opts_table_origins = [
    opts_table_cb_origins,
    (ORIGINS,              []),
]

opts_table_stage = [
    opts_table_cb_stage,
    (STAGE,                None),
]

opts_table_actuators = [
    opts_table_cb_actuators,
    (SYNC_ACT,             False),
    (ACT_TIMEOUT,          None)
]

#
# Options for pkg(1) subcommands.  Built by combining the option tables above,
# with some optional subcommand unique options defined below.
#
opts_main = \
    opts_table_beopts + \
    opts_table_concurrency + \
    opts_table_li_ignore + \
    opts_table_li_no_psync + \
    opts_table_licenses + \
    opts_table_reject + \
    opts_table_no_index + \
    opts_table_no_refresh + \
    opts_table_nqv + \
    opts_table_parsable + \
    opts_table_origins + \
    []

opts_install = \
    opts_main + \
    opts_table_actuators + \
    []

# "update" cmd inherits all main cmd options
# TODO fix back to opts_install
opts_update = \
    opts_main + \
    opts_table_force + \
    opts_table_stage + \
    opts_table_actuators + \
    []

# "attach-linked" cmd inherits all main cmd options
opts_attach_linked = \
    opts_main + \
    opts_table_force + \
    opts_table_li_md_only + \
    opts_table_li_no_pkg_updates + \
    opts_table_li_props + \
    [
    opts_cb_li_attach,
    (ALLOW_RELINK,         False),
    (ATTACH_CHILD,         False),
    (ATTACH_PARENT,        False),
]

opts_revert = \
    opts_table_beopts + \
    opts_table_nqv + \
    opts_table_parsable + \
    [
    (TAGGED,               False),
]

opts_set_mediator = \
    opts_table_beopts + \
    opts_table_no_index + \
    opts_table_nqv + \
    opts_table_parsable + \
    [
    (MED_IMPLEMENTATION,   None),
    (MED_VERSION,          None)
]

# "set-property-linked" cmd inherits all main cmd options
opts_set_property_linked = \
    opts_main + \
    opts_table_li_md_only + \
    opts_table_li_no_pkg_updates + \
    opts_table_li_target1 + \
    []

# "sync-linked" cmd inherits all main cmd options
opts_sync_linked = \
    opts_main + \
    opts_table_li_md_only + \
    opts_table_li_no_pkg_updates + \
    opts_table_li_target + \
    opts_table_stage + \
    []

opts_uninstall = \
    opts_table_beopts + \
    opts_table_concurrency + \
    opts_table_li_ignore + \
    opts_table_li_no_psync + \
    opts_table_no_index + \
    opts_table_nqv + \
    opts_table_parsable + \
    opts_table_stage + \
    opts_table_actuators

opts_audit_linked = \
    opts_table_li_no_psync + \
    opts_table_li_target + \
    opts_table_no_headers + \
    opts_table_quiet + \
    []

opts_detach_linked = \
    opts_table_force + \
    opts_table_li_md_only + \
    opts_table_li_no_pkg_updates + \
    opts_table_li_target + \
    opts_table_nqv + \
    []

opts_list_linked = \
    opts_table_li_ignore + \
    opts_table_no_headers + \
    []

opts_list_property_linked = \
    opts_table_li_target1 + \
    opts_table_no_headers + \
    []

opts_list_inventory = \
    opts_table_li_no_psync + \
    opts_table_no_refresh + \
    opts_table_no_headers + \
    opts_table_origins + \
    opts_table_quiet + \
    opts_table_verbose + \
    [
    opts_cb_list,
    (LIST_INSTALLED_NEWEST, False),
    (LIST_ALL,              False),
    (LIST_NEWEST,           False),
    (SUMMARY,               False),
    (LIST_UPGRADABLE,       False),
]

pkg_op_opts = {

    pkgdefs.PKG_OP_ATTACH         : opts_attach_linked,
    pkgdefs.PKG_OP_AUDIT_LINKED   : opts_audit_linked,
    pkgdefs.PKG_OP_CHANGE_FACET   : opts_install,
    pkgdefs.PKG_OP_CHANGE_VARIANT : opts_install,
    pkgdefs.PKG_OP_DETACH         : opts_detach_linked,
    pkgdefs.PKG_OP_INSTALL        : opts_install,
    pkgdefs.PKG_OP_LIST           : opts_list_inventory,
    pkgdefs.PKG_OP_LIST_LINKED    : opts_list_linked,
    pkgdefs.PKG_OP_PROP_LINKED    : opts_list_property_linked,
    pkgdefs.PKG_OP_PUBCHECK       : [],
    pkgdefs.PKG_OP_REVERT         : opts_revert,
    pkgdefs.PKG_OP_SET_MEDIATOR   : opts_set_mediator,
    pkgdefs.PKG_OP_SET_PROP_LINKED: opts_set_property_linked,
    pkgdefs.PKG_OP_SYNC           : opts_sync_linked,
    pkgdefs.PKG_OP_UNINSTALL      : opts_uninstall,
    pkgdefs.PKG_OP_UPDATE         : opts_update
}

def get_pkg_opts(op, add_table=None):
        """Get the available options for a particular operation specified by
        'op'. If the client uses custom pkg_op_opts tables they can be specified
        by 'add_table'."""

        popts = pkg_op_opts.copy()
        if add_table is not None:
                popts.update(add_table)

        try:
                opts = popts[op]
        except KeyError:
                opts = None
        return opts

def get_pkg_opts_defaults(op, opt, add_table=None):
        """ Get the default value for a certain option 'opt' of a certain
        operation 'op'. This is useful for clients which toggle boolean options.
        """
        popts = get_pkg_opts(op, add_table)

        for o in popts:
                if type(o) != tuple:
                        continue
                opt_name, default = o
                if opt_name == opt:
                        return default

def opts_assemble(op, api_inst, opts, add_table=None, cwd=None):
        """Assembly of the options for a specific operation. Options are read in
        from a dict (see explanation below) and sanity tested.

        This is the common interface to supply options to the functions of the
        API.

        'op' is the operation for which the options need to be assembled and
        verified. The currently supported operations are listed in
        pkgdefs.pkg_op_values.

        'api_inst' is a reference to the API instance, required for some of the
        verification steps.

        'opts' is the raw options table to be processed. It needs to be a dict
        in the format: { option_name: argument, ... }
        """

        global _orig_cwd

        if cwd is not None:
                _orig_cwd = cwd
        else:
                _orig_cwd = None

        popts = get_pkg_opts(op, add_table)

        rv = {}
        callbacks = []

        for o in popts:
                if type(o) != tuple:
                        callbacks.append(o)
                        continue

                avail_opt, default = o
                # for options not given we substitue the default value
                if avail_opt not in opts:
                        rv[avail_opt] = default
                        continue

                if type(default) == int:
                        assert type(opts[avail_opt]) == int, opts[avail_opt]
                elif type(default) == list:
                        assert type(opts[avail_opt]) == list, opts[avail_opt]
                elif type(default) == bool:
                        assert type(opts[avail_opt]) == bool, opts[avail_opt]

                rv[avail_opt] = opts[avail_opt]

        rv_updated = rv.copy()

        # run the option verification callbacks
        for cb in callbacks:
                cb(api_inst, rv, rv_updated)

        return rv_updated

