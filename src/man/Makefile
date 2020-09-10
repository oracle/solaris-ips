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
# Copyright (c) 2020, Oracle and/or its affiliates.
#

# Nothing to do here when just building the gate, as nroff man pages
# are handled by xml2roff() in src/setup.py
all install lint clint pylint check test test-verbose test-generate:

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
	rm -rf manpages-ua.zip manpages

clobber: clean

FRC:
