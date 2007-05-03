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

# client.py -> /usr/bin/pkg
# publish.py -> /usr/bin/pkgsend
# depot.py -> /usr/lib/pkg.depotd
#
# pkg/*.py -> /usr/lib/python2.4/vendor-packages/pkg/

MACH:sh = uname -p

PYTHON = /usr/bin/python

ROOT = ../proto/root_${MACH}
ROOTUSRBIN = $(ROOT)/usr/bin
ROOTUSRLIB = $(ROOT)/usr/lib
ROOTPYTHON = $(ROOTUSRLIB)/python2.4
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg

LINKPYTHONPKG = /usr/lib/python2.4/vendor-packages/pkg

ROOTDIRS = \
	$(ROOT) \
	$(ROOTUSRBIN) \
	$(ROOTUSRLIB) \
	$(ROOTPYTHONPKG)/server \
	$(ROOTPYTHONPKG)/publish \
	$(ROOTPYTHONPKG)/client

PROGS = pkg pkgsend pkg.depotd
ROOTPROGS = \
	$(ROOT)/usr/bin/pkg \
	$(ROOT)/usr/bin/pkgsend \
	$(ROOT)/usr/lib/pkg.depotd

PYMODS = \
	pkg-modules/__init__.py \
	pkg-modules/config.py \
	pkg-modules/content.py \
	pkg-modules/dependency.py \
	pkg-modules/fmri.py \
	pkg-modules/package.py \
	pkg-modules/sysvpkg.py \
	pkg-modules/version.py

PYSERVERMODS = \
	pkg-modules/server/__init__.py \
	pkg-modules/server/catalog.py \
	pkg-modules/server/config.py \
	pkg-modules/server/package.py \
	pkg-modules/server/transaction.py

PYCLIENTMODS = \
	pkg-modules/client/arch.so \
	pkg-modules/client/__init__.py \
	pkg-modules/client/catalog.py \
	pkg-modules/client/image.py

PYPUBLISHMODS = \
	pkg-modules/publish/__init__.py \
	pkg-modules/server/transaction.py

ROOTPYMODS = $(PYMODS:pkg-modules/%=$(ROOTPYTHONPKG)/%)
ROOTPYSERVERMODS = \
	$(PYSERVERMODS:pkg-modules/server/%=$(ROOTPYTHONPKG)/server/%)
ROOTPYPUBLISHMODS = \
	$(PYPUBLISHMODS:pkg-modules/publish/%=$(ROOTPYTHONPKG)/publish/%)
ROOTPYCLIENTMODS = \
	$(PYCLIENTMODS:pkg-modules/client/%=$(ROOTPYTHONPKG)/client/%)

all := TARGET = all

all: $(PROGS) client-mods

clean:
	rm -f $(PROGS)

install: $(ROOTDIRS) $(ROOTPROGS) $(ROOTPYMODS) $(ROOTPYSERVERMODS) \
	$(ROOTPYPUBLISHMODS) $(ROOTPYCLIENTMODS)

client-mods:
	@cd pkg-modules/client; pwd; $(MAKE) $(TARGET)

# XXX link is a developer target to connect the local machine to the current
# repository's working copy's versions of the commands and modules.
PWD:sh = pwd
link:
	ln -s $(PWD)/client.py /usr/bin/pkg
	ln -s $(PWD)/publish.py /usr/bin/pkgsend
	ln -s $(PWD)/depot.py /usr/lib/pkg.depotd
	ln -s $(PWD)/pkg-modules /usr/lib/python2.4/vendor-packages/pkg

# Invoke all known modules with tests.
test:
	$(PYTHON) $(LINKPYTHONPKG)/version.py
	$(PYTHON) $(LINKPYTHONPKG)/fmri.py

$(ROOT) $(ROOTUSRBIN) $(ROOTUSRLIB):
	mkdir -p $(ROOT)
	mkdir -p $(ROOTUSRBIN)
	mkdir -p $(ROOTUSRLIB)

$(ROOTPYTHONPKG) $(ROOTPYTHONPKG)/server:
	mkdir -p $(ROOTPYTHONPKG)/server

$(ROOTPYTHONPKG)/publish:
	mkdir -p $(ROOTPYTHONPKG)/publish

$(ROOTPYTHONPKG)/client:
	mkdir -p $(ROOTPYTHONPKG)/client

$(ROOTUSRBIN)/%: %
	rm -f $@; install -f $(ROOTUSRBIN) -m 0555 $<

$(ROOTUSRLIB)/%: %
	rm -f $@; install -f $(ROOT)/usr/lib -m 0555 $<

$(ROOTPYTHONPKG)/server/%: pkg-modules/server/%
	rm -f $@; install -f $(ROOTPYTHONPKG)/server -m 0444 $<

$(ROOTPYTHONPKG)/publish/%: pkg-modules/publish/%
	rm -f $@; install -f $(ROOTPYTHONPKG)/publish -m 0444 $<

$(ROOTPYTHONPKG)/client/%.so: pkg-modules/client/%.so
	rm -f $@; install -f $(ROOTPYTHONPKG)/client -m 0555 $<

$(ROOTPYTHONPKG)/client/%: pkg-modules/client/%
	rm -f $@; install -f $(ROOTPYTHONPKG)/client -m 0444 $<

$(ROOTPYTHONPKG)/%: pkg-modules/%
	rm -f $@; install -f $(ROOTPYTHONPKG) -m 0444 $<

pkg: client.py
	cp client.py pkg

pkgsend: publish.py
	cp publish.py pkgsend

pkg.depotd: depot.py
	cp depot.py pkg.depotd
