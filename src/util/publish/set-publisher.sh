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
# Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.
#

#
# set-publisher.sh takes a set of repositories and uses the rules
# in set-publisher.transforms to change the consolidation-specific
# publisher names to that specified by the transforms file.
#
# There are 3 options:
#   -b <build>
#     e.g. -b 136, to make sure to publish only packages from the
#     specified build.  Packages from any other builds contained in the
#     repository are simply discarded.  This allows us to ignore
#     packages obsoleted in a previous build without requiring that
#     the consolidations strip them.  This option is optional.
#
#   -d recv_dir
#     A scratch directory to use for pkgrecv.  If it's not initially
#     empty other packages there will be published at publication time.
#     This option is required.
#
#   -j <package>
#     A specific package to republish.  More than one package may be
#     specified this way and only those packages will be republished.  This
#     option is optional.
#
#   -p repository
#     A file: or http: repository path to publish the results.  This
#     repository should have already been created with opensolaris.org
#     as its publisher.  This option is required.
#

recv_dir=
publish_repo=
only_this_build=
just_these_pkgs=

while getopts b:d:j:p: opt; do
	case $opt in
	b)	only_this_build="$OPTARG";;
	d)	recv_dir="$OPTARG";;
	j)	just_these_pkgs="$just_these_pkgs $OPTARG";;
	p)	publish_repo="$OPTARG";;
	?)	print "Usage: $0: [-b build] -d directory -p publish_repo "
		    "input_repos" 
		exit 2;;
	esac
done
shift $(expr $OPTIND - 1)

if [[ -z $recv_dir || -z $publish_repo ]]; then
	echo "one of the options not specified."
	print "Usage: $0: [-b build] -d directory -p publish_repo input_repos" 
	exit 2
fi
if [ ! -d $recv_dir ]; then
	mkdir $recv_dir
	if [ $? -ne 0 ]; then
		echo "couldn't mkdir $recv_dir"
		exit 1
	fi
fi

#
# Iterate through the repositories, and pkgrecv the contents of each
# of them.
#
for repo in $*; do
	echo $repo
	pkglist=$(pkgrecv -s $repo --newest)
	if [ $? -ne 0 ]; then
		echo "no suitable response from $repo.  exiting"
		exit 1
	fi

	# Don't recv packages for other builds if $only_this_build is set.
	modified_pkglist=""
	if [ ! -z $only_this_build ]; then
		for pkg in $pkglist; do
			new=$(echo $pkg | grep -- "0.${only_this_build}:")
			modified_pkglist="$modified_pkglist $new"

			if [ -z $new ]; then
				echo "skipping $pkg"
			fi
		done
	else
		modified_pkglist="$pkglist"
	fi

	echo "pkgrecv -s $repo -d $recv_dir --raw $modified_pkglist"
	pkgrecv -s $repo -d $recv_dir --raw $modified_pkglist
	if [ $? -ne 0 ]; then
		echo "error from pkgrecv -s $repo -d $recv_dir --raw" \
		    "$modified_pkglist"
		exit 1
	fi
done

#
# Replace the publisher name as specified by the transforms file and
# publish.
#
if [ -z $just_these_pkgs ]; then
	for pkg in $(echo $recv_dir/*/*); do
		./pkgmogrify.py -O $pkg/manifest $pkg/manifest \
		    ./set-publisher.transforms
		./pkg_publish $pkg $publish_repo
	done
else
	for unquoted in $just_these_pkgs; do
		quoted=$(python -c \
		    'import sys, urllib; print urllib.quote(sys.argv[1], "")' \
		    ${unquoted})
		if [ ! -d ${recv_dir}/${quoted} ]; then
			echo "WARNING: Package \"${unquoted}\" not found"
			continue
		fi
		for pkg in $(echo $recv_dir/${quoted}/*); do
			./pkgmogrify.py -O $pkg/manifest $pkg/manifest \
			    ./set-publisher.transforms
			./pkg_publish $pkg $publish_repo
		done
	done
fi

pkgrepo -s ${publish_repo} refresh
