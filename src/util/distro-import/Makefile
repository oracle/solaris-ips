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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

# Needs to point to filesystem on Solaris install dvd
# replace as needed with a local solaris install image
WOS_PATH=/net/netinstall.sfbay/export/nv/x/72/Solaris_11/Product

TMPPKGS=SUNWcsdreplace

default:	$(TMPPKGS) cluster.import

cluster.import:	$(WOS_PATH)/.clustertoc
	./clustertoc2import.py $(WOS_PATH)/.clustertoc | egrep -v 'SUNWjds-registration|SUNWdttsr|SUNWdttsu' > $@

etc/driver_aliases: etc $(WOS_PATH)/SUNWcsd/pkgmap
	./get_file_from_pkg.py $(WOS_PATH)/SUNWcsd etc/driver_aliases | \
	./driver_names.py `find common i386 -type f` > etc/driver_aliases

etc/name_to_major:	etc $(WOS_PATH)/SUNWcsd/pkgmap
	./get_file_from_pkg.py $(WOS_PATH)/SUNWcsd etc/name_to_major | \
	./driver_names.py `find common i386 -type f` > etc/name_to_major

etc:
	mkdir etc

SUNWcsdreplace: etc/name_to_major etc/driver_aliases


%:	%.prototype
	pkgmk -r `pwd` -f $@.prototype -d `pwd` -o


import:	cluster.import $(TMPPKGS)
	./solaris.py -w $(WOS_PATH) all.i386
