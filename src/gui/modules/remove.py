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

import sys
import os
import itertools
import errno
import gettext
from threading import Thread
try:
        import pygtk
        pygtk.require("2.0")
except:
        sys.exit(1)
try:
        import gtk
        import gtk.glade
        import gobject
except:
        sys.exit(1)

import pkg.fmri as fmri
import pkg.client.bootenv as bootenv
import pkg.client.imageplan as imageplan
import pkg.client.pkgplan as pkgplan
import pkg.client.progress as progress
import pkg.client.retrieve as retrieve
import pkg.gui.enumerations as enumerations
import pkg.gui.filelist as filelist
import pkg.gui.thread as guithread

class Remove(progress.ProgressTracker):
        def __init__(self, remove_list, parent):
                gettext.install("pkg","/usr/lib/locale") # Workaround as BE is using msg(_("message")) which bypasses the self._ mechanism the GUI is using
                progress.ProgressTracker.__init__(self)
                self.gui_thread = guithread.ThreadRun()
                self.remove_list = remove_list
                self.parent = parent
                self.gladefile = parent.gladefile
                #This is hack since we should show proper dialog.
                self.error = None
                self.create_plan_dialog_gui()
                self.create_remove_gui()
                self.create_removing_gui()
                list_of_packages = self.prepare_list_of_packages()
                self.thread = Thread(target = self.plan_the_removeimage, args = (list_of_packages, ))
                self.thread.start()
                self.createplandialog.run()
                return

        def create_plan_dialog_gui(self):
                gladefile = self.gladefile
                wTreePlan = gtk.glade.XML(gladefile, "createplandialog2") 
                self.createplandialog = wTreePlan.get_widget("createplandialog2")
                self.createplantextview = wTreePlan.get_widget("createplantextview2")
                self.createplanprogress = wTreePlan.get_widget("createplanprogress2")
                self.createplantextbuffer = self.createplantextview.get_buffer()
                self.createplanprogress.set_pulse_step(0.1)
                try:
                        dic = \
                            {
                                "on_cancelcreateplan2_clicked":self.on_cancelcreateplan_clicked,
                            }
                        wTreePlan.signal_autoconnect(dic)
                except AttributeError, error:
                        print self.parent._('GUI will not respond to any event! %s.\
                            Check create_plan_dialog_gui()')\
                            % error
                return

        def create_remove_gui(self):
                gladefile = self.gladefile
                wTree = gtk.glade.XML(gladefile, "removedialog") 
                self.removedialog = wTree.get_widget("removedialog")
                self.summary_label = wTree.get_widget("removelabel")
                self.treeview = wTree.get_widget("treeview3")
                self.remove_column = gtk.TreeViewColumn('Removed')
                self.next_button = wTree.get_widget("next_remove")
                self.treeview.append_column(self.remove_column)
                self.cell = gtk.CellRendererText()
                self.remove_column.pack_start(self.cell, True)
                self.remove_column.add_attribute(self.cell, 'text', 0)
                self.treeview.expand_all()
                try:
                        dic = \
                            {
                                "on_cancel_remove_clicked":self.on_cancel_button_clicked,
                                "on_next_remove_clicked":self.on_next_button_clicked,
                            }
                        wTree.signal_autoconnect(dic)
                except AttributeError, error:
                        print self.parent._('GUI will not respond to any event! %s.Check create_remove_gui()')\
                            % error
                return

        def update_createplan_progress(self, action):
                textiter = self.createplantextbuffer.get_end_iter()
                self.createplantextbuffer.insert(textiter, action)
                self.createplanprogress.pulse()

        def create_removing_gui(self):
                gladefile = self.gladefile
                wTree = gtk.glade.XML(gladefile, "removingdialog") 
                self.removingdialog = wTree.get_widget("removingdialog")
                self.removingtextview = wTree.get_widget("removingtextview")
                self.removingprogress = wTree.get_widget("removingprogress")
                self.removingtextbuffer = self.removingtextview.get_buffer()
                return

        def on_cancelcreateplan_clicked(self, widget):
                self.gui_thread.cancel()
                self.createplandialog.destroy()

        def on_cancel_button_clicked(self, widget):
                self.gui_thread.cancel()
                self.removedialog.destroy()

        def prepare_list_of_packages(self):
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


        def plan_the_removeimage(self, list_of_packages):
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
                                gobject.idle_add(self.update_createplan_progress, self.parent._("Evaluating: %s\n") % f.get_fmri())
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


        def eval_output_start(self):
                return

        def eval_output_done(self):
                self.createplandialog.hide()
                if self.gui_thread.is_cancelled(): #If the evaluation was cancelled, return
                        return
                self.removedialog.show()
                packaged_removed = \
                    [
                        ["Packages To Be Removed:"],
                    ]
                if self.ip.state != imageplan.EVALUATED_OK:
                        packaged_removed = \
                            [
                                ["Cannot remove, due to the following dependencies:"],
                            ]
                self.treestore = gtk.TreeStore(str)
                remove_iter = None 
                remove_count = 0
                self.total_remove_count = 0
                self.total_files_count = 0
                if self.ip.state == imageplan.EVALUATED_OK:
                        self.next_button.set_sensitive(True)
                        for package_plan in self.ip.pkg_plans:
                                if package_plan.origin_fmri and not package_plan.destination_fmri:
                                        if not remove_iter:
                                                remove_iter = self.treestore.append(None, packaged_removed[0])
                                        pkg_version = package_plan.origin_fmri.version.get_short_version()# + dt_str
                                        pkg = package_plan.origin_fmri.get_name() + "@" + pkg_version
                                        remove_count = remove_count + 1
                                        self.treestore.append(remove_iter, [pkg])
                else:
                        self.next_button.set_sensitive(False)
                        if self.error:
                                for package in self.error:
                                        if not remove_iter:
                                                remove_iter = self.treestore.append(None,packaged_removed[0])
                                        self.treestore.append(remove_iter, [package])

                self.treeview.set_model(self.treestore)
                self.treeview.expand_all()
                remove_str = self.parent._("%d packages will be removed\n\n")
                if remove_count == 1:
                        remove_str = self.parent._("%d package will be removed\n\n")
                self.summary_label.set_text(remove_str % remove_count)
                return True

        def update_remove_progress(self, current, total):
                progress = float(current)/total
                self.removingprogress.set_fraction(progress)

        def on_next_button_clicked(self, widget):
                self.remove_thread = Thread(target = self.remove_stage, args = ())
                self.remove_thread.start()

        def remove_stage(self):
                self.removedialog.hide()
                self.removingdialog.show()
                self.ip.preexecute()
                try:
                        be = bootenv.BootEnv(self.ip.image.get_root())
                except RuntimeError:
                        be = bootenv.BootEnvNull(self.ip.image.get_root())
                try:
                        self.ip.execute()
                except RuntimeError, e:
                        be.restore_install_uninstall()
                except Exception, e:
                        be.restore_install_uninstall()
                        raise

                if self.ip.state == imageplan.EXECUTED_OK:
                        be.activate_install_uninstall()
                else:
                        be.restore_install_uninstall()

        def act_output(self):
                gobject.idle_add(self.update_remove_progress, self.ip.progtrack.act_cur_nactions, self.ip.progtrack.act_goal_nactions)
                return

        def act_output_done(self):
                if self.parent != None:
                        self.parent.update_package_list()
                self.removingdialog.hide()
                return

        def cat_output_start(self): 
                return

        def cat_output_done(self): 
                return

        def ver_output(self): 
                return

        def ver_output_error(self, actname, errors): 
                return

        def dl_output(self): 
                return

        def dl_output_done(self): 
                return

        def eval_output_progress(self): 
                return

        def ind_output(self):
                return

        def ind_output_done(self):
                return
