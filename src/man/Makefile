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
# Copyright (c) 2020, 2024, Oracle and/or its affiliates.
#

INSTALL:sh =	echo /opt/onbld/bin/$(uname -p)/stash file -v
MKDIR = 	mkdir -p
XML2ROFF =	/usr/share/xml/xsolbook/python/xml2roff.py --logfile nroff/xml2roff.log

PROTO_AREA:sh =	echo $(dirname $(dirname $(pwd)))/proto/root_$(uname -p)
MAN_DIR =	$(PROTO_AREA)/usr/share/man

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

install: all
	@for lang in "" /ja_JP.UTF-8 /zh_CN.UTF-8; do \
		dir=$(MAN_DIR)$$lang; \
		for man in $(MAN1:%=man1/%) $(MAN7:%=man7/%) $(MAN8:%=man8/%); do \
			$(INSTALL) nroff$$lang/$$man $$dir/$$man; \
		done; \
	done; \
	# install English manpage sources to put into localizable file package \
	dir=$(MAN_DIR)/__LOCALE__; \
	for man in $(MAN1); do \
		$(INSTALL) $$man $$dir/man1/$$man; \
	done; \
	for man in $(MAN7); do \
		$(INSTALL) $$man $$dir/man7/$$man; \
	done; \
	for man in $(MAN8); do \
		$(INSTALL) $$man $$dir/man8/$$man; \
	done

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
