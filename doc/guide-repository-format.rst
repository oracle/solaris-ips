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

.. _Repository file system layout:

Repository file system layout
=============================

File system Layout
------------------

The types of information that the depot server stores and/or retrieves can
be categorized as follows:

    - depot data
        This includes: configuration data, presentation content (such as
        web page templates), publishing data (e.g. in-flight transactions),
        and temporary data (e.g. the feed cache).

    - repository data
        This includes: catalog information, package content (files), package
        metadata (manifests), and search data.

Layout
~~~~~~

    The depot server uses the following 'root' directory structures for the
    storage and retrieval of depot and repository data:

    - repo_dir (depot and repository data)
        cfg_cache (depot data)
            A file containing the cached configuration information for the
            depot server.

        catalog/ (repository data)
            This directory contains the repository catalog and its related
            metadata.

        file/ (repository data)
            This directory contains the file content of packages in the
            repository.

            Files are stored using a two-level path fragment, derived from the
            SHA1-hash of a file's content, assumed to have at least 8 distinct
            characters.

            Example:
                00/
                0023bb/
                000023bb53fdc7bcf35e62b7b0b353a56d36a504

        index/ (repository data)
            This directory contains the search indices for the repository.

        pkg/ (repository data)
            This directory contains the metadata (manifests) for the
            repository's packages.

            The manifests for each package are stored in a directory with the
            same name as the package stem using a URL-encoded filename.

            Example:
                entire/
                    0.5.11%2C5.11-0.86%3A20080422T234219Z

        trans/ (depot data)
            This directory contains in-flight transactions for packages that
            are waiting for the publication process to complete so that they
            can be added to the repository's catalog.

            Each transaction is stored in a directory named after the pending
            transaction id and contains the manifest waiting for publication
            to finish stored with the filename of 'manifest'.

            Example:
                1229379580_pkg%3A%2Fsystem%2Flibc%400.1%2C5.11-98%3A20081215T221940Z/
                    manifest

        updatelog/ (repository data)
            This directory contains metadata detailing changes to the repository
            by publishing operations.

    - content_root (depot data)

        web/
            This directory contains all of the web presentation content for the
            depot.
