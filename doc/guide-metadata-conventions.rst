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

Tags and attributes
-------------------

Definitions
~~~~~~~~~~~

    Both packages and actions within a package can carry metadata, which
    we informally refer to as attributes and tags.

    Attributes:  settings that apply to an entire package.  Introduction
    of an attribute that causes different deliveries by the client could
    cause a conflict with the versioning algebra, so we attempt to avoid
    them.

    Tags are the settings that affect individual files within a package.
    Tags may eventually have values, depending on how many tags are
    required to handle the SPARC-based platform binaries.

Attribute and tag syntax and namespace
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Syntax
``````

    The syntax for attributes and tags is similar to that used for
    pkg(5) and smf(5) FMRIs.

    [org_prefix,][name][:locale]

    The organizational prefix is a forward-ordered or reverse-ordered
    domain name, followed by a common.  The name field is a  
    The default locale, if the locale field is omitted is "C", a 7-bit
    ASCII locale.

    Each of these fields is [A-Za-z][A-Za-z0-9\_-.]*.

Unprefixed attributes and tags
``````````````````````````````

    All unprefixed attributes and tags are reserved for use by the
    framework.

    Generally, unprefixed tags are introduced in the definition of an
    action.

Attributes and tags common to all packages
``````````````````````````````````````````

    The "pkg" attribute is to be used for attributes common to all
    packages, regardless of which particular OS platforms that a specific
    package may target.

Common attributes
^^^^^^^^^^^^^^^^^

    pkg.name
       A short, descriptive name for the package.  In accordance with
       2.1 above, pkg.name:fr would be the descriptive name in French.
       Exact numerical version strings are discouraged in the
       descriptive name.

       Example:  "Apache HTTPD Web Server 2.x"

    pkg.description
       A descriptive paragraph for the package.  Exact numerical version
       strings can be embedded in the paragraph.

    pkg.detailed_url
       One or more URLs to pages or sites with further information about
       the package.

Common tags
^^^^^^^^^^^

    XXX variant/facet usage

    pkg.debug
       This file is used when the package is intended to be installed in
       a debug configuration.  For example, we expect to deliver a debug
       version of the kernel, in addition to the standard non-debug
       version.

    XXX pkg.platform

    XXX ISA (particularly need to know i386 on i86pc vs amd64 on i86pc)

    pkg.compatibility
        (for shipping non-bleeding edge .so.x.y.z copies, perhaps)
        XXX are we still going to use this?

Informational tags
^^^^^^^^^^^^^^^^^^

The following tags are not necessary for correct package installation,
but having a shared convention lowers confusion between publishers and
users.

info.maintainer
    A human readable string describing the entity providing the
    package.  For an individual, this string is expected to be their
    name, or name and email.

info.maintainer_url
    A URL associated with the entity providing the package.

info.upstream
    A human readable string describing the entity that creates the
    software.  For an individual, this string is expected to be
    their name, or name and email.

info.upstream_url
    A URL associated with the entity that creates the 
    software delivered within the package.

info.source_url
    A URL to the source code bundle, if appropriate, for the package.

info.repository_url
    A URL to the source code repository, if appropriate, for the
    package.

info.repository_changeset
    A changeset ID for the version of the source code contained in
    info.repository_url.

info.gui.classification
    A list of labels classifying the package into the categories
    shared among |pkg5| graphical clients.

Attributes common to all packages for an OS platform
````````````````````````````````````````````````````

    Each OS platform is expected to define a string representing that
    platform.  For example, the |OS_Name| platform is represented by
    the string "opensolaris".

Organization specific attributes
````````````````````````````````

    Organizations wishing to provide a package with additional metadata
    or to amend an existing package's metadata (in a repository that
    they have control over) must use an organization-specific prefix.
    For example, a service organization might introduce
    ``service.example.com,support_level`` or
    ``com.example.service,support_level`` to describe a level of support
    for a package and its contents.

.. 3.3.  Attributes best avoided

.. built-on release

.. One problem we may run into is packages that have been built on a
    release newer than that on the image.  These packages should be
    evaluated as unsuitable for the image, and not offered in the graph.
    There are a few ways to handle this case:

..    1.  Separate repository.  All packages offered by a repository were
        built on a known system configuration.  This change requires
        negotiation between client and server for a built-on match
        condition.  It also means that multiple repositories are needed
        for a long lifecycle distribution.

..    2.  Attributes.  Each package comes with a built-on attribute.  This
        means that clients move from one built-on release to another
        triggered by conditions set by the base package on the client.
        Another drawback is that it becomes impossible to request a
        specific package by an FMRI, without additional knowledge.

..   3.  Additional version specifier.  We could extend
        release,branch:timestamp to release,built,branch:timestamp--or
        fold the built and branch version together.  Since the built
        portion must reserve major.minor.micro, that means we move to a
        package FMRI that looks like

..        coreutils@6.7,5.11.0.1:timestamp

..        This choice looks awkward.  We could instead treat the built
        portion as having a default value on a particular client.  Then
        the common specifier would be

..        name@release[,build]-branch:timestamp

..        build would be the highest available valid release for the
        image.

..    The meaning of the built-on version could be controversial.  A
    simple approach would be to base it on base/minimal's release,
    rather than uname(1) output.



