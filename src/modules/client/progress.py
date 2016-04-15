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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

#
# Missing docstring; pylint: disable=C0111
#

from __future__ import division
from __future__ import print_function

import inspect
import itertools
import math
import sys
import simplejson as json
import six
import time
from functools import wraps
# Redefining built-in 'range'; pylint: disable=W0622
# import-error: six.moves; pylint: disable=F0401
from six.moves import range

import pkg.client.pkgdefs as pkgdefs
import pkg.client.publisher as publisher
import pkg.fmri
import pkg.misc as misc

from pkg.client import global_settings
from pkg.client import printengine
logger = global_settings.logger

from collections import deque

class ProgressTrackerException(Exception):
        """Thrown if a ProgressTracker determines that it can't be instantiated.
        For example, the tracker which depends on a UNIX style terminal should
        throw this exception if it can't find a valid terminal."""
        def __str__(self):
                return "ProgressTrackerException: {0}".format(
                    " ".join(self.args))


def format_pair(format1, v1, v2, scale=None, targetwidth=None,
    format2=None):
        """Format a pair of numbers 'v1' and 'v2' representing a fraction, such
        as v1=3 v2=200, such that for all anticipated values of v1 (0 through
        v2) , the result is a fixed width pair separated by '/':

            format_pair("{0:d}", 3, 200)               --> "  3/200"

        'format1' is the preferred number format.  In the event that targetwidth
        is specified and the width of (format1.format(v2) > targetwidth), then
        'format2' is used instead:

            format_pair("{0:.1f}", 20.322, 1000.23,
                targetwidth=5, format2="{0:d}")             --> "  20/1000"

        This provides a mechanism for downshifting the accuracy of an output
        to preserve column width.

        Inputs are scaled (divided by 'scale') if scale is specified."""

        if scale:
                v1 /= float(scale)
                v2 /= float(scale)
        realformat = format1
        v2format = realformat.format(v2)
        v2len = len(v2format)
        if format2 and targetwidth and v2len > targetwidth:
                # see if format2 is shorter.
                # convert type 'float' to 'int'.
                if "d" in format2:
                        v2format = format2.format(int(v2))
                else:
                        v2format = format2.format(v2)
                v2len1 = len(v2format)
                if v2len1 < v2len:
                        realformat = format2
                        v2len = v2len1

        formatcolon = realformat.find(":")
        v1format = realformat[0:formatcolon + 1] + str(v2len) + \
            realformat[formatcolon + 1:]
        if "d" in v1format:
                return (v1format.format(int(v1))) + "/" + v2format
        else:
                return (v1format.format(v1)) + "/" + v2format


class SpeedEstimator(object):
        """This class implements a rudimentary download speed estimator.
        newdata() is used to indicate download progress; curl calls
        us back pretty frequently so that's not a terrible way to
        go.  Download progress records are kept on a deque, and are
        expired after self.interval seconds have elapsed.  Speed estimates
        are smoothed so that things don't bounce around too fast.

        The class also implements some heuristics designed to prevent
        handing out crappy estimates early in the download."""

        # INTERVAL describes the interval, in seconds, which is used to
        # compute the download speed.
        INTERVAL = 10.0
        # This is the decay rate (or how much we mix in the historical
        # notion of speed into the current notion).
        SMOOTHING = 0.98

        def __init__(self, goalbytes):

                # Ok to modify this during operation.
                self.goalbytes = goalbytes
                self.__deque = deque()
                self.__intervalbytes = 0
                self.__curtotal = 0
                self.__last_smooth_speed = None
                self.__instartup = True
                self.__noestimate = True
                self.__starttime = None
                self.__donetime = None

        @staticmethod
        def format_speed(speed):
                if speed is None:
                        return None

                #
                # A little hack to keep things tidy: if the length of
                # the speedstr > 5, we whack off the floating point
                # portion.
                #
                speedstr = misc.bytes_to_str(speed, "{num:>.1f}{shortunit}")
                if speed < 1024 or len(speedstr) > 5:
                        speedstr = misc.bytes_to_str(speed,
                            "{num:d}{shortunit}")
                speedstr += "/s"
                return speedstr

        def newdata(self, nbytes, timestamp=None):
                """Add new data as it becomes available; timestamp can be
                overridden, although this is primarily designed for testing."""

                # must be started before adding data (sorry)
                assert self.__starttime

                #
                # Step 1: Insert latest datum
                #
                curtime = timestamp if timestamp else time.time()
                self.__curtotal += nbytes
                self.__deque.append((curtime, nbytes))
                self.__intervalbytes += nbytes

                #
                # Step 2: Expunge old data
                #
                while len(self.__deque) > 0:
                        (ts, val) = self.__deque[0]
                        if ts < curtime - self.INTERVAL:
                                self.__intervalbytes -= val
                                self.__deque.popleft()
                        else:
                                break

                #
                # Step 3: Recompute the estimate
                #
                # compute time delta between front and back of deque
                timelapse = self.__deque[-1][0] - self.__deque[0][0]

                if len(self.__deque) <= 1 or timelapse == 0.0:
                        # can't operate yet
                        self.__noestimate = True
                        return

                #
                # 'ratiocomplete' is just the percentage done.  It is
                # used to disable 'startup mode' if the d/l completes
                # very rapidly.  We'll always start giving the user an
                # estimate once ratiocomplete >= 50%.
                # pylint is picky about this message:
                # old-division; pylint: disable=W1619
                ratiocomplete = 0.0 if self.goalbytes == 0 else \
                    self.__curtotal / self.goalbytes

                #
                # Keep track of whether we're in the warmup phase.  This
                # is used to deny estimates to callers until we feel good
                # about them.  This is very heuristic; it's a higher bar than
                # we use below for disabling the estimate, basically because
                # we want to open with a solid estimate.
                #
                if self.__instartup and len(self.__deque) > 50 and \
                    timelapse > (self.INTERVAL / 5.0):
                        self.__instartup = False

                #
                # Even if we haven't accomplished the above requirements,
                # exit startup mode when we're 1/3 done or more.
                #
                if self.__instartup and ratiocomplete > 0.33:
                        self.__instartup = False

                #
                # Take a look at the deque length as well as how much an
                # interval's worth of data we have. If it is quite short,
                # maybe the download has stalled out, or perhaps the user
                # used ctrl-z and then resumed; disable the estimate until we
                # build up more data.
                #
                if len(self.__deque) < 10 or timelapse < (self.INTERVAL / 20.0):
                        self.__noestimate = True
                else:
                        self.__noestimate = False

                curspeed = self.__intervalbytes / timelapse

                if self.__last_smooth_speed is None:
                        self.__last_smooth_speed = curspeed
                else:
                        self.__last_smooth_speed = \
                            int((self.SMOOTHING * self.__last_smooth_speed) + \
                            ((1.0 - self.SMOOTHING) * curspeed))

        def start(self, timestamp=None):
                assert not self.__starttime
                self.__starttime = timestamp if timestamp else time.time()

        def done(self, timestamp=None):
                assert not self.__donetime
                self.__donetime = timestamp if timestamp else time.time()

        def get_speed_estimate(self):
                if self.__noestimate or self.__instartup or \
                    not self.__last_smooth_speed:
                        return None
                return int(self.__last_smooth_speed)

        def get_final_speed(self):
                if self.__donetime is None:
                        return None
                try:
                        # pylint is picky about this message:
                        # old-division; pylint: disable=W1619
                        return self.goalbytes / self.elapsed()
                except ZeroDivisionError:
                        return None

        def elapsed(self):
                return None if self.__donetime is None else \
                    self.__donetime - self.__starttime

        def __str__(self):
                s = "<SpeedEstimator: "
                d = self.__dict__.copy()
                d.pop("_SpeedEstimator__deque")
                s += str(d)
                s += " __deque=["
                for x, (timestamp, nbytes) in enumerate(self.__deque):
                        if x % 3 == 0:
                                s += "\n    "
                        s += "(t={0:>.3f}, b={1:5d}), ".format(
                            timestamp - self.__starttime, nbytes)
                s += "]>"
                return s


class PrintTimer(object):
        """This helper class is used to implement damping of excessive
        printing by progress trackers.

        'print_value': This is a handy 'clicker' attribute which can be
        read to get a monotonically increasing count of the number of times
        time_to_print() has returned True.  Can be used to key a spinner,
        e.g.:
                print("{0}".format(pt.print_value.format(len(__spinner_chars))))
        """

        def __init__(self, delay):
                self.print_value = 0
                self.__delay = delay
                self.__last_print_time = 0

        def reset(self):
                self.__last_print_time = 0

        def reset_now(self):
                self.__last_print_time = time.time()

        #
        # See if it has been more than __delay time since the last time we
        # indicated that it was time to print.  If this returns true, the
        # caller should go ahead and print; this will not return true again
        # until the 'delay' period has elapsed again.
        #
        def time_to_print(self):
                tt = time.time()
                if (tt - self.__last_print_time) < self.__delay:
                        return False
                self.__last_print_time = tt
                self.print_value += 1
                return True


class OutSpec(object):
        """OutSpec is used by the progress tracker frontend to convey
        contextual information to backend routines about the output
        being requested.  'first' means "this is the first output
        for this group of items" (so perhaps print a header).
        'last' similarly means "this is the last output for this
        group of items."  Additional strings can be passed via
        the 'changed' list, denoting other events of significance."""

        def __init__(self, first=False, last=False, changed=None):
                self.first = first
                self.last = last
                self.changed = [] if changed is None else changed

        def __str__(self):
                s = "<outspec:"
                s += " +first" if self.first else ""
                s += " +last" if self.last else ""
                if self.changed:
                        for chg in self.changed:
                                s += " +'{0}'".format(str(chg))
                s += ">"
                return s

        # Defining "boolness" of a class, Python 2 uses the special method
        # called __nonzero__() while Python 3 uses __bool__(). For Python
        # 2 and 3 compatibility, define __bool__() only, and let
        # __nonzero__ = __bool__
        def __bool__(self):
                return bool(self.first) or bool(self.last) or bool(self.changed)

        __nonzero__ = __bool__

class TrackerItem(object):
        """This class describes an item of interest in tracking progress
        against some "bucket" of work (for example, searching a filesystem for
        some item).

        This provides a way to wrap together begin and end times of the
        operation, the operation's name, and 'curinfo'-- some additional
        tidbit of information (such as the current directory being scanned)."""

        def __init__(self, name):
                self.starttime = -1 # signal setattr that we're in __init__.
                self.name = name
                self.endtime = None
                self.items = 0
                #
                # Used by clients to track if this item has been printed yet.
                # The object itself does not care about the value of this
                # attribute but will clear it on reset()
                #
                self.printed = False

                #
                # This attribute allows us to hang some client data
                # off of this object; use this to store some information
                # about the thing we're currently working on.
                #
                self.curinfo = None
                self.starttime = None # done constructing

        def reset(self):
                # This is a kludge but I can't find a better way to do this
                # and keep pylint's "definied outside of __init__" rule (W0201)
                # happy, without either repeating all of this code twice, or
                # disabling the rule file-wide.  Both of which seem even worse.
                self.__init__(self.name)

        def __setattr__(self, attrname, value):
                #
                # Start 'starttime' when 'items' is first set (even to zero)
                # Note that starttime is initially set to -1 to avoid starting
                # the timer during __init__().
                #
                # Special behavior only for 'items' and only when not resetting
                if attrname != "items" or self.starttime == -1:
                        self.__dict__[attrname] = value
                        return

                if self.starttime is None:
                        assert not getattr(self, "endtime", None), \
                            "can't set items after explicit done(). " \
                            "Tried to set {0}={1} (is {2})".format(
                            attrname, value, self.__dict__[attrname])
                        self.starttime = time.time()
                self.__dict__[attrname] = value

        def start(self):
                assert self.endtime is None
                if not self.starttime:
                        self.starttime = time.time()

        def done(self):
                self.endtime = time.time()

        def elapsed(self):
                if not self.starttime:
                        return 0.0
                endtime = self.endtime
                if endtime is None:
                        endtime = time.time()
                return endtime - self.starttime

        def __str__(self):
                info = ""
                if self.curinfo:
                        info = " ({0})".format(str(self.curinfo))
                return "<{0}: {1}{2}>".format(self.name, self.items, info)


class GoalTrackerItem(TrackerItem):
        """This class extends TrackerItem to include the notion of progress
        towards some goal which is known in advance of beginning the operation
        (such as downloading 37 packages).  In addition to the features of
        TrackerItem, this class provides helpful routines for conversion to
        printable strings of the form "  3/100"."""

        def __init__(self, name):
                TrackerItem.__init__(self, name)
                self.goalitems = None

        def reset(self):
                # See comment in superclass.
                self.__init__(self.name)

        # start 'starttime' when items gets set to non-zero
        def __setattr__(self, attrname, value):
                # Special behavior only for 'items' and only when not resetting
                if attrname != "items" or self.starttime == -1:
                        self.__dict__[attrname] = value
                        return

                assert not getattr(self, "endtime", None), \
                    "can't set values after explicit done(). " \
                    "Tried to set {0}={1} (is {2})".format(
                    attrname, value, self.__dict__[attrname])

                # see if this is the first time we're setting items
                if self.starttime is None:
                        if self.goalitems is None:
                                raise RuntimeError(
                                    "Cannot alter items until goalitems is set")
                        self.starttime = time.time()
                self.__dict__[attrname] = value

        def done(self, goalcheck=True):
                # Arguments number differs from overridden method;
                #     pylint: disable=W0221
                TrackerItem.done(self)

                # See if we indeed met our goal.
                if goalcheck and not self.metgoal():
                        exstr = _("Goal mismatch '{name}': "
                            "expected goal: {expected}, "
                            "current value: {current}").format(
                            name=self.name,
                            expected=self.goalitems,
                            current=self.items)
                        logger.error("\n" + exstr)
                        assert self.metgoal(), exstr

        def metgoal(self):
                if self.items == 0 and self.goalitems is None:
                        return True
                return self.items == self.goalitems

        def pair(self):
                if self.goalitems is None:
                        assert self.items == 0
                        return format_pair("{0:d}", 0, 0)
                return format_pair("{0:d}", self.items, self.goalitems)

        def pairplus1(self):
                # For use when you want to display something happening,
                # such as: Downloading item 3/3, since typically items is
                # not incremented until after the operation completes.
                #
                # To ensure that we don't print 4/3 in the last iteration of
                # output, we also account for that case.
                if self.goalitems is None:
                        assert self.items == 0
                        return format_pair("{0:d}", 1, 1)
                if self.items == self.goalitems:
                        items = self.items
                else:
                        items = self.items + 1
                return format_pair("{0:d}", items, self.goalitems)

        def pctdone(self):
                """Returns progress towards a goal as a percentage.
                i.e. 37 / 100 would yield 37.0"""
                if self.goalitems is None or self.goalitems == 0:
                        return 0
                # pylint is picky about this message:
                # old-division; pylint: disable=W1619
                return math.floor(100.0 *
                    self.items / self.goalitems)

        def __str__(self):
                info = ""
                if self.curinfo:
                        info = " ({0})".format(str(self.curinfo))
                return "<{0}: {1}{2}>".format(self.name, self.pair(), info)

#
# This implements a decorator which is used to mark methods in
# this class as abstract-- needing to be implemented by subclasses.
#
# This is similar to, but looser than, the sorts of abstractness
# enforcement we'd get from using python's abc module; in abc,
# abstractness is checked and enforced at construction time.  Some
# of our subclasses are more dynamic than that-- building out
# the required methods at __init__ time.
#
def pt_abstract(func):
        # Unused argument 'args', 'kwargs'; pylint: disable=W0613
        @wraps(func)
        def enforce_abstract(*args, **kwargs):
                raise NotImplementedError("{0} is abstract in "
                    "superclass; you must implement it in your "
                    "subclass.".format(func.__name__))

        return enforce_abstract


#
# We define a separate class to hold the set of interfaces which comprise
# a progress tracker 'backend'.  This mix-in allows introspection by
# subclasses about which interfaces actually comprise the backend APIs
# versus front-end APIs.
#
class ProgressTrackerBackend(object):
        # allow def func(args): pass
        # More than one statement on a line; pylint: disable=C0321

        def __init__(self): pass

        #
        # This set of methods should be regarded as abstract *and* protected.
        #
        @pt_abstract
        def _output_flush(self): pass

        @pt_abstract
        def _change_purpose(self, old_purpose, new_purpose): pass

        @pt_abstract
        def _cache_cats_output(self, outspec): pass

        @pt_abstract
        def _load_cat_cache_output(self, outspec): pass

        @pt_abstract
        def _refresh_output_progress(self, outspec): pass

        @pt_abstract
        def _plan_output(self, outspec, planitem): pass

        @pt_abstract
        def _plan_output_all_done(self): pass

        @pt_abstract
        def _mfst_fetch(self, outspec): pass

        @pt_abstract
        def _mfst_commit(self, outspec): pass

        @pt_abstract
        def _repo_ver_output(self, outspec, repository_scan=False): pass

        @pt_abstract
        def _repo_ver_output_error(self, errors): pass

        @pt_abstract
        def _repo_ver_output_done(self): pass

        def _repo_fix_output(self, outspec): pass

        @pt_abstract
        def _repo_fix_output_error(self, errors): pass

        @pt_abstract
        def _repo_fix_output_info(self, errors): pass

        @pt_abstract
        def _repo_fix_output_done(self): pass

        @pt_abstract
        def _archive_output(self, outspec): pass

        @pt_abstract
        def _dl_output(self, outspec): pass

        @pt_abstract
        def _act_output(self, outspec, actionitem): pass

        @pt_abstract
        def _act_output_all_done(self): pass

        @pt_abstract
        def _job_output(self, outspec, jobitem): pass

        @pt_abstract
        def _republish_output(self, outspec): pass

        @pt_abstract
        def _lint_output(self, outspec): pass

        @pt_abstract
        def _li_recurse_start_output(self): pass

        @pt_abstract
        def _li_recurse_end_output(self): pass

        @pt_abstract
        def _li_recurse_output_output(self, lin, stdout, stderr): pass

        @pt_abstract
        def _li_recurse_status_output(self, done): pass

        @pt_abstract
        def _li_recurse_progress_output(self, lin): pass

        @pt_abstract
        def _reversion(self, pfmri, outspec): pass

class ProgressTrackerFrontend(object):
        """This essentially abstract class forms the interface that other
        modules in the system use to record progress against various goals."""

        # More than one statement on a line; pylint: disable=C0321

        # Major phases of operation
        PHASE_PREPLAN = 1
        PHASE_PLAN = 2
        PHASE_DOWNLOAD = 3
        PHASE_EXECUTE = 4
        PHASE_FINALIZE = 5
        # Extra phase used when we're doing some part of a subphase
        # (such as rebuilding the search index) in a standalone operation.
        PHASE_UTILITY = 6
        MAJOR_PHASE = [PHASE_PREPLAN, PHASE_PLAN, PHASE_DOWNLOAD, PHASE_EXECUTE,
            PHASE_FINALIZE, PHASE_UTILITY]

        # Planning phases
        PLAN_SOLVE_SETUP = 100
        PLAN_SOLVE_SOLVER = 101
        PLAN_FIND_MFST = 102
        PLAN_PKGPLAN = 103
        PLAN_ACTION_MERGE = 104
        PLAN_ACTION_CONFLICT = 105
        PLAN_ACTION_CONSOLIDATE = 106
        PLAN_ACTION_MEDIATION = 107
        PLAN_ACTION_FINALIZE = 108
        PLAN_MEDIATION_CHG = 109 # for set-mediator
        PLAN_PKG_VERIFY = 110
        PLAN_PKG_FIX = 111

        # Action phases
        ACTION_REMOVE = 200
        ACTION_INSTALL = 201
        ACTION_UPDATE = 202

        # Finalization/Job phases
        JOB_STATE_DB = 300
        JOB_IMAGE_STATE = 301
        JOB_FAST_LOOKUP = 302
        JOB_PKG_CACHE = 303
        JOB_READ_SEARCH = 304
        JOB_UPDATE_SEARCH = 305
        JOB_REBUILD_SEARCH = 306
        # pkgrepo job items
        JOB_REPO_DELSEARCH = 307
        JOB_REPO_UPDATE_CAT = 308
        JOB_REPO_ANALYZE_RM = 309
        JOB_REPO_ANALYZE_REPO = 310
        JOB_REPO_RM_MFST = 311
        JOB_REPO_RM_FILES = 312
        JOB_REPO_VERIFY_REPO = 313
        JOB_REPO_FIX_REPO = 314

        # Operation purpose.  This set of modes is used by callers to indicate
        # to the progress tracker what's going on at a high level.  This allows
        # output to be customized by subclasses to meet the needs of a
        # particular purpose.

        #
        # The purpose of current operations is in the "normal" set of things,
        # including install, uninstall, change-variant, and other operations
        # in which we can print arbitrary status information with impunity
        #
        PURPOSE_NORMAL = 0

        #
        # The purpose of current operations is in the service of trying to
        # output a listing (list, contents, etc.) to the end user.  Subclasses
        # will likely want to suppress various bits of status (for non-tty
        # output) or erase it (for tty output).
        #
        PURPOSE_LISTING = 1

        #
        # The purpose of current operations is in the service of figuring out
        # if the packaging system itself is up to date.
        #
        PURPOSE_PKG_UPDATE_CHK = 2

        #
        # Types of lint phases
        #
        LINT_PHASETYPE_SETUP = 0
        LINT_PHASETYPE_EXECUTE = 1

        def __init__(self):
                # needs to be here due to use of _()
                self.phase_names = {
                    self.PHASE_PREPLAN:  _("Startup"),
                    self.PHASE_PLAN:     _("Planning"),
                    self.PHASE_DOWNLOAD: _("Download"),
                    self.PHASE_EXECUTE:  _("Actions"),
                    self.PHASE_FINALIZE: _("Finalize"),
                    self.PHASE_UTILITY:  "",
                }

                # find the widest string in the list of phases so we can
                # set column width properly.
                self.phase_max_width = \
                    max(len(x) for x in self.phase_names.values())

                self.li_phase_names = {
                    self.PHASE_PREPLAN:  _("Startup"),
                    self.PHASE_PLAN:     _("Planning"),
                    self.PHASE_DOWNLOAD: _("Downloading"),
                    self.PHASE_FINALIZE: _("Executing"),
                    self.PHASE_UTILITY:  _("Processing"),
                }

        @pt_abstract
        def set_purpose(self, purpose): pass

        @pt_abstract
        def get_purpose(self): pass

        @pt_abstract
        def reset_download(self): pass

        @pt_abstract
        def reset(self): pass

        @pt_abstract
        def set_major_phase(self, majorphase): pass

        @pt_abstract
        def flush(self): pass

        @pt_abstract
        def cache_catalogs_start(self): pass

        @pt_abstract
        def cache_catalogs_done(self): pass

        @pt_abstract
        def load_catalog_cache_start(self): pass

        @pt_abstract
        def load_catalog_cache_done(self): pass

        # fetching catalogs
        @pt_abstract
        def refresh_start(self, pub_cnt, full_refresh, target_catalog=False):
                pass

        @pt_abstract
        def refresh_start_pub(self, pub): pass

        @pt_abstract
        def refresh_end_pub(self, pub): pass

        @pt_abstract
        def refresh_progress(self, pub, nbytes): pass

        @pt_abstract
        def refresh_done(self): pass

        # planning an operation
        @pt_abstract
        def plan_all_start(self): pass

        @pt_abstract
        def plan_start(self, planid, goal=None): pass

        @pt_abstract
        def plan_add_progress(self, planid, nitems=1): pass

        @pt_abstract
        def plan_done(self, planid): pass

        @pt_abstract
        def plan_all_done(self): pass

        # getting manifests over the network
        @pt_abstract
        def manifest_fetch_start(self, goal_mfsts): pass

        @pt_abstract
        def manifest_fetch_progress(self, completion): pass

        @pt_abstract
        def manifest_commit(self): pass

        @pt_abstract
        def manifest_fetch_done(self): pass

        # verifying the content of a repository
        @pt_abstract
        def repo_verify_start(self, npkgs): pass

        @pt_abstract
        def repo_verify_start_pkg(self, pkgfmri, repository_scan=False): pass

        @pt_abstract
        def repo_verify_add_progress(self, pkgfmri): pass

        @pt_abstract
        def repo_verify_yield_error(self, pkgfmri, errors): pass

        @pt_abstract
        def repo_verify_yield_warning(self, pkgfmri, warnings): pass

        @pt_abstract
        def repo_verify_yield_info(self, pkgfmri, info): pass

        @pt_abstract
        def repo_verify_end_pkg(self, pkgfmri): pass

        @pt_abstract
        def repo_verify_done(self): pass

        # fixing the content of a repository
        @pt_abstract
        def repo_fix_start(self, npkgs): pass

        @pt_abstract
        def repo_fix_add_progress(self, pkgfmri): pass

        @pt_abstract
        def repo_fix_yield_error(self, pkgfmri, errors): pass

        @pt_abstract
        def repo_fix_yield_info(self, pkgfmri, info): pass

        @pt_abstract
        def repo_fix_done(self): pass

        # archiving to .p5p files
        @pt_abstract
        def archive_set_goal(self, arcname, nitems, nbytes): pass

        @pt_abstract
        def archive_add_progress(self, nitems, nbytes): pass

        @pt_abstract
        def archive_done(self): pass

        # Called when bits arrive, either from on-disk cache or over-the-wire.
        @pt_abstract
        def download_set_goal(self, npkgs, nfiles, nbytes): pass

        @pt_abstract
        def download_start_pkg(self, pkgfmri): pass

        @pt_abstract
        def download_end_pkg(self, pkgfmri): pass

        @pt_abstract
        def download_add_progress(self, nfiles, nbytes, cachehit=False):
                """Call to provide news that the download has made progress."""
                pass

        @pt_abstract
        def download_done(self, dryrun=False):
                """Call when all downloading is finished."""
                pass

        @pt_abstract
        def download_get_progress(self): pass

        # Running actions
        @pt_abstract
        def actions_set_goal(self, actionid, nactions): pass

        @pt_abstract
        def actions_add_progress(self, actionid): pass

        @pt_abstract
        def actions_done(self, actionid): pass

        @pt_abstract
        def actions_all_done(self): pass

        @pt_abstract
        def job_start(self, jobid, goal=None): pass

        @pt_abstract
        def job_add_progress(self, jobid, nitems=1): pass

        @pt_abstract
        def job_done(self, jobid): pass

        @pt_abstract
        def republish_set_goal(self, npkgs, ngetbytes, nsendbytes): pass

        @pt_abstract
        def republish_start_pkg(self, pkgfmri, getbytes=None, sendbytes=None):
                pass

        @pt_abstract
        def republish_end_pkg(self, pkgfmri): pass

        @pt_abstract
        def upload_add_progress(self, nbytes):
                """Call to provide news that the upload has made progress."""
                pass

        @pt_abstract
        def republish_done(self, dryrun=False):
                """Call when all republishing is finished."""
                pass

        @pt_abstract
        def lint_next_phase(self, goalitems, lint_phasetype):
                """Call to indicate a new phase of lint progress."""
                pass

        @pt_abstract
        def lint_add_progress(self): pass

        @pt_abstract
        def lint_done(self): pass

        @pt_abstract
        def set_linked_name(self, lin):
                """Called once an image determines its linked image name."""
                pass

        @pt_abstract
        def li_recurse_start(self, pkg_op, total):
                """Call when we recurse into a child linked image."""
                pass

        @pt_abstract
        def li_recurse_end(self):
                """Call when we return from a child linked image."""
                pass

        @pt_abstract
        def li_recurse_status(self, lin_running, done):
                """Call to update the progress tracker with the list of
                images being operated on."""
                pass

        @pt_abstract
        def li_recurse_output(self, lin, stdout, stderr):
                """Call to display output from linked image operations."""
                pass

        @pt_abstract
        def li_recurse_progress(self, lin):
                """Call to indicate that the named child made progress."""
                pass

        @pt_abstract
        def reversion_start(self, goal_pkgs, goal_revs): pass

        @pt_abstract
        def reversion_add_progress(self, pfmri, pkgs=0, reversioned=0,
            adjusted=0):
                pass

        @pt_abstract
        def reversion_done(self): pass


class ProgressTracker(ProgressTrackerFrontend, ProgressTrackerBackend):
        """This class is used by the client to render and track progress
        towards the completion of various tasks, such as download,
        installation, update, etc.

        The superclass is largely concerned with tracking the raw numbers, and
        with calling various callback routines when events of interest occur.
        The callback routines are defined in the ProgressTrackerBackend class,
        below.

        Different subclasses provide the actual rendering to the user, with
        differing levels of detail and prettiness.

        Note that as currently envisioned, this class is concerned with
        tracking the progress of long-running operations: it is NOT a general
        purpose output mechanism nor an error collector.

        Most subclasses of ProgressTracker need not override the methods of
        this class.  However, most subclasses will need need to mix in and
        define ALL of the methods from the ProgressTrackerBackend class."""

        DL_MODE_DOWNLOAD = 1
        DL_MODE_REPUBLISH = 2

        def __init__(self):
                ProgressTrackerBackend.__init__(self)
                ProgressTrackerFrontend.__init__(self)
                self.reset()

        def reset_download(self):
                # Attribute defined outside __init__; pylint: disable=W0201
                self.dl_mode = None
                self.dl_caching = 0
                self.dl_estimator = None

                self.dl_pkgs = GoalTrackerItem(_("Download packages"))
                self.dl_files = GoalTrackerItem(_("Download files"))
                self.dl_bytes = GoalTrackerItem(_("Download bytes"))
                self._dl_items = [self.dl_pkgs, self.dl_files, self.dl_bytes]

                # republishing support; republishing also uses dl_bytes
                self.repub_pkgs = \
                    GoalTrackerItem(_("Republished pkgs"))
                self.repub_send_bytes = \
                    GoalTrackerItem(_("Republish sent bytes"))

        def reset(self):
                # Attribute defined outside __init__; pylint: disable=W0201
                self.major_phase = self.PHASE_PREPLAN
                self.purpose = self.PURPOSE_NORMAL

                self.pub_refresh = GoalTrackerItem(_("Refresh Publishers"))
                # We don't know the goal in advance for this one
                self.pub_refresh_bytes = TrackerItem(_("Refresh bytes"))
                self.refresh_target_catalog = None
                self.refresh_full_refresh = False

                self.mfst_fetch = GoalTrackerItem(_("Download Manifests"))
                self.mfst_commit = GoalTrackerItem(_("Committed Manifests"))

                self.repo_ver_pkgs = GoalTrackerItem(
                    _("Verify Repository Content"))
                self.repo_fix = GoalTrackerItem(_("Fix Repository Content"))

                # archiving support
                self.archive_items = GoalTrackerItem(_("Archived items"))
                self.archive_bytes = GoalTrackerItem(_("Archived bytes"))

                # reversioning support
                self.reversion_pkgs = GoalTrackerItem(_("Processed Packages"))
                self.reversion_revs = GoalTrackerItem(_("Reversioned Packages"))
                self.reversion_adjs = GoalTrackerItem(_("Adjusted Packages"))

                # Used to measure elapsed time of entire planning; not otherwise
                # rendered to the user.
                self.plan_generic = TrackerItem("")

                self._planitems = {
                        self.PLAN_SOLVE_SETUP:
                            TrackerItem(_("Solver setup")),
                        self.PLAN_SOLVE_SOLVER:
                            TrackerItem(_("Running solver")),
                        self.PLAN_FIND_MFST:
                            TrackerItem(_("Finding local manifests")),
                        self.PLAN_PKGPLAN:
                            GoalTrackerItem(_("Package planning")),
                        self.PLAN_ACTION_MERGE:
                            TrackerItem(_("Merging actions")),
                        self.PLAN_ACTION_CONFLICT:
                            TrackerItem(_("Checking for conflicting actions")),
                        self.PLAN_ACTION_CONSOLIDATE:
                            TrackerItem(_("Consolidating action changes")),
                        self.PLAN_ACTION_MEDIATION:
                            TrackerItem(_("Evaluating mediators")),
                        self.PLAN_ACTION_FINALIZE:
                            TrackerItem(_("Finalizing action plan")),
                        self.PLAN_MEDIATION_CHG:
                            TrackerItem(_("Evaluating mediator changes")),
                        self.PLAN_PKG_VERIFY:
                            GoalTrackerItem(_("Verifying Packages")),
                        self.PLAN_PKG_FIX:
                            GoalTrackerItem(_("Fixing Packages")),
                }

                self._actionitems = {
                        self.ACTION_REMOVE:
                            GoalTrackerItem(_("Removing old actions")),
                        self.ACTION_INSTALL:
                            GoalTrackerItem(_("Installing new actions")),
                        self.ACTION_UPDATE:
                            GoalTrackerItem(_("Updating modified actions")),
                }

                self._jobitems = {
                        self.JOB_STATE_DB:
                            TrackerItem(_("Updating package state database")),
                        self.JOB_IMAGE_STATE:
                            TrackerItem(_("Updating image state")),
                        self.JOB_FAST_LOOKUP:
                            TrackerItem(_("Creating fast lookup database")),
                        self.JOB_PKG_CACHE:
                            GoalTrackerItem(_("Updating package cache")),
                        self.JOB_READ_SEARCH:
                            TrackerItem(_("Reading search index")),
                        self.JOB_UPDATE_SEARCH:
                            GoalTrackerItem(_("Updating search index")),
                        self.JOB_REBUILD_SEARCH:
                            GoalTrackerItem(_("Building new search index")),

                        # pkgrepo job items
                        self.JOB_REPO_DELSEARCH:
                            TrackerItem(_("Deleting search index")),
                        self.JOB_REPO_UPDATE_CAT:
                            TrackerItem(_("Updating catalog")),
                        self.JOB_REPO_ANALYZE_RM:
                            GoalTrackerItem(_("Analyzing removed packages")),
                        self.JOB_REPO_ANALYZE_REPO:
                            GoalTrackerItem(_("Analyzing repository packages")),
                        self.JOB_REPO_RM_MFST:
                            GoalTrackerItem(_("Removing package manifests")),
                        self.JOB_REPO_RM_FILES:
                            GoalTrackerItem(_("Removing package files")),
                        self.JOB_REPO_VERIFY_REPO:
                            GoalTrackerItem(_("Verifying repository content")),
                        self.JOB_REPO_FIX_REPO:
                            GoalTrackerItem(_("Fixing repository content"))

                }

                self.reset_download()

                self._archive_name = None

                # Lint's interaction with the progresstracker probably
                # needs further work.
                self.lint_phase = None
                self.lint_phasetype = None
                # This GoalTrackerItem is created on the fly.
                self.lintitems = None

                # Linked images
                self.linked_name = None
                self.linked_running = []
                self.linked_pkg_op = None
                self.linked_total = 0

        def set_major_phase(self, majorphase):
                # Attribute defined outside __init__; pylint: disable=W0201
                self.major_phase = majorphase

        def flush(self):
                """Used to signal to the progresstracker that it should make
                the output ready for use by another subsystem.  In a
                terminal-based environment, this would make sure that no
                partially printed lines were present, and flush e.g. stdout."""
                self._output_flush()

        def set_purpose(self, purpose):
                op = self.purpose
                self.purpose = purpose # pylint: disable=W0201
                if op != self.purpose:
                        self._change_purpose(op, purpose)

        def get_purpose(self):
                return self.purpose

        def cache_catalogs_start(self):
                self._cache_cats_output(OutSpec(first=True))

        def cache_catalogs_done(self):
                self._cache_cats_output(OutSpec(last=True))

        def load_catalog_cache_start(self):
                self._load_cat_cache_output(OutSpec(first=True))

        def load_catalog_cache_done(self):
                self._load_cat_cache_output(OutSpec(last=True))

        def refresh_start(self, pub_cnt, full_refresh, target_catalog=False):
                #
                # We can wind up doing multiple refreshes in some cases,
                # for example when we have to check if pkg(5) is up-to-date,
                # so we reset these each time we start.
                #
                self.pub_refresh.reset()
                self.pub_refresh.goalitems = pub_cnt
                self.pub_refresh_bytes.reset()
                # Attribute defined outside __init__; pylint: disable=W0201
                self.refresh_full_refresh = full_refresh
                self.refresh_target_catalog = target_catalog
                if self.refresh_target_catalog:
                        assert self.refresh_full_refresh

        def refresh_start_pub(self, pub):
                outspec = OutSpec()
                # for now we only refresh one at a time, so we stash
                # this here, and then assert for it in end_pub and
                # in refresh_progress.
                self.pub_refresh.curinfo = pub
                if not self.pub_refresh.printed:
                        outspec.first = True
                outspec.changed.append("startpublisher")
                self.pub_refresh.printed = True
                self._refresh_output_progress(outspec)

        def refresh_end_pub(self, pub):
                assert pub == self.pub_refresh.curinfo
                assert self.pub_refresh.printed
                outspec = OutSpec()
                outspec.changed.append("endpublisher")
                self.pub_refresh.items += 1
                self._refresh_output_progress(outspec)

        def refresh_progress(self, pub, nbytes):
                # when called back from the transport we lose the knowledge
                # of what 'pub' is, at least for now.
                assert pub is None or pub == self.pub_refresh.curinfo
                assert self.pub_refresh.printed
                self.pub_refresh_bytes.items += nbytes
                self._refresh_output_progress(OutSpec())

        def refresh_done(self):
                # If refreshes fail, we might not meet the goal.
                self.pub_refresh.done(goalcheck=False)
                self.pub_refresh_bytes.done()
                self._refresh_output_progress(OutSpec(last=True))

        def plan_all_start(self):
                self.set_major_phase(self.PHASE_PLAN)
                self.plan_generic.reset()
                self.plan_generic.start()

        def plan_start(self, planid, goal=None):
                planitem = self._planitems[planid]
                planitem.reset()
                if goal:
                        if not isinstance(planitem, GoalTrackerItem):
                                raise RuntimeError(
                                    "can't set goal on non-goal tracker")
                        planitem.goalitems = goal
                planitem.start()

        def plan_add_progress(self, planid, nitems=1):
                planitem = self._planitems[planid]
                outspec = OutSpec(first=not planitem.printed)
                planitem.items += nitems
                self._plan_output(outspec, planitem)
                planitem.printed = True

        def plan_done(self, planid):
                planitem = self._planitems[planid]
                planitem.done()
                if planitem.printed:
                        self._plan_output(OutSpec(last=True), planitem)

        def plan_all_done(self):
                self.plan_generic.done()
                self._plan_output_all_done()

        def manifest_fetch_start(self, goal_mfsts):
                self.mfst_fetch.reset()
                self.mfst_commit.reset()
                self.mfst_fetch.goalitems = goal_mfsts
                self.mfst_commit.goalitems = goal_mfsts

        def manifest_fetch_progress(self, completion):
                assert self.major_phase in [self.PHASE_PLAN, self.PHASE_UTILITY]
                outspec = OutSpec(first=not self.mfst_fetch.printed)
                self.mfst_fetch.printed = True
                if completion:
                        self.mfst_fetch.items += 1
                        outspec.changed.append("manifests")
                self._mfst_fetch(outspec)

        def manifest_commit(self):
                assert self.major_phase in [self.PHASE_PLAN, self.PHASE_UTILITY]
                outspec = OutSpec(first=not self.mfst_commit.printed)
                self.mfst_commit.printed = True
                self.mfst_commit.items += 1
                self._mfst_commit(outspec)

        def manifest_fetch_done(self):
                # These can fail to reach their goals due to various transport
                # errors, depot misconfigurations, etc.  So disable goal check.
                self.mfst_fetch.done(goalcheck=False)
                self.mfst_commit.done(goalcheck=False)
                if self.mfst_fetch.printed:
                        self._mfst_fetch(OutSpec(last=True))

        def repo_verify_start(self, npkgs):
                self.repo_ver_pkgs.reset()
                self.repo_ver_pkgs.goalitems = npkgs

        def repo_verify_start_pkg(self, pkgfmri, repository_scan=False):
                if pkgfmri != self.repo_ver_pkgs.curinfo:
                        self.repo_ver_pkgs.items += 1
                        self.repo_ver_pkgs.curinfo = pkgfmri
                self._repo_ver_output(OutSpec(changed=["startpkg"]),
                    repository_scan=repository_scan)

        def repo_verify_add_progress(self, pkgfmri):
                self._repo_ver_output(OutSpec())

        def repo_verify_yield_error(self, pkgfmri, errors):
                self._repo_ver_output_error(errors)

        def repo_verify_end_pkg(self, pkgfmri):
                self._repo_ver_output(OutSpec(changed=["endpkg"]))
                self.repo_ver_pkgs.curinfo = None

        def repo_verify_done(self):
                self.repo_ver_pkgs.done()

        def repo_fix_start(self, nitems):
                self.repo_fix.reset()
                self.repo_fix.goalitems = nitems

        def repo_fix_add_progress(self, pkgfmri):
                self._repo_fix_output(OutSpec())

        def repo_fix_yield_error(self, pkgfmri, errors):
                self._repo_fix_output_error(errors)

        def repo_fix_yield_info(self, pkgfmri, info):
                self._repo_fix_output_info(info)

        def repo_fix_done(self):
                self.repo_fix.done()

        def archive_set_goal(self, arcname, nitems, nbytes):
                self._archive_name = arcname # pylint: disable=W0201
                self.archive_items.goalitems = nitems
                self.archive_bytes.goalitems = nbytes

        def archive_add_progress(self, nitems, nbytes):
                outspec = OutSpec()
                if not self.archive_bytes.printed:
                        self.archive_bytes.printed = True
                        outspec.first = True
                self.archive_items.items += nitems
                self.archive_bytes.items += nbytes
                self._archive_output(outspec)

        def archive_done(self):
                """Call when all archiving is finished"""
                self.archive_items.done()
                self.archive_bytes.done()
                # only print 'last' if we printed 'first'
                if self.archive_bytes.printed:
                        self._archive_output(OutSpec(last=True))

        def download_set_goal(self, npkgs, nfiles, nbytes):
                # Attribute defined outside __init__; pylint: disable=W0201
                self.dl_mode = self.DL_MODE_DOWNLOAD
                self.dl_pkgs.goalitems = npkgs
                self.dl_files.goalitems = nfiles
                self.dl_bytes.goalitems = nbytes
                self.dl_estimator = SpeedEstimator(self.dl_bytes.goalitems)

        def download_start_pkg(self, pkgfmri):
                self.set_major_phase(self.PHASE_DOWNLOAD)
                self.dl_pkgs.curinfo = pkgfmri
                outspec = OutSpec(changed=["startpkg"])
                if self.dl_bytes.goalitems != 0:
                        if not self.dl_bytes.printed:
                                # indicate that this is the first _dl_output
                                # call
                                self.dl_bytes.printed = True
                                self.dl_estimator.start()
                                outspec.first = True
                        self._dl_output(outspec)

        def download_end_pkg(self, pkgfmri):
                self.dl_pkgs.items += 1
                if self.dl_bytes.goalitems != 0:
                        self._dl_output(OutSpec(changed=["endpkg"]))

        def download_add_progress(self, nfiles, nbytes, cachehit=False):
                """Call to provide news that the download has made progress"""
                #
                # These guards are present because download_add_progress can
                # be called when an *upload* aborts; we want to prevent updates
                # to these items, since they in this case might have no goals.
                #
                if self.dl_bytes.goalitems > 0:
                        self.dl_bytes.items += nbytes
                if self.dl_files.goalitems > 0:
                        self.dl_files.items += nfiles

                if cachehit:
                        # attr defined outside __init__; pylint: disable=W0201
                        self.dl_caching += 1
                        self.dl_estimator.goalbytes -= nbytes
                else:
                        self.dl_caching = 0 # pylint: disable=W0201
                        self.dl_estimator.newdata(nbytes)

                if self.dl_bytes.goalitems != 0:
                        outspec = OutSpec()
                        if nbytes > 0:
                                outspec.changed.append("dl_bytes")
                        if nfiles > 0:
                                outspec.changed.append("dl_files")
                        if self.dl_mode == self.DL_MODE_DOWNLOAD:
                                self._dl_output(outspec)
                        if self.dl_mode == self.DL_MODE_REPUBLISH:
                                self._republish_output(outspec)

        def download_done(self, dryrun=False):
                """Call when all downloading is finished."""
                if dryrun:
                        # Dryrun mode is used by pkgrecv in order to
                        # simulate a download; we do what we have to
                        # in order to fake up a download result.
                        self.dl_pkgs.items = self.dl_pkgs.goalitems
                        self.dl_files.items = self.dl_files.goalitems
                        self.dl_bytes.items = self.dl_bytes.goalitems
                        self.dl_estimator.start(timestamp=0)
                        self.dl_estimator.newdata(self.dl_bytes.goalitems,
                            timestamp=0)
                        self.dl_estimator.done(timestamp=0)
                else:
                        self.dl_estimator.done()

                self.dl_pkgs.done()
                self.dl_files.done()
                self.dl_bytes.done()

                if self.dl_bytes.goalitems != 0:
                        self._dl_output(OutSpec(last=True))

        def actions_set_goal(self, actionid, nactions):
                """Called to set the goal for a particular phase of action
                activity (i.e. ACTION_REMOVE, ACTION_INSTALL, or ACTION_UPDATE.
                """
                assert self.major_phase == self.PHASE_EXECUTE
                actionitem = self._actionitems[actionid]
                actionitem.reset()
                actionitem.goalitems = nactions

        def actions_add_progress(self, actionid):
                assert self.major_phase == self.PHASE_EXECUTE
                actionitem = self._actionitems[actionid]
                actionitem.items += 1
                self._act_output(OutSpec(first=(actionitem.items == 1)),
                    actionitem)

        def actions_done(self, actionid):
                """Called when done each phase of actions processing."""
                assert self.major_phase == self.PHASE_EXECUTE
                actionitem = self._actionitems[actionid]
                actionitem.done()
                if actionitem.goalitems != 0:
                        self._act_output(OutSpec(last=True), actionitem)

        def actions_all_done(self):
                total_actions = sum(x.items for x in self._actionitems.values())
                if total_actions != 0:
                        self._act_output_all_done()

        def job_start(self, jobid, goal=None):
                jobitem = self._jobitems[jobid]
                jobitem.reset()
                outspec = OutSpec()
                if goal:
                        if not isinstance(jobitem, GoalTrackerItem):
                                raise RuntimeError(
                                    "can't set goal on non-goal tracker")
                        jobitem.goalitems = goal
                jobitem.printed = True
                self._job_output(outspec, jobitem)

        def job_add_progress(self, jobid, nitems=1):
                jobitem = self._jobitems[jobid]
                outspec = OutSpec(first=not jobitem.printed)
                jobitem.printed = True
                jobitem.items += nitems
                self._job_output(outspec, jobitem)

        def job_done(self, jobid):
                jobitem = self._jobitems[jobid]
                # only print the 'done' if we printed the 'start'
                jobitem.done()
                if jobitem.printed:
                        self._job_output(OutSpec(last=True), jobitem)

        def republish_set_goal(self, npkgs, ngetbytes, nsendbytes):
                self.dl_mode = self.DL_MODE_REPUBLISH # pylint: disable=W0201

                self.repub_pkgs.goalitems = npkgs
                self.repub_send_bytes.goalitems = nsendbytes

                self.dl_bytes.goalitems = ngetbytes
                # We don't have a good value to set this to.
                self.dl_files.goalitems = 1 << 64
                # Attribute defined outside __init__; pylint: disable=W0201
                self.dl_estimator = SpeedEstimator(self.dl_bytes.goalitems)

        def republish_start_pkg(self, pkgfmri, getbytes=None, sendbytes=None):
                assert isinstance(pkgfmri, pkg.fmri.PkgFmri)

                if getbytes is not None:
                        # Allow reset of GET and SEND amounts on a per-package
                        # basis.  This allows the user to monitor the overall
                        # progress of the operation in terms of total packages
                        # while not requiring the program to pre-process all
                        # packages to determine total byte sizes before starting
                        # the operation.
                        assert sendbytes is not None
                        self.dl_bytes.items = 0
                        self.dl_bytes.goalitems = getbytes
                        self.dl_estimator.goalbytes = getbytes

                        self.repub_send_bytes.items = 0
                        self.repub_send_bytes.goalitems = sendbytes

                self.repub_pkgs.curinfo = pkgfmri
                outspec = OutSpec(changed=["startpkg"])
                #
                # We can't do our normal trick of checking to see if
                # dl_bytes.items is zero because it might have been reset
                # above.
                #
                if not self.repub_pkgs.printed:
                        # indicate that this is the first _republish_output call
                        outspec.first = True
                        self.repub_pkgs.printed = True
                        self.dl_estimator.start()
                if self.repub_pkgs.goalitems != 0:
                        self._republish_output(outspec)

        def republish_end_pkg(self, pkgfmri):
                self.repub_pkgs.items += 1
                self._republish_output(OutSpec(changed=["endpkg"]))

        def upload_add_progress(self, nbytes):
                """Call to provide news that the upload has made progress"""
                #
                # upload_add_progress can be called when a *download* aborts;
                # this guard prevents us from updating the item (which has
                # no goal set, and will raise an exception).
                #
                if self.repub_send_bytes.goalitems and \
                    self.repub_send_bytes.goalitems > 0:
                        self.repub_send_bytes.items += nbytes
                        self._republish_output(OutSpec())

        def republish_done(self, dryrun=False):
                """Call when all republishing is finished"""
                if dryrun:
                        self.repub_pkgs.items = self.repub_pkgs.goalitems
                        self.repub_send_bytes.items = \
                            self.repub_send_bytes.goalitems
                        self.dl_bytes.items = self.dl_bytes.goalitems

                self.repub_pkgs.done()
                self.repub_send_bytes.done()
                self.dl_bytes.done()

                if self.repub_pkgs.goalitems != 0:
                        outspec = OutSpec(last=True)
                        # Get the header printed if we've not printed
                        # anything else thus far (happens in dryrun mode).
                        outspec.first = not self.repub_pkgs.printed
                        self._republish_output(outspec)
                        self.repub_pkgs.printed = True

        def lint_next_phase(self, goalitems, lint_phasetype):
                # Attribute defined outside __init__; pylint: disable=W0201
                self.lint_phasetype = lint_phasetype
                if self.lint_phase is not None:
                        self._lint_output(OutSpec(last=True))
                if self.lint_phase is None:
                        self.lint_phase = 0
                self.lint_phase += 1
                if lint_phasetype == self.LINT_PHASETYPE_SETUP:
                        phasename = _("Lint setup {0:d}".format(
                            self.lint_phase))
                else:
                        phasename = _("Lint phase {0:d}".format(
                            self.lint_phase))
                self.lintitems = GoalTrackerItem(phasename)
                self.lintitems.goalitems = goalitems
                self._lint_output(OutSpec(first=True))

        def lint_add_progress(self):
                self.lintitems.items += 1
                self._lint_output(OutSpec())

        def lint_done(self):
                self.lint_phase = None # pylint: disable=W0201
                if self.lintitems:
                        self._lint_output(OutSpec(last=True))

        def set_linked_name(self, lin):
                """Called once an image determines its linked image name."""
                self.linked_name = lin # pylint: disable=W0201

        def li_recurse_start(self, pkg_op, total):
                """Called when we recurse into a child linked image."""
                # Attribute defined outside __init__; pylint: disable=W0201
                self.linked_pkg_op = pkg_op
                self.linked_total = total
                self._li_recurse_start_output()

        def li_recurse_end(self):
                """Called when we return from a child linked image."""
                self._li_recurse_end_output()

        def li_recurse_status(self, lin_running, done):
                """Call to update the progress tracker with the list of
                images being operated on."""
                # Attribute defined outside __init__; pylint: disable=W0201
                self.linked_running = sorted(lin_running)
                self._li_recurse_status_output(done)

        def li_recurse_output(self, lin, stdout, stderr):
                """Call to display output from linked image operations."""
                self._li_recurse_output_output(lin, stdout, stderr)

        def li_recurse_progress(self, lin):
                """Call to indicate that the named child made progress."""
                self._li_recurse_progress_output(lin)

        def reversion_start(self, goal_pkgs, goal_revs):
                self.reversion_adjs.reset()
                self.reversion_revs.reset()
                self.reversion_pkgs.reset()
                self.reversion_revs.goalitems = goal_revs
                self.reversion_pkgs.goalitems = goal_pkgs
                self.reversion_adjs.goalitems = -1

        def reversion_add_progress(self, pfmri, pkgs=0, reversioned=0,
            adjusted=0):
                outspec = OutSpec()
                if not self.reversion_pkgs.printed:
                        self.reversion_pkgs.printed = True
                        outspec.first = True

                self.reversion_revs.items += reversioned
                self.reversion_adjs.items += adjusted
                self.reversion_pkgs.items += pkgs
                self._reversion(pfmri, outspec)

        def reversion_done(self):
                self.reversion_pkgs.done()
                self.reversion_revs.done()
                self.reversion_adjs.done(goalcheck=False)
                if self.reversion_pkgs.printed:
                        self._reversion("Done", OutSpec(last=True))


class MultiProgressTracker(ProgressTrackerFrontend):
        """This class is a proxy, dispatching incoming progress tracking calls
        to one or more contained (in self._trackers) additional progress
        trackers.  So, you can use this class to route progress tracking calls
        to multiple places at once (for example, to the screen and to a log
        file).

        We hijack most of the methods of the front-end superclass, except for
        the constructor.  For each hijacked method, we substitute a closure of
        the multido() routine bound with the appropriate arguments."""

        def __init__(self, ptlist):
                ProgressTrackerFrontend.__init__(self)

                self._trackers = [t for t in ptlist]
                if len(self._trackers) == 0:
                        raise ProgressTrackerException("No trackers specified")

                #
                # Returns a multido closure, which will iterate and call the
                # named method for each tracker registered with the class.
                #
                def make_multido(method_name):
                        # self and method_name are bound in this context.
                        def multido(*args, **kwargs):
                                for trk in self._trackers:
                                        f = getattr(trk, method_name)
                                        f(*args, **kwargs)
                        return multido

                #
                # Look in the ProgressTrackerFrontend for a list of frontend
                # methods to multiplex.
                #
                for methname, m in six.iteritems(
                    ProgressTrackerFrontend.__dict__):
                        if methname == "__init__":
                                continue
                        if not inspect.isfunction(m):
                                continue
                        # Override all methods which aren't the constructor.
                        # Yes, this is a big hammer.
                        setattr(self, methname, make_multido(methname))
                return


class QuietProgressTracker(ProgressTracker):
        """This progress tracker outputs nothing, but is semantically
        intended to be "quiet."  See also NullProgressTracker below."""

        #
        # At construction, we inspect the ProgressTrackerBackend abstract
        # superclass, and implement all of its methods as empty stubs.
        #
        def __init__(self):
                ProgressTracker.__init__(self)

                # We modify the object such that all of the methods it needs to
                # implement are set to this __donothing empty method.

                def __donothing(*args, **kwargs):
                        # Unused argument 'args', 'kwargs';
                        #     pylint: disable=W0613
                        pass

                for methname in ProgressTrackerBackend.__dict__:
                        if methname == "__init__":
                                continue
                        boundmeth = getattr(self, methname)
                        if not inspect.ismethod(boundmeth):
                                continue
                        setattr(self, methname, __donothing)


class NullProgressTracker(QuietProgressTracker):
        """This ProgressTracker is a subclass of QuietProgressTracker because
        that's convenient for now.  It is semantically intended to be a no-op
        progress tracker, and is useful for short-running operations which
        need not display progress of any kind.

        This subclass should be used by external consumers wanting to create
        their own ProgressTracker class as any new output methods added to the
        ProgressTracker class will also be handled here, insulating them from
        additions to the ProgressTracker class."""


class FunctionProgressTracker(ProgressTracker):
        """This ProgressTracker is principally used for debugging.
        Essentially it uses method replacement in order to create a
        "tracing" ProgressTracker that shows calls to front end methods
        and calls from the frontend to the backend."""

        #
        # When an instance of this class is initialized, we use inspection to
        # insert a new method for each method; for frontend methods "chain"
        # the old one behind the new one.  The new method dumps out the
        # arguments.
        #
        def __init__(self, output_file=sys.stdout):
                ProgressTracker.__init__(self)
                self.output_file = output_file

                def __donothing(*args, **kwargs):
                        # Unused argument 'args', 'kwargs';
                        #     pylint: disable=W0613
                        pass

                # We modify the instance such that all of the methods it needs
                # to implement are set to this __printargs method.
                def make_printargs(methname, chainedmeth):
                        def __printargs(*args, **kwargs):
                                s = ""
                                for x in args:
                                        s += "{0}, ".format(str(x))
                                for x in sorted(kwargs):
                                        s += "{0}={1}, ".format(x, kwargs[x])
                                s = s[:-2]

                                #
                                # Invoke chained method implementation; it's
                                # counter-intuitive, but we do this before
                                # printing things out, because under the
                                # circumstances we create in
                                # test_progress_tracker(), the chained method
                                # could throw an exception, aborting an
                                # upstream MultiProgressTracker's multido(),
                                # and spoiling the test_multi() test case.
                                #
                                chainedmeth(*args, **kwargs)
                                print("{0}({1})".format(methname, s),
                                    file=self.output_file)

                        return __printargs

                for methname in ProgressTrackerFrontend.__dict__:
                        if methname == "__init__":
                                continue
                        #
                        # this gets us the bound method, which we say here
                        # is "chained"-- we'll call it next after our inserted
                        # method.
                        #
                        chainedmeth = getattr(self, methname, None)
                        if not inspect.ismethod(chainedmeth):
                                continue
                        setattr(self, methname,
                            make_printargs(methname, chainedmeth))

                for methname in ProgressTrackerBackend.__dict__:
                        if methname == "__init__":
                                continue
                        chainedmeth = getattr(self, methname, None)
                        if not inspect.ismethod(chainedmeth):
                                continue
                        chainedmeth = __donothing
                        setattr(self, methname,
                            make_printargs(methname, chainedmeth))


class DotProgressTracker(ProgressTracker):
        """This tracker writes a series of dots for every operation.
        This is intended for use by linked images."""

        TERM_DELAY = 0.1

        def __init__(self, output_file=sys.stdout, term_delay=TERM_DELAY):
                ProgressTracker.__init__(self)

                self._pe = printengine.POSIXPrintEngine(output_file,
                    ttymode=False)
                self._ptimer = PrintTimer(term_delay)

                def make_dot():
                        def dot(*args, **kwargs):
                                # Unused argument 'args', 'kwargs';
                                #     pylint: disable=W0613
                                if self._ptimer.time_to_print():
                                        self._pe.cprint(".", end='')
                        return dot

                for methname in ProgressTrackerBackend.__dict__:
                        if methname == "__init__":
                                continue
                        boundmeth = getattr(self, methname, None)
                        if not inspect.ismethod(boundmeth):
                                continue
                        setattr(self, methname, make_dot())


class CommandLineProgressTracker(ProgressTracker):
        """This progress tracker is a generically useful tracker for command
        line output.  It needs no special terminal features and so is
        appropriate for sending through a pipe.  This code is intended to be
        platform neutral."""

        # Default to printing periodic output every 5 seconds.
        TERM_DELAY = 5.0

        def __init__(self, output_file=sys.stdout, print_engine=None,
            term_delay=TERM_DELAY):
                ProgressTracker.__init__(self)
                if not print_engine:
                        self._pe = printengine.POSIXPrintEngine(output_file,
                            ttymode=False)
                else:
                        self._pe = print_engine
                self._ptimer = PrintTimer(term_delay)

        def _phase_prefix(self):
                if self.major_phase == self.PHASE_UTILITY:
                        return ""

                # The following string was originally expressed as
                # "%*s: ". % \
                #     (self.phase_max_width, self.phase_names[self.major_phase]
                #     )
                # however xgettext incorrectly flags this as an improper use of
                # non-parameterized messages, which gets detected as an error
                # during our build.  So instead, we express the string using
                # an equivalent <str>.format(..) function
                s = _("{{phase:>{0:d}}}: ").format(self.phase_max_width)
                return s.format(phase=self.phase_names[self.major_phase])

        #
        # Helper routines
        #
        def __generic_start(self, msg):
                # In the case of listing/up-to-date check operations, we
                # we don't want to output planning information, so skip.
                if self.purpose != self.PURPOSE_NORMAL:
                        return
                self._pe.cprint(self._phase_prefix() + msg, end='')
                # indicate that we just printed.
                self._ptimer.reset_now()

        def __generic_done(self, msg=None):
                # See __generic_start above.
                if self.purpose != self.PURPOSE_NORMAL:
                        return
                if msg is None:
                        msg = " " + _("Done")
                self._pe.cprint(msg, end='\n')
                self._ptimer.reset()

        def __generic_done_item(self, item, msg=None):
                # See __generic_start above.
                if self.purpose != self.PURPOSE_NORMAL:
                        return
                if msg is None:
                        if global_settings.client_output_verbose > 0:
                                msg = " " + _("Done ({elapsed:>.3f}s)")
                        else:
                                msg = " " + _("Done")
                outmsg = msg.format(elapsed=item.elapsed())
                self._pe.cprint(outmsg, end='\n')
                self._ptimer.reset()

        #
        # Overridden methods from ProgressTrackerBackend
        #
        def _output_flush(self):
                self._pe.flush()

        def _change_purpose(self, op, np):
                self._ptimer.reset()
                if np == self.PURPOSE_PKG_UPDATE_CHK:
                        self._pe.cprint(self._phase_prefix() +
                            _("Checking that pkg(5) is up to date ..."), end='')
                if op == self.PURPOSE_PKG_UPDATE_CHK:
                        self._pe.cprint(" "  + _("Done"))

        def _cache_cats_output(self, outspec):
                if outspec.first:
                        self.__generic_start(_("Caching catalogs ..."))
                if outspec.last:
                        self.__generic_done()

        def _load_cat_cache_output(self, outspec):
                if outspec.first:
                        self.__generic_start(_("Loading catalog cache ..."))
                if outspec.last:
                        self.__generic_done()

        def _refresh_output_progress(self, outspec):
                # See __generic_start above.
                if self.purpose != self.PURPOSE_NORMAL:
                        return
                if "startpublisher" in outspec.changed:
                        p = self.pub_refresh.curinfo.prefix
                        if self.refresh_target_catalog:
                                m = _("Retrieving target catalog '{0}' "
                                    "...").format(p)
                        elif self.refresh_full_refresh:
                                m = _("Retrieving catalog '{0}' ...").format(p)
                        else:
                                m = _("Refreshing catalog '{0}' ...").format(p)
                        self.__generic_start(m)
                elif "endpublisher" in outspec.changed:
                        self.__generic_done()

        def _plan_output(self, outspec, planitem):
                if outspec.first:
                        self.__generic_start(_("{0} ...").format(planitem.name))
                if outspec.last:
                        self.__generic_done_item(planitem)

        def _plan_output_all_done(self):
                self.__generic_done(self._phase_prefix() + \
                    _("Planning completed in {0:>.2f} seconds").format(
                    self.plan_generic.elapsed()))

        def _mfst_fetch(self, outspec):
                if not self._ptimer.time_to_print() and \
                    not outspec.first and not outspec.last:
                        return
                if self.purpose != self.PURPOSE_NORMAL:
                        return

                # Reset timer; this prevents double printing for
                # outspec.first and then again for the timer expiration
                if outspec.first:
                        self._ptimer.reset_now()

                #
                # There are a couple of reasons we might fetch manifests--
                # pkgrecv, pkglint, etc. can all do this.  _phase_prefix()
                # adjusts the output based on the major phase.
                #
                self._pe.cprint(self._phase_prefix() +
                    _("Fetching manifests: {num}  {pctcomplete}% "
                    "complete").format(
                    num=self.mfst_fetch.pair(),
                    pctcomplete=int(self.mfst_fetch.pctdone())))

        def _mfst_commit(self, outspec):
                # For now, manifest commit is hard to handle in this
                # line-oriented prog tracker, as we alternate back and forth
                # between fetching and committing, and we don't want to
                # spam the user with this too much.
                pass

        def _repo_ver_output(self, outspec, repository_scan=False):
                pass

        def _repo_ver_output_error(self, errors):
                self._pe.cprint(errors)

        def _repo_ver_output_warning(self, warnings):
                pass

        def _repo_ver_output_info(self, info):
                pass

        def _repo_ver_output_done(self):
                pass

        def _repo_fix_output(self, outspec):
                pass

        def _repo_fix_output_error(self, errors):
                self._pe.cprint(errors)

        def _repo_fix_output_info(self, info):
                self._pe.cprint(info)

        def _repo_fix_output_done(self):
                pass

        def _dl_output(self, outspec):
                if not self._ptimer.time_to_print() and not outspec.first and \
                    not outspec.last:
                        return

                # Reset timer; this prevents double printing for
                # outspec.first and then again for the timer expiration
                if outspec.first:
                        self._ptimer.reset_now()

                if not outspec.last:
                        speed = self.dl_estimator.get_speed_estimate()
                else:
                        speed = self.dl_estimator.get_final_speed()
                speedstr = "" if speed is None else \
                    "({0})".format(self.dl_estimator.format_speed(speed))

                if not outspec.last:
                        # 'first' or time to print
                        mbs = format_pair("{0:.1f}", self.dl_bytes.items,
                            self.dl_bytes.goalitems, scale=(1024 * 1024))
                        self._pe.cprint(
                            _("Download: {num} items  {mbs}MB  "
                            "{pctcomplete}% complete {speed}").format(
                            num=self.dl_files.pair(), mbs=mbs,
                            pctcomplete=int(self.dl_bytes.pctdone()),
                            speed=speedstr))
                else:
                        # 'last'
                        goal = misc.bytes_to_str(self.dl_bytes.goalitems)
                        self.__generic_done(
                            msg=_("Download: Completed {num} in {sec:>.2f} "
                            "seconds {speed}").format(
                            num=goal, sec=self.dl_estimator.elapsed(),
                            speed=speedstr))

        def _republish_output(self, outspec):
                if "startpkg" in outspec.changed:
                        pkgfmri = self.repub_pkgs.curinfo
                        self.__generic_start(_("Republish: {0} ... ").format(
                            pkgfmri.get_fmri(anarchy=True)))
                if "endpkg" in outspec.changed:
                        self.__generic_done()

        def _archive_output(self, outspec):
                if not self._ptimer.time_to_print() and not outspec:
                        return
                if outspec.first:
                        # tell ptimer that we just printed.
                        self._ptimer.reset_now()

                if outspec.last:
                        goal = misc.bytes_to_str(self.archive_bytes.goalitems)
                        self.__generic_done(
                            msg=_("Archiving: Completed {num} in {secs:>.2f} "
                            "seconds").format(
                            num=goal, secs=self.archive_items.elapsed()))
                        return

                mbs = format_pair("{0:.1f}", self.archive_bytes.items,
                    self.archive_bytes.goalitems, scale=(1024 * 1024))
                self._pe.cprint(
                    _("Archiving: {pair} items  {mbs}MB  {pctcomplete}% "
                    "complete").format(
                    pair=self.archive_items.pair(), mbs=mbs,
                    pctcomplete=int(self.archive_bytes.pctdone())))

        #
        # The progress tracking infrastructure wants to tell us about each
        # kind of action activity (install, remove, update).  For this
        # progress tracker, we don't really care to expose that to the user,
        # so we work in terms of total actions instead.
        #
        def _act_output(self, outspec, actionitem):
                if not self._ptimer.time_to_print() and not outspec.first:
                        return
                # reset timer, since we're definitely printing now...
                self._ptimer.reset_now()
                total_actions = \
                    sum(x.items for x in self._actionitems.values())
                total_goal = \
                    sum(x.goalitems for x in self._actionitems.values())
                self._pe.cprint(self._phase_prefix() +
                    _("{num} actions ({type})").format(
                    num=format_pair("{0:d}", total_actions, total_goal),
                    type=actionitem.name))

        def _act_output_all_done(self):
                total_goal = \
                    sum(x.goalitems for x in self._actionitems.values())
                total_time = \
                    sum(x.elapsed() for x in self._actionitems.values())
                if total_goal == 0:
                        return
                self._pe.cprint(self._phase_prefix() +
                    _("Completed {numactions:d} actions in {time:>.2f} "
                    "seconds.").format(
                    numactions=total_goal, time=total_time))

        def _job_output(self, outspec, jobitem):
                if outspec.first:
                        self.__generic_start("{0} ... ".format(jobitem.name))
                if outspec.last:
                        self.__generic_done_item(jobitem)

        def _lint_output(self, outspec):
                if outspec.first:
                        if self.lint_phasetype == self.LINT_PHASETYPE_SETUP:
                                self._pe.cprint("{0} ... ".format(
                                    self.lintitems.name), end='')
                        elif self.lint_phasetype == self.LINT_PHASETYPE_EXECUTE:
                                self._pe.cprint("# --- {0} ---".format(
                                    self.lintitems.name))
                if outspec.last:
                        if self.lint_phasetype == self.LINT_PHASETYPE_SETUP:
                                self.__generic_done()
                        elif self.lint_phasetype == self.LINT_PHASETYPE_EXECUTE:
                                pass

        def _li_recurse_start_output(self):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        self.__generic_start(
                            _("Linked image publisher check ..."))
                        return

        def _li_recurse_end_output(self):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        self.__generic_done()
                        return
                self._pe.cprint(self._phase_prefix() +
                    _("Finished processing linked images."))

        def __li_dump_output(self, output):
                if not output:
                        return
                lines = output.splitlines()
                nlines = len(lines)
                for linenum, line in enumerate(lines):
                        line = misc.force_str(line)
                        if linenum < nlines - 1:
                                self._pe.cprint("| " + line)
                        else:
                                if lines[linenum].strip() != "":
                                        self._pe.cprint("| " + line)
                                self._pe.cprint("`")

        def _li_recurse_output_output(self, lin, stdout, stderr):
                if not stdout and not stderr:
                        return
                self._pe.cprint(self._phase_prefix() +
                    _("Linked image '{0}' output:").format(lin))
                self.__li_dump_output(stdout)
                self.__li_dump_output(stderr)

        def _li_recurse_status_output(self, done):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        return

                running = " ".join([str(i) for i in self.linked_running])
                msg = _("Linked images: {pair} done; {numworking:d} working: "
                    "{running}").format(
                    pair=format_pair("{0:d}", done, self.linked_total),
                    numworking=len(self.linked_running),
                    running=running)
                self._pe.cprint(self._phase_prefix() + msg)

        def _li_recurse_progress_output(self, lin):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        return

        def _reversion(self, pfmri, outspec):
                if not self._ptimer.time_to_print() and not outspec:
                        return

                if outspec.first:
                        # tell ptimer that we just printed.
                        self._ptimer.reset_now()

                if outspec.last:
                        self.__generic_done(
                            msg=_("Reversioned {revs} of {pkgs} packages "
                            "and adjusted {adjs} packages.").format(
                            revs=self.reversion_revs.items,
                            pkgs=self.reversion_pkgs.items,
                            adjs=self.reversion_adjs.items))
                        return

                self._pe.cprint(
                    _("Reversioning: {pkgs} processed, {revs} reversioned, "
                    "{adjs} adjusted").format(
                    pkgs=self.reversion_pkgs.pair(),
                    revs=self.reversion_revs.pair(),
                    adjs=self.reversion_adjs.items))


class RADProgressTracker(CommandLineProgressTracker):
        """This progress tracker is a subclass of CommandLineProgressTracker
        which is specific for RAD progress event.
        """

        # Default to printing periodic output every 5 seconds.
        TERM_DELAY = 5.0

        # Output constants.
        O_PHASE = "phase"
        O_MESSAGE = "message"
        O_TIME = "time_taken"
        O_TIME_U = "time_unit"
        O_TYPE = "type"
        O_PRO_ITEMS = "processed_items"
        O_GOAL_ITEMS = "goal_items"
        O_PCT_DONE = "percent_done"
        O_ITEM_U = "item_unit"
        O_SPEED = "speed"
        O_RUNNING = "running"
        O_GOAL_PRO_ITEMS = "goal_processed_items"
        O_REV_ITEMS = "reversioned_items"
        O_GOAL_REV_ITEMS = "goal_reversion_items"
        O_ADJ_ITEMS = "adjusted_items"
        O_LI_OUTPUT = "li_output"
        O_LI_ERROR = "li_errors"

        def __init__(self, term_delay=TERM_DELAY, prog_event_handler=None):
                CommandLineProgressTracker.__init__(self,
                    term_delay=term_delay)
                self.__prog_event_handler = prog_event_handler

        def _phase_prefix(self):
                if self.major_phase == self.PHASE_UTILITY:
                        return "Utility"

                return self.phase_names[self.major_phase]

        #
        # Helper routines
        #
        def __prep_prog_json(self, msg=None, phase=None, prog_json=None):
                # prepare progress json.
                phase_name = self._phase_prefix()
                if phase:
                        phase_name = phase
                if prog_json:
                        return prog_json
                else:
                        return {self.O_PHASE: phase_name,
                            self.O_MESSAGE: msg}

        def __handle_prog_output(self, prog_json, end="\n"):
                # If event handler is set, report an event. Otherwise, print.
                if self.__prog_event_handler:
                        self.__prog_event_handler(event=prog_json)
                else:
                        self._pe.cprint(json.dumps(prog_json), end=end)

        def __generic_start(self, msg):
                # In the case of listing/up-to-date check operations, we
                # don't want to output planning information, so skip.
                if self.purpose != self.PURPOSE_NORMAL:
                        return

                prog_json = self.__prep_prog_json(msg)
                self.__handle_prog_output(prog_json)
                # indicate that we just printed.
                self._ptimer.reset_now()

        def __generic_done(self, msg=None, phase=None, prog_json=None):
                # See __generic_start above.
                if self.purpose != self.PURPOSE_NORMAL:
                        return
                if msg is None:
                        msg = _("Done")
                prog_json = self.__prep_prog_json(msg, phase, prog_json)
                self.__handle_prog_output(prog_json, end='\n')
                self._ptimer.reset()

        def __generic_done_item(self, item, msg=None):
                # See __generic_start above.
                if self.purpose != self.PURPOSE_NORMAL:
                        return
                if msg is None:
                        if global_settings.client_output_verbose > 0:
                                msg = _("Done ({elapsed:>.3f}s)")
                        else:
                                msg = _("Done")
                outmsg = msg.format(elapsed=item.elapsed())
                prog_json = self.__prep_prog_json(outmsg)
                self.__handle_prog_output(prog_json, end='\n')
                self._ptimer.reset()

        def _change_purpose(self, op, np):
                self._ptimer.reset()
                if np == self.PURPOSE_PKG_UPDATE_CHK:
                        prog_json = self.__prep_prog_json(
                            _("Checking that pkg(5) is up to date ..."))
                        self.__handle_prog_output(prog_json)

        def _cache_cats_output(self, outspec):
                if outspec.first:
                        self.__generic_start(_("Caching catalogs ..."))
                if outspec.last:
                        self.__generic_done()

        def _load_cat_cache_output(self, outspec):
                if outspec.first:
                        self.__generic_start(_("Loading catalog cache ..."))
                if outspec.last:
                        self.__generic_done()

        def _refresh_output_progress(self, outspec):
                # See __generic_start above.
                if self.purpose != self.PURPOSE_NORMAL:
                        return
                if "startpublisher" in outspec.changed:
                        p = self.pub_refresh.curinfo.prefix
                        if self.refresh_target_catalog:
                                m = _("Retrieving target catalog '{0}' "
                                    "...").format(p)
                        elif self.refresh_full_refresh:
                                m = _("Retrieving catalog '{0}' ...").format(p)
                        else:
                                m = _("Refreshing catalog '{0}' ...").format(p)
                        self.__generic_start(m)
                elif "endpublisher" in outspec.changed:
                        self.__generic_done()

        def _plan_output(self, outspec, planitem):
                if outspec.first:
                        self.__generic_start(_("{0} ...").format(planitem.name))
                if outspec.last:
                        self.__generic_done_item(planitem)

        def _plan_output_all_done(self):
                prog_json = {self.O_PHASE: self._phase_prefix(),
                    self.O_MESSAGE: _("Planning completed"),
                    self.O_TIME: self.plan_generic.elapsed(),
                    self.O_TIME_U: _("second")}
                self.__generic_done(prog_json=prog_json)

        def _mfst_fetch(self, outspec):
                if not self._ptimer.time_to_print() and \
                    not outspec.first and not outspec.last:
                        return
                if self.purpose != self.PURPOSE_NORMAL:
                        return

                # Reset timer; this prevents double printing for
                # outspec.first and then again for the timer expiration
                if outspec.first:
                        self._ptimer.reset_now()

                #
                # There are a couple of reasons we might fetch manifests--
                # pkgrecv, pkglint, etc. can all do this.  _phase_prefix()
                # adjusts the output based on the major phase.
                #
                goalitems = self.mfst_fetch.goalitems
                if goalitems == None:
                        goalitems = 0
                prog_json = {self.O_PHASE: self._phase_prefix(),
                    self.O_MESSAGE: _("Fetching manifests"),
                    self.O_PRO_ITEMS: self.mfst_fetch.items,
                    self.O_GOAL_ITEMS: goalitems,
                    self.O_PCT_DONE: int(self.mfst_fetch.pctdone()),
                    self.O_ITEM_U: _("manifest")
                    }
                self.__handle_prog_output(prog_json)

        def _dl_output(self, outspec):
                if not self._ptimer.time_to_print() and not outspec.first and \
                    not outspec.last:
                        return

                # Reset timer; this prevents double printing for
                # outspec.first and then again for the timer expiration
                if outspec.first:
                        self._ptimer.reset_now()

                if not outspec.last:
                        speed = self.dl_estimator.get_speed_estimate()
                else:
                        speed = self.dl_estimator.get_final_speed()
                speedstr = "" if speed is None else \
                    "({0})".format(self.dl_estimator.format_speed(speed))

                if not outspec.last:
                        # 'first' or time to print
                        prog_json = {
                            self.O_PHASE: self._phase_prefix(),
                            self.O_MESSAGE: _("Downloading"),
                            self.O_PRO_ITEMS: self.dl_bytes.items,
                            self.O_GOAL_ITEMS: self.dl_bytes.goalitems,
                            self.O_PCT_DONE: int(self.dl_bytes.pctdone()),
                            self.O_SPEED: speedstr,
                            self.O_ITEM_U: _("byte")
                            }
                        self.__handle_prog_output(prog_json)
                else:
                        # 'last'
                        prog_json = {self.O_PHASE: self._phase_prefix(),
                            self.O_MESSAGE: _("Download completed"),
                            self.O_PRO_ITEMS: self.dl_bytes.goalitems,
                            self.O_SPEED: speedstr,
                            self.O_ITEM_U: _("byte"),
                            self.O_TIME: self.dl_estimator.elapsed(),
                            self.O_TIME_U: _("second")
                            }
                        self.__generic_done(prog_json=prog_json)

        def _republish_output(self, outspec):
                if "startpkg" in outspec.changed:
                        pkgfmri = self.repub_pkgs.curinfo
                        self.__generic_start(_("Republish: {0} ... ").format(
                            pkgfmri.get_fmri(anarchy=True)))
                if "endpkg" in outspec.changed:
                        self.__generic_done()

        def _archive_output(self, outspec):
                if not self._ptimer.time_to_print() and not outspec:
                        return
                if outspec.first:
                        # tell ptimer that we just printed.
                        self._ptimer.reset_now()

                if outspec.last:
                        prog_json = {self.O_PHASE: self._phase_prefix(),
                            self.O_MESSAGE: _("Archiving completed"),
                            self.O_PRO_ITEMS: self.archive_bytes.goalitems,
                            self.O_ITEM_U: _("byte"),
                            self.O_TIME: self.archive_items.elapsed(),
                            self.O_TIME_U: _("second")
                            }
                        self.__generic_done(prog_json=prog_json)
                        return

                prog_json = {self.O_PHASE: self._phase_prefix(),
                    self.O_MESSAGE: _("Archiving"),
                    self.O_PRO_ITEMS: self.archive_bytes.items,
                    self.O_GOAL_ITEMS: self.archive_bytes.goalitems,
                    self.O_PCT_DONE: int(self.archive_bytes.pctdone()),
                    self.O_ITEM_U: _("byte")
                    }
                self.__handle_prog_output(prog_json)

        #
        # The progress tracking infrastructure wants to tell us about each
        # kind of action activity (install, remove, update).  For this
        # progress tracker, we don't really care to expose that to the user,
        # so we work in terms of total actions instead.
        #
        def _act_output(self, outspec, actionitem):
                if not self._ptimer.time_to_print() and not outspec.first:
                        return
                # reset timer, since we're definitely printing now...
                self._ptimer.reset_now()
                total_actions = \
                    sum(x.items for x in self._actionitems.values())
                total_goal = \
                    sum(x.goalitems for x in self._actionitems.values())
                prog_json = {self.O_PHASE: self._phase_prefix(),
                    self.O_MESSAGE: _("Action activity"),
                    self.O_PRO_ITEMS: total_actions,
                    self.O_GOAL_ITEMS: total_goal,
                    self.O_TYPE: actionitem.name,
                    self.O_ITEM_U: _("action")
                    }
                self.__handle_prog_output(prog_json)

        def _act_output_all_done(self):
                total_goal = \
                    sum(x.goalitems for x in self._actionitems.values())
                total_time = \
                    sum(x.elapsed() for x in self._actionitems.values())
                if total_goal == 0:
                        return

                prog_json = {self.O_PHASE: self._phase_prefix(),
                    self.O_MESSAGE: _("Completed actions activities"),
                    self.O_PRO_ITEMS: total_goal,
                    self.O_ITEM_U: _("action"),
                    self.O_TIME: total_time,
                    self.O_TIME_U: _("second")
                    }
                self.__handle_prog_output(prog_json)

        def _job_output(self, outspec, jobitem):
                if outspec.first:
                        self.__generic_start("{0} ... ".format(jobitem.name))
                if outspec.last:
                        self.__generic_done_item(jobitem)

        def _lint_output(self, outspec):
                if outspec.first:
                        if self.lint_phasetype == self.LINT_PHASETYPE_SETUP:
                                msg = "{0} ... ".format(
                                    self.lintitems.name)
                                prog_json = {self.O_PHASE: _("Setup"),
                                    self.O_MESSAGE: msg
                                    }
                                self.__handle_prog_output(prog_json)
                        elif self.lint_phasetype == self.LINT_PHASETYPE_EXECUTE:
                                msg = "# --- {0} ---".format(
                                    self.lintitems.name)
                                prog_json = {self.O_PHASE: _("Execute"),
                                    self.O_MESSAGE: msg
                                    }
                                self.__handle_prog_output(prog_json)
                if outspec.last:
                        if self.lint_phasetype == self.LINT_PHASETYPE_SETUP:
                                self.__generic_done(phase=_("Setup"))
                        elif self.lint_phasetype == self.LINT_PHASETYPE_EXECUTE:
                                pass

        def _li_recurse_start_output(self):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        self.__generic_start(
                            _("Linked image publisher check ..."))
                        return

        def _li_recurse_end_output(self):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        self.__generic_done()
                        return
                prog_json = self.__prep_prog_json(
                    _("Finished processing linked images."))
                self.__handle_prog_output(prog_json)

        def __li_dump_output(self, output):
                if not output:
                        return []
                lines = output.splitlines()
                return lines

        def _li_recurse_output_output(self, lin, stdout, stderr):
                if not stdout and not stderr:
                        return
                prog_json = {self.O_PHASE: self._phase_prefix(),
                    self.O_MESSAGE: _("Linked image '{0}' output:").format(lin)}
                prog_json[self.O_LI_OUTPUT] = self.__li_dump_output(stdout)
                prog_json[self.O_LI_ERROR] = self.__li_dump_output(stderr)
                self.__handle_prog_output(prog_json)

        def _li_recurse_status_output(self, done):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        return

                prog_json = {self.O_PHASE: self._phase_prefix(),
                    self.O_MESSAGE: _("Linked images status"),
                    self.O_PRO_ITEMS: done,
                    self.O_GOAL_ITEMS: self.linked_total,
                    self.O_ITEM_U: _("linked image"),
                    self.O_RUNNING: [str(i) for i in self.linked_running]
                    }

                self.__handle_prog_output(prog_json)

        def _li_recurse_progress_output(self, lin):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        return

        def _reversion(self, pfmri, outspec):
                if not self._ptimer.time_to_print() and not outspec:
                        return

                if outspec.first:
                        # tell ptimer that we just printed.
                        self._ptimer.reset_now()

                if outspec.last:
                        prog_json = {self.O_PHASE: _("Reversion"),
                            self.O_MESSAGE: _("Done"),
                            self.O_PRO_ITEMS: self.reversion_pkgs.items,
                            self.O_REV_ITEMS: self.reversion_revs.items,
                            self.O_ADJ_ITEMS: self.reversion_adjs.items,
                            self.O_ITEM_U: _("package")
                            }
                        self.__generic_done(prog_json=prog_json)
                        return

                prog_json = {self.O_PHASE: _("Reversion"),
                    self.O_MESSAGE: "Reversioning",
                    self.O_PRO_ITEMS: self.reversion_pkgs.items,
                    self.O_GOAL_PRO_ITEMS: self.reversion_pkgs.goalitems,
                    self.O_REV_ITEMS: self.reversion_revs.items,
                    self.O_GOAL_REV_ITEMS: self.reversion_revs.goalitems,
                    self.O_ADJ_ITEMS: self.reversion_adjs.items,
                    self.O_ITEM_U: _("package")
                    }
                self.__handle_prog_output(prog_json)

        @classmethod
        def get_json_schema(cls):
                """Construct json schema."""

                json_schema = {"$schema":
                    "http://json-schema.org/draft-04/schema#",
                    "title": "progress schema",
                    "type": "object",
                    "properties": {cls.O_PHASE:  {"type": "string"},
                        cls.O_MESSAGE: {"type": "string"},
                        cls.O_TIME: {"type": "number"},
                        cls.O_TIME_U: {"type": "string"},
                        cls.O_TYPE: {"type": "string"},
                        cls.O_PRO_ITEMS: {"type": "number"},
                        cls.O_GOAL_ITEMS: {"type": "number"},
                        cls.O_PCT_DONE: {"type": "number"},
                        cls.O_ITEM_U: {"type": "string"},
                        cls.O_SPEED: {"type": "string"},
                        cls.O_RUNNING: {"type": "array"},
                        cls.O_GOAL_PRO_ITEMS: {"type": "number"},
                        cls.O_REV_ITEMS : {"type": "number"},
                        cls.O_GOAL_REV_ITEMS: {"type": "number"},
                        cls.O_ADJ_ITEMS: {"type": "number"},
                        cls.O_LI_OUTPUT : {"type": "array"},
                        cls.O_LI_ERROR : {"type": "array"},
                        },
                    "required":  [cls.O_PHASE, cls.O_MESSAGE]
                }
                return json_schema

class LinkedChildProgressTracker(CommandLineProgressTracker):
        """This tracker is used for recursion with linked children.
        This is intended for use only by linked images."""

        def __init__(self, output_file):
                CommandLineProgressTracker.__init__(self, output_file)

                # We modify the instance such that everything except for the
                # linked image methods are no-opped out.  In multi-level
                # recursion, this ensures that output from children is
                # displayed.

                def __donothing(*args, **kwargs):
                        # Unused argument 'args', 'kwargs';
                        #     pylint: disable=W0613
                        pass

                for methname in ProgressTrackerBackend.__dict__:
                        if methname == "__init__":
                                continue
                        if methname.startswith("_li_recurse"):
                                continue
                        boundmeth = getattr(self, methname)
                        if not inspect.ismethod(boundmeth):
                                continue
                        setattr(self, methname, __donothing)

class FancyUNIXProgressTracker(ProgressTracker):
        """This progress tracker is designed for UNIX-like OS's-- those which
        have UNIX-like terminal semantics.  It attempts to load the 'curses'
        package.  If that or other terminal-liveness tests fail, it gives up:
        the client should pick some other more suitable tracker.  (Probably
        CommandLineProgressTracker)."""

        #
        # The minimum interval (in seconds) at which we should update the
        # display during operations which produce a lot of output.  Needed to
        # avoid spamming a slow terminal.
        #
        TERM_DELAY = 0.10
        TERM_DELAY_SLOW = 0.25

        def __init__(self, output_file=sys.stdout, term_delay=None):
                ProgressTracker.__init__(self)

                try:
                        self._pe = printengine.POSIXPrintEngine(output_file,
                            ttymode=True)
                except printengine.PrintEngineException as e:
                        raise ProgressTrackerException(
                            "Couldn't create print engine: {0}".format(
                            " ".join(e.args)))

                if term_delay is None:
                        term_delay = self.TERM_DELAY_SLOW if self._pe.isslow() \
                            else self.TERM_DELAY
                self._ptimer = PrintTimer(term_delay)

                self._phases_hdr_printed = False
                self._jobs_lastjob = None

                if not output_file.isatty():
                        raise ProgressTrackerException(
                            "output_file is not a TTY")

                self.__spinner_chars = "|/-\\"

                # For linked image spinners.
                self.__linked_spinners = []

        #
        # Overridden methods from ProgressTrackerBackend
        #
        def _output_flush(self):
                self._pe.flush()

        def __generic_start(self, msg):
                # Ensure the last message displayed is flushed in case the
                # corresponding operation did not complete successfully.
                self.__generic_done()
                self._pe.cprint(msg, end='', erase=True)

        def __generic_done(self):
                self._pe.cprint("", end='', erase=True)
                self._ptimer.reset()

        def __generic_done_newline(self):
                self._pe.cprint("")
                self._ptimer.reset()

        def _spinner(self):
                sp = self._ptimer.print_value % len(self.__spinner_chars)
                return self.__spinner_chars[sp]

        def _up2date(self):
                if not self._ptimer.time_to_print():
                        return
                self._pe.cprint(
                    _("Checking that pkg(5) is up to date {0}").format(
                    self._spinner()), end='', erase=True)

        # Unused argument 'op'; pylint: disable=W0613
        def _change_purpose(self, op, np):
                self._ptimer.reset()
                if np == self.PURPOSE_PKG_UPDATE_CHK:
                        self._up2date()

        def _cache_cats_output(self, outspec):
                if outspec.first:
                        self.__generic_start(_("Caching catalogs ..."))
                if outspec.last:
                        self.__generic_done()

        def _load_cat_cache_output(self, outspec):
                if outspec.first:
                        self.__generic_start(_("Loading catalog cache ..."))
                if outspec.last:
                        self.__generic_done()

        def _refresh_output_progress(self, outspec):
                if self.purpose == self.PURPOSE_PKG_UPDATE_CHK:
                        self._up2date()
                        return
                if self._ptimer.time_to_print() and not outspec:
                        return

                # for very small xfers (like when we just get the attrs) this
                # isn't very interesting, so elide it.
                if self.pub_refresh_bytes.items <= 32 * 1024:
                        nbytes = ""
                else:
                        nbytes = " " + \
                            misc.bytes_to_str(self.pub_refresh_bytes.items)

                if self.refresh_target_catalog:
                        prefix = _("Retrieving target catalog")
                elif self.refresh_full_refresh:
                        prefix = _("Retrieving catalog")
                else:
                        prefix = _("Refreshing catalog")
                msg = _("{prefix} {pub_cnt} {publisher}{bytes}").format(
                    prefix=prefix,
                    pub_cnt=self.pub_refresh.pairplus1(),
                    publisher=self.pub_refresh.curinfo,
                    bytes=nbytes)

                self._pe.cprint(msg, end="", erase=True)
                if outspec.last:
                        self.__generic_done()

        def _plan_output(self, outspec, planitem):
                if self.purpose == self.PURPOSE_PKG_UPDATE_CHK:
                        self._up2date()
                        return
                if outspec.first:
                        self.__generic_start("")
                if not self._ptimer.time_to_print() and not outspec:
                        return

                extra_info = ""
                if isinstance(planitem, GoalTrackerItem):
                        extra_info = ": {0}".format(planitem.pair())
                msg = _("Creating Plan ({name}{info}): {spinner}").format(
                    name=planitem.name,
                    info=extra_info,
                    spinner=self._spinner())
                self._pe.cprint(msg, sep='', end='', erase=True)

        def _plan_output_all_done(self):
                self.__generic_done()

        def _mfst_fetch(self, outspec):
                if self.purpose == self.PURPOSE_PKG_UPDATE_CHK:
                        self._up2date()
                        return
                if outspec.first:
                        self.__generic_start("")
                if not self._ptimer.time_to_print() and not outspec:
                        return

                #
                # There are a couple of reasons we might fetch manifests--
                # pkgrecv, pkglint, etc. can all do this.  So we adjust
                # the output based on the major mode.
                #
                if self.major_phase == self.PHASE_PLAN:
                        msg = _("Creating Plan ({name} {pair}) "
                            "{spinner}").format(
                            name=self.mfst_fetch.name,
                            pair=self.mfst_fetch.pair(),
                            spinner=self._spinner())
                if self.major_phase == self.PHASE_UTILITY:
                        # note to translators: the position of these strings
                        # should probably be left alone, as they form part of
                        # the progress output text.
                        msg = _("{name} ({fetchpair}) {spinchar}").format(
                            name=self.mfst_fetch.name,
                            fetchpair=self.mfst_fetch.pair(),
                            spinchar=self._spinner())
                self._pe.cprint(msg, sep='', end='', erase=True)

                if outspec.last:
                        self.__generic_done()

        def _reversion(self, pfmri, outspec):

                if not self._ptimer.time_to_print() and not outspec:
                        return

                if isinstance(pfmri, pkg.fmri.PkgFmri):
                        stem = pfmri.get_pkg_stem(anarchy=True)
                else:
                        stem = pfmri

                # The first time, emit header.
                if outspec.first:
                        self._pe.cprint("{0:38} {1:>13} {2:>13} {3:>11}".format(
                            _("PKG"), _("Processed"), _("Reversioned"),
                            _("Adjusted")))

                s = "{0:<40.40} {1:>11} {2:>13} {3:>11}".format(
                    stem, self.reversion_pkgs.pair(),
                    self.reversion_revs.pair(), self.reversion_adjs.items)
                self._pe.cprint(s, end='', erase=True)

                if outspec.last:
                        self.__generic_done_newline()

        def _mfst_commit(self, outspec):
                if self.purpose == self.PURPOSE_PKG_UPDATE_CHK:
                        self._up2date()
                        return
                if not self._ptimer.time_to_print():
                        return
                if self.major_phase == self.PHASE_PLAN:
                        msg = _("Creating Plan (Committing Manifests): "
                            "{0}").format(self._spinner())
                if self.major_phase == self.PHASE_UTILITY:
                        msg = _("Committing Manifests {0}").format(
                            self._spinner())
                self._pe.cprint(msg, sep='', end='', erase=True)
                return

        def _repo_ver_output(self, outspec, repository_scan=False):
                """If 'repository_scan' is set and we have no FRMRI set, we emit
                a message saying that we're performing a scan if the repository.
                If we have no FMRI, we emit a message saying we don't know what
                package we're looking at.

                """
                if not self.repo_ver_pkgs.curinfo:
                        if repository_scan:
                                pkg_stem = _("Scanning repository "
                                    "(this could take some time)")
                        else:
                                pkg_stem = _("Unknown package")
                else:
                        pkg_stem = self.repo_ver_pkgs.curinfo.get_pkg_stem()
                if not self._ptimer.time_to_print() and not outspec:
                        return
                if "endpkg" in outspec.changed:
                        self._pe.cprint("", end='', erase=True)
                        return
                s = "{0:64} {1} {2}".format(
                    pkg_stem, self.repo_ver_pkgs.pair(), self._spinner())
                self._pe.cprint(s, end='', erase=True)

        def _repo_ver_output_error(self, errors):
                self._output_flush()
                self._pe.cprint(errors)

        def _repo_fix_output(self, outspec):
                s = "{0}".format( self._spinner())
                self._pe.cprint(s, end='', erase=True)

        def _repo_fix_output_error(self, errors):
                self._output_flush()
                self._pe.cprint(errors)

        def _repo_fix_output_info(self, info):
                self._output_flush()
                self._pe.cprint(info)

        def _archive_output(self, outspec):
                if not self._ptimer.time_to_print() and not outspec:
                        return

                # The first time, emit header.
                if outspec.first:
                        self._pe.cprint("{0:44} {1:>13} {2:>11}".format(
                            _("ARCHIVE"), _("FILES"), _("STORE (MB)")))

                mbs = format_pair("{0:.1f}", self.archive_bytes.items,
                    self.archive_bytes.goalitems, scale=(1024 * 1024),
                    targetwidth=5, format2="{0:d}")
                s = "{0:<44.44} {1:>11} {2:>11}".format(
                    self._archive_name, self.archive_items.pair(), mbs)
                self._pe.cprint(s, end='', erase=True)

                if outspec.last:
                        self.__generic_done_newline()

        def _dl_output(self, outspec):
                if not self._ptimer.time_to_print() and not outspec.first \
                    and not outspec.last and not "startpkg" in outspec.changed \
                    and not "endpkg" in outspec.changed:
                        return

                # The first time, emit header.
                if outspec.first:
                        self._pe.cprint("{0:34} {1:>9} {2:>13} {3:>12} "
                            "{4:>7}".format(_("DOWNLOAD"), _("PKGS"),
                            _("FILES"), _("XFER (MB)"), _("SPEED")))

                if outspec.last:
                        pkg_name = _("Completed")
                else:
                        pkg_name = self.dl_pkgs.curinfo.get_name()
                if len(pkg_name) > 34:
                        pkg_name = "..." + pkg_name[-30:]

                if outspec.last:
                        speedstr = self.dl_estimator.format_speed(
                            self.dl_estimator.get_final_speed())
                        if speedstr is None:
                                speedstr = "--"
                else:
                        #
                        # if we see 10 items in a row come out of the cache,
                        # show the "cache" moniker in the speed column until we
                        # see a non-cache download.
                        #
                        if self.dl_caching > 10:
                                speedstr = "cache"
                        else:
                                speedstr = self.dl_estimator.format_speed(
                                    self.dl_estimator.get_speed_estimate())
                                if speedstr is None:
                                        speedstr = "--"

                # Use floats unless it makes the field too wide
                mbstr = format_pair("{0:.1f}", self.dl_bytes.items,
                    self.dl_bytes.goalitems, scale=1024.0 * 1024.0,
                    targetwidth=5, format2="{0:d}")
                s = "{0:<34.34} {1:>9} {2:>13} {3:>12} {4:>7}".format(
                    pkg_name, self.dl_pkgs.pair(), self.dl_files.pair(),
                    mbstr, speedstr)
                self._pe.cprint(s, end='', erase=True)

                if outspec.last:
                        self.__generic_done_newline()
                        self.__generic_done_newline()

        def _republish_output(self, outspec):
                if not outspec.first and not outspec.last \
                    and not self._ptimer.time_to_print():
                        return

                # The first time, emit header.
                if outspec.first:
                        self._pe.cprint("{0:40} {1:>12} {2:>11} {3:>11}".format(
                            _("PROCESS"), _("ITEMS"), _("GET (MB)"),
                            _("SEND (MB)")))

                if outspec.last:
                        pkg_name = "Completed"
                else:
                        pkg_name = self.repub_pkgs.curinfo.get_name()
                if len(pkg_name) > 40:
                        pkg_name = "..." + pkg_name[-37:]

                s = "{0:<40.40} {1:>12} {2:>11} {3:>11}".format(
                    pkg_name, self.repub_pkgs.pair(),
                    format_pair("{0:.1f}", self.dl_bytes.items,
                        self.dl_bytes.goalitems, scale=(1024 * 1024),
                        targetwidth=5, format2="{0:d}"),
                    format_pair("{0:.1f}", self.repub_send_bytes.items,
                        self.repub_send_bytes.goalitems, scale=(1024 * 1024),
                        targetwidth=5, format2="{0:d}"))
                self._pe.cprint(s, erase=True, end='')

                if outspec.last:
                        self.__generic_done_newline()
                        self.__generic_done_newline()

        def _print_phases_hdr(self):
                if self._phases_hdr_printed:
                        return
                self._pe.cprint("{0:40} {1:>11}".format(_("PHASE"), _("ITEMS")))
                self._phases_hdr_printed = True

        def _act_output(self, outspec, actionitem):
                if actionitem.goalitems == 0:
                        return
                # emit header if needed
                if outspec.first:
                        self._print_phases_hdr()

                if not self._ptimer.time_to_print() and \
                    not outspec.last and not outspec.first:
                        return
                self._pe.cprint("{0:40} {1:>11}".format(
                    actionitem.name, actionitem.pair()), end='', erase=True)
                if outspec.last:
                        self.__generic_done_newline()

        def _act_output_all_done(self):
                pass

        def _job_output(self, outspec, jobitem):
                if not self._ptimer.time_to_print() and not outspec and \
                    jobitem == self._jobs_lastjob:
                        return
                self._jobs_lastjob = jobitem

                # emit phases header if needed
                if outspec.first:
                        self._print_phases_hdr()

                spin = "" if outspec.last else self._spinner()
                if isinstance(jobitem, GoalTrackerItem):
                        val = jobitem.pair()
                else:
                        val = _("Done") if outspec.last else _("working")

                self._pe.cprint("{0:40} {1:>11} {2}".format(jobitem.name,
                    val, spin), end='', erase=True)
                if outspec.last:
                        self.__generic_done_newline()

        def _lint_output(self, outspec):
                if not self._ptimer.time_to_print() and not outspec.last:
                        return
                self._pe.cprint("{0:40} {1:>11}".format(self.lintitems.name,
                    self.lintitems.pair()), end='', erase=True)
                if outspec.last:
                        self.__generic_done()

        def _li_recurse_start_output(self):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        self.__generic_start(
                            _("Linked image publisher check"))
                        return

        def _li_recurse_end_output(self):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        return
                msg = _("{phasename} linked: {numdone} done").format(
                    phasename=self.li_phase_names[self.major_phase],
                    numdone=format_pair("{0:d}", self.linked_total,
                        self.linked_total))
                self._pe.cprint(msg, erase=True)

        def __li_dump_output(self, output):
                if not output:
                        return
                lines = output.splitlines()
                nlines = len(lines)
                for linenum, line in enumerate(lines):
                        line = misc.force_str(line)
                        if linenum < nlines - 1:
                                self._pe.cprint("| " + line)
                        else:
                                if lines[linenum].strip() != "":
                                        self._pe.cprint("| " + line)
                                self._pe.cprint("`")

        def _li_recurse_output_output(self, lin, stdout, stderr):
                if not stdout and not stderr:
                        self._pe.cprint("", erase=True, end='')
                        return

                self._pe.cprint(_("Linked image '{0}' output:").format(lin),
                    erase=True)
                self.__li_dump_output(stdout)
                self.__li_dump_output(stderr)

        def _li_recurse_status_output(self, done):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        return

                assert self.major_phase in self.li_phase_names, self.major_phase

                running = " ".join([str(i) for i in self.linked_running])
                msg = _("{phase} linked: {numdone} done; "
                    "{numworking:d} working: {running}").format(
                    phase=self.li_phase_names[self.major_phase],
                    numdone=format_pair("{0:d}", done, self.linked_total),
                    numworking=len(self.linked_running),
                    running=running)
                self._pe.cprint(msg, erase=True)

                self.__linked_spinners = list(
                    itertools.repeat(0, len(self.linked_running)))

        def _li_recurse_progress_output(self, lin):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        return
                if not self._ptimer.time_to_print():
                        return
                # find the index of the child that made progress
                i = self.linked_running.index(lin)

                # update that child's spinner
                self.__linked_spinners[i] = \
                    (self.__linked_spinners[i] + 1) % len(self.__spinner_chars)
                spinners = "".join([
                        self.__spinner_chars[i]
                        for i in self.__linked_spinners
                ])
                self._pe.cprint(_("Linked progress: {0}").format(spinners),
                    end='', erase=True)


#
# This code lives here, for now, anyway, because it is called both from
# the API test suite and from the $SRC/tests/interactive/runprogress.py
# utility.
#
def test_progress_tracker(t, gofast=False):
        # Unused variables (in several loops) pylint: disable=W0612
        import random

        print("Use ctrl-c to skip sections")

        if gofast == False:
                fast = 1.0
        else:
                fast = 0.10

        global_settings.client_output_verbose = 1

        dlscript = {
            "chrysler/lebaron": [],
            "mazda/mx-5": [],
            "acura/tsx": [],
            "honda/civic-si": [],
            "a-very-very-long-package-name-which-will-have-to-be-truncated": [],
        }

        for purp in [ProgressTracker.PURPOSE_PKG_UPDATE_CHK,
            ProgressTracker.PURPOSE_NORMAL]:
                t.set_purpose(purp)
                try:
                        t.refresh_start(4, full_refresh=False)
                        for x in ["woop", "gub", "zip", "yowee"]:
                                p = publisher.Publisher(x)
                                t.refresh_start_pub(p)
                                time.sleep(0.10 * fast)
                                t.refresh_progress(x, 1024 * 8)
                                time.sleep(0.10 * fast)
                                t.refresh_progress(x, 0)
                                time.sleep(0.10 * fast)
                                t.refresh_progress(x, 1024 * 128)
                                t.refresh_end_pub(p)
                        t.refresh_done()

                        t.cache_catalogs_start()
                        time.sleep(0.25 * fast)
                        t.cache_catalogs_done()

                        t.load_catalog_cache_start()
                        time.sleep(0.25 * fast)
                        t.load_catalog_cache_done()

                except KeyboardInterrupt:
                        t.flush()

                try:
                        t.set_major_phase(t.PHASE_PLAN)
                        planids = sorted([v for k, v in
                            ProgressTrackerFrontend.__dict__.items()
                            if k.startswith("PLAN_")])
                        t.plan_all_start()
                        for planid in planids:
                                r = random.randint(20, 100)
                                # we always try to set a goal; this will fail
                                # for ungoaled items, so then we try again
                                # without a goal.  This saves us the complicated
                                # task of inspecting the tracker-- and
                                # multiprogress makes such inspection much
                                # harder.
                                try:
                                        t.plan_start(planid, goal=r)
                                except RuntimeError:
                                        t.plan_start(planid)
                                for x in range(0, r):
                                        t.plan_add_progress(planid)
                                        time.sleep(0.02 * fast)
                                t.plan_done(planid)
                        t.plan_all_done()
                except KeyboardInterrupt:
                        t.flush()

                try:
                        t.manifest_fetch_start(len(dlscript))
                        for pkgnm in dlscript:
                                t.manifest_fetch_progress(
                                    completion=False)
                                time.sleep(0.05 * fast)
                                t.manifest_fetch_progress(
                                    completion=True)
                                time.sleep(0.05 * fast)
                        for pkgnm in dlscript:
                                t.manifest_commit()
                                time.sleep(0.05 * fast)
                        t.manifest_fetch_done()
                except KeyboardInterrupt:
                        t.flush()

        perpkgfiles = 50
        pkggoalfiles = len(dlscript) * perpkgfiles
        pkggoalbytes = 0
        filesizemax = 250000
        hunkmax = 8192
        approx_time = 5.0 * fast   # how long we want the dl to take
        # invent a list of random download chunks.
        for pkgname, filelist in six.iteritems(dlscript):
                for f in range(0, perpkgfiles):
                        filesize = random.randint(0, filesizemax)
                        hunks = []
                        while filesize > 0:
                                delta = min(filesize,
                                    random.randint(0, hunkmax))
                                hunks.append(delta)
                                filesize -= delta
                                pkggoalbytes += delta
                        filelist.append(hunks)

        # pylint is picky about this message:
        # old-division; pylint: disable=W1619
        pauseperfile = approx_time / pkggoalfiles

        try:
                t.download_set_goal(len(dlscript), pkggoalfiles, pkggoalbytes)
                n = 0
                for pkgname, pkgfiles in six.iteritems(dlscript):
                        fmri = pkg.fmri.PkgFmri(pkgname)
                        t.download_start_pkg(fmri)
                        for pkgfile in pkgfiles:
                                for hunk in pkgfile:
                                        t.download_add_progress(0, hunk)
                                t.download_add_progress(1, 0)
                                time.sleep(pauseperfile)
                        t.download_end_pkg(fmri)
                t.download_done()
        except KeyboardInterrupt:
                t.flush()

        try:
                t.reset_download()
                t.republish_set_goal(len(dlscript), pkggoalbytes, pkggoalbytes)
                n = 0
                for pkgname, pkgfiles in six.iteritems(dlscript):
                        fmri = pkg.fmri.PkgFmri(pkgname)
                        t.republish_start_pkg(fmri)
                        for pkgfile in pkgfiles:
                                for hunk in pkgfile:
                                        t.download_add_progress(0, hunk)
                                        t.upload_add_progress(hunk)
                                t.download_add_progress(1, 0)
                                time.sleep(pauseperfile)
                        t.republish_end_pkg(fmri)
                t.republish_done()
        except KeyboardInterrupt:
                t.flush()

        try:
                t.reset_download()
                t.archive_set_goal("testarchive", pkggoalfiles, pkggoalbytes)
                n = 0
                for pkgname, pkgfiles in six.iteritems(dlscript):
                        for pkgfile in pkgfiles:
                                for hunk in pkgfile:
                                        t.archive_add_progress(0, hunk)
                                t.archive_add_progress(1, 0)
                                time.sleep(pauseperfile)
                t.archive_done()
        except KeyboardInterrupt:
                t.flush()
        try:
                t.set_major_phase(t.PHASE_EXECUTE)

                nactions = 100
                t.actions_set_goal(t.ACTION_REMOVE, nactions)
                t.actions_set_goal(t.ACTION_INSTALL, nactions)
                t.actions_set_goal(t.ACTION_UPDATE, nactions)
                for act in [t.ACTION_REMOVE, t.ACTION_INSTALL, t.ACTION_UPDATE]:
                        for x in range(0, nactions):
                                t.actions_add_progress(act)
                                time.sleep(0.0015 * fast)
                        t.actions_done(act)
                t.actions_all_done()
        except KeyboardInterrupt:
                t.flush()

        try:
                t.set_major_phase(t.PHASE_FINALIZE)
                for jobname, job in ProgressTrackerFrontend.__dict__.items():
                        if not jobname.startswith("JOB_"):
                                continue
                        r = random.randint(5, 30)
                        # we always try to set a goal; this will fail for
                        # ungoaled items, so then we try again without a goal.
                        # This saves us the complicated task of inspecting the
                        # tracker-- and multiprogress makes such inspection
                        # much harder.
                        try:
                                t.job_start(job, goal=r)
                        except RuntimeError:
                                t.job_start(job)

                        for x in range(0, r):
                                t.job_add_progress(job)
                                time.sleep(0.02 * fast)
                        t.job_done(job)
        except KeyboardInterrupt:
                t.flush()

        try:
                # do some other things to drive up test coverage.
                t.flush()

                # test lint
                for phase in [t.LINT_PHASETYPE_SETUP, t.LINT_PHASETYPE_EXECUTE]:
                        t.lint_next_phase(2, phase)
                        for x in range(0, 100):
                                t.lint_add_progress()
                                time.sleep(0.02 * fast)
                t.lint_done()
        except KeyboardInterrupt:
                t.flush()
        return
