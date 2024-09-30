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

SUBDIRS=zoneproxy util/mkcert man po svc web cffi_src modules


STASH:sh =	echo /opt/onbld/bin/$(uname -p)/stash
INSTALL =	$(STASH) file -v
MKDIR =		mkdir -p

PROTO_AREA:sh = echo $(dirname $(pwd))/proto/root_$(uname -p)
PROTO_VENDOR_PACKAGES = $(PROTO_AREA)/usr/lib/python3.9/vendor-packages

RESOURCE_DIR =	$(PROTO_AREA)/usr/share/lib/pkg
TRANSFORM_DIR =	$(PROTO_AREA)/usr/share/pkg/transforms

EXECATTRD_DIR =	$(PROTO_AREA)/etc/security/exec_attr.d
AUTHATTRD_DIR =	$(PROTO_AREA)/etc/security/auth_attr.d
USERATTRD_DIR =	$(PROTO_AREA)/etc/user_attr.d

SCRIPTS_DIR = $(PROTO_AREA)/usr/bin
LIB_DIR = $(PROTO_AREA)/usr/lib
RAD_DIR = $(PROTO_AREA)/usr/share/lib/pkg

SYSREPO_DIR = $(PROTO_AREA)/etc/pkg/sysrepo
SYSREPO_LOGS_DIR = $(PROTO_AREA)/var/log/pkg/sysrepo

DEPOT_DIR = $(PROTO_AREA)/etc/pkg/depot
DEPOT_LOGS_DIR = $(PROTO_AREA)/var/log/pkg/depot

EMPTY_DIRS = \
	$(PROTO_AREA)/var/cache/pkg/depot \
	$(PROTO_AREA)/etc/pkg/depot/conf.d \
	$(PROTO_AREA)/usr/share/pkg/ignored_deps \
	$(PROTO_AREA)/var/cache/pkg/mirror \
	$(PROTO_AREA)/var/log/pkg/mirror \
	$(PROTO_AREA)/var/cache/pkg/sysrepo


RESOURCE_FILES = \
	util/opensolaris.org.sections \
	util/pkglintrc

TRANSFORM_FILES = \
	util/publish/transforms/developer \
	util/publish/transforms/documentation \
	util/publish/transforms/locale \
	util/publish/transforms/smf-manifests

EXECATTRD_FILE = util/misc/exec_attr.d/package:pkg
AUTHATTRD_FILE = util/misc/auth_attr.d/package:pkg
USERATTRD_FILE = util/misc/user_attr.d/package:pkg

SYSREPO_FILES = \
	util/apache2/sysrepo/sysrepo_httpd.conf.mako \
	util/apache2/sysrepo/sysrepo_publisher_response.mako
SYSREPO_PYTHON_FILE = \
	util/apache2/sysrepo/sysrepo_p5p.py

SYSREPO_LOG_STUBS = \
	util/apache2/sysrepo/logs/access_log \
	util/apache2/sysrepo/logs/error_log

DEPOT_FILES = \
	util/apache2/depot/depot.conf.mako \
	util/apache2/depot/depot_httpd.conf.mako \
	util/apache2/depot/depot_httpd_ssl_protocol.conf
DEPOT_PYTHON_FILE = \
	util/apache2/depot/depot_index.py

DEPOT_LOG_STUBS = \
	util/apache2/depot/logs/access_log \
	util/apache2/depot/logs/error_log


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
	rm -rf $(PROTO_AREA)
	@cd pkg; pwd; make clobber


install: $(SUBDIRS)
	@# add resource files
	@for file in $(RESOURCE_FILES); do \
		$(INSTALL) -C $$file $(RESOURCE_DIR)/$$(basename $$file); \
	done
	@# add transforms
	@for file in $(TRANSFORM_FILES); do \
		$(INSTALL) -C $$file $(TRANSFORM_DIR)/$$(basename $$file); \
	done
	@$(INSTALL) $(EXECATTRD_FILE) $(EXECATTRD_DIR)/$$(basename $(EXECATTRD_FILE))
	@$(INSTALL) $(AUTHATTRD_FILE) $(AUTHATTRD_DIR)/$$(basename $(AUTHATTRD_FILE))
	@$(INSTALL) $(USERATTRD_FILE) $(USERATTRD_DIR)/$$(basename $(USERATTRD_FILE))

	@# additional files
	@$(INSTALL) -Cp client.py $(SCRIPTS_DIR)/pkg
	@$(INSTALL) -Cp pkgdep.py $(SCRIPTS_DIR)/pkgdepend
	@$(INSTALL) -Cp pkgrepo.py $(SCRIPTS_DIR)/pkgrepo
	@$(INSTALL) -Cp publish.py $(SCRIPTS_DIR)/pkgsend
	@$(INSTALL) -Cp pull.py $(SCRIPTS_DIR)/pkgrecv
	@$(INSTALL) -Cp sign.py $(SCRIPTS_DIR)/pkgsign

	@$(INSTALL) -Cp util/publish/pkgdiff.py $(SCRIPTS_DIR)/pkgdiff
	@$(INSTALL) -Cp util/publish/pkgfmt.py $(SCRIPTS_DIR)/pkgfmt
	@$(INSTALL) -Cp util/publish/pkglint.py $(SCRIPTS_DIR)/pkglint
	@$(INSTALL) -Cp util/publish/pkgmerge.py $(SCRIPTS_DIR)/pkgmerge
	@$(INSTALL) -Cp util/publish/pkgmogrify.py $(SCRIPTS_DIR)/pkgmogrify
	@$(INSTALL) -Cp util/publish/pkgsurf.py $(SCRIPTS_DIR)/pkgsurf

	@$(INSTALL) -Cp depot.py $(LIB_DIR)/pkg.depotd
	@$(INSTALL) -Cp sysrepo.py $(LIB_DIR)/pkg.sysrepo
	@$(INSTALL) -Cp depot-config.py $(LIB_DIR)/pkg.depot-config
	@$(INSTALL) -Cp cronjob-removal.sh $(LIB_DIR)/cronjob-removal.sh

	@$(INSTALL) -Cp rad-invoke.py $(RAD_DIR)/rad-invoke

	@# add sysrepo files and log stubs
	@for file in $(SYSREPO_FILES); do \
		$(INSTALL) -C $$file $(SYSREPO_DIR)/$$(basename $$file); \
	done
	@$(INSTALL) -Cp $(SYSREPO_PYTHON_FILE) $(SYSREPO_DIR)/$$(basename $(SYSREPO_PYTHON_FILE));
	@for file in $(SYSREPO_LOG_STUBS); do \
		$(INSTALL) $$file $(SYSREPO_LOGS_DIR)/$$(basename $$file); \
	done

	@# add depot files and log stubs
	@for file in $(DEPOT_FILES); do \
		$(INSTALL) -C $$file $(DEPOT_DIR)/$$(basename $$file); \
	done
	@$(INSTALL) -Cp $(DEPOT_PYTHON_FILE) $(DEPOT_DIR)/$$(basename $(DEPOT_PYTHON_FILE));
	@for file in $(DEPOT_LOG_STUBS); do \
		$(INSTALL) $$file $(DEPOT_LOGS_DIR)/$$(basename $$file); \
	done

	@# add symlinks
	@$(STASH) symlink -v cronjob-removal.sh $(LIB_DIR)/update-refresh.sh
	@$(STASH) symlink -v ../cronjob-removal.sh $(LIB_DIR)/update-manager/update-refresh.sh

	@# create additional empty directories
	@for dir in $(EMPTY_DIRS); do \
		$(MKDIR) $$dir; \
	done


lint: $(SUBDIRS) clint pylint

# Allow for CLINT variable being set from the environment.
$(LINT)CLINT = lint
CLINT = $(LINT)

CLINT_FLAGS = -m64 -u -axms -erroff=E_NAME_DEF_NOT_USED2
CLINT_INCLUDES = -Imodules -I/usr/include/python3.9

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

test-generate:
	$(PYTHON39) tests/run.py test -g
	$(PYTHON311) tests/run.py test -g

FRC:
