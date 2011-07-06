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
# Copyright (c) 2007, 2011, Oracle and/or its affiliates. All rights reserved.
#

MACH:sh = uname -p

INSTALL = /usr/sbin/install

ROOT = ../../proto/root_${MACH}
ROOTETC = $(ROOT)/etc
ROOTETCBRAND = $(ROOT)/etc/brand/ipkg
ROOTUSRLIB = $(ROOT)/usr/lib
ROOTBRAND = $(ROOTUSRLIB)/brand
ROOTBRANDPKG = $(ROOTBRAND)/ipkg

LINKBRANDPKG = /usr/lib/brand/ipkg

ROOTDIRS = \
	$(ROOT) \
	$(ROOTETC) \
	$(ROOTETCBRAND) \
	$(ROOTUSRLIB) \
	$(ROOTBRAND) \
	$(ROOTBRANDPKG)

ROOTBINS = \
	$(ROOTBRANDPKG)/attach \
	$(ROOTBRANDPKG)/boot \
	$(ROOTBRANDPKG)/clone \
	$(ROOTBRANDPKG)/detach \
	$(ROOTBRANDPKG)/halt \
	$(ROOTBRANDPKG)/image_install \
	$(ROOTBRANDPKG)/p2v \
	$(ROOTBRANDPKG)/pkgcreatezone \
	$(ROOTBRANDPKG)/poststate \
	$(ROOTBRANDPKG)/prestate \
	$(ROOTBRANDPKG)/support \
	$(ROOTBRANDPKG)/sysboot \
	$(ROOTBRANDPKG)/uninstall

ROOTFILES = \
	$(ROOTBRANDPKG)/common.ksh \
	$(ROOTBRANDPKG)/developerenv.ksh \
	$(ROOTBRANDPKG)/pkgrm.lst \
	$(ROOTBRANDPKG)/smf_disable.lst \
	$(ROOTETCBRAND)/pkgrm.conf \
	$(ROOTETCBRAND)/smf_disable.conf

BIN = \
	support \

FILEMODE = 0444
$(ROOTBINS) := FILEMODE = 755
$(ROOTETCBRAND)/% := FILEMODE = 644


support := LDLIBS = -lzonecfg

all := TARGET = all


support: support.c
	$(LINK.c) -o $@ $@.c $(LDLIBS)

all:

clean:
	rm -f $(BIN)

clobber: clean
	rm -f $(ROOTFILES) $(ROOTBINS)
	rm -fr $(ROOTBRAND)

install: $(ROOTFILES) $(ROOTBINS)


$(ROOT) $(ROOTETC) $(ROOTETCBRAND) $(ROOTUSRLIB) \
	$(ROOTBRAND) $(ROOTBRANDPKG):
	mkdir -p $@

$(ROOTETCBRAND)/%: $(ROOTETCBRAND) %
	rm -f $@; $(INSTALL) -f $(ROOTETCBRAND) -m $(FILEMODE) $<

$(ROOTBRANDPKG)/%: $(ROOTBRANDPKG) %
	rm -f $@; $(INSTALL) -f $(ROOTBRANDPKG) -m $(FILEMODE) $<
