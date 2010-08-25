#!/bin/ksh
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
# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.
#
# ##########################################################################
# This script is run as part of a cron job at 0:30, 9:30, 12:30, 18:30, 21:30
# 1. Refresh the IPS catalog
#
# 2. Call /usr/lib/pm-updatemanager --checkupdates-all to check and cache whether updates
#    are available. The generated cache is checked by /usr/lib/updatemanagernotifier,
#    which in turn notifies the user via a popup and notification panel icon.
#
# 3. Fetch updates to Packagemanager's Start Page files:
#    startpagebase-<locale prefix>.tar.gz
#
# From the URL in the specifed Packagemanager Gconf key:
#    /apps/packagemanager/preferences/startpage_url
#
# For all en_* locales the file checked for is:
#    startpagebase-C.tar.gz
# For other locales the file checked is based on locale prefix:
#    E.g. fr_BE.UTF-8 = startpagebase-fr.tar.gz
#    E.g. zh_TW.UTF-8, zh_CN.UTF-8, zh_HK.UTF-8 = startpagebase-zh.tar.gz
#         within startpagebase-zh.tar.gz, there should be 3 directories:
#         zh_TW, zh_CN and zh_HK to support all three zh* locales.
#
# There may be more then one supported locale directory within tarball, which are
# being updated to:
#    /var/pkg/gui/cache/startpagebase/<locale>  
#
# Note: script also checks for "C" locale updates if there is no Start Page
# file for the current system locale
#
# ##########################################################################

# Refresh the IPS catalog
fmri=svc:/application/pkg/update
image_dir=`svcprop -p update/image_dir $fmri`

# We want to limit the number of times we hit the servers, but our
# calculations are all based on the canonical crontab entry.  If the
# user has modified that, then use the times as they specified.
cronentry=$(crontab -l | grep update-refresh.sh)
if [[ $cronentry == "30 0,9,12,18,21 * * * "* ]]; then
	# When did we last run, and how many times have we tried since?
	lastrun=$(svcprop -p update/lastrun $fmri 2> /dev/null)

	# Easiest way to get seconds since the epoch.
	now=$(/usr/bin/python -ESc 'import time; print int(time.time())')

	# The canonical crontab entry runs this script five times a day,
	# seven days a week.  We want it to complete roughly once a week.
	# But because we're not at 100% after even two weeks, we increase
	# the chance of success every fifth of a day until we're at 100%.
	rolls=$(((now - lastrun) / 17280))
	(( rolls > 34 )) && rolls=34
	chance=$((35 - rolls))
	roll=$((RANDOM % chance))
	(( roll > 0 )) && exit 0

	# Otherwise, we will run, so record the current time for later.
	cat <<-EOF | svccfg -s pkg/update
	setprop update/lastrun = integer: $now
	select default
	refresh
	EOF
fi

# Wait a random part of 30 minutes so servers do not get hit all at once
let dither=1800*$RANDOM
let dither=dither/32767
sleep $dither

cd $image_dir

pkg refresh 2>/dev/null

# Check and cache whether updates are available
/usr/bin/pm-updatemanager --nice --checkupdates-all --image-dir $image_dir

# Fetch updates to Packagemanager's Start Page files
TAR="/usr/gnu/bin/tar"
WGET="/usr/bin/wget"
GREP="/usr/gnu/bin/grep"
PATH="/usr/bin"

DEFAULT_LOCALE="C"
SUPPORTED_LOCALES="ar cs fr it nl sv zh_TW C de hu ja pt_BR zh_CN ca es id ko ru zh_HK"  
LOCALE_FILE="/etc/default/init"
FILE_PREFIX="startpagebase-"
FILE_SUFFFIX=".tar.gz"
DEBUG=0

#Debug output
debug() {
	if [ "$DEBUG" != "0" ];	then
	  	echo $1
	fi
}

CACHE_DIR="/var/pkg/gui_cache/startpagebase"
if mkdir -p $CACHE_DIR; then
	debug "Using CACHE_DIR: $CACHE_DIR"
else
	exit 0
fi
TMP_SYS_DIR="/var/pkg/gui_cache/"
TMP_BASE_DIR="startpagebase.$$"
TMP_DIR=$TMP_SYS_DIR$TMP_BASE_DIR
if mkdir $TMP_DIR; then
	debug "Using TMP_DIR: $TMP_DIR"
else
	exit 0
fi
trap "cd $TMP_SYS_DIR; rm -rf $TMP_BASE_DIR" 0 2 15

# Setup in setlocale_dep_variables()
BASEURL=""
LOCALE=""
LOCALE_ROOT=""
FILE=""
UNPACKED_DIR=""
URL=""
UPTODATE=""

#Fetch the compressed file if modified
download() {
	cd $CACHE_DIR
	ret=`LC_ALL="C" $WGET -N $URL 2>&1` #Need returned string in C locale
	if [ "$?" != "0" ]; then
	  	debug "Err: fetching $URL"
	  	return 1
	fi

	UPTODATE=`echo "$ret" | $GREP "not retrieving"`
	if [ "$UPTODATE" != "" ]; then
	  	debug "Uptodate: no need to get $URL"
	  	return 1
	fi
	return 0
}

#Unpack updates
unpack() {
	if [ -d "$TMP_DIR/$UNPACKED_DIR" ]; then
		rm $TMP_DIR/$UNPACKED_DIR 2>&1
	fi

	cp $FILE $TMP_DIR 2>&1
	if [ "$?" != "0" ]; then
	  	debug "Err: unpacking $FILE"
	  	return 1
	fi

	cd $TMP_DIR
	$TAR -xzf $FILE 2>&1
	if [ "$?" != "0" ]; then
	  	debug "Err: unpacking $FILE"
	  	return 1
	fi
	return 0
}

#Install Updates
install() {
	if [ -d "$CACHE_DIR/$UNPACKED_DIR" ]; then
		mv $CACHE_DIR/$UNPACKED_DIR $CACHE_DIR/$UNPACKED_DIR.$$ 2>&1
		if [ "$?" != "0" ]; then
		  	debug "Err: moving $CACHE_DIR/$UNPACKED_DIR"
		  	return 1
		fi
	fi

	mv $TMP_DIR/$UNPACKED_DIR $CACHE_DIR 2>&1
	if [ "$?" != "0" ]; then
	  	debug "Err: moving $TMP_DIR/$UNPACKED_DIR to $CACHE_DIR"
	  	mv $CACHE_DIR/$UNPACKED_DIR.$$ $CACHE_DIR/$UNPACKED_DIR 2>&1
	  	return 1
	fi


	if [ -d "$CACHE_DIR/$UNPACKED_DIR.$$" ]; then
		rm -rf $CACHE_DIR/$UNPACKED_DIR.$$ 2>&1
		if [ "$?" != "0" ]; then
		  	debug "Err: removing $CACHE_DIR/$UNPACKED_DIR.$$"
		  	return 1
		fi
	fi
	return 0
}

#Get Base URL
getbaseurl() {
	BASEURL=`gconftool-2 -g '/apps/packagemanager/preferences/startpage_url' 2>/dev/null`
	if [ "$BASEURL" = '' ]; then
		return 1
	fi
	return 0
}

#Get Default locale
getlocale() {
	def_locale=`awk -F"=" '$1=="LANG" {print $2}' $LOCALE_FILE`
	locale_prefix=${def_locale%.*}
	locale_root_prefix=${locale_prefix%_*}

	LOCALE=$locale_prefix
	LOCALE_ROOT=$locale_root_prefix
}

#Set variables that have a locale component
setlocale_dep_variables() {
	FILE=$FILE_PREFIX$LOCALE$FILE_SUFFFIX
	UNPACKED_DIR=$LOCALE
	URL=$BASEURL/$FILE
	debug "Locale: $LOCALE Download File: $FILE"
}

#Download updates for the default locale
download_for_default_locale() {
        LOCALE=$DEFAULT_LOCALE
        setlocale_dep_variables
        if download; then
                debug "Got: $URL"
                return 0
        fi
        return 1
}

# Main Body
if getbaseurl; then
	debug "Using: $URL"
else
	debug "Empty Update URL"
	exit 0 #Ignoring failure
fi

getlocale
setlocale_dep_variables

# Example: 
#  locale de_DE (root de), try de_DE -> de -> C
#  locale de (root de), try de -> C
if download; then
	debug "Got: $URL"
else
        if [ "$UPTODATE" != "" ] || [ "$LOCALE" = "$DEFAULT_LOCALE" ]; then
                exit 0
        fi
	if [ "$LOCALE" != "$LOCALE_ROOT" ]; then
		LOCALE=$LOCALE_ROOT
		setlocale_dep_variables
		if download; then
			debug "Got: $URL"
		else
                        if [ "$UPTODATE" != "" ]; then
                                exit 0
                        fi
                        if ! download_for_default_locale; then
                                exit 0
                        fi
                fi
        else
                if ! download_for_default_locale; then
                        exit 0
                fi
        fi
fi

if unpack; then
	debug "Unpacked: $FILE"
        for LANGUAGE in $SUPPORTED_LOCALES;
        do
		UNPACKED_DIR=$LANGUAGE
		if install; then
			debug "Installed: $FILE to $CACHE_DIR/$UNPACKED_DIR"
		fi
        done
fi
