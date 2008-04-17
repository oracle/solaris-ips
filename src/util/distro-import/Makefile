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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

# Needs to point to filesystem on Solaris install dvd
# replace as needed with a local solaris install image


WOS_PKGS=/net/netinstall.sfbay/export/nv/x/$(BUILDID)/Solaris_11/Product
NONWOS_PKGS=/net/paradise.sfbay/export/integrate_dock/nv/nv_indiana1/all \
            /net/paradise.sfbay/export/integrate_dock/nv/nv_indiana1/i386

TEST_PKGS=
REPO=http://localhost:10000
JUST_THESE_PKGS=

ALL_PKGS=$(TEST_PKGS) \
	 $(NONWOS_PKGS) \
	 $(WOS_PKGS)

TMPPKGS=SUNWfixes
EXTRA_OPTIONS=
SOLARIS.PY=./solaris.py -b $(BUILDID) $(EXTRA_OPTIONS)

#
# always remove the following (editable) files from packages we bulk import;
# we're doing this until the necessary actions are available.  For now,
# cache as-installed versions.
#
ELIDED_FILES= \
	boot/solaris/devicedb/master	\
	etc/devlink.tab			\
	etc/hba.conf			\
	etc/ima.conf			\
	etc/inet/services		\
	etc/mpapi.conf			\
	etc/security/auth_attr		\
	etc/security/exec_attr		\
	etc/security/prof_attr		\
	etc/user_attr

#
# these files get placed into proto area from per-build cached versions
#
CACHED_FILES=					\
	$(ELIDED_FILES)				\
	boot/grub/menu.lst			\
	boot/grub/splash.xpm.gz			\
	etc/inet/hosts				\
	etc/zones/SUNWblank.xml			\
	etc/zones/SUNWdefault.xml		\
	lib/svc/method/fs-usr			\
	lib/svc/method/sshd			\
	lib/svc/method/svc-dlmgmtd		\
	var/svc/profile/generic_limited_net.xml \
	var/svc/profile/generic_open.xml

FIXFILES=					\
	boot/solaris/filelist.ramdisk		\
	etc/X11/gdm/custom.conf			\
	etc/driver_aliases			\
	etc/name_to_major			\
	etc/nsswitch.conf			\
	etc/pam.conf				\
	etc/passwd				\
	etc/power.conf				\
	etc/release				\
	etc/shadow				\
	etc/svc/global_repo.db			\
	etc/svc/nonglobal_repo.db		\
	etc/user_attr.cdonly			\
	lib/libc.so.1				\
	usr/bin/ksh				\
	usr/has/bin/sh				\
	usr/has/bin/vi				\
	usr/jdk/instances/jdk1.6.0/LICENSE	\
	usr/jdk/instances/jdk1.6.0/README.html	\
	usr/jdk/instances/jdk1.6.0/jre/LICENSE	\
	usr/jdk/instances/jdk1.6.0/jre/README	\
	usr/share/man/man.cf			\
	usr/share/man/missing.man		\
	$(CACHED_FILES)

JDKFILES = LICENSE README.html
JREFILES = LICENSE README

PROG=	ksh-wrapper

OBJS=	ksh-wrapper.o

SRCS=	$(OBJS:%.o=%.c)

CFLAGS=		-g -v

LINTFLAGS=	-axsm

UNBUNDLED_TARGETS=\
ClusterTools.import\
Studio.import\
NetBeans.import

BUILDS= 75a\
	79b\
	86


#
# Starting in build 80, filelist.ramdisk began moving between various
# packages.
#
FILELIST_RAMDISK_PKG_$(BUILDID)	= SUNWckr
FILELIST_RAMDISK_PKG_79b	= SUNWcakr.i
FILELIST_RAMDISK_PKG_75a	= SUNWcakr.i
FILELIST_RAMDISK_PKG_74		= SUNWcakr.i
FILELIST_RAMDISK_PKG_72		= SUNWcakr.i
FILELIST_RAMDISK_PKG_71		= SUNWcakr.i

default:	86/slim_import

cluster.import:	$(WOS_PKGS)/.clustertoc Makefile
	./clustertoc2import.py $(WOS_PKGS)/.clustertoc | \
	sed "s/version 2.2.1a/version 2.2.1.1/" > $@

proto/etc/user_attr.cdonly: proto $(BUILDID)/user_attr
	( cat $(BUILDID)/user_attr; \
	  echo "jack::::profiles=Primary Administrator;roles=root") > $@

proto/etc/driver_aliases:	proto $(BUILDID)/all.i386.$(BUILDID) cluster.import
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsd etc/driver_aliases | \
	./driver_names.py $(BUILDID)/all.i386.$(BUILDID) > $@

proto/etc/name_to_major:	proto $(BUILDID)/all.i386.$(BUILDID) cluster.import
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsd etc/name_to_major | \
	./driver_names.py $(BUILDID)/all.i386.$(BUILDID) > $@

proto/etc/nsswitch.conf:	proto Makefile
	./get_file_from_pkg.py	$(WOS_PKGS)/SUNWcsr etc/nsswitch.files > $@

proto/etc/X11/gdm/custom.conf:	proto Makefile
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWgnome-display-mgr-root	\
	etc/X11/gdm/custom.conf | nawk '/^\[daemon\]/ { print $$0;	\
			    print "AutomaticLoginEnable=true";		\
			    print "AutomaticLogin=jack";		\
			    print "GdmXserverTimeout=30";		\
			    continue }  { print $$0 }' > $@

proto/etc/power.conf:	proto Makefile
	./get_file_from_pkg.py	$(WOS_PKGS)/SUNWpmr etc/power.conf | nawk \
	'/^autoshutdown/{gsub("unconfigured","default");} {print $$0}' > $@

proto/boot/solaris/filelist.ramdisk:	proto
	(./get_file_from_pkg.py $(WOS_PKGS)/$(FILELIST_RAMDISK_PKG_$(BUILDID)) \
	    boot/solaris/filelist.ramdisk; \
	echo etc/zfs/zpool.cache) > $@

proto/etc/pam.conf:	proto
	(./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsr etc/pam.conf;	\
	echo "gdm-autologin auth  required    pam_unix_cred.so.1";	\
	echo "gdm-autologin auth  sufficient  pam_allow.so.1";		\
	echo "gdm-autologin account  sufficient  pam_allow.so.1";	\
	echo "gdm-autologin session  sufficient  pam_allow.so.1";	\
	echo "gdm-autologin password  sufficient  pam_allow.so.1"	\
	) > $@

proto/etc/svc/global_repo.db:	proto
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsr lib/svc/seed/global.db > $@

proto/etc/svc/nonglobal_repo.db:	proto
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsr lib/svc/seed/nonglobal.db > $@

# fix booting on non-sse capable cpus until 6332924 gets fixed
proto/lib/libc.so.1: proto
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcslr lib/libc.so.1 > $@
	/usr/bin/elfedit -e 'cap:hw1 -and -cmp sse' $@

proto/usr/share/man/missing.man:	proto	missing.man
	cp missing.man $@

proto/etc/release:	proto
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWsolnm etc/release | head -1 | \
	sed 's/.*snv_/                  OpenSolaris 2008.05 snv_/' \
	> $@
	cat release.figlet >> $@

proto/usr/share/man/man.cf:	proto
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWman usr/share/man/man.cf | \
	sed \
	'/MANSECTS/s/$$/,1openssl,3openssl,5openssl,7openssl/' \
	> $@

proto/usr/bin/ksh:	proto $(PROG)
	cp $(PROG) $@

#
# change root's default shell, homedir and add jack user
#
proto/etc/passwd:	proto Makefile
	(./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsr etc/passwd | nawk -F:			\
	'/^root/{ print "root:x:0:0:Super-User:/root:/usr/bin/bash";continue} {print $$0}';	\
	echo "jack:x:65432:10:Default User:/jack:/usr/bin/bash") > $@

proto/etc/shadow:	proto Makefile
	(./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsr etc/shadow | nawk -F:		\
	'/^root/{ print "root:wqy8hz4xKqw4o:13817::::::";continue} {print $$0}';	\
	echo "jack:9Nd/cwBcNWFZg:13817::::::") > $@

proto/usr/has/bin/sh:	proto Makefile
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsr sbin/sh > $@

proto/usr/has/bin/vi:	proto Makefile
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsu usr/bin/edit > $@

$(JDKFILES:%=proto/usr/jdk/instances/jdk1.6.0/%):	proto DLJ/$(@F)
	cp DLJ/$(@F) $@

$(JREFILES:%=proto/usr/jdk/instances/jdk1.6.0/jre/%):	proto DLJ/$(@F)
	cp DLJ/$(@F) $@

$(CACHED_FILES:%=proto/%):	proto $(BUILDID)/$(@F) Makefile
	cat $(BUILDID)/$(@F) > $@

proto:	Makefile
	mkdir -p proto/boot/grub
	mkdir -p proto/boot/solaris/devicedb
	mkdir -p proto/etc/X11/gdm
	mkdir -p proto/etc/inet
	mkdir -p proto/etc/security
	mkdir -p proto/etc/svc
	mkdir -p proto/etc/zones
	mkdir -p proto/lib/svc/method
	mkdir -p proto/usr/bin
	mkdir -p proto/usr/jdk/instances/jdk1.6.0/jre
	mkdir -p proto/usr/share/man
	mkdir -p proto/var/svc/profile
	mkdir -p proto/usr/has/bin

%/$(TMPPKGS):
	$(MAKE) BUILDID=$(@D) $(@F)

%:	$(BUILDID)/%.prototype $(BUILDID)/%.pkginfo $(FIXFILES:%=proto/%)
	pkgmk -b ./proto -r . -f $(BUILDID)/$@.prototype -d `pwd` -o

import:	cluster.import $(TMPPKGS)
	rm -f all.i386.$(BUILDID); ln -s $(BUILDID)/all.i386.$(BUILDID)
	$(SOLARIS.PY) -s $(REPO) -w $(WOS_PKGS) $(ELIDED_FILES:%=-D %) all.i386.$(BUILDID)

%/import:
	$(MAKE) BUILDID=$(@:%/import=%) import

slim_import:	$(BUILDID)/slim_cluster $(TMPPKGS)
	rm -f slim_cluster; ln -s $(BUILDID)/slim_cluster slim_cluster
	$(SOLARIS.PY) -s $(REPO) $(ALL_PKGS:%=-w %) $(ELIDED_FILES:%=-D %) $(JUST_THESE_PKGS:%=-j %) slim_cluster 

%/slim_import:
	$(MAKE) BUILDID=$(@:%/slim_import=%) slim_import

redist_import:	$(BUILDID)/redist_cluster $(TMPPKGS)
	rm -f redist_cluster; ln -s $(BUILDID)/redist_cluster redist_cluster
	$(SOLARIS.PY) -s $(REPO) $(ALL_PKGS:%=-w %) $(ELIDED_FILES:%=-D %) $(JUST_THESE_PKGS:%=-j %) redist_cluster 

%/redist_import:
	$(MAKE) BUILDID=$(@:%/redist_import=%) redist_import

%/entire:
	$(MAKE) BUILDID=$(@:%/entire=%) entire

entire: $(BUILDID)/entire.incorporation
	PKG_REPO=$(REPO) ./import_manifest_file entire@0.5.11,5.11-0.$(BUILDID) $(BUILDID)/entire.incorporation

$(UNBUNDLED_TARGETS:%=$(BUILDS)/%):
	$(MAKE) BUILDID=$(@D) $(@F)

$(UNBUNDLED_TARGETS): unbundleds/$$(@:%.import=%)
	rm -f redist_cluster; ln -s $(BUILDID)/redist_cluster redist_cluster
	$(SOLARIS.PY) -s $(REPO) $(ALL_PKGS:%=-w %) $(ELIDED_FILES:%=-D %) `./package_names.py unbundleds/$(@:%.import=%)`  unbundleds/$(@:%.import=%) redist_cluster


%/SUNWipkg:
	$(MAKE) BUILDID=$(@D) $(@F)

SUNWipkg:
	PKG_REPO=$(REPO) ./publish_ips pkg:/SUNWipkg@0.5.11,5.11-0.`echo $(BUILDID) | tr '[a-z]' ' '`

clean:
	rm -f $(OBJS)
	rm -rf proto

clobber: clean
	rm -f $(PROG)

lint:
	$(LINT) $(LINTFLAGS) $(SRCS)

.KEEP_STATE:
