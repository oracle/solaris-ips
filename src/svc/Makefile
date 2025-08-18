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
# Copyright (c) 2024, 2025, Oracle and/or its affiliates.
#

include ../Makefile.constants

SVCCFG =	/usr/sbin/svccfg

ROOTSMFAPP =		$(ROOTLIBSVC)/manifest/application/pkg
ROOTSMFPROFILE =	$(ROOTETCSVC)/profile/system
ROOTSVCMETHOD =		$(ROOTLIBSVC)/method
ROOTSVCSHARE =		$(ROOTLIBSVC)/share

SMF_MANIFESTS = \
	pkg-auto-update.xml \
	pkg-depot.xml \
	pkg-mdns.xml \
	pkg-mirror.xml \
	pkg-oci-config.xml \
	pkg-repositories-setup.xml \
	pkg-server.xml \
	pkg-system-repository.xml \
	pkg-sysrepo-cache.xml \
	zoneproxy-client.xml \
	zoneproxyd.xml

SMF_PROFILE = \
	pkg-auto-update-cleanup-enable.xml

SVC_METHOD_SCRIPTS = \
	svc-pkg-auto-update \
	svc-pkg-auto-update-cleanup \
	svc-pkg-depot \
	svc-pkg-mdns \
	svc-pkg-mirror \
	svc-pkg-oci-config \
	svc-pkg-repositories-setup \
	svc-pkg-server \
	svc-pkg-sysrepo \
	svc-pkg-sysrepo-cache

SVC_SHARE_SCRIPT = \
	pkg5_include.sh

all:

# Validate SMF manifests
lint:
	@for manifest in $(SMF_MANIFESTS); do \
		echo "SMF manifest validate:" $$manifest; \
		$(SVCCFG) validate $$manifest; \
	done

ROOTSMFMANIFESTS = $(SMF_MANIFESTS:%=$(ROOTSMFAPP)/%)
ROOTSMFPROFILES = $(SMF_PROFILE:%=$(ROOTSMFPROFILE)/%)
ROOTSVCMETHODSCRIPTS = $(SVC_METHOD_SCRIPTS:%=$(ROOTSVCMETHOD)/%)
ROOTSVCSHARESCRIPTS = $(SVC_SHARE_SCRIPT:%=$(ROOTSVCSHARE)/%)

install: $(ROOTSMFMANIFESTS) $(ROOTSMFPROFILES) \
	$(ROOTSVCMETHODSCRIPTS) $(ROOTSVCSHARESCRIPTS)

$(ROOTSMFAPP)/%: %
	$(INS.file.strip)

$(ROOTSMFPROFILE)/%: %
	$(INS.file.strip)

$(ROOTSVCMETHOD)/%: %
	$(INS.file.strip)

$(ROOTSVCMETHOD)/%: %.py
	$(INS.file.strip)

$(ROOTSVCSHARE)/%: %
	$(INS.file.strip)

check:

clean:

clobber: clean
