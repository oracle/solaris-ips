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
ROOTSHARE = $(ROOT)/usr/share/lib/pkg
ROOTMANIFEST = $(ROOT)/var/svc/manifest
ROOTPYTHON = $(ROOTUSRLIB)/python2.4
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg
ROOTMAN1 = $(ROOT)/usr/share/man/cat1
ROOTMAN1M = $(ROOT)/usr/share/man/cat1m

LINKPYTHONPKG = /usr/lib/python2.4/vendor-packages/pkg

ROOTDIRS = \
	$(ROOT) \
	$(ROOTUSRBIN) \
	$(ROOTUSRLIB) \
	$(ROOTPYTHONPKG)/actions \
	$(ROOTPYTHONPKG)/server \
	$(ROOTPYTHONPKG)/publish \
	$(ROOTPYTHONPKG)/client \
	$(ROOTPYTHONPKG)/actions \
	$(ROOTPYTHONPKG)/bundle \
	$(ROOTMANIFEST) \
	$(ROOTSHARE) \
	$(ROOTMAN1) \
	$(ROOTMAN1M)

PROGS = pkg pkgsend pkg.depotd

ROOTPROGS = \
	$(ROOT)/usr/bin/pkg \
	$(ROOT)/usr/bin/pkgsend \
	$(ROOT)/usr/lib/pkg.depotd

PYMODS = \
	modules/__init__.py \
	modules/Queue25.py \
	modules/arch.so \
	modules/catalog.py \
	modules/config.py \
	modules/cpiofile.py \
	modules/dependency.py \
	modules/elf.so \
	modules/fmri.py \
	modules/manifest.py \
	modules/misc.py \
	modules/package.py \
	modules/smf.py \
	modules/sysvpkg.py \
	modules/version.py

PYACTIONMODS = \
	modules/actions/__init__.py \
	modules/actions/attribute.py \
	modules/actions/depend.py \
	modules/actions/directory.py \
	modules/actions/driver.py \
	modules/actions/file.py \
	modules/actions/generic.py \
	modules/actions/hardlink.py \
	modules/actions/link.py \
	modules/actions/unknown.py

PYSERVERMODS = \
	modules/server/__init__.py \
	modules/server/config.py \
	modules/server/face.py \
	modules/server/transaction.py

PYCLIENTMODS = \
	modules/client/__init__.py \
	modules/client/filelist.py \
	modules/client/filter.py \
	modules/client/image.py \
	modules/client/imageconfig.py \
	modules/client/imageplan.py \
	modules/client/pkgplan.py \
	modules/client/retrieve.py

PYPUBLISHMODS = \
	modules/publish/__init__.py \
	modules/publish/transaction.py

PYBUNDLEMODS = \
	modules/bundle/__init__.py \
	modules/bundle/SolarisPackageDatastreamBundle.py \
	modules/bundle/TarBundle.py \
	modules/bundle/SolarisPackageDirBundle.py

ROOTPYMODS = $(PYMODS:modules/%=$(ROOTPYTHONPKG)/%)
ROOTPYACTIONMODS = \
	$(PYACTIONMODS:modules/actions/%=$(ROOTPYTHONPKG)/actions/%)
ROOTPYSERVERMODS = \
	$(PYSERVERMODS:modules/server/%=$(ROOTPYTHONPKG)/server/%)
ROOTPYPUBLISHMODS = \
	$(PYPUBLISHMODS:modules/publish/%=$(ROOTPYTHONPKG)/publish/%)
ROOTPYCLIENTMODS = \
	$(PYCLIENTMODS:modules/client/%=$(ROOTPYTHONPKG)/client/%)
ROOTPYACTIONMODS = \
	$(PYACTIONMODS:modules/actions/%=$(ROOTPYTHONPKG)/actions/%)
ROOTPYBUNDLEMODS = \
	$(PYBUNDLEMODS:modules/bundle/%=$(ROOTPYTHONPKG)/bundle/%)

ROOTPKGMANIFEST = $(ROOTMANIFEST)/pkg-server.xml

ROOTPKGWEB = $(ROOTSHARE)/pkg-block-logo.png

ROOTCOMPONENTS = \
	$(ROOTDIRS) \
	$(ROOTPROGS) \
	$(ROOTPYMODS) \
	$(ROOTPYACTIONMODS) \
	$(ROOTPYSERVERMODS) \
	$(ROOTPYPUBLISHMODS) \
	$(ROOTPYCLIENTMODS) \
	$(ROOTPYACTIONMODS) \
	$(ROOTPYBUNDLEMODS)

all := TARGET = all
link := TARGET = link
install := TARGET = install
link-clean := TARGET = link-clean

all: $(PROGS) binary-modules

clean:
	rm -f $(PROGS)

clobber: clean
	rm -fr $(ROOT)

install: all $(ROOTCOMPONENTS)
	@cd brand; pwd; $(MAKE) $(TARGET)
	@cd man; pwd; $(MAKE) $(TARGET)
	@cd web; pwd; $(MAKE) $(TARGET)
	@cd pkgdefs; pwd; $(MAKE) $(TARGET)

binary-modules:
	@cd modules; pwd; $(MAKE) $(TARGET)

# XXX link is a developer target to connect the local machine to the current
# repository's working copy's versions of the commands, modules, and supporting
# files.
PWD:sh = pwd
link:
	ln -sf $(PWD)/client.py /usr/bin/pkg
	ln -sf $(PWD)/publish.py /usr/bin/pkgsend
	ln -sf $(PWD)/depot.py /usr/lib/pkg.depotd
	ln -sf $(PWD)/modules /usr/lib/python2.4/vendor-packages/pkg
	@cd web; pwd; $(MAKE) $(TARGET)
	@cd brand; pwd; $(MAKE) $(TARGET)
	@cd man; pwd; $(MAKE) $(TARGET)

link-clean:
	rm -f /usr/bin/pkg
	rm -f /usr/bin/pkgsend
	rm -f /usr/lib/pkg.depotd
	rm -f /usr/lib/python2.4/vendor-packages/pkg
	@cd web; pwd; $(MAKE) $(TARGET)
	@cd brand; pwd; $(MAKE) $(TARGET)
	@cd man; pwd; $(MAKE) $(TARGET)
        
# Invoke all known modules with tests.
# XXX Invoke the bundle tests.
test:
	# $(PYTHON) $(LINKPYTHONPKG)/bundle/__init__.py a_sysv_pkg
	# $(PYTHON) $(LINKPYTHONPKG)/bundle/__init__.py a_tarball
	$(PYTHON) $(LINKPYTHONPKG)/misc.py
	$(PYTHON) $(LINKPYTHONPKG)/version.py
	$(PYTHON) $(LINKPYTHONPKG)/fmri.py
	$(PYTHON) $(LINKPYTHONPKG)/catalog.py
	$(PYTHON) $(LINKPYTHONPKG)/manifest.py
	$(PYTHON) $(LINKPYTHONPKG)/smf.py
	$(PYTHON) $(LINKPYTHONPKG)/client/imageconfig.py
	$(PYTHON) $(LINKPYTHONPKG)/client/filter.py

proto: $(ROOT)

$(ROOT):
	mkdir -p $(ROOTDIRS)

$(ROOTUSRBIN)/%: %
	rm -f $@; install -f $(ROOTUSRBIN) -m 0555 $<

$(ROOTUSRLIB)/%: %
	rm -f $@; install -f $(ROOT)/usr/lib -m 0555 $<

$(ROOTPYTHONPKG)/actions/%: modules/actions/%
	rm -f $@; install -f $(ROOTPYTHONPKG)/actions -m 0444 $<

$(ROOTPYTHONPKG)/server/%: modules/server/%
	rm -f $@; install -f $(ROOTPYTHONPKG)/server -m 0444 $<

$(ROOTPYTHONPKG)/publish/%: modules/publish/%
	rm -f $@; install -f $(ROOTPYTHONPKG)/publish -m 0444 $<

$(ROOTPYTHONPKG)/client/%: modules/client/%
	rm -f $@; install -f $(ROOTPYTHONPKG)/client -m 0444 $<

$(ROOTPYTHONPKG)/bundle/%: modules/bundle/%
	rm -f $@; install -f $(ROOTPYTHONPKG)/bundle -m 0444 $<

$(ROOTPYTHONPKG)/%.so: modules/%.so
	rm -f $@; install -f $(ROOTPYTHONPKG) -m 0555 $<

$(ROOTPYTHONPKG)/%: modules/%
	rm -f $@; install -f $(ROOTPYTHONPKG) -m 0444 $<

pkg: client.py
	cp client.py pkg

pkgsend: publish.py
	cp publish.py pkgsend

pkg.depotd: depot.py
	cp depot.py pkg.depotd
