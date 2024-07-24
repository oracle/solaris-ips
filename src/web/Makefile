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
# Copyright (c) 2024, Oracle and/or its affiliates.
#

INSTALL:sh =	echo /opt/onbld/bin/$(uname -p)/stash file -v

PROTO_AREA:sh =	echo $(dirname $(dirname $(pwd)))/proto/root_$(uname -p)
WEB_DIR = $(PROTO_AREA)/usr/share/lib/pkg/web

WEB_FILES = \
	*.shtml \
	_themes/*.png \
	_themes/default/en/* \
	_themes/default/feed-icon-14x14.png \
	_themes/opensolaris.com/en/* \
	_themes/opensolaris.org/en/* \
	_themes/opensolaris.org/feed-icon-14x14.png \
	_themes/oracle.com/*.png \
	_themes/oracle.com/en/* \
	_themes/pkg-block-logo.svg \
	_themes/sun.com/en/* \
	_themes/yui-reset-font-grids_base-min.css \
	en/* \
	robots.txt

# install same set of files in "en/" in "__LOCALE__/" as well
# for localizable file package (regarding themes, install
# theme "oracle.com" only)
LOCALIZABLE_WEB_FILES = \
	en/* \
	_themes/oracle.com/en/*

all:

install:
	@for file in $(WEB_FILES); do \
		$(INSTALL) -C $$file $(WEB_DIR)/$$file; \
	done; \
	for file in $(LOCALIZABLE_WEB_FILES); do \
		$(INSTALL) -C $$file $(WEB_DIR)/$${file/en/__LOCALE__}; \
	done; \
	# The apache-based depot includes an shtml file we add to the web dir \
	$(INSTALL) -C ../util/apache2/depot/repos.shtml $(WEB_DIR)/repos.shtml

check lint:

clean:

clobber: clean
