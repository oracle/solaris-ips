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

#
# Needs to point to filesystem on Solaris install dvd
# replace as needed with a local solaris install image
#
WOS_PKGS=/net/netinstall.sfbay/export/nv/x/$(BUILDID)/Solaris_11/Product
NONWOS_PKGS=/net/paradise.sfbay/export/integrate_dock/nv/nv_osol0904/all \
            /net/paradise.sfbay/export/integrate_dock/nv/nv_osol0904/i386

TEST_PKGS=
REPO=http://localhost:10000
JUST_THESE_PKGS=

ALL_PKGS=	../../../packages/i386	\
		$(TEST_PKGS)		\
		$(NONWOS_PKGS)		\
		$(WOS_PKGS)

POUND_SIGN:sh=				echo \\043

#set default
ARCH=i386

i386_DEFINES=		\
	ARCH=i386 	\
	ARCH32=i86	\
	ARCH64=amd64	\
	i386_ONLY=''	\
	sparc_ONLY=$(POUND_SIGN)	

sparc_DEFINES=		\
	ARCH=sparc 	\
	ARCH32=sparcv7	\
	ARCH64=sparcv9	\
	i386_ONLY=$(POUND_SIGN)	\
	sparc_ONLY=''

ARCH_DEFINES=$($(ARCH)_DEFINES)

TMPPKGS=SUNWfixes
EXTRA_OPTIONS=

GLOBAL_CHATTRS_BASE=	\
	reboot		\
	smf_manifests

GLOBAL_CHATTRS_86 = $(GLOBAL_CHATTRS_BASE) 
GLOBAL_CHATTRS_89 = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_90 = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_91 = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_92 = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_93 = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_94 = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_95 = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_96 = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_97 = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_98 = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_99 = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_100a = $(GLOBAL_CHATTRS_BASE)
GLOBAL_CHATTRS_101 = $(GLOBAL_CHATTRS_BASE) fonts gnome
GLOBAL_CHATTRS_101a = $(GLOBAL_CHATTRS_101)
GLOBAL_CHATTRS_105 = $(GLOBAL_CHATTRS_101)
GLOBAL_CHATTRS = $(GLOBAL_CHATTRS_$(BUILDID))

SOLARIS.PY=./solaris.py -b 0.$(BUILDID) $(EXTRA_OPTIONS) -T \*.py \
	$(GLOBAL_CHATTRS:%= -G %) $(ARCH_DEFINES:%= -m %)

#
# always remove the following (editable) files from packages we bulk import;
# we're doing this until the necessary actions are available.  For now,
# cache as-installed versions.
#
ELIDED_FILES_BASE= \
	boot/solaris/devicedb/master	\
	etc/hba.conf			\
	etc/ima.conf			\
	etc/inet/services		\
	etc/mpapi.conf			\
	etc/security/auth_attr		\
	etc/security/exec_attr		\
	etc/security/prof_attr		\
	etc/user_attr

ELIDED_FILES_86 = $(ELIDED_FILES_BASE) etc/devlink.tab
ELIDED_FILES_89 = $(ELIDED_FILES_BASE) kernel/drv/sd.conf etc/devlink.tab
ELIDED_FILES_90 = $(ELIDED_FILES_89)
ELIDED_FILES_91 = $(ELIDED_FILES_89)
ELIDED_FILES_92 = $(ELIDED_FILES_89)
ELIDED_FILES_93 = $(ELIDED_FILES_89)
ELIDED_FILES_94 = $(ELIDED_FILES_89)
ELIDED_FILES_95 = $(ELIDED_FILES_89)
ELIDED_FILES_96 = $(ELIDED_FILES_89)
ELIDED_FILES_97 = $(ELIDED_FILES_89)
ELIDED_FILES_98 = $(ELIDED_FILES_89)
ELIDED_FILES_99 = $(ELIDED_FILES_89)
ELIDED_FILES_100a = $(ELIDED_FILES_BASE) kernel/drv/sd.conf
ELIDED_FILES_101 = $(ELIDED_FILES_100a)
ELIDED_FILES_101a = $(ELIDED_FILES_100a)
ELIDED_FILES_105 = $(ELIDED_FILES_100a)
ELIDED_FILES = $(ELIDED_FILES_$(BUILDID))

#
# these files get placed into proto area from per-build cached versions
#
CACHED_FILES_BASE=							\
	$(ELIDED_FILES)							\
	boot/grub/menu.lst						\
	boot/grub/splash.xpm.gz						\
	etc/inet/hosts							\
	etc/zones/SUNWblank.xml						\
	etc/zones/SUNWdefault.xml					\
	lib/svc/method/fs-usr						\
	lib/svc/method/sshd						\
	lib/svc/method/svc-coreadm					\
	lib/svc/method/svc-dlmgmtd					\
	usr/jdk/instances/jdk1.6.0/jre/lib/fontconfig.properties	\
	usr/lib/vp-services						\
	usr/lib/vp-shares						\
	var/svc/manifest/system/coreadm.xml				\
	var/svc/profile/generic_limited_net.xml				\
	var/svc/profile/generic_open.xml

CACHED_FILES_86 = $(CACHED_FILES_BASE)
CACHED_FILES_89 = $(CACHED_FILES_BASE)
CACHED_FILES_90 = $(CACHED_FILES_BASE)
CACHED_FILES_91 = $(CACHED_FILES_BASE)
CACHED_FILES_92 = $(CACHED_FILES_BASE)
CACHED_FILES_93 = $(CACHED_FILES_BASE)
CACHED_FILES_94 = $(CACHED_FILES_BASE)
CACHED_FILES_95 = $(CACHED_FILES_BASE)
CACHED_FILES_96 = $(CACHED_FILES_BASE)
CACHED_FILES_97 = $(CACHED_FILES_BASE)
CACHED_FILES_98 = $(CACHED_FILES_BASE)
CACHED_FILES_99 = $(CACHED_FILES_BASE)					\
	etc/security/policy.conf					\
	root/.bashrc							\
	root/.profile
CACHED_FILES_100a = $(CACHED_FILES_99)
CACHED_FILES_101 = $(CACHED_FILES_99)					\
	etc/mailcap							\
	etc/mime.types
CACHED_FILES_101a = $(CACHED_FILES_101)					\
	boot/solaris.xpm						\
	etc/skel/.bashrc						\
	etc/skel/.profile						\
	lib/svc/method/svc-ipagent					\
	lib/svc/method/xvm-vnc-config					\
	kernel/drv/nvidia.conf						\
	usr/lib/xen/bin/ipagent						\
	usr/X11/lib/xscreensaver/config/opensolaris-logo.png		\
	var/svc/manifest/application/graphical-login/gdm.xml		\
	var/svc/manifest/system/ipagent.xml				\
	var/svc/manifest/system/xvm/vnc-config.xml
CACHED_FILES_105 = $(CACHED_FILES_101a)
CACHED_FILES = $(CACHED_FILES_$(BUILDID))

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
	lib/svc/method/svc-hostid		\
	usr/bin/ksh				\
	usr/has/bin/sh				\
	usr/has/bin/vi				\
	usr/jdk/instances/jdk1.6.0/LICENSE	\
	usr/jdk/instances/jdk1.6.0/README.html	\
	usr/jdk/instances/jdk1.6.0/jre/LICENSE	\
	usr/jdk/instances/jdk1.6.0/jre/README	\
	usr/sbin/extract_hostid			\
	usr/share/man/man.cf			\
	usr/share/man/missing.man		\
	usr/share/applications/services.desktop	\
	usr/share/applications/shares.desktop	\
	$(CACHED_FILES)

JDKFILES = LICENSE README.html
JREFILES = LICENSE README

PROG=	ksh-wrapper

OBJS=	ksh-wrapper.o

SRCS=	$(OBJS:%.o=%.c)

CFLAGS=		-g -v

LINTFLAGS=	-axsm

UNBUNDLED_TARGETS=		\
	ClusterTools.import	\
	ClusterTools8.import	\
	DTraceGUI.import	\
	Eclipse.import		\
	GlassFishV2.import	\
	MessageQueue41.import	\
	NetBeans.import		\
	OpenOffice.import	\
	Studio.import		\
	Webstackui.import

UNBUNDLED_CLUSTERS=		\
	Clusters.import

BUILDS=	75a			\
	79b			\
	86			\
	89			\
	90			\
	91			\
	92			\
	93			\
	94			\
	95			\
	96			\
	97			\
	98			\
	99			\
	100a			\
	101			\
	101a			\
	105

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

default:	105/slim_import

cluster.import:	$(WOS_PKGS)/.clustertoc Makefile
	./clustertoc2import.py $(WOS_PKGS)/.clustertoc | \
	sed "s/version 2.2.1a/version 2.2.1.1/" > $@

proto/etc/user_attr.cdonly: proto $(BUILDID)/user_attr
	( cat $(BUILDID)/user_attr; \
	  echo "jack::::profiles=Primary Administrator;roles=root") > $@

proto/etc/driver_aliases:	proto $(BUILDID)/redist_cluster cluster.import
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsd etc/driver_aliases | \
	./driver_names.py $(INCLUDE_PATH_$(BUILDID)) \
	$(BUILDID)/redist_cluster > $@

proto/etc/name_to_major:	proto $(BUILDID)/redist_cluster cluster.import
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsd etc/name_to_major | \
	./driver_names.py $(INCLUDE_PATH_$(BUILDID)) \
	$(BUILDID)/redist_cluster > $@

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

proto/lib/svc/method/svc-hostid: proto 100a/svc-hostid
	cp 100a/svc-hostid $@

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

proto/usr/share/applications/shares.desktop: proto
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWgnome-system-tools \
	usr/share/applications/shares.desktop | \
	./desktop_exec.sh /usr/lib/vp-shares > $@

proto/usr/share/applications/services.desktop: proto
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWgnome-system-tools \
	usr/share/applications/services.desktop | \
	./desktop_exec.sh /usr/lib/vp-services > $@

#
# change root's default shell, homedir, password
#
proto/etc/passwd:	proto Makefile
	(./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsr etc/passwd | nawk -F:			\
	'/^root/{ print "root:x:0:0:Super-User:/root:/usr/bin/bash";continue} {print $$0}') > $@

proto/etc/shadow:	proto Makefile
	(./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsr etc/shadow | nawk -F:		\
	'/^root/{ print "root:$$5$$VgppCOxA$$ycFmYW4ObRRHhtsGEygDdexk5bugqgSiaSR9niNCouC:14146::::::";continue} {print $$0}') > $@

proto/usr/has/bin/sh:	proto Makefile
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsr sbin/sh > $@

proto/usr/has/bin/vi:	proto Makefile
	./get_file_from_pkg.py $(WOS_PKGS)/SUNWcsu usr/bin/edit > $@

proto/usr/sbin/extract_hostid:	proto ../misc/extract_hostid
	cp ../misc/extract_hostid $@

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
	mkdir -p proto/etc/skel
	mkdir -p proto/etc/svc
	mkdir -p proto/etc/zones
	mkdir -p proto/kernel/drv
	mkdir -p proto/lib/svc/method
	mkdir -p proto/root
	mkdir -p proto/usr/X11/lib/xscreensaver/config
	mkdir -p proto/usr/bin
	mkdir -p proto/usr/has/bin
	mkdir -p proto/usr/jdk/instances/jdk1.6.0/jre/lib
	mkdir -p proto/usr/lib/xen/bin
	mkdir -p proto/usr/sbin
	mkdir -p proto/usr/share/applications
	mkdir -p proto/usr/share/man
	mkdir -p proto/var/svc/manifest/application/graphical-login
	mkdir -p proto/var/svc/manifest/system/xvm
	mkdir -p proto/var/svc/profile

%/$(TMPPKGS):
	$(MAKE) BUILDID=$(@D) $(@F)

%:	$(BUILDID)/%.prototype $(BUILDID)/%.pkginfo $(FIXFILES:%=proto/%)
	pkgmk -b ./proto -r . -f $(BUILDID)/$@.prototype -d `pwd` -o

INCLUDE_PATH_75a = 75a:73:72:71:00
INCLUDE_PATH_79b = 79b:78:77:76:$(INCLUDE_PATH_75a)
INCLUDE_PATH_84 = 84:83:82:81:80:$(INCLUDE_PATH_79b)
INCLUDE_PATH_85 = 85:$(INCLUDE_PATH_84)
INCLUDE_PATH_86 = 86:$(INCLUDE_PATH_85)
INCLUDE_PATH_89 = 89:88:87:$(INCLUDE_PATH_86)
INCLUDE_PATH_90 = 90:$(INCLUDE_PATH_89)
INCLUDE_PATH_91 = 91:$(INCLUDE_PATH_90)
INCLUDE_PATH_92 = 92:$(INCLUDE_PATH_91)
INCLUDE_PATH_93 = 93:$(INCLUDE_PATH_92)
INCLUDE_PATH_94 = 94:$(INCLUDE_PATH_93)
INCLUDE_PATH_95 = 95:$(INCLUDE_PATH_94)
INCLUDE_PATH_96 = 96:$(INCLUDE_PATH_95)
INCLUDE_PATH_97 = 97:$(INCLUDE_PATH_96)
INCLUDE_PATH_98 = 98:$(INCLUDE_PATH_97)
INCLUDE_PATH_99 = 99:$(INCLUDE_PATH_98)
INCLUDE_PATH_100a = 100a:$(INCLUDE_PATH_99)
INCLUDE_PATH_101 = 101:$(INCLUDE_PATH_100a)
INCLUDE_PATH_101a = 101a:$(INCLUDE_PATH_101)
INCLUDE_PATH_105 = 105:104:103:102:$(INCLUDE_PATH_101a)

import:	cluster.import $(TMPPKGS)
	$(SOLARIS.PY) -s $(REPO) -w $(WOS_PKGS) $(ELIDED_FILES:%=-D %) \
		$(INCLUDE_PATH_$(BUILDID):%=-I %) $(BUILDID)/all.i386

%/import:
	$(MAKE) BUILDID=$(@:%/import=%) import

slim_import:	$(BUILDID)/slim_cluster $(TMPPKGS)
	$(SOLARIS.PY) -s $(REPO) $(ALL_PKGS:%=-w %) $(ELIDED_FILES:%=-D %) \
		$(JUST_THESE_PKGS:%=-j %) $(INCLUDE_PATH_$(BUILDID):%=-I %) \
		$(BUILDID)/slim_cluster 

%/slim_import:
	if test -z "$(JUST_THESE_PKGS)"; then \
		$(MAKE) clobber; \
	fi
	$(MAKE) BUILDID=$(@:%/slim_import=%) slim_import

redist_import:	$(BUILDID)/redist_cluster $(TMPPKGS)
	$(SOLARIS.PY) -s $(REPO) $(ALL_PKGS:%=-w %) $(ELIDED_FILES:%=-D %) \
		$(JUST_THESE_PKGS:%=-j %) $(INCLUDE_PATH_$(BUILDID):%=-I %) \
		$(BUILDID)/redist_cluster 
	$(MAKE) $(BUILDID)/entire

%/redist_import:
	if test -z "$(JUST_THESE_PKGS)"; then \
		$(MAKE) clobber; \
	fi
	$(MAKE) BUILDID=$(@:%/redist_import=%) redist_import

%/entire:
	$(MAKE) BUILDID=$(@:%/entire=%) entire

$(BUILDID)/entire.incorporation: FRC
	./build_entire_incorporation $(BUILDID) > $@

entire: $(BUILDID)/entire.incorporation
	PKG_REPO=$(REPO) ./import_manifest_file \
		entire@0.5.11,5.11-0.`echo $(BUILDID) | tr -d '[a-z]'` \
		$(BUILDID)/entire.incorporation

$(UNBUNDLED_TARGETS:%=$(BUILDS)/%) $(UNBUNDLED_CLUSTERS:%=$(BUILDS)/%):
	$(MAKE) BUILDID=$(@D) $(@F)

$(UNBUNDLED_TARGETS): unbundleds/$$(@:%.import=%)
	rm -f redist_cluster; ln -s $(BUILDID)/redist_cluster redist_cluster
	$(SOLARIS.PY) -s $(REPO) $(ALL_PKGS:%=-w %) $(ELIDED_FILES:%=-D %) \
		`./package_names.py unbundleds/$(@:%.import=%)` \
		$(INCLUDE_PATH_$(BUILDID):%=-I %) unbundleds/$(@:%.import=%) \
		redist_cluster

$(UNBUNDLED_CLUSTERS): unbundleds/$$(@:%.import=%)
	rm -f redist_cluster; ln -s $(BUILDID)/redist_cluster redist_cluster
	$(SOLARIS.PY) -s $(REPO) $(ALL_PKGS:%=-w %) $(ELIDED_FILES:%=-D %) \
		`./package_names.py unbundleds/$(@:%.import=%)` \
		$(INCLUDE_PATH_$(BUILDID):%=-I %) unbundleds/$(@:%.import=%) \
		$(UNBUNDLED_TARGETS:%.import=unbundleds/%) redist_cluster

%/all_unbundleds:
	$(MAKE) BUILDID=$(@D) $(@F)

all_unbundleds:	$(UNBUNDLED_TARGETS:%=$(BUILDID)/%)
	$(MAKE) $(BUILDID)/$(UNBUNDLED_CLUSTERS)


#
# Used to generate the GUI Package Manager classification files from the
# current package classifications.
#
guiclassification:
	./gen_os_files.py

%/SUNWipkg %/backpublish:
	$(MAKE) BUILDID=$(@D) $(@F)

SUNWipkg:
	PKG_REPO=$(REPO) ./publish_ips $(BUILDID) SUNWipkg

backpublish:
	PKG_REPO=$(REPO) ./publish_ips $(BUILDID) SUNWipkg
	PKG_REPO=$(REPO) ./publish_ips $(BUILDID) SUNWipkg-gui
	PKG_REPO=$(REPO) ./publish_ips $(BUILDID) SUNWipkg-gui-l10n
	PKG_REPO=$(REPO) ./publish_ips $(BUILDID) SUNWpython-cherrypy
	PKG_REPO=$(REPO) ./publish_ips $(BUILDID) SUNWpython-pyopenssl

clean:
	rm -f $(OBJS)
	rm -rf proto

clobber: clean
	rm -f $(PROG)
	rm -rf $(TMPPKGS)

lint:
	$(LINT) $(LINTFLAGS) $(SRCS)

.KEEP_STATE:

FRC:
