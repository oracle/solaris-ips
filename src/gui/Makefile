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
INSTALL = /usr/sbin/install

ROOT = ../../proto/root_${MACH}/usr
ROOTETC = ../../proto/root_${MACH}/etc
ROOTUSRLIB = $(ROOT)/lib
ROOTSHARE = $(ROOT)/share/package-manager
ROOTHELPSHARE = $(ROOT)/share/gnome/help/package-manager
ROOTDESKTOPSHARE = $(ROOT)/share/applications
ROOTDATASHARE = $(ROOTSHARE)/data
ROOTPYTHON = $(ROOTUSRLIB)/python2.4
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg/gui
ROOTICONSHARE = $(ROOT)/share/icons/package-manager
ROOTAPPICONSHARE = $(ROOT)/share/icons/hicolor/48x48/apps
ROOTGCONFSHARE = $(ROOTETC)/gconf/schemas

ROOTDIRS = \
   $(ROOTPYTHONPKG) \
   $(ROOTSHARE) \
   $(ROOTICONSHARE) \
   $(ROOTAPPICONSHARE) \
   $(ROOTDATASHARE) \
   $(ROOTDESKTOPSHARE) \
   $(ROOTGCONFSHARE) \
   $(ROOTHELPSHARE)

PYMODS = \
   modules/__init__.py \
   modules/imageinfo.py \
   modules/installupdate.py \
   modules/repository.py \
   modules/enumerations.py \
   modules/beadmin.py
PYCMODS = $(PYMODS:%.py=%.pyc)

ICONS = \
   data/icons/status_checkmark.png \
   data/icons/status_installed.png \
   data/icons/status_newupdate.png 

HELP_DIR:sh = echo help/*

HELP = \
   package-manager.xml \
   legal.xml 

APPICONS = \
   data/packagemanager.png

GLADEICONS = \
   data/PM_app_48x.png \
   data/PM_package_36x.png \
   data/update_all24x.png \
   data/remove24x.png \
   data/reload24x.png \
   data/install_update24x.png \
   data/legend_installed.png \
   data/legend_newupdate.png \
   data/new_star_24x.png

CATALOG = \
   data/opensolaris.org \
   data/opensolaris.org.sections

DESKTOP = \
   data/packagemanager.desktop \
   data/addmoresoftware.desktop

GCONF = \
   data/packagemanager-preferences.schemas

ROOTPYMODS = $(PYMODS:modules/%=$(ROOTPYTHONPKG)/%)

ROOTICONS = $(ICONS:data/icons/%=$(ROOTICONSHARE)/%)

ROOTDESKTOP = $(DESKTOP:data/%=$(ROOTDESKTOPSHARE)/%)

ROOTGCONF = $(GCONF:%=$(ROOTGCONFSHARE)/%)

ROOTCATALOG = $(CATALOG:data/%=$(ROOTDATASHARE)/%)

ROOTGLADEICONS = $(GLADEICONS:data/%=$(ROOTSHARE)/%)

ROOTAPPICONS = $(APPICONS:data/%=$(ROOTAPPICONSHARE)/%)

ROOTHELP = $(HELP_DIR:help/%=$(ROOTHELPSHARE)/%)

ROOTPYGLADE = $(ROOTSHARE)/packagemanager.glade

ROOTPYCALLMODS = \
	$(ROOTPYMODS:%.py=%.pyc)

ROOTCOMPONENTS = \
   $(ROOTDIRS) \
   $(ROOTPROGS) \
   $(ROOTPYMODS) \
   $(ROOTPYCALLMODS) \
   $(ROOTCATALOG) \
   $(ROOTPYGLADE) \
   $(ROOTGLADEICONS) \
   $(ROOTHELP) \
   $(ROOTICONS) \
   $(ROOTAPPICONS) \
   $(ROOTDESKTOP) \
   $(ROOTGCONF) \

all := TARGET = all
install := TARGET = install
clean := TARGET = clean
clobber := TARGET = clobber
link := TARGET = link
link-clean := TARGET = link-clean

all: data/packagemanager.desktop data/addmoresoftware.desktop

install: all $(ROOTCOMPONENTS)

clean clobber:
	rm -f $(PYCMODS)
	rm -f $(DESKTOP)
	rm -f $(GCONF)
	rm -f ../po/.intltool-merge-cache
   
modules/%.pyc: modules/%.py
	python -m compileall -l $(@D)

data/packagemanager.desktop: data/packagemanager.desktop.in
	cd data; pwd; \
	  LC_ALL=C intltool-merge -d -u -c ../../po/.intltool-merge-cache ../../po packagemanager.desktop.in packagemanager.desktop

data/addmoresoftware.desktop: data/addmoresoftware.desktop.in
	cd data; pwd; \
	  LC_ALL=C intltool-merge -d -u -c ../../po/.intltool-merge-cache ../../po addmoresoftware.desktop.in addmoresoftware.desktop

data/packagemanager-preferences.schemas: data/packagemanager-preferences.schemas.in
	cd data; pwd; \
	  LC_ALL=C intltool-merge -d -u -c ../../po/.intltool-merge-cache ../../po packagemanager-preferences.schemas.in packagemanager-preferences.schemas

data/packagemanager.png: data/PM_app_48x.png
	cp data/PM_app_48x.png data/packagemanager.png

PWD:sh = pwd

#This will not link l10n files
link:
	mkdir -p /usr/share/lib/package-manager/data
	ln -sf $(PWD)/../packagemanager.py /usr/bin/packagemanager
	ln -sf $(PWD)/data/packagemanager.glade /usr/share/package-manager/packagemanager.glade
	ln -sf $(PWD)/data/opensolaris.org /usr/share/package-manager/data/opensolaris.org
	ln -sf $(PWD)/data/opensolaris.org.sections /usr/share/package-manager/data/opensolaris.org.sections
	ln -sf $(PWD)/data/packagemanager.desktop /usr/share/applications/packagemanager.desktop
	ln -sf $(PWD)/data/addmoresoftware.desktop /usr/share/applications/addmoresoftware.desktop
	ln -sf $(PWD)/data/packagemanager.schemas /etc/gconf/schemas/packagemanager-preferences.schemas
	ln -sf $(PWD)/data/icons /usr/share/icons/package-manager
	ln -sf $(PWD)/data/icons/packagemanager.png /usr/share/icons/hicolor/48x48/apps/packagemanager.png
	ln -sf $(PWD)/modules /usr/lib/python2.4/vendor-packages/pkg/gui

link-clean:
	rm -rf /usr/share/lib/package-manager
	rm -rf /usr/lib/python2.4/vendor-packages/pkg/gui
	rm -f /usr/share/applications/packagemanager.desktop
	rm -f /usr/share/applications/addmoresoftware.desktop
	rm -f /usr/bin/packagemanager
	rm -f /usr/share/icons/hicolor/48x48/apps/packagemanager.png

proto: $(ROOT)

$(ROOTDIRS):
	mkdir -m 0755 -p $@

help/%/%.mo: help/%/%.po
	msgfmt -o $@ $<

help/%/package-manager.xml: help/%/%.mo
	xml2po -t $< -o $@ $@.in

$(ROOTHELPSHARE)/%: help/%/package-manager.xml
	rm -rf $@
	$(INSTALL) -d -m 0755 $@
	$(INSTALL) -f $@ -m 0644 $<
	$(INSTALL) -f $@ -m 0644 $(<D)/legal.xml
	$(INSTALL) -d -m 0755 $@/figures
	$(INSTALL) -f $@/figures -m 0644 $(<D)/figures/package_manager.png
	$(INSTALL) -f $@/figures -m 0644 $(<D)/figures/update_all.png

$(ROOTDATASHARE)/%: data/%
	rm -f $@; $(INSTALL) -f $(ROOTDATASHARE) -m 0644 $<

$(ROOTPYTHONPKG)/%: modules/%
	rm -f $@; $(INSTALL) -f $(ROOTPYTHONPKG) -m 0644 $<

$(ROOTICONSHARE)/%: data/icons/%
	rm -f $@; $(INSTALL) -f $(ROOTICONSHARE) -m 0644 $<

$(ROOTAPPICONSHARE)/%: data/%
	rm -f $@; $(INSTALL) -f $(ROOTAPPICONSHARE) -m 0644 $<

$(ROOTGCONFSHARE)/%: %
	rm -f $@; install -f $(ROOTGCONFSHARE) -m 0644 $<

$(ROOTDESKTOPSHARE)/%: data/%
	rm -f $@; $(INSTALL) -f $(ROOTDESKTOPSHARE) -m 0644 $<

$(ROOTSHARE)/%: data/%
	rm -f $@; $(INSTALL) -f $(ROOTSHARE) -m 0644 $<

