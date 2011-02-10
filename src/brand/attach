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

m_attach_log=$(gettext "Log File: %s")
m_zfs=$(gettext "A ZFS file system was created for the zone.")
m_usage=$(gettext  "attach [-a archive] [-d dataset] [-n] [-r zfs-recv] [-u]\n\tThe -a archive option specifies a tar file or cpio archive.\n\tThe -d dataset option specifies an existing dataset.\n\tThe -r zfs-recv option receives the output of a 'zfs send' command\n\tof an existing zone root dataset.\n\tThe -u option indicates that the software should be updated to match\n\tthe current host.")
m_attach_root=$(gettext "               Attach Path: %s")
m_attach_ds=$(gettext   "        Attach ZFS Dataset: %s")
m_gzinc=$(gettext       "       Global zone version: %s")
m_zinc=$(gettext        "   Non-Global zone version: %s")
m_need_update=$(gettext "                Evaluation: Packages in zone %s are out of sync with the global zone. To proceed, retry with the -u flag.")
m_cache=$(gettext       "                     Cache: Using %s.")
m_updating=$(gettext    "  Updating non-global zone: Output follows")
m_sync_done=$(gettext   "  Updating non-global zone: Zone updated.")
m_complete=$(gettext    "                    Result: Attach Succeeded.")
m_failed=$(gettext      "                    Result: Attach Failed.")

#
# These two messages are used by the install_image function in
# /usr/lib/brand/shared/common.ksh.  Yes, this is terrible.
#
installing=$(gettext    "                Installing: This may take several minutes...")
no_installing=$(gettext "                Installing: Using pre-existing data in zonepath")

f_sanity_variant=$(gettext "  Sanity Check: FAILED, couldn't determine %s from image.")
f_sanity_global=$(gettext  "  Sanity Check: FAILED, appears to be a global zone (%s=%s).")
f_update=$(gettext "Could not update attaching zone")
f_no_pref_publisher=$(gettext "Unable to get preferred publisher information for zone '%s'.")
f_nosuch_key=$(gettext "Failed to find key %s for global zone publisher")
f_nosuch_cert=$(gettext "Failed to find cert %s for global zone publisher")
f_ds_config=$(gettext  "Failed to configure dataset %s: could not set %s.")
f_no_active_ds_mounted=$(gettext  "Failed to locate any dataset mounted at %s.  Attach requires a mounted dataset.")

# Clean up on interrupt
trap_cleanup() {
	typeset msg=$(gettext "Installation cancelled due to interrupt.")

	log "$msg"

	# umount any mounted file systems
	umnt_fs

	trap_exit
}

# If the attach failed then clean up the ZFS datasets we created.
trap_exit() {
	if [[ $EXIT_CODE == $ZONE_SUBPROC_OK ]]; then
		# unmount the zoneroot if labeled brand
		is_brand_labeled
		(( $? == 1 )) && ( umount $ZONEROOT || \
		    log "$f_zfs_unmount" "$ZONEPATH/root" )
	else
		if [[ "$install_media" != "-" ]]; then
			/usr/lib/brand/ipkg/uninstall $ZONENAME $ZONEPATH -F
		else
			# Restore the zone properties for the pre-existing
			# dataset.
			if [[ -n "$ACTIVE_DS" ]]; then
				zfs set zoned=off $ACTIVE_DS
				(( $? != 0 )) && error "$f_ds_config" \
				    "$ACTIVE_DS" "zoned=off"
				zfs set canmount=on $ACTIVE_DS
				(( $? != 0 )) && error "$f_ds_config" \
				    "$ACTIVE_DS" "canmount=on"
				zfs set mountpoint=$ZONEROOT $ACTIVE_DS
				(( $? != 0 )) && error "$f_ds_config" \
				    "$ACTIVE_DS" "mountpoint=$ZONEROOT"
			fi
		fi
		log "$m_failed"
	fi

	exit $EXIT_CODE
}

EXIT_CODE=$ZONE_SUBPROC_USAGE
install_media="-"

trap trap_cleanup INT
trap trap_exit EXIT

#set -o xtrace

PKG="/usr/bin/pkg"
KEYDIR=/var/pkg/ssl

# If we weren't passed at least two arguments, exit now.
(( $# < 2 )) && exit $ZONE_SUBPROC_USAGE

ZONENAME="$1"
ZONEPATH="$2"
# XXX shared/common script currently uses lower case zonename & zonepath
zonename="$ZONENAME"
zonepath="$ZONEPATH"

shift; shift	# remove ZONENAME and ZONEPATH from arguments array

ZONEROOT="$ZONEPATH/root"
logdir="$ZONEROOT/var/log"

#
# Resetting GZ_IMAGE to something besides slash allows for simplified
# debugging of various global zone image configurations-- simply make
# an image somewhere with the appropriate interesting parameters.
#
GZ_IMAGE=${GZ_IMAGE:-/}
PKG_IMAGE=$GZ_IMAGE
export PKG_IMAGE

allow_update=0
noexecute=0

unset inst_type

# Get publisher information for global zone.  These structures are used
# to store information about the global zone publishers and
# incorporations.

typeset -A gz_publishers
typeset gz_incorporations=""

#
# Gather the zone publisher details. $1 is the location of the image we
# are processing and $2 is an associative array used to store publisher
# details.
#
gather_zone_publisher_details() {
	STORED_IMAGE=$PKG_IMAGE
	PKG_IMAGE=$1;export PKG_IMAGE
	typeset -n publishers=$2
	typeset -li publisher_count=0
	typeset -li url_count=0
	typeset line=
	typeset name=
	typeset mirror=
	typeset origin=
	typeset opublisher=

	#
	# Store publisher, origin and security details. It is assumed
	# that mirrors all use the same key as the origins.
	#
	for line in $(get_publisher_urls all origin); do
		print $line | IFS="=" read name origin
		# When a publisher has multiple origins, the
		# additional origins don't contain the publisher
		# name. Correct for this by checking if origin is not
		# set by get_publisher_urls() and, if so, use the
		# "name" as the origin and set the name to the value
		# we have already saved.
		if [[ -z $origin ]]; then
			origin=$name
			name=${publisher.name}
		elif [[ "$origin" == "None" ]]; then
			# Publisher with no origins.
			origin=""
		fi

		# Use a compound variable to store all the data
		# relating to a publisher.
		if [[ -z ${publishers[$name]} ]]; then
			typeset -C publisher_$publisher_count
			typeset -n publisher=publisher_$publisher_count
			typeset publisher.sticky=""
			typeset publisher.preferred=""
			typeset publisher.enabled=""
			typeset -a publisher.origins=""
			typeset -a publisher.mirrors=""
			typeset publisher.name=$name
			typeset publisher.keyfile=""
			typeset publisher.certfile=""

			get_publisher_attrs ${publisher.name} origin | \
			    IFS=" " read publisher.sticky publisher.preferred \
			    publisher.enabled
			if [[ -n "$origin" ]]; then
				get_pub_secinfo ${publisher.name} | \
				    read publisher.keyfile publisher.certfile
				[[ ${publisher.keyfile} != "None" && \
				    ! -f ${PKG_IMAGE}/${publisher.keyfile} ]] && \
				    fail_usage "$f_nosuch_key" \
				        ${publisher.keyfile}
				[[ ${publisher.certfile} != "None" && \
				    ! -f ${PKG_IMAGE}/${publisher.certfile} ]] && \
				    fail_usage "$f_nosuch_cert" \
				        ${publisher.certfile}
			else
				# Publisher has no origins.
				publisher.keyfile="None"
				publisher.certfile="None"
			fi
			publisher_count=publisher_count+1
			url_count=0
		fi
		publisher.origins[$url_count]=$origin
		publishers[$name]=${publisher}
		url_count=url_count+1
	done

	#
	# Store mirror details
	#
	url_count=0
	for line in $(get_publisher_urls all mirror); do
		print $line | IFS="=" read name mirror
		if [[ -z $mirror ]]; then
			mirror=$name
			name=${publisher.name}
		fi
		if [[ -z $opublisher || $opublisher != $name ]]; then
			opublisher=$name
			eval publisher="${publishers[$name]}"
			url_count=0
		fi
		publisher.mirrors[$url_count]=$mirror
		publishers[$name]=${publisher}
		url_count=url_count+1
	done
	
	PKG_IMAGE=$STORED_IMAGE;export PKG_IMAGE
}

#
# $1 is an associative array of publishers. Search this array and
# return the preferred publisher.
#
get_preferred_publisher() {
	typeset -n publishers=$1
	typeset publisher=

	for key in ${!publishers[*]}; do
		eval publisher="${publishers[$key]}"
		if [[ ${publisher.preferred}  ==  "true" ]]; then
			print ${key}
			return 0
		fi
	done
	return 1
}

#
# $1 is an empty string to be populated with a list of incorporation
# fmris.
#
gather_incorporations() {
	typeset -n incorporations=$1
	typeset p=

	for p in \
	    $(LC_ALL=C $PKG search -Hl -o pkg.name \
	    ':pkg.depend.install-hold:core-os*');do
		incorporations="$incorporations $(get_pkg_fmri $p)"
	done
}

#
# Print the pkg(1) command which defines a publisher. $1 is an associative 
# array of publisher details and $2 is the publisher to be printed.
#
print_publisher_pkg_defn() {
	typeset -n publishers=$1
	typeset pname=$2
	typeset publisher=
	typeset args=""
	typeset origin=
	typeset mirror=

	eval publisher="${publishers[$pname]}"

	if [[ ${publisher.preferred} == "true" ]]; then
		args="$args -P"
	fi

	for origin in ${publisher.origins[*]}; do
		args="$args -g $origin"
	done

	for mirror in ${publisher.mirrors[*]}; do
		args="$args -m $mirror"
	done

	if [[ ${publisher.sticky} == "true" ]]; then
		args="$args --sticky"
	else
		args="$args --non-sticky"
	fi

	if [[ ${publisher.enabled} == "true" ]]; then
		args="$args --enable"
	else
		args="$args --disable"
	fi

	echo "$args"
}

# Other brand attach options are invalid for this brand.
while getopts "a:d:nr:u" opt; do
	case $opt in
		a)
			if [[ -n "$inst_type" ]]; then
				fatal "$incompat_options" "$m_usage"
			fi
		 	inst_type="archive"
			install_media="$OPTARG"
			;;
		d)
			if [[ -n "$inst_type" ]]; then
				fatal "$incompat_options" "$m_usage"
			fi
		 	inst_type="directory"
			install_media="$OPTARG"
			;;
		n)	noexecute=1 ;;
		r)
			if [[ -n "$inst_type" ]]; then
				fatal "$incompat_options" "$m_usage"
			fi
		 	inst_type="stdin"
			install_media="$OPTARG"
			;;
		u)	allow_update=1 ;;
		?)	fail_usage "" ;;
		*)	fail_usage "";;
	esac
done
shift $((OPTIND-1))

if [[ $noexecute == 1 && -n "$inst_type" ]]; then
	fatal "$m_usage"
fi

[[ -z "$inst_type" ]] && inst_type="directory"

if [ $noexecute -eq 1 ]; then
	#
	# The zone doesn't have to exist when the -n option is used, so do
	# this work early.
	#

	# XXX There is no sw validation for IPS right now, so just pretend
	# everything will be ok.
	EXIT_CODE=$ZONE_SUBPROC_OK
	exit $ZONE_SUBPROC_OK
fi

LOGFILE=$(/usr/bin/mktemp -t -p /var/tmp $ZONENAME.attach_log.XXXXXX)
if [[ -z "$LOGFILE" ]]; then
	fatal "$e_tmpfile"
fi
exec 2>>"$LOGFILE"

log "$m_attach_log" "$LOGFILE"

#
# TODO - once sxce is gone, move the following block into
# usr/lib/brand/shared/common.ksh code to share with other brands using
# the same zfs dataset logic for attach. This currently uses get_current_gzbe
# so we can't move it yet since beadm isn't in sxce.
#

# Validate that the zonepath is not in the root dataset.
pdir=`dirname $ZONEPATH`
get_zonepath_ds $pdir
fail_zonepath_in_rootds $ZONEPATH_DS

EXIT_CODE=$ZONE_SUBPROC_NOTCOMPLETE

if [[ "$install_media" == "-" ]]; then
	#
	# Since we're using a pre-existing dataset, the dataset currently
	# mounted on the {zonepath}/root becomes the active dataset.  We
	# can't depend on the usual dataset attributes to detect this since
	# the dataset could be a detached zone or one that the user set up by
	# hand and lacking the proper attributes.  However, since the zone is
	# not attached yet, the 'install_media == -' means the dataset must be
	# mounted at this point.
	#
	ACTIVE_DS=`mount -p | nawk -v zroot=$ZONEROOT '{
	    if ($3 == zroot && $4 == "zfs")
		    print $1
	}'`

	[[ -z "$ACTIVE_DS" ]] && fatal "$f_no_active_ds_mounted" $ZONEROOT

	# Set up proper attributes on the ROOT dataset.
	get_zonepath_ds $ZONEPATH
	zfs list -H -t filesystem -o name $ZONEPATH_DS/ROOT >/dev/null 2>&1
	(( $? != 0 )) && fatal "$f_no_active_ds"

	# need to ensure zoned is off to set mountpoint=legacy.
	zfs set zoned=off $ZONEPATH_DS/ROOT
	(( $? != 0 )) && fatal "$f_ds_config" $ZONEPATH_DS/ROOT "zoned=off"

	zfs set mountpoint=legacy $ZONEPATH_DS/ROOT
	(( $? != 0 )) && fatal "$f_ds_config" $ZONEPATH_DS/ROOT \
	    "mountpoint=legacy"
	zfs set zoned=on $ZONEPATH_DS/ROOT
	(( $? != 0 )) && fatal "$f_ds_config" $ZONEPATH_DS/ROOT "zoned=on"

	#
	# We're typically using a pre-existing mounted dataset so setting the
	# following propery changes will cause the {zonepath}/root dataset to
	# be unmounted.  However, a p2v with an update-on-attach will have
	# created the dataset with the correct properties, so setting these
	# attributes won't unmount the dataset.  Thus, we check the mount
	# and attempt the remount if necessary.
	#
	get_current_gzbe
	zfs set $PROP_PARENT=$CURRENT_GZBE $ACTIVE_DS
	(( $? != 0 )) && fatal "$f_ds_config" $ACTIVE_DS \
	    "$PROP_PARENT=$CURRENT_GZBE"
	zfs set $PROP_ACTIVE=on $ACTIVE_DS
	(( $? != 0 )) && fatal "$f_ds_config" $ACTIVE_DS "$PROP_ACTIVE=on"
	zfs set canmount=noauto $ACTIVE_DS
	(( $? != 0 )) && fatal "$f_ds_config" $ACTIVE_DS "canmount=noauto"
	zfs set zoned=off $ACTIVE_DS
	(( $? != 0 )) && fatal "$f_ds_config" $ACTIVE_DS "zoned=off"
	zfs inherit mountpoint $ACTIVE_DS
	(( $? != 0 )) && fatal "$f_ds_config" $ACTIVE_DS "'inherit mountpoint'"
	zfs inherit zoned $ACTIVE_DS
	(( $? != 0 )) && fatal "$f_ds_config" $ACTIVE_DS "'inherit zoned'"

	mounted_ds=`mount -p | nawk -v zroot=$ZONEROOT '{
	    if ($3 == zroot && $4 == "zfs")
		    print $1
	}'`

	if [[ -z $mounted_ds ]]; then
		mount -F zfs $ACTIVE_DS $ZONEROOT || fatal "$f_zfs_mount"
	fi
else
	#
	# Since we're not using a pre-existing ZFS dataset layout, create
	# the zone datasets and mount them.  Start by creating the zonepath
	# dataset, similar to what zoneadm would do for an initial install.
	#
	zds=$(zfs list -H -t filesystem -o name $pdir 2>/dev/null)
	if (( $? == 0 )); then
		pnm=$(/usr/bin/basename $ZONEPATH)
		# The zonepath dataset might already exist.
		zfs list -H -t filesystem -o name $zds/$pnm >/dev/null 2>&1
		if (( $? != 0 )); then
			zfs create "$zds/$pnm"
			(( $? != 0 )) && fatal "$f_zfs_create"
			vlog "$m_zfs"
		fi
	fi

	create_active_ds
fi

#
# The zone's datasets are now in place.
#

log "$m_attach_root" "$ZONEROOT"
# note \n to add whitespace
log "$m_attach_ds\n" "$ACTIVE_DS"

install_image "$inst_type" "$install_media"

#
# End of TODO block to move to common code.
#

#
# Perform a sanity check to confirm that the image is not a global zone.
#
VARIANT=variant.opensolaris.zone
variant=$(LC_ALL=C $PKG -R $ZONEROOT variant -H $VARIANT)
[[ $? -ne 0 ]] && fatal "$f_sanity_variant" $VARIANT

echo $variant | IFS=" " read variantname variantval
[[ $? -ne 0 ]] && fatal "$f_sanity_variant"

# Check that we got the output we expect...
[[ $variantname = "$VARIANT" ]] || fatal "$f_sanity_variant" $VARIANT

# Check that the variant is non-global, else fail
[[ $variantval = "nonglobal" ]] || fatal "$f_sanity_global" $VARIANT $variantval

# We would like to ensure that our NGZ publishers are a superset of
# those in the GZ. We do this by building a list of all publishers in
# the GZ. We then process this list in the NGZ, first removing (if
# present) and then installing all publishers in this list. Other
# publisher, i.e. those not in the GZ list, are left as is.

#
# Gather all the publisher details for the global zone
#
gather_zone_publisher_details $PKG_IMAGE gz_publishers

#
# Get the preferred publisher for the global zone
# If we were not able to get the zone's preferred publisher, complain.
#
gz_publisher_pref=$(get_preferred_publisher gz_publishers)

if [[ $? -ne 0 ]]; then
	fail_usage "$f_no_pref_publisher" "global"
fi

vlog "Preferred global publisher: $gz_publisher_pref"

#
# Try to find the "entire" incorporation's FMRI in the gz.
#
gz_entire_fmri=$(get_entire_incorp)

#
# If entire isn't installed, create an array of global zone core-os
# incorporations.
#
if [[ -z $gz_entire_fmri ]]; then
	gather_incorporations gz_incorporations
fi

#
# We're done with the global zone: switch images to the non-global
# zone.
#
PKG_IMAGE="$ZONEROOT"

#
# Try to find the "entire" incorporation's FMRI in the ngz.
#
ngz_entire_fmri=$(get_entire_incorp)

[[ -n $gz_entire_fmri ]] && log "$m_gzinc" "$gz_entire_fmri"
[[ -n $ngz_entire_fmri ]] && log "$m_zinc" "$ngz_entire_fmri"

#
# Create the list of incorporations we wish to install/update in the
# ngz.
#
typeset -n incorp_list
if [[ -n $gz_entire_fmri ]]; then
    incorp_list=gz_entire_fmri
else
    incorp_list=gz_incorporations
fi

#
# If there is a cache, use it.
#
if [[ -f /var/pkg/pkg5.image && -d /var/pkg/publisher ]]; then
	PKG_CACHEROOT=/var/pkg/publisher
	export PKG_CACHEROOT
	log "$m_cache" "$PKG_CACHEROOT"
fi

log "$m_updating"

#
# The NGZ publishers must be a superset of the GZ publisher. Process
# the GZ publishers and make the NGZ publishers match them.
# You can't remove a preferred publisher, so temporarily create
# a preferred publisher
RANDOM=$$

ZNAME=za$RANDOM

LC_ALL=C $PKG set-publisher --no-refresh -P -g http://localhost:10000 $ZNAME
for key in ${!gz_publishers[*]}; do
	typeset newloc=""

	args=$(print_publisher_pkg_defn gz_publishers $key)

	# Copy credentials from global zone.
	safe_dir var
	safe_dir var/pkg

	eval publisher="${gz_publishers[$key]}"
	if [[ ${publisher.keyfile} != "None" || \
	    ${publisher.certfile} != "None" ]]; then
		if [[ -e $ZONEROOT/$KEYDIR ]]; then
			safe_dir $KEYDIR
		else
			mkdir -m 755 $ZONEROOT/$KEYDIR
		fi
	fi

	if [[ ${publisher.keyfile} != "None" ]]; then
		relnewloc="$KEYDIR/$(basename ${publisher.keyfile})"
		newloc="$ZONEROOT/$relnewloc"
		safe_copy ${publisher.keyfile} $newloc
		chmod 644 $newloc
		chown -h root:root $newloc
		args="$args -k $relnewloc"
	fi
	if [[ ${publisher.certfile} != "None" ]]; then
		relnewloc="$KEYDIR/$(basename ${publisher.certfile})"
		newloc="$ZONEROOT/$relnewloc"
		safe_copy ${publisher.certfile} $newloc
		chmod 644 $newloc
		chown -h root:root $newloc
		args="$args -c $relnewloc"
	fi
	LC_ALL=C $PKG unset-publisher $key >/dev/null 2>&1
	LC_ALL=C $PKG set-publisher $args $key
	
done

#
# Now remove our temporary publisher
#
LC_ALL=C $PKG unset-publisher $ZNAME

#
# Bring the ngz entire incorporation into sync with the gz as follows:
# - First compare the existence of entire in both global and non-global
#   zone and update the non-global zone accordingly.
# - Then, if updates aren't allowed check if we can attach because no
#   updates are required. If we can, then we are finished.
# - Finally, we know we can do updates and they are required, so update
#   all the non-global zone incorporations using the list we gathered
#   from the global zone earlier.
#
if [[ -z $gz_entire_fmri && -n $ngz_entire_fmri ]]; then
	if [[ $allow_update == 1 ]]; then
		LC_ALL=C $PKG uninstall entire || pkg_err_check "$f_update"
	else
		log "\n$m_need_update" "$ZONENAME"
		EXIT_CODE=$ZONE_SUBPROC_NOTCOMPLETE
		exit $EXIT_CODE
    fi
fi

if [[ $allow_update == 0 ]]; then
	LC_ALL=C $PKG install --accept --no-refresh -n $incorp_list
	if [[ $? == 4 ]]; then
		log "\n$m_complete"
		EXIT_CODE=$ZONE_SUBPROC_OK
		exit $EXIT_CODE
	else
		log "\n$m_need_update" "$ZONENAME"
		EXIT_CODE=$ZONE_SUBPROC_NOTCOMPLETE
		exit $EXIT_CODE
	fi
fi

#
# If the NGZ doesn't have entire, but the GZ does, then we have to install
# entire twice. First time we don't specify a version and let constraining
# incorporations determine the version. Second time, we try to install the
# same version as we have in the GZ.
#
if [[ -n $gz_entire_fmri && -z $ngz_entire_fmri ]]; then
	LC_ALL=C $PKG install --accept --no-refresh entire  || \
	    pkg_err_check "$f_update"
fi

LC_ALL=C $PKG install --accept --no-refresh $incorp_list  || \
    pkg_err_check "$f_update"

log "\n$m_sync_done"
log "$m_complete"

EXIT_CODE=$ZONE_SUBPROC_OK
exit $ZONE_SUBPROC_OK
