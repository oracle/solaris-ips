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

PKG_CLIENT_NAME = "packagemanager"

import locale
import os
import sys
import gettext
try:
        import gobject
        import gtk
        import pango
except ImportError:
        sys.exit(1)
import pkg.misc as misc
import pkg.gui.misc as gui_misc
import pkg.client.progress as progress
import pkg.client.api_errors as api_errors
import pkg.client.api as api
import pkg.gui.installupdate as installupdate
import pkg.gui.enumerations as enumerations
import pkg.gui.repository as repository
from pkg.client import global_settings
import pkg.client.publisher as publisher
        
CLIENT_API_VERSION = gui_misc.get_client_api_version()

debug = False

class Webinstall:
        def __init__(self, image_dir):
                global_settings.client_name = PKG_CLIENT_NAME
                self.image_dir = image_dir
    
                try:
                        self.application_dir = os.environ["PACKAGE_MANAGER_ROOT"]
                except KeyError:
                        self.application_dir = "/"
                misc.setlocale(locale.LC_ALL, "")
                for module in (gettext, gtk.glade):
                        module.bindtextdomain("pkg", self.application_dir +
                            "/usr/share/locale")
                        module.textdomain("pkg")
                self.pub_pkg_list = None
                self.pr = progress.NullProgressTracker()
                self.pub_new_tasks = []
                self.pkg_install_tasks = []
                self.param = None
                self.preferred = None
                
                # Webinstall Dialog
                self.gladefile = self.application_dir + \
                        "/usr/share/package-manager/packagemanager.glade"
                w_xmltree_webinstall = gtk.glade.XML(self.gladefile, "webinstalldialog")
                self.w_webinstall_dialog = \
                        w_xmltree_webinstall.get_widget("webinstalldialog")
                
                self.w_webinstall_proceed = \
                        w_xmltree_webinstall.get_widget("proceed_button")
                self.w_webinstall_cancel = \
                        w_xmltree_webinstall.get_widget("cancel_button")
                self.w_webinstall_close = \
                        w_xmltree_webinstall.get_widget("close_button")
                self.w_webinstall_proceed_label = \
                        w_xmltree_webinstall.get_widget("proceed_new_repo_label")
                self.w_webinstall_info_label = \
                        w_xmltree_webinstall.get_widget("label19")

                self.w_webinstall_textview = \
                        w_xmltree_webinstall.get_widget("webinstall_textview")  
                infobuffer = self.w_webinstall_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)

                try:
                        dic = \
                            {
                                "on_webinstalldialog_close": \
                                    self.__on_webinstall_dialog_close,
                                "on_cancel_button_clicked": \
                                    self.__on_cancel_button_clicked,
                                "on_help_button_clicked": \
                                    self.__on_help_button_clicked,
                                "on_proceed_button_clicked": \
                                    self.__on_proceed_button_clicked,
                            }
                        w_xmltree_webinstall.signal_autoconnect(dic)


                except AttributeError, error:
                        print _("GUI will not respond to any event! %s. "
                            "Check webinstall.py signals") % error
 
                self.w_webinstall_dialog.show_all()
                self.w_webinstall_dialog.set_icon(
                    gui_misc.get_app_pixbuf(self.application_dir,"PM_app_48x"))
                self.api_o = self.__get_api_object(self.image_dir, self.pr)
        
        def __output_new_pub_tasks(self, infobuffer, textiter, num_tasks):
                if num_tasks == 0:
                        return                                        
                if num_tasks == 1:
                        infobuffer.insert_with_tags_by_name(textiter,
                            _("\n Add New Repository\n"), "bold")
                else:
                        infobuffer.insert_with_tags_by_name(textiter,
                            _("\n Add New Repositories\n"), "bold")
                self.__output_pub_tasks(infobuffer, textiter, self.pub_new_tasks)

        def __nothing_todo(self, infobuffer, textiter):
                self.w_webinstall_proceed.hide()
                self.w_webinstall_cancel.hide()
                self.w_webinstall_close.show()

                infobuffer.insert(textiter,
                    _("\n All specified repositories and packages are already on the "
                    "system.\n"))

        @staticmethod
        def __output_pub_tasks(infobuffer, textiter, pub_tasks):
                for pub_info in pub_tasks:
                        if pub_info == None:
                                continue
                        infobuffer.insert_with_tags_by_name(textiter,
                            _("\t%s ") % pub_info.prefix, "bold")
                        repo = pub_info.selected_repository
                        if repo != None:
                                infobuffer.insert(textiter,
                                        _(" (%s)\n") % repo.origins[0].uri)

        def __output_pkg_install_tasks(self, infobuffer, textiter, num_tasks):
                if num_tasks == 0:
                        return                        
                infobuffer.insert_with_tags_by_name(textiter, _("\n Install Packages\n"),
                    "bold")
                for entry in self.pkg_install_tasks:
                        pub_info = entry[0]
                        packages = entry[1]
                        if len(packages) > 0:
                                for pkg in packages:
                                        infobuffer.insert_with_tags_by_name(textiter,
                                            _("\t%s: ")
                                            % pub_info.prefix, "bold")
                                        infobuffer.insert(textiter,
                                            _("%s\n") % pkg)
                        
        def process_param(self, param=None):
                if param == None or self.api_o == None:
                        self.w_webinstall_proceed.set_sensitive(False)
                        return
                self.param = param
                self.pub_pkg_list = self.api_parse_publisher_info(param)
                if self.pub_pkg_list == None:
                        self.w_webinstall_proceed.set_sensitive(False)
                        return
                self.__create_task_lists()        
                infobuffer = self.w_webinstall_textview.get_buffer()
                infobuffer.set_text("")
                
                num_new_pub = len(self.pub_new_tasks)
                num_install_tasks = len(self.pkg_install_tasks)

                self.__set_proceed_label(num_new_pub)
                textiter = infobuffer.get_end_iter()
                if num_new_pub == 0 and num_install_tasks == 0:
                        self.__nothing_todo(infobuffer, textiter)
                        self.w_webinstall_proceed.set_sensitive(False)
                        self.w_webinstall_cancel.grab_focus()
                        self.w_webinstall_info_label.hide()
                        return
                        
                self.__output_new_pub_tasks(infobuffer, textiter, num_new_pub)
                self.__output_pkg_install_tasks(infobuffer, textiter, num_install_tasks)

                infobuffer.place_cursor(infobuffer.get_start_iter())
                self.w_webinstall_proceed.grab_focus()
                                
        def __set_proceed_label(self, num_new_pub):
                if num_new_pub == 0:
                        self.w_webinstall_proceed_label.hide()
                else:
                        if num_new_pub == 1:
                                self.w_webinstall_proceed_label.set_text(
                                    _("Proceed only if you trust this new repository "))
                        else:
                                self.w_webinstall_proceed_label.set_text(
                                    _("Proceed only if you trust these new repositories"))

        def __on_webinstall_dialog_close(self, widget, param=None):
                self.__exit_app()

        def __on_cancel_button_clicked(self, widget):
                self.__exit_app()

        def __on_help_button_clicked(self, widget):
                gui_misc.display_help(self.application_dir, "webinstall")

        def __exit_app(self, be_name = None):
                self.w_webinstall_dialog.destroy()
                gtk.main_quit()
                sys.exit(0)
                return

        def __create_task_lists(self):
                pub_new_reg_ssl_tasks = []
                self.pub_new_tasks = []
                self.pkg_install_tasks = []
                for entry in self.pub_pkg_list:
                        pub_info = entry[0]
                        packages = entry[1]
                        if not pub_info:
                                # TBD: For nowe we are skipping p5i files which contains
                                # only pkg names and not publisher information
                                continue

                        repo = pub_info.repositories

                        if not self.__is_publisher_registered(pub_info.prefix):
                                if len(repo) > 0 and repo[0].origins[0] != None and \
                                    repo[0].origins[0].scheme == "https":
                                        #TBD: check for registration uri as well as scheme
                                        #    repo.registration_uri.uri != None:
                                        pub_new_reg_ssl_tasks.append(pub_info)
                                else:
                                        self.pub_new_tasks.append(pub_info)
                        if packages != None and len(packages) > 0:
                                self.pkg_install_tasks.append((pub_info, packages))
                self.pub_new_tasks = pub_new_reg_ssl_tasks + self.pub_new_tasks
                        
        def __is_publisher_registered(self, name):
                try:
                        if self.api_o != None and self.api_o.has_publisher(name):
                                return True
                except api_errors.PublisherError, ex:
                        gobject.idle_add(self.__error_occurred, self.w_webinstall_dialog, 
                            str(ex), gtk.MESSAGE_ERROR, _("Repository Error"))
                return False

        def __on_proceed_button_clicked(self, widget):
                self.w_webinstall_proceed.set_sensitive(False)
                self.__create_task_lists()
                if len(self.pub_new_tasks) > 0:
                        self.__add_new_pub()
                        return
                if len(self.pkg_install_tasks) > 0:
                        self.__install_pkgs()
                        return
                        
        def __add_new_pub(self):
                if len(self.pub_new_tasks) == 0:
                        return
                pub = self.pub_new_tasks.pop(0)
                if debug:
                        print("Add New Publisher:\n\tName: %s" % pub.prefix)
                        repo = pub.selected_repository
                        print("\tURL: %s" % repo.origins[0].uri)
                        
                repo_gui = repository.Repository(self, True)
                repo_gui.webinstall_new_pub(self.w_webinstall_dialog, pub)

        # Publisher Callback - invoked at end of adding publisher
        def reload_packages(self):
                if len(self.pub_new_tasks) > 0:
                        self.__add_new_pub()
                        return
                elif len(self.pkg_install_tasks) > 0:
                        self.__install_pkgs()
                else:
                        self.__exit_app()
                
        def __install_pkgs(self):
                if len(self.pkg_install_tasks) == 0:
                        return
                # Handle all packages from all pubs as single install action
                pref_pub = self.api_o.get_preferred_publisher()
                self.preferred = pref_pub.prefix
                all_package_stems = []        
                for pkg_installs in self.pkg_install_tasks:
                        pub_info = pkg_installs[0]
                        packages = pkg_installs[1]
                        pub_pkg_stems = self.process_pkg_stems(pub_info, packages)
                        for pkg in pub_pkg_stems:
                                all_package_stems.append(pkg)
                self.pkg_install_tasks = []

                if debug:
                        print "Install Packages: %s" % all_package_stems
                
                #TBD: Having to get new api object, self.api_o.reset() is not working
                self.api_o = self.__get_api_object(self.image_dir, self.pr)
                installupdate.InstallUpdate(all_package_stems, self, self.api_o, 
                    action = enumerations.INSTALL_UPDATE,
                    parent_name = _("Package Manager"),
                    main_window = self.w_webinstall_dialog,
                    icon_confirm_dialog = gui_misc.get_app_pixbuf(
                        self.application_dir,"PM_package_36x"),
                    web_install = True)

        def process_pkg_stems(self, pub_info, packages):
                if not self.__is_publisher_registered(pub_info.prefix):
                        return []
                if pub_info.prefix == self.preferred:
                        pkg_stem = "pkg:/"
                else:
                        pkg_stem = "pkg://" + pub_info.prefix + "/"
                packages_with_stem = []
                for pkg in packages:
                        packages_with_stem.append(pkg_stem + pkg)
                return packages_with_stem
       
        # Install Callback - invoked at end of installing packages
        def update_package_list(self, update_list):
                self.__exit_app()

        def __get_api_object(self, img_dir, progtrack):
                api_o = None
                try:
                        api_o = api.ImageInterface(img_dir,
                            CLIENT_API_VERSION,
                            progtrack, None, PKG_CLIENT_NAME)
                except (api_errors.VersionException,\
                    api_errors.ImageNotFoundException), ex:
                        gobject.idle_add(self.__error_occurred, self.w_webinstall_dialog, 
                            str(ex), gtk.MESSAGE_ERROR, _("API Error"))
                return api_o

        # TBD: Move generic error handling into gui misc module and reuse across modules
        @staticmethod
        def __error_occurred(parent, error_msg, msg_type=gtk.MESSAGE_ERROR, 
                title = None):
                msgbox = gtk.MessageDialog(parent =
                    parent,
                    buttons = gtk.BUTTONS_CLOSE,
                    flags = gtk.DIALOG_MODAL,
                    type = msg_type,
                    message_format = None)
                msgbox.set_markup(error_msg)
                if title != None:
                        msgbox.set_title(title)
                else:
                        msgbox.set_title(_("Error"))
                        
                msgbox.run()
                msgbox.destroy()

        def api_parse_publisher_info(self, param=None):
                '''<path to mimetype file|origin_url>
                   returns list of publisher and package list tuples'''
                p5i_info = None
                file_obj = None
                if self.param.endswith(".p5i"):                
                        try:
                                file_obj = open(self.param)
                                p5i_info = self.api_o.parse_p5i(file_obj)
                                file_obj.close()
                        except (api_errors.InvalidP5IFile, 
                                api_errors.InvalidResourceLocation,
                                api_errors.RetrievalError,
                                api_errors.UnsupportedP5IFile,
                                api_errors.PublisherError), ex:
                                self.w_webinstall_proceed.set_sensitive(False)
                                self.__error_occurred( 
                                    self.w_webinstall_dialog,
                                    str(ex), gtk.MESSAGE_ERROR, _("Repository Error"))
                                file_obj.close()
                                return None
                        except IOError:
                                if file_obj != None:
                                        file_obj.close()
                                self.w_webinstall_proceed.set_sensitive(False)
                                msg = _("Error reading the p5i file.")
                                self.__error_occurred(
                                    self.w_webinstall_dialog,
                                    msg, gtk.MESSAGE_ERROR, _("Repository Error"))                        
                                return None
                else:
                        self.w_webinstall_proceed.set_sensitive(False)
                        return None
                return p5i_info
