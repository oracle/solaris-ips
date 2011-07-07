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

#
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.
#

"""
System linked image module classes.  System linked images support both child
and parent linking.  System linked image child configuration information is
stored within a parent images pkg5.image configuration file.
"""

# pkg classes
import pkg.client.pkgdefs as pkgdefs

# import linked image common code
import common as li # Relative import; pylint: disable-msg=W0403


class LinkedImageSystemPlugin(li.LinkedImagePlugin):
        """See parent class for docstring."""

        # specify what functionality we support
        support_attach = True
        support_detach = True

        # default attach property values
        attach_props_def = {
            li.PROP_RECURSE:        True
        }

        def __init__(self, pname, linked):
                """See parent class for docstring."""
                li.LinkedImagePlugin.__init__(self, pname, linked)

                # globals
                self.__pname = pname
                self.__linked = linked
                self.__img = linked.image

        def init_root(self, old_altroot):
                """See parent class for docstring."""
                # nothing to do
                return

        def get_altroot(self, ignore_errors=False):
                """See parent class for docstring."""
                # nothing to do
                return None

        def get_child_list(self, nocache=False, ignore_errors=False):
                """See parent class for docstring."""

                if not self.__img.cfg:
                        # this may be a new image that hasn't actually been
                        # created yet
                        return []

                rv = []
                for lin in self.__img.cfg.linked_children:
                        path = self.get_child_props(lin)[li.PROP_PATH]
                        rv.append([lin, path])

                for lin, path in rv:
                        assert lin.lin_type == self.__pname

                return rv

        def get_child_props(self, lin):
                """See parent class for docstring."""

                # make a copy of the properties
                props = self.__img.cfg.linked_children[lin].copy()

                # update path to include any altroot
                altroot = self.__linked.altroot()
                props[li.PROP_PATH] = \
                    li.add_altroot_path(props[li.PROP_PATH], altroot)

                return props

        def attach_child_inmemory(self, props, allow_relink):
                """See parent class for docstring."""

                # make sure this child doesn't already exist
                lin = props[li.PROP_NAME]
                lin_list = [i[0] for i in self.get_child_list()]
                assert lin not in lin_list or allow_relink

                # make a copy of the properties
                props = props.copy()

                # update path to remove any altroot
                altroot = self.__linked.altroot()
                props[li.PROP_PATH] = \
                    li.rm_altroot_path(props[li.PROP_PATH], altroot)

                # delete temporal properties
                props = li.rm_dict_ent(props, li.temporal_props)

                self.__img.cfg.linked_children[lin] = props

        def detach_child_inmemory(self, lin):
                """See parent class for docstring."""

                # make sure this child exists
                assert lin in [i[0] for i in self.get_child_list()]

                # Delete this linked image
                del self.__img.cfg.linked_children[lin]

        def sync_children_todisk(self):
                """See parent class for docstring."""

                self.__img.cfg.write()

                return (pkgdefs.EXIT_OK, None)


class LinkedImageSystemChildPlugin(li.LinkedImageChildPlugin):
        """See parent class for docstring."""

        def __init__(self, lic):
                """See parent class for docstring."""
                li.LinkedImageChildPlugin.__init__(self, lic)

                # globals
                self.__linked = lic.child_pimage.linked

        def munge_props(self, props):
                """See parent class for docstring."""

                # update path to remove any altroot
                altroot = self.__linked.altroot()
                props[li.PROP_PATH] = \
                    li.rm_altroot_path(props[li.PROP_PATH], altroot)
