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
# Copyright (c) 2016, 2024, Oracle and/or its affiliates.
#

EXEC =	certgen
SRCS =	mkcert.c
OBJS =	$(SRCS:%.c=%.o)
CERTS = cust_key.pem cust_cert.pem
CLEANFILES = $(OBJS) $(EXEC) $(CERTS)

CC = cc
CFLAGS = -D CUSTOM_EXT
LDLIBS = -lcrypto

all:	install

install: $(EXEC)

check:

clean:
	rm -rf $(CLEANFILES)

clobber: clean

$(EXEC): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(LDLIBS) $^

