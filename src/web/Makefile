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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

MACH:sh = uname -p

ROOT = ../../proto/root_${MACH}
ROOTSHARE = $(ROOT)/usr/share/lib/pkg
ROOTPKGWEB = $(ROOTSHARE)

WEBCOMPONENTS = \
	$(ROOTPKGWEB)/pkg-block-icon.png \
	$(ROOTPKGWEB)/pkg-block-logo.png \
	$(ROOTPKGWEB)/pkg.css

all := TARGET = all
link := TARGET = link
link-clean := TARGET = link-clean
install := TARGET = install

all:

install: $(WEBCOMPONENTS)

PWD:sh = pwd 
link:
	mkdir -p /usr/share/lib/pkg
	ln -sf $(PWD)/pkg-block-icon.png /usr/share/lib/pkg/pkg-block-icon.png
	ln -sf $(PWD)/pkg-block-logo.png /usr/share/lib/pkg/pkg-block-logo.png
	ln -sf $(PWD)/pkg.css /usr/share/lib/pkg/pkg.css

link-clean:
	rm -rf /usr/share/lib/pkg

clean:

clobber: clean
	rm -f $(ROOTPKGWEB)

$(ROOTPKGWEB)/%: %
	rm -f $@; install -f $(ROOT)/usr/share/lib/pkg -m 0444 $<
