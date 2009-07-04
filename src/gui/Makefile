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
ROOTSHARE = $(ROOT)/share/package-manager
ROOTUSRLIB = $(ROOT)/lib

ROOTAPPICONSHARE = $(ROOT)/share/icons/hicolor/48x48/apps
ROOTDATASHARE = $(ROOTSHARE)/data
ROOTDESKTOPSHARE = $(ROOT)/share/applications
ROOTGCONFSHARE = $(ROOTETC)/gconf/schemas
ROOTHELPSHARE = $(ROOT)/share/gnome/help/package-manager
ROOTICON16SHARE = $(ROOTSHARE)/icons/hicolor/16x16/actions
ROOTICON22SHARE = $(ROOTSHARE)/icons/hicolor/22x22/actions
ROOTMIMEICONSHARE = $(ROOT)/share/icons/hicolor/48x48/mimetypes
ROOTMIMETYPESHARE = $(ROOT)/share/mime/packages
ROOTPYTHON = $(ROOTUSRLIB)/python2.4
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg/gui
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTSPSHARE = $(ROOTSHARE)/data/startpagebase

ROOTDIRS = \
   $(ROOTAPPICONSHARE) \
   $(ROOTDATASHARE) \
   $(ROOTDESKTOPSHARE) \
   $(ROOTGCONFSHARE) \
   $(ROOTHELPSHARE) \
   $(ROOTICON16SHARE) \
   $(ROOTICON22SHARE) \
   $(ROOTMIMEICONSHARE) \
   $(ROOTMIMETYPESHARE) \
   $(ROOTPYTHONPKG) \
   $(ROOTSHARE) \
   $(ROOTSPSHARE)

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
   data/arrow.png \
   data/new_star_24x.png

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

ICONS16 = \
   data/icons/16x16/status_checkmark.png \
   data/icons/16x16/status_installed.png \
   data/icons/16x16/status_newupdate.png \
   data/icons/16x16/progress_checkmark.png \
   data/icons/16x16/progress_blank.png

ICONS22 = \
   data/icons/22x22/search.png \
   data/icons/22x22/search_all.png

PYMODS = \
   modules/__init__.py \
   modules/beadmin.py \
   modules/cache.py \
   modules/enumerations.py \
   modules/imageinfo.py \
   modules/installupdate.py \
   modules/misc.py \
   modules/parseqs.py \
   modules/progress.py \
   modules/repository.py \
   modules/webinstall.py

PYCMODS = $(PYMODS:%.py=%.pyc)

STATICHELPFILES = \
	$(C_ONLY_HELP_LOCALES:%=help/%/figures/update_all.png) \
	$(C_ONLY_HELP_LOCALES:%=help/%/figures/pm_pkglist.png) \
	$(C_ONLY_HELP_LOCALES:%=help/%/figures/pm_store.png) \
	$(C_ONLY_HELP_LOCALES:%=help/%/figures/wi_start.png)

STATICSPFILES = \
	$(SP_LOCALES:%=data/startpagebase/%/startpage.html) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/opensolaris.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/startpage_learn.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/startpage_share.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/startpage_star.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/startpage_use.png) \
	$(C_ONLY_SP_LOCALES:%=data/startpagebase/%/stub_test.html)

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

ROOTICONS16 = $(ICONS16:data/icons/16x16/%=$(ROOTICON16SHARE)/%)
ROOTICONS22 = $(ICONS22:data/icons/22x22/%=$(ROOTICON22SHARE)/%)

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
   $(ROOTICONS16) \
   $(ROOTICONS22) \
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
	ln -sf $(PWD)/data/icons /usr/share/package-manager/icons/hicolor
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

$(ROOTICON16SHARE)/%: $(ROOTDIRS) data/icons/16x16/%
	$(INSTALL) -f $(ROOTICON16SHARE) -m 0644 $<

$(ROOTICON22SHARE)/%: $(ROOTDIRS) data/icons/22x22/%
	$(INSTALL) -f $(ROOTICON22SHARE) -m 0644 $<

$(ROOTPYTHONPKG)/%: $(ROOTDIRS) modules/%
	$(INSTALL) -f $(ROOTPYTHONPKG) -m 0644 $<

$(ROOTSHARE)/%: $(ROOTDIRS) data/%
	$(INSTALL) -f $(ROOTSHARE) -m 0644 $<
