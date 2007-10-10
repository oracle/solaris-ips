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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

# Needs to point to filesystem on Solaris install dvd
# replace as needed with a local solaris install image

WOS_PKGS=/net/netinstall.sfbay/export/nv/x/74/Solaris_11/Product
SLIM_PATH=/net/indiana-build.central/export/slim_stage
GNOME_PKGS=$(SLIM_PATH)/GNOME/latest
INSTALL_PKGS=$(SLIM_PATH)/INSTALL/latest
SLIM_PKGS=$(SLIM_PATH)/SLIM_PKGS/latest
FOX_PKGS=$(SLIM_PATH)/FOX/latest

TMPPKGS=SUNWfixes

FIXFILES= \
	etc/name_to_major \
	etc/driver_aliases \
	boot/solaris/filelist.ramdisk \
	etc/svc/global_repo.db \
	etc/svc/nonglobal_repo.db

default:	$(TMPPKGS) cluster.import

cluster.import:	$(WOS_PATH)/.clustertoc Makefile
	./clustertoc2import.py $(WOS_PATH)/.clustertoc | egrep -v 'SUNWjds-registration|SUNWdttsr|SUNWdttsu' > $@

proto/etc/driver_aliases: proto
	./get_file_from_pkg.py $(WOS_PATH)/SUNWcsd etc/driver_aliases | \
	./driver_names.py `find common i386 -type f` > $@

proto/etc/name_to_major:	proto
	./get_file_from_pkg.py $(WOS_PATH)/SUNWcsd etc/name_to_major | \
	./driver_names.py `find common i386 -type f` > $@

proto/boot/solaris/filelist.ramdisk:	proto
	(./get_file_from_pkg.py $(WOS_PATH)/SUNWcakr.i boot/solaris/filelist.ramdisk; \
	echo etc/zfs/zpool.cache) > $@

proto/etc/svc/global_repo.db:	proto
	./get_file_from_pkg.py $(WOS_PATH)/SUNWcsr lib/svc/seed/global.db > $@

proto/etc/svc/nonglobal_repo.db:	proto
	./get_file_from_pkg.py $(WOS_PATH)/SUNWcsr lib/svc/seed/nonglobal.db > $@

proto:	Makefile
	mkdir -p proto/etc/svc
	mkdir -p proto/boot/solaris

SUNWfixes: $(FIXFILES:%=proto/%)

%:	%.prototype
	pkgmk -b ./proto -r . -f $@.prototype -d `pwd` -o


import:	cluster.import $(TMPPKGS)
	./solaris.py -w $(WOS_PATH) all.i386

slim_import:	slim_cluster $(TMPPKGS)
	./solaris.py -w $(GNOME_PKGS) -w $(INSTALL_PKGS) -w $(FOX_PKGS) -w $(SLIM_PKGS) -w $(WOS_PKGS) slim_cluster

