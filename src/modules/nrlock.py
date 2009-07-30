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

"""Interface and implementation for Non-Reentrant locks.  Derived from
RLocks (which are reentrant locks).  The default Python base locking
type, threading.Lock(), is non-reentrant but it doesn't support any
operations other than aquire() and release(), and we'd like to be able
to support things like RLocks._is_owned() so that we can "assert" lock
ownership assumptions in our code."""

import threading

# Rename some stuff so "from pkg.nrlock import *" is safe
__all__ = [ 'NRLock' ]

def NRLock(*args, **kwargs):
    return _NRLock(*args, **kwargs)

class _NRLock(threading._RLock):

    def __init__(self, verbose=None):
        self.__rlock = threading.RLock(verbose)

    def __repr__(self):
        self.__rlock.__repr__()

    def acquire(self, blocking=1):
        assert not self.__rlock._is_owned(), "recursive NRLock acquire"
        return self.__rlock.acquire(blocking)

    def release(self):
        return self.__rlock.release()

    def _is_owned(self):
        return self.__rlock._is_owned()
