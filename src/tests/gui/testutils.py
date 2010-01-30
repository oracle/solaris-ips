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

import os
import sys

# Set the path so that modules can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)

import pkg5testenv

def setup_environment(proto):
        pkg5testenv.setup_environment(proto)

try:
        if "DISPLAY" in os.environ:
                import pygtk
                pygtk.require('2.0')
                import gtk
except ImportError:
        pass

def check_for_gtk():
        return "gtk" in globals()

def check_if_a11y_enabled():
        if not check_for_gtk():
                return False
        # To determine if A11Y is enabled we are starting small gtk application
        # and then we do check if the applications' window does contain
        # accessible widget. This allows us to be sure that A11Y is not 
        # only enabled in the gconf key, but it's truly running.
        window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        button = gtk.Button("Check Accessibility")
        window.add(button)
        a11y_enabled = False
        if window.get_accessible().get_n_accessible_children() != 0:
                a11y_enabled = True
        return a11y_enabled
