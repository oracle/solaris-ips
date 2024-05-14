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
# Copyright (c) 2007, 2024, Oracle and/or its affiliates.
#

PYTHON39 = /usr/bin/python3.9
PYTHON311 = /usr/bin/python3.11

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

PYCODESTYLE = /usr/bin/pycodestyle
JOBS = 4

SUBDIRS=zoneproxy util/mkcert man po

PROTO_AREA:sh = echo $(dirname $(pwd))/proto/root_$(uname -p)
PROTO_VENDOR_PACKAGES = $(PROTO_AREA)/usr/lib/python3.9/vendor-packages

PYLINT_TARGETS = \
	pkg.altroot \
	pkg.client.__init__ \
	pkg.client.api \
	pkg.client.linkedimage \
	pkg.client.pkg_solver \
	pkg.client.pkgdefs \
	pkg.client.pkgremote \
	pkg.client.plandesc \
	pkg.client.printengine \
	pkg.client.progress \
	pkg.misc \
	pkg.pipeutils


all: $(SUBDIRS)
	$(PYTHON39) setup.py build
	$(PYTHON311) setup.py build

clean: $(SUBDIRS)
	$(PYTHON39) setup.py clean
	$(PYTHON311) setup.py clean
	@cd pkg; pwd; make clean

clobber: $(SUBDIRS)
	$(PYTHON39) setup.py clobber
	$(PYTHON311) setup.py clobber
	@cd pkg; pwd; make clobber

install: $(SUBDIRS)
	$(PYTHON39) setup.py install
	$(PYTHON311) setup.py install

lint: pylint
	$(PYTHON39) setup.py lint
	$(PYTHON311) setup.py lint
	@cd zoneproxy; pwd; make lint

clint:
	$(PYTHON39) setup.py clint
	@cd zoneproxy; pwd; make lint

#
# Unfortunately, pylint seems pretty fragile and will crash if
# we try to run it over all the current pkg source.  Hence for
# now we only run it over a subset of the source.  As source
# files are made pylint clean they should be added to the
# pylint_targets list.
#
# Insert the tests directory into sys.path with PYTHONPATH
# so any custom checkers can be found.
#
pylint:
	PYTHONPATH=$(PROTO_VENDOR_PACKAGES):tests \
		$(PYTHON39) -m pylint --rcfile tests/pylintrc $(PYLINT_TARGETS)

# A note about bandit baselines: bandit will report new errors but it
# will not fail on a new duplicate issues (bandit bugs: 466 and 558)

bandit:
	$(PYTHON39) -m bandit -r -q -c tests/banditrc . -b tests/bandit-baseline.json

# When generating a baseline, if there are warnings/errors
# bandit will exit with a value of 1.
regen-bandit:
	$(PYTHON39) -m bandit -r -q -c tests/banditrc . -o tests/bandit-baseline.json -f json || true

check: $(SUBDIRS)
	$(PYCODESTYLE) --statistics --count `cat tests/pycodestyle-whitelist.txt`

#
# This rule propagates the current make target through all of the
# subdirectories in $SUBDIRS.
#
$(SUBDIRS): FRC
	@cd $@; pwd; $(MAKE) $(TARGET)

# Use the bits we just built to create the packages.
# Note: pylint should be added back once the gate gets cleaned.
packages: install check bandit
	@cd pkg; pwd; $(MAKE) $(TARGET) check \
		PATH=$(PROTO_AREA)/usr/bin:$$PATH

# Just packages with no checking
justpackages: install
	@cd pkg; pwd; $(MAKE) $(TARGET) repository-metadata \
		PATH=$(PROTO_AREA)/usr/bin:$$PATH

dist:
	hg archive -r default -p pkg7-%h ../pkg7-%h.tar.bz2

test-39:
	$(PYTHON39) tests/run.py -j ${JOBS} -v

test-311:
	$(PYTHON311) tests/run.py -j ${JOBS} -v

test:
	$(MAKE) -k test-39 JOBS=${JOBS}
	$(MAKE) -k test-311 JOBS=${JOBS}

test-verbose:
	$(PYTHON39) setup.py test -v
	$(PYTHON311) setup.py test -v

test-generate:
	$(PYTHON39) setup.py test -g
	$(PYTHON311) setup.py test -g

FRC:
