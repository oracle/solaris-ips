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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
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
ROOTAPPHIGHINVICONSHARE = $(ROOT)/share/icons/HighContrastInverse/48x48/apps
ROOTDATASHARE = $(ROOTSHARE)/data
ROOTDESKTOPSHARE = $(ROOT)/share/applications
ROOTGCONFSHARE = $(ROOTETC)/gconf/schemas
ROOTHELPSHARE = $(ROOT)/share/gnome/help/package-manager
ROOTHIGHICON16SHARE = $(ROOTSHARE)/icons/HighContrast/16x16/actions
ROOTHIGHICON24SHARE = $(ROOTSHARE)/icons/HighContrast/24x24/actions
ROOTHIGHICON48SHARE = $(ROOTSHARE)/icons/HighContrast/48x48/actions
ROOTHIGHINV = $(ROOTSHARE)/icons/HighContrastInverse
ROOTHIGHINVICON16SHARE = $(ROOTSHARE)/icons/HighContrastInverse/16x16/actions
ROOTHIGHINVICON24SHARE = $(ROOTSHARE)/icons/HighContrastInverse/24x24/actions
ROOTHIGHINVICON48SHARE = $(ROOTSHARE)/icons/HighContrastInverse/48x48/actions
ROOTHIGHPRINTINV = $(ROOTSHARE)/icons/HighContrastLargePrintInverse
ROOTICON16SHARE = $(ROOTSHARE)/icons/hicolor/16x16/actions
ROOTICON24SHARE = $(ROOTSHARE)/icons/hicolor/24x24/actions
ROOTICON48SHARE = $(ROOTSHARE)/icons/hicolor/48x48/actions
ROOTMIMEICONSHARE = $(ROOT)/share/icons/hicolor/48x48/mimetypes
ROOTMIMETYPESHARE = $(ROOT)/share/mime/packages
ROOTOMFSHARE = $(ROOT)/share/omf/package-manager
ROOTPYTHON = $(ROOTUSRLIB)/python2.6
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg/gui
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTSPSHARE = $(ROOTSHARE)/data/startpagebase

ROOTDIRS = \
   $(ROOTAPPICONSHARE) \
   $(ROOTAPPHIGHICONSHARE) \
   $(ROOTAPPHIGHINVICONSHARE) \
   $(ROOTDATASHARE) \
   $(ROOTDESKTOPSHARE) \
   $(ROOTGCONFSHARE) \
   $(ROOTHELPSHARE) \
   $(ROOTHIGHICON16SHARE) \
   $(ROOTHIGHICON24SHARE) \
   $(ROOTHIGHICON48SHARE) \
   $(ROOTHIGHINVICON16SHARE) \
   $(ROOTHIGHINVICON24SHARE) \
   $(ROOTHIGHINVICON48SHARE) \
   $(ROOTICON16SHARE) \
   $(ROOTICON24SHARE) \
   $(ROOTICON48SHARE) \
   $(ROOTMIMEICONSHARE) \
   $(ROOTMIMETYPESHARE) \
   $(ROOTPYTHONPKG) \
   $(ROOTOMFSHARE) \
   $(ROOTSHARE) \
   $(ROOTSPSHARE)

APPICONS = \
   data/icons/48x48/packagemanager.png

APPHIGHICONS = \
   data/icons/HighContrast/48x48/packagemanager.png

APPHIGHINVICONS = \
   data/icons/HighContrastInverse/48x48/packagemanager.png

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
HELP_LOCALES = C ar ca cs de es fr hu id it ja ko pl pt_BR ru sv zh_CN zh_HK zh_TW
C_ONLY_SP_LOCALES = C
SP_LOCALES = C ar ca cs de es fr hu id it ja ko nl pt_BR ru sv zh_CN zh_HK zh_TW


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

HIGHINVICONS16 = \
   data/icons/HighContrastInverse/16x16/filter_all.png \
   data/icons/HighContrastInverse/16x16/filter_selected.png \
   data/icons/HighContrastInverse/16x16/progress_checkmark.png \
   data/icons/HighContrastInverse/16x16/selection.png \
   data/icons/HighContrastInverse/16x16/status_checkmark.png \
   data/icons/HighContrastInverse/16x16/status_installed.png \
   data/icons/HighContrastInverse/16x16/status_newupdate.png \
   data/icons/HighContrastInverse/16x16/status_notinstalled.png

HIGHICONS24 = \
   data/icons/HighContrast/24x24/pm-install_update.png \
   data/icons/HighContrast/24x24/pm-refresh.png \
   data/icons/HighContrast/24x24/pm-remove.png \
   data/icons/HighContrast/24x24/pm-update_all.png

HIGHINVICONS24 = \
   data/icons/HighContrastInverse/24x24/pm-install_update.png \
   data/icons/HighContrastInverse/24x24/pm-refresh.png \
   data/icons/HighContrastInverse/24x24/pm-remove.png \
   data/icons/HighContrastInverse/24x24/pm-update_all.png

HIGHICONS48 = \
   data/icons/HighContrast/48x48/packagemanager.png \
   data/icons/HighContrast/48x48/pm-install_update.png \
   data/icons/HighContrast/48x48/pm-refresh.png \
   data/icons/HighContrast/48x48/pm-remove.png \
   data/icons/HighContrast/48x48/pm-update_all.png

HIGHINVICONS48 = \
   data/icons/HighContrastInverse/48x48/packagemanager.png \
   data/icons/HighContrastInverse/48x48/pm-install_update.png \
   data/icons/HighContrastInverse/48x48/pm-refresh.png \
   data/icons/HighContrastInverse/48x48/pm-remove.png \
   data/icons/HighContrastInverse/48x48/pm-update_all.png

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

OMFFILES = \
   help/package-manager-ar.omf \
   help/package-manager-C.omf \
   help/package-manager-ca.omf \
   help/package-manager-cs.omf \
   help/package-manager-de.omf \
   help/package-manager-es.omf \
   help/package-manager-fr.omf \
   help/package-manager-hu.omf \
   help/package-manager-id.omf \
   help/package-manager-it.omf \
   help/package-manager-ja.omf \
   help/package-manager-ko.omf \
   help/package-manager-pl.omf \
   help/package-manager-pt_BR.omf \
   help/package-manager-ru.omf \
   help/package-manager-sv.omf \
   help/package-manager-zh_CN.omf \
   help/package-manager-zh_HK.omf \
   help/package-manager-zh_TW.omf

PYMODS = \
   modules/__init__.py \
   modules/beadmin.py \
   modules/cache.py \
   modules/detailspanel.py \
   modules/entrystyle.py \
   modules/enumerations.py \
   modules/exportconfirm.py \
   modules/globalexceptionhandler.py \
   modules/imageinfo.py \
   modules/installupdate.py \
   modules/misc.py \
   modules/misc_non_gui.py \
   modules/parseqs.py \
   modules/pmgconf.py \
   modules/pmlogging.py \
   modules/preferences.py \
   modules/progress.py \
   modules/repository.py \
   modules/searcherror.py \
   modules/startpage.py \
   modules/uarenamebe.py \
   modules/versioninfo.py \
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
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/hc_dialog-information.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/hc_dialog-warning.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/hc_install.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/hc_opensolaris.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/hci_dialog-information.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/hci_dialog-warning.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/hci_install.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/hci_opensolaris.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/install.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/opensolaris.png) \

#
# Define the paths to all of the stuff we'll install.
#
ROOTAPPICONS = $(APPICONS:data/icons/48x48/%=$(ROOTAPPICONSHARE)/%)
ROOTAPPHIGHICONS = $(APPHIGHICONS:data/icons/HighContrast/48x48/%=$(ROOTAPPHIGHICONSHARE)/%)
ROOTAPPHIGHINVICONS = $(APPHIGHINVICONS:data/icons/HighContrastInverse/48x48/%=$(ROOTAPPHIGHINVICONSHARE)/%)

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

ROOTOMFFILES = $(OMFFILES:help/%=$(ROOTOMFSHARE)/%)

ROOTSPDIRS = \
	$(SP_LOCALES:%=$(ROOTSPSHARE)/%)

ROOTSPFILES = \
	$(STATICSPFILES:data/startpagebase/%=$(ROOTSPSHARE)/%)

ROOTHIGHICONS16 = $(HIGHICONS16:data/icons/HighContrast/16x16/%=$(ROOTHIGHICON16SHARE)/%)
ROOTHIGHICONS24 = $(HIGHICONS24:data/icons/HighContrast/24x24/%=$(ROOTHIGHICON24SHARE)/%)
ROOTHIGHICONS48 = $(HIGHICONS48:data/icons/HighContrast/48x48/%=$(ROOTHIGHICON48SHARE)/%)

ROOTHIGHINVICONS16 = $(HIGHINVICONS16:data/icons/HighContrastInverse/16x16/%=$(ROOTHIGHINVICON16SHARE)/%)
ROOTHIGHINVICONS24 = $(HIGHINVICONS24:data/icons/HighContrastInverse/24x24/%=$(ROOTHIGHINVICON24SHARE)/%)
ROOTHIGHINVICONS48 = $(HIGHINVICONS48:data/icons/HighContrastInverse/48x48/%=$(ROOTHIGHINVICON48SHARE)/%)

ROOTICONS16 = $(ICONS16:data/icons/16x16/%=$(ROOTICON16SHARE)/%)
ROOTICONS24 = $(ICONS24:data/icons/24x24/%=$(ROOTICON24SHARE)/%)
ROOTICONS48 = $(ICONS48:data/icons/48x48/%=$(ROOTICON48SHARE)/%)

ROOTPYGLADE = $(ROOTSHARE)/packagemanager.ui

#
# .py and .pyc files
#
ROOTPYMODS = $(PYMODS:modules/%=$(ROOTPYTHONPKG)/%)
ROOTPYCALLMODS = $(ROOTPYMODS:%.py=%.pyc)

ROOTCOMPONENTS = \
   $(ROOTAPPICONS) \
   $(ROOTAPPHIGHICONS) \
   $(ROOTAPPHIGHINVICONS) \
   $(ROOTDESKTOP) \
   $(ROOTGCONF) \
   $(ROOTHELPFILES) \
   $(ROOTHIGHICONS16) \
   $(ROOTHIGHICONS24) \
   $(ROOTHIGHICONS48) \
   $(ROOTHIGHINVICONS16) \
   $(ROOTHIGHINVICONS24) \
   $(ROOTHIGHINVICONS48) \
   $(ROOTHIGHPRINTINV) \
   $(ROOTICONS16) \
   $(ROOTICONS24) \
   $(ROOTICONS48) \
   $(ROOTMIMEICONS) \
   $(ROOTMIMETYPE) \
   $(ROOTPYGLADE) \
   $(ROOTPYMODS) \
   $(ROOTPYCALLMODS) \
   $(ROOTOMFFILES) \
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

$(ROOTDIRS):
	$(INSTALL) -d -m 0755 $@

$(ROOTAPPHIGHICONSHARE)/%: $(ROOTDIRS) data/icons/HighContrast/48x48/%
	$(INSTALL) -f $(ROOTAPPHIGHICONSHARE) -m 0644 $<

$(ROOTAPPHIGHINVICONSHARE)/%: $(ROOTDIRS) data/icons/HighContrastInverse/48x48/%
	$(INSTALL) -f $(ROOTAPPHIGHINVICONSHARE) -m 0644 $<

$(ROOTAPPICONSHARE)/%: $(ROOTDIRS) data/icons/48x48/%
	$(INSTALL) -f $(ROOTAPPICONSHARE) -m 0644 $<

# Ordering of Rules important to have these executed first before more general rules
# Breaking Alphabetical layout
$(ROOTMIMETYPESHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTMIMETYPESHARE) -m 0644 $<

# Ordering of Rules important to have these executed first before more general rules
# Breaking Alphabetical layout
$(ROOTMIMEICONSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTMIMEICONSHARE) -m 0644 $<

$(ROOTOMFSHARE)/%: $(ROOTDIRS) help/%
	$(INSTALL) -f $(ROOTOMFSHARE) -m 0644 $<

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

$(ROOTHIGHINVICON16SHARE)/%: $(ROOTDIRS) data/icons/HighContrastInverse/16x16/%
	$(INSTALL) -f $(ROOTHIGHINVICON16SHARE) -m 0644 $<

$(ROOTHIGHINVICON24SHARE)/%: $(ROOTDIRS) data/icons/HighContrastInverse/24x24/%
	$(INSTALL) -f $(ROOTHIGHINVICON24SHARE) -m 0644 $<

$(ROOTHIGHINVICON48SHARE)/%: $(ROOTDIRS) data/icons/HighContrastInverse/48x48/%
	$(INSTALL) -f $(ROOTHIGHINVICON48SHARE) -m 0644 $<

$(ROOTICON16SHARE)/%: $(ROOTDIRS) data/icons/16x16/%
	$(INSTALL) -f $(ROOTICON16SHARE) -m 0644 $<

$(ROOTICON24SHARE)/%: $(ROOTDIRS) data/icons/24x24/%
	$(INSTALL) -f $(ROOTICON24SHARE) -m 0644 $<

$(ROOTICON48SHARE)/%: $(ROOTDIRS) data/icons/48x48/%
	$(INSTALL) -f $(ROOTICON48SHARE) -m 0644 $<

$(ROOTHIGHPRINTINV):
	rm -f $(ROOTHIGHPRINTINV)
	ln -s HighContrastInverse $(ROOTHIGHPRINTINV)

$(ROOTPYTHONPKG)/%: $(ROOTDIRS) modules/%
	$(INSTALL) -f $(ROOTPYTHONPKG) -m 0644 $<

$(ROOTSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTSHARE) -m 0644 $<

