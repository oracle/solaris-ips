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
#

import socket
import urllib2

import pkg.fmri
import pkg.client.imagestate as imagestate
from pkg.misc import versioned_urlopen
from pkg.misc import TransferTimedOutException
from pkg.misc import retryable_http_errors

# client/retrieve.py - collected methods for retrieval of pkg components
# from repositories
def __get_intent_str(img, fmri):
        """Returns a string representing the intent of the client in retrieving
        information based on the operation information provided by the image
        history object.
        """

        op = img.history.operation_name
        if not op:
                # The client hasn't indicated what operation is executing.
                op = "unknown"

        reason = imagestate.INTENT_INFO
        initial_pkg = ""
        parent_pkg = ""
        try:
                targets = img.state.get_targets()
                # Attempt to determine why the client is retrieving the
                # manifest for this fmri and what its current target is.
                target, reason = targets[-1]

                na_current = fmri.get_fmri(anarchy=True)
                na_target = target.get_fmri(anarchy=True)
                if na_target == na_current:
                        # If the fmri for the manifest being retrieved does not
                        # match the fmri of the target, then this manifest is
                        # being retrieved for information purposes only, so don't
                        # provide this information.

                        # The fmri responsible for the current one being processed
                        # should immediately precede the current one in the target
                        # list.
                        parent = targets[-2][0]
                        parent_pkg = parent.get_fmri(anarchy=True)[len("pkg:/"):]

                        if len(targets) > 2:
                                # If there are more than two targets in the list, then
                                # the very first fmri is the one that caused the
                                # current and parent fmris to be retrieved.
                                initial = targets[0][0]
                                initial_pkg = initial.get_fmri(
                                    anarchy=True)[len("pkg:/"):]
                        else:
                                initial_pkg = parent_pkg
                                parent_pkg = ""
        except IndexError:
                # Any part of the target information may not be available.
                # Ignore it, and move on.
                pass

        version = ""
        if reason != imagestate.INTENT_INFO:
                # Only provide version information for non-informational
                # operations.
                version = "none"
                try:
                        version = "%s" % img.get_version_installed(fmri).version
                except AttributeError:
                        # We didn't get a match back, drive on.
                        pass

        info = {
            "operation": op,
            "version": version,
            "reason": reason,
            "initial_target": initial_pkg,
            "parent_target": parent_pkg,
        }

        # op/installed_version/reason/initial_target/immediate_parent/
        return "(%s)" % ";".join([
            "%s=%s" % (key, info[key]) for key in info.keys()
            if info[key] != ""
        ])

def get_datastream(img, fmri, fhash):
        """Retrieve a file handle based on a package fmri and a file hash.
        """

        authority = fmri.get_authority_str()
        authority = pkg.fmri.strip_auth_pfx(authority)
        url_prefix = img.get_url_by_authority(authority)
        ssl_tuple = img.get_ssl_credentials(authority)
        uuid = img.get_uuid(authority)

        try:
                f = versioned_urlopen(url_prefix, "file", [0], fhash,
                    ssl_creds=ssl_tuple, imgtype=img.type, uuid=uuid)[0]
        except urllib2.HTTPError, e:
                raise NameError, "could not retrieve file '%s' from '%s'" % \
                    (fhash, url_prefix)
        except urllib2.URLError, e:
                if len(e.args) == 1 and isinstance(e.args[0], socket.sslerror):
                        raise RuntimeError, e

                raise NameError, "could not retrieve file '%s' from '%s'" % \
                    (fhash, url_prefix)
        except:
                raise NameError, "could not retrieve file '%s' from '%s'" % \
                    (fhash, url_prefix)

        return f

def __get_manifest(img, fmri, method):
        """Given an image object, fmri, and http method; return a file object
        for the related manifest and send intent information.
        """

        authority = fmri.get_authority_str()
        authority = pkg.fmri.strip_auth_pfx(authority)
        url_prefix = img.get_url_by_authority(authority)
        ssl_tuple = img.get_ssl_credentials(authority)
        uuid = img.get_uuid(authority)

        # Tell the server why this resource is being requested.
        headers = {
            "X-IPkg-Intent": __get_intent_str(img, fmri)
        }

        return versioned_urlopen(url_prefix, "manifest", [0],
            fmri.get_url_path(), ssl_creds=ssl_tuple, imgtype=img.type,
            method=method, headers=headers, uuid=uuid)[0]

def get_manifest(img, fmri):
        """Retrieve the manifest for the given fmri.  Return it as a buffer to
        the caller.
        """

        authority = fmri.tuple()[0]
        authority = pkg.fmri.strip_auth_pfx(authority)
        url_prefix = img.get_url_by_authority(authority)

        try:
                m = __get_manifest(img, fmri, "GET")
        except urllib2.HTTPError, e:
                if e.code in retryable_http_errors:
                        raise TransferTimedOutException

                raise NameError, "could not retrieve manifest '%s' from '%s'" % \
                    (fmri.get_url_path(), url_prefix)
        except urllib2.URLError, e:
                if len(e.args) == 1 and isinstance(e.args[0], socket.sslerror):
                        raise RuntimeError, e
                elif len(e.args) == 1 and isinstance(e.args[0],
                    socket.timeout):
                        raise TransferTimedOutException

                raise NameError, "could not retrieve manifest '%s' from '%s'" % \
                    (fmri.get_url_path(), url_prefix)
        except:
                raise NameError, "could not retrieve manifest '%s' from '%s'" % \
                    (fmri.get_url_path(), url_prefix)

        return m.read()

def touch_manifest(img, fmri):
        """Perform a HEAD operation on the manifest for the given fmri.
        """

        authority = fmri.get_authority_str()
        authority = pkg.fmri.strip_auth_pfx(authority)
        url_prefix = img.get_url_by_authority(authority)

        try:
                __get_manifest(img, fmri, "HEAD")
        except:
                raise NameError, "could not 'touch' manifest '%s' at '%s'" % \
                    (fmri.get_url_path(), url_prefix)

