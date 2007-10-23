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

ELFSRCS = elf.c liblist.c elfextract.c
ELFOBJS = $(ELFSRCS:%.c=%.o)

PYTHONINC = /usr/include/python2.4

INC = -I$(PYTHONINC) -I.
CFLAGS = -g -Kpic -v $(INC)
LIBS = -lelf -lmd
LDFLAGS = -G

LINTFLAGS += -u -axms -erroff=E_NAME_DEF_NOT_USED2

gcc := CC = gcc
gcc := CFLAGS = -Wall -fpic $(INC)
gcc := LDFLAGS = --shared

#
# 'arch' can be built large files aware, which seems to be what python
# would like the best.
#
# The elf stuff seems less reasonable, since libelf consumers must be 
# built non-LF aware (sigh... fist shaking).
#
LF = -D_FILE_OFFSET_BITS=64
$(ARCHMODULE) := CFLAGS += $(LF)

all: $(ARCHMODULE) $(ELFMODULE)

gcc: all

lint:
	$(LINT) $(LINTFLAGS) $(LF) $(LIBS) $(INC) $(ARCHSRCS)
	$(LINT) $(LINTFLAGS) $(LIBS) $(INC) $(ELFSRCS)

clean:
	rm -f $(ARCHOBJS) $(ELFOBJS)

clobber: clean
	rm -f $(ARCHMODULE) $(ELFMODULE)

$(ARCHMODULE): $(ARCHOBJS)
	$(CC) $(LDFLAGS) $(LIBS) $(ARCHOBJS) -o $@

$(ELFMODULE): $(ELFOBJS)
	$(CC) $(LDFLAGS) $(LIBS) $(ELFOBJS) -o $@

%.o : %.c
	$(CC) -c $(CFLAGS) $(LF_FLAGS) $<
