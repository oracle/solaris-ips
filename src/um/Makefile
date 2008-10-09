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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

MACH:sh = uname -p

KSH=/usr/bin/ksh
PYTHON = /usr/bin/python

ROOT = ../../proto/root_${MACH}/usr
ROOTETC = ../../proto/root_${MACH}/etc
ROOTLIB = ../../proto/root_${MACH}/lib
ROOTUSRLIB = $(ROOT)/lib
ROOTSCRIPTSSHARE = $(ROOT)/lib/update-manager
ROOTSHARE = $(ROOT)/share/update-manager
ROOTAUTOSTARTSHARE = $(ROOTETC)/xdg/autostart
ROOTDESKTOPSHARE = $(ROOT)/share/applications
ROOTDATASHARE = $(ROOTSHARE)/data
ROOTPYTHON = $(ROOTUSRLIB)/python2.4
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg/um
ROOTICONSHARE = $(ROOT)/share/icons/update-manager
ROOTGCONFSHARE = $(ROOTETC)/gconf/schemas
ROOTSVCSHARE = $(ROOTLIB)/svc/method

ROOTDIRS = \
   $(ROOTPYTHONPKG) \
   $(ROOTSHARE) \
   $(ROOTSCRIPTSSHARE) \
   $(ROOTICONSHARE) \
   $(ROOTDATASHARE) \
   $(ROOTAUTOSTARTSHARE) \
   $(ROOTDESKTOPSHARE) \
   $(ROOTSVCSHARE) \
   $(ROOTGCONFSHARE)

ICONS = \
   data/icons/notify_update.png \
   data/icons/status_checkmark.png \
   data/icons/status_blank.png

GLADEICONS = \
   data/PM_app_48x.png \
   data/PM_package_36x.png

AUTOSTART = \
   data/updatemanagernotifier.desktop

DESKTOP = \
   data/updatemanager.desktop

SCRIPTS = \
   update-refresh.sh

GCONF = \
   data/updatemanager-preferences.schemas

SVC = \
   pkg-update

ROOTICONS = $(ICONS:data/%=$(ROOTICONSHARE)/%)

ROOTGLADEICONS = $(GLADEICONS:data/%=$(ROOTSHARE)/%)

ROOTAUTOSTART = $(AUTOSTART:%=$(ROOTAUTOSTARTSHARE)/%)

ROOTDESKTOP = $(DESKTOP:data/%=$(ROOTDESKTOPSHARE)/%)

ROOTGCONF = $(GCONF:%=$(ROOTGCONFSHARE)/%)

ROOTSCRIPTS = $(SCRIPTS:%=$(ROOTSCRIPTSSHARE)/%)

ROOTSVC = $(SVC:%=$(ROOTSVCSHARE)/%)

ROOTPYGLADE = $(ROOTSHARE)/updatemanager.glade

ROOTCOMPONENTS = \
   $(ROOTDIRS) \
   $(ROOTPROGS) \
   $(ROOTICONS) \
   $(ROOTAUTOSTART) \
   $(ROOTDESKTOP) \
   $(ROOTGCONF) \
   $(ROOTSCRIPTS) \
   $(ROOTSVC) \
   $(ROOTGLADEICONS) \
   $(ROOTPYGLADE) \

all := TARGET = all
install := TARGET = install
clean := TARGET = clean
link := TARGET = link
link-clean := TARGET = link-clean

all:
	cd data; pwd;\
	  LC_ALL=C intltool-merge -d -u -c ../po/.intltool-merge-cache ../po updatemanager.desktop.in updatemanager.desktop;\
	  LC_ALL=C intltool-merge -d -u -c ../po/.intltool-merge-cache ../po updatemanagernotifier.desktop.in updatemanagernotifier.desktop;\
	  LC_ALL=C intltool-merge -d -u -c ../po/.intltool-merge-cache ../po updatemanager-preferences.schemas.in updatemanager-preferences.schemas

install: all $(ROOTCOMPONENTS)
	#@cd po; pwd;\
	#  mkdir -p ../$(ROOT); \
	#  for PO in *.po; do \
	#    LING=`basename $$PO .po`; \
	#    MO=$$LING.mo; \
	#    msgfmt -o $$MO $$PO; \
	#    mkdir -p ../$(ROOT)/share/locale/$$LING/LC_MESSAGES; \
	#    cp $$MO ../$(ROOT)/share/locale/$$LING/LC_MESSAGES/updatemanager.mo; \
	#  done;

clean:
	rm -f $(AUTOSTART);\
	rm -f $(DESKTOP);\
	rm -f $(GCONF)
   
PWD:sh = pwd

#This will not link l10n files
link:
	ln -sf $(PWD)/../updatemanagernotifier.py /usr/lib/updatemanagernotifier
	ln -sf $(PWD)/data/updatemanager.glade /usr/share/update-manager/updatemanager.glade
	ln -sf $(PWD)/update-refresh.sh /usr/lib/update-manager/update-refresh.sh
	ln -sf $(PWD)/pkg-update /lib/svc/method/pkg-update
	ln -sf $(PWD)/data/updatemanagernotifier.desktop /etc/xdg/autostart/updatemanagernotifier.desktop
	ln -sf $(PWD)/data/updatemanager-preferences.schemas /etc/gconf/schemas/updatemanage-preferences.schemas
	ln -sf $(PWD)/data/icons /usr/share/icons/update-manager
	ln -sf $(PWD)/data/updatemanager.desktop /usr/share/applications/updatemanager.desktop

link-clean:
	rm -rf /usr/share/update-manager
	rm -f /etc/xdg/autostart/updatemanagernotifier.desktop
	rm -f /etc/gconf/schemas/updatemanager-preferences.schemas
	rm -f /usr/lib/updatemanagernotifier
	rm -f /usr/lib/-manager/update-refresh.sh
	rm -f /lib/svc/method/pkg-update
	rm -f /usr/share/applications/updatemanager.desktop

proto: $(ROOT)

$(ROOTDIRS):
	mkdir -m 0755 -p $@

$(ROOTDATASHARE)/%: data/%
	rm -f $@; install -f $(ROOTDATASHARE) -m 0644 $<

$(ROOTPYTHONPKG)/%: modules/%
	rm -f $@; install -f $(ROOTPYTHONPKG) -m 0644 $<

$(ROOTICONSHARE)/%: data/%
	rm -f $@; install -f $(ROOTICONSHARE) -m 0644 $<

$(ROOTGCONFSHARE)/%: %
	rm -f $@; install -f $(ROOTGCONFSHARE) -m 0644 $<

$(ROOTAUTOSTARTSHARE)/%: %
	rm -f $@; install -f $(ROOTAUTOSTARTSHARE) -m 0644 $<

$(ROOTDESKTOPSHARE)/%: data/%
	rm -f $@; install -f $(ROOTDESKTOPSHARE) -m 0644 $<

$(ROOTSCRIPTSSHARE)/%: %
	rm -f $@; install -f $(ROOTSCRIPTSSHARE) -m 0644 $<

$(ROOTSVCSHARE)/%: %
	rm -f $@; install -f $(ROOTSVCSHARE) -m 0644 $<

$(ROOTSHARE)/%: data/%
	rm -f $@; install -f $(ROOTSHARE) -m 0644 $<

