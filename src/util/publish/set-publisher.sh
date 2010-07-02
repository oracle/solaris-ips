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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

# set-publisher.sh takes a set of repositories and uses the rules
# in set-publisher.transforms to change the consolidation-specific
# publisher names to opensolaris.org.
#
# It requires 3 options:
#   -b <build>
#     e.g. -b 136, to make sure to publish only packages from the
#     specified build.  Packages from any other builds contained in the
#     repository are simply discarded.  This allows us to ignore
#     packages obsoleted in a previous build without requiring that
#     the consolidations strip them.
#
#   -d recv_dir
#     A scratch directory to use for pkgrecv.  If it's not initially
#     empty other packages there will be published at publication time.
#
#   -p repository
#     A file: or http: repository path to publish the results.  This
#     repository should have already been created with opensolaris.org
#     as its publisher.

recv_dir=
publish_repo=
only_this_build=
while getopts b:d:p: opt
do
	case $opt in
	b)	only_this_build="$OPTARG";;
	d)	recv_dir="$OPTARG";;
	p)	publish_repo="$OPTARG";;
	?)	print "Usage: $0: -b build -d directory -p publish_repo input_repos" 
		exit 2;;
	esac
done
shift $(expr $OPTIND - 1)

if [[ -z $only_this_build || -z $recv_dir || -z $publish_repo ]]; then
	echo "one of the options not specified."
	print "Usage: $0: -b build -d directory -p publish_repo input_repos" 
	exit 2
fi
if [ ! -d $recv_dir ]; then
	mkdir $recv_dir
	if [ $? -ne 0 ]; then
		echo "couldn't mkdir $recv_dir"
		exit 1
	fi
fi

# Iterate through the repositories, and pkgrecv the contents of each
# of them.
for repo in $*; do
	echo $repo
	pkglist=$(pkgrecv -s $repo -n)
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

	echo "pkgrecv -s $repo -d $recv_dir $modified_pkglist"
	pkgrecv -s $repo -d $recv_dir $modified_pkglist
	if [ $? -ne 0 ]; then
		echo "error from pkgrecv -s $repo -d $recv_dir $modified_pkglist"
		exit 1
	fi
done

# Replace the publisher name with opensolaris.org and publish.
for pkg in $(echo $recv_dir/*/*); do
	./pkgmogrify.py -O $pkg/manifest $pkg/manifest ./set-publisher.transforms
	./pkg_publish $pkg $publish_repo
done
