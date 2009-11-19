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

all := TARGET = all
link := TARGET = link
link-clean := TARGET = link-clean

all:

PWD:sh = pwd 
link:
	-mkdir -p /usr/share/man/cat1 /usr/share/man/cat1m /usr/share/man/cat5
	ln -sf $(PWD)/packagemanager.1.txt /usr/share/man/cat1/packagemanager.1
	ln -sf $(PWD)/pkg.1.txt /usr/share/man/cat1/pkg.1
	ln -sf $(PWD)/pkgdep.1.txt /usr/share/man/cat1/pkgdep.1
	ln -sf $(PWD)/pkgmogrify.1.txt /usr/share/man/cat1/pkgmogrify.1
	ln -sf $(PWD)/pkgrecv.1.txt /usr/share/man/cat1/pkgrecv.1
	ln -sf $(PWD)/pkgsend.1.txt /usr/share/man/cat1/pkgsend.1
	ln -sf $(PWD)/pm-updatemanager.1.txt /usr/share/man/cat1/pm-updatemanager.1
	ln -sf $(PWD)/pkg.depotd.1m.txt /usr/share/man/cat1m/pkg.depotd.1m
	ln -sf $(PWD)/pkg.5.txt /usr/share/man/man5/pkg.5

link-clean:
	rm -f /usr/share/man/cat1/packagemanager.1
	rm -f /usr/share/man/cat1/pkg.1
	rm -f /usr/share/man/cat1/pkgrecv.1
	rm -f /usr/share/man/cat1/pkgsend.1
	rm -f /usr/share/man/cat1/pm-updatemanager.1
	rm -f /usr/share/man/cat1m/pkg.depotd.1m
	rm -f /usr/share/man/cat5/pkg.5

