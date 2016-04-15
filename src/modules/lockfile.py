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

#
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

import errno
import fcntl
import os
import platform

import pkg.catalog
import pkg.misc as misc
import pkg.nrlock as nrlock
import pkg.client.api_errors as api_errors

from pkg.client import global_settings
from pkg.misc import DummyLock

class LockFile(object):
        """A class that provides generic lockfile support.  This
        allows Python processes to perform inter-process locking
        using the filesystem."""

        def __init__(self, filepath, set_lockstr=None, get_lockstr=None,
            failure_exc=None, provide_mutex=True):
                """Create a LockFile object.  The 'filepath' argument
                should be the path to the file that will be used as the
                lockfile.  If the caller may supply the following
                optional arguments:

                set_lockstr - A function that returns a string.  This
                is called when the lock operation wants to write
                implementation specific text into the lock file.

                get_lockstr - A function that takes a string and returns
                a dictionary.  This function must be able to parse
                the lock string created by set_lockstr.  The dictionary
                object is passed as **kwargs to 'failure_exc' if
                the lock is non-blocking and fails.

                failure_exc - If a non-blocking lock acquisition fails,
                this exception will be raised.  It should allow the
                caller to specify a kwargs argument, but not all
                invocations will provide kwargs.

                provide_mutex - By default, the LockFile object
                will use a mutex to sychronize access for threads in
                the current process.  If the caller is already providing
                mutual exclusion to the LockFile object, this should
                be set to False."""

                self._fileobj = None
                self._filepath = filepath
                self._set_lockstr = set_lockstr
                self._get_lockstr = get_lockstr
                self._provide_mutex = False
                if failure_exc:
                        self._failure_exc = failure_exc
                else:
                        self._failure_exc = FileLocked
                if provide_mutex:
                        self._lock = nrlock.NRLock()
                        self._provide_mutex = True
                else:
                        self._lock = DummyLock()

        @property
        def locked(self):
                if self._provide_mutex:
                        return self._lock.locked and self._fileobj
                return self._fileobj

        def lock(self, blocking=True):
                """Lock the lockfile, to prevent access from other
                processes.  If blocking is False, this method will
                return an exception, instead of blocking, if the lock
                is held.  If the lockfile cannot be opened,
                this method may return an EnvironmentError."""

                #
                # The password locking in cfgfiles.py depends on the behavior
                # of this function, which imitates that of libc's lckpwdf(3C).
                # If this function is changed, it either needs to continue to be
                # compatible with lckpwdf, or changes to cfgfiles.py must be
                # made.
                #

                rval = self._lock.acquire(blocking=int(blocking))
                # Lock acquisition failed.
                if not rval:
                        raise self._failure_exc()

                lock_type = fcntl.LOCK_EX
                if not blocking:
                        lock_type |= fcntl.LOCK_NB

                # Attempt an initial open of the lock file.
                lf = None

                # Caller should catch EACCES and EROFS.
                try:
                        # If the file is a symlink we catch an exception
                        # and do not update the file.
                        fd = os.open(self._filepath,
                            os.O_RDWR|os.O_APPEND|os.O_CREAT|
                            os.O_NOFOLLOW)
                        lf = os.fdopen(fd, "ab+")
                except OSError as e:
                        self._lock.release()
                        if e.errno == errno.ELOOP:
                                raise api_errors.UnexpectedLinkError(
                                    os.path.dirname(self._filepath),
                                    os.path.basename(self._filepath),
                                    e.errno)
                        raise e
                except:
                        self._lock.release()
                        raise

                # Attempt to lock the file.
                try:
                        fcntl.lockf(lf, lock_type)
                except IOError as e:
                        if e.errno not in (errno.EAGAIN, errno.EACCES):
                                self._lock.release()
                                raise

                        # If the lock failed (because it is likely contended),
                        # then extract the information about the lock acquirer
                        # and raise an exception.
                        lock_data = lf.read().strip()
                        self._lock.release()
                        if self._get_lockstr:
                                lock_dict = self._get_lockstr(lock_data)
                        else:
                                lock_dict = {}
                        raise self._failure_exc(**lock_dict)

                # Store information about the lock acquirer and write it.
                try:
                        lf.truncate(0)
                        lock_str = None
                        if self._set_lockstr:
                                lock_str = self._set_lockstr()
                        if lock_str:
                                lf.write(misc.force_bytes(lock_str))
                        lf.flush()
                        self._fileobj = lf
                except:
                        self._fileobj = None
                        lf.close()
                        self._lock.release()
                        raise

        def unlock(self):
                """Unlocks the LockFile."""

                if self._fileobj:
                        # To avoid race conditions with the next caller
                        # waiting for the lock file, it is simply
                        # truncated instead of removed.
                        try:
                                fcntl.lockf(self._fileobj, fcntl.LOCK_UN)
                                self._fileobj.truncate(0)
                                self._fileobj.close()
                                self._lock.release()
                        except EnvironmentError:
                                # If fcntl, or the file operations returned
                                # an exception, drop the lock. Do not catch
                                # the exception that could escape from
                                # releasing the lock.
                                self._lock.release()
                                raise
                        finally:
                                self._fileobj = None
                else:
                        if self._provide_mutex:
                                assert not self._lock.locked


class FileLocked(Exception):        
        """Generic exception class used by LockFile.  Raised
        in non-blocking mode when file or thread is already locked."""

        def __init__(self, *args, **kwargs):
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self._args = kwargs

        def __str__(self):
                errstr = "Unable to lock file"
                if self.data:
                        errstr += ": {0}".format(self.data)
                return errstr


def client_lock_get_str(lockstr):
        lockdict = {}

        try:
                pid, pid_name, hostname, lock_ts =  lockstr.split(b"\n", 4)
                lockdict["pid"] = pid
                lockdict["pid_name"] = pid_name
                lockdict["hostname"] = hostname
                return lockdict
        except ValueError:
                return lockdict

def client_lock_set_str():
        lock_ts = pkg.catalog.now_to_basic_ts()

        return "\n".join((str(os.getpid()), global_settings.client_name,
            platform.node(), lock_ts, "\n"))

def generic_lock_get_str(lockstr):
        lock_dict = {}
        try:
                pid, hostname, lock_ts = lockstr.split(b"\n", 3)
                lock_dict["pid"] = pid
                lock_dict["hostname"] = hostname
                return lock_dict
        except ValueError:
                return lock_dict

def generic_lock_set_str():
        lock_ts = pkg.catalog.now_to_basic_ts()

        return "\n".join((str(os.getpid()), platform.node(), lock_ts, "\n"))
