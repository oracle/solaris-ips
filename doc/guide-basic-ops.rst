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

.. _Basic operations:

|pkg5| basic operations
=======================

We provide a brief summary of the client operations and their invocation
via |pkg1|, the command line client.  Use of ``PackageManager`` and
other graphical clients is covered by the *Image Packaging System User's
Guide* for |OS_Name|, or by user documentation of the software
component utilizing image packaging.

Listing installed and available packages
----------------------------------------

Since an image may include hundreds of installed packages, and publisher
repositories may contains hundreds or thousands more available packages,
we note that the ``list`` subcommand has a number of options for filtering
these sets of packages into specific groups.  To see the set of packages
currently installed in an image, the plain subcommand is used::

    /usr/bin/pkg list

With the ``-u`` option, ``list`` will restrict its output to those
installed packages for which upgrade--newer versions--are available.
This option is a convenient way to detect if newer software has been
released by one or more of the publishers you've subscribed to.

With the ``-a`` option, ``list`` will list all known packages for the
subscribed publishers.

Installing a package
--------------------

To install a package, we first need to know the name of the package.
Package names are part of a larger set of named entites, called
*fault-managed resources*, and referred to using Fault-Managed Resource
Identifiers (FMRIs).  A package FMRI contains the name of the package's
publisher, a common label for the package, and a version specifier.  For
instance, a valid package FMRI for the Image Packaging System is::

    pkg://opensolaris.org/package/pkg@0.5.11-0.137

which identifies this instance of ``package/pkg`` as the package version
published by ``opensolaris.org`` for Build 137 of the development
version of the operating system.

|pkg1| has an abbreviation expansion algorithm so that shorter strings
than the full FMRI can be used to match package names for installation.

Once we know the FMRI, installation uses the ``install`` subcommand to
|pkg1|::

    $ pfexec pkg install package/pkg

|pkg1| will calculate a valid version of ``package/pkg`` to install
within the image, and then display progress as it retrieves and executes
the actions that make up that version of the package.

Removing a package
------------------

Removal is the opposite of installation, so package removal is done via
the ``uninstall`` subcommand to |pkg1|.  As an example, to remove the
HTML Tidy library::

    $ pfexec pkg uninstall text/tidy

Searching for package content
-----------------------------

Image packaging supports both local and remote search.  Local search is
confined to the packages installed within the image, while remote search
queries repositories associated with the active list of publishers.
The search facility is versatile, and can be used to query metadata,
dependencies, and contents for the union of the sets of packages the
publishers each offer.

Basic search is available via the ``search`` subcommand, with the ``-l``
option to keep the search local to the present image::

    $ pkg search -l bash
    INDEX      ACTION VALUE                      PACKAGE
    basename   dir    etc/bash                   pkg:/shell/bash@4.0.28-0.137
    basename   dir    usr/share/bash             pkg:/shell/bash@4.0.28-0.137
    basename   file   usr/bin/bash               pkg:/shell/bash@4.0.28-0.137
    pkg.fmri   set    opensolaris.org/shell/bash pkg:/shell/bash@4.0.28-0.137


By default, the ``search`` subcommand searches remote repositories.  In
this mode, it is useful for searching for specific filenames, such as
the name of an executable or an include file::

    $ pkg search xpath.h
    INDEX    ACTION VALUE                              PACKAGE
    basename file   usr/include/libxml2/libxml/xpath.h pkg:/library/libxml2@2.7.6-0.139

Depot servers may also be queried from a web browser, by setting the
location to that of the running depot.  A browser user interface is
provided for search results.

XXX More one search -p, specifically.  Maybe also complex queries.
Definitely a longer explanation of search here or in the SAG.

Adding a publisher
------------------

Image packaging allows the retrieval and installation of software
package from a variety of publishers, each of whom may offer different,
interesting components.  To add an additional publisher, use the
``set-publisher`` subcommand::

    /usr/bin/pkg set-publisher ....

In some cases, a publisher's servers may be unavailable.  Although
|pkg1| attempts to minimize the impact of downtime or unreachable
repositories, it can be simpler to
disable a publisher for the duration of the outage.  ``set-publisher``
makes it easy to disable a publisher::

    /usr/bin/pkg set-publisher --disable ....

Over time, a publisher may no longer offer software interesting for your
system.  |pkg1| performance is generally not affected by additional
publisher entries, but it is good policy to trim unused configuration
from one's system.  To remove a publisher, use ``pkg unset-publisher``::

    /usr/bin/pkg unset-publisher ....

XXX .p5i file based publisher addition.

Initializing an image
---------------------

Although generally not needed for typical operations, when testing newly
created packages, it may be convenient to create a temporary image that
can be deleted after testing has been completed.  To create an image,
use the ``image-create`` subcommand.  An initial publisher must be
specified::

    /usr/bin/pkg image-create ....

To delete an image, simply remove the directory containing the image.

On a typical |OS_Name| installation, the system image starts at the root
of the filesystem ('``/``'), with the packaging metadata stored in
``/var/pkg``.

|pkg1| attempts to determine which image to operate upon automatically,
by scanning its invocation directory.  We can identify the target image
via the ``-R image_directory`` option to any |pkg1| invocation.

