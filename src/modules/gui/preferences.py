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
# Copyright (c) 2010, 2013, Oracle and/or its affiliates. All rights reserved.
#

import g11nsvc as g11nsvc
import re
import sys
try:
        import gobject
        gobject.threads_init()
        import gtk
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)
import pkg.client.api_errors as api_errors
import pkg.client.api as api
import pkg.gui.misc as gui_misc
import pkg.gui.enumerations as enumerations

PREFERENCES_NOTEBOOK_GENERAL_PAGE = 0
PREFERENCES_NOTEBOOK_SIG_POL_PAGE = 1
PREFERENCES_NOTEBOOK_LANGUAGES_PAGE = 2
GDK_2BUTTON_PRESS = 5     # gtk.gdk._2BUTTON_PRESS causes pylint warning
LOCALE_PREFIX = "facet.locale."
LANG_STAR_SUFFIX = "_*"

ALL_LOCALES = "facet.locale.*"
ALL_DEVEL = "facet.devel"
ALL_DOC = "facet.doc.*"

LANG_MATCH = re.compile(r'facet\.locale\.([a-z]{2,3})$')
LANG_STAR_MATCH = re.compile(r'facet\.locale\.([a-z]{2,3})_\*$')
LOCALE_MATCH = re.compile(r'facet\.locale\.([a-z]{2,3}_[A-Z]{2,3}.*$)')

SYSTEM_G11LOCALE_MATCH = re.compile(r'^([a-z]{2,3}_[A-Z]{2,3})\.*(.*)$')
SYSTEM_FACETLOCALE_MATCH = re.compile(r'([a-z]{2,3}_[A-Z]{2,3})\(*(.*?)\)*$')

debug = False

class Preferences:
        def __init__(self, parent, builder, window_icon, gconf):
                self.gconf = gconf
                self.parent = parent
                self.w_preferencesdialog = \
                    builder.get_object("preferencesdialog")
                self.w_preferencesdialog.set_icon(window_icon)
                w_startup_label = \
                    builder.get_object("startup_label")
                w_startup_label.hide()
                w_startup_hbox =  \
                    builder.get_object("startup_hbox")
                w_startup_hbox.hide()
                self.w_startpage_checkbutton = \
                    builder.get_object("startpage_checkbutton")
                self.w_exit_checkbutton = \
                    builder.get_object("exit_checkbutton")
                self.w_confirm_updateall_checkbutton = \
                    builder.get_object("confirm_updateall_checkbutton")
                self.w_confirm_install_checkbutton = \
                    builder.get_object("confirm_install_checkbutton")
                self.w_confirm_remove_checkbutton = \
                    builder.get_object("confirm_remove_checkbutton")
                self.w_help_button = builder.get_object("preferenceshelp")
                self.w_close_button = builder.get_object("preferencesclose")
                self.w_cancel_button = builder.get_object("preferencescancel")
                self.w_languages_all_radiobutton = \
                    builder.get_object("lang_install_all_radiobutton")
                self.w_languages_only_radiobutton = \
                    builder.get_object("lang_install_only_radiobutton")
                self.w_feature_devel_checkbutton = \
                    builder.get_object("feature_devel_checkbutton")
                self.w_feature_doc_checkbutton = \
                    builder.get_object("feature_doc_checkbutton")

                self.w_locales_treeview = \
                    builder.get_object("languages_treeview")
                self.w_preferences_notebook = builder.get_object(
                        "preferences_notebook")
                self.w_languages_treeview = builder.get_object(
                        "languages_treeview")

                self.w_gsig_ignored_radiobutton =  builder.get_object(
                    "gsig_ignored_radiobutton")
                self.w_gsig_optional_radiobutton =  builder.get_object(
                    "gsig_optional_but_valid_radiobutton")
                self.w_gsig_valid_radiobutton =  builder.get_object(
                    "gsig_valid_radiobutton")
                self.w_gsig_name_radiobutton =  builder.get_object(
                    "gsig_name_radiobutton")
                self.w_gsig_name_entry =  builder.get_object(
                    "gsig_name_entry")
                self.w_gsig_cert_names_vbox =  builder.get_object(
                    "gsig_cert_names_vbox")

                self.orig_gsig_policy = None

                self.watch = gtk.gdk.Cursor(gtk.gdk.WATCH)
                self.orig_lang_locale_count_dict = {}
                self.orig_facets_dict = {}
                self.orig_facet_lang_dict = {}
                self.orig_facet_lang_star_dict = {}
                self.orig_facet_locale_dict = {}
                self.facet_g11_locales_dict = {}
                self.facetlocales_list = []
                self.facets_to_set = {}
                self.locales_setup = False
                self.locales_treeview_selection = []
                self.locales_list = self.__get_locales_liststore()
                self.__init_locales_tree_view(self.locales_list)
                self.__init_locales_list()

        def show_signature_policy(self):
                self.w_preferences_notebook.set_current_page(
                    PREFERENCES_NOTEBOOK_SIG_POL_PAGE)
                self.w_preferencesdialog.show()

        def set_window_icon(self, window_icon):
                self.w_preferencesdialog.set_icon(window_icon)

        def setup_signals(self):
                signals_table = [
                    (self.w_preferencesdialog, "show",
                     self.__on_preferencesdialog_show),
                    (self.w_preferencesdialog, "delete_event",
                     self.__on_preferencesdialog_delete_event),
                    (self.w_help_button, "clicked",
                     self.__on_preferenceshelp_clicked),
                    (self.w_close_button, "clicked",
                     self.__on_preferencesclose_clicked),
                    (self.w_cancel_button, "clicked",
                     self.__on_preferencescancel_clicked),
                    (self.w_languages_all_radiobutton, "toggled",
                     self.__on_languages_all_radiobutton_toggled),
                    (self.w_preferences_notebook, "switch_page",
                     self.__on_notebook_change),
                    (self.w_languages_treeview, "button_press_event",
                     self.__on_languages_treeview_button_and_key_events),
                    (self.w_languages_treeview, "key_press_event",
                     self.__on_languages_treeview_button_and_key_events),

                    (self.w_gsig_ignored_radiobutton, "toggled",
                        self.__on_gsig_radiobutton_toggled),
                    (self.w_gsig_optional_radiobutton, "toggled",
                        self.__on_gsig_radiobutton_toggled),
                    (self.w_gsig_valid_radiobutton, "toggled",
                        self.__on_gsig_radiobutton_toggled),
                    (self.w_gsig_name_radiobutton, "toggled",
                        self.__on_gsig_radiobutton_toggled),
                     ]
                for widget, signal_name, callback in signals_table:
                        widget.connect(signal_name, callback)

        def __on_gsig_radiobutton_toggled(self, widget):
                self.w_gsig_cert_names_vbox.set_sensitive(
                    self.w_gsig_name_radiobutton.get_active())

        def __update_img_sig_policy_prop(self, set_props):
                try:
                        self.parent.get_api_object().img.set_properties(set_props)
                except api_errors.ApiException, e:
                        error_msg = str(e)
                        msg_title = _("Preferences Error")
                        msg_type = gtk.MESSAGE_ERROR
                        gui_misc.error_occurred(None, error_msg, msg_title, msg_type)
                        return False
                return True

        def __update_img_sig_policy(self):
                orig = self.orig_gsig_policy
                ignore = self.w_gsig_ignored_radiobutton.get_active()
                verify = self.w_gsig_optional_radiobutton.get_active()
                req_sigs = self.w_gsig_valid_radiobutton.get_active()
                req_names = self.w_gsig_name_radiobutton.get_active()
                names = gui_misc.fetch_signature_policy_names_from_textfield(
                    self.w_gsig_name_entry.get_text())
                if req_names and len(names) == 0:
                        return False
                set_props = gui_misc.setup_signature_policy_properties(ignore,
                    verify, req_sigs, req_names, names, orig)
                if len(set_props) > 0:
                        return self.__update_img_sig_policy_prop(set_props)
                return True

        def __prepare_img_signature_policy(self):
                if self.orig_gsig_policy:
                        return
                sig_policy = self.__fetch_img_signature_policy()
                self.orig_gsig_policy = sig_policy
                self.w_gsig_ignored_radiobutton.set_active(
                    sig_policy[gui_misc.SIG_POLICY_IGNORE])
                self.w_gsig_optional_radiobutton.set_active(
                    sig_policy[gui_misc.SIG_POLICY_VERIFY])
                self.w_gsig_valid_radiobutton.set_active(
                    sig_policy[gui_misc.SIG_POLICY_REQUIRE_SIGNATURES])
                self.w_gsig_cert_names_vbox.set_sensitive(False)

                if sig_policy[gui_misc.SIG_POLICY_REQUIRE_NAMES]:
                        self.w_gsig_name_radiobutton.set_active(True)
                        self.w_gsig_cert_names_vbox.set_sensitive(True)

                names = sig_policy[gui_misc.PROP_SIGNATURE_REQUIRED_NAMES]
                gui_misc.set_signature_policy_names_for_textfield(
                    self.w_gsig_name_entry, names)

        def __fetch_img_signature_policy(self):
                prop_sig_pol = self.parent.get_api_object().img.get_property(
                    gui_misc.PROP_SIGNATURE_POLICY)
                prop_sig_req_names = self.parent.get_api_object().img.get_property(
                    gui_misc.PROP_SIGNATURE_REQUIRED_NAMES)
                return gui_misc.create_sig_policy_from_property(
                    prop_sig_pol, prop_sig_req_names)

        def __on_notebook_change(self, widget, event, pagenum):
                if pagenum == PREFERENCES_NOTEBOOK_LANGUAGES_PAGE:
                        self.w_preferencesdialog.window.set_cursor(
                            self.watch )
                        gobject.idle_add(self.__prepare_locales)
                elif pagenum == PREFERENCES_NOTEBOOK_SIG_POL_PAGE:
                        gobject.idle_add(self.__prepare_img_signature_policy)

        @staticmethod
        def __get_locales_liststore():
                return gtk.ListStore(
                        gobject.TYPE_STRING,   # enumerations.LOCALE_NAME
                                               # - <language> (territory)
                        gobject.TYPE_STRING,   # enumerations.LOCALE_LANGUAGE
                                               # - Display <language> name
                        gobject.TYPE_STRING,   # enumerations.LOCALE_TERRITORY
                                               # - Display <territory> name
                        gobject.TYPE_STRING,   # enumerations.LOCALE
                                               # - <language>_<territory>(code)
                        gobject.TYPE_BOOLEAN,  # enumerations.LOCALE_SELECTED
                        )

        def __select_column_clicked(self, data):
                sort_model = self.w_locales_treeview.get_model()
                model = sort_model.get_model()
                iter_next = sort_model.get_iter_first()
                none_selected = True
                all_selected = True
                list_of_paths = []
                while iter_next != None:
                        sort_path = sort_model.get_path(iter_next)
                        path = sort_model.convert_path_to_child_path(sort_path)
                        list_of_paths.append(path)
                        app_iter = sort_model.convert_iter_to_child_iter(None,
                                            iter_next)
                        val = model.get_value(app_iter,
                            enumerations.LOCALE_SELECTED)
                        if val:
                                none_selected = False
                        else:
                                all_selected = False
                        iter_next = sort_model.iter_next(iter_next)

                some_selected = not all_selected and not none_selected
                select_all = none_selected or some_selected
                for path in list_of_paths:
                        app_iter = model.get_iter(path)
                        val = model.get_value(app_iter,
                            enumerations.LOCALE_SELECTED)
                        if select_all and not val:
                                model.set_value(app_iter,
                                    enumerations.LOCALE_SELECTED, True)
                        elif not select_all and val:
                                model.set_value(app_iter,
                                    enumerations.LOCALE_SELECTED, False)

        @staticmethod
        def __sort_func(treemodel, iter1, iter2, column):
                col_val1 = treemodel.get_value(iter1, column)
                col_val2 = treemodel.get_value(iter2, column)
                ret = cmp(col_val1, col_val2)
                if ret != 0:
                        return ret
                if column == enumerations.LOCALE_LANGUAGE:
                        ter1 = treemodel.get_value(iter1,
                            enumerations.LOCALE_TERRITORY)
                        ter2 = treemodel.get_value(iter2,
                            enumerations.LOCALE_TERRITORY)
                        ret = cmp(ter1, ter2)
                elif column == enumerations.LOCALE_TERRITORY:
                        lang1 = treemodel.get_value(iter1,
                            enumerations.LOCALE_LANGUAGE)
                        lang2 = treemodel.get_value(iter2,
                            enumerations.LOCALE_LANGUAGE)
                        ret = cmp(lang1, lang2)
                return ret

        def __init_locales_tree_view(self, locales_list):
                locales_sort_model = gtk.TreeModelSort(locales_list)
                locales_sort_model.set_sort_column_id(enumerations.LOCALE_LANGUAGE,
                    gtk.SORT_ASCENDING)

                locales_sort_model.set_sort_func(enumerations.LOCALE_LANGUAGE,
                    self.__sort_func,
                    enumerations.LOCALE_LANGUAGE)
                locales_sort_model.set_sort_func(enumerations.LOCALE_TERRITORY,
                    self.__sort_func,
                    enumerations.LOCALE_TERRITORY)

                # Selected column - Not sorted
                toggle_renderer = gtk.CellRendererToggle()
                column = gtk.TreeViewColumn("",
                    toggle_renderer, active = enumerations.LOCALE_SELECTED)
                column.set_expand(False)
                column.set_clickable(True)
                column.connect('clicked', self.__select_column_clicked)
                select_image = self.parent.get_theme_selection_coloumn_image()
                column.set_widget(select_image)
                self.w_locales_treeview.append_column(column)

                # Language column - sort using custom __sort_func()
                lang_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Language"),
                    lang_renderer,  text = enumerations.LOCALE_LANGUAGE)
                column.set_expand(True)
                column.set_sort_column_id(enumerations.LOCALE_LANGUAGE)
                column.set_sort_indicator(True)
                self.w_locales_treeview.append_column(column)

                # Territory column - sort using custom __sort_func()
                ter_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Territory"),
                    ter_renderer,  text = enumerations.LOCALE_TERRITORY)
                column.set_expand(True)
                column.set_sort_column_id(enumerations.LOCALE_TERRITORY)
                column.set_sort_indicator(True)
                self.w_locales_treeview.append_column(column)

                self.w_locales_treeview.get_selection().set_mode(
                    gtk.SELECTION_MULTIPLE)
                self.w_locales_treeview.get_selection().connect('changed',
                    self.__on_languages_treeview_changed)
                self.w_locales_treeview.set_model(locales_sort_model)

        def __init_locales_list(self):
                sorted_model = self.w_locales_treeview.get_model()
                self.w_locales_treeview.set_model(None)
                if not sorted_model:
                        return
                model = sorted_model.get_model()
                model.clear()
                model.insert(0, ["", _("Loading ..."), "", "", False])
                self.w_locales_treeview.set_model(sorted_model)

        def __prepare_locales(self):
                try:
                        if self.locales_setup:
                                return
                        self.__prepare_locales_list()
                finally:
                        self.w_preferencesdialog.window.set_cursor(None)

        def __api_get_facets(self):
                facets = {}
                try:
                        # XXX facets should be accessible through pkg.client.api
                        facets = self.parent.get_api_object().img.get_facets()
                except api_errors.ApiException, ex:
                        err = str(ex)
                        self.w_preferencesdialog.hide()
                        gobject.idle_add(self.parent.error_occurred, err,
                            None, gtk.MESSAGE_INFO )
                return facets

        @staticmethod
        def __strip_g11system_codeset(g11locale):
                strippedlocale = ""
                m = re.match(SYSTEM_G11LOCALE_MATCH, g11locale)
                #Note: for now strip out system locale (code@locale variant)
                #ignore group(2)
                if m != None and len(m.groups()) == 2:
                        strippedlocale = m.group(1)
                return strippedlocale

        @staticmethod
        def __facetlocale_to_g11locale(facetlocale):
                g11locale = ""
                m = re.match(SYSTEM_FACETLOCALE_MATCH, facetlocale)
                if m != None and len(m.groups()) == 2:
                        g11locale = m.group(1)
                        if m.group(2) != '':
                                g11locale += "." + m.group(2)
                return g11locale

        def __prepare_locales_list(self):
                sorted_model = self.w_locales_treeview.get_model()
                self.w_locales_treeview.set_model(None)
                if not sorted_model:
                        return
                # Reset api so we have up to date facet list
                if not self.parent.do_api_reset():
                        #do_api_reset fails then it will inform the user
                        return

                model = sorted_model.get_model()
                self.orig_facets_dict.clear()
                self.orig_facets_dict = self.__api_get_facets()
                self.__setup_optional_components_tab(self.orig_facets_dict)
                self.__process_orig_facets(self.orig_facets_dict)

                # Count selected facet locales for each lang
                self.orig_lang_locale_count_dict.clear()
                for locale, selected in  self.orig_facet_locale_dict.items():
                        lang = locale.split("_")[0]
                        if not self.orig_lang_locale_count_dict.has_key(lang):
                                self.orig_lang_locale_count_dict[lang] = 0
                        if selected:
                                self.orig_lang_locale_count_dict[lang] += 1

                # Setup locales:
                # Try to fetch available locales from system/locale package
                # using __get_system_locales()
                if self.facet_g11_locales_dict == None or \
                        len(self.facet_g11_locales_dict) == 0:
                        facetlocales_list = self.__get_system_locales()
                        if facetlocales_list == None:
                                return
                        for facetlocale in facetlocales_list:
                                g11locale = self.__facetlocale_to_g11locale(
                                    facetlocale)
                                self.facet_g11_locales_dict[facetlocale] = g11locale
                # Setup locales:
                # If not available fall back and get the locales installed on
                # the system using loc_pop.get_valid_locales() and strip any codeset
                if self.facet_g11_locales_dict == None or \
                        len(self.facet_g11_locales_dict) == 0:
                        # pylint: disable=E1101
                        loc_pop = g11nsvc.G11NSvcLocalePopulate()
                        g11locales_list = loc_pop.get_valid_locales()
                        for g11locale in g11locales_list:
                                strippedlocale = self.__strip_g11system_codeset(
                                    g11locale)
                                facetlocale = strippedlocale
                                self.facet_g11_locales_dict[facetlocale] = \
                                        strippedlocale
                # pylint: disable=E1101
                loc_ops = g11nsvc.G11NSvcLocaleOperations(
                    self.facet_g11_locales_dict.values())

                # Process facet locales
                locale_list = []
                for facetlocale, g11locale in self.facet_g11_locales_dict.items():
                        if g11locale == "C" or g11locale == "POSIX":
                                continue
                        locale_name = loc_ops.get_locale_desc(g11locale)
                        if locale_name == None or locale_name == "" :
                                continue
                        locale_language = loc_ops.get_language_desc(g11locale)
                        locale_territory = loc_ops.get_territory_desc(g11locale)
                        locale = facetlocale
                        is_latin = g11locale.endswith("latin")
                        if is_latin:
                                locale_territory += _(" [latin]")
                        lang = locale.split("_")[0]

                        sel_count = 0
                        if self.orig_lang_locale_count_dict.has_key(lang):
                                sel_count = self.orig_lang_locale_count_dict[lang]

                        # Precedence order:
                        # <lang>_<ter>: <lang>_* e.g. nl_BE: nl_*
                        selected = False
                        if sel_count == 0:
                                if self.orig_facet_lang_star_dict.has_key(
                                lang):
                                        selected = \
                                                self.orig_facet_lang_star_dict[lang]
                        elif self.orig_facet_locale_dict.has_key(locale):
                                selected = self.orig_facet_locale_dict[
                                    locale]

                        # locale row contains:
                        #
                        # locale_name = <language> (territory)
                        # locale_language = Display <language> name
                        # locale_territory = Display <territory> name
                        # facetlocale = <language>_<territory>(<codeset>)
                        # selected = selected
                        locale_row = [locale_name, locale_language,
                            locale_territory, facetlocale, selected]
                        locale_list.append(locale_row)
                # Sort and setup model
                model.clear()
                i = 0
                locale_list.sort(key=lambda locale_list: locale_list[
                    enumerations.LOCALE_LANGUAGE])
                for locale_row in locale_list:
                        model.insert(i, locale_row)
                        i += 1
                self.w_locales_treeview.set_model(sorted_model)

                if debug:
                        print "DEBUG loaded facets: ", \
                                self.orig_facet_lang_dict, \
                                self.orig_facet_lang_star_dict, \
                                self.orig_facet_locale_dict
                self.locales_setup = True

        def __get_system_locales(self):
                try:
                        api_o = self.parent.get_api_object()
                        res = api_o.get_pkg_list(
                            pkg_list = api.ImageInterface.LIST_INSTALLED,
                            patterns = ['system/locale'],
                            repos=[],
                            raise_unmatched=False, return_fmris=True,
                            variants=True )

                        manifest = None
                        for entry in res:
                                manifest = api_o.get_manifest(entry[0],
                                    all_variants=True, repos=[] )
                                break
                        facets = None
                        if manifest != None:
                                facets = list(manifest.gen_facets())
                        if debug and facets != None:
                                print "DEBUG facets from system/locale:", facets

                        facetlocales = []
                        if facets == None:
                                return facetlocales

                        for facet_key in facets:
                                if not facet_key.startswith(LOCALE_PREFIX):
                                        continue
                                m = re.match(LOCALE_MATCH, facet_key)
                                if m != None and len(m.groups()) == 1:
                                        locale = m.group(1)
                                        facetlocales.append(locale)
                        return facetlocales

                except api_errors.ApiException, ex:
                        err = str(ex)
                        self.w_preferencesdialog.hide()
                        gobject.idle_add(self.parent.error_occurred, err,
                            None, gtk.MESSAGE_INFO )
                        return None

        def __setup_optional_components_tab(self, facets):
                install_all = self.__is_install_all(facets, ALL_LOCALES)
                self.w_languages_all_radiobutton.set_active(install_all)
                self.w_languages_only_radiobutton.set_active(not install_all)
                self.w_locales_treeview.set_sensitive(not install_all)

                install_devel = self.__is_install_all(facets, ALL_DEVEL)
                self.w_feature_devel_checkbutton.set_active(install_devel)
                install_doc = self.__is_install_all(facets, ALL_DOC)
                self.w_feature_doc_checkbutton.set_active(install_doc)

        @staticmethod
        def __is_install_all(facets, component_type):
                if facets != None and facets.has_key(component_type):
                        return facets[component_type]
                # Default to True if key not present
                return True

        def __process_orig_facets(self, facets):
                if debug:
                        print "DEBUG orig facets", facets

                self.orig_facet_lang_dict.clear()
                self.orig_facet_lang_star_dict.clear()
                self.orig_facet_locale_dict.clear()

                # Process facets
                for facet_key in facets.keys():
                        val = facets[facet_key]
                        if not facet_key.startswith(LOCALE_PREFIX):
                                continue
                        if facet_key == ALL_LOCALES:
                                self.orig_facet_lang_dict[ALL_LOCALES] = val
                                continue
                        m = re.match(LANG_MATCH, facet_key)
                        if m != None and len(m.groups()) == 1:
                                lang = m.group(1)
                                self.orig_facet_lang_dict[lang] = val
                                continue
                        m = re.match(LANG_STAR_MATCH, facet_key)
                        if m != None and len(m.groups()) == 1:
                                lang = m.group(1)
                                self.orig_facet_lang_star_dict[lang] = val
                                continue
                        m = re.match(LOCALE_MATCH, facet_key)
                        if m != None and len(m.groups()) == 1:
                                locale = m.group(1)
                                self.orig_facet_locale_dict[locale] = val

        def __dump_locales_list(self):
                self.facets_to_set = self.__api_get_facets()
                install_all = self.w_languages_all_radiobutton.get_active()
                self.facets_to_set[ALL_LOCALES] = install_all

                if install_all:
                        return

                sorted_model = self.w_locales_treeview.get_model()
                if not sorted_model:
                        return
                model = sorted_model.get_model()

                lang_locale_dict = {}
                lang_locale_count_dict = {}
                for row in model:
                        selected = row[enumerations.LOCALE_SELECTED]
                        locale = row[enumerations.LOCALE]
                        lang = locale.split("_")[0]

                        if not lang_locale_dict.has_key(lang):
                                lang_locale_dict[lang] = {}
                        lang_locale_dict[lang][locale] = selected
                        if not lang_locale_count_dict.has_key(lang):
                                lang_locale_count_dict[lang] = 0
                        if selected:
                                lang_locale_count_dict[lang] += 1

                for lang, locales in lang_locale_dict.items():
                        sel_count = lang_locale_count_dict[lang]
                        self.__process_locales_to_set(lang, locales, sel_count)

                if debug:
                        print "DEBUG facets to set:", self.facets_to_set

        def __dump_optional_components(self):
                install_devel = self.w_feature_devel_checkbutton.get_active()
                install_doc = self.w_feature_doc_checkbutton.get_active()

                if install_devel == False:
                        self.facets_to_set[ALL_DEVEL] = False
                elif self.facets_to_set.has_key(ALL_DEVEL):
                        del self.facets_to_set[ALL_DEVEL]

                if install_doc == False:
                        self.facets_to_set[ALL_DOC] = False
                elif self.facets_to_set.has_key(ALL_DOC):
                        del self.facets_to_set[ALL_DOC]

        def __process_locales_to_set(self, lang, locales, sel_count):
                locales_count = len(locales)
                if locales_count == 0:
                        return

                # All Selected
                if sel_count == locales_count:
                        self.facets_to_set[LOCALE_PREFIX + lang + \
                                    LANG_STAR_SUFFIX] = True
                        self.facets_to_set[LOCALE_PREFIX + lang] = True
                        for item in locales.items():
                                key = LOCALE_PREFIX + item[0]
                                if self.facets_to_set.has_key(key):
                                        del self.facets_to_set[key]
                # None Selected
                elif sel_count == 0:
                        has_orig_star_key = \
                                self.orig_facet_lang_star_dict.has_key(lang)
                        has_orig_lang_count_key = \
                                self.orig_lang_locale_count_dict.has_key(lang)
                        # Has the user made a change to get us to the None selected state?
                        # If not then just ignore.
                        if (has_orig_star_key and
                                self.orig_facet_lang_star_dict[lang]) or \
                            (has_orig_lang_count_key and
                                self.orig_lang_locale_count_dict[lang] > 0):
                                if self.facets_to_set.has_key(LOCALE_PREFIX +
                                    lang + LANG_STAR_SUFFIX):
                                        del self.facets_to_set[LOCALE_PREFIX +
                                            lang + LANG_STAR_SUFFIX]
                                if self.facets_to_set.has_key(LOCALE_PREFIX +
                                    lang):
                                        del self.facets_to_set[LOCALE_PREFIX +
                                            lang]

                        for item in locales.items():
                                key = LOCALE_PREFIX + item[0]
                                if self.facets_to_set.has_key(key):
                                        del self.facets_to_set[key]
                # Some Selected
                else:
                        self.facets_to_set[LOCALE_PREFIX + lang] = True
                        star_key = LOCALE_PREFIX + lang + LANG_STAR_SUFFIX
                        if self.facets_to_set.has_key(star_key):
                                del self.facets_to_set[star_key]
                        for locale, val in locales.items():
                                key = LOCALE_PREFIX + locale
                                if val:
                                        self.facets_to_set[key] = val
                                else:
                                        if self.facets_to_set.has_key(key):
                                                del self.facets_to_set[key]

        def __on_languages_treeview_button_and_key_events(self,
            treeview, event):
                if event.type == GDK_2BUTTON_PRESS:
                        self.__enable_disable()

        def __on_languages_treeview_changed(self, treeselection):
                selection = treeselection.get_selected_rows()
                pathlist = selection[1]
                self.locales_treeview_selection = pathlist
                if pathlist != None and len(pathlist) == 1:
                        self.__enable_disable()

        def __enable_disable(self):
                sorted_model = self.w_locales_treeview.get_model()
                if sorted_model == None:
                        return
                model = sorted_model.get_model()
                if len(self.locales_treeview_selection) == 0:
                        return

                path = self.locales_treeview_selection[0]
                child_path = sorted_model.convert_path_to_child_path(path)
                itr = model.get_iter(child_path)
                selected = model.get_value(itr, enumerations.LOCALE_SELECTED)
                model.set_value(itr, enumerations.LOCALE_SELECTED, not selected)

                for path in self.locales_treeview_selection[1:]:
                        child_path = sorted_model.convert_path_to_child_path(path)
                        itr = model.get_iter(child_path)
                        model.set_value(itr, enumerations.LOCALE_SELECTED,
                            not selected)

        def set_modal_and_transient(self, parent_window):
                gui_misc.set_modal_and_transient(self.w_preferencesdialog,
                    parent_window)

        def __on_preferencesdialog_delete_event(self, widget, event):
                self.__on_preferencesclose_clicked(None)
                return True

        def __on_preferencesdialog_show(self, widget):
                self.orig_gsig_policy = {}
                self.locales_setup = False

                pagenum = self.w_preferences_notebook.get_current_page()
                if pagenum == PREFERENCES_NOTEBOOK_LANGUAGES_PAGE:
                        self.w_preferencesdialog.window.set_cursor(self.watch)
                        gobject.idle_add(self.__prepare_locales)
                elif pagenum == PREFERENCES_NOTEBOOK_SIG_POL_PAGE:
                        gobject.idle_add(self.__prepare_img_signature_policy)
                return True

        def __on_preferencescancel_clicked(self, widget):
                self.w_preferencesdialog.hide()

        def __on_preferencesclose_clicked(self, widget):
                error_dialog_title = _("Preferences")
                text = self.w_gsig_name_entry.get_text()
                req_names = self.w_gsig_name_radiobutton.get_active()
                if not gui_misc.check_sig_required_names_policy(text,
                    req_names, error_dialog_title):
                        return
                if self.orig_gsig_policy and not self.__update_img_sig_policy():
                        return
                self.__dump_locales_list()
                self.__dump_optional_components()
                self.w_preferencesdialog.hide()
                ignore_all_default = len(self.orig_facets_dict) == 0 and \
                        len(self.facets_to_set) == 1 \
                        and self.facets_to_set.has_key(ALL_LOCALES) and \
                        self.facets_to_set[ALL_LOCALES] == True
                if not ignore_all_default and self.orig_facets_dict != {} and \
                        self.orig_facets_dict != self.facets_to_set:
                        self.parent.update_facets(self.facets_to_set)
                self.gconf.set_show_startpage(
                    self.w_startpage_checkbutton.get_active())
                self.gconf.set_save_state(
                    self.w_exit_checkbutton.get_active())
                self.gconf.set_show_image_update(
                    self.w_confirm_updateall_checkbutton.get_active())
                self.gconf.set_show_install(
                    self.w_confirm_install_checkbutton.get_active())
                self.gconf.set_show_remove(
                    self.w_confirm_remove_checkbutton.get_active())

        def __on_preferenceshelp_clicked(self, widget):
                pagenum = self.w_preferences_notebook.get_current_page()
                if pagenum == PREFERENCES_NOTEBOOK_SIG_POL_PAGE:
                        tag = "img-sig-policy"
                else:
                        tag = "pkg-mgr-prefs"
                gui_misc.display_help(tag)

        def __on_languages_all_radiobutton_toggled(self, widget):
                self.w_locales_treeview.set_sensitive(
                    not  self.w_languages_all_radiobutton.get_active())

        def activate(self):
                self.w_startpage_checkbutton.set_active(
                    self.gconf.show_startpage)
                self.w_exit_checkbutton.set_active(self.gconf.save_state)
                self.w_confirm_updateall_checkbutton.set_active(
                    self.gconf.show_image_update)
                self.w_confirm_install_checkbutton.set_active(
                    self.gconf.show_install)
                self.w_confirm_remove_checkbutton.set_active(
                    self.gconf.show_remove)
                self.__setup_optional_components_tab(self.__api_get_facets())
                self.w_preferencesdialog.show()

