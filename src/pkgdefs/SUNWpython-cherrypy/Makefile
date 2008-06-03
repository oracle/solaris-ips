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

CP = CherryPy
CPVER = 3.0.3
CPARC = $(CP)-$(CPVER).tar.gz
CPDIR = $(CP)-$(CPVER)
CPURL = http://download.cherrypy.org/cherrypy/$(CPVER)/$(CPARC)

TEST = test
WGET = wget
GUNZIP = gunzip
TAR = tar

MACH:sh = uname -p

ROOT = ../../../proto/root_$(MACH)
PKG = SUNWpython-cherrypy
PKGARCHIVE = ../../../packages/$(MACH)
PROTOLOC = $(ROOT)/usr/lib/python2.4/vendor-packages/cherrypy

# By default create only the sysv package; failure of the IPS package to build
# may confuse without enlightening.
install: sysv-pkg

sysv-pkg: $(PKGARCHIVE) prototype
	[ -f $(PKGARCHIVE)/$(PKG)/pkgmap ] || pkgmk -a $(MACH) -o -r $(ROOT) -d $(PKGARCHIVE)

$(CPARC):
	[ -f $(CPARC) ] || $(WGET) $(CPURL) || \
	echo "Unable to retrieve $(CPARC).\n" \
	"\nPlease retrieve the file and place it in:\n$(PWD)\n" || exit 1

$(CPDIR): $(CPARC)
	[ -d $(CPDIR) ] || gunzip -dc $(CPARC) | $(TAR) xf -

$(PROTOLOC): $(CPDIR)
	(cd $(CPDIR); \
	python setup.py install -f --prefix=../$(ROOT)/usr; \
	cd ..; \
	rm -rf $(ROOT)/usr/lib/python2.4/vendor-packages/cherrypy; \
	mkdir -p $(ROOT)/usr/lib/python2.4/vendor-packages; \
	mv $(ROOT)/usr/lib/python2.4/site-packages/cherrypy $(PROTOLOC); \
	rmdir $(ROOT)/usr/lib/python2.4/site-packages)

prototype: $(PROTOLOC)
	(cd $(ROOT); pkgproto .) | \
		nawk 'BEGIN { \
			print "i pkginfo"; \
			print "i copyright" \
		} \
		$$1 == "d" { \
			$$4 = "755" \
		} \
		$$1 == "f" { \
			$$4 = "444" \
		} \
		{ \
			$$5 = "root"; \
			$$6 = "bin"; \
		} \
		{ \
			if ($$1 == "d" && $$3 ~ /^(usr(\/lib(\/python2.4(\/vendor-packages(\/cherrypy(\/.*)?)?)?)?)?)$$/) \
			{ \
				print \
			} \
			if ($$1 == "f" && $$3 ~ /^usr\/lib\/python2.4\/vendor-packages\/cherrypy/) \
			{ \
				print \
			} \
		}' > prototype

clobber:
	rm -f prototype
	rm -rf $(CPDIR)
	rm -rf $(PKGARCHIVE)/$(PKG)

# This will only work if there's a server running, so allow failure.
img-pkg: sysv-pkg
	-../../util/distro-import/solaris.py -b 0.0 -w $(PKGARCHIVE) $(PKG).import

$(PKGARCHIVE):
	[ -d $(PKGARCHIVE) ] || mkdir -p $(PKGARCHIVE)

FRC:
