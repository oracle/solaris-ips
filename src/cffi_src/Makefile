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
# Copyright (c) 2024, 2025, Oracle and/or its affiliates.
#

include ../Makefile.constants

EXTENSIONS = _arch _sha512_t _sysattr _syscallat

all: $(EXTENSIONS:=.cpython-39.so) $(EXTENSIONS:=.cpython-311.so)

%-39.so := PYTHON=$(PYTHON39)
%-311.so := PYTHON=$(PYTHON311)

_arch.cpython-%.so: build_arch.py
	CC=$(GCC) $(PYTHON) $^

_sha512_t.cpython-%.so: build_sha512_t.py
	CC=$(GCC) $(PYTHON) $^

_sysattr.cpython-%.so: build_sysattr.py
	CC=$(GCC) $(PYTHON) $^

_syscallat.cpython-%.so: build_syscallat.py
	CC=$(GCC) $(PYTHON) $^

ROOT39EXTENSIONS = $(EXTENSIONS:%=$(ROOTPY39PKG)/%.cpython-39.so)
ROOT311EXTENSIONS = $(EXTENSIONS:%=$(ROOTPY311PKG)/%.cpython-311.so)

install: $(ROOT39EXTENSIONS) $(ROOT311EXTENSIONS)

$(ROOTPY39PKG)/%.so: %.so
	$(INS.file)

$(ROOTPY311PKG)/%.so: %.so
	$(INS.file)

check:

clint: all
	$(LINT.c) _arch.c
	$(LINT.c) _syscallat.c
	$(LINT.c) -lnvpair _sysattr.c
	$(LINT.c) -lmd _sha512_t.c

lint: clint

clean:
	rm -f $(EXTENSIONS:=.*)

clobber: clean
