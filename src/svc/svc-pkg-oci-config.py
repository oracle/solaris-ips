#!/usr/bin/python3.11 -Es
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
# Copyright (c) 2024, 2025, Oracle and/or its affiliates.
#

''' Contact the OCI metadata service and store the ocids for
    the original image, tenancy and instance in the [oci] section.
'''

import gettext
import locale
import requests
import smf_include
import pkg.client.imageconfig
import pkg.config as pkgcfg
import pkg.misc

HEADERS = {'Authorization': 'Bearer Oracle'}
MDURL = 'http://169.254.169.254/opc/v2/instance/'
CLIENT_VERSION = 83


def write_config(metadata):
    ''' Write out or clear the ocids '''
    imgcfg = pkg.client.imageconfig.ImageConfig('/var/pkg/pkg5.image', '/')
    for prop in ['id', 'image', 'tenantId']:
        if metadata and metadata[prop]:
            imgcfg.set_property('oci', prop, metadata[prop])
        else:
            try:
                imgcfg.remove_property('oci', prop)
            except (pkgcfg.UnknownPropertyError, pkgcfg.UnknownSectionError):
                pass
    imgcfg.write()


def start():
    ''' Cache OCIDs from metadata service into image props '''

    try:
        mdret = requests.get(MDURL, headers=HEADERS, timeout=10)
    except Exception as reason:
        metadata = None
    else:
        metadata = mdret.json()
    write_config(metadata)

    return smf_include.SMF_EXIT_OK


def stop():
    ''' Remove any cached OCI ocids '''

    write_config(None)

    return smf_include.SMF_EXIT_OK


smf_include.smf_main()
