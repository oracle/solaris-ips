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
# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.
#

include ../Makefile.buildnum

ARCH:sh=	uname -p
REPO=http://localhost:10000
MERGEDIR=../../../proto/merge
SETPUBLISHERDIR=../../../proto/set-publisher
PROTO=../../../proto/root_$(ARCH)
PYTHONPATH=$(PROTO)/usr/lib/python2.6/vendor-packages
SPARC_REPO=http://localhost:10001
i386_REPO=http://localhost:10002
EXTRA_ARGS=
JUST_THESE_PKGS=
EXCLUDE_THESE_PKGS=

ON_REPO=http://localhost:20000
INSTALL_REPO=http://localhost:20001
X_REPO=http://localhost:20002
IPS_REPO=http://localhost:20003
VPANELS_REPO=http://localhost:20004
USERLAND_REPO=http://localhost:20005
L10N_REPO=http://localhost:20006
DESKTOP_REPO=http://localhost:20007
CDE_REPO=http://localhost:20008
CACAO_REPO=http://localhost:20010
CNS_REPO=http://localhost:20011
JDMK_REPO=http://localhost:20012
NVIDIA_REPO=http://localhost:20013
DEVPRO_REPO=http://localhost:20014
SOLARIS_RE_REPO=http://localhost:20015
MAN_REPO=http://localhost:20016
LDOMS_REPO=http://localhost:20017
SIC_TEAM_REPO=http://localhost:20018
SUNVTS_REPO=http://localhost:20019
JAVA_REPO=http://localhost:20020

INPUT_REPOS = \
    $(ON_REPO) \
    $(INSTALL_REPO) \
    $(X_REPO) \
    $(IPS_REPO) \
    $(VPANELS_REPO) \
    $(USERLAND_REPO) \
    $(L10N_REPO) \
    $(DESKTOP_REPO) \
    $(CDE_REPO) \
    $(CACAO_REPO) \
    $(CNS_REPO) \
    $(JDMK_REPO) \
    $(NVIDIA_REPO) \
    $(DEVPRO_REPO) \
    $(SOLARIS_RE_REPO) \
    $(MAN_REPO) \
    $(LDOMS_REPO) \
    $(SIC_TEAM_REPO) \
    $(SUNVTS_REPO) \
    $(JAVA_REPO)

ON_EXTRA_REPO=http://localhost:30000

ON_EXTRA_CONTENT = \
    driver/management/bmc \
    driver/management/ipmi \
    driver/storage/ifp \
    driver/storage/isp \
    shell/ksh88

$(MERGEDIR):
	mkdir -p $(MERGEDIR)

$(SETPUBLISHERDIR):
	mkdir -p $(SETPUBLISHERDIR)

#
# add other targets as needed; -r flag recursively expands
# incorporations
# be sure to clobber between publish targets
# note that multiple invocations of merge can be done
# and followed by a single publish
#
merge:
	PATH=$(PROTO)/usr/bin:${PATH} PYTHONPATH=$(PYTHONPATH) ./merge.py \
	    $(EXTRA_ARGS) -r -d $(MERGEDIR) \
	    -v sparc,$(SPARC_REPO) -v i386,$(i386_REPO) arch $(JUST_THESE_PKGS)

clobber_merge:
	rm -fr $(MERGEDIR)

publish: $(MERGEDIR)
	for var in `(cd $(MERGEDIR); echo * )`; do \
		PATH=$(PROTO)/usr/bin:${PATH} PYTHONPATH=$(PYTHONPATH) \
		    ./pkg_publish $(MERGEDIR)/$$var $(REPO); \
	done
	pkgrepo -s $(REPO) refresh

publish_setpublisher: $(SETPUBLISHERDIR)
	PATH=$(PROTO)/usr/bin:${PATH} PYTHONPATH=$(PYTHONPATH) \
	    ./set-publisher.sh $(BRANCHID:%=-b %) -d $(SETPUBLISHERDIR) \
	    $(JUST_THESE_PKGS:%=-j %) $(EXCLUDE_THESE_PKGS:%=-x %) -p $(REPO) \
	    $(INPUT_REPOS)

publish_setpublisher-extra: $(SETPUBLISHERDIR)
	INPUT_REPOS="$(ON_EXTRA_REPO)" JUST_THESE_PKGS="$(ON_EXTRA_CONTENT)" \
	    $(MAKE) publish_setpublisher

clobber_setpublisher:
	rm -fr $(SETPUBLISHERDIR)

clean:

clobber: clobber_merge clobber_setpublisher
