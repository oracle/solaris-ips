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

pkg
MULTI-PLATFORM

The core pkg(5) technology is generic enough to be useful across multiple platforms
(e.g. Windows and Linux). The full range of supported platforms are listed here:
http://wikis.sun.com/display/IpsBestPractices/OS+Platform+Support

The following modules within the pkg(5) source base are multi-platform:
    - the CLIs (client.py, publish.py, depot.py, pull.py)
    - src/modules (the core of pkg(5))
    - src/tests (except the CLI tests do not run on Windows)
    - src/man
    - src/web
    - src/po (except for the GUI messages which are OpenSolaris-only)

The following modules are not multi-platform (only supported on OpenSolaris):
    - src/brand
    - src/gui, src/um and the start scripts (packagemanger.py, updatemanager.py,
        and updatemanagernotifier.py)
    - pkgdefs
    - SMF support: src/svc-pkg-depot, src/pkg-server.xml, src/pkg-update.xml
    - src/util


The following modules are only used for non-OpenSolaris support:
    - src/scripts

Multi-platform support is focused on providing support for user images as the 
operating system software is not delivered for other platforms using pkg(5).

Development best practices for writing multi-platform pkg(5) code are available
here: http://opensolaris.org/os/project/pkg/devinfo/bestpractices/.

Build instructions for non-OpenSolaris platforms are here:
http://wiki.updatecenter.java.net/Wiki.jsp?page=IPSHOWTO

Information about using multi-platform pkg(5) and pre-built binaries
are available here: http://wikis.sun.com/display/IpsBestPractices
