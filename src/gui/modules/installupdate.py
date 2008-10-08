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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import errno
import gettext # XXX Temporary workaround
import itertools
import os
import sys
import time
from threading import Thread
from urllib2 import URLError
try:
        import gobject
        import gtk
        import gtk.glade
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)
import pkg.client.bootenv as bootenv
import pkg.client.history as history
import pkg.client.imageplan as imageplan
import pkg.client.imagestate as imagestate
import pkg.client.imageconfig as imageconfig
import pkg.client.progress as progress
import pkg.client.retrieve as retrieve
import pkg.client.api_errors as api_errors
import pkg.fmri as fmri
import pkg.client.indexer as indexer
import pkg.search_errors as search_errors
from pkg.misc import TransferTimedOutException
from pkg.misc import CLIENT_DEFAULT_MEM_USE_KB
import pkg.gui.enumerations as enumerations
import pkg.gui.filelist as filelist
import pkg.gui.thread as guithread
from pkg.gui.filelist import CancelException

class InstallUpdate(progress.ProgressTracker):
        def __init__(self, install_list, parent, \
            image_update = False, ips_update = False):
                # XXX Workaround as BE is using msg(_("message")) 
                # which bypasses the self._ mechanism the GUI is using
                gettext.install("pkg","/usr/lib/locale")
                progress.ProgressTracker.__init__(self)
                self.gui_thread = guithread.ThreadRun()
                self.install_list = install_list
                self.update_list = None
                self.parent = parent
                self.image_update = image_update
                self.ips_update = ips_update
                self.ip = None
                self.progress_stop_timer_thread = False
                self.progress_stop_timer_running = False                
                w_tree_createplan = gtk.glade.XML(parent.gladefile, "createplandialog")
                w_tree_installupdate = gtk.glade.XML(parent.gladefile, "installupdate")
                w_tree_downloadingfiles = \
                    gtk.glade.XML(parent.gladefile, "downloadingfiles")
                w_tree_installingdialog = \
                    gtk.glade.XML(parent.gladefile, "installingdialog") 
                w_tree_networkdown = gtk.glade.XML(parent.gladefile, "networkdown")
                self.w_createplan_dialog = \
                    w_tree_createplan.get_widget("createplandialog")                    
                self.w_createplan_progressbar = \
                    w_tree_createplan.get_widget("createplanprogress") 
                self.w_createplan_textview = \
                    w_tree_createplan.get_widget("createplantextview")
                self.w_createplan_label = \
                    w_tree_createplan.get_widget("packagedependencies")
                self.w_createplancancel_button = \
                    w_tree_createplan.get_widget("cancelcreateplan")
                self.w_installupdate_dialog = w_tree_installupdate.get_widget("installupdate")
                self.w_summary_label = w_tree_installupdate.get_widget("packagenamelabel3")
                self.w_review_treeview = w_tree_installupdate.get_widget("treeview1")
                self.w_downloadingfiles_dialog = \
                    w_tree_downloadingfiles.get_widget("downloadingfiles")
                self.w_download_textview = \
                    w_tree_downloadingfiles.get_widget("downloadtextview")
                self.w_download_progressbar = \
                    w_tree_downloadingfiles.get_widget("downloadprogress")
                self.w_installing_dialog = \
                    w_tree_installingdialog.get_widget("installingdialog")
                self.w_installingdialog_label = \
                    w_tree_installingdialog.get_widget("packagedependencies3")                    
                self.w_installingdialog_expander = \
                    w_tree_installingdialog.get_widget("expander4")                     
                self.w_installing_textview = \
                    w_tree_installingdialog.get_widget("installingtextview")
                self.w_installing_progressbar = \
                    w_tree_installingdialog.get_widget("installingprogress")
                self.w_networkdown_dialog = w_tree_networkdown.get_widget("networkdown")
                self.w_createplan_progressbar.set_pulse_step(0.1)
                installed_updated_column = gtk.TreeViewColumn('Installed/Updated')
                self.w_review_treeview.append_column(installed_updated_column)
                cell = gtk.CellRendererText()
                installed_updated_column.pack_start(cell, True)
                installed_updated_column.add_attribute(cell, 'text', 0)
                self.w_review_treeview.expand_all()
                try:
                        dic_createplan = \
                            {
                                "on_cancelcreateplan_clicked": \
                                    self.__on_cancelcreateplan_clicked,
                            }
                        dic_installupdate = \
                            {
                                "on_cancel_button_clicked": \
                                    self.__on_cancel_button_clicked,
                                "on_next_button_clicked":self.__on_next_button_clicked,
                            }
                        dic_downloadingfiles = \
                            {
                                "on_canceldownload_clicked": \
                                    self.__on_cancel_download_clicked,
                            }
                        dic_networkdown = \
                            {
                                "on_networkdown_close_clicked": \
                                    self.__on_networkdown_close_clicked,
                            }
                        w_tree_createplan.signal_autoconnect(dic_createplan)
                        w_tree_installupdate.signal_autoconnect(dic_installupdate)
                        w_tree_downloadingfiles.signal_autoconnect(dic_downloadingfiles)
                        w_tree_networkdown.signal_autoconnect(dic_networkdown)
                except AttributeError, error:
                        print self.parent._('GUI will not respond to any event! %s. \
                            Check installupdate.py signals') \
                            % error
                if image_update or ips_update:
                        list_of_packages = install_list
                else:
                        list_of_packages = self.__prepare_list_of_packages()
                # XXX Hidden until progress will give information about fmri                        
                self.w_installingdialog_expander.hide()
                pulse_t = Thread(target = self.__progressdialog_progress_pulse)
                thread = Thread(target = self.__plan_the_install_updateimage, \
                    args = (list_of_packages, ))
                pulse_t.start()
                thread.start()
                self.w_createplan_label.set_text(\
                    self.parent._("Checking package dependencies..."))
                self.w_createplancancel_button.set_sensitive(True)           
                self.w_createplan_dialog.run()

        def __on_cancelcreateplan_clicked(self, widget):
                '''Handler for signal send by cancel button, which user might press during
                evaluation stage - while the dialog is creating plan'''
                self.ip.image.history.operation_result = \
                    history.RESULT_CANCELED
                self.w_createplan_label.set_text(\
                    self.parent._("Canceling..."))
                self.w_createplancancel_button.set_sensitive(False)                    
                self.gui_thread.cancel()

        def __on_cancel_button_clicked(self, widget):
                '''Handler for signal send by cancel button, which is available for the 
                user after evaluation stage on the dialog showing what will be installed
                or updated'''
                self.ip.image.history.operation_result = \
                    history.RESULT_CANCELED
                self.gui_thread.cancel()
                self.w_installupdate_dialog.destroy()

        def __on_next_button_clicked(self, widget):
                '''Handler for signal send by next button, which is available for the 
                user after evaluation stage on the dialog showing what will be installed
                or updated'''
                download_thread = Thread(target = self.__download_stage, args = ())
                download_thread.start()

        def __on_cancel_download_clicked(self, widget):
                '''Handler for signal send by cancel button, which user might press during
                download stage.'''
                self.ip.image.history.operation_result = \
                    history.RESULT_CANCELED
                self.gui_thread.cancel()
                self.w_downloadingfiles_dialog.destroy()

        def __on_networkdown_close_clicked(self, widget):
                '''Handler for signal send by close button on the dialog showing that
                there was some problem with the network connection.'''
                self.ip.image.history.operation_result = \
                    history.RESULT_FAILED_TRANSPORT
                self.gui_thread.cancel()
                self.w_networkdown_dialog.destroy()

        def __update_createplan_progress(self, action):
                buf = self.w_createplan_textview.get_buffer()
                textiter = buf.get_end_iter()
                buf.insert(textiter, action)
                
        def __progressdialog_progress_pulse(self):
                while not self.progress_stop_timer_thread:
                        gobject.idle_add(self.w_createplan_progressbar.pulse)
                        time.sleep(0.1)

        def __update_download_progress(self, cur_bytes, total_bytes):
                prog = float(cur_bytes)/total_bytes
                self.w_download_progressbar.set_fraction(prog)
                a = str(cur_bytes/1024)
                b = str(total_bytes/1024)
                c = "Downloaded: " + a + " / " + b + " KB"
                self.w_download_progressbar.set_text(c)

        def __update_install_progress(self, current, total):
                prog = float(current)/total
                self.w_installing_progressbar.set_fraction(prog)

        def __update_install_pulse(self):
                while not self.progress_stop_timer_thread:
                        self.progress_stop_timer_running = True
                        gobject.idle_add(self.w_installing_progressbar.pulse)
                        time.sleep(0.1)
                self.progress_stop_timer_running = False

        def __prepare_list_of_packages(self):
                ''' This method return the dictionary of 
                images and newest marked packages'''
                fmri_to_install_update = {}
                for row in self.install_list:
                        if row[enumerations.MARK_COLUMN]:
                                image = row[enumerations.IMAGE_OBJECT_COLUMN]
                                packages = row[enumerations.PACKAGE_OBJECT_COLUMN]
                                im = fmri_to_install_update.get(image)
                                # XXX Hack to be bug to bug compatible - incorporations
                                pkg_name = packages[0].get_name()
                                if im:
                                        im.append(pkg_name)
                                else:
                                        fmri_to_install_update[image] = [pkg_name, ]
                return fmri_to_install_update

        def __plan_the_install_updateimage(self, list_of_packages):
                '''Function which plans the image'''
                self.gui_thread.run()
                filters = []
                verbose = False
                noexecute = False
                for image in list_of_packages:
                        # Take a list of packages, specified in pkg_list, and attempt
                        # to assemble an appropriate image plan.  This is a helper
                        # routine for some common operations in the client.
                        #
                        # This method checks all authorities for a package match;
                        # however, it defaults to choosing the preferred authority
                        # when an ambiguous package name is specified.  If the user
                        # wishes to install a package from a non-preferred authority,
                        # the full FMRI that contains an authority should be used
                        # to name the package.

                        pkg_list = list_of_packages.get(image)

                        error = 0
                        self.ip = imageplan.ImagePlan(image, self,
                            self.gui_thread.is_cancelled, filters = filters)
                        if self.image_update:
                                self.ip.image.history.operation_name = \
                                    "image-update"
                        else:
                                self.ip.image.history.operation_name = \
                                    "install"

                        self.__load_optional_dependencies(image)

                        for p in pkg_list:
                                try:
                                        conp = image.apply_optional_dependencies(p)
                                        matches = list(image.inventory([ conp ],
                                            all_known = True))
                                except (RuntimeError,
                                    api_errors.InventoryException):
                                        # XXX Module directly printing.
                                        error = 1
                                        continue

                                pnames = {}
                                pmatch = []
                                npnames = {}
                                npmatch = []
                                for m, state in matches:
                                        if m.preferred_authority():
                                                pnames[m.get_pkg_stem()] = 1
                                                pmatch.append(m)
                                        else:
                                                npnames[m.get_pkg_stem()] = 1
                                                npmatch.append(m)

                                if len(pnames.keys()) > 1:
                                        # XXX Module directly printing.
                                        error = 1
                                        continue
                                elif len(pnames.keys()) < 1 and len(npnames.keys()) > 1:
                                        # XXX Module directly printing.
                                        error = 1
                                        continue

                                # matches is a list reverse sorted by version, so take
                                # the first; i.e., the latest.
                                if len(pmatch) > 0:
                                        self.ip.propose_fmri(pmatch[0])
                                else:
                                        self.ip.propose_fmri(npmatch[0])

                        if error != 0:
                                raise RuntimeError, "Unable to assemble image plan"

                        self.ip.image.history.operation_start_state = \
                            self.ip.get_plan()

                        try:
                                self.__evaluate(image)
                        except CancelException, e:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                        else:
                                self.ip.image.history.operation_end_state = \
                                    self.ip.get_plan(full=False)

                        image.imageplan = self.ip

                return

        def __load_optional_dependencies(self, image):
                for b_fmri in image.gen_installed_pkgs():
                        if self.gui_thread.is_cancelled():
                                return
                        mfst = image.get_manifest(b_fmri, filtered = True)

                        for dep in mfst.gen_actions_by_type("depend"):
                                required, min_fmri, max_fmri = dep.parse(image)
                                if required == False:
                                        image.update_optional_dependency(min_fmri)

        def __evaluate(self, image):
                '''Code duplication from imageplan.evaluate()'''
                assert self.ip.state == imageplan.UNEVALUATED

                self.ip.progtrack.evaluate_start()

                outstring = ""
                
                # Operate on a copy, as it will be modified in flight.
                for f in self.ip.target_fmris[:]:
                        self.ip.progtrack.evaluate_progress()
                        try:
                                self.__evaluate_fmri(f, image)
                        except KeyError, e:
                                outstring += "Attemping to install %s causes:\n\t%s\n" % \
                                    (f.get_name(), e)
                        except (retrieve.ManifestRetrievalError,
                            retrieve.DatastreamRetrievalError, NameError):
                                gobject.idle_add(self.__creating_plan_net_error)
                                return
                if outstring:
                        raise RuntimeError("No packages were installed because "
                            "package dependencies could not be satisfied\n" +
                            outstring)                        
                                
                for f in self.ip.target_fmris:
                        self.ip.add_pkg_plan(f)
                        self.ip.progtrack.evaluate_progress()

                for f in self.ip.target_rem_fmris[:]:
                        self.ip.evaluate_fmri_removal(f)
                        self.ip.progtrack.evaluate_progress()

                # we now have a workable set of packages to add/upgrade/remove
                # now combine all actions together to create a synthetic single
                # step upgrade operation, and handle editable files moving from
                # package to package.  See theory comment in execute, below.

                self.ip.state = imageplan.EVALUATED_PKGS

                self.ip.removal_actions = [ (p, src, dest)
                                         for p in self.ip.pkg_plans
                                         for src, dest in p.gen_removal_actions()
                ]

                self.ip.update_actions = [ (p, src, dest)
                                        for p in self.ip.pkg_plans
                                        for src, dest in p.gen_update_actions()
                ]

                self.ip.install_actions = [ (p, src, dest)
                                         for p in self.ip.pkg_plans
                                         for src, dest in p.gen_install_actions()
                ]

                self.ip.progtrack.evaluate_progress()

                # iterate over copy of removals since we're modding list
                # keep track of deletion count so later use of index works
                named_removals = {}
                deletions = 0
                for i, a in enumerate(self.ip.removal_actions[:]):
                        # remove dir removals if dir is still in final image
                        if a[1].name == "dir" and \
                            os.path.normpath(a[1].attrs["path"]) in \
                            self.ip.get_directories():
                                del self.ip.removal_actions[i - deletions]
                                deletions += 1
                                continue
                        # store names of files being removed under own name
                        # or original name if specified
                        if a[1].name == "file":
                                attrs = a[1].attrs
                                fname = attrs.get("original_name",
                                    "%s:%s" % (a[0].origin_fmri.get_name(), attrs["path"]))
                                named_removals[fname] = \
                                    (i - deletions,
                                    id(self.ip.removal_actions[i-deletions][1]))

                self.ip.progtrack.evaluate_progress()

                for a in self.ip.install_actions:
                        # In order to handle editable files that move their path or
                        # change pkgs, for all new files with original_name attribute,
                        # make sure file isn't being removed by checking removal list.
                        # if it is, tag removal to save file, and install to recover
                        # cached version... caching is needed if directories
                        # are removed or don't exist yet.
                        if a[2].name == "file" and "original_name" in a[2].attrs and \
                            a[2].attrs["original_name"] in named_removals:
                                cache_name = a[2].attrs["original_name"]
                                index = named_removals[cache_name][0]
                                assert(id(self.ip.removal_actions[index][1]) ==
                                       named_removals[cache_name][1])
                                self.ip.removal_actions[index][1].attrs["save_file"] = \
                                    cache_name
                                a[2].attrs["save_file"] = cache_name

                self.ip.progtrack.evaluate_progress()
                # Go over update actions
                l_actions = self.ip.get_link_actions()
                l_refresh = []
                for a in self.ip.update_actions:
                        # for any files being updated that are the target of
                        # _any_ hardlink actions, append the hardlink actions
                        # to the update list so that they are not broken...
                        if a[2].name == "file":
                                path = a[2].attrs["path"]
                                if path in l_actions:
                                        l_refresh.extend([(a[0], l, l) for l in l_actions[path]])
                self.ip.update_actions.extend(l_refresh)
                # sort actions to match needed processing order
                self.ip.removal_actions.sort(key = lambda obj:obj[1], reverse=True)
                self.ip.update_actions.sort(key = lambda obj:obj[2])
                self.ip.install_actions.sort(key = lambda obj:obj[2])

                self.ip.progtrack.evaluate_done()

                self.ip.state = imageplan.EVALUATED_OK

        def __creating_plan_net_error(self):
                '''Helper method which shows the dialog informing user that there was
                problem with network connection'''
                self.progress_stop_timer_thread = True
                self.w_createplan_dialog.hide()
                self.w_networkdown_dialog.show()

        def __evaluate_fmri(self, pfmri, image):

                if self.gui_thread.is_cancelled():
                        raise CancelException
                gobject.idle_add(self.__update_createplan_progress, \
                    self.parent._("Evaluating: %s\n") % pfmri.get_fmri())

                self.ip.progtrack.evaluate_progress()
                self.ip.image.state.set_target(pfmri, imagestate.INTENT_PROCESS)
                m = image.get_manifest(pfmri)

                # [manifest] examine manifest for dependencies
                for a in m.actions:
                        if a.name != "depend":
                                continue

                        type = a.attrs["type"]

                        f = fmri.PkgFmri(a.attrs["fmri"],
                            self.ip.image.attrs["Build-Release"])

                        if self.ip.image.has_version_installed(f) and \
                                    type != "exclude":
                                continue

                        # XXX This alone only prevents infinite recursion when a
                        # cycle member is on the commandline, as we never update
                        # target_fmris.  Is target_fmris supposed to be just
                        # what was specified on the commandline, or include what
                        # we've found while processing dependencies?
                        # XXX probably should just use propose_fmri() here
                        # instead of this and the has_version_installed() call
                        # above.
                        if self.ip.is_proposed_fmri(f):
                                continue

                        # XXX LOG  "%s not in pending transaction;
                        # checking catalog" % f

                        required = True
                        excluded = False
                        if type == "optional" and \
                            not self.ip.image.cfg_cache.get_policy(imageconfig.REQUIRE_OPTIONAL):
                                required = False
                        elif type == "transfer" and \
                            not self.ip.image.older_version_installed(f):
                                required = False
                        elif type == "exclude":
                                excluded = True
                        elif type == "incorporate":
                                self.ip.image.update_optional_dependency(f)
                                if self.ip.image.older_version_installed(f) or \
                                    self.ip.older_version_proposed(f):
                                        required = True
                                else:
                                        required = False

                        if not required:
                                continue

                        if excluded:
                                self.ip.image.state.set_target()
                                raise RuntimeError, "excluded by '%s'" % f

                        # treat-as-required, treat-as-required-unless-pinned,
                        # ignore
                        # skip if ignoring
                        #     if pinned
                        #       ignore if treat-as-required-unless-pinned
                        #     else
                        #       **evaluation of incorporations**
                        #     [imageplan] pursue installation of this package
                        #     -->
                        #     backtrack or reset??

                        # This will be the newest version of the specified
                        # dependency package, coming from the preferred
                        # authority, if it's available there.
                        cf = self.ip.image.inventory([ a.attrs["fmri"] ],
                            all_known = True, preferred = True,
                            first_only = True).next()[0]

                        # XXX LOG "adding dependency %s" % pfmri

                        #msg("adding dependency %s" % cf)

                        self.ip.propose_fmri(cf)
                        self.__evaluate_fmri(cf, image)

                self.ip.image.state.set_target()

        def __download_stage(self, rebuild=False):
                '''Parts of the code duplicated from install and image-update from pkg(1) 
                and pkg.client.ImagePlan.preexecute()'''
                self.gui_thread.run()
                if not rebuild:
                        gobject.idle_add(self.w_installupdate_dialog.hide)
                if rebuild:
                        gobject.idle_add(self.w_installing_dialog.hide)
                gobject.idle_add(self.w_downloadingfiles_dialog.show)

                # Checks the index to make sure it exists and is
                # consistent. If it's inconsistent an exception is thrown.
                # If it's totally absent, it will index the existing packages
                # so that the incremental update that follows at the end of
                # the function will work correctly. It also repairs the index
                # for this BE so the user can boot into this BE and have a
                # correct index.
                try:
                        self.ip.image.update_index_dir()
                        ind = indexer.Indexer(self.ip.image.index_dir,
                            CLIENT_DEFAULT_MEM_USE_KB, progtrack=self.ip.progtrack)
                        if not ind.check_index_existence() or \
                            not ind.check_index_has_exactly_fmris(
                                self.ip.image.gen_installed_pkg_names()):
                                # XXX Once we have a framework for emitting a
                                # message to the user in this spot in the
                                # code, we should tell them something has gone
                                # wrong so that we continue to get feedback to
                                # allow us to debug the code.
                                ind.rebuild_index_from_scratch(
                                    self.ip.image.get_fmri_manifest_pairs())
                except search_errors.IndexingException:
                        # If there's a problem indexing, we want to attempt
                        # to finish the installation anyway. If there's a
                        # problem updating the index on the new image,
                        # that error needs to be communicated to the user.
                        pass

                
                try:
                        for p in self.ip.pkg_plans:
                                p.preexecute()

                        for package_plan in self.ip.pkg_plans:
                                if self.gui_thread.is_cancelled():
                                       return
                                self.__download(package_plan)
                except TransferTimedOutException:
                        gobject.idle_add(self.w_downloadingfiles_dialog.hide)
                        gobject.idle_add(self.w_networkdown_dialog.show)
                        return
                except URLError, e:
                        #if e.reason[0] == 8:
                        gobject.idle_add(self.w_downloadingfiles_dialog.hide)
                        gobject.idle_add(self.w_networkdown_dialog.show)
                        return
                except CancelException:
                        gobject.idle_add(self.w_downloadingfiles_dialog.hide)
                        return

                self.ip.progtrack.download_done()
                gobject.idle_add(self.w_downloadingfiles_dialog.hide)

                try:
                        be = bootenv.BootEnv(self.ip.image.get_root())
                except RuntimeError:
                        be = bootenv.BootEnvNull(self.ip.image.get_root())

                if self.image_update:
                        be.init_image_recovery(self.ip.image)
                        if self.ip.image.is_liveroot():
                                return 1
                try:
                        self.__installation_stage()
                        if self.image_update:
                                be.activate_image()
                        else:
                                be.activate_install_uninstall()
                        ret_code = 0
                except RuntimeError, e:
                        if self.image_update:
                                be.restore_image()
                        else:
                                be.restore_install_uninstall()
                        ret_code = 1
                except search_errors.InconsistentIndexException, e:
                        ret_code = 2
                except search_errors.PartialIndexingException, e:
                        ret_code = 2
                except search_errors.ProblematicPermissionsIndexException, e:
                        ret_code = 2
                except Exception, e:
                        if self.image_update:
                                be.restore_image()
                        else:
                                be.restore_install_uninstall()
                        self.ip.image.cleanup_downloads()
                        raise

                self.ip.image.cleanup_downloads()
                if ret_code == 0:
                        self.ip.image.cleanup_cached_content()
                elif ret_code == 2:
                        return_code = 0
                        return_code = self.__rebuild_index()
                        if return_code == 1:
                                return
                        self.__download_stage(True)

        def __download(self, package_plan):
                '''Code duplication from pkg.client.PkgPlan.download() except that
                pkg.gui.filelist is called instead of pkg.client.fileobject with shared
                cancel object - self.gui_thread that allows to cancel download 
                operation'''
                flist = filelist.FileList(self,
                    package_plan.image,
                    package_plan.destination_fmri,
                    self.gui_thread,
                    maxbytes = None
                    )
                _PkgPlan__prog = package_plan._PkgPlan__progtrack
                _PkgPlan__prog.download_start_pkg(package_plan.get_xfername())

                for src, dest in itertools.chain(*package_plan.actions):
                        if dest:
                                if dest.needsdata(src):
                                        flist.add_action(dest)

                flist.flush()
                package_plan._PkgPlan__progtrack.download_end_pkg()

        def __rebuild_index(self):
                '''Code duplication from pkg(1):
                       Forcibly rebuild the search indexes. Will remove existing indexes
                       and build new ones from scratch.'''
                quiet = False
                
                try:
                        self.ip.image.rebuild_search_index(self.ip.progtrack)
                except search_errors.InconsistentIndexException, iie:
                        return 1
                except search_errors.ProblematicPermissionsIndexException, ppie:
                        return 1

        def __installation_stage(self):
                '''Code duplication from imageplan.py def execute(self)'''
                self.gui_thread.run()
                text = self.parent._("Installing Packages...")
                gobject.idle_add(self.w_installingdialog_label.set_text, text)
                gobject.idle_add(self.w_installing_dialog.show)
                self.ip.state = imageplan.PREEXECUTED_OK

                if self.ip.nothingtodo():
                        self.ip.image.history.operation_result = \
                            history.RESULT_NOTHING_TO_DO
                        self.ip.state = imageplan.EXECUTED_OK
                        self.ip.progtrack.actions_done()
                        return

                # execute removals
                self.ip.progtrack.actions_set_goal("Removal Phase", len(self.ip.removal_actions))
                for p, src, dest in self.ip.removal_actions:                        
                        p.execute_removal(src, dest)
                        self.ip.progtrack.actions_add_progress()

                # execute installs
                self.ip.progtrack.actions_set_goal("Install Phase", len(self.ip.install_actions))
                for p, src, dest in self.ip.install_actions:
                        p.execute_install(src, dest)
                        self.ip.progtrack.actions_add_progress()

                # execute updates
                self.ip.progtrack.actions_set_goal("Update Phase", len(self.ip.update_actions))

                for p, src, dest in self.ip.update_actions:
                        p.execute_update(src, dest)
                        self.ip.progtrack.actions_add_progress()

                # handle any postexecute operations

                for p in self.ip.pkg_plans:
                        p.postexecute()

                self.ip.state = imageplan.EXECUTED_OK

                # reduce memory consumption
                del self.ip.removal_actions
                del self.ip.update_actions
                del self.ip.install_actions

                del self.ip.target_rem_fmris
                del self.ip.target_fmris
                # XXX This is accessing private member, and this fix should go
                # Once we will remove code duplication.
                del self.ip._ImagePlan__directories
                
                # Perform the incremental update to the search indexes
                # for all changed packages
                plan_info = []
                for p in self.ip.pkg_plans:
                        d_fmri = p.destination_fmri
                        d_manifest_path = None
                        if d_fmri:
                                d_manifest_path = \
                                    self.ip.image.get_manifest_path(d_fmri)
                        o_fmri = p.origin_fmri
                        o_manifest_path = None
                        o_filter_file = None
                        if o_fmri:
                                o_manifest_path = \
                                    self.ip.image.get_manifest_path(o_fmri)
                        plan_info.append((d_fmri, d_manifest_path, o_fmri,
                                          o_manifest_path))
                self.update_list = self.ip.pkg_plans[:]
                del self.ip.pkg_plans

                self.ip.progtrack.actions_set_goal("Index Phase", len(plan_info))

                try:
                        self.ip.image.update_index_dir()
                        ind = indexer.Indexer(self.ip.image.index_dir,
                            CLIENT_DEFAULT_MEM_USE_KB, progtrack=self.ip.progtrack)
                        ind.client_update_index((self.ip.filters, plan_info))
                except (KeyboardInterrupt,
                    search_errors.ProblematicPermissionsIndexException):
                        # ProblematicPermissionsIndexException is included here
                        # as there's little chance that trying again will fix
                        # this problem.
                        self.ip.image.history.operation_result = \
                            history.RESULT_FAILED_STORAGE
                        raise
                except Exception, e:
                        del(ind)
                        # XXX Once we have a framework for emitting a message
                        # to the user in this spot in the code, we should tell
                        # them something has gone wrong so that we continue to
                        # get feedback to allow us to debug the code.
                        self.ip.image.rebuild_search_index(self.ip.progtrack)
                        self.ip.image.history.operation_result = \
                            history.RESULT_FAILED_UNKNOWN

                self.ip.image.history.operation_result = \
                    history.RESULT_SUCCEEDED
                self.ip.progtrack.actions_done()

        def actions_done(self):
                if self.parent != None:
                        if not self.ips_update and not self.image_update:
                                gobject.idle_add(self.__update_package_list)
                gobject.idle_add(self.w_installing_dialog.hide)

                if self.ips_update:
                        gobject.idle_add(self.parent.shutdown_after_ips_update)
                elif self.image_update:
                        gobject.idle_add(self.parent.shutdown_after_image_update)

        def __update_package_list(self):
                for pkg in self.update_list:
                        pkg_name = pkg.get_xfername()
                        self.__update_install_list(pkg_name)
                del self.update_list
                self.parent.update_package_list()
                        
        def __update_install_list(self, pkg_name):
                for row in self.install_list:
                        if row[enumerations.NAME_COLUMN] == pkg_name:
                                row[enumerations.MARK_COLUMN] = True
                                return

        def download_file_path(self, file_path):
                '''Called by GUI's filelist.py through the progress, which is passed 
                to the filelist.'''
                # XXX this function should be removed and also pkg.gui.filelist should 
                # not call it, since we don't want to show single file progress
                gobject.idle_add(self.__add_file_to_downloadtext, file_path)

        def __add_file_to_downloadtext(self, file_path):
                '''Function which adds another line text in the "more details" download 
                dialog'''
                buf = self.w_download_textview.get_buffer()
                textiter = buf.get_end_iter()
                buf.insert(textiter, self.parent._("Downloading: ") + file_path + "\n")

        def __add_info_to_installtext(self, text):
                '''Function which adds another line text in the "more details" install 
                dialog'''
                buf = self.w_installing_textview.get_buffer()
                textiter = buf.get_end_iter()
                buf.insert(textiter, text)

        def cat_output_start(self): 
                return

        def cat_output_done(self): 
                return

        def eval_output_start(self):
                '''Called by progress tracker when the evaluation of the packages just 
                started.'''
                return

        def eval_output_progress(self):
                '''Called by progress tracker each time some package was evaluated. The
                call is being done by calling progress tracker evaluate_progress() 
                function'''
                return

        def eval_output_done(self):
                gobject.idle_add(self.__eval_output_done)

        def __eval_output_done(self):
                '''Called by progress tracker after the evaluation of the packages is 
                finished. Gets information like how many packages will be 
                updated/installed and maximum amount of data which will be downloaded. 
                Later this information is being adjusted, while downloading'''
                if self.gui_thread.is_cancelled():
                        self.progress_stop_timer_thread = True
                        self.w_createplan_dialog.hide()
                        return
                updated_installed = \
                    [
                        ["Packages To Be Installed:"],
                        ["Packages To Be Updated:"]
                    ]
                treestore = gtk.TreeStore(str)
                install_iter = None 
                updated_iter = None
                install_count = 0
                updated_count = 0
                total_download_count = 0
                total_files_count = 0
                npkgs = 0
                for package_plan in self.ip.pkg_plans:
                        npkgs += 1
                        if package_plan.origin_fmri and package_plan.destination_fmri:
                                if not updated_iter:
                                        updated_iter = treestore.append(None, \
                                            updated_installed[1])
                                d_fmri = package_plan.destination_fmri
                                dt = self.get_datetime(d_fmri.version)
                                dt_str = (":%02d%02d") % (dt.month, dt.day)
                                pkg_version = d_fmri.version.get_short_version() + dt_str
                                pkg = d_fmri.get_name() + "@" + pkg_version
                                updated_count = updated_count + 1
                                treestore.append(updated_iter, [pkg])
                        elif package_plan.destination_fmri:
                                if not install_iter:
                                        install_iter = treestore.append(None, \
                                            updated_installed[0])
                                d_fmri = package_plan.destination_fmri
                                dt = self.get_datetime(d_fmri.version)
                                dt_str = (":%02d%02d") % (dt.month, dt.day)
                                pkg_version = d_fmri.version.get_short_version() + dt_str
                                pkg = d_fmri.get_name() + "@" + pkg_version
                                install_count = install_count + 1
                                treestore.append(install_iter, [pkg])
                        xferfiles, xfersize = package_plan.get_xferstats()
                        total_download_count = total_download_count + xfersize
                        total_files_count = total_files_count + xferfiles
                self.ip.progtrack.download_set_goal(npkgs, total_files_count, \
                    total_download_count)
                self.w_review_treeview.set_model(treestore)
                self.w_review_treeview.expand_all()
                updated_str = self.parent._("%d packages will be updated\n")
                if updated_count == 1:
                        updated_str = self.parent._("%d package will be updated\n")
                install_str = self.parent._("%d packages will be installed\n\n")
                if install_count == 1:
                        install_str = self.parent._("%d package will be installed\n\n")
                self.w_summary_label.set_text((updated_str + install_str + \
                    self.parent._("%d MB will be downloaded"))% \
                    (updated_count, install_count, (total_download_count/1024/1024)))
                self.progress_stop_timer_thread = True
                self.w_createplan_dialog.hide()
                self.w_installupdate_dialog.show()

        def ver_output(self): 
                return

        def ver_output_error(self, actname, errors): 
                return

        def dl_output(self):
                gobject.idle_add(self.__update_download_progress, self.dl_cur_nbytes, \
                    self.dl_goal_nbytes)
                return

        def dl_output_done(self):
                return

        def act_output(self):
                gobject.idle_add(self.__update_install_progress, \
                    self.act_cur_nactions, self.act_goal_nactions)
                return

        def act_output_done(self):
                return

        def ind_output(self):
                self.progress_stop_timer_thread = False
                gobject.idle_add(self.__indexing_progress)
                return

        def __indexing_progress(self):
                if not self.progress_stop_timer_running:
                        self.w_installingdialog_label.set_text(\
                            self.parent._("Creating packages index..."))
                        Thread(target = self.__update_install_pulse).start()
                        
        def ind_output_done(self):
                self.progress_stop_timer_thread = True
                return

        @staticmethod
        def get_datetime(version):
                '''Support function for change in the IPS API: get_timestamp() was
                replaced by get_datetime()'''
                dt = None
                try:
                        dt = version.get_datetime()
                except AttributeError:
                        dt = version.get_timestamp()
                return dt

