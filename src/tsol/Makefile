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
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.
#

MACH:sh = uname -p

INSTALL = /usr/sbin/install -s

ROOTSECTSOLDOOR = ../../proto/root_${MACH}/etc/security/tsol/doors
ROOTSECTSOL = ../../proto/root_${MACH}/etc/security/tsol
ROOTVARTSOL = ../../proto/root_${MACH}/var/tsol

ROOTDIRS = \
	$(ROOTSECTSOLDOOR) \
	$(ROOTSECTSOL) \
	$(ROOTVARTSOL)

clobber: $(ROOTDIRS)
	rm -f $(ROOTVARTSOL)/doors
	rmdir $(ROOTDIRS)

#
# Make directories and create a symbolic link for tsol
#

$(ROOTDIRS):
	$(INSTALL) -d -m 0755 $@

install: $(ROOTDIRS)
	@if [ ! -h $(ROOTVARTSOL)/doors ]; then \
		cd $(ROOTVARTSOL); \
		ln -s ../../etc/security/tsol/doors; \
	fi
