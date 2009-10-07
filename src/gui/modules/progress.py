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

MIN_IND_ELEMENTS_BOUNCE = 5      # During indexing the progress will be progressive if 
                                 # the number of indexing elements is greater then this, 
                                 # otherwise it will bounce

from pkg.client.progress import NullProgressTracker
import pkg.misc

class GuiProgressTracker(NullProgressTracker):

        def __init__(self):
                NullProgressTracker.__init__(self)
                self.prev_pkg = None
                self.act_phase_last = None
                self.ind_started = None

        def cat_output_start(self):
                self.update_details_text(_("Retrieving catalog '%s'...\n") % \
                    self.cat_cur_catalog)
                return

        def cat_output_done(self):
                return

        def cache_cats_output_start(self):
                self.update_details_text(_("Caching catalogs ...\n"))
                return

        def cache_cats_output_done(self):
                return

        def load_cat_cache_output_start(self):
                self.update_details_text(_("Loading catalog cache ...\n"))
                return

        def load_cat_cache_output_done(self):
                return

        def refresh_output_start(self):
                return

        def refresh_output_progress(self):
                self.update_details_text(
                    _("Refreshing catalog %s\n") % self.refresh_cur_pub)
                return

        def refresh_output_done(self):
                self.update_details_text(
                    _("Finished refreshing catalog %s\n") % self.refresh_cur_pub)
                return

        def eval_output_start(self):
                return

        def eval_output_progress(self):
                '''Called by progress tracker each time some package was evaluated. The
                call is being done by calling progress tracker evaluate_progress() 
                function'''
                if self.prev_pkg != self.eval_cur_fmri:
                        self.prev_pkg = self.eval_cur_fmri
                        self.update_details_text("%s\n" % self.eval_cur_fmri,
                            "level1")
                        text = _("Evaluating: %s") % self.eval_cur_fmri.get_name()
                        self.update_label_text(text)

        def eval_output_done(self):
                return

        def ver_output(self):
                return

        def ver_output_error(self, actname, errors):
                return

        def ver_output_done(self):
                return

        def dl_output(self):
                self.update_progress(self.dl_cur_nbytes, self.dl_goal_nbytes)
                size_a_str = ""
                size_b_str = ""
                if self.dl_cur_nbytes >= 0:
                        size_a_str = pkg.misc.bytes_to_str(self.dl_cur_nbytes)
                if self.dl_goal_nbytes >= 0:
                        size_b_str = pkg.misc.bytes_to_str(self.dl_goal_nbytes)
                c = _("Downloaded %(current)s of %(total)s") % \
                    {"current" : size_a_str,
                    "total" : size_b_str}
                self.update_label_text(c)
                if self.prev_pkg != self.dl_cur_pkg:
                        self.prev_pkg = self.dl_cur_pkg
                        self.update_details_text(
                            _("Package %d of %d: %s\n") % (self.dl_cur_npkgs+1, 
                            self.dl_goal_npkgs, self.dl_cur_pkg), "level1")

        def dl_output_done(self):
                self.update_details_text("\n")

        def act_output(self, force=False):
                if self.act_phase != self.act_phase_last:
                        self.act_phase_last = self.act_phase
                        self.update_label_text(self.act_phase)
                        self.update_details_text(_("%s\n") % self.act_phase, "level1")
                self.update_progress(self.act_cur_nactions, self.act_goal_nactions)
                return

        def act_output_done(self):
                return

        def ind_output(self, force=False):
                if self.ind_started != self.ind_phase:
                        self.ind_started = self.ind_phase
                        self.update_label_text(self.ind_phase)
                        self.update_details_text(
                            _("%s\n") % (self.ind_phase), "level1")
                self.__indexing_progress()

        def ind_output_done(self):
                self.update_progress(self.ind_cur_nitems, self.ind_goal_nitems)

        def __indexing_progress(self):
                #It doesn't look nice if the progressive is just for few elements
                if self.ind_goal_nitems > MIN_IND_ELEMENTS_BOUNCE:
                        self.update_progress(self.ind_cur_nitems-1, self.ind_goal_nitems)
                else:
                        if not self.is_progress_bouncing():
                                self.start_bouncing_progress()

        def update_progress(self, current_progress, total_progress):
                raise NotImplementedError("abstract method update_progress() not "
                    "implemented in superclass")

        def start_bouncing_progress(self):
                raise NotImplementedError("abstract method start_bouncing_progress() "
                    "not implemented in superclass")

        def is_progress_bouncing(self):
                raise NotImplementedError("abstract method is_progress_bouncing() "
                    "not implemented in superclass")

        def stop_bouncing_progress(self):
                raise NotImplementedError("abstract method stop_bouncing_progress() "
                    "not implemented in superclass")

        def update_label_text(self, text):
                raise NotImplementedError("abstract method update_label_text() "
                    "not implemented in superclass")

        def update_details_text(self, text, *tags):
                raise NotImplementedError("abstract method update_details_text() "
                    "not implemented in superclass")

