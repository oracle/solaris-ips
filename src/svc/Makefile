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
# Copyright (c) 2024, Oracle and/or its affiliates.
#

INSTALL:sh =	echo /opt/onbld/bin/$(uname -p)/stash file -v
MKDIR = 	mkdir -p
SVCCFG =	/usr/sbin/svccfg

PROTO_AREA:sh =	echo $(dirname $(dirname $(pwd)))/proto/root_$(uname -p)
SMF_APP_DIR =	$(PROTO_AREA)/lib/svc/manifest/application/pkg
SMF_PROFILE_DIR =	$(PROTO_AREA)/etc/svc/profile/system

SMF_MANIFESTS = \
	pkg-auto-update.xml \
	pkg-depot.xml \
	pkg-mdns.xml \
	pkg-mirror.xml \
	pkg-repositories-setup.xml \
	pkg-server.xml \
	pkg-system-repository.xml \
	pkg-sysrepo-cache.xml \
	zoneproxy-client.xml \
	zoneproxyd.xml

SMF_PROFILE = \
	pkg-auto-update-cleanup-enable.xml


all:

# Validate SMF manifests
lint:
	@for manifest in $(SMF_MANIFESTS); do \
		echo "SMF manifest validate:" $$manifest; \
		$(SVCCFG) validate $$manifest; \
	done

install:
	@for manifest in $(SMF_MANIFESTS); do \
		$(INSTALL) -C $$manifest $(SMF_APP_DIR)/$$manifest; \
	done; \
	# install English .pot file to put into localizable file package \
	$(INSTALL) -C $(SMF_PROFILE) $(SMF_PROFILE_DIR)/$(SMF_PROFILE);

check:

clean:

clobber: clean
