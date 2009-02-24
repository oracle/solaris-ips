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

KSH=/usr/bin/ksh
PYTHON = /usr/bin/python
INSTALL = /usr/sbin/install -s

ROOT = ../../proto/root_${MACH}/usr
ROOTETC = ../../proto/root_${MACH}/etc
ROOTUSRLIB = $(ROOT)/lib

ROOTAPPICONSHARE = $(ROOT)/share/icons/hicolor/48x48/apps
ROOTDATASHARE = $(ROOTSHARE)/data
ROOTDESKTOPSHARE = $(ROOT)/share/applications
ROOTGCONFSHARE = $(ROOTETC)/gconf/schemas
ROOTHELPSHARE = $(ROOT)/share/gnome/help/package-manager
ROOTSPSHARE = $(ROOT)/share/package-manager/data/startpagebase
ROOTICONSHARE = $(ROOT)/share/icons/package-manager
ROOTPYTHON = $(ROOTUSRLIB)/python2.4
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg/gui
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTSHARE = $(ROOT)/share/package-manager

ROOTDIRS = \
   $(ROOTAPPICONSHARE) \
   $(ROOTDATASHARE) \
   $(ROOTDESKTOPSHARE) \
   $(ROOTGCONFSHARE) \
   $(ROOTHELPSHARE) \
   $(ROOTSPSHARE) \
   $(ROOTICONSHARE) \
   $(ROOTPYTHONPKG) \
   $(ROOTSHARE)

APPICONS = \
   data/packagemanager.png

CATALOG = \
   data/opensolaris.org \
   data/opensolaris.org.sections

DESKTOP = \
   data/packagemanager.desktop \
   data/addmoresoftware.desktop

GCONF = \
   data/packagemanager-preferences.schemas

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

#
# List of locales for which to build help.  From this we build
# the list of help file names.
#
HELP_LOCALES = C de es fr it ja ko pt_BR ru sv zh_CN zh_HK zh_TW

SP_LOCALES = C

#
# package-manager.xml is constructed from package-manager.xml.in and
# from help/<locale>/<locale.mo> (which is in turn built from
# help/<locale>/<locale.po>).  This list names all help files created
# in the build process.
#
BUILDHELPFILES = \
	$(HELP_LOCALES:%=help/%/package-manager.xml) \
	$(HELP_LOCALES:%=help/%/%.mo) \

STATICHELPFILES = \
	$(HELP_LOCALES:%=help/%/legal.xml) \
	$(HELP_LOCALES:%=help/%/figures/update_all.png) \
	$(HELP_LOCALES:%=help/%/figures/package_manager.png)

STATICSPFILES = \
	$(SP_LOCALES:%=data/startpagebase/%/startpage_star.png) \
	$(SP_LOCALES:%=data/startpagebase/%/opensolaris.png) \
	$(SP_LOCALES:%=data/startpagebase/%/startpage.html) \
	$(SP_LOCALES:%=data/startpagebase/%/startpage_learn.png) \
	$(SP_LOCALES:%=data/startpagebase/%/startpage_use.png) \
	$(SP_LOCALES:%=data/startpagebase/%/startpage_share.png) \
	$(SP_LOCALES:%=data/startpagebase/%/startpage_ignite.png) \
	$(SP_LOCALES:%=data/startpagebase/%/stub_test.html)

ICONS = \
   data/icons/status_checkmark.png \
   data/icons/status_installed.png \
   data/icons/status_newupdate.png \
   data/icons/progress_checkmark.png \
   data/icons/progress_blank.png

PYMODS = \
   modules/__init__.py \
   modules/imageinfo.py \
   modules/cache.py \
   modules/installupdate.py \
   modules/repository.py \
   modules/enumerations.py \
   modules/parseqs.py \
   modules/misc.py \
   modules/beadmin.py

PYCMODS = $(PYMODS:%.py=%.pyc)


#
# Define the paths to all of the stuff we'll install.
#
ROOTAPPICONS = $(APPICONS:data/%=$(ROOTAPPICONSHARE)/%)

ROOTCATALOG = $(CATALOG:data/%=$(ROOTDATASHARE)/%)

ROOTDESKTOP = $(DESKTOP:data/%=$(ROOTDESKTOPSHARE)/%)

ROOTGCONF = $(GCONF:data/%=$(ROOTGCONFSHARE)/%)

ROOTGLADEICONS = $(GLADEICONS:data/%=$(ROOTSHARE)/%)

ROOTHELPDIRS = \
	$(HELP_LOCALES:%=$(ROOTHELPSHARE)/%) \
	$(HELP_LOCALES:%=$(ROOTHELPSHARE)/%/figures) \

ROOTHELPFILES = \
	$(BUILDHELPFILES:help/%=$(ROOTHELPSHARE)/%) \
	$(STATICHELPFILES:help/%=$(ROOTHELPSHARE)/%)

ROOTSPDIRS = \
	$(SP_LOCALES:%=$(ROOTSPSHARE)/%)

ROOTSPFILES = \
	$(STATICSPFILES:data/startpagebase/%=$(ROOTSPSHARE)/%)

ROOTICONS = $(ICONS:data/icons/%=$(ROOTICONSHARE)/%)

ROOTPYGLADE = $(ROOTSHARE)/packagemanager.glade

#
# .py and .pyc files
#
ROOTPYMODS = $(PYMODS:modules/%=$(ROOTPYTHONPKG)/%)
ROOTPYCALLMODS = $(ROOTPYMODS:%.py=%.pyc)

ROOTCOMPONENTS = \
   $(ROOTAPPICONS) \
   $(ROOTCATALOG) \
   $(ROOTDESKTOP) \
   $(ROOTGCONF) \
   $(ROOTGLADEICONS) \
   $(ROOTHELPFILES) \
   $(ROOTSPFILES) \
   $(ROOTICONS) \
   $(ROOTPYGLADE) \
   $(ROOTPYMODS) \
   $(ROOTPYCALLMODS)

#
# Triggered by all:'s dependency.  Drives production of e.g.
# data/packagemanager.desktop from data/packagemanager.desktop.in
#
data/%: data/%.in
	LC_ALL=C intltool-merge -d -u \
	    -c ../po/.intltool-merge-cache ../po $@.in $@

all: $(DESKTOP) $(GCONF) $(PYCMODS) $(BUILDHELPFILES)

install: all $(ROOTCOMPONENTS) $(ROOTDIRS)

clean:
	rm -f $(PYCMODS) $(DESKTOP) $(GCONF) $(APPICONS)
	rm -f $(BUILDHELPFILES)
	rm -f ../po/.intltool-merge-cache

clobber: clean
	rm -f $(ROOTCOMPONENTS)

#
# These rules drive the production of the .mo and package-manager.xml
# files, which are built into help/<locale>/...
#
help/%/%.mo: help/%/%.po
	msgfmt -o $@ $<

help/%/package-manager.xml: help/%/%.mo
	xml2po -t $< -o $@ $@.in

#
# Build .pyc compile python files.
#
modules/%.pyc: modules/%.py
	python -m compileall -l $(@D)

# See APPICONS above.
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

$(ROOTDIRS):
	$(INSTALL) -d -m 0755 $@

$(ROOTAPPICONSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTAPPICONSHARE) -m 0644 $<

$(ROOTSPDIRS): $(ROOTDIRS)
	$(INSTALL) -d -m 0755 $@

$(ROOTSPSHARE)/%: $(ROOTSPDIRS) data/startpagebase/%
	$(INSTALL) -f $(@D) -m 0644 $<

$(ROOTDATASHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTDATASHARE) -m 0644 $<

$(ROOTDESKTOPSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTDESKTOPSHARE) -m 0644 $<

$(ROOTGCONFSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTGCONFSHARE) -m 0644 $<

#
# These two are broad rules, but at present everything in help is just
# copied from the help directory in a straightforward way.
#
$(ROOTHELPDIRS): $(ROOTDIRS)
	$(INSTALL) -d -m 0755 $@

$(ROOTHELPSHARE)/%: $(ROOTHELPDIRS) help/%
	$(INSTALL) -f $(@D) -m 0644 $<

$(ROOTICONSHARE)/%: $(ROOTDIRS) data/icons/%
	$(INSTALL) -f $(ROOTICONSHARE) -m 0644 $<

$(ROOTPYTHONPKG)/%: $(ROOTDIRS) modules/%
	$(INSTALL) -f $(ROOTPYTHONPKG) -m 0644 $<

$(ROOTSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTSHARE) -m 0644 $<
