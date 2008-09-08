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


import gettext
import sys
import time
from threading import Thread
try:
        import gobject
        import gtk
        import gtk.glade
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)
import pkg.client.bootenv as bootenv
import pkg.client.imageplan as imageplan
import pkg.search_errors as search_errors
import pkg.indexer as indexer
import pkg.client.progress as progress
import pkg.gui.enumerations as enumerations
import pkg.gui.thread as guithread

class Remove(progress.ProgressTracker):
        def __init__(self, remove_list, parent):
                # XXX Workaround as BE is using msg(_("message")) 
                # which bypasses the self._ mechanism the GUI is using
                gettext.install("pkg","/usr/lib/locale")
                progress.ProgressTracker.__init__(self)
                self.gui_thread = guithread.ThreadRun()
                self.remove_list = remove_list
                self.parent = parent
                #This is hack since we should show proper dialog.
                self.error = None
                self.ip = None
                self.progress_stop_timer_thread = False
                self.progress_stop_timer_running = False
                w_tree_createplan = gtk.glade.XML(parent.gladefile, "createplandialog2")
                w_tree_removedialog = gtk.glade.XML(parent.gladefile, "removedialog")
                w_tree_removingdialog = gtk.glade.XML(parent.gladefile, "removingdialog") 
                self.w_createplan_dialog = \
                    w_tree_createplan.get_widget("createplandialog2")
                self.w_createplan_textview = \
                    w_tree_createplan.get_widget("createplantextview2")
                self.w_createplan_progressbar = \
                    w_tree_createplan.get_widget("createplanprogress2")
                self.w_createplan_expander = \
                    w_tree_createplan.get_widget("expander7")      
                self.w_createplan_label = \
                    w_tree_createplan.get_widget("packagedependencies5")  
                self.w_createplancancel_button = \
                    w_tree_createplan.get_widget("cancelcreateplan2")                      
                self.w_remove_dialog = w_tree_removedialog.get_widget("removedialog")
                self.w_summary_label = w_tree_removedialog.get_widget("removelabel")
                self.w_review_treeview = w_tree_removedialog.get_widget("treeview3")
                self.w_next_button = w_tree_removedialog.get_widget("next_remove")
                self.w_removing_dialog = \
                    w_tree_removingdialog.get_widget("removingdialog")
                self.w_removing_progressbar = \
                    w_tree_removingdialog.get_widget("removingprogress")
                self.w_removingdialog_label = \
                    w_tree_removingdialog.get_widget("packagedependencies4")
                self.w_removingdialog_expander = \
                    w_tree_removingdialog.get_widget("expander6") 
                self.w_createplan_progressbar.set_pulse_step(0.1)
                remove_column = gtk.TreeViewColumn('Removed')
                self.w_review_treeview.append_column(remove_column)
                cell = gtk.CellRendererText()
                remove_column.pack_start(cell, True)
                remove_column.add_attribute(cell, 'text', 0)
                self.w_review_treeview.expand_all()
                try:
                        dic_createplan = \
                            {
                                "on_cancelcreateplan2_clicked": \
                                    self.__on_cancelcreateplan_clicked,
                            }
                        dic_removedialog = \
                            {
                                "on_cancel_remove_clicked": \
                                    self.__on_cancel_button_clicked,
                                "on_next_remove_clicked":self.__on_next_button_clicked,
                            }
                        w_tree_createplan.signal_autoconnect(dic_createplan)
                        w_tree_removedialog.signal_autoconnect(dic_removedialog)
                except AttributeError, error:
                        print self.parent._('GUI will not respond to any event! %s. \
                            Check remove.py signals') \
                            % error
                list_of_packages = self.__prepare_list_of_packages()
                # XXX Hidden until progress will give information about fmri
                self.w_createplan_expander.hide()
                self.w_removingdialog_expander.hide()
                pulse_t = Thread(target = self.__progressdialog_progress_pulse)
                thread = Thread(target = self.__plan_the_removeimage, \
                    args = (list_of_packages, ))
                pulse_t.start()
                thread.start()
                self.w_createplan_label.set_text(\
                    self.parent._("Checking package dependencies..."))
                self.w_createplancancel_button.set_sensitive(True)
                self.w_createplan_dialog.run()
                return

        def __on_cancelcreateplan_clicked(self, widget):         
                self.w_createplan_label.set_text(\
                    self.parent._("Canceling..."))
                self.w_createplancancel_button.set_sensitive(False)                    
                self.gui_thread.cancel()

        def __on_next_button_clicked(self, widget):
                self.w_remove_dialog.hide()
                self.w_removing_dialog.show()
                remove_thread = Thread(target = self.__remove_stage, args = ())
                remove_thread.start()

        def __on_cancel_button_clicked(self, widget):
                self.gui_thread.cancel()
                self.w_remove_dialog.hide()

        # XXX Not used until progress will give information about fmri
        def __update_createplan_progress(self, action):
                buf = self.w_createplan_textview.get_buffer()
                textiter = buf.get_end_iter()
                buf.insert(textiter, action)
                self.w_createplan_progressbar.pulse()

        def __update_remove_progress(self, current, total):
                prog = float(current)/total
                self.w_removing_progressbar.set_fraction(prog)

        def __prepare_list_of_packages(self):
                ''' This method return the dictionary of images for removal'''
                fmri_to_remove = {}
                for row in self.remove_list:
                        if row[enumerations.MARK_COLUMN]:
                                image = row[enumerations.IMAGE_OBJECT_COLUMN]
                                package = row[enumerations.INSTALLED_OBJECT_COLUMN]
                                im = fmri_to_remove.get(image)
                                if im:
                                        if package:
                                                im.append(package)
                                else:
                                        if package:
                                                fmri_to_remove[image] = [package, ]
                return fmri_to_remove

        def __plan_the_removeimage(self, list_of_packages):
                '''Function which plans the image'''
                self.gui_thread.run()
                filters = []
                for image in list_of_packages:
                        self.ip = imageplan.ImagePlan(image, self, filters = filters)
                        fmris = list_of_packages.get(image)
                        for fmri in fmris:
                                if self.gui_thread.is_cancelled():
                                        self.progress_stop_timer_thread = True
                                        gobject.idle_add(self.w_createplan_dialog.hide)
                                        return
                                self.ip.propose_fmri_removal(fmri)
                        try:
                                self.ip.evaluate()
                                if self.gui_thread.is_cancelled():
                                        self.progress_stop_timer_thread = True
                                        gobject.idle_add(self.w_createplan_dialog.hide)
                                        return
                                image.imageplan = self.ip
                        except imageplan.NonLeafPackageException, e:
                                        self.error = e[1]
                                        self.ip.progtrack.evaluate_done()
                                        return
                return

        def __remove_stage(self):
                self.ip.preexecute()
                try:
                        be = bootenv.BootEnv(self.ip.image.get_root())
                except RuntimeError:
                        be = bootenv.BootEnvNull(self.ip.image.get_root())
                try:
                        ret_code = 0
                        self.ip.execute()
                except RuntimeError:
                        be.restore_install_uninstall()
                except search_errors.InconsistentIndexException, e:
                        ret_code = 2
                except search_errors.PartialIndexingException, e:
                        ret_code = 2
                except search_errors.ProblematicPermissionsIndexException, e:
                        ret_code = 2
                except KeyError, e:
                        # XXX KeyError was seen while problem with
                        # creating index
                        ret_code = 2
                except Exception:
                        be.restore_install_uninstall()
                        gobject.idle_add(self.w_removing_dialog.hide)
                        raise

                if ret_code == 2:
                        return_code = 0
                        return_code = self.__rebuild_index()
                        if return_code == 1:
                                gobject.idle_add(self.w_removing_dialog.hide)
                                return

                if self.ip.state == imageplan.EXECUTED_OK:
                        be.activate_install_uninstall()
                else:
                        be.restore_install_uninstall()

                if self.parent != None:
                        gobject.idle_add(self.parent.update_package_list)

                gobject.idle_add(self.w_removing_dialog.hide)

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
                        
        def __progressdialog_progress_pulse(self):
                while not self.progress_stop_timer_thread:
                        gobject.idle_add(self.w_createplan_progressbar.pulse)
                        time.sleep(0.1)

        def __removedialog_progress_pulse(self):
                while not self.progress_stop_timer_thread:
                        self.progress_stop_timer_running = True
                        gobject.idle_add(self.w_removing_progressbar.pulse)
                        time.sleep(0.1)
                self.progress_stop_timer_running = False
                
        def cat_output_start(self): 
                return

        def cat_output_done(self): 
                return

        def eval_output_start(self):
                return

        def eval_output_progress(self): 
                return

        def eval_output_done(self):
            gobject.idle_add(self.__eval_output_done)
            
        def __eval_output_done(self):
                if self.gui_thread.is_cancelled():
                        self.progress_stop_timer_thread = True
                        self.w_createplan_dialog.hide()
                        return
                packaged_removed = \
                    [
                        ["Packages To Be Removed:"],
                    ]
                if self.ip.state != imageplan.EVALUATED_OK:
                        packaged_removed = \
                            [
                                ["Cannot remove, due to the following dependencies:"],
                            ]
                treestore = gtk.TreeStore(str)
                remove_iter = None 
                remove_count = 0
                if self.ip.state == imageplan.EVALUATED_OK:
                        self.w_next_button.set_sensitive(True)
                        for package_plan in self.ip.pkg_plans:
                                if package_plan.origin_fmri and not \
                                    package_plan.destination_fmri:
                                        if not remove_iter:
                                                remove_iter = \
                                                    treestore.append(None, \
                                                    packaged_removed[0])
                                        pkg_fmri = package_plan.origin_fmri
                                        pkg_version = \
                                            pkg_fmri.version.get_short_version()
                                        pkg = package_plan.origin_fmri.get_name() + \
                                            "@" + pkg_version
                                        remove_count = remove_count + 1
                                        treestore.append(remove_iter, [pkg])
                else:
                        self.w_next_button.set_sensitive(False)
                        if self.error:
                                for package in self.error:
                                        if not remove_iter:
                                                remove_iter = \
                                                    treestore.append(None, \
                                                    packaged_removed[0])
                                        treestore.append(remove_iter, [package])

                self.w_review_treeview.set_model(treestore)
                self.w_review_treeview.expand_all()
                remove_str = self.parent._("%d packages will be removed\n\n")
                if remove_count == 1:
                        remove_str = self.parent._("%d package will be removed\n\n")
                text = remove_str % remove_count
                self.w_summary_label.set_text(text)
                self.progress_stop_timer_thread = True
                self.w_createplan_dialog.hide()
                self.w_remove_dialog.show()

        def ver_output(self): 
                return

        def ver_output_error(self, actname, errors): 
                return

        def dl_output(self): 
                return

        def dl_output_done(self): 
                return

        def act_output(self):
                text = self.parent._("Removing Packages...")
                gobject.idle_add(self.w_removingdialog_label.set_text, text)
                gobject.idle_add(self.__update_remove_progress, \
                    self.ip.progtrack.act_cur_nactions, \
                    self.ip.progtrack.act_goal_nactions)
                return

        def act_output_done(self):
                return

        def ind_output(self):
                self.progress_stop_timer_thread = False
                gobject.idle_add(self.__indexing_progress)
                return

        def __indexing_progress(self):
                if not self.progress_stop_timer_running:
                        self.w_removingdialog_label.set_text(\
                            self.parent._("Creating packages index..."))
                        Thread(target = self.__removedialog_progress_pulse).start()

        def ind_output_done(self):
                self.progress_stop_timer_thread = True
                return
