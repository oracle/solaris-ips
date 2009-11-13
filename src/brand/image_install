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

#
# image_install is used when installing a zone in a 'p2v' scenario.  In
# this case the zone install hook will branch off to this script which
# is responsible for setting up the physical system image in the zonepath
# and performing the various modifications necessary to enable a physical
# system image to run inside a zone.  This script sets up the image in the
# zonepath then calls the p2v script to modify the image to run in a zone.
#

. /usr/lib/brand/ipkg/common.ksh

m_usage=$(gettext "\n        install {-a archive|-d path} {-p|-u} [-s|-v]")
install_log=$(gettext   "    Log File: %s")

p2ving=$(gettext        "Postprocessing: This may take a while...")
p2v_prog=$(gettext      "   Postprocess: ")
p2v_done=$(gettext      "        Result: Postprocessing complete.")
p2v_fail=$(gettext      "        Result: Postprocessing failed.")
m_postnote3=$(gettext "              Make any other adjustments, such as disabling SMF services\n              that are no longer needed.")

media_missing=\
$(gettext "%s: you must specify an installation source using '-a' or '-d'.")
cfgchoice_missing=\
$(gettext "you must specify -u (sys-unconfig) or -p (preserve identity).")

# Clean up on interrupt
trap_cleanup()
{
	msg=$(gettext "Installation cancelled due to interrupt.")
	log "$msg"

	trap_exit
}

# If the install failed then clean up the ZFS datasets we created.
trap_exit()
{
	# umount any mounted file systems
	[[ -n "$fstmpfile" ]] && umnt_fs

	if (( $zone_is_mounted != 0 )); then
		error "$v_unmount"
		zoneadm -z $ZONENAME unmount
		zone_is_mounted=0
	fi

	if (( $EXIT_CODE != $ZONE_SUBPROC_OK )); then
		/usr/lib/brand/ipkg/uninstall $ZONENAME $ZONEPATH -F
	fi

	exit $EXIT_CODE
}

#
# The main body of the script starts here.
#
# This script should never be called directly by a user but rather should
# only be called by pkgcreatezone to install an OpenSolaris system image into
# a zone.
#

#
# Exit code to return if install is interrupted or exit code is otherwise
# unspecified.
#
EXIT_CODE=$ZONE_SUBPROC_USAGE

zone_is_mounted=0
trap trap_cleanup INT
trap trap_exit EXIT

# If we weren't passed at least two arguments, exit now.
(( $# < 2 )) && exit $ZONE_SUBPROC_USAGE

ZONENAME="$1"
ZONEPATH="$2"
# XXX shared/common script currently uses lower case zonename & zonepath
zonename="$ZONENAME"
zonepath="$ZONEPATH"

ZONEROOT="$ZONEPATH/root"

shift; shift	# remove zonename and zonepath from arguments array

unset inst_type
unset msg
unset silent_mode
unset verbose_mode

#
# It is worth noting here that we require the end user to pick one of
# -u (sys-unconfig) or -p (preserve config).  This is because we can't
# really know in advance which option makes a better default.  Forcing
# the user to pick one or the other means that they will consider their
# choice and hopefully not be surprised or disappointed with the result.
#
unset unconfig_zone
unset preserve_zone

while getopts "a:d:psuv" opt
do
	case "$opt" in
		a)
			if [[ -n "$inst_type" ]]; then
				fatal "$both_kinds" "zoneadm install"
			fi
		 	inst_type="archive"
			install_media="$OPTARG"
			;;
		d)
			if [[ -n "$inst_type" ]]; then
				fatal "$both_kinds" "zoneadm install"
			fi
		 	inst_type="directory"
			install_media="$OPTARG"
			;;
		p)	preserve_zone="-p";;
		s)	silent_mode=1;;
		u)	unconfig_zone="-u";;
		v)	verbose_mode="-v";;
		*)	exit $ZONE_SUBPROC_USAGE;;
	esac
done
shift OPTIND-1

# The install can't be both verbose AND silent...
[[ -n $silent_mode && -n $verbose_mode ]] && \
    fatal "$f_incompat_options" "-s" "-v"

[[ -z $install_media ]] && fatal "$media_missing" "zoneadm install"

# The install can't both preserve and unconfigure
[[ -n $unconfig_zone && -n $preserve_zone ]] && \
    fatal "$f_incompat_options" "-u" "-p"

# Must pick one or the other.
[[ -z $unconfig_zone && -z $preserve_zone ]] && fail_usage "$cfgchoice_missing"

LOGFILE=$(/usr/bin/mktemp -t -p /var/tmp $ZONENAME.install_log.XXXXXX)
[[ -z "$LOGFILE" ]] && fatal "$e_tmpfile"
exec 2>>"$LOGFILE"
log "$install_log" "$LOGFILE"

vlog "Starting pre-installation tasks."

#
# From here on out, an unspecified exit or interrupt should exit with
# ZONE_SUBPROC_NOTCOMPLETE, meaning a user will need to do an uninstall before
# attempting another install, as we've modified the directories we were going
# to install to in some way.
#
EXIT_CODE=$ZONE_SUBPROC_NOTCOMPLETE

# ZONEROOT was created by our caller (pkgcreatezone)

vlog "Installation started for zone \"$ZONENAME\""
install_image "$inst_type" "$install_media"

#
# Run p2v.
#
# Getting the output to the right places is a little tricky because what
# we want is for p2v to output in the same way the installer does: verbose
# messages to the log file always, and verbose messages printed to the
# user if the user passes -v.  This rules out simple redirection.  And
# we can't use tee or other tricks because they cause us to lose the
# return value from the p2v script due to the way shell pipelines work.
#
# The simplest way to do this seems to be to hand off the management of
# the log file to the p2v script.  So we run p2v with -l to tell it where
# to find the log file and then reopen the log (O_APPEND) when p2v is done.
#
log "$p2ving"
vlog "running: p2v $verbose_mode $unconfig_zone $ZONENAME $ZONEPATH"
/usr/lib/brand/ipkg/p2v -l "$LOGFILE" $verbose_mode $unconfig_zone $ZONENAME \
    $ZONEPATH
p2v_result=$?
exec 2>>$LOGFILE

if (( $p2v_result != 0 )); then
	log "$p2v_fail"
	log ""
	log "$install_fail"
	log "$install_log" "$LOGFILE"
	exit $ZONE_SUBPROC_FATAL
fi
vlog "$p2v_done"

zone_is_mounted=1
zoneadm -z $ZONENAME mount -f || fatal "$e_badmount"

safe_copy $LOGFILE $ZONEPATH/lu/a/var/log/$ZONENAME.install$$.log

zoneadm -z $ZONENAME unmount || fatal "$e_badunmount"
zone_is_mounted=0

trap - EXIT
rm -f $LOGFILE

# Mount active dataset on the root.
is_brand_labeled
(( $? == 0 )) && mount_active_ds

log ""
log "$m_complete" ${SECONDS}
printf "$install_log\n" "$ZONEROOT/var/log/$ZONENAME.install$$.log"
printf "$m_postnote\n"
printf "$m_postnote2\n"
printf "$m_postnote3\n"

exit $ZONE_SUBPROC_OK
