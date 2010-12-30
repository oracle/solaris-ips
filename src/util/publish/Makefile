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
# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.
#

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

ON_REPO=http://localhost:20000
INSTALL_REPO=http://localhost:20001
X_REPO=http://localhost:20002
IPS_REPO=http://localhost:20003
VPANELS_REPO=http://localhost:20004
USERLAND_REPO=http://localhost:20005
L10N_REPO=http://localhost:20006

INPUT_REPOS = \
    $(ON_REPO) \
    $(INSTALL_REPO) \
    $(X_REPO) \
    $(IPS_REPO) \
    $(VPANELS_REPO) \
    $(USERLAND_REPO) \
    $(L10N_REPO)

ON_EXTRA_REPO=http://localhost:30000
L10N_EXTRA_REPO=http://localhost:30006

ON_EXTRA_CONTENT = \
    driver/management/bmc \
    driver/storage/ifp \
    driver/storage/isp \
    driver/storage/qus \
    shell/ksh88 \
    system/header/header-ifp

L10N_EXTRA_CONTENT = \
    system/font/truetype/fonts-core \
    system/input-method/iiim/atok \
    system/input-method/iiim/wnn

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
	    ./set-publisher.sh $(BUILDID:%=-b %) -d $(SETPUBLISHERDIR) \
	    $(JUST_THESE_PKGS:%=-j %) -p $(REPO) $(INPUT_REPOS)

publish_setpublisher-extra: $(SETPUBLISHERDIR)
	INPUT_REPOS="$(ON_EXTRA_REPO) $(L10N_EXTRA_REPO)" \
	    JUST_THESE_PKGS="$(ON_EXTRA_CONTENT) $(L10N_EXTRA_CONTENT)" \
	    $(MAKE) publish_setpublisher

clobber_setpublisher:
	rm -fr $(SETPUBLISHERDIR)

clean:

clobber: clobber_merge clobber_setpublisher
