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
# Copyright (c) 2024, Oracle and/or its affiliates.
#

XGETTEXT =	/usr/gnu/bin/xgettext
MSGFMT =	/usr/bin/msgfmt
MKDIR = 	mkdir -p
INSTALL =	cp

PROTO_AREA:sh =	echo $(dirname $(dirname $(pwd)))/proto/root_$(uname -p)
LOCALE_DIR =	$(PROTO_AREA)/usr/share/locale

LOCALES:sh =	grep -v "^\#" LINGUAS
CATALOGS =	$(LOCALES:=.mo)


all: $(CATALOGS) pkg.pot

%.mo: %.po
	$(MSGFMT) -o $@ $^

pkg.pot: POTFILES.in
	$(XGETTEXT) --add-comments --keyword=N_ --from-code=UTF-8 -f POTFILES.in -D .. -o pkg.pot

install: all
	@for locale in $(LOCALES); do \
		dir=$(LOCALE_DIR)/$$locale/LC_MESSAGES; \
		$(MKDIR) $$dir; \
		$(INSTALL) $$locale.mo $$dir/pkg.mo; \
		echo "copying $$locale.mo -> $$dir/pkg.mo"; \
	done; \
	dir=$(LOCALE_DIR)/__LOCALE__/LC_MESSAGES; \
	$(MKDIR) $$dir; \
	$(INSTALL) pkg.pot $$dir/pkg.pot; \
	echo "copying pkg.pot -> $$dir/pkg.pot"

check:
	$(XGETTEXT) --keyword=N_ --from-code=UTF-8 -f POTFILES.in -D .. -o /dev/null 2>i18n_errs.txt
	@if [ -s i18n_errs.txt ]; then \
		echo "The following i18n errors were detected and should be corrected:"; \
		echo "(this list is saved in i18n_errs.txt)"; \
		cat i18n_errs.txt; \
		exit 1; \
	fi

clean:
	rm -f pkg.pot *.mo i18n_errs.txt

clobber: clean
