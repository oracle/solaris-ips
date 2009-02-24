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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

MACH:sh = uname -p

KSH = /usr/bin/ksh
PYTHON = /usr/bin/python
INSTALL = /usr/sbin/install -s

ROOT = ../../proto/root_${MACH}/usr
ROOTETC = ../../proto/root_${MACH}/etc
ROOTLIB = ../../proto/root_${MACH}/lib
ROOTUSRLIB = $(ROOT)/lib

ROOTAPPICONSHARE = $(ROOT)/share/icons/hicolor/48x48/apps
ROOTAUTOSTARTSHARE = $(ROOTETC)/xdg/autostart
ROOTDESKTOPSHARE = $(ROOT)/share/applications
ROOTGCONFSHARE = $(ROOTETC)/gconf/schemas
ROOTICONSHARE = $(ROOT)/share/icons/update-manager
ROOTPYTHON = $(ROOTUSRLIB)/python2.4
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg/um
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTSCRIPTSSHARE = $(ROOT)/lib/update-manager
ROOTSHARE = $(ROOT)/share/update-manager
ROOTSVCSHARE = $(ROOTLIB)/svc/method

ROOTDIRS = \
   $(ROOTAPPICONSHARE) \
   $(ROOTAUTOSTARTSHARE) \
   $(ROOTDESKTOPSHARE) \
   $(ROOTGCONFSHARE) \
   $(ROOTICONSHARE) \
   $(ROOTPYTHONPKG) \
   $(ROOTSCRIPTSSHARE) \
   $(ROOTSHARE) \
   $(ROOTSVCSHARE)

APPICONS = \
   data/updatemanager.png

AUTOSTART = \
   data/updatemanagernotifier.desktop

DESKTOP = \
   data/updatemanager.desktop

GCONF = \
   data/updatemanager-preferences.schemas

GLADEICONS = \
   data/PM_app_48x.png \
   data/PM_package_36x.png

ICONS = \
   data/icons/notify_update.png \
   data/icons/status_checkmark.png \
   data/icons/status_blank.png

PYGLADE = \
   data/updatemanager.glade

SCRIPTS = \
   update-refresh.sh

SVC = \
   pkg-update

#
# Define the paths to all of the stuff we'll install.
#
ROOTAPPICONS = $(APPICONS:data/%=$(ROOTAPPICONSHARE)/%)

ROOTAUTOSTART = $(AUTOSTART:data/%=$(ROOTAUTOSTARTSHARE)/%)

ROOTDESKTOP = $(DESKTOP:data/%=$(ROOTDESKTOPSHARE)/%)

ROOTGCONF = $(GCONF:data/%=$(ROOTGCONFSHARE)/%)

ROOTGLADEICONS = $(GLADEICONS:data/%=$(ROOTSHARE)/%)

ROOTICONS = $(ICONS:data/icons/%=$(ROOTICONSHARE)/%)

ROOTPYGLADE = $(PYGLADE:data/%=$(ROOTSHARE)/%)

ROOTSCRIPTS = $(SCRIPTS:%=$(ROOTSCRIPTSSHARE)/%)

ROOTSVC = $(SVC:%=$(ROOTSVCSHARE)/%)

ROOTCOMPONENTS = \
   $(ROOTAPPICONS) \
   $(ROOTAUTOSTART) \
   $(ROOTDESKTOP) \
   $(ROOTGCONF) \
   $(ROOTGLADEICONS) \
   $(ROOTICONS) \
   $(ROOTPYGLADE) \
   $(ROOTSCRIPTS) \
   $(ROOTSVC)

#
# Triggered by all:'s dependency.  Drives production of e.g.
# data/updatemanager.desktop from data/updatemanager.desktop.in
#
data/%: data/%.in
	LC_ALL=C intltool-merge -d -u \
	    -c ../po/.intltool-merge-cache ../po $@.in $@

all: $(AUTOSTART) $(DESKTOP) $(GCONF) $(APPICONS)

install: all $(ROOTCOMPONENTS) $(ROOTDIRS)

	# XXX out for now.
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
	rm -f $(AUTOSTART) $(DESKTOP) $(GCONF) $(APPICONS)

clobber: clean
	rm -f $(ROOTCOMPONENTS)

# See APPICONS above.
data/updatemanager.png: data/PM_app_48x.png
	cp data/PM_app_48x.png data/updatemanager.png

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
	ln -sf $(PWD)/data/icons/updatemanager.png /usr/share/icons/hicolor/48x48/apps/updatemanager.png
	ln -sf $(PWD)/data/updatemanager.desktop /usr/share/applications/updatemanager.desktop

link-clean:
	rm -rf /usr/share/update-manager
	rm -f /etc/xdg/autostart/updatemanagernotifier.desktop
	rm -f /etc/gconf/schemas/updatemanager-preferences.schemas
	rm -f /usr/lib/updatemanagernotifier
	rm -f /usr/lib/-manager/update-refresh.sh
	rm -f /lib/svc/method/pkg-update
	rm -f /usr/share/applications/updatemanager.desktop
	rm -f /usr/share/icons/hicolor/48x48/apps/updatemanager.png

$(ROOTDIRS):
	$(INSTALL) -d -m 0755 $@

$(ROOTAPPICONSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTAPPICONSHARE) -m 0644 $<

$(ROOTAUTOSTARTSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTAUTOSTARTSHARE) -m 0644 $<

$(ROOTDESKTOPSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTDESKTOPSHARE) -m 0644 $<

$(ROOTGCONFSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTGCONFSHARE) -m 0644 $<

$(ROOTICONSHARE)/%: $(ROOTDIRS) data/icons/%
	$(INSTALL) -f $(ROOTICONSHARE) -m 0644 $<

$(ROOTPYTHONPKG)/%: $(ROOTDIRS) modules/%
	$(INSTALL) -f $(ROOTPYTHONPKG) -m 0644 $<

$(ROOTSCRIPTSSHARE)/%: $(ROOTDIRS) %
	$(INSTALL) -f $(ROOTSCRIPTSSHARE) -m 0644 $<

$(ROOTSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTSHARE) -m 0644 $<

$(ROOTSVCSHARE)/%: $(ROOTDIRS) %
	$(INSTALL) -f $(ROOTSVCSHARE) -m 0644 $<
