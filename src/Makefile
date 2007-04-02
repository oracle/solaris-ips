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
#ident	"$Hg$ SMI"

# client.py -> /usr/bin/pkg
# publish.py -> /usr/bin/pkgsend
# depot.py -> /usr/lib/pkg.depotd
#
# pkg/*.py -> /usr/lib/python2.4/vendor-packages/pkg/

MACH:sh = uname -p

ROOT = ../proto/root_${MACH}
ROOTUSRBIN = $(ROOT)/usr/bin
ROOTUSRLIB = $(ROOT)/usr/lib
ROOTPYTHON = $(ROOTUSRLIB)/python2.4
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg

ROOTDIRS = $(ROOT) $(ROOTUSRBIN) $(ROOTUSRLIB) $(ROOTPYTHONPKG)

PROGS = pkg pkgsend pkg.depotd
ROOTPROGS = \
	$(ROOT)/usr/bin/pkg \
	$(ROOT)/usr/bin/pkgsend \
	$(ROOT)/usr/lib/pkg.depotd

PYMODS = \
	pkg-modules/config.py \
	pkg-modules/fmri.py \
	pkg-modules/version.py
ROOTPYMODS = $(PYMODS:pkg-modules/%=$(ROOTPYTHONPKG)/%)

all: $(PROGS)

install: $(ROOTDIRS) $(ROOTPROGS) $(ROOTPYMODS)

$(ROOT) $(ROOTUSRBIN) $(ROOTUSRLIB) $(ROOTPYTHONPKG):
	mkdir -p $(ROOT)
	mkdir -p $(ROOTUSRBIN)
	mkdir -p $(ROOTUSRLIB)
	mkdir -p $(ROOTPYTHONPKG)

$(ROOTUSRBIN)/%: %
	install -f $(ROOTUSRBIN) -m 0555 $<

$(ROOTUSRLIB)/%: %
	install -f $(ROOT)/usr/lib -m 0555 $<

$(ROOTPYTHONPKG)/%: pkg-modules/%
	install -f $(ROOTPYTHONPKG) -m 0444 $<

pkg: client.py
	cp client.py pkg

pkgsend: publish.py
	cp publish.py pkgsend

pkg.depotd: depot.py
	cp depot.py pkg.depotd

