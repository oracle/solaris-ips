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

"""
This module consists of user readable enumerations for the data models
used in the IPS GUI
"""

(
MARK_COLUMN,
STATUS_ICON_COLUMN,
NAME_COLUMN,
DESCRIPTION_COLUMN,
STATUS_COLUMN,
FMRI_COLUMN,             # This should go once, the api will be fully functionall
STEM_COLUMN,
DISPLAY_NAME_COLUMN,
IS_VISIBLE_COLUMN,       # True indicates that the package is visible in ui
CATEGORY_LIST_COLUMN,    # list of categories to which package belongs
AUTHORITY_COLUMN,        # Authority for this package
) = range(11)

#For the STATUS_COLUMN
(
INSTALLED,
NOT_INSTALLED,
UPDATABLE,
) = range(3)

#Categories
(
CATEGORY_ID,
CATEGORY_NAME,
CATEGORY_DESCRIPTION,
SECTION_LIST_OBJECT,     #List with the sections to which category belongs 
) = range(4)

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
REPOSITORY_NAME,
) = range(2)

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
INFO_DEPEND_DEPEND_INFO
) = range(5)

#Repository action
(
ADD_PUBLISHER,
MANAGE_PUBLISHERS
) = range(2)

# Publisher List in Manage Publishers Dialog
(
PUBLISHER_PRIORITY,
PUBLISHER_NAME,
PUBLISHER_ALIAS,
PUBLISHER_ENABLED,
PUBLISHER_PREFERRED,
PUBLISHER_OBJECT,
PUBLISHER_ENABLE_CHANGED,
PUBLISHER_REMOVED,
) = range(8)

# Repositories List in the Modify Publisher Dialog
(
MREPOSITORY_NAME,
MREPOSITORY_ACTIVE,
MREPOSITORY_REGISTERED,
MREPOSITORY_OBJECT,
MREPOSITORY_PUB_OBJECT,
) = range(5)
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
