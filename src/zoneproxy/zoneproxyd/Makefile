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
# Copyright (c) 2010, 2012, Oracle and/or its affiliates. All rights reserved.
#

PROG =	zoneproxyd
SRCS =	zoneproxyd.c
HDR =	zoneproxy_impl.h
OBJS =	$(SRCS:%.c=%.o)

include ../Makefile.constants

ROOTHDIR =	$(PROTO_AREA)/usr/include
ROOTHDR =	$(ROOTHDIR)/$(HDR)
CLOBBERFILES +=	$(ROOTHDR)

LDLIBS +=	-lcontract -lsocket -lumem -lscf
CPPFLAGS +=	-D_REENTRANT -D_FILE_OFFSET_BITS=64
CFLAGS +=	-mt
LINTFLAGS +=	-erroff=E_SEC_CREAT_WITHOUT_EXCL -U__PRAGMA_REDEFINE_EXTNAME

.KEEP_STATE:

$(ROOTHDR): $(ROOTHDIR) $(HDR)
	$(INSTALL) -m 0644 -d $(ROOTHDIR) -f $(HDR)

$(ROOTHDIR):
	$(MKDIR) -m 0755 $@

all:	$(PROG)

install: $(ZONES_PROG) $(ROOTHDR)

lint: lint_PROG
