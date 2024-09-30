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
# Copyright (c) 2010, 2023, Oracle and/or its affiliates.
#

PKGVERS_BUILTON   = 5.11
MINORNUM          = 11
UPDATENUM         = 4
#
# The SRUNUM will need to be reset once the final trunk build for
# the delivery from trunk has been delivered.
#
SRUNUM            = 78
ORDER             = 0
#
# In the normal case the PLATNUM should be 0, however when
# producing an SRU build from trunk it should be set to 1
#
PLATNUM           = 0
PKGVERS_COMPONENT = $(MINORNUM).$(UPDATENUM)
#
# Generate the BUILDID based upon the tag in the gate.
# Need to remove the respin number from the tag.
#
BUILDID.cmd       = \
	hg tags | \
	awk '$$1 ~ /^st[0-9]+/ {exit} \
             END { \
                 build_label=substr($$1, 3); \
                 split(build_label, pieces, "[.]"); \
                 print pieces[1] + 0 \
                 }'
BUILDID           = $(BUILDID.cmd:sh)
NIGHTLYID:sh      = hg parents --template '{rev}'
CHANGESET:sh      = hg id -i
PKGVERS_BRANCH    = \
	$(MINORNUM).$(UPDATENUM).$(SRUNUM).$(ORDER).$(PLATNUM).$(BUILDID).$(NIGHTLYID)
PKGVERS           = $(PKGVERS_COMPONENT)-$(PKGVERS_BRANCH)
ARCH              = $(TARGET_ARCH:-%=%)
REV:sh            = date +%Y.%m.%d.%H.%M.%S

PDIR              = pkgtmp
PWD:sh            = pwd
PKGDEST           = $(PWD)/../../packages/$(ARCH)
PKGROOT           = $(PWD)/../../proto/root_$(ARCH)

PKGPUBLISHER      = nightly
PKGPUBLISHER_LOCALIZABLE      = pkg5-localizable

POUND_SIGN:sh     = echo \\043
PUBLISHALL        = $(POUND_SIGN)
# This won't work if we obsolete a package in an update build, but shouldn't be
# necessary after we stop publishing duplicate packages.
MANIFESTS.cmd     = \
	cd manifests; \
	buildnum=$(BUILDID); \
	m=$$($(PKGMOGRIFY) -O /dev/null *.p5m ../transforms/nopublish); \
	echo "$$m" | while read name build; do \
		[[ $$build -ge $${buildnum%%.*} ]] && echo $$name; \
	done | sed -e 's/:/\\:/g'; \
	exit 0
MANIFESTS         = $(MANIFESTS.cmd:sh)
ALL_MANIFESTS:sh  = \
	cd manifests; \
	print *.p5m | sed -e 's/:/\\:/g'; \
	exit 0
$(PUBLISHALL)MANIFESTS      = $(ALL_MANIFESTS)

# PKGCMDENV needs to specify the interpreter used
# so that the shell ignores the one specified in the
# file because those suppress the use of non-default
# environments which are actually used as part of the
# build. Bit of a smoke and mirrors.
PYTHON39	  = python3.9
PY39DIR		  = usr/lib/$(PYTHON39)
PY39DIRVP	  = $(PY39DIR)/vendor-packages

PYTHON311	  = python3.11
PY311DIR	  = usr/lib/$(PYTHON311)
PY311DIRVP	  = $(PY311DIR)/vendor-packages

PYDIR		  = usr/lib/$(PYTHON39)
PYDIRVP		  = $(PYDIR)/vendor-packages
PKGCMDENV         = \
	PATH=$(PKGROOT)/usr/bin:/usr/sbin:/usr/bin \
	PYTHONPATH=$(PKGROOT)/$(PYDIRVP) $(PYTHON39) $(PKGROOT)/usr/bin/
PKG               = $(PKGCMDENV)/pkg
PKGDEPEND         = $(PKGCMDENV)/pkgdepend
PKGDIFF           = $(PKGCMDENV)/pkgdiff
PKGFMT            = $(PKGCMDENV)/pkgfmt
PKGLINT           = $(PKGCMDENV)/pkglint
PKGMOGRIFY        = $(PKGCMDENV)/pkgmogrify
PKGREPO           = $(PKGCMDENV)/pkgrepo
PKGSEND           = $(PKGCMDENV)/pkgsend
MOGRIFESTS        = $(MANIFESTS:%.p5m=$(PDIR)/%.mog)
ALL_MOGRIFESTS    = $(ALL_MANIFESTS:%.p5m=$(PDIR)/%.mog)
PUBLIFESTS        = $(MANIFESTS:%.p5m=$(PDIR)/%.pub)
DEPENDED          = $(MANIFESTS:%.p5m=$(PDIR)/%.dep)
INCORP            = consolidation\:ips\:ips-incorporation

PM_TRANSFORMS     = defaults

i386_DEFINES      = \
	i386_ONLY=''    \
	sparc_ONLY=$(POUND_SIGN)

sparc_DEFINES     = \
	i386_ONLY=$(POUND_SIGN) \
	sparc_ONLY=''

ARCH_DEFINES      = $($(ARCH)_DEFINES)

PKGMOG_DEFVALS    = \
	ARCH=$(ARCH) \
	PKGVERS_COMPONENT=$(PKGVERS_COMPONENT) \
	PKGVERS_BUILTON=$(PKGVERS_BUILTON) \
	PKGVERS_BRANCH=$(PKGVERS_BRANCH) \
	PKGVERS=$(PKGVERS) \
	REV=$(REV) \
	PYDIR=$(PYDIR) \
	PYDIRVP=$(PYDIRVP) \
	PY39DIR=$(PY39DIR) \
	PY39DIRVP=$(PY39DIRVP) \
	PY311DIR=$(PY311DIR) \
	PY311DIRVP=$(PY311DIRVP) \
	CHANGESET=$(CHANGESET) \
	PKGPUBLISHER_LOCALIZABLE=$(PKGPUBLISHER_LOCALIZABLE)
PKGMOG_DEFINES    = $(PKGMOG_DEFVALS:%=-D %)
PKGMOG_DEFINES    += $(ARCH_DEFINES:%=-D %)

all: $(MOGRIFESTS)
install: lint

clean:
	rm -rf $(PDIR)

clobber: clean
	rm -rf $(PKGDEST) Makefile.link

pkgfmt:
	$(PKGFMT) -c manifests/*.p5m

$(PDIR):
	mkdir -p $@

# Finalize the repository
repository-metadata: pkgfmt publish-pkgs
	$(PKGREPO) -s $(PKGDEST)/repo refresh

publish-pkgs: $(PKGDEST)/repo .WAIT $(PUBLIFESTS)

# Initialize the repository
$(PKGDEST)/repo:
	$(PKGREPO) create $@
	$(PKGREPO) -s $@ set publisher/prefix=$(PKGPUBLISHER)
	$(PKGREPO) -s $@ add-publisher $(PKGPUBLISHER_LOCALIZABLE)

# Special rule for creating the incorporation.  Note that the incorporation
# looks at all manifests, not just the ones listed in $(MANIFESTS).  This is
# because we need to incorporate obsolete and renamed packages, even if we
# choose not to continue republishing them.
$(PDIR)/$(INCORP).mog: manifests/$(INCORP).p5m $(PDIR) \
	$(ALL_MOGRIFESTS:$(PDIR)/$(INCORP).mog=)
	$(PKGMOGRIFY) -I transforms defaults incorp2 manifests/$(INCORP).p5m | \
		$(PKGMOGRIFY) $(PKGMOG_DEFINES) -D DEPTYPE=incorporate \
		-I transforms -O $@ /dev/stdin incorp \
		$(ALL_MOGRIFESTS:$(PDIR)/$(INCORP).mog=)

# The main mogrification rule
$(PDIR)/%.mog: manifests/%.p5m $(PM_TRANSFORMS:%=transforms/%) $(PDIR) \
	$(PM_TRANSFORMS:%=transforms/%)
	$(PKGMOGRIFY) $(PKGMOG_DEFINES) -I transforms -O $@ $< $(PM_TRANSFORMS)

# The main dependency generation rule
$(PDIR)/%.dep: $(PDIR)/%.mog
	$(PKGDEPEND) generate -m -d $(PKGROOT) $< > $@

# Resolve all dependencies at once, providing a single target that publication
# can use.
$(PDIR)/.resolved: $(DEPENDED)
	$(PKGDEPEND) resolve -e external_deps.txt -m $(DEPENDED)
	touch $@

# The final run of pkgmogrify to strip those versions that
# do not matter.
$(PDIR)/%.strip: $(PDIR)/.resolved
	$(PKGMOGRIFY) -I transforms -O $@ strip_versions $(@:%.strip=%.dep.res)

# The main publication rule
$(PDIR)/%.pub: $(PDIR)/%.strip $(PKGDEST)/repo
	$(PKGSEND) -s file://$(PKGDEST)/repo publish -d $(PKGROOT) \
		-d license_files -T \*.py --fmri-in-manifest --no-index \
		--no-catalog $(@:%.pub=%.strip)
	touch $@

# Compare the proto area with the package manifests; if they've got different
# filesets, complain
check: $(PDIR)/protomanifest $(PDIR)/pkgmanifest
	$(PKGDIFF) $(PDIR)/protomanifest $(PDIR)/pkgmanifest

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
# To tell pkglint to bypass any potential missing dependencies during
# the lint run, please edit external_deps.txt
lint: repository-metadata $(PDIR)
	@sed -e "s#/usr/share/lib/pkg/opensolaris.org.sections#$(PKGROOT)&#" \
		< ips-pkglintrc > $(PDIR)/pkglintrc

	@# Ensure that the shipped pkglint_whitelist.txt is self-consistent.
	@# That is, when sorting it in the C locale and diffing the output
	@# against itself, we should see no differences.
	@# (This catches whitelist putbacks that aren't correctly sorted)
	@env LC_ALL=C sort pkglint_whitelist.txt | diff - pkglint_whitelist.txt
	@echo "Running pkglint"
	@rm -rf $(PDIR)/pkglint-cache
	@rm -f $(PDIR)/pkglint-out*
	@if [ -n "$(PKGLINT_REF_REPO)" ]; then				\
		env LC_ALL=C $(PKGLINT) -f $(PDIR)/pkglintrc \
			-c $(PDIR)/pkglint-cache \
			-r $(PKGLINT_REF_REPO) -l file://$(PKGDEST)/repo; \
	fi
	-@if [ -z "$(PKGLINT_REF_REPO)" ]; then				\
		cat external_deps_fragment.pkglintrc >> $(PDIR)/pkglintrc; \
		cat external_deps.txt >> $(PDIR)/pkglintrc;	\
		( $(PKGLINT) -c $(PDIR)/pkglint-cache			\
			-f $(PDIR)/pkglintrc				\
			-l file://$(PKGDEST)/repo > /dev/null ) 2>&1 |	\
			sed -e 's/@[0-9TZ.:,-]*//g' |			\
			env LC_ALL=C sort |				\
			diff pkglint_whitelist.txt -			\
			| grep -v pkglint.manifest007			\
			| grep -v pkglint.action008			\
			> $(PDIR)/pkglint-out-diff.txt;			\
									\
		egrep "^< WARNING |^< ERROR |^< CRITICAL "		\
			$(PDIR)/pkglint-out-diff.txt			\
			> $(PDIR)/pkglint-out-fixes.txt;		\
		egrep -v "^< WARNING |^< ERROR |^< CRITICAL "		\
			$(PDIR)/pkglint-out-diff.txt			\
			| sed -e '/^[0-9,]*[ad][0-9,]*$$/d'		\
			> $(PDIR)/pkglint-out-breakage.txt;		\
	fi
	@if [ -s $(PDIR)/pkglint-out-fixes.txt ]; then			\
		echo "";						\
		echo "The following pkglint errors are now fixed:";	\
		cat $(PDIR)/pkglint-out-fixes.txt;			\
		echo "pkglint-whitelist.txt should be updated";		\
	fi
	@if [ -s $(PDIR)/pkglint-out-breakage.txt ]; then		\
		echo "";						\
		echo "New pkglint errors detected:";			\
		cat $(PDIR)/pkglint-out-breakage.txt;			\
		exit 1;						\
	fi

# A little bit of Python is the easiest way to generate the commandline options
# to pkgsend generate.
TARGETS.cmd       = \
	$(PKGMOGRIFY) -O /dev/null transforms/find-links $(MOGRIFESTS) | \
		python -c 'import os, sys; print(" ".join(("--target " + os.path.normpath(os.path.join(os.path.dirname(p), t)) for p, t in (l.strip().split() for l in sys.stdin.readlines()))))'

# Create a pseudo-manifest of the proto area
$(PDIR)/protomanifest: FRC transforms/compare-strip $(PDIR)
	$(PKGSEND) generate $(TARGETS.cmd:sh) $(PKGROOT) | \
		$(PKGMOGRIFY) $(PKGMOG_DEFINES) transforms/compare-strip \
		/dev/stdin > $@

# Create a pseudo-manifest of the combined packages
$(PDIR)/pkgmanifest: $(MOGRIFESTS) transforms/compare-strip $(PDIR)
	$(PKGMOGRIFY) $(PKGMOG_DEFINES) transforms/compare-strip $(MOGRIFESTS) \
		> $@

FRC:
