#!/usr/bin/ksh -pf
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

# This is necessary to ensure the resulting permissions on the repository
# directories and files are correct.
umask 0022

PUBLISHER="Copyright $(date +'%Y') Sun Microsystems, Inc.  All rights reserved.\nUse is subject to license terms."

usage() {
        cat << EOF
${0##*/}: $1

This utility will take a specified directory and use its contents
to create an ISO9660 image file using Rock Ridge Extensions using
the mkisofs utility.

Usage:
  ${0##*/} [-s src_path] [-d filename]
Options:
  -a appid      The identifier for the application that the
                ISO image will contain (e.g. 'Solaris 10 GA').
                Limit of 128 characters.
  -b pubid      The identifier for the publisher of the ISO
                image.  Limit of 128 characters.  If not
                provided, this will default to:
                $PUBLISHER
  -d filename   The pathname to write the resulting ISO image
                to.
  -i volid      The ID (volume name or label) of the ISO
                image (e.g. 'sol_10_ga').  Limit of 32
                characters.
  -p prepid     The identifier of the preparer of the ISO
                image (e.g. 'Joe Smith (joe.smith@sun.com').
                Limit of 128 characters.
  -s src_path   The name of a directory to use for the
                contents of the ISO image.  If not provided,
                and \$SRC is not defined, the current directory
                will be used.
  -x glob       Exclude glob from being included in the ISO
                image.  glob is a shell wild-card-style pattern
                that must match the last part of a pathname or
                the entire pathname.  Multiple globs may be
                excluded by specifying the option multiple
                times.
  -h            Display this usage message
Environment:
  SRC     Source directory
  DEST    Destination filename
EOF

        if [[ -n "$1" ]]; then
                exit 2
        fi
}

if [[ $# -eq 0 ]]; then
        usage
        exit 2
fi

while getopts ':a:b:d:i:p:s:x:h?' OPT; do
        case "$OPT" in
                a)      APPID=$OPTARG
                        ;;
                b)      PUBLISHER=$OPTARG
                        ;;
                d)      DEST=$OPTARG
                        ;;
                i)      VOLID=$OPTARG
                        ;;
                p)      PREPARER=$OPTARG
                        ;;
                s)      SRC=$OPTARG
                        ;;
                x)      EXCLUDE="${EXCLUDE}-x ${OPTARG} "
                        ;;
                h|\?)   usage
                        exit 0
                        ;;
                *)      usage "-${OPTARG} requires an argument"
        esac
done

if [[ -z $APPID ]]; then
        usage "You must specify an Application ID with -a."
fi

if [[ -z $DEST ]]; then
        usage "You must specify a destination filename with -d."
fi

if [[ -z $PREPARER ]]; then
        usage "You must specify a preparer with -p."
fi

if [[ -z $SRC ]]; then
        SRC=.
fi

if [[ -z $VOLID ]]; then
        usage "You must specify a Volume ID with -i."
fi

mkisofs \
        -o "$DEST" \
        -l \
        -no-limit-pathtables \
        -allow-leading-dots \
        -A "$APPID" \
        -publisher "$PUBLISHER" \
        -p "$PREPARER" \
        -R \
        -uid 0 \
        -gid 0 \
        -V "$VOLID" \
        -v \
        $EXCLUDE \
        $SRC
