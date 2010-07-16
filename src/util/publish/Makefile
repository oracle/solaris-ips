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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#
ARCH:sh=	uname -p
REPO=http://localhost:10000
ON_REPO=http://localhost:20000
INSTALL_REPO=http://localhost:20001
X_REPO=http://localhost:20002
MERGEDIR=../../../proto/merge
SETPUBLISHERDIR=../../../proto/set-publisher
PROTO=../../../proto/root_$(ARCH)
PYTHONPATH=$(PROTO)/usr/lib/python2.6/vendor-packages
SPARC_REPO=http://localhost:10001
i386_REPO=http://localhost:10002
EXTRA_ARGS=
JUST_THESE_PKGS=


$(MERGEDIR):
	mkdir -p $(MERGEDIR)

$(SETPUBLISHERDIR):
	mkdir -p $(SETPUBLISHERDIR)

# add other targets as needed; -r flag recursively expands
# incorporations
# be sure to clobber between publish targets
# note that multiple invocations of merge can be done
# and followed by a single publish

merge:
	PYTHONPATH=$(PYTHONPATH) ./merge.py $(EXTRA_ARGS) -r -d $(MERGEDIR) -v sparc,$(SPARC_REPO) -v i386,$(i386_REPO) arch $(JUST_THESE_PKGS)

publish: $(MERGEDIR)
	for var in `(cd $(MERGEDIR); echo * )` ;\
	do PYTHONPATH=$(PYTHONPATH) ./pkg_publish $(MERGEDIR)/$$var $(REPO); done

publish_setpublisher: $(SETPUBLISHERDIR)
	PYTHONPATH=$(PYTHONPATH) ./set-publisher.sh -b $(BUILDID) \
		-d $(SETPUBLISHERDIR) -p $(REPO) \
		$(ON_REPO) \
		$(INSTALL_REPO) \
		$(X_REPO)

clean:

clobber:
	rm -rf $(MERGEDIR) $(SETPUBLISHERDIR)
