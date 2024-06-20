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
# Copyright (c) 2015, 2024, Oracle and/or its affiliates.
#


import calendar
import datetime
import errno
import getopt
import itertools
import rapidjson as json
import os
import re
import socket
import sys
import tempfile
import textwrap
import time
import traceback
import jsonschema

import pkg
import pkg.actions as actions
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.bootenv as bootenv
import pkg.client.progress as progress
import pkg.client.linkedimage as li
import pkg.client.publisher as publisher
import pkg.client.options as options
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.pipeutils as pipeutils
import pkg.portable as portable
import pkg.version as version

from pkg.client import global_settings
from pkg.client.api import (IMG_TYPE_ENTIRE, IMG_TYPE_PARTIAL,
    IMG_TYPE_USER, RESULT_CANCELED, RESULT_FAILED_BAD_REQUEST,
    RESULT_FAILED_CONFIGURATION, RESULT_FAILED_CONSTRAINED,
    RESULT_FAILED_LOCKED, RESULT_FAILED_STORAGE, RESULT_NOTHING_TO_DO,
    RESULT_SUCCEEDED, RESULT_FAILED_TRANSPORT, RESULT_FAILED_UNKNOWN,
    RESULT_FAILED_OUTOFMEMORY)
from pkg.client.debugvalues import DebugValues
from pkg.client.pkgdefs import *
from pkg.misc import EmptyI, msg, emsg, PipeError

CLIENT_API_VERSION = 83
PKG_CLIENT_NAME = "pkg"
pkg_timer = pkg.misc.Timer("pkg client")
SYSREPO_HIDDEN_URI = "<system-repository>"
PROG_DELAY = 5.0


def _strify(input):
    """Convert unicode string into byte string in Python 2 and convert
    bytes string into unicode string in Python 3. This will be used by json
    loads function."""

    if isinstance(input, dict):
        return dict([(_strify(key), _strify(value)) for key, value in
            input.items()])
    elif isinstance(input, list):
        return [_strify(element) for element in input]
    elif isinstance(input, (str, bytes)):
        return misc.force_str(input, "utf-8")
    else:
        return input


def _get_pkg_input_schema(subcommand, opts_mapping=misc.EmptyDict):
    """Get the input schema for pkg subcommand."""

    # Return None if the subcommand is not defined.
    if subcommand not in cmds:
        return None

    props = {}
    data_schema = __get_pkg_input_schema(subcommand,
        opts_mapping=opts_mapping)
    props.update(data_schema)
    schema = __construct_json_schema("{0} input schema".format(subcommand),
        properties=props)
    return schema


def _get_pkg_output_schema(subcommand):
    """Get the output schema for pkg subcommand."""

    # Return None if the subcommand is not defined.
    if subcommand not in cmds:
        return None

    props = {"status": {"type": "number"},
        "errors": {"type": "array",
            "items": __default_error_json_schema()
            }
        }
    required = ["status"]
    data_schema = cmds[subcommand][1]()
    if data_schema:
        props["data"] = data_schema
    schema = __construct_json_schema("{0} output schema".format(
        subcommand), properties=props, required=required)
    return schema


def __get_pkg_input_schema(pkg_op, opts_mapping=misc.EmptyDict):
    properties = {}
    for entry in options.pkg_op_opts[pkg_op]:
        if type(entry) != tuple:
            continue
        if len(entry) == 4:
            opt, dummy_default, dummy_valid_args, \
                schema = entry

            if opt in opts_mapping:
                optn = opts_mapping[opt]
                if optn:
                    properties[optn] = schema
                else:
                    properties[opt] = schema
            else:
                properties[opt] = schema

    arg_name = "pargs_json"
    input_schema = \
        {arg_name: {
            "type": "array",
            "items": {
                "type": "string"
                }
            },
            "opts_json": {"type": "object",
                "properties": properties
            },
        }
    return input_schema


def __pkg_list_output_schema():
    data_schema = {"type": "array",
        "items": {
            "type": "object",
            "properties": {
                "pub": {"type": "string"},
                "pkg": {"type": "string"},
                "version": {"type": "string"},
                "summary": {"type": "string"},
                "states": {"type": "array",
                    "items": {"type": "string"}}
                }
            }
        }
    return data_schema


def __get_plan_props():
    msg_payload_item = {
        "type": "object",
        "properties": {
            "msg_time": {"type": ["null", "string"]},
            "msg_level": {"type": ["null", "string"]},
            "msg_type": {"type": ["null", "string"]},
            "msg_text": {"type": ["null", "string"]}
        }
    }
    plan_props = {"type": "object",
        "properties": {
            "image-name": {"type": ["null", "string"]},
            "affect-services": {
              "type": "array",
              "items": {}
            },
            "licenses": {
              "type": "array",
              "items": [
                {
                  "type": "array",
                  "items": [
                    {"type": ["null", "string"]},
                    {},
                    {
                      "type": "array",
                      "items": [
                        {"type": ["null", "string"]},
                        {"type": ["null", "string"]},
                        {"type": ["null", "string"]},
                        {"type": ["null", "boolean"]},
                        {"type": ["null", "boolean"]}
                      ]}]
                },
                {"type": "array",
                  "items": [
                    {"type": ["null", "string"]},
                    {},
                    {"type": "array",
                      "items": [
                        {"type": ["null", "string"]},
                        {"type": ["null", "string"]},
                        {"type": ["null", "string"]},
                        {"type": ["null", "boolean"]},
                        {"type": ["null", "boolean"]}
                      ]}]}]
            },
            "child-images": {
              "type": "array",
              "items": {}
            },
            "change-mediators": {
              "type": "array",
              "items": {}
            },
            "change-facets": {
              "type": "array",
              "items": {}
            },
            "remove-packages": {
              "type": "array",
              "items": {}
            },
            "be-name": {
              "type": ["null", "string"],
            },
            "space-available": {
              "type": ["null", "number"],
            },
            "boot-archive-rebuild": {
              "type": ["null", "boolean"],
            },
            "version": {
              "type": ["null", "number"],
            },
            "create-new-be": {
              "type": ["null", "boolean"],
            },
            "change-packages": {
              "type": "array",
              "items": {}
            },
            "space-required": {
              "type": ["null", "number"],
            },
            "change-variants": {
              "type": "array",
              "items": {}
            },
            "affect-packages": {
              "type": "array",
              "items": {}
            },
            "change-editables": {
              "type": "array",
              "items": {}
            },
            "create-backup-be": {
              "type": ["null", "boolean"],
            },
            "release-notes": {
              "type": "array",
              "items": {}
            },
            "add-packages": {
              "type": "array",
              "items": {
                "type": ["null", "string"]
              },
            },
            "backup-be-name": {
              "type": ["null", "string"]
            },
            "activate-be": {
              "type": ["null", "boolean"],
            },
            # Because item id is non-deterministic, only properties that
            # can be determined are listed here.
            "item-messages": {"type": "object",
                "properties": {
                    "unpackaged": {"type": "object",
                        "properties": {
                            "errors": {"type": "array",
                                            "items": msg_payload_item},
                            "warnings": {"type": "array",
                                                 "items": msg_payload_item}
                        }
                    }
                }
            }
          }
        }
    return plan_props


def __pkg_exact_install_output_schema():
    data_schema = {"type": "object",
        "properties": {
            "plan": __get_plan_props()
            }
        }
    return data_schema


def __pkg_install_output_schema():
    data_schema = {"type": "object",
        "properties": {
            "plan": __get_plan_props()
            }
        }
    return data_schema


def __pkg_update_output_schema():
    data_schema = {"type": "object",
        "properties": {
            "plan": __get_plan_props()
            }
        }
    return data_schema


def __pkg_uninstall_output_schema():
    data_schema = {"type": "object",
        "properties": {
            "plan": __get_plan_props(),
            }
        }
    return data_schema


def __pkg_publisher_set_output_schema():
    data_schema = {"type": "object",
        "properties": {
            "header": {"type": "string"},
            "added": {"type": "array", "items": {"type": "string"}},
            "updated": {"type": "array", "items": {"type": "string"}}
            }
        }
    return data_schema


def __pkg_publisher_unset_output_schema():
    return {}


def __pkg_publisher_output_schema():
    data_schema = {"type": "object",
        "properties": {
            "header": {"type": "array", "items": {"type": "string"}},
            "publishers": {"type": "array", "items": {"type": "array",
                "items": {"type": ["null", "string"]}}},
            "publisher_details": {"type": "array",
                "items": {"type": "object", "properties": {
                    "Publisher": {"type": ["null", "string"]},
                    "Alias": {"type": ["null", "string"]},
                    "Client UUID": {"type": ["null", "string"]},
                    "Catalog Updated": {"type": ["null", "string"]},
                    "Enabled": {"type": ["null", "string"]},
                    "Properties": {"type": "object"},
                    "origins": {"type": "array",
                        "items": {"type": "object"}},
                    "mirrors": {"type": "array",
                        "items": {"type": "object"}},
                    "Approved CAs": {"type": "array"},
                    "Revoked CAs": {"type": "array"},
                }}}
            }
        }
    return data_schema


def __pkg_info_output_schema():
    data_schema = {"type": "object",
        "properties": {
            "licenses": {"type": "array", "items": {"type": "array",
                "items": {"type": ["null", "string"]}}},
            "package_attrs": {"type": "array",
                "items": {"type": "array", "items": {"type": "array",
                "items": [{"type": ["null", "string"]}, {"type": "array",
                "items": {"type": ["null", "string"]}}]}}}
        }
    }
    return data_schema


def __pkg_verify_output_schema():
    data_schema = {"type": "object",
        "properties": {
            "plan": __get_plan_props(),
            }
        }
    return data_schema


def __pkg_fix_output_schema():
    data_schema = {"type": "object",
        "properties": {
            "plan": __get_plan_props(),
            }
        }
    return data_schema


def _format_update_error(e, errors_json=None):
    # This message is displayed to the user whenever an
    # ImageFormatUpdateNeeded exception is encountered.
    if errors_json:
        error = {"reason": str(e), "errtype": "format_update"}
        errors_json.append(error)


def _error_json(text, cmd=None, errors_json=None, errorType=None):
    """Prepare an error message for json output. """

    if not isinstance(text, str):
        # Assume it's an object that can be stringified.
        text = str(text)

    # If the message starts with whitespace, assume that it should come
    # *before* the command-name prefix.
    text_nows = text.lstrip()
    ws = text[:len(text) - len(text_nows)]

    if cmd:
        text_nows = "{0}: {1}".format(cmd, text_nows)
        pkg_cmd = "pkg "
    else:
        pkg_cmd = "pkg: "

    if errors_json is not None:
        error = {}
        if errorType:
            error["errtype"] = errorType
        error["reason"] = ws + pkg_cmd + text_nows
        errors_json.append(error)


def _collect_proxy_config_errors(errors_json=None):
    """If the user has configured http_proxy or https_proxy in the
    environment, collect the values. Some transport errors are
    not debuggable without this information handy."""

    http_proxy = os.environ.get("http_proxy", None)
    https_proxy = os.environ.get("https_proxy", None)

    if not http_proxy and not https_proxy:
        return

    err = "\nThe following proxy configuration is set in the " \
        "environment:\n"
    if http_proxy:
        err += "http_proxy: {0}\n".format(http_proxy)
    if https_proxy:
        err += "https_proxy: {0}\n".format(https_proxy)
    if errors_json:
        errors_json.append({"reason": err})


def _get_fmri_args(api_inst, pargs, cmd=None, errors_json=None):
    """ Convenience routine to check that input args are valid fmris. """

    res = []
    errors = []
    for pat, err, pfmri, matcher in api_inst.parse_fmri_patterns(pargs):
        if not err:
            res.append((pat, err, pfmri, matcher))
            continue
        if isinstance(err, version.VersionError):
            # For version errors, include the pattern so
            # that the user understands why it failed.
            errors.append("Illegal FMRI '{0}': {1}".format(pat,
                err))
        else:
            # Including the pattern is redundant for other
            # exceptions.
            errors.append(err)
    if errors:
        _error_json("\n".join(str(e) for e in errors),
            cmd=cmd, errors_json=errors_json)
    return len(errors) == 0, res


def __default_error_json_schema():
    """Get the default error json schema."""

    error_schema = {
        "type": "object",
        "properties": {
            "errtype": {"type": "string",
                "enum": ["format_update", "catalog_refresh",
                "catalog_refresh_failed", "inventory",
                "inventory_extra", "plan_license", "publisher_set",
                "unsupported_repo_op", "cert_info", "info_not_found",
                "info_no_licenses"]},
            "reason": {"type": "string"},
            "info": {"type": "string"}
            }
        }
    return error_schema


def __construct_json_schema(title, description=None, stype="object",
    properties=None, required=None, additional_prop=False):
    """Construct  json schema."""

    json_schema = {"$schema": "http://json-schema.org/draft-04/schema#",
        "title": title,
        "type": stype,
        }
    if description:
        json_schema["description"] = description
    if properties:
        json_schema["properties"] = properties
    if required:
        json_schema["required"] = required
    json_schema["additionalProperties"] = additional_prop
    return json_schema


def __prepare_json(status, op=None, schema=None, data=None, errors=None):
    """Prepare json structure for returning."""

    ret_json = {"status": status}

    if errors:
        if not isinstance(errors, list):
            ret_json["errors"] = [errors]
        else:
            ret_json["errors"] = errors
    if data:
        ret_json["data"] = data
    if op:
        op_schema = _get_pkg_output_schema(op)
        try:
            jsonschema.validate(ret_json, op_schema)
        except jsonschema.ValidationError as e:
            newret_json = {"status": EXIT_OOPS,
                "errors": [{"reason": str(e)}]}
            return newret_json
    if schema:
        ret_json["schema"] = schema

    return ret_json


def _collect_catalog_failures(cre, ignore_perms_failure=False, errors=None):
    total = cre.total
    succeeded = cre.succeeded
    partial = 0
    refresh_errstr = ""

    for pub, err in cre.failed:
        if isinstance(err, api_errors.CatalogOriginRefreshException):
            if len(err.failed) < err.total:
                partial += 1

            refresh_errstr += _("\n{0}/{1} repositories for "
                "publisher '{2}' could not be refreshed.\n").format(
                len(err.failed), err.total, pub)
            for o, e in err.failed:
                refresh_errstr += "\n"
                refresh_errstr += str(e)
            refresh_errstr += "\n"
        else:
            refresh_errstr += "\n\n" + str(err)

    partial_str = ":"
    if partial:
        partial_str = _(" ({0} partial):").format(str(partial))

    txt = _("pkg: {succeeded}/{total} catalogs successfully "
        "updated{partial}").format(succeeded=succeeded, total=total,
        partial=partial_str)

    if errors is not None:
        if cre.failed:
            error = {"reason": txt, "errtype": "catalog_refresh"}
        else:
            error = {"info": txt, "errtype": "catalog_refresh"}
        errors.append(error)

    for pub, err in cre.failed:
        if ignore_perms_failure and \
            not isinstance(err, api_errors.PermissionsException):
            # If any errors other than a permissions exception are
            # found, then don't ignore them.
            ignore_perms_failure = False
            break

    if cre.failed and ignore_perms_failure:
        # Consider those that failed to have succeeded and add them
        # to the actual successful total.
        return succeeded + partial + len(cre.failed)

    if errors is not None:
        error = {"reason": str(refresh_errstr),
            "errtype": "catalog_refresh"}
        errors.append(error)

    if cre.errmessage:
        if errors is not None:
            error = {"reason": str(cre.errmessage),
                "errtype": "catalog_refresh"}
            errors.append(error)

    return succeeded + partial


def _list_inventory(op, api_inst, pargs,
    li_parent_sync, list_all, list_installed_newest, list_newest,
    list_upgradable, origins, quiet, refresh_catalogs, **other_opts):
    """List packages."""

    api_inst.progresstracker.set_purpose(
        api_inst.progresstracker.PURPOSE_LISTING)

    variants = False
    pkg_list = api.ImageInterface.LIST_INSTALLED
    if list_all:
        variants = True
        pkg_list = api.ImageInterface.LIST_ALL
    elif list_installed_newest:
        pkg_list = api.ImageInterface.LIST_INSTALLED_NEWEST
    elif list_newest:
        pkg_list = api.ImageInterface.LIST_NEWEST
    elif list_upgradable:
        pkg_list = api.ImageInterface.LIST_UPGRADABLE

    # Each pattern in pats can be a partial or full FMRI, so
    # extract the individual components.  These patterns are
    # transformed here so that partial failure can be detected
    # when more than one pattern is provided.
    errors_json = []
    rval, res = _get_fmri_args(api_inst, pargs, cmd=op,
        errors_json=errors_json)
    if not rval:
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    api_inst.log_operation_start(op)
    if pkg_list != api_inst.LIST_INSTALLED and refresh_catalogs:
        # If the user requested packages other than those
        # installed, ensure that a refresh is performed if
        # needed since the catalog may be out of date or
        # invalid as a result of publisher information
        # changing (such as an origin uri, etc.).
        try:
            api_inst.refresh(ignore_unreachable=False)
        except api_errors.PermissionsException:
            # Ignore permission exceptions with the
            # assumption that an unprivileged user is
            # executing this command and that the
            # refresh doesn't matter.
            pass
        except api_errors.CatalogRefreshException as e:
            succeeded = _collect_catalog_failures(e,
                ignore_perms_failure=True, errors=errors_json)
            if succeeded != e.total:
                # If total number of publishers does
                # not match 'successful' number
                # refreshed, abort.
                return __prepare_json(EXIT_OOPS,
                    errors=errors_json)

        except:
            # Ignore the above error and just use what
            # already exists.
            pass

    state_map = [
        [(api.PackageInfo.INSTALLED, "installed")],
        [(api.PackageInfo.FROZEN, "frozen")],
        [
            (api.PackageInfo.OBSOLETE, "obsolete"),
            (api.PackageInfo.LEGACY, "legacy"),
            (api.PackageInfo.RENAMED, "renamed")
        ],
    ]

    # Now get the matching list of packages and display it.
    found = False

    data = []
    try:
        res = api_inst.get_pkg_list(pkg_list, patterns=pargs,
            raise_unmatched=True, repos=origins, variants=variants)
        for pt, summ, cats, states, attrs in res:
            found = True
            entry = {}
            pub, stem, ver = pt
            entry["pub"] = pub
            entry["pkg"] = stem
            entry["version"] = ver
            entry["summary"] = summ

            stateslist = []
            for sentry in state_map:
                for s, v in sentry:
                    if s in states:
                        stateslist.append(v)
                        break
            entry["states"] = stateslist
            data.append(entry)
        if not found and not pargs:
            if pkg_list == api_inst.LIST_INSTALLED:
                if not quiet:
                    err = {"reason":
                        _("no packages installed")}
                    errors_json.append(err)
                api_inst.log_operation_end(
                    result=RESULT_NOTHING_TO_DO)
            elif pkg_list == api_inst.LIST_INSTALLED_NEWEST:
                if not quiet:
                    err = {"reason": _("no packages "
                        "installed or available for "
                        "installation")}
                    errors_json.append(err)
                api_inst.log_operation_end(
                    result=RESULT_NOTHING_TO_DO)
            elif pkg_list == api_inst.LIST_UPGRADABLE:
                if not quiet:
                    img = api_inst._img
                    cat = img.get_catalog(
                        img.IMG_CATALOG_INSTALLED)
                    if cat.package_count > 0:
                        err = {"reason":
                            _("no packages have "
                            "newer versions "
                            "available")}
                    else:
                        err = {"reason":
                            _("no packages are "
                            "installed")}
                    errors_json.append(err)
                api_inst.log_operation_end(
                    result=RESULT_NOTHING_TO_DO)
            else:
                api_inst.log_operation_end(
                    result=RESULT_NOTHING_TO_DO)
            return __prepare_json(EXIT_OOPS,
                errors=errors_json)

        api_inst.log_operation_end()
        return __prepare_json(EXIT_OK, data=data,
            errors=errors_json)
    except (api_errors.InvalidPackageErrors,
        api_errors.ActionExecutionError,
        api_errors.PermissionsException) as e:
        _error_json(e, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, data=data,
            errors=errors_json)
    except api_errors.CatalogRefreshException as e:
        _collect_catalog_failures(e, errors=errors_json)
        return __prepare_json(EXIT_OOPS, data=data,
            errors=errors_json)
    except api_errors.InventoryException as e:
        if e.illegal:
            for i in e.illegal:
                _error_json(i, errors_json=errors_json)
            api_inst.log_operation_end(
                result=RESULT_FAILED_BAD_REQUEST)
            return __prepare_json(EXIT_OOPS, data=data,
                errors=errors_json)

        if quiet:
            # Collect nothing.
            pass
        elif pkg_list == api.ImageInterface.LIST_ALL or \
            pkg_list == api.ImageInterface.LIST_NEWEST:
            _error_json(_("no known packages matching:\n  {0}"
                ).format("\n  ".join(e.notfound)), cmd=op,
                errors_json=errors_json,
                errorType="inventory")
        elif pkg_list == api.ImageInterface.LIST_INSTALLED_NEWEST:
            _error_json(_("no packages matching the following "
                "patterns are allowed by installed "
                "incorporations, or image variants that are known "
                "or installed\n  {0}").format(
                "\n  ".join(e.notfound)), cmd=op,
                errors_json=errors_json,
                errorType="inventory_extra")
        elif pkg_list == api.ImageInterface.LIST_UPGRADABLE:
            # Creating a list of packages that are uptodate
            # and that are not installed on the system.
            no_updates = []
            not_installed = []
            try:
                for entry in api_inst.get_pkg_list(
                    api.ImageInterface.LIST_INSTALLED,
                    patterns=e.notfound, raise_unmatched=True):
                    pub, stem, ver = entry[0]
                    no_updates.append(stem)
            except api_errors.InventoryException as exc:
                not_installed = exc.notfound

            err_str = ""
            if not_installed:
                err_str = _("no packages matching the "
                    "following patterns are installed:\n  {0}"
                    ).format("\n  ".join(not_installed))

            if no_updates:
                err_str = err_str + _("no updates are "
                    "available for the following packages:\n  "
                    "{0}").format("\n  ".join(no_updates))
            if err_str:
                _error_json(err_str, cmd=op,
                    errors_json=errors_json,
                    errorType="inventory")
        else:
            _error_json(_("no packages matching the following "
                "patterns are installed:\n  {0}").format(
                "\n  ".join(e.notfound)), cmd=op,
                errors_json=errors_json,
                errorType="inventory")

        if found and e.notfound:
            # Only some patterns matched.
            api_inst.log_operation_end()
            return __prepare_json(EXIT_PARTIAL, data=data,
                errors=errors_json)
        api_inst.log_operation_end(result=RESULT_NOTHING_TO_DO)
        return __prepare_json(EXIT_OOPS, data=data, errors=errors_json)


def _get_tracker(prog_delay=PROG_DELAY, prog_tracker=None):
    if prog_tracker:
        return prog_tracker
    elif global_settings.client_output_parsable_version is not None:
        progresstracker = progress.NullProgressTracker()
    elif global_settings.client_output_quiet:
        progresstracker = progress.QuietProgressTracker()
    elif global_settings.client_output_progfd:
        # This logic handles linked images: for linked children
        # we elide the progress output.
        output_file = os.fdopen(global_settings.client_output_progfd,
            "w")
        child_tracker = progress.LinkedChildProgressTracker(
            output_file=output_file)
        dot_tracker = progress.DotProgressTracker(
            term_delay=prog_delay, output_file=output_file)
        progresstracker = progress.MultiProgressTracker(
            [child_tracker, dot_tracker])
    else:
        try:
            progresstracker = progress.FancyUNIXProgressTracker(
                term_delay=prog_delay)
        except progress.ProgressTrackerException:
            progresstracker = progress.CommandLineProgressTracker(
                term_delay=prog_delay)
    return progresstracker


def _accept_plan_licenses(api_inst):
    """Helper function that marks all licenses for the current plan as
    accepted if they require acceptance."""

    plan = api_inst.describe()
    for pfmri, src, dest, accepted, displayed in plan.get_licenses():
        if not dest.must_accept:
            continue
        api_inst.set_plan_license_status(pfmri, dest.license,
            accepted=True)


display_plan_options = ["basic", "fmris", "variants/facets", "services",
    "actions", "boot-archive"]


def __api_alloc(pkg_image, orig_cwd, prog_delay=PROG_DELAY, prog_tracker=None,
    errors_json=None):
    """Allocate API instance."""

    provided_image_dir = True
    pkg_image_used = False

    if pkg_image:
        imgdir = pkg_image

    if "imgdir" not in locals():
        imgdir, provided_image_dir = api.get_default_image_root(
            orig_cwd=orig_cwd)
        if os.environ.get("PKG_IMAGE"):
            # It's assumed that this has been checked by the above
            # function call and hasn't been removed from the
            # environment.
            pkg_image_used = True

    if not imgdir:
        if errors_json:
            err = {"reason": "Could not find image. Set the "
                "pkg_image property to the\nlocation of an image."}
            errors_json.append(err)
        return

    progresstracker = _get_tracker(prog_delay=prog_delay,
        prog_tracker=prog_tracker)
    try:
        return api.ImageInterface(imgdir, CLIENT_API_VERSION,
            progresstracker, None, PKG_CLIENT_NAME,
            exact_match=provided_image_dir)
    except api_errors.ImageNotFoundException as e:
        if e.user_specified:
            if pkg_image_used:
                _error_json(_("No image rooted at '{0}' "
                    "(set by $PKG_IMAGE)").format(e.user_dir),
                    errors_json=errors_json)
            else:
                _error_json(_("No image rooted at '{0}'")
                   .format(e.user_dir), errors_json=errors_json)
        else:
            _error_json(_("No image found."),
                errors_json=errors_json)
        return
    except api_errors.PermissionsException as e:
        _error_json(e, errors_json=errors_json)
        return
    except api_errors.ImageFormatUpdateNeeded as e:
        _format_update_error(e, errors_json=errors_json)
        return


def __api_prepare_plan(operation, api_inst):
    # Exceptions which happen here are printed in the above level, with
    # or without some extra decoration done here.
    # XXX would be nice to kick the progress tracker.
    errors_json = []
    try:
        api_inst.prepare()
    except (api_errors.PermissionsException, api_errors.UnknownErrors) as e:
        # Prepend a newline because otherwise the exception will
        # be printed on the same line as the spinner.
        _error_json("\n" + str(e), errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.TransportError as e:
        raise e
    except api_errors.PlanLicenseErrors as e:
        # Prepend a newline because otherwise the exception will
        # be printed on the same line as the spinner.
        _error_json(_("\nThe following packages require their "
            "licenses to be accepted before they can be installed "
            "or updated:\n {0}").format(str(e)),
            errors_json=errors_json, errorType="plan_license")
        return __prepare_json(EXIT_LICENSE, errors=errors_json)
    except api_errors.InvalidPlanError as e:
        # Prepend a newline because otherwise the exception will
        # be printed on the same line as the spinner.
        _error_json("\n" + str(e), errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.ImageFormatUpdateNeeded as e:
        _format_update_error(e, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.ImageInsufficentSpace as e:
        _error_json(str(e), errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.LinkedImageException as e:
        _error_json(str(e), errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        _error_json(_("\nAn unexpected error happened while preparing "
            "for {op}: {err}").format(op=operation, err=str(e)))
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    return __prepare_json(EXIT_OK)


def __api_execute_plan(operation, api_inst):
    rval = None
    errors_json = []
    try:
        api_inst.execute_plan()
        pd = api_inst.describe()
        if pd.actuator_timed_out:
            rval = __prepare_json(EXIT_ACTUATOR)
        else:
            rval = __prepare_json(EXIT_OK)
    except RuntimeError as e:
        _error_json(_("{operation} failed: {err}").format(
            operation=operation, err=e), errors_json=errors_json)
        rval = __prepare_json(EXIT_OOPS, errors=errors_json)
    except (api_errors.InvalidPlanError,
        api_errors.ActionExecutionError,
        api_errors.InvalidPackageErrors) as e:
        # Prepend a newline because otherwise the exception will
        # be printed on the same line as the spinner.
        _error_json("\n" + str(e), errors_json=errors_json)
        rval = __prepare_json(EXIT_OOPS, errors=errors_json)
    except (api_errors.LinkedImageException) as e:
        _error_json(_("{operation} failed (linked image exception(s))"
            ":\n{err}").format(operation=operation, err=e),
            errors_json=errors_json)
        rval = __prepare_json(e.lix_exitrv, errors=errors_json)
    except api_errors.ImageUpdateOnLiveImageException:
        _error_json(_("{0} cannot be done on live image").format(
            operation), errors_json=errors_json)
        rval = __prepare_json(EXIT_NOTLIVE, errors=errors_json)
    except api_errors.RebootNeededOnLiveImageException:
        _error_json(_("Requested \"{0}\" operation would affect files "
            "that cannot be modified in live image.\n"
            "Please retry this operation on an alternate boot "
            "environment.").format(operation), errors_json=errors_json)
        rval = __prepare_json(EXIT_NOTLIVE, errors=errors_json)
    except api_errors.CorruptedIndexException as e:
        _error_json("The search index appears corrupted.  Please "
            "rebuild the index with 'pkg rebuild-index'.",
            errors_json=errors_json)
        rval = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.ProblematicPermissionsIndexException as e:
        _error_json(str(e), errors_json=errors_json)
        _error_json(_("\n(Failure to consistently execute pkg commands "
            "as a privileged user is often a source of this problem.)"),
            errors_json=errors_json)
        rval = __prepare_json(EXIT_OOPS, errors=errors_json)
    except (api_errors.PermissionsException, api_errors.UnknownErrors) as e:
        # Prepend a newline because otherwise the exception will
        # be printed on the same line as the spinner.
        _error_json("\n" + str(e), errors_json=errors_json)
        rval = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.ImageFormatUpdateNeeded as e:
        _format_update_error(e, errors_json=errors_json)
        rval = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.BEException as e:
        _error_json(e, errors_json=errors_json)
        rval = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.WrapSuccessfulIndexingException:
        raise
    except api_errors.ImageInsufficentSpace as e:
        _error_json(str(e), errors_json=errors_json)
        rval = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.InvalidMediatorTarget as e:
        _error_json(str(e), errors_json=errors_json)
        # An invalid target means the operation completed but
        # the user needs to consider the state of any image so
        # return a EXIT_PARTIAL.
        rval = __prepare_json(EXIT_PARTIAL, errors=errors_json)
    except Exception as e:
        _error_json(_("An unexpected error happened during "
            "{operation}: {err}").format(
            operation=operation, err=e), errors_json=errors_json)
        rval = __prepare_json(EXIT_OOPS, errors=errors_json)
    finally:
        exc_type = exc_value = exc_tb = None
        if rval is None:
            # Store original exception so that the real cause of
            # failure can be raised if this fails.
            exc_type, exc_value, exc_tb = sys.exc_info()

        try:
            salvaged = api_inst.describe().salvaged
            newbe = api_inst.describe().new_be
            stat = None
            if rval:
                stat = rval["status"]
            if salvaged and (stat == EXIT_OK or not newbe):
                # Only show salvaged file list if populated
                # and operation was successful, or if operation
                # failed and a new BE was not created for
                # the operation.
                err = _("\nThe following "
                    "unexpected or editable files and "
                    "directories were\n"
                    "salvaged while executing the requested "
                    "package operation; they\nhave been moved "
                    "to the displayed location in the image:\n")
                for opath, spath in salvaged:
                    err += "  {0} -> {1}\n".format(opath,
                        spath)
                errors_json.append({"info": err})
        except Exception:
            if rval is not None:
                # Only raise exception encountered here if the
                # exception previously raised was suppressed.
                raise

        if exc_value or exc_tb:
            raise exc_value

    return rval


def __api_plan_exception(op, noexecute, verbose, api_inst, errors_json=[],
    display_plan_cb=None):
    e_type, e, e_traceback = sys.exc_info()

    if e_type == api_errors.ImageNotFoundException:
        _error_json(_("No image rooted at '{0}'").format(e.user_dir),
            cmd=op, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    if e_type == api_errors.ImageLockingFailedError:
        _error_json(_(e), cmd=op, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    if e_type == api_errors.InventoryException:
        _error_json("\n" + _("{operation} failed (inventory exception):\n"
            "{err}").format(operation=op, err=e),
            errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    if isinstance(e, api_errors.LinkedImageException):
        _error_json(_("{operation} failed (linked image exception(s)):\n"
            "{err}").format(operation=op, err=e),
            errors_json=errors_json)
        return __prepare_json(e.lix_exitrv, errors=errors_json)
    if e_type == api_errors.IpkgOutOfDateException:
        error = {"info": _("""\
WARNING: pkg(7) appears to be out of date, and should be updated before
running {op}.  Please update pkg(7) by executing 'pkg install
pkg:/package/pkg' as a privileged user and then retry the {op}."""
            ).format(**locals())}
        errors_json.append(error)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    if e_type == api_errors.CatalogRefreshException:
        _collect_catalog_failures(e, errors=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    if e_type == api_errors.ConflictingActionErrors:
        if verbose and display_plan_cb:
            display_plan_cb(api_inst, verbose=verbose,
                noexecute=noexecute, plan_only=True)
        _error_json("\n" + str(e), cmd=op, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    if e_type == api_errors.ImageFormatUpdateNeeded:
        _format_update_error(e, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    if e_type == api_errors.ImageUpdateOnLiveImageException:
        _error_json("\n" + _("The proposed operation cannot be "
            "performed on a live image."), cmd=op,
            errors_json=errors_json)
        return __prepare_json(EXIT_NOTLIVE, errors=errors_json)

    if issubclass(e_type, api_errors.BEException):
        _error_json("\n" + str(e), cmd=op, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    if e_type == api_errors.PlanCreationException:
        # Prepend a newline because otherwise the exception will
        # be printed on the same line as the spinner.
        txt = str(e)
        if e.multiple_matches:
            txt += "\n\n" + _("Please provide one of the package "
                "FMRIs listed above to the install command.")
        _error_json("\n" + txt, cmd=op, errors_json=errors_json)
        if verbose:
            err_txt = "\n".join(e.verbose_info)
            if err_txt:
                errors_json.append({"reason": err_txt})
        if e.invalid_mediations:
            # Bad user input for mediation.
            return __prepare_json(EXIT_BADOPT, errors=errors_json)
        if e.no_solution:
            return __prepare_json(EXIT_CONSTRAINED, errors=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    if isinstance(e, (api_errors.CertificateError,
        api_errors.UnknownErrors,
        api_errors.PermissionsException,
        api_errors.InvalidPropertyValue,
        api_errors.InvalidResourceLocation,
        api_errors.UnsupportedVariantGlobbing,
        fmri.IllegalFmri,
        api_errors.SigningException,
        api_errors.NonLeafPackageException,
        api_errors.ReadOnlyFileSystemException,
        api_errors.InvalidPlanError,
        api_errors.ActionExecutionError,
        api_errors.InvalidPackageErrors,
        api_errors.ImageBoundaryErrors,
        api_errors.InvalidVarcetNames)):
        # Prepend a newline because otherwise the exception will
        # be printed on the same line as the spinner.
        _error_json("\n" + str(e), cmd=op, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    # if we didn't deal with the exception above, pass it on.
    raise
    # NOTREACHED


def __api_plan(_op, _api_inst, _accept=False, _li_ignore=None, _noexecute=False,
    _omit_headers=False, _origins=None, _parsable_version=None, _quiet=False,
    _quiet_plan=False, _show_licenses=False, _stage=API_STAGE_DEFAULT,
    _verbose=0, display_plan_cb=None, logger=None, _unpackaged=False,
    _unpackaged_only=False, _verify_paths=EmptyI, **kwargs):

    # All the api interface functions that we invoke have some
    # common arguments.  Set those up now.
    if _op not in (PKG_OP_REVERT, PKG_OP_FIX, PKG_OP_VERIFY,
        PKG_OP_DEHYDRATE, PKG_OP_REHYDRATE):
        kwargs["li_ignore"] = _li_ignore
    if _op == PKG_OP_VERIFY:
        kwargs["unpackaged"] = _unpackaged
        kwargs["unpackaged_only"] = _unpackaged_only
        kwargs["verify_paths"] = _verify_paths
    elif _op == PKG_OP_FIX:
        kwargs["unpackaged"] = _unpackaged

    kwargs["noexecute"] = _noexecute
    if _origins:
        kwargs["repos"] = _origins
    if _stage != API_STAGE_DEFAULT:
        kwargs["pubcheck"] = False

    # display plan debugging information
    if _verbose > 2:
        DebugValues["plan"] = "True"

    # plan the requested operation
    stuff_to_do = None

    if _op == PKG_OP_ATTACH:
        api_plan_func = _api_inst.gen_plan_attach
    elif _op in [PKG_OP_CHANGE_FACET, PKG_OP_CHANGE_VARIANT]:
        api_plan_func = _api_inst.gen_plan_change_varcets
    elif _op == PKG_OP_DEHYDRATE:
        api_plan_func = _api_inst.gen_plan_dehydrate
    elif _op == PKG_OP_DETACH:
        api_plan_func = _api_inst.gen_plan_detach
    elif _op == PKG_OP_EXACT_INSTALL:
        api_plan_func = _api_inst.gen_plan_exact_install
    elif _op == PKG_OP_FIX:
        api_plan_func = _api_inst.gen_plan_fix
    elif _op == PKG_OP_INSTALL:
        api_plan_func = _api_inst.gen_plan_install
    elif _op == PKG_OP_REHYDRATE:
        api_plan_func = _api_inst.gen_plan_rehydrate
    elif _op == PKG_OP_REVERT:
        api_plan_func = _api_inst.gen_plan_revert
    elif _op == PKG_OP_SYNC:
        api_plan_func = _api_inst.gen_plan_sync
    elif _op == PKG_OP_UNINSTALL:
        api_plan_func = _api_inst.gen_plan_uninstall
    elif _op == PKG_OP_UPDATE:
        api_plan_func = _api_inst.gen_plan_update
    elif _op == PKG_OP_VERIFY:
        api_plan_func = _api_inst.gen_plan_verify
    else:
        raise RuntimeError("__api_plan() invalid op: {0}".format(_op))

    errors_json = []
    planned_self = False
    child_plans = []
    try:
        for pd in api_plan_func(**kwargs):
            if planned_self:
                # we don't display anything for child images
                # since they currently do their own display
                # work (unless parsable output is requested).
                child_plans.append(pd)
                continue

            # the first plan description is always for ourself.
            planned_self = True
            pkg_timer.record("planning", logger=logger)

            # if we're in parsable mode don't display anything
            # until after we finish planning for all children
            if _parsable_version is None and display_plan_cb:
                display_plan_cb(_api_inst, [], _noexecute,
                    _omit_headers, _op, _parsable_version,
                    _quiet, _quiet_plan, _show_licenses,
                    _stage, _verbose, _unpackaged,
                    _unpackaged_only)

            # if requested accept licenses for child images.  we
            # have to do this before recursing into children.
            if _accept:
                _accept_plan_licenses(_api_inst)
    except:
        ret = __api_plan_exception(_op, _noexecute, _verbose,
            _api_inst, errors_json=errors_json,
            display_plan_cb=display_plan_cb)
        if ret["status"] != EXIT_OK:
            pkg_timer.record("planning", logger=logger)
            return ret

    if not planned_self:
        # if we got an exception we didn't do planning for children
        pkg_timer.record("planning", logger=logger)

    elif _api_inst.isparent(_li_ignore):
        # if we didn't get an exception and we're a parent image then
        # we should have done planning for child images.
        pkg_timer.record("planning children", logger=logger)

    # if we didn't display our own plan (due to an exception), or if we're
    # in parsable mode, then display our plan now.
    parsable_plan = None
    if not planned_self or _parsable_version is not None:
        try:
            if display_plan_cb:
                display_plan_cb(_api_inst, child_plans,
                    _noexecute, _omit_headers, _op,
                    _parsable_version, _quiet, _quiet_plan,
                    _show_licenses, _stage, _verbose,
                    _unpackaged, _unpackaged_only)
            else:
                plan = _api_inst.describe()
                parsable_plan = plan.get_parsable_plan(
                    _parsable_version, child_plans,
                    api_inst=_api_inst)
                # Convert to json.
                parsable_plan = json.loads(json.dumps(
                    parsable_plan))
        except api_errors.ApiException as e:
            _error_json(e, cmd=_op, errors_json=errors_json)
            return __prepare_json(EXIT_OOPS, errors=errors_json)

    # if we didn't accept licenses (due to an exception) then do that now.
    if not planned_self and _accept:
        _accept_plan_licenses(_api_inst)

    data = {}
    if parsable_plan:
        data["plan"] = parsable_plan

    return __prepare_json(EXIT_OK, data=data)


def __api_plan_file(api_inst):
    """Return the path to the PlanDescription save file."""

    plandir = api_inst.img_plandir
    return os.path.join(plandir, "plandesc")


def __api_plan_save(api_inst, logger=None):
    """Save an image plan to a file."""

    # get a pointer to the plan
    plan = api_inst.describe()

    # save the PlanDescription to a file
    path = __api_plan_file(api_inst)
    oflags = os.O_CREAT | os.O_TRUNC | os.O_WRONLY
    try:
        fd = os.open(path, oflags, 0o644)
        with os.fdopen(fd, "w") as fobj:
            plan._save(fobj)

        # cleanup any old style imageplan save files
        for f in os.listdir(api_inst.img_plandir):
            path = os.path.join(api_inst.img_plandir, f)
            if re.search(r"^actions\.[0-9]+\.json$", f):
                os.unlink(path)
            if re.search(r"^pkgs\.[0-9]+\.json$", f):
                os.unlink(path)
    except OSError as e:
        raise api_errors._convert_error(e)

    pkg_timer.record("saving plan", logger=logger)


def __api_plan_load(api_inst, stage, origins, logger=None):
    """Loan an image plan from a file."""

    # load an existing plan
    path = __api_plan_file(api_inst)
    plan = api.PlanDescription()
    try:
        with open(path) as fobj:
            plan._load(fobj)
    except OSError as e:
        raise api_errors._convert_error(e)

    pkg_timer.record("loading plan", logger=logger)

    api_inst.reset()
    api_inst.set_alt_repos(origins)
    api_inst.load_plan(plan, prepared=(stage == API_STAGE_EXECUTE))
    pkg_timer.record("re-initializing plan", logger=logger)

    if stage == API_STAGE_EXECUTE:
        __api_plan_delete(api_inst)


def __api_plan_delete(api_inst):
    """Delete an image plan file."""

    path = __api_plan_file(api_inst)
    try:
        os.unlink(path)
    except OSError as e:
        raise api_errors._convert_error(e)


def __verify_exit_status(api_inst):
    """Determine verify exit status."""

    plan = api_inst.describe()
    for item_id, parent_id, msg_time, msg_level, msg_type, msg_text in \
        plan.gen_item_messages():
        if msg_level == MSG_ERROR:
            return EXIT_OOPS
    return EXIT_OK


def __api_op(_op, _api_inst, _accept=False, _li_ignore=None, _noexecute=False,
    _origins=None, _parsable_version=None, _quiet=False, _quiet_plan=False,
    _show_licenses=False, _stage=API_STAGE_DEFAULT, _verbose=0,
    _unpackaged=False, _unpackaged_only=False, _verify_paths=EmptyI,
    display_plan_cb=None, logger=None, **kwargs):
    """Do something that involves the api.

    Arguments prefixed with '_' are primarily used within this
    function.  All other arguments must be specified via keyword
    assignment and will be passed directly on to the api
    interfaces being invoked."""

    data = {}
    if _stage in [API_STAGE_DEFAULT, API_STAGE_PLAN]:
        # create a new plan
        ret = __api_plan(_op=_op, _api_inst=_api_inst,
            _accept=_accept, _li_ignore=_li_ignore,
            _noexecute=_noexecute, _origins=_origins,
            _parsable_version=_parsable_version, _quiet=_quiet,
            _show_licenses=_show_licenses, _stage=_stage,
            _verbose=_verbose, _quiet_plan=_quiet_plan,
            _unpackaged=_unpackaged, _unpackaged_only=_unpackaged_only,
            _verify_paths=_verify_paths, display_plan_cb=display_plan_cb,
            logger=logger, **kwargs)

        if "_failures" in _api_inst._img.transport.repo_status:
            ret.setdefault("data", {}).update(
                {"repo_status":
                _api_inst._img.transport.repo_status})

        if ret["status"] != EXIT_OK:
            return ret
        if "data" in ret:
            data.update(ret["data"])

        if not _noexecute and _stage == API_STAGE_PLAN:
            # We always save the plan, even if it is a noop.  We
            # do this because we want to be able to verify that we
            # can load and execute a noop plan.  (This mimics
            # normal api behavior which doesn't prevent an api
            # consumer from creating a noop plan and then
            # preparing and executing it.)
            __api_plan_save(_api_inst, logger=logger)
        # for pkg verify or fix.
        if _op in [PKG_OP_FIX, PKG_OP_VERIFY] and _noexecute and \
            _quiet_plan:
            exit_code = __verify_exit_status(_api_inst)
            return __prepare_json(exit_code, data=data)
        if _api_inst.planned_nothingtodo():
            return __prepare_json(EXIT_NOP, data=data)
        if _noexecute or _stage == API_STAGE_PLAN:
            return __prepare_json(EXIT_OK, data=data)
    else:
        assert _stage in [API_STAGE_PREPARE, API_STAGE_EXECUTE]
        __api_plan_load(_api_inst, _stage, _origins, logger=logger)

    # Exceptions which happen here are printed in the above level,
    # with or without some extra decoration done here.
    if _stage in [API_STAGE_DEFAULT, API_STAGE_PREPARE]:
        ret = __api_prepare_plan(_op, _api_inst)
        pkg_timer.record("preparing", logger=logger)

        if ret["status"] != EXIT_OK:
            return ret
        if _stage == API_STAGE_PREPARE:
            return __prepare_json(EXIT_OK, data=data)

    ret = __api_execute_plan(_op, _api_inst)
    pkg_timer.record("executing", logger=logger)

    if ret["status"] == EXIT_OK and data:
        ret = __prepare_json(EXIT_OK, data=data)

    return ret


def _exact_install(op, api_inst, pargs,
    accept, backup_be, backup_be_name, be_activate, be_name, li_ignore,
    li_parent_sync, new_be, noexecute, origins, parsable_version, quiet,
    refresh_catalogs, reject_pats, show_licenses, update_index, verbose,
    display_plan_cb=None, logger=None):
    errors_json = []
    if not pargs:
        error = {"reason": _("at least one package name required")}
        errors_json.append(error)
        return __prepare_json(EXIT_BADOPT, errors=errors_json, op=op)

    rval, res = _get_fmri_args(api_inst, pargs, cmd=op,
        errors_json=errors_json)
    if not rval:
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    xrval, xres = _get_fmri_args(api_inst, reject_pats, cmd=op,
                errors_json=errors_json)
    if not xrval:
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    return __api_op(op, api_inst, _accept=accept, _li_ignore=li_ignore,
        _noexecute=noexecute, _origins=origins, _quiet=quiet,
        _show_licenses=show_licenses, _verbose=verbose,
        backup_be=backup_be, backup_be_name=backup_be_name,
        be_activate=be_activate, be_name=be_name,
        li_parent_sync=li_parent_sync, new_be=new_be,
        _parsable_version=parsable_version, pkgs_inst=pargs,
        refresh_catalogs=refresh_catalogs, reject_list=reject_pats,
        update_index=update_index, display_plan_cb=display_plan_cb,
        logger=logger)


def _install(op, api_inst, pargs, accept, act_timeout, backup_be,
    backup_be_name, be_activate, be_name, li_ignore, li_erecurse,
    li_parent_sync, new_be, noexecute, origins, parsable_version, quiet,
    refresh_catalogs, reject_pats, show_licenses, stage, update_index,
    verbose, display_plan_cb=None, logger=None):
    """Attempt to take package specified to INSTALLED state.  The operands
    are interpreted as glob patterns."""

    errors_json = []
    if not pargs:
        error = {"reason": _("at least one package name required")}
        errors_json.append(error)
        return __prepare_json(EXIT_BADOPT, errors=errors_json, op=op)

    rval, res = _get_fmri_args(api_inst, pargs, cmd=op,
        errors_json=errors_json)
    if not rval:
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    xrval, xres = _get_fmri_args(api_inst, reject_pats, cmd=op,
                errors_json=errors_json)
    if not xrval:
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    return __api_op(op, api_inst, _accept=accept, _li_ignore=li_ignore,
        _noexecute=noexecute, _origins=origins,
        _parsable_version=parsable_version, _quiet=quiet,
        _show_licenses=show_licenses, _stage=stage, _verbose=verbose,
        act_timeout=act_timeout, backup_be=backup_be,
        backup_be_name=backup_be_name, be_activate=be_activate,
        be_name=be_name, li_erecurse=li_erecurse,
        li_parent_sync=li_parent_sync, new_be=new_be, pkgs_inst=pargs,
        refresh_catalogs=refresh_catalogs, reject_list=reject_pats,
        update_index=update_index, display_plan_cb=display_plan_cb,
        logger=logger)


def _update(op, api_inst, pargs, accept, act_timeout, backup_be, backup_be_name,
    be_activate, be_name, force, ignore_missing, li_ignore, li_erecurse,
    li_parent_sync, new_be, noexecute, origins, parsable_version, quiet,
    refresh_catalogs, reject_pats, show_licenses, stage, update_index, verbose,
    display_plan_cb=None, logger=None):
    """Attempt to take all installed packages specified to latest
    version."""

    errors_json = []
    rval, res = _get_fmri_args(api_inst, pargs, cmd=op,
        errors_json=errors_json)
    if not rval:
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    xrval, xres = _get_fmri_args(api_inst, reject_pats, cmd=op,
            errors_json=errors_json)
    if not xrval:
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    if res:
        # If there are specific installed packages to update,
        # then take only those packages to the latest version
        # allowed by the patterns specified.  (The versions
        # specified can be older than what is installed.)
        pkgs_update = pargs
    else:
        # If no packages were specified, attempt to update all
        # installed packages.
        pkgs_update = None

    return __api_op(op, api_inst, _accept=accept, _li_ignore=li_ignore,
        _noexecute=noexecute, _origins=origins,
        _parsable_version=parsable_version, _quiet=quiet,
        _show_licenses=show_licenses, _stage=stage, _verbose=verbose,
        act_timeout=act_timeout, backup_be=backup_be,
        backup_be_name=backup_be_name, be_activate=be_activate,
        be_name=be_name, force=force, ignore_missing=ignore_missing,
        li_erecurse=li_erecurse, li_parent_sync=li_parent_sync,
        new_be=new_be, pkgs_update=pkgs_update,
        refresh_catalogs=refresh_catalogs, reject_list=reject_pats,
        update_index=update_index, display_plan_cb=display_plan_cb,
        logger=logger)


def _uninstall(op, api_inst, pargs,
    act_timeout, backup_be, backup_be_name, be_activate, be_name,
    ignore_missing, li_ignore, li_erecurse, li_parent_sync, new_be, noexecute,
    parsable_version, quiet, stage, update_index, verbose,
    display_plan_cb=None, logger=None):
    """Attempt to take package specified to DELETED state."""

    errors_json = []
    if not pargs:
        error = {"reason": _("at least one package name required")}
        errors_json.append(error)
        return __prepare_json(EXIT_BADOPT, errors=errors_json, op=op)

    rval, res = _get_fmri_args(api_inst, pargs, cmd=op,
        errors_json=errors_json)
    if not rval:
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    return __api_op(op, api_inst, _li_ignore=li_ignore,
        _noexecute=noexecute, _parsable_version=parsable_version,
        _quiet=quiet, _stage=stage, _verbose=verbose,
        act_timeout=act_timeout, backup_be=backup_be,
        backup_be_name=backup_be_name, be_activate=be_activate,
        be_name=be_name, ignore_missing=ignore_missing,
        li_erecurse=li_erecurse, li_parent_sync=li_parent_sync,
        new_be=new_be, pkgs_to_uninstall=pargs, update_index=update_index,
        display_plan_cb=display_plan_cb, logger=logger)


def _publisher_set(op, api_inst, pargs, ssl_key, ssl_cert, origin_uri,
    reset_uuid, add_mirrors, remove_mirrors, add_origins, remove_origins,
    enable_origins, disable_origins, refresh_allowed, disable, sticky,
    search_before, search_after, search_first, approved_ca_certs,
    revoked_ca_certs, unset_ca_certs, set_props, add_prop_values,
    remove_prop_values, unset_props, repo_uri, proxy_uri):
    """Function to set publisher."""

    name = None
    errors_json = []
    if len(pargs) == 0 and not repo_uri:
        errors_json.append({"reason": _("requires a publisher name")})
        return __prepare_json(EXIT_BADOPT, errors=errors_json, op=op)
    elif len(pargs) > 1:
        errors_json.append({"reason": _("only one publisher name may "
            "be specified")})
        return __prepare_json(EXIT_BADOPT, errors=errors_json, op=op)
    elif pargs:
        name = pargs[0]

    # Get sanitized SSL Cert/Key input values.
    ssl_cert, ssl_key = _get_ssl_cert_key(api_inst.root, api_inst.is_zone,
        ssl_cert, ssl_key)

    if not repo_uri:
        # Normal case.
        ret_json = _set_pub_error_wrap(_add_update_pub, name, [],
            api_inst, name, disable=disable, sticky=sticky,
            origin_uri=origin_uri, add_mirrors=add_mirrors,
            remove_mirrors=remove_mirrors, add_origins=add_origins,
            remove_origins=remove_origins,
            enable_origins=enable_origins,
            disable_origins=disable_origins, ssl_cert=ssl_cert,
            ssl_key=ssl_key, search_before=search_before,
            search_after=search_after, search_first=search_first,
            reset_uuid=reset_uuid, refresh_allowed=refresh_allowed,
            set_props=set_props, add_prop_values=add_prop_values,
            remove_prop_values=remove_prop_values,
            unset_props=unset_props, approved_cas=approved_ca_certs,
            revoked_cas=revoked_ca_certs, unset_cas=unset_ca_certs,
            proxy_uri=proxy_uri)

        if "errors" in ret_json:
            for err in ret_json["errors"]:
                errors_json.append(err)
        return __prepare_json(ret_json["status"], errors=errors_json)

    # Automatic configuration via -p case.
    def get_pubs():
        if proxy_uri:
            proxies = [publisher.ProxyURI(proxy_uri)]
        else:
            proxies = []
        repo = publisher.RepositoryURI(repo_uri,
            ssl_cert=ssl_cert, ssl_key=ssl_key, proxies=proxies)
        return __prepare_json(EXIT_OK, data=api_inst.get_publisherdata(
            repo=repo))

    ret_json = None
    try:
        ret_json = _set_pub_error_wrap(get_pubs, name,
            [api_errors.UnsupportedRepositoryOperation])
    except api_errors.UnsupportedRepositoryOperation as e:
        # Fail if the operation can't be done automatically.
        _error_json(str(e), cmd=op, errors_json=errors_json,
            errorType="unsupported_repo_op")
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    else:
        if ret_json["status"] != EXIT_OK and "errors" in ret_json:
            for err in ret_json["errors"]:
                _error_json(err["reason"], cmd=op,
                    errors_json=errors_json)
            return __prepare_json(ret_json["status"],
                errors=errors_json)
    # For the automatic publisher configuration case, update or add
    # publishers based on whether they exist and if they match any
    # specified publisher prefix.
    if "data" not in ret_json:
        _error_json(_("""
The specified repository did not contain any publisher configuration
information.  This is likely the result of a repository configuration
error.  Please contact the repository administrator for further
assistance."""), errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    pubs = ret_json["data"]
    if name and name not in pubs:
        known = [p.prefix for p in pubs]
        unknown = [name]
        e = api_errors.UnknownRepositoryPublishers(known=known,
            unknown=unknown, location=repo_uri)
        _error_json(str(e), errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    added = []
    updated = []
    failed = []

    for src_pub in sorted(pubs):
        prefix = src_pub.prefix
        if name and prefix != name:
            # User didn't request this one.
            continue

        src_repo = src_pub.repository
        if not api_inst.has_publisher(prefix=prefix):
            add_origins = []
            if not src_repo or not src_repo.origins:
                # If the repository publisher configuration
                # didn't include configuration information
                # for the publisher's repositories, assume
                # that the origin for the new publisher
                # matches the URI provided.
                add_origins.append(repo_uri)

            # Any -p origins/mirrors returned from get_pubs() should
            # use the proxy we declared, if any.
            if proxy_uri and src_repo:
                proxies = [publisher.ProxyURI(proxy_uri)]
                for repo_uri in src_repo.origins:
                    repo_uri.proxies = proxies
                for repo_uri in src_repo.mirrors:
                    repo_uri.proxies = proxies

            ret_json = _set_pub_error_wrap(_add_update_pub, name,
                [], api_inst, prefix, pub=src_pub,
                add_origins=add_origins, ssl_cert=ssl_cert,
                ssl_key=ssl_key, sticky=sticky,
                search_after=search_after,
                search_before=search_before,
                search_first=search_first,
                set_props=set_props,
                add_prop_values=add_prop_values,
                remove_prop_values=remove_prop_values,
                unset_props=unset_props, proxy_uri=proxy_uri)
            if ret_json["status"] == EXIT_OK:
                added.append(prefix)

            # When multiple publishers result from a single -p
            # operation, this ensures that the new publishers are
            # ordered correctly.
            search_first = False
            search_after = prefix
            search_before = None
        else:
            add_origins = []
            add_mirrors = []
            dest_pub = api_inst.get_publisher(prefix=prefix,
                duplicate=True)
            dest_repo = dest_pub.repository
            if dest_repo.origins and \
                not dest_repo.has_origin(repo_uri):
                add_origins = [repo_uri]

            if not src_repo and not add_origins:
                # The repository doesn't have to provide origin
                # information for publishers.  If it doesn't,
                # the origin of every publisher returned is
                # assumed to match the URI that the user
                # provided.  Since this is an update case,
                # nothing special needs to be done.
                if not dest_repo.origins:
                    add_origins = [repo_uri]
            elif src_repo:
                # Avoid duplicates by adding only those mirrors
                # or origins not already known.
                add_mirrors = [
                    u.uri
                    for u in src_repo.mirrors
                    if u.uri not in dest_repo.mirrors
                ]
                add_origins = [
                    u.uri
                    for u in src_repo.origins
                    if u.uri not in dest_repo.origins
                ]

                # Special bits to update; for these, take the
                # new value as-is (don't attempt to merge).
                for prop in ("collection_type", "description",
                    "legal_uris", "name", "refresh_seconds",
                    "registration_uri", "related_uris"):
                    src_val = getattr(src_repo, prop)
                    if src_val is not None:
                        setattr(dest_repo, prop,
                            src_val)

            # If an alias doesn't already exist, update it too.
            if src_pub.alias and not dest_pub.alias:
                dest_pub.alias = src_pub.alias

            ret_json = _set_pub_error_wrap(_add_update_pub, name,
                [], api_inst, prefix, pub=dest_pub,
                add_mirrors=add_mirrors, add_origins=add_origins,
                set_props=set_props,
                add_prop_values=add_prop_values,
                remove_prop_values=remove_prop_values,
                unset_props=unset_props, proxy_uri=proxy_uri)

            if ret_json["status"] == EXIT_OK:
                updated.append(prefix)

        if ret_json["status"] != EXIT_OK:
            for err in ret_json["errors"]:
                failed.append((prefix, err["reason"]))
            continue

    first = True
    for pub, rmsg in failed:
        if first:
            first = False
            _error_json("failed to add or update one or more "
                "publishers", cmd=op, errors_json=errors_json,
                 errorType="publisher_set")
        errors_json.append({"reason": "  {0}:\n{1}".format(pub, rmsg),
            "errtype": "publisher_set"})

    data = {}
    if added or updated:
        if first:
            data["header"] = "pkg set-publisher:"
        if added:
            data["added"] = added
        if updated:
            data["updated"] = updated

    if failed:
        if len(failed) != len(pubs):
            # Not all publishers retrieved could be added or
            # updated.
            return __prepare_json(EXIT_PARTIAL, data=data,
                errors=errors_json)
        return __prepare_json(EXIT_OOPS, data=data, errors=errors_json)

    # Now that the configuration was successful, attempt to refresh the
    # catalog data for all of the configured publishers.  If the refresh
    # had been allowed earlier while configuring each publisher, then this
    # wouldn't be necessary and some possibly invalid configuration could
    # have been eliminated sooner.  However, that would be much slower as
    # each refresh requires a client image state rebuild.
    ret_json = __refresh(api_inst, added + updated)
    ret_json["data"] = data
    return ret_json


def _publisher_unset(op, api_inst, pargs):
    """Function to unset publishers."""

    errors_json = []
    if not pargs:
        errors_json.append({"reason": _("at least one publisher must "
            "be specified")})
        return __prepare_json(EXIT_BADOPT, errors=errors_json, op=op)

    errors = []
    goal = len(pargs)
    progtrack = api_inst.progresstracker
    progtrack.job_start(progtrack.JOB_PKG_CACHE, goal=goal)
    for name in pargs:
        try:
            api_inst.remove_publisher(prefix=name, alias=name)
        except api_errors.ImageFormatUpdateNeeded as e:
            _format_update_error(e, errors_json)
            return __prepare_json(EXIT_OOPS, errors=errors_json)
        except (api_errors.PermissionsException,
            api_errors.PublisherError,
            api_errors.ModifyingSyspubException) as e:
            errors.append((name, e))
        finally:
            progtrack.job_add_progress(progtrack.JOB_PKG_CACHE)

    progtrack.job_done(progtrack.JOB_PKG_CACHE)
    retcode = EXIT_OK
    errors_json = []
    if errors:
        if len(errors) == len(pargs):
            # If the operation failed for every provided publisher
            # prefix or alias, complete failure occurred.
            retcode = EXIT_OOPS
        else:
            # If the operation failed for only some of the provided
            # publisher prefixes or aliases, then partial failure
            # occurred.
            retcode = EXIT_PARTIAL

        txt = ""
        for name, err in errors:
            txt += "\n"
            txt += _("Removal failed for '{pub}': {msg}").format(
                pub=name, msg=err)
            txt += "\n"
        _error_json(txt, cmd=op, errors_json=errors_json)

    return __prepare_json(retcode, errors=errors_json)


def _publisher_list(op, api_inst, pargs, omit_headers, preferred_only,
    inc_disabled, output_format):
    """pkg publishers. Note: publisher_a is a left-over parameter."""

    errors_json = []
    field_data = {
        "publisher" : [("default", "tsv"), _("PUBLISHER"), ""],
        "attrs" : [("default"), "", ""],
        "type" : [("default", "tsv"), _("TYPE"), ""],
        "status" : [("default", "tsv"), _("STATUS"), ""],
        "repo_loc" : [("default"), _("LOCATION"), ""],
        "uri": [("tsv"), _("URI"), ""],
        "sticky" : [("tsv"), _("STICKY"), ""],
        "enabled" : [("tsv"), _("ENABLED"), ""],
        "syspub" : [("tsv"), _("SYSPUB"), ""],
        "proxy"  : [("tsv"), _("PROXY"), ""],
        "proxied" : [("default"), _("P"), ""]
    }

    desired_field_order = (_("PUBLISHER"), "", _("STICKY"),
                           _("SYSPUB"), _("ENABLED"), _("TYPE"),
                           _("STATUS"), _("P"), _("LOCATION"))

    # Custom key function for preserving field ordering
    def key_fields(item):
        return desired_field_order.index(get_header(item))

    # Functions for manipulating field_data records
    def filter_default(record):
        return "default" in record[0]

    def filter_tsv(record):
        return "tsv" in record[0]

    def get_header(record):
        return record[1]

    def get_value(record):
        return record[2]

    def set_value(record, value):
        record[2] = value

    api_inst.progresstracker.set_purpose(
        api_inst.progresstracker.PURPOSE_LISTING)

    cert_cache = {}

    def get_cert_info(ssl_cert):
        if not ssl_cert:
            return None
        if ssl_cert not in cert_cache:
            c = cert_cache[ssl_cert] = {}
            errors = c["errors"] = []
            times = c["info"] = {
                "effective": "",
                "expiration": "",
            }

            try:
                cert = misc.validate_ssl_cert(ssl_cert)
            except (EnvironmentError,
                api_errors.CertificateError,
                api_errors.PermissionsException) as e:
                # If the cert information can't be retrieved,
                # add the errors to a list and continue on.
                errors.append(e)
                c["valid"] = False
            else:
                nb = cert.get_notBefore()
                # strptime's first argument must be str
                t = time.strptime(misc.force_str(nb),
                    "%Y%m%d%H%M%SZ")
                nb = datetime.datetime.utcfromtimestamp(
                    calendar.timegm(t))
                times["effective"] = nb.strftime("%c")

                na = cert.get_notAfter()
                t = time.strptime(misc.force_str(na),
                    "%Y%m%d%H%M%SZ")
                na = datetime.datetime.utcfromtimestamp(
                    calendar.timegm(t))
                times["expiration"] = na.strftime("%c")
                c["valid"] = True

        return cert_cache[ssl_cert]

    retcode = EXIT_OK
    data = {}
    if len(pargs) == 0:
        if preferred_only:
            pref_pub = api_inst.get_highest_ranked_publisher()
            if api_inst.has_publisher(pref_pub):
                pubs = [pref_pub]
            else:
                # Only publisher known is from an installed
                # package and is not configured in the image.
                pubs = []
        else:
            pubs = [
                p for p in api_inst.get_publishers()
                if inc_disabled or not p.disabled
            ]
        # Create a formatting string for the default output
        # format
        if output_format == "default":
            filter_func = filter_default

        # Create a formatting string for the tsv output
        # format
        if output_format == "tsv":
            filter_func = filter_tsv
            desired_field_order = (_("PUBLISHER"), "", _("STICKY"),
                   _("SYSPUB"), _("ENABLED"), _("TYPE"),
                   _("STATUS"), _("URI"), _("PROXY"))

        # Extract our list of headers from the field_data
        # dictionary Make sure they are extracted in the
        # desired order by using our custom key function.
        hdrs = list(map(get_header, sorted(filter(filter_func,
            list(field_data.values())), key=key_fields)))

        if not omit_headers:
            data["headers"] = hdrs
        data["publishers"] = []
        for p in pubs:
            # Store all our publisher related data in
            # field_data ready for output

            set_value(field_data["publisher"], p.prefix)
            # Setup the synthetic attrs field if the
            # format is default.
            if output_format == "default":
                pstatus = ""

                if not p.sticky:
                    pstatus_list = [_("non-sticky")]
                else:
                    pstatus_list = []

                if p.disabled:
                    pstatus_list.append(_("disabled"))
                if p.sys_pub:
                    pstatus_list.append(_("syspub"))
                if pstatus_list:
                    pstatus = "({0})".format(
                        ", ".join(pstatus_list))
                set_value(field_data["attrs"], pstatus)

            if p.sticky:
                set_value(field_data["sticky"], _("true"))
            else:
                set_value(field_data["sticky"], _("false"))
            if not p.disabled:
                set_value(field_data["enabled"], _("true"))
            else:
                set_value(field_data["enabled"], _("false"))
            if p.sys_pub:
                set_value(field_data["syspub"], _("true"))
            else:
                set_value(field_data["syspub"], _("false"))

            # Only show the selected repository's information in
            # summary view.
            if p.repository:
                origins = p.repository.origins
                mirrors = p.repository.mirrors
            else:
                origins = mirrors = []

            set_value(field_data["repo_loc"], "")
            set_value(field_data["proxied"], "")
            # Update field_data for each origin and output
            # a publisher record in our desired format.
            for uri in sorted(origins):
                # XXX get the real origin status
                set_value(field_data["type"], _("origin"))
                set_value(field_data["proxy"], "-")
                set_value(field_data["proxied"], "F")

                set_value(field_data["uri"], uri)
                if uri.disabled:
                    set_value(field_data["enabled"],
                        _("false"))
                    set_value(field_data["status"],
                        _("disabled"))
                else:
                    set_value(field_data["enabled"],
                        _("true"))
                    set_value(field_data["status"],
                        _("online"))

                if uri.proxies:
                    set_value(field_data["proxied"], _("T"))
                    set_value(field_data["proxy"],
                        ", ".join(
                        [proxy.uri
                        for proxy in uri.proxies]))
                if uri.system:
                    set_value(field_data["repo_loc"],
                        SYSREPO_HIDDEN_URI)
                else:
                    set_value(field_data["repo_loc"], uri)

                values = map(get_value,
                    sorted(filter(filter_func,
                    field_data.values()), key=key_fields)
                )
                entry = []
                for e in values:
                    if isinstance(e, str):
                        entry.append(e)
                    else:
                        entry.append(str(e))
                data["publishers"].append(entry)
            # Update field_data for each mirror and output
            # a publisher record in our desired format.
            for uri in mirrors:
                # XXX get the real mirror status
                set_value(field_data["type"], _("mirror"))
                # We do not currently deal with mirrors. So
                # they are always online.
                set_value(field_data["status"], _("online"))
                set_value(field_data["proxy"], "-")
                set_value(field_data["proxied"], _("F"))

                set_value(field_data["uri"], uri)

                if uri.proxies:
                    set_value(field_data["proxied"],
                        _("T"))
                    set_value(field_data["proxy"],
                        ", ".join(
                        [p.uri for p in uri.proxies]))
                if uri.system:
                    set_value(field_data["repo_loc"],
                        SYSREPO_HIDDEN_URI)
                else:
                    set_value(field_data["repo_loc"], uri)

                values = map(get_value,
                    sorted(filter(filter_func,
                    field_data.values()), key=key_fields)
                )
                entry = []
                for e in values:
                    if isinstance(e, str):
                        entry.append(e)
                    else:
                        entry.append(str(e))
                data["publishers"].append(entry)

            if not origins and not mirrors:
                set_value(field_data["type"], "")
                set_value(field_data["status"], "")
                set_value(field_data["uri"], "")
                set_value(field_data["proxy"], "")
                values = map(get_value,
                    sorted(filter(filter_func,
                    field_data.values()), key=key_fields)
                )
                entry = []
                for e in values:
                    if isinstance(e, str):
                        entry.append(e)
                    else:
                        entry.append(str(e))
                data["publishers"].append(entry)
    else:
        def collect_ssl_info(uri, uri_data):
            retcode = EXIT_OK
            c = get_cert_info(uri.ssl_cert)
            uri_data["SSL Key"] = str(uri.ssl_key)
            uri_data["SSL Cert"] = str(uri.ssl_cert)

            if not c:
                return retcode

            if c["errors"]:
                retcode = EXIT_OOPS

            for e in c["errors"]:
                errors_json.append({"reason":
                    "\n" + str(e) + "\n", "errtype": "cert_info"})

            if c["valid"]:
                uri_data["Cert. Effective Date"] = \
                    str(c["info"]["effective"])
                uri_data["Cert. Expiration Date"] = \
                    str(c["info"]["expiration"])
            return retcode

        def collect_repository(r, pub_data):
            retcode = 0
            origins_data = []
            for uri in r.origins:
                origin_data = {"Origin URI": str(uri)}
                if uri.disabled:
                    origin_data["Status"] = _("Disabled")
                else:
                    origin_data["Status"] = _("Online")
                if uri.proxies:
                    origin_data["Proxy"] = \
                        [str(p.uri) for p in uri.proxies]
                rval = collect_ssl_info(uri, origin_data)
                if rval == 1:
                    retcode = EXIT_PARTIAL
                origins_data.append(origin_data)

            mirrors_data = []
            for uri in r.mirrors:
                mirror_data = {"Mirror URI": str(uri)}
                mirror_data["Status"] = _("Online")
                if uri.proxies:
                    mirror_data["Proxy"] = \
                        [str(p.uri) for p in uri.proxies]
                rval = collect_ssl_info(uri, mirror_data)
                if rval == 1:
                    retcode = EXIT_PARTIAL
                mirrors_data.append(mirror_data)
            if origins_data:
                pub_data["origins"] = origins_data
            if mirrors_data:
                pub_data["mirrors"] = mirrors_data
            return retcode

        def collect_signing_certs(p, pub_data):
            if p.approved_ca_certs:
                pub_data["Approved CAs"] = [str(cert) for
                    cert in p.approved_ca_certs]
            if p.revoked_ca_certs:
                pub_data["Revoked CAs"] = [str(cert) for
                    cert in p.revoked_ca_certs]

        for name in pargs:
            # detailed print
            pub = api_inst.get_publisher(prefix=name, alias=name)
            dt = api_inst.get_publisher_last_update_time(pub.prefix)
            if dt:
                dt = dt.strftime("%c")

            pub_data = {}
            pub_data["Publisher"] = pub.prefix
            pub_data["Alias"] = pub.alias

            rval = collect_repository(pub.repository, pub_data)
            if rval != 0:
                # There was an error in displaying some
                # of the information about a repository.
                # However, continue on.
                retcode = rval

            pub_data["Client UUID"] = pub.client_uuid
            pub_data["Catalog Updated"] = dt
            collect_signing_certs(pub, pub_data)
            if pub.disabled:
                pub_data["enabled"] = "No"
            else:
                pub_data["enabled"] = "Yes"
            if pub.sticky:
                pub_data["sticky"] = "Yes"
            else:
                pub_data["sticky"] = "No"
            if pub.sys_pub:
                pub_data["sys_pub"] = "Yes"
            else:
                pub_data["sys_pub"] = "No"
            if pub.properties:
                pub_data["Properties"] = {}
                for k, v in pub.properties.items():
                    pub_data["Properties"][k] = v
            data.setdefault("publisher_details", []).append(
                pub_data)
    return __prepare_json(retcode, data=data, errors=errors_json, op=op)


def _info(op, api_inst, pargs, display_license, info_local, info_remote,
    origins, quiet):
    """Display information about a package or packages.
    """

    errors_json = []
    data = {}
    if info_remote and not pargs:
        error = {"reason": _("must request remote info for specific "
            "packages")}
        errors_json.append(error)
        return __prepare_json(EXIT_BADOPT, errors=errors_json, op=op)

    err = EXIT_OK
    # Reset the progress tracker here, because we may have to switch to a
    # different tracker due to the options parse.
    api_inst.progresstracker = _get_tracker()

    api_inst.progresstracker.set_purpose(
        api_inst.progresstracker.PURPOSE_LISTING)

    info_needed = api.PackageInfo.ALL_OPTIONS
    if not display_license:
        info_needed = api.PackageInfo.ALL_OPTIONS - \
            frozenset([api.PackageInfo.LICENSES])
    info_needed -= api.PackageInfo.ACTION_OPTIONS
    info_needed |= frozenset([api.PackageInfo.DEPENDENCIES])

    try:
        ret = api_inst.info(pargs, info_local, info_needed,
            ranked=info_remote, repos=origins)
    except api_errors.ImageFormatUpdateNeeded as e:
        _format_update_error(e, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.NoPackagesInstalledException:
        _error_json(_("no packages installed"), errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.ApiException as e:
        _error_json(e, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    pis = ret[api.ImageInterface.INFO_FOUND]
    notfound = ret[api.ImageInterface.INFO_MISSING]
    illegals = ret[api.ImageInterface.INFO_ILLEGALS]

    if illegals:
        # No other results will be returned if illegal patterns were
        # specified.
        for i in illegals:
            errors_json.append({"reason": str(i)})
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    no_licenses = []
    for i, pi in enumerate(pis):
        if display_license:
            if not pi.licenses:
                no_licenses.append(pi.fmri)
            elif not quiet:
                lics = []
                for lic in pi.licenses:
                    lics.append(str(lic))
                data.setdefault("licenses", []).append(
                    [pi.pkg_stem, lics])
            continue

        if quiet:
            continue

        state = ""
        if api.PackageInfo.INSTALLED in pi.states:
            state = _("Installed")
        elif api.PackageInfo.UNSUPPORTED in pi.states:
            state = _("Unsupported")
        else:
            state = _("Not installed")

        lparen = False
        if api.PackageInfo.OBSOLETE in pi.states:
            state += " ({0}".format(_("Obsolete"))
            lparen = True
        elif api.PackageInfo.RENAMED in pi.states:
            state += " ({0}".format(_("Renamed"))
            lparen = True
        elif api.PackageInfo.LEGACY in pi.states:
            state += " ({0}".format(_("Legacy"))
            lparen = True
        if api.PackageInfo.FROZEN in pi.states:
            if lparen:
                state += ", {0})".format(_("Frozen"))
            else:
                state += " ({0})".format(_("Frozen"))
        elif lparen:
            state += ")"

        attr_list = []
        seen = {}

        def __append_attr_lists(label, values):
            """Given arguments label and values, either extend
            the existing list value or add new one to
            attr_list"""

            if not isinstance(values, list):
                values = [values]
            if label in seen:
                seen[label].extend(values)
            else:
                attr_list.append([label, values])
                seen[label] = values

        __append_attr_lists(_("Name"), pi.pkg_stem)
        __append_attr_lists(_("Summary"), pi.summary)
        if pi.description:
            __append_attr_lists(_("Description"), pi.description)
        if pi.category_info_list:
            category_info = []
            verbose = len(pi.category_info_list) > 1
            category_info.append \
                (pi.category_info_list[0].__str__(verbose))
            if len(pi.category_info_list) > 1:
                for ci in pi.category_info_list[1:]:
                    category_info.append \
                        (ci.__str__(verbose))
            __append_attr_lists(_("Category"), category_info)

        __append_attr_lists(_("State"), state)

        # Renamed packages have dependencies, but the dependencies
        # may not apply to this image's variants so won't be
        # returned.
        if api.PackageInfo.RENAMED in pi.states:
            __append_attr_lists(_("Renamed to"), pi.dependencies)

        # XXX even more info on the publisher would be nice?
        __append_attr_lists(_("Publisher"), pi.publisher)
        hum_ver = pi.get_attr_values("pkg.human-version")
        if hum_ver and hum_ver[0] != str(pi.version):
            __append_attr_lists(_("Version"), "{0} ({1})".format(
                pi.version, hum_ver[0]))
        else:
            __append_attr_lists(_("Version"), str(pi.version))

        __append_attr_lists(_("Branch"), str(pi.branch))
        __append_attr_lists(_("Packaging Date"), pi.packaging_date)
        if pi.last_install:
            __append_attr_lists(_("Last Install Time"),
                pi.last_install)
        if pi.last_update:
            __append_attr_lists(_("Last Update Time"),
                pi.last_update)
        __append_attr_lists(_("Size"), misc.bytes_to_str(pi.size))
        __append_attr_lists(_("FMRI"),
            pi.fmri.get_fmri(include_build=False))
        # XXX add license/copyright info here?

        addl_attr_list = {
            "info.keyword": _("Additional Keywords"),
            "info.upstream": _("Project Contact"),
            "info.maintainer": _("Project Maintainer"),
            "info.maintainer-url": _("Project Maintainer URL"),
            "pkg.detailed-url": _("Project URL"),
            "info.upstream-url": _("Project URL"),
            "info.repository-changeset": _("Repository Changeset"),
            "info.repository-url": _("Source URL"),
            "info.source-url": _("Source URL")
        }

        for key in addl_attr_list:
            if key in pi.attrs:
                __append_attr_lists(addl_attr_list[key],
                    pi.get_attr_values(key))

        if "package_attrs" not in data:
            data["package_attrs"] = [attr_list]
        else:
            data["package_attrs"].append(attr_list)

    if notfound:
        err_txt = ""
        if pis:
            err = EXIT_PARTIAL
            if not quiet:
                err_txt += "\n"
        else:
            err = EXIT_OOPS
        if not quiet:
            if info_local:
                err_txt += _("""\
pkg: info: no packages matching the following patterns you specified are
installed on the system.  Try querying remotely instead:\n""")
            elif info_remote:
                err_txt += _("""\
pkg: info: no packages matching the following patterns you specified were
found in the catalog.  Try relaxing the patterns, refreshing, and/or
examining the catalogs:\n""")
            err_txt += "\n"
            for p in notfound:
                err_txt += "        {0}".format(p)
            errors_json.append({"reason": err_txt,
                "errtype": "info_not_found"})

    if no_licenses:
        err_txt = ""
        if len(no_licenses) == len(pis):
            err = EXIT_OOPS
        else:
            err = EXIT_PARTIAL

        if not quiet:
            err_txt += _("no license information could be found "
                "for the following packages:\n")
            for pfmri in no_licenses:
                err_txt += "\t{0}\n".format(pfmri)
            _error_json(err_txt, errors_json=errors_json,
                errorType="info_no_licenses")

    return __prepare_json(err, errors=errors_json, data=data)


def _verify(op, api_inst, pargs, omit_headers, parsable_version, quiet, verbose,
    unpackaged, unpackaged_only, verify_paths, display_plan_cb=None, logger=None):
    """Determine if installed packages match manifests."""

    errors_json = []
    if pargs and unpackaged_only:
        error = {"reason": _("can not report only unpackaged contents "
            "with package arguments.")}
        errors_json.append(error)
        return __prepare_json(EXIT_BADOPT, errors=errors_json)

    return __api_op(op, api_inst, args=pargs, _noexecute=True,
        _omit_headers=omit_headers, _quiet=quiet, _quiet_plan=True,
        _verbose=verbose, _parsable_version=parsable_version,
        _unpackaged=unpackaged, _unpackaged_only=unpackaged_only,
        _verify_paths=verify_paths, display_plan_cb=display_plan_cb,
        logger=logger)


def _fix(op, api_inst, pargs, accept, backup_be, backup_be_name, be_activate,
    be_name, new_be, noexecute, omit_headers, parsable_version, quiet,
    show_licenses, verbose, unpackaged, display_plan_cb=None, logger=None):
    """Fix packaging errors found in the image."""

    return __api_op(op, api_inst, args=pargs, _accept=accept,
        _noexecute=noexecute, _omit_headers=omit_headers, _quiet=quiet,
        _show_licenses=show_licenses, _verbose=verbose, backup_be=backup_be,
        backup_be_name=backup_be_name, be_activate=be_activate,
        be_name=be_name, new_be=new_be, _parsable_version=parsable_version,
        _unpackaged=unpackaged, display_plan_cb=display_plan_cb,
        logger=logger)


def __refresh(api_inst, pubs, full_refresh=False):
    """Private helper method for refreshing publisher data."""

    errors_json = []
    try:
        # The user explicitly requested this refresh, so set the
        # refresh to occur immediately.
        api_inst.refresh(full_refresh=full_refresh,
            immediate=True, pubs=pubs)
    except api_errors.ImageFormatUpdateNeeded as e:
        _format_update_error(e, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.PublisherError as e:
        _error_json(e, errors_json=errors_json)
        _error_json(_("'pkg publisher' will show a list of publishers."
            ), errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except (api_errors.UnknownErrors, api_errors.PermissionsException) as e:
        # Prepend a newline because otherwise the exception will
        # be printed on the same line as the spinner.
        _error_json("\n" + str(e), errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.CatalogRefreshException as e:
        if _collect_catalog_failures(e, errors=errors_json) == 0:
            return __prepare_json(EXIT_OOPS, errors=errors_json)
        return __prepare_json(EXIT_PARTIAL, errors=errors_json)
    return __prepare_json(EXIT_OK)


def _get_ssl_cert_key(root, is_zone, ssl_cert, ssl_key):
    if ssl_cert is not None or ssl_key is not None:
        # In the case of zones, the ssl cert given is assumed to
        # be relative to the root of the image, not truly absolute.
        orig_cwd = _get_orig_cwd()
        if is_zone:
            if ssl_cert is not None:
                ssl_cert = os.path.abspath(
                    root + os.sep + ssl_cert)
            if ssl_key is not None:
                ssl_key = os.path.abspath(
                    root + os.sep + ssl_key)
        elif orig_cwd:
            if ssl_cert and not os.path.isabs(ssl_cert):
                ssl_cert = os.path.normpath(os.path.join(
                    orig_cwd, ssl_cert))
            if ssl_key and not os.path.isabs(ssl_key):
                ssl_key = os.path.normpath(os.path.join(
                    orig_cwd, ssl_key))
    return ssl_cert, ssl_key


def _set_pub_error_wrap(func, pfx, raise_errors, *args, **kwargs):
    """Helper function to wrap set-publisher private methods.  Returns
    a tuple of (return value, message).  Callers should check the return
    value for errors."""

    errors_json = []
    try:
        return func(*args, **kwargs)
    except api_errors.CatalogRefreshException as e:
        for entry in raise_errors:
            if isinstance(e, entry):
                raise
        succeeded = _collect_catalog_failures(e,
            ignore_perms_failure=True, errors=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)

    except api_errors.InvalidDepotResponseException as e:
        for entry in raise_errors:
            if isinstance(e, entry):
                raise
        if pfx:
            errors_json.append({"reason": _("The origin URIs for "
                "'{pubname}' do not appear to point to a valid "
                "pkg repository.\nPlease verify the repository's "
                "location and the client's network configuration."
                "\nAdditional details:\n\n{details}").format(
                pubname=pfx, details=str(e))})
            return __prepare_json(EXIT_OOPS, errors=errors_json)
        errors_json.append({"reason": _("The specified URI does "
            "not appear to point to a valid pkg repository.\nPlease "
            "check the URI and the client's network configuration."
            "\nAdditional details:\n\n{0}").format(str(e))})
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.ImageFormatUpdateNeeded as e:
        for entry in raise_errors:
            if isinstance(e, entry):
                raise
        _format_update_error(e, errors_json=errors_json)
        return __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.ApiException as e:
        for entry in raise_errors:
            if isinstance(e, entry):
                raise
        # Prepend a newline because otherwise the exception will
        # be printed on the same line as the spinner.
        errors_json.append({"reason": ("\n" + str(e))})
        return __prepare_json(EXIT_OOPS, errors=errors_json)


def _add_update_pub(api_inst, prefix, pub=None, disable=None, sticky=None,
    origin_uri=None, add_mirrors=EmptyI, remove_mirrors=EmptyI,
    add_origins=EmptyI, remove_origins=EmptyI, enable_origins=EmptyI,
    disable_origins=EmptyI, ssl_cert=None, ssl_key=None,
    search_before=None, search_after=None, search_first=False,
    reset_uuid=None, refresh_allowed=False,
    set_props=EmptyI, add_prop_values=EmptyI,
    remove_prop_values=EmptyI, unset_props=EmptyI, approved_cas=EmptyI,
    revoked_cas=EmptyI, unset_cas=EmptyI, proxy_uri=None):

    repo = None
    new_pub = False
    errors_json = []
    if not pub:
        try:
            pub = api_inst.get_publisher(prefix=prefix,
                alias=prefix, duplicate=True)
            if reset_uuid:
                pub.reset_client_uuid()
            repo = pub.repository
        except api_errors.UnknownPublisher as e:
            if not origin_uri and not add_origins and \
                (remove_origins or remove_mirrors or
                remove_prop_values or add_mirrors or
                enable_origins or disable_origins):
                errors_json.append({"reason": str(e)})
                return __prepare_json(EXIT_OOPS,
                    errors=errors_json)

            # No pre-existing, so create a new one.
            repo = publisher.Repository()
            pub = publisher.Publisher(prefix, repository=repo)
            new_pub = True
    elif not api_inst.has_publisher(prefix=pub.prefix):
        new_pub = True

    if not repo:
        repo = pub.repository
        if not repo:
            # Could be a new publisher from auto-configuration
            # case where no origin was provided in repository
            # configuration.
            repo = publisher.Repository()
            pub.repository = repo

    if sticky is not None:
        # Set stickiness only if provided
        pub.sticky = sticky

    if proxy_uri:
        # we only support a single proxy for now.
        proxies = [publisher.ProxyURI(proxy_uri)]
    else:
        proxies = []

    if origin_uri:
        # For compatibility with old -O behaviour, treat -O as a wipe
        # of existing origins and add the new one.

        origin_uri = misc.parse_uri(origin_uri, cwd=_get_orig_cwd())

        # Only use existing cert information if the new URI uses
        # https for transport.
        if repo.origins and not (ssl_cert or ssl_key) and \
            any(origin_uri.startswith(scheme + ":")
                for scheme in publisher.SSL_SCHEMES):

            for uri in repo.origins:
                if ssl_cert is None:
                    ssl_cert = uri.ssl_cert
                if ssl_key is None:
                    ssl_key = uri.ssl_key
                break

        repo.reset_origins()
        o = publisher.RepositoryURI(origin_uri, proxies=proxies)
        repo.add_origin(o)

        # XXX once image configuration supports storing this
        # information at the uri level, ssl info should be set
        # here.

    for entry in (("mirror", add_mirrors, remove_mirrors), ("origin",
        add_origins, remove_origins)):
        etype, add, remove = entry
        # XXX once image configuration supports storing this
        # information at the uri level, ssl info should be set
        # here.
        if "*" in remove:
            getattr(repo, "reset_{0}s".format(etype))()
        else:
            for u in remove:
                getattr(repo, "remove_{0}".format(etype))(u)

        for u in add:
            uri = publisher.RepositoryURI(u, proxies=proxies)
            try:
                getattr(repo, "add_{0}".format(etype)
                    )(uri)
            except (api_errors.DuplicateSyspubOrigin,
                api_errors.DuplicateRepositoryOrigin):
                # If this exception occurs, we know the
                # origin already exists. Then if it is
                # combined with --enable or --disable,
                # we turn it into an update task for the
                # origin. Otherwise, raise the exception
                # again.
                if not (disable_origins or enable_origins):
                    raise

    if disable is not None:
        # Set disabled property only if provided.
        # If "*" in enable or disable origins list or disable without
        # enable or disable origins specified, then it is a publisher
        # level disable.
        if not (enable_origins or disable_origins):
            pub.disabled = disable
        else:
            if disable_origins:
                if "*" in disable_origins:
                    for o in repo.origins:
                        o.disabled = True
                else:
                    for diso in disable_origins:
                        ori = repo.get_origin(diso)
                        ori.disabled = True
            if enable_origins:
                if "*" in enable_origins:
                    for o in repo.origins:
                        o.disabled = False
                else:
                    for eno in enable_origins:
                        ori = repo.get_origin(eno)
                        ori.disabled = False

    # None is checked for here so that a client can unset a ssl_cert or
    # ssl_key by using -k "" or -c "".
    if ssl_cert is not None or ssl_key is not None:
        # Assume the user wanted to update the ssl_cert or ssl_key
        # information for *all* of the currently selected
        # repository's origins and mirrors that use SSL schemes.
        found_ssl = False
        for uri in repo.origins:
            if uri.scheme not in publisher.SSL_SCHEMES:
                continue
            found_ssl = True
            if ssl_cert is not None:
                uri.ssl_cert = ssl_cert
            if ssl_key is not None:
                uri.ssl_key = ssl_key
        for uri in repo.mirrors:
            if uri.scheme not in publisher.SSL_SCHEMES:
                continue
            found_ssl = True
            if ssl_cert is not None:
                uri.ssl_cert = ssl_cert
            if ssl_key is not None:
                uri.ssl_key = ssl_key

        if (ssl_cert or ssl_key) and not found_ssl:
            # None of the origins or mirrors for the publisher
            # use SSL schemes so the cert and key information
            # won't be retained.
            errors_json.append({"reason": _("Publisher '{0}' does "
                "not have any SSL-based origins or mirrors."
                ).format(prefix)})
            return __prepare_json(EXIT_BADOPT, errors=errors_json)

    if set_props or add_prop_values or remove_prop_values or unset_props:
        pub.update_props(set_props=set_props,
            add_prop_values=add_prop_values,
            remove_prop_values=remove_prop_values,
            unset_props=unset_props)

    if new_pub:
        api_inst.add_publisher(pub,
            refresh_allowed=refresh_allowed, approved_cas=approved_cas,
            revoked_cas=revoked_cas, unset_cas=unset_cas,
            search_after=search_after, search_before=search_before,
            search_first=search_first)
    else:
        for ca in approved_cas:
            try:
                ca = os.path.normpath(
                    os.path.join(_get_orig_cwd(), ca))
                with open(ca, "rb") as fh:
                    s = fh.read()
            except EnvironmentError as e:
                if e.errno == errno.ENOENT:
                    raise api_errors.MissingFileArgumentException(
                        ca)
                elif e.errno == errno.EACCES:
                    raise api_errors.PermissionsException(
                        ca)
                raise
            pub.approve_ca_cert(s)

        for hsh in revoked_cas:
            pub.revoke_ca_cert(hsh)

        for hsh in unset_cas:
            pub.unset_ca_cert(hsh)

        api_inst.update_publisher(pub,
            refresh_allowed=refresh_allowed, search_after=search_after,
            search_before=search_before, search_first=search_first)

    return __prepare_json(EXIT_OK)


def _get_orig_cwd():
    """Get the original current working directory."""
    try:
        orig_cwd = os.getcwd()
    except OSError as e:
        try:
            orig_cwd = os.environ["PWD"]
            if not orig_cwd or orig_cwd[0] != "/":
                orig_cwd = None
        except KeyError:
            orig_cwd = None
    return orig_cwd


def __pkg(subcommand, pargs_json, opts_json, pkg_image=None,
    prog_delay=PROG_DELAY, prog_tracker=None, opts_mapping=misc.EmptyDict,
    api_inst=None):
    """Private function to invoke pkg subcommands."""

    errors_json = []
    if subcommand is None:
        err = {"reason": "Sub-command cannot be none type."}
        errors_json.append(err)
        return None, __prepare_json(EXIT_OOPS, errors=errors_json)
    if subcommand not in cmds:
        err = {"reason": "Unknown sub-command: {0}.".format(
            subcommand)}
        errors_json.append(err)
        return None, __prepare_json(EXIT_OOPS, errors=errors_json)

    arg_name = "pargs_json"
    try:
        if pargs_json is None:
            pargs = []
        # Pargs_json is already a list, use it.
        elif isinstance(pargs_json, list):
            pargs = pargs_json
        else:
            pargs = json.loads(pargs_json)
        if not isinstance(pargs, list):
            if not isinstance(pargs, str):
                err = {"reason": "{0} is invalid.".format(
                    arg_name)}
                errors_json.append(err)
                return None, __prepare_json(EXIT_OOPS,
                    errors=errors_json)
            misc.force_str(pargs)
            pargs = [pargs]
        else:
            for idx in range(len(pargs)):
                misc.force_str(pargs[idx])
    except Exception as e:
        err = {"reason": "{0} is invalid.".format(
            arg_name)}
        errors_json.append(err)
        return None, __prepare_json(EXIT_OOPS, errors=errors_json)

    try:
        if opts_json is None:
            opts = {}
        # If opts_json is already a dict, use it.
        elif isinstance(opts_json, dict):
            opts = opts_json
        else:
            opts = json.loads(opts_json, object_hook=_strify)
        if not isinstance(opts, dict):
            err = {"reason": "opts_json is invalid."}
            errors_json.append(err)
            return None, __prepare_json(EXIT_OOPS,
                errors=errors_json)
    except:
        err = {"reason": "opts_json is invalid."}
        errors_json.append(err)
        return None, __prepare_json(EXIT_OOPS, errors=errors_json)

    try:
        # Validate JSON input with JSON schema.
        input_schema = _get_pkg_input_schema(subcommand,
            opts_mapping=opts_mapping)
        jsonschema.validate({arg_name: pargs, "opts_json": opts},
            input_schema)
    except jsonschema.ValidationError as e:
        return None, __prepare_json(EXIT_BADOPT,
            errors=[{"reason": str(e)}])

    orig_cwd = _get_orig_cwd()

    # Get ImageInterface and image object.
    if not api_inst:
        api_inst = __api_alloc(pkg_image, orig_cwd,
            prog_delay=prog_delay, prog_tracker=prog_tracker,
            errors_json=errors_json)
    if api_inst is None:
        return None, __prepare_json(EXIT_OOPS, errors=errors_json)

    func = cmds[subcommand][0]
    # Get the available options for the requested operation to create the
    # getopt parsing strings.
    valid_opts = options.get_pkg_opts(subcommand, add_table=cmd_opts)
    pargs_limit = None
    if len(cmds[subcommand]) > 2:
        pargs_limit = cmds[subcommand][2]

    if not valid_opts:
        # if there are no options for an op, it has its own processing.
        try:
            if subcommand in ["unset-publisher"]:
                return api_inst, func(subcommand, api_inst, pargs,
                    **opts)
            else:
                return api_inst, func(api_inst, pargs, **opts)
        except getopt.GetoptError as e:
            err = {"reason": str(e)}
            return api_inst, __prepare_json(EXIT_OOPS, errors=err)
    try:
        opt_dict = misc.opts_parse(subcommand, [],
            valid_opts, opts_mapping, use_cli_opts=False, **opts)
        if pargs_limit is not None and len(pargs) > pargs_limit:
            err = {"reason": _("illegal argument -- {0}").format(
                pargs[pargs_limit])}
            return api_inst, __prepare_json(EXIT_OOPS, errors=err)
        opts = options.opts_assemble(subcommand, api_inst, opt_dict,
                add_table=cmd_opts, cwd=orig_cwd)
    except api_errors.InvalidOptionError as e:
        # We can't use the string representation of the exception since
        # it references internal option names. We substitute the RAD
        # options and create a new exception to make sure the messages
        # are correct.

        # Convert the internal options to RAD options. We make sure that
        # when there is a short and a long version for the same option
        # we print both to avoid confusion.
        def get_cli_opt(option):
            try:
                option_name = None
                if option in opts_mapping:
                    option_name = opts_mapping[option]

                if option_name:
                    return option_name
                else:
                    return option
            except KeyError:
                # ignore if we can't find a match
                # (happens for repeated arguments or invalid
                # arguments)
                return option
            except TypeError:
                # ignore if we can't find a match
                # (happens for an invalid arguments list)
                return option
        cli_opts = []
        opt_def = []

        for o in e.options:
            cli_opts.append(get_cli_opt(o))

            # collect the default value (see comment below)
            opt_def.append(options.get_pkg_opts_defaults(subcommand,
                o, add_table=cmd_opts))

        # Prepare for headache:
        # If we have an option 'b' which is set to True by default it
        # will be toggled to False if the users specifies the according
        # option on the CLI.
        # If we now have an option 'a' which requires option 'b' to be
        # set, we can't say "'a' requires 'b'" because the user can only
        # specify 'not b'. So the correct message would be:
        # "'a' is incompatible with 'not b'".
        # We can get there by just changing the type of the exception
        # for all cases where the default value of one of the options is
        # True.
        if e.err_type == api_errors.InvalidOptionError.REQUIRED:
            if len(opt_def) == 2 and (opt_def[0] or opt_def[1]):
                e.err_type = \
                    api_errors.InvalidOptionError.INCOMPAT

        # This new exception will have the CLI options, so can be passed
        # directly to usage().
        new_e = api_errors.InvalidOptionError(err_type=e.err_type,
            options=cli_opts, msg=e.msg)
        err = {"reason": str(new_e)}
        return api_inst, __prepare_json(EXIT_BADOPT, errors=err)
    return api_inst, func(op=subcommand, api_inst=api_inst,
        pargs=pargs, **opts)


def __handle_errors_json(func, non_wrap_print=True, subcommand=None,
    pargs_json=None, opts_json=None, pkg_image=None,
    prog_delay=PROG_DELAY, prog_tracker=None, opts_mapping=misc.EmptyDict,
    api_inst=None, reset_api=False):
    """Error handling for pkg subcommands."""

    traceback_str = misc.get_traceback_message()
    errors_json = []

    _api_inst = None
    try:
        # Out of memory errors can be raised as EnvironmentErrors with
        # an errno of ENOMEM, so in order to handle those exceptions
        # with other errnos, we nest this try block and have the outer
        # one handle the other instances.
        try:
            if non_wrap_print:
                _api_inst, ret_json = func(subcommand, pargs_json,
                    opts_json, pkg_image=pkg_image,
                    prog_delay=prog_delay,
                    prog_tracker=prog_tracker,
                    opts_mapping=opts_mapping,
                    api_inst=api_inst)
            else:
                func()
        except (MemoryError, EnvironmentError) as __e:
            if isinstance(__e, EnvironmentError) and \
                __e.errno != errno.ENOMEM:
                raise
            if _api_inst:
                _api_inst.abort(
                    result=RESULT_FAILED_OUTOFMEMORY)
            _error_json(misc.out_of_memory(),
                errors_json=errors_json)
            ret_json = __prepare_json(EXIT_OOPS,
                errors=errors_json)
    except SystemExit as __e:
        if _api_inst:
            _api_inst.abort(result=RESULT_FAILED_UNKNOWN)
        raise __e
    except (PipeError, KeyboardInterrupt):
        if _api_inst:
            _api_inst.abort(result=RESULT_CANCELED)
        # We don't want to display any messages here to prevent
        # possible further broken pipe (EPIPE) errors.
        ret_json = __prepare_json(EXIT_OOPS)
    except api_errors.LinkedImageException as __e:
        _error_json(_("Linked image exception(s):\n{0}").format(
              str(__e)), errors_json=errors_json)
        ret_json = __prepare_json(__e.lix_exitrv, errors=errors_json)
    except api_errors.CertificateError as __e:
        if _api_inst:
            _api_inst.abort(result=RESULT_FAILED_CONFIGURATION)
        _error_json(__e, errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.PublisherError as __e:
        if _api_inst:
            _api_inst.abort(result=RESULT_FAILED_BAD_REQUEST)
        _error_json(__e, errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.ImageLockedError as __e:
        if _api_inst:
            _api_inst.abort(result=RESULT_FAILED_LOCKED)
        _error_json(__e, errors_json=errors_json)
        ret_json = __prepare_json(EXIT_LOCKED, errors=errors_json)
    except api_errors.TransportError as __e:
        if _api_inst:
            _api_inst.abort(result=RESULT_FAILED_TRANSPORT)

        errors_json.append({"reason": _("Errors were encountered "
            "while attempting to retrieve package or file data "
            "for the requested operation.")})
        errors_json.append({"reason": _("Details follow:\n\n{0}"
            ).format(__e)})
        _collect_proxy_config_errors(errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.InvalidCatalogFile as __e:
        if _api_inst:
            _api_inst.abort(result=RESULT_FAILED_STORAGE)
        errors_json.append({"reason": _("An error was encountered "
            "while attempting to read image state information to "
            "perform the requested operation. Details follow:\n\n{0}"
            ).format(__e)})
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.InvalidDepotResponseException as __e:
        if _api_inst:
            _api_inst.abort(result=RESULT_FAILED_TRANSPORT)
        errors_json.append({"reason": _("\nUnable to contact a valid "
            "package repository. This may be due to a problem with "
            "the repository, network misconfiguration, or an "
            "incorrect pkg client configuration.  Please verify the "
            "client's network configuration and repository's location."
            "\nAdditional details:\n\n{0}").format(__e)})
        _collect_proxy_config_errors(errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.HistoryLoadException as __e:
        # Since a history related error occurred, discard all
        # information about the current operation(s) in progress.
        if _api_inst:
            _api_inst.clear_history()
        _error_json(_("An error was encountered while attempting to "
            "load history information\nabout past client operations."),
            errors_json=errors_json)
        _error_json(__e, errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.HistoryStoreException as __e:
        # Since a history related error occurred, discard all
        # information about the current operation(s) in progress.
        if _api_inst:
            _api_inst.clear_history()
        _error_json({"reason": _("An error was encountered while "
            "attempting to store information about the\ncurrent "
            "operation in client history. Details follow:\n\n{0}"
            ).format(__e)}, errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.HistoryPurgeException as __e:
        # Since a history related error occurred, discard all
        # information about the current operation(s) in progress.
        if _api_inst:
            _api_inst.clear_history()
        errors_json.append({"reason": _("An error was encountered "
            "while attempting to purge client history. "
            "Details follow:\n\n{0}").format(__e)})
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.VersionException as __e:
        if _api_inst:
            _api_inst.abort(result=RESULT_FAILED_UNKNOWN)
        _error_json(_("The pkg command appears out of sync with the "
            "libraries provided\nby pkg:/package/pkg. The client "
            "version is {client} while the library\nAPI version is "
            "{api}.").format(client=__e.received_version,
            api=__e.expected_version), errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.WrapSuccessfulIndexingException as __e:
        ret_json = __prepare_json(EXIT_OK)
    except api_errors.WrapIndexingException as __e:
        def _wrapper():
            raise __e.wrapped
        __, ret_json = __handle_errors_json(_wrapper, non_wrap_print=False)

        s = ""
        if ret_json["status"] == 99:
            s += _("\n{err}{stacktrace}").format(
            err=__e, stacktrace=traceback_str)

        s += _("\n\nDespite the error while indexing, the operation "
            "has completed successfuly.")
        _error_json(s, errors_json=errors_json)
        if "errors" in ret_json:
            ret_json["errors"].extend(errors_json)
        else:
            ret_json["errors"] = errors_json
    except api_errors.ReadOnlyFileSystemException as __e:
        _error_json("The file system is read only.",
            errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.UnexpectedLinkError as __e:
        _error_json(str(__e), errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.UnrecognizedCatalogPart as __e:
        _error_json(str(__e), errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except api_errors.InvalidConfigFile as __e:
        _error_json(str(__e), errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except (api_errors.PkgUnicodeDecodeError, UnicodeEncodeError) as __e:
        _error_json(str(__e), errors_json=errors_json)
        ret_json = __prepare_json(EXIT_OOPS, errors=errors_json)
    except:
        if _api_inst:
            _api_inst.abort(result=RESULT_FAILED_UNKNOWN)
        if non_wrap_print:
            traceback.print_exc()
            _error_json(traceback.format_exc()+"\n"+traceback_str,
                errors_json=errors_json)
        ret_json = __prepare_json(99, errors=errors_json)

    if reset_api:
        try:
            if _api_inst:
                _api_inst.reset()
        except:
            # If any errors occur during reset, we will discard
            # this api_inst.
            _api_inst = None

    return _api_inst, ret_json


def _pkg_invoke(subcommand=None, pargs_json=None, opts_json=None, pkg_image=None,
    prog_delay=PROG_DELAY, prog_tracker=None, opts_mapping=misc.EmptyDict,
    api_inst=None, reset_api=False, return_api=False):
    """pkg subcommands invocation. Output will be in JSON format.
    subcommand: a string type pkg subcommand.

    pargs_json: a JSON blob containing a list of pargs.

    opts_json: a JSON blob containing a dictionary of pkg
    subcommand options.

    pkg_image: a string type alternate image path.

    prog_delay: long progress event delay in sec.

    prog_tracker: progress tracker object.

    alternate_pargs_name: by default, 'pargs_json' will be the name in
        input JSON schema. This option allows consumer to change the
        pargs_json into an alternate name.
    """

    _api_inst, ret_json = __handle_errors_json(__pkg,
        subcommand=subcommand, pargs_json=pargs_json,
        opts_json=opts_json, pkg_image=pkg_image,
        prog_delay=prog_delay, prog_tracker=prog_tracker,
        opts_mapping=opts_mapping, api_inst=api_inst, reset_api=reset_api)
    if return_api:
        return _api_inst, ret_json
    else:
        return ret_json


class ClientInterface(object):
    """Class to provide a general interface to various clients."""

    def __init__(self, pkg_image=None, prog_delay=PROG_DELAY,
        prog_tracker=None, opts_mapping=misc.EmptyDict):
        self.api_inst = None
        self.pkg_image = pkg_image
        self.prog_delay = prog_delay
        self.prog_tracker = prog_tracker
        self.opts_mapping = opts_mapping

    def __cmd_invoke(self, cmd, pargs_json=None, opts_json=None):
        """Helper function for command invocation."""

        # We will always reset api instance on exception.
        _api_inst, ret_json = _pkg_invoke(cmd, pargs_json=pargs_json,
            opts_json=opts_json, pkg_image=self.pkg_image,
            prog_delay=self.prog_delay, prog_tracker=self.prog_tracker,
            opts_mapping=self.opts_mapping, api_inst=self.api_inst,
            reset_api=True, return_api=True)
        self.api_inst = _api_inst
        return ret_json

    def list_inventory(self, pargs_json=None, opts_json=None):
        """Invoke pkg list subcommand."""

        return self.__cmd_invoke("list", pargs_json=pargs_json,
            opts_json=opts_json)

    def info(self, pargs_json=None, opts_json=None):
        """Invoke pkg info subcommand."""

        return self.__cmd_invoke("info", pargs_json=pargs_json,
            opts_json=opts_json)

    def exact_install(self, pargs_json=None, opts_json=None):
        """Invoke pkg exact-install subcommand."""

        return self.__cmd_invoke("exact-install",
            pargs_json=pargs_json, opts_json=opts_json)

    def install(self, pargs_json=None, opts_json=None):
        """Invoke pkg install subcommand."""

        return self.__cmd_invoke("install", pargs_json=pargs_json,
            opts_json=opts_json)

    def update(self, pargs_json=None, opts_json=None):
        """Invoke pkg update subcommand."""

        return self.__cmd_invoke("update", pargs_json=pargs_json,
            opts_json=opts_json)

    def uninstall(self, pargs_json=None, opts_json=None):
        """Invoke pkg uninstall subcommand."""

        return self.__cmd_invoke("uninstall", pargs_json=pargs_json,
            opts_json=opts_json)

    def publisher_set(self, pargs_json=None, opts_json=None):
        """Invoke pkg set-publisher subcommand."""

        return self.__cmd_invoke("set-publisher",
            pargs_json=pargs_json, opts_json=opts_json)

    def publisher_unset(self, pargs_json=None):
        """Invoke pkg unset-publisher subcommand."""

        return self.__cmd_invoke("unset-publisher",
            pargs_json=pargs_json)

    def publisher_list(self, pargs_json=None, opts_json=None):
        """Invoke pkg publisher subcommand."""

        return self._cmd_invoke("publisher", pargs_json=pargs_json,
            opts_json=opts_json)

    def verify(self, pargs_json=None, opts_json=None):
        """Invoke pkg verify subcommand."""

        return self._cmd_invoke("verify", pargs_json=pargs_json,
            opts_json=opts_json)

    def fix(self, pargs_json=None, opts_json=None):
        """Invoke pkg fix subcommand."""

        return self._cmd_invoke("fix", pargs_json=pargs_json,
            opts_json=opts_json)

    def get_pkg_input_schema(self, subcommand):
        """Get input schema for a specific subcommand."""

        return _get_pkg_input_schema(subcommand,
            opts_mapping=self.opts_mapping)

    def get_pkg_output_schema(self, subcommand):
        """Get output schema for a specific subcommand."""

        return _get_pkg_output_schema(subcommand)


cmds = {
    "exact-install"   : [_exact_install, __pkg_exact_install_output_schema],
    "fix"             : [_fix, __pkg_fix_output_schema],
    "list"            : [_list_inventory, __pkg_list_output_schema],
    "install"         : [_install, __pkg_install_output_schema],
    "update"          : [_update, __pkg_update_output_schema],
    "uninstall"       : [_uninstall, __pkg_uninstall_output_schema],
    "set-publisher"   : [_publisher_set,
                          __pkg_publisher_set_output_schema],
    "unset-publisher" : [_publisher_unset,
                          __pkg_publisher_unset_output_schema],
    "publisher"       : [_publisher_list, __pkg_publisher_output_schema],
    "info"            : [_info, __pkg_info_output_schema],
    "verify"          : [_verify, __pkg_verify_output_schema]
}

# Addendum table for option extensions.
cmd_opts = {}
