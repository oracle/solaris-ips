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

#
# Only change PATH if you give full consideration to GNU or other variants
# of common commands having different arguments and output.  Setting PATH is
# and not using the full path to executables provides a performance improvement
# by using the ksh builtin equivalent of many common commands.
#
export PATH=/usr/bin:/usr/sbin
unset LD_LIBRARY_PATH

. /usr/lib/brand/shared/common.ksh

PROP_PARENT="org.opensolaris.libbe:parentbe"
PROP_ACTIVE="org.opensolaris.libbe:active"
PROP_BE_HANDLE="com.oracle.libbe:nbe_handle"

f_incompat_options=$(gettext "cannot specify both %s and %s options")
f_sanity_detail=$(gettext  "Missing %s at %s")
f_sanity_sparse=$(gettext  "Is this a sparse zone image?  The image must be whole-root.")
sanity_ok=$(gettext     "  Sanity Check: Passed.  Looks like a Solaris system.")
sanity_fail=$(gettext   "  Sanity Check: FAILED (see log for details).")
sanity_fail_vers=$(gettext  "  Sanity Check: the Solaris image (release %s) is not an OpenSolaris image and cannot be installed in this type of branded zone.")
install_fail=$(gettext  "        Result: *** Installation FAILED ***")
f_zfs_in_root=$(gettext "Installing a zone inside of the root pool's 'ROOT' dataset is unsupported.")
f_root_create=$(gettext "Unable to create the zone's ZFS dataset mountpoint.")
f_no_gzbe=$(gettext "unable to determine global zone boot environment.")
f_multiple_ds=$(gettext "multiple active datasets.")
f_no_active_ds=$(gettext "no active dataset.")
f_zfs_unmount=$(gettext "Unable to unmount the zone's root ZFS dataset (%s).\nIs there a global zone process inside the zone root?\nThe current zone boot environment will remain mounted.\n")
f_zfs_mount=$(gettext "Unable to mount the zone's ZFS dataset.")

f_safedir=$(gettext "Expected %s to be a directory.")
f_cp=$(gettext "Failed to cp %s %s.")
f_cp_unsafe=$(gettext "Failed to safely copy %s to %s.")

f_sysrepo_fail=$(gettext "Unable to enable svc:/application/pkg/system-repository, please enable the service manually.")
f_zones_proxyd_fail=$(gettext "Unable to enable svc:/application/pkg/zones-proxyd, please enable the service manually.")
f_set_sysrepo_prop_fail=$(gettext "Unable to set the use-system-repo property.")

m_brnd_usage=$(gettext "brand-specific usage: ")

v_unconfig=$(gettext "Performing zone sys-unconfig")
e_unconfig=$(gettext "sys-unconfig failed")
v_mounting=$(gettext "Mounting the zone")
e_badmount=$(gettext "Zone mount failed")
v_unmount=$(gettext "Unmounting zone")
e_badunmount=$(gettext "Zone unmount failed")
e_exitfail=$(gettext "Postprocessing failed.")
v_update_format=$(gettext "Updating image format")
e_update_format=$(gettext "Updating image format failed")

m_complete=$(gettext    "        Done: Installation completed in %s seconds.")
m_postnote=$(gettext    "  Next Steps: Boot the zone, then log into the zone console (zlogin -C)")
m_postnote2=$(gettext "              to complete the configuration process.")

is_brand_labeled() {
	if [[ -z $ALTROOT ]]; then
		AR_OPTIONS=""
	else
		AR_OPTIONS="-R $ALTROOT"
	fi
	brand=$(/usr/sbin/zoneadm $AR_OPTIONS -z $ZONENAME \
		list -p | awk -F: '{print $6}')
	[[ $brand == "labeled" ]] && return 1
	return 0
}

sanity_check() {
	typeset dir="$1"
	shift
	res=0

	#
	# Check for some required directories and make sure this isn't a
	# sparse zone image from SXCE.
	#
	checks="etc etc/svc var var/svc"
	for x in $checks; do
		if [[ ! -e $dir/$x ]]; then
			log "$f_sanity_detail" "$x" "$dir"
			res=1
		fi
	done
	if (( $res != 0 )); then
		log "$f_sanity_sparse"
		log "$sanity_fail"
		fatal "$install_fail" "$ZONENAME"
	fi

	# Check for existence of pkg command.
	if [[ ! -x $dir/usr/bin/pkg ]]; then
		log "$f_sanity_detail" "usr/bin/pkg" "$dir"
		log "$sanity_fail"
		fatal "$install_fail" "$ZONENAME"
	fi

	#
	# XXX There should be a better way to do this.
	# Check image release.  We only work on the same minor release as the
	# system is running.  The INST_RELEASE file doesn't exist with IPS on
	# OpenSolaris, so its presence means we have an earlier Solaris
	# (i.e. non-OpenSolaris) image.
	#
	if [[ -f "$dir/var/sadm/system/admin/INST_RELEASE" ]]; then
		image_vers=$(nawk -F= '{if ($1 == "VERSION") print $2}' \
		    $dir/var/sadm/system/admin/INST_RELEASE)
		vlog "$sanity_fail_vers" "$image_vers"
		fatal "$install_fail" "$ZONENAME"
	fi
	
	vlog "$sanity_ok"
}

function get_current_gzbe {
	#
	# If there is no alternate root (normal case) then set the
	# global zone boot environment by finding the boot environment
	# that is active now.
	# If a zone exists in a boot environment mounted on an alternate root,
	# then find the boot environment where the alternate root is mounted.
	#
	CURRENT_GZBE=$(beadm list -H | nawk -v alt=$ALTROOT -F\; '{
		if (length(alt) == 0) {
		    # Field 3 is the BE status.  'N' is the active BE.
		    if ($3 !~ "N")
			next
		} else {
		    # Field 4 is the BE mountpoint.
		    if ($4 != alt)
		next
		}
		# Field 2 is the BE UUID
		print $2
	    }')
	if [ -z "$CURRENT_GZBE" ]; then
		return 1
	fi
	return 0
}

#
# get_active_be zone
#
# Finds the active boot environment for the given zone.
#
# Arguments:
#
#  zone		zone structure initialized with init_zone
#
# Globals:
#
#  CURRENT_GZBE	Current global zone boot environment.  If not already set,
#		it will be set.
#
# Returns:
#
#  0 on success, else 1.
#
function get_active_be {
	typeset -n zone=$1
	typeset active_ds=
	typeset tab=$(printf "\t")

	[[ -z "$CURRENT_GZBE" ]] && get_current_gzbe

	typeset name parent active
	zfs list -H -r -d 1 -t filesystem -o name,$PROP_PARENT,$PROP_ACTIVE \
	    ${zone.ROOT_ds} | while IFS=$tab read name parent active ; do
		[[ $parent == "$CURRENT_GZBE" ]] || continue
		[[ $active == on ]] || continue
		vlog "Found active dataset %s" "$name"
		if [[ -n "$active_ds" ]] ; then
			error "$f_multiple_ds"
			return 1
		fi
		active_ds=$name
	done
	if [[ -z $active_ds ]]; then
		error "$f_no_active_ds"
		return 1
	fi

	zone.active_ds=$active_ds
}

function set_active_be {
	typeset -n zone="$1"
	typeset be="$2"

	[[ -z "$CURRENT_GZBE" ]] && get_current_gzbe

	#
	# Turn off the active property on BE's with the same GZBE
	#
	zfs list -H -r -d 1 -t filesystem -o name,$PROP_PARENT,$PROP_ACTIVE \
	    ${zone.ROOT_ds} | while IFS=$tab read name parent active ; do
		[[ $parent == "$CURRENT_GZBE" ]] || continue
		[[ $active == on ]] || continue
		[[ $name ==  "${zone.ROOT_ds}/$be" ]] && continue
		vlog "Deactivating active dataset %s" "$name"
		zfs set $PROP_ACTIVE=off "$name" || return 1
	done

	zone.active_ds="${zone.ROOT_ds}/$be"

	zfs set "$PROP_PARENT=$CURRENT_GZBE" ${zone.active_ds} \
	    || return 1
	zfs set "$PROP_ACTIVE=on" ${zone.active_ds} || return 1

	zfs set "$PROP_BE_HANDLE=on" "${zone.rpool_ds}" || return 1

	return 0
}

#
# Run sys-unconfig on the zone.
#
unconfigure_zone() {
	vlog "$v_unconfig"

	vlog "$v_mounting"
	ZONE_IS_MOUNTED=1
	zoneadm -z $ZONENAME mount -f || fatal "$e_badmount"

	# If unconfig service exists and is online then use sysconfig
	SC_ONLINE=$(svcprop -p restarter/state \
	    svc:/milestone/unconfig:default 2> /dev/null)
	if (( $? == 0 )) && [[ $SC_ONLINE == "online" ]]; then
		zlogin -S $ZONENAME "export _UNCONFIG_ALT_ROOT=/a; \
		    /usr/sbin/sysconfig unconfigure -g system; \
		    export _UNCONFIG_ALT_ROOT= ;" \
		    </dev/null >/dev/null 2>&1
	else
		zlogin -S $ZONENAME /usr/sbin/sys-unconfig -R /a \
		    </dev/null >/dev/null 2>&1
	fi

	if (( $? != 0 )); then
		error "$e_unconfig"
		failed=1
	fi

	vlog "$v_unmount"
	zoneadm -z $ZONENAME unmount || fatal "$e_badunmount"
	ZONE_IS_MOUNTED=0

	[[ -n $failed ]] && fatal "$e_exitfail"
}

#
# Emits to stdout the fmri for the supplied package,
# stripped of publisher name and other junk.
#
get_pkg_fmri() {
	typeset pname=$1
	typeset pkg_fmri=
	typeset info_out=

	info_out=$(LC_ALL=C $PKG info pkg:/$pname 2>/dev/null)
	if [[ $? -ne 0 ]]; then
		return 1
	fi
	pkg_fmri=$(echo $info_out | grep FMRI | cut -d'@' -f 2)
	echo "$pname@$pkg_fmri"
	return 0
}

#
# Emits to stdout the entire incorporation for this image,
# stripped of publisher name and other junk.
#
get_entire_incorp() {
	get_pkg_fmri entire
	return $?
}

#
# Handle pkg exit code.  Exit 0 means Command succeeded, exit 4 means
# No changes were made - nothing to do.  Any other exit code is an error.
#
pkg_err_check() {
	typeset res=$?
	(( $res != 0 && $res != 4 )) && fail_fatal "$1"
}

#
# Enable the services needed to perform packaging operations inside a zone.
#
enable_zones_services() {                                                       
	/usr/sbin/svcadm enable -st svc:/application/pkg/system-repository
	if [[ $? -ne 0 ]]; then
		error "$f_sysrepo_fail"
		return 1
	fi
	/usr/sbin/svcadm enable -st svc:/application/pkg/zones-proxyd
	if [[ $? -ne 0 ]]; then
		error "$f_zones_proxyd_fail"
		return 1
	fi
	return 0
}
