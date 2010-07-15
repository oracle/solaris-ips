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
# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.
#

__all__ = [ "transport" ]

import pkg.misc as misc
import pkg.client.publisher as publisher

def Transport(tcfg):
        """Returns a transport object"""

        from pkg.client.transport.transport import Transport
        return Transport(tcfg)

def ImageTransportCfg(image):
        """Returns an ImageTransportCfg object"""

        from pkg.client.transport.transport import ImageTransportCfg
        return ImageTransportCfg(image)

def GenericTransportCfg(publishers=misc.EmptyI, c_download=None,
            i_download=None, pkgdir=None, policy_map=misc.ImmutableDict()):
        """Returns GenericTransportCfg object"""

        from pkg.client.transport.transport import GenericTransportCfg
        return GenericTransportCfg(publishers=publishers,
            c_download=c_download, i_download=i_download, pkgdir=pkgdir,
            policy_map=policy_map)

# The following two methods are to be used by clients without an Image that 
# need to configure a transport and or publishers.

def setup_publisher(repo_uri, prefix, xport, xport_cfg,
    remote_prefix=False, remote_publishers=False):
        """Given transport 'xport' and publisher configuration 'xport_cfg'
        take the string that identifies a repository by uri in 'repo_uri'
        and create a publisher object.  The caller must specify the prefix.

        If remote_prefix is True, the caller will contact the remote host
        and use its publisher info to determine the publisher's actual prefix.

        If remote_publishers is True, the caller will obtain the prefix and
        repository information from the repo's publisher info."""
        

        if isinstance(repo_uri, list):
                repo = publisher.Repository(origins=repo_uri)
                repouri_list = repo_uri
        else:
                repouri_list = [publisher.RepositoryURI(repo_uri)]
                repo = publisher.Repository(origins=repouri_list)

        pub = publisher.Publisher(prefix=prefix, repositories=[repo])

        if not remote_prefix and not remote_publishers:
                xport_cfg.add_publisher(pub)
                return pub

        try:
                newpubs = xport.get_publisherdata(pub) 
        except apx.UnsupportedRepositoryOperation:
                newpubs = None

        if not newpubs:
                xport_cfg.add_publisher(pub)
                return pub

        for p in newpubs:
                psr = p.selected_repository

                if not psr:
                        p.add_repository(repo)
                elif remote_publishers:
                        if not psr.origins:
                                for r in repouri_list:
                                        psr.add_origin(r)
                        elif repo not in psr.origins:
                                for i, r in enumerate(repouri_list):
                                        psr.origins.insert(i, r)
                else:
                        psr.origins = repouri_list

                xport_cfg.add_publisher(p)

        # Return first publisher in list
        return newpubs[0]

def setup_transport():
        """Initialize the transport and transport configuration. The caller
        must manipulate the transport configuration and add publishers
        once it receives control of the objects."""

        xport_cfg = GenericTransportCfg()
        xport = Transport(xport_cfg)

        return xport, xport_cfg
