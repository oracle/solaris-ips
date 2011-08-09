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

import os.path
import xml.dom.minidom as minidom
import xml.parsers
import xml.parsers.expat

import pkg.flavor.base as base
from pkg.portable import PD_LOCAL_PATH, PD_PROTO_DIR, PD_PROTO_DIR_LIST

# A list of locations beneath a given proto_dir where we expect to
# find SMF manifest files
manifest_locations = [ "lib/svc/manifest", "var/svc/manifest" ]

class SMFManifestDependency(base.PublishingDependency):

        # maps SMF fmris to the manifest files that defined them
        instance_mf = None

        # maps SMF FMRIs to a list the SMF FMRIs they declare as dependencies
        instance_deps = None

        manifest = None

        def __init__(self, action, path, pkg_vars, proto_dir):
                """ See __init__ for PublishingDependency.
                """
                self.manifest = path
                base_names = [os.path.basename(path)]
                paths = [os.path.dirname(path)]
                base.PublishingDependency.__init__(self, action,
                    base_names, paths, pkg_vars, proto_dir, "smf_manifest")

        def __repr__(self):
                return "SMFDep(%s, %s, %s, %s)" % (self.action,
                    self.base_names[0], self.run_paths, self.pkg_vars)

        @staticmethod
        def _clear_cache():
                """Clear our manifest caches.  This is primarily provided for
                test code."""
                SMFManifestDependency.instance_mf = None
                SMFManifestDependency.instance_deps = None

        @staticmethod
        def populate_cache(proto_dirs, force_update=False):
                """Build our instance_mf and instance_deps dictionaries
                from the known SMF manifests installed on the current system
                and those that appear in the proto_dirs.
                """

                if not force_update:
                        if SMFManifestDependency.instance_mf != None:
                                return

                SMFManifestDependency.instance_mf = {}
                SMFManifestDependency.instance_deps = {}

                def find(manifests, dirname, fnames):
                         for file in fnames:
                                 path = os.path.join(dirname, file)
                                 if os.path.isfile(path):
                                        manifests.append(path)

                manifest_paths = []

                # we want our proto_dirs to be the authoritative source
                # for SMF manifests, so scan the local system first, then
                # iterate through the proto_dirs, starting from the
                # oldest, overwriting with progressively newer proto_dirs
                for location in manifest_locations:
                        manifest_paths.append(os.path.join("/", location))
                for proto_dir in reversed(proto_dirs):
                        for location in manifest_locations:
                                manifest_paths.append(os.path.join(proto_dir,
                                    location))

                for location in manifest_paths:
                        manifests = []
                        os.path.walk(location, find, manifests)
                        for manifest_file in manifests:
                                SMFManifestDependency.__populate_smf_dics(
                                    manifest_file)
        @staticmethod
        def __populate_smf_dics(manifest_file):
                """Add a information information about the SMF instances and
                their dependencies from the given manifest_file to a global
                set of dictionaries."""

                instance_mf, instance_deps = parse_smf_manifest(
                    manifest_file)

                # more work is needed here when
                # multiple-manifests per service is supported by
                # SMF: we'll need to merge additional
                # service-level dependencies into each service
                # instance as each manifest gets added.
                if instance_mf:
                        SMFManifestDependency.instance_mf.update(
                            instance_mf)
                if instance_deps:
                        SMFManifestDependency.instance_deps.update(
                            instance_deps)

def split_smf_fmri(fmri):
        """Split an SMF FMRI into constituent parts, returning the svc protocol,
        the service name, and the instance name, if any."""

        protocol = None
        service = None
        instance = None

        arr = fmri.split(":")
        if len(arr) == 2 and arr[0] == "svc":
                protocol = "svc"
                service = arr[1]
        elif len(arr) == 3 and arr[0] == "svc":
                protocol = "svc"
                service = arr[1]
                instance = arr[2]
        else:
                raise ValueError(_("FMRI does not appear to be valid"))
        return protocol, service, instance

def search_smf_dic(fmri, dictionary):
        """Search a dictionary of SMF FMRI mappings, returning a list of
        results. If the FMRI points to an instance, we can return quickly. If
        the FMRI points to a service, we return all matching instances.  Note
        if the dictionary contains service FMRIs, those won't appear in the
        results - we only ever return instances."""

        protocol, service, instance = split_smf_fmri(fmri)
        results = []
        if instance is not None:
                if fmri in dictionary:
                        results.append(dictionary[fmri])
        else:
                # return all matching instances of this service
                for item in dictionary:
                        if item.startswith(protocol + ":" + service + ":"):
                                results.append(dictionary[item])
        return results

def get_smf_dependencies(fmri, instance_deps):
        """Given an instance FMRI, determine the FMRIs it depends on.  If we
        match more than one fmri, we raise an exception. """

        results = search_smf_dic(fmri, instance_deps)
        if len(results) == 1:
                return results[0]
        elif len(results) > 1:
                # this can only happen if we've been asked to resolve a
                # service-level FMRI, not a fully qualified instance FMRI
                raise ValueError(
                    _("more than one set of dependencies found: %s") % results)

        results = search_smf_dic(fmri, SMFManifestDependency.instance_deps)
        if len(results) == 1:
                return results[0]
        elif len(results) > 1:
                raise ValueError(
                    _("more than one set of dependencies found: %s") % results)

        return []

def resolve_smf_dependency(fmri, instance_mf):
        """Given an SMF FMRI that satisfies a given SMF dependency, determine
        which file(s) deliver that dependency using both the provided
        instance_mf dictionary and the global SmfManifestDependency dictionary.
        If multiple files match, we have a problem."""

        manifests = set()

        manifests.update(search_smf_dic(fmri, instance_mf))

        manifests.update(search_smf_dic(
            fmri, SMFManifestDependency.instance_mf))

        if len(manifests) == 0:
                # we can't satisfy the dependency at all
                raise ValueError(_("cannot resolve FMRI to a delivered file"))

        elif len(manifests) > 1:
                # instances satisfying the dependency are delivered by
                # multiple files - we can't deal with this either
                raise ValueError(
                    _("FMRI is delivered by multiple files: %s") % manifests)

        # we should only ever have one element in our set at this point,
        # so doing a pop() is safe.
        return manifests.pop()

def process_smf_manifest_deps(action, pkg_vars, **kwargs):
        """Given an action and a place to find the file it references, if the
        file is an SMF manifest, we return a list of SmfManifestDependencies
        pointing to the SMF manifests in the proto area that would satisfy each
        dependency, a list of errors, and a dictionary containing the SMF FMRIs
        that were contained in the SMF manifest that this action delivers.

        Note that while we resolve SMF dependencies from SMF FMRIs to the files
        that deliver them, we don't attempt to further resolve those files to
        pkg(5) packages at this point.
        That stage is done using the normal "pkgdepend resolve" mechanism."""

        if action.name != "file":
                return [], \
                    [ _("%s actions cannot deliver SMF manifests") %
                    action.name ], {}

        # we don't report an error here, as SMF manifest files may be delivered
        # to a location specifically not intended to be imported to the SMF
        # repository.
        if not has_smf_manifest_dir(action.attrs["path"]):
                return [], [], {}

        proto_file = action.attrs[PD_LOCAL_PATH]
        SMFManifestDependency.populate_cache(action.attrs[PD_PROTO_DIR_LIST])

        deps = []
        elist = []
        dep_manifests = set()

        instance_mf, instance_deps = parse_smf_manifest(proto_file)
        if instance_mf is None:
                return [], [ _("Unable to parse SMF manifest %s") %
                    proto_file ], {}

        for fmri in instance_mf:
                try:
                        protocol, service, instance = split_smf_fmri(fmri)
                        # we're only interested in trying to resolve
                        # dependencies that instances have declared
                        if instance is None:
                                continue

                except ValueError, err:
                        elist.append(_("Problem resolving %(fmri)s: %(err)s") %
                            locals())
                        continue

                # determine the set of SMF FMRIs we depend on
                dep_fmris = set()
                try:
                        dep_fmris = set(
                            get_smf_dependencies(fmri, instance_deps))
                except ValueError, err:
                        elist.append(
                            _("Problem determining dependencies for %(fmri)s:"
                            "%(err)s") % locals())

                # determine the file paths that deliver those dependencies
                for dep_fmri in dep_fmris:
                        manifest = None
                        try:
                                manifest = resolve_smf_dependency(dep_fmri,
                                    instance_mf)
                        except ValueError, err:
                                # we've declared an SMF dependency, but can't
                                # determine what file delivers it from the known
                                # SMF manifests in either the proto area or the
                                # local machine.
                                elist.append(
                                    _("Unable to generate SMF dependency on "
                                    "%(dep_fmri)s declared in %(proto_file)s by "
                                    "%(fmri)s: %(err)s") % locals())

                        if manifest:
                                dep_manifests.add(manifest)

        for manifest in dep_manifests:
                deps.append(SMFManifestDependency(action, manifest, pkg_vars,
                    action.attrs[PD_PROTO_DIR]))
        pkg_attrs = {
            "org.opensolaris.smf.fmri": instance_mf.keys()
        }
        return deps, elist, pkg_attrs

def __get_smf_dependencies(deps):
        """Given a minidom Element deps, search for the <service_fmri> elements
        inside it, and return the values as a list of strings."""

        dependencies = []
        for dependency in deps:
                fmris = dependency.getElementsByTagName("service_fmri")
                dep_type = dependency.getAttribute("type")
                grouping = dependency.getAttribute("grouping")
                delete = dependency.getAttribute("delete")

                # we don't include SMF path dependencies as these are often
                # not packaged files.
                if fmris and dep_type == "service" and \
                    grouping == "require_all" and \
                    delete != "true":
                        for service_fmri in fmris:
                                dependency = service_fmri.getAttribute("value")
                                if dependency:
                                        dependencies.append(dependency)
        return dependencies

def is_smf_manifest(smf_file):
        """Quickly determine if smf_file is a valid SMF manifest."""
        try:
                smf_doc = minidom.parse(smf_file)
        # catching ValueError, as minidom has been seen to raise this on some
        # invalid XML files.
        except (xml.parsers.expat.ExpatError, ValueError):
                return False

        if not smf_doc.doctype:
                return False

        if smf_doc.doctype.systemId != \
            "/usr/share/lib/xml/dtd/service_bundle.dtd.1":
                return False
        return True

def parse_smf_manifest(smf_file):
        """Returns a tuple of two dictionaries. The first maps the SMF FMRIs
        found in that manifest to the path of the manifest file. The second maps
        each SMF FMRI found in the file to the list of FMRIs that are declared
        as dependencies.

        Note this method makes no distinction between service FMRIs and instance
        FMRIs; both get added to the dictionaries, but only the instance FMRIs
        should be used to determine dependencies.

        Calling this with a path to the file, we include manifest_paths in the
        first dictionary, otherwise with raw file data, we don't.

        If we weren't handed an SMF XML file, or have trouble parsing it, we
        return a tuple of None, None.
        """

        instance_mf = {}
        instance_deps = {}

        try:
                smf_doc = minidom.parse(smf_file)
        # catching ValueError, as minidom has been seen to raise this on some
        # invalid XML files.
        except (xml.parsers.expat.ExpatError, ValueError):
                return None, None

        if not smf_doc.doctype:
                return None, None

        if smf_doc.doctype.systemId != \
            "/usr/share/lib/xml/dtd/service_bundle.dtd.1":
                return None, None

        manifest_path = None

        if isinstance(smf_file, str):
                manifest_path = smf_file

        svcs = smf_doc.getElementsByTagName("service")
        for service in svcs:

                fmris = []
                svc_dependencies = []
                create_default = False
                duplicate_default = False

                # get the service name
                svc_name = service.getAttribute("name")
                if svc_name and not svc_name.startswith("/"):
                        svc_name = "/" + svc_name
                        fmris.append("svc:%s" % svc_name)
                else:
                        # no defined service name, so no dependencies here
                        continue

                # Get the FMRIs we declare dependencies on. When splitting SMF
                # services across multiple manifests is supported, more work
                # will be needed here.
                svc_deps = []
                for child in service.childNodes:
                        if isinstance(child, minidom.Element) and \
                            child.tagName == "dependency":
                                svc_deps.append(child)

                svc_dependencies.extend(__get_smf_dependencies(svc_deps))

                # determine our instances
                if service.getElementsByTagName("create_default_instance"):
                        create_default = True

                insts = service.getElementsByTagName("instance")
                for instance in insts:
                        inst_dependencies = []
                        inst_name = instance.getAttribute("name")
                        fmri = None
                        if inst_name:
                                if inst_name == "default" and create_default:
                                        # we've declared a
                                        # create_default_instance tag but we've
                                        # also explicitly created an instance
                                        # called "default"
                                        duplicate_default = True

                                fmri = "svc:%s:%s" % (svc_name, inst_name)

                                # we can use getElementsByTagName here, since
                                # there are no nested <dependency> tags that
                                # won't apply, unlike for <service> above, when
                                # we needed to look strictly at immediate
                                # children.
                                inst_deps = instance.getElementsByTagName(
                                    "dependency")
                                inst_dependencies.extend(
                                    __get_smf_dependencies(inst_deps))

                        if fmri is not None:
                                instance_deps[fmri] = svc_dependencies + \
                                    inst_dependencies
                                fmris.append(fmri)

                if create_default and not duplicate_default:
                        fmri = "svc:%s:default" % svc_name
                        fmris.append(fmri)
                        instance_deps[fmri] = svc_dependencies

                # add the service FMRI
                instance_deps["svc:%s" % svc_name] = svc_dependencies
                for fmri in fmris:
                        instance_mf[fmri] = manifest_path

        return instance_mf, instance_deps

def has_smf_manifest_dir(path, prefix=None):
        """Determine if the given path string contains any of the directories
        where SMF manifests are usually delivered.  An optional named parameter
        prefix gets stripped from the path before checking.
        """
        global manifest_locations
        check_path = path
        if prefix:
                check_path = path.replace(prefix, "", 1)
        for location in manifest_locations:
                if check_path and check_path.startswith(location):
                        return True
        return False
