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


Depot Operations
----------------

    - versions
        Version 0:
            A GET operation that retrieves text data representing what operations
            are supported and version information about the depot server.

            Example:
                URL:
                http://pkg.opensolaris.org/versions/0/

            Expects:
                Nothing

            Returns:
                text/plain data containing the version of the pkg(5) software that
                the depot is based upon, a list of the operations currently
                supported, and the protocol version supported for each
                operation.

            Sample Output:
                pkg-server bfc04991436e
                info 0
                search 0
                versions 0
                catalog 0
                manifest 0
                add 0
                file 0
                abandon 0
                close 0
                open 0

Metadata Operations
-------------------

    - catalog
        Version 0:
            A GET operation that retrieves a text/plain datastream
            representing a complete catalog or an incremental update to an
            existing one as requested.

            Example:
                URL:
                http://pkg.opensolaris.org/catalog/0/

            Expects:
                Nothing or the following headers:
                    If-Modified-Since: {ISO 8601 formatted date and time in UTC}

            Returns:
                Either the contents of a pkg(5) catalog file, or the entries
                that were added since the specified date as they are found
                in the catalog file, separated by newlines.

    - info
        Version 0:
            A GET operation that retrieves a text/plain description of a
            package and its licensing information specified by the provided
            FMRI.

            Example:
                URL:
                http://pkg.opensolaris.org/info/0/entire@0.5.11,5.11-0.101:20081119T235706Z

            Expects:
                A URL-encoded pkg(5) FMRI, excluding the 'pkg:/' scheme prefix
                and publisher information, and including the full version
                information.

            Returns:
                A text/plain representation of the specified package and its
                licensing information.

            Sample Output:
                Name: entire
                Summary: entire incorporation
                Publisher: Unknown
                Version: 0.5.11
                Build Release: 5.11
                Branch: 0.101
                Packaging Date: Wed Nov 19 23:57:06 2008
                Size: 0.00 B
                FMRI: pkg:/entire@0.5.11,5.11-0.101:20081119T235706Z

                License:

    - manifest
        Version 0:
            A GET operation that retrieves the contents of the manifest file for
            a package specified by the provided FMRI.

            Example:
                URL:
                http://pkg.opensolaris.org/manifest/0/entire@0.5.11,5.11-0.101:20081119T235706Z

            Expects:
                A URL-encoded pkg(5) FMRI excluding the 'pkg:/' scheme prefix
                and publisher information and including the full version
                information.

            Returns:
                The contents of the package's manifest file.

    - p5i
        Version 0:
                A GET operation that retrieves an application/vnd.pkg5.info
                datastream representing publisher and package information.
                This is intended for consumption by clients for the purposes
                of auto-configuration, metadata management policy determination,
                and triggering packaging operations such as installation.

            Example:
                URL:
                http://pkg.opensolaris.org/release/p5i/0/SUNWcs

            Expects:
                A full or partial URL-encoded pkg(5) FMRI, excluding the
                publisher prefix.  If the partial or full FMRI is valid, it will
                be added to the datastream as is.  If it includes the wildcard
                character '*', a search of the repository's catalog for matching
                entries will be performed and the unique set of resulting
                package stems will be added to the datastream.  If no match is
                found, a 404 error will be raised.

            Returns:
                Returns a pkg(5) information datastream based on the repository
                configuration's publisher information and the provided full or
                partial FMRI or matching entries.  The Content-Type of the
                response is 'application/vnd.pkg5.info'.

    - publisher
        Version 0:
                A GET operation that retrieves an application/vnd.pkg5.info
                datastream representing publisher information.  This is intended
                for consumption by clients for auto-configuration and metadata
                management policy determination.

            Example:
                URL:
                http://pkg.opensolaris.org/release/publisher/0

            Expects:
                Nothing

            Returns:
                Returns a pkg(5) information datastream based on the repository
                configuration's publisher information.  The Content-Type of the
                response is 'application/vnd.pkg5.info'.

    - search
        Version 0:
            A GET operation that retrieves a text/plain list of packages with
            metadata that matches the specified criteria.

            Example:
                URL:
                http://pkg.opensolaris.org/release/search/0/vim

            Expects:
                A URL-encoded token representing the search criteria.

            Returns:
                A text/plain list of matching entries, separated by newlines.
                Each entry consists of a set of four space-separated values:

                    index   - what search index the entry was found in

                    action  - what package action the entry is related to

                    value   - the value that the matched the search criteria

                    package - the fmri of the package that contains the match

                Results are streamed to the client as they are found.

            Sample Output:
                basename pkg:/SUNWvim@7.1.284,5.11-0.101:20081119T230659Z dir usr/share/vim
                basename pkg:/SUNWvim@7.1.284,5.11-0.93:20080708T171331Z file usr/bin/vim

Content Operations
------------------

    The pkg.depotd(5) server provides the following operations for retrieving
    package content:

    - file
        Version 0:
            A GET operation that retrieves the contents of a file, belonging to a
            package, using a SHA-1 hash of the file's content.

            Example:
                URL:
                http://pkg.opensolaris.org/release/file/0/
                a00030db8b91f85d0b7144d0d4ef241a3f1ae28f

            Expects:
                A SHA-1 hash of the file's content belonging to a package in the
                request path.

            Returns:
                The contents of the file, compressed using the gzip compression
                algorithm.

