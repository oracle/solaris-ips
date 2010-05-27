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

PACKAGE STATES
--------------


Server states
~~~~~~~~~~~~~

    We phrase the state machine in terms of a single removal state,
    ABANDONED, which covers both the never-created package instance
    (even with a series of never-finished transaction events).  It may
    be more appropriate to separate the ABANDONED state into
    TX_ABANDONED and PKG_DELETED.

    This leaves us with a state transition diagram like::

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

Client states
~~~~~~~~~~~~~

    Within an image, each package version can have only one state, as
    given in the following diagram::

              0
              |
              v
          IN_CATALOG ---------> OUT_CATALOG
              |                      ^
      +--->---+---<-------+          |
      |       |           |          |
      |       v           |          |
      |   INSTALLED --> FROZEN       |
      |       |                      |
      |       |                      |
      |       v                      |
      +-- PRESERVED                  |
      |       |                      |
      |       |                      |
      |       v                      |
      +-- DELETED -------------------+


    0 -> IN_CATALOG:
        A catalog update with new entries.

    IN_CATALOG:
        An entry for this package is available in the locally installed
        catalog.

    IN_CATALOG -> OUT_CATALOG:
        Entry formerly present on local catalog is no longer published by any
        repository.  (Package never locally installed.)

    OUT_CATALOG:
        Although a formerly known package, no entry for this package is
        available in the locally installed catalog.  An INSTALLED or
        FROZEN package can never be OUT_CATALOG, as the system will
        preserve the entry until the package is no longer in a locally
        public state.

    IN_CATALOG -> INSTALLED:
        Transition takes place on package installation.

    INSTALLED -> FROZEN:
        Transition takes place if manually frozen or frozen by virtue of
	reference from another package group.

    FROZEN -> INSTALLED:
        Manually unfrozen, or unfrozen by reference drop due to
	change in formerly referring package group.

    INSTALLED -> PRESERVED:
        Old copies moved aside during upgrade of package components, but
	not removed.

    PRESERVED -> DELETED:
        Old copies removed.

    DELETED -> OUT_CATALOG:
	Package has been removed from client catalog.  Client software
	would take a PRESERVED package through DELETED automatically to
	reach OUT_CATALOG.

    PRESERVED -> INSTALLED:
        Package reinstalled or reversed.

    DELETED -> INSTALLED:
        Package reinstalled.

    XXX How does the ZFS snapshot (that we might have taken prior to an
    operation) get represented in the state?  Is there an image state
    machine model as well?

    XXX Need a substate of INSTALLED for damaged packages.

    XXX Need a substate of INSTALLED for packages where the global zone
    portion is available, but local installation has not finished.  Can
    we generalize this state for all diskless installs?

