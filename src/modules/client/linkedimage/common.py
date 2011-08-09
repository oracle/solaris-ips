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
Linked image module classes.

The following classes for manipulating linked images are defined here:

        LinkedImage
        LinkedImageChild

The following template classes which linked image plugins should inherit from
are also defined here:

        LinkedImagePlugin
        LinkedImageChildPlugin

"""

#
# Too many lines in module; pylint: disable-msg=C0302
#

# standard python classes
import operator
import os
import simplejson as json
import sys
import tempfile

# pkg classes
import pkg.actions
import pkg.altroot as ar
import pkg.catalog
import pkg.client.api_errors as apx
import pkg.client.bootenv as bootenv
import pkg.client.linkedimage
import pkg.client.pkgdefs as pkgdefs
import pkg.client.pkgplan as pkgplan
import pkg.fmri
import pkg.misc as misc
import pkg.pkgsubprocess
import pkg.version

from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues

logger = global_settings.logger

# linked image relationship types (returned by LinkedImage.list_related())
REL_PARENT = "parent"
REL_SELF   = "self"
REL_CHILD  = "child"

# linked image properties
PROP_NAME           = "li-name"
PROP_ALTROOT        = "li-altroot"
PROP_PARENT_PATH    = "li-parent"
PROP_PATH           = "li-path"
PROP_MODEL          = "li-model"
PROP_RECURSE        = "li-recurse"
prop_values         = frozenset([
    PROP_ALTROOT,
    PROP_NAME,
    PROP_PATH,
    PROP_MODEL,
    PROP_PARENT_PATH,
    PROP_RECURSE,
])

# properties that never get saved
temporal_props = frozenset([
    PROP_ALTROOT,
])

# special linked image name values (PROP_NAME)
PV_NAME_NONE = "-"

# linked image model values (PROP_MODEL)
PV_MODEL_PUSH = "push"
PV_MODEL_PULL = "pull"
model_values = frozenset([
    PV_MODEL_PUSH,
    PV_MODEL_PULL,
])

# files which contain linked image data
__DATA_DIR     = "linked"
PATH_PPKGS     = os.path.join(__DATA_DIR, "linked_ppkgs")
PATH_PROP      = os.path.join(__DATA_DIR, "linked_prop")
PATH_PUBS      = os.path.join(__DATA_DIR, "linked_ppubs")

class LinkedImagePlugin(object):
        """This class is a template that all linked image plugins should
        inherit from.  Linked image plugins derived from this class are
        designed to manage linked aspects of the current image (vs managing
        linked aspects of a specific child of the current image).

        All the interfaces exported by this class and its descendants are
        private to the linked image subsystem and should not be called
        directly by any other subsystem."""

        # functionality flags
        support_attach = False
        support_detach = False

        def __init__(self, pname, linked):
                """Initialize a linked image plugin.

                'pname' is the name of the plugin class derived from this
                base class.

                'linked' is the LinkedImage object initializing this plugin.
                """

                return

        def init_root(self, old_altroot):
                """Called when the path to the image that we're operating on
                is changing.  This normally occurs when we clone an image
                after we've planned and prepared to do an operation."""

                # return value: None
                raise NotImplementedError

        def get_altroot(self, ignore_errors=False):
                """If the linked image plugin is able to detect that we're
                operating on an image in an alternate root then return the
                path of the alternate root."""

                # return value: string or None
                raise NotImplementedError

        def get_child_list(self, nocache=False, ignore_errors=False):
                """Return a list of the child images associated with the
                current image."""

                # return value: list
                raise NotImplementedError

        def get_child_props(self, lin):
                """Get the linked image properties associated with the
                specified child image."""

                # return value: dict
                raise NotImplementedError

        def attach_child_inmemory(self, props, allow_relink):
                """Attach the specified child image. This operation should
                only affect in-memory state of the current image. It should
                not update any persistent on-disk linked image state or access
                the child image in any way. This routine should assume that
                the linked image properties have already been validated."""

                # return value: None
                raise NotImplementedError

        def detach_child_inmemory(self, lin):
                """Detach the specified child image. This operation should
                only affect in-memory state of the current image. It should
                not update any persistent on-disk linked image state or access
                the child image in any way."""

                # return value: None
                raise NotImplementedError

        def sync_children_todisk(self):
                """Sync out the in-memory linked image state of this image to
                disk."""

                # return value: tuple:
                #    (pkgdefs EXIT_* return value, exception object or None)
                raise NotImplementedError


class LinkedImageChildPlugin(object):
        """This class is a template that all linked image child plugins should
        inherit from.  Linked image child plugins derived from this class are
        designed to manage linked aspects of children of the current image.
        (vs managing linked aspects of the current image itself).

        All the interfaces exported by this class and its descendants are
        private to the linked image subsystem and should not be called
        directly by any other subsystem."""

        def __init__(self, lic):
                """Initialize a linked image child plugin.

                'lic' is the LinkedImageChild object initializing this plugin.
                """

                return

        def munge_props(self, props):
                """Called before a parent image saves linked image properties
                into a child image.  Gives the linked image child plugin a
                chance to update the properties that will be saved within the
                child image."""

                # return value: None
                raise NotImplementedError


class LinkedImageName(object):
        """A class for naming child linked images.  Linked image names are
        used for all child images (and only child images), and they encode two
        pieces of information.  The name of the plugin used to manage the
        image and a linked image name.  Linked image names have the following
        format "<linked_image_plugin>:<linked_image_name>"""

        def __init__(self, name):
                assert type(name) == str

                self.lin_type = self.lin_name = None

                try:
                        self.lin_type, self.lin_name = name.split(":")
                except ValueError:
                        raise apx.LinkedImageException(lin_malformed=name)

                if len(self.lin_type) == 0 or len(self.lin_name) == 0 :
                        raise apx.LinkedImageException(lin_malformed=name)

                if self.lin_type not in pkg.client.linkedimage.p_types:
                        raise apx.LinkedImageException(lin_malformed=name)

        def __str__(self):
                return "%s:%s" % (self.lin_type, self.lin_name)

        def __len__(self):
                return len(self.__str__())

        def __cmp__(self, other):
                assert (type(self) == LinkedImageName)
                if not other:
                        return 1
                if other == PV_NAME_NONE:
                        return 1
                assert type(other) == LinkedImageName
                c = cmp(self.lin_type, other.lin_type)
                if c != 0:
                        return c
                c = cmp(self.lin_name, other.lin_name)
                return c

        def __hash__(self):
                return hash(str(self))

        def __eq__(self, other):
                if not isinstance(other, LinkedImageName):
                        return False

                return str(self) == str(other)

        def __ne__(self, other):
                return not self.__eq__(self, other)

class LinkedImage(object):
        """A LinkedImage object is used to manage the linked image aspects of
        an image.  This image could be a child image, a parent image, or both
        a parent and child.  This object allows for access to linked image
        properties and also provides routines that allow operations to be
        performed on child images."""

        # Too many instance attributes; pylint: disable-msg=R0902
        # Too many public methods; pylint: disable-msg=R0904

        # Properties that a parent image with push children should save locally.
        __parent_props = frozenset([
            PROP_PATH
        ])

        # Properties that a pull child image should save locally.
        __pull_child_props = frozenset([
            PROP_NAME,
            PROP_PATH,
            PROP_MODEL,
            PROP_PARENT_PATH,
        ])

        # Properties that a parent image with push children should save in
        # those children.
        __push_child_props = frozenset([
            PROP_NAME,
            PROP_PATH,
            PROP_MODEL,
            PROP_RECURSE,
        ])

        # make sure there is no invalid overlap
        assert not (temporal_props & (
            __parent_props |
            __pull_child_props |
            __push_child_props))

        def __init__(self, img):
                """Initialize a new LinkedImage object."""

                # globals
                self.__img = img

                # variables reset by self.__update_props()
                self.__props = dict()
                self.__ppkgs = frozenset()
                self.__ppubs = None
                self.__pimg = None

                # variables reset by self.reset_recurse()
                self.__lic_list = []

                # variables reset by self._init_root()
                self.__root = None
                self.__path_ppkgs = None
                self.__path_prop = None
                self.__path_ppubs = None

                # initialize with no properties
                self.__update_props()
                self.reset_recurse()

                # initialize linked image plugin objects
                self.__plugins = dict()
                for p in pkg.client.linkedimage.p_types:
                        self.__plugins[p] = \
                            pkg.client.linkedimage.p_classes[p](p, self)

                # if the image has a path setup, we can load data from it.
                if self.__img.imgdir:
                        self._init_root()

        @property
        def image(self):
                """Get a pointer to the image object associated with this
                linked image object."""
                return self.__img

        def _init_root(self):
                """Called during object initialization and by
                image.py`__set_root() to let us know when we're changing the
                root location of the image.  (The only time we change the root
                path is when changes BEs during operations which clone BEs.
                So when this happens most our metadata shouldn't actually
                change."""

                assert self.__img.root, \
                    "root = %s" % str(self.__img.root)
                assert self.__img.imgdir, \
                    "imgdir = %s" % str(self.__img.imgdir)

                # save the old root image path
                old_root = None
                if self.__root:
                        old_root = self.__root

                # figure out the new root image path
                new_root = self.__img.root.rstrip(os.sep)
                if new_root == "":
                        new_root = os.sep

                # initialize paths for linked image data files
                self.__root = new_root
                imgdir = self.__img.imgdir.rstrip(os.sep)
                self.__path_ppkgs = os.path.join(imgdir, PATH_PPKGS)
                self.__path_prop = os.path.join(imgdir, PATH_PROP)
                self.__path_ppubs = os.path.join(imgdir, PATH_PUBS)

                # if this isn't a reset, then load data from the image
                if not old_root:
                        self.__load()

                # we're not linked or we're not changing root paths we're done
                if not old_root or not self.__props:
                        return

                # get the old altroot directory
                old_altroot = self.altroot()

                # update the altroot property
                self.__set_altroot(self.__props, old_root=old_root)

                # Tell linked image plugins about the updated paths
                # Unused variable 'plugin'; pylint: disable-msg=W0612
                for plugin, lip in self.__plugins.iteritems():
                # pylint: enable-msg=W0612
                        lip.init_root(old_altroot)

                # Tell linked image children about the updated paths
                for lic in self.__lic_list:
                        lic.child_init_root(old_altroot)

        def __update_props(self, props=None):
                """Internal helper routine used when we want to update any
                linked image properties.  This routine sanity check the
                new properties, updates them, and resets any cached state
                that is affected by property values."""

                if props == None:
                        props = dict()
                elif props:
                        self.__verify_props(props)

                        # all temporal properties must exist
                        assert (temporal_props - set(props)) == set(), \
                            "%s - %s == set()" % (temporal_props, set(props))

                # update state
                self.__props = props
                self.__ppkgs = frozenset()
                self.__ppubs = None
                self.__pimg = None

        def __verify_props(self, props):
                """Perform internal consistency checks for a set of linked
                image properties.  Don't update any state."""

                props_set = set(props)

                # if we're not a child image ourselves, then we're done
                if (props_set - temporal_props) == self.__parent_props:
                        return props

                # make sure PROP_MODEL was specified
                if PROP_NAME not in props:
                        _rterr(path=self.__root,
                            missing_props=[PROP_NAME])

                # validate the linked image name
                try:
                        lin = LinkedImageName(str(props[PROP_NAME]))
                except apx.LinkedImageException:
                        _rterr(path=self.__root,
                            bad_prop=(PROP_NAME, props[PROP_NAME]))

                if lin.lin_type not in self.__plugins:
                        _rterr(path=self.__root, lin=lin,
                            bad_lin_type=lin.lin_type)

                # make sure PROP_MODEL was specified
                if PROP_MODEL not in props:
                        _rterr(path=self.__root, lin=lin,
                            missing_props=[PROP_MODEL])

                model = props[PROP_MODEL]
                if model not in model_values:
                        _rterr(path=self.__root, lin=lin,
                            bad_prop=(PROP_MODEL, model))

                if model == PV_MODEL_PUSH:
                        missing = self.__push_child_props - props_set
                        if missing:
                                _rterr(path=self.__root, lin=lin,
                                    missing_props=missing)

                if model == PV_MODEL_PULL:
                        missing = self.__pull_child_props - props_set
                        if missing:
                                _rterr(path=self.__root, lin=lin,
                                    missing_props=missing)

        @staticmethod
        def __unset_altroot(props):
                """Given a set of linked image properties, strip out any
                altroot properties.  This involves removing the altroot
                component from the image path property.  This is normally done
                before we write image properties to disk."""

                # get the current altroot
                altroot = props[PROP_ALTROOT]

                # remove it from the image path
                props[PROP_PATH] = rm_altroot_path(
                    props[PROP_PATH], altroot)

                if PROP_PARENT_PATH in props:
                        # remove it from the parent image path
                        props[PROP_PARENT_PATH] = rm_altroot_path(
                            props[PROP_PARENT_PATH], altroot)

                # delete the current altroot
                del props[PROP_ALTROOT]

        def __set_altroot(self, props, old_root=None):
                """Given a set of linked image properties, the image paths
                stored within those properties may not match the actual image
                paths if we're executing within an alternate root environment.
                We try to detect this condition here, and if this situation
                occurs we update the linked image paths to reflect the current
                image paths and we fabricate a new linked image altroot
                property that points to the new path prefix that was
                pre-pended to the image paths."""

                # we may have to update the parent image path as well
                p_path = None
                if PROP_PARENT_PATH in props:
                        p_path = props[PROP_PARENT_PATH]

                if old_root:
                        # get the old altroot
                        altroot = props[PROP_ALTROOT]

                        # remove the altroot from the image paths
                        path = rm_altroot_path(old_root, altroot)
                        if p_path:
                                p_path = rm_altroot_path(p_path, altroot)

                        # get the new altroot
                        altroot = get_altroot_path(self.__root, path)
                else:
                        path = props[PROP_PATH]
                        altroot = get_altroot_path(self.__root, path)

                # update properties with altroot
                props[PROP_ALTROOT] = altroot
                props[PROP_PATH] = add_altroot_path(path, altroot)
                if p_path:
                        props[PROP_PARENT_PATH] = \
                            add_altroot_path(p_path, altroot)

        def __guess_altroot(self, ignore_errors=False):
                """If we're initializing parent linked image properties for
                the first time (or if those properties somehow got deleted)
                then we need to know if the parent image that we're currently
                operating on is located within an alternate root.  One way to
                do this is to ask our linked image plugins if they can
                determine this (the zones linked image plugin usually can
                if the image is a global zone)."""

                # ask each plugin if we're operating in an alternate root
                p_altroots = []
                for plugin, lip in self.__plugins.iteritems():
                        p_altroot = lip.get_altroot(
                            ignore_errors=ignore_errors)
                        if p_altroot:
                                p_altroots.append((plugin, p_altroot))

                if not p_altroots:
                        # no altroot suggested by plugins
                        return os.sep

                # check for conflicting altroots
                altroots = list(set([
                        p_altroot
                        # Unused variable; pylint: disable-msg=W0612
                        for pname, p_altroot in p_altroots
                        # pylint: enable-msg=W0612
                ]))

                if len(altroots) == 1:
                        # we have an altroot from our plugins
                        return altroots[0]

                # we have conflicting altroots, time to die
                _rterr(li=self, multiple_altroots=p_altroots)

        def __fabricate_parent_props(self, ignore_errors=False):
                """Fabricate the minimum set of properties required for a
                parent image."""

                props = dict()
                props[PROP_PATH] = self.__img.root
                props[PROP_ALTROOT] = self.__guess_altroot(
                    ignore_errors=ignore_errors)
                return props

        def __load_ondisk_props(self, tmp=True):
                """Load linked image properties from disk and return them to
                the caller.  We sanity check the properties, but we don't
                update any internal linked image state.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                path = self.__path_prop
                path_tmp = "%s.%d" % (self.__path_prop, self.__img.runid)

                # read the linked image properties from disk
                if tmp and path_exists(path_tmp):
                        path = path_tmp
                        props = load_data(path)
                elif path_exists(path):
                        props = load_data(path)
                else:
                        return None

                # make sure there are no saved temporal properties
                assert not (set(props) & temporal_props)

                if PROP_NAME in props:
                        # convert PROP_NAME into a linked image name obj
                        name = props[PROP_NAME]
                        try:
                                lin = LinkedImageName(name)
                                props[PROP_NAME] = lin
                        except apx.LinkedImageException:
                                _rterr(path=self.__root,
                                    bad_prop=(PROP_NAME, name))

                # sanity check our properties
                self.__verify_props(props)
                return props

        def __load_ondisk_ppkgs(self, tmp=True):
                """Load linked image parent constraints from disk.
                Don't update any internal state.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                path = "%s.%d" % (self.__path_ppkgs, self.__img.runid)
                if tmp and path_exists(path):
                        return frozenset([
                            pkg.fmri.PkgFmri(str(s))
                            for s in load_data(path, missing_val=misc.EmptyI)
                        ])

                path = self.__path_ppkgs
                if path_exists(path):
                        return frozenset([
                            pkg.fmri.PkgFmri(str(s))
                            for s in load_data(path, missing_val=misc.EmptyI)
                        ])

                return None

        def __load_ondisk_ppubs(self, tmp=True):
                """Load linked image parent publishers from disk.
                Don't update any internal state.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                path = "%s.%d" % (self.__path_ppubs, self.__img.runid)
                if tmp and path_exists(path):
                        return load_data(path)

                path = self.__path_ppubs
                if path_exists(path):
                        return load_data(path)

                return None

        def __load(self):
                """Load linked image properties and constraints from disk.
                Update the linked image internal state with the loaded data."""

                #
                # Normally, if we're a parent image we'll have linked image
                # properties stored on disk.  So load those now.
                #
                # If no properties are loaded, we may still be a parent image
                # that is just missing it's metadata.  (oops.)  We attempt to
                # detect this situation by invoking __isparent(), which will
                # ask each child if there are any children.  This is a best
                # effort attempt, so when we do this we ignore any plugin
                # runtime errors since we really want Image object
                # initialization to succeed.  If we don't have any linked
                # image metadata, and we're having runtime errors querying for
                # children, then we'll allow initialization here, but any
                # subsequent operation that tries to access children will fail
                # and the caller will have to specify that they want to ignore
                # all children to allow the operation to succeed.
                #
                props = self.__load_ondisk_props()
                if not props and not self.__isparent(ignore_errors=True):
                        # we're not linked
                        return

                if not props:
                        #
                        # Oops.  We're a parent image with no properties
                        # stored on disk.  Rather than throwing an exception
                        # try to fabricate up some props with reasonably
                        # guessed values which the user can subsequently
                        # change and/or fix.
                        #
                        props = self.__fabricate_parent_props(
                            ignore_errors=True)
                else:
                        self.__set_altroot(props)

                self.__update_props(props)

                ppkgs = self.__load_ondisk_ppkgs()
                if self.ischild() and ppkgs == None:
                        _rterr(li=self, err="Constraints data missing.")
                if self.ischild():
                        self.__ppkgs = ppkgs

                # load parent publisher data. if publisher data is missing
                # continue along and we'll just skip the publisher checks,
                # it's better than failing and preventing any image updates.
                self.__ppubs = self.__load_ondisk_ppubs()

        @staticmethod
        def __validate_prop_recurse(v):
                """Verify property value for PROP_RECURSE."""
                if v in [True, False]:
                        return True
                if type(v) == str and v.lower() in ["true", "false"]:
                        return True
                return False

        def __validate_attach_props(self, model, props):
                """Validate user supplied linked image attach properties.
                Don't update any internal state."""

                # make sure that only attach time options have been
                # specified, and that they have allowed values.
                validate_props = {
                        PROP_RECURSE: self.__validate_prop_recurse
                }

                if model == PV_MODEL_PUSH:
                        allowed_props = self.__push_child_props
                else:
                        assert model == PV_MODEL_PULL
                        allowed_props = self.__pull_child_props

                errs = []

                # check each property the user specified.
                for k, v in props.iteritems():

                        # did the user specify an allowable property?
                        if k not in validate_props:
                                errs.append(apx.LinkedImageException(
                                    attach_bad_prop=k))
                                continue

                        # did the user specify a valid property value?
                        if not validate_props[k](v):
                                errs.append(apx.LinkedImageException(
                                    attach_bad_prop_value=(k, v)))
                                continue

                        # is this property valid for this type of image?
                        if k not in allowed_props:
                                errs.append(apx.LinkedImageException(
                                    attach_bad_prop=k))
                                continue

                if errs:
                        raise apx.LinkedImageException(bundle=errs)

        def __init_pimg(self, path):
                """Initialize an Image object which can be used to access a
                parent image."""

                try:
                        os.stat(path)
                except OSError:
                        raise apx.LinkedImageException(parent_bad_path=path)

                try:
                        pimg = self.__img.alloc(
                            root=path,
                            runid=self.__img.runid,
                            user_provided_dir=True,
                            cmdpath=self.__img.cmdpath)
                except apx.ImageNotFoundException:
                        raise apx.LinkedImageException(parent_bad_img=path)

                return pimg

        def altroot(self):
                """Return the altroot path prefix for the current image."""

                return self.__props.get(PROP_ALTROOT, os.sep)

        def nothingtodo(self):
                """If our in-memory linked image state matches the on-disk
                linked image state then there's nothing to do.  If the state
                differs then there is stuff to do since the new state needs
                to be saved to disk."""

                # compare in-memory and on-disk properties
                li_ondisk_props = self.__load_ondisk_props(tmp=False)
                if li_ondisk_props == None:
                        li_ondisk_props = dict()
                li_inmemory_props = self.__props.copy()
                if li_inmemory_props:
                        self.__unset_altroot(li_inmemory_props)
                li_inmemory_props = rm_dict_ent(li_inmemory_props,
                    temporal_props)
                if li_ondisk_props != li_inmemory_props:
                        return False

                # compare in-memory and on-disk constraints
                li_ondisk_ppkgs = self.__load_ondisk_ppkgs(tmp=False)
                if li_ondisk_ppkgs == None:
                        li_ondisk_ppkgs = frozenset()
                if self.__ppkgs != li_ondisk_ppkgs:
                        return False

                # compare in-memory and on-disk parent publishers
                li_ondisk_ppubs = self.__load_ondisk_ppubs(tmp=False)
                if self.__ppubs != li_ondisk_ppubs:
                        return False

                return True

        def get_pubs(self, img=None):
                """Return publisher information for the specified image.  If
                no image is specified we return publisher information for the
                current image.

                Publisher information is returned in a sorted list of lists
                of the format:
                        <publisher name>, <sticky>

                Where:
                        <publisher name> is a string
                        <sticky> is a boolean

                The tuples are sorted by publisher rank.
                """

                # default to ourselves
                if img == None:
                        img = self.__img

                # get a sorted list of the images publishers
                pubs = img.get_sorted_publishers(inc_disabled=False)

                rv = []
                for p in pubs:
                        rv.append([str(p), p.sticky])
                return rv

        def check_pubs(self, op):
                """If we're a child image's, verify that the parent image
                publisher configuration is a subset of the child images
                publisher configuration.  This means that all publishers
                configured within the parent image must also be configured
                within the child image with the same:

                        - publisher rank
                        - sticky and disabled settings

                The child image may have additional publishers configured but
                they must all be lower ranked than the parent's publishers.
                """

                # if we're not a child image then bail
                if not self.ischild():
                        return

                # if we're using the sysrepo then don't bother
                if self.__img.cfg.get_policy("use-system-repo"):
                        return

                if op in [pkgdefs.API_OP_DETACH]:
                        # we don't need to do a pubcheck for detach
                        return

                pubs = self.get_pubs()
                ppubs = self.__ppubs

                if ppubs == None:
                        # parent publisher data is missing, press on and hope
                        # for the best.
                        return

                # child image needs at least as many publishers as the parent
                if len(pubs) < len(ppubs):
                        raise apx.PlanCreationException(
                            linked_pub_error=(pubs, ppubs))

                # check rank, sticky, and disabled settings
                for (p, pp) in zip(pubs, ppubs):
                        if p == pp:
                                continue
                        raise apx.PlanCreationException(
                            linked_pub_error=(pubs, ppubs))

        def syncmd_from_parent(self, op=None):
                """Update linked image constraint, publisher data, and
                state from our parent image."""

                if not self.ischild():
                        # we're not a child image, nothing to do
                        return

                if self.__props[PROP_MODEL] == PV_MODEL_PUSH:
                        # parent pushes data to us, nothing to do
                        return

                # initalize the parent image
                if not self.__pimg:
                        path = self.__props[PROP_PARENT_PATH]
                        self.__pimg = self.__init_pimg(path)

                # generate new constraints
                cati = self.__pimg.get_catalog(self.__img.IMG_CATALOG_INSTALLED)
                ppkgs = frozenset(cati.fmris())

                # generate new publishers
                ppubs = self.get_pubs(img=self.__pimg)

                # check if anything has changed
                need_sync = False

                if self.__ppkgs != ppkgs:
                        # we have new constraints
                        self.__ppkgs = ppkgs
                        need_sync = True

                if self.__ppubs != ppubs:
                        # parent has new publishers
                        self.__ppubs = ppubs
                        need_sync = True

                if not need_sync:
                        # nothing changed
                        return

                # if we're not planning an image attach operation then write
                # the linked image metadata to disk.
                if op != pkgdefs.API_OP_ATTACH:
                        self.syncmd()

        def syncmd(self):
                """Write in-memory linked image state to disk."""

                # create a list of metadata file paths
                paths = [self.__path_ppkgs, self.__path_prop,
                    self.__path_ppubs]

                # cleanup any temporary files
                for path in paths:
                        path = "%s.%d" % (path, self.__img.runid)
                        path_unlink(path, noent_ok=True)

                if not self.ischild() and not self.isparent():
                        # we're no longer linked; delete metadata
                        for path in paths:
                                path_unlink(path, noent_ok=True)
                        return

                # save our properties, but first remove altroot path prefixes
                # and any temporal properties
                props = self.__props.copy()
                self.__unset_altroot(props)
                props = rm_dict_ent(props, temporal_props)
                save_data(self.__path_prop, props)

                if not self.ischild():
                        # if we're not a child we don't have constraints
                        path_unlink(self.__path_ppkgs, noent_ok=True)
                        return

                # we're a child so save our latest constraints
                save_data(self.__path_ppkgs, self.__ppkgs)
                save_data(self.__path_ppubs, self.__ppubs)

        @property
        def child_name(self):
                """If the current image is a child image, this function
                returns a linked image name object which represents the name
                of the current image."""

                if not self.ischild():
                        raise self.__apx_not_child()
                return self.__props[PROP_NAME]

        def ischild(self):
                """Indicates whether the current image is a child image."""

                return PROP_NAME in self.__props

        def __isparent(self, ignore_errors=False):
                """Indicates whether the current image is a parent image.

                'ignore_plugin_errors' ignore plugin runtime errors when
                trying to determine if we're a parent image.
                """

                return len(self.__list_children(
                    ignore_errors=ignore_errors)) > 0

        def isparent(self):
                """Indicates whether the current image is a parent image."""

                return self.__isparent()

        def child_props(self, lin=None):
                """Return a dictionary which represents the linked image
                properties associated with a linked image.

                'lin' is the name of the child image.  If lin is None then
                the current image is assumed to be a linked image and it's
                properties are returned.

                Always returns a copy of the properties in case the caller
                tries to update them."""

                if lin == None:
                        # If we're not linked we'll return an empty
                        # dictionary.  That's ok.
                        return self.__props.copy()

                # make sure the specified child exists
                self.__verify_child_name(lin, raise_except=True)

                # make a copy of the props in case they are updated
                lip = self.__plugins[lin.lin_type]
                props = lip.get_child_props(lin).copy()

                # add temporal properties
                props[PROP_ALTROOT] = self.altroot()
                return props

        def __apx_not_child(self):
                """Raise an exception because the current image is not a child
                image."""

                return apx.LinkedImageException(self_not_child=self.__root)

        def __verify_child_name(self, lin, raise_except=False):
                """Check if a specific child image exists."""

                assert type(lin) == LinkedImageName, \
                    "%s == LinkedImageName" % type(lin)

                for i in self.__list_children():
                        if i[0] == lin:
                                return True

                if raise_except:
                        raise apx.LinkedImageException(child_unknown=lin)
                return False

        def parent_fmris(self):
                """A set of the fmris installed in our parent image."""

                if not self.ischild():
                        # We return None since frozenset() would indicate
                        # that there are no packages installed in the parent
                        # image.
                        return None

                return self.__ppkgs

        def parse_name(self, name, allow_unknown=False):
                """Given a string representing a linked image child name,
                returns linked image name object representing the same name.

                'allow_unknown' indicates whether the name must represent
                actual children or simply be syntactically correct."""

                assert type(name) == str

                lin = LinkedImageName(name)
                if not allow_unknown:
                        self.__verify_child_name(lin, raise_except=True)
                return lin

        def __list_children(self, li_ignore=None, ignore_errors=False):
                """Returns a list of linked child images associated with the
                current image.

                'li_ignore' see list_related() for a description.

                The returned value is a list of tuples where each tuple
                contains (<li name>, <li path>)."""

                if li_ignore == []:
                        # ignore all children
                        return []

                li_children = [
                    entry
                    for p in pkg.client.linkedimage.p_types
                    for entry in self.__plugins[p].get_child_list(
                        ignore_errors=ignore_errors)
                ]

                # sort by linked image name
                li_children = sorted(li_children, key=operator.itemgetter(0))

                if li_ignore == None:
                        # don't ignore any children
                        return li_children

                li_all = set([lin for lin, path in li_children])
                errs = [
                    apx.LinkedImageException(child_unknown=lin)
                    for lin in (set(li_ignore) - li_all)
                ]
                if errs:
                        raise apx.LinkedImageException(bundle=errs)

                return [
                    (lin, path)
                    for lin, path in li_children
                    if lin not in li_ignore
                ]

        def list_related(self, li_ignore=None):
                """Returns a list of linked images associated with the
                current image.  This includes both child and parent images.

                'li_ignore' is either None or a list.  If it's None (the
                default), all children will be listed.  If it's an empty list
                no children will be listed.  Otherwise, any children listed
                in li_ignore will be ommited from the results.

                The returned value is a list of tuples where each tuple
                contains (<li name>, <relationship>, <li path>)."""

                li_children = self.__list_children(li_ignore=li_ignore)
                li_list = [
                    (lin, REL_CHILD, path)
                    for lin, path in li_children
                ]

                if not li_list and not self.ischild():
                        # we're not linked
                        return []

                # we're linked so append ourself to the list
                lin = PV_NAME_NONE
                if self.ischild():
                        lin = self.child_name
                li_self = (lin, REL_SELF, self.__props[PROP_PATH])
                li_list.append(li_self)

                # if we have a path to our parent then append that as well.
                if PROP_PARENT_PATH in self.__props:
                        li_parent = (PV_NAME_NONE, REL_PARENT,
                            self.__props[PROP_PARENT_PATH])
                        li_list.append(li_parent)

                # sort by linked image name
                li_list = sorted(li_list, key=operator.itemgetter(0))

                return li_list

        def attach_parent(self, lin, path, props, allow_relink=False,
            force=False):
                """We only update in-memory state; nothing is written to
                disk, to sync linked image state to disk call syncmd."""

                assert type(lin) == LinkedImageName
                assert type(path) == str
                assert props == None or type(props) == dict, \
                    "type(props) == %s" % type(props)
                if props == None:
                        props = dict()

                lip = self.__plugins[lin.lin_type]

                if self.ischild() and not allow_relink:
                        raise apx.LinkedImageException(self_linked=self.__root)

                if not lip.support_attach and not force:
                        raise apx.LinkedImageException(
                            attach_parent_notsup=lin.lin_type)

                # Path must be an absolute path.
                if not os.path.isabs(path):
                        raise apx.LinkedImageException(parent_path_notabs=path)

                # we don't bother to cleanup the path to the parent image here
                # because when we allocate an Image object for the parent
                # image, it will do that work for us.
                pimg = self.__init_pimg(path)

                # make sure we're not linking to ourselves
                if self.__img.root == pimg.root:
                        raise apx.LinkedImageException(link_to_self=True)

                # make sure we're not linking the root image as a child
                if self.__img.root == misc.liveroot():
                        raise apx.LinkedImageException(
                            attach_root_as_child=True)

                # get the cleaned up parent image path.
                path = pimg.root

                # If we're in an alternate root, the parent must also be within
                # that alternate root.
                if not check_altroot_path(path, self.altroot()):
                        raise apx.LinkedImageException(
                            parent_not_in_altroot=(path, self.altroot()))

                self.__validate_attach_props(PV_MODEL_PULL, props)

                # make a copy of the properties
                props = props.copy()
                props[PROP_NAME] = lin
                props[PROP_PARENT_PATH] = path
                props[PROP_PATH] = self.__img.root
                props[PROP_MODEL] = PV_MODEL_PULL
                props[PROP_ALTROOT] = self.altroot()

                for k, v in lip.attach_props_def.iteritems():
                        if k not in self.__pull_child_props:
                                # this prop doesn't apply to pull images
                                continue
                        if k not in props:
                                props[k] = v

                self.__update_props(props)
                self.__pimg = pimg

        def detach_parent(self, force=False):
                """We only update in memory state; nothing is written to
                disk, to sync linked image state to disk call syncmd."""

                lin = self.child_name
                lip = self.__plugins[lin.lin_type]
                if not force:
                        if self.__props[PROP_MODEL] == PV_MODEL_PUSH:
                                raise apx.LinkedImageException(
                                    detach_from_parent=self.__root)

                        if not lip.support_detach:
                                raise apx.LinkedImageException(
                                    detach_parent_notsup=lin.lin_type)

                # Generate a new set of linked image properties.  If we have
                # no children then we don't need any more properties.
                props = None

                # If we have children we'll need to keep some properties.
                if self.isparent():
                        strip = prop_values - \
                            (self.__parent_props | temporal_props)
                        props = rm_dict_ent(self.__props, strip)

                # Update our linked image properties.
                self.__update_props(props)

        def __insync(self):
                """Determine if an image is in sync with its constraints."""

                assert self.ischild()

                cat = self.__img.get_catalog(self.__img.IMG_CATALOG_INSTALLED)
                excludes = [ self.__img.cfg.variants.allow_action ]

                sync_fmris = []

                for fmri in cat.fmris():
                        # get parent dependencies from the catalog
                        parent_deps = [
                            a
                            for a in cat.get_entry_actions(fmri,
                                [pkg.catalog.Catalog.DEPENDENCY],
                                excludes=excludes)
                            if a.name == "depend" and \
                                a.attrs["type"] == "parent"
                        ]

                        if parent_deps:
                                sync_fmris.append(fmri)

                if not sync_fmris:
                        # No packages to sync
                        return True

                # create a dictionary of packages installed in the parent
                ppkgs_dict = dict([
                        (fmri.pkg_name, fmri)
                        for fmri in self.parent_fmris()
                ])

                for fmri in sync_fmris:
                        if fmri.pkg_name not in ppkgs_dict:
                                return False
                        pfmri = ppkgs_dict[fmri.pkg_name]
                        if fmri.version != pfmri.version and \
                            not pfmri.version.is_successor(fmri.version,
                                pkg.version.CONSTRAINT_AUTO):
                                return False
                return True

        def audit_self(self, li_parent_sync=True):
                """If the current image is a child image, this function
                audits the current image to see if it's in sync with its
                parent."""

                if not self.ischild():
                        return (pkgdefs.EXIT_OOPS, self.__apx_not_child(), None)

                try:
                        if li_parent_sync:
                                # try to refresh linked image constraints from
                                # the parent image.
                                self.syncmd_from_parent()

                except apx.LinkedImageException, e:
                        return (e.lix_exitrv, e, None)

                if not self.__insync():
                        e = apx.LinkedImageException(
                            child_diverged=self.child_name)
                        return (pkgdefs.EXIT_DIVERGED, e, None)

                return (pkgdefs.EXIT_OK, None, None)

        @staticmethod
        def __rvdict2rv(rvdict, rv_map=None):
                """Internal helper function that takes a dictionary returned
                from an operations on multiple children and merges the results
                into a single return code."""

                assert not rvdict or type(rvdict) == dict
                for k, (rv, err, p_dict) in rvdict.iteritems():
                        assert type(k) == LinkedImageName
                        assert type(rv) == int
                        assert err is None or \
                            isinstance(err, apx.LinkedImageException)
                        assert p_dict is None or isinstance(p_dict, dict)
                if type(rv_map) != type(None):
                        assert type(rv_map) == list
                        for (rv_set, rv) in rv_map:
                                assert(type(rv_set) == set)
                                assert(type(rv) == int)

                if not rvdict:
                        return (pkgdefs.EXIT_OK, None, None)

                if not rv_map:
                        rv_map = [(set([pkgdefs.EXIT_OK]), pkgdefs.EXIT_OK)]

                p_dicts = [
                    p_dict for (rv, e, p_dict) in rvdict.itervalues()
                    if p_dict is not None
                ]

                rv_mapped = set()
                rv_seen = set([rv for (rv, e, p_dict) in rvdict.itervalues()])
                for (rv_map_set, rv_map_rv) in rv_map:
                        if (rv_seen == rv_map_set):
                                return (rv_map_rv, None, p_dicts)
                        # keep track of all the return values that are mapped
                        rv_mapped |= rv_map_set

                # the mappings better have included pkgdefs.EXIT_OK
                assert pkgdefs.EXIT_OK in rv_mapped

                # if we had errors for unmapped return values, bundle them up
                errs = [
                        e
                        for (rv, e, p_dict) in rvdict.itervalues()
                        if e and rv not in rv_mapped
                ]
                if errs:
                        err = apx.LinkedImageException(bundle=errs)
                else:
                        err = None

                if len(rv_seen) == 1:
                        # we have one consistent return value
                        return (list(rv_seen)[0], err, p_dicts)

                return (pkgdefs.EXIT_PARTIAL, err, p_dicts)

        def audit_rvdict2rv(self, rvdict):
                """Convenience function that takes a dictionary returned from
                an operations on multiple children and merges the results into
                a single return code."""

                rv_map = [
                    (set([pkgdefs.EXIT_OK]), pkgdefs.EXIT_OK),
                    (set([pkgdefs.EXIT_DIVERGED]), pkgdefs.EXIT_DIVERGED),
                    (set([pkgdefs.EXIT_OK, pkgdefs.EXIT_DIVERGED]),
                        pkgdefs.EXIT_DIVERGED),
                ]
                return self.__rvdict2rv(rvdict, rv_map)

        def sync_rvdict2rv(self, rvdict):
                """Convenience function that takes a dictionary returned from
                an operations on multiple children and merges the results into
                a single return code."""

                rv_map = [
                    (set([pkgdefs.EXIT_OK]), pkgdefs.EXIT_OK),
                    (set([pkgdefs.EXIT_OK, pkgdefs.EXIT_NOP]), pkgdefs.EXIT_OK),
                    (set([pkgdefs.EXIT_NOP]), pkgdefs.EXIT_NOP),
                ]
                return self.__rvdict2rv(rvdict, rv_map)

        def detach_rvdict2rv(self, rvdict):
                """Convenience function that takes a dictionary returned from
                an operations on multiple children and merges the results into
                a single return code."""

                return self.__rvdict2rv(rvdict)

        def __validate_child_attach(self, lin, path, props,
            allow_relink=False):
                """Sanity check the parameters associated with a child image
                that we are trying to attach."""

                assert type(lin) == LinkedImageName
                assert type(props) == dict
                assert type(path) == str

                # check the name to make sure it doesn't already exist
                if self.__verify_child_name(lin) and not allow_relink:
                        raise apx.LinkedImageException(child_dup=lin)

                self.__validate_attach_props(PV_MODEL_PUSH, props)

                # Path must be an absolute path.
                if not os.path.isabs(path):
                        raise apx.LinkedImageException(child_path_notabs=path)

                # If we're in an alternate root, the child must also be within
                # that alternate root
                if not check_altroot_path(path, self.altroot()):
                        raise apx.LinkedImageException(
                            child_not_in_altroot=(path, self.altroot()))

                # path must be an image
                try:
                        img_prefix = ar.ar_img_prefix(path)
                except OSError:
                        raise apx.LinkedImageException(child_path_eaccess=path)
                if not img_prefix:
                        raise apx.LinkedImageException(child_bad_img=path)

                # Does the parent image (ourselves) reside in clonable BE?
                # Unused variable 'be_uuid'; pylint: disable-msg=W0612
                (be_name, be_uuid) = bootenv.BootEnv.get_be_name(self.__root)
                # pylint: enable-msg=W0612
                if be_name:
                        img_is_clonable = True
                else:
                        img_is_clonable = False

                # If the parent image is clonable then the new child image
                # must be nested within the parents filesystem namespace.
                path = path.rstrip(os.sep) + os.sep
                p_root = self.__root.rstrip(os.sep) + os.sep
                if img_is_clonable and not path.startswith(p_root):
                        raise apx.LinkedImageException(
                            child_not_nested=(path, p_root))

                # Find the common parent directory of the both parent and the
                # child image.
                dir_common = os.path.commonprefix([p_root, path])
                dir_common.rstrip(os.sep)

                # Make sure there are no additional images in between the
                # parent and the child. (Ie, prevent linking of images if one
                # of the images is nested within another unrelated image.)
                # This is done by looking at all the parent directories for
                # both the parent and the child image until we reach a common
                # ancestor.

                # First check the parent directories of the child.
                d = os.path.dirname(path.rstrip(os.sep))
                while d != dir_common and d.startswith(dir_common):
                        try:
                                tmp = ar.ar_img_prefix(d)
                        except OSError, e:
                                # W0212 Access to a protected member
                                # pylint: disable-msg=W0212
                                raise apx._convert_error(e)
                        if not tmp:
                                d = os.path.dirname(d)
                                continue
                        raise apx.LinkedImageException(child_nested=(path, d))

                # Then check the parent directories of the parent.
                d = os.path.dirname(p_root.rstrip(os.sep))
                while d != dir_common and d.startswith(dir_common):
                        try:
                                tmp = ar.ar_img_prefix(d)
                        except OSError, e:
                                # W0212 Access to a protected member
                                # pylint: disable-msg=W0212
                                raise apx._convert_error(e)
                        if not tmp:
                                d = os.path.dirname(d)
                                continue
                        raise apx.LinkedImageException(child_nested=(path, d))

                # Child image should not already be linked
                img_li_data_props = os.path.join(img_prefix, PATH_PROP)
                try:
                        exists = ar.ar_exists(path, img_li_data_props)
                except OSError, e:
                        # W0212 Access to a protected member
                        # pylint: disable-msg=W0212
                        raise apx._convert_error(e)
                if exists and not allow_relink:
                        raise apx.LinkedImageException(img_linked=path)

        def attach_child(self, lin, path, props,
            accept=False, allow_relink=False, force=False, li_md_only=False,
            li_pkg_updates=True, noexecute=False,
            progtrack=None, refresh_catalogs=True, reject_list=misc.EmptyI,
            show_licenses=False, update_index=True):
                """Attach an image as a child to the current image (the
                current image will become a parent image. This operation
                results in attempting to sync the child image with the parent
                image.

                For descriptions of parameters please see the descriptions in
                api.py`gen_plan_*"""

                # Too many arguments; pylint: disable-msg=R0913
                # Too many return statements; pylint: disable-msg=R0911
                assert type(lin) == LinkedImageName
                assert type(path) == str
                assert props == None or type(props) == dict, \
                    "type(props) == %s" % type(props)
                if props == None:
                        props = dict()

                lip = self.__plugins[lin.lin_type]
                if not lip.support_attach and not force:
                        e = apx.LinkedImageException(
                            attach_child_notsup=lin.lin_type)
                        return (e.lix_exitrv, e, None)

                # Path must be an absolute path.
                if not os.path.isabs(path):
                        e = apx.LinkedImageException(child_path_notabs=path)
                        return (e.lix_exitrv, e, None)

                # cleanup specified path
                cwd = os.getcwd()
                try:
                        os.chdir(path)
                except OSError, e:
                        e = apx.LinkedImageException(child_path_eaccess=path)
                        return (e.lix_exitrv, e, None)
                path = os.getcwd()
                os.chdir(cwd)

                # make sure we're not linking to ourselves
                if self.__img.root == path:
                        raise apx.LinkedImageException(link_to_self=True)

                # make sure we're not linking the root image as a child
                if path == misc.liveroot():
                        raise apx.LinkedImageException(
                            attach_root_as_child=True)

                # if the current image isn't linked yet then we need to
                # generate some linked image properties for ourselves
                if PROP_PATH not in self.__props:
                        p_props = self.__fabricate_parent_props()
                        self.__update_props(p_props)

                # sanity check the input
                try:
                        self.__validate_child_attach(lin, path, props,
                            allow_relink=allow_relink)
                except apx.LinkedImageException, e:
                        return (e.lix_exitrv, e, None)

                # make a copy of the options and start updating them
                child_props = props.copy()
                child_props[PROP_NAME] = lin
                child_props[PROP_PATH] = path
                child_props[PROP_MODEL] = PV_MODEL_PUSH
                child_props[PROP_ALTROOT] = self.altroot()

                # fill in any missing defaults options
                for k, v in lip.attach_props_def.iteritems():
                        if k not in child_props:
                                child_props[k] = v

                # attach the child in memory
                lip.attach_child_inmemory(child_props, allow_relink)

                if noexecute and li_md_only:
                        # we've validated parameters, nothing else to do
                        return (pkgdefs.EXIT_OK, None, None)

                # update the child
                try:
                        lic = LinkedImageChild(self, lin)
                except apx.LinkedImageException, e:
                        return (e.lix_exitrv, e, None)

                rv, e, p_dict = self.__sync_child(lic,
                    accept=accept, li_attach_sync=True, li_md_only=li_md_only,
                    li_pkg_updates=li_pkg_updates, noexecute=noexecute,
                    progtrack=progtrack,
                    refresh_catalogs=refresh_catalogs, reject_list=reject_list,
                    show_licenses=show_licenses, update_index=update_index)

                assert isinstance(e, (type(None), apx.LinkedImageException))

                if rv not in [pkgdefs.EXIT_OK, pkgdefs.EXIT_NOP]:
                        return (rv, e, p_dict)

                if noexecute:
                        # if noexecute then we're done
                        return (pkgdefs.EXIT_OK, None, p_dict)

                # save child image properties
                rv, e = lip.sync_children_todisk()
                assert isinstance(e, (type(None), apx.LinkedImageException))
                if e:
                        return (pkgdefs.EXIT_OOPS, e, p_dict)

                # save parent image properties
                self.syncmd()

                return (pkgdefs.EXIT_OK, None, p_dict)

        def audit_children(self, lin_list, **kwargs):
                """Audit one or more children of the current image to see if
                they are in sync with this image."""

                return self.__children_op(lin_list,
                    self.__audit_child, **kwargs)

        def sync_children(self, lin_list, **kwargs):
                """Sync one or more children of the current image."""

                return self.__children_op(lin_list,
                    self.__sync_child, **kwargs)

        def detach_children(self, lin_list, **kwargs):
                """Detach one or more children from the current image. This
                operation results in the removal of any constraint package
                from the child images."""

                # get parameter meant for __detach_child()
                force = noexecute = False
                if "force" in kwargs:
                        force = kwargs["force"]
                if "noexecute" in kwargs:
                        noexecute = kwargs["noexecute"]

                # expand lin_list before calling __detach_child()
                if not lin_list:
                        lin_list = [i[0] for i in self.__list_children()]

                rvdict = self.__children_op(lin_list,
                    self.__detach_child, **kwargs)

                for lin in lin_list:
                        # if the detach failed leave metadata in parent
                        # Unused variable 'rv'; pylint: disable-msg=W0612
                        rv, e, p_dict = rvdict[lin]
                        # pylint: enable-msg=W0612
                        assert e == None or \
                            (isinstance(e, apx.LinkedImageException))
                        if e and not force:
                                continue

                        # detach the child in memory
                        lip = self.__plugins[lin.lin_type]
                        lip.detach_child_inmemory(lin)

                        if not noexecute:
                                # sync out the fact that we detached the child
                                rv2, e2 = lip.sync_children_todisk()
                                assert e2 == None or \
                                    (isinstance(e2, apx.LinkedImageException))
                                if not e:
                                        # don't overwrite previous errors
                                        rvdict[lin] = (rv2, e2, p_dict)

                if not (self.ischild() or self.isparent()):
                        # we're not linked anymore, so delete all our linked
                        # properties.
                        self.__update_props()
                        self.syncmd()

                return rvdict

        def __children_op(self, lin_list, op, **kwargs):
                """Perform a linked image operation on multiple children."""

                assert type(lin_list) == list
                assert type(kwargs) == dict
                assert "lin" not in kwargs
                assert "lic" not in kwargs

                if not lin_list:
                        lin_list = [i[0] for i in self.__list_children()]

                rvdict = dict()
                for lin in lin_list:
                        try:
                                lic = LinkedImageChild(self, lin)

                                # perform the requested operation
                                rvdict[lin] = op(lic, **kwargs)

                                # Unused variable; pylint: disable-msg=W0612
                                rv, e, p_dict = rvdict[lin]
                                # pylint: enable-msg=W0612
                                assert e == None or \
                                    (isinstance(e, apx.LinkedImageException))

                        except apx.LinkedImageException, e:
                                rvdict[lin] = (e.lix_exitrv, e, None)

                return rvdict

        @staticmethod
        def __audit_child(lic):
                """Recurse into a child image and audit it."""
                return lic.child_audit()

        @staticmethod
        def __sync_child(lic, **kwargs):
                """Recurse into a child image and sync it."""
                return lic.child_sync(**kwargs)

        def __detach_child(self, lic, force=False, noexecute=False,
            progtrack=None):
                """Recurse into a child image and detach it."""

                lin = lic.child_name
                lip = self.__plugins[lin.lin_type]
                if not force and not lip.support_detach:
                        # we can't detach this type of image.
                        e = apx.LinkedImageException(
                            detach_child_notsup=lin.lin_type)
                        return (pkgdefs.EXIT_OOPS, e, None)

                # remove linked data from the child
                return lic.child_detach(noexecute=noexecute,
                    progtrack=progtrack)

        def reset_recurse(self):
                """Reset all child recursion state."""

                self.__lic_list = []

        def init_recurse(self, op, li_ignore, accept,
            refresh_catalogs, update_index, args):
                """When planning changes on a parent image, prepare to
                recurse into all child images and operate on them as well."""

                # Too many arguments; pylint: disable-msg=R0913

                if op == pkgdefs.API_OP_DETACH:
                        # we don't need to recurse for these operations
                        self.__lic_list = []
                        return

                if PROP_RECURSE in self.__props and \
                    not self.__props[PROP_RECURSE]:
                        # don't bother to recurse into children
                        self.__lic_list = []
                        return

                self.__lic_list = []
                # Unused variable 'path'; pylint: disable-msg=W0612
                for (lin, path) in self.__list_children(li_ignore):
                # pylint: enable-msg=W0612
                        self.__lic_list.append(LinkedImageChild(self, lin))

                if not self.__lic_list:
                        # no child images to recurse into
                        return

                #
                # given the api operation being performed on the current
                # image, figure out what api operation should be performed on
                # child images.
                #
                # the recursion policy which hard coded here is that if we do
                # an pkg update in the parent image without any packages
                # specified (ie, we want to update everything) then when we
                # recurse we'll also do an update of everything.  but if we're
                # doing any other operation like install, uninstall, an update
                # of specific packages, etc, then when we recurse we'll do a
                # sync in the child.
                #
                if op == pkgdefs.API_OP_UPDATE and not args["pkgs_update"]:
                        pkg_op = pkgdefs.PKG_OP_UPDATE
                else:
                        pkg_op = pkgdefs.PKG_OP_SYNC

                for lic in self.__lic_list:
                        lic.child_init_recurse(pkg_op, accept,
                            refresh_catalogs, update_index,
                            args)

        def do_recurse(self, stage, ip=None):
                """When planning changes within a parent image, recurse into
                all child images and operate on them as well."""

                assert stage in pkgdefs.api_stage_values
                assert stage != pkgdefs.API_STAGE_DEFAULT

                res = []
                for lic in self.__lic_list:
                        res.append(lic.child_do_recurse(stage=stage, ip=ip))
                return res

        def recurse_nothingtodo(self):
                """Return True if there is no planned work to do on child
                image."""

                for lic in self.__lic_list:
                        if not lic.child_nothingtodo():
                                return False
                return True

        @staticmethod
        def __has_parent_dep(fmri, cat, excludes):
                """Check if a package has a parent dependency."""

                for a in cat.get_entry_actions(fmri,
                    [pkg.catalog.Catalog.DEPENDENCY], excludes=excludes):
                        if a.name == "depend" and a.attrs["type"] == "parent":
                                return True
                return False

        def extra_dep_actions(self, excludes=misc.EmptyI,
            installed_catalog=False):
                """Since we don't publish packages with parent dependencies
                yet, but we want to be able to sync packages between zones,
                we'll need to fake up some extra package parent dependencies.

                Here we'll inspect the catalog to find packages that we think
                should have parent dependencies and then we'll return a
                dictionary, indexed by fmri, which contains the extra
                dependency actions that should be added to each package."""

                # create a parent dependency action with a nonglobal zone
                # variant tag.
                attrs = dict()
                attrs["type"] = "parent"
                attrs["fmri"] = pkg.actions.depend.DEPEND_SELF
                attrs["variant.opensolaris.zone"] = "nonglobal"

                # Used * or ** magic; pylint: disable-msg=W0142
                pda = pkg.actions.depend.DependencyAction(**attrs)
                # pylint: enable-msg=W0142

                if not pda.include_this(excludes):
                        # we're not operating on a nonglobal zone image so we
                        # don't need to fabricate parent zone dependencies
                        return dict()

                if not self.ischild():
                        # we're not a child image so parent dependencies are
                        # irrelevant
                        return dict()

                osnet_incorp = "consolidation/osnet/osnet-incorporation"
                ips_incorp = "consolidation/osnet/ips-incorporation"

                #
                # it's time consuming to walk the catalog looking for packages
                # to dynamically add parent dependencies too.  so to speed
                # things up we'll check if the currently installed osnet and
                # ips incorporations already have parent dependencies.  if
                # they do then this image has already been upgraded to a build
                # where these dependencies are being published so there's no
                # need for us to dynamically add them.
                #
                osnet_has_pdep = False
                ips_has_pdep = False
                cat = self.__img.get_catalog(self.__img.IMG_CATALOG_INSTALLED)
                for (ver, fmris) in cat.fmris_by_version(osnet_incorp):
                        if self.__has_parent_dep(fmris[0], cat, excludes):
                                # osnet incorporation has parent deps
                                osnet_has_pdep = True
                for (ver, fmris) in cat.fmris_by_version(ips_incorp):
                        if self.__has_parent_dep(fmris[0], cat, excludes):
                                # ips incorporation has parent deps
                                ips_has_pdep = True
                if osnet_has_pdep and ips_has_pdep:
                        return dict()

                if not installed_catalog:
                        # search the known catalog
                        cat = self.__img.get_catalog(
                            self.__img.IMG_CATALOG_KNOWN)

                # assume that the osnet and ips incorporations should always
                # have a parent dependencies.
                inc_fmris = set()
                for tgt in [osnet_incorp, ips_incorp]:
                        for (ver, fmris) in cat.fmris_by_version(tgt):
                                for fmri in fmris:
                                        if not self.__has_parent_dep(fmri, cat,
                                            excludes):
                                                inc_fmris |= set([fmri])

                # find the fmris that each osnet/ips incorporation incorporates
                inc_pkgs = set()
                for fmri in inc_fmris:
                        for a in cat.get_entry_actions(fmri,
                            [pkg.catalog.Catalog.DEPENDENCY],
                            excludes=excludes):
                                if (a.name != "depend") or \
                                    (a.attrs["type"] != "incorporate"):
                                        continue

                                # create an fmri for the incorporated package
                                build_release = str(fmri.version.build_release)
                                inc_pkgs |= set([pkg.fmri.PkgFmri(
                                    a.attrs["fmri"],
                                    build_release=build_release)])

                # translate the incorporated package fmris into actual
                # packages in the known catalog
                dep_fmris = set()
                for fmri in inc_pkgs:
                        for (ver, fmris) in cat.fmris_by_version(fmri.pkg_name):
                                if ver == fmri.version or ver.is_successor(
                                    fmri.version, pkg.version.CONSTRAINT_AUTO):
                                        dep_fmris |= set(fmris)

                # all the fmris we want to add dependencies to.
                all_fmris = inc_fmris | dep_fmris

                # remove some unwanted fmris
                rm_fmris = set()
                for pfmri in all_fmris:
                        # eliminate renamed or obsoleted fmris
                        entry = cat.get_entry(pfmri)
                        state = entry["metadata"]["states"]
                        if self.__img.PKG_STATE_OBSOLETE in state or \
                            self.__img.PKG_STATE_RENAMED in state:
                                rm_fmris |= set([pfmri])
                                continue

                        # eliminate any group packages
                        if pfmri.pkg_name.startswith("group/"):
                                rm_fmris |= set([pfmri])
                                continue

                all_fmris -= rm_fmris

                return dict([(fmri, [pda]) for fmri in all_fmris])


class LinkedImageChild(object):
        """A LinkedImageChild object is used when a parent image wants to
        access a child image.  These accesses may include things like:
        saving/pushing linked image metadata into a child image, syncing or
        auditing a child image, or recursing into a child image to keep it in
        sync with planned changes in the parent image."""

        # Too many instance attributes; pylint: disable-msg=R0902

        def __init__(self, li, lin):
                assert isinstance(li, LinkedImage), \
                    "isinstance(%s, LinkedImage)" % type(li)
                assert isinstance(lin, LinkedImageName), \
                    "isinstance(%s, LinkedImageName)" % type(lin)

                # globals
                self.__linked = li
                self.__img = li.image

                # cache properties.
                self.__props = self.__linked.child_props(lin)
                assert self.__props[PROP_NAME] == lin

                try:
                        imgdir = ar.ar_img_prefix(self.child_path)
                except OSError:
                        raise apx.LinkedImageException(
                            lin=lin, child_path_eaccess=self.child_path)

                if not imgdir:
                        raise apx.LinkedImageException(
                            lin=lin, child_bad_img=self.child_path)

                # initialize paths for linked image data files
                self.__path_ppkgs = os.path.join(imgdir, PATH_PPKGS)
                self.__path_prop = os.path.join(imgdir, PATH_PROP)
                self.__path_ppubs = os.path.join(imgdir, PATH_PUBS)

                # initialize a linked image child plugin
                self.__plugin = \
                    pkg.client.linkedimage.p_classes_child[lin.lin_type](self)

                # variables reset by self.child_reset_recurse()
                self.__r_op = None
                self.__r_args = None
                self.__r_progtrack = None
                self.__r_rv_nop = False
                self.child_reset_recurse()

        @property
        def child_name(self):
                """Get the path associated with a child image."""
                return self.__props[PROP_NAME]

        @property
        def child_path(self):
                """Get the path associated with a child image."""
                return self.__props[PROP_PATH]

        @property
        def child_pimage(self):
                """Get a pointer to the parent image object associated with
                this child."""
                return self.__img

        def __push_data(self, root, path, data, tmp, test):
                """Write data to a child image."""

                # first save our data to a temporary file
                path_tmp = "%s.%s" % (path, self.__img.runid)
                save_data(path_tmp, data, root=root)

                # check if we're updating the data
                updated = True

                try:
                        exists = ar.ar_exists(root, path)
                except OSError, e:
                        # W0212 Access to a protected member
                        # pylint: disable-msg=W0212
                        raise apx._convert_error(e)

                if exists:
                        try:
                                updated = ar.ar_diff(root, path, path_tmp)
                        except OSError, e:
                                # W0212 Access to a protected member
                                # pylint: disable-msg=W0212
                                raise apx._convert_error(e)

                # if we're not actually updating any data, or if we were just
                # doing a test to see if the data has changed, then delete the
                # temporary data file
                if not updated or test:
                        ar.ar_unlink(root, path_tmp)
                        return updated

                if not tmp:
                        # we are updating the real data.
                        try:
                                ar.ar_rename(root, path_tmp, path)
                        except OSError, e:
                                # W0212 Access to a protected member
                                # pylint: disable-msg=W0212
                                raise apx._convert_error(e)

                return True

        def __push_ppkgs(self, tmp=False, test=False, ip=None):
                """Sync linked image parent constraint data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                # there has to be an image plan to export
                cati = self.__img.get_catalog(self.__img.IMG_CATALOG_INSTALLED)
                ppkgs = set(cati.fmris())

                if ip != None and ip.plan_desc:
                        # if there's an image plan the we need to update the
                        # installed packages based on that plan.
                        for src, dst in ip.plan_desc:
                                if src == dst:
                                        continue
                                if src:
                                        assert src in ppkgs
                                        ppkgs -= set([src])
                                if dst:
                                        assert dst not in ppkgs
                                        ppkgs |= set([dst])

                # paranoia
                ppkgs = frozenset(ppkgs)

                # save the planned cips
                return self.__push_data(self.child_path, self.__path_ppkgs,
                    ppkgs, tmp, test)

        def __push_props(self, tmp=False, test=False):
                """Sync linked image properties data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                # make a copy of the props we want to push
                props = self.__props.copy()
                assert PROP_PARENT_PATH not in props

                self.__plugin.munge_props(props)

                # delete temporal properties
                props = rm_dict_ent(props, temporal_props)

                return self.__push_data(self.child_path, self.__path_prop,
                    props, tmp, test)

        def __push_ppubs(self, tmp=False, test=False):
                """Sync linked image parent publisher data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                ppubs = self.__linked.get_pubs()
                return self.__push_data(self.child_path, self.__path_ppubs,
                    ppubs, tmp, test)

        def __syncmd(self, tmp=False, test=False, ip=None):
                """Sync linked image data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                if ip:
                        tmp = True

                ppkgs_updated = self.__push_ppkgs(tmp, test, ip=ip)
                props_updated = self.__push_props(tmp, test)
                pubs_updated = self.__push_ppubs(tmp, test)

                return (props_updated or ppkgs_updated or pubs_updated)

        @staticmethod
        def __flush_output():
                """We flush stdout and stderr before and after operating on
                child images to avoid any out-of-order output problems that
                could be caused by caching of output."""

                try:
                        sys.stdout.flush()
                except IOError:
                        pass
                except OSError, e:
                        # W0212 Access to a protected member
                        # pylint: disable-msg=W0212
                        raise apx._convert_error(e)

                try:
                        sys.stderr.flush()
                except IOError:
                        pass
                except OSError, e:
                        # W0212 Access to a protected member
                        # pylint: disable-msg=W0212
                        raise apx._convert_error(e)

        def __pkg_cmd(self, pkg_op, pkg_args, stage=None, progtrack=None):
                """Perform a pkg(1) operation on a child image."""

                if stage == None:
                        stage = pkgdefs.API_STAGE_DEFAULT
                assert stage in pkgdefs.api_stage_values

                #
                # Build up a command line to execute.  Note that we take care
                # to try to run the exact same pkg command that we were
                # executed with.  We do this because pkg commonly tries to
                # access the image that the command is being run from.
                #
                pkg_bin = "pkg"
                cmdpath = self.__img.cmdpath
                if cmdpath and os.path.basename(cmdpath) == "pkg":
                        try:
                                # check if the currently running pkg command
                                # exists and is accessible.
                                os.stat(cmdpath)
                                pkg_bin = cmdpath
                        except OSError:
                                pass

                pkg_cmd = [
                    pkg_bin,
                    "-R", str(self.child_path),
                    "--runid=%s" % self.__img.runid,
                ]

                # propagate certain debug options
                for k in [
                    "broken-conflicting-action-handling",
                    "disp_linked_cmds",
                    "plan"]:
                        if DebugValues[k]:
                                pkg_cmd.append("-D")
                                pkg_cmd.append("%s=1" % k)

                # add the subcommand argument
                pkg_cmd.append(pkg_op)

                # propagate stage option
                if stage != pkgdefs.API_STAGE_DEFAULT:
                        pkg_cmd.append("--stage=%s" % stage)

                # add the subcommand argument options
                pkg_cmd.extend(pkg_args)

                if progtrack:
                        progtrack.li_recurse_start(self.child_name)

                # flush all output before recursing into child
                self.__flush_output()

                disp_linked_cmds = DebugValues.get_value("disp_linked_cmds")
                if not disp_linked_cmds and \
                    "PKG_DISP_LINKED_CMDS" in os.environ:
                        disp_linked_cmds = True
                pv_in_args = False
                for a in pkg_args:
                        if a.startswith("--parsable="):
                                pv_in_args = True
                # If we're using --parsable, don't emit the child cmd
                # information as info because it will confuse the JSON parser.
                if disp_linked_cmds and not pv_in_args:
                        logger.info("child cmd: %s" % " ".join(pkg_cmd))
                else:
                        logger.debug("child cmd: %s" % " ".join(pkg_cmd))

                #
                # Start the operation on the child.  let the child have direct
                # access to stdout but capture stderr.
                #
                ferrout = tempfile.TemporaryFile()
                # If we're using --parsable, then we need to capture stdout so
                # that we can parse the plan of the child image and include it
                # in our plan.
                outloc = None
                if pv_in_args:
                        outloc = tempfile.TemporaryFile()
                try:
                        p = pkg.pkgsubprocess.Popen(pkg_cmd, stderr=ferrout,
                            stdout=outloc)
                        p.wait()
                except OSError, e:
                        # W0212 Access to a protected member
                        # pylint: disable-msg=W0212
                        raise apx._convert_error(e)

                # flush output generated by the child
                self.__flush_output()

                # get error output generated by the child
                ferrout.seek(0)
                errout = "".join(ferrout.readlines())

                if progtrack:
                        progtrack.li_recurse_end(self.child_name)

                p_dict = None
                # A parsable plan is only displayed if the operation was
                # successful and the stage was default or plan.
                if pv_in_args and stage in (pkgdefs.API_STAGE_PLAN,
                    pkgdefs.API_STAGE_DEFAULT) and p.returncode == 0:
                        outloc.seek(0)
                        output = outloc.read()
                        try:
                                p_dict = json.loads(output)
                        except ValueError, e:
                                # JSON raises a subclass of ValueError when it
                                # can't parse a string.
                                raise apx.UnparsableJSON(output, e)
                        p_dict["image-name"] = str(self.child_name)

                return (p.returncode, errout, p_dict)

        def child_detach(self, noexecute=False, progtrack=None):
                """Detach a child image."""

                # When issuing a detach from a prent we must always use the
                # force flag. (Normally a child will refuse to detach from a
                # parent unless it attached to the parent, which is never the
                # case here.)
                pkg_args = ["-f"]
                pkg_args.extend(["-v"] * progtrack.verbose)
                if progtrack.quiet:
                        pkg_args.append("-q")
                if noexecute:
                        pkg_args.append("-n")

                rv, errout, p_dict = self.__pkg_cmd(pkgdefs.PKG_OP_DETACH,
                    pkg_args)

                # if the detach command ran, return its status.
                if rv in [pkgdefs.EXIT_OK, pkgdefs.EXIT_NOPARENT]:
                        return (pkgdefs.EXIT_OK, None, p_dict)

                e = apx.LinkedImageException(lin=self.child_name, exitrv=rv,
                    pkg_op_failed=(pkgdefs.PKG_OP_DETACH, rv, errout))
                return (rv, e, p_dict)

        def child_audit(self):
                """Audit a child image to see if it's in sync with its
                constraints."""

                # first sync our metadata
                self.__syncmd()

                # recurse into the child image
                pkg_args = ["-q"]

                rv, errout, p_dict = self.__pkg_cmd(pkgdefs.PKG_OP_AUDIT_LINKED,
                    pkg_args)

                # if the audit command ran, return its status.
                if rv in [pkgdefs.EXIT_OK, pkgdefs.EXIT_DIVERGED]:
                        return (rv, None, p_dict)

                # something went unexpectedly wrong.
                e = apx.LinkedImageException(lin=self.child_name, exitrv=rv,
                    pkg_op_failed=(pkgdefs.PKG_OP_AUDIT_LINKED, rv, errout))
                return (rv, e, p_dict)

        def child_sync(self, accept=False, li_attach_sync=False,
            li_md_only=False, li_pkg_updates=True, progtrack=None,
            noexecute=False, refresh_catalogs=True, reject_list=misc.EmptyI,
            show_licenses=False, update_index=True):
                """Try to bring a child image into sync with its
                constraints.

                'li_attach_sync' indicates if this sync is part of an attach
                operation.

                For descriptions of parameters please see the descriptions in
                api.py`gen_plan_*"""

                # Too many arguments; pylint: disable-msg=R0913

                if li_md_only:
                        # we're not going to recurse into the child image,
                        # we're just going to update its metadata.
                        try:
                                updated = self.__syncmd(test=noexecute)
                        except apx.LinkedImageException, e:
                                return (e.lix_exitrv, e, None)

                        if updated:
                                return (pkgdefs.EXIT_OK, None, None)
                        else:
                                return (pkgdefs.EXIT_NOP, None, None)

                # first sync the metadata
                try:
                        # if we're doing this sync as part of an attach, then
                        # temporarily sync the metadata since we don't know
                        # yet if the attach will succeed.  if the attach
                        # doesn't succeed this means we don't have to delete
                        # any metadata.  if the attach succeeds the child will
                        # make the temporary metadata permanent as part of the
                        # commit.
                        self.__syncmd(tmp=li_attach_sync)
                except apx.LinkedImageException, e:
                        return (e.lix_exitrv, e, None)

                pkg_args = []
                pkg_args.extend(["-v"] * progtrack.verbose)
                if progtrack.quiet:
                        pkg_args.append("-q")
                if noexecute:
                        pkg_args.append("-n")
                if accept:
                        pkg_args.append("--accept")
                if show_licenses:
                        pkg_args.append("--licenses")
                if not refresh_catalogs:
                        pkg_args.append("--no-refresh")
                if not update_index:
                        pkg_args.append("--no-index")
                if not li_pkg_updates:
                        pkg_args.append("--no-pkg-updates")
                if progtrack.parsable_version is not None:
                        assert progtrack.quiet
                        pkg_args.append("--parsable=%s" %
                            progtrack.parsable_version)
                for pat in reject_list:
                        pkg_args.extend(["--reject", str(pat)])

                rv, errout, p_dict = self.__pkg_cmd(pkgdefs.PKG_OP_SYNC,
                    pkg_args, progtrack=progtrack)

                # if the audit command ran, return its status.
                if rv in [pkgdefs.EXIT_OK, pkgdefs.EXIT_NOP]:
                        return (rv, None, p_dict)

                # something went unexpectedly wrong.
                e = apx.LinkedImageException(lin=self.child_name, exitrv=rv,
                    pkg_op_failed=(pkgdefs.PKG_OP_SYNC, rv, errout))
                return (rv, e, p_dict)

        def child_init_root(self, old_altroot):
                """Our image path is being updated, so figure out our new
                child image paths.  This interface only gets invoked when:

                - We're doing a packaging operation on a parent image and
                  we've just cloned that parent to create a new BE that we're
                  going to update.  This clone also cloned all the children
                  and so now we need to update our paths to point to the newly
                  created children.

                - We tried to update a cloned image (as described above) and
                  our update failed, hence we're changing paths back to the
                  original images that were the source of the clone."""

                # get the image path without the altroot
                altroot_path = self.__props[PROP_PATH]
                path = rm_altroot_path(altroot_path, old_altroot)

                # update the path with the current altroot
                altroot = self.__linked.altroot()
                path = add_altroot_path(path, altroot)

                # update properties with altroot
                self.__props[PROP_PATH] = path
                self.__props[PROP_ALTROOT] = altroot

                # we don't bother to update update PROP_PARENT_PATH since
                # that is only used when reading constraint data from the
                # parent image, and this interface is only invoked when we're
                # starting or finishing execution of a plan on a cloned image
                # (at which point we have no need to access the parent
                # anymore).

        def child_nothingtodo(self):
                """Check if there are any changes planned for a child
                image."""
                return self.__r_rv_nop

        def child_reset_recurse(self):
                """Reset child recursion state for child."""

                self.__r_op = None
                self.__r_args = None
                self.__r_progtrack = None
                self.__r_rv_nop = False

        def child_init_recurse(self, pkg_op, accept, refresh_catalogs,
            update_index, args):
                """When planning changes on a parent image, prepare to
                recurse into a child image."""

                assert pkg_op in [pkgdefs.PKG_OP_SYNC, pkgdefs.PKG_OP_UPDATE]

                progtrack = args["progtrack"]
                noexecute = args["noexecute"]

                pkg_args = []

                pkg_args.extend(["-v"] * progtrack.verbose)
                if progtrack.quiet:
                        pkg_args.append("-q")
                if noexecute:
                        pkg_args.append("-n")
                if progtrack.parsable_version is not None:
                        pkg_args.append("--parsable=%s" %
                            progtrack.parsable_version)

                # W0511 XXX / FIXME Comments; pylint: disable-msg=W0511
                # XXX: also need to support --licenses.
                # pylint: enable-msg=W0511
                if accept:
                        pkg_args.append("--accept")
                if not refresh_catalogs:
                        pkg_args.append("--no-refresh")
                if not update_index:
                        pkg_args.append("--no-index")

                # options specific to: attach, set-property-linked, sync
                if "li_pkg_updates" in args and not args["li_pkg_updates"]:
                        pkg_args.append("--no-pkg-updates")

                if pkg_op == pkgdefs.PKG_OP_UPDATE:
                        # skip ipkg up to date check for child images
                        pkg_args.append("-f")

                self.__r_op = pkg_op
                self.__r_args = pkg_args
                self.__r_progtrack = progtrack

        def child_do_recurse(self, stage, ip=None):
                """When planning changes within a parent image, recurse into
                a child image."""

                assert stage in pkgdefs.api_stage_values
                assert stage != pkgdefs.API_STAGE_DEFAULT
                assert stage != pkgdefs.API_STAGE_PLAN or ip != None

                assert self.__r_op != None
                assert self.__r_args != None

                if stage == pkgdefs.API_STAGE_PUBCHECK:
                        self.__syncmd()

                if stage == pkgdefs.API_STAGE_PLAN:
                        # sync our metadata
                        if not self.__syncmd(ip=ip):
                                # no metadata changes in the child image.
                                self.__r_rv_nop = True

                if self.__r_rv_nop:
                        if stage == pkgdefs.API_STAGE_EXECUTE:
                                self.child_reset_recurse()
                        # the child image told us it has no changes planned.
                        return pkgdefs.EXIT_NOP, None

                rv, errout, p_dict = self.__pkg_cmd(self.__r_op, self.__r_args,
                    stage=stage, progtrack=self.__r_progtrack)

                if rv in [pkgdefs.EXIT_OK, pkgdefs.EXIT_NOP]:
                        # common case (we hope)
                        pass
                else:
                        e = apx.LinkedImageException(
                            lin=self.child_name, exitrv=rv,
                            pkg_op_failed=(self.__r_op, rv, errout))
                        self.child_reset_recurse()
                        raise e

                if stage == pkgdefs.API_STAGE_PLAN and rv == pkgdefs.EXIT_NOP:
                        self.__r_rv_nop = True

                if stage == pkgdefs.API_STAGE_EXECUTE:
                        # we're done with this operation
                        self.child_reset_recurse()

                return rv, p_dict


# ---------------------------------------------------------------------------
# Utility Functions
#
def save_data(path, data, root="/"):
        """Save JSON encoded linked image metadata to a file."""

        # make sure the directory we're about to save data into exists.
        path_dir = os.path.dirname(path)
        pathtmp = "%s.%d.tmp" % (path, os.getpid())

        try:
                if not ar.ar_exists(root, path_dir):
                        ar.ar_mkdir(root, path_dir, misc.PKG_DIR_MODE)

                # write the output to a temporary file
                fd = ar.ar_open(root, pathtmp, os.O_WRONLY,
                    mode=0644, create=True, truncate=True)
                fobj = os.fdopen(fd, "w")
                json.dump(data, fobj, encoding="utf-8",
                    cls=pkg.client.linkedimage.PkgEncoder)
                fobj.close()

                # atomically create the desired file
                ar.ar_rename(root, pathtmp, path)
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable-msg=W0212
                raise apx._convert_error(e)

def load_data(path, missing_val=None):
        """Load JSON encoded linked image metadata from a file."""

        try:
                if (missing_val != None) and not path_exists(path):
                        return missing_val
                fobj = open(path)
                data = json.load(fobj, encoding="utf-8",
                    object_hook=pkg.client.linkedimage.PkgDecoder)
                fobj.close()
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable-msg=W0212
                raise apx._convert_error(e)
        return data


class PkgEncoder(json.JSONEncoder):
        """Utility class used when json encoding linked image metadata."""

        # E0202 An attribute inherited from JSONEncoder hide this method
        # pylint: disable-msg=E0202
        def default(self, obj):
                """Required routine that overrides the default base
                class version.  This routine must serialize 'obj' when
                attempting to save 'obj' json format."""

                if isinstance(obj, (pkg.fmri.PkgFmri,
                    pkg.client.linkedimage.common.LinkedImageName)):
                        return str(obj)

                if isinstance(obj, pkgplan.PkgPlan):
                        return obj.getstate()

                if isinstance(obj, (set, frozenset)):
                        return list(obj)

                return json.JSONEncoder.default(self, obj)


def PkgDecoder(dct):
        """Utility class used when json decoding linked image metadata."""
        # Replace unicode keys/values with strings
        rvdct = {}
        for k, v in dct.iteritems():

                # unicode must die
                if type(k) == unicode:
                        k = k.encode("utf-8")
                if type(v) == unicode:
                        v = v.encode("utf-8")

                # convert boolean strings values back into booleans
                if type(v) == str:
                        if v.lower() == "true":
                                v = True
                        elif v.lower() == "false":
                                v = False

                rvdct[k] = v
        return rvdct

def rm_dict_ent(d, keys):
        """Remove a set of keys from a dictionary."""
        return dict([
                (k, v)
                for k, v in d.iteritems()
                if k not in keys
        ])

def _rterr(li=None, lic=None, lin=None, path=None, err=None,
    bad_cp=None,
    bad_iup=None,
    bad_lin_type=None,
    bad_prop=None,
    missing_props=None,
    multiple_altroots=None,
    saved_temporal_props=None):
        """Oops.  We hit a runtime error.  Die with a nice informative
        message.  Note that runtime errors should never happen and usually
        indicate bugs (or possibly corrupted linked image metadata), so they
        are not localized (just like asserts are not localized)."""
        # Too many arguments; pylint: disable-msg=R0913

        assert not (li and lic)
        assert not ((lin or path) and li)
        assert not ((lin or path) and lic)
        assert path == None or type(path) == str

        if bad_cp:
                assert err == None
                err = "Invalid linked content policy: %s" % bad_cp
        elif bad_iup:
                assert err == None
                err = "Invalid linked image update policy: %s" % bad_iup
        elif bad_lin_type:
                assert err == None
                err = "Invalid linked image type: %s" % bad_lin_type
        elif bad_prop:
                assert err == None
                err = "Invalid linked property value: %s=%s" % bad_prop
        elif missing_props:
                assert err == None
                err = "Missing required linked properties: %s" % \
                    ", ".join(missing_props)
        elif multiple_altroots:
                assert err == None
                err = "Multiple plugins reported different altroots:"
                for plugin, altroot in multiple_altroots:
                        err += "\n\t%s = %s" % (plugin, altroot)
        elif saved_temporal_props:
                assert err == None
                err = "Found saved temporal linked properties: %s" % \
                    ", ".join(saved_temporal_props)
        else:
                assert err != None

        if li:
                if li.ischild():
                        lin = li.child_name
                path = li.image.root

        if lic:
                lin = lic.child_name
                path = lic.child_path

        err_prefix = "Linked image error: "
        if lin:
                err_prefix = "Linked image (%s) error: " % (str(lin))

        err_suffix = ""
        if path and lin:
                err_suffix = "\nLinked image (%s) path: %s" % (str(lin), path)
        elif path:
                err_suffix = "\nLinked image path: %s" % (path)

        raise RuntimeError(
            "%s: %s%s" % (err_prefix, err, err_suffix))

# ---------------------------------------------------------------------------
# Functions for accessing files in the current root
#
def path_exists(path):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_exists("/", path)
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable-msg=W0212
                raise apx._convert_error(e)

def path_isdir(path):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_isdir("/", path)
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable-msg=W0212
                raise apx._convert_error(e)

def path_mkdir(path, mode):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_mkdir("/", path, mode)
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable-msg=W0212
                raise apx._convert_error(e)

def path_unlink(path, noent_ok=False):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_unlink("/", path, noent_ok=noent_ok)
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable-msg=W0212
                raise apx._convert_error(e)

# ---------------------------------------------------------------------------
# Functions for managing images which may be in alternate roots
#
def check_altroot_path(path, altroot):
        """Check if 'path' is nested within 'altroot'"""

        assert os.path.isabs(path), "os.path.isabs(%s)" % path
        assert os.path.isabs(altroot), "os.path.isabs(%s)" % altroot

        # make sure both paths have one trailing os.sep.
        altroot = altroot.rstrip(os.sep) + os.sep
        path = path.rstrip(os.sep) + os.sep

        # check for nested or equal paths
        if path.startswith(altroot):
                return True
        return False

def add_altroot_path(path, altroot):
        """Return a path where 'path' is nested within 'altroot'"""

        assert os.path.isabs(path), "os.path.isabs(%s)" % path
        assert os.path.isabs(altroot), "os.path.isabs(%s)" % altroot

        altroot = altroot.rstrip(os.sep) + os.sep
        path = path.lstrip(os.sep)
        altroot_path = altroot + path

        # sanity check
        assert check_altroot_path(altroot_path, altroot), \
            "check_altroot_path(%s, %s)" % (altroot_path, altroot)

        return altroot_path

def rm_altroot_path(path, altroot):
        """Return the relative porting of 'path', which must be nested within
        'altroot'"""

        assert os.path.isabs(path), "not os.path.isabs(%s)" % path
        assert os.path.isabs(altroot), "not os.path.isabs(%s)" % altroot

        assert check_altroot_path(path, altroot), \
            "not check_altroot_path(%s, %s)" % (path, altroot)

        rv = path[len(altroot.rstrip(os.sep)):]
        if rv == "":
                rv = "/"
        assert os.path.isabs(rv)
        return rv

def get_altroot_path(path, path_suffix):
        """Given 'path', and a relative path 'path_suffix' that must match
        the suffix of 'path', return the unmatched prefix of 'path'."""

        assert os.path.isabs(path), "os.path.isabs(%s)" % path
        assert os.path.isabs(path_suffix), "os.path.isabs(%s)" % path_suffix

        # make sure both paths have one trailing os.sep.
        path = path.rstrip(os.sep) + os.sep
        path_suffix = path_suffix.rstrip(os.sep) + os.sep

        i = path.rfind(path_suffix)
        if i <= 0:
                # path and path_suffix are either unrelated or equal
                altroot = os.sep
        else:
                altroot = path[:i]

        # sanity check
        assert check_altroot_path(path, altroot), \
            "check_altroot_path(%s, %s)" % (path, altroot)

        return altroot
