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
BE_DATE_TIME,
BE_CURRENT_PIXBUF,
BE_ACTIVE_DEFAULT,
BE_SIZE
) = range(7)

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
                        gobject.TYPE_STRING,      # BE_DATE_TIME
                        gtk.gdk.Pixbuf,           # BE_CURRENT_PIXBUF
                        gobject.TYPE_BOOLEAN,     # BE_ACTIVE_DEFAULT
                        gobject.TYPE_STRING,      # BE_SIZE
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
                self.w_reset_button = w_tree_beadmin.get_widget("resetbebutton")
                w_active_gtkimage = w_tree_beadmin.get_widget("activebeimage")
                self.w_progress_dialog = w_tree_progress.get_widget("progressdialog")
                self.w_progressinfo_label = w_tree_progress.get_widget("progressinfo")
                progress_button = w_tree_progress.get_widget("progresscancel")
                self.w_progressbar = w_tree_progress.get_widget("progressbar")
                self.w_beconfirmation_dialog =  \
                    w_tree_beconfirmation.get_widget("beconfirmationdialog")
                self.w_beconfirmation_treeview = \
                    w_tree_beconfirmation.get_widget("beconfirmtreeview")
                self.w_beconfirmationdefault_label = \
                    w_tree_beconfirmation.get_widget("beconfirmationdefault")
                self.w_beconfirmationsummary_label = \
                    w_tree_beconfirmation.get_widget("beconfirmationsummary")
                self.w_cancelbe_button = w_tree_beconfirmation.get_widget("cancel_be")
                progress_button.hide()
                self.w_progressbar.set_pulse_step(0.1)
                self.list_filter = self.be_list.filter_new()
                self.w_be_treeview.set_model(self.list_filter)
                self.__init_tree_views()
                treestore = gtk.ListStore(gobject.TYPE_STRING)
                self.w_beconfirmation_treeview.set_model(treestore)
                cell = gtk.CellRendererText()
                be_column = gtk.TreeViewColumn('BE', cell, text = BE_ID)
                self.w_beconfirmation_treeview.append_column(be_column)
                self.active_image = gui_misc.get_icon_pixbuf(
                    self.parent.application_dir, "status_checkmark")
                w_active_gtkimage.set_from_pixbuf(self.active_image)

                try:
                        dic = \
                            {
                                "on_cancel_be_clicked": \
                                    self.__on_cancel_be_clicked,
                                "on_reset_be_clicked": \
                                    self.__on_reset_be_clicked,
                                "on_ok_be_clicked": \
                                    self.__on_ok_be_clicked,
                            }
                        dic_conf = \
                            {
                                "on_cancel_be_conf_clicked": \
                                    self.__on_cancel_be_conf_clicked,
                                "on_ok_be_conf_clicked": \
                                    self.__on_ok_be_conf_clicked,
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
                sel.set_mode(gtk.SELECTION_NONE)
                sel = self.w_beconfirmation_treeview.get_selection()
                sel.set_mode(gtk.SELECTION_NONE)
                self.w_beadmin_dialog.show_all()
                self.w_progress_dialog.set_title(
                    _("Loading Boot Environment Information"))
                self.w_progressinfo_label.set_text(
                    _("Fetching BE entries..."))
                self.be_destroy_supports_capital_f = \
                    self.__check_if_be_supports_capital_f()
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
                column = gtk.TreeViewColumn(_("Boot Environment"),
                    name_renderer, text = BE_NAME)
                column.set_cell_data_func(name_renderer, self.__cell_data_function, None)
                column.set_expand(True)
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

        def __on_reset_be_clicked(self, widget):
                self.be_list.clear()
                self.w_progress_dialog.show()
                self.progress_stop_thread = False
                Thread(target = self.__progress_pulse).start()
                Thread(target = self.__prepare_beadmin_list).start()
                self.__enable_disable_reset()

        def __on_ok_be_clicked(self, widget):
                self.w_progress_dialog.set_title(_("Applying changes"))
                self.w_progressinfo_label.set_text(
                    _("Applying changes, please wait ..."))
                if self.w_reset_button.get_property('sensitive') == 0:
                        self.progress_stop_thread = True
                        self.__on_beadmin_delete_event(None, None)
                        return
                Thread(target = self.__activate).start()
                
        def __on_cancel_be_clicked(self, widget):
                self.__on_beadmin_delete_event(None, None)

        def __on_cancel_be_conf_clicked(self, widget):
                self.w_beconfirmation_dialog.hide()

        def __on_ok_be_conf_clicked(self, widget):
                self.w_beconfirmation_dialog.hide()
                self.progress_stop_thread = False
                Thread(target = self.__on_progressdialog_progress).start()
                Thread(target = self.__delete_activate_be).start()

        def __on_beadmin_delete_event(self, widget, event):
                self.w_beadmin_dialog.destroy()
                return True

        def __activate(self):
                default = None
                treestore = self.w_beconfirmation_treeview.get_model()
                treestore.clear()
                first = True
                for row in self.be_list:
                        if row[BE_MARKED]:
                                treestore.append([row[BE_NAME]])
                                if first:
                                        self.w_beconfirmation_treeview.set_sensitive(True)
                                        first = False
                        if row[BE_ACTIVE_DEFAULT] == True and row[BE_ID] != \
                            self.initial_default:
                                default = row[BE_NAME]
                summary_text = ""
                be_change_no = len(treestore)
                if  be_change_no == 0:
                        treestore.append([_("No change")])
                        self.w_beconfirmation_treeview.set_sensitive(False)
                else:
                        summary_text += \
                            _("%d BE's will be deleted") % be_change_no

                if default:
                        self.w_beconfirmationdefault_label.set_text(default+"\n")
                        self.w_beconfirmationdefault_label.set_sensitive(True)
                        if be_change_no > 0:
                                summary_text += "\n"
                        summary_text += \
                            _("The Active BE will be changed upon reboot")
                else:
                        self.w_beconfirmationdefault_label.set_sensitive(False)
                        self.w_beconfirmationdefault_label.set_text(
                            _("No change\n"))
                self.w_beconfirmationsummary_label.set_text(summary_text)
                self.w_beconfirmation_treeview.expand_all()
                self.w_cancelbe_button.grab_focus()
                self.w_beconfirmation_dialog.show()
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
                for row in self.be_list:
                        if row[BE_MARKED]:
                                succeed = self.__destroy_be(row[BE_NAME])
                                if succeed == 1:
                                        not_deleted.append(row[BE_NAME])
                for row in self.be_list:
                        if row[BE_ACTIVE_DEFAULT] == True and row[BE_ID] != \
                            self.initial_default:
                                succeed = self.__set_default_be(row[BE_NAME])
                                if succeed == 1:
                                        not_default = row[BE_NAME]
                if len(not_deleted) == 0 and not_default == None:
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
                        gobject.idle_add(self.__error_occured, msg)
                        return
                self.__on_beadmin_delete_event(None, None)
                                
        def __error_occured(self, error_msg, reset=True):
                msg = error_msg
                msgbox = gtk.MessageDialog(parent = self.w_beadmin_dialog,
                    buttons = gtk.BUTTONS_CLOSE,
                    flags = gtk.DIALOG_MODAL, type = gtk.MESSAGE_ERROR,
                    message_format = None)
                msgbox.set_markup(msg)
                msgbox.set_title(_("BE error"))
                msgbox.run()
                msgbox.destroy()
                if reset:
                        self.__on_reset_be_clicked(None)

        def __active_pane_toggle(self, cell, filtered_path, filtered_model):
                model = filtered_model.get_model()
                path = filtered_model.convert_path_to_child_path(filtered_path)
                itr = model.get_iter(path)
                if itr:
                        modified = model.get_value(itr, BE_MARKED)
                        model.set_value(itr, BE_MARKED, not modified)
                self.__enable_disable_reset()
                
        def __enable_disable_reset(self):
                for row in self.be_list:
                        if row[BE_MARKED] == True:
                                self.w_reset_button.set_sensitive(True)
                                return
                        if row[BE_ID] == self.initial_default:
                                if row[BE_ACTIVE_DEFAULT] == False:
                                        self.w_reset_button.set_sensitive(True)
                                        return
                self.w_reset_button.set_sensitive(False)
                return                

        def __active_pane_default(self, cell, filtered_path, filtered_model):
                model = filtered_model.get_model()
                path = filtered_model.convert_path_to_child_path(filtered_path)
                for row in model:
                        row[BE_ACTIVE_DEFAULT] = False
                itr = model.get_iter(path)
                if itr:
                        modified = model.get_value(itr, BE_ACTIVE_DEFAULT)
                        model.set_value(itr, BE_ACTIVE_DEFAULT, not modified)
                        self.__enable_disable_reset()

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
                                                except (UnicodeError, LookupError):
                                                        print _(
                                                        "Error conversion from UTF-8 " \
                                                        "to %s.") \
                                                        % locale.getpreferredencoding()
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
                                        except (UnicodeError, LookupError):
                                                print _(
                                                "Error conversion from UTF-8 to %s.") \
                                                % locale.getpreferredencoding()
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
                                        except (UnicodeError, LookupError):
                                                print _(
                                                "Error conversion from %s to UTF-8.") \
                                                % locale.getpreferredencoding()
                                self.be_list.insert(j, [j, False,
                                    name,
                                    date_time, active_img,
                                    active_boot, converted_size])
                                j += 1
                self.w_be_treeview.set_cursor(self.initial_active, None,
                    start_editing=True)
                self.w_be_treeview.scroll_to_cell(self.initial_active)

        def __destroy_be(self, be_name):
                cmd = [ "/sbin/beadm", "destroy", "-F", be_name ]
                if not self.be_destroy_supports_capital_f:
                        cmd = [ "/sbin/beadm", "destroy", "-f", be_name ]
                return self.__beadm_invoke_command(cmd)

        def __set_default_be(self, be_name):
                cmd = [ "/sbin/beadm", "activate", be_name ]
                return self.__beadm_invoke_command(cmd)

        def __cell_data_default_function(self, column, renderer, model, itr, data):
                if itr:
                        if model.get_value(itr, BE_MARKED):
                                self.__set_renderer_active(renderer, False)
                        else:
                                self.__set_renderer_active(renderer, True)
                                
        def __cell_data_delete_function(self, column, renderer, model, itr, data):
                if itr:
                        if model.get_value(itr, BE_ACTIVE_DEFAULT) or \
                            (self.initial_active == model.get_value(itr, BE_ID)):
                                self.__set_renderer_active(renderer, False)
                        else:
                                self.__set_renderer_active(renderer, True)

        @staticmethod
        def __beadm_invoke_command(cmd):
                try:
                        # Subprocess platform specific, but beadm is only on Solars so we 
                        # can use it...
                        stdouterr = open('/dev/null', 'w')
                        returncode = subprocess.call(cmd, stdout = stdouterr, \
                            stderr = stdouterr,)
                except OSError:
                        returncode = 1
                return returncode

        @staticmethod
        def __check_if_be_supports_capital_f():
                '''The beadmin command changed arguments and before build 86 to supress
                the prompt back for the destroy operation we had to used -f instead of
                -F. This function should return True only when the old beadm is used.'''
                supports_capital_f = True
                try:
                        cmd = [ "/sbin/beadm" ]
                        stdout = open('/dev/null', 'w')
                        stderr = subprocess.Popen(cmd, stdout = stdout, \
                            stderr=subprocess.PIPE).stderr
                        out = stderr.read().split('\n')
                        for line in out:
                                if "beadm destroy" in line:
                                        if "[-f]" in line:
                                                supports_capital_f = False
                except OSError:
                        return supports_capital_f
                return supports_capital_f
                
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
