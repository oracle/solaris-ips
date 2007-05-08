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

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

ARCHMODULE = arch.so

ARCHSRCS = arch.c
ARCHOBJS = $(ARCHSRCS:%.c=%.o)

ELFMODULE = elf.so

ELFSRCS = elf.c
ELFOBJS = $(ELFSRCS:%.c=%.o)

PYTHONINC = /usr/include/python2.4

CFLAGS += -I$(PYTHONINC)

all: $(ARCHMODULE) $(ELFMODULE)

lint:
	$(LINT) -c $(CFLAGS) $(ARCHSRCS)
	$(LINT) -c $(CFLAGS) $(ELFSRCS)

$(ARCHMODULE): $(ARCHOBJS)
	$(CC) -G $(ARCHOBJS) -o $@

$(ELFMODULE): $(ELFOBJS)
	$(CC) -G $(ELFOBJS) -o $@

%.o : %.c
	$(CC) -c -Kpic $(CFLAGS) $<
