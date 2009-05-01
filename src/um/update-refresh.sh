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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

# ##########################################################################
# This script is run as part of a cron job at 0:30, 9:30, 12:30, 18:30, 21:30
# 1. Refresh the IPS catalog
#
# 2. Fetch updates to Packagemanager's Start Page files:
#    startpagebase-<locale prefix>.tar.gz
#
# From the URL in the specifed Packagemanager Gconf key:
#    /apps/packagemanager/preferences/startpage_url
#
# For all en_* locales the file checked for is:
#    startpagebase-C.tar.gz
# For other locales the file checked is based on locale prefix:
#    E.g. fr_BE.UTF-8 = startpagebase-fr.tar.gz
#
# If a new set is obtained for the given locale, the cache files are updated:
#    /var/pkg/gui/cache/startpagebase/<locale>  
#
# Note: script also checks for "C" locale updates if there is no Start Page
# file for the current system locale
#
# ##########################################################################

# Refresh the IPS catalog
fmri=svc:/application/pkg/update
image_dir=`svcprop -p update/image_dir $fmri`

cd $image_dir

pkg refresh 2>/dev/null

# Fetch updates to Packagemanager's Start Page files
TAR="/usr/gnu/bin/tar"
WGET="/usr/bin/wget"
GREP="/usr/gnu/bin/grep"
PATH="/usr/bin"

DEFAULT_LOCALE="C"
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
	if install; then
		debug "Installed: $FILE to $CACHE_DIR/$UNPACKED_DIR"
	fi
fi