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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

# client.py -> /usr/bin/pkg
# pull.py -> /usr/bin/pkgrecv
# publish.py -> /usr/bin/pkgsend
# depot.py -> /usr/lib/pkg.depotd
#
# pkg/*.py -> /usr/lib/python2.4/vendor-packages/pkg/

MACH:sh = uname -p

KSH=/usr/bin/ksh
PYTHON = /usr/bin/python

ROOT = ../proto/root_${MACH}
ROOTUSRBIN = $(ROOT)/usr/bin
ROOTUSRLIB = $(ROOT)/usr/lib
ROOTSHARE = $(ROOT)/usr/share/lib/pkg
ROOTMANIFEST = $(ROOT)/var/svc/manifest/application
ROOTPYTHON = $(ROOTUSRLIB)/python2.4
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg
ROOTMAN1 = $(ROOT)/usr/share/man/cat1
ROOTMAN1M = $(ROOT)/usr/share/man/cat1m
ROOTMAN5 = $(ROOT)/usr/share/man/cat5

LINKPYTHONPKG = /usr/lib/python2.4/vendor-packages/pkg

VERSION:sh = hg id -i
FILEVERSION = sed -n -e '/^VERSION/s/.*"\([^"]*\)"/\1/p' $@ 2> /dev/null || true

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
	$(ROOTPYTHONPKG)/portable \
	$(ROOTMANIFEST) \
	$(ROOTSHARE) \
	$(ROOTMAN1) \
	$(ROOTMAN1M) \
	$(ROOTMAN5)

PROGS = pkg pkgrecv pkgsend pkg.depotd

ROOTPROGS = \
	$(ROOT)/usr/bin/pkg \
	$(ROOT)/usr/bin/pkgrecv \
	$(ROOT)/usr/bin/pkgsend \
	$(ROOT)/usr/lib/pkg.depotd

PYMODS = \
	modules/__init__.py \
	modules/Queue25.py \
	modules/arch.so \
	modules/catalog.py \
	modules/cfgfiles.py \
	modules/config.py \
	modules/cpiofile.py \
	modules/dependency.py \
	modules/depotcontroller.py \
	modules/elf.so \
	modules/fmri.py \
	modules/manifest.py \
	modules/misc.py \
	modules/pkgtarfile.py \
	modules/smf.py \
	modules/subprocess_method.py \
	modules/sysvpkg.py \
	modules/urlhelpers.py \
	modules/updatelog.py \
	modules/version.py
PYCMODS = $(PYMODS:%.py=%.pyc)

PYACTIONMODS = \
	modules/actions/__init__.py \
	modules/actions/attribute.py \
	modules/actions/depend.py \
	modules/actions/directory.py \
	modules/actions/driver.py \
	modules/actions/file.py \
	modules/actions/generic.py \
	modules/actions/group.py \
	modules/actions/hardlink.py \
	modules/actions/legacy.py \
	modules/actions/license.py \
	modules/actions/link.py \
	modules/actions/unknown.py \
	modules/actions/user.py

PYCACTIONMODS = $(PYACTIONMODS:%.py=%.pyc)

PYSERVERMODS = \
	modules/server/__init__.py \
	modules/server/config.py \
	modules/server/face.py \
	modules/server/transaction.py
PYCSERVERMODS = $(PYSERVERMODS:%.py=%.pyc)

PYCLIENTMODS = \
	modules/client/__init__.py \
	modules/client/bootenv.py \
	modules/client/filelist.py \
	modules/client/filter.py \
	modules/client/image.py \
	modules/client/imageconfig.py \
	modules/client/imageplan.py \
	modules/client/imagetypes.py \
	modules/client/pkgplan.py \
	modules/client/progress.py \
	modules/client/retrieve.py
PYCCLIENTMODS = $(PYCLIENTMODS:%.py=%.pyc)

PYPUBLISHMODS = \
	modules/publish/__init__.py \
	modules/publish/transaction.py
PYCPUBLISHMODS = $(PYPUBLISHMODS:%.py=%.pyc)

PYBUNDLEMODS = \
	modules/bundle/__init__.py \
	modules/bundle/SolarisPackageDatastreamBundle.py \
	modules/bundle/TarBundle.py \
	modules/bundle/SolarisPackageDirBundle.py
PYCBUNDLEMODS = $(PYBUNDLEMODS:%.py=%.pyc)

PYPORTABLEMODS = \
	modules/portable/__init__.py \
	modules/portable/util.py \
	modules/portable/os_unix.py \
	modules/portable/os_sunos.py
PYCPORTABLEMODS = $(PYPORTABLEMODS:%.py=%.pyc)

ROOTPYMODS = $(PYMODS:modules/%=$(ROOTPYTHONPKG)/%)
ROOTPYACTIONMODS = \
	$(PYACTIONMODS:modules/actions/%=$(ROOTPYTHONPKG)/actions/%)
ROOTPYSERVERMODS = \
	$(PYSERVERMODS:modules/server/%=$(ROOTPYTHONPKG)/server/%)
ROOTPYPUBLISHMODS = \
	$(PYPUBLISHMODS:modules/publish/%=$(ROOTPYTHONPKG)/publish/%)
ROOTPYCLIENTMODS = \
	$(PYCLIENTMODS:modules/client/%=$(ROOTPYTHONPKG)/client/%)
ROOTPYBUNDLEMODS = \
	$(PYBUNDLEMODS:modules/bundle/%=$(ROOTPYTHONPKG)/bundle/%)
ROOTPYPORTABLEMODS = \
	$(PYPORTABLEMODS:modules/portable/%=$(ROOTPYTHONPKG)/portable/%)

ROOTPYCALLMODS = \
	$(ROOTPYMODS:%.py=%.pyc) \
	$(ROOTPYACTIONMODS:%.py=%.pyc) \
	$(ROOTPYSERVERMODS:%.py=%.pyc) \
	$(ROOTPYPUBLISHMODS:%.py=%.pyc) \
	$(ROOTPYCLIENTMODS:%.py=%.pyc) \
	$(ROOTPYBUNDLEMODS:%.py=%.pyc) \
	$(ROOTPYPORTABLEMODS:%.py=%.pyc)

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
	$(ROOTPYBUNDLEMODS) \
	$(ROOTPYPORTABLEMODS) \
	$(ROOTPYCALLMODS) \
	$(ROOTPKGMANIFEST)

all := TARGET = all
link := TARGET = link
install := TARGET = install
link-clean := TARGET = link-clean
clean := TARGET = clean
clobber := TARGET = clobber
test := TARGET = test
test-verbose := TARGET = test-verbose

all: $(PROGS) binary-modules

clean:
	rm -f $(PROGS)
	@cd modules; pwd; $(MAKE) $(TARGET)
	@cd man; pwd; $(MAKE) $(TARGET)
	@cd web; pwd; $(MAKE) $(TARGET)
	@cd tests; pwd; $(MAKE) $(TARGET)

clobber: clean
	rm -fr $(ROOT)
	rm -f $(PYCMODS) $(PYCACTIONMODS) $(PYCSERVERMODS) \
	$(PYCPUBLISHMODS) $(PYCCLIENTMODS) $(PYCBUNDLEMODS) \
	$(PYCPORTABLEMODS)
	@cd modules; pwd; $(MAKE) $(TARGET)
	@cd man; pwd; $(MAKE) $(TARGET)
	@cd web; pwd; $(MAKE) $(TARGET)

install: all $(ROOTCOMPONENTS)
	@cd brand; pwd; $(MAKE) $(TARGET)
	@cd man; pwd; $(MAKE) $(TARGET)
	@cd web; pwd; $(MAKE) $(TARGET)
	@cd pkgdefs; pwd; $(MAKE) $(TARGET)

modules/%.pyc: modules/%.py
	python -m compileall -l $(@D)

binary-modules:
	@cd modules; pwd; $(MAKE) $(TARGET)

# XXX link is a developer target to connect the local machine to the current
# repository's working copy's versions of the commands, modules, and supporting
# files.
PWD:sh = pwd
link:
	ln -sf $(PWD)/client.py /usr/bin/pkg
	ln -sf $(PWD)/pull.py /usr/bin/pkgrecv
	ln -sf $(PWD)/publish.py /usr/bin/pkgsend
	ln -sf $(PWD)/depot.py /usr/lib/pkg.depotd
	ln -sf $(PWD)/modules /usr/lib/python2.4/vendor-packages/pkg
	ln -sf $(PWD)/pkg-server.xml /var/svc/manifest/application/pkg-server.xml
	@cd web; pwd; $(MAKE) $(TARGET)
	@cd brand; pwd; $(MAKE) $(TARGET)
	@cd man; pwd; $(MAKE) $(TARGET)

link-clean:
	rm -f /usr/bin/pkg
	rm -f /usr/bin/pkgrecv
	rm -f /usr/bin/pkgsend
	rm -f /usr/lib/pkg.depotd
	rm -f /usr/lib/python2.4/vendor-packages/pkg
	rm -f /var/svc/manifest/application/pkg-server.xml
	@cd web; pwd; $(MAKE) $(TARGET)
	@cd brand; pwd; $(MAKE) $(TARGET)
	@cd man; pwd; $(MAKE) $(TARGET)

test:
	@cd tests; pwd; $(MAKE) $(TARGET)

test-verbose: test

proto: $(ROOT)

$(ROOT):
	mkdir -p $(ROOTDIRS)

$(ROOTUSRBIN)/%: %
	rm -f $@; install -f $(ROOTUSRBIN) -m 0555 $<

$(ROOTUSRLIB)/%: %
	rm -f $@; install -f $(ROOT)/usr/lib -m 0555 $<

$(ROOTPYTHONPKG)/__init__.py: FRC
	if [ "$(VERSION)" != "$(FILEVERSION:sh)" ]; then \
		rm -f $@; \
		cat modules/__init__.py | \
			sed -e '/^VERSION/s/"[^"]*"/"$(VERSION)"/' > $@; \
		chmod 0444 $@; \
	fi

$(ROOTPYTHONPKG)/__init__.pyc: $(ROOTPYTHONPKG)/__init__.py
	python -m py_compile $(ROOTPYTHONPKG)/__init__.py

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

$(ROOTPYTHONPKG)/portable/%: modules/portable/%
	rm -f $@; install -f $(ROOTPYTHONPKG)/portable -m 0444 $<

$(ROOTPYTHONPKG)/%.so: modules/%.so
	rm -f $@; install -f $(ROOTPYTHONPKG) -m 0555 $<

$(ROOTPYTHONPKG)/%: modules/%
	rm -f $@; install -f $(ROOTPYTHONPKG) -m 0444 $<

$(ROOTMANIFEST)/%: %
	rm -f $@; install -f $(ROOTMANIFEST) -m 0444 $<

pkg: client.py
	cp client.py pkg

pkgrecv: pull.py
	cp pull.py pkgrecv

pkgsend: publish.py
	cp publish.py pkgsend

pkg.depotd: depot.py
	cp depot.py pkg.depotd

FRC:
