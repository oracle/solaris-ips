#!/usr/bin/python3.11 -Es
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
# Copyright (c) 2024, 2026, Oracle and/or its affiliates.
#

''' Contact the OCI metadata service and store the ocids for
    the original image, tenancy and instance in the [oci] section.
'''

import os
import requests
import smf_include
from pkg import smf
import pkg.client.imageconfig
import pkg.client.image
import pkg.config as pkgcfg
import pkg.misc

HEADERS = {'Authorization': 'Bearer Oracle'}
MDURL = 'http://169.254.169.254/opc/v2/instance/'
CLIENT_VERSION = 83


def write_config(pkg_image, metadata):
    ''' Write out or clear the ocids '''
    if pkg_image == '/':
        cfgdir = os.path.join(pkg_image, pkg.client.image.img_root_prefix)
    else:
        cfgdir = os.path.join(pkg_image, pkg.client.image.img_user_prefix)
    cfgfile = os.path.join(cfgdir, "pkg5.image")

    imgcfg = pkg.client.imageconfig.ImageConfig(cfgfile, pkg_image)
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
        pkg_image = smf.get_prop(os.getenv('SMF_FMRI'), 'config/pkg_image')
    except smf.NonzeroExitException:
        pkg_image = '/'

    try:
        mdret = requests.get(MDURL, headers=HEADERS, timeout=10)
    except requests.RequestException:
        metadata = None
    else:
        metadata = mdret.json()
    write_config(pkg_image, metadata)

    return smf_include.SMF_EXIT_OK


def stop():
    ''' Remove any cached OCI ocids '''

    try:
        pkg_image = smf.get_prop(os.getenv('SMF_FMRI'), 'config/pkg_image')
    except smf.NonzeroExitException:
        pass

    write_config(pkg_image, None)

    return smf_include.SMF_EXIT_OK


smf_include.smf_main()
