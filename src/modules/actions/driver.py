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

#
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a driver packaging object.

This module contains the DriverAction class, which represents a driver-type
packaging object.
"""

import os
import subprocess

import generic

class DriverAction(generic.Action):
        """Class representing a driver-type packaging object."""

        name = "driver"
        key_attr = "name"

        # XXX This is a gross hack to let us test the action without having to
        # be root.
        if "USR_SBIN" in os.environ:
                usr_sbin = os.environ["USR_SBIN"]
                if not usr_sbin.endswith("/"):
                        usr_sbin += "/"
        else:
                usr_sbin = "/usr/sbin/"

        add_drv = usr_sbin + "add_drv"
        rem_drv = usr_sbin + "rem_drv"
        update_drv = usr_sbin + "update_drv"

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

        @staticmethod
        def __call(args, fmt, fmtargs):
                proc = subprocess.Popen(args, stdout = subprocess.PIPE,
                    stderr = subprocess.STDOUT)
                buf = proc.stdout.read()
                ret = proc.wait()

                if ret != 0:
                        fmtargs["retcode"] = ret
                        # XXX Module printing
                        print
                        fmt += " failed with return code %(retcode)s"
                        print _(fmt) % fmtargs
                        print ("command run was:"), " ".join(args)
                        print ("command output was:")
                        print "-" * 60
                        print buf,
                        print "-" * 60

        def install(self, pkgplan, orig):
                image = pkgplan.image

		if image.is_zone():
			return

                n2m = os.path.normpath(os.path.sep.join(
                    (image.get_root(), "etc/name_to_major")))

                # Check to see if the driver has already been installed.
                major = [
                    line.rstrip()
                    for line in file(n2m)
                    if line.split()[0] == self.attrs["name"]
                ]

                # In the case where the the packaging system thinks the driver
                # is installed and the driver database doesn't, do a fresh
                # install instead of an update.  If the system thinks the driver
                # is installed but the packaging has no previous knowledge of
                # it, read the driver files to construct what *should* have been
                # there, and proceed.
                #
                # XXX Log that this occurred.
                if major and not orig:
                        orig = self.__get_image_data(image, self.attrs["name"])
                elif orig and not major:
                        orig = None

                if orig:
                        return self.__update_install(image, orig)

                args = ( self.add_drv, "-n", "-b", image.get_root() )

                if "alias" in self.attrs:
                        args += (
                            "-i",
                            " ".join([ '"%s"' % x for x in self.attrlist("alias") ])
                        )
                if "class" in self.attrs:
                        args += (
                            "-c",
                            " ".join(self.attrlist("class"))
                        )
                if "perms" in self.attrs:
                        args += (
                            "-m",
                            ",".join(self.attrlist("perms"))
                        )
                if "policy" in self.attrs:
                        args += (
                            "-p",
                            " ".join(self.attrlist("policy"))
                        )
                if "privs" in self.attrs:
                        args += (
                            "-P",
                            ",".join(self.attrlist("privs"))
                        )

                args += ( self.attrs["name"], )

                self.__call(args, "driver (%(name)s) install",
                    {"name": self.attrs["name"]})

                for cp in self.attrlist("clone_perms"):
                        # If we're given three fields, assume the minor node
                        # name is the same as the driver name.
                        if len(cp.split()) == 3:
                                cp = self.attrs["name"] + " " + cp
                        args = (
                            self.update_drv, "-b", image.get_root(), "-a",
                            "-m", cp, "clone"
                        )
                        self.__call(args, "driver (%(name)s) clone permission "
                            "update", {"name": self.attrs["name"]})

        def __update_install(self, image, orig):
                add_base = ( self.update_drv, "-b", image.get_root(), "-a" )
                rem_base = ( self.update_drv, "-b", image.get_root(), "-d" )

                nalias = set(self.attrlist("alias"))
                oalias = set(orig.attrlist("alias"))
                add_alias = nalias - oalias
                rem_alias = oalias - nalias

                nclass = set(self.attrlist("class"))
                oclass = set(orig.attrlist("class"))
                add_class = nclass - oclass
                rem_class = oclass - nclass

                nperms = set(self.attrlist("perms"))
                operms = set(orig.attrlist("perms"))
                add_perms = nperms - operms
                rem_perms = operms - nperms

                nprivs = set(self.attrlist("privs"))
                oprivs = set(orig.attrlist("privs"))
                add_privs = nprivs - oprivs
                rem_privs = oprivs - nprivs

                npolicy = set(self.attrlist("policy"))
                opolicy = set(orig.attrlist("policy"))
                add_policy = npolicy - opolicy
                rem_policy = opolicy - npolicy

                nclone = set(self.attrlist("clone_perms"))
                oclone = set(orig.attrlist("clone_perms"))
                add_clone = nclone - oclone
                rem_clone = oclone - nclone

                for i in add_alias:
                        args = add_base + ("-i", '"%s"' % i, self.attrs["name"])
                        self.__call(args, "driver (%(name)s) upgrade (addition "
                            "of alias '%(alias)s')",
                            {"name": self.attrs["name"], "alias": i})

                for i in rem_alias:
                        args = rem_base + ("-i", '"%s"' % i, self.attrs["name"])
                        self.__call(args, "driver (%(name)s) upgrade (removal "
                            "of alias '%(alias)s')",
                            {"name": self.attrs["name"], "alias": i})

                # update_drv doesn't do anything with classes, so we have to
                # futz with driver_classes by hand.
                def update_classes(add_class, rem_class):
                        dcp = os.path.normpath(os.path.join(
                            image.get_root(), "etc/driver_classes"))

                        try:
                                dcf = file(dcp, "r")
                                lines = dcf.readlines()
                                dcf.close()
                        except IOError, e:
                                e.args += ("reading",)
                                raise

                        for i, l in enumerate(lines):
                                arr = l.split()
                                if len(arr) == 2 and \
                                    arr[0] == self.attrs["name"] and \
                                    arr[1] in rem_class:
                                        del lines[i]

                        for i in add_class:
                                lines += ["%s\t%s\n" % (self.attrs["name"], i)]

                        try:
                                dcf = file(dcp, "w")
                                dcf.writelines(lines)
                                dcf.close()
                        except IOError, e:
                                e.args += ("writing",)
                                raise

                if add_class or rem_class:
                        try:
                                update_classes(add_class, rem_class)
                        except IOError, e:
                                print "%s (%s) upgrade (classes modification) " \
                                    "failed %s etc/driver_classes with error: " \
                                    "%s (%s)" % (self.name, self.attrs["name"],
                                        e[1], e[0], e[2])
                                print "tried to add %s and remove %s" % \
                                    (add_class, rem_class)

                # For perms, we do removes first because of a busted starting
                # point in build 79, where smbsrv has perms of both "* 666" and
                # "* 640".  The actions move us from 666 to 640, but if we add
                # first, the 640 overwrites the 666 in the file, and then the
                # deletion of 666 complains and fails.
                #
                # We can get around it by removing the 666 first, and then
                # adding the 640, which overwrites the existing 640.
                #
                # XXX Need to think if there are any cases where this might be
                # the wrong order, and whether the other attributes should be
                # done in this order, too.
                for i in rem_perms:
                        args = rem_base + ("-m", i, self.attrs["name"])
                        self.__call(args, "driver (%(name)s) upgrade (removal "
                            "of minor perm '%(perm)s')",
                            {"name": self.attrs["name"], "perm": i})

                for i in add_perms:
                        args = add_base + ("-m", i, self.attrs["name"])
                        self.__call(args, "driver (%(name)s) upgrade (addition "
                            "of minor perm '%(perm)s')",
                            {"name": self.attrs["name"], "perm": i})

                for i in add_privs:
                        args = add_base + ("-P", i, self.attrs["name"])
                        self.__call(args, "driver (%(name)s) upgrade (addition "
                            "of privilege '%(priv)s')",
                            {"name": self.attrs["name"], "priv": i})

                for i in rem_privs:
                        args = rem_base + ("-P", i, self.attrs["name"])
                        self.__call(args, "driver (%(name)s) upgrade (removal "
                            "of privilege '%(priv)s')",
                            {"name": self.attrs["name"], "priv": i})

                for i in add_policy:
                        args = add_base + ("-p", i, self.attrs["name"])
                        self.__call(args, "driver (%(name)s) upgrade (addition "
                            "of policy '%(policy)s')",
                            {"name": self.attrs["name"], "policy": i})

                for i in rem_policy:
                        args = rem_base + ("-p", i, self.attrs["name"])
                        self.__call(args, "driver (%(name)s) upgrade (removal "
                            "of policy '%(policy)s')",
                            {"name": self.attrs["name"], "policy": i})

                for i in rem_clone:
                        if len(i.split()) == 3:
                                i = self.attrs["name"] + " " + i
                        args = rem_base + ("-m", i, "clone")
                        self.__call(args, "driver (%(name)s) upgrade (removal "
                            "of clone permission '%(perm)s')",
                            {"name": self.attrs["name"], "perm": i})

                for i in add_clone:
                        if len(i.split()) == 3:
                                i = self.attrs["name"] + " " + i
                        args = add_base + ("-m", i, "clone")
                        self.__call(args, "driver (%(name)s) upgrade (addition "
                            "of clone permission '%(perm)s')",
                            {"name": self.attrs["name"], "perm": i})

        @classmethod
        def __get_image_data(cls, img, name, collect_errs = False):
                """Construct a driver action from image information.

                Setting 'collect_errs' to True will collect all caught
                exceptions and return them in a tuple with the action.
                """

                errors = [ ]

                # See if it's installed
                try:
                        n2mf = file(os.path.normpath(os.path.join(
                            img.get_root(), "etc/name_to_major")))

                        major = [
                            line.rstrip()
                            for line in n2mf
                            if line.split()[0] == name
                        ]
                        n2mf.close()
                except IOError, e:
                        e.args += ("etc/name_to_major",)
                        if collect_errs:
                                errors.append(e)
                        else:
                                raise

                if not major:
                        if collect_errs:
                                return None, []
                        else:
                                return None

                if len(major) > 1:
                        try:
                                raise RuntimeError, \
                                    "More than one entry for driver '%s' in " \
                                    "/etc/name_to_major" % name
                        except RuntimeError, e:
                                if collect_errs:
                                        errors.append(e)
                                else:
                                        raise

                act = cls()
                act.attrs["name"] = name

                # Grab aliases
                try:
                        daf = file(os.path.normpath(os.path.join(
                            img.get_root(), "etc/driver_aliases")))
                except IOError, e:
                        e.args += ("etc/driver_aliases",)
                        if collect_errs:
                                errors.append(e)
                        else:
                                raise
                else:
                        act.attrs["alias"] = [
                            line.split()[1].strip('"')
                            for line in daf
                            if line.split()[0] == name
                        ]
                        daf.close()

                # Grab classes
                try:
                        dcf = file(os.path.normpath(os.path.join(
                            img.get_root(), "etc/driver_classes")))
                except IOError, e:
                        e.args += ("etc/driver_classes",)
                        if collect_errs:
                                errors.append(e)
                        else:
                                raise
                else:
                        act.attrs["class"] = [ ]
                        for line in dcf:
                                larr = line.rstrip().split()
                                if len(larr) == 2 and larr[0] == name:
                                        act.attrs["class"].append(larr[1])
                        dcf.close()

                # Grab minor node permissions
                try:
                        dmf = file(os.path.normpath(os.path.join(
                            img.get_root(), "etc/minor_perm")))
                except IOError, e:
                        e.args += ("etc/minor_perm",)
                        if collect_errs:
                                errors.append(e)
                        else:
                                raise
                else:
                        act.attrs["perms"] = [ ]
                        act.attrs["clone_perms"] = [ ]
                        for line in dmf:
                                maj, perm = line.rstrip().split(":", 1)
                                if maj == name:
                                        act.attrs["perms"].append(perm)
                                # Although some clone_perms might by rights
                                # belong to a driver whose name is not the minor
                                # name here, there's no way to figure that out.
                                elif maj == "clone" and perm.split()[0] == name:
                                        act.attrs["clone_perms"].append(
                                            " ".join(perm.split()[1:]))
                        dmf.close()

                # Grab device policy
                try:
                        dpf = file(os.path.normpath(os.path.join(
                            img.get_root(), "etc/security/device_policy")))
                except IOError, e:
                        e.args += ("etc/security/device_policy",)
                        if collect_errs:
                                errors.append(e)
                        else:
                                raise
                else:
                        act.attrs["policy"] = [ ]
                        for line in dpf:
                                fields = line.rstrip().split()
                                n = ""
                                try:
                                        n, c = fields[0].split(":", 1)
                                        # Canonicalize a "*" minorspec to empty
                                        if c == "*":
                                                del fields[0]
                                        else:
                                                fields[0] = c
                                except ValueError:
                                        n = fields[0]
                                        del fields[0]
                                except IndexError:
                                        pass

                                if n == name:
                                        act.attrs["policy"].append(
                                            " ".join(fields)
                                        )
                        dpf.close()

                # Grab device privileges
                try:
                        dpf = file(os.path.normpath(os.path.join(
                            img.get_root(), "etc/security/extra_privs")))
                except IOError, e:
                        e.args += ("etc/security/extra_privs",)
                        if collect_errs:
                                errors.append(e)
                        else:
                                raise
                else:
                        act.attrs["privs"] = [
                            line.rstrip().split(":", 1)[1]
                            for line in dpf
                            if line.split(":", 1)[0] == name
                        ]
                        dpf.close()

                if collect_errs:
                        return act, errors
                else:
                        return act

        def verify(self, img, **args):
                """Verify that the driver is installed as specified."""

		if img.is_zone():
			return []

                name = self.attrs["name"]

                onfs, errors = \
                    self.__get_image_data(img, name, collect_errs = True)

                for i, err in enumerate(errors):
                        if isinstance(err, IOError):
                                errors[i] = "%s: %s" % (err.args[2], err)
                        elif isinstance(err, RuntimeError):
                                errors[i] = "etc/name_to_major: more than " \
                                    "one entry for '%s' is present" % name

                if not onfs:
                        errors[0:0] = [
                            "etc/name_to_major: '%s' entry not present" % name
                        ]
                        return errors

                onfs_aliases = set(onfs.attrlist("alias"))
                mfst_aliases = set(self.attrlist("alias"))
                for a in onfs_aliases - mfst_aliases:
                        errors.append("extra alias '%s' found in "
                            "etc/driver_aliases" % a)
                for a in mfst_aliases - onfs_aliases:
                        errors.append("alias '%s' missing from "
                        "etc/driver_aliases" % a)

                onfs_classes = set(onfs.attrlist("class"))
                mfst_classes = set(self.attrlist("class"))
                for a in onfs_classes - mfst_classes:
                        errors.append("extra class '%s' found in "
                            "etc/driver_classes" % a)
                for a in mfst_classes - onfs_classes:
                        errors.append("class '%s' missing from "
                            "etc/driver_classes" % a)

                onfs_perms = set(onfs.attrlist("perms"))
                mfst_perms = set(self.attrlist("perms"))
                for a in onfs_perms - mfst_perms:
                        errors.append("extra minor node permission '%s' found "
                            "in etc/minor_perm" % a)
                for a in mfst_perms - onfs_perms:
                        errors.append("minor node permission '%s' missing "
                            "from etc/minor_perm" % a)

                onfs_policy = set(onfs.attrlist("policy"))
                # Canonicalize "*" minorspecs to empty
                policylist = list(self.attrlist("policy"))
                for i, p in enumerate(policylist):
                        f = p.split()
                        if f[0] == "*":
                                policylist[i] = " ".join(f[1:])
                mfst_policy = set(policylist)
                for a in onfs_policy - mfst_policy:
                        errors.append("extra device policy '%s' found in "
                            "etc/security/device_policy" % a)
                for a in mfst_policy - onfs_policy:
                        errors.append("device policy '%s' missing from "
                            "etc/security/device_policy" % a)

                onfs_privs = set(onfs.attrlist("privs"))
                mfst_privs = set(self.attrlist("privs"))
                for a in onfs_privs - mfst_privs:
                        errors.append("extra device privilege '%s' found in "
                            "etc/security/extra_privs" % a)
                for a in mfst_privs - onfs_privs:
                        errors.append("device privilege '%s' missing from "
                            "etc/security/extra_privs" % a)

                return errors

        def remove(self, pkgplan):
		image = pkgplan.image

		if image.is_zone():
			return

                args = (
                    self.rem_drv,
                    "-b",
                    image.get_root(),
                    self.attrs["name"]
                )

                self.__call(args, "driver (%(name)s) removal",
                    {"name": self.attrs["name"]})

                for cp in self.attrlist("clone_perms"):
                        if len(cp.split()) == 3:
                                cp = self.attrs["name"] + " " + cp
                        args = (
                            self.update_drv, "-b", image.get_root(),
                            "-d", "-m", cp, "clone"
                        )
                        self.__call(args, "driver (%(name)s) clone permission "
                            "update", {"name": self.attrs["name"]})


        def generate_indices(self):
                ret = {}
                if "name" in self.attrs:
                        ret["driver_name"] = self.attrs["name"]
                if "alias" in self.attrs:
                        ret["driver_aliases"] = self.attrs["alias"]
                return ret

