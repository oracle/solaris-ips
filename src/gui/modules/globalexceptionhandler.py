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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import sys
import threading
import traceback
from cStringIO import StringIO

try:
        import gobject
        import gtk
        import pango
except ImportError:
        sys.exit(1)
import pkg.misc as misc
import pkg.gui.misc as gui_misc

class GlobalExceptionHandler:
        def __init__(self, name):
                self.parent = None
                self.name = name
                sys.excepthook = self.global_exception_handler
                self.installThreadExcepthook()

        def global_exception_handler(self, exctyp, value, tb):
                trace = StringIO()
                traceback.print_exception (exctyp, value, tb, None, trace)
                if exctyp is MemoryError:
                        gobject.idle_add(self.__display_memory_err)
                else:
                        gobject.idle_add(self.__display_unknown_err_ex, trace)

        def installThreadExcepthook(self):
                """
                Workaround for sys.excepthook python thread bug from:
                Bug: sys.excepthook doesn't work in threads
                http://bugs.python.org/issue1230540#msg91244
                """
                init_old = threading.Thread.__init__
                def init(self, *ite_args, **ite_kwargs):
                        init_old(self, *ite_args, **ite_kwargs)
                        run_old = self.run
                        def run_with_except_hook(*rweh_args, **rweh_kwargs):
                                try:
                                        run_old(*rweh_args, **rweh_kwargs)
                                except (KeyboardInterrupt, SystemExit):
                                        raise
                                except:
                                        if not sys:
                                                raise
                                        sys.excepthook(*sys.exc_info())
                        self.run = run_with_except_hook
                threading.Thread.__init__ = init

        def __display_memory_err(self):
                try:
                        dmsg = misc.out_of_memory()
                        msg_stripped = dmsg.replace("\n", " ")
                        gui_misc.error_occurred(None, msg_stripped, _("Package Manager"),
                            gtk.MESSAGE_ERROR)
                except MemoryError:
                        print dmsg
                except Exception:
                        pass
                if self.parent:
                        self.parent.unhandled_exception_shutdown()
                else:
                        sys.exit()

        def __display_unknown_err_ex(self, trace):
                try:
                        self.__display_unknown_err(trace)
                except MemoryError:
                        print trace
                except Exception:
                        pass
                if self.parent:
                        self.parent.unhandled_exception_shutdown()
                else:
                        sys.exit()

        def __display_unknown_err(self, trace):
                dmsg = _("An unknown error occurred")
                md = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, message_format=dmsg)
                close_btn = md.add_button(gtk.STOCK_CLOSE, 100)
                md.set_default_response(100)

                dmsg = _("Please let the developers know about this problem by\n"
                    "filing a bug together with the error details listed below at:")
                md.format_secondary_text(dmsg)
                md.set_title(_('Unexpected Error'))

                uri_btn = gtk.LinkButton(
                    "http://defect.opensolaris.org/bz/enter_bug.cgi?product=pkg",
                    "defect.opensolaris.org")
                uri_btn.set_relief(gtk.RELIEF_NONE)
                uri_btn.set_size_request(160, -1)
                align = gtk.Alignment(0, 0, 0, 0)
                align.set_padding(0, 0, 56, 0)
                align.add(uri_btn)

                textview = gtk.TextView()
                textview.show()
                textview.set_editable(False)
                sw = gtk.ScrolledWindow()
                sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
                sw.add(textview)
                fr = gtk.Frame()
                fr.set_shadow_type(gtk.SHADOW_IN)
                fr.add(sw)
                ca = md.get_content_area()
                ca.pack_start(align, False, False, 0)
                ca.pack_start(fr)

                textbuffer = textview.get_buffer()
                textbuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
                textbuffer.create_tag("level1", left_margin=30, right_margin=10)
                textiter = textbuffer.get_end_iter()
                textbuffer.insert_with_tags_by_name(textiter,
                     _("Error details:\n"), "bold")
                textbuffer.insert_with_tags_by_name(textiter, trace.getvalue(), "level1")
                publisher_str = ""
                if self.parent:
                        publisher_str = \
                                gui_misc.get_publishers_for_output(
                                    self.parent.get_api_object())
                        if publisher_str != "":
                                textbuffer.insert_with_tags_by_name(textiter,
                                    _("\nList of configured publishers:"), "bold")
                                textbuffer.insert_with_tags_by_name(
                                    textiter, publisher_str + "\n", "level1")

                if publisher_str == "":
                        textbuffer.insert_with_tags_by_name(textiter,
                            _("\nPlease include output from:\n"), "bold")
                        textbuffer.insert(textiter, "$ pkg publisher\n")

                ver = gui_misc.get_version()
                textbuffer.insert_with_tags_by_name(textiter,
                    _("\npkg version:\n"), "bold")
                textbuffer.insert_with_tags_by_name(textiter, ver + "\n", "level1")
                md.set_size_request(550, 400)
                md.set_resizable(True)
                close_btn.grab_focus()
                md.show_all()
                md.run()
                md.destroy()
