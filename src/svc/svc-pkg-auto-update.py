#!/usr/bin/python3.11 -uEs
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at LICENSE.txt
# or https://oss.oracle.com/licenses/.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at LICENSE.txt.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#
#
# Copyright (c) 2019, 2026, Oracle and/or its affiliates.
#

import os
import subprocess
import time
import pkg.no_site_packages  # pylint: disable=unused-import
from pkg import smf
from pkg.client import pkgdefs
import bemgmt
import smf_include
import rapidjson as json


def update_pkg():
    """ Attempt an update of pkg(7) """
    print('Attempting update of pkg', flush=True)
    cmd = ['/usr/bin/pkg', 'update', '--deny-new-be', 'package/pkg']
    return subprocess.call(cmd)


def start():
    """ SMF Start/Periodic Method to update system """

    myfmri = os.getenv('SMF_FMRI')
    parsable_output = '/system/volatile/' + myfmri + '/parsable_output.json'

    # First clear out any prior degraded state.  This ensures that if this
    # run needs to degrade the service its reason is shown by 'svcs -x' not
    # that of a prior degraded state.
    if 'degraded' in smf.get_prop(myfmri, 'restarter/state'):
        smf.clear(myfmri)

    auto_reboot = smf.get_prop(myfmri, 'config/auto-reboot') == 'true'
    if auto_reboot:
        try:
            reboot_hook = smf.get_prop(myfmri, 'config/reboot-check-hook')
            if reboot_hook and not os.access(reboot_hook, os.X_OK):
                print(f'{reboot_hook} not executable')
                reboot_hook = False
        except smf.NonzeroExitException:
            reboot_hook = False

    try:
        postupdate_hook = smf.get_prop(myfmri, 'config/postupdate-hook')
        if postupdate_hook and not os.access(postupdate_hook, os.X_OK):
            print(f'{postupdate_hook} not executable')
            postupdate_hook = False
    except smf.NonzeroExitException:
        postupdate_hook = False

    cmd = ['/usr/bin/pkg']
    try:
        if pkg_image := smf.get_prop(myfmri, 'config/pkg_image'):
            cmd.extend(['-R', pkg_image])
            if auto_reboot and pkg_image != '/':
                print('Auto reboot ignored when operating on non-active ' +
                      f'image: {pkg_image}')
                auto_reboot = False
    except smf.NonzeroExitException:
        pass

    try:
        packages = smf.get_prop(myfmri, 'config/packages')
    except smf.NonzeroExitException:
        packages = []
    else:
        # Split on any whitespace, ignoring any leading/trailing/repeated
        # sequences of whitespace
        packages = packages.split()

    # If we have a list of packages use 'pkg install' so that this can be
    # used to change the installed set.  If packages is empty then perform
    # an unconstrained update.
    if packages:
        cmd.extend(['install'])
    else:
        cmd.extend(['update'])

    try:
        if smf.get_prop(myfmri, 'config/require-new-be') == 'true':
            cmd.append('--require-new-be')
    except smf.NonzeroExitException:
        pass

    try:
        backup_be = smf.get_prop(myfmri, 'config/backup-be')
        if backup_be == 'true':
            cmd.append('--require-backup-be')
        else:
            cmd.append('--no-backup-be')
    except smf.NonzeroExitException:
        pass

    if smf.get_prop(myfmri, 'config/activate-new-be') == 'false':
        if auto_reboot:
            message = 'Invalid configuration: config/auto-reboot = true ' + \
                'with config/activate-new-be = false'
            smf_include.smf_method_exit(smf_include.SMF_EXIT_ERR_CONFIG,
                                        'invalid-configuration', message)
        cmd.append('--no-be-activate')

    # Add any extra args that should be passed to pkg, eg for verbose output
    # for zones related arguments.
    try:
        extra_args = smf.get_prop(myfmri, 'config/pkg_extra_args')
    except smf.NonzeroExitException:
        extra_args = []
    else:
        # Split on any whitespace, ignoring any leading/trailing/repeated
        # sequences of whitespace
        extra_args = extra_args.split()

    if extra_args:
        # Make sure we don't add any duplicate arguments
        repeatable = ["-Z", "-z", "--reject"]
        cmd.extend(a for a in extra_args if a not in cmd or a in repeatable)

    # Finally add the list of packages. This is a no-op if the list is empty.
    cmd.extend(packages)

    # Attempt the update 3 times, in case the image is locked,
    # backing off longer each time.
    for wait_secs in [60, 120, 300]:
        print('Running:', ' '.join(cmd), flush=True)
        pkg_status = subprocess.call(cmd)
        if pkg_status == pkgdefs.EXIT_PKG_OOD:
            # Attempt update of pkg(7) and retry
            pkg_status = update_pkg()
            if pkg_status == pkgdefs.EXIT_OK:
                print('Retrying:', ' '.join(cmd), flush=True)
                pkg_status = subprocess.call(cmd)
        if pkg_status != pkgdefs.EXIT_LOCKED:
            break
        print(f'Image locked, sleeping for {wait_secs} seconds', flush=True)
        time.sleep(wait_secs)

    bename = None
    new_be_created = False
    new_be_activated = False
    try:
        with open(parsable_output) as pkg_out:
            pkgplan = json.loads(pkg_out.read())

        new_be_created = pkgplan['create-new-be']
        new_be_activated = pkgplan['activate-be']
        bename = pkgplan['be-name']
    except FileNotFoundError:
        pass

    # Avoid passing None as a BE name to the hook commands
    if not bename:
        bename = ""

    # The postupdate_hook doesn't contribute to the service state and
    # if configured it is always run regardless pkg success or fail.
    if postupdate_hook:
        hook_cmd = f"{postupdate_hook} {pkg_image} {pkg_status} {bename}"
        print(f'Running postupdate-hook {hook_cmd}', flush=True)
        exitcode, output = subprocess.getstatusoutput(hook_cmd)
        print(output, flush=True)

    if pkg_status == pkgdefs.EXIT_NOP:
        return smf_include.SMF_EXIT_OK

    if pkg_status == pkgdefs.EXIT_PKG_OOD:
        message = 'pkg(7) appears to be out of date, and should be updated.'
        smf_include.smf_method_exit(smf_include.SMF_EXIT_DEGRADED,
                                    'constrained', message)
    elif pkg_status == pkgdefs.EXIT_CONSTRAINED:
        message = 'Updates available but no solution found'
        smf_include.smf_method_exit(smf_include.SMF_EXIT_DEGRADED,
                                    'constrained', message)
    elif pkg_status == pkgdefs.EXIT_LICENSE:
        message = 'License acceptance required'
        smf_include.smf_method_exit(smf_include.SMF_EXIT_DEGRADED,
                                    'license', message)
    elif pkg_status == pkgdefs.EXIT_LOCKED:
        # Even though we have retried don't go into maintenance for a
        # locked image issue, just let the next period deal with this.
        # Mark the service as degraded so the admin is made aware.
        message = 'Image remained locked after retries'
        smf_include.smf_method_exit(smf_include.SMF_EXIT_DEGRADED,
                                    'image-locked', message)
    elif pkg_status != pkgdefs.EXIT_OK:
        message = 'Update failed, see service log for details'
        smf_include.smf_method_exit(smf_include.SMF_EXIT_DEGRADED,
                                    'update-failed', message)

    if new_be_created and new_be_activated and auto_reboot:
        if reboot_hook:
            hook_cmd = f"{reboot_hook} {bename}"
            print(f'Running reboot-check-hook {hook_cmd}', flush=True)
            exitcode, output = subprocess.getstatusoutput(hook_cmd)
            if exitcode != 0:
                print(output)
                print(f'Reboot Hook failed {exitcode}, removing {bename}')
                # Remove the BE as a future auto-update may create the same BE.
                # Leaving it risks it becoming stale and surprising the
                # admin on a manual reboot.
                try:
                    bemgmt.BEManager().destroy(bename)
                except bemgmt.be_errors.BeMgmtError as e:
                    print(f'BE destroy failed: {e}', flush=True)

                message = f'Reboot Hook failed {exitcode}, see service log'
                smf_include.smf_method_exit(smf_include.SMF_EXIT_DEGRADED,
                                            'reboot-check-hook-failed',
                                            message)

        print('Reboot after auto update', flush=True)
        msg = myfmri + ' : automatic reboot after update'
        try:
            grace_period = smf.get_prop(myfmri, 'config/shutdown-grace-period')
        except smf.NonzeroExitException:
            grace_period = 60
        subprocess.call(['/usr/sbin/shutdown', '-yrg', grace_period, msg])
    elif not new_be_created:
        print('Auto update completed, no reboot needed', flush=True)

    return smf_include.SMF_EXIT_OK


smf_include.smf_main()
