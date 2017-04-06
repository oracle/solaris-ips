.. CDDL HEADER START

.. The contents of this file are subject to the terms of the
   Common Development and Distribution License (the "License").
   You may not use this file except in compliance with the License.

.. You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
   or http://www.opensolaris.org/os/licensing.
   See the License for the specific language governing permissions
   and limitations under the License.

.. When distributing Covered Code, include this CDDL HEADER in each
   file and include the License file at usr/src/OPENSOLARIS.LICENSE.
   If applicable, add the following below this CDDL HEADER, with the
   fields enclosed by brackets "[]" replaced with your own identifying
   information: Portions Copyright [yyyy] [name of copyright owner]

.. CDDL HEADER END


.. Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.

..  :vim set expandtab:

.. _Transaction States:

Transaction states
==================

On a depot open for publication, a new package version may be in the
process of publication.  As the package version is built up, it goes
through a series of *transaction states*.  We may also refer to these as
"server states".

We phrase the state machine in terms of a single removal state,
ABANDONED, which covers both the never-created package instance (even
with a series of never-finished transaction events).  It may be more
appropriate to separate the ABANDONED state into TX_ABANDONED and
PKG_DELETED.

This summary leaves us with a state transition diagram like::

               0
               |
               |
               v
      +--> TRANSACTING --> ABANDONED <--+
      |        |               ^        |
      |        |               |        |
      |        v               |        |
      |    SUBMITTED ----> INCOMPLETE   |
      |        |               |        |
      |        |               |        |
      +--- PUBLISHED <---------+        |
               |                        |
               |                        |
               +------------------------+

    0 -> TRANSACTING
        On initial package creation.

    TRANSACTING -> ABANDONED
        If initial package transaction never committed, commitment
        failed, or explicitly dropped.

    TRANSACTING -> SUBMITTED
        On successful package transaction commitment.  Packages with
        syntax errors or immediate inconsistencies would have failed in
        commitment.

    SUBMITTED:
        The package modified by the transaction is known by a specific
        version.  Its contents are in the repository.

    SUBMITTED -> INCOMPLETE
        If commitment included a deferred inconsistency (package
        dependency is the only expected form), then the package is left
        in the incomplete state.

    INCOMPLETE:
        The package with the specific version string is on the
        incomplete list.  Its contents are in the repository.

    INCOMPLETE -> ABANDONED
        If incomplete package explicitly removed.  (Possibly by
        timeout from arrival in INCOMPLETE.)

    SUBMITTED -> PUBLISHED
        If commitment had no deferred inconsistencies, then the package
        is considered ready for publication.

    INCOMPLETE -> PUBLISHED
        If the deferred inconsistencies, upon reevaluation, are now held
        to no longer be inconsistent, then the package is considered
        ready for publication.

    PUBLISHED:
        The package with the specific version string is present in the
        catalog.  Its contents remain in the repository.

    PUBLISHED -> ABANDONED
        On manual request for package decommissioning, the package will
        be moved to the abandoned state.

    ABANDONED:
        A package with a specific version string is no longer in the
        catalog or on the incomplete list.  Its contents, if they were
        in the repository, should be removed from the repository.

    XXX ARCHIVED might be a special state connected to PUBLISHED, or
    merely a substate.  An archived package has its manifest and
    contents in the repository, but cannot be installed on a client.
    The point of including ARCHIVED packages is to allow client
    deduction on a system not installed by the pkg system.
