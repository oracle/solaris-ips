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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

# NOTE: this script runs in the global zone and touches the non-global
# zone, so care should be taken to validate any modifications so that they
# are safe.

# Restrict executables to /usr/bin and /usr/sbin
PATH=/usr/bin:/usr/sbin
export PATH
unset LD_LIBRARY_PATH

. /usr/lib/brand/ipkg/common.ksh

LOGFILE=
EXIT_CODE=1

# Clean up on failure
trap_exit()
{
	if (( $ZONE_IS_MOUNTED != 0 )); then
		error "$v_unmount"
		zoneadm -z $ZONENAME unmount
	fi

	exit $EXIT_CODE
}

#
# For an exclusive stack zone, fix up the network configuration files.
# We need to do this even if unconfiguring the zone so sys-unconfig works
# correctly.
#
fix_net()
{
	[[ "$STACK_TYPE" == "shared" ]] && return

	NETIF_CNT=0
	for i in $ZONEROOT/etc/hostname.* $ZONEROOT/etc/dhcp.*
	do
		if [[ -f "$i" ]]; then
			NETIF_CNT=$(expr $NETIF_CNT + 1)
			OLD_HOSTNET="$i"
		fi
	done
	if (( $NETIF_CNT != 1 )); then
		vlog "$v_nonetfix"
		return
	fi

	NET=$(LC_ALL=C zonecfg -z $ZONENAME info net)
	if (( $? != 0 )); then
		error "$e_badinfo" "net"
		return
	fi

	NETIF=$(echo $NET | nawk '{
		for (i = 1; i < NF; i++) {
			if ($i == "physical:") {
				if (length(net) == 0) {
					i++
					net = $i
				} else {
					multiple=1
				}
			}
		}
	}
	END {	if (!multiple)
			print net
	}')

	if [[ -z "$NETIF" ]]; then
		vlog "$v_nonetfix"
		return
	fi

	NEWHOSTNET=${OLD_HOSTNET%*.*}
	if [[ "$OLD_HOSTNET" != "$NEWHOSTNET.$NETIF" ]]; then
		safe_move $OLD_HOSTNET $NEWHOSTNET.$NETIF
	fi
}

#
# Disable all of the shares since the zone cannot be an NFS server.
# Note that we disable the various instances of the svc:/network/shares/group
# SMF service in the fix_smf function. 
#
fix_nfs()
{
	zonedfs=$ZONEROOT/etc/dfs

	if [[ -h $zonedfs/dfstab || ! -f $zonedfs/dfstab ]]; then
		error "$e_badfile" "/etc/dfs/dfstab"
		return
	fi

	tmpfile=$(mktemp -t)
	if [[ -z "$tmpfile" ]]; then
		error "$e_tmpfile"
		return
	fi

	nawk '{
		if (substr($1, 0, 1) == "#") {
			print $0
		} else {
			print "#", $0
			modified=1
		}
	}
	END {
		if (modified == 1) {
			printf("# Modified by p2v ")
			system("/usr/bin/date")
			exit 0
		}
		exit 1
	}' $zonedfs/dfstab >>$tmpfile

	if (( $? == 0 )); then
		if [[ ! -f $zonedfs/dfstab.pre_p2v ]]; then
			safe_copy $zonedfs/dfstab $zonedfs/dfstab.pre_p2v
		fi
		safe_copy $tmpfile $zonedfs/dfstab
	fi
	rm -f $tmpfile
}

#
# Comment out most of the old mounts since they are either unneeded or
# likely incorrect within a zone.  Specific mounts can be manually 
# reenabled if the corresponding device is added to the zone.
#
fix_vfstab()
{
	if [[ -h $ZONEROOT/etc/vfstab || ! -f $ZONEROOT/etc/vfstab ]]; then
		error "$e_badfile" "/etc/vfstab"
		return
	fi

	tmpfile=$(mktemp -t)
	if [[ -z "$tmpfile" ]]; then
		error "$e_tmpfile"
		return
	fi

	nawk '{
		if (substr($1, 0, 1) == "#") {
			print $0
		} else if ($1 == "fd" || $1 == "/proc" || $1 == "swap" ||
		    $1 == "ctfs" || $1 == "objfs" || $1 == "sharefs" ||
		    $4 == "nfs" || $4 == "lofs") {
			print $0
		} else {
			print "#", $0
			modified=1
		}
	}
	END {
		if (modified == 1) {
			printf("# Modified by p2v ")
			system("/usr/bin/date")
			exit 0
		}
		exit 1
	}' $ZONEROOT/etc/vfstab >>$tmpfile

	if (( $? == 0 )); then
		if [[ ! -f $ZONEROOT/etc/vfstab.pre_p2v ]]; then
			safe_copy $ZONEROOT/etc/vfstab \
			    $ZONEROOT/etc/vfstab.pre_p2v
		fi
		safe_copy $tmpfile $ZONEROOT/etc/vfstab
	fi
	rm -f $tmpfile
}

#
# Delete or disable SMF services.
#
fix_smf()
{
	SMF_UPGRADE=/a/var/svc/profile/upgrade

	#
	# Fix network services if shared stack.
	#
	if [[ "$STACK_TYPE" == "shared" ]]; then
		vlog "$v_fixnetsvcs"

		NETPHYSDEF="svc:/network/physical:default"
		NETPHYSNWAM="svc:/network/physical:nwam"

		vlog "$v_enblsvc" "$NETPHYSDEF"
		zlogin -S $ZONENAME "echo /usr/sbin/svcadm enable $NETPHYSDEF \
		    >>$SMF_UPGRADE" </dev/null

		vlog "$v_dissvc" "$NETPHYSNWAM"
		zlogin -S $ZONENAME \
		    "echo /usr/sbin/svcadm disable $NETPHYSNWAM \
		    >>$SMF_UPGRADE" </dev/null

		# Disable routing svcs.
		vlog "$v_dissvc" 'svc:/network/routing/*'
		zlogin -S $ZONENAME \
		    "echo /usr/sbin/svcadm disable 'svc:/network/routing/*' \
		    >>$SMF_UPGRADE" </dev/null
	fi

	#
	# Disable well-known services that don't run in a zone.
	#
	vlog "$v_rminvalidsvcs"
	for i in $(egrep -hv "^#" \
	    /usr/lib/brand/ipkg/smf_disable.lst \
	    /etc/brand/ipkg/smf_disable.conf)
	do
		# Disable the svc.
		vlog "$v_dissvc" "$i"
		zlogin -S $ZONENAME \
		    "echo /usr/sbin/svcadm disable $i >>$SMF_UPGRADE" </dev/null
	done

	#
	# Since zones can't be NFS servers, disable all of the instances of
	# the shares svc.
	#
	vlog "$v_dissvc" 'svc:/network/shares/*'
	zlogin -S $ZONENAME \
	    "echo /usr/sbin/svcadm disable 'svc:/network/shares/*' \
	    >>$SMF_UPGRADE" </dev/null
}

#
# Remove well-known pkgs that do not work inside a zone.
#
rm_pkgs()
{
	for i in $(egrep -hv "^#" /usr/lib/brand/ipkg/pkgrm.lst \
	    /etc/brand/ipkg/pkgrm.conf)
	do
		pkg info $i >/dev/null 2>&1
		if (( $? != 0 )); then
			continue
		fi

		vlog "$v_rmpkg" "$i"
		zlogin -S $ZONENAME LC_ALL=C \
		    /usr/bin/pkg -R /a uninstall -r $i </dev/null >&2 || \
		    error "$e_rmpkg" $i
	done
}

#
# Zoneadmd writes a one-line index file into the zone when the zone boots,
# so any information about installed zones from the original system will
# be lost at that time.  Here we'll warn the sysadmin about any pre-existing
# zones that they might want to clean up by hand, but we'll leave the zonepaths
# in place in case they're on shared storage and will be migrated to
# a new host.
#
warn_zones()
{
	zoneconfig=$ZONEROOT/etc/zones

	if [[ -h $zoneconfig/index || ! -f $zoneconfig/index ]]; then
		error "$e_badfile" "/etc/zones/index"
		return
	fi

	NGZ=$(nawk -F: '{
		if (substr($1, 0, 1) == "#" || $1 == "global")
			continue

		if ($2 == "installed")
			printf("%s ", $1)
	}' $zoneconfig/index)

	# Return if there are no installed zones to warn about.
	[[ -z "$NGZ" ]] && return

	log "$v_rmzones" "$NGZ"

	NGZP=$(nawk -F: '{
		if (substr($1, 0, 1) == "#" || $1 == "global")
			continue

		if ($2 == "installed")
			printf("%s ", $3)
	}' $zoneconfig/index)

	log "$v_rmzonepaths"

	for i in $NGZP
	do
		log "    %s" "$i"
	done
}

#
# failure should unmount the zone if necessary;
#
ZONE_IS_MOUNTED=0
trap trap_exit EXIT

#
# Parse the command line options.
#
OPT_U=
OPT_V=
OPT_L=
while getopts "b:uvl:" opt
do
	case "$opt" in
		u)	OPT_U="-u";;
		v)	OPT_V="-v";;
		l)	LOGFILE="$OPTARG"; OPT_L="-l \"$OPTARG\"";;
		*)	exit 1;;
	esac
done
shift OPTIND-1

(( $# != 2 )) && exit 1

[[ -n $LOGFILE ]] && exec 2>>$LOGFILE

ZONENAME=$1
ZONEPATH=$2
ZONEROOT=$ZONEPATH/root

e_badinfo=$(gettext "Failed to get '%s' zone resource")
e_badfile=$(gettext "Invalid '%s' file within the zone")
e_tmpfile=$(gettext "Unable to create temporary file")
v_mkdirs=$(gettext "Creating mount points")
v_nonetfix=$(gettext "Cannot update /etc/hostname.{net} file")
v_change_var=$(gettext "Changing the pkg variant to nonglobal...")
e_change_var=$(gettext "Changing the pkg variant to nonglobal failed")
v_update=$(gettext "Updating the zone software to match the global zone...")
v_updatedone=$(gettext "Zone software update complete")
e_badupdate=$(gettext "Updating the Zone software failed")
v_adjust=$(gettext "Updating the image to run within a zone")
v_stacktype=$(gettext "Stack type '%s'")
v_rmhollowsvcs=$(gettext "Deleting global zone-only SMF services")
v_fixnetsvcs=$(gettext "Adjusting network SMF services")
v_rminvalidsvcs=$(gettext "Disabling invalid SMF services")
v_collectingsmf=$(gettext "Collecting SMF svc data")
v_delsvc=$(gettext "Delete SMF svc '%s'")
e_delsvc=$(gettext "deleting SMF svc '%s'")
v_enblsvc=$(gettext "Enable SMF svc '%s'")
e_enblsvc=$(gettext "enabling SMF svc '%s'")
v_dissvc=$(gettext "Disable SMF svc '%s'")
e_adminf=$(gettext "Unable to create admin file")
v_rmpkg=$(gettext "Remove package '%s'")
e_rmpkg=$(gettext "removing package '%s'")
v_rmzones=$(gettext "The following zones in this image will be unusable: %s")
v_rmzonepaths=$(gettext "These zonepaths could be removed from this image:")
v_exitgood=$(gettext "Postprocessing successful.")

#
# Do some validation on the paths we'll be accessing
#
safe_dir etc
safe_dir etc/dfs
safe_dir etc/zones
safe_dir var
safe_dir var/log
safe_dir var/pkg

# Now do the work to update the zone.

# Before booting the zone we may need to create a few mnt points, just in
# case they don't exist for some reason.
#
# Whenever we reach into the zone while running in the global zone we
# need to validate that none of the interim directories are symlinks
# that could cause us to inadvertently modify the global zone.
vlog "$v_mkdirs"
if [[ ! -f $ZONEROOT/tmp && ! -d $ZONEROOT/tmp ]]; then
	mkdir -m 1777 -p $ZONEROOT/tmp || exit $EXIT_CODE
fi
if [[ ! -f $ZONEROOT/var/run && ! -d $ZONEROOT/var/run ]]; then
	mkdir -m 1755 -p $ZONEROOT/var/run || exit $EXIT_CODE
fi
if [[ ! -h $ZONEROOT/etc && ! -f $ZONEROOT/etc/mnttab ]]; then
	touch $ZONEROOT/etc/mnttab || exit $EXIT_CODE
	chmod 444 $ZONEROOT/etc/mnttab || exit $EXIT_CODE
fi
if [[ ! -f $ZONEROOT/proc && ! -d $ZONEROOT/proc ]]; then
	mkdir -m 755 -p $ZONEROOT/proc || exit $EXIT_CODE
fi
if [[ ! -f $ZONEROOT/dev && ! -d $ZONEROOT/dev ]]; then
	mkdir -m 755 -p $ZONEROOT/dev || exit $EXIT_CODE
fi
if [[ ! -h $ZONEROOT/etc && ! -h $ZONEROOT/etc/svc && ! -d $ZONEROOT/etc/svc ]]
then
	mkdir -m 755 -p $ZONEROOT/etc/svc/volatile || exit $EXIT_CODE
fi

# Check for zones inside of image.
warn_zones

STACK_TYPE=$(zoneadm -z $ZONENAME list -p | nawk -F: '{print $7}')
if (( $? != 0 )); then
	error "$e_badinfo" "stacktype"
fi
vlog "$v_stacktype" "$STACK_TYPE"

# Note that we're doing this before update-on-attach has run.
fix_net
fix_nfs
fix_vfstab

#
# Mount the zone so that we can do all of the updates needed on the zone.
#
vlog "$v_mounting"
ZONE_IS_MOUNTED=1
zoneadm -z $ZONENAME mount -f || fatal "$e_badmount"

#
# Any errors in these functions are not considered fatal.  The zone can be
# be fixed up manually afterwards and it may need some additional manual
# cleanup in any case.
#

log "$v_adjust"
# cleanup SMF services
fix_smf
# remove invalid pkgs
rm_pkgs

vlog "$v_unmount"
zoneadm -z $ZONENAME unmount || fatal "$e_badunmount"
ZONE_IS_MOUNTED=0

is_brand_labeled
brand_labeled=$?
if (( $brand_labeled == 1 )); then
	# The labeled brand needs to mount the zone's root dataset back onto
	# ZONEROOT so we can finish processing.
	mount_active_ds
fi

# Change the pkging variant from global zone to non-global zone.
log "$v_change_var"
pkg -R $ZONEROOT change-variant variant.opensolaris.zone=nonglobal || \
    fatal "$e_change_var"

#
# Run update on attach.  State is currently 'incomplete' so use the private
# force-update option.
# This also leaves the zone in the 'installed' state.  This is a known bug
# in 'zoneadm attach'.  We change the zone state back to 'incomplete' for
# now but this can be removed once 'zoneadm attach' is fixed.
#
log "$v_update"
zoneadm -z $ZONENAME attach -U >&2 || fatal "$e_badupdate"
zoneadm -z $ZONENAME mark incomplete || fatal "$e_badupdate"
log "$v_updatedone"

[[ -n $OPT_U ]] && unconfigure_zone

(( $brand_labeled == 1 )) && mount_active_ds

trap - EXIT
vlog "$v_exitgood"
exit 0
