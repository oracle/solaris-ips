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

PYTHON = /usr/bin/python2.6

all := TARGET = all
install := TARGET = install
packages := TARGET = install
clean := TARGET = clean
clobber := TARGET = clobber
lint := TARGET = lint
clint := TARGET = clint
pylint := TARGET = pylint
test := TARGET = test
test-verbose := TARGET = test-verbose
test-generate := TARGET = test-generate
test-leaks := TARGET = test-leaks

SUBDIRS=web gui um po util/misc brand zoneproxy

all: $(SUBDIRS)
	$(PYTHON) setup.py build

clean: $(SUBDIRS)
	$(PYTHON) setup.py clean
	@cd pkg; pwd; make clean

clobber: $(SUBDIRS)
	$(PYTHON) setup.py clobber
	@cd pkg; pwd; make clobber

#
# run pylint as part of the install target.
# it's the best way to ensure things stay pylint clean.
#
install: $(SUBDIRS)
	$(PYTHON) setup.py install
	$(PYTHON) setup.py pylint_quiet

lint:
	$(PYTHON) setup.py lint

clint:
	$(PYTHON) setup.py clint

pylint:
	$(PYTHON) setup.py pylint

#
# This rule propagates the current make target through all of the
# subdirectories in $SUBDIRS.
#
$(SUBDIRS): FRC
	@cd $@; pwd; $(MAKE) $(TARGET)

# Use the bits we just built to create the packages.
packages: install
	@cd pkg; pwd; $(MAKE) $(TARGET) check svr4_test \
		PATH=$$(hg root)/proto/root_$$(uname -p)/usr/bin:$$PATH \
		PYTHONPATH=$$(hg root)/proto/root_$$(uname -p)/usr/lib/python2.6/vendor-packages

test:
	$(PYTHON) setup.py test

test-verbose:
	$(PYTHON) setup.py test -v

test-generate:
	$(PYTHON) setup.py test -g

test-leaks:
	@cd tests; pwd; /bin/ksh memleaks.ksh

FRC:
