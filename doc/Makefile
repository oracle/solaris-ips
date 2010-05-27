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

# Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.

PWD:sh = pwd

RST2HTML_FLAGS = --rfc-references \
                 --no-generator \
                 --time \
                 --stylesheet-path=$(CSS) \
		 --link-stylesheet

RST2LATEX = rst2latex.py

RST2LATEX_FLAGS = --documentclass=ireport --documentoptions=12pt

draft := RST2LATEX_FLAGS = --documentclass=idraft --documentoptions=12pt

.MAKE.STATE:

M4_ARGS = -DCOMPLETE=1

WEB_INCLUDES = macros.rsi web.css

output/%.rsi: output %.rst
	gm4 $(M4_ARGS) $< > $@


TXT_FRAGMENTS = \
	apt.txt \
	catalog.txt \
	deduction.txt \
	elf-jar-handling.txt \
	es-requirements.txt \
	file-metadata.txt \
	filter.txt \
	image.txt \
	multi-platform.txt \
	one-pager-main.txt \
	protocol-versioning.txt \
	publication.txt \
	razor.txt \
	rest.txt \
	rfes.txt \
	transaction-order.txt \
	usr-setuid-bins.txt \
	versions.txt \
	wos-conversion.txt \
	wos-filetype-stats.txt \
	xml.txt

RST_FRAGMENTS = \
	actions.rst \
	depot.rst \
	guide-basic-ops.rst \
	guide-implementation-depot.rst \
	guide-metadata-conventions.rst \
	guide-naming-conventions.rst \
	guide-pkg-states.rst \
	guide-publication-protocol.rst \
	guide-repository-format.rst \
	guide-retrieval-protocol.rst \
	guide-txn-states.rst \

RST_JOINS = \
	guide-main.rst

CSS=pkg-guide-web.css

HTML_DIR = html-out
FILE_URL = file://$(PWD)/$(HTML_DIR)

HTML_CSS = $(HTML_DIR)/$(CSS)
HTML_FRAGMENTS = $(RST_FRAGMENTS:%.rst=$(HTML_DIR)/%.html)
HTML_JOINS = $(RST_JOINS:%.rst=$(HTML_DIR)/%.html)

.KEEP_STATE:

pdf: guide-main.pdf

draft: pdf

html: $(HTML_DIR) .WAIT $(HTML_CSS) $(HTML_FRAGMENTS) $(HTML_JOINS)

$(HTML_JOINS): $(HTML_FRAGMENTS)

html-out:
	-mkdir $@

# If we are embedding stylesheets, then we may wish to have this rule also
# depend on $(CSS).
$(HTML_DIR)/%.html: %.rst macros.rst
	rst2html.py $(RST2HTML_FLAGS) $< > $@

$(HTML_DIR)/$(CSS): $(CSS)
	cp $(CSS) $@

%.pdf: %.rst macros.rst $(RSI_INCLUDES)
	$(RST2LATEX) $(RST2LATEX_FLAGS) $< > $(<:%.rst=%.tex)
	pdflatex $(<:%.rst=%.tex)
	pdflatex $(<:%.rst=%.tex)

clean:
	rm -f $(HTML_FRAGMENTS) $(RSI_INCLUDES)

clobber: clean
