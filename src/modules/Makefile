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
INSTALL:sh =   echo /opt/onbld/bin/$(uname -p)/stash file -v
GSED =	/usr/gnu/bin/sed

PROTO_AREA:sh =	echo $(dirname $(dirname $(pwd)))/proto/root_$(uname -p)
PY39DIRVP= $(PROTO_AREA)/usr/lib/python3.9/vendor-packages/pkg
PY311DIRVP= $(PROTO_AREA)/usr/lib/python3.11/vendor-packages/pkg

EXTENSIONS = actions/_actions actions/_common _varcet _misc solver elf

PYFILES = \
	*.py \
	actions/*.py \
	bundle/*.py \
	client/*.py \
	client/linkedimage/*.py \
	client/transport/*.py \
	file_layout/*.py \
	flavor/*.py \
	lint/*.py \
	no_site_packages/*.py \
	portable/*.py \
	publish/*.py \
	server/*.py

all: $(EXTENSIONS:=.cpython-39.so) $(EXTENSIONS:=.cpython-311.so)

PYTHON39CFLAGS:sh =	python3.9-config --cflags
PYTHON311CFLAGS:sh =	python3.11-config --cflags

PYTHON39LDFLAGS:sh =	python3.9-config --ldflags
PYTHON311LDFLAGS:sh =	python3.11-config --ldflags

%-39.so := PYTHONCFLAGS=$(PYTHON39CFLAGS)
%-311.so := PYTHONCFLAGS=$(PYTHON311CFLAGS)

%-39.so := PYTHONLDFLAGS=$(PYTHON39LDFLAGS) -shared -zstrip-class=nonalloc
%-311.so := PYTHONLDFLAGS=$(PYTHON311LDFLAGS) -shared -zstrip-class=nonalloc

_misc.cpython-%.so: _misc.c
	gcc $^ $(PYTHONCFLAGS) $(PYTHONLDFLAGS) -o $@

_varcet.cpython-%.so: _varcet.c
	gcc $^ $(PYTHONCFLAGS) $(PYTHONLDFLAGS) -o $@

actions/_actions.cpython-%.so: actions/_actions.c
	gcc $^ $(PYTHONCFLAGS) $(PYTHONLDFLAGS) -o $@

actions/_common.cpython-%.so: actions/_common.c
	gcc $^ $(PYTHONCFLAGS) $(PYTHONLDFLAGS) -o $@

elf.cpython-%.so: elf.c elfextract.c liblist.c
	gcc $^ $(PYTHONCFLAGS) -I. -lelf -lmd $(PYTHONLDFLAGS) -o $@

solver.cpython-%.so: solver/solver.c solver/py_solver.c
	gcc $^ -D_FILE_OFFSET_BITS=64 -Wno-return-type -Wno-strict-aliasing -Wno-unused-function -Wno-unused-variable $(PYTHONCFLAGS) -ztext -lm -lc $(PYTHONLDFLAGS) -o $@

# PRIVATE_BUILD set in the environment tells us to not strip
# the prefix of proto area paths recorded in the .pyc files.
$(PRIVATE_BUILD)PYCOMPILE_FLAGS = -s $(PROTO_AREA)

install: all
	@for file in $(PYFILES); do \
		$(INSTALL) -Cp $$file $(PY39DIRVP)/$$file; \
	done
	@for file in $(PYFILES); do \
		$(INSTALL) -Cp $$file $(PY311DIRVP)/$$file; \
	done

	@# substitute VERSION with mercurial revision in pkg/__init__.py
	@hg_revision=`hg id -i`; \
	echo "doing version substitution: $$hg_revision"; \
	$(GSED) -i "s|VERSION = \"unknown\"|VERSION = \"$$hg_revision\"|" $(PY39DIRVP)/__init__.py; \
	$(GSED) -i "s|VERSION = \"unknown\"|VERSION = \"$$hg_revision\"|" $(PY311DIRVP)/__init__.py

	$(PYTHON39) -m compileall $(PYCOMPILE_FLAGS) -j8 --invalidation-mode=checked-hash $(PY39DIRVP)
	$(PYTHON311) -m compileall $(PYCOMPILE_FLAGS) -j8 --invalidation-mode=checked-hash $(PY311DIRVP)

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
CLINT_INCLUDES = -I/usr/include/python3.9 -I.

clint: all
	$(CLINT) $(CLINT_FLAGS) $(CLINT_INCLUDES) -lelf -lmd elf.c elfextract.c liblist.c
	$(CLINT) $(CLINT_FLAGS) $(CLINT_INCLUDES) actions/_actions.c
	$(CLINT) $(CLINT_FLAGS) $(CLINT_INCLUDES) actions/_common.c
	$(CLINT) $(CLINT_FLAGS) $(CLINT_INCLUDES) _varcet.c
	$(CLINT) $(CLINT_FLAGS) $(CLINT_INCLUDES) _misc.c
	$(CLINT) $(CLINT_FLAGS) $(CLINT_INCLUDES) solver/solver.c solver/py_solver.c

lint: clint

clean:
	rm -f $(EXTENSIONS:=.cpython-39.so) $(EXTENSIONS:=.cpython-311.so)

clobber: clean
