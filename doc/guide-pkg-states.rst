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

.. _Package States:

Package states
==============

By a *package state*, we mean an image's recorded state for a particular
package version.  We might also refer to these as "client states".
Within an image, each package version can have only one state, as given
in the following diagram::

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

