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
# Copyright (c) 2011, 2016, Oracle and/or its affiliates. All rights reserved.
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

# standard python classes
import collections
import copy
import operator
import os
import select
import simplejson as json
import six

# Redefining built-in 'reduce', 'zip'; pylint: disable=W0622
# import-error: six.moves; pylint: disable=F0401
from functools import reduce
from six.moves import zip

# pkg classes
import pkg.actions
import pkg.altroot as ar
import pkg.catalog
import pkg.client.api_errors as apx
import pkg.client.bootenv as bootenv
import pkg.client.linkedimage
import pkg.client.pkgdefs as pkgdefs
import pkg.client.pkgplan as pkgplan
import pkg.client.pkgremote
import pkg.client.progress as progress
import pkg.facet
import pkg.fmri
import pkg.misc as misc
import pkg.pkgsubprocess
import pkg.version

from pkg.client import global_settings

logger = global_settings.logger

# linked image relationship types (returned by LinkedImage.list_related())
REL_PARENT = "parent"
REL_SELF   = "self"
REL_CHILD  = "child"

# linked image properties
PROP_CURRENT_PARENT_PATH = "li-current-parent"
PROP_CURRENT_PATH        = "li-current-path"
PROP_MODEL               = "li-model"
PROP_NAME                = "li-name"
PROP_PARENT_PATH         = "li-parent"
PROP_PATH                = "li-path"
PROP_PATH_TRANSFORM      = "li-path-transform"
PROP_RECURSE             = "li-recurse"
prop_values         = frozenset([
    PROP_CURRENT_PARENT_PATH,
    PROP_CURRENT_PATH,
    PROP_MODEL,
    PROP_NAME,
    PROP_PARENT_PATH,
    PROP_PATH,
    PROP_PATH_TRANSFORM,
    PROP_RECURSE,
])

# properties that never get saved
temporal_props = frozenset([
    PROP_CURRENT_PARENT_PATH,
    PROP_CURRENT_PATH,
    PROP_PATH_TRANSFORM,
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
PATH_PFACETS    = os.path.join(__DATA_DIR, "linked_pfacets")
PATH_PPKGS     = os.path.join(__DATA_DIR, "linked_ppkgs")
PATH_PROP      = os.path.join(__DATA_DIR, "linked_prop")
PATH_PUBS      = os.path.join(__DATA_DIR, "linked_ppubs")

#
# we define PATH_TRANSFORM_NONE as a tuple instead of just None because this
# will prevent it from being accidently serialized to json.
#
PATH_TRANSFORM_NONE = ("/", "/")

LI_RVTuple = collections.namedtuple("LI_RVTuple", "rvt_rv rvt_e rvt_p_dict")

def _li_rvtuple_check(rvtuple):
        """Sanity check a linked image operation return value tuple.
        The format of said tuple is:
                process return code
                LinkedImageException exception (optional)
                json dictionary containing planned image changes
        """

        # make sure we're using the LI_RVTuple class
        assert type(rvtuple) == LI_RVTuple

        # decode the tuple
        rv, e, p_dict = rvtuple

        # rv must be an integer
        assert type(rv) == int
        # any exception returned must be a LinkedImageException
        assert e is None or type(e) == apx.LinkedImageException
        # if specified, p_dict must be a dictionary
        assert p_dict is None or type(p_dict) is dict
        # some child return codes should never be associated with an exception
        assert rv not in [pkgdefs.EXIT_OK, pkgdefs.EXIT_NOP] or e is None
        # a p_dict can only be returned if the child returned EXIT_OK
        assert rv == pkgdefs.EXIT_OK or p_dict is None

        # return the value that was passed in
        return rvtuple

def _li_rvdict_check(rvdict):
        """Given a linked image return value dictionary, sanity check all the
        entries."""

        assert type(rvdict) == dict
        for k, v in six.iteritems(rvdict):
                assert type(k) == LinkedImageName, \
                    ("Unexpected rvdict key: ", k)
                _li_rvtuple_check(v)

        # return the value that was passed in
        return rvdict

def _li_rvdict_exceptions(rvdict):
        """Given a linked image return value dictionary, return a list of any
        exceptions that were encountered while processing children."""

        # sanity check rvdict
        _li_rvdict_check(rvdict)

        # get a list of exceptions
        return [
            rvtuple.rvt_e
            for rvtuple in rvdict.values()
            if rvtuple.rvt_e is not None
        ]

def _li_rvdict_raise_exceptions(rvdict):
        """If an exception was encountered while operating on a linked
        child then raise that exception.  If multiple exceptions were
        encountered while operating on multiple children, then bundle
        those exceptions together and raise them."""

        # get a list of exceptions
        exceptions = _li_rvdict_exceptions(rvdict)

        if len(exceptions) == 1:
                # one exception encountered
                raise exceptions[0]

        if exceptions:
                # multiple exceptions encountered
                raise apx.LinkedImageException(bundle=exceptions)

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

        # Unused argument; pylint: disable=W0613
        def __init__(self, pname, linked):
                """Initialize a linked image plugin.

                'pname' is the name of the plugin class derived from this
                base class.

                'linked' is the LinkedImage object initializing this plugin.
                """

                return

        def init_root(self, root):
                """Called when the path to the image that we're operating on
                is changing.  This normally occurs when we clone an image
                after we've planned and prepared to do an operation."""

                # return value: None
                raise NotImplementedError

        def guess_path_transform(self, ignore_errors=False):
                """If the linked image plugin is able to detect that we're
                operating on an image in an alternate root then return an
                transform that can be used to translate between the original
                image path and the current one."""

                # return value: string or None
                raise NotImplementedError

        def get_child_list(self, nocache=False, ignore_errors=False):
                """Return a list of the child images and paths associated with
                the current image.  The paths that are returned should be
                absolute paths to the original child image locations."""

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

                # return value: LI_RVTuple()
                raise NotImplementedError


class LinkedImageChildPlugin(object):
        """This class is a template that all linked image child plugins should
        inherit from.  Linked image child plugins derived from this class are
        designed to manage linked aspects of children of the current image.
        (vs managing linked aspects of the current image itself).

        All the interfaces exported by this class and its descendants are
        private to the linked image subsystem and should not be called
        directly by any other subsystem."""

        def __init__(self, lic): # Unused argument; pylint: disable=W0613
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

        @staticmethod
        def getstate(obj, je_state=None):
                """Returns the serialized state of this object in a format
                that that can be easily stored using JSON, pickle, etc."""
                # Unused argument; pylint: disable=W0613
                return str(obj)

        @staticmethod
        def fromstate(state, jd_state=None):
                """Allocate a new object using previously serialized state
                obtained via getstate()."""
                # Unused argument; pylint: disable=W0613
                return LinkedImageName(state)

        def __str__(self):
                return "{0}:{1}".format(self.lin_type, self.lin_name)

        def __len__(self):
                return len(self.__str__())

        def __lt__(self, other):
                assert type(self) == LinkedImageName
                if not other:
                        return False
                if other == PV_NAME_NONE:
                        return False
                assert type(other) == LinkedImageName
                if self.lin_type < other.lin_type:
                        return True
                if self.lin_type != other.lin_type:
                        return False
                return self.lin_name < other.lin_name

        def __gt__(self, other):
                assert type(self) == LinkedImageName
                if not other:
                        return True
                if other == PV_NAME_NONE:
                        return True
                assert type(other) == LinkedImageName
                if self.lin_type > other.lin_type:
                        return True
                if self.lin_type != other.lin_type:
                        return False
                return self.lin_name > other.lin_name

        def __le__(self, other):
                return not self > other

        def __ge__(self, other):
                return not self < other

        def __hash__(self):
                return hash(str(self))

        def __eq__(self, other):
                if not isinstance(other, LinkedImageName):
                        return False

                return str(self) == str(other)

        def __ne__(self, other):
                return not self.__eq__(other)

class LinkedImage(object):
        """A LinkedImage object is used to manage the linked image aspects of
        an image.  This image could be a child image, a parent image, or both
        a parent and child.  This object allows for access to linked image
        properties and also provides routines that allow operations to be
        performed on child images."""

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
                self.__pfacets = pkg.facet.Facets()
                self.__pimg = None

                # variables reset by self.__recursion_init()
                self.__lic_ignore = None
                self.__lic_dict = {}

                # variables reset by self._init_root()
                self.__root = None
                self.__path_ppkgs = None
                self.__path_prop = None
                self.__path_ppubs = None
                self.__path_pfacets = None
                self.__img_insync = True

                # initialize with no properties
                self.__update_props()

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
                    "root = {0}".format(str(self.__img.root))
                assert self.__img.imgdir, \
                    "imgdir = {0}".format(str(self.__img.imgdir))

                # Check if this is our first time accessing the current image
                # or if we're just re-initializing ourselves.
                first_pass = self.__root is None

                # figure out the new root image path
                root = self.__img.root.rstrip(os.sep) + os.sep

                # initialize paths for linked image data files
                self.__root = root
                imgdir = self.__img.imgdir.rstrip(os.sep) + os.sep
                self.__path_ppkgs = os.path.join(imgdir, PATH_PPKGS)
                self.__path_prop = os.path.join(imgdir, PATH_PROP)
                self.__path_ppubs = os.path.join(imgdir, PATH_PUBS)
                self.__path_pfacets = os.path.join(imgdir, PATH_PFACETS)

                # if this isn't a reset, then load data from the image
                if first_pass:
                        # the first time around we load non-temporary data (if
                        # there is any) so that we can audit ourselves and see
                        # if we're in currently in sync.
                        self.__load(tmp=False)
                        if self.ischild():
                                self.__img_insync = self.__insync()

                        # now re-load all the data taking into account any
                        # temporary new data associated with an in-progress
                        # operation.
                        self.__load()

                # if we're not linked we're done
                if not self.__props:
                        return

                # if this is a reset, update temporal properties
                if not first_pass:
                        self.__set_current_path(self.__props, update=True)

                # Tell linked image plugins about the updated paths
                # Unused variable 'plugin'; pylint: disable=W0612
                for plugin, lip in six.iteritems(self.__plugins):
                # pylint: enable=W0612
                        lip.init_root(root)

                # Tell linked image children about the updated paths
                for lic in six.itervalues(self.__lic_dict):
                        lic.child_init_root()

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
                        for p in temporal_props:
                                # PROP_CURRENT_PARENT_PATH can only be set if
                                # we have PROP_PARENT_PATH.
                                if p is PROP_CURRENT_PARENT_PATH and \
                                    PROP_PARENT_PATH not in props:
                                        continue
                                assert p in props, \
                                    "'{0}' not in {1}".format(p, set(props))

                # update state
                self.__props = props
                self.__ppkgs = frozenset()
                self.__ppubs = None
                self.__pfacets = pkg.facet.Facets()
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
        def set_path_transform(props, path_transform,
            path=None, current_path=None, update=False):
                """Given a new path_transform, update path properties."""

                if update:
                        assert (set(props) & temporal_props), \
                            "no temporal properties are set: {0}".format(props)
                else:
                        assert not (set(props) & temporal_props), \
                            "temporal properties already set: {0}".format(props)

                # Either 'path' or 'current_path' must be specified.
                assert path is None or current_path is None
                assert path is not None or current_path is not None

                if path is not None:
                        current_path = path_transform_apply(path,
                            path_transform)

                elif current_path is not None:
                        path = path_transform_revert(current_path,
                            path_transform)

                props[PROP_PATH] = path
                props[PROP_CURRENT_PATH] = current_path
                props[PROP_PATH_TRANSFORM] = path_transform
                if PROP_PARENT_PATH in props:
                        props[PROP_CURRENT_PARENT_PATH] = path_transform_apply(
                            props[PROP_PARENT_PATH], path_transform)

        def __set_current_path(self, props, update=False):
                """Given a set of linked image properties, the image paths
                stored within those properties may not match the actual image
                paths if we're executing within an alternate root environment.
                To deal with this situation we create temporal in-memory
                properties that represent the current path to the image, and a
                transform that allows us to translate between the current path
                and the original path."""

                current_path = self.__root
                path_transform = compute_path_transform(props[PROP_PATH],
                    current_path)

                self.set_path_transform(props, path_transform,
                    current_path=current_path, update=update)

        def __guess_path_transform(self, ignore_errors=False):
                """If we're initializing parent linked image properties for
                the first time (or if those properties somehow got deleted)
                then we need to know if the parent image that we're currently
                operating on is located within an alternate root.  One way to
                do this is to ask our linked image plugins if they can
                determine this (the zones linked image plugin usually can
                if the image is a global zone)."""

                # ask each plugin if we're operating in an alternate root
                p_transforms = []
                for plugin, lip in six.iteritems(self.__plugins):
                        p_transform = lip.guess_path_transform(
                            ignore_errors=ignore_errors)
                        if p_transform is not PATH_TRANSFORM_NONE:
                                p_transforms.append((plugin, p_transform))

                if not p_transforms:
                        # no transform suggested by plugins
                        return PATH_TRANSFORM_NONE

                # check for conflicting transforms
                transforms = list(set([
                        p_transform
                        # Unused variable; pylint: disable=W0612
                        for pname, p_transform in p_transforms
                        # pylint: enable=W0612
                ]))

                if len(transforms) == 1:
                        # we have a transform from our plugins
                        return transforms[0]

                # we have conflicting transforms, time to die
                _rterr(li=self, multiple_transforms=p_transforms)

        def __fabricate_parent_props(self, ignore_errors=False):
                """Fabricate the minimum set of properties required for a
                parent image."""

                # ask our plugins if we're operating with alternate image paths
                path_transform = self.__guess_path_transform(
                    ignore_errors=ignore_errors)

                props = dict()
                self.set_path_transform(props, path_transform,
                    current_path=self.__root)
                return props

        def __load_ondisk_props(self, tmp=True):
                """Load linked image properties from disk and return them to
                the caller.  We sanity check the properties, but we don't
                update any internal linked image state.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                path = self.__path_prop
                path_tmp = "{0}.{1:d}".format(self.__path_prop,
                    global_settings.client_runid)

                # read the linked image properties from disk
                if tmp and path_exists(path_tmp):
                        path = path_tmp
                        props = load_data(path)
                elif path_exists(path):
                        props = load_data(path)
                else:
                        return None

                # make sure there are no saved temporal properties
                assert not set(props) & temporal_props

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

        def __load_ondisk_pfacets(self, tmp=True):
                """Load linked image inherited facets from disk.
                Don't update any internal state.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                pfacets = misc.EmptyDict
                path = "{0}.{1:d}".format(self.__path_pfacets,
                    global_settings.client_runid)
                if tmp and path_exists(path):
                        pfacets = load_data(path)
                else:
                        path = self.__path_pfacets
                        pfacets = load_data(path, missing_ok=True)

                if pfacets is None:
                        return None

                rv = pkg.facet.Facets()
                for k, v in six.iteritems(pfacets):
                        # W0212 Access to a protected member
                        # pylint: disable=W0212
                        rv._set_inherited(k, v)
                return rv

        def __load_ondisk_ppkgs(self, tmp=True):
                """Load linked image parent packages from disk.
                Don't update any internal state.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                fmri_strs = None
                path = "{0}.{1:d}".format(self.__path_ppkgs,
                    global_settings.client_runid)
                if tmp and path_exists(path):
                        fmri_strs = load_data(path)
                else:
                        path = self.__path_ppkgs
                        fmri_strs = load_data(path, missing_ok=True)

                if fmri_strs is None:
                        return None

                return frozenset([
                    pkg.fmri.PkgFmri(str(s))
                    for s in fmri_strs
                ])

        def __load_ondisk_ppubs(self, tmp=True):
                """Load linked image parent publishers from disk.
                Don't update any internal state.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                ppubs = None
                path = "{0}.{1:d}".format(self.__path_ppubs,
                    global_settings.client_runid)
                if tmp and path_exists(path):
                        ppubs = load_data(path)
                else:
                        path = self.__path_ppubs
                        ppubs = load_data(path, missing_ok=True)

                return ppubs

        def __load(self, tmp=True):
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
                props = self.__load_ondisk_props(tmp=tmp)
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
                        self.__set_current_path(props)

                self.__update_props(props)

                if not self.ischild():
                        return

                # load parent packages. if parent package data is missing just
                # continue along and hope for the best.
                ppkgs = self.__load_ondisk_ppkgs(tmp=tmp)
                if ppkgs is not None:
                        self.__ppkgs = ppkgs

                # load inherited facets. if inherited facet data is missing
                # just continue along and hope for the best.
                pfacets = self.__load_ondisk_pfacets(tmp=tmp)
                if pfacets is not None:
                        self.__pfacets = pfacets

                # load parent publisher data. if publisher data is missing
                # continue along and we'll just skip the publisher checks,
                # it's better than failing and preventing any image updates.
                self.__ppubs = self.__load_ondisk_ppubs(tmp=tmp)

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
                for k, v in six.iteritems(props):

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

                if len(errs) == 1:
                        raise errs[0]
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
                            user_provided_dir=True,
                            cmdpath=self.__img.cmdpath)
                except apx.ImageNotFoundException:
                        raise apx.LinkedImageException(parent_bad_img=path)

                return pimg

        def nothingtodo(self):
                """If our in-memory linked image state matches the on-disk
                linked image state then there's nothing to do.  If the state
                differs then there is stuff to do since the new state needs
                to be saved to disk."""

                # check if we're not a linked image.
                if not self.isparent() and not self.ischild():
                        # if any linked image metadata files exist they need
                        # to be deleted.
                        paths = [
                            self.__path_pfacets,
                            self.__path_ppkgs,
                            self.__path_ppubs,
                            self.__path_prop,
                        ]
                        for path in paths:
                                if path_exists(path):
                                        return False
                        return True

                # compare in-memory and on-disk properties
                li_ondisk_props = self.__load_ondisk_props(tmp=False)
                if li_ondisk_props == None:
                        li_ondisk_props = dict()
                li_inmemory_props = rm_dict_ent(self.__props,
                    temporal_props)
                if li_ondisk_props != li_inmemory_props:
                        return False

                # linked image metadata files with inherited data
                paths = [
                    self.__path_pfacets,
                    self.__path_ppkgs,
                    self.__path_ppubs,
                ]

                # check if we're just a parent image.
                if not self.ischild():
                        # parent images only have properties.  if any linked
                        # image metadata files that contain inherited
                        # information exist they need to be deleted.
                        for path in paths:
                                if path_exists(path):
                                        return False
                        return True

                # if we're missing any metadata files then there's work todo
                for path in paths:
                        if not path_exists(path):
                                return False

                # compare in-memory and on-disk inherited facets
                li_ondisk_pfacets = self.__load_ondisk_pfacets(tmp=False)
                if self.__pfacets != li_ondisk_pfacets:
                        return False

                # compare in-memory and on-disk parent packages
                li_ondisk_ppkgs = self.__load_ondisk_ppkgs(tmp=False)
                if self.__ppkgs != li_ondisk_ppkgs:
                        return False

                # compare in-memory and on-disk parent publishers
                li_ondisk_ppubs = self.__load_ondisk_ppubs(tmp=False)
                if self.__ppubs != li_ondisk_ppubs:
                        return False

                return True

        def pubcheck(self):
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

                pubs = get_pubs(self.__img)
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

        def __syncmd_from_parent(self):
                """Update linked image constraint, publisher data, and
                state from our parent image."""

                if not self.ischild():
                        # we're not a child image, nothing to do
                        return

                if self.__props[PROP_MODEL] == PV_MODEL_PUSH:
                        # parent pushes data to us, nothing to do
                        return

                # initialize the parent image
                if not self.__pimg:
                        path = self.parent_path()
                        self.__pimg = self.__init_pimg(path)

                # get metadata from our parent image
                self.__ppubs = get_pubs(self.__pimg)
                self.__ppkgs = get_packages(self.__pimg)
                self.__pfacets = get_inheritable_facets(self.__pimg)

        def syncmd_from_parent(self, catch_exception=False):
                """Update linked image constraint, publisher data, and state
                from our parent image.  If catch_exception is true catch any
                linked image exceptions and pack them up in a linked image
                return value tuple."""

                try:
                        self.__syncmd_from_parent()
                except apx.LinkedImageException as e:
                        if not catch_exception:
                                raise e
                        return LI_RVTuple(e.lix_exitrv, e, None)
                return

        def syncmd(self):
                """Write in-memory linked image state to disk."""

                # create a list of metadata file paths
                paths = [
                    self.__path_pfacets,
                    self.__path_ppkgs,
                    self.__path_ppubs,
                    self.__path_prop,
                ]

                # cleanup any temporary files
                for path in paths:
                        path = "{0}.{1:d}".format(path,
                            global_settings.client_runid)
                        path_unlink(path, noent_ok=True)

                if not self.ischild() and not self.isparent():
                        # we're no longer linked; delete metadata
                        for path in paths:
                                path_unlink(path, noent_ok=True)
                        return

                # save our properties, but first remove any temporal properties
                props = rm_dict_ent(self.__props, temporal_props)
                save_data(self.__path_prop, props)

                if not self.ischild():
                        # if we're not a child we don't have parent data
                        path_unlink(self.__path_pfacets, noent_ok=True)
                        path_unlink(self.__path_ppkgs, noent_ok=True)
                        path_unlink(self.__path_ppubs, noent_ok=True)
                        return

                # we're a child so save our latest constraints
                save_data(self.__path_pfacets, self.__pfacets)
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

        def isparent(self, li_ignore=None):
                """Indicates whether the current image is a parent image."""

                return len(self.__list_children(li_ignore=li_ignore)) > 0

        def islinked(self):
                """Indicates wether the current image is already linked."""
                return self.ischild() or self.isparent()

        def get_path_transform(self):
                """Return the current path transform property."""

                return self.__props.get(
                    PROP_PATH_TRANSFORM, PATH_TRANSFORM_NONE)

        def inaltroot(self):
                """Check if we're accessing a linked image at an alternate
                location/path."""

                return self.get_path_transform() != PATH_TRANSFORM_NONE

        def path(self):
                """Report our current image path."""

                assert self.islinked()
                return self.__props[PROP_PATH]

        def current_path(self):
                """Report our current image path."""

                assert self.islinked()
                return self.__props[PROP_CURRENT_PATH]

        def parent_path(self):
                """If we know where our parent should be, report it's expected
                location."""

                if PROP_PARENT_PATH not in self.__props:
                        return None

                path = self.__props[PROP_CURRENT_PARENT_PATH]
                assert path[-1] == "/"
                return path

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
                self.set_path_transform(props, self.get_path_transform(),
                    path=props[PROP_PATH])
                return props

        def __apx_not_child(self):
                """Raise an exception because the current image is not a child
                image."""

                return apx.LinkedImageException(self_not_child=self.__root)

        def __verify_child_name(self, lin, raise_except=False):
                """Check if a specific child image exists."""

                assert type(lin) == LinkedImageName, \
                    "{0} == LinkedImageName".format(type(lin))

                for i in self.__list_children():
                        if i[0] == lin:
                                return True

                if raise_except:
                        raise apx.LinkedImageException(child_unknown=lin)
                return False

        def verify_names(self, lin_list):
                """Given a list of linked image name objects, make sure all
                the children exist."""

                assert isinstance(lin_list, list), \
                    "type(lin_list) == {0}, str(lin_list) == {1}".format(
                    type(lin_list), str(lin_list))

                for lin in lin_list:
                        self.__verify_child_name(lin, raise_except=True)

        def inherited_facets(self):
                """Facets inherited from our parent image."""
                return self.__pfacets

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

                li_children = []
                for p in pkg.client.linkedimage.p_types:
                        for lin, path in self.__plugins[p].get_child_list(
                            ignore_errors=ignore_errors):
                                assert lin.lin_type == p
                                path = path_transform_apply(path,
                                    self.get_path_transform())
                                li_children.append([lin, path])

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
                if len(errs) == 1:
                        raise errs[0]
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

                path = self.current_path()
                li_self = (lin, REL_SELF, path)
                li_list.append(li_self)

                # if we have a path to our parent then append that as well.
                path = self.parent_path()
                if path is not None:
                        li_parent = (PV_NAME_NONE, REL_PARENT, path)
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
                    "type(props) == {0}".format(type(props))
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

                # get the cleaned up parent image path.
                path = pimg.root

                # Make sure our parent image is at it's default path.  (We
                # don't allow attaching new images if an image is located at
                # an alternate path.)
                if pimg.linked.inaltroot():
                        raise apx.LinkedImageException(attach_with_curpath=(
                            pimg.linked.path(), pimg.current_path()))

                self.__validate_attach_props(PV_MODEL_PULL, props)
                self.__validate_attach_img_paths(path, self.__root)

                # make a copy of the properties and update them
                props = props.copy()
                props[PROP_NAME] = lin
                props[PROP_MODEL] = PV_MODEL_PULL

                # If we're in an alternate root, the parent must also be within
                # that alternate root.
                path_transform = self.get_path_transform()
                if not path_transform_applied(path, path_transform):
                        raise apx.LinkedImageException(
                            parent_not_in_altroot=(path, path_transform[1]))

                # Set path related properties.  We use self.__root in place of
                # current_path() since we may not actually be linked yet.
                props[PROP_PARENT_PATH] = path.rstrip(os.sep) + os.sep
                self.set_path_transform(props, path_transform,
                    current_path=self.__root)

                for k, v in six.iteritems(lip.attach_props_def):
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

        def audit_self(self, latest_md=True):
                """If the current image is a child image, this function
                audits the current image to see if it's in sync with its
                parent."""

                if not self.ischild():
                        e = self.__apx_not_child()
                        return LI_RVTuple(pkgdefs.EXIT_OOPS, e, None)

                if not latest_md:
                        # we don't use the latest linked image metadata.
                        # instead return cached insync value which was
                        # computed using the initial linked image metadata
                        # that we loaded from disk.
                        if not self.__img_insync:
                                e = apx.LinkedImageException(
                                    child_diverged=self.child_name)
                                return LI_RVTuple(pkgdefs.EXIT_DIVERGED, e,
                                    None)
                        return LI_RVTuple(pkgdefs.EXIT_OK, None, None)

                if not self.__insync():
                        e = apx.LinkedImageException(
                            child_diverged=self.child_name)
                        return LI_RVTuple(pkgdefs.EXIT_DIVERGED, e, None)

                return LI_RVTuple(pkgdefs.EXIT_OK, None, None)

        def insync(self, latest_md=True):
                """A convenience wrapper for audit_self().  Note that we
                consider non-child images as always in sync and ignore
                any runtime errors."""

                rv = self.image.linked.audit_self(latest_md=latest_md)[0]
                if rv == pkgdefs.EXIT_DIVERGED:
                        return False
                return True

        @staticmethod
        def __rvdict2rv(rvdict, rv_map=None):
                """Internal helper function that takes a dictionary returned
                from an operations on multiple children and merges the results
                into a single return code."""

                _li_rvdict_check(rvdict)
                if type(rv_map) != type(None):
                        assert type(rv_map) == list
                        for (rv_set, rv) in rv_map:
                                assert type(rv_set) == set
                                assert type(rv) == int

                if not rvdict:
                        return LI_RVTuple(pkgdefs.EXIT_OK, None, None)

                if not rv_map:
                        rv_map = [(set([pkgdefs.EXIT_OK]), pkgdefs.EXIT_OK)]

                p_dicts = [
                    rvtuple.rvt_p_dict
                    for rvtuple in six.itervalues(rvdict)
                    if rvtuple.rvt_p_dict is not None
                ]

                rv_mapped = set()
                rv_seen = set([
                    rvtuple.rvt_rv
                    for rvtuple in six.itervalues(rvdict)
                ])
                for (rv_map_set, rv_map_rv) in rv_map:
                        if rv_seen == rv_map_set:
                                return LI_RVTuple(rv_map_rv, None, p_dicts)
                        # keep track of all the return values that are mapped
                        rv_mapped |= rv_map_set

                # the mappings better have included pkgdefs.EXIT_OK
                assert pkgdefs.EXIT_OK in rv_mapped

                # if we had errors for unmapped return values, bundle them up
                errs = [
                        rvtuple.rvt_e
                        for rvtuple in six.itervalues(rvdict)
                        if rvtuple.rvt_e and rvtuple.rvt_rv not in rv_mapped
                ]
                if len(errs) == 1:
                        err = errs[0]
                elif errs:
                        err = apx.LinkedImageException(bundle=errs)
                else:
                        err = None

                if len(rv_seen) == 1:
                        # we have one consistent return value
                        return LI_RVTuple(list(rv_seen)[0], err, p_dicts)

                return LI_RVTuple(pkgdefs.EXIT_PARTIAL, err, p_dicts)

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
                path_transform = self.__props[PROP_PATH_TRANSFORM]
                if not path_transform_applied(path, path_transform):
                        raise apx.LinkedImageException(
                            child_not_in_altroot=(path, path_transform[1]))

                # path must be an image
                try:
                        img_prefix = ar.ar_img_prefix(path)
                except OSError as e:
                        raise apx.LinkedImageException(lin=lin,
                            child_op_failed=("find", path, e))
                if not img_prefix:
                        raise apx.LinkedImageException(child_bad_img=path)

                # Does the parent image (ourselves) reside in clonable BE?
                # Unused variable 'be_uuid'; pylint: disable=W0612
                (be_name, be_uuid) = bootenv.BootEnv.get_be_name(self.__root)
                # pylint: enable=W0612
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

                # Child image should not already be linked
                img_li_data_props = os.path.join(img_prefix, PATH_PROP)
                try:
                        exists = ar.ar_exists(path, img_li_data_props)
                except OSError as e:
                        # W0212 Access to a protected member
                        # pylint: disable=W0212
                        raise apx._convert_error(e)
                if exists and not allow_relink:
                        raise apx.LinkedImageException(img_linked=path)

                self.__validate_attach_img_paths(p_root, path)

        def __validate_attach_img_paths(self, ppath, cpath):
                """Make sure there are no additional images in between the
                parent and the child. For example, this prevents linking of
                images if one of the images is nested within another unrelated
                image. This is done by looking at all the parent directories
                for both the parent and the child image until we reach a
                common ancestor."""

                # Make sure each path has a trailing '/'.
                ppath = ppath.rstrip(os.sep) + os.sep
                cpath = cpath.rstrip(os.sep) + os.sep

                # Make sure we're not linking to ourselves.
                if ppath == cpath:
                        raise apx.LinkedImageException(link_to_self=ppath)

                # The parent image can't be nested nested within child.
                if ppath.startswith(cpath):
                        raise apx.LinkedImageException(
                                parent_nested=(ppath, cpath))

                # Make sure we're not linking the root image as a child.
                if cpath == misc.liveroot():
                        raise apx.LinkedImageException(
                            attach_root_as_child=cpath)

                # Make sure our current image is at it's default path.  (We
                # don't allow attaching new images if an image is located at
                # an alternate path.)
                if self.inaltroot():
                        raise apx.LinkedImageException(attach_with_curpath=(
                            self.path(), self.current_path()))

                def abort_if_imgdir(d):
                        """Raise an exception if directory 'd' contains an
                        image."""
                        try:
                                tmp = ar.ar_img_prefix(d)
                        except OSError as e:
                                # W0212 Access to a protected member
                                # pylint: disable=W0212
                                raise apx._convert_error(e)
                        if tmp:
                                raise apx.LinkedImageException(
                                    intermediate_image=(ppath, cpath, d))

                # Find the common parent directory of the both parent and the
                # child image.
                dir_common = os.sep
                pdirs = ppath.split(os.sep)[1:-1]
                cdirs = cpath.split(os.sep)[1:-1]
                for pdir, cdir in zip(pdirs, cdirs):
                        if pdir != cdir:
                                break
                        dir_common = os.path.join(dir_common, pdir)
                dir_common = dir_common.rstrip(os.sep) + os.sep

                # Test the common parent.
                if ppath != dir_common and cpath != dir_common:
                        abort_if_imgdir(dir_common)

                # First check the parent directories of the child.
                d = os.path.dirname(cpath.rstrip(os.sep)) + os.sep
                while len(d) > len(dir_common):
                        abort_if_imgdir(d)
                        d = os.path.dirname(d.rstrip(os.sep))
                        if d != os.sep:
                                d += os.sep

                # Then check the parent directories of the parent.
                d = os.path.dirname(ppath.rstrip(os.sep)) + os.sep
                while len(d) > len(dir_common):
                        abort_if_imgdir(d)
                        d = os.path.dirname(d.rstrip(os.sep))
                        if d != os.sep:
                                d += os.sep

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

                assert type(lin) == LinkedImageName
                assert type(path) == str
                assert props == None or type(props) == dict, \
                    "type(props) == {0}".format(type(props))
                if props == None:
                        props = dict()

                lip = self.__plugins[lin.lin_type]
                if not lip.support_attach and not force:
                        e = apx.LinkedImageException(
                            attach_child_notsup=lin.lin_type)
                        return LI_RVTuple(e.lix_exitrv, e, None)

                # Path must be an absolute path.
                if not os.path.isabs(path):
                        e = apx.LinkedImageException(child_path_notabs=path)
                        return LI_RVTuple(e.lix_exitrv, e, None)

                # cleanup specified path
                cwd = os.getcwd()
                try:
                        os.chdir(path)
                except OSError as e:
                        e = apx.LinkedImageException(lin=lin,
                            child_op_failed=("access", path, e))
                        return LI_RVTuple(e.lix_exitrv, e, None)
                path = os.getcwd()
                os.chdir(cwd)

                # if the current image isn't linked yet then we need to
                # generate some linked image properties for ourselves
                if PROP_PATH not in self.__props:
                        p_props = self.__fabricate_parent_props()
                        self.__update_props(p_props)

                # sanity check the input
                try:
                        self.__validate_child_attach(lin, path, props,
                            allow_relink=allow_relink)
                except apx.LinkedImageException as e:
                        return LI_RVTuple(e.lix_exitrv, e, None)

                # make a copy of the options and start updating them
                child_props = props.copy()
                child_props[PROP_NAME] = lin
                child_props[PROP_MODEL] = PV_MODEL_PUSH

                # set path related properties
                self.set_path_transform(child_props,
                    self.get_path_transform(), current_path=path)

                # fill in any missing defaults options
                for k, v in six.iteritems(lip.attach_props_def):
                        if k not in child_props:
                                child_props[k] = v

                # attach the child in memory
                lip.attach_child_inmemory(child_props, allow_relink)

                if noexecute and li_md_only:
                        # we've validated parameters, nothing else to do
                        return LI_RVTuple(pkgdefs.EXIT_OK, None, None)

                # update the child
                try:
                        lic = LinkedImageChild(self, lin)
                except apx.LinkedImageException as e:
                        return LI_RVTuple(e.lix_exitrv, e, None)

                rvdict = {}
                list(self.__children_op(
                    _pkg_op=pkgdefs.PKG_OP_SYNC,
                    _lic_list=[lic],
                    _rvdict=rvdict,
                    _progtrack=progtrack,
                    _failfast=False,
                    _expect_plan=True,
                    _syncmd_tmp=True,
                    accept=accept,
                    li_md_only=li_md_only,
                    li_pkg_updates=li_pkg_updates,
                    noexecute=noexecute,
                    refresh_catalogs=refresh_catalogs,
                    reject_list=reject_list,
                    show_licenses=show_licenses,
                    update_index=update_index))

                rvtuple = rvdict[lin]

                if noexecute or rvtuple.rvt_rv not in [
                    pkgdefs.EXIT_OK, pkgdefs.EXIT_NOP ]:
                        return rvtuple

                # commit child image property updates
                rvtuple2 = lip.sync_children_todisk()
                _li_rvtuple_check(rvtuple2)
                if rvtuple2.rvt_e:
                        return rvtuple2

                # save parent image properties
                self.syncmd()

                # The recursive child operation may have returned NOP, but
                # since we always update our own image metadata, we always
                # return OK.
                if rvtuple.rvt_rv == pkgdefs.EXIT_NOP:
                        return LI_RVTuple(pkgdefs.EXIT_OK, None, None)
                return rvtuple

        def audit_children(self, lin_list):
                """Audit one or more children of the current image to see if
                they are in sync with this image."""

                if lin_list == []:
                        lin_list = None

                lic_dict, rvdict = self.__children_init(lin_list=lin_list,
                    failfast=False)

                list(self.__children_op(
                    _pkg_op=pkgdefs.PKG_OP_AUDIT_LINKED,
                    _lic_list=list(lic_dict.values()),
                    _rvdict=rvdict,
                    _progtrack=progress.QuietProgressTracker(),
                    _failfast=False))
                return rvdict

        def sync_children(self, lin_list, accept=False,
            li_md_only=False, li_pkg_updates=True, progtrack=None,
            noexecute=False, refresh_catalogs=True, reject_list=misc.EmptyI,
            show_licenses=False, update_index=True):
                """Sync one or more children of the current image."""

                if progtrack is None:
                        progtrack = progress.NullProgressTracker()

                if lin_list == []:
                        lin_list = None

                lic_dict = self.__children_init(lin_list=lin_list)

                _syncmd_tmp = True
                if not noexecute and li_md_only:
                        _syncmd_tmp = False

                rvdict = {}
                list(self.__children_op(
                    _pkg_op=pkgdefs.PKG_OP_SYNC,
                    _lic_list=list(lic_dict.values()),
                    _rvdict=rvdict,
                    _progtrack=progtrack,
                    _failfast=False,
                    _expect_plan=True,
                    _syncmd_tmp=_syncmd_tmp,
                    accept=accept,
                    li_md_only=li_md_only,
                    li_pkg_updates=li_pkg_updates,
                    noexecute=noexecute,
                    refresh_catalogs=refresh_catalogs,
                    reject_list=reject_list,
                    show_licenses=show_licenses,
                    update_index=update_index))
                return rvdict

        def detach_children(self, lin_list, force=False, noexecute=False,
            li_md_only=False, li_pkg_updates=True):
                """Detach one or more children from the current image. This
                operation results in the removal of any constraint package
                from the child images."""

                if lin_list == []:
                        lin_list = None

                lic_dict, rvdict = self.__children_init(lin_list=lin_list,
                    failfast=False)

                # check if we support detach for these children.  we don't use
                # iteritems() when walking lic_dict because we might modify
                # lic_dict.
                for lin in lic_dict:
                        lip = self.__plugins[lin.lin_type]
                        if lip.support_detach or force:
                                continue

                        # we can't detach this type of image.
                        e = apx.LinkedImageException(
                                detach_child_notsup=lin.lin_type)
                        rvdict[lin] = LI_RVTuple(e.lix_exitrv, e, None)
                        _li_rvtuple_check(rvdict[lin])
                        del lic_dict[lin]

                # do the detach
                list(self.__children_op(
                    _pkg_op=pkgdefs.PKG_OP_DETACH,
                    _lic_list=list(lic_dict.values()),
                    _rvdict=rvdict,
                    _progtrack=progress.NullProgressTracker(),
                    _failfast=False,
                    li_md_only=li_md_only,
                    li_pkg_updates=li_pkg_updates,
                    noexecute=noexecute))

                # if any of the children successfully detached, then we want
                # to discard our metadata for that child.
                for lin, rvtuple in six.iteritems(rvdict):

                        # if the detach failed leave metadata in parent
                        if rvtuple.rvt_e and not force:
                                continue

                        # detach the child in memory
                        lip = self.__plugins[lin.lin_type]
                        lip.detach_child_inmemory(lin)

                        if noexecute:
                                continue

                        # commit child image property updates
                        rvtuple2 = lip.sync_children_todisk()
                        _li_rvtuple_check(rvtuple2)

                        # don't overwrite previous errors
                        if rvtuple2.rvt_e and rvtuple.rvt_e is None:
                                rvdict[lin] = rvtuple2

                if not (self.ischild() or self.isparent()):
                        # we're not linked anymore, so delete all our linked
                        # properties.
                        self.__update_props()
                        self.syncmd()

                return rvdict

        def __children_op(self, _pkg_op, _lic_list, _rvdict, _progtrack,
            _failfast, _expect_plan=False, _ignore_syncmd_nop=True,
            _syncmd_tmp=False, _pd=None, **kwargs):
                """Wrapper for __children_op_vec() to stay compatible with old
                callers which only support one operation for all linked images.

                '_pkg_op' is the pkg.1 operation that we're going to perform

                '_lic_list' is a list of linked image child objects to perform
                the operation on.

                '_ignore_syncmd_nop' a boolean that indicates if we should
                always recurse into a child even if the linked image meta data
                isn't changing.

                See __children_op_vec() for an explanation of the remaining
                options."""

                for p_dict in self.__children_op_vec(
                    _lic_op_vectors=[(_pkg_op, _lic_list, kwargs,
                        _ignore_syncmd_nop)],
                    _rvdict=_rvdict,
                    _progtrack=_progtrack,
                    _failfast=_failfast,
                    _expect_plan=_expect_plan,
                    _syncmd_tmp=_syncmd_tmp,
                    _pd=_pd,
                    stage=pkgdefs.API_STAGE_DEFAULT
                    ):
                        yield p_dict

        def __children_op_vec(self, _lic_op_vectors, _rvdict, _progtrack,
            _failfast, _expect_plan=False, _syncmd_tmp=False, _pd=None,
            stage=pkgdefs.API_STAGE_DEFAULT):
                """An iterator function which performs a linked image
                operation on multiple children in parallel.

                '_lic_op_vectors' is a list of tuples containing the operation
                to perform, the list of linked images the operation is to be
                performed on, the kwargs for this operation and if the metadata
                sync nop should be ignored in the following form:
                        [(pkg_op, lin_list, kwargs, ignore_syncmd_nop), ...]

                '_rvdict' is a dictionary, indexed by linked image name, which
                contains rvtuples of the result of the operation for each
                child.

                '_prograck' is a ProgressTracker pointer.

                '_failfast' is a boolean.  If True and we encounter a failure
                operating on a child then we raise an exception immediately.
                If False then we'll attempt to perform the operation on all
                children and rvdict will contain a LI_RVTuple result for all
                children.

                '_expect_plan' is a boolean that indicates if we expect this
                operation to generate an image plan.

                '_syncmd_tmp' a boolean that indicates if we should write
                linked image metadata in a temporary location in child images,
                or just overwrite any existing data.

                '_pd' a PlanDescription pointer."""


                lic_all = reduce(operator.add,
                    [i[1] for i in _lic_op_vectors], [])
                lic_num = len(lic_all)

                # make sure we don't have any duplicate LICs or duplicate LINs
                assert lic_num == len(set(lic_all))
                assert lic_num == len(set([i.child_name for i in lic_all]))

                # At the moment the PT doesn't seem to really use the operation
                # type for display reasons. It only uses it to treat pubcheck
                # differently. Therefore it should be sufficient to skip the
                # operation type in case we have different operations going on
                # at the same time.
                # Additionally, if the operation is the same for all children
                # we can use some optimizations.
                concurrency = global_settings.client_concurrency
                if len(_lic_op_vectors) == 1:
                        pkg_op = _lic_op_vectors[0][0]

                        if pkg_op in [ pkgdefs.PKG_OP_AUDIT_LINKED,
                            pkgdefs.PKG_OP_PUBCHECK ]:
                                # These operations are cheap so ideally we'd
                                # like to use full parallelism.  But if the user
                                # specified a concurrency limit we should
                                # respect that.
                                if not global_settings.client_concurrency_set:
                                        # No limit was specified, use full
                                        # concurrency.
                                        concurrency = -1
                else:
                        pkg_op = "<various>"

                if lic_num:
                        _progtrack.li_recurse_start(pkg_op, lic_num)

                # If we have a plan for the current image that means linked
                # image metadata is probably changing so we always save it to
                # a temporary file (and we don't overwrite the existing
                # metadata until after we execute the plan).
                if _pd is not None:
                        _syncmd_tmp = True

                lic_setup = []
                for pkg_op, lic_list, kwargs, ignore_syncmd_nop in \
                    _lic_op_vectors:

                        if stage != pkgdefs.API_STAGE_DEFAULT:
                                kwargs = kwargs.copy()
                                kwargs["stage"] = stage

                        # get parent metadata common to all child images
                        _pmd = None
                        if pkg_op != pkgdefs.PKG_OP_DETACH:
                                ppubs = get_pubs(self.__img)
                                ppkgs = get_packages(self.__img, pd=_pd)
                                pfacets = get_inheritable_facets(self.__img,
                                    pd=_pd)
                                _pmd = (ppubs, ppkgs, pfacets)

                        # setup operation for each child
                        for lic in lic_list:
                                try:
                                        lic.child_op_setup(pkg_op, _pmd,
                                            _progtrack, ignore_syncmd_nop,
                                            _syncmd_tmp, **kwargs)
                                        lic_setup.append(lic)
                                except apx.LinkedImageException as e:
                                        _rvdict[lic.child_name] = \
                                            LI_RVTuple(e.lix_exitrv, e, None)

                # if _failfast is true, then throw an exception if we failed
                # to setup any of the children.  if _failfast is false we'll
                # continue to perform the operation on any children that
                # successfully initialized and we'll report setup errors along
                # with the final results for all children.
                if _failfast and _li_rvdict_exceptions(_rvdict):
                        # before we raise an exception we need to cleanup any
                        # children that we setup.
                        for lic in lic_setup:
                                lic.child_op_abort()
                        # raise an exception
                        _li_rvdict_raise_exceptions(_rvdict)

                def __child_op_finish(lic, lic_list, _rvdict,
                    _progtrack, _failfast, _expect_plan):
                        """An iterator function invoked when a child has
                        finished an operation.

                        'lic' is the child that has finished execution.

                        'lic_list' a list of children to remove 'lic' from.

                        See __children_op() for an explanation of the other
                        parameters."""

                        assert lic.child_op_is_done()

                        lic_list.remove(lic)

                        rvtuple, stdout, stderr = lic.child_op_rv(_expect_plan)
                        _li_rvtuple_check(rvtuple)
                        _rvdict[lic.child_name] = rvtuple

                        # check if we should raise an exception
                        if _failfast and _li_rvdict_exceptions(_rvdict):

                                # we're going to raise an exception.  abort
                                # the remaining children.
                                for lic in lic_list:
                                        lic.child_op_abort()

                                # raise an exception
                                _li_rvdict_raise_exceptions(_rvdict)

                        if rvtuple.rvt_rv in [ pkgdefs.EXIT_OK,
                            pkgdefs.EXIT_NOP ]:

                                # only display child output if there was no
                                # error (otherwise the exception includes the
                                # output so we'll display it twice.)
                                _progtrack.li_recurse_output(lic.child_name,
                                    stdout, stderr)

                        # check if we should yield a plan.
                        if _expect_plan and rvtuple.rvt_rv == pkgdefs.EXIT_OK:
                                yield rvtuple.rvt_p_dict

                # check if we did everything we needed to do during child
                # setup.  (this can happen if we're just doing an implicit
                # syncmd during setup we discover the linked image metadata
                # isn't changing.)  we iterate over a copy of lic_setup to
                # allow __child_op_finish() to remove elements from lic_setup
                # while we're walking through it.
                for lic in copy.copy(lic_setup):
                        if not lic.child_op_is_done():
                                continue
                        for p_dict in __child_op_finish(lic, lic_setup,
                            _rvdict, _progtrack, _failfast,
                            _expect_plan):
                                yield p_dict

                # keep track of currently running children
                lic_running = []

                # keep going as long as there are children to process
                progtrack_update = False
                while len(lic_setup) or len(lic_running):

                        while lic_setup and (
                            concurrency > len(lic_running) or
                            concurrency <= 0):
                                # start processing on a child
                                progtrack_update = True
                                lic = lic_setup.pop()
                                lic_running.append(lic)
                                lic.child_op_start()

                        if progtrack_update:
                                # display progress on children
                                progtrack_update = False
                                done = lic_num - len(lic_setup) - \
                                    len(lic_running)
                                lin_running = sorted([
                                    lic.child_name for lic in lic_running])
                                _progtrack.li_recurse_status(lin_running,
                                    done)

                        # poll on all the linked image children and see which
                        # ones have pending output.
                        fd_hash = dict([
                            (lic.fileno(), lic)
                            for lic in lic_running
                        ])
                        p = select.poll()
                        for fd in fd_hash.keys():
                                p.register(fd, select.POLLIN)
                        events = p.poll()
                        lic_list = [ fd_hash[event[0]] for event in events ]

                        for lic in lic_list:
                                _progtrack.li_recurse_progress(lic.child_name)
                                if not lic.child_op_is_done():
                                        continue
                                # a child finished processing
                                progtrack_update = True
                                for p_dict in __child_op_finish(lic,
                                    lic_running, _rvdict, _progtrack,
                                    _failfast, _expect_plan):
                                        yield p_dict

                _li_rvdict_check(_rvdict)
                if lic_num:
                        _progtrack.li_recurse_end()

        def __children_init(self, lin_list=None, li_ignore=None, failfast=True):
                """Initialize LinkedImageChild objects for children specified
                in 'lin_list'.  If 'lin_list' is not specified, then
                initialize objects for all children (excluding any being
                ignored via 'li_ignore')."""

                # you can't specify children to operate on and children to be
                # ignored at the same time
                assert lin_list is None or li_ignore is None

                # if no children we listed, build a list of children
                if lin_list is None:
                        lin_list = [
                            i[0]
                            for i in self.__list_children(li_ignore)
                        ]
                else:
                        self.verify_names(lin_list)

                rvdict = {}
                lic_dict = {}
                for lin in lin_list:
                        try:
                                lic = LinkedImageChild(self, lin)
                                lic_dict[lin] = lic
                        except apx.LinkedImageException as e:
                                rvdict[lin] = LI_RVTuple(e.lix_exitrv, e, None)

                if failfast:
                        _li_rvdict_raise_exceptions(rvdict)
                        return lic_dict

                return (lic_dict, rvdict)

        def __recursion_init(self, li_ignore):
                """Initialize child objects used during recursive packaging
                operations."""

                self.__lic_ignore = li_ignore
                self.__lic_dict = self.__children_init(li_ignore=li_ignore)

        def api_recurse_init(self, li_ignore=None, repos=None):
                """Initialize planning state.  If we're a child image we save
                our current state (which may reflect a planned state that we
                have not committed to disk) into the plan.  We also initialize
                all our children to prepare to recurse into them."""

                if PROP_RECURSE in self.__props and \
                    not self.__props[PROP_RECURSE]:
                        # we don't want to recurse
                        self.__recursion_init(li_ignore=[])
                        return

                # Initialize children
                self.__recursion_init(li_ignore)

                if not self.__lic_dict:
                        # we don't need to recurse
                        return

                # if we have any children we don't support operations using
                # temporary repositories.
                if repos:
                        raise apx.PlanCreationException(no_tmp_origins=True)

        def api_recurse_pubcheck(self, progtrack):
                """Do a recursive publisher check"""

                # get a list of of children to recurse into.
                lic_list = list(self.__lic_dict.values())

                # do a publisher check on all of them
                rvdict = {}
                list(self.__children_op(
                    _pkg_op=pkgdefs.PKG_OP_PUBCHECK,
                    _lic_list=lic_list,
                    _rvdict=rvdict,
                    _progtrack=progtrack,
                    _failfast=False))

                # raise an exception if one or more children failed the
                # publisher check.
                _li_rvdict_raise_exceptions(rvdict)

        def __api_recurse(self, stage, progtrack):
                """This is an iterator function.  It recurses into linked
                image children to perform the specified operation.
                """

                # get a pointer to the current image plan
                pd = self.__img.imageplan.pd

                # get a list of of children to recurse into.
                lic_list = list(self.__lic_dict.values())

                # sanity check stage
                assert stage in [pkgdefs.API_STAGE_PLAN,
                    pkgdefs.API_STAGE_PREPARE, pkgdefs.API_STAGE_EXECUTE]

                # if we're ignoring all children then we can't be recursing
                assert pd.children_ignored != [] or lic_list == []

                # sanity check the plan description state
                if stage == pkgdefs.API_STAGE_PLAN:
                        # the state should be uninitialized
                        assert pd.children_planned == []
                        assert pd.children_nop == []
                else:
                        # if we ignored all children, we better not have
                        # recursed into any children.
                        assert pd.children_ignored != [] or \
                            pd.children_planned == pd.children_nop == []

                        # there shouldn't be any overloap between sets of
                        # children in the plan
                        assert not (set(pd.children_planned) &
                            set(pd.children_nop))
                        if pd.children_ignored:
                                assert not (set(pd.children_ignored) &
                                    set(pd.children_planned))
                                assert not (set(pd.children_ignored) &
                                    set(pd.children_nop))

                        # make sure set of child handles matches the set of
                        # previously planned children.
                        assert set(self.__lic_dict) == set(pd.children_planned)

                # if we're in the planning stage, we should pass the current
                # image plan onto the child and also expect an image plan from
                # the child.
                expect_plan = False
                if stage == pkgdefs.API_STAGE_PLAN:
                        expect_plan = True

                # Assemble list of LICs from LINs in pd.child_op_vectors and
                # create new lic_op_vectors to pass to __children_op_vec().
                lic_op_vectors = []
                for op, lin_list, kwargs, ignore_syncmd_nop in \
                    pd.child_op_vectors:
                        assert "stage" not in kwargs
                        lic_list = []
                        for l in lin_list:
                                try:
                                        lic_list.append(self.__lic_dict[l])
                                except KeyError:
                                        # For the prepare and execute phase we
                                        # remove children for which there is
                                        # nothing to do from self.__lic_dict.
                                        # So ignore those we can't find.
                                        pass
                        lic_op_vectors.append((op, lic_list, kwargs,
                            ignore_syncmd_nop))

                rvdict = {}
                for p_dict in self.__children_op_vec(
                    _lic_op_vectors=lic_op_vectors,
                    _rvdict=rvdict,
                    _progtrack=progtrack,
                    _failfast=True,
                    _expect_plan=expect_plan,
                    stage=stage,
                    _pd=pd):
                        yield p_dict

                assert not _li_rvdict_exceptions(rvdict)

                for lin in rvdict:
                        # check for children that don't need any updates
                        if rvdict[lin].rvt_rv == pkgdefs.EXIT_NOP:
                                assert lin not in pd.children_nop
                                pd.children_nop.append(lin)
                                del self.__lic_dict[lin]

                        # record the children that are done planning
                        if stage == pkgdefs.API_STAGE_PLAN and \
                            rvdict[lin].rvt_rv == pkgdefs.EXIT_OK:
                                assert lin not in pd.children_planned
                                pd.children_planned.append(lin)

        @staticmethod
        def __recursion_ops(api_op):
                """Determine what pkg command to use when recursing into child
                images."""

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


                # To improve performance we assume the child is already in sync,
                # so if its linked image metadata isn't changing then the child
                # won't need any updates so there will be no need to recurse
                # into it.
                ignore_syncmd_nop = False
                pkg_op_erecurse = None

                if api_op == pkgdefs.API_OP_SYNC:
                        pkg_op_irecurse = pkgdefs.PKG_OP_SYNC
                        # If we are doing an explict sync, we do have to make
                        # sure we actually recurse into the child and sync
                        # metadata.
                        ignore_syncmd_nop = True
                elif api_op == pkgdefs.API_OP_INSTALL:
                        pkg_op_irecurse = pkgdefs.PKG_OP_SYNC
                        pkg_op_erecurse = pkgdefs.PKG_OP_INSTALL
                elif api_op == pkgdefs.API_OP_CHANGE_FACET:
                        pkg_op_irecurse = pkgdefs.PKG_OP_SYNC
                        pkg_op_erecurse = pkgdefs.PKG_OP_CHANGE_FACET
                elif api_op == pkgdefs.API_OP_CHANGE_VARIANT:
                        pkg_op_irecurse = pkgdefs.PKG_OP_SYNC
                        pkg_op_erecurse = pkgdefs.PKG_OP_CHANGE_VARIANT
                if api_op == pkgdefs.API_OP_UPDATE:
                        pkg_op_irecurse = pkgdefs.PKG_OP_SYNC
                        pkg_op_erecurse = pkgdefs.PKG_OP_UPDATE
                elif api_op == pkgdefs.API_OP_UNINSTALL:
                        pkg_op_irecurse = pkgdefs.PKG_OP_SYNC
                        pkg_op_erecurse = pkgdefs.PKG_OP_UNINSTALL
                else:
                        pkg_op_irecurse = pkgdefs.PKG_OP_SYNC

                return pkg_op_irecurse, pkg_op_erecurse, ignore_syncmd_nop

        @staticmethod
        def __recursion_args(op, refresh_catalogs, update_index, api_kwargs):
                """Determine what pkg command arguments to use when recursing
                into child images."""

                kwargs = {}
                kwargs["noexecute"] = api_kwargs["noexecute"]
                kwargs["refresh_catalogs"] = refresh_catalogs
                kwargs["show_licenses"] = False
                kwargs["update_index"] = update_index

                #
                # when we recurse we always accept all new licenses (for now).
                #
                # ultimately (when start yielding back plan descriptions for
                # children) in addition to accepting licenses on the plan for
                # the current image the api client will also have to
                # explicitly accept licenses for all child images.  but until
                # that happens we'll just assume that the parent image license
                # space is a superset of the child image license space (and
                # since the api consumer must accept licenses in the parent
                # before we'll do anything, we'll assume licenses in the child
                # are accepted as well).
                #
                kwargs["accept"] = True

                if "li_pkg_updates" in api_kwargs:
                        # option specific to: attach, set-property-linked, sync
                        kwargs["li_pkg_updates"] = api_kwargs["li_pkg_updates"]

                if op == pkgdefs.PKG_OP_INSTALL:
                        assert "pkgs_inst" in api_kwargs
                        # option specific to: install
                        kwargs["pkgs_inst"] = api_kwargs["pkgs_inst"]
                        kwargs["reject_list"] = api_kwargs["reject_list"]
                elif op == pkgdefs.PKG_OP_CHANGE_VARIANT:
                        assert "variants" in api_kwargs
                        # option specific to: change-variant
                        kwargs["variants"] = api_kwargs["variants"]
                        kwargs["facets"] = None
                        kwargs["reject_list"] = api_kwargs["reject_list"]
                elif op == pkgdefs.PKG_OP_CHANGE_FACET:
                        assert "facets" in api_kwargs
                        # option specific to: change-facet
                        kwargs["facets"] = api_kwargs["facets"]
                        kwargs["variants"] = None
                        kwargs["reject_list"] = api_kwargs["reject_list"]
                elif op == pkgdefs.PKG_OP_UNINSTALL:
                        assert "pkgs_to_uninstall" in api_kwargs
                        # option specific to: uninstall
                        kwargs["pkgs_to_uninstall"] = \
                            api_kwargs["pkgs_to_uninstall"]
                        del kwargs["show_licenses"]
                        del kwargs["refresh_catalogs"]
                        del kwargs["accept"]
                elif op == pkgdefs.PKG_OP_UPDATE:
                        # skip ipkg up to date check for child images
                        kwargs["force"] = True
                        kwargs["pkgs_update"] = api_kwargs["pkgs_update"]
                        kwargs["reject_list"] = api_kwargs["reject_list"]

                return kwargs

        def api_recurse_plan(self, api_kwargs, erecurse_list, refresh_catalogs,
            update_index, progtrack):
                """Plan child image updates."""

                pd = self.__img.imageplan.pd
                api_op = pd.plan_type

                pd.child_op_vectors = []

                # Get LinkedImageNames of all children
                lin_list = list(self.__lic_dict.keys())

                pkg_op_irecurse, pkg_op_erecurse, ignore_syncmd_nop = \
                    self.__recursion_ops(api_op)

                # Prepare op vector for explicit recurse operations
                if erecurse_list:
                        assert pkg_op_erecurse
                        # remove recurse children from sync list
                        lin_list = list(set(lin_list) - set(erecurse_list))

                        erecurse_kwargs = self.__recursion_args(pkg_op_erecurse,
                            refresh_catalogs, update_index, api_kwargs)
                        pd.child_op_vectors.append((pkg_op_erecurse,
                            list(erecurse_list), erecurse_kwargs, True))

                # Prepare op vector for implicit recurse operations
                irecurse_kwargs = self.__recursion_args(pkg_op_irecurse,
                    refresh_catalogs, update_index, api_kwargs)

                pd.child_op_vectors.append((pkg_op_irecurse, lin_list,
                    irecurse_kwargs, ignore_syncmd_nop))

                pd.children_ignored = self.__lic_ignore

                # recurse into children
                for p_dict in self.__api_recurse(pkgdefs.API_STAGE_PLAN,
                    progtrack):
                        yield p_dict

        def api_recurse_prepare(self, progtrack):
                """Prepare child image updates."""
                progtrack.set_major_phase(progtrack.PHASE_DOWNLOAD)
                list(self.__api_recurse(pkgdefs.API_STAGE_PREPARE, progtrack))

        def api_recurse_execute(self, progtrack):
                """Execute child image updates."""
                progtrack.set_major_phase(progtrack.PHASE_FINALIZE)
                list(self.__api_recurse(pkgdefs.API_STAGE_EXECUTE, progtrack))

        def init_plan(self, pd):
                """Initialize our state in the PlanDescription."""

                # if we're a child, save our parent package state into the
                # plan description
                pd.li_props = rm_dict_ent(self.__props.copy(), temporal_props)
                pd.li_ppkgs = self.__ppkgs
                pd.li_ppubs = self.__ppubs
                pd.li_pfacets = self.__pfacets

        def setup_plan(self, pd):
                """Reload a previously created plan."""

                # make a copy of the linked image properties
                props = pd.li_props.copy()

                # generate temporal properties
                if props:
                        self.__set_current_path(props)

                # load linked image state from the plan
                self.__update_props(props)
                self.__ppubs = pd.li_ppubs
                self.__ppkgs = pd.li_ppkgs
                self.__pfacets = pd.li_pfacets

                # now initialize our recursion state, this involves allocating
                # handles to operate on children.  we don't need handles for
                # children that were either ignored during planning, or which
                # return EXIT_NOP after planning (since these children don't
                # need any updates).
                li_ignore = copy.copy(pd.children_ignored)

                # merge the children that returned nop into li_ignore (since
                # we don't need to recurse into them).  if li_ignore is [],
                # then we ignored all children during planning
                if li_ignore != [] and pd.children_nop:
                        if li_ignore is None:
                                # no children were ignored during planning
                                li_ignore = []
                        li_ignore += pd.children_nop

                # Initialize children
                self.__recursion_init(li_ignore=li_ignore)

        def recurse_nothingtodo(self):
                """Return True if there is no planned work to do on child
                image."""

                for lic in six.itervalues(self.__lic_dict):
                        if lic.child_name not in \
                            self.__img.imageplan.pd.children_nop:
                                return False
                return True


class LinkedImageChild(object):
        """A LinkedImageChild object is used when a parent image wants to
        access a child image.  These accesses may include things like:
        saving/pushing linked image metadata into a child image, syncing or
        auditing a child image, or recursing into a child image to keep it in
        sync with planned changes in the parent image."""

        def __init__(self, li, lin):
                assert isinstance(li, LinkedImage), \
                    "isinstance({0}, LinkedImage)".format(type(li))
                assert isinstance(lin, LinkedImageName), \
                    "isinstance({0}, LinkedImageName)".format(type(lin))

                # globals
                self.__linked = li
                self.__img = li.image

                # cache properties.
                self.__props = self.__linked.child_props(lin)
                assert self.__props[PROP_NAME] == lin

                try:
                        imgdir = ar.ar_img_prefix(self.child_path)
                except OSError as e:
                        raise apx.LinkedImageException(lin=lin,
                            child_op_failed=("find", self.child_path, e))

                if not imgdir:
                        raise apx.LinkedImageException(
                            lin=lin, child_bad_img=self.child_path)

                # initialize paths for linked image data files
                self.__path_ppkgs = os.path.join(imgdir, PATH_PPKGS)
                self.__path_prop = os.path.join(imgdir, PATH_PROP)
                self.__path_ppubs = os.path.join(imgdir, PATH_PUBS)
                self.__path_pfacets = os.path.join(imgdir, PATH_PFACETS)

                # initialize a linked image child plugin
                self.__plugin = \
                    pkg.client.linkedimage.p_classes_child[lin.lin_type](self)

                self.__pkg_remote = pkg.client.pkgremote.PkgRemote()
                self.__child_op_rvtuple = None
                self.__child_op = None

        @property
        def child_name(self):
                """Get the name associated with a child image."""
                return self.__props[PROP_NAME]

        @property
        def child_path(self):
                """Get the path associated with a child image."""

                if self.__linked.inaltroot():
                        return self.__props[PROP_CURRENT_PATH]
                return self.__props[PROP_PATH]

        @property
        def child_pimage(self):
                """Get a pointer to the parent image object associated with
                this child."""
                return self.__img

        def __push_data(self, root, path, data, tmp, test):
                """Write data to a child image."""

                try:
                        # first save our data to a temporary file
                        path_tmp = "{0}.{1}".format(path,
                            global_settings.client_runid)
                        save_data(path_tmp, data, root=root,
                            catch_exception=False)

                        # Check if the data is changing.  To do this
                        # comparison we load the serialized on-disk json data
                        # into memory because there are no guarantees about
                        # data ordering during serialization.  When loading
                        # the data we don't bother decoding it into objects.
                        updated = True
                        old_data = load_data(path, missing_ok=True,
                            root=root, decode=False,
                            catch_exception=False)
                        if old_data is not None:
                                new_data = load_data(path_tmp,
                                    root=root, decode=False,
                                    catch_exception=False)
                                # We regard every combination of the same
                                # elements in a list being the same data, for
                                # example, ["a", "b"] equals ["b", "a"], so we
                                # need to sort the list first before comparison
                                # because ["a", "b"] != ["b", "a"] in Python.
                                if isinstance(old_data, list) and \
                                     isinstance(new_data, list):
                                        old_data = sorted(old_data)
                                        new_data = sorted(new_data)
                                if old_data == new_data:
                                        updated = False


                        # If we're not actually updating any data, or if we
                        # were just doing a test to see if the data has
                        # changed, then delete the temporary data file.
                        if not updated or test:
                                ar.ar_unlink(root, path_tmp)
                                return updated

                        if not tmp:
                                ar.ar_rename(root, path_tmp, path)

                except OSError as e:
                        raise apx.LinkedImageException(lin=self.child_name,
                            child_op_failed=("metadata update",
                            self.child_path, e))

                return True

        def __push_ppkgs(self, ppkgs, tmp=False, test=False):
                """Sync linked image parent constraint data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                # save the planned parent packages
                return self.__push_data(self.child_path, self.__path_ppkgs,
                    ppkgs, tmp, test)

        def __push_pfacets(self, pfacets, tmp=False, test=False):
                """Sync linked image parent facet data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                # save the planned parent facets
                return self.__push_data(self.child_path, self.__path_pfacets,
                    pfacets, tmp, test)


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

        def __push_ppubs(self, ppubs, tmp=False, test=False):
                """Sync linked image parent publisher data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                return self.__push_data(self.child_path, self.__path_ppubs,
                    ppubs, tmp, test)

        def __syncmd(self, pmd, tmp=False, test=False):
                """Sync linked image data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                # unpack parent metadata tuple
                ppubs, ppkgs, pfacets = pmd

                ppkgs_updated = self.__push_ppkgs(ppkgs, tmp, test)
                props_updated = self.__push_props(tmp, test)
                pubs_updated = self.__push_ppubs(ppubs, tmp, test)
                pfacets_updated = self.__push_pfacets(pfacets, tmp, test)

                return (props_updated or ppkgs_updated or pubs_updated or
                    pfacets_updated)

        def __child_op_setup_syncmd(self, pmd, ignore_syncmd_nop=True,
            tmp=False, test=False, stage=pkgdefs.API_STAGE_DEFAULT):
                """Prepare to perform an operation on a child image by syncing
                the latest linked image data to that image.  As part of this
                operation, if we discover that the meta data hasn't changed we
                may report back that there is nothing to do (EXIT_NOP).

                'pmd' is a tuple that contains parent metadata that we will
                sync to the child image.  Note this is not all the metadata
                that we will sync, just the set which is common to all
                children.

                'ignore_syncmd_nop' a boolean that indicates if we should
                always recurse into a child even if the linked image meta data
                isn't changing.

                'tmp' a boolean that indicates if we should save the child
                image meta data into temporary files (instead of overwriting
                the persistent meta data files).

                'test' a boolean that indicates we shouldn't save any child
                image meta data, instead we should just test to see if the
                meta data is changing.

                'stage' indicates which stage of execution we should be
                performing on a child image."""

                # we don't update metadata during all stages of operation
                if stage not in [
                    pkgdefs.API_STAGE_DEFAULT, pkgdefs.API_STAGE_PLAN]:
                        return True

                try:
                        updated = self.__syncmd(pmd, tmp=tmp, test=test)
                except apx.LinkedImageException as e:
                        self.__child_op_rvtuple = \
                            LI_RVTuple(e.lix_exitrv, e, None)
                        return False

                if ignore_syncmd_nop:
                        # we successfully updated the metadata
                        return True

                # if the metadata changed then report success
                if updated:
                        return True

                # the metadata didn't change, so this operation is a NOP
                self.__child_op_rvtuple = \
                    LI_RVTuple(pkgdefs.EXIT_NOP, None, None)
                return False

        def __child_setup_sync(self, _pmd, _progtrack, _ignore_syncmd_nop,
            _syncmd_tmp,
            accept=False,
            li_md_only=False,
            li_pkg_updates=True,
            noexecute=False,
            refresh_catalogs=True,
            reject_list=misc.EmptyI,
            show_licenses=False,
            stage=pkgdefs.API_STAGE_DEFAULT,
            update_index=True):
                """Prepare to sync a child image.  This involves updating the
                linked image metadata in the child and then possibly recursing
                into the child to actually update packages.

                For descriptions of parameters please see the descriptions in
                api.py`gen_plan_*"""

                if li_md_only:
                        #
                        # we're not going to recurse into the child image,
                        # we're just going to update its metadata.
                        #
                        # we don't support updating packages in the parent
                        # during attach metadata only sync.
                        #
                        if not self.__child_op_setup_syncmd(_pmd,
                            ignore_syncmd_nop=False,
                            test=noexecute, stage=stage):
                                # the update failed
                                return
                        self.__child_op_rvtuple = \
                            LI_RVTuple(pkgdefs.EXIT_OK, None, None)
                        return

                #
                # first sync the metadata
                #
                # if we're doing this sync as part of an attach, then
                # temporarily sync the metadata since we don't know yet if the
                # attach will succeed.  if the attach doesn't succeed this
                # means we don't have to delete any metadata.  if the attach
                # succeeds the child will make the temporary metadata
                # permanent as part of the commit.
                #
                # we don't support updating packages in the parent
                # during attach.
                #
                if not self.__child_op_setup_syncmd(_pmd,
                    ignore_syncmd_nop=_ignore_syncmd_nop,
                    tmp=_syncmd_tmp, stage=stage):
                        # the update failed or the metadata didn't change
                        return

                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_SYNC,
                    accept=accept,
                    backup_be=None,
                    backup_be_name=None,
                    be_activate=True,
                    be_name=None,
                    li_ignore=None,
                    li_md_only=li_md_only,
                    li_parent_sync=True,
                    li_pkg_updates=li_pkg_updates,
                    li_target_all=False,
                    li_target_list=[],
                    new_be=None,
                    noexecute=noexecute,
                    origins=[],
                    parsable_version=\
                        global_settings.client_output_parsable_version,
                    quiet=global_settings.client_output_quiet,
                    refresh_catalogs=refresh_catalogs,
                    reject_pats=reject_list,
                    show_licenses=show_licenses,
                    stage=stage,
                    update_index=update_index,
                    verbose=global_settings.client_output_verbose)

        def __child_setup_update(self, _pmd, _progtrack, _syncmd_tmp,
            accept, force, noexecute, pkgs_update, refresh_catalogs,
            reject_list, show_licenses, stage, update_index):
                """Prepare to update a child image."""

                # first sync the metadata
                if not self.__child_op_setup_syncmd(_pmd,
                    ignore_syncmd_nop=True,
                    tmp=_syncmd_tmp, stage=stage):
                        # the update failed or the metadata didn't change
                        return

                # We need to make sure we don't pass None as pargs in
                # client.py`update()
                if pkgs_update is None:
                        pkgs_update = []

                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_UPDATE,
                    act_timeout=0,
                    accept=accept,
                    backup_be=None,
                    backup_be_name=None,
                    be_activate=True,
                    be_name=None,
                    force=force,
                    ignore_missing=True,
                    li_erecurse=None,
                    li_ignore=None,
                    li_parent_sync=True,
                    new_be=None,
                    noexecute=noexecute,
                    origins=[],
                    pargs=pkgs_update,
                    parsable_version=\
                        global_settings.client_output_parsable_version,
                    quiet=global_settings.client_output_quiet,
                    refresh_catalogs=refresh_catalogs,
                    reject_pats=reject_list,
                    show_licenses=show_licenses,
                    stage=stage,
                    update_index=update_index,
                    verbose=global_settings.client_output_verbose)

        def __child_setup_install(self, _pmd, _progtrack, _syncmd_tmp,
            accept, noexecute, pkgs_inst, refresh_catalogs, reject_list,
            show_licenses, stage, update_index):
                """Prepare to install a pkg in a child image."""

                # first sync the metadata
                if not self.__child_op_setup_syncmd(_pmd,
                    ignore_syncmd_nop=True,
                    tmp=_syncmd_tmp, stage=stage):
                        # the update failed or the metadata didn't change
                        return

                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_INSTALL,
                    accept=accept,
                    act_timeout=0,
                    backup_be=None,
                    backup_be_name=None,
                    be_activate=True,
                    be_name=None,
                    li_erecurse=None,
                    li_ignore=None,
                    li_parent_sync=True,
                    new_be=None,
                    noexecute=noexecute,
                    origins=[],
                    pargs=pkgs_inst,
                    parsable_version=\
                        global_settings.client_output_parsable_version,
                    quiet=global_settings.client_output_quiet,
                    refresh_catalogs=refresh_catalogs,
                    reject_pats=reject_list,
                    show_licenses=show_licenses,
                    stage=stage,
                    update_index=update_index,
                    verbose=global_settings.client_output_verbose)

        def __child_setup_uninstall(self, _pmd, _progtrack, _syncmd_tmp,
            noexecute, pkgs_to_uninstall, stage, update_index):
                """Prepare to install a pkg in a child image."""

                # first sync the metadata
                if not self.__child_op_setup_syncmd(_pmd,
                    ignore_syncmd_nop=True,
                    tmp=_syncmd_tmp, stage=stage):
                        # the update failed or the metadata didn't change
                        return

                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_UNINSTALL,
                    act_timeout=0,
                    backup_be=None,
                    backup_be_name=None,
                    be_activate=True,
                    be_name=None,
                    li_erecurse=None,
                    li_ignore=None,
                    li_parent_sync=True,
                    new_be=None,
                    noexecute=noexecute,
                    pargs=pkgs_to_uninstall,
                    parsable_version=\
                        global_settings.client_output_parsable_version,
                    quiet=global_settings.client_output_quiet,
                    stage=stage,
                    update_index=update_index,
                    ignore_missing=True,
                    verbose=global_settings.client_output_verbose)

        def __child_setup_change_varcets(self, _pmd, _progtrack, _syncmd_tmp,
            accept, facets, noexecute, refresh_catalogs, reject_list,
            show_licenses, stage, update_index, variants):
                """Prepare to install a pkg in a child image."""

                # first sync the metadata
                if not self.__child_op_setup_syncmd(_pmd,
                    ignore_syncmd_nop=True,
                    tmp=_syncmd_tmp, stage=stage):
                        # the update failed or the metadata didn't change
                        return

                assert not (variants and facets)
                if variants:
                        op = pkgdefs.PKG_OP_CHANGE_VARIANT
                        varcet_dict = variants
                else:
                        op = pkgdefs.PKG_OP_CHANGE_FACET
                        varcet_dict = facets

                # need to transform varcets back to string list
                varcets = [ "{0}={1}".format(a, b) for (a, b) in
                    varcet_dict.items()]

                self.__pkg_remote.setup(self.child_path,
                    op,
                    accept=accept,
                    act_timeout=0,
                    backup_be=None,
                    backup_be_name=None,
                    be_activate=True,
                    be_name=None,
                    li_erecurse=None,
                    li_ignore=None,
                    li_parent_sync=True,
                    new_be=None,
                    noexecute=noexecute,
                    origins=[],
                    pargs=varcets,
                    parsable_version=\
                        global_settings.client_output_parsable_version,
                    quiet=global_settings.client_output_quiet,
                    refresh_catalogs=refresh_catalogs,
                    reject_pats=reject_list,
                    show_licenses=show_licenses,
                    stage=stage,
                    update_index=update_index,
                    verbose=global_settings.client_output_verbose)

        def __child_setup_detach(self, _progtrack, li_md_only=False,
            li_pkg_updates=True, noexecute=False):
                """Prepare to detach a child image."""

                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_DETACH,
                    force=True,
                    li_md_only=li_md_only,
                    li_pkg_updates=li_pkg_updates,
                    li_target_all=False,
                    li_target_list=[],
                    noexecute=noexecute,
                    quiet=global_settings.client_output_quiet,
                    verbose=global_settings.client_output_verbose)

        def __child_setup_pubcheck(self, _pmd):
                """Prepare to a check if a child's publishers are in sync."""

                # first sync the metadata
                # a pubcheck should never update persistent meta data
                if not self.__child_op_setup_syncmd(_pmd, tmp=True):
                        # the update failed
                        return

                # setup recursion into the child image
                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_PUBCHECK)

        def __child_setup_audit(self, _pmd):
                """Prepare to a child image to see if it's in sync with its
                constraints."""

                # first sync the metadata
                if not self.__child_op_setup_syncmd(_pmd, tmp=True):
                        # the update failed
                        return

                # setup recursion into the child image
                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_AUDIT_LINKED,
                    li_parent_sync=True,
                    li_target_all=False,
                    li_target_list=[],
                    omit_headers=True,
                    quiet=True)

        def child_op_abort(self):
                """Public interface to abort an operation on a child image."""

                self.__pkg_remote.abort()
                self.__child_op_rvtuple = None
                self.__child_op = None

        def child_op_setup(self, _pkg_op, _pmd, _progtrack, _ignore_syncmd_nop,
            _syncmd_tmp, **kwargs):
                """Public interface to setup an operation that we'd like to
                perform on a child image."""

                assert self.__child_op_rvtuple is None
                assert self.__child_op is None

                self.__child_op = _pkg_op

                if _pkg_op == pkgdefs.PKG_OP_AUDIT_LINKED:
                        self.__child_setup_audit(_pmd, **kwargs)
                elif _pkg_op == pkgdefs.PKG_OP_DETACH:
                        self.__child_setup_detach(_progtrack, **kwargs)
                elif _pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        self.__child_setup_pubcheck(_pmd, **kwargs)
                elif _pkg_op == pkgdefs.PKG_OP_SYNC:
                        self.__child_setup_sync(_pmd, _progtrack,
                            _ignore_syncmd_nop, _syncmd_tmp, **kwargs)
                elif _pkg_op == pkgdefs.PKG_OP_UPDATE:
                        self.__child_setup_update(_pmd, _progtrack,
                            _syncmd_tmp, **kwargs)
                elif _pkg_op == pkgdefs.PKG_OP_INSTALL:
                        self.__child_setup_install(_pmd, _progtrack,
                            _syncmd_tmp, **kwargs)
                elif _pkg_op == pkgdefs.PKG_OP_UNINSTALL:
                        self.__child_setup_uninstall(_pmd, _progtrack,
                            _syncmd_tmp, **kwargs)
                elif _pkg_op == pkgdefs.PKG_OP_CHANGE_FACET or \
                    _pkg_op == pkgdefs.PKG_OP_CHANGE_VARIANT:
                        self.__child_setup_change_varcets(_pmd, _progtrack,
                            _syncmd_tmp, **kwargs)
                else:
                        raise RuntimeError(
                            "Unsupported package client op: {0}".format(
                            _pkg_op))

        def child_op_start(self):
                """Public interface to start an operation on a child image."""

                # if we have a return value this operation is done
                if self.__child_op_rvtuple is not None:
                        return True

                self.__pkg_remote.start()

        def child_op_is_done(self):
                """Public interface to query if an operation on a child image
                is done."""

                # if we have a return value this operation is done
                if self.__child_op_rvtuple is not None:
                        return True

                # make sure there is some data from the child
                return self.__pkg_remote.is_done()

        def child_op_rv(self, expect_plan):
                """Public interface to get the result of an operation on a
                child image.

                'expect_plan' boolean indicating if the child is performing a
                planning operation.  this is needed because if we're running
                in parsable output mode then the child will emit a parsable
                json version of the plan on stdout, and we'll verify it by
                running it through the json parser.
                """

                # The child op is now done, so we reset __child_op to make sure
                # we don't accidentally reuse the LIC without properly setting
                # it up again. However, we still need the op type in this
                # function so we make a copy.
                pkg_op = self.__child_op
                self.__child_op = None

                # if we have a return value this operation is done
                if self.__child_op_rvtuple is not None:
                        rvtuple = self.__child_op_rvtuple
                        self.__child_op_rvtuple = None
                        return (rvtuple, None, None)

                # make sure we're not going to block
                assert self.__pkg_remote.is_done()

                (rv, e, stdout, stderr) = self.__pkg_remote.result()
                if e is not None:
                        rv = pkgdefs.EXIT_OOPS

                # if we got an exception, or a return value other than OK or
                # NOP, then return an exception.
                if e is not None or \
                    rv not in [pkgdefs.EXIT_OK, pkgdefs.EXIT_NOP]:
                        e = apx.LinkedImageException(
                            lin=self.child_name, exitrv=rv,
                            pkg_op_failed=(pkg_op, rv, stdout + stderr, e))
                        rvtuple = LI_RVTuple(rv, e, None)
                        return (rvtuple, stdout, stderr)

                # check for NOP.
                if rv == pkgdefs.EXIT_NOP:
                        assert e is None
                        rvtuple = LI_RVTuple(rv, None, None)
                        return (rvtuple, stdout, stderr)

                if global_settings.client_output_parsable_version is None or \
                    not expect_plan:
                        rvtuple = LI_RVTuple(rv, None, None)
                        return (rvtuple, stdout, stderr)

                # If a plan was created and we're in parsable output mode then
                # parse the plan that should have been displayed to stdout.
                p_dict = None
                try:
                        p_dict = json.loads(stdout)
                except ValueError as e:
                        # JSON raises a subclass of ValueError when it
                        # can't parse a string.

                        e = apx.LinkedImageException(
                            lin=self.child_name,
                            unparsable_output=(pkg_op, stdout + stderr, e))
                        rvtuple = LI_RVTuple(rv, e, None)
                        return (rvtuple, stdout, stderr)

                p_dict["image-name"] = str(self.child_name)
                rvtuple = LI_RVTuple(rv, None, p_dict)
                return (rvtuple, stdout, stderr)

        def fileno(self):
                """Return the progress pipe associated with the PkgRemote
                instance that is operating on a child image."""
                return self.__pkg_remote.fileno()

        def child_init_root(self):
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

                # PROP_PARENT_PATH better not be present because
                # LinkedImageChild objects are only used with push child
                # images.
                assert PROP_PARENT_PATH not in self.__props

                # Remove any path transform and reapply.
                self.__props = rm_dict_ent(self.__props, temporal_props)
                self.__linked.set_path_transform(self.__props,
                    self.__linked.get_path_transform(),
                    path=self.__props[PROP_PATH])


# ---------------------------------------------------------------------------
# Interfaces to obtain linked image metadata from an image
#
def get_pubs(img):
        """Return publisher information for the specified image.

        Publisher information is returned in a sorted list of lists
        of the format:
                <publisher name>, <sticky>

        Where:
                <publisher name> is a string
                <sticky> is a boolean

        The tuples are sorted by publisher rank.
        """

        return [
            [str(p), p.sticky]
            for p in img.get_sorted_publishers(inc_disabled=False)
        ]

def get_packages(img, pd=None):
        """Figure out the current (or planned) list of packages in img."""

        ppkgs = set(img.get_catalog(img.IMG_CATALOG_INSTALLED).fmris())

        # if there's an image plan the we need to update the installed
        # packages based on that plan.
        if pd is not None:
                for src, dst in pd.plan_desc:
                        if src == dst:
                                continue
                        if src:
                                assert src in ppkgs
                                ppkgs -= set([src])
                        if dst:
                                assert dst not in ppkgs
                                ppkgs |= set([dst])

        # paranoia
        return frozenset(ppkgs)

def get_inheritable_facets(img, pd=None):
        """Get Facets from an image that a child should inherit.

        We only want to sync facets which affect packages that have parent
        dependencies on themselves.  In practice this essentially limits us to
        "facet.version-lock.*" facets."""

        # get installed (or planned) parent packages and facets
        ppkgs = get_packages(img, pd=pd)
        facets = img.cfg.facets
        if pd is not None and pd.new_facets is not None:
                facets = pd.new_facets

        # create a packages dictionary indexed by package stem.
        ppkgs_dict = dict([
                (pfmri.pkg_name, pfmri)
                for pfmri in ppkgs
        ])

        #
        # iterate through all installed (or planned) package incorporation
        # dependency actions and find those that are affected by image facets.
        #
        # we don't check for package-wide facets here because they don't do
        # anything.  (ie, facets defined via "set" actions in a package have
        # no effect on other actions within that package.)
        #
        faceted_deps = dict()
        cat = img.get_catalog(img.IMG_CATALOG_KNOWN)
        for pfmri in ppkgs:
                for act in cat.get_entry_actions(pfmri, [cat.DEPENDENCY]):
                        # we're only interested in incorporate dependencies
                        if act.name != "depend" or \
                            act.attrs["type"] != "incorporate":
                                continue

                        # check if any image facets affect this dependency
                        # W0212 Access to a protected member
                        # pylint: disable=W0212
                        matching_facets = facets._action_match(act)
                        # pylint: enable=W0212
                        if not matching_facets:
                                continue

                        # if all the matching facets are true we don't care
                        # about the match.
                        if set([i[1] for i in matching_facets]) == set([True]):
                                continue

                        # save this set of facets.
                        faceted_deps[act] = matching_facets

        #
        # For each faceted incorporation dependency, check if it affects a
        # package that has parent dependencies on itself.  This is really a
        # best effort in that we don't follow package renames or obsoletions,
        # etc.
        #
        # To limit the number of packages we inspect, we'll try to match the
        # incorporation dependency fmri targets packages by stem to packages
        # which are installed (or planned) within the parent image.  This
        # allows us to quickly get a fully qualified fmri and check against a
        # package for which we have already downloaded a manifest.
        #
        # If we can't match the dependency fmri package stem against packages
        # installed (or planned) in the parent image, we don't bother
        # searching for allowable packages in the catalog, because even if we
        # found them in the catalog and they did have a parent dependency,
        # they'd all still be uninstallable in any children because there
        # would be no way to satisfy the parent dependency.  (as we already
        # stated the package is not installed in the parent.)
        #
        faceted_linked_deps = dict()
        for act in faceted_deps:
                for fmri in act.attrlist("fmri"):
                        pfmri = pkg.fmri.PkgFmri(fmri)
                        pfmri = ppkgs_dict.get(pfmri.pkg_name, None)
                        if pfmri is None:
                                continue

                        # check if this package has a dependency on itself in
                        # its parent image.
                        for act2 in cat.get_entry_actions(pfmri,
                            [cat.DEPENDENCY]):
                                if act2.name != "depend" or \
                                    act2.attrs["type"] != "parent":
                                        continue
                                if pkg.actions.depend.DEPEND_SELF not in \
                                    act2.attrlist("fmri"):
                                        continue
                                faceted_linked_deps[act] = faceted_deps[act]
                                break
        del faceted_deps

        #
        # Create a set of all facets which affect incorporation dependencies
        # on synced packages.
        #
        # Note that we can't limit ourselves to only passing on facets that
        # affect dependencies which have been disabled.  Doing this could lead
        # to incorrect results because facets allow for pattern matching.  So
        # for example say we had the following dependencies on synced
        # packages:
        #
        #    depend type=incorporation fmri=some_synced_pkg1 facet.123456=true
        #    depend type=incorporation fmri=some_synced_pkg2 facet.456789=true
        #
        # and the following image facets:
        #
        #    facet.123456 = True
        #    facet.*456* = False
        #
        # if we only passed through facets which affected disabled packages
        # we'd just pass through "facet.*456*", but this would result in
        # disabling both dependencies above, not just the second dependency.
        #
        pfacets = pkg.facet.Facets()
        for facets in faceted_linked_deps.values():
                for k, v in facets:
                        # W0212 Access to a protected member
                        # pylint: disable=W0212
                        pfacets._set_inherited(k, v)

        return pfacets

# ---------------------------------------------------------------------------
# Utility Functions
#
def save_data(path, data, root="/", catch_exception=True):
        """Save JSON encoded linked image metadata to a file."""

        # make sure the directory we're about to save data into exists.
        path_dir = os.path.dirname(path)
        pathtmp = "{0}.{1:d}.tmp".format(path, os.getpid())

        try:
                if not ar.ar_exists(root, path_dir):
                        ar.ar_mkdir(root, path_dir, misc.PKG_DIR_MODE)

                # write the output to a temporary file
                fd = ar.ar_open(root, pathtmp, os.O_WRONLY,
                    mode=0o644, create=True, truncate=True)
                fobj = os.fdopen(fd, "w")
                json.dump(data, fobj, encoding="utf-8",
                    cls=pkg.client.linkedimage.PkgEncoder)
                fobj.close()

                # atomically create the desired file
                ar.ar_rename(root, pathtmp, path)
        except OSError as e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                if catch_exception:
                        raise apx._convert_error(e)
                raise e

def load_data(path, missing_ok=False, root="/", decode=True,
    catch_exception=False):
        """Load JSON encoded linked image metadata from a file."""

        object_hook = None
        if decode:
                object_hook = pkg.client.linkedimage.PkgDecoder

        try:
                if missing_ok and not path_exists(path, root=root):
                        return None

                fd = ar.ar_open(root, path, os.O_RDONLY)
                fobj = os.fdopen(fd, "r")
                data = json.load(fobj, encoding="utf-8",
                    object_hook=object_hook)
                fobj.close()
        except OSError as e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                if catch_exception:
                        raise apx._convert_error(e)
                raise apx._convert_error(e)
        return data


class PkgEncoder(json.JSONEncoder):
        """Utility class used when json encoding linked image metadata."""

        # E0202 An attribute inherited from JSONEncoder hide this method
        # pylint: disable=E0202
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
        for k, v in six.iteritems(dct):

                k = misc.force_str(k)
                v = misc.force_str(v)

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
                for k, v in six.iteritems(d)
                if k not in keys
        ])

def _rterr(li=None, lic=None, lin=None, path=None, err=None,
    bad_cp=None,
    bad_iup=None,
    bad_lin_type=None,
    bad_prop=None,
    missing_props=None,
    multiple_transforms=None,
    saved_temporal_props=None):
        """Oops.  We hit a runtime error.  Die with a nice informative
        message.  Note that runtime errors should never happen and usually
        indicate bugs (or possibly corrupted linked image metadata), so they
        are not localized (just like asserts are not localized)."""

        assert not (li and lic)
        assert not ((lin or path) and li)
        assert not ((lin or path) and lic)
        assert path == None or type(path) == str

        if bad_cp:
                assert err == None
                err = "Invalid linked content policy: {0}".format(bad_cp)
        elif bad_iup:
                assert err == None
                err = "Invalid linked image update policy: {0}".format(bad_iup)
        elif bad_lin_type:
                assert err == None
                err = "Invalid linked image type: {0}".format(bad_lin_type)
        elif bad_prop:
                assert err == None
                err = "Invalid linked property value: {0}={1}".format(*bad_prop)
        elif missing_props:
                assert err == None
                err = "Missing required linked properties: {0}".format(
                    ", ".join(missing_props))
        elif multiple_transforms:
                assert err == None
                err = "Multiple plugins reported different path transforms:"
                for plugin, transform in multiple_transforms:
                        err += "\n\t{0} = {1} -> {2}".format(plugin,
                            transform[0], transform[1])
        elif saved_temporal_props:
                assert err == None
                err = "Found saved temporal linked properties: {0}".format(
                    ", ".join(saved_temporal_props))
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
                err_prefix = "Linked image ({0}) error: ".format(str(lin))

        err_suffix = ""
        if path and lin:
                err_suffix = "\nLinked image ({0}) path: {1}".format(str(lin),
                    path)
        elif path:
                err_suffix = "\nLinked image path: {0}".format(path)

        raise RuntimeError(
            "{0}: {1}{2}".format(err_prefix, err, err_suffix))

# ---------------------------------------------------------------------------
# Functions for accessing files in the current root
#
def path_exists(path, root="/"):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_exists(root, path)
        except OSError as e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                raise apx._convert_error(e)

def path_isdir(path):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_isdir("/", path)
        except OSError as e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                raise apx._convert_error(e)

def path_mkdir(path, mode):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_mkdir("/", path, mode)
        except OSError as e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                raise apx._convert_error(e)

def path_unlink(path, noent_ok=False):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_unlink("/", path, noent_ok=noent_ok)
        except OSError as e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                raise apx._convert_error(e)

# ---------------------------------------------------------------------------
# Functions for managing images which may be in alternate roots
#

def path_transform_applicable(path, path_transform):
        """Check if 'path_transform' can be applied to 'path'."""

        # Make sure path has a leading and trailing os.sep.
        assert os.path.isabs(path), "path is not absolute: {0}".format(path)
        path = path.rstrip(os.sep) + os.sep

        # If there is no transform, then any any translation is valid.
        if path_transform == PATH_TRANSFORM_NONE:
                return True

        # check for nested or equal paths
        if path.startswith(path_transform[0]):
                return True
        return False

def path_transform_applied(path, path_transform):
        """Check if 'path_transform' has been applied to 'path'."""

        # Make sure path has a leading and trailing os.sep.
        assert os.path.isabs(path), "path is not absolute: {0}".format(path)
        path = path.rstrip(os.sep) + os.sep

        # Reverse the transform.
        path_transform = (path_transform[1], path_transform[0])
        return path_transform_applicable(path, path_transform)

def path_transform_apply(path, path_transform):
        """Apply the 'path_transform' to 'path'."""

        # Make sure path has a leading and trailing os.sep.
        assert os.path.isabs(path), "path is not absolute: {0}".format(path)
        path = path.rstrip(os.sep) + os.sep

        if path_transform == PATH_TRANSFORM_NONE:
                return path

        oroot, nroot = path_transform
        assert path_transform_applicable(path, path_transform)
        return os.path.join(nroot, path[len(oroot):])

def path_transform_revert(path, path_transform):
        """Unapply the 'path_transform' from 'path'."""

        # Reverse the transform.
        path_transform = (path_transform[1], path_transform[0])
        return path_transform_apply(path, path_transform)

def compute_path_transform(opath, npath):
        """Given an two paths create a transform that can be used to translate
        between them."""

        # Make sure all paths have a leading and trailing os.sep.
        assert os.path.isabs(opath), "opath is not absolute: {0}".format(opath)
        assert os.path.isabs(npath), "npath is not absolute: {0}".format(npath)
        opath = opath.rstrip(os.sep) + os.sep
        npath = npath.rstrip(os.sep) + os.sep

        # Remove the longest common path suffix.  Do this by reversing the
        # path strings, finding the longest common prefix, removing the common
        # prefix, and reversing the paths strings again.  Make sure there is a
        # trailing os.sep.
        i = 0
        opath_rev = opath[::-1]
        npath_rev = npath[::-1]
        for i in range(min(len(opath_rev), len(npath_rev))):
                if opath_rev[i] != npath_rev[i]:
                        break
        oroot = opath_rev[i:][::-1].rstrip(os.sep) + os.sep
        nroot = npath_rev[i:][::-1].rstrip(os.sep) + os.sep

        # Old root and new root should start and end with a '/'.
        assert oroot[0] == nroot[0] == '/'
        assert oroot[-1] == nroot[-1] == '/'

        # Return the altroot transform tuple.
        if oroot == nroot:
                return PATH_TRANSFORM_NONE
        return (oroot, nroot)
