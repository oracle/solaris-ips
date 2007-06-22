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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import bisect
import os
import re
import sha
import shutil
import time
import urllib

import pkg.fmri as fmri
import pkg.package as package

# The type member is used for the ordering of actions.
ACTION_DIR = 10
ACTION_FILE = 20
ACTION_LINK = 50
ACTION_HARDLINK = 55
ACTION_DEVICE = 100
ACTION_USER = 200
ACTION_GROUP = 210
ACTION_SERVICE = 300
ACTION_RESTART = 310
ACTION_DEPEND = 400

DEPEND_REQUIRE = 0
DEPEND_OPTIONAL = 1
DEPEND_INCORPORATE =10

depend_str = { DEPEND_REQUIRE : "require",
                DEPEND_OPTIONAL : "optional",
                DEPEND_INCORPORATE : "incorporate"
}

class ManifestAction(object):
        def __init__(self):
                self.type = None
                self.attrs = {}
                self.mandatory_attrs = []

        def is_complete(self):
                for a in self.mandatory_attrs:
                        if not self.attrs.has_key(a):
                                return False

                return True

class FileManifestAction(ManifestAction):
        def __init__(self):
                ManifestAction.__init__(self)

                self.type = ACTION_FILE
                self.mandatory_attrs = [ "owner", "mode", "hash", "group",
                    "path" ]

        def __str__(self):
                # XXX generalize to superclass?
                r = "file %s %s %s %s %s" % (self.attrs["mode"],
                    self.attrs["owner"], self.attrs["group"],
                    self.attrs["path"], self.attrs["hash"])

                for k in self.attrs.keys():
                        if k in self.mandatory_attrs:
                                continue
                        r = r + " %s=%s" % (k, self.attrs[k])

                return r

class LinkManifestAction(ManifestAction):
        def __init__(self):
                ManifestAction.__init__(self)

                self.type = ACTION_LINK
                self.mandatory_attrs = [ "path", "target" ]

class DependencyManifestAction(ManifestAction):
        def __init__(self):
                ManifestAction.__init__(self)

                self.type = ACTION_DEPEND
                self.mandatory_attrs = [ "fmri", "dtype" ]

        def __str__(self):
                # XXX generalize to superclass?
                r = "%s %s" % (depend_str[self.attrs["dtype"]],
                    self.attrs["fmri"])

                for k in self.attrs.keys():
                        if k in self.mandatory_attrs:
                                continue
                        r = r + " %s=%s" % (k, self.attrs[k])

                return r


class Manifest(object):
        """A Manifest is the representation of the actions composing a specific
        package version on both the client and the repository.  Both purposes
        utilize the same storage format.

        The serialized structure of a manifest is an unordered list of package
        attributes, followed by an unordered list of actions (such as files to
        install).

        The special action, "set", represents an attribute setting.

        The reserved attribute, "fmri", represents the package and version
        described by this manifest.  It is available as a string via the
        attributes dictionary, and as an FMRI object from the fmri member.

        The list of manifest-wide reserved attributes is

        base_directory          Default base directory, for non-user images.
        fmri                    Package FMRI.
        isa                     Package is intended for a list of ISAs.
        licenses                Package contains software available under a list
                                of license terms.
        platform                Package is intended for a list of platforms.
        relocatable             Suitable for User Image.

        All non-prefixed attributes are reserved to the framework.  Third
        parties may prefix their attributes with a reversed domain name, domain
        name, or stock symbol.  An example might be

        com.example,supported

        as an indicator that a specific package version is supported by the
        vendor, example.com.

        manifest.null is provided as the null manifest.  Differences against the
        null manifest result in the complete set of attributes and actions of
        the non-null manifest, meaning that all operations can be viewed as
        tranitions between the manifest being installed and the manifest already
        present in the image (which may be the null manifest).

        XXX Need one or more differences methods, so that we can build a list of
        the actions we must take and the actions that are no longer relevant,
        which would include deletions.
        """

        def __init__(self):
                self.fmri = None

                self.actions = []
                self.attributes = {}
                return

        def __str__(self):
                r = ""

                if self.fmri != None:
                        r = r + "set fmri = %s\n" % self.fmri

                for att in sorted(self.attributes.keys()):
                        r = r + "set %s = %s\n" % (att, self.attributes[att])

                for act in self.actions:
                        r = r + "%s\n" % act

                return r

        def display_differences(self, other):
                """Output expects that self is newer than other.  Use of sets
                requires that we convert the action objects into some marshalled
                form, otherwise set member identities are derived from the
                object pointers, rather than the contents."""

                sset = set()
                oset = set()

                for acs in self.actions:
                        sset.add("%s" % acs)

                for aco in other.actions:
                        oset.add("%s" % aco)

                for ats in self.attributes.keys():
                        sset.add("%s=%s" % (ats, self.attributes[ats]))

                for ato in other.attributes.keys():
                        oset.add("%s=%s" % (ato, other.attributes[ato]))

                dset = sset.symmetric_difference(oset)

                for att in dset:
                        if att in sset:
                                print "+ %s" % att
                        else:
                                print "- %s" % att

        def set_fmri(self, fmri):
                self.fmri = fmri

        def add_attribute_line(self, str):
                """An attribute line is 

                set attribute = str

                where str becomes the value of the attribute.

                XXX For now, the value is left as a simple string.  We could in
                principle parse into specific types."""

                m = re.match("^set ([a-z,.-_]*)\s*=\s*(.*)$", str)
                self.attributes[m.group(1)] = m.group(2)

                return

        def add_file_action_line(self, str):
                """A file action line is

                file mode owner group path hash n=v

                """

                m = re.match("^file (\d+) ([^\s]+) ([^\s]+) ([^\s]+) ([^\s]+)\s?(.*)", str)
                if m == None:
                        raise SyntaxError, "invalid file action '%s'" % str

                a = FileManifestAction()
                a.attrs["mode"] = m.group(1)
                a.attrs["owner"] = m.group(2)
                a.attrs["group"] = m.group(3)
                a.attrs["path"] = m.group(4)
                a.attrs["hash"] = m.group(5)

                # if any name value settings, add to action's tags
                if m.group(6) != "":
                        nvs = re.split("\s+", m.group(6))

                        for nv in nvs:
                                # XXX what if v is empty?  syntax error?
                                n, v = re.split("=", nv, 1)
                                n.strip()
                                v.strip()
                                a.attrs[n] = v

                if len(self.actions) == 0:
                        self.actions.append(a)
                else:
                        bisect.insort(self.actions, a)

        def add_dependency_action_line(self, str):
                """A dependency action line is one or more of

                require fmri n=v
                incorporate fmri n=v
                optional fmri n=v

                """

                m = re.match("^(require|incorporate|optional) ([^\s]+)\s?(.*)", str)
                if m == None:
                        raise SyntaxError, "invalid dependency action '%s'" % str

                a = DependencyManifestAction()
                for k in depend_str.keys():
                        if depend_str[k] == m.group(1):
                                a.attrs["dtype"] = k
                                break

                if a.attrs["dtype"] == None:
                        raise KeyError, "unknown dependency type '%s'" % m.group(1)

                a.attrs["fmri"] = m.group(2)

                # if any name value settings, add to action's tags
                if m.group(3) != "":
                        nvs = re.split("\s+", m.group(6))

                        for nv in nvs:
                                # XXX what if v is empty?  syntax error?
                                n, v = re.split("=", nv, 1)
                                n.strip()
                                v.strip()
                                a.attrs[n] = v

                if len(self.actions) == 0:
                        self.actions.append(a)
                else:
                        bisect.insort(self.actions, a)

        def set_content(self, str):
                """str is the text representation of the manifest"""

                for l in str.splitlines():
                        if re.match("^\s*$", l):
                                continue
                        if re.match("^set ", l):
                                self.add_attribute_line(l)
                        elif re.match("^file ", l):
                                self.add_file_action_line(l)
                        elif re.match("^(require|optional|incorporate) ", l):
                                self.add_dependency_action_line(l)
                        else:
                                raise SyntaxError, "unknown action '%s'" % l

                return

null = Manifest()

if __name__ == "__main__":
        m1 = Manifest()

        x = """\
set com.sun,test = true
require pkg:/library/libc
file 0555 sch staff /usr/bin/i386/sort fff555fff isa=i386
"""
        m1.set_content(x)

        print m1

        m2 = Manifest()

        y = """\
set com.sun,test = true
set com.sun,data = true
require pkg:/library/libc
file 0555 sch staff /usr/bin/i386/sort fff555ff9 isa=i386
file 0555 sch staff /usr/bin/amd64/sort eeeaaaeee isa=amd64
"""

        m2.set_content(y)

        print m2

        m2.display_differences(m1)

        print null

        m2.display_differences(null)
