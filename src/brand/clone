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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

. /usr/lib/brand/ipkg/common.ksh

m_usage=$(gettext "clone {sourcezone}")
f_nosource=$(gettext "Error: unable to determine source zone dataset.")

# Clean up on failure
trap_exit()
{
	if (( $ZONE_IS_MOUNTED != 0 )); then
		error "$v_unmount"
		zoneadm -z $ZONENAME unmount
	fi

	exit $ZONE_SUBPROC_INCOMPLETE
}

# Set up ZFS dataset hierarchy for the zone.

ROOT="rpool/ROOT"

# Other brand clone options are invalid for this brand.
while getopts "R:z:" opt; do
	case $opt in
		R)	ZONEPATH="$OPTARG" ;;
		z)	ZONENAME="$OPTARG" ;;
		*)	fail_usage "";;
	esac
done
shift $((OPTIND-1))

if [ $# -ne 1 ]; then
	fail_usage "";
fi

sourcezone=$1

# Find the active source zone dataset to clone.
sourcezonepath=`/usr/sbin/zoneadm -z $sourcezone list -p | awk -F: '{print $4}'`
if [ -z "$sourcezonepath" ]; then
	fail_fatal "$f_nosource"
fi

get_current_gzbe
get_zonepath_ds $sourcezonepath
get_active_ds $CURRENT_GZBE $ZONEPATH_DS

#
# Now set up the zone's datasets
#

#
# First make the top-level dataset.
#

pdir=`/usr/bin/dirname $ZONEPATH`
zpname=`/usr/bin/basename $ZONEPATH`

get_zonepath_ds $pdir
zpds=$ZONEPATH_DS

fail_zonepath_in_rootds $zpds

#
# We need to tolerate errors while creating the datasets and making the
# mountpoint, since these could already exist from some other BE.
#

/usr/sbin/zfs create $zpds/$zpname

/usr/sbin/zfs create -o mountpoint=legacy -o zoned=on $zpds/$zpname/ROOT

# make snapshot
SNAPNAME=${ZONENAME}_snap
SNAPNUM=0
while [ $SNAPNUM -lt 100 ]; do
	/usr/sbin/zfs snapshot $ACTIVE_DS@$SNAPNAME
        if [ $? = 0 ]; then
                break
	fi
	SNAPNUM=`expr $SNAPNUM + 1`
	SNAPNAME="${ZONENAME}_snap$SNAPNUM"
done

if [ $SNAPNUM -ge 100 ]; then
	fail_fatal "$f_zfs_create"
fi

# do clone
BENAME=zbe
BENUM=0
while [ $BENUM -lt 100 ]; do
	/usr/sbin/zfs clone $ACTIVE_DS@$SNAPNAME $zpds/$zpname/ROOT/$BENAME
	if [ $? = 0 ]; then
		break
	fi
	BENUM=`expr $BENUM + 1`
	BENAME="zbe-$BENUM"
done

if [ $BENUM -ge 100 ]; then
	fail_fatal "$f_zfs_create"
fi

/usr/sbin/zfs set $PROP_ACTIVE=on $zpds/$zpname/ROOT/$BENAME || \
	fail_incomplete "$f_zfs_create"

/usr/sbin/zfs set $PROP_PARENT=$CURRENT_GZBE $zpds/$zpname/ROOT/$BENAME || \
	fail_incomplete "$f_zfs_create"

/usr/sbin/zfs set canmount=noauto $zpds/$zpname/ROOT/$BENAME || \
	fail_incomplete "$f_zfs_create"

if [ ! -d $ZONEPATH/root ]; then
	/usr/bin/mkdir -p $ZONEPATH/root
	/usr/bin/chmod 700 $ZONEPATH
fi

ZONE_IS_MOUNTED=0
trap trap_exit EXIT

#
# Completion of unconfigure_zone will leave the zone root mounted for
# ipkg brand zones.  The root won't be mounted for labeled brand zones.
#
is_brand_labeled
(( $? == 0 )) && unconfigure_zone

trap - EXIT
exit $ZONE_SUBPROC_OK
