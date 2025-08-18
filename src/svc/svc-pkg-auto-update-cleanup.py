#!/usr/bin/python3.11 -uEs
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
# Copyright (c) 2019, 2025, Oracle and/or its affiliates.
#

import pkg.no_site_packages
import pkg.smf as smf
import subprocess
import smf_include
import os


def start():
    keep = int(smf.get_prop(os.getenv('SMF_FMRI'), 'config/keep'))
    candidates = []
    # beadm list sorts by the first field so include created date
    cmd = ['/usr/sbin/beadm', 'list', '-Ho', 'created,policy,fmri']
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as beadm_out:
        for be in beadm_out.stdout.readlines():
            creation, policy, be_fmri = be.decode().strip().split(';')
            if 'auto' in policy.split(','):
                candidates.append(be_fmri)

    if len(candidates) - keep > 0:
        remove_bes = candidates[:len(candidates) - keep]
        print('Removing the following boot environments:', *remove_bes)
        for be in remove_bes:
            subprocess.call(['/usr/sbin/beadm', 'destroy', '-fF', be])


smf_include.smf_main()
