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

# client.py -> /usr/bin/pkg
# pkgdep.py -> /usr/bin/pkgdep
# pull.py -> /usr/bin/pkgrecv
# publish.py -> /usr/bin/pkgsend
# depot.py -> /usr/lib/pkg.depotd
#
# pkg/*.py -> /usr/lib/python2.4/vendor-packages/pkg/

PYTHON = /usr/bin/python

all := TARGET = all
link := TARGET = link
install := TARGET = install
packages := TARGET = packages
link-clean := TARGET = link-clean
clean := TARGET = clean
clobber := TARGET = clobber
coverage := TARGET = coverage
test := TARGET = test
test-verbose := TARGET = test-verbose
test-generate := TARGET = test-generate
test-leaks := TARGET = test-leaks

SUBDIRS=web gui um po util/misc brand

all: $(SUBDIRS)
	$(PYTHON) setup.py build

clean: $(SUBDIRS)
	$(PYTHON) setup.py clean
	@cd pkgdefs; pwd; make clean

clobber: $(SUBDIRS)
	$(PYTHON) setup.py clobber
	@cd pkgdefs; pwd; make clobber

install: $(SUBDIRS)
	$(PYTHON) setup.py install

#
# This rule propagates the current make target through all of the
# subdirectories in $SUBDIRS.
#
$(SUBDIRS): FRC
	@cd $@; pwd; $(MAKE) $(TARGET)

packages: install
	@cd pkgdefs; pwd; $(MAKE) $(TARGET) check

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
	ln -sf $(PWD)/pkg-update.xml /var/svc/manifest/application/pkg-update.xml
	@cd web; pwd; $(MAKE) $(TARGET)
	@cd brand; pwd; $(MAKE) $(TARGET)
	@cd man; pwd; $(MAKE) $(TARGET)
	@cd gui; pwd; $(MAKE) $(TARGET)
	@cd um; pwd; $(MAKE) $(TARGET)

link-clean:
	rm -f /usr/bin/pkg
	rm -f /usr/bin/pkgrecv
	rm -f /usr/bin/pkgsend
	rm -f /usr/lib/pkg.depotd
	rm -f /usr/lib/python2.4/vendor-packages/pkg
	rm -f /var/svc/manifest/application/pkg-server.xml
	rm -f /var/svc/manifest/application/pkg-update.xml
	@cd web; pwd; $(MAKE) $(TARGET)
	@cd brand; pwd; $(MAKE) $(TARGET)
	@cd man; pwd; $(MAKE) $(TARGET)
	@cd gui; pwd; $(MAKE) $(TARGET)
	@cd um; pwd; $(MAKE) $(TARGET)

test:
	$(PYTHON) setup.py test

test-verbose:
	$(PYTHON) setup.py test -v

test-generate: 
	$(PYTHON) setup.py test -g

test-leaks:
	@cd tests; pwd; /bin/ksh memleaks.ksh

coverage:
	$(PYTHON) setup.py coverage

FRC:
