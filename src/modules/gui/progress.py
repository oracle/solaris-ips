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
# Copyright (c) 2009, 2012, Oracle and/or its affiliates. All rights reserved.
#

# Display linear, incremental progress if the # of elements is greater than
# this, else bounce back and forth.
MIN_ELEMENTS_BOUNCE = 5  

import pkg.client.progress as progress
import pkg.client.pkgdefs as pkgdefs

class GuiProgressTracker(progress.ProgressTracker):

        def __init__(self, indent = False):
                progress.ProgressTracker.__init__(self)
                self.dl_prev_pkg = None
                self.last_actionitem = None
                self.ind_started = False
                self.item_started = False
                self.indent = indent

        def _change_purpose(self, old_purpose, new_purpose):
                pass

        def _cache_cats_output(self, outspec):
                if outspec.first:
                        i = "level1" if self.indent else ""
                        self.update_details_text(_("Caching catalogs ..."), i)
                if outspec.last:
                        self.update_details_text("\n")
                return

        def _load_cat_cache_output(self, outspec):
                if outspec.first:
                        i = "level1" if self.indent else ""
                        self.update_details_text(
                            _("Loading catalog cache ..."), i)
                if outspec.last:
                        self.update_details_text("\n")
                return

        def _refresh_output_progress(self, outspec):
                i = "level1" if self.indent else ""

                if "startpublisher" in outspec.changed:
                        if self.refresh_full_refresh:
                                msg = _("Retrieving catalog: %s") % \
                                    self.pub_refresh.curinfo
                        else:
                                msg = _("Refreshing catalog: %s") % \
                                    self.pub_refresh.curinfo
                        self.update_details_text(msg, i)
                if "endpublisher" in outspec.changed:
                        self.update_details_text("\n", i)
                return

        def _plan_output(self, outspec, planitem):
                '''Called by progress tracker each time some package was
                evaluated. The call is being done by calling progress tracker
                evaluate_progress() function'''
                if self.purpose == self.PURPOSE_PKG_UPDATE_CHK:
                        if not outspec.first:
                                return
                        text = _("Up to date check: planning (%s)") % \
                            planitem.name
                        self.update_label_text(text)
                        return

                text = _("Planning: %s") % planitem.name
                if outspec.first:
                        self.update_label_text(text)
                        i = "level1" if self.indent else ""
                        self.update_details_text(text + _("... "), i)
                if outspec.last:
                        self.update_details_text(_("Done\n"))

                if isinstance(planitem, progress.GoalTrackerItem):
                        self.__generic_progress(text, planitem.items,
                            planitem.goalitems)
                else:
                        self.__generic_progress(text, 1, 1)

                if outspec.last:
                        self.reset_label_text_after_delay()

        def _plan_output_all_done(self):
                text = _("Planning: Complete\n")
                self.update_label_text(text)
                i = "level1" if self.indent else ""
                self.update_details_text(text, i)

        def _mfst_fetch(self, outspec):
                if outspec.first:
                        text = _("Fetching %d manifests") % \
                            self.mfst_fetch.goalitems
                        self.update_label_text(text)
                        self.stop_bouncing_progress()

                if "manifests" in outspec.changed:
                        self.__generic_progress("Fetching manifests",
                            self.mfst_fetch.items + 1,
                            self.mfst_fetch.goalitems)

                if outspec.last:
                        self.start_bouncing_progress()
                pass

        def _mfst_commit(self, outspec):
                text = _("Committing manifests")
                self.update_label_text(text)
                pass

        def _ver_output(self): pass
        def _ver_output_error(self, actname, errors): pass
        def _ver_output_warning(self, actname, warnings): pass
        def _ver_output_info(self, actname, info): pass
        def _ver_output_done(self): pass

        def _dl_output(self, outspec):
                self.display_download_info()
                if "startpkg" in outspec.changed:
                        self.update_details_text(
                            _("Package %d of %d: %s\n") % (
                            self.dl_pkgs.items + 1,
                            self.dl_pkgs.goalitems, self.dl_pkgs.curinfo),
                            "level1")

                if outspec.last:
                        self.update_details_text("\n")

        def _act_output(self, outspec, actionitem):
                if actionitem != self.last_actionitem:
                        self.last_actionitem = actionitem
                        self.update_label_text(actionitem.name)
                        self.update_details_text("%s\n" % actionitem.name,
                            "level1")
                if actionitem.goalitems > 0:
                        self.display_phase_info(actionitem.name,
                            actionitem.items,
                            actionitem.goalitems)
                return

        def _act_output_all_done(self):
                return

        def _job_output(self, outspec, job):
                if outspec.first:
                        self.update_label_text(job.name)
                        self.update_details_text(
                            "%s ... " % (job.name), "level1")

                if isinstance(job, progress.GoalTrackerItem):
                        self.__generic_progress(job.name, job.items,
                            job.goalitems)
                else:
                        self.__generic_progress(job.name, 1, 1)

                if outspec.last:
                        self.update_details_text(_("Done\n"))
                return

        def _li_recurse_start_output(self):
                pass

        def _li_recurse_end_output(self):
                # elide output for publisher check
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        return
                i = "level1" if self.indent else ""
                self.update_details_text(
                    _("Finished processing linked images.\n\n"), i)

        def __li_dump_output(self, output):
                i = "level1" if self.indent else ""
                if not output:
                        return
                lines = output.splitlines()
                nlines = len(lines)
                for linenum, line in enumerate(lines):
                        if linenum < nlines - 1:
                                self.update_details_text("| " + line + "\n", i)
                        else:
                                if lines[linenum].strip() != "":
                                        self.update_details_text(
                                            "| " + line + "\n", i)
                                self.update_details_text("`\n", i)
                        
        def _li_recurse_output_output(self, lin, stdout, stderr):
                if not stdout and not stderr:
                        return
                i = "level1" if self.indent else ""
                self.update_details_text(_("Linked image '%s' output:\n") % lin,
                    i)
                self.__li_dump_output(stdout)
                self.__li_dump_output(stderr)

        def _li_recurse_status_output(self, done):
                if self.linked_pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        return

                i = "level1" if self.indent else ""

                running = " ".join([str(s) for s in self.linked_running])
                msg = _("Linked images: %s done; %d working: %s\n") % \
                    (progress.format_pair("%d", done, self.linked_total),
                    len(self.linked_running), running)
                self.update_details_text(msg, i)

        def _li_recurse_progress_output(self, lin):
                self.__generic_progress("Linked Images", 1, 1)
                pass

        def __generic_progress(self, phase, cur_nitems, goal_nitems):
                # It doesn't look nice if the progressive is just for few
                # elements
                if goal_nitems > MIN_ELEMENTS_BOUNCE:
                        if self.is_progress_bouncing():
                                self.stop_bouncing_progress()
                        self.display_phase_info(phase, cur_nitems-1,
                            goal_nitems)
                else:
                        if not self.is_progress_bouncing():
                                self.start_bouncing_progress()

        @progress.pt_abstract
        def update_progress(self, current_progress, total_progress): pass

        @progress.pt_abstract
        def start_bouncing_progress(self): pass

        @progress.pt_abstract
        def is_progress_bouncing(self): pass

        @progress.pt_abstract
        def stop_bouncing_progress(self): pass

        @progress.pt_abstract
        def display_download_info(self): pass

        @progress.pt_abstract
        def display_phase_info(self, phase_name, cur_n, goal_n): pass

        @progress.pt_abstract
        def reset_label_text_after_delay(self): pass

        @progress.pt_abstract
        def update_label_text(self, text): pass

        @progress.pt_abstract
        def update_details_text(self, text, *tags): pass

