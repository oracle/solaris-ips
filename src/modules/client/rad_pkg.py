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
# Copyright (c) 2015, 2016, Oracle and/or its affiliates. All rights reserved.
#

import os
import six
import simplejson as json
import subprocess
import traceback
import pkg
import pkg.fmri as fmri
import pkg.client.client_api as entry
import pkg.client.pkgdefs as pkgdefs
import pkg.client.progress as progress

# progress delay.
PROG_DELAY   = 5.0

# Error codes.
SUCCEED = pkgdefs.EXIT_OK
ERROR = pkgdefs.EXIT_OOPS
INVALIDOPTION = pkgdefs.EXIT_BADOPT
PARTIALSUCCEED = pkgdefs.EXIT_PARTIAL
NO_OP = pkgdefs.EXIT_NOP
ACTUATOR_TIMEOUT = pkgdefs.EXIT_ACTUATOR
UNANTICIPATED = 99

valid_modes = ["native", "fork"]


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
                        ret_json = {"status": UNANTICIPATED, "errors": [{"reason":
                            str(ex)}]}
                return ret_json

def is_image(img_root):
        img_prefixes = ["var/pkg", ".org.opensolaris,pkg"]

        def is_image_helper(sub_d):
                # First check for new image configuration file.
                if os.path.isfile(os.path.join(sub_d, "pkg5.image")):
                        # Regardless of directory structure, assume
                        # this is an image for now.
                        return True

                if not os.path.isfile(os.path.join(sub_d, "cfg_cache")):
                        # For older formats, if configuration is
                        # missing, this can't be an image.
                        return False

                # Configuration exists, but for older formats,
                # all of these directories have to exist.
                for n in ("state", "pkg"):
                        if not os.path.isdir(os.path.join(sub_d, n)):
                                return False

                return True

        for imp in img_prefixes:
                sub_dir = os.path.join(img_root, imp)
                if os.path.isdir(sub_dir) and is_image_helper(sub_dir):
                        return True

        return False


class PkgException(Exception):
        """Exception throwed by pkg related functions."""

        def __init__(self, err_code, err_message):
                self.err_code = err_code
                self.err_message = err_message

        def __str__(self):
                return self.err_message


def set_any(attr):
        """General setter generation function."""

        def delegate_set(self, val):
                setattr(self, attr, val)
        return delegate_set

def get_any(attr):
        """General getter generation function."""

        def delegate_get(self):
                return getattr(self, attr)
        return delegate_get

def eliminateNoneOpts(**opts):
        """Eliminate all None value options, since RAD client will always
        pass the full list of arguments no matter it is None or not."""

        new_dict = {}
        for k, v in opts.items():
                if v is not None:
                        new_dict[k] = v
        return new_dict


class PkgPublisher(object):

        def __init__(self):
                self._prefix = None
                self._alias = None
                self._client_UUID = None
                self._cat_updated_time = None
                self._enabled = None
                self._sticky = None
                self._syspub = None
                self._mirrors = []
                self._origins = []
                self._properties = []
                self._approved_CAs = []
                self._revoked_CAs = []

        prefix = property(get_any("_prefix"), set_any("_prefix"))
        alias = property(get_any("_alias"), set_any("_alias"))
        client_UUID = property(get_any("_client_UUID"),
            set_any("_client_UUID"))
        cat_updated_time = property(get_any("_cat_updated_time"),
            set_any("_cat_updated_time"))
        enabled = property(get_any("_enabled"), set_any("_enabled"))
        sticky = property(get_any("_sticky"), set_any("_sticky"))
        syspub = property(get_any("_syspub"), set_any("_syspub"))
        mirrors = property(get_any("_mirrors"), set_any("_mirrors"))
        origins = property(get_any("_origins"), set_any("_origins"))
        properties = property(get_any("_properties"), set_any("_properties"))
        approved_CAs = property(get_any("_approved_CAs"),
            set_any("_approved_CAs"))
        revoked_CAs = property(get_any("_revoked_CAs"),
            set_any("_revoked_CAs"))


class PkgSource(object):

        def __init__(self):
                self._URI = None
                self._type = None
                self._status = None
                self._proxies = []
                self._cert_effective_date = None
                self._cert_expiration_date = None
                self._SSL_key = None
                self._SSL_cert = None

        URI = property(get_any("_URI"), set_any("_URI"))
        type = property(get_any("_type"), set_any("_type"))
        status = property(get_any("_status"), set_any("_status"))
        proxies = property(get_any("_proxies"), set_any("_proxies"))
        cert_effective_date = property(get_any("_cert_effective_date"),
            set_any("_cert_effective_date"))
        cert_expiration_date = property(get_any("_cert_expiration_date"),
            set_any("_cert_expiration_date"))
        SSL_key = property(get_any("_SSL_key"), set_any("_SSL_key"))
        SSL_cert = property(get_any("_SSL_cert"), set_any("_SSL_cert"))


class PkgFmri(object):

        def __init__(self):
                self.__fmri = None

        def fmri_initialize(self, fmri_str):
                self.__fmri = fmri.PkgFmri(fmri_str)

        def get_name(self):
                if self.__fmri:
                        return self.__fmri.get_name()

        def get_publisher(self):
                if self.__fmri:
                        return self.__fmri.get_publisher_str()

        def get_pkg_stem(self, no_publisher=None, include_scheme=None):
                opts = eliminateNoneOpts(anarchy=no_publisher,
                    include_scheme=include_scheme)
                if self.__fmri:
                        return self.__fmri.get_pkg_stem(**opts)

        def get_fmri(self, default_publisher=None, no_publisher=None,
            include_scheme=None, include_build=None, include_timestamp=None):
                opts = eliminateNoneOpts(default_publisher=default_publisher,
                    anarchy=no_publisher, include_scheme=include_scheme,
                    include_build=include_build)
                if self.__fmri:
                        fmri_str = self.__fmri.get_fmri(**opts)
                        if include_timestamp == False:
                                rind = fmri_str.rfind(":")
                                if rind != -1:
                                        fmri_str = fmri_str[:rind]
                        return fmri_str

        def get_version(self):
                if self.__fmri:
                        return self.__fmri.get_version()

        def get_timestamp(self):
                if self.__fmri:
                        return self.__fmri.get_timestamp().isoformat()


class PkgInfo(object):

        def __init__(self):
                self._pkg_name = None
                self._summary = None
                self._description = None
                self._category = None
                self._state = None
                self._renamedto = None
                self._publisher = None
                self._last_update_time = None
                self._last_install_time = None
                self._size = None
                self._fmri = None
                self._licenses = []

        pkg_name = property(get_any("_pkg_name"), set_any("_pkg_name"))
        summary = property(get_any("_summary"), set_any("_summary"))
        description = property(get_any("_description"),
            set_any("_description"))
        category = property(get_any("_category"), set_any("_category"))
        state = property(get_any("_state"), set_any("_state"))
        renamed_to = property(get_any("_renamedto"), set_any("_renamedto"))
        publisher = property(get_any("_publisher"), set_any("_publisher"))
        last_install_time = property(get_any("_last_install_time"),
            set_any("_last_install_time"))
        last_update_time = property(get_any("_last_update_time"),
            set_any("_last_update_time"))
        size = property(get_any("_size"), set_any("_size"))
        fmri = property(get_any("_fmri"), set_any("_fmri"))
        licenses = property(get_any("_licenses"), set_any("_licenses"))


class PkgImage(object):

        def __init__(self):
                self.__image_path = None
                self.__mode = "native"
                self.__progress_interval = 5.0
                self._prog_event_handler = None

        def __get_mode(self):
                return self.__mode

        def __set_mode(self, val):
                if val is not None and not isinstance(val, six.string_types):
                        raise PkgException(ERROR, "Wrong value type")
                if val is None:
                        val = "native"
                if val not in valid_modes:
                        raise PkgException(ERROR, "Invalid mode. Please use: "
                            "{0}".format(", ".join(valid_modes)))
                self.__mode = val

        def __get_interval(self):
                return self.__progress_interval

        def __set_interval(self, val):
                if not isinstance(val, (six.integer_types, float)):
                        raise PkgException(ERROR, "Wrong value type")
                self.__progress_interval = val

        image_path = property(get_any("_PkgImage__image_path"),
            set_any("_PkgImage__image_path"))
        mode = property(__get_mode, __set_mode)
        progress_interval = property(__get_interval, __set_interval)

        def __fork_pkg_cmd(self, subcommand, pargs_json=None, opts_json=None):
                try:
                        args = ["/usr/share/lib/pkg/rad-invoke"]
                        # If not JSON formatted string, need conversion.
                        if pargs_json and not isinstance(pargs_json,
                            six.string_types):
                                pargs_json = json.dumps(pargs_json)
                        if opts_json and not isinstance(opts_json,
                            six.string_types):
                                opts_json = json.dumps(opts_json)
                        if self.__image_path:
                                args.extend(["-R", self.__image_path])
                        if pargs_json:
                                args.extend(["--pargs", pargs_json])
                        if opts_json:
                                args.extend(["--opts", opts_json])
                        args.extend(["--prog-delay",
                            str(self.__progress_interval)])

                        args.append(subcommand)

                        p = subprocess.Popen(args, env=os.environ,
                            stdout=subprocess.PIPE)
                        actualret = None
                        # Process output JSON lines.
                        while True:
                                out_line = p.stdout.readline()
                                if out_line == b'' and p.poll() is not None:
                                        break
                                if out_line:
                                        out_json = json.loads(out_line)
                                        # This indicates it is progress output.
                                        if "phase" in out_json:
                                                self._prog_event_handler(
                                                    out_json)
                                        # This indicates it is the actual
                                        # return.
                                        elif "status" in out_json:
                                                actualret = out_json
                        if not actualret:
                                return {"status": ERROR, "errors": [{"reason":
                                    "no result collected in fork mode."}]}
                        return actualret
                except Exception as ex:
                        return {"status": ERROR, "errors": [{"reason": str(ex)}
                            ]}

        def __pkg(self, subcommand, pargs_json=None, opts_json=None,
            mode=None):
                """Perform pkg operation.

                subcommand: a string type pkg subcommand.

                pargs_json: a JSON blob containing a list of pargs.

                opts_json: a JSON blob containing a dictionary of pkg
                subcommand options.
                """

                ret_json = None
                fork_exec = False

                if mode:
                        if mode not in valid_modes:
                                ret_json = {"status": ERROR, "errors":
                                    [{"reason": "Invalid mode. Please use: "
                                    "{0}".format(", ".join(valid_modes))}]}
                                return ret_json
                        if mode == "fork":
                                fork_exec = True
                elif self.__mode == "fork":
                        fork_exec = True

                if fork_exec:
                        return self.__fork_pkg_cmd(subcommand,
                            pargs_json=pargs_json, opts_json=opts_json)

                try:
                        ret_json = rad_pkg(subcommand=subcommand,
                            pargs_json=pargs_json, opts_json=opts_json,
                            pkg_image=self.__image_path,
                            prog_event_handler=self._prog_event_handler,
                            prog_delay=self.__progress_interval)
                        return ret_json
                except Exception as ex:
                        return {"status": UNANTICIPATED, "errors": [{"reason":
                            traceback.format_exc()}]}

        def __handle_error(self, out_json):
                try:
                        if isinstance(out_json, six.string_types):
                                out_json = json.loads(out_json)
                except Exception as ex:
                        out_json = {"status": ERROR, "errors": [{"reason":
                            "invalid JSON output: {0}".format(out_json)}]}

                if out_json["status"] not in [SUCCEED, NO_OP,
                    ACTUATOR_TIMEOUT]:
                        err_code = out_json["status"]
                        err_message = ""
                        if "errors" in out_json:
                                errs = []
                                for e in out_json["errors"]:
                                        if "reason" in e:
                                                errs.append(e["reason"])
                                        elif "info" in e:
                                                errs.append(e["info"])
                                err_message = "{0}".format("\n".join(errs))
                        raise PkgException(err_code, err_message)

                return out_json

        def __convert_opts2json(self, **opts):
                json_dict = {}
                for k, v in opts.items():
                        if v is not None:
                                json_dict[k] = v
                return json_dict

        def list_packages(self, pkg_fmri_patterns=None, refresh_catalogs=None,
            origins=None, list_installed_newest=None, list_all=None,
            list_newest=None, list_upgradable=None, mode=None):
                # Convert options into JSON. There is also a chance here to
                # change the name of an option here. Basically the options can
                # also be passed as **kwargs here, but listing them all here
                # provides clues of which options are used in RAD.
                opts_json = self.__convert_opts2json(
                    refresh_catalogs=refresh_catalogs,
                    origins=origins,
                    list_installed_newest=list_installed_newest,
                    list_all=list_all, list_newest=list_newest,
                    list_upgradable=list_upgradable)
                ret_json = self.__pkg("list", pargs_json=pkg_fmri_patterns,
                    opts_json=opts_json, mode=mode)
                return self.__handle_error(ret_json)

        def exact_install(self, pkg_fmri_patterns=None, backup_be_name=None,
            be_name=None, deny_new_be=None, no_backup_be=None,
            be_activate=None, require_backup_be=None, require_new_be=None,
            concurrency=None, accept=None, show_licenses=None,
            reject_pats=None, update_index=None, refresh_catalogs=None,
            noexecute=None, parsable_version=None, origins=None,
            mode=None):
                opts_json = self.__convert_opts2json(
                    backup_be_name=backup_be_name,
                    be_name=be_name, deny_new_be=deny_new_be,
                    no_backup_be=no_backup_be,
                    be_activate=be_activate,
                    require_backup_be=require_backup_be,
                    require_new_be=require_new_be,
                    concurrency=concurrency, accept=accept,
                    show_licenses=show_licenses,
                    reject_pats=reject_pats, update_index=update_index,
                    refresh_catalogs=refresh_catalogs,
                    noexecute=noexecute, parsable_version=parsable_version,
                    origins=origins)
                ret_json = self.__pkg("exact-install",
                    pargs_json=pkg_fmri_patterns, opts_json=opts_json,
                    mode=mode)
                return self.__handle_error(ret_json)

        def install(self, pkg_fmri_patterns=None, backup_be_name=None,
            be_name=None, deny_new_be=None, no_backup_be=None,
            be_activate=None, require_backup_be=None, require_new_be=None,
            concurrency=None, accept=None, show_licenses=None,
            reject_pats=None, update_index=None, refresh_catalogs=None,
            noexecute=None, parsable_version=None, origins=None,
            li_erecurse_all=None, li_erecurse_list=None,
            li_erecurse_excl=None, sync_act=None, act_timeout=None,
            mode=None):
                opts_json = self.__convert_opts2json(
                    backup_be_name=backup_be_name,
                    be_name=be_name, deny_new_be=deny_new_be,
                    no_backup_be=no_backup_be,
                    be_activate=be_activate,
                    require_backup_be=require_backup_be,
                    require_new_be=require_new_be,
                    concurrency=concurrency, accept=accept,
                    show_licenses=show_licenses,
                    reject_pats=reject_pats, update_index=update_index,
                    refresh_catalogs=refresh_catalogs,
                    noexecute=noexecute, parsable_version=parsable_version,
                    origins=origins, li_erecurse_all=li_erecurse_all,
                    li_erecurse_list=li_erecurse_list,
                    li_erecurse_excl=li_erecurse_excl, sync_act=sync_act,
                    act_timeout=act_timeout)
                ret_json = self.__pkg("install", pargs_json=pkg_fmri_patterns,
                    opts_json=opts_json, mode=mode)
                return self.__handle_error(ret_json)

        def update(self, pkg_fmri_patterns=None, backup_be_name=None,
            be_name=None, deny_new_be=None, no_backup_be=None,
            be_activate=None, require_backup_be=None, require_new_be=None,
            concurrency=None, accept=None, show_licenses=None,
            reject_pats=None, update_index=None, refresh_catalogs=None,
            noexecute=None, parsable_version=None, origins=None,
            li_erecurse_all=None, li_erecurse_list=None,
            li_erecurse_excl=None, sync_act=None, act_timeout=None,
            ignore_missing=None, force=None, mode=None):
                opts_json = self.__convert_opts2json(
                    backup_be_name=backup_be_name,
                    be_name=be_name, deny_new_be=deny_new_be,
                    no_backup_be=no_backup_be,
                    be_activate=be_activate,
                    require_backup_be=require_backup_be,
                    require_new_be=require_new_be,
                    concurrency=concurrency, accept=accept,
                    show_licenses=show_licenses,
                    reject_pats=reject_pats, update_index=update_index,
                    refresh_catalogs=refresh_catalogs,
                    noexecute=noexecute, parsable_version=parsable_version,
                    origins=origins, li_erecurse_all=li_erecurse_all,
                    li_erecurse_list=li_erecurse_list,
                    li_erecurse_excl=li_erecurse_excl, sync_act=sync_act,
                    act_timeout=act_timeout, ignore_missing=ignore_missing,
                    force=force)
                ret_json = self.__pkg("update", pargs_json=pkg_fmri_patterns,
                    opts_json=opts_json, mode=mode)
                return self.__handle_error(ret_json)

        def uninstall(self, pkg_fmri_patterns=None, backup_be_name=None,
            be_name=None, deny_new_be=None, no_backup_be=None,
            be_activate=None, require_backup_be=None, require_new_be=None,
            concurrency=None, update_index=None, refresh_catalogs=None,
            noexecute=None, parsable_version=None, li_erecurse_all=None,
            li_erecurse_list=None, li_erecurse_excl=None, sync_act=None,
            act_timeout=None, ignore_missing=None, mode=None):
                opts_json = self.__convert_opts2json(
                    backup_be_name=backup_be_name,
                    be_name=be_name, deny_new_be=deny_new_be,
                    no_backup_be=no_backup_be,
                    be_activate=be_activate,
                    require_backup_be=require_backup_be,
                    require_new_be=require_new_be,
                    concurrency=concurrency, update_index=update_index,
                    refresh_catalogs=refresh_catalogs,
                    noexecute=noexecute, parsable_version=parsable_version,
                    li_erecurse_all=li_erecurse_all,
                    li_erecurse_list=li_erecurse_list,
                    li_erecurse_excl=li_erecurse_excl, sync_act=sync_act,
                    act_timeout=act_timeout, ignore_missing=ignore_missing)
                ret_json = self.__pkg("uninstall",
                    pargs_json=pkg_fmri_patterns,
                    opts_json=opts_json, mode=mode)
                return self.__handle_error(ret_json)

        def info(self, pkg_fmri_patterns=None, license_only=None,
            info_local=None, info_remote=None, origins=None, mode=None):
                opts_json = self.__convert_opts2json(
                    display_license=license_only, info_local=info_local,
                    Info_remote=info_remote, origins=origins)
                ret_json = self.__pkg("info", pargs_json=pkg_fmri_patterns,
                    opts_json=opts_json, mode=mode)
                return self.__handle_error(ret_json)

        def publisher(self, publishers=None, preferred_only=False,
            include_disabled=True, mode=None):
                opts_json = self.__convert_opts2json(
                    preferred_only=preferred_only,
                    inc_disabled=include_disabled)
                ret_json = self.__pkg("publisher", pargs_json=publishers,
                    opts_json=opts_json, mode=mode)
                # if not in single publisher mode.
                if not publishers and "data" in ret_json and "publishers" in \
                    ret_json["data"]:
                        all_pubs = [dr[0] for dr in
                            ret_json["data"]["publishers"]]
                        ret_json = self.__pkg("publisher", pargs_json=all_pubs,
                            opts_json={}, mode=mode)

                return self.__handle_error(ret_json)

        def set_publisher(self, publishers=None, ssl_key=None, ssl_cert=None,
            approved_ca_certs=None, revoked_ca_certs=None,
            unset_ca_certs=None, origin_uri=None, reset_uuid=None,
            add_mirrors=None, remove_mirrors=None, add_origins=None,
            remove_origins=None, refresh_allowed=None, disable=None,
            sticky=None, repo_uri=None, proxy_uri=None, set_props=None,
            add_prop_values=None, remove_prop_values=None, unset_props=None,
            search_before=None, search_after=None, search_first=None,
            mode=None):
                opts_json = self.__convert_opts2json(ssl_key=ssl_key,
                    ssl_cert=ssl_cert, approved_ca_certs=approved_ca_certs,
                    revoked_ca_certs=revoked_ca_certs,
                    unset_ca_certs=unset_ca_certs, origin_uri=origin_uri,
                    reset_uuid=reset_uuid, add_mirrors=add_mirrors,
                    remove_mirrors=remove_mirrors, add_origins=add_origins,
                    remove_origins=remove_origins,
                    refresh_allowed=refresh_allowed, disable=disable,
                    sticky=sticky, repo_uri=repo_uri, proxy_uri=proxy_uri,
                    set_props=set_props, add_prop_values=add_prop_values,
                    remove_prop_values=remove_prop_values,
                    unset_props=unset_props,
                    search_before=search_before, search_after=search_after,
                    search_first=search_first)
                ret_json = self.__pkg("set-publisher", pargs_json=publishers,
                    opts_json=opts_json, mode=mode)
                return self.__handle_error(ret_json)

        def unset_publisher(self, publishers=None, mode=None):
                ret_json = self.__pkg("unset-publisher", pargs_json=publishers,
                    opts_json=None, mode=mode)
                return self.__handle_error(ret_json)

#
# Mapping of the internal option name to an alternate name that user provided
# via keyword argument.
#
# {option_name: alternate_name}
#
#
opts_mapping = {}
