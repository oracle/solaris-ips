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
# Copyright (c) 2020, 2025, Oracle and/or its affiliates.
#

include ../Makefile.constants

XML2ROFF =	/usr/share/xml/xsolbook/python/xml2roff.py --logfile nroff/xml2roff.log

ROOTMAN =	$(ROOTUSRSHARE)/man

MAN1 = \
	pkg.1 \
	pkgdepend.1 \
	pkgdiff.1 \
	pkgfmt.1 \
	pkglint.1 \
	pkgmerge.1 \
	pkgmogrify.1 \
	pkgrecv.1 \
	pkgrepo.1 \
	pkgsend.1 \
	pkgsign.1 \
	pkgsurf.1

MAN7 = \
	pkg.7

MAN8 = \
	pkg.depot-config.8 \
	pkg.depotd.8 \
	pkg.sysrepo.8


all: \
	$(MAN1:%=nroff/man1/%) \
	$(MAN7:%=nroff/man7/%) \
	$(MAN8:%=nroff/man8/%) \
	$(MAN1:%=nroff/ja_JP.UTF-8/man1/%) \
	$(MAN7:%=nroff/ja_JP.UTF-8/man7/%) \
	$(MAN8:%=nroff/ja_JP.UTF-8/man8/%) \
	$(MAN1:%=nroff/zh_CN.UTF-8/man1/%) \
	$(MAN7:%=nroff/zh_CN.UTF-8/man7/%) \
	$(MAN8:%=nroff/zh_CN.UTF-8/man8/%)

nroff/man1/% nroff/man7/% nroff/man8/%: %
	$(XML2ROFF) -o nroff $^

nroff/ja_JP.UTF-8/man1/% nroff/ja_JP.UTF-8/man7/% nroff/ja_JP.UTF-8/man8/%: ja_JP/%
	$(XML2ROFF) -o nroff/ja_JP.UTF-8 $^

nroff/zh_CN.UTF-8/man1/% nroff/zh_CN.UTF-8/man7/% nroff/zh_CN.UTF-8/man8/%: zh_CN/%
	$(XML2ROFF) -o nroff/zh_CN.UTF-8 $^

ROOTMANFILES =	\
	$(MAN1:%=$(ROOTMAN)/man1/%) \
	$(MAN7:%=$(ROOTMAN)/man7/%) \
	$(MAN8:%=$(ROOTMAN)/man8/%)

ROOTMANJPFILES =	\
	$(MAN1:%=$(ROOTMAN)/ja_JP.UTF-8/man1/%) \
	$(MAN7:%=$(ROOTMAN)/ja_JP.UTF-8/man7/%) \
	$(MAN8:%=$(ROOTMAN)/ja_JP.UTF-8/man8/%)

ROOTMANCNFILES =	\
	$(MAN1:%=$(ROOTMAN)/zh_CN.UTF-8/man1/%) \
	$(MAN7:%=$(ROOTMAN)/zh_CN.UTF-8/man7/%) \
	$(MAN8:%=$(ROOTMAN)/zh_CN.UTF-8/man8/%)

# install English manpage sources to put into localizable file package
ROOTMANLOCALEFILES =	\
	$(MAN1:%=$(ROOTMAN)/__LOCALE__/man1/%) \
	$(MAN7:%=$(ROOTMAN)/__LOCALE__/man7/%) \
	$(MAN8:%=$(ROOTMAN)/__LOCALE__/man8/%)

install: \
	$(ROOTMANFILES) \
	$(ROOTMANJPFILES) \
	$(ROOTMANCNFILES) \
	$(ROOTMANLOCALEFILES)

$(ROOTMAN)/%: nroff/%
	$(INS.file)

$(ROOTMAN)/__LOCALE__/man1/%: %
	$(INS.file)

$(ROOTMAN)/__LOCALE__/man7/%: %
	$(INS.file)

$(ROOTMAN)/__LOCALE__/man8/%: %
	$(INS.file)

check lint:

# Generate a zipfile of manpages for translation when necessary
# After generating, submit to translation engine using the instructions
# under "Translated man pages" in the ON Development Process wiki page.
manpages-ua.zip: FRC
	rm -rf manpages-ua.zip manpages
	mkdir -p manpages
	for manpage in *.1 *.7 *.8; do ; \
		cp $$manpage manpages/$$manpage ; \
		printf '"manpages/%s" "%s" ja_JP+zh_CN solbook\n' \
		    $$manpage $$manpage >> manpages/manpages.bom ; \
	done
	sort -u manpages/manpages.bom -o manpages/manpages.bom
	zip -r manpages-ua.zip manpages/

clean:
	rm -rf manpages-ua.zip manpages nroff

clobber: clean

FRC:
