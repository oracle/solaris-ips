#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

#
# Copyright (c) 2024, 2025, Oracle and/or its affiliates.
#

include ../Makefile.constants

ROOTPKGWEB = $(ROOTUSRSHARELIBPKG)/web

WEBFILES:sh = find en/ _themes/ -type f
WEBFILES += \
	config.shtml \
	index.shtml \
	repos.shtml \
	shared.shtml \
	robots.txt

# install same set of files in "en/" in "__LOCALE__/" as well
# for localizable file package (regarding themes, install
# theme "oracle.com" only)
WEBLOCALEFILES1:sh = find en/ -type f
WEBLOCALEFILES2:sh = find _themes/oracle.com/en/ -type f

all:

ROOTPKGWEBFILES = $(WEBFILES:%=$(ROOTPKGWEB)/%)
ROOTPKGWEBLOCALEFILES = \
	$(WEBLOCALEFILES1:en/%=$(ROOTPKGWEB)/__LOCALE__/%) \
	$(WEBLOCALEFILES2:_themes/oracle.com/en/%=$(ROOTPKGWEB)/_themes/oracle.com/__LOCALE__/%)

install: $(ROOTPKGWEBFILES) $(ROOTPKGWEBLOCALEFILES)

$(ROOTPKGWEB)/%: %
	$(INS.file.strip)

$(ROOTPKGWEB)/__LOCALE__/%: en/%
	$(INS.file.strip)

$(ROOTPKGWEB)/_themes/oracle.com/__LOCALE__%: _themes/oracle.com/en/%
	$(INS.file.strip)

# The depot-related repos.shtml is installed from a different location
$(ROOTPKGWEB)/repos.shtml: ../util/apache2/depot/repos.shtml
	$(INS.file.strip)

check lint:

clean:

clobber: clean
