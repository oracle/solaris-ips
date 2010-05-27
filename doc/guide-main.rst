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


=================================
Image Packaging Developer's Guide
=================================
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
*PSARC/2008/190:* pkg(5): image packaging system
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Authors: David Comay, Danek Duvall, Tim Foster, Stephen Hahn, Krister Johansen,
          Dan Price, Brock Pytlik, Bart Smaalders, Shawn Walker
:Organization: http://hub.opensolaris.org/bin/view/Project+pkg/
:Contact: pkg-discuss@opensolaris.org
:Status: Interim draft
:Date: 2010-04-19

.. include:: macros.rst

.. sectnum::
.. contents:: Table of Contents
   :depth: 3

--------
Overview
--------

.. section-autonumbering
   :start: 1
   :depth: 2

About this document
===================

.. admonition:: ARC Notice

   For the purposes of review, this document--a draft of the
   developer guide--contains additional information that may be omitted
   from the final guide.  Such information is generally set off from the
   main text.

In this text, *The Image Packaging Developer's Guide*, we cover a range
of topics covering technical aspects of software delivery using |pkg5|,
the image packaging system.  As you complete Parts I, II, and III of the
document, you should feel comfortable

* with basic |pkg5| principles of operation and use,

* with authoring packages, decorated with correct metadata and named
  according to convention,

* renaming previously published packages, and

* managing simple and complex |depotd1m| deployments.

Parts IV and V focus on implementing components capable of replacing
the default image packaging retrieval clients and depot servers,
respectively.

Introduction
============

The Image Packaging System, or |pkg5|, is a software delivery mechanism
that enables the publication and retrieval of versioned, interdependent
software components.  The goal of this mechanism is to always produce a
functioning image, in which each component in that image has its
dependencies on other components met in a self-consistent fashion.
Usually, when we refer to an image, we are referring to the *system
image* associated with an instance of the |OS_Name| operating system,
but an image can also be used to deliver an independent set of software
components, or a set linked in some fashion to yet another image.
Inter-image relationships allow |pkg5| to be used in a wide variety of
software deployment contexts.

The idea of a versioned component comes from recognizing that, in
general, software components change over time, as bugs are fixed, new
features introduced, component boundaries changed, or the component
itself becomes irrelevant.  We can look at the history of a component as
a series of versions of that component, persisting indefinitely.  In the
following chapters, the relationship over time of a component to other
components, and to itself, will be revisited.  The intent is to
emphasize that each software component has a lifecycle, and that there
are representative states and operations in |pkg5| as a component moves
through that lifecycle.

There are a number of features in |pkg5| that make it particularly
appealing in a network context.  In general, all |pkg5| metadata is
searchable remotely, easing the discovery of available software.  |pkg5|
content delivery is bandwidth-efficient, sending only needed data to the
client, and always in a compressed form.  Each publisher's depot
software has public information, which allows the identification of
other locations for software retrieval, such as mirrors for that depot
or publishers of related software.  These features are discussed as they
apply to each of the components.

|pkg5|, although it has a command line client, was developed to support
both interactive use with other clients and programmatic use by higher
level management software.  We generally illustrate operations by
reviewing the command line client.  For developers and package
publishers, we will identify where package metadata, such as additional
information about the package or a specific object delivered by the
package, can influence these different client uses.  We, in addition,
describe the more complex publication scenarios, such as signed
manifests and obsolescence.  For operators and administrators, we
discuss security, in the form of access control, and depot management.
Our final sections focus on |pkg5| extensions, such as entitlement
support.

Key concepts
============

In this section, we attempt to review the key concepts and indicate
where further discussion and examples can be found in this Guide.
Packages may be installed into images; image contents are the
consequence of package installations.

Packages, package versions, actions, and actuators
--------------------------------------------------

Package
    A package represents a set of related resources that can be
    installed into a file system location on a computing system.  In the
    image packaging system, packages are distinguished by their package
    names and by their package versions.  Only a single version of a
    package may be installed to a file system location.

Package names
    Since the name of a package often is the easiest way to identify its
    contents, the selection of a package name is an important step in
    package publication.  The set of package names, or *package
    namespace* follows conventions to allow publishers to have uniquely
    named packages.  As an example, the package name for the image
    packaging system is ``pkg://opensolaris.org/package/pkg``.  Package
    names can be matched on unique substrings, which is convenient for
    interactive use, so we will often abbreviate package names to their
    unique portion.  Thus, for command line invocations, we will often
    write ``pkg install package/pkg`` to update the image packaging
    system's package.

Package versions
    A package version is a multiple component object.  Two versions of a
    particular package can always be ordered via a comparison:  they
    will either be equal, or one will be less than the other.  In the
    image packaging system, a version consists of three sub-versions and
    a timestamp.  For instance, a recent version of ``package/pkg`` is
    ``0.5.11,5.11-0.138:20100430T013957Z``.

Package states
    Each package version has a specific state in each image.  For
    instance a package version may be *installed* or merely *known* by
    having an entry in a catalog.
    See `Package States`_.

Package tags and file attributes
    As briefly mentioned, packages and their content may have additional
    information associated with them.  There are both mandatory and
    optional metadata items that package publisher can provide and
    with which client software is expected to comply.  Additionally,
    specific publishers may wish to provide additional metadata for
    their own use, or for use with the search facility.

Actions
    The resources that a package delivers are called actions, as
    they cause changes to the system on which the package is installed.
    Actions that differ between the current and proposed package
    versions are delivered; actions that do not differ are not
    delivered.

    There are a number of action types for delivering content to the
    file system, such as ``file``, ``directory``, and ``link``, as well
    as action types that deliver new system metadata, like the ``user``
    action, which delivers a new or modified user account.  The file
    within the package that contains its set of actions is called a
    *manifest*.  An arbitrary amount of metadata may be added to any
    action; such metadata items are called *tags*.

Actuators
    A special kind of action tag is the actuator, which identifies a
    side effect this action will have when installed on the in-use image
    on a running system (a "live image").  Actuators have no effect on
    non-live images.  One typical actuator use is to request a restart
    of a particular |smf5| service instance.  This request is made by
    specifying the FMRI as the value for the ``restart_fmri`` actuator.

Images and image types
----------------------

Image
    We refer to a file system location configured to receive package
    installations as an image.  Each collection of installed package
    instances is some kind of image.  We envision three kinds:

    - entire images
        An entire image contains (and can contain) all appropriate
        packages from a repository.  It has a machine type and release.

    - partial images
        A partial image contains (and can contain) all appropriate
        packages from a repository.  An partial image is tied to an
        entire image and has an identified list of non-writeable
        directory paths.  It inherits its machine type and release.

    - user images
        A user image consists entirely of relocatable packages.  It is
        tied to an entire image for dependency satisfaction of
        non-relocatable packages.  It inherits its machine type and
        release.

Publishers, catalogs, and repositories
--------------------------------------

Publishers
    Each package has a publisher, which represents the person or
    organization that has assembled the package and makes it available
    for installation.

Catalogs
    Since a publisher can make one or more packages available, each
    publisher generally provides a list of all packages and versions
    currently available for retrieval.  The file that contains this list
    is called a *catalog*.

Repository
    Although a package [will be able to] be distributed independently,
    publishers with many packages may find it easier to publish that
    collection to a repository, which is a structured set of directories
    and files that contains the packages, their metadata, and their
    contents.  A *depot* is a network server that can respond to
    requests for specific operations on [one or more] repositories.

Dependencies and constraints
----------------------------

Packages can have relationships with other packages, such as a
``require`` relationship, where the presence of a package is mandatory
for a second package to be installed.  Each declaration of a
relationship in a package's metadata is done using a ``depend`` action,
which expresses the relationship as a *dependency*.  Dependency types
include

``require``
    A require dependency states that the package mentioned by the
    ``fmri`` attribute of the ``depend`` action must also be installed
    into the image, with version at or above the specified version.  If
    no version is given, any version is allowed.

``optional``
    An optional dependency states that the package mentioned by the
    ``fmri`` attribute, if a version is installed in the image, that
    version must be at or above the specified version.

``exclude``
    An exclude dependency states that, if the package version or a
    successor mentioned by the ``fmri`` attribute is installed in the
    image, the current package (containing the ``depend`` action) cannot
    be installed.

``incorporate``
    An incorporation dependency expresses a special type of
    relationship, where the presence of the dependent package is
    constrained to the version range implied by the ``fmri`` portion of
    the ``depend`` action.  Incorporation dependencies are used to
    restrict the set of package versions to a known and, presumably,
    tested subset of all available versions.

|OS_Name|-specific concepts
-----------------------------

Migration and compatibility
    |pkg5| supplants the historical Solaris Operating System packaging
    tools, although these are still supported for compatibility.  Moving
    a software component to the Image Packaging System requires some
    planning.

|smf5| configuration transition
    Certain resource types, such as manual pages and desktop icons, are
    delivered by multiple applications.  New |smf5| service instances
    have been provided to simplify the integration of standard resources.

Application configuration
    For some applications, specific operations must be taken after
    package installation or removal.  In addition to general techniques
    for handling such operations, we review specific utilities and
    services introduced for handling typical cases.

Commands
========

 - **Retrieval clients.** |pkg1|, PackageManager.  UpdateManager.

   - use of SSL

   - relationship with |beadm1m|, |libbe3lib|, ZFS

 - **Publication and manipulation clients.** |pkgsend1| and |pkgrecv1|

   - |pkgdepend1|, |pkgdiff1|, |pkgfmt1|, |pkgmogrify1|

   - authentication

 - **Depot servers.** |depotd1m|

   - reverse proxy

   - horizontal use

 Other commands affected.

.. include:: guide-basic-ops.rst

---------------------------------
Authoring and publishing packages
---------------------------------

.. section-autonumbering
   :start: 1

Getting started
===============

Pick a publisher name, based on a DNS domain you control.

Running a depot
---------------

An |smf5| service instance of ``pkg/server`` is provided with a default
OpenSolaris installation.

set publisher name

set read-write to enabled

Publishing to files
-------------------

Transaction basics
==================

If we examine the process of publishing a particular version of a
package, we can see there are three sets of decisions:

* package contents, or what files or other resources are delivered by
  this version of the package;
* package name, or what the package is called; and
* package metadata, or what additional information is provided to
  describe the package's purpose within a larger system.

Before we discuss these topics, we review how publication works.

.. admonition:: ARC notice

    Additional options for access control to publication operations are
    under consideration.

To publish a package, we use the |pkgsend1| command to open a transaction
with an active package depot, to send actions, which are the resources
and metadata delivered by the package, and finally to close the
transaction.  Upon the request for the transaction to be closed, the
depot daemon will, for a valid submission, update its catalog and search
indices to reflect the newly published package version.  Clients, such
as |pkg1|, can then refresh their local catalogs and retrieve the new
package version.

Let's work through the above description in the form of an example.
In the following example, we wish to publish a simple package that
provides the ``/etc/release`` file, which, on a typical |OS_Name|
system, contains some descriptive information about this particular
release of the operating system.

.. include:: guide-txn-states.rst

Supported Actions
-----------------

|pkg5| supports an extensible set of "actions", which are defined as
reversible operations that a package can request to enable its later
function on the target image.

.. admonition:: ARC notice

  Packages need a limited set of operations on individual files to
  manipulate the configuration.  The current class actions are given in
  Appendix A.  It appears that if "manifest" and "rbac" were supported,
  along with some management of editable files (preserve, renamenew,
  initd, renameold), then the remaining operations could be deferred to
  image instantiation.

We can analyze the typical delivered components of a working operating
system to identify the set of common actions.  The decision to provide
an action for a specific class of resource is strongly influenced by the
need for elements of that class to be fully configured for system boot to
complete.  Resources that can be configured after initial boot are
generally not provided with actions, and are expected to use ``file``
actions to deliver content and an |smf5| service to derive and assemble
any necessary local configuration.

depend
    Declare dependency on other packages.

directory
    All directories.

driver
    Package contains device driver Module loading will be disabled
    during operations on live images.

file
    All other files.  Preservation and rename handling are managed as
    optional tags.

hardlink, link
    All hard and symbolic links.

set
    Set a package tag.

user, group
    Package requires user, group, or other package-reference managed
    resource.

legacy
    Record package attributes into legacy packaging metadata.

license
    License files, which deliver into the image metadata rather than
    the image's filesystems.

signature
    Deliver a cryptographic signature for the containing manifest.

Interface summary::

    <interface>
        <action name="dependency" payload="false" commitment="Committed" />
        <action name="directory" payload="false" commitment="Committed" />
        <action name="hardlink" payload="false" commitment="Committed" />
        <action name="legacy" payload="false" commitment="Committed" />
        <action name="license" payload="true" commitment="Committed" />
        <action name="link" payload="false" commitment="Committed" />
        <action name="driver" payload="false" commitment="Committed" />
        <action name="file" payload="true" commitment="Committed" />
        <action name="group" payload="false" commitment="Committed" />
        <action name="user" payload="false" commitment="Committed" />
        <action name="signature" payload="false" commitment="Committed" />
    </interface>

.. sidebar:: Custom actions

  It is discouraged, but certainly possible to deliver custom actions
  into the appropriate ``$PYTHONROOT/vendor-packages/pkg directory``, by
  including those actions in a separate package that the new package
  requires, and invoking the |pkg1| client twice--once to deliver the
  custom actions and once to use them to install the new package.
  (Rescanning pkg.actions would complicate the image plan/package plan
  evaluations.)

  XXX The deployer may wish to deny such actions from operating.  For this
  case, the set of known actions is fixed elsewhere in the pkg modules
  and updated with subsequent versions.  A global and per-image policy,
  known-actions-only, allows the deployer to disallow operations on
  packages utilizing actions of unknown provenance.

  Interface::

    <interface>
        <policy name="known-actions-only" scope="global,image"
            type="boolean" commitment="Committed">
        Deployer control over execution of unknown actions.
        </policy>
    <interface>

Actuators
~~~~~~~~~

Reboot necessity.

Those system configuration steps which can be deferred.

Variants and facets
~~~~~~~~~~~~~~~~~~~

Packaging considerations
========================

Many of the good packaging criteria present trade-offs among themselves. It
will often be difficult to satisfy all requirements equally. These criteria are
presented in order of importance; however, this sequence is meant to serve as a
flexible guide depending on the circumstances. Although each of these criteria
is important, it is up to you to optimize these requirements to produce a good
set of packages.

Optimize for Client-Server Configurations
-----------------------------------------

You should consider the various patterns of software use
(client and server) when laying out packages. Good packaging
design divides the affected files to optimize installation of each
configuration type. For example, for a network protocol implementation,
it should be possible to install the client without necessarily
installing the server.

Package by Functional Boundaries
--------------------------------

Packages should be self-contained and distinctly identified with a set of
functionality. For example, a package containing UFS should contain all UFS
utilities and be limited to only UFS binaries.

Packages should be organized from a customer's point of view into functional
units.

Package Along License or Royalty Boundaries
-------------------------------------------

Put code that requires royalty payments due to contractual agreements or
that has distinct software license terms in a dedicated package or group
of packages. Do not to disperse the code into more packages than
necessary.

Overlap in Packages
-------------------

When constructing the packages, ensure that duplicate files are eliminated when
possible. Unnecessary duplication of files results in support and version
difficulties. If your product has multiple packages, constantly compare the
contents of these packages for redundancies.

Sizing Considerations
---------------------

Size is package-specific and depends on other criteria. For example, the
maximum size of /opt should be considered. When possible, a good package should
not contain only one or two files or contain extremely large numbers of files.
There are cases where a smaller or larger package might be appropriate to
satisfy other criteria.

Licensing Considerations for Packages
-------------------------------------

If you are distributing software that uses licensing, there are several things
you need to consider:

    - Business operations
    - Communication with users
    - Technology

*Business Operations.*  Before you begin distributing licensed software, set up
your business operations to distribute, price, and track licenses. There are a
variety of ways to distribute licenses, such as fax, electronic mail, or an 800
telephone number. You need to choose a method of distribution and set up all
the necessary processes. You also need to consider whether licenses need to be
upgraded with the software and how this will be done.

Pricing policy and types of licenses must also be considered. You must consider
how the product is used and what kinds of licenses your users will need to use
the product effectively. Single user licenses may not be appropriate for many
situations.

*Communication with Users.* Before you implement licensing, you need to inform
your users, particularly if the product has not been licensed in the past.

When you do implement licensing, you may want to consider implementing it
gradually. The first step would be monitoring the use of licenses, followed by
warning that the software is being used without a license, and finally, denying
the use of the software.

*Technology.* If you are going to use a commercial product for licensing, there
are many things to consider when making your choice. You need to decide what
your priorities are. For example, is ease of administration and use most
important? Or is enforcing the licensing policy more important?

You also need to consider whether the software will be used in a heterogeneous
or homogeneous environment and whether standards are important. You may also
want to look at the security provided by the product. Is it easy to get around
the enforcement of licenses?

The issues involved in choosing a commercial product will vary depending on
the kind of application and your reasons for implementing licensing.


Naming your package
===================

.. include:: guide-naming-conventions.rst

Decorating your package
=======================

.. include:: guide-metadata-conventions.rst

A full packaging example
========================

Delivery examples
=================

In the following sections, we give examples of delivering specific
resources via the image packaging system.

Device driver
-------------

XXX ``e1000g``

Versioned interpreter
---------------------

XXX perl
XXX ``verexec``

|smf5| Service
--------------

XXX pkg.depotd

GNOME Desktop Elements
----------------------

XXX pick a specific Gnome application

Coordinating groups of packages using incorporations
----------------------------------------------------

Renaming a package
------------------

Making a package version obsolete
---------------------------------

Moving a file between packages
------------------------------

Migrating an existing package
=============================

Migrating a System V Package
----------------------------

XXX pkgsend

Migrating a |tar1| archive
--------------------------

XXX pkgsend

Publishing from an installation directory
-----------------------------------------

Pre-publication tools
=====================

pkgmogrify, pkgdepend, pkgdiff, and pkgfmt.

----------------
Depot operations
----------------

Distributing packages with a depot
==================================

XXX thread tuning

Using Apache HTTPD as a reverse proxy cache
-------------------------------------------

recommended

can speed up operations

Running a content mirror
------------------------

From DVD

Via rsync

Long-term operations
--------------------

Splitting and spreading package retrieval load
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

can be load balanced

Tuning search
~~~~~~~~~~~~~

Publishing packages with a depot
================================

running in r/w mode

XXX could we automate snapshots?

----------------
Packaging client
----------------

.. section-autonumbering
   :start: 1

.. include:: guide-pkg-states.rst

- protocol / network format
        - client side REST API
        - publication side REST API

Retrieval protocol operations
=============================

Publication protocol operations
===============================

.. include:: guide-publication-protocol.rst

Other protocol operations
=========================

- versions
      Version 0

      A GET operation that retrieves the current set of operations
      offered by the contacted depot.

      Example:

          URL: http://pkg.opensolaris.org/versions/0

      Expects:

          No body.

      Returns:

          List of operations and versions, one operation per line, space
          separated list of versions for each operation.
- search
      Version 1

      A GET operation that presents a query to the search index
      capability of the contacted depot.


--------------------------------
Package depots and other servers
--------------------------------

.. section-autonumbering
   :start: 1

.. include:: guide-repository-format.rst

|depotd1m| implementation
=========================

.. include:: guide-implementation-depot.rst

--------------------------------
Appendix: Reference manual pages
--------------------------------

pkg(1)
======

.. raw:: html

   <pre>

.. raw:: html
   :file: ../src/man/pkg.1.txt

.. raw:: html

   </pre>

.. raw:: latex

   \begin{verbatim}

.. raw:: latex
   :file: ../src/man/pkg.1.txt

.. raw:: latex

   \end{verbatim}

pkgrecv(1)
==========

.. raw:: html

   <pre>

.. raw:: html
   :file: ../src/man/pkgrecv.1.txt

.. raw:: html

   </pre>

.. raw:: latex

   \begin{verbatim}

.. raw:: latex
   :file: ../src/man/pkgrecv.1.txt

.. raw:: latex

   \end{verbatim}

pkgsend(1)
==========

.. raw:: html

   <pre>

.. raw:: html
   :file: ../src/man/pkgsend.1.txt

.. raw:: html

   </pre>

.. raw:: latex

   \begin{verbatim}

.. raw:: latex
   :file: ../src/man/pkgsend.1.txt

.. raw:: latex

   \end{verbatim}

pkg.depotd(1M)
==============

.. raw:: html

   <pre>

.. raw:: html
   :file: ../src/man/pkg.depotd.1m.txt

.. raw:: html

   </pre>

.. raw:: latex

   \begin{verbatim}

.. raw:: latex
   :file: ../src/man/pkg.depotd.1m.txt

.. raw:: latex

   \end{verbatim}

pkg(5)
======

.. raw:: html

   <pre>

.. raw:: html
   :file: ../src/man/pkg.5.txt

.. raw:: html

   </pre>

.. raw:: latex

   \begin{verbatim}

.. raw:: latex
   :file: ../src/man/pkg.5.txt

.. raw:: latex

   \end{verbatim}

---------------------------
Appendix:  Protocol details
---------------------------

------------------------------------------
Appendix:  Architectural process materials
------------------------------------------

.. raw:: html

   <pre>

.. raw:: html
   :file: one-pager-main.txt

.. raw:: html

   </pre>


