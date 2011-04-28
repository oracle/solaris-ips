<%doc>
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
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.

#
# This file is a template for the IPS system publisher Apache configuration
# file.  It is used to serve the "publisher" response from proxied file://
# repositories to pkg(5) clients that aren't using the "syspub" response
# to obtain their publisher information.
#
</%doc>
{
  "packages": [], 
  "publishers": [
    {
      "alias": null, 
      "intermediate_certs": [], 
      "name": "${pub}", 
      "packages": [], 
      "repositories": [
        {
          "collection_type": "core",
          "description": "This is an automatic response.  This publisher is generated automatically by the IPS system repository, and serves content from a file-based repository.",
          "legal_uris": [], 
          "mirrors": [], 
          "name": "IPS System Repository: ${pub}", 
          "origins": [], 
          "refresh_seconds": null, 
          "registration_uri": "", 
          "related_uris": []
        }
      ], 
      "signing_ca_certs": []
    }
  ], 
  "version": 1
}
