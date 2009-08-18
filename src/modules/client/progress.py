#!/usr/bin/python2.4
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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import errno
import sys
import os
import time
from pkg.misc import PipeError, emsg
import pkg.portable as portable

class ProgressTracker(object):
        """ This abstract class is used by the client to render and track
            progress towards the completion of various tasks, such as
            download, installation, update, etc.

            The superclass is largely concerned with tracking the
            raw numbers, and with calling various callback routines
            when events of interest occur.

            Different subclasses provide the actual rendering to the
            user, with differing levels of detail and prettiness.

            Note that as currently envisioned, this class is concerned
            with tracking the progress of long-running operations: it is
            NOT a general purpose output mechanism nor an error collector.

            Subclasses of ProgressTracker must implement all of the
            *_output_* methods.

            External consumers should base their subclasses on the
            NullProgressTracker class. """

        def __init__(self):
                self.reset()

        def reset(self):
                self.cat_cur_catalog = None

                self.refresh_pub_cnt = 0
                self.refresh_cur_pub_cnt = 0
                self.refresh_cur_pub = None

                self.ver_cur_fmri = None

                self.eval_cur_fmri = None
                self.eval_prop_npkgs = 0
                self.eval_goal_install_npkgs = 0
                self.eval_goal_update_npkgs = 0
                self.eval_goal_remove_npkgs = 0

                self.dl_goal_nfiles = 0
                self.dl_cur_nfiles = 0
                self.dl_goal_nbytes = 0
                self.dl_cur_nbytes = 0
                self.dl_goal_npkgs = 0
                self.dl_cur_npkgs = 0
                self.dl_cur_pkg = "None"

                self.act_cur_nactions = 0
                self.act_goal_nactions = 0
                self.act_phase = "None"
                self.act_phase_last = "None"

                self.ind_cur_nitems = 0
                self.ind_goal_nitems = 0
                self.ind_phase = "None"
                self.ind_phase_last = "None"

                self.last_printed = 0 # when did we last emit status?

        def catalog_start(self, catalog):
                self.cat_cur_catalog = catalog
                self.cat_output_start()

        def catalog_done(self):
                self.cat_output_done()

        def cache_catalogs_start(self):
                self.cache_cats_output_start()

        def cache_catalogs_done(self):
                self.cache_cats_output_done()

        def load_catalog_cache_start(self):
                self.load_cat_cache_output_start()

        def load_catalog_cache_done(self):
                self.load_cat_cache_output_done()

        def refresh_start(self, pub_cnt):
                self.refresh_pub_cnt = pub_cnt
                self.refresh_cur_pub_cnt = 0
                self.refresh_output_start()

        def refresh_progress(self, pub):
                self.refresh_cur_pub = pub
                self.refresh_cur_pub_cnt += 1
                self.refresh_output_progress()

        def refresh_done(self):
                self.refresh_output_done()

        def evaluate_start(self, npkgs=-1):
                self.eval_prop_npkgs = npkgs
                self.eval_output_start()

        def evaluate_progress(self, fmri=None):
                if fmri:
                        self.eval_cur_fmri = fmri
                self.eval_output_progress()

        def evaluate_done(self, install_npkgs=-1, \
            update_npkgs=-1, remove_npkgs=-1):
                self.eval_goal_install_npkgs = install_npkgs
                self.eval_goal_update_npkgs = update_npkgs
                self.eval_goal_remove_npkgs = remove_npkgs
                self.eval_output_done()

        def verify_add_progress(self, fmri):
                self.ver_cur_fmri = fmri
                self.ver_output()

        def verify_yield_error(self, actname, errors):
                self.ver_output_error(actname, errors)

        def verify_done(self):
                self.ver_cur_fmri = None
                self.ver_output_done()

        def download_set_goal(self, npkgs, nfiles, nbytes):
                self.dl_goal_npkgs = npkgs
                self.dl_goal_nfiles = nfiles
                self.dl_goal_nbytes = nbytes

        def download_start_pkg(self, pkgname):
                self.dl_cur_pkg = pkgname
                if self.dl_goal_nbytes != 0:
                        self.dl_output()

        def download_end_pkg(self):
                self.dl_cur_npkgs += 1
                if self.dl_goal_nbytes != 0:
                        self.dl_output()

        def download_add_progress(self, nfiles, nbytes):
                """ Call to provide news that the download has made progress """

                self.dl_cur_nbytes += nbytes
                self.dl_cur_nfiles += nfiles
                if self.dl_goal_nbytes != 0:
                        self.dl_output()

        def download_done(self):
                """ Call when all downloading is finished """
                if self.dl_goal_nbytes != 0:
                        self.dl_output_done()

                if self.dl_cur_npkgs != self.dl_goal_npkgs:
                        emsg("\nExpected %s pkgs, received %s pkgs instead." %
                            (self.dl_goal_npkgs, self.dl_cur_npkgs))
                if self.dl_cur_nfiles != self.dl_goal_nfiles:
                        emsg("\nExpected %s files, received %s files instead."
                            % (self.dl_goal_nfiles, self.dl_cur_nfiles))
                if self.dl_cur_nbytes != self.dl_goal_nbytes:
                        emsg("\nExpected %s bytes, received %s bytes instead."
                            % (self.dl_goal_nbytes, self.dl_cur_nbytes))

                assert self.dl_cur_npkgs == self.dl_goal_npkgs
                assert self.dl_cur_nfiles == self.dl_goal_nfiles
                assert self.dl_cur_nbytes == self.dl_goal_nbytes

        def download_get_progress(self):
                return (self.dl_cur_npkgs, self.dl_cur_nfiles,
                    self.dl_cur_nbytes)

        def actions_set_goal(self, phase, nactions):
                self.act_phase = phase
                self.act_goal_nactions = nactions
                self.act_cur_nactions = 0

        def actions_add_progress(self):
                self.act_cur_nactions += 1
                if self.act_goal_nactions > 0:
                        self.act_output()

        def actions_done(self):
                if self.act_goal_nactions > 0:
                        self.act_output_done()
                assert self.act_goal_nactions == self.act_cur_nactions

        def index_set_goal(self, phase, nitems):
                self.ind_phase = phase
                self.ind_goal_nitems = nitems
                self.ind_cur_nitems = 0

        def index_add_progress(self):
                self.ind_cur_nitems += 1
                if self.ind_goal_nitems > 0:
                        self.ind_output()

        def index_done(self):
                if self.ind_goal_nitems > 0:
                        self.ind_output_done()
                assert self.ind_goal_nitems == self.ind_cur_nitems

        def index_optimize(self):
                return

        #
        # This set of methods should be regarded as abstract *and* protected.
        # If you aren't in this class hierarchy, these should not be
        # called directly.  Subclasses should implement all of these methods.
        #
        def cat_output_start(self):
                raise NotImplementedError("cat_output_start() not implemented "
                    "in superclass")

        def cat_output_done(self):
                raise NotImplementedError("cat_output_done() not implemented "
                    "in superclass")

        def cache_cats_output_start(self):
                raise NotImplementedError("cache_cats_output_start() not "
                    "implemented in superclass")

        def cache_cats_output_done(self):
                raise NotImplementedError("cache_cats_output_done() not "
                    "implemented in superclass")

        def load_cat_cache_output_start(self):
                raise NotImplementedError("load_cat_cache_output_start() not "
                    "implemented in superclass")

        def load_cat_cache_output_done(self):
                raise NotImplementedError("load_cat_cache_output_done() not "
                    "implemented in superclass")

        def refresh_output_start(self):
                return

        def refresh_output_progress(self):
                return

        def refresh_output_done(self):
                return

        def eval_output_start(self):
                raise NotImplementedError("eval_output_start() not implemented "
                    "in superclass")

        def eval_output_progress(self):
                raise NotImplementedError("eval_output_progress() not "
                    "implemented in superclass")

        def eval_output_done(self):
                raise NotImplementedError("eval_output_done() not implemented "
                    "in superclass")

        def ver_output(self):
                raise NotImplementedError("ver_output() not implemented in "
                    "superclass")

        def ver_output_error(self, actname, errors):
                raise NotImplementedError("ver_output_error() not implemented "
                    "in superclass")

        def ver_output_done(self):
                raise NotImplementedError("ver_output_done() not implemented "
                    "in superclass")

        def dl_output(self):
                raise NotImplementedError("dl_output() not implemented in "
                    "superclass")

        def dl_output_done(self):
                raise NotImplementedError("dl_output_done() not implemented "
                    "in superclass")

        def act_output(self, force=False):
                raise NotImplementedError("act_output() not implemented in "
                    "superclass")

        def act_output_done(self):
                raise NotImplementedError("act_output_done() not implemented "
                    "in superclass")

        def ind_output(self, force=False):
                raise NotImplementedError("ind_output() not implemented in "
                    "superclass")

        def ind_output_done(self):
                raise NotImplementedError("ind_output_done() not implemented "
                    "in superclass")


class ProgressTrackerException(Exception):
        """ This exception is currently thrown if a ProgressTracker determines
            that it can't be instantiated; for example, the tracker which
            depends on a UNIX style terminal should throw this exception
            if it can't find a valid terminal. """

        def __init__(self):
                Exception.__init__(self)



class QuietProgressTracker(ProgressTracker):
        """ This progress tracker outputs nothing, but is semantically
            intended to be "quiet"  See also NullProgressTracker below. """

        def __init__(self):
                ProgressTracker.__init__(self)

        def cat_output_start(self):
                return

        def cat_output_done(self):
                return

        def cache_cats_output_start(self):
                return

        def cache_cats_output_done(self):
                return

        def load_cat_cache_output_start(self):
                return

        def load_cat_cache_output_done(self):
                return

        def eval_output_start(self):
                return

        def eval_output_progress(self):
                return

        def eval_output_done(self):
                return

        def ver_output(self):
                return

        def ver_output_done(self):
                return

        def ver_output_error(self, actname, errors):
                return

        def dl_output(self):
                return

        def dl_output_done(self):
                return

        def act_output(self, force=False):
                return

        def act_output_done(self):
                return

        def ind_output(self, force=False):
                return

        def ind_output_done(self):
                return


class NullProgressTracker(QuietProgressTracker):
        """ This ProgressTracker is a subclass of QuietProgressTracker
            because that's convenient for now.  It is semantically intended to
            be a no-op progress tracker, and is useful for short-running
            operations which need not display progress of any kind.

            This subclass should be used by external consumers wanting to create
            their own ProgressTracker class as any new output methods added to
            the ProgressTracker class will also be handled here, insulating them
            from additions to the ProgressTracker class. """


class CommandLineProgressTracker(ProgressTracker):
        """ This progress tracker is a generically useful tracker for
            command line output.  It needs no special terminal features
            and so is appropriate for sending through a pipe.  This code
            is intended to be platform neutral. """

        def __init__(self):
                ProgressTracker.__init__(self)
                self.dl_last_printed_pkg = None

        def cat_output_start(self):
                return

        def cat_output_done(self):
                return

        def cache_cats_output_start(self):
                return

        def cache_cats_output_done(self):
                return

        def load_cat_cache_output_start(self):
                return

        def load_cat_cache_output_done(self):
                return

        def eval_output_start(self):
                return

        def eval_output_progress(self):
                return

        def eval_output_done(self):
                return

        def ver_output(self):
                return

        def ver_output_error(self, actname, errors):
                return

        def ver_output_done(self):
                return

        def dl_output(self):
                try:
                        # The first time, emit header.
                        if self.dl_cur_pkg != self.dl_last_printed_pkg:
                                if self.dl_last_printed_pkg != None:
                                        print "Done"
                                print "Download: %s ... " % (self.dl_cur_pkg),
                                self.dl_last_printed_pkg = self.dl_cur_pkg
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def dl_output_done(self):
                try:
                        print "Done"
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def act_output(self, force=False):
                if self.act_phase != self.act_phase_last:
                        try:
                                print "%s ... " % self.act_phase,
                        except IOError, e:
                                if e.errno == errno.EPIPE:
                                        raise PipeError, e
                                raise
                        self.act_phase_last = self.act_phase
                return

        def act_output_done(self):
                try:
                        print "Done"
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def ind_output(self, force=False):
                if self.ind_phase != self.ind_phase_last:
                        try:
                                print "%s ... " % self.ind_phase,
                        except IOError, e:
                                if e.errno == errno.EPIPE:
                                        raise PipeError, e
                                raise
                        self.ind_phase_last = self.ind_phase
                return

        def ind_output_done(self):
                try:
                        print "Done"
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise



class FancyUNIXProgressTracker(ProgressTracker):
        """ This progress tracker is designed for UNIX-like OS's--
            those which have UNIX-like terminal semantics.  It attempts
            to load the 'curses' package.  If that or other terminal-liveness
            tests fail, it gives up: the client should pick some other more
            suitable tracker.  (Probably CommandLineProgressTracker). """

        #
        # The minimum interval at which we should update the display during
        # operations which produce a lot of output.  Needed to avoid spamming
        # a slow terminal.
        #
        TERM_DELAY = 0.10

        def __init__(self):
                ProgressTracker.__init__(self)

                self.act_started = False
                self.ind_started = False
                self.last_print_time = 0

                try:
                        import curses
                        if not os.isatty(sys.stdout.fileno()):
                                raise ProgressTrackerException()

                        curses.setupterm()
                        self.cr = curses.tigetstr("cr")
                except KeyboardInterrupt:
                        raise
                except:
                        if portable.ostype == "windows" and \
                            os.isatty(sys.stdout.fileno()):
                                self.cr = '\r'
                        else:
                                raise ProgressTrackerException()
                self.dl_started = False
                self.spinner = 0
                self.spinner_chars = "/-\|"
                self.curstrlen = 0

        def __generic_start(self, msg):
                # Ensure the last message displayed is flushed in case the
                # corresponding operation did not complete successfully.
                self.__generic_done()
                self.curstrlen = len(msg)
                try:
                        print "%s" % msg,
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def __generic_done(self):
                try:
                        print self.cr,
                        print " " * self.curstrlen,
                        print self.cr,
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def cat_output_start(self):
                self.__generic_start(_("Retrieving catalog '%s'...") % \
                    self.cat_cur_catalog)

        def cat_output_done(self):
                self.__generic_done()

        def cache_cats_output_start(self):
                self.__generic_start(_("Caching catalogs ..."))

        def cache_cats_output_done(self):
                self.__generic_done()

        def load_cat_cache_output_start(self):
                self.__generic_start(_("Loading catalog cache ..."))

        def load_cat_cache_output_done(self):
                self.__generic_done()

        def refresh_output_start(self):
                self.__generic_start(_("Refreshing catalog"))

        def refresh_output_progress(self):
                try:
                        print self.cr,
                        print " " * self.curstrlen,
                        print self.cr,
                        s = "Refreshing catalog %d/%d %s" % \
                            (self.refresh_cur_pub_cnt, self.refresh_pub_cnt,
                            self.refresh_cur_pub)
                        self.curstrlen = len(s)
                        print "%s" % s,
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def refresh_output_done(self):
                self.__generic_done()

        def eval_output_start(self):
                # Ensure the last message displayed is flushed in case the
                # corresponding operation did not complete successfully.
                self.__generic_done()

                s = "Creating Plan"
                self.curstrlen = len(s)
                try:
                        print "%s" % s,
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def eval_output_progress(self):
                if (time.time() - self.last_print_time) < self.TERM_DELAY:
                        return

                self.last_print_time = time.time()
                self.spinner = (self.spinner + 1) % len(self.spinner_chars)
                try:
                        print self.cr,
                        s = "Creating Plan %c" % self.spinner_chars[
                            self.spinner]
                        self.curstrlen = len(s)
                        print "%s" % s,
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def eval_output_done(self):
                self.__generic_done()
                self.last_print_time = 0

        def ver_output(self):
                try:
                        assert self.ver_cur_fmri != None
                        print self.cr,
                        if (time.time() - self.last_print_time) < \
                            self.TERM_DELAY:
                                return
                        self.last_print_time = time.time()
                        self.spinner = (self.spinner + 1) % \
                            len(self.spinner_chars)
                        s = "%-50s..... %c%c" % \
                            (self.ver_cur_fmri.get_pkg_stem(),
                             self.spinner_chars[self.spinner],
                             self.spinner_chars[self.spinner])
                        self.curstrlen = len(s)
                        print s, self.cr,
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def ver_output_error(self, actname, errors):
                # for now we just get the "Verifying" progress
                # thingy out of the way.
                try:
                        print " " * self.curstrlen, self.cr,
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def ver_output_done(self):
                try:
                        print self.cr,
                        # Add a carriage return to prevent python from
                        # auto-terminating with a newline if this is the
                        # last output line on exit.  This works because
                        # python doesn't think there's any output to
                        # terminate even though sys.stdout.softspace is
                        # in effect.  sys.stdout.softspace isn't set
                        # here because more output may happen after
                        # this.
                        print " " * self.curstrlen, self.cr,
                        sys.stdout.flush()
                        self.last_print_time = 0
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def dl_output(self, force=False):
                if self.dl_started and not force and \
                    (time.time() - self.last_print_time) < self.TERM_DELAY:
                        return

                self.last_print_time = time.time()

                try:
                        # The first time, emit header.
                        if not self.dl_started:
                                self.dl_started = True
                                print "%-38s %7s %11s %12s" % ("DOWNLOAD", \
                                    "PKGS", "FILES", "XFER (MB)")
                        else:
                                print self.cr,

                        pkg_name = self.dl_cur_pkg
                        if len(pkg_name) > 38:
                                pkg_name = pkg_name[:34] + "..."

                        print "%-38.38s %7s %11s %12s" % \
                            (pkg_name,
                            "%d/%d" % (self.dl_cur_npkgs, self.dl_goal_npkgs),
                            "%d/%d" % (self.dl_cur_nfiles, self.dl_goal_nfiles),
                            "%.1f/%.1f" % \
                                ((self.dl_cur_nbytes / 1024.0 / 1024.0),
                                (self.dl_goal_nbytes / 1024.0 / 1024.0))),
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def dl_output_done(self):
                self.dl_cur_pkg = "Completed"
                self.dl_output(force=True)
                try:
                        print
                        print
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def act_output(self, force=False):
                if not force and \
                    (time.time() - self.last_print_time) < self.TERM_DELAY:
                        return

                self.last_print_time = time.time()
                try:
                        # The first time, emit header.
                        if not self.act_started:
                                self.act_started = True
                                print "%-40s %11s" % ("PHASE", "ACTIONS")
                        else:
                                print self.cr,

                        print "%-40s %11s" % \
                            (
                                self.act_phase,
                                "%d/%d" % (self.act_cur_nactions,
                                    self.act_goal_nactions)
                             ),

                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def act_output_done(self):
                self.act_output(force=True)
                try:
                        print
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def index_optimize(self):
                self.ind_output_done()
                self.ind_started = False
                self.last_print_time = 0
                try:
                        print "Optimizing Index..."
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def ind_output(self, force=False):
                if not force and \
                    (time.time() - self.last_print_time) < self.TERM_DELAY:
                        return

                self.last_print_time = time.time()
                try:
                        # The first time, emit header.
                        if not self.ind_started:
                                self.ind_started = True
                                print "%-40s %11s" % ("PHASE", "ITEMS")
                        else:
                                print self.cr,

                        print "%-40s %11s" % \
                            (
                                self.ind_phase,
                                "%d/%d" % (self.ind_cur_nitems,
                                    self.ind_goal_nitems)
                             ),

                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def ind_output_done(self):
                self.ind_output(force=True)
                try:
                        print
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise
