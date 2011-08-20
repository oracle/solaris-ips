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

#
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.
#

"""
Definitions for values used by the pkg(1) client.
"""

# pkg exit codes
EXIT_OK        =  0 # Command succeeded.
EXIT_OOPS      =  1 # An error occurred.
EXIT_BADOPT    =  2 # Invalid command line options were specified.
EXIT_PARTIAL   =  3 # Multiple ops were requested, but not all succeeded.
EXIT_NOP       =  4 # No changes were made - nothing to do.
EXIT_NOTLIVE   =  5 # The requested op cannot be performed on a live image.
EXIT_LICENSE   =  6 # License acceptance required for requested op.
EXIT_LOCKED    =  7 # Image is currently locked by another process
EXIT_EACCESS   =  8 # Can't access requested image
EXIT_DIVERGED  =  9 # Image is not in sync with its constraints
EXIT_NOPARENT  = 10 # Image is not linked to a parent image
EXIT_PARENTOP  = 11 # Linked operation must be done from parent

# package operations
PKG_OP_ATTACH          = "attach-linked"
PKG_OP_AUDIT_LINKED    = "audit-linked"
PKG_OP_CHANGE_FACET    = "change-facet"
PKG_OP_CHANGE_VARIANT  = "change-variant"
PKG_OP_DETACH          = "detach-linked"
PKG_OP_INSTALL         = "install"
PKG_OP_LIST            = "list"
PKG_OP_LIST_LINKED     = "list-linked"
PKG_OP_PROP_LINKED     = "property-linked"
PKG_OP_REVERT          = "revert"
PKG_OP_SET_MEDIATOR    = "set-mediator"
PKG_OP_SET_PROP_LINKED = "set-property-linked"
PKG_OP_SYNC            = "sync-linked"
PKG_OP_UNINSTALL       = "uninstall"
PKG_OP_UPDATE          = "update"
pkg_op_values          = frozenset([
    PKG_OP_ATTACH,
    PKG_OP_AUDIT_LINKED,
    PKG_OP_CHANGE_FACET,
    PKG_OP_CHANGE_VARIANT,
    PKG_OP_DETACH,
    PKG_OP_INSTALL,
    PKG_OP_LIST,
    PKG_OP_LIST_LINKED,
    PKG_OP_PROP_LINKED,
    PKG_OP_REVERT,
    PKG_OP_SET_MEDIATOR,
    PKG_OP_SET_PROP_LINKED,
    PKG_OP_SYNC,
    PKG_OP_UNINSTALL,
    PKG_OP_UPDATE,
])

API_OP_ATTACH         = "attach-linked"
API_OP_CHANGE_FACET   = "change-facet"
API_OP_CHANGE_VARIANT = "change-variant"
API_OP_DETACH         = "detach-linked"
API_OP_INSTALL        = "install"
API_OP_REVERT         = "revert"
API_OP_SET_MEDIATOR   = "set-mediator"
API_OP_SYNC           = "sync-linked"
API_OP_UNINSTALL      = "uninstall"
API_OP_UPDATE         = "update"
api_op_values         = frozenset([
    API_OP_ATTACH,
    API_OP_CHANGE_FACET,
    API_OP_CHANGE_VARIANT,
    API_OP_DETACH,
    API_OP_INSTALL,
    API_OP_REVERT,
    API_OP_SET_MEDIATOR,
    API_OP_SYNC,
    API_OP_UNINSTALL,
    API_OP_UPDATE
])

API_STAGE_DEFAULT  = "default"
API_STAGE_PUBCHECK = "pubcheck"
API_STAGE_PLAN     = "plan"
API_STAGE_PREPARE  = "prepare"
API_STAGE_EXECUTE  = "execute"
api_stage_values  = frozenset([
    API_STAGE_PUBCHECK,
    API_STAGE_DEFAULT,
    API_STAGE_PLAN,
    API_STAGE_PREPARE,
    API_STAGE_EXECUTE,
])
