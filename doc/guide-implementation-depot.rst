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


When communicating with the depot server via HTTP, operations are
presented via a URL-based mechanism that allows each to be versioned so
that changes in protocol can be hidden from older clients as the
interfaces to operations evolve.

Operations made available by a |depotd1m| server can be accessed via
GET or POST, as appropriate for each operation, via a URL such as the
following:

    http://pkg.opensolaris.org/release/manifest/0/SUNWvim%407.1.284%2C5.11-0.101%3A20081119T230659Z

The above example can be broken down into four basic components:

        publisher_origin_url    - http://pkg.opensolaris.org/release/
        operation_name          - manifest
        protocol_version        - 0
        operation_arguments     - SUNWvim%407.1.284%2C5.11-0.101%3A20081119T230659Z

Each of these components can be described as follows:

        publisher_origin_url    - A URL that can be used to access a depot
                                  server's repository.

        operation_name          - The name of the operation that the client is
                                  wanting to initiate.

        protocol_version        - An integer value representing the version of
                                  the operation's protocol spoken by the client.

        operation_arguments     - String data (such as a package FMRI) that is
                                  parsed and then used to determine what
                                  resource(s) will be used to perform an
                                  operation.  Some operations expect arguments
                                  or data to be passed via POST-based form data,
                                  headers, or the request body instead.

Operation Types
---------------

Each operation that the depot server provides is either designed to interact
with a pkg(5) repository, or with the depot server itself.  These operations
can be categorized as follows:

    - content
        These operations are read-only, and retrieve file data that comprises
        the content of a package in a repository.

    - depot
        These operations are read-only, and permit retrieval of: the list of
        operations that the depot server currently provides (including protocol
        version and pkg(5) software version), statistics information, and other
        depot information.

    - metadata
        These operations are read-only, and retrieve metadata related to a
        package FMRI, such as its name, version, etc. stored in a repository's
        catalog.

    - publishing
        These operations alter a repository's catalog, package metadata, and
        allow storage of package content.

Modes
-----

Which types of operations are available is dependent on which mode the
depot server is currently operating in:

    - default
        In default mode, the depot server allows content, depot, metadata,
        and publishing operations.
    - readonly
        In readonly mode, the depot server allows content, depot, and
        metadata operations.
    - mirror
        In mirror mode, the depot server allows content and depot
        operations.

