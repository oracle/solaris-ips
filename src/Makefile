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
# Copyright (c) 2007, 2025, Oracle and/or its affiliates.
#

include Makefile.constants

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

JOBS = 4

SUBDIRS=zoneproxy util/mkcert man po svc web cffi_src modules

ROOTSH =	$(ROOT)/usr/share
ROOTSHLIBPKG =	$(ROOTSH)/lib/pkg
ROOTSHPKGTRANSFORMS =	$(ROOTSH)/pkg/transforms

ROOTETC =	$(ROOT)/etc
ROOTETCPKG =	$(ROOTETC)/pkg
ROOTETCSECURITY =	$(ROOTETC)/security
ROOTAUTHATTRD =	$(ROOTETCSECURITY)/auth_attr.d
ROOTEXECATTRD =	$(ROOTETCSECURITY)/exec_attr.d
ROOTUSERATTRD =	$(ROOTETC)/user_attr.d

ROOTBIN =	$(ROOT)/usr/bin
ROOTLIB =	$(ROOT)/usr/lib

ROOTSYSREPO =	$(ROOTETCPKG)/sysrepo
ROOTDEPOT =	$(ROOTETCPKG)/depot

ROOTVARLOGPKG =	$(ROOT)/var/log/pkg
ROOTVARLOGPKGDEPOT = $(ROOTVARLOGPKG)/depot
ROOTVARLOGPKGSYSREPO = $(ROOTVARLOGPKG)/sysrepo

SYSREPO_LOGS_DIR = $(ROOT)/var/log/pkg/sysrepo
DEPOT_LOGS_DIR = $(ROOT)/var/log/pkg/depot


RESOURCE_FILES = \
	util/opensolaris.org.sections \
	util/pkglintrc

TRANSFORM_FILES = \
	util/publish/transforms/developer \
	util/publish/transforms/documentation \
	util/publish/transforms/locale \
	util/publish/transforms/smf-manifests

SYSREPO_FILES = \
	util/apache2/sysrepo/sysrepo_httpd.conf.mako \
	util/apache2/sysrepo/sysrepo_publisher_response.mako \
	util/apache2/sysrepo/sysrepo_p5p.py

DEPOT_FILES = \
	util/apache2/depot/depot.conf.mako \
	util/apache2/depot/depot_httpd.conf.mako \
	util/apache2/depot/depot_httpd_ssl_protocol.conf \
	util/apache2/depot/depot_index.py


ROOTFILES = \
	$(ROOTBIN)/pkg \
	$(ROOTBIN)/pkgdepend \
	$(ROOTBIN)/pkgdiff \
	$(ROOTBIN)/pkgfmt \
	$(ROOTBIN)/pkglint \
	$(ROOTBIN)/pkgmerge \
	$(ROOTBIN)/pkgmogrify \
	$(ROOTBIN)/pkgrecv \
	$(ROOTBIN)/pkgrepo \
	$(ROOTBIN)/pkgsend \
	$(ROOTBIN)/pkgsign \
	$(ROOTBIN)/pkgsurf \
	$(ROOTLIB)/pkg.depotd \
	$(ROOTLIB)/pkg.sysrepo \
	$(ROOTLIB)/pkg.depot-config \
	$(ROOTLIB)/cronjob-removal.sh \
	$(ROOTSHLIBPKG)/rad-invoke

ROOTRESOURCE_FILES = \
	$(RESOURCE_FILES:util/%=$(ROOTSHLIBPKG)/%)
ROOTTRANSFORM_FILES = \
	$(TRANSFORM_FILES:util/publish/transforms/%=$(ROOTSHPKGTRANSFORMS)/%)
ROOTSYSREPO_FILES = \
	$(SYSREPO_FILES:util/apache2/sysrepo/%=$(ROOTSYSREPO)/%)
ROOTDEPOT_FILES = \
	$(DEPOT_FILES:util/apache2/depot/%=$(ROOTDEPOT)/%)

ROOTATTRFILES = \
	$(ROOTAUTHATTRD)/package\:pkg \
	$(ROOTEXECATTRD)/package\:pkg \
	$(ROOTUSERATTRD)/package\:pkg

ROOTEMPTYDIRS = \
	$(ROOT)/etc/pkg/depot/conf.d \
	$(ROOT)/usr/share/pkg/ignored_deps \
	$(ROOT)/var/cache/pkg/depot \
	$(ROOT)/var/cache/pkg/mirror \
	$(ROOT)/var/cache/pkg/sysrepo \
	$(ROOT)/var/log/pkg/mirror

ROOTEMPTYFILES = \
	$(ROOTVARLOGPKGDEPOT)/access_log \
	$(ROOTVARLOGPKGDEPOT)/error_log \
	$(ROOTVARLOGPKGSYSREPO)/access_log \
	$(ROOTVARLOGPKGSYSREPO)/error_log

# Each of these needs its own rule specifying the target below
ROOTSYMLINKS = \
	$(ROOTLIB)/update-refresh.sh \
	$(ROOTLIB)/update-manager/update-refresh.sh


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

clean: $(SUBDIRS)
	@cd pkg; pwd; make clean

clobber: $(SUBDIRS)
	rm -rf $(ROOT)
	@cd pkg; pwd; make clobber



install: $(SUBDIRS) \
	$(ROOTFILES) \
	$(ROOTRESOURCE_FILES) \
	$(ROOTTRANSFORM_FILES) \
	$(ROOTSYSREPO_FILES) \
	$(ROOTDEPOT_FILES) \
	$(ROOTATTRFILES) \
	$(ROOTEMPTYFILES) \
	$(ROOTEMPTYDIRS) \
	$(ROOTSYMLINKS)

$(ROOTSHLIBPKG)/%: util/%
	$(INS.file.strip)

$(ROOTSHPKGTRANSFORMS)/%: util/publish/transforms/%
	$(INS.file.strip)

$(ROOT)/etc/security/%: util/misc/%
	$(INS.file)
$(ROOT)/etc/user_attr.d/%: util/misc/user_attr.d/%
	$(INS.file)

$(ROOTBIN)/%: util/publish/%.py
	$(INS.file.pstrip)

# Scripts with different installed names need their own targets
$(ROOTBIN)/pkg: client.py
	$(INS.file.pstrip)
$(ROOTBIN)/pkgdepend: pkgdep.py
	$(INS.file.pstrip)
$(ROOTBIN)/pkgrepo: pkgrepo.py
	$(INS.file.pstrip)
$(ROOTBIN)/pkgsend: publish.py
	$(INS.file.pstrip)
$(ROOTBIN)/pkgrecv: pull.py
	$(INS.file.pstrip)
$(ROOTBIN)/pkgsign: sign.py
	$(INS.file.pstrip)
$(ROOTLIB)/pkg.depotd: depot.py
	$(INS.file.pstrip)
$(ROOTLIB)/pkg.sysrepo: sysrepo.py
	$(INS.file.pstrip)
$(ROOTLIB)/pkg.depot-config: depot-config.py
	$(INS.file.pstrip)
$(ROOTLIB)/cronjob-removal.sh: cronjob-removal.sh
	$(INS.file.pstrip)
$(ROOTSHLIBPKG)/rad-invoke: rad-invoke.py
	$(INS.file.pstrip)

$(ROOTSYSREPO)/%: util/apache2/sysrepo/%
	$(INS.file.strip)
# Target specialized for python file which uses pstrip instead
$(ROOTSYSREPO)/sysrepo_p5p.py: util/apache2/sysrepo/sysrepo_p5p.py
	$(INS.file.pstrip)

$(ROOTDEPOT)/%: util/apache2/depot/%
	$(INS.file.strip)
# Target specialized for python file which uses pstrip instead
$(ROOTDEPOT)/depot_index.py: util/apache2/depot/depot_index.py
	$(INS.file.pstrip)

$(ROOTEMPTYFILES):
	$(INS.emptyfile)

$(ROOTEMPTYDIRS):
	$(INS.dir)

# Symlinks
$(ROOTLIB)/update-refresh.sh:
	$(INS.symlink) cronjob-removal.sh $@

$(ROOTLIB)/update-manager/update-refresh.sh:
	$(INS.symlink) ../cronjob-removal.sh $@


lint: $(SUBDIRS) clint pylint

# Runs lint tools over IPS C extension source code.
clint: cffi_src modules
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
	PYTHONPATH=$(ROOTPYPKG):tests \
		$(PYTHON) -m pylint --rcfile tests/pylintrc $(PYLINT_TARGETS)

# A note about bandit baselines: bandit will report new errors but it
# will not fail on a new duplicate issues (bandit bugs: 466 and 558)

bandit:
	$(PYTHON) -m bandit -r -q -c tests/banditrc . -b tests/bandit-baseline.json

# When generating a baseline, if there are warnings/errors
# bandit will exit with a value of 1.
regen-bandit:
	$(PYTHON) -m bandit -r -q -c tests/banditrc . -o tests/bandit-baseline.json -f json || true

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
		PATH=$(ROOT)/usr/bin:$$PATH

# Just packages with no checking
justpackages: install
	@cd pkg; pwd; $(MAKE) $(TARGET) repository-metadata \
		PATH=$(ROOT)/usr/bin:$$PATH

dist:
	hg archive -r default -p pkg7-%h ../pkg7-%h.tar.bz2

test-311:
	$(PYTHON311) tests/run.py -j ${JOBS} -v

test:
	$(MAKE) -k test-311 JOBS=${JOBS}

test-generate:
	$(PYTHON311) tests/run.py test -g

FRC:
