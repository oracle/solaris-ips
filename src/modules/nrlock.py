#!/usr/bin/python
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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
#

import sys
import threading
import traceback

# Rename some stuff so "from pkg.nrlock import *" is safe
__all__ = [ 'NRLock' ]

def NRLock(*args, **kwargs):
        return _NRLock(*args, **kwargs)

class _NRLock(threading._RLock):
        """Interface and implementation for Non-Reentrant locks.  Derived from
        RLocks (which are reentrant locks).  The default Python base locking
        type, threading.Lock(), is non-reentrant but it doesn't support any
        operations other than aquire() and release(), and we'd like to be
        able to support things like RLocks._is_owned() so that we can "assert"
        lock ownership assumptions in our code."""

        def __init__(self):
                threading._RLock.__init__(self)

        def acquire(self, blocking=1):
                if self._is_owned():
                        raise NRLockException("Recursive NRLock acquire")
                return threading._RLock.acquire(self, blocking)

        @property
        def locked(self):
                """A boolean indicating whether the lock is currently locked."""
                return self._is_owned()

        def _debug_lock_release(self):
                errbuf = ""
                owner = self._RLock__owner
                if not owner:
                        return errbuf

                # Get stack of current owner, if lock is owned.
                for tid, stack in sys._current_frames().items():
                        if tid != owner.ident:
                                continue
                        errbuf += "Stack of owner:\n"
                        for filenm, lno, func, txt in \
                            traceback.extract_stack(stack):
                                errbuf += "  File: \"{0}\", line {1:d},in {2}".format(
                                    filenm, lno, func)
                                if txt:
                                        errbuf += "\n    {0}".format(txt.strip())
                                errbuf += "\n"
                        break

                return errbuf

        def release(self):
                try:
                        threading._RLock.release(self)
                except RuntimeError:
                        errbuf = "Release of unacquired lock\n"
                        errbuf += self._debug_lock_release()
                        raise NRLockException(errbuf)

class NRLockException(Exception):

        def __init__(self, *args, **kwargs):
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self._args = kwargs

        def __str__(self):
                return str(self.data)
