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

import gettext # XXX Temporary workaround
import sys
import time
import datetime
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
import pkg.client.progress as progress
import pkg.misc
import pkg.client.api as api
import pkg.client.api_errors as api_errors
from pkg.misc import TransferTimedOutException, TransportException
import pkg.gui.enumerations as enumerations

class InstallUpdate(progress.ProgressTracker):
        def __init__(self, install_list, parent, api_o, \
            ips_update = False, action = -1):
                if action == -1:
                        return
                # XXX Workaround as BE is using msg(_("message")) 
                # which bypasses the self._ mechanism the GUI is using
                gettext.install("pkg","/usr/share/locale")
                progress.ProgressTracker.__init__(self)
                api_o.progresstracker = self
                self.update_list = []
                self.parent = parent
                self.ips_update = ips_update
                self.ip = None
                self.progress_stop_timer_thread = False
                self.progress_stop_timer_running = False
                self.prev_pkg = None
                self.action = action
                self.api_o = api_o
                w_tree_createplan = gtk.glade.XML(parent.gladefile, "createplandialog")
                w_tree_installupdate = gtk.glade.XML(parent.gladefile, "installupdate")
                w_tree_errordialog = gtk.glade.XML(parent.gladefile, "errordialog")
                w_tree_downloadingfiles = \
                    gtk.glade.XML(parent.gladefile, "downloadingfiles")
                w_tree_installingdialog = \
                    gtk.glade.XML(parent.gladefile, "installingdialog") 
                w_tree_networkdown = gtk.glade.XML(parent.gladefile, "networkdown")
                self.w_createplan_dialog = \
                    w_tree_createplan.get_widget("createplandialog")
                self.w_error_dialog = \
                    w_tree_errordialog.get_widget("errordialog")    
                self.w_errortext_label = \
                    w_tree_errordialog.get_widget("errortext")
                self.w_errortext_textview = \
                    w_tree_errordialog.get_widget("errortextdetails")
                self.w_next_button = \
                    w_tree_installupdate.get_widget("next")
                remove_warning_triange = \
                    w_tree_installupdate.get_widget("warningtriangle")
                self.w_cancel_button = \
                    w_tree_installupdate.get_widget("cancel")
                self.w_createplan_progressbar = \
                    w_tree_createplan.get_widget("createplanprogress") 
                self.w_createplan_textview = \
                    w_tree_createplan.get_widget("createplantextview")
                self.w_createplan_label = \
                    w_tree_createplan.get_widget("packagedependencies")
                self.w_createplancancel_button = \
                    w_tree_createplan.get_widget("cancelcreateplan")
                self.w_canceldownload_button = \
                    w_tree_downloadingfiles.get_widget("canceldownload")
                self.w_download_label = \
                    w_tree_downloadingfiles.get_widget("packagedependencies2")
                self.w_installupdate_dialog = \
                    w_tree_installupdate.get_widget("installupdate")
                self.w_summary_label = \
                    w_tree_installupdate.get_widget("packagenamelabel3")
                self.w_review_treeview = w_tree_installupdate.get_widget("treeview1")
                self.w_information_label = w_tree_installupdate.get_widget("label5")
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
                remove_warning_triange.hide()

                if self.action == enumerations.REMOVE:
                        self.w_installupdate_dialog.set_title(self.parent._(\
                            "Remove Confirmation"))
                        self.w_information_label.set_text(\
                            self.parent._("This action affects other packages.\n" \
                            "Review the packages to be removed.\n" \
                            "Click Next to continue."))
                        self.w_installing_dialog.set_title(\
                            self.parent._("Removing Packages"))
                        self.w_createplan_dialog.set_title(\
                            self.parent._("Remove Check"))
                        self.w_installingdialog_label.set_text(\
                            self.parent._("Removing Packages..."))
                        remove_warning_triange.show()

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
                        dic_error = \
                            {
                                "on_error_close_clicked": \
                                    self.__on_error_close_clicked,
                            }
                        w_tree_createplan.signal_autoconnect(dic_createplan)
                        w_tree_installupdate.signal_autoconnect(dic_installupdate)
                        w_tree_downloadingfiles.signal_autoconnect(dic_downloadingfiles)
                        w_tree_networkdown.signal_autoconnect(dic_networkdown)
                        w_tree_errordialog.signal_autoconnect(dic_error)
                except AttributeError, error:
                        print self.parent._('GUI will not respond to any event! %s. \
                            Check installupdate.py signals') \
                            % error
                # XXX Hidden until progress will give information about fmri 
                self.w_installingdialog_expander.hide()
                pulse_t = Thread(target = self.__progressdialog_progress_pulse)
                thread = Thread(target = self.__plan_the_install_updateimage_ex, \
                    args = (install_list, ))
                pulse_t.start()
                thread.start()
                self.w_createplan_label.set_text(\
                    self.parent._("Checking package dependencies..."))
                self.w_createplancancel_button.set_sensitive(True)           
                self.w_createplan_dialog.show()

        def __on_cancelcreateplan_clicked(self, widget):
                '''Handler for signal send by cancel button, which user might press during
                evaluation stage - while the dialog is creating plan'''
                if self.api_o.can_be_canceled():
                        Thread(target = self.api_o.cancel, args = ()).start()
                        self.w_createplan_label.set_text(\
                            self.parent._("Canceling..."))
                        self.w_createplancancel_button.set_sensitive(False)

        def __on_cancel_button_clicked(self, widget):
                '''Handler for signal send by cancel button, which is available for the 
                user after evaluation stage on the dialog showing what will be installed
                or updated'''
                self.api_o.reset()
                self.w_installupdate_dialog.destroy()

        def __on_next_button_clicked(self, widget):
                '''Handler for signal send by next button, which is available for the 
                user after evaluation stage on the dialog showing what will be installed
                or updated'''
                self.w_installupdate_dialog.hide()
                download_thread = Thread(target = self.__prepare_stage_ex, \
                    args = (self.api_o, ))
                download_thread.start()

        def __on_cancel_download_clicked(self, widget):
                '''Handler for signal send by cancel button, which user might press during
                download stage.'''
                if self.api_o.can_be_canceled():
                        Thread(target = self.api_o.cancel, args = ()).start()
                        self.w_download_label.set_text(\
                            self.parent._("Canceling..."))
                        self.w_canceldownload_button.set_sensitive(False)

        def __on_networkdown_close_clicked(self, widget):
                '''Handler for signal send by close button on the dialog showing that
                there was some problem with the network connection.'''
                self.w_networkdown_dialog.destroy()

        def __on_error_close_clicked(self, widget):
                self.w_error_dialog.destroy()

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
                size_a_str = ""
                size_b_str = ""
                if cur_bytes > 0:
                        size_a_str = pkg.misc.bytes_to_str(cur_bytes)
                if total_bytes > 0:
                        size_b_str = pkg.misc.bytes_to_str(total_bytes)
                c = "Downloaded: " + size_a_str + " / " + size_b_str
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

        def __plan_the_install_updateimage_ex(self, list_of_packages):
                try:
                        self.__plan_the_install_updateimage(list_of_packages)
                except Exception:
                        self.progress_stop_timer_thread = True
                        gobject.idle_add(self.w_createplan_dialog.hide)
                        msg = self.parent._("An unknown error occured while " \
                            "preparing the\nlist of packages\n\nPlease let the " \
                            "developers know about this problem by filing\n" \
                            "a bug at http://defect.opensolaris.org")
                        msg += self.parent._("\n\nException value: ") + "\n" + str(sys.exc_value)
                        gobject.idle_add(self.parent.error_occured, msg)
                        sys.exc_clear()
                        return

        def __plan_the_install_updateimage(self, list_of_packages):
                '''Function which plans the image'''
                gobject.idle_add(self.__update_createplan_progress, \
                    self.parent._("Evaluation started.\n" \
                        "Gathering packages information, please wait...\n"))
                stuff_to_do = False
                if self.action == enumerations.INSTALL_UPDATE:
                        try:
                                stuff_to_do, cre = self.api_o.plan_install( \
                                    list_of_packages, filters = [])
                                if cre and not cre.succeeded:
                                        self.progress_stop_timer_thread = True
                                        gobject.idle_add(self.w_createplan_dialog.hide)
                                        msg = self.parent._("Unexpected failure with" \
                                            "\ncatalog refresh during install" \
                                            " while \ndetermining what to update.")
                                        gobject.idle_add(self.parent.error_occured, msg)
                                        return
                        except api_errors.InvalidCertException:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                msg = self.parent._("Invalid repository certificate." \
                                    "\nYou can not install packages from the" \
                                    "\nrepopsitory, which doesn't have" \
                                    "\nappropriate certificate.")
                                gobject.idle_add(self.parent.error_occured, msg)
                                return
                        except api_errors.PlanCreationException, e:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                err_msg = self.parent._("Install/Update failure" \
                                   " in plan creation.")
                                err_text = str(e)
                                gobject.idle_add(self.__error_with_details, \
                                    err_msg, err_text)
                                return
                        except api_errors.InventoryException:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                msg = self.parent._("Install failed.\n" \
                                   "The inventory is not correct.")
                                gobject.idle_add(self.parent.error_occured, msg)
                                return
                        except api_errors.CanceledException:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                return
                        except api_errors.CatalogRefreshException:
                                # network problem
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                msg = self.parent._("Please check the network " \
                                    "connection.\nIs the repository accessible?")
                                gobject.idle_add(self.parent.error_occured, msg)
                                return

                elif self.action == enumerations.REMOVE:
                        try:
                                plan_uninstall = self.api_o.plan_uninstall
                                stuff_to_do = \
                                    plan_uninstall(list_of_packages, False, False)
                        except api_errors.PlanCreationException, e:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                err_msg = self.parent._("Remove failure in plan" \
                                   " creation.")
                                err_text = str(e)
                                gobject.idle_add(self.__error_with_details, \
                                    err_msg, err_text)
                                return
                        except api_errors.CanceledException:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                return
                        except api_errors.NonLeafPackageException, nlpe:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.__afterplan_nonleaf_dialog, nlpe)
                                return

                elif self.action == enumerations.IMAGE_UPDATE:  
                        try:
                                # we are passing force, since we already checked if the
                                # SUNWipkg and SUNWipkg-gui are up to date.
                                stuff_to_do, opensolaris_image, cre = \
                                    self.api_o.plan_update_all(sys.argv[0], \
                                    refresh_catalogs = False, \
                                    noexecute = False, force = True)
                                if cre and not cre.succeeded:
                                        self.progress_stop_timer_thread = True
                                        gobject.idle_add(self.w_createplan_dialog.hide)
                                        msg = self.parent._("Unexpected failure with" \
                                            "\ncatalog refresh during image-update" \
                                            " while \ndetermining what to update.")
                                        gobject.idle_add(self.parent.error_occured, msg)
                                        return
                        except api_errors.CatalogRefreshException:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                msg = self.parent._("Update All failed during " \
                                    "catalog refresh\n")
                                gobject.idle_add(self.parent.error_occured, msg)
                                return
                        except api_errors.IpkgOutOfDateException:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                msg = self.parent._("pkg(5) appears to be out of " \
                                    "date and should be\n updated before running " \
                                    "Update All.\nPlease update SUNWipkg package")
                                gobject.idle_add(self.parent.error_occured, msg)
                                return
                        except api_errors.PlanCreationException, e:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                err_msg = self.parent._("Update All failure in plan" \
                                   " creation.")
                                err_text = str(e)
                                gobject.idle_add(self.__error_with_details, \
                                    err_msg, err_text)
                                return
                        except api_errors.CanceledException:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                return
                        except api_errors.NetworkUnavailableException:
                                self.progress_stop_timer_thread = True
                                gobject.idle_add(self.w_createplan_dialog.hide)
                                msg = self.parent._("Please check the network " \
                                    "connection.\nIs the repository accessible?")
                                gobject.idle_add(self.parent.error_occured, msg)
                                return
                if stuff_to_do:
                        gobject.idle_add(self.__afterplan_confirmation_dialog, self.api_o)
                elif self.action == enumerations.INSTALL_UPDATE:
                        self.progress_stop_timer_thread = True
                        gobject.idle_add(self.w_createplan_dialog.hide)
                        msg = self.parent._("Selected packages for update can\n" \
                            "only be updated using Update All.")
                        title = self.parent._("Unable to update")
                        gobject.idle_add(self.parent.error_occured, msg, title)
                else:
                        self.progress_stop_timer_thread = True
                        gobject.idle_add(self.w_createplan_dialog.hide)
                        msg = self.parent._("The action for selected packages " \
                            "could not be completed.")
                        title = self.parent._("Unable to perform action")
                        gobject.idle_add(self.parent.error_occured, msg, title)
                        

        def __prepare_stage_ex(self, api_o):
                try:
                        self.__prepare_stage(api_o)
                except Exception:
                        gobject.idle_add(self.w_downloadingfiles_dialog.hide)
                        msg = self.parent._("An unknown error occured while " \
                            "downloading the files\n\nPlease let the developers know " \
                            "about this problem by filing\na bug " \
                            "at http://defect.opensolaris.org")
                        msg += self.parent._("\n\nException value: ") + "\n" + str(sys.exc_value)
                        gobject.idle_add(self.parent.error_occured, msg)
                        sys.exc_clear()

        def __prepare_stage(self, api_o):
                gobject.idle_add(self.w_downloadingfiles_dialog.show)
                text = self.parent._("Preparing to download packages, please wait...")
                gobject.idle_add(self.__add_info_to_downloadtext, text)
                try:
                        api_o.prepare()
                except (api_errors.ProblematicPermissionsIndexException, \
                    api_errors.PlanMissingException):
                        gobject.idle_add(self.w_downloadingfiles_dialog.hide)
                        msg = self.parent._("An error occured while " \
                            "downloading the files\nPlease check your permissions and" \
                            "\nnetwork connection.")
                        gobject.idle_add(self.parent.error_occured, msg)
                        return
                except api_errors.CanceledException:
                        gobject.idle_add(self.w_downloadingfiles_dialog.hide)
                        return
                except (TransferTimedOutException, TransportException):
                        gobject.idle_add(self.w_downloadingfiles_dialog.hide)
                        gobject.idle_add(self.w_networkdown_dialog.show)
                        return
                except URLError:
                        gobject.idle_add(self.w_downloadingfiles_dialog.hide)
                        gobject.idle_add(self.w_networkdown_dialog.show)
                        return
                self.__execute_stage_ex(api_o)
                
        def __execute_stage_ex(self, api_o):
                try:
                        self.__execute_stage(api_o)
                except Exception:
                        gobject.idle_add(self.w_installing_dialog.hide)
                        msg = self.parent._("An unknown error occured while " \
                            "installing\nupdating or removing packages" \
                            "\n\nPlease let the developers know about this problem " \
                            "by filing\na bug at http://defect.opensolaris.org")
                        msg += self.parent._("\n\nException value: ") + "\n" + str(sys.exc_value)
                        gobject.idle_add(self.parent.error_occured, msg)
                        sys.exc_clear()
                        return

        def __execute_stage(self, api_o):
                text = self.parent._("Installing Packages...")
                gobject.idle_add(self.w_downloadingfiles_dialog.hide)
                gobject.idle_add(self.w_installingdialog_label.set_text, text)
                gobject.idle_add(self.w_installing_dialog.show)
                try:
                        api_o.execute_plan()
                except api_errors.CorruptedIndexException:
                        gobject.idle_add(self.w_installing_dialog.hide)
                        msg = self.parent._("There was an error during installation." \
                            "\nThe index is corrupted. You might wan't try to fix" \
                            "\nthis problem by running command:" \
                            "\npfexec pkg rebuild-index")
                        gobject.idle_add(self.parent.error_occured, msg)
                        return
                except api_errors.ProblematicPermissionsIndexException:
                        gobject.idle_add(self.w_installing_dialog.hide)
                        msg = self.parent._("An error occured while " \
                            "installing the files\nPlease check your permissions")
                        gobject.idle_add(self.parent.error_occured, msg)
                        return
                except api_errors.ImageplanStateException:
                        gobject.idle_add(self.w_installing_dialog.hide)
                        msg = self.parent._("There was an error during installation." \
                            "\nThe State of the image is incorrect and the operation" \
                            "\ncan't be finished.")
                        gobject.idle_add(self.parent.error_occured, msg)
                        return
                except api_errors.ImageUpdateOnLiveImageException:
                        gobject.idle_add(self.w_installing_dialog.hide)
                        msg = self.parent._("This is an Live Image. The install" \
                            "\noperation can't be performed.")
                        gobject.idle_add(self.parent.error_occured, msg)
                        return
                except api_errors.PlanMissingException:
                        gobject.idle_add(self.w_installing_dialog.hide)
                        msg = self.parent._("There was an error during installation." \
                            "\nThe Plan of the operation is missing and the operation" \
                            "\ncan't be finished.")
                        gobject.idle_add(self.parent.error_occured, msg)
                        return
                gobject.idle_add(self.__operations_done)

        def __operations_done(self):
                if self.parent != None:
                        if not self.ips_update and not self.action == \
                            enumerations.IMAGE_UPDATE:
                                self.__update_package_list()
                self.w_installing_dialog.hide()

                if self.ips_update:
                        self.parent.shutdown_after_ips_update()
                elif self.action == enumerations.IMAGE_UPDATE:
                        self.parent.shutdown_after_image_update()

        def __update_package_list(self):
                self.parent.update_package_list(self.update_list)

        def __add_info_to_downloadtext(self, text):
                '''Function which adds another line text in the "more details" download 
                dialog'''
                buf = self.w_download_textview.get_buffer()
                textiter = buf.get_end_iter()
                if text:
                        buf.insert(textiter, text + "\n")

        def __error_with_details(self, err_msg, err_text):
                self.w_errortext_label.set_text(err_msg)
                buf = self.w_errortext_textview.get_buffer()
                textiter = buf.get_end_iter()
                buf.insert(textiter, err_text)
                self.w_error_dialog.run()
                self.w_error_dialog.destroy()

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
                cur_eval_fmri = self.eval_cur_fmri
                gobject.idle_add(self.__update_createplan_progress, \
                    self.parent._("Evaluating: %s\n") % cur_eval_fmri)

        def eval_output_done(self):
                ninst = self.eval_goal_install_npkgs
                nupdt = self.eval_goal_update_npkgs
                nremv = self.eval_goal_remove_npkgs
                nbytes = self.dl_goal_nbytes
                gobject.idle_add(self.__eval_output_done, \
                    ninst, nupdt, nremv, nbytes)

        def __eval_output_done(self, ninst, nupdt, nremv, nbytes):
                label_text = ""
                if nupdt > 0 and nupdt != 1:
                        label_text += \
                            self.parent._("%d packages will be updated\n") % nupdt
                elif nupdt == 1:
                        label_text += \
                            self.parent._("%d package will be updated\n") % nupdt
                if ninst > 0 and ninst != 1:
                        label_text += \
                            self.parent._("%d packages will be installed\n\n") % ninst
                elif ninst == 1:
                        label_text += \
                            self.parent._("%d package will be installed\n\n") % ninst
                if nremv > 0 and nremv != 1:
                        label_text += \
                            self.parent._("%d packages will be removed\n\n") % nremv
                elif nremv == 1:
                        label_text += \
                            self.parent._("%d package will be removed\n\n") % nremv
                if not nbytes:
                        nbytes = 0
                if nbytes > 0:
                        size_str = pkg.misc.bytes_to_str(nbytes)
                        label_text += self.parent._("%s will be downloaded") % size_str
                self.w_summary_label.set_text(label_text)

        def __afterplan_nonleaf_dialog(self, non_leaf_exception):
                self.w_installupdate_dialog.set_title(self.parent._(\
                    "Remove Confirmation"))
                self.w_information_label.set_text(\
                    self.parent._("This action couldn't be finished.\n" \
                    "Some of the selected packages depends on other.\n" \
                    "Please review the dependencies."))
                self.w_next_button.hide()
                self.w_cancel_button.set_label(self.parent._("Close"))
                pkg_blocker = non_leaf_exception[0]
                treestore = gtk.TreeStore(str)
                pkg_iter = treestore.append(None, [pkg_blocker])
                for pkg_a in non_leaf_exception[1]:
                        treestore.append(pkg_iter, [pkg_a])
                self.w_review_treeview.set_model(treestore)
                self.w_review_treeview.expand_all()
                label_text = self.parent._("None of the packages will be removed")
                self.w_summary_label.set_text(label_text)
                self.progress_stop_timer_thread = True
                self.w_createplan_dialog.hide()
                self.w_installupdate_dialog.show()


        def __afterplan_confirmation_dialog(self, api_o):
                updated_installed = \
                    [
                        ["Packages To Be Installed:"],
                        ["Packages To Be Updated:"],
                        ["Packages To Be Removed:"]
                    ]
                treestore = gtk.TreeStore(str)
                install_iter = None 
                updated_iter = None
                remove_iter = None
                plan = api_o.describe().get_changes()
                for pkg_plan in plan:
                        origin_fmri = pkg_plan[0]
                        destination_fmri = pkg_plan[1]
                        if origin_fmri and destination_fmri:
                                if not updated_iter:
                                        updated_iter = treestore.append(None, \
                                            updated_installed[1])
                                pkg_a = self.__get_pkgstr_from_pkginfo(destination_fmri)
                                treestore.append(updated_iter, [pkg_a])
                        elif not origin_fmri and destination_fmri:
                                if not install_iter:
                                        install_iter = treestore.append(None, \
                                            updated_installed[0])
                                pkg_a = self.__get_pkgstr_from_pkginfo(destination_fmri)
                                treestore.append(install_iter, [pkg_a])
                        elif origin_fmri and not destination_fmri:
                                if not remove_iter:
                                        remove_iter = treestore.append(None, \
                                            updated_installed[2])
                                pkg_a = self.__get_pkgstr_from_pkginfo(origin_fmri)
                                treestore.append(remove_iter, [pkg_a])

                self.w_review_treeview.set_model(treestore)
                self.w_review_treeview.expand_all()
                self.progress_stop_timer_thread = True
                self.w_createplan_dialog.hide()
                self.w_installupdate_dialog.show()

        def __get_pkgstr_from_pkginfo(self, pkginfo):
                dt_str = self.get_datetime(pkginfo.packaging_date)
                s_ver = pkginfo.version
                s_bran = pkginfo.branch
                pkg_name = pkginfo.pkg_stem
                if not pkg_name in self.update_list:
                        self.update_list.append(pkg_name)
                l_ver = 0
                version_pref = ""
                while l_ver < len(s_ver) -1:
                        version_pref += "%d%s" % (s_ver[l_ver],".")
                        l_ver += 1
                version_pref += "%d%s" % (s_ver[l_ver],"-")
                l_ver = 0
                version_suf = ""
                while l_ver < len(s_bran) -1:
                        version_suf += "%d%s" % (s_bran[l_ver],".")
                        l_ver += 1
                version_suf += "%d" % s_bran[l_ver]
                pkg_version = version_pref + version_suf + dt_str
                return pkg_name + "@" + pkg_version  

        def ver_output(self): 
                return

        def ver_output_error(self, actname, errors): 
                return

        def dl_output(self):
                gobject.idle_add(self.__update_download_progress, \
                    self.dl_cur_nbytes, self.dl_goal_nbytes)
                if self.prev_pkg != self.dl_cur_pkg:
                        self.prev_pkg = self.dl_cur_pkg
                        text = self.parent._("Downloading: ") + self.dl_cur_pkg
                        gobject.idle_add(self.__add_info_to_downloadtext, text)
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
        def get_datetime(date_time):
                '''Support function for getting date from the API.'''
                date_tmp = time.strptime(date_time, "%a %b %d %H:%M:%S %Y")
                date_tmp2 = datetime.datetime(*date_tmp[0:5])
                return date_tmp2.strftime(":%m%d")
