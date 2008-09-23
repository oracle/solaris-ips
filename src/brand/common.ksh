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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

ZONE_SUBPROC_OK=0
ZONE_SUBPROC_USAGE=253
ZONE_SUBPROC_INCOMPLETE=254
ZONE_SUBPROC_FATAL=255

PROP_PARENT="org.opensolaris.libbe:parentbe"
PROP_ACTIVE="org.opensolaris.libbe:active"

f_zfs_in_root=$(gettext "Installing a zone in the ROOT pool is unsupported.")
f_zfs_create=$(gettext "Unable to create the zone's ZFS dataset.")
f_root_create=$(gettext "Unable to create the zone's ZFS dataset mountpoint.")
f_no_gzbe=$(gettext "Error: unable to determine global zone boot environment.")
f_no_ds=$(gettext "Error: no zonepath dataset.")
f_multiple_ds=$(gettext "Error: multiple active datasets.")
f_no_active_ds=$(gettext "Error: no active dataset.")
f_zfs_mount=$(gettext "Unable to mount the zone's ZFS dataset.")

fail_incomplete() {
	print "$1"
	exit $ZONE_SUBPROC_INCOMPLETE
}

fail_fatal() {
	print "$1"
	exit $ZONE_SUBPROC_FATAL
}

fail_usage() {
	print "Usage: $1"
	exit $ZONE_SUBPROC_USAGE
}

get_current_gzbe() {
	#
	# If there is no beadm command then the system doesn't really
	# support multiple boot environments.  We still want zones to work,
	# so simulate the existence of a single boot environment.
	#
	if [ -x /usr/sbin/beadm ]; then
		CURRENT_GZBE=`/usr/sbin/beadm list -H | /usr/bin/nawk -F\; '{
			# Field 3 is the BE status.  'N' is the active BE.
			if ($3 ~ "N")
				# Field 2 is the BE UUID
				print $2
		}'`
	else
		CURRENT_GZBE="opensolaris"
	fi

	if [ -z "$CURRENT_GZBE" ]; then
		fail_fatal "$f_no_gzbe"
	fi
}

# Find the dataset mounted on the zonepath.
get_zonepath_ds() {
	ZONEPATH_DS=`/usr/sbin/zfs list -H -t filesystem -o name,mountpoint | \
	    /usr/bin/nawk -v zonepath=$1 '{
		if ($2 == zonepath)
			print $1
	}'`

	if [ -z "$ZONEPATH_DS" ]; then
		fail_fatal "$f_no_ds"
	fi
}

# Find the active dataset under the zonepath dataset to mount on zonepath/root.
# $1 CURRENT_GZBE
# $2 ZONEPATH_DS
get_active_ds() {
	ACTIVE_DS=`/usr/sbin/zfs list -H -r -t filesystem \
	    -o name,$PROP_PARENT,$PROP_ACTIVE $2/ROOT | \
	    /usr/bin/nawk -v gzbe=$1 ' {
		if ($1 ~ /ROOT\/[^\/]+$/ && $2 == gzbe && $3 == "on") {
			print $1
			if (found == 1)
				exit 1
			found = 1
		}
	    }'`

	if [ $? -ne 0 ]; then
		fail_fatal "$f_multiple_ds"
	fi

	if [ -z "$ACTIVE_DS" ]; then
		fail_fatal "$f_no_active_ds"
	fi
}

# Check that zone is not in the ROOT dataset.
fail_zonepath_in_rootds() {
	case $1 in
		rpool/ROOT/*)
			fail_fatal "$f_zfs_in_root"
			break;
			;;
		*)
			break;
			;;
	esac
}
