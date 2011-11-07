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
#   $ make book      (makes the pdf using rst2pdf)
#   $ make xmlbook   (makes docbook using rst2docbook)
#   $ make check     (makes pdfs from each book fragment)
#   $ make chpt1.pdf (makes a single pdf)
#   $ make -e IGNORE_ERRORS=true chpt4.pdf
#   $ make clobber
#
#
# Note: in order for the pdf to build, we need to have
# library/python-2/python-imaging-26 installed, due to
# the png logo we use in macros.txt, referenced by
# developer-guide.txt
#

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
		appendix-a.txt		\
		appendix-b.txt

PROTO=../../proto/dev-guide
DOCTMP=doctmp
DOCTOOLS=doctools
TOOLSPATH=$(DOCTOOLS)/lib/python2.6/site-packages

RST2PDF=@PYTHONPATH=$(TOOLSPATH) $(DOCTOOLS)/bin/rst2pdf -s $(STYLE) $(BOOK_OPT)
STYLE=dev-guide.style

# XXX unused at present - unsure if rst2docbook is correct, or whether we want
# to go to the docutils xml, then apply XSLT et al to get to docbook instead.
# For now, $RST2DOCBOOK gets used.
RST2XML=PYTHONPATH=$(TOOLSPATH) $(DOCTOOLS)/bin/rst2xml.py --no-generator --no-file-insertion

RST2DOCBOOK=PYTHONPATH=$(TOOLSPATH) $(DOCTOOLS)/bin/rst2docbook.py \
	--no-generator --no-file-insertion --doctype=book
DOCBOOKRST_URL=http://docutils.sourceforge.net/sandbox/oliverr/docbook
DOCBOOKRST_CMD=echo $(DOCBOOKRST_URL) | sed -e 's/http:\/\///g'
DOCBOOKRST_PATH=$(DOCBOOKRST_CMD:sh)

# when building the pdf book, we add specific options here
BOOK_OPT=

EASY_INSTALL=PYTHONPATH=$(TOOLSPATH) /usr/bin/easy_install
GPATCH=/usr/bin/gpatch
WGET=/usr/bin/wget

# our version of docutils doesn't work with rst2pdf at the moment, so we need
# to apply a patch to that code.  We apply a similar patch to docbook.py
CREATEPDF=$(TOOLSPATH)/rst2pdf-0.16-py2.6.egg/rst2pdf/createpdf.py
DOCBOOKPY=$(TOOLSPATH)/docutils-0.8.1-py2.6.egg/docutils/writers/docbook.py

VERSION_CMD=hg identify | awk '{print $1}'
VERSION=$(VERSION_CMD:sh)
DATE_CMD=date +%F:%R:%S-%Z
DATE=$(DATE_CMD:sh)

VERSTAMP=$(DATE) $(VERSION)

all:	install
install: rst2pdf proto book

# pull down a local copy of rst2pdf and rst2docbook.py
tools:  rst2pdf rst2docbook proto

rst2pdf: proto
	@if [ ! -f $(CREATEPDF) ]; then \
		$(EASY_INSTALL) --prefix=$(DOCTOOLS) rst2pdf; \
		$(GPATCH) -f -R $(CREATEPDF) < createpdf.patch; \
	fi

rst2docbook: rst2pdf
	@if [ ! -f $(DOCBOOKPY) ]; then \
		cd $(DOCTMP) ; \
		$(WGET) -q -r -np $(DOCBOOKRST_URL); \
		cd $(DOCBOOKRST_PATH); \
		python setup.py install --prefix=../../../../../$(DOCTOOLS); \
		cd ../../../../../ ; \
		# XXX this is ugly; \
		cp -r $(TOOLSPATH)/docutils $(TOOLSPATH)/docutils-0.8.1-py2.6.egg ; \
		rm -rf $(TOOLSPATH)/docutils ; \
		$(GPATCH) -f -R $(DOCBOOKPY) < docbook.patch; \
	fi

proto: doctmp doctools
	mkdir -p $(PROTO)
	@cp macros.txt $(PROTO)
	@echo ".. |version| replace:: $(VERSTAMP)" >> $(PROTO)/macros.txt

doctools:
	mkdir -p $(TOOLSPATH)

doctmp:
	mkdir $(DOCTMP)

# tries to build all fragments, then builds the book itself
check:	$(BOOK_FRAGMENTS:%.txt=$(PROTO)/%.pdf) book
copy:	$(BOOK_FRAGMENTS:%.txt=$(PROTO)/%.txt)

book: booktxt
	$(MAKE) BOOK_OPT=-b1 $(PROTO)/book.pdf

xmlbook: booktxt
	$(MAKE) $(PROTO)/book.xml

booktxt: proto
	# Convert bold/italic mentions of "Chapter x" into hyperlinks
	# and concatenate into a single file, to render our book
	cat $(BOOK_FRAGMENTS) | \
		gsed -re 's#\*\*(Chapter [0-9]+)\*\*#`\1`_#g' | \
		gsed -re 's#\*(Chapter [0-9]+)\*#`\1`_#g' | \
		gsed -re 's#\*\*(Appendix [AB])\*\*#`\1`_#g' | \
		gsed -re 's#\*(Appendix [AB])\*#`\1`_#g' > $(PROTO)/book.txt

	@# XXX this is ugly, but means we get to reuse the %.pdf & %.xml targets
	cp $(PROTO)/book.txt book.txt

$(PROTO)/%.txt: proto
	cp $*.txt $(PROTO)
	@cat $(PROTO)/macros.txt >> $(PROTO)/$*.txt

$(PROTO)/%.pdf: tools proto $(PROTO)/%.txt
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

$(PROTO)/%.xml: tools proto $(PROTO)/%.txt
	@print "creating $(PROTO)/$*.xml"
	$(RST2DOCBOOK) $(PROTO)/$*.txt $@

# convenience targets to build a single fragment
%.txt: $(PROTO)/%.txt
%.pdf: $(PROTO)/%.txt $(PROTO)/%.pdf

clean:
	rm -rf $(PROTO) $(DOCTMP)

clobber: clean
	rm -rf $(DOCTOOLS)

