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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import xml.dom.minidom as minidom
import xml.dom as dom

# 1. Manifest interrogation functions
#
# - Inventory of services within an smf(5) manifest
# - Inventory of dependency and dependent elements within a service
#
#   Now, dependencies can be stated at either the service or the instance level.
#   We are only concerned with those dependencies stated in the manifest, and
#   not those that an installer or configuration program might add.
#
# 2. SMF management functions
#
# - Temporarily enable service instance
# - Temporarily disable service instances
#
# 3. Index handling
#    XXX Better placed in service action?
#
# - Function to turn a service dependency into a package FMRI, based on index
#
#   Need to manage an index of service to package associations.  Unclear whether
#   package to service association is also required.

def is_smf_manifest(f):
        """Return true if the given file is an smf(5) manifest."""

        # XXX Reports false positive for unenhanced smf(5) profile.

        try:
                d = minidom.parse(f)
        except (IOError, OSError), e:
                raise
        except:
                # Well formedness error from underlying parser.
                return False

        for n in d.childNodes:
                if n.nodeType == dom.Node.DOCUMENT_TYPE_NODE and \
                    n.name == "service_bundle" and \
                    n.systemId == "/usr/share/lib/xml/dtd/service_bundle.dtd.1":
                        return True

        return False

def get_info(f):
        """Return a dictionary of the relevant relationships expressed by the
        provided service description.

        The 'provides' entry of the dictionary is a list of the service
        instances defined in the service description.  The 'requires' entry is a
        list of tuples, each having the grouping attribute and the list of
        service or service instance FMRIs in that dependency group.  Finally,
        the 'imposes' entry is a list of tuples, each having the grouping
        attribute and the (always unit length) list of dependent service
        FMRIs."""

        d = minidom.parse(f)

        info = {}
        info["provides"] = []
        info["requires"] = []
        info["imposes"] = []

        for svc in d.getElementsByTagName("service"):
                sname = str(svc.getAttribute("name"))
                if svc.getElementsByTagName("create_default_instance"):
                        info["provides"].append("svc:/%s:default" % sname)
                for ins in svc.getElementsByTagName("instance"):
                        info["provides"].append("svc:/%s:%s" % (sname,
                            str(ins.getAttribute("name"))))

        for dep in d.getElementsByTagName("dependency"):
                if dep.getAttribute("type") != "service":
                        continue

                gp = str(dep.getAttribute("grouping"))
                fmris = []
                for s in dep.getElementsByTagName("service_fmri"):
                        fmris.append(str(s.getAttribute("value")))

                info["requires"].append((gp, fmris))

        for dpt in d.getElementsByTagName("dependent"):
                gp = str(dpt.getAttribute("grouping"))
                fmris = []
                for s in dpt.getElementsByTagName("service_fmri"):
                        fmris.append(str(s.getAttribute("value")))

                info["imposes"].append((gp, fmris))

        return info

