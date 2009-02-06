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

install := TARGET = install
packages := TARGET = install
clobber := TARGET = clobber
clean := TARGET = clean

BUILDPYOPENSSL:sh = if [ -n "$BUILD_PYOPENSSL" ]; then echo SUNWpython-pyopenssl; fi

SUBDIRS= SUNWipkg SUNWipkg-brand SUNWipkg-gui SUNWipkg-gui-data \
    SUNWipkg-gui-l10n SUNWipkg-um SUNWpython-cherrypy SUNWpython-mako \
    $(BUILDPYOPENSSL)

all:

.PARALLEL:

$(SUBDIRS): FRC
	@cd $@; pwd; $(MAKE) $(TARGET)

install packages: $(SUBDIRS)
	pkgtrans ../../packages/$(MACH) pkg5-`hg id -i`.pkg $(SUBDIRS)
	rm -f ../../packages/$(MACH)/pkg5.pkg
	cd ../../packages/$(MACH) && ln -s pkg5-`hg id -i`.pkg pkg5.pkg

clean: $(SUBDIRS)

clobber: $(SUBDIRS)
	rm -f ../../packages/$(MACH)/pkg-*.pkg
	rm -f ../../packages/$(MACH)/pkg5.pkg

FRC:
