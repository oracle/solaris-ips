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
                w_tree_createplan = gtk.glade.XML(parent.gladefile, "createplandialog2")
                w_tree_removedialog = gtk.glade.XML(parent.gladefile, "removedialog")
                w_tree_removingdialog = gtk.glade.XML(parent.gladefile, "removingdialog") 
                self.w_createplan_dialog = \
                    w_tree_createplan.get_widget("createplandialog2")
                self.w_createplan_textview = \
                    w_tree_createplan.get_widget("createplantextview2")
                self.w_createplan_progressbar = \
                    w_tree_createplan.get_widget("createplanprogress2")
                self.w_remove_dialog = w_tree_removedialog.get_widget("removedialog")
                self.w_summary_label = w_tree_removedialog.get_widget("removelabel")
                self.w_review_treeview = w_tree_removedialog.get_widget("treeview3")
                self.w_next_button = w_tree_removedialog.get_widget("next_remove")
                self.w_removing_dialog = \
                    w_tree_removingdialog.get_widget("removingdialog")
                self.w_removing_progressbar = \
                    w_tree_removingdialog.get_widget("removingprogress")
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
                thread = Thread(target = self.__plan_the_removeimage, \
                    args = (list_of_packages, ))
                thread.start()
                self.w_createplan_dialog.run()
                return

        def __on_cancelcreateplan_clicked(self, widget):
                self.gui_thread.cancel()
                self.w_createplan_dialog.destroy()

        def __on_next_button_clicked(self, widget):
                remove_thread = Thread(target = self.__remove_stage, args = ())
                remove_thread.start()

        def __on_cancel_button_clicked(self, widget):
                self.gui_thread.cancel()
                self.w_remove_dialog.destroy()

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
                                        return
                                self.ip.propose_fmri_removal(fmri)
                        self.ip.state = imageplan.UNEVALUATED
                        self.ip.progtrack.evaluate_start()
                        for f in self.ip.target_rem_fmris[:]:
                                gobject.idle_add(self.__update_createplan_progress, \
                                    self.parent._("Evaluating: %s\n") % f.get_fmri())
                                try:
                                        self.ip.evaluate_fmri_removal(f)
                                except imageplan.NonLeafPackageException, e:
                                        self.error = e[1]
                                        gobject.idle_add(self.ip.progtrack.evaluate_done)
                                        return   
                        self.ip.state = imageplan.EVALUATED_OK
                        image.imageplan = self.ip
                        gobject.idle_add(self.ip.progtrack.evaluate_done)
                return

        def __remove_stage(self):
                self.w_remove_dialog.hide()
                self.w_removing_dialog.show()
                self.ip.preexecute()
                try:
                        be = bootenv.BootEnv(self.ip.image.get_root())
                except RuntimeError:
                        be = bootenv.BootEnvNull(self.ip.image.get_root())
                try:
                        self.ip.execute()
                except RuntimeError:
                        be.restore_install_uninstall()
                except Exception:
                        be.restore_install_uninstall()
                        raise

                if self.ip.state == imageplan.EXECUTED_OK:
                        be.activate_install_uninstall()
                else:
                        be.restore_install_uninstall()

        def cat_output_start(self): 
                return

        def cat_output_done(self): 
                return

        def eval_output_start(self):
                return

        def eval_output_progress(self): 
                return

        def eval_output_done(self):
                self.w_createplan_dialog.hide()
                if self.gui_thread.is_cancelled():
                        return
                self.w_remove_dialog.show()
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
                self.w_summary_label.set_text(remove_str % remove_count)
                return True

        def ver_output(self): 
                return

        def ver_output_error(self, actname, errors): 
                return

        def dl_output(self): 
                return

        def dl_output_done(self): 
                return

        def act_output(self):
                gobject.idle_add(self.__update_remove_progress, \
                    self.ip.progtrack.act_cur_nactions, \
                    self.ip.progtrack.act_goal_nactions)
                return

        def act_output_done(self):
                if self.parent != None:
                        self.parent.update_package_list()
                self.w_removing_dialog.hide()
                return

        def ind_output(self):
                return

        def ind_output_done(self):
                return
