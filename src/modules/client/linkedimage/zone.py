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
# Copyright (c) 2011, 2015, Oracle and/or its affiliates. All rights reserved.
#

"""
Zone linked image module classes.  Zone linked images only support
child attach.  Zone linked image child configuration information is all
derived from zonecfg(1m) options and this plugin, no child configuration
information is stored within a parent image.
"""

# standard python classes
import os
import six
import tempfile

# pkg classes
import pkg.client.api_errors as apx
import pkg.client.pkgdefs as pkgdefs
import pkg.pkgsubprocess

from pkg.client.debugvalues import DebugValues

# import linked image common code
import common as li # Relative import; pylint: disable=W0403

# W0511 XXX / FIXME Comments; pylint: disable=W0511
# XXX: should be defined by libzonecfg python wrapper
# pylint: enable=W0511

ZONE_GLOBAL                  = "global"

ZONE_STATE_STR_CONFIGURED    = "configured"
ZONE_STATE_STR_INCOMPLETE    = "incomplete"
ZONE_STATE_STR_UNAVAILABLE   = "unavailable"
ZONE_STATE_STR_INSTALLED     = "installed"
ZONE_STATE_STR_READY         = "ready"
ZONE_STATE_STR_MOUNTED       = "mounted"
ZONE_STATE_STR_RUNNING       = "running"
ZONE_STATE_STR_SHUTTING_DOWN = "shutting_down"
ZONE_STATE_STR_DOWN          = "down"

zone_installed_states = [
    ZONE_STATE_STR_INSTALLED,
    ZONE_STATE_STR_READY,
    ZONE_STATE_STR_MOUNTED,
    ZONE_STATE_STR_RUNNING,
    ZONE_STATE_STR_SHUTTING_DOWN,
    ZONE_STATE_STR_DOWN
]


#
# If we're operating on a zone image it's very tempting to want to know
# the zone name of that image.  Unfortunately, there's no good way to
# determine this, and more importantly, there is no real need to know
# the zone name.  The only reason to know the name of a linked image is
# so that we can import linked image properties from the associated
# parent image.  But for zones we should never do this.  When operating
# on zone images we may not have access to the associated parent image
# (for example, when running inside a zone).  So every zone image must
# contain all the information needed to do a pkg operation at the start
# of that operation.  i.e., the linked image information required for
# operations must be pushed (or exported) from the parent image.  We can
# not pull (or import) this information from the parent image (in the
# cases where the parent image is accessible).
#
#
# There are lots of possible execution modes that we can find ourselves
# in.  Here are some of the possibilities:
#
# 1) in a gz operating on /
# 2) in a gz operating on a zone linked image via pkg -R
# 3) in a ngz operating on /
# 4) in a ngz operating on an alterate BE image via pkg -R
#    (not supported yet, but we'd like to support it).
# 5) in a ngz operating on an linked image via pkg -R
#    (this could be a default or user image linked to
#    the zone.)
# 6) in a ngz operating on an unlinked image via pkg -R
#
# The only scenarios that we really care about in this plugin are are 2,
# 3, and 4.  While it's tempting to try and detect these scenarios by
# looking at image paths, private zone files, or libbe uuids, all those
# methods have problems.  We can't even check the image zone variant to
# determine if we're dealing with a zone, since in the future if we want
# to support user images within a zone, it's likely they will have the
# zone variant also set to nonglobal.  There's really one way
# to detect if we're working on a zone image, and that is via the image
# metadata.  Ie, either via a pkg cfg_cache linked image property, or
# via linked image properties exported to us by our associated parent
# image.
#


class LinkedImageZonePlugin(li.LinkedImagePlugin):
        """See parent class for docstring."""

        # default attach property values
        attach_props_def = {
            li.PROP_RECURSE:        False
        }

        __zone_pkgs = frozenset([
            frozenset(["system/zones"]),
            frozenset(["SUNWzoner", "SUNWzoneu"])
        ])

        def __init__(self, pname, linked):
                """See parent class for docstring."""
                li.LinkedImagePlugin.__init__(self, pname, linked)

                # globals
                self.__pname = pname
                self.__linked = linked
                self.__img = linked.image
                self.__in_gz_cached = None

                # keep track of our freshly attach children
                self.__children = dict()

                # cache zoneadm output
                self.__zoneadm_list_cache = None

        def __in_gz(self, ignore_errors=False):
                """Check if we're executing in the global zone.  Note that
                this doesn't tell us anything about the image we're
                manipulating, just the environment that we're running in."""

                if self.__in_gz_cached != None:
                        return self.__in_gz_cached

                # check if we're running in the gz
                try:
                        self.__in_gz_cached = (_zonename() == ZONE_GLOBAL)
                except OSError as e:
                        # W0212 Access to a protected member
                        # pylint: disable=W0212
                        if ignore_errors:
                                # default to being in the global zone
                                return True
                        raise apx._convert_error(e)
                except apx.LinkedImageException as e:
                        if ignore_errors:
                                # default to being in the global zone
                                return True
                        raise e

                return self.__in_gz_cached

        def __zones_supported(self):
                """Check to see if zones are supported in the current image.
                i.e. can the current image have zone children."""

                # pylint: disable=E1120
                if DebugValues.get_value("zones_supported"):
                        return True
                # pylint: enable=E1120

                # first check if the image variant is global
                variant = "variant.opensolaris.zone"
                value = self.__img.cfg.variants[variant]
                if value != "global":
                        return False

                #
                # sanity check the path to to /etc/zones.  below we check for
                # the zones packages, and any image that has the zones
                # packages installed should have a /etc/zones file (since
                # those packages deliver this file) but it's possible that the
                # image was corrupted and the user now wants to be able to run
                # pkg commands to fix it.  if the path doesn't exist then we
                # don't have any zones so just report that zones are
                # unsupported (since zoneadm may fail to run anyway).
                #
                path = self.__img.root
                if not os.path.isdir(os.path.join(path, "etc")):
                        return False
                if not os.path.isdir(os.path.join(path, "etc/zones")):
                        return False

                # get a set of installed packages
                cati = self.__img.get_catalog(self.__img.IMG_CATALOG_INSTALLED)
                pkgs_inst = frozenset([
                        stem
                        # Unused variable 'pub'; pylint: disable=W0612
                        for pub, stem in cati.pkg_names()
                        # pylint: enable=W0612
                ])

                # check if the zones packages are installed
                for pkgs in self.__zone_pkgs:
                        if (pkgs & pkgs_inst) == pkgs:
                                return True

                return False

        def __list_zones_cached(self, nocache=False, ignore_errors=False):
                """List the zones associated with the current image.  Since
                this involves forking and running zone commands, cache the
                results."""

                # if nocache is set then delete any cached children
                if nocache:
                        self.__zoneadm_list_cache = None

                # try to return the cached children
                if self.__zoneadm_list_cache != None:
                        assert type(self.__zoneadm_list_cache) == list
                        return self.__zoneadm_list_cache

                # see if the target image supports zones
                if not self.__zones_supported():
                        self.__zoneadm_list_cache = []
                        return self.__list_zones_cached()

                # zones are only visible when running in the global zone
                if not self.__in_gz(ignore_errors=ignore_errors):
                        self.__zoneadm_list_cache = []
                        return self.__list_zones_cached()

                # find zones
                try:
                        zdict = _list_zones(self.__img.root,
                            self.__linked.get_path_transform())
                except OSError as e:
                        # W0212 Access to a protected member
                        # pylint: disable=W0212
                        if ignore_errors:
                                # don't cache the result
                                return []
                        raise apx._convert_error(e)
                except apx.LinkedImageException as e:
                        if ignore_errors:
                                # don't cache the result
                                return []
                        raise e

                # convert zone names into into LinkedImageName objects
                zlist = []
                # state is unused
                # pylint: disable=W0612
                for zone, (path, state) in six.iteritems(zdict):
                        lin = li.LinkedImageName("{0}:{1}".format(self.__pname,
                            zone))
                        zlist.append([lin, path])

                self.__zoneadm_list_cache = zlist
                return self.__list_zones_cached()

        def init_root(self, root):
                """See parent class for docstring."""
                # nuke any cached children
                self.__zoneadm_list_cache = None

        def guess_path_transform(self, ignore_errors=False):
                """See parent class for docstring."""

                zlist = self.__list_zones_cached(nocache=True,
                    ignore_errors=ignore_errors)
                if not zlist:
                        return li.PATH_TRANSFORM_NONE

                # only global zones can have zone children, and global zones
                # always execute with "/" as their root.  so if the current
                # image path is not "/", then assume we're in an alternate
                # root.
                root = self.__img.root.rstrip(os.sep) + os.sep
                return (os.sep, root)

        def get_child_list(self, nocache=False, ignore_errors=False):
                """See parent class for docstring."""

                inmemory = []
                # find any newly attached zone images
                for lin in self.__children:
                        path = self.__children[lin][li.PROP_PATH]
                        inmemory.append([lin, path])

                ondisk = []
                for (lin, path) in self.__list_zones_cached(nocache,
                    ignore_errors=ignore_errors):
                        if lin in [i[0] for i in inmemory]:
                                # we re-attached a zone in memory.
                                continue
                        ondisk.append([lin, path])

                rv = []
                rv.extend(ondisk)
                rv.extend(inmemory)

                for lin, path in rv:
                        assert lin.lin_type == self.__pname

                return rv

        def get_child_props(self, lin):
                """See parent class for docstring."""

                if lin in self.__children:
                        return self.__children[lin]

                props = dict()
                props[li.PROP_NAME] = lin
                for i_lin, i_path in self.get_child_list():
                        if lin == i_lin:
                                props[li.PROP_PATH] = i_path
                                break
                assert li.PROP_PATH in props

                props[li.PROP_MODEL] = li.PV_MODEL_PUSH
                for k, v in six.iteritems(self.attach_props_def):
                        if k not in props:
                                props[k] = v

                return props

        def attach_child_inmemory(self, props, allow_relink):
                """See parent class for docstring."""

                # make sure this child doesn't already exist
                lin = props[li.PROP_NAME]
                lin_list = [i[0] for i in self.get_child_list()]
                assert lin not in lin_list or allow_relink

                # cache properties (sans any temporarl ones)
                self.__children[lin] = li.rm_dict_ent(props, li.temporal_props)

        def detach_child_inmemory(self, lin):
                """See parent class for docstring."""

                # make sure this child exists
                assert lin in [i[0] for i in self.get_child_list()]

                # Delete this linked image
                del self.__children[lin]

        def sync_children_todisk(self):
                """See parent class for docstring."""

                # nothing to do
                return li.LI_RVTuple(pkgdefs.EXIT_OK, None, None)


class LinkedImageZoneChildPlugin(li.LinkedImageChildPlugin):
        """See parent class for docstring."""

        def __init__(self, lic):
                """See parent class for docstring."""
                li.LinkedImageChildPlugin.__init__(self, lic)

        def munge_props(self, props):
                """See parent class for docstring."""

                #
                # For zones we always update the pushed child image path to
                # be '/' (Since any linked children of the zone will be
                # relative to that zone's root).
                #
                props[li.PROP_PATH] = "/"


def _zonename():
        """Get the zonname of the current system."""

        cmd = DebugValues.get_value("bin_zonename") # pylint: disable=E1120
        if cmd is not None:
                cmd = [cmd]
        else:
                cmd = ["/bin/zonename"]

        # if the command doesn't exist then bail.
        if not li.path_exists(cmd[0]):
                return

        fout = tempfile.TemporaryFile()
        ferrout = tempfile.TemporaryFile()
        p = pkg.pkgsubprocess.Popen(cmd, stdout=fout, stderr=ferrout)
        p.wait()
        if (p.returncode != 0):
                cmd = " ".join(cmd)
                ferrout.seek(0)
                errout = "".join(ferrout.readlines())
                raise apx.LinkedImageException(
                    cmd_failed=(p.returncode, cmd, errout))

        # parse the command output
        fout.seek(0)
        l = fout.readlines()[0].rstrip()
        return l

def _zoneadm_list_parse(line, cmd, output):
        """Parse zoneadm list -p output.  It's possible for zonepath to
        contain a ":".  If it does it will be escaped to be "\:".  (But note
        that if the zonepath contains a "\" it will not be escaped, which
        is argubaly a bug.)"""

        # zoneadm list output should never contain a NUL char, so
        # temporarily replace any escaped colons with a NUL, split the string
        # on any remaining colons, and then switch any NULs back to colons.
        tmp_char = "\0"
        fields = [
                field.replace(tmp_char, ":")
                for field in line.replace("\:", tmp_char).split(":")
        ]

        try:
                # Unused variable; pylint: disable=W0612
                z_id, z_name, z_state, z_path, z_uuid, z_brand, z_iptype = \
                    fields[:7]
                # pylint: enable=W0612
        except ValueError:
                raise apx.LinkedImageException(
                    cmd_output_invalid=(cmd, output))

        return z_name, z_state, z_path, z_brand

def _list_zones(root, path_transform):
        """Get the zones associated with the image located at 'root'.  We
        return a dictionary where the keys are zone names and the values are
        tuples containing zone root path and current state. The global zone is
        excluded from the results. Solaris10 branded zones are excluded from the
        results."""

        rv = dict()
        cmd = DebugValues.get_value("bin_zoneadm") # pylint: disable=E1120
        if cmd is not None:
                cmd = [cmd]
        else:
                cmd = ["/usr/sbin/zoneadm"]

        # if the command doesn't exist then bail.
        if not li.path_exists(cmd[0]):
                return rv

        # make sure "root" has a trailing '/'
        root = root.rstrip(os.sep) + os.sep

        # create the zoneadm command line
        cmd.extend(["-R", str(root), "list", "-cp"])

        # execute zoneadm and save its output to a file
        fout = tempfile.TemporaryFile()
        ferrout = tempfile.TemporaryFile()
        p = pkg.pkgsubprocess.Popen(cmd, stdout=fout, stderr=ferrout)
        p.wait()
        if (p.returncode != 0):
                cmd = " ".join(cmd)
                ferrout.seek(0)
                errout = "".join(ferrout.readlines())
                raise apx.LinkedImageException(
                    cmd_failed=(p.returncode, cmd, errout))

        # parse the command output
        fout.seek(0)
        output = fout.readlines()
        for l in output:
                l = l.rstrip()

                z_name, z_state, z_path, z_brand = \
                    _zoneadm_list_parse(l, cmd, output)

                # skip brands that we don't care about
                # W0511 XXX / FIXME Comments; pylint: disable=W0511
                # XXX: don't hard code brand names, use a brand attribute
                # pylint: enable=W0511
                if z_brand not in ["ipkg", "solaris", "sn1", "labeled"]:
                        continue

                # we don't care about the global zone.
                if (z_name == "global"):
                        continue

                # append "/root" to zonepath
                z_rootpath = os.path.join(z_path, "root")
                assert z_rootpath.startswith(root), \
                    "zone path '{0}' doesn't begin with '{1}".format(
                    z_rootpath, root)

                # If there is a current path transform in effect then revert
                # the path reported by zoneadm to the original zone path.
                if li.path_transform_applied(z_rootpath, path_transform):
                        z_rootpath = li.path_transform_revert(z_rootpath,
                            path_transform)

                # we only care about zones that have been installed
                if z_state not in zone_installed_states:
                        continue

                rv[z_name] = (z_rootpath, z_state)

        return rv

def list_running_zones():
        """Return dictionary with currently running zones of the system in the
        following form:
                { zone_name : zone_path, ... }
        """

        zdict = _list_zones("/", li.PATH_TRANSFORM_NONE)
        rzdict = {}
        for z_name, (z_path, z_state) in six.iteritems(zdict):
                if z_state == ZONE_STATE_STR_RUNNING:
                        rzdict[z_name] = z_path

        return rzdict
