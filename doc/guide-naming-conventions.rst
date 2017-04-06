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


Package naming conventions
--------------------------

Definitions
~~~~~~~~~~~

To be consistent with the system, following the introduction of the
fault management architecture, each package is named by an FMRI in the
``pkg:`` scheme.  That is, we have::

    pkg://publisher/pkg_name@version

The publisher is generally expected to be a forward or reverse domain
name identifying the publisher from which a package can be retrieved.
Publishers which cannot be determined to be a domain name are
legitimate, but optional functionality, like automatic server discovery
for a particular publisher, may fail to work.  In the examples that
follow, we use "opensolaris.org" as a generic publisher.

Although RFC 2396 usage would suggest using the "authority" term, we
instead call it the publisher name, as the role of this section of the
FMRI is to identify the source for the package, which we consider a
publication of one or more software components.

The pkg_name, like service names, can be split into a category,
subcategories, and a basename.  This namespace might be populated
with "manifest" and other metadata endpoints, as well as the SHA-1
names of the package's included files.  (Although the direct access
to properties of the ``svc`` FMRI scheme has been rarely used.)

A "group package" is a package that depends upon (minimum versions
of) other packages, as well as optionally delivering files or other
actions.  An "incorporating package" is a group package that places
forward constraints upon the versions of the packages it depends upon,
which restricts the interval of valid package versions to one the author
of the incorporation believes functional.


Namespace
~~~~~~~~~

Single namespace, separate publishers
``````````````````````````````````````

The primary design point of the package namespace is to allow
multiple package producers to co-exist in a single namespace, so
that images can switch between equivalent components from different
producers.

Domain-name-based escape
````````````````````````

At any point in the category hierarchy, a safe namespace can be created
by using the forward or reverse domain name, either as a subcategory or
as a comma-led prefix to a subcategory or package base name.  (This
scheme is similar to FMRI namespace escapes in smf(5), although we are
eliminating use of stock symbol prefixes.)  Generally, safe namespaces
are only needed when the components delivered by a package need to be
distinguished from those delivered by a package in the single namespace;
reasons for distinguishing the components might include construction of
a collection of components, insulated from changes in the wider system,
or for legal reasons.

For instance, when example.com wishes to publish the "whiskers"
package without reference to a larger namespace convention it can
use any of the following examples::

    pkg://opensolaris.org/.../com.example/whiskers

    pkg://opensolaris.org/.../com.example,whiskers

    pkg://opensolaris.org/.../com.example,software/whiskers

and so forth.

Locally reserved namespace
``````````````````````````

The top-level "site" category is reserved for use by the entity that
administrates the server.  Neither the organizations producing the
operating system nor those providing additional software components may
use the site category.

The top-level "vendor" category is reserved for use by organizations
providing additional.  The leading subcategory must be a domain.  That
is, if example.com wishes to publish the "whiskers" package in the
vendor category, it would use a package name like::

    pkg://opensolaris.org/vendor/example.com/whiskers

Use of the "vendor" category, and the vendor-escaped packages below, is
likely only to be of interest to organizations that redistribute
software from multiple source vendors.

Additional reserved namespace
`````````````````````````````

.. admonition:: ARC Notice

   Some or all of these reservations may be eliminated or reduced when
   the single namespace convention reaches its final form.

The top-level "cluster", "feature", "group", and "metacluster"
categories are all reserved for future use.

Single namespace conventions
````````````````````````````

Discussion
^^^^^^^^^^

Packaging systems and distributions appear to have explicit
categories, subcategories, and potentially larger groups; some
distributions have explicit fields for these values, others use
tagging or multi-valued fields, which allows them to classify
certain packages multiply.  For the FMRI namespace case, the system
is similar to a packaging system with multiple, single-valued,
category fields.

There appear to be two standard approaches to categorizing packages:

    1.  By what primary class of thing a package delivers.

    2.  By what area of functionality a package's contents address.

In the first approach, we get strict top-level categories like
"application", "driver", "library", and "system" or "kernel", as
well as potentially overlapping categories like "utility" and
"tool".  Use of the leading subcategory is limited, and generally
given to the subsystem involved.  A relatively detailed worked
example of the X11 subsystem under this scheme is given in

http://mail.opensolaris.org/pipermail/pkg-discuss/2008-February/001838.html

XXX This reference is now wrong.

In the second, we would also see categories like these, but leading
subcategory is much more likely to classify according to
functionality, so that we would see "application/mail",
"application/web", "application/compiler", and so forth.  Most
network packaging systems appear to classify in this fashion.

An appealing variation of the second form is to rotate all of the
non-"application" packages under a "system" mega-category, such that
all of the leaf packages (with the possible exception of device
drivers) are exposed at the category level.  Table 1 shows some
example transformations under this scheme.

.. table::  Rotating non-application categories under system.

    ========================= ====================
    FROM                      TO
    ========================= ====================
    application/web/firefox   web/firefox
    application/compiler/gcc4 compiler/gcc4
    library/c                 system/library/c 
    kernel/generic            system/kernel/generic
    ========================= ====================



