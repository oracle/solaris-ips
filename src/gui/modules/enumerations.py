#!/usr/bin/python
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
# Copyright (c) 2010, Oracle and/or its affiliates.  All rights reserved.
#

"""
This module consists of user readable enumerations for the data models
used in the IPS GUI
"""

#Application List
(
MARK_COLUMN,
STATUS_ICON_COLUMN,
NAME_COLUMN,
DESCRIPTION_COLUMN,
STATUS_COLUMN,
STEM_COLUMN,
ACTUAL_NAME_COLUMN,
IS_VISIBLE_COLUMN,       # True indicates that the package is visible in ui
CATEGORY_LIST_COLUMN,    # list of categories to which package belongs
PUBLISHER_COLUMN,        # Publisher for this package
PUBLISHER_PREFIX_COLUMN, # Publisher prefix for this package
RENAMED_COLUMN,          # True indicates this package has been
) = range(12)

#Categories
(
CATEGORY_ID,
CATEGORY_NAME,
CATEGORY_VISIBLE_NAME,
CATEGORY_DESCRIPTION,
SECTION_LIST_OBJECT,     #List with the sections to which category belongs 
CATEGORY_IS_VISIBLE,
) = range(6)

#Sections
(
SECTION_ID,
SECTION_NAME,
SECTION_ENABLED,
) = range(3)

#Filter
(
FILTER_ID,
FILTER_ICON,
FILTER_NAME,
) = range(3)

#Filter
(
FILTER_ALL,
FILTER_INSTALLED,
FILTER_UPDATES,
FILTER_NOT_INSTALLED,
FILTER_SEPARATOR,
FILTER_SELECTED,
) = range(6)

#Search
(
SEARCH_ID,
SEARCH_ICON,
SEARCH_NAME,
) = range(3)

#Repositories switch
(
REPOSITORY_ID,
REPOSITORY_DISPLAY_NAME,
REPOSITORY_PREFIX,
REPOSITORY_ALIAS,
) = range(4)

(
INSTALL_UPDATE,
REMOVE,
IMAGE_UPDATE
) = range(3)

# Info Cache entries
(
INFO_GENERAL_LABELS,
INFO_GENERAL_TEXT,
INFO_INSTALLED_TEXT,
INFO_DEPEND_INFO,
INFO_DEPEND_DEPEND_INFO,
INFO_DEPEND_DEPEND_INSTALLED_INFO
) = range(6)

# Install/Update/Remove confirmation
(
CONFIRM_NAME,
CONFIRM_PUB,
CONFIRM_DESC,
CONFIRM_STATUS,
CONFIRM_STEM
) = range(5)

#Repository action
(
ADD_PUBLISHER,
MANAGE_PUBLISHERS
) = range(2)

# Publisher List in Manage Publishers Dialog
(
PUBLISHER_PRIORITY,
PUBLISHER_PRIORITY_CHANGED,
PUBLISHER_NAME,
PUBLISHER_ALIAS,
PUBLISHER_ENABLED,
PUBLISHER_STICKY,
PUBLISHER_OBJECT,
PUBLISHER_ENABLE_CHANGED,
PUBLISHER_STICKY_CHANGED,
PUBLISHER_REMOVED,
) = range(10)

# Publisher Priority
(
PUBLISHER_MOVE_BEFORE,
PUBLISHER_MOVE_AFTER,
) = range(2)

# Return values from /usr/lib/pm-checkforupdates
(
UPDATES_AVAILABLE,
NO_UPDATES_AVAILABLE,
UPDATES_UNDETERMINED
) = range(3)

# Search Text Style
(
SEARCH_STYLE_NORMAL,
SEARCH_STYLE_PROMPT
) = range(2)

# Versions
(
VERSION_ID,
VERSION_DISPLAY_NAME,
VERSION_NAME,
VERSION_STATUS
) = range(4)
