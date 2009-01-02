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


import getopt
import os
import sys
import time
import locale
import gettext
import pango
import errno
from threading import Thread
from threading import Timer

try:
        import gobject
        gobject.threads_init()        
        import gtk
        import gtk.glade
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)

import pkg.client.image as image
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress
import pkg.gui.beadmin as beadm
import pkg.misc as misc
from pkg.client import global_settings

# Put _() in the global namespace
import __builtin__
__builtin__._ = gettext.gettext

IMAGE_DIRECTORY_DEFAULT = "/"   # Image default directory
IMAGE_DIR_COMMAND = "svcprop -p update/image_dir svc:/application/pkg/update"
CLIENT_API_VERSION = 4          # API version
PKG_CLIENT_NAME = "updatemanager" # API client name
SELECTION_CHANGE_LIMIT = 0.5    # Time limit in seconds to cancel selection updates
IND_DELAY = 0.05                # Time delay for printing index progress
UPDATES_FETCH_DELAY = 200       # Time to wait before fetching updates, allows gtk main
                                # loop time to start and display main UI
#UM Row Model
(
UM_ID,
UM_INSTALL_MARK,
UM_STATUS,
UM_NAME,
UM_REBOOT,
UM_LATEST_VER,
UM_SIZE,
UM_FMRI,
) = range(8)

#UPDATE STEPS
(
UPDATE_EVAL,
UPDATE_DOWNLOAD,
UPDATE_INSTALL,
UPDATE_INDEX,
) = range(4)

#UPDATE TYPES
(
UPDATE_ACTIVE,
UPDATE_INACTIVE,
UPDATE_DONE,
) = range(3)

class GUIProgressTracker(progress.ProgressTracker):
        """ This progress tracker is designed for Gnome GUI's
        The parent must provide a number of callback methods to render progress
        in the GUI context. """

        def __init__(self, parent):
                progress.ProgressTracker.__init__(self)
                self.parent = parent
                
                self.act_started = False
                self.ind_started = False
                self.last_print_time = 0
                self.dl_started = False
                self.dl_cur_pkg = None

        def reset(self):
                progress.ProgressTracker.reset(self)
                self.act_started = False
                self.ind_started = False
                self.last_print_time = 0
                self.dl_started = False
                
        def cat_output_start(self):
                catstr = _("Fetching catalog: '%s' ..." % (self.cat_cur_catalog))
                gobject.idle_add(self.parent.output, "%s" % catstr)

        def cat_output_done(self):
                gobject.idle_add(self.parent.output_done, _("Fetching catalog"))

        def eval_output_start(self):
                s = _("Creating Plan ... ")
                gobject.idle_add(self.parent.output, "%s" % s)

        def eval_output_progress(self):
                if (time.time() - self.last_print_time) >= 0.10:
                        self.last_print_time = time.time()
                else:
                        return
                gobject.idle_add(self.parent.progress_pulse)

        def eval_output_done(self):
                gobject.idle_add(self.parent.output_done, _("Creating Plan"))
                self.last_print_time = 0

        def ver_output(self):
                if self.ver_cur_fmri != None:
                        if (time.time() - self.last_print_time) >= 0.10:
                                self.last_print_time = time.time()
                        else:
                                return
                        gobject.idle_add(self.parent.progress_pulse)
                        gobject.idle_add(self.parent.output, 
                            _("Verifying: %s ...") %
                            self.ver_cur_fmri.get_pkg_stem())
                else:
                        gobject.idle_add(self.parent.output, "")
                        self.last_print_time = 0

        def ver_output_error(self, actname, errors):
                gobject.idle_add(self.parent.output_done, _("Verifying"))

        def dl_output(self):
                gobject.idle_add(self.parent.dl_progress, 
                    self.dl_started, self.dl_cur_pkg,
                    self.dl_cur_npkgs, self.dl_goal_npkgs,
                    self.dl_cur_nfiles, self.dl_goal_nfiles,
                    self.dl_cur_nbytes / 1024.0 / 1024.0,
                    self.dl_goal_nbytes / 1024.0 / 1024.0)

                if not self.dl_started:
                        self.dl_started = True

        def dl_output_done(self):
                self.dl_cur_pkg = _("Completed")
                self.dl_output()
                gobject.idle_add(self.parent.output_done, _("Download"))

        def act_output(self):
                if (time.time() - self.last_print_time) >= 0.05:
                        self.last_print_time = time.time()
                else:
                        return
                
                gobject.idle_add(self.parent.act_progress, self.act_started,
                    self.act_phase, self.act_cur_nactions, self.act_goal_nactions)

                if not self.act_started:
                        self.act_started = True

        def act_output_done(self):
                self.act_output()
                gobject.idle_add(self.parent.output_done, _("Install"))

        def ind_output(self):
                if (time.time() - self.last_print_time) >= IND_DELAY:
                        self.last_print_time = time.time()
                else:
                        return

                gobject.idle_add(self.parent.ind_progress, self.ind_started,
                    self.ind_phase, self.ind_cur_nitems, self.ind_goal_nitems)

                if not self.ind_started:
                        self.ind_started = True
                        
        def ind_output_done(self):
                self.act_output()
                gobject.idle_add(self.parent.output_done, _("Index"))


class Updatemanager:
        def __init__(self):
                global_settings.client_name = PKG_CLIENT_NAME
                    
                try:
                        self.application_dir = os.environ["UPDATE_MANAGER_ROOT"]
                except KeyError:
                        self.application_dir = "/"
                misc.setlocale(locale.LC_ALL, "")
                for module in (gettext, gtk.glade):
                        module.bindtextdomain("pkg", self.application_dir +
                            "/usr/share/locale")
                        module.textdomain("pkg")
                # XXX Remove and use _() where self._ and self.parent._ are being used
                # Duplicate ListStore setup in get_updates_to_list()
                self.um_list = \
                    gtk.ListStore(
                        gobject.TYPE_INT,         # UM_ID
                        gobject.TYPE_BOOLEAN,     # UM_INSTALL_MARK
                        gtk.gdk.Pixbuf,           # UM_STATUS
                        gobject.TYPE_STRING,      # UM_NAME
                        gtk.gdk.Pixbuf,           # UM_REBOOT
                        gobject.TYPE_STRING,      # UM_LATEST_VER
                        gobject.TYPE_STRING,      # UM_SIZE
                        gobject.TYPE_STRING,      # UM_FMRI                        
                        )
                self.progress_stop_thread = False
                self.initial_active = 0
                self.initial_default = 0
                self.last_select_time = 0
                self.size_thread_running = False
                self.cancelled = False
                self.fmri_description = None
                self.install = False
                self.install_error = False
                self.done_icon = None
                self.blank_icon = None
                self.update_stage = UPDATE_EVAL
                self.toggle_counter = 0
                self.selection_timer = None
                self.package_selection = None
                self.cur_pkg = None
                self.show_all_opts = False
                self.show_install_updates_only = False
                self.do_refresh = False
                self.ua_start = 0
                
                # Progress Dialog
                self.gladefile = self.application_dir + \
                    "/usr/share/update-manager/updatemanager.glade"
                w_xmltree_progress = gtk.glade.XML(self.gladefile, "progressdialog")
                self.w_progress_dialog = w_xmltree_progress.get_widget("progressdialog")
                
                self.w_progressinfo_label = w_xmltree_progress.get_widget("progressinfo")
                self.w_progressinfo_separator = w_xmltree_progress.get_widget(
                    "progressinfo_separator")                
                self.w_progressinfo_expander = \
                    w_xmltree_progress.get_widget("progressinfo_expander")
                self.w_progressinfo_textview = \
                    w_xmltree_progress.get_widget("progressinfo_textview")
                infobuffer = self.w_progressinfo_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)

                self.w_progressinfo_expander_label = \
                    w_xmltree_progress.get_widget("progressinfo_expander_label")
                
                self.w_progress_install_vbox = \
                    w_xmltree_progress.get_widget("progress_install_vbox")
                
                self.w_progress_eval_img = \
                    w_xmltree_progress.get_widget("progress_eval_img")
                self.w_progress_eval_label = \
                    w_xmltree_progress.get_widget("progress_eval_label")
                self.w_progress_download_img = \
                    w_xmltree_progress.get_widget("progress_download_img")
                self.w_progress_download_label = \
                    w_xmltree_progress.get_widget("progress_download_label")
                self.w_progress_install_img = \
                    w_xmltree_progress.get_widget("progress_install_img")
                self.w_progress_install_label = \
                    w_xmltree_progress.get_widget("progress_install_label")
                self.w_progress_index_img = \
                    w_xmltree_progress.get_widget("progress_index_img")
                self.w_progress_index_label = \
                    w_xmltree_progress.get_widget("progress_index_label")
                self.w_progress_closeon_finish_chk = \
                    w_xmltree_progress.get_widget("closeon_finish_checkbutton")

                self.w_progress_cancel = w_xmltree_progress.get_widget("progresscancel")
                self.w_progress_ok = w_xmltree_progress.get_widget("progressok")
                self.w_progressbar = w_xmltree_progress.get_widget("progressbar")
                
                # UM Dialog
                w_xmltree_um = gtk.glade.XML(self.gladefile, "um_dialog")
                self.w_um_dialog = w_xmltree_um.get_widget("um_dialog")
                
                self.w_um_dialog.connect("destroy", self.__on_um_dialog_close)
                self.w_um_intro_label = w_xmltree_um.get_widget("um_intro_label")
                self.w_um_install_button = w_xmltree_um.get_widget("um_install_button")
                self.w_um_updateall_button = \
                    w_xmltree_um.get_widget("um_updateall_button")
                self.w_um_expander = w_xmltree_um.get_widget("um_expander")
                self.w_um_expander.set_expanded(True)

                self.w_progress_dialog.set_transient_for(self.w_um_dialog)

                self.w_um_scrolledwindow = w_xmltree_um.get_widget("um_scrolledwindow")
                self.w_um_treeview = w_xmltree_um.get_widget("um_treeview")  
                self.w_um_textview = w_xmltree_um.get_widget("um_textview")  
                infobuffer = self.w_um_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
                self.w_select_checkbox = w_xmltree_um.get_widget("selectall_checkbutton")
                self.w_delete_button = w_xmltree_um.get_widget("cancel_button")
                
                # ua_confirm_dialog
                w_xmltree_ua = gtk.glade.XML(self.gladefile, "ua_confirm_dialog")
                self.w_ua_confirm_dialog = \
                    w_xmltree_ua.get_widget("ua_confirm_dialog")
                self.w_ua_be_name_entry = \
                    w_xmltree_ua.get_widget("ua_be_name_entry")
                self.w_ua_proceed_button = \
                    w_xmltree_ua.get_widget("ua_proceed_button")
                self.w_ua_cancel_button = \
                    w_xmltree_ua.get_widget("ua_cancel_button")                
                
                self.details_cache = {}
                
                try:
                        dic = \
                            {
                                "on_um_dialog_close": \
                                    self.__on_um_dialog_close,
                                "on_cancel_button_clicked": \
                                    self.__on_cancel_button_clicked,
                                "on_install_button_clicked": \
                                    self.__on_install_button_clicked,
                                "on_um_updateall_button_clicked": \
                                    self.__on_updateall_button_clicked,
                                "on_um_expander_activate": \
                                    self.__on_um_expander_activate,
                                "on_selectall_checkbutton_toggled": \
                                    self.__on_selectall_checkbutton_toggled,
                            }
                        w_xmltree_um.signal_autoconnect(dic)

                        dic_progress = \
                            {
                                "on_progresscancel_clicked": \
                                    self.__on_progresscancel_clicked,
                                "on_progressok_clicked": \
                                    self.__on_progressok_clicked,
                            }
                        w_xmltree_progress.signal_autoconnect(dic_progress)

                        dic_ua = \
                            {
                                "on_ua_cancel_button_clicked": \
                                    self.__on_ua_cancel_button_clicked,
                                "on_ua_proceed_button_clicked": \
                                    self.__on_ua_proceed_button_clicked,
                            }
                        w_xmltree_ua.signal_autoconnect(dic_ua)

                except AttributeError, error:
                        print _("GUI will not respond to any event! %s. "
                            "Check updatemanager.py signals") % error

                self.pr = GUIProgressTracker(self)
                self.api_obj = None
 
                self.w_um_dialog.show_all()

        def __set_cancel_state(self, status):
                if self.install_error:
                        return
                        
                if status:
                        gobject.idle_add(self.w_progress_cancel.grab_focus)

                gobject.idle_add(self.w_progress_cancel.set_sensitive, status)
                
        def __progress_step(self, type_step, img, label, str_step):
                if type_step == UPDATE_ACTIVE:
                        self.__progress_active_step(img, label, str_step)
                elif type_step == UPDATE_DONE:
                        self.__progress_done_step(img, label, str_step)
                else:
                        self.__progress_inactive_step(img, label, str_step)
                        
        def __progress_steps(self, eval_type, evaluate, dl_type, download, install_type,
            install, index_type, index):                        
                self.__progress_step(eval_type, self.w_progress_eval_img,
                    self.w_progress_eval_label, evaluate)
                self.__progress_step(dl_type, self.w_progress_download_img,
                    self.w_progress_download_label,download)
                self.__progress_step(install_type, self.w_progress_install_img,
                    self.w_progress_install_label, install)
                self.__progress_step(index_type, self.w_progress_index_img,
                    self.w_progress_index_label, index)
                        
        def __progress_steps_start(self):
                self.__progress_steps(
                    UPDATE_ACTIVE, _("Evaluate"),
                    UPDATE_INACTIVE, _("Download"),
                    UPDATE_INACTIVE, _("Install"),
                    UPDATE_INACTIVE, _("Index"))
                        
        def __progress_steps_download(self):
                self.__progress_steps(
                    UPDATE_DONE, _("Evaluate"),
                    UPDATE_ACTIVE, _("Download"),
                    UPDATE_INACTIVE, _("Install"),
                    UPDATE_INACTIVE, _("Index"))
 
        def __progress_steps_install(self):
                self.__progress_steps(
                    UPDATE_DONE, _("Evaluate"),
                    UPDATE_DONE, _("Download"),
                    UPDATE_ACTIVE, _("Install"),
                    UPDATE_INACTIVE, _("Index"))
 
        def __progress_steps_index(self):
                self.__progress_steps(
                    UPDATE_DONE, _("Evaluate"),
                    UPDATE_DONE, _("Download"),
                    UPDATE_DONE, _("Install"),
                    UPDATE_ACTIVE, _("Index"))
        
        def __progress_steps_done(self):
                self.__progress_steps(
                    UPDATE_DONE, _("Evaluate"),
                    UPDATE_DONE, _("Download"),
                    UPDATE_DONE, _("Install"),
                    UPDATE_DONE, _("Index"))


        def __progress_cancel_eval(self):
                self.__progress_cancel_step(self.w_progress_eval_img,
                    self.w_progress_eval_label, _("Evaluate - canceling..."))

        def __progress_cancel_download(self):
                self.__progress_cancel_step(self.w_progress_download_img,
                    self.w_progress_download_label, _("Download - canceling..."))
                        

        def __progress_error_eval(self):
                self.__progress_error_step(self.w_progress_eval_img,
                    self.w_progress_eval_label, _("Evaluate - failed"))

        def __progress_error_download(self):
                self.__progress_error_step(self.w_progress_download_img,
                    self.w_progress_download_label, _("Download - failed"))

        def __progress_error_install(self):
                self.__progress_error_step(self.w_progress_install_img,
                    self.w_progress_install_label, _("Install - failed"))

        def __progress_error_index(self):
                self.__progress_error_step(self.w_progress_index_img,
                    self.w_progress_index_label, _("Index - failed"))

        @staticmethod
        def __progress_active_step(widget_image, widget_label, str_step):
                widget_label.set_markup("<b>%s</b>" % str_step)
                widget_image.set_from_stock(gtk.STOCK_GO_FORWARD, gtk.ICON_SIZE_MENU) 

        def __progress_inactive_step(self, widget_image, widget_label, str_step):
                widget_label.set_text("%s" % str_step)
                widget_image.set_from_pixbuf(self.blank_icon)

        def __progress_done_step(self, widget_image, widget_label, str_step):
                widget_label.set_markup("<b>%s</b>" % str_step)                
                widget_image.set_from_pixbuf(self.done_icon)

        def __progress_error_step(self, widget_image, widget_label, str_step):
                widget_label.set_markup("<b>%s</b>" % str_step)
                widget_image.set_from_stock(gtk.STOCK_REMOVE, gtk.ICON_SIZE_MENU)
                
                # On error open the Details panel and make sure the Window is visible
                # to the user, even if it has been minimized
                self.w_progressinfo_expander.set_expanded(True)
                self.w_progress_cancel.set_sensitive(True)
                self.w_um_dialog.present()

        @staticmethod
        def __progress_cancel_step(widget_image, widget_label, str_step):
                widget_label.set_markup("<b>%s</b>" % str_step)
                widget_image.set_from_stock(gtk.STOCK_STOP, gtk.ICON_SIZE_MENU) 


        def __set_initial_selection(self):
                if len(self.um_list) == 0:
                        return                
                self.w_um_treeview.set_cursor(0, None)

        def __remove_installed(self, installed_fmris):
                model = self.w_um_treeview.get_model()
                iter_next = model.get_iter_first()

                installed_fmris_dic = dict([(k, None) for k in installed_fmris])

                while iter_next != None:
                        if model.get_value(iter_next, UM_NAME) in installed_fmris_dic:
                                self.um_list.remove(iter_next)
                                self.toggle_counter -= 1
                        else:
                                iter_next = model.iter_next(iter_next)
                        
        def __mark_cell_data_default_function(self, column, renderer, model, itr, data):
                if itr:
                        if model.get_value(itr, UM_STATUS) != None:
                                self.__set_renderer_active(renderer, False)
                        else:
                                self.__set_renderer_active(renderer, True)
                                
        @staticmethod
        def __set_renderer_active(renderer, active):
                if active:
                        renderer.set_property("sensitive", True)
                        renderer.set_property("mode", gtk.CELL_RENDERER_MODE_ACTIVATABLE)
                else:
                        renderer.set_property("sensitive", False)
                        renderer.set_property("mode", gtk.CELL_RENDERER_MODE_INERT)
                
        def __get_icon_pixbuf(self, icon_name):
                return self.__get_pixbuf_from_path(self.application_dir +
                    "/usr/share/icons/update-manager/", icon_name)

        #
        def get_icon_pixbuf(self, icon_name):
                return self.__get_pixbuf_from_path(self.application_dir +
                    "/usr/share/icons/package-manager/", icon_name)
                    
        def __get_app_pixbuf(self, icon_name):
                return self.__get_pixbuf_from_path(self.application_dir +
                    "/usr/share/update-manager/", icon_name)
                        
        def __get_pixbuf_from_path(self, path, icon_name):
                icon = icon_name.replace(' ', '_')

                # Performance: Faster to check if files exist rather than catching
                # exceptions when they do not. Picked up open failures using dtrace
                png_exists = os.path.exists(self.application_dir + path + icon + ".png")
                svg_exists = os.path.exists(self.application_dir + path + icon + ".svg")
                       
                if not png_exists and not svg_exists:
                        return None
                try:
                        return gtk.gdk.pixbuf_new_from_file(
                            self.application_dir + path + icon + ".png")
                except gobject.GError:
                        try:
                                return gtk.gdk.pixbuf_new_from_file(
                                    self.application_dir + path + icon + ".svg")
                        except gobject.GError:
                                iconview = gtk.IconView()
                                icon = iconview.render_icon(getattr(gtk,
                                    "STOCK_MISSING_IMAGE"),
                                    size = gtk.ICON_SIZE_MENU,
                                    detail = None)
                                # XXX Could return image-we don't want to show ugly icon.
                                return None


        def __get_selected_fmris(self):
                model = self.w_um_treeview.get_model()
                iter_next = model.get_iter_first()
                list_of_selected_fmris = []
                while iter_next != None:
                        if model.get_value(iter_next, UM_INSTALL_MARK):
                                list_of_selected_fmris.append(model.get_value(iter_next,
                                    UM_NAME))
                        iter_next = model.iter_next(iter_next)
                return list_of_selected_fmris

        def init_tree_views(self):
                model = self.w_um_treeview.get_model()
                toggle_renderer = gtk.CellRendererToggle()
                toggle_renderer.connect('toggled', self.__active_pane_toggle, model)
                column = gtk.TreeViewColumn("", toggle_renderer,
                    active = UM_INSTALL_MARK)
                column.set_cell_data_func(toggle_renderer,
                    self.__mark_cell_data_default_function, None)                    
                toggle_renderer.set_property("activatable", True)
                column.set_expand(False)

                # Show Canceland Install Updates + selection column + checkbox
                if self.show_install_updates_only:
                        self.w_um_updateall_button.hide()
                        self.show_all_opts = True

                # Show Cancel, Update All and Install Updates + selection column+checkbox
                if self.show_all_opts:
                        self.w_select_checkbox.show()
                        self.w_um_install_button.show()
                        self.w_um_treeview.append_column(column)
                        self.w_um_intro_label.set_text(_(
                            "Updates are available for the following packages.\n"
                            "Select the packages you want to update and click Install."))
                # Show Cancel, Update All only
                else:
                        self.w_select_checkbox.hide()
                        self.w_um_install_button.hide()
                        self.w_um_intro_label.set_text(_(
                            "Updates are available for the following packages.\n"
                            "Click Update All to create a new boot environment and "
                            "install all packages into it."))
                        
                render_pixbuf = gtk.CellRendererPixbuf()
                column = gtk.TreeViewColumn()
                column.pack_start(render_pixbuf, expand = False)
                column.add_attribute(render_pixbuf, "pixbuf", UM_STATUS)
                column.set_title("   ")
                # Hiding Status column for now
                #self.w_um_treeview.append_column(column)
                
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Name"), name_renderer,
                    text = UM_NAME)
                column.set_cell_data_func(name_renderer, self.__cell_data_function, None)
                column.set_expand(True)
                self.w_um_treeview.append_column(column)
                
                column = gtk.TreeViewColumn()
                render_pixbuf = gtk.CellRendererPixbuf()
                column.pack_start(render_pixbuf, expand = True)
                column.add_attribute(render_pixbuf, "pixbuf", UM_REBOOT)
                # Hiding Reboot required column for now
                # self.w_um_treeview.append_column(column)

                version_renderer = gtk.CellRendererText()
                version_renderer.set_property('xalign', 0.0)
                column = gtk.TreeViewColumn(_("Latest Version"), version_renderer,
                    text = UM_LATEST_VER) 
                column.set_cell_data_func(version_renderer,
                    self.__cell_data_function, None)
                column.set_expand(True)
                self.w_um_treeview.append_column(column)

                size_renderer = gtk.CellRendererText()
                size_renderer.set_property('xalign', 0.0)
                column = gtk.TreeViewColumn(_("Size (Meg)"), size_renderer,
                    text = UM_SIZE)
                column.set_cell_data_func(size_renderer, self.__cell_data_function, None)
                column.set_expand(True)
                # XXX Hiding Size as it takes too long to fetch at the minute
                #self.w_um_treeview.append_column(column)

                #Added selection listener
                self.package_selection = self.w_um_treeview.get_selection()
                self.package_selection.set_mode(gtk.SELECTION_SINGLE)
                self.package_selection.connect("changed",
                    self.__on_package_selection_changed, None)

                # Setup Icons
                self.done_icon = self.__get_icon_pixbuf("status_checkmark")
                self.blank_icon = self.__get_icon_pixbuf("status_blank")
                self.w_um_dialog.set_icon(self.__get_app_pixbuf("PM_package_36x"))
                self.w_ua_confirm_dialog.set_icon(self.__get_app_pixbuf("PM_package_36x"))

        @staticmethod
        def __get_image_path():
                '''This function gets the image path or the default'''
                if local_image_dir != None:
                        return local_image_dir
                        
                image_directory = os.popen(IMAGE_DIR_COMMAND).readline().rstrip()
                if len(image_directory) == 0:
                        image_directory = IMAGE_DIRECTORY_DEFAULT
                return image_directory
                
        def get_updates_to_list(self):
                '''This function fetches a list of the updates
                        that are available to list'''
                # MUST match self.um_list ListStore setup in __init__
                um_list = \
                    gtk.ListStore(
                        gobject.TYPE_INT,         # UM_ID
                        gobject.TYPE_BOOLEAN,     # UM_INSTALL_MARK
                        gtk.gdk.Pixbuf,           # UM_STATUS
                        gobject.TYPE_STRING,      # UM_NAME
                        gtk.gdk.Pixbuf,           # UM_REBOOT
                        gobject.TYPE_STRING,      # UM_LATEST_VER
                        gobject.TYPE_STRING,      # UM_SIZE
                        gobject.TYPE_STRING,      # UM_FMRI                        
                        )

                image_obj = self.__get_image_obj_from_directory(self.__get_image_path())
                
                count = 0
                pkg_upgradeable = None
                for pkg, state in sorted(image_obj.inventory(all_known = True)):
                        while gtk.events_pending():
                                gtk.main_iteration(False)
                        if state["upgradable"] and state["state"] == "installed":
                                pkg_upgradeable = pkg
                        
                        # Allow testing by listing uninstalled packages, -u option
                        add_package = False
                        if pkg_upgradeable != None and not state["upgradable"]:
                                if list_uninstalled:
                                        add_package = not \
                                        image_obj.fmri_is_same_pkg(pkg_upgradeable, pkg)
                                else:
                                        add_package = \
                                        image_obj.fmri_is_same_pkg(pkg_upgradeable, pkg)

                        if add_package:
                                count += 1
                                # XXX: Would like to caputre if package for upgrade is
                                # incorporated, could then indicate this to user
                                # and take action when doing install to run image-update.
                                #if state["incorporated"]:
                                #        incState = _("Inc")
                                #else:
                                #        incState = "--"
                                
                                um_list.insert(count, [count, False, None,
                                    pkg.get_name(), None, pkg.get_version(), None,
                                    pkg.get_fmri()])
                                
                if debug:
                        print _("count: %d") % count

                self.progress_stop_thread = True
                gobject.idle_add(self.w_um_treeview.set_model, um_list)
                gobject.idle_add(self.__set_initial_selection)
                self.um_list = um_list                
                self.__selectall_toggle(True)
                if len(self.um_list) == 0:
                        self.__display_noupdates()
                        return          
                        
                # XXX: Currently this will fetch the sizes but it really slows down the
                # app responsiveness - until we get caching I think we should just hide
                # the size column
                # gobject.timeout_add(1000, self.__setup_sizes)
                
        def __get_api_obj(self):
                if self.api_obj != None:
                        return self.api_obj
                try:
                        self.api_obj = api.ImageInterface(self.__get_image_path(),
                            CLIENT_API_VERSION, self.pr, self.__set_cancel_state,
                            PKG_CLIENT_NAME)
                        return self.api_obj
                except api_errors.ImageNotFoundException, ine:
                        self.w_um_expander.set_expanded(True)
                        infobuffer = self.w_um_textview.get_buffer()
                        infobuffer.set_text("")
                        textiter = infobuffer.get_end_iter()
                        infobuffer.insert_with_tags_by_name(textiter, _("Error\n"),
                            "bold")
                        infobuffer.insert(textiter,
                            _("'%s' is not an install image\n") % 
                            ine.user_specified)
                except api_errors.VersionException, ve:
                        self.w_um_expander.set_expanded(True)
                        infobuffer = self.w_um_textview.get_buffer()
                        infobuffer.set_text("")
                        textiter = infobuffer.get_end_iter()
                        infobuffer.insert_with_tags_by_name(textiter, _("Error\n"),
                            "bold")
                        infobuffer.insert(textiter, 
                            _("Version mismatch: expected %s received %s\n") %
                            (ve.expected_version, ve.received_version))
                return None
                
        def __display_noupdates(self):
                self.w_um_scrolledwindow.set_policy(gtk.POLICY_NEVER,
                    gtk.POLICY_AUTOMATIC)
                self.w_um_expander.set_expanded(True)
                infobuffer = self.w_um_textview.get_buffer()
                textiter = infobuffer.get_end_iter()
                infobuffer.insert_with_tags_by_name(textiter,
                    _("\nNo Updates available"), "bold")

                self.w_um_install_button.set_sensitive(False)
                self.w_um_updateall_button.set_sensitive(False)
                self.w_select_checkbox.set_active(False)
                self.w_select_checkbox.set_sensitive(False)
                self.w_um_dialog.present()
                
        def __get_info_from_name(self, name):
                local = True
                get_license = False
                
                if self.fmri_description != name:
                        return None
                if self.__get_api_obj() == None:
                        return None
                        
                ret = self.__get_api_obj().info([name], local, get_license)
                
                pis = ret[api.ImageInterface.INFO_FOUND]
                if len(pis) == 1:
                        return pis[0]
                else:
                        return None

        def __get_details_from_name(self, name):                        
                info = self.__get_info_from_name(name)
                if info is not None:
                        return self.__update_details_from_info(name, info)
                else:
                        return None
                        
        def __update_details_from_info(self, name, info):
                ver = "%s-%s" % (info.version, info.branch)
                str_details = _(
                    '\nDescription:\t\t%s\nFMRI:       \t\t\t%s' +
                    '\nVersion:    \t\t%s\nPackaged on:\t\t%s' +
                    '\nSize:       \t\t\t%s\n') \
                    % (info.summary, info.fmri, ver, info.packaging_date,
                    misc.bytes_to_str(info.size))
                self.details_cache[name] = str_details
                return str_details

        # This is copied from a similar function in packagemanager.py 
        def __get_image_obj_from_directory(self, image_directory):
                image_obj = image.Image()
                dr = "/"
                try:
                        image_obj.find_root(image_directory)
                        while gtk.events_pending():
                                gtk.main_iteration(False)
                        image_obj.load_config()
                        while gtk.events_pending():
                                gtk.main_iteration(False)
                        image_obj.load_catalogs(self.pr)
                        while gtk.events_pending():
                                gtk.main_iteration(False)
                except ValueError:
                        print _('%s is not valid image, trying root image') \
                            % image_directory
                        try:
                                dr = os.environ["PKG_IMAGE"]
                        except KeyError:
                                print
                        try:
                                image_obj.find_root(dr)
                                image_obj.load_config()
                        except ValueError:
                                print _('%s is not valid root image, return None') \
                                    % dr
                                image_obj = None
                return image_obj

                
        @staticmethod
        def __removed_filter(model, itr):
                '''This function filters category in the main application view'''
                return True
                
        def __on_package_selection_changed(self, selection, widget):
                '''This function is for handling package selection changes'''
                model, itr = selection.get_selected()
                if itr:                        
                        fmri = model.get_value(itr, UM_NAME) 
                        delta = time.time() - self.last_select_time
                        if delta < SELECTION_CHANGE_LIMIT:
                                if self.selection_timer is not None:
                                        self.selection_timer.cancel()
                                        self.selection_timer = None
                        
                        self.fmri_description = fmri
                        self.last_select_time = time.time()

                        if self.details_cache.has_key(fmri):
                                if self.selection_timer is not None:
                                        self.selection_timer.cancel()  
                                        self.selection_timer = None
                                infobuffer = self.w_um_textview.get_buffer()
                                infobuffer.set_text("")
                                textiter = infobuffer.get_end_iter()
                                infobuffer.insert_with_tags_by_name(textiter,
                                    "\n%s\n" % fmri, "bold")
                                infobuffer.insert(textiter, self.details_cache[fmri])
                        else:
                                infobuffer = self.w_um_textview.get_buffer()
                                infobuffer.set_text(
                                    _("\nFetching details for %s ...") % fmri)
                                self.selection_timer = Timer(SELECTION_CHANGE_LIMIT,
                                    self.__show_package_info_thread,
                                    args=(fmri, )).start()

        def __show_package_info_thread(self, fmri):
                Thread(target = self.__show_package_info,
                    args = (fmri, )).start()

        def __show_package_info(self, fmri):
                details = self.__get_details_from_name(fmri)
                if self.fmri_description == fmri and details != None:
                        infobuffer = self.w_um_textview.get_buffer()
                        infobuffer.set_text("")
                        textiter = infobuffer.get_end_iter()
                        infobuffer.insert_with_tags_by_name(textiter,
                            "\n%s\n" % fmri, "bold")
                        infobuffer.insert(textiter, details)
                elif self.fmri_description == fmri and details == None:
                        infobuffer = self.w_um_textview.get_buffer()
                        infobuffer.set_text("")
                        textiter = infobuffer.get_end_iter()
                        infobuffer.insert_with_tags_by_name(textiter,
                            _("\nNo details available"), "bold")

        def __on_um_dialog_close(self, widget):
                self.__exit_app()

        def __on_cancel_button_clicked(self, widget):
                self.__exit_app()

        def __exit_app(self):
                self.cancelled = True
                self.w_um_dialog.hide()
                gtk.main_quit()
                sys.exit(0)
                return True
        
        def __on_progressok_clicked(self, widget):
                self.w_progress_dialog.hide()

        def __on_progresscancel_clicked(self, widget):
                if self.install_error:
                        self.w_progress_dialog.hide()
                        self.w_progressinfo_expander.set_expanded(False)
                        
                if self.api_obj != None and self.api_obj.can_be_canceled():
                        if self.update_stage == UPDATE_EVAL:
                                self.__progress_cancel_eval()
                        elif  self.update_stage == UPDATE_DOWNLOAD:
                                self.__progress_cancel_download()
                                
                        self.__update_progress_info(
                                _("\nCanceling update, please wait ..."))
                        self.w_progress_cancel.set_sensitive(False)
                        Thread(target = self.api_obj.cancel).start()
                else:
                        self.__update_progress_info(
                                _("\nUnable to cancel at this time."))

        def __on_install_button_clicked(self, widget):
                self.setup_progressdialog_show(_("Installing Updates"),
                        showCancel = True, showOK = True,
                        isInstall = True, showCloseOnFinish = debug)
                Thread(target = self.__install).start()   

        def __on_ua_cancel_button_clicked(self, widget):
                self.w_ua_confirm_dialog.hide()
                return

        def __on_ua_proceed_button_clicked(self, widget):
                self.w_ua_confirm_dialog.hide()
                self.ua_start = time.time()
                self.setup_progressdialog_show(_("Update All"),
                    showCancel = True, showOK = True,
                    isInstall = True, showCloseOnFinish = debug)

                Thread(target = self.__update_image,
                        args = (self.w_ua_be_name_entry.get_text(),)).start()
                return

        def __on_updateall_button_clicked(self, widget):
                self.__selectall_toggle(True)
                date_str = time.strftime("%m/%d/%Y", time.localtime())
                self.w_ua_be_name_entry.set_text("opensolaris-ua-%s" % date_str)
                self.w_ua_proceed_button.grab_focus()
                self.w_ua_confirm_dialog.show()
                return
               
        def __on_selectall_checkbutton_toggled(self, widget):
                self.__selectall_toggle(widget.get_active())

        def __handle_incorporated_error(self, list_incorp):
                self.__update_progress_info(_("ERROR"), True)
                self.__update_progress_info(
                        _("Following Incorporated package(s) cannot be updated:"))
                for i in list_incorp:
                        self.__update_progress_info("\t%s" % i)
                self.__update_progress_info(
                        _("Update using: Update All\n"), True)

        def __handle_update_progress_error(self, str_error, ex = None,
                stage = UPDATE_EVAL):
                self.install_error = True
                if stage == UPDATE_EVAL:
                        gobject.idle_add(self.__progress_error_eval)
                elif stage == UPDATE_DOWNLOAD:
                        gobject.idle_add(self.__progress_error_download)
                elif stage == UPDATE_INSTALL:
                        gobject.idle_add(self.__progress_error_install)
                elif stage == UPDATE_INDEX:
                        gobject.idle_add(self.__progress_error_index)
                else:
                        gobject.idle_add(self.__progress_error_eval)
                        
                gobject.idle_add(self.__update_progress_info,
                    _("\nERROR"), True)
                if ex != None:
                        gobject.idle_add(self.__update_progress_info,
                            _("%s\n%s" % (str_error, ex)))
                else:
                        gobject.idle_add(self.__update_progress_info,
                            _("%s\n" % str_error))
                self.__cleanup()

        def __update_image(self, be_name = None):
                self.install = True
                self.install_error = False
                self.update_stage = UPDATE_EVAL

                # Evaluate
                try:
                        gobject.idle_add(self.__update_progress_info,
                            _("\nEvaluate\n"), True)
                        if self.__get_api_obj() == None:
                                return
                                
                        stuff_to_do, opensolaris_image, cre = \
                            self.__get_api_obj().plan_update_all(sys.argv[0],
                                refresh_catalogs = self.do_refresh)
                            #XXX waiting for change to API to allow be name to be passed
                            # self.api_obj.plan_update_all(sys.argv[0], be_name)
                        if cre:
                                self.__handle_update_progress_error(
                                    _("Update All failed during catalog refresh\n"
                                    "while determining what to update:"), cre,
                                    stage = self.update_stage)
                                return
                        if not opensolaris_image:
                                self.__handle_update_progress_error(
                                    _("This is not an OpenSolaris image\n"),
                                    stage = self.update_stage)
                                return
                        if not stuff_to_do:
                                self.__handle_update_progress_error(
                                    _("No updates available for this image."),
                                    stage = self.update_stage)
                                return
                except (api_errors.CanceledException):
                        self.__handle_cancel_exception()
                        return
                except api_errors.CatalogRefreshException, cre:
                        self.__handle_update_progress_error(
                            _("Update All failed during catalog refresh\n"
                            "while determining what to update:"), cre,
                            stage = self.update_stage)
                except api_errors.PlanCreationException, pce:
                        self.__handle_update_progress_error(
                            _("Update All failure in plan creation:"), pce,
                            stage = self.update_stage)
                        return
                except api_errors.IpkgOutOfDateException:
                        self.__handle_update_progress_error(
                            _(
                            "pkg(5) appears to be out of date and should be\n" +
                            "updated before running Update All.\n" +
                            "Please update pkg(5) using:\n" +
                            "\t'pfexec pkg install SUNWipkg' " +
                            "and then retry Update All."),
                            stage = self.update_stage)
                        return
                except api_errors.ApiException, aex:
                        self.__handle_update_progress_error(
                            _("Update All API failure in evaluation:"), aex,
                            stage = self.update_stage)
                        return
                except Exception, uex:
                        self.__handle_update_progress_error(
                            _("Update All unexpected error in evaluation:"),
                            uex, stage = self.update_stage)
                        return
                        
                if self.__shared_update_steps(_("Update All"),
                    _("Update All finished successfully.\n")) != 0:
                        return
                
                gobject.idle_add(self.__display_update_image_success)       

        def __display_update_image_success(self):
                elapsed = (time.time() - self.ua_start)/ 60.0 
                info_str = ""
                if elapsed >= 1.0:
                        info_str = \
                            _(
                            "\nUpdate All finished successfully in %1.f mins\n\n" %
                            elapsed)
                else:
                        info_str = \
                            _(
                            "\nUpdate All finished successfully in < 1 min\n\n")

                info_str += _(
                    "Please reboot after reviewing the release notes posted at:\n\n"
                    "http://opensolaris.org/os/project/indiana/resources/"
                    "relnotes/200811/x86/")

                self.w_um_dialog.hide()
                msgbox = gtk.MessageDialog(parent = self.w_um_dialog,
                    buttons = gtk.BUTTONS_CLOSE, flags = gtk.DIALOG_MODAL,
                    type = gtk.MESSAGE_INFO,
                    message_format = info_str)
                msgbox.set_title(_("Update All Completed"))
                msgbox.run()
                msgbox.destroy()                        
                self.__exit_app()
                
        def __handle_cancel_exception(self):
                gobject.idle_add(self.w_progress_dialog.hide)
                gobject.idle_add(self.w_progressinfo_expander.set_expanded, False)
                self.__cleanup()                

        def __install(self):
                self.install = True
                self.install_error = False
                self.update_stage = UPDATE_EVAL
                list_fmris_to_install = self.__get_selected_fmris()
                if len(list_fmris_to_install) == 0:
                        self.__handle_update_progress_error(
                            _("Nothing selected to update."))
                        return
                        
                if self.__get_api_obj() == None:
                        return
      
                if debug:
                        print _("Updating ...")
                        print list_fmris_to_install
                        
                # Evaluate
                try:
                        gobject.idle_add(self.__update_progress_info,
                            _("\nEvaluate\n"), True)
                        ret, exception_caught = \
                            self.__get_api_obj().plan_install(list_fmris_to_install,
                            [], refresh_catalogs = self.do_refresh)
                        if exception_caught != None:
                                self.__handle_update_progress_error(
                                    _("Update error in plan install:"),
                                    exception_caught,
                                    stage = self.update_stage)
                        return
                                
                except (api_errors.CanceledException):
                        self.__handle_cancel_exception()
                        return
                except (api_errors.ApiException), aex:
                        self.__handle_update_progress_error(
                            _("Update unexpected API error:"), aex,
                            stage = self.update_stage)
                        return
                except (Exception), uex:
                        self.__handle_update_progress_error(
                            _("Update unexpected error:"), uex,
                            stage = self.update_stage)
                        return
                
                if not ret:
                        #XXX Nothing to do, must be an incorporated package
                        # need to offer Update All to user
                        self.install_error = True
                        gobject.idle_add(self.__progress_error_eval)
                        gobject.idle_add(self.__handle_incorporated_error,
                            list_fmris_to_install)
                        self.__cleanup()    
                        return
                        
                list_changes = self.__get_api_obj().describe().get_changes()
                list_planned = [x[1].pkg_stem for x in list_changes]

                if len(list_planned) != len(list_fmris_to_install):
                        list_incorp = self.__unique(list_fmris_to_install, list_planned)
                        gobject.idle_add(self.__progress_error_eval)
                        gobject.idle_add(self.__handle_incorporated_error, list_incorp)

                gobject.idle_add(self.__update_progress_info,
                    _("Packages to be installed:"))
                for i in list_planned:
                        gobject.idle_add(self.__update_progress_info, "\t%s" % i)

                if self.__shared_update_steps(_("Update"),
                    _("Update finished successfully.")) != 0:
                        return
                        
                gobject.idle_add(self.__remove_installed, list_planned)
                gobject.idle_add(self.w_um_install_button.set_sensitive, False)
                gobject.idle_add(self.w_progressinfo_expander.set_expanded, False)
        
        def __shared_update_steps(self, what_msg, success_msg):
                # Download
                try:
                        self.update_stage = UPDATE_DOWNLOAD
                        self.__get_api_obj().prepare()
                except (api_errors.CanceledException):
                        self.__handle_cancel_exception()
                        return 1
                except (api_errors.ApiException), aex:
                        self.install_error = True
                        gobject.idle_add(self.__progress_error_download)
                        gobject.idle_add(self.__update_progress_info,
                            _("\nERROR"), True)
                        gobject.idle_add(self.__update_progress_info,
                            _("%s Download failed:\n%s" % (what_msg, aex)))
                        self.__cleanup()                
                        return 1
                except EnvironmentError, uex:
                        if uex.errno in (errno.EDQUOT, errno.ENOSPC):
                                self.__handle_update_progress_error(
                                    _(
                                    "%s exceded available disc space" % (what_msg)),
                                    stage = self.update_stage)
                                gobject.idle_add(self.__prompt_to_load_beadm)
                        else:
                                self.__handle_update_progress_error(
                                    _("%s unexpected error:" % (what_msg)),
                                    uex, stage = self.update_stage)
                        return 1
                except Exception, uex:
                        self.__handle_update_progress_error(
                                _("%s unexpected error:" % (what_msg)),
                                uex, stage = self.update_stage)
                        return 1

                # Install
                try:
                        self.update_stage = UPDATE_INSTALL
                        gobject.idle_add(self.w_progress_cancel.set_sensitive, False)
                        self.__get_api_obj().execute_plan()
                except (api_errors.CanceledException):
                        self.__handle_cancel_exception()
                        return 1
                except (api_errors.ApiException), aex:
                        self.install_error = True
                        gobject.idle_add(self.__progress_error_install)
                        gobject.idle_add(self.__update_progress_info,
                            _("\nERROR"), True)
                        gobject.idle_add(self.__update_progress_info,
                            _("%s Execute plan failed:\n%s" % (what_msg, aex)))
                        self.__cleanup()                
                        return 1
                except EnvironmentError, uex:
                        if uex.errno in (errno.EDQUOT, errno.ENOSPC):
                                self.__handle_update_progress_error(
                                    _(
                                    "%s exceded available disc space" % what_msg),
                                    stage = self.update_stage)
                                gobject.idle_add(self.__prompt_to_load_beadm)
                        else:
                                self.__handle_update_progress_error(
                                    _("%s unexpected error:" % (what_msg)),
                                    uex, stage = self.update_stage)
                        return 1
                except Exception, uex:
                        self.__handle_update_progress_error(
                                _("%s unexpected error:" % (what_msg)),
                                uex, stage = self.update_stage)
                        return 1
                        
                self.__cleanup()                
                gobject.idle_add(self.__progress_steps_done)
                gobject.idle_add(self.__update_progress_info,
                    _(success_msg), True)
                gobject.idle_add(self.w_progress_ok.set_sensitive, True)
                        
                return 0

        def __prompt_to_load_beadm(self):
                msgbox = gtk.MessageDialog(parent = self.w_progress_dialog,
                    buttons = gtk.BUTTONS_OK_CANCEL, flags = gtk.DIALOG_MODAL,
                    type = gtk.MESSAGE_ERROR,
                    message_format = _(
                    "Not enough disc space: the Update All action cannot "
                    "be performed.\n\n"
                    "Click OK to launch BE Management to manage your "
                    "existing BE's and free up disc space."))
                msgbox.set_title(_("Not Enough Disc Space"))
                result = msgbox.run()
                msgbox.destroy()
                if result == gtk.RESPONSE_OK:
                        gobject.idle_add(self.__create_beadm)
                        
        def __create_beadm(self):
                self.gladefile = \
                        "/usr/share/package-manager/packagemanager.glade"
                beadm.Beadmin(self)
                return False
                
        @staticmethod
        def __unique(list1, list2):
                """Return a list containing all items
                        in 'list1' that are not in 'list2'"""
                list2 = dict([(k, None) for k in list2])
                return [item for item in list1 if item not in list2]
                
        def __cleanup(self):
                self.install = False
                self.api_obj.reset()
                self.pr.reset()
                self.progress_stop_thread = True   
                
        @staticmethod
        def __on_um_expander_activate(widget):
                return

        def __selectall_toggle(self, select):
                for row in self.um_list:
                        row[UM_INSTALL_MARK] = select
                if select:
                        self.toggle_counter += len(self.um_list)
                        self.w_um_install_button.set_sensitive(True)
                else:
                        self.toggle_counter = 0
                        self.w_um_install_button.set_sensitive(False)

        def __active_pane_toggle(self, cell, filtered_path, filtered_model):
                model = self.w_um_treeview.get_model()
                itr = model.get_iter(filtered_path)
                if itr:
                        installed = model.get_value(itr, UM_STATUS)
                        if installed is None:
                                modified = model.get_value(itr, UM_INSTALL_MARK)
                                model.set_value(itr, UM_INSTALL_MARK, not modified)
                        if not modified:
                                self.toggle_counter += 1
                        else:
                                self.toggle_counter -= 1

                        if self.toggle_counter > 0:
                                self.w_um_install_button.set_sensitive(True)
                        else:
                                self.toggle_counter = 0
                                self.w_um_install_button.set_sensitive(False)
                                
        @staticmethod
        def __cell_data_function(column, renderer, model, itr, data):
                '''Function which sets the background colour to black if package is 
                selected'''
                if itr:
                        if model.get_value(itr, 1):
                                #XXX Setting BOLD looks too noisy - disable for now
                                # renderer.set_property("weight", pango.WEIGHT_BOLD)
                                renderer.set_property("weight", pango.WEIGHT_NORMAL)
                        else:
                                renderer.set_property("weight", pango.WEIGHT_NORMAL)
        
        def __on_progressdialog_progress(self, isInstall):
                if not self.progress_stop_thread:
                        self.w_progressbar.pulse()
                        return True
                else:
                        if isInstall:
                                self.w_progressbar.set_fraction(0.0)
                                if not self.install_error and \
                                    self.w_progress_closeon_finish_chk.get_active():
                                        self.w_progress_dialog.hide()
                        else:
                                self.w_progress_dialog.hide()
                        return False

        def setup_progressdialog_show(self, title, info = None, showDetails = True, 
                showCancel = False, showOK = False, isInstall = False, 
                showCloseOnFinish = False):
                infobuffer = self.w_progressinfo_textview.get_buffer()
                infobuffer.set_text("")

                if info != None:
                        self.w_progressinfo_label.set_text(info)
                        self.w_progressinfo_label.show()
                else:
                        self.w_progressinfo_label.hide()
                        
                if showDetails:
                        self.w_progressinfo_expander.show()    
                        self.w_progressinfo_separator.show()    
                        self.w_progressinfo_expander.set_expanded(False)  
                else:
                        self.w_progressinfo_expander.hide()    
                        self.w_progressinfo_separator.hide()    
                        
                if showCancel:
                        self.w_progress_cancel.show()
                        self.w_progress_cancel.set_sensitive(True)
                        self.w_progress_cancel.grab_focus()
                else:
                        self.w_progress_cancel.hide() 
                        
                if showOK:
                        self.w_progress_ok.show()
                        self.w_progress_ok.set_sensitive(False)
                else:
                        self.w_progress_ok.hide()

                if isInstall:
                        self.__progress_steps_start()
                        self.w_progress_install_vbox.show()
                else:
                        self.w_progress_install_vbox.hide()   
                        
                if showCloseOnFinish:
                        self.w_progress_closeon_finish_chk.show()
                        self.w_progress_ok.show()
                else:
                        self.w_progress_closeon_finish_chk.hide()
                        self.w_progress_ok.hide()
                        
                self.w_progress_dialog.set_title(title)
                
                self.w_progress_dialog.show()
                self.progress_stop_thread = False
                gobject.timeout_add(100, self.__on_progressdialog_progress, isInstall)

        def setup_updates(self):
                Thread(target = self.get_updates_to_list(), args = ()).start()
                return False

        @staticmethod
        def __update_size(size, pkg):
                pkg[UM_SIZE] = size/ 1024.0 /1024.0 # Display in MB

        # Handle GUI Progress Output
        def output(self, str_out): 
                self.__update_progress_info(str_out)
                if debug:
                        print str_out
                
        def output_done(self, what="not specified"): 
                self.__update_progress_info(" ")
                        
                if debug:
                        print "%s: finished" % what
                
        @staticmethod
        def progress_pulse():
                if debug:
                        print "pulse: \n"

        def dl_progress(self, dl_started, dl_cur_pkg,
            dl_cur_npkgs, dl_goal_npkgs,
            dl_cur_nfiles, dl_goal_nfiles,
            dl_cur_nmegbytes, dl_goal_nmegbytes): 
                if not dl_started:
                        self.cur_pkg = ""
                        self.__progress_steps_download()
                        self.__update_progress_info(_("\nDownload\n"), True)
                        
                if self.cur_pkg != dl_cur_pkg:
                        self.__update_progress_info("%s" % dl_cur_pkg)
                self.cur_pkg = dl_cur_pkg
                        
                self.__update_progress_info(
                    _("\tpkg %d/%d: \tfiles %d/%d \txfer %.2f/%.2f(meg)") %
                    (dl_cur_npkgs, dl_goal_npkgs,
                    dl_cur_nfiles, dl_goal_nfiles,
                    dl_cur_nmegbytes, dl_goal_nmegbytes))
                
                if debug:
                        print "DL: %s - %s\npkg %d/%d: files %d/%d: megs %.2f/%.2f\n" % \
                            (dl_started, dl_cur_pkg,
                            dl_cur_npkgs, dl_goal_npkgs,
                            dl_cur_nfiles, dl_goal_nfiles,
                            dl_cur_nmegbytes, dl_goal_nmegbytes)

        def act_progress(self, act_started,
            act_phase, act_cur_nactions, act_goal_nactions): 
                                
                if not act_started:
                        self.__progress_steps_install()
                        self.__update_progress_info(_("\nInstall\n"), True)
                        self.__update_progress_info(
                            _("\t%s\t%d/%d actions") %
                            (act_phase, act_cur_nactions, act_goal_nactions))
                else:
                        self.__update_progress_info(
                            _("\t%s\t%d/%d actions") %
                            (act_phase, act_cur_nactions, act_goal_nactions))
                
                if debug:
                        print "Install: %s - %s\nact %d/%d\n" % \
                            (act_started, act_phase, act_cur_nactions,
                            act_goal_nactions)

        def ind_progress(self, ind_started,
            ind_phase, ind_cur_nitems, ind_goal_nitems):
                if not self.install:
                        return
                        
                if not ind_started:
                        if self.update_stage != UPDATE_INSTALL:
                                return
                        self.update_stage = UPDATE_INDEX
                        self.__progress_steps_index()                        
                        self.__update_progress_info(_("Index\n"), True)
                        self.__update_progress_info(_("\t%-25s\t%d/%d actions" %
                            (ind_phase, ind_cur_nitems, ind_goal_nitems)))
                else:
                        self.__update_progress_info(
                            _("\t%-25s\t%d/%d actions") %
                            (ind_phase, ind_cur_nitems, ind_goal_nitems))
                        
                if debug:
                        print "Index: %s - %s\nact %d/%d\n" % \
                            (ind_started, ind_phase, ind_cur_nitems, ind_goal_nitems)

        def __update_progress_info(self, str_out, bold = False):
                infobuffer = self.w_progressinfo_textview.get_buffer()
                textiter = infobuffer.get_end_iter()
                
                # Requires TextView tag to be setup once in __init__
                # infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
                if bold:
                        infobuffer.insert_with_tags_by_name(textiter,
                            "%s\n" % str_out, "bold")
                else:
                        infobuffer.insert(textiter, "%s\n" % str_out)
                self.w_progressinfo_textview.scroll_to_iter(textiter, 0.0)
                
#-------------------- remove those
def main():
        gtk.main()
        return 0
        
if __name__ == "__main__":
        list_uninstalled = False
        debug = False
        show_all_opts = False
        show_install_updates_only = False
        local_image_dir = None
        do_refresh = False

        try:
                opts, args = getopt.getopt(sys.argv[1:], "hdualir",
                    ["help", "debug","uninstalled"])
        except getopt.error, msg:
                print "%s, for help use --help" % msg
                sys.exit(2)

        for option, argument in opts:
                if option in ("-h", "--help"):
                        print "Use -d (--debug) to run in debug mode."
                        sys.exit(0)
                if option in ("-d", "--debug"):
                        debug = True
                if option in ("-u", "--uninstalled"):
                        list_uninstalled = True
                if option in ("-a", "--all"):
                        show_all_opts = True
                if option in ("-i", "--install_updates"):
                        show_install_updates_only = True
                if option in ("-l", "--local_image"):
                        local_image_dir = os.getcwd()
                # Refresh catalogs during plan_install and plan_update_all
                if option in ("-r", "--refresh"):
                        do_refresh = True
                        
        um = Updatemanager()
        um.show_all_opts = show_all_opts
        um.show_install_updates_only = show_install_updates_only
        um.do_refresh = do_refresh
        um.init_tree_views()

        um.setup_progressdialog_show(_("Checking for new software"),
            showDetails = False)
        gobject.timeout_add(UPDATES_FETCH_DELAY, um.setup_updates)
        main()

