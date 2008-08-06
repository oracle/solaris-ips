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
ROOTUSRLIB = $(ROOT)/lib
ROOTSHARE = $(ROOT)/share/package-manager
ROOTDESKTOPSHARE = $(ROOT)/share/applications
ROOTDATASHARE = $(ROOTSHARE)/data
ROOTPYTHON = $(ROOTUSRLIB)/python2.4
ROOTPYTHONVENDOR = $(ROOTPYTHON)/vendor-packages
ROOTPYTHONPKG = $(ROOTPYTHONVENDOR)/pkg/gui
ROOTICONSHARE = $(ROOT)/share/icons/package-manager

ROOTDIRS = \
   $(ROOTPYTHONPKG) \
   $(ROOTSHARE) \
   $(ROOTICONSHARE) \
   $(ROOTDATASHARE) \
   $(ROOTDESKTOPSHARE) 

PYMODS = \
   modules/__init__.py \
   modules/imageinfo.py \
   modules/installupdate.py \
   modules/remove.py \
   modules/enumerations.py \
   modules/filelist.py \
   modules/thread.py 
PYCMODS = $(PYMODS:%.py=%.pyc)

ICONS = \
   data/icons/new_update.png 

GLADEICONS = \
   data/PM_app_48x.png \
   data/PM_package_36x.png

CATALOG = \
   data/opensolaris.org \
   data/opensolaris.org.sections

DESKTOP = \
   data/packagemanager.desktop

ROOTPYMODS = $(PYMODS:modules/%=$(ROOTPYTHONPKG)/%)

ROOTICONS = $(ICONS:data/%=$(ROOTICONSHARE)/%)

ROOTDESKTOP = $(DESKTOP:%=$(ROOTDESKTOPSHARE)/%)

ROOTCATALOG = $(CATALOG:data/%=$(ROOTDATASHARE)/%)

ROOTGLADEICONS = $(GLADEICONS:data/%=$(ROOTSHARE)/%)

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
   $(ROOTICONS) \
   $(ROOTDESKTOP) \

all := TARGET = all
install := TARGET = install
clean := TARGET = clean
link := TARGET = link
link-clean := TARGET = link-clean

all:
	cd data; pwd;\
	  LC_ALL=C intltool-merge -d -u -c ../po/.intltool-merge-cache ../po packagemanager.desktop.in packagemanager.desktop

install: all $(ROOTCOMPONENTS)
	@cd po; pwd;\
	  mkdir -p ../$(ROOT); \
	  for PO in *.po; do \
	    LING=`basename $$PO .po`; \
	    MO=$$LING.mo; \
	    msgfmt -o $$MO $$PO; \
	    mkdir -p ../$(ROOT)/share/locale/$$LING/LC_MESSAGES; \
	    cp $$MO ../$(ROOT)/share/locale/$$LING/LC_MESSAGES/packagemanager.mo; \
	  done;

clean:
	rm -f $(PYCMODS)
	rm -f $(DESKTOP)
   
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
	ln -sf $(PWD)/data/icons /usr/share/icons/package-manager
	ln -sf $(PWD)/modules /usr/lib/python2.4/vendor-packages/pkg/gui

link-clean:
	rm -rf /usr/share/lib/package-manager
	rm -rf /usr/lib/python2.4/vendor-packages/pkg/gui
	rm -f /usr/share/applications/packagemanager.desktop
	rm -f /usr/bin/packagemanager

proto: $(ROOT)

$(ROOTDIRS):
	mkdir -m 0755 -p $@

$(ROOTDATASHARE)/%: data/%
	rm -f $@; install -f $(ROOTDATASHARE) -m 0644 $<

$(ROOTPYTHONPKG)/%: modules/%
	rm -f $@; install -f $(ROOTPYTHONPKG) -m 0644 $<

$(ROOTICONSHARE)/%: data/%
	rm -f $@; install -f $(ROOTICONSHARE) -m 0644 $<

$(ROOTDESKTOPSHARE)/%: %
	rm -f $@; install -f $(ROOTDESKTOPSHARE) -m 0644 $<

$(ROOTSHARE)/%: data/%
	rm -f $@; install -f $(ROOTSHARE) -m 0644 $<

