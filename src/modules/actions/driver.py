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
# Copyright (c) 2010, 2011, Oracle and/or its affiliates. All rights reserved.
#

"""module describing a driver packaging object.

This module contains the DriverAction class, which represents a driver-type
packaging object.
"""

import os
from tempfile import mkstemp

import generic
import pkg.pkgsubprocess as subprocess
from pkg.client.debugvalues import DebugValues

class DriverAction(generic.Action):
        """Class representing a driver-type packaging object."""

        __slots__ = []

        name = "driver"
        key_attr = "name"
        globally_identical = True

        usr_sbin = None
        add_drv = None
        rem_drv = None
        update_drv = None

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

                if not self.__class__.usr_sbin:
                        self.__usr_sbin_init()

                #
                # Clean up clone_perms.  This attribute may been specified either as:
                #     <minorname> <mode> <owner> <group>
                # or
                #     <mode> <owner> <group>
                #
                # In the latter case, the <minorname> is assumed to be
                # the same as the driver name.  Correct any such instances
                # here so that there is only one form, so that we can cleanly
                # compare, verify, etc.
                #
                if not self.attrlist("clone_perms"):
                        return

                new_cloneperms = []
                for cp in self.attrlist("clone_perms"):
                        # If we're given three fields, assume the minor node
                        # name is the same as the driver name.
                        if len(cp.split()) == 3:
                                new_cloneperms.append(
                                    self.attrs["name"] + " " + cp)
                        else:
                                new_cloneperms.append(cp)
                if len(new_cloneperms) == 1:
                        self.attrs["clone_perms"] = new_cloneperms[0]
                else:
                        self.attrs["clone_perms"] = new_cloneperms

        def __usr_sbin_init(self):
                """Initialize paths to device management commands that we will
                execute when handling package driver actions"""

                usr_sbin = DebugValues.get("driver-cmd-dir", "/usr/sbin") + "/"
                self.__class__.usr_sbin = usr_sbin
                self.__class__.add_drv = usr_sbin + "add_drv"
                self.__class__.rem_drv = usr_sbin + "rem_drv"
                self.__class__.update_drv = usr_sbin + "update_drv"

        def __getstate__(self):
                """This object doesn't have a default __dict__, instead it
                stores its contents via __slots__.  Hence, this routine must
                be provide to translate this object's contents into a
                dictionary for pickling"""

                pstate = generic.Action.__getstate__(self)
                return (None, pstate)

        def __setstate__(self, state):
                """This object doesn't have a default __dict__, instead it
                stores its contents via __slots__.  Hence, this routine must
                be provide to translate a pickled dictionary copy of this
                object's contents into a real in-memory object."""

                (state, pstate) = state
                assert state == None
                generic.Action.__setstate__(self, pstate)

                if not self.__class__.usr_sbin:
                        self.__usr_sbin_init()

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

        @classmethod
        def __activate_drivers(cls):
                cls.__call([cls.usr_sbin + "devfsadm", "-u"],
                    "Driver activation failed", {})

        def install(self, pkgplan, orig):
                image = pkgplan.image

                if image.is_zone():
                        return

                # See if it's installed
                major = False
                try:
                        for fields in DriverAction.__gen_read_binding_file(
                            image, "etc/name_to_major", minfields=2,
                            maxfields=2):
                                if fields[0] == self.attrs["name"]:
                                        major = True
                                        break
                except IOError:
                        pass

                # Iterate through driver_aliases and the driver actions of the
                # target image to see if this driver will bind to an alias that
                # some other driver will bind to.  If we find that it will, and
                # it's unclaimed by any other driver action, then we want to
                # comment out (for easier recovery) the entry from the file.  If
                # it's claimed by another driver action, then we should fail
                # installation, as if two driver actions tried to deliver the
                # same driver.  If it's unclaimed, but appears to belong to a
                # driver of the same name as this one, we'll safely slurp it in
                # with __get_image_data().
                #
                # XXX This check should be done in imageplan preexecution.

                file_db = {}
                alias_lines = {}
                alias_conflict = None
                lines = []
                try:
                        for fields in DriverAction.__gen_read_binding_file(
                            image, "etc/driver_aliases", raw=True, minfields=2,
                            maxfields=2):
                                if isinstance(fields, str):
                                        lines.append(fields + "\n")
                                        continue

                                name, alias = fields
                                file_db.setdefault(name, set()).add(alias)
                                alias_lines.setdefault(alias, []).append(
                                    (name, len(lines)))
                                lines.append("%s \"%s\"\n" % tuple(fields))
                except IOError:
                        pass

                a2d = getattr(image.imageplan, "alias_to_driver", None)
                driver_actions = image.imageplan.get_actions("driver")
                if a2d is None:
                        # For all the drivers we know will be in the final
                        # image, remove them from the db we made by slurping in
                        # the aliases file.  What's left is what we should be
                        # checking for dups against, along with the rest of the
                        # drivers.
                        for name in driver_actions.iterkeys():
                                file_db.pop(name, None)

                        # Build a mapping of aliases to driver names based on
                        # the target image's driver actions.
                        a2d = {}
                        for alias, name in (
                            (a, n)
                            for n, act_list in driver_actions.iteritems()
                            for act in act_list
                            for a in act.attrlist("alias")
                        ):
                                a2d.setdefault(alias, set()).add(name)

                        # Enhance that mapping with data from driver_aliases.
                        for name, aliases in file_db.iteritems():
                                for alias in aliases:
                                        a2d.setdefault(alias, set()).add(name)

                        # Stash this on the imageplan so we don't have to do the
                        # work again.
                        image.imageplan.alias_to_driver = a2d

                for alias in self.attrlist("alias"):
                        names = a2d[alias]
                        assert self.attrs["name"] in names
                        if len(names) > 1:
                                alias_conflict = alias
                                break

                if alias_conflict:
                        be_name = getattr(image.bootenv, "be_name_clone", None)
                        name, line = alias_lines[alias_conflict][0]
                        errdict = {
                            "new": self.attrs["name"],
                            "old": name,
                            "alias": alias_conflict,
                            "line": line,
                            "be": be_name,
                            "imgroot": image.get_root()
                        }
                        if name in driver_actions:
                                raise RuntimeError("\
The '%(new)s' driver shares the alias '%(alias)s' with the '%(old)s'\n\
driver; both drivers cannot be installed simultaneously.  Please remove\n\
the package delivering '%(old)s' or ensure that the package delivering\n\
'%(new)s' will not be installed, and try the operation again." % errdict)
                        else:
                                comment = "# pkg(5): "
                                lines[line] = comment + lines[line]
                                # XXX Module printing
                                if be_name:
                                        print "\
The '%(new)s' driver shares the alias '%(alias)s' with the '%(old)s'\n\
driver, but the system cannot determine how the latter was delivered.\n\
Its entry on line %(line)d in /etc/driver_aliases has been commented\n\
out.  If this driver is no longer needed, it may be removed by booting\n\
into the '%(be)s' boot environment and invoking 'rem_drv %(old)s'\n\
as well as removing line %(line)d from /etc/driver_aliases or, before\n\
rebooting, mounting the '%(be)s' boot environment and running\n\
'rem_drv -b <mountpoint> %(old)s' and removing line %(line)d from\n\
<mountpoint>/etc/driver_aliases." % \
                                            errdict
                                else:
                                        print "\
The '%(new)s' driver shares the  alias '%(alias)s' with the '%(old)s'\n\
driver, but the system cannot determine how the latter was delivered.\n\
Its entry on line %(line)d in /etc/driver_aliases has been commented\n\
out.  If this driver is no longer needed, it may be removed by invoking\n\
'rem_drv -b %(imgroot)s %(old)s' as well as removing line %(line)d\n\
from %(imgroot)s/etc/driver_aliases." % \
                                            errdict

                        dap = image.get_root() + "/etc/driver_aliases"
                        datd, datp = mkstemp(suffix=".driver_aliases",
                            dir=image.get_root() + "/etc")
                        f = os.fdopen(datd, "w")
                        f.writelines(lines)
                        f.close()
                        st = os.stat(dap)
                        os.chmod(datp, st.st_mode)
                        os.chown(datp, st.st_uid, st.st_gid)
                        os.rename(datp, dap)

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

                if image.is_liveroot():
                        args = ( self.add_drv, "-u" )
                        image.imageplan.add_actuator("install",
                            "activate-drivers", self.__activate_drivers)
                else:
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
                        args = (
                            self.update_drv, "-b", image.get_root(), "-a",
                            "-m", cp, "clone"
                        )
                        self.__call(args, "driver (%(name)s) clone permission "
                            "update", {"name": self.attrs["name"]})

                if "devlink" in self.attrs:
                        dlp = os.path.normpath(os.path.join(
                            image.get_root(), "etc/devlink.tab"))
                        dlf = file(dlp)
                        dllines = dlf.readlines()
                        dlf.close()
                        st = os.stat(dlp)

                        dlt, dltp = mkstemp(suffix=".devlink.tab",
                            dir=image.get_root() + "/etc")
                        dlt = os.fdopen(dlt, "w")
                        dlt.writelines(dllines)
                        dlt.writelines((
                            s.replace("\\t", "\t") + "\n"
                            for s in self.attrlist("devlink")
                            if s.replace("\\t", "\t") + "\n" not in dllines
                        ))
                        dlt.close()
                        os.chmod(dltp, st.st_mode)
                        os.chown(dltp, st.st_uid, st.st_gid)
                        os.rename(dltp, dlp)

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
                        args = add_base + ("-i", '%s' % i, self.attrs["name"])
                        self.__call(args, "driver (%(name)s) upgrade (addition "
                            "of alias '%(alias)s')",
                            {"name": self.attrs["name"], "alias": i})

                for i in rem_alias:
                        args = rem_base + ("-i", '%s' % i, self.attrs["name"])
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

                # We have to update devlink.tab by hand, too.
                def update_devlinks():
                        dlp = os.path.normpath(os.path.join(
                            image.get_root(), "etc/devlink.tab"))

                        try:
                                dlf = file(dlp)
                                lines = dlf.readlines()
                                dlf.close()
                                st = os.stat(dlp)
                        except IOError, e:
                                e.args += ("reading",)
                                raise

                        olines = set(orig.attrlist("devlink"))
                        nlines = set(self.attrlist("devlink"))
                        add_lines = nlines - olines
                        rem_lines = olines - nlines

                        missing_entries = []
                        for line in rem_lines:
                                try:
                                        lineno = lines.index(line.replace("\\t", "\t") + "\n")
                                except ValueError:
                                        missing_entries.append(line.replace("\\t", "\t"))
                                        continue
                                del lines[lineno]

                        # Don't put in duplicates.  Because there's no way to
                        # tell what driver owns what line, this means that if
                        # two drivers try to own the same line, one of them will
                        # be unhappy if the other is uninstalled.  So don't do
                        # that.
                        lines.extend((
                            s.replace("\\t", "\t") + "\n"
                            for s in add_lines
                            if s.replace("\\t", "\t") + "\n" not in lines
                        ))

                        try:
                                dlt, dltp = mkstemp(suffix=".devlink.tab",
                                    dir=image.get_root() + "/etc")
                                dlt = os.fdopen(dlt, "w")
                                dlt.writelines(lines)
                                dlt.close()
                                os.chmod(dltp, st.st_mode)
                                os.chown(dltp, st.st_uid, st.st_gid)
                                os.rename(dltp, dlp)
                        except EnvironmentError, e:
                                e.args += ("writing",)
                                raise

                        if missing_entries:
                                raise RuntimeError, missing_entries

                if "devlink" in orig.attrs or "devlink" in self.attrs:
                        try:
                                update_devlinks()
                        except IOError, e:
                                print "%s (%s) upgrade (devlinks modification) " \
                                    "failed %s etc/devlink.tab with error: " \
                                    "%s (%s)" % (self.name, self.attrs["name"],
                                        e[1], e[0], e[2])
                        except RuntimeError, e:
                                print "%s (%s) upgrade (devlinks modification) " \
                                    "failed modifying\netc/devlink.tab.  The " \
                                    "following entries were to be removed, " \
                                    "but were\nnot found:\n    " % \
                                    (self.name, self.attrs["name"]) + \
                                    "\n    ".join(e.args[0])

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

                # We remove policies before adding them, since removing a policy
                # for a driver/minor combination removes it completely from the
                # policy file, not just the subset you might have specified.
                #
                # Also, when removing a policy, there is no way to convince
                # update_drv to remove it unless there's a minor node associated
                # with it.
                for i in rem_policy:
                        spec = i.split()
                        # Test if there is a minor node and if so use it
                        # for the policy removal. Otherwise, if none is
                        # supplied, then use the wild card to match.
                        if len(spec) == 3:
                                minornode = spec[0]
                        elif len(spec) == 2:
                                # This can happen when the policy is defined
                                # in the package manifest without an associated
                                # minor node.
                                minornode = "*"
                        else:
                                print "driver (%s) update (removal of " \
                                    "policy '%s') failed: invalid policy " \
                                    "spec." % (self.attrs["name"], i)
                                continue

                        args = rem_base + ("-p", minornode, self.attrs["name"])
                        self.__call(args, "driver (%(name)s) upgrade (removal "
                            "of policy '%(policy)s')",
                            {"name": self.attrs["name"], "policy": i})

                for i in add_policy:
                        args = add_base + ("-p", i, self.attrs["name"])
                        self.__call(args, "driver (%(name)s) upgrade (addition "
                            "of policy '%(policy)s')",
                            {"name": self.attrs["name"], "policy": i})

                for i in rem_clone:
                        args = rem_base + ("-m", i, "clone")
                        self.__call(args, "driver (%(name)s) upgrade (removal "
                            "of clone permission '%(perm)s')",
                            {"name": self.attrs["name"], "perm": i})

                for i in add_clone:
                        args = add_base + ("-m", i, "clone")
                        self.__call(args, "driver (%(name)s) upgrade (addition "
                            "of clone permission '%(perm)s')",
                            {"name": self.attrs["name"], "perm": i})

        @staticmethod
        def __gen_read_binding_file(img, path, minfields=None, maxfields=None,
            raw=False):

                myfile = file(os.path.normpath(os.path.join(
                    img.get_root(), path)))
                for line in myfile:
                        line = line.strip()
                        fields = line.split()
                        result_fields = []
                        for field in fields:
                                # This is a compromise, for now.  In fact,
                                # comments can begin anywhere in the line,
                                # except inside of quoted material.
                                if field[0] == "#":
                                        break
                                field = field.strip('"')
                                result_fields.append(field)

                        if minfields is not None:
                                if len(result_fields) < minfields:
                                        if raw:
                                                yield line
                                        continue

                        if maxfields is not None:
                                if len(result_fields) > maxfields:
                                        if raw:
                                                yield line
                                        continue

                        if result_fields:
                                yield result_fields
                        elif raw:
                                yield line
                myfile.close()


        @classmethod
        def __get_image_data(cls, img, name, collect_errs = False):
                """Construct a driver action from image information.

                Setting 'collect_errs' to True will collect all caught
                exceptions and return them in a tuple with the action.
                """

                errors = []

                # See if it's installed
                found_major = 0
                try:
                        for fields in DriverAction.__gen_read_binding_file(img,
                             "etc/name_to_major", minfields=2, maxfields=2):
                                if fields[0] == name:
                                        found_major += 1
                except IOError, e:
                        e.args += ("etc/name_to_major",)
                        if collect_errs:
                                errors.append(e)
                        else:
                                raise

                if found_major == 0:
                        if collect_errs:
                                return None, []
                        else:
                                return None

                if found_major > 1:
                        try:
                                raise RuntimeError, \
                                    "More than one entry for driver '%s' in " \
                                    "/etc/name_to_major" % name
                        except RuntimeError, e:
                                if collect_errs:
                                        errors.append(e)
                                else:
                                        raise

                act = cls(name=name)

                # Grab aliases
                try:
                        act.attrs["alias"] = []
                        for fields in DriverAction.__gen_read_binding_file(img,
                             "etc/driver_aliases", minfields=2, maxfields=2):
                                if fields[0] == name:
                                        act.attrs["alias"].append(fields[1])
                except IOError, e:
                        e.args += ("etc/driver_aliases",)
                        if collect_errs:
                                errors.append(e)
                        else:
                                raise

                # Grab classes
                try:
                        act.attrs["class"] = []
                        for fields in DriverAction.__gen_read_binding_file(img,
                             "etc/driver_classes", minfields=2, maxfields=2):
                                if fields[0] == name:
                                        act.attrs["class"].append(fields[1])
                except IOError, e:
                        e.args += ("etc/driver_classes",)
                        if collect_errs:
                                errors.append(e)
                        else:
                                raise

                # Grab minor node permissions.  Note that the clone driver
                # action doesn't actually own its minor node perms; those are
                # owned by other driver actions, through their clone_perms
                # attributes.
                try:
                        act.attrs["perms"] = []
                        act.attrs["clone_perms"] = []
                        for fields in DriverAction.__gen_read_binding_file(img,
                             "etc/minor_perm", minfields=4, maxfields=4):
                                # Break first field into pieces.
                                namefields = fields[0].split(":")
                                if len(namefields) != 2:
                                        continue
                                major = namefields[0]
                                minor = namefields[1]
                                if major == name and name != "clone":
                                        act.attrs["perms"].append(
                                            minor + " " + " ".join(fields[1:]))
                                elif major == "clone" and minor == name:
                                        act.attrs["clone_perms"].append(
                                            minor + " " + " ".join(fields[1:]))
                except IOError, e:
                        e.args += ("etc/minor_perm",)
                        if collect_errs:
                                errors.append(e)
                        else:
                                raise

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
                                line = line.strip()
                                if line.startswith("#"):
                                        continue
                                fields = line.split()
                                if len(fields) < 2:
                                        continue
                                n = ""
                                try:
                                        n, c = fields[0].split(":", 1)
                                        fields[0] = c
                                except ValueError:
                                        # If there is no minor node
                                        # specificition then set it to the
                                        # wildcard but saving the driver
                                        # name first.
                                        n = fields[0]
                                        fields[0] = "*"
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
                        act.attrs["privs"] = [ ]
                        for line in dpf:
                                line = line.strip()
                                if line.startswith("#"):
                                        continue
                                fields = line.split(":", 1)
                                if len(fields) != 2:
                                        continue
                                if fields[0] == name:
                                        act.attrs["privs"].append(fields[1])
                        dpf.close()

                if collect_errs:
                        return act, errors
                else:
                        return act

        def verify(self, img, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image."""

                errors = []
                warnings = []
                info = []
                if img.is_zone():
                        return errors, warnings, info

                name = self.attrs["name"]

                onfs, errors = \
                    self.__get_image_data(img, name, collect_errs = True)

                for i, err in enumerate(errors):
                        if isinstance(err, IOError):
                                errors[i] = "%s: %s" % (err.args[2], err)
                        elif isinstance(err, RuntimeError):
                                errors[i] = _("etc/name_to_major: more than "
                                    "one entry for '%s' is present") % name

                if not onfs:
                        errors[0:0] = [
                            _("etc/name_to_major: '%s' entry not present") % name
                        ]
                        return errors, warnings, info

                onfs_aliases = set(onfs.attrlist("alias"))
                mfst_aliases = set(self.attrlist("alias"))
                for a in onfs_aliases - mfst_aliases:
                        warnings.append(_("extra alias '%s' found in "
                            "etc/driver_aliases") % a)
                for a in mfst_aliases - onfs_aliases:
                        errors.append(_("alias '%s' missing from "
                        "etc/driver_aliases") % a)

                onfs_classes = set(onfs.attrlist("class"))
                mfst_classes = set(self.attrlist("class"))
                for a in onfs_classes - mfst_classes:
                        warnings.append(_("extra class '%s' found in "
                            "etc/driver_classes") % a)
                for a in mfst_classes - onfs_classes:
                        errors.append(_("class '%s' missing from "
                            "etc/driver_classes") % a)

                onfs_perms = set(onfs.attrlist("perms"))
                mfst_perms = set(self.attrlist("perms"))
                for a in onfs_perms - mfst_perms:
                        warnings.append(_("extra minor node permission '%s' "
                            "found in etc/minor_perm") % a)
                for a in mfst_perms - onfs_perms:
                        errors.append(_("minor node permission '%s' missing "
                            "from etc/minor_perm") % a)

                # Canonicalize "*" minorspecs to empty
                policylist = list(onfs.attrlist("policy"))
                for i, p in enumerate(policylist):
                        f = p.split()
                        if f[0] == "*":
                                policylist[i] = " ".join(f[1:])
                onfs_policy = set(policylist)

                policylist = self.attrlist("policy")
                for i, p in enumerate(policylist):
                        f = p.split()
                        if f[0] == "*":
                                policylist[i] = " ".join(f[1:])
                mfst_policy = set(policylist)
                for a in onfs_policy - mfst_policy:
                        warnings.append(_("extra device policy '%s' found in "
                            "etc/security/device_policy") % a)
                for a in mfst_policy - onfs_policy:
                        errors.append(_("device policy '%s' missing from "
                            "etc/security/device_policy") % a)

                onfs_privs = set(onfs.attrlist("privs"))
                mfst_privs = set(self.attrlist("privs"))
                for a in onfs_privs - mfst_privs:
                        warnings.append(_("extra device privilege '%s' found "
                            "in etc/security/extra_privs") % a)
                for a in mfst_privs - onfs_privs:
                        errors.append(_("device privilege '%s' missing from "
                            "etc/security/extra_privs") % a)

                return errors, warnings, info

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
                        args = (
                            self.update_drv, "-b", image.get_root(),
                            "-d", "-m", cp, "clone"
                        )
                        self.__call(args, "driver (%(name)s) clone permission "
                            "update", {"name": self.attrs["name"]})

                if "devlink" in self.attrs:
                        dlp = os.path.normpath(os.path.join(
                            image.get_root(), "etc/devlink.tab"))

                        try:
                                dlf = file(dlp)
                                lines = dlf.readlines()
                                dlf.close()
                                st = os.stat(dlp)
                        except IOError, e:
                                print "%s (%s) removal (devlinks modification) " \
                                    "failed reading etc/devlink.tab with error: " \
                                    "%s (%s)" % (self.name, self.attrs["name"],
                                        e[0], e[1])
                                return

                        devlinks = self.attrlist("devlink")

                        missing_entries = []
                        for line in devlinks:
                                try:
                                        lineno = lines.index(line.replace("\\t", "\t") + "\n")
                                except ValueError:
                                        missing_entries.append(line.replace("\\t", "\t"))
                                        continue
                                del lines[lineno]

                        if missing_entries:
                                print "%s (%s) removal (devlinks modification) " \
                                    "failed modifying\netc/devlink.tab.  The " \
                                    "following entries were to be removed, " \
                                    "but were\nnot found:\n    " % \
                                    (self.name, self.attrs["name"]) + \
                                    "\n    ".join(missing_entries)

                        try:
                                dlt, dltp = mkstemp(suffix=".devlink.tab",
                                    dir=image.get_root() + "/etc")
                                dlt = os.fdopen(dlt, "w")
                                dlt.writelines(lines)
                                dlt.close()
                                os.chmod(dltp, st.st_mode)
                                os.chown(dltp, st.st_uid, st.st_gid)
                                os.rename(dltp, dlp)
                        except EnvironmentError, e:
                                print "%s (%s) removal (devlinks modification) " \
                                    "failed writing etc/devlink.tab with error: " \
                                    "%s (%s)" % (self.name, self.attrs["name"],
                                        e[0], e[1])

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                ret = []
                if "name" in self.attrs:
                        ret.append(("driver", "driver_name", self.attrs["name"],
                            None))
                if "alias" in self.attrs:
                        ret.append(("driver", "alias", self.attrs["alias"],
                            None))
                return ret
