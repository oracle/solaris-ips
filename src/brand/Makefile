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


MACH:sh = uname -p

PYTHON = /usr/bin/python
INSTALL = /usr/sbin/install

ROOT = ../../proto/root_${MACH}
ROOTETC = $(ROOT)/etc
ROOTETCZONES = $(ROOT)/etc/zones
ROOTUSRLIB = $(ROOT)/usr/lib
ROOTBRAND = $(ROOTUSRLIB)/brand
ROOTBRANDPKG = $(ROOTBRAND)/ipkg

LINKBRANDPKG = /usr/lib/brand/ipkg

ROOTDIRS = \
	$(ROOT) \
	$(ROOTETC) \
	$(ROOTETCZONES) \
	$(ROOTUSRLIB) \
	$(ROOTBRAND) \
	$(ROOTBRANDPKG)

ROOTFILES = \
	$(ROOTETCZONES)/SUNWipkg.xml \
	$(ROOTBRANDPKG)/config.xml \
	$(ROOTBRANDPKG)/platform.xml \
	$(ROOTBRANDPKG)/attach \
	$(ROOTBRANDPKG)/clone \
	$(ROOTBRANDPKG)/common.ksh \
	$(ROOTBRANDPKG)/detach \
	$(ROOTBRANDPKG)/pkgcreatezone \
	$(ROOTBRANDPKG)/poststate \
	$(ROOTBRANDPKG)/prestate \
	$(ROOTBRANDPKG)/query \
	$(ROOTBRANDPKG)/uninstall

all := TARGET = all
link := TARGET = link
link-clean := TARGET = link-clean

all:

clean:

clobber: clean
	rm -f $(ROOTFILES)
	rm -fr $(ROOTBRAND)

install: $(ROOTFILES)

# XXX link is a developer target to connect the local machine to the current
# repository's working copy's versions of the commands and modules.
PWD:sh = pwd
link:
	mkdir -p /usr/lib/brand/ipkg
	ln -sf $(PWD)/config.xml /usr/lib/brand/ipkg/config.xml
	ln -sf $(PWD)/platform.xml /usr/lib/brand/ipkg/platform.xml
	ln -sf $(PWD)/attach /usr/lib/brand/ipkg/attach
	ln -sf $(PWD)/clone /usr/lib/brand/ipkg/clone
	ln -sf $(PWD)/common.ksh /usr/lib/brand/ipkg/common.ksh
	ln -sf $(PWD)/detach /usr/lib/brand/ipkg/detach
	ln -sf $(PWD)/pkgcreatezone /usr/lib/brand/ipkg/pkgcreatezone
	ln -sf $(PWD)/poststate /usr/lib/brand/ipkg/poststate
	ln -sf $(PWD)/prestate /usr/lib/brand/ipkg/prestate
	ln -sf $(PWD)/query /usr/lib/brand/ipkg/query
	ln -sf $(PWD)/uninstall /usr/lib/brand/ipkg/uninstall
	ln -sf $(PWD)/SUNWipkg.xml /etc/zones/SUNWipkg.xml

link-clean:
	rm -rf /usr/lib/brand/ipkg
	rm -f /etc/zones/SUNWipkg.xml

$(ROOT) $(ROOTETC) $(ROOTETCZONES) $(ROOTUSRLIB) $(ROOTBRAND) $(ROOTBRANDPKG):
	mkdir -p $@

$(ROOTETCZONES)/%: $(ROOTETCZONES) %
	rm -f $@; $(INSTALL) -f $(ROOTETCZONES) -m 0444 $<

$(ROOTBRANDPKG)/%: $(ROOTBRANDPKG) %
	rm -f $@; $(INSTALL) -f $(ROOTBRANDPKG) -m 0444 $<
