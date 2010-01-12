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
ROOTSHARE = $(ROOT)/share/update-manager
ROOTUSRLIB = $(ROOT)/lib

ROOTAPPICONSHARE = $(ROOT)/share/icons/hicolor/48x48/apps
ROOTAPPHIGHICONSHARE = $(ROOT)/share/icons/HighContrast/48x48/apps
ROOTAUTOSTARTSHARE = $(ROOTETC)/xdg/autostart
ROOTDESKTOPSHARE = $(ROOT)/share/applications
ROOTGCONFSHARE = $(ROOTETC)/gconf/schemas
ROOTHIGHICON24SHARE = $(ROOTSHARE)/icons/HighContrast/24x24/actions
ROOTHIGHICON36SHARE = $(ROOTSHARE)/icons/HighContrast/36x36/actions
ROOTHIGHICON48SHARE = $(ROOTSHARE)/icons/HighContrast/48x48/actions
ROOTICON24SHARE = $(ROOTSHARE)/icons/hicolor/24x24/actions
ROOTICON36SHARE = $(ROOTSHARE)/icons/hicolor/36x36/actions
ROOTICON48SHARE = $(ROOTSHARE)/icons/hicolor/48x48/actions
ROOTPYTHON = $(ROOTUSRLIB)/python2.6
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg/um
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTSCRIPTSSHARE = $(ROOT)/lib/update-manager
ROOTSVCSHARE = $(ROOTLIB)/svc/method

ROOTDIRS = \
   $(ROOTAPPICONSHARE) \
   $(ROOTAPPHIGHICONSHARE) \
   $(ROOTAUTOSTARTSHARE) \
   $(ROOTDESKTOPSHARE) \
   $(ROOTGCONFSHARE) \
   $(ROOTHIGHICON24SHARE) \
   $(ROOTHIGHICON36SHARE) \
   $(ROOTHIGHICON48SHARE) \
   $(ROOTICON24SHARE) \
   $(ROOTICON36SHARE) \
   $(ROOTICON48SHARE) \
   $(ROOTPYTHONPKG) \
   $(ROOTSCRIPTSSHARE) \
   $(ROOTSHARE) \
   $(ROOTSVCSHARE)

APPICONS = \
   data/icons/48x48/updatemanager.png

APPHIGHICONS = \
   data/icons/HighContrast/48x48/updatemanager.png

AUTOSTART = \
   data/updatemanagernotifier.desktop

DESKTOP = \
   data/updatemanager.desktop

GCONF = \
   data/updatemanager-preferences.schemas

HIGHICONS24 = \
   data/icons/HighContrast/24x24/updatemanager.png

HIGHICONS36 = \
   data/icons/HighContrast/36x36/updatemanager.png

HIGHICONS48 = \
   data/icons/HighContrast/48x48/updatemanager.png

ICONS24 = \
   data/icons/24x24/updatemanager.png

ICONS36 = \
   data/icons/36x36/updatemanager.png

ICONS48 = \
   data/icons/48x48/updatemanager.png

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
ROOTAPPHIGHICONS = $(APPHIGHICONS:data/%=$(ROOTAPPHIGHICONSHARE)/%)

ROOTAUTOSTART = $(AUTOSTART:data/%=$(ROOTAUTOSTARTSHARE)/%)

ROOTDESKTOP = $(DESKTOP:data/%=$(ROOTDESKTOPSHARE)/%)

ROOTGCONF = $(GCONF:data/%=$(ROOTGCONFSHARE)/%)

ROOTHIGHICONS24 = $(HIGHICONS24:data/icons/HighContrast/24x24/%=$(ROOTHIGHICON24SHARE)/%)
ROOTHIGHICONS36 = $(HIGHICONS36:data/icons/HighContrast/36x36/%=$(ROOTHIGHICON36SHARE)/%)
ROOTHIGHICONS48 = $(HIGHICONS48:data/icons/HighContrast/48x48/%=$(ROOTHIGHICON48SHARE)/%)

ROOTICONS24 = $(ICONS24:data/icons/24x24/%=$(ROOTICON24SHARE)/%)
ROOTICONS36 = $(ICONS36:data/icons/36x36/%=$(ROOTICON36SHARE)/%)
ROOTICONS48 = $(ICONS48:data/icons/48x48/%=$(ROOTICON48SHARE)/%)

ROOTPYGLADE = $(PYGLADE:data/%=$(ROOTSHARE)/%)

ROOTSCRIPTS = $(SCRIPTS:%=$(ROOTSCRIPTSSHARE)/%)

ROOTSVC = $(SVC:%=$(ROOTSVCSHARE)/%)

ROOTCOMPONENTS = \
   $(ROOTAPPICONS) \
   $(ROOTAPPHIGHICONS) \
   $(ROOTAUTOSTART) \
   $(ROOTDESKTOP) \
   $(ROOTGCONF) \
   $(ROOTHIGHICONS24) \
   $(ROOTHIGHICONS36) \
   $(ROOTHIGHICONS48) \
   $(ROOTICONS24) \
   $(ROOTICONS36) \
   $(ROOTICONS48) \
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
	rm -f $(AUTOSTART) $(DESKTOP) $(GCONF)

clobber: clean
	rm -f $(ROOTCOMPONENTS)

PWD:sh = pwd

#This will not link l10n files
link:
	ln -sf $(PWD)/../updatemanagernotifier.py /usr/lib/updatemanagernotifier
	ln -sf $(PWD)/data/updatemanager.glade /usr/share/update-manager/updatemanager.glade
	ln -sf $(PWD)/update-refresh.sh /usr/lib/update-manager/update-refresh.sh
	ln -sf $(PWD)/pkg-update /lib/svc/method/pkg-update
	ln -sf $(PWD)/data/updatemanagernotifier.desktop /etc/xdg/autostart/updatemanagernotifier.desktop
	ln -sf $(PWD)/data/updatemanager-preferences.schemas /etc/gconf/schemas/updatemanage-preferences.schemas
	ln -sf $(PWD)/data/icons /usr/share/update-manager/icons/hicolor
	ln -sf $(PWD)/data/icons/48x48/updatemanager.png /usr/share/icons/hicolor/48x48/apps/updatemanager.png
	ln -sf $(PWD)/data/icons/HighContrast/48x48/updatemanager.png /usr/share/icons/HighContrast/48x48/apps/updatemanager.png
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
	rm -f /usr/share/icons/HighContrast/48x48/apps/updatemanager.png

$(ROOTDIRS):
	$(INSTALL) -d -m 0755 $@

$(ROOTAPPHIGHICONSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTAPPHIGHICONSHARE) -m 0644 $<

$(ROOTAPPICONSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTAPPICONSHARE) -m 0644 $<

$(ROOTAUTOSTARTSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTAUTOSTARTSHARE) -m 0644 $<

$(ROOTDESKTOPSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTDESKTOPSHARE) -m 0644 $<

$(ROOTGCONFSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTGCONFSHARE) -m 0644 $<

$(ROOTHIGHICON24SHARE)/%: $(ROOTDIRS) data/icons/HighContrast/24x24/%
	$(INSTALL) -f $(ROOTHIGHICON24SHARE) -m 0644 $<

$(ROOTHIGHICON36SHARE)/%: $(ROOTDIRS) data/icons/HighContrast/36x36/%
	$(INSTALL) -f $(ROOTHIGHICON36SHARE) -m 0644 $<

$(ROOTHIGHICON48SHARE)/%: $(ROOTDIRS) data/icons/HighContrast/48x48/%
	$(INSTALL) -f $(ROOTHIGHICON48SHARE) -m 0644 $<

$(ROOTICON24SHARE)/%: $(ROOTDIRS) data/icons/24x24/%
	$(INSTALL) -f $(ROOTICON24SHARE) -m 0644 $<

$(ROOTICON36SHARE)/%: $(ROOTDIRS) data/icons/36x36/%
	$(INSTALL) -f $(ROOTICON36SHARE) -m 0644 $<

$(ROOTICON48SHARE)/%: $(ROOTDIRS) data/icons/48x48/%
	$(INSTALL) -f $(ROOTICON48SHARE) -m 0644 $<

$(ROOTPYTHONPKG)/%: $(ROOTDIRS) modules/%
	$(INSTALL) -f $(ROOTPYTHONPKG) -m 0644 $<

$(ROOTSCRIPTSSHARE)/%: $(ROOTDIRS) %
	$(INSTALL) -f $(ROOTSCRIPTSSHARE) -m 0644 $<

$(ROOTSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTSHARE) -m 0644 $<

$(ROOTSVCSHARE)/%: $(ROOTDIRS) %
	$(INSTALL) -f $(ROOTSVCSHARE) -m 0644 $<
