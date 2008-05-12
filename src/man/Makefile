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

MACH:sh = uname -p

ROOT = ../../proto/root_${MACH}
ROOTMAN = $(ROOT)/usr/share/man
ROOTMAN1 = $(ROOTMAN)/cat1
ROOTMAN1M = $(ROOTMAN)/cat1m
ROOTMAN5 = $(ROOTMAN)/cat5

MANPAGES = $(ROOTMAN1)/pkg.1 $(ROOTMAN1)/pkgrecv.1 $(ROOTMAN1)/pkgsend.1 $(ROOTMAN1M)/pkg.depotd.1m $(ROOTMAN5)/pkg.5

all := TARGET = all
link := TARGET = link
link-clean := TARGET = link-clean
install := TARGET = install

all:

install: $(MANPAGES)

PWD:sh = pwd 
link:
	-mkdir -p /usr/share/man/cat1 /usr/share/man/cat1m /usr/share/man/cat5
	ln -sf $(PWD)/pkg.1.txt /usr/share/man/cat1/pkg.1
	ln -sf $(PWD)/pkgrecv.1.txt /usr/share/man/cat1/pkgrecv.1
	ln -sf $(PWD)/pkgsend.1.txt /usr/share/man/cat1/pkgsend.1
	ln -sf $(PWD)/pkg.depotd.1m.txt /usr/share/man/cat1m/pkg.depotd.1m
	ln -sf $(PWD)/pkg.5.txt /usr/share/man/man5/pkg.5

link-clean:
	rm -f /usr/share/man/cat1/pkg.1
	rm -f /usr/share/man/cat1/pkgrecv.1
	rm -f /usr/share/man/cat1/pkgsend.1
	rm -f /usr/share/man/cat1m/pkg.depotd.1m
	rm -f /usr/share/man/cat5/pkg.5

clean:

clobber: clean

$(ROOTMAN1)/%: %.txt
	cp $< $*
	rm -f $@; install -f $(ROOTMAN1) -m 0444 $*

$(ROOTMAN1M)/%: %.txt
	cp $< $*
	rm -f $@; install -f $(ROOTMAN1M) -m 0444 $*

$(ROOTMAN5)/%: %.txt
	cp $< $*
	rm -f $@; install -f $(ROOTMAN5) -m 0444 $*
