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

# Copyright (c) 2013, 2016, Oracle and/or its affiliates. All rights reserved.

import os

import pkg.client.pkgdefs as pkgdefs
import pkg.client.linkedimage as li
import pkg.misc as misc

from pkg.client.api_errors import InvalidOptionError, LinkedImageException
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
IGNORE_MISSING        = "ignore_missing"
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
# options for explicit recursion; see description in client.py
LI_ERECURSE_ALL       = "li_erecurse_all"
LI_ERECURSE_INCL      = "li_erecurse_list"
LI_ERECURSE_EXCL      = "li_erecurse_excl"
LI_ERECURSE           = "li_erecurse"
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
UNPACKAGED            = "unpackaged"
UNPACKAGED_ONLY       = "unpackaged_only"
VERBOSE               = "verbose"
SYNC_ACT              = "sync_act"
ACT_TIMEOUT           = "act_timeout"
PUBLISHERS            = "publishers"
SSL_KEY               = "ssl_key"
SSL_CERT              = "ssl_cert"
APPROVED_CA_CERTS     = "approved_ca_certs"
REVOKED_CA_CERTS      = "revoked_ca_certs"
UNSET_CA_CERTS        = "unset_ca_certs"
ORIGIN_URI            = "origin_uri"
RESET_UUID            = "reset_uuid"
ADD_MIRRORS           = "add_mirrors"
REMOVE_MIRRORS        = "remove_mirrors"
ADD_ORIGINS           = "add_origins"
REMOVE_ORIGINS        = "remove_origins"
ENABLE_ORIGINS        = "enable_origins"
DISABLE_ORIGINS       = "disable_origins"
REFRESH_ALLOWED       = "refresh_allowed"
PUB_ENABLE            = "enable"
PUB_DISABLE           = "disable"
PUB_STICKY            = "sticky"
PUB_NON_STICKY        = "non_sticky"
REPO_URI              = "repo_uri"
PROXY_URI             = "proxy_uri"
SEARCH_BEFORE         = "search_before"
SEARCH_AFTER          = "search_after"
SEARCH_FIRST          = "search_first"
SET_PROPS             = "set_props"
ADD_PROP_VALUES       = "add_prop_values"
REMOVE_PROP_VALUES    = "remove_prop_values"
UNSET_PROPS           = "unset_props"
PREFERRED_ONLY        = "preferred_only"
INC_DISABLED          = "inc_disabled"
OUTPUT_FORMAT         = "output_format"
DISPLAY_LICENSE       = "display_license"
INFO_LOCAL            = "info_local"
INFO_REMOTE           = "info_remote"

def opts_table_cb_info(api_inst, opts, opts_new):
        opts_new[ORIGINS] = set()
        for e in opts[ORIGINS]:
                opts_new[ORIGINS].add(misc.parse_uri(e,
                    cwd=_orig_cwd))
        if opts[ORIGINS]:
                opts_new[INFO_REMOTE] = True
        if opts[QUIET]:
                global_settings.client_output_quiet = True
        if not opts_new[INFO_LOCAL] and not opts_new[INFO_REMOTE]:
                opts_new[INFO_LOCAL] = True
        elif opts_new[INFO_LOCAL] and opts_new[INFO_REMOTE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [INFO_LOCAL, INFO_REMOTE])

def __parse_set_props(args):
        """"Parse set property options that were specified on the command
        line into a dictionary.  Make sure duplicate properties were not
        specified."""

        set_props = dict()
        for pv in args:
                try:
                        p, v = pv.split("=", 1)
                except ValueError:
                        raise InvalidOptionError(msg=_("properties to be set "
                            "must be of the form '<name>=<value>'. This is "
                            "what was given: {0}").format(pv))

                if p in set_props:
                        raise InvalidOptionError(msg=_("a property may only "
                            "be set once in a command. {0} was set twice"
                            ).format(p))
                set_props[p] = v

        return set_props

def __parse_prop_values(args, add=True):
        """"Parse add or remove property values options that were specified
        on the command line into a dictionary.  Make sure duplicate properties
        were not specified."""

        props_values = dict()
        if add:
                add_txt = "added"
        else:
                add_txt = "removed"

        for pv in args:
                try:
                        p, v = pv.split("=", 1)
                except ValueError:
                        raise InvalidOptionError(msg=_("property values to be "
                            "{add} must be of the form '<name>=<value>'. "
                            "This is what was given: {key}").format(
                            add=add_txt, key=pv))

                props_values.setdefault(p, [])
                props_values[p].append(v)

        return props_values

def opts_table_cb_pub_list(api_inst, opts, opts_new):
        if opts[OUTPUT_FORMAT] == None:
                opts_new[OUTPUT_FORMAT] = "default"

def opts_table_cb_pub_props(api_inst, opts, opts_new):
        opts_new[SET_PROPS] = __parse_set_props(opts[SET_PROPS])
        opts_new[ADD_PROP_VALUES] = __parse_prop_values(opts[ADD_PROP_VALUES])
        opts_new[REMOVE_PROP_VALUES] = __parse_prop_values(
            opts[REMOVE_PROP_VALUES], add=False)
        opts_new[UNSET_PROPS] = set(opts[UNSET_PROPS])

def opts_table_cb_pub_search(api_inst, opts, opts_new):
        if opts[SEARCH_BEFORE] and opts[SEARCH_AFTER]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [SEARCH_BEFORE, SEARCH_AFTER])

        if opts[SEARCH_BEFORE] and opts[SEARCH_FIRST]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [SEARCH_BEFORE, SEARCH_FIRST])

        if opts[SEARCH_AFTER] and opts[SEARCH_FIRST]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [SEARCH_AFTER, SEARCH_FIRST])

def opts_table_cb_pub_opts(api_inst, opts, opts_new):
        del opts_new[PUB_DISABLE]
        del opts_new[PUB_ENABLE]
        del opts_new[PUB_STICKY]
        del opts_new[PUB_NON_STICKY]

        if opts[PUB_DISABLE] and opts[PUB_ENABLE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [PUB_DISABLE, PUB_ENABLE])

        if opts[PUB_STICKY] and opts[PUB_NON_STICKY]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [PUB_STICKY, PUB_NON_STICKY])

        opts_new[PUB_DISABLE] = None
        if opts[PUB_DISABLE]:
                opts_new[PUB_DISABLE] = True

        if opts[PUB_ENABLE]:
                opts_new[PUB_DISABLE] = False

        opts_new[PUB_STICKY] = None
        if opts[PUB_STICKY]:
                opts_new[PUB_STICKY] = True

        if opts[PUB_NON_STICKY]:
                opts_new[PUB_STICKY] = False

        if opts[ORIGIN_URI] and opts[ADD_ORIGINS]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [ORIGIN_URI, ADD_ORIGINS])

        if opts[ORIGIN_URI] and opts[REMOVE_ORIGINS]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [ORIGIN_URI, REMOVE_ORIGINS])

        if opts[REPO_URI] and opts[ADD_ORIGINS]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [REPO_URI, ADD_ORIGINS])
        if opts[REPO_URI] and opts[ADD_MIRRORS]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [REPO_URI, ADD_MIRRORS])
        if opts[REPO_URI] and opts[REMOVE_ORIGINS]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [REPO_URI, REMOVE_ORIGINS])
        if opts[REPO_URI] and opts[REMOVE_MIRRORS]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [REPO_URI, REMOVE_MIRRORS])
        if opts[REPO_URI] and opts[PUB_DISABLE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [REPO_URI, PUB_DISABLE])
        if opts[REPO_URI] and opts[PUB_ENABLE]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [REPO_URI, PUB_ENABLE])
        if opts[REPO_URI] and not opts[REFRESH_ALLOWED]:
                raise InvalidOptionError(InvalidOptionError.REQUIRED,
                    [REPO_URI, REFRESH_ALLOWED])
        if opts[REPO_URI] and opts[RESET_UUID]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [REPO_URI, RESET_UUID])

        if opts[PROXY_URI] and not (opts[ADD_ORIGINS] or opts[ADD_MIRRORS]
            or opts[REPO_URI] or opts[REMOVE_ORIGINS] or opts[REMOVE_MIRRORS]):
                raise InvalidOptionError(InvalidOptionError.REQUIRED_ANY,
                    [PROXY_URI, ADD_ORIGINS, ADD_MIRRORS, REMOVE_ORIGINS,
                    REMOVE_MIRRORS, REPO_URI])

        opts_new[ADD_ORIGINS] = set()
        opts_new[REMOVE_ORIGINS] = set()
        opts_new[ADD_MIRRORS] = set()
        opts_new[REMOVE_MIRRORS] = set()
        opts_new[ENABLE_ORIGINS] = set()
        opts_new[DISABLE_ORIGINS] = set()
        for e in opts[ADD_ORIGINS]:
                if e == "*":
                        if not (opts[PUB_DISABLE] or opts[PUB_ENABLE]):
                                raise InvalidOptionError(InvalidOptionError.XOR,
                                    [PUB_ENABLE, PUB_DISABLE])
                        # Allow wildcard to support an easy, scriptable
                        # way of enabling all existing entries.
                        if opts[PUB_DISABLE]:
                                opts_new[DISABLE_ORIGINS].add("*")
                        if opts[PUB_ENABLE]:
                                opts_new[ENABLE_ORIGINS].add("*")
                else:
                        opts_new[ADD_ORIGINS].add(misc.parse_uri(e,
                            cwd=_orig_cwd))

        # If enable/disable is specified and "*" is not present, then assign
        # origins collected to be added into disable/enable set as well.
        if opts[PUB_DISABLE]:
                if "*" not in opts_new[DISABLE_ORIGINS]:
                        opts_new[DISABLE_ORIGINS] = opts_new[ADD_ORIGINS]

        if opts[PUB_ENABLE]:
                if "*" not in opts_new[ENABLE_ORIGINS]:
                        opts_new[ENABLE_ORIGINS] = opts_new[ADD_ORIGINS]

        for e in opts[REMOVE_ORIGINS]:
                if e == "*":
                        # Allow wildcard to support an easy, scriptable
                        # way of removing all existing entries.
                        opts_new[REMOVE_ORIGINS].add("*")
                else:
                        opts_new[REMOVE_ORIGINS].add(misc.parse_uri(e,
                            cwd=_orig_cwd))

        for e in opts[ADD_MIRRORS]:
                opts_new[ADD_MIRRORS].add(misc.parse_uri(e, cwd=_orig_cwd))
        for e in opts[REMOVE_MIRRORS]:
                if e == "*":
                        # Allow wildcard to support an easy, scriptable
                        # way of removing all existing entries.
                        opts_new[REMOVE_MIRRORS].add("*")
                else:
                        opts_new[REMOVE_MIRRORS].add(misc.parse_uri(e,
                            cwd=_orig_cwd))

        if opts[REPO_URI]:
                opts_new[REPO_URI] = misc.parse_uri(opts[REPO_URI],
                    cwd=_orig_cwd)

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

def opts_table_cb_unpackaged(api_inst, opts, opts_new):
        # Check whether unpackaged and unpackaged_only options are used
        # together.

        if opts[UNPACKAGED] and opts[UNPACKAGED_ONLY]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [UNPACKAGED, UNPACKAGED_ONLY])

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
                        "image property: '{0}'.").format(p))

                if p in linked_props:
                        raise InvalidOptionError(msg=_("linked image "
                            "property specified multiple times: "
                            "'{0}'.").format(p))

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

def opts_table_cb_li_recurse(api_inst, opts, opts_new):

        del opts_new[LI_ERECURSE_INCL]
        del opts_new[LI_ERECURSE_EXCL]
        del opts_new[LI_ERECURSE_ALL]

        if opts[LI_ERECURSE_EXCL] and not opts[LI_ERECURSE_ALL]:
                raise InvalidOptionError(InvalidOptionError.REQUIRED,
                    [LI_ERECURSE_EXCL, LI_ERECURSE_ALL])

        if opts[LI_ERECURSE_INCL] and not opts[LI_ERECURSE_ALL]:
                raise InvalidOptionError(InvalidOptionError.REQUIRED,
                    [LI_ERECURSE_INCL, LI_ERECURSE_ALL])

        if opts[LI_ERECURSE_INCL] and opts[LI_ERECURSE_EXCL]:
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [LI_ERECURSE_INCL, LI_ERECURSE_EXCL])

        if not opts[LI_ERECURSE_ALL]:
                opts_new[LI_ERECURSE] = None
                return

        # Go through all children and check if they are in the recurse list.
        li_child_targets = []
        li_child_list = set([
                lin
                for lin, rel, path in api_inst.list_linked()
                if rel == "child"
        ])

        def parse_lin(ulin):
                lin = None
                try:
                        lin = api_inst.parse_linked_name(ulin,
                            allow_unknown=True)
                except LinkedImageException as e:
                        try:
                                lin = api_inst.parse_linked_name(
                                    "zone:{0}".format(ulin), allow_unknown=True)
                        except LinkedImageException as e:
                                pass
                if lin is None or lin not in li_child_list:
                        raise InvalidOptionError(msg=
                            _("invalid linked image or zone name "
                            "'{0}'.").format(ulin))

                return lin

        if opts[LI_ERECURSE_INCL]:
                # include list specified
                for ulin in opts[LI_ERECURSE_INCL]:
                        li_child_targets.append(parse_lin(ulin))
                opts_new[LI_ERECURSE] = li_child_targets
        else:
                # exclude list specified
                for ulin in opts[LI_ERECURSE_EXCL]:
                        li_child_list.remove(parse_lin(ulin))
                opts_new[LI_ERECURSE] = li_child_list

        # If we use image recursion we need to make sure uninstall and update
        # ignore non-existing packages in the parent image.
        if opts_new[LI_ERECURSE] and IGNORE_MISSING in opts:
                opts_new[IGNORE_MISSING] = True

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

def opts_table_cb_publishers(api_inst, opts, opts_new):
        publishers = set()
        for p in opts[PUBLISHERS]:
                publishers.add(p)
        opts_new[PUBLISHERS] = publishers

def opts_table_cb_parsable(api_inst, opts, opts_new):
        if opts[PARSABLE_VERSION] is not None and opts.get(VERBOSE, False):
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [VERBOSE, PARSABLE_VERSION])
        if opts[PARSABLE_VERSION] is not None and opts.get(OMIT_HEADERS,
            False):
                raise InvalidOptionError(InvalidOptionError.INCOMPAT,
                    [OMIT_HEADERS, PARSABLE_VERSION])
        if opts[PARSABLE_VERSION] is not None:
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
                    "'{0}'").format(opts[STAGE]))

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
                err = _("value '{0}' invalid").format(v)
                raise InvalidOptionError(msg=err, options=[k])

        # check the minimum bounds
        if minimum is not None and v < minimum:
                err = _("value must be >= {0:d}").format(minimum)
                raise InvalidOptionError(msg=err, options=[k])

        # update the new options array to make the value an integer
        opts_new[k] = v

def opts_cb_fd(k, api_inst, opts, opts_new):
        opts_cb_int(k, api_inst, opts, opts_new, minimum=0)

        err = _("value '{0}' invalid").format(opts_new[k])
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
#       (k, v, [val], {})
#   where the values are:
#       k: the key value for the options dictionary
#       v: the default value. valid values are: True/False, None, [], 0
#       val: the valid argument list. It should be a list,
#       and it is optional.
#       {}: json schema.
#

opts_table_info = [
    opts_table_cb_info,
    (DISPLAY_LICENSE,    False, [], {"type": "boolean"}),
    (INFO_LOCAL,         False, [], {"type": "boolean"}),
    (INFO_REMOTE,        False, [], {"type": "boolean"}),
    (ORIGINS,            [],    [], {"type": "array",
                                     "items": {"type": "string"}
                                    }),
    (QUIET,              False, [], {"type": "boolean"})
]

opts_table_pub_list = [
    opts_table_cb_pub_list,
    (PREFERRED_ONLY,  False, [],                 {"type": "boolean"}),
    (INC_DISABLED,    True,  [],                 {"type": "boolean"}),
    (OUTPUT_FORMAT,   None,  ["default", "tsv"], {"type": ["null", "string"]}),
    (OMIT_HEADERS,    False, [],                 {"type": "boolean"})
]

opts_table_pub_props = [
    opts_table_cb_pub_props,
    (SET_PROPS,           [], [], {"type": "array", "items": {"type": "string"}
                                  }),
    (ADD_PROP_VALUES,     [], [], {"type": "array",
                                   "items": {"type": "string"}
                                  }),
    (REMOVE_PROP_VALUES,  [], [], {"type": "array",
                                   "items": {"type": "string"}
                                  }),
    (UNSET_PROPS,         [], [], {"type": "array", "items": {"type": "string"}
                                  })
]

opts_table_ssl = [
    (SSL_KEY,            None, [],  {"type": ["null", "string"]}),
    (SSL_CERT,           None, [],  {"type": ["null", "string"]}),
    (APPROVED_CA_CERTS,  [],   [],  {"type": "array",
                                     "items": {"type": "string"}
                                    }),
    (REVOKED_CA_CERTS,   [],   [],  {"type": "array",
                                     "items": {"type": "string"}
                                    }),
    (UNSET_CA_CERTS,     [],   [],  {"type": "array",
                                     "items": {"type": "string"}
                                    }),
]

opts_table_pub_search = [
    opts_table_cb_pub_search,
    (SEARCH_BEFORE,   None,  [], {"type": ["null", "string"]}),
    (SEARCH_AFTER,    None,  [], {"type": ["null", "string"]}),
    (SEARCH_FIRST,    False, [], {"type": "boolean"}),
]

opts_table_pub_opts = [
    opts_table_cb_pub_opts,
    (ORIGIN_URI,      None,  [], {"type": ["null", "string"]}),
    (RESET_UUID,      False, [], {"type": "boolean"}),
    (ADD_MIRRORS,     [],    [], {"type": "array",
                                  "items": {"type": "string"}
                                 }),
    (REMOVE_MIRRORS,  [],    [], {"type": "array",
                                  "items": {"type": "string"}
                                 }),
    (ADD_ORIGINS,     [],    [], {"type": "array",
                                  "items": {"type": "string"}
                                 }),
    (REMOVE_ORIGINS,  [],    [], {"type": "array",
                                  "items": {"type": "string"}
                                 }),
    (ENABLE_ORIGINS,  [],    [], {"type": "array",
                                  "items": {"type": "string"}
                                 }),
    (DISABLE_ORIGINS, [],    [], {"type": "array",
                                  "items": {"type": "string"}
                                 }),
    (REFRESH_ALLOWED, True,  [], {"type": "boolean"}),
    (PUB_ENABLE,      False, [], {"type": "boolean"}),
    (PUB_DISABLE,     False, [], {"type": "boolean"}),
    (PUB_STICKY,      False, [], {"type": "boolean"}),
    (PUB_NON_STICKY,  False, [], {"type": "boolean"}),
    (REPO_URI,        None,  [], {"type": ["null", "string"]}),
    (PROXY_URI,       None,  [], {"type": ["null", "string"]}),
]

opts_table_beopts = [
    opts_table_cb_beopts,
    (BACKUP_BE_NAME,     None,  [], {"type": ["null", "string"]}),
    (BE_NAME,            None,  [], {"type": ["null", "string"]}),
    (DENY_NEW_BE,        False, [], {"type": "boolean"}),
    (NO_BACKUP_BE,       False, [], {"type": "boolean"}),
    (BE_ACTIVATE,        True,  [], {"type": "boolean"}),
    (REQUIRE_BACKUP_BE,  False, [], {"type": "boolean"}),
    (REQUIRE_NEW_BE,     False, [], {"type": "boolean"}),
]

opts_table_concurrency = [
    opts_table_cb_concurrency,
    (CONCURRENCY,        None, [], {"type": ["null", "integer"],
        "minimum": 0}),
]

opts_table_force = [
    (FORCE,                False, [], {"type": "boolean"}),
]

opts_table_li_ignore = [
    opts_table_cb_li_ignore,
    (LI_IGNORE_ALL,        False, [], {"type": "boolean"}),
    (LI_IGNORE_LIST,       [],    [], {"type": "array",
                                       "items": {"type": "string"}
                                      }),
]

opts_table_li_md_only = [
    opts_table_cb_md_only,
    (LI_MD_ONLY,         False, [], {"type": "boolean"}),
]

opts_table_li_no_pkg_updates = [
    (LI_PKG_UPDATES,       True, [], {"type": "boolean"}),
]

opts_table_li_no_psync = [
    opts_table_cb_li_no_psync,
    (LI_PARENT_SYNC,       True, [], {"type": "boolean"}),
]

opts_table_li_props = [
    opts_table_cb_li_props,
    (LI_PROPS,             [], [], {"type": "array",
                                    "items": {"type": "string"}
                                   }),
]

opts_table_li_target = [
    opts_table_cb_li_target,
    (LI_TARGET_ALL,        False, [], {"type": "boolean"}),
    (LI_TARGET_LIST,       [],    [], {"type": "array",
                                       "items": {"type": "string"}
                                      }),
]

opts_table_li_target1 = [
    opts_table_cb_li_target1,
    (LI_NAME,              None, [], {"type": ["null", "string"]}),
]

opts_table_li_recurse = [
    opts_table_cb_li_recurse,
    (LI_ERECURSE_ALL,       False, [], {"type": "boolean"}),
    (LI_ERECURSE_INCL,      [], [], {"type": "array",
                                     "items": {"type": "string"}
                                    }),
    (LI_ERECURSE_EXCL,      [], [], {"type": "array",
        "items": {"type": "string"}}),
]

opts_table_licenses = [
    (ACCEPT,               False, [], {"type": "boolean"}),
    (SHOW_LICENSES,        False, [], {"type": "boolean"}),
]

opts_table_no_headers = [
    opts_table_cb_no_headers_vs_quiet,
    (OMIT_HEADERS,         False, [], {"type": "boolean"}),
]

opts_table_no_index = [
    (UPDATE_INDEX,         True, [], {"type": "boolean"}),
]

opts_table_no_refresh = [
    (REFRESH_CATALOGS,     True, [], {"type": "boolean"}),
]

opts_table_reject = [
    (REJECT_PATS,          [], [], {"type": "array",
                                    "items": {"type": "string"}
                                   }),
]

opts_table_verbose = [
    opts_table_cb_v,
    (VERBOSE,              0, [], {"type": "integer", "minimum": 0}),
]

opts_table_quiet = [
    opts_table_cb_q,
    (QUIET,                False, [], {"type": "boolean"}),
]

opts_table_parsable = [
    opts_table_cb_parsable,
    (PARSABLE_VERSION,     None,  [None, 0], {"type": ["null", "integer"],
                                       "minimum": 0, "maximum": 0
                                      }),
]

opts_table_nqv = \
    opts_table_quiet + \
    opts_table_verbose + \
    [
    opts_table_cb_nqv,
    (NOEXECUTE,            False, [], {"type": "boolean"}),
]

opts_table_origins = [
    opts_table_cb_origins,
    (ORIGINS,              [], [], {"type": "array",
                                    "items": {"type": "string"}
                                   }),
]

opts_table_stage = [
    opts_table_cb_stage,
    (STAGE,                None, [], {"type": ["null", "string"]}),
]

opts_table_missing = [
    (IGNORE_MISSING,       False, [], {"type": "boolean"}),
]

opts_table_actuators = [
    opts_table_cb_actuators,
    (SYNC_ACT,             False, [], {"type": "boolean"}),
    (ACT_TIMEOUT,          None,  [], {"type": ["null", "integer"],
        "minimum": 0})
]

opts_table_publishers = [
    opts_table_cb_publishers,
    (PUBLISHERS, [], [], {"type": "array",
                          "items": {"type": "string"}
                         }),
]

opts_table_unpackaged = [
    (UNPACKAGED,       False, [], {"type": "boolean"}),
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
    opts_table_stage + \
    opts_table_li_recurse + \
    opts_table_actuators + \
    []

opts_set_publisher = \
    opts_table_ssl + \
    opts_table_pub_opts + \
    opts_table_pub_props + \
    opts_table_pub_search + \
    []

opts_info = \
    opts_table_info + \
    []

# "update" cmd inherits all main cmd options
opts_update = \
    opts_main + \
    opts_table_force + \
    opts_table_li_recurse + \
    opts_table_stage + \
    opts_table_actuators + \
    opts_table_missing + \
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
    opts_table_li_recurse + \
    opts_table_missing + \
    opts_table_actuators + \
    []

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
    (LIST_INSTALLED_NEWEST, False, [], {"type": "boolean"}),
    (LIST_ALL,              False, [], {"type": "boolean"}),
    (LIST_NEWEST,           False, [], {"type": "boolean"}),
    (SUMMARY,               False, [], {"type": "boolean"}),
    (LIST_UPGRADABLE,       False, [], {"type": "boolean"}),
]

opts_dehydrate = \
    opts_table_nqv + \
    opts_table_publishers + \
    []

opts_fix = \
    opts_table_beopts + \
    opts_table_nqv + \
    opts_table_licenses + \
    opts_table_no_headers + \
    opts_table_parsable + \
    opts_table_unpackaged + \
    []

opts_verify = \
    opts_table_quiet + \
    opts_table_verbose + \
    opts_table_no_headers + \
    opts_table_parsable + \
    opts_table_unpackaged + \
    [
    opts_table_cb_nqv,
    opts_table_cb_unpackaged,
    (UNPACKAGED_ONLY,  False, [], {"type": "boolean"}),
]

opts_publisher = \
    opts_table_pub_list + \
    []

pkg_op_opts = {

    pkgdefs.PKG_OP_ATTACH         : opts_attach_linked,
    pkgdefs.PKG_OP_AUDIT_LINKED   : opts_audit_linked,
    pkgdefs.PKG_OP_CHANGE_FACET   : opts_install,
    pkgdefs.PKG_OP_CHANGE_VARIANT : opts_install,
    pkgdefs.PKG_OP_DEHYDRATE      : opts_dehydrate,
    pkgdefs.PKG_OP_DETACH         : opts_detach_linked,
    pkgdefs.PKG_OP_EXACT_INSTALL  : opts_main,
    pkgdefs.PKG_OP_FIX            : opts_fix,
    pkgdefs.PKG_OP_INFO           : opts_info,
    pkgdefs.PKG_OP_INSTALL        : opts_install,
    pkgdefs.PKG_OP_LIST           : opts_list_inventory,
    pkgdefs.PKG_OP_LIST_LINKED    : opts_list_linked,
    pkgdefs.PKG_OP_PROP_LINKED    : opts_list_property_linked,
    pkgdefs.PKG_OP_PUBCHECK       : [],
    pkgdefs.PKG_OP_PUBLISHER_LIST : opts_publisher,
    pkgdefs.PKG_OP_REHYDRATE      : opts_dehydrate,
    pkgdefs.PKG_OP_REVERT         : opts_revert,
    pkgdefs.PKG_OP_SET_MEDIATOR   : opts_set_mediator,
    pkgdefs.PKG_OP_SET_PUBLISHER  : opts_set_publisher,
    pkgdefs.PKG_OP_SET_PROP_LINKED: opts_set_property_linked,
    pkgdefs.PKG_OP_SYNC           : opts_sync_linked,
    pkgdefs.PKG_OP_UNINSTALL      : opts_uninstall,
    pkgdefs.PKG_OP_UNSET_PUBLISHER: [],
    pkgdefs.PKG_OP_UPDATE         : opts_update,
    pkgdefs.PKG_OP_VERIFY         : opts_verify
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
                if len(o) == 2:
                        opt_name, default = o
                elif len(o) == 3:
                        opt_name, default, dummy_valid_args = o
                elif len(o) == 4:
                        opt_name, default, dummy_valid_args, dummy_schema = o
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
                valid_args = []
                # If no valid argument list specified.
                if len(o) == 2:
                        avail_opt, default = o
                elif len(o) == 3:
                        avail_opt, default, valid_args = o
                elif len(o) == 4:
                        avail_opt, default, valid_args, schema = o
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

                if valid_args:
                        assert type(default) == list or default is None, \
                            default
                        raise_error = False
                        if type(opts[avail_opt]) == list:
                                if not set(opts[avail_opt]).issubset(
                                    set(valid_args)):
                                        raise_error = True
                        else:
                                # If the any of valid_args is integer, we first
                                # try to convert the argument value into
                                # integer. This is for CLI mode where arguments
                                # are strings.
                                if any(type(va) == int for va in valid_args):
                                        try:
                                                opts[avail_opt] = int(
                                                    opts[avail_opt])
                                        except Exception:
                                                pass
                                if opts[avail_opt] not in valid_args:
                                        raise_error = True
                        if raise_error:
                                raise InvalidOptionError(
                                    InvalidOptionError.ARG_INVALID,
                                    [opts[avail_opt], avail_opt],
                                    valid_args=valid_args)

                rv[avail_opt] = opts[avail_opt]

        rv_updated = rv.copy()

        # run the option verification callbacks
        for cb in callbacks:
                cb(api_inst, rv, rv_updated)

        return rv_updated

