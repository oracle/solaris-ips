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
#

PKGVERS_COMPONENT = 0.5.11
PKGVERS_BUILTON   = 5.11
BUILDNUM.cmd      = hg tags | nawk '$$1 ~ /^in[0-9]*$$/ {print substr($$1, 3) + 1; exit}'
BUILDNUM          = $(BUILDNUM.cmd:sh)
CURBUILD.cmd      = pkg -R / list -H osnet-incorporation | sed -e 's/.*-0\.\([^ ]*\).*/\1/'
CURBUILD          = $(CURBUILD.cmd:sh)
PKGVERS_BRANCH    = 0.$(BUILDNUM)
PKGVERS           = $(PKGVERS_COMPONENT),$(PKGVERS_BUILTON)-$(PKGVERS_BRANCH)
ARCH.cmd          = uname -p
ARCH              = $(ARCH.cmd:sh)
REV.cmd           = date +%Y.%m.%d.%H.%M.%S
REV               = $(REV.cmd:sh)

PDIR              = pkgtmp
PWD:sh            = pwd
PKGDEST           = $(PWD)/../../packages/$(ARCH)
PKGROOT           = ../../proto/root_$(ARCH)
PKGLINT           = $(PKGROOT)/usr/bin/pkglint -f $(PKGROOT)/usr/share/lib/pkg/pkglintrc

PKGPUBLISHER      = pkg5-nightly

POUND_SIGN:sh     = echo \\043
PUBLISHALL        = $(POUND_SIGN)
MANIFESTS.cmd     = \
	cd manifests; \
	buildnum=$(BUILDNUM); \
	m=$$($(PKGMOGRIFY) -O /dev/null *.p5m ../transforms/nopublish); \
	echo "$$m" | while read name build; do \
		[[ $$build -gt $${buildnum%%.*} ]] && echo $$name; \
	done
MANIFESTS         = $(MANIFESTS.cmd:sh)
$(PUBLISHALL)MANIFESTS:sh      = (cd manifests; print *.p5m)
PKGS.cmd          = print $(MANIFESTS:%.p5m=%) | sed -e s/%2F/\\//g
PKGS              = $(PKGS.cmd:sh)
PKGMOGRIFY        = pkgmogrify
PKGSEND           = pkgsend
PKGREPO           = pkgrepo
MOGRIFESTS        = $(MANIFESTS:%.p5m=$(PDIR)/%.mog)
PUBLIFESTS        = $(MANIFESTS:%.p5m=$(PDIR)/%.pub)
INCORP            = consolidation%2Fips%2Fips-incorporation

PM_TRANSFORMS     = defaults

PKGMOG_DEFVALS    = \
	ARCH=$(ARCH) \
	PKGVERS_COMPONENT=$(PKGVERS_COMPONENT) \
	PKGVERS_BUILTON=$(PKGVERS_BUILTON) \
	PKGVERS_BRANCH=$(PKGVERS_BRANCH) \
	PKGVERS=$(PKGVERS) \
	REV=$(REV) \
	CURBUILD_BRANCH=0.$(CURBUILD) \
	PYDIR=usr/lib/python2.6 \
	PYDIRVP=usr/lib/python2.6/vendor-packages
PKGMOG_DEFINES    = $(PKGMOG_DEFVALS:%=-D %)

all: $(MOGRIFESTS)
install: lint

clean:
	rm -rf $(PDIR)

clobber: clean
	rm -rf $(PKGDEST) Makefile.link

# Pass SVr4 package production off to its own makefile
svr4:
	$(MAKE) -f Makefile.svr4 _svr4

$(PDIR):
	mkdir -p $@

# Finalize the repository
repository-metadata: publish-pkgs
	$(PKGREPO) -s $(PKGDEST)/repo refresh

publish-pkgs: $(PKGDEST)/repo .WAIT $(PUBLIFESTS)

# Initialize the repository
$(PKGDEST)/repo:
	$(PKGREPO) create $@
	$(PKGREPO) -s $@ set publisher/prefix=$(PKGPUBLISHER)

# Special rule for creating the incorporation.  Note that the incorporation
# looks at all manifests, not just the ones listed in $(MANIFESTS).  This is
# because we need to incorporate obsolete and renamed packages, even if we
# choose not to continue republishing them.
$(PDIR)/$(INCORP).mog: manifests/$(INCORP).p5m $(PDIR) transforms/incorp
	$(PKGMOGRIFY) -I transforms incorp2 manifests/$(INCORP).p5m | \
		$(PKGMOGRIFY) $(PKGMOG_DEFINES) -D DEPTYPE=incorporate \
		-I transforms -O $@ /dev/stdin incorp manifests/*.p5m

# The main mogrification rule
$(PDIR)/%.mog: manifests/%.p5m $(PM_TRANSFORMS:%=transforms/%) $(PDIR) $(PM_TRANSFORMS:%=transforms/%)
	$(PKGMOGRIFY) $(PKGMOG_DEFINES) -I transforms -O $@ $< $(PM_TRANSFORMS)

# The main publication rule
$(PDIR)/%.pub: $(PDIR)/%.mog $(PKGDEST)/repo
	$(PKGSEND) -s file://$(PKGDEST)/repo publish -d $(PKGROOT) -d license_files \
		-T \*.py --fmri-in-manifest --no-index --no-catalog $<
	touch $@

# Compare the proto area with the package manifests; if they've got different
# filesets, complain
check: $(PDIR)/protomanifest $(PDIR)/pkgmanifest
	pkgdiff $(PDIR)/protomanifest $(PDIR)/pkgmanifest

# We either lint against a reference repository, provided in
# $(PKGLINT_REF_REPO) or just with the repository we built.
# If the latter, we expect a number of pkglint warnings, due
# to being unable to lookup dependencies.
# Rather than using the pkglint return code, we collect the
# output, remove versioning information then diff against
# a list of those expected warnings.
#
# From this diff, we produce two files:
# 1) a list of fixed pkglint errors/warnings previously
#    recorded in the whitelist
# 2) a list of new pkglint errors/warnings
#
# If new warnings/errors appear in the lint output, we return an error.
#
lint: repository-metadata
	# Ensure that the shipped pkglint_whitelist.txt is self-consistent.
	# That is, when sorting it in the C locale and diffing the output
	# against itself, we should see no differences.
	# (This catches whitelist putbacks that aren't correctly sorted)
	env LC_ALL=C sort pkglint_whitelist.txt | diff - pkglint_whitelist.txt
	@echo "Running pkglint"
	@rm -rf $(PDIR)/pkglint-cache
	@rm -f $(PDIR)/pkglint-out*
	@if [ -n "$(PKGLINT_REF_REPO)" ]; then				\
		$(PKGLINT) -c $(PDIR)/pkglint-cache 			\
			-r $(PKGLINT_REF_REPO) -l file://$(PKGDEST)/repo; \
	fi
	-@if [ -z "$(PKGLINT_REF_REPO)" ]; then 			\
		( $(PKGLINT) -c $(PDIR)/pkglint-cache 			\
			-l file://$(PKGDEST)/repo > /dev/null ) 2>&1 |	\
			sed -e 's/@[0-9TZ.:,-]*//g' |			\
			env LC_ALL=C sort |				\
			diff pkglint_whitelist.txt -			\
			> $(PDIR)/pkglint-out-diff.txt; 		\
									\
		egrep "^< WARNING |^< ERROR |^< CRITICAL " 		\
			$(PDIR)/pkglint-out-diff.txt 			\
			> $(PDIR)/pkglint-out-fixes.txt; 		\
 		egrep -v "^< WARNING |^< ERROR |^< CRITICAL "		\
			$(PDIR)/pkglint-out-diff.txt 			\
			| sed -e '/^[0-9,]*[ad][0-9,]*$$/d' 		\
			> $(PDIR)/pkglint-out-breakage.txt; 		\
	fi
	@if [ -s $(PDIR)/pkglint-out-fixes.txt ]; then 			\
		echo "";						\
		echo "The following pkglint errors are now fixed:"; 	\
		cat $(PDIR)/pkglint-out-fixes.txt; 			\
		echo "pkglint-whitelist.txt should be updated";		\
	fi
	@if [ -s $(PDIR)/pkglint-out-breakage.txt ]; then 		\
		echo "";						\
		echo "New pkglint errors detected:";			\
		cat $(PDIR)/pkglint-out-breakage.txt; 			\
		exit 1; 						\
	fi

# A little bit of Python is the easiest way to generate the commandline options
# to pkgsend generate.
TARGETS.cmd       = \
	$(PKGMOGRIFY) -O /dev/null transforms/find-links $(MOGRIFESTS) | \
		python -c 'import os, sys; print " ".join(("--target " + os.path.normpath(os.path.join(os.path.dirname(p), t)) for p, t in (l.strip().split() for l in sys.stdin.readlines())))'

# Create a pseudo-manifest of the proto area
$(PDIR)/protomanifest: FRC transforms/compare-strip $(PDIR)
	$(PKGSEND) generate $(TARGETS.cmd:sh) $(PKGROOT) | \
		$(PKGMOGRIFY) $(PKGMOG_DEFINES) transforms/compare-strip \
		/dev/stdin > $@

# Create a pseudo-manifest of the combined packages
$(PDIR)/pkgmanifest: $(MOGRIFESTS) transforms/compare-strip $(PDIR)
	$(PKGMOGRIFY) $(PKGMOG_DEFINES) transforms/compare-strip $(MOGRIFESTS) > $@

FRC:
