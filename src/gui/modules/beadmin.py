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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import sys
import pango
import time
import datetime
import locale
import pkg.pkgsubprocess as subprocess
from threading import Thread

try:
        import gobject
        gobject.threads_init()
        import gnome
        import gtk
        import gtk.glade
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)
import pkg.gui.misc as gui_misc

nobe = False

try:
        import libbe as be
except ImportError:
        # All actions are disabled when libbe can't be imported. 
        nobe = True
import pkg.misc

#BE_LIST
(
BE_ID,
BE_MARKED,
BE_NAME,
BE_ORIG_NAME,
BE_DATE_TIME,
BE_CURRENT_PIXBUF,
BE_ACTIVE_DEFAULT,
BE_SIZE,
BE_EDITABLE
) = range(9)

class Beadmin:
        def __init__(self, parent):
                self.parent = parent

                if nobe:
                        msg = _("The <b>libbe</b> library was not "
                            "found on your system."
                            "\nAll functions for managing Boot Environments are disabled")
                        msgbox = gtk.MessageDialog(
                            buttons = gtk.BUTTONS_CLOSE,
                            flags = gtk.DIALOG_MODAL, type = gtk.MESSAGE_INFO,
                            message_format = None)
                        msgbox.set_markup(msg)
                        msgbox.set_title(_("BE management"))
                        msgbox.run()
                        msgbox.destroy()
                        return

                self.be_list = \
                    gtk.ListStore(
                        gobject.TYPE_INT,         # BE_ID
                        gobject.TYPE_BOOLEAN,     # BE_MARKED
                        gobject.TYPE_STRING,      # BE_NAME
                        gobject.TYPE_STRING,      # BE_ORIG_NAME
                        gobject.TYPE_STRING,      # BE_DATE_TIME
                        gtk.gdk.Pixbuf,           # BE_CURRENT_PIXBUF
                        gobject.TYPE_BOOLEAN,     # BE_ACTIVE_DEFAULT
                        gobject.TYPE_STRING,      # BE_SIZE
                        gobject.TYPE_BOOLEAN,     # BE_EDITABLE
                        )
                self.progress_stop_thread = False
                self.initial_active = 0
                self.initial_default = 0
                w_tree_beadmin = gtk.glade.XML(parent.gladefile, "beadmin")
                w_tree_progress = gtk.glade.XML(parent.gladefile, "progressdialog")
                w_tree_beconfirmation = gtk.glade.XML(parent.gladefile,
                    "beconfirmationdialog")
                self.w_beadmin_dialog = w_tree_beadmin.get_widget("beadmin")
                self.w_be_treeview = w_tree_beadmin.get_widget("betreeview")
                self.w_cancel_button = w_tree_beadmin.get_widget("cancelbebutton")
                self.w_ok_button = w_tree_beadmin.get_widget("okbebutton")
                w_active_gtkimage = w_tree_beadmin.get_widget("activebeimage")
                self.w_progress_dialog = w_tree_progress.get_widget("progressdialog")
                self.w_progressinfo_label = w_tree_progress.get_widget("progressinfo")
                progress_button = w_tree_progress.get_widget("progresscancel")
                self.w_progressbar = w_tree_progress.get_widget("progressbar")
                self.w_beconfirmation_dialog =  \
                    w_tree_beconfirmation.get_widget("beconfirmationdialog")
                self.w_beconfirmation_textview = \
                    w_tree_beconfirmation.get_widget("beconfirmtext")
                self.w_cancelbe_button = w_tree_beconfirmation.get_widget("cancel_be")
                self.w_ok_button.set_sensitive(False)
                progress_button.hide()
                self.w_progressbar.set_pulse_step(0.1)
                self.list_filter = self.be_list.filter_new()
                self.w_be_treeview.set_model(self.list_filter)
                self.__init_tree_views()
                self.active_image = gui_misc.get_icon_pixbuf(
                    self.parent.application_dir, "status_checkmark")
                w_active_gtkimage.set_from_pixbuf(self.active_image)

                bebuffer = self.w_beconfirmation_textview.get_buffer()
                bebuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)

                try:
                        dic = \
                            {
                                "on_cancel_be_clicked": \
                                    self.__on_cancel_be_clicked,
                                "on_ok_be_clicked": \
                                    self.__on_ok_be_clicked,
                                "on_help_bebutton_clicked": \
                                    self.__on_help_bebutton_clicked,
                            }
                        dic_conf = \
                            {
                                "on_cancel_be_conf_clicked": \
                                    self.__on_cancel_be_conf_clicked,
                                "on_ok_be_conf_clicked": \
                                    self.__on_ok_be_conf_clicked,
                                "on_beconfirmationdialog_delete_event": \
                                    self.__on_beconfirmationdialog_delete_event,
                            }            
                        w_tree_beadmin.signal_autoconnect(dic)
                        w_tree_beconfirmation.signal_autoconnect(dic_conf)
                except AttributeError, error:
                        print _("GUI will not respond to any event! %s. "
                            "Check beadmin.py signals") \
                            % error
                Thread(target = self.__progress_pulse).start()
                Thread(target = self.__prepare_beadmin_list).start()
                sel = self.w_be_treeview.get_selection()
                self.w_cancel_button.grab_focus()
                sel.set_mode(gtk.SELECTION_SINGLE)
                self.w_beadmin_dialog.show_all()
                self.w_progress_dialog.set_title(
                    _("Loading Boot Environment Information"))
                self.w_progressinfo_label.set_text(
                    _("Fetching BE entries..."))
                self.w_progress_dialog.show()

        def __progress_pulse(self):
                while not self.progress_stop_thread:
                        gobject.idle_add(self.w_progressbar.pulse)
                        time.sleep(0.1)
                gobject.idle_add(self.w_progress_dialog.hide)

        def __prepare_beadmin_list(self):
                be_list = be.beList()
                gobject.idle_add(self.__create_view_with_be, be_list)
                self.progress_stop_thread = True
                return

        def __init_tree_views(self):
                model = self.w_be_treeview.get_model()

                column = gtk.TreeViewColumn()
                column.set_title("")
                render_pixbuf = gtk.CellRendererPixbuf()
                column.pack_start(render_pixbuf, expand = True)
                column.add_attribute(render_pixbuf, "pixbuf", BE_CURRENT_PIXBUF)
                self.w_be_treeview.append_column(column)

                name_renderer = gtk.CellRendererText()
                name_renderer.connect('edited', self.__be_name_edited, model)
                column = gtk.TreeViewColumn(_("Boot Environment"),
                    name_renderer, text = BE_NAME)
                column.set_cell_data_func(name_renderer, self.__cell_data_function, None)
                column.set_expand(True)
                if "beVerifyBEName" in be.__dict__:
                        column.add_attribute(name_renderer, "editable", 
                            BE_EDITABLE)
                self.w_be_treeview.append_column(column)
                
                datetime_renderer = gtk.CellRendererText()
                datetime_renderer.set_property('xalign', 0.0)
                column = gtk.TreeViewColumn(_("Created"), datetime_renderer,
                    text = BE_DATE_TIME)
                column.set_cell_data_func(datetime_renderer,
                    self.__cell_data_function, None)
                column.set_expand(True)
                self.w_be_treeview.append_column(column)

                size_renderer = gtk.CellRendererText()
                size_renderer.set_property('xalign', 1.0)
                column = gtk.TreeViewColumn(_("Size"), size_renderer,
                    text = BE_SIZE)
                column.set_cell_data_func(size_renderer, self.__cell_data_function, None)
                column.set_expand(False)
                self.w_be_treeview.append_column(column)
              
                radio_renderer = gtk.CellRendererToggle()
                radio_renderer.connect('toggled', self.__active_pane_default, model)
                column = gtk.TreeViewColumn(_("Active on Reboot"),
                    radio_renderer, active = BE_ACTIVE_DEFAULT)
                radio_renderer.set_property("activatable", True)
                radio_renderer.set_property("radio", True)
                column.set_cell_data_func(radio_renderer,
                    self.__cell_data_default_function, None)
                column.set_expand(False)
                self.w_be_treeview.append_column(column)

                toggle_renderer = gtk.CellRendererToggle()
                toggle_renderer.connect('toggled', self.__active_pane_toggle, model)
                column = gtk.TreeViewColumn(_("Delete"), toggle_renderer,
                    active = BE_MARKED)
                toggle_renderer.set_property("activatable", True)
                column.set_cell_data_func(toggle_renderer,
                    self.__cell_data_delete_function, None)
                column.set_expand(False)
                self.w_be_treeview.append_column(column)

        def __on_help_bebutton_clicked(self, widget):
                if self.parent != None:
                        gui_misc.display_help(self.parent.application_dir, "manage_be")
                else:
                        gui_misc.display_help()
                
        def __on_ok_be_clicked(self, widget):
                self.w_progress_dialog.set_title(_("Applying changes"))
                self.w_progressinfo_label.set_text(
                    _("Applying changes, please wait ..."))
                if self.w_ok_button.get_property('sensitive') == 0:
                        self.progress_stop_thread = True
                        self.__on_beadmin_delete_event(None, None)
                        return
                Thread(target = self.__activate).start()
                
        def __on_cancel_be_clicked(self, widget):
                self.__on_beadmin_delete_event(None, None)
                return False

        def __on_beconfirmationdialog_delete_event(self, widget, event):
                self.__on_cancel_be_conf_clicked(widget)
                return True

        def __on_cancel_be_conf_clicked(self, widget):
                self.w_beconfirmation_dialog.hide()

        def __on_ok_be_conf_clicked(self, widget):
                self.w_beconfirmation_dialog.hide()
                self.progress_stop_thread = False
                Thread(target = self.__on_progressdialog_progress).start()
                Thread(target = self.__delete_activate_be).start()
                
        def __on_beadmin_delete_event(self, widget, event, stub=None):
                self.w_beadmin_dialog.destroy()
                return True

        def __activate(self):
                active_text = _("Active on reboot:\n")
                delete_text = _("Delete boot environments:\n")
                rename_text = _("Rename boot environments:\n")
                active = ""
                delete = ""
                rename = {}
                for row in self.be_list:

                        if row[BE_MARKED]:
                                delete += row[BE_NAME] + "\n"
                        if row[BE_ACTIVE_DEFAULT] == True and row[BE_ID] != \
                            self.initial_default:
                                active += row[BE_NAME] + "\n"
                        if row[BE_NAME] != row[BE_ORIG_NAME]:
                                rename[row[BE_ORIG_NAME]] = row[BE_NAME]
                textbuf = self.w_beconfirmation_textview.get_buffer()
                textbuf.set_text("")
                textiter = textbuf.get_end_iter()
                if len(active) > 0:
                        textbuf.insert_with_tags_by_name(textiter,
                            active_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            active)
                if len(delete) > 0:
                        if len(active) > 0:
                                textbuf.insert_with_tags_by_name(textiter,
                                    "\n")                                
                        textbuf.insert_with_tags_by_name(textiter,
                            delete_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            delete)
                if len(rename) > 0:
                        if len(delete) > 0 or len(active) > 0:
                                textbuf.insert_with_tags_by_name(textiter,
                                    "\n")                                
                        textbuf.insert_with_tags_by_name(textiter,
                            rename_text, "bold")
                        for orig in rename:
                                textbuf.insert_with_tags_by_name(textiter,
                                    orig)
                                textbuf.insert_with_tags_by_name(textiter,
                                    _(" to "), "bold")
                                textbuf.insert_with_tags_by_name(textiter,
                                    rename.get(orig) + "\n")
                self.w_cancelbe_button.grab_focus()
                gobject.idle_add(self.w_beconfirmation_dialog.show)
                self.progress_stop_thread = True                

        def __on_progressdialog_progress(self):
                # This needs to be run in gobject.idle_add, otherwise we will get
                # Xlib: unexpected async reply (sequence 0x2db0)!
                gobject.idle_add(self.w_progress_dialog.show)
                while not self.progress_stop_thread:
                        gobject.idle_add(self.w_progressbar.pulse)
                        time.sleep(0.1)
                gobject.idle_add(self.w_progress_dialog.hide)

        def __delete_activate_be(self):
                not_deleted = []
                not_default = None
                not_renamed = {}
		# The while gtk.events_pending():
                #        gtk.main_iteration(False)
		# Is not working if we are calling libbe, so it is required
		# To have sleep in few places in this function
                # Remove
                for row in self.be_list:
                        if row[BE_MARKED]:
				time.sleep(0.1)
                                result = self.__destroy_be(row[BE_NAME])
                                if result != 0:
                                        not_deleted.append(row[BE_NAME])
                # Rename
                for row in self.be_list:
                        if row[BE_NAME] != row[BE_ORIG_NAME]:
				time.sleep(0.1)
                                result = self.__rename_be(row[BE_ORIG_NAME],
                                    row[BE_NAME])
                                if result !=0:
                                        not_renamed[row[BE_ORIG_NAME]] = row[BE_NAME]
                # Set active
                for row in self.be_list:
                        if row[BE_ACTIVE_DEFAULT] == True and row[BE_ID] != \
                            self.initial_default:
				time.sleep(0.1)
                                result = self.__set_default_be(row[BE_NAME])
                                if result != 0:
                                        not_default = row[BE_NAME]
                if len(not_deleted) == 0 and not_default == None \
                    and len(not_renamed) == 0:
                        self.progress_stop_thread = True
                else:
                        self.progress_stop_thread = True
                        msg = ""
                        if not_default:
                                msg += _("<b>Couldn't change Active "
                                    "Boot Environment to:</b>\n") + not_default
                        if len(not_deleted) > 0:
                                if not_default:
                                        msg += "\n\n"
                                msg += _("<b>Couldn't delete Boot "
                                    "Environments:</b>\n")
                                for row in not_deleted:
                                        msg += row + "\n"
                        if len(not_renamed) > 0:
                                if not_default or len(not_deleted):
                                        msg += "\n"
                                msg += _("<b>Couldn't rename Boot "
                                    "Environments:</b>\n")
                                for orig in not_renamed:
                                        msg += _("%s <b>to</b> %s\n") % (orig, 
                                            not_renamed.get(orig))                                
                        gobject.idle_add(self.__error_occured, msg)
                        return
                gobject.idle_add(self.__on_cancel_be_clicked, None)
                                
        def __rename_cell(self, model, itr, new_name):
                model.set_value(itr, BE_NAME, new_name)

        def __rename_be(self, orig_name, new_name):
                return be.beRename(orig_name, new_name)

        def __error_occured(self, error_msg, reset=True):
                msg = error_msg
                msgbox = gtk.MessageDialog(parent = self.w_beadmin_dialog,
                    buttons = gtk.BUTTONS_CLOSE,
                    flags = gtk.DIALOG_MODAL, type = gtk.MESSAGE_ERROR,
                    message_format = None)
                msgbox.set_property('text', msg)
                msgbox.set_title(_("BE error"))
                msgbox.run()
                msgbox.destroy()
                if reset:
                        self.__on_reset_be()

        def __on_reset_be(self):
                self.be_list.clear()
                self.w_progress_dialog.show()
                self.progress_stop_thread = False
                Thread(target = self.__progress_pulse).start()
                Thread(target = self.__prepare_beadmin_list).start()
                self.w_ok_button.set_sensitive(False)

        def __active_pane_toggle(self, cell, filtered_path, filtered_model):
                model = filtered_model.get_model()
                path = filtered_model.convert_path_to_child_path(filtered_path)
                itr = model.get_iter(path)
                if itr:
                        modified = model.get_value(itr, BE_MARKED)
                        # Do not allow to set active if selected for removal
                        model.set_value(itr, BE_MARKED, not modified)
                        # Do not allow to rename if we are removing be.
                        model.set_value(itr, BE_EDITABLE, modified)
                self.__enable_disable_ok()
                
        def __enable_disable_ok(self):
                for row in self.be_list:
                        if row[BE_MARKED] == True:
                                self.w_ok_button.set_sensitive(True)
                                return
                        if row[BE_ID] == self.initial_default:
                                if row[BE_ACTIVE_DEFAULT] == False:
                                        self.w_ok_button.set_sensitive(True)
                                        return
                        if row[BE_NAME] != row[BE_ORIG_NAME]:
                                self.w_ok_button.set_sensitive(True)
                                return
                self.w_ok_button.set_sensitive(False)
                return

        def __be_name_edited(self, cell, filtered_path, new_name, filtered_model):
                model = filtered_model.get_model()
                path = filtered_model.convert_path_to_child_path(filtered_path)
                itr = model.get_iter(path)
                if itr:
                        if model.get_value(itr, BE_NAME) == new_name:
                                return
                        if self.__verify_be_name(new_name) != 0:
                                return
                        self.__rename_cell(model, itr, new_name)
                        self.__enable_disable_ok()                
                        return

        #TBD: Notify user if name clash using same logic as Repo Add and warning text
        def __verify_be_name(self, new_name):
                if be.beVerifyBEName(new_name) != 0:
                        return -1
                for row in self.be_list:
                        if new_name == row[BE_NAME]:
                                return -1
                return 0

        def __active_pane_default(self, cell, filtered_path, filtered_model):
                model = filtered_model.get_model()
                path = filtered_model.convert_path_to_child_path(filtered_path)
                for row in model:
                        row[BE_ACTIVE_DEFAULT] = False
                itr = model.get_iter(path)
                if itr:
                        modified = model.get_value(itr, BE_ACTIVE_DEFAULT)
                        model.set_value(itr, BE_ACTIVE_DEFAULT, not modified)
                        self.__enable_disable_ok()

        def __create_view_with_be(self, be_list):
                dates = None
                i = 0
                j = 0
                error_code = None
                be_list_loop = None
                if len(be_list) > 1 and type(be_list[0]) == type(-1):
                        error_code = be_list[0]
                if error_code != None and error_code == 0:
                        be_list_loop = be_list[1]
                elif error_code != None and error_code != 0:
                        msg = _("The <b>libbe</b> library couldn't  "
                            "prepare list of Boot Environments."
                            "\nAll functions for managing Boot Environments are disabled")
                        self.__error_occured(msg, False)
                        return
                else:
                        be_list_loop = be_list

                for bee in be_list_loop:
                        if bee.get("orig_be_name"):
                                name = bee.get("orig_be_name")
                                active = bee.get("active")
                                active_boot = bee.get("active_boot")
                                be_size = bee.get("space_used")
                                be_date = bee.get("date")
                                converted_size = \
                                    self.__convert_size_of_be_to_string(be_size)
                                active_img = None
                                if not be_date and j == 0:
                                        dates = self.__get_dates_of_creation(be_list_loop)
                                if dates:
                                        try:
                                                date_time = repr(dates[i])[1:-3]
                                                date_tmp = time.strptime(date_time, \
                                                    "%a %b %d %H:%M %Y")
                                                date_tmp2 = \
                                                        datetime.datetime(*date_tmp[0:5])
                                                try:
                                                        date_format = \
                                                        unicode(
                                                            _("%m/%d/%y %H:%M"),
                                                            "utf-8").encode(
                                                            locale.getpreferredencoding())
                                                except (UnicodeError, LookupError,
                                                    locale.Error):
                                                        date_format = "%F %H:%M"
                                                date_time = \
                                                    date_tmp2.strftime(date_format)
                                                i += 1
                                        except (NameError, ValueError, TypeError):
                                                date_time = None
                                else:
                                        date_tmp = time.localtime(be_date)
                                        try:
                                                date_format = \
                                                    unicode(
                                                        _("%m/%d/%y %H:%M"),
                                                        "utf-8").encode(
                                                        locale.getpreferredencoding())
                                        except (UnicodeError, LookupError, locale.Error):
                                                date_format = "%F %H:%M"
                                        date_time = \
                                            time.strftime(date_format, date_tmp)
                                if active:
                                        active_img = self.active_image
                                        self.initial_active = j
                                if active_boot:
                                        self.initial_default = j
                                if date_time != None:
                                        try:
                                                date_time = unicode(date_time,
                                                locale.getpreferredencoding()).encode(
                                                        "utf-8")
                                        except (UnicodeError, LookupError, locale.Error):
                                                pass 
                                self.be_list.insert(j, [j, False,
                                    name, name,
                                    date_time, active_img,
                                    active_boot, converted_size, active_img == None])
                                j += 1
                self.w_be_treeview.set_cursor(self.initial_active, None,
                    start_editing=True)
                self.w_be_treeview.scroll_to_cell(self.initial_active)

        def __destroy_be(self, be_name):
                return be.beDestroy(be_name, 1, True)

        def __set_default_be(self, be_name):
                return be.beActivate(be_name)

        def __cell_data_default_function(self, column, renderer, model, itr, data):
                if itr:
                        if model.get_value(itr, BE_MARKED):
                                self.__set_renderer_active(renderer, False)
                        else:
                                self.__set_renderer_active(renderer, True)
                                
        def __cell_data_delete_function(self, column, renderer, model, itr, data):
                if itr:
                        if model.get_value(itr, BE_ACTIVE_DEFAULT) or \
                            (self.initial_active == model.get_value(itr, BE_ID)) or \
                            (model.get_value(itr, BE_NAME) !=
                            model.get_value(itr, BE_ORIG_NAME)):
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

        @staticmethod
        def __get_dates_of_creation(be_list):
                #zfs list -H -o creation rpool/ROOT/opensolaris-1
                cmd = [ "/sbin/zfs", "list", "-H", "-o","creation" ]
                for bee in be_list:
                        if bee.get("orig_be_name"):
                                name = bee.get("orig_be_name")
                                pool = bee.get("orig_be_pool")
                                cmd += [pool+"/ROOT/"+name]
                if len(cmd) <= 5:
                        return None
                list_of_dates = []
                try:
                        proc = subprocess.Popen(cmd, stdout = subprocess.PIPE,
                            stderr = subprocess.PIPE,)
                        line_out = proc.stdout.readline()
                        while line_out:
                                list_of_dates.append(line_out)
                                line_out =  proc.stdout.readline()
                except OSError:
                        return list_of_dates
                return list_of_dates

        @staticmethod
        def __convert_size_of_be_to_string(be_size):
                if not be_size:
                        be_size = 0
                return pkg.misc.bytes_to_str(be_size)

        @staticmethod
        def __cell_data_function(column, renderer, model, itr, data):
                if itr:
                        if model.get_value(itr, BE_CURRENT_PIXBUF):
                                renderer.set_property("weight", pango.WEIGHT_BOLD)
                        else:
                                renderer.set_property("weight", pango.WEIGHT_NORMAL)
