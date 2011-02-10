#!/bin/sh
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
# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.
#

# This script generates l10n.py from opensolaris.org.sections
CATEGORY_FILE=../../util/opensolaris.org.sections
OUTPUT_FILE=l10n.py
LANG=C

export LANG

printf "%s\n" "#!/usr/bin/env python" > $OUTPUT_FILE
head -24 $0 | tail -23 >> $OUTPUT_FILE

echo "
# The following categories are shown in GUI.

def N_(message): return message

l10n_categories = [" \
>> $OUTPUT_FILE

cat $CATEGORY_FILE | grep "^category[ ]*=" |\
  sed -e "s|category[ ]*=[ ]*\(.*\)|\1|" | tr "," "\n" | sort | uniq |\
  awk '{printf ("  N_(\"%s\"),\n", $0)}' \
>> $OUTPUT_FILE

printf "%s\n" "  None" >> $OUTPUT_FILE
printf "]"             >> $OUTPUT_FILE
