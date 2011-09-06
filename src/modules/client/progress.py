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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#

import errno
import sys
import os
import time

from pkg.client import global_settings
logger = global_settings.logger

from pkg.misc import PipeError
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

        def __init__(self, parsable_version=None, quiet=False, verbose=0):

                self.parsable_version = parsable_version
                self.quiet = quiet
                self.verbose = verbose

                self.reset()

        def set_linked_name(self, lin):
                """Called once an image determines it's linked image name."""
                return

        def reset_download(self):
                self.dl_started = False
                self.dl_goal_nfiles = 0
                self.dl_cur_nfiles = 0
                self.dl_goal_nbytes = 0
                self.dl_cur_nbytes = 0
                self.dl_goal_npkgs = 0
                self.dl_cur_npkgs = 0
                self.cur_pkg = "None"

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

                self.reset_download()

                self.act_cur_nactions = 0
                self.act_goal_nactions = 0
                self.act_phase = "None"
                self.act_phase_last = "None"

                self.ind_cur_nitems = 0
                self.ind_goal_nitems = 0
                self.ind_phase = "None"
                self.ind_phase_last = "None"

                self.item_cur_nitems = 0
                self.item_cur_nbytes = 0
                self.item_goal_nitems = 0
                self.item_goal_nbytes = 0
                self.item_phase = "None"
                self.item_phase_last = "None"

                self.send_cur_nbytes = 0
                self.send_goal_nbytes = 0
                self.republish_started = False

                # The tracker sets this to True whenever it has emitted
                # output, but not yet written a newline. ProgressTracker
                # users should call flush() when wanting to interrupt
                # the tracker to write their own output.
                # When the tracker writes a newline, we automatically reset
                # this flag to False.
                self.needs_cr = False

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

        def verify_yield_warning(self, actname, warnings):
                self.ver_output_warning(actname, warnings)

        def verify_yield_info(self, actname, info):
                self.ver_output_info(actname, info)

        def verify_done(self):
                self.ver_cur_fmri = None
                self.ver_output_done()

        def archive_set_goal(self, arcname, nitems, nbytes):
                self.item_phase = arcname
                self.item_goal_nitems = nitems
                self.item_goal_nbytes = nbytes

        def archive_add_progress(self, nitems, nbytes):
                self.item_cur_nitems += nitems
                self.item_cur_nbytes += nbytes
                if self.item_goal_nitems > 0:
                        self.archive_output()

        def archive_done(self):
                """ Call when all archiving is finished """
                if self.item_goal_nitems != 0:
                        self.archive_output_done()

                if self.item_cur_nitems != self.item_goal_nitems:
                        logger.error("\nExpected %s files, archived %s files "
                            "instead." % (self.item_goal_nitems,
                            self.item_cur_nitems))
                if self.item_cur_nbytes != self.item_goal_nbytes:
                        logger.error("\nExpected %s bytes, archived %s bytes "
                            "instead." % (self.item_goal_nbytes,
                            self.item_cur_nbytes))

                assert self.item_cur_nitems == self.item_goal_nitems
                assert self.item_cur_nbytes == self.item_goal_nbytes

        def download_set_goal(self, npkgs, nfiles, nbytes):
                self.dl_goal_npkgs = npkgs
                self.dl_goal_nfiles = nfiles
                self.dl_goal_nbytes = nbytes

        def download_start_pkg(self, pkgname):
                self.cur_pkg = pkgname
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
                if self.dl_started:
                        if self.dl_goal_nbytes != 0:
                                self.dl_output()
                elif self.republish_started:
                        if self.dl_goal_nbytes != 0:
                                self.republish_output()

        def download_done(self):
                """ Call when all downloading is finished """
                if self.dl_goal_nbytes != 0:
                        self.dl_output_done()

                if self.dl_cur_npkgs != self.dl_goal_npkgs:
                        logger.error("\nExpected %s pkgs, received %s pkgs "
                            "instead." % (self.dl_goal_npkgs,
                            self.dl_cur_npkgs))
                if self.dl_cur_nfiles != self.dl_goal_nfiles:
                        logger.error("\nExpected %s files, received %s files "
                            "instead." % (self.dl_goal_nfiles,
                            self.dl_cur_nfiles))
                if self.dl_cur_nbytes != self.dl_goal_nbytes:
                        logger.error("\nExpected %s bytes, received %s bytes "
                            "instead." % (self.dl_goal_nbytes,
                            self.dl_cur_nbytes))

                assert self.dl_cur_npkgs == self.dl_goal_npkgs, \
                    "Expected %s packages but got %s" % \
                    (self.dl_goal_npkgs, self.dl_cur_npkgs)
                assert self.dl_cur_nfiles == self.dl_goal_nfiles, \
                    "Expected %s files but got %s" % \
                    (self.dl_goal_nfiles, self.dl_cur_nfiles)
                assert self.dl_cur_nbytes == self.dl_goal_nbytes, \
                    "Expected %s bytes but got %s" % \
                    (self.dl_goal_nbytes, self.dl_cur_nbytes)

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

        def item_set_goal(self, phase, nitems):
                self.item_phase = phase
                self.item_goal_nitems = nitems
                self.item_cur_nitems = 0

        def item_add_progress(self):
                self.item_cur_nitems += 1
                if self.item_goal_nitems > 0:
                        self.item_output()

        def item_done(self):
                if self.item_goal_nitems > 0:
                        self.item_output_done()
                assert self.item_goal_nitems == self.item_cur_nitems

        def republish_set_goal(self, npkgs, ngetbytes, nsendbytes):
                self.item_cur_nitems = 0
                self.item_goal_nitems = npkgs
                self.dl_cur_nbytes = 0
                self.dl_goal_nbytes = ngetbytes
                self.send_cur_nbytes = 0
                self.send_goal_nbytes = nsendbytes

        def republish_start_pkg(self, pkgname, getbytes=None, sendbytes=None):
                self.cur_pkg = pkgname

                if getbytes is not None:
                        # Allow reset of GET and SEND amounts on a per-package
                        # basis.  This allows the user to monitor the overall
                        # progress of the operation in terms of total packages
                        # while not requiring the program to pre-process all
                        # packages to determine total byte sizes before starting
                        # the operation.
                        assert sendbytes is not None
                        self.dl_cur_nbytes = 0
                        self.dl_goal_nbytes = getbytes
                        self.send_cur_nbytes = 0
                        self.send_goal_nbytes = sendbytes

                if self.item_goal_nitems != 0:
                        self.republish_output()

        def republish_end_pkg(self):
                self.item_cur_nitems += 1
                if self.item_goal_nitems != 0:
                        self.republish_output()

        def upload_add_progress(self, nbytes):
                """ Call to provide news that the upload has made progress """

                self.send_cur_nbytes += nbytes
                if self.send_goal_nbytes != 0:
                        self.republish_output()

        def republish_done(self):
                """ Call when all downloading is finished """
                if self.item_goal_nitems != 0:
                        self.republish_output_done()

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

        def li_recurse_start(self, lin):
                """Called when we recurse into a child linked image."""

                raise NotImplementedError("li_recurse_start() not implemented "
                    "in superclass")

        def li_recurse_end(self, lin):
                """Called when we return from a child linked image."""

                raise NotImplementedError("li_recurse_end() not implemented "
                    "in superclass")

        def ver_output(self):
                raise NotImplementedError("ver_output() not implemented in "
                    "superclass")

        def ver_output_error(self, actname, errors):
                raise NotImplementedError("ver_output_error() not implemented "
                    "in superclass")

        def ver_output_warning(self, actname, warnings):
                raise NotImplementedError("ver_output_warning() not "
                    "implemented in superclass")

        def ver_output_info(self, actname, info):
                raise NotImplementedError("ver_output_info() not "
                    "implemented in superclass")

        def ver_output_done(self):
                raise NotImplementedError("ver_output_done() not implemented "
                    "in superclass")

        def archive_output(self):
                raise NotImplementedError("archive_output() not implemented in "
                    "superclass")

        def archive_output_done(self):
                raise NotImplementedError("archive_output_done() not "
                    "implemented in superclass")

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

        def item_output(self, force=False):
                raise NotImplementedError("item_output() not implemented in "
                    "superclass")

        def item_output_done(self):
                raise NotImplementedError("item_output_done() not implemented "
                    "in superclass")

        def republish_output(self):
                raise NotImplementedError("republish_output() not implemented "
                    "in superclass")

        def republish_output_done(self):
                raise NotImplementedError("republish_output_done() not "
                    "implemented in superclass")

        def flush(self):
                raise NotImplementedError("flush() not implemented in "
                    "superclass")


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

        def __init__(self, parsable_version=None):
                ProgressTracker.__init__(self,
                    parsable_version=parsable_version, quiet=True)

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

        def li_recurse_start(self, lin):
                return

        def li_recurse_end(self, lin):
                return

        def ver_output(self):
                return

        def ver_output_done(self):
                return

        def ver_output_error(self, actname, errors):
                return

        def ver_output_warning(self, actname, warnings):
                return

        def ver_output_info(self, actname, info):
                return

        def archive_output(self):
                return

        def archive_output_done(self):
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

        def item_output(self, force=False):
                return

        def item_output_done(self):
                return

        def republish_output(self):
                return

        def republish_output_done(self):
                return

        def flush(self):
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

        def __init__(self, parsable_version=None, quiet=False, verbose=0):
                ProgressTracker.__init__(self,
                    parsable_version=parsable_version, quiet=quiet,
                    verbose=verbose)
                self.last_printed_pkg = None
                self.msg_prefix = ""

        def set_linked_name(self, lin):
                self.msg_prefix = ""
                if lin:
                        self.msg_prefix = _("Image %s ") % lin

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

        def li_recurse_start(self, lin):
                msg = _("Recursing into linked image: %s") % lin
                msg = "%s%s" % (self.msg_prefix, msg)

                try:
                        print "%s\n" % msg
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def li_recurse_end(self, lin):
                msg = _("Returning from linked image: %s") % lin
                msg = "%s%s" % (self.msg_prefix, msg)

                try:
                        print "%s\n" % msg
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def ver_output(self):
                return

        def ver_output_error(self, actname, errors):
                return

        def ver_output_warning(self, actname, warnings):
                return

        def ver_output_info(self, actname, info):
                return

        def ver_output_done(self):
                return

        def __generic_pkg_output(self, pkg_line):
                try:
                        # The first time, emit header.
                        if self.cur_pkg != self.last_printed_pkg:
                                if self.last_printed_pkg != None:
                                        print _("Done")
                                print pkg_line % self.cur_pkg,
                                self.last_printed_pkg = self.cur_pkg
                                self.needs_cr = True
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def dl_output(self):
                self.__generic_pkg_output(_("Download: %s ... "))

        def republish_output(self):
                self.__generic_pkg_output(_("Republish: %s ... "))

        def __generic_done(self):
                try:
                        print _("Done")
                        self.needs_cr = False
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def dl_output_done(self):
                self.__generic_done()

        def republish_output_done(self):
                self.__generic_done()

        def __generic_output(self, phase_attr, last_phase_attr, force=False):
                pattr = getattr(self, phase_attr)
                last_pattr = getattr(self, last_phase_attr)
                if pattr != last_pattr:
                        try:
                                print "%s ... " % pattr,
                                self.needs_cr = True
                        except IOError, e:
                                if e.errno == errno.EPIPE:
                                        raise PipeError, e
                                raise
                        setattr(self, last_phase_attr, pattr)

        def archive_output(self, force=False):
                self.__generic_output("item_phase", "item_phase_last",
                    force=force)

        def archive_output_done(self):
                self.__generic_done()

        def act_output(self, force=False):
                self.__generic_output("act_phase", "act_phase_last",
                    force=force)

        def act_output_done(self):
                self.__generic_done()

        def ind_output(self, force=False):
                self.__generic_output("ind_phase", "ind_phase_last",
                    force=force)

        def ind_output_done(self):
                self.__generic_done()

        def item_output(self, force=False):
                self.__generic_output("item_phase", "item_phase_last",
                    force=force)

        def item_output_done(self):
                self.__generic_done()

        def flush(self):
                try:
                        if self.needs_cr:
                                print "\n",
                                self.needs_cr = False
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

        def __init__(self, parsable_version=None, quiet=False, verbose=0):
                ProgressTracker.__init__(self,
                    parsable_version=parsable_version, quiet=quiet,
                    verbose=verbose)

                self.act_started = False
                self.ind_started = False
                self.item_started = False
                self.last_print_time = 0
                self.clear_eol = ""
                self.msg_prefix = ""

                try:
                        import curses
                        if not os.isatty(sys.stdout.fileno()):
                                raise ProgressTrackerException()

                        curses.setupterm()
                        self.cr = curses.tigetstr("cr")
                        self.clear_eol = curses.tigetstr("el") or ""
                except KeyboardInterrupt:
                        raise
                except:
                        if portable.ostype == "windows" and \
                            os.isatty(sys.stdout.fileno()):
                                self.cr = '\r'
                        else:
                                raise ProgressTrackerException()
                self.spinner = 0
                self.spinner_chars = "/-\|"
                self.curstrlen = 0

        def set_linked_name(self, lin):
                self.msg_prefix = ""
                if lin:
                        self.msg_prefix = _("Image %s ") % lin

        def __generic_start(self, msg):
                # Ensure the last message displayed is flushed in case the
                # corresponding operation did not complete successfully.
                self.__generic_done()
                self.curstrlen = len(msg)
                try:
                        print "%s" % msg,
                        self.needs_cr = True
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
                        self.needs_cr = False
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
                        msg = _("Refreshing catalog %(current)d/%(total)d "
                            "%(publisher)s") % {
                            "current": self.refresh_cur_pub_cnt,
                            "total": self.refresh_pub_cnt,
                            "publisher": self.refresh_cur_pub }
                        msg = "%s%s" % (self.msg_prefix, msg)
                        self.curstrlen = len(msg)
                        print "%s" % msg,
                        self.needs_cr = True
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

                msg = _("Creating Plan")
                msg = "%s%s" % (self.msg_prefix, msg)

                self.curstrlen = len(msg)
                try:
                        print "%s" % msg,
                        self.needs_cr = True
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
                        msg = _("Creating Plan %c") % self.spinner_chars[
                            self.spinner]
                        msg = "%s%s" % (self.msg_prefix, msg)

                        self.curstrlen = len(msg)
                        print "%s" % msg,
                        self.needs_cr = True
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def eval_output_done(self):
                self.__generic_done()
                self.last_print_time = 0

        def li_recurse_start(self, lin):
                self.__generic_done()

                msg = _("Recursing into linked image: %s") % lin
                msg = "%s%s" % (self.msg_prefix, msg)

                try:
                        print "%s" % msg, self.cr
                        self.curstrlen = len(msg)
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def li_recurse_end(self, lin):
                msg = _("Returning from linked image: %s") % lin
                msg = "%s%s" % (self.msg_prefix, msg)

                try:
                        print "%s" % msg, self.cr
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

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
                        s = "%-70s..... %c%c" % \
                            (self.ver_cur_fmri.get_pkg_stem(),
                             self.spinner_chars[self.spinner],
                             self.spinner_chars[self.spinner])
                        self.curstrlen = len(s)
                        sys.stdout.write(s + self.clear_eol + self.cr)
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
                        self.needs_cr = False
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def ver_output_warning(self, actname, warnings):
                # Display logic is the same as that for errors.
                return self.ver_output_error(actname, warnings)

        def ver_output_info(self, actname, info):
                # Display logic is the same as that for errors.
                return self.ver_output_error(actname, info)

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
                        self.needs_cr = False
                        sys.stdout.flush()
                        self.last_print_time = 0
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def archive_output(self, force=False):
                if self.item_started and not force and \
                    (time.time() - self.last_print_time) < self.TERM_DELAY:
                        return

                self.last_print_time = time.time()
                try:
                        # The first time, emit header.
                        if not self.item_started:
                                self.item_started = True
                                if self.last_print_time:
                                        print
                                print "%-45s %11s %12s" % (_("ARCHIVE"),
                                    _("FILES"), _("STORE (MB)"))
                        else:
                                print self.cr,

                        s = "%-45.45s %11s %12s" % \
                            (self.item_phase,
                                "%d/%d" % \
                                (self.item_cur_nitems,
                                self.item_goal_nitems),
                            "%.1f/%.1f" % \
                                ((self.item_cur_nbytes / 1024.0 / 1024.0),
                                (self.item_goal_nbytes / 1024.0 / 1024.0)))
                        sys.stdout.write(s + self.clear_eol)
                        self.needs_cr = True
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def archive_output_done(self):
                self.archive_output(force=True)
                self.__generic_simple_done()

        def dl_output(self, force=False):
                if self.dl_started and not force and \
                    (time.time() - self.last_print_time) < self.TERM_DELAY:
                        return

                self.last_print_time = time.time()

                try:
                        # The first time, emit header.
                        if not self.dl_started:
                                self.dl_started = True
                                print "%-38s %7s %11s %12s" % (_("DOWNLOAD"),
                                    _("PKGS"), _("FILES"), _("XFER (MB)"))
                        else:
                                print self.cr,
                                self.needs_cr = True

                        pkg_name = self.cur_pkg
                        if len(pkg_name) > 38:
                                pkg_name = "..." + pkg_name[-34:]

                        s = "%-38.38s %7s %11s %12s" % \
                            (pkg_name,
                            "%d/%d" % (self.dl_cur_npkgs, self.dl_goal_npkgs),
                            "%d/%d" % (self.dl_cur_nfiles, self.dl_goal_nfiles),
                            "%.1f/%.1f" % \
                                ((self.dl_cur_nbytes / 1024.0 / 1024.0),
                                (self.dl_goal_nbytes / 1024.0 / 1024.0)))
                        sys.stdout.write(s + self.clear_eol)
                        self.needs_cr = True
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def dl_output_done(self):
                self.cur_pkg = "Completed"
                self.dl_output(force=True)

                # Reset.
                self.dl_started = False
                self.spinner = 0
                self.curstrlen = 0

                try:
                        print
                        print
                        self.needs_cr = False
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def republish_output(self, force=False):
                if self.republish_started and not force and \
                    (time.time() - self.last_print_time) < self.TERM_DELAY:
                        return

                self.last_print_time = time.time()

                try:
                        # The first time, emit header.
                        if not self.republish_started:
                                self.republish_started = True
                                print "%-40s %12s %12s %12s" % (_("PROCESS"),
                                    _("ITEMS"), _("GET (MB)"), _("SEND (MB)"))
                        else:
                                print self.cr,
                                self.needs_cr = True

                        pkg_name = self.cur_pkg
                        if len(pkg_name) > 40:
                                pkg_name = "..." + pkg_name[-37:]

                        s = "%-40.40s %12s %12s %12s" % \
                            (pkg_name,
                            "%d/%d" % (self.item_cur_nitems,
                                self.item_goal_nitems),
                            "%.1f/%.1f" % \
                                ((self.dl_cur_nbytes / 1024.0 / 1024.0),
                                (self.dl_goal_nbytes / 1024.0 / 1024.0)),
                            "%.1f/%.1f" % \
                                ((self.send_cur_nbytes / 1024.0 / 1024.0),
                                (self.send_goal_nbytes / 1024.0 / 1024.0)))
                        sys.stdout.write(s + self.clear_eol)
                        self.needs_cr = True
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def republish_output_done(self):
                self.cur_pkg = "Completed"
                self.republish_output(force=True)

                # Reset.
                self.republish_started = False
                self.spinner = 0
                self.curstrlen = 0

                try:
                        print
                        print
                        self.needs_cr = False
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def __generic_simple_done(self):
                try:
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
                                print "%-40s %11s" % (_("PHASE"), _("ACTIONS"))
                        else:
                                print self.cr,

                        print "%-40s %11s" % \
                            (
                                self.act_phase,
                                "%d/%d" % (self.act_cur_nactions,
                                    self.act_goal_nactions)
                             ),
                        self.needs_cr = True

                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def act_output_done(self):
                self.act_output(force=True)
                self.__generic_simple_done()

        def index_optimize(self):
                self.ind_started = False
                self.last_print_time = 0
                try:
                        msg = _("Optimizing Index...")
                        msg = "%s%s" % (self.msg_prefix, msg)

                        print msg
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
                                if self.last_print_time:
                                        print
                                print "%-40s %11s" % (_("PHASE"), _("ITEMS"))
                        else:
                                print self.cr,

                        print "%-40s %11s" % \
                            (
                                self.ind_phase,
                                "%d/%d" % (self.ind_cur_nitems,
                                    self.ind_goal_nitems)
                             ),

                        self.needs_cr = True
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def ind_output_done(self):
                self.ind_output(force=True)
                self.__generic_simple_done()

        def item_output(self, force=False):
                if self.item_started and not force and \
                    (time.time() - self.last_print_time) < self.TERM_DELAY:
                        return

                self.last_print_time = time.time()
                try:
                        # The first time, emit header.
                        if not self.item_started:
                                self.item_started = True
                                if self.last_print_time:
                                        print
                                print "%-40s %11s" % (_("PHASE"), _("ITEMS"))
                        else:
                                print self.cr,

                        print "%-40s %11s" % \
                            (
                                self.item_phase,
                                "%d/%d" % (self.item_cur_nitems,
                                    self.item_goal_nitems)
                             ),

                        self.needs_cr = True
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def item_output_done(self):
                self.item_output(force=True)
                self.__generic_simple_done()

        def flush(self):
                try:
                        if self.needs_cr:
                                print "\n",
                                self.needs_cr = False
                        sys.stdout.flush()
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise
