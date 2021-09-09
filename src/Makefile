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
# Copyright (c) 2007, 2021, Oracle and/or its affiliates.
#

PYTHON37 = /usr/bin/python3.7

all := TARGET = all
install := TARGET = install
packages := TARGET = install
clean := TARGET = clean
clobber := TARGET = clobber
lint := TARGET = lint
clint := TARGET = clint
pylint := TARGET = pylint
check := TARGET = check
test := TARGET = test
test-verbose := TARGET = test-verbose
test-generate := TARGET = test-generate

#
# clear PYTHONPATH when invoking /usr/bin/pkg (we don't want to load any
# pkg python modules from this workspace since they may be out of sync
# with the pkg modules in the root filesystem).
#
PYLINT_VER_CMD = PYTHONPATH= /usr/bin/pkg info pkg:/developer/python/pylint | \
	/usr/bin/grep Version | \
	/usr/bin/awk -F: '{print $$2}' | /usr/bin/sed -e 's/ //g'

PYCODESTYLE = /usr/bin/pycodestyle
JOBS = 4

SUBDIRS=zoneproxy util/mkcert man

all: $(SUBDIRS)
	$(PYTHON37) setup.py build

clean: $(SUBDIRS)
	$(PYTHON37) setup.py clean
	@cd pkg; pwd; make clean

clobber: $(SUBDIRS)
	$(PYTHON37) setup.py clobber
	@cd pkg; pwd; make clobber

#
# run pylint as part of the install target.
# it's the best way to ensure things stay pylint clean.
#
install: $(SUBDIRS)
	$(PYTHON37) setup.py install

lint:
	$(PYTHON37) setup.py lint
	@cd zoneproxy; pwd; make lint

clint:
	$(PYTHON37) setup.py clint
	@cd zoneproxy; pwd; make lint

pylint: install
	PYLINT_VER=$(PYLINT_VER_CMD:sh) $(PYTHON37) setup.py pylint_py3k

bandit:
	$(PYTHON37) setup.py bandit

check:
	$(PYCODESTYLE) --statistics --count `cat tests/pycodestyle-whitelist.txt`

#
# This rule propagates the current make target through all of the
# subdirectories in $SUBDIRS.
#
$(SUBDIRS): FRC
	@cd $@; pwd; $(MAKE) $(TARGET)

# Use the bits we just built to create the packages.
packages: install pylint check bandit
	@cd pkg; pwd; $(MAKE) $(TARGET) check \
		PATH=$$(hg root)/proto/root_$$(uname -p)/usr/bin:$$PATH

# Just packages with no checking
justpackages: install
	@cd pkg; pwd; $(MAKE) $(TARGET) repository-metadata \
		PATH=$$(hg root)/proto/root_$$(uname -p)/usr/bin:$$PATH

dist:
	hg archive -r default -p pkg7-%h ../pkg7-%h.tar.bz2

test-37:
	$(PYTHON37) tests/run.py -j ${JOBS} -v

test:
	$(MAKE) -k test-37 JOBS=${JOBS}

test-verbose:
	$(PYTHON37) setup.py test -v

test-generate:
	$(PYTHON37) setup.py test -g

FRC:
