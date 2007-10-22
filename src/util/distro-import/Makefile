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

WOS_PKGS=/net/netinstall.sfbay/export/nv/x/$(BUILDID)/Solaris_11/Product
SLIM_PATH=/net/indiana-build.central/export/slim_stage
GNOME_PKGS=$(SLIM_PATH)/GNOME/latest
INSTALL_PKGS=$(SLIM_PATH)/INSTALL/latest
SLIM_PKGS=$(SLIM_PATH)/SLIM_PKGS/latest
FOX_PKGS=$(SLIM_PATH)/FOX/latest
REPO=http://localhost:10000
JUST_THESE_PKGS=

ALL_PKGS=$(GNOME_PKGS) \
         $(INSTALL_PKGS) \
         $(SLIM_PKGS) \
         $(FOX_PKGS) \
	 $(WOS_PKGS)

TMPPKGS=SUNWfixes

#
# always remove the following (editable) files from packages we bulk import; 
# we're doing this until the necessary actions are available.  
#
ELIDED_FILES= \
	boot/solaris/devicedb/master 	\
	etc/security/auth_attr 		\
	etc/security/prof_attr 		\
	etc/security/exec_attr		\
	etc/devlink.tab

FIXFILES= \
	etc/name_to_major \
	etc/driver_aliases \
	boot/solaris/filelist.ramdisk \
	etc/svc/global_repo.db \
	etc/svc/nonglobal_repo.db \
	$(ELIDED_FILES)


default: 74/$(TMPPKGS)


cluster.import:	$(WOS_PKGS)/.clustertoc Makefile
	./clustertoc2import.py $(WOS_PKGS)/.clustertoc  > $@

proto/etc/driver_aliases: proto $(BUILDID)/all.i386.$(BUILDID) cluster.import
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsd etc/driver_aliases | \
	./driver_names.py $(BUILDID)/all.i386.$(BUILDID) > $@

proto/etc/name_to_major:	proto $(BUILDID)/all.i386.$(BUILDID) cluster.import
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsd etc/name_to_major | \
	./driver_names.py $(BUILDID)/all.i386.$(BUILDID) > $@

proto/boot/solaris/filelist.ramdisk:	proto
	(./get_file_from_pkg.py $(WOS_PKGS)/SUNWcakr.i boot/solaris/filelist.ramdisk; \
	echo etc/zfs/zpool.cache) > $@

proto/etc/svc/global_repo.db:	proto
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsr lib/svc/seed/global.db > $@

proto/etc/svc/nonglobal_repo.db:	proto
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsr lib/svc/seed/nonglobal.db > $@

$(ELIDED_FILES:%=proto/%):	proto $(BUILDID)/$(@F)
	cat $(BUILDID)/$(@F) > $@

proto:	Makefile
	mkdir -p proto/etc/svc
	mkdir -p proto/boot/solaris/devicedb
	mkdir -p proto/etc/security


%/$(TMPPKGS): 
	$(MAKE) BUILDID=$(@D) $(@F)

%:	$(BUILDID)/%.prototype $(BUILDID)/%.pkginfo $(FIXFILES:%=proto/%)
	pkgmk -b ./proto -r . -f $(BUILDID)/$@.prototype -d `pwd` -o


import:	cluster.import $(TMPPKGS)
	rm -f all.i386.$(BUILDID); ln -s $(BUILDID)/all.i386.$(BUILDID)
	./solaris.py -s $(REPO) -w $(WOS_PKGS) $(ELIDED_FILES:%=-D %) all.i386.$(BUILDID)

%/import:	
	$(MAKE) BUILDID=$(@:%/import=%) import


%/slim_import:	
	$(MAKE) BUILDID=$(@:%/slim_import=%) slim_import


slim_import:	$(BUILDID)/slim_cluster  $(TMPPKGS)
	rm -f slim_cluster; ln -s $(BUILDID)/slim_cluster slim_cluster
	./solaris.py -s $(REPO) $(ALL_PKGS:%=-w %) $(ELIDED_FILES:%=-D %) slim_cluster $(JUST_THESE_PKGS)

.KEEP_STATE:


