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
PYTHON = /usr/bin/python2.6
INSTALL = /usr/sbin/install -s

ROOT = ../../proto/root_${MACH}/usr
ROOTETC = ../../proto/root_${MACH}/etc
ROOTSHARE = $(ROOT)/share/package-manager
ROOTUSRLIB = $(ROOT)/lib

ROOTAPPICONSHARE = $(ROOT)/share/icons/hicolor/48x48/apps
ROOTAPPHIGHICONSHARE = $(ROOT)/share/icons/HighContrast/48x48/apps
ROOTDATASHARE = $(ROOTSHARE)/data
ROOTDESKTOPSHARE = $(ROOT)/share/applications
ROOTGCONFSHARE = $(ROOTETC)/gconf/schemas
ROOTHELPSHARE = $(ROOT)/share/gnome/help/package-manager
ROOTHIGHICON16SHARE = $(ROOTSHARE)/icons/HighContrast/16x16/actions
ROOTHIGHICON24SHARE = $(ROOTSHARE)/icons/HighContrast/24x24/actions
ROOTHIGHICON48SHARE = $(ROOTSHARE)/icons/HighContrast/48x48/actions
ROOTICON16SHARE = $(ROOTSHARE)/icons/hicolor/16x16/actions
ROOTICON24SHARE = $(ROOTSHARE)/icons/hicolor/24x24/actions
ROOTICON48SHARE = $(ROOTSHARE)/icons/hicolor/48x48/actions
ROOTMIMEICONSHARE = $(ROOT)/share/icons/hicolor/48x48/mimetypes
ROOTMIMETYPESHARE = $(ROOT)/share/mime/packages
ROOTPYTHON = $(ROOTUSRLIB)/python2.6
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg/gui
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTSPSHARE = $(ROOTSHARE)/data/startpagebase

ROOTDIRS = \
   $(ROOTAPPICONSHARE) \
   $(ROOTAPPHIGHICONSHARE) \
   $(ROOTDATASHARE) \
   $(ROOTDESKTOPSHARE) \
   $(ROOTGCONFSHARE) \
   $(ROOTHELPSHARE) \
   $(ROOTHIGHICON16SHARE) \
   $(ROOTHIGHICON24SHARE) \
   $(ROOTHIGHICON36SHARE) \
   $(ROOTHIGHICON48SHARE) \
   $(ROOTICON16SHARE) \
   $(ROOTICON24SHARE) \
   $(ROOTICON36SHARE) \
   $(ROOTICON48SHARE) \
   $(ROOTMIMEICONSHARE) \
   $(ROOTMIMETYPESHARE) \
   $(ROOTPYTHONPKG) \
   $(ROOTSHARE) \
   $(ROOTSPSHARE)

APPICONS = \
   data/icons/48x48/packagemanager.png

APPHIGHICONS = \
   data/icons/HighContrast/48x48/packagemanager.png

CATALOG = \
   data/opensolaris.org \
   data/opensolaris.org.sections

DESKTOP = \
   data/packagemanager.desktop \
   data/addmoresoftware.desktop

GCONF = \
   data/packagemanager-preferences.schemas

MIMEICONS = \
   data/gnome-mime-application-vnd.pkg5.info.png

MIMETYPE = \
   data/packagemanager-info.xml

#
# List of locales for which to build help.  From this we build
# the list of help file names.
#
C_ONLY_HELP_LOCALES = C
HELP_LOCALES = C ar cs de es fr it ja ko pt_BR ru sv zh_CN zh_HK zh_TW
C_ONLY_SP_LOCALES = C
SP_LOCALES = C de es fr it ja ko pt_BR ru sv zh_CN zh_HK zh_TW


#
# package-manager.xml is constructed from package-manager.xml.in and
# from help/<locale>/<locale.mo> (which is in turn built from
# help/<locale>/<locale.po>).  This list names all help files created
# in the build process.
#
BUILDHELPFILES = \
	$(HELP_LOCALES:%=help/%/package-manager.xml) \

HIGHICONS16 = \
   data/icons/HighContrast/16x16/filter_all.png \
   data/icons/HighContrast/16x16/filter_selected.png \
   data/icons/HighContrast/16x16/progress_checkmark.png \
   data/icons/HighContrast/16x16/selection.png \
   data/icons/HighContrast/16x16/status_checkmark.png \
   data/icons/HighContrast/16x16/status_installed.png \
   data/icons/HighContrast/16x16/status_newupdate.png \
   data/icons/HighContrast/16x16/status_notinstalled.png

HIGHICONS24 = \
   data/icons/HighContrast/24x24/pm-install_update.png \
   data/icons/HighContrast/24x24/pm-refresh.png \
   data/icons/HighContrast/24x24/pm-remove.png \
   data/icons/HighContrast/24x24/pm-update_all.png

HIGHICONS48 = \
   data/icons/HighContrast/48x48/packagemanager.png \
   data/icons/HighContrast/48x48/pm-install_update.png \
   data/icons/HighContrast/48x48/pm-refresh.png \
   data/icons/HighContrast/48x48/pm-remove.png \
   data/icons/HighContrast/48x48/pm-update_all.png

ICONS16 = \
   data/icons/16x16/filter_all.png \
   data/icons/16x16/filter_selected.png \
   data/icons/16x16/progress_blank.png \
   data/icons/16x16/progress_checkmark.png \
   data/icons/16x16/selection.png \
   data/icons/16x16/status_checkmark.png \
   data/icons/16x16/status_installed.png \
   data/icons/16x16/status_newupdate.png \
   data/icons/16x16/status_notinstalled.png

ICONS24 = \
   data/icons/24x24/pm-check.png \
   data/icons/24x24/pm-install_update.png \
   data/icons/24x24/pm-refresh.png \
   data/icons/24x24/pm-remove.png \
   data/icons/24x24/pm-update_all.png

ICONS48 = \
   data/icons/48x48/packagemanager.png \
   data/icons/48x48/pm-install_update.png \
   data/icons/48x48/pm-refresh.png \
   data/icons/48x48/pm-remove.png \
   data/icons/48x48/pm-update_all.png

PYMODS = \
   modules/__init__.py \
   modules/beadmin.py \
   modules/cache.py \
   modules/enumerations.py \
   modules/imageinfo.py \
   modules/installupdate.py \
   modules/misc.py \
   modules/misc_non_gui.py \
   modules/parseqs.py \
   modules/progress.py \
   modules/repository.py \
   modules/uarenamebe.py \
   modules/webinstall.py

PYCMODS = $(PYMODS:%.py=%.pyc)

STATICHELPFILES = \
	$(C_ONLY_HELP_LOCALES:%=help/%/figures/pkgmgr-main.png) \
	$(C_ONLY_HELP_LOCALES:%=help/%/figures/startpage_new.png) \
	$(C_ONLY_HELP_LOCALES:%=help/%/figures/update_all_new.png) \
	$(C_ONLY_HELP_LOCALES:%=help/%/figures/webinstall.png)

STATICSPFILES = \
	$(SP_LOCALES:%=data/startpagebase/%/startpage.html) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/dialog-information.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/dialog-warning.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/opensolaris.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/startpage_ignite.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/startpage_learn.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/startpage_share.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/startpage_star.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/startpage_use.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/stub_test.html)

#
# Define the paths to all of the stuff we'll install.
#
ROOTAPPICONS = $(APPICONS:data/%=$(ROOTAPPICONSHARE)/%)
ROOTAPPHIGHICONS = $(APPHIGHICONS:data/%=$(ROOTAPPHIGHICONSHARE)/%)

ROOTCATALOG = $(CATALOG:data/%=$(ROOTDATASHARE)/%)

ROOTDESKTOP = $(DESKTOP:data/%=$(ROOTDESKTOPSHARE)/%)

ROOTGCONF = $(GCONF:data/%=$(ROOTGCONFSHARE)/%)

ROOTHELPDIRS = \
	$(HELP_LOCALES:%=$(ROOTHELPSHARE)/%) \
	$(C_ONLY_HELP_LOCALES:%=$(ROOTHELPSHARE)/%/figures) \

ROOTHELPFILES = \
	$(BUILDHELPFILES:help/%=$(ROOTHELPSHARE)/%) \
	$(STATICHELPFILES:help/%=$(ROOTHELPSHARE)/%)

ROOTMIMEICONS = $(MIMEICONS:data/%=$(ROOTMIMEICONSHARE)/%)

ROOTMIMETYPE = $(MIMETYPE:data/%=$(ROOTMIMETYPESHARE)/%)

ROOTSPDIRS = \
	$(SP_LOCALES:%=$(ROOTSPSHARE)/%)

ROOTSPFILES = \
	$(STATICSPFILES:data/startpagebase/%=$(ROOTSPSHARE)/%)

ROOTHIGHICONS16 = $(HIGHICONS16:data/icons/HighContrast/16x16/%=$(ROOTHIGHICON16SHARE)/%)
ROOTHIGHICONS24 = $(HIGHICONS24:data/icons/HighContrast/24x24/%=$(ROOTHIGHICON24SHARE)/%)
ROOTHIGHICONS48 = $(HIGHICONS48:data/icons/HighContrast/48x48/%=$(ROOTHIGHICON48SHARE)/%)

ROOTICONS16 = $(ICONS16:data/icons/16x16/%=$(ROOTICON16SHARE)/%)
ROOTICONS24 = $(ICONS24:data/icons/24x24/%=$(ROOTICON24SHARE)/%)
ROOTICONS48 = $(ICONS48:data/icons/48x48/%=$(ROOTICON48SHARE)/%)

ROOTPYGLADE = $(ROOTSHARE)/packagemanager.glade

#
# .py and .pyc files
#
ROOTPYMODS = $(PYMODS:modules/%=$(ROOTPYTHONPKG)/%)
ROOTPYCALLMODS = $(ROOTPYMODS:%.py=%.pyc)

ROOTCOMPONENTS = \
   $(ROOTAPPICONS) \
   $(ROOTAPPHIGHICONS) \
   $(ROOTCATALOG) \
   $(ROOTDESKTOP) \
   $(ROOTGCONF) \
   $(ROOTHELPFILES) \
   $(ROOTHIGHICONS16) \
   $(ROOTHIGHICONS24) \
   $(ROOTHIGHICONS36) \
   $(ROOTHIGHICONS48) \
   $(ROOTICONS16) \
   $(ROOTICONS24) \
   $(ROOTICONS36) \
   $(ROOTICONS48) \
   $(ROOTMIMEICONS) \
   $(ROOTMIMETYPE) \
   $(ROOTPYGLADE) \
   $(ROOTPYMODS) \
   $(ROOTPYCALLMODS) \
   $(ROOTSPFILES)

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
	rm -f $(PYCMODS) $(DESKTOP) $(GCONF)
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
	ln -sf $(PWD)/data/icons /usr/share/package-manager/icons/hicolor
	ln -sf $(PWD)/data/icons/48x48/packagemanager.png /usr/share/icons/hicolor/48x48/apps/packagemanager.png
	ln -sf $(PWD)/data/icons/HighContrast/48x48/packagemanager.png /usr/share/icons/HighContrast/48x48/apps/packagemanager.png
	ln -sf $(PWD)/modules /usr/lib/python2.6/vendor-packages/pkg/gui

link-clean:
	rm -rf /usr/share/lib/package-manager
	rm -rf /usr/lib/python2.6/vendor-packages/pkg/gui
	rm -f /usr/share/applications/packagemanager.desktop
	rm -f /usr/share/applications/addmoresoftware.desktop
	rm -f /usr/bin/packagemanager
	rm -f /usr/share/icons/hicolor/48x48/apps/packagemanager.png
	rm -f /usr/share/icons/HighContrast/48x48/apps/packagemanager.png

$(ROOTDIRS):
	$(INSTALL) -d -m 0755 $@

$(ROOTAPPHIGHICONSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTAPPHIGHICONSHARE) -m 0644 $<

$(ROOTAPPICONSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTAPPICONSHARE) -m 0644 $<

# Ordering of Rules important to have these executed first before more general rules
# Breaking Alphabetical layout
$(ROOTMIMETYPESHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTMIMETYPESHARE) -m 0644 $<

# Ordering of Rules important to have these executed first before more general rules
# Breaking Alphabetical layout
$(ROOTMIMEICONSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTMIMEICONSHARE) -m 0644 $<

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

$(ROOTHIGHICON16SHARE)/%: $(ROOTDIRS) data/icons/HighContrast/16x16/%
	$(INSTALL) -f $(ROOTHIGHICON16SHARE) -m 0644 $<

$(ROOTHIGHICON24SHARE)/%: $(ROOTDIRS) data/icons/HighContrast/24x24/%
	$(INSTALL) -f $(ROOTHIGHICON24SHARE) -m 0644 $<

$(ROOTHIGHICON48SHARE)/%: $(ROOTDIRS) data/icons/HighContrast/48x48/%
	$(INSTALL) -f $(ROOTHIGHICON48SHARE) -m 0644 $<

$(ROOTICON16SHARE)/%: $(ROOTDIRS) data/icons/16x16/%
	$(INSTALL) -f $(ROOTICON16SHARE) -m 0644 $<

$(ROOTICON24SHARE)/%: $(ROOTDIRS) data/icons/24x24/%
	$(INSTALL) -f $(ROOTICON24SHARE) -m 0644 $<

$(ROOTICON48SHARE)/%: $(ROOTDIRS) data/icons/48x48/%
	$(INSTALL) -f $(ROOTICON48SHARE) -m 0644 $<

$(ROOTPYTHONPKG)/%: $(ROOTDIRS) modules/%
	$(INSTALL) -f $(ROOTPYTHONPKG) -m 0644 $<

$(ROOTSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTSHARE) -m 0644 $<
