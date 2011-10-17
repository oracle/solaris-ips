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
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.
#


# A simple Makefile to build the dev-guide.
# Examples:
#
#   $ make book
#   $ make check
#   $ make chpt1.pdf
#   $ make -e IGNORE_ERRORS=true chpt4.pdf
#   $ make clobber

# set this to make the build to ignore errors in RST documents.
IGNORE_ERRORS=

BOOK_FRAGMENTS= developer-guide.txt	\
		chpt1.txt		\
		chpt2.txt		\
		chpt3.txt		\
		chpt4.txt		\
		chpt5.txt		\
		chpt6.txt		\
		chpt7.txt		\
		chpt8.txt		\
		chpt9.txt		\
		chpt10.txt		\
		chpt11.txt		\
		chpt12.txt		\
		chpt13.txt		\
		chpt14.txt		\
		appendix1.txt		\
		appendix2.txt

PROTO=../../proto/dev-guide
DOCTMP=doctmp
DOCTOOLS=doctools
TOOLSPATH=$(DOCTOOLS)/lib/python2.6/site-packages

# styles are searched under $(TOOLSPATH)/rst2pdf-0.16-py2.6.egg/rst2pdf/styles/
STYLE=serif.style

RST2PDF=@PYTHONPATH=$(TOOLSPATH) $(DOCTOOLS)/bin/rst2pdf -s $(STYLE) $(BOOK_OPT)

# when building the book, we add options specific to that here
BOOK_OPT=
EASY_INSTALL=PYTHONPATH=$(TOOLSPATH) /usr/bin/easy_install
GPATCH=/usr/bin/gpatch

# our version of docutils doesn't work with rst2pdf at the moment, so we need
# to apply a patch to that code.
CREATEPDF=$(TOOLSPATH)/rst2pdf-0.16-py2.6.egg/rst2pdf/createpdf.py

all:	install
install: rst2pdf proto book

# pull down a local copy of rst2pdf
rst2pdf: proto
	@if [ ! -f $(CREATEPDF) ]; then \
		$(EASY_INSTALL) --prefix=$(DOCTOOLS) rst2pdf; \
		$(GPATCH) -f -R $(CREATEPDF) < createpdf.patch; \
	fi

proto: doctmp doctools
	mkdir -p $(PROTO)

doctools:
	mkdir -p $(TOOLSPATH)

doctmp:
	mkdir $(DOCTMP)

# tries to build all fragments, then builds the book itself
check:	$(BOOK_FRAGMENTS:%.txt=$(PROTO)/%.pdf) book
copy:	$(BOOK_FRAGMENTS:%.txt=$(PROTO)/%.txt)

book: proto
	# Convert bold/italic mentions of "Chapter x" into hyperlinks
	# and concatenate into a single file, to render our book
	cat $(BOOK_FRAGMENTS) | \
		gsed -re 's#\*\*(Chapter [0-9]+)\*\*#`\1`_#g' | \
		gsed -re 's#\*(Chapter [0-9]+)\*#`\1`_#g' | \
		gsed -re 's#\*\*(Appendix [0-9]+)\*\*#`\1`_#g' | \
		gsed -re 's#\*(Appendix [0-9]+)\*#`\1`_#g' > $(PROTO)/book.txt

	@# XXX this is ugly, but means we get to reuse the %.pdf target
	cp $(PROTO)/book.txt book.txt
	$(MAKE) BOOK_OPT=-b1 $(PROTO)/book.pdf

$(PROTO)/%.txt: proto
	cp $*.txt $(PROTO)

$(PROTO)/%.pdf: rst2pdf proto $(PROTO)/%.txt
	@print "creating $(PROTO)/$*.pdf"
	$(RST2PDF) -o $@ $(PROTO)/$*.txt 2> $(DOCTMP)/$*.rst-output.txt
	@if [ -s $(DOCTMP)/$*.rst-output.txt ]; then \
		print "Errors/warnings found in $*.txt"; \
		cat $(DOCTMP)/$*.rst-output.txt; \
		if [ -z "$(IGNORE_ERRORS)" ]; then \
			rm $(DOCTMP)/$*.rst-output.txt; \
			exit 1;\
		fi; \
	fi;

# convenience targets to build a single fragment
%.txt: $(PROTO)/%.txt
%.pdf: $(PROTO)/%.txt $(PROTO)/%.pdf

clean:
	rm -rf $(PROTO) $(DOCTMP)

clobber: clean
	rm -rf $(DOCTOOLS)

