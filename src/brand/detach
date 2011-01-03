#!/bin/ksh -p
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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#


. /usr/lib/brand/ipkg/common.ksh

m_usage=$(gettext  "detach [-n ].")

f_mount=$(gettext "Error: error mounting zone root dataset.")
f_ds_config=$(gettext  "Failed to configure dataset %s: could not set %s.")

noexecute=0

# Other brand detach options are invalid for this brand.
while getopts "nR:z:" opt; do
	case $opt in
		n)	noexecute=1 ;;
		R)	zonepath="$OPTARG" ;;
		z)	zonename="$OPTARG" ;;
		?)	fail_usage "" ;;
		*)	fail_usage "";;
	esac
done
shift $((OPTIND-1))

if [ $noexecute -eq 1 ]; then
	# dry-run - output zone's config and exit
	cat /etc/zones/$zonename.xml
	exit $ZONE_SUBPROC_OK
fi

#
# Detaching
#
# Leave the active dataset mounted on the zone's rootpath for ease of
# migration.
#
get_current_gzbe
get_zonepath_ds $zonepath
get_active_ds $CURRENT_GZBE $ZONEPATH_DS

/usr/sbin/zfs set zoned=off $ACTIVE_DS || \
    fail_incomplete "$f_ds_config" "$ACTIVE_DS" "zoned=off"

/usr/sbin/zfs set canmount=on $ACTIVE_DS || \
    fail_incomplete "$f_ds_config" "$ACTIVE_DS" "canmount=on"

#
# This mounts the dataset.
# XXX do we have to worry about subsidiary datasets?
#
/usr/sbin/zfs set mountpoint=$zonepath/root $ACTIVE_DS || \
    fail_incomplete "$f_ds_config" "$ACTIVE_DS" "mountpoint=$zonepath/root"

#
# There is no sw inventory in an ipkg branded zone, so just use the original
# xml file.
#
cp /etc/zones/$zonename.xml $zonepath/SUNWdetached.xml

exit $ZONE_SUBPROC_OK
