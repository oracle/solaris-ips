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

#
# get script name (bname) and path (dname)
#
bname=`basename $0`

#
# common shell script functions
#
. /usr/lib/brand/ipkg/common.ksh
. /usr/lib/brand/shared/uninstall.ksh

#
# options processing
#
zonename=$1
if [ -z "$zonename" ]; then
	printf "$f_abort\n" >&2
	exit $ZONE_SUBPROC_FATAL
fi
zonepath=$2
if [ -z "$zonepath" ]; then
	printf "$f_abort" >&2
	exit $ZONE_SUBPROC_FATAL
fi
shift 2

options="FhHnv"
options_repeat=""
options_seen=""

opt_F=""
opt_n=""
opt_v=""

# check for bad or duplicate options
OPTIND=1
while getopts $options OPT ; do
case $OPT in
	\? ) usage_err ;; # invalid argument
	: ) usage_err ;; # argument expected
	* )
		opt=`echo $OPT | sed 's/-\+//'`
		if [ -n "$options_repeat" ]; then
			echo $options_repeat | grep $opt >/dev/null
			[ $? = 0 ] && break
		fi
		( echo $options_seen | grep $opt >/dev/null ) &&
			usage_err
		options_seen="${options_seen}${opt}"
		;;
esac
done

# check for a help request
OPTIND=1
while getopts :$options OPT ; do
case $OPT in
	h|H ) usage
esac
done

# process options
OPTIND=1
while getopts :$options OPT ; do
case $OPT in
	F ) opt_F="-F" ;;
	n ) opt_n="-n" ;;
	v ) opt_v="-v" ;;
esac
done
shift `expr $OPTIND - 1`

[ $# -gt 0 ]  && usage_err

#
# main
#
zoneroot=$zonepath/root

nop=""
if [[ -n "$opt_n" ]]; then
	nop="echo"
	#
	# in '-n' mode we should never return success (since we haven't
	# actually done anything). so override ZONE_SUBPROC_OK here.
	#
	ZONE_SUBPROC_OK=$ZONE_SUBPROC_FATAL
fi

#
# We want uninstall to work in the face of various problems, such as a
# zone with no delegated root dataset or multiple active datasets, so we
# don't use the common functions.  Instead, we do our own work here and
# are tolerant of errors.
#

# get_current_gzbe
CURRENT_GZBE=`/sbin/beadm list -H | /bin/nawk -F\; '{
	# Field 3 is the BE status.  'N' is the active BE.
	if ($3 ~ "N")
		# Field 2 is the BE UUID
		print $2
	}'`

if [ -z "$CURRENT_GZBE" ]; then
	print "$f_no_gzbe"
fi

uninstall_get_zonepath_ds
uninstall_get_zonepath_root_ds

# find all the zone BEs datasets associated with this global zone BE.
unset fs_all
(( fs_all_c = 0 ))
if [ -n "$CURRENT_GZBE" ]; then
	/sbin/zfs list -H -t filesystem -o $PROP_PARENT,name \
	    -r $ZONEPATH_RDS |
	    while IFS="	" read uid fs; do

		# only look at filesystems directly below $ZONEPATH_RDS
		[[ "$fs" != ~()($ZONEPATH_RDS/+([^/])) ]] &&
			continue

		# match by PROP_PARENT uuid
		[[ "$uid" != ${CURRENT_GZBE} ]] &&
			continue

		fs_all[$fs_all_c]=$fs
		(( fs_all_c = $fs_all_c + 1 ))
	done
fi

destroy_zone_datasets

exit $ZONE_SUBPROC_OK
