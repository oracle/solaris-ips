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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

KSH=/usr/bin/ksh
PYTHON=/usr/bin/python

TEST_LOG:sh=echo /tmp/$$.ipkg-test.log
test-verbose := TEST_DEBUG=-x
test-verbose := TEST_LOG=/dev/stdout

# Invoke all known modules with tests.
# XXX Invoke the bundle tests.
test: api-test cli-test leak-test

api-test:
	@echo "Logging to $(TEST_LOG)"
	$(TEST_DEBUG) $(PYTHON) api-complete.py >> $(TEST_LOG)

#
# If we keep the dependencies sane, then orthogonal sets
# of tests can be run in parallel.
#
cli-test:
	@echo "Logging to $(TEST_LOG)"
	$(TEST_DEBUG) $(PYTHON) cli-complete.py >> $(TEST_LOG)

leak-test: cli-test
	# workaround: memleaks doesn't run cleanly at this time
	-$(KSH) $(TEST_DEBUG) memleaks.ksh >> $(TEST_LOG)


test-verbose: test

clean:
	rm -f *.pyc

