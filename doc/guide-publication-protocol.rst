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

    - add
        Version 0:
            A POST operation that adds content to an in-flight transaction for
            the Transaction ID specified.  This could either be file content
            for the package or metadata about the package.

            This data is not added to the repository for retrieval until a close
            operation for the specified Transaction ID is executed.

            Example:
                URL:
                http://pkg.opensolaris.org/add/0/1228870796_pkg%3A%2Fsystem%2Flibc%400.1%2C5.11-98%3A20081210T005956Z

                HEADERS:
                X-IPkg-SetAttr1: description=Package Name

                REQUEST BODY:

            Expects:
                A Transaction ID as output by pkgsend(1) in the request path.
                The file content (if applicable), to be added, in the request
                body.  Any attributes to be set in the headers in the pattern
                of:

                    X-IPkg-SetAttr{integer}: attr=value

            Returns:
                Response status of 200 on success; any other status indicates
                failure.

    - abandon
        Version 0:
            A GET operation that aborts an in-flight transaction for the
            Transaction ID specified.  This will discard any data related to
            the transaction.

            Example:
                URL:
                http://pkg.opensolaris.org/abandon/0/1228870796_pkg%3A%2Fsystem%2Flibc%400.1%2C5.11-98%3A20081210T005956Z

            Expects:
                A Transaction ID as output by pkgsend(1) in the request path.

            Returns:
                Response status of 200 on success; any other status indicates
                failure.

    - close
        Version 0:
            A GET operation that ends an in-flight transaction for the
            Transaction ID specified.  If successful, the corresponding package
            is added to the repository catalog and is immediately available to
            repository users.

            Example:
                URL:
                http://pkg.opensolaris.org/abandon/0/1228870796_pkg%3A%2Fsystem%2Flibc%400.1%2C5.11-98%3A20081210T005956Z

            Expects:
                A Transaction ID as output by pkgsend(1) in the request path.

            Returns:
                Response status of 200 on success; any other status indicates
                failure.

    - open
        Version 0:
            A GET operation that starts an in-flight transaction for the
            package FMRI specified.

            Example:
                URL:
                http://pkg.opensolaris.org/open/0/system%2Flibc@0.1-98

            Expects:
                A URL-encoded pkg(5) FMRI (excluding timestamp).

            Returns:
                Response status of 200 on success and an identifier for the new
                transaction in the 'Transaction-ID' response header; any other
                status indicates failure.

