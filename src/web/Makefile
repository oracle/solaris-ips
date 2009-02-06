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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#
ROOTSHARE = /usr/lib/share/pkg
RSWEB = $(ROOTSHARE)/web

all:

PWD:sh = pwd
link:
	mkdir -p $(RSWEB)
	ln -sf $(PWD)/en $(RSWEB)/en
	ln -sf $(PWD)/_themes $(RSWEB)/_themes
	ln -sf $(PWD)/config.shtml $(RSWEB)/config.shtml
	ln -sf $(PWD)/index.shtml $(RSWEB)/index.shtml
	ln -sf $(PWD)/robots.txt $(RSWEB)/robots.txt
	ln -sf $(PWD)/shared.shtml $(RSWEB)/shared.shtml

link-clean:
	rm -rf /usr/share/lib/pkg

install: all

clean:

clobber:
