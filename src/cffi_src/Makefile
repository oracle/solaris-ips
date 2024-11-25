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
# Copyright (c) 2024, Oracle and/or its affiliates.
#

PYTHON39 = /usr/bin/python3.9
PYTHON311 = /usr/bin/python3.11
INSTALL:sh =	echo /opt/onbld/bin/$(uname -p)/stash file -v

PROTO_AREA:sh =	echo $(dirname $(dirname $(pwd)))/proto/root_$(uname -p)
PY39DIRVP= $(PROTO_AREA)/usr/lib/python3.9/vendor-packages/pkg
PY311DIRVP= $(PROTO_AREA)/usr/lib/python3.11/vendor-packages/pkg

EXTENSIONS = _arch _sha512_t _sysattr _syscallat

all: $(EXTENSIONS:=.cpython-39.so) $(EXTENSIONS:=.cpython-311.so)

%-39.so := PYTHON=$(PYTHON39)
%-311.so := PYTHON=$(PYTHON311)

_arch.cpython-%.so: build_arch.py
	$(PYTHON) $^

_sha512_t.cpython-%.so: build_sha512_t.py
	$(PYTHON) $^

_sysattr.cpython-%.so: build_sysattr.py
	$(PYTHON) $^

_syscallat.cpython-%.so: build_syscallat.py
	$(PYTHON) $^

install: all
	@for extension in $(EXTENSIONS:=.cpython-39.so); do \
		$(INSTALL) $$extension $(PY39DIRVP)/$$extension; \
	done;
	@for extension in $(EXTENSIONS:=.cpython-311.so); do \
		$(INSTALL) $$extension $(PY311DIRVP)/$$extension; \
	done;

check:

# Allow for CLINT variable being set from the environment.
$(LINT)CLINT = lint
CLINT = $(LINT)

CLINT_FLAGS = -m64 -u -axms -erroff=E_NAME_DEF_NOT_USED2
CLINT_INCLUDES = -I/usr/include/python3.11

clint: all
	$(CLINT) $(CLINT_FLAGS) $(CLINT_INCLUDES) _arch.c
	$(CLINT) $(CLINT_FLAGS) $(CLINT_INCLUDES) _syscallat.c
	$(CLINT) $(CLINT_FLAGS) $(CLINT_INCLUDES) -lnvpair _sysattr.c
	$(CLINT) $(CLINT_FLAGS) $(CLINT_INCLUDES) -lmd _sha512_t.c

lint: clint

clean:
	rm -f $(EXTENSIONS:=.*)

clobber: clean
