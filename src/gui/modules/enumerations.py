#!/usr/bin/python2.4
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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

(
    MARK_COLUMN,
    STATUS_ICON_COLUMN,
    ICON_COLUMN,
    NAME_COLUMN,
    INSTALLED_VERSION_COLUMN,
    INSTALLED_OBJECT_COLUMN, # This will speed up a little bit
    LATEST_AVAILABLE_COLUMN,
    RATING_COLUMN,           # Not in revision 1
    DESCRIPTION_COLUMN,
    PACKAGE_OBJECT_COLUMN,   # pkg.client.fmri.py module
    IMAGE_OBJECT_COLUMN,     # This takes not much memory, so we can use that :)
    IS_VISIBLE_COLUMN,       # True indicates that the package is visible in ui
    CATEGORY_LIST_OBJECT     # list of categories to which package belongs
) = range(13)

#Categories
(
    CATEGORY_NAME,
    CATEGORY_DESCRIPTION,
    CATEGORY_ICON,
    CATEGORY_VISIBLE,
    SECTION_LIST_OBJECT,     #List with the sections to which category belongs 
) = range(5)

#Sections
(
    SECTION_NAME,
) = range(1)

#Filter
(
    FILTER_NAME,
) = range(1)

#Repositories switch
(
    REPOSITORY_NAME,
) = range(1)
