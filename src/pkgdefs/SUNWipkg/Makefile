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

ROOT = ../../../proto/root_$(MACH)
PKGARCHIVE = ../../../packages/$(MACH)
PKG:sh = . ./pkginfo; echo $PKG

# By default create only the sysv package; failure of the IPS package to build
# may confuse without enlightening.
install: sysv-pkg

sysv-pkg: $(PKGARCHIVE) prototype
	pkgmk -a $(MACH) -o -r $(ROOT) -d $(PKGARCHIVE)

clean: FRC

clobber: clean
	rm -rf $(PKGARCHIVE)/$(PKG)

$(PKGARCHIVE):
	[ -d $(PKGARCHIVE) ] || mkdir -p $(PKGARCHIVE)

FRC:
