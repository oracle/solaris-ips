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

class ManifestRetrievalError(Exception):
        """Used when manifest retrieval fails"""
        def __init__(self, data):
                Exception.__init__(self)
                self.data = data

        def __str__(self):
                return str(self.data)

class DatastreamRetrievalError(Exception):
        """Used when datastream retrieval fails"""
        def __init__(self, data):
                Exception.__init__(self)
                self.data = data

        def __str__(self):
                return str(self.data)

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
        initial_pkg = None
        needed_by_pkg = None
        current_auth = fmri.get_authority()
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
                        needed_by = targets[-2][0]

                        needed_by_auth = needed_by.get_authority()
                        if needed_by_auth == current_auth:
                                # To prevent dependency information being shared
                                # across authority boundaries, authorities must
                                # match.
                                needed_by_pkg = needed_by.get_fmri(
                                    anarchy=True)[len("pkg:/"):]
                        else:
                                # If they didn't match, indicate that the
                                # package is needed by another, but not which
                                # one.
                                needed_by_pkg = "unknown"

                        if len(targets) > 2:
                                # If there are more than two targets in the
                                # list, then the very first fmri is the one
                                # that caused the current and needed_by fmris
                                # to be retrieved.
                                initial = targets[0][0]
                                initial_auth = initial.get_authority()
                                if initial_auth == current_auth:
                                        # Prevent providing information across
                                        # authorities.
                                        initial_pkg = initial.get_fmri(
                                            anarchy=True)[len("pkg:/"):]
                                else:
                                        # If they didn't match, indicate that
                                        # the needed_by_pkg was a dependency of
                                        # another, but not which one.
                                        initial_pkg = "unknown"
                        else:
                                # If there are only two targets in the stack,
                                # then the first target is both the initial
                                # target and is the cause of the current fmri
                                # being retrieved.
                                initial_pkg = needed_by_pkg
        except IndexError:
                # Any part of the target information may not be available.
                # Ignore it, and move on.
                pass

        prior_version = None
        if reason != imagestate.INTENT_INFO:
                # Only provide version information for non-informational
                # operations.
                try:
                        prior = "%s" % img.get_version_installed(fmri)
                        prior_version = prior.version
                        prior_auth = prior.get_authority()
                        if prior_auth != current_auth:
                                # Prevent providing information across
                                # authorities by indicating that a prior
                                # version was installed, but not which one.
                                prior_version = "unknown"
                except AttributeError:
                        # We didn't get a match back, drive on.
                        pass

        info = {
            "operation": op,
            "prior_version": prior_version,
            "reason": reason,
            "initial_target": initial_pkg,
            "needed_by": needed_by_pkg,
        }

        # op/prior_version/reason/initial_target/needed_by/
        return "(%s)" % ";".join([
            "%s=%s" % (key, info[key]) for key in info
            if info[key] is not None
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
                raise DatastreamRetrievalError("could not retrieve file '%s'"
                    "from '%s'\nHTTPError, code:%s"% (hash, url_prefix, e.code))
        except urllib2.URLError, e:
                if len(e.args) == 1 and isinstance(e.args[0], socket.sslerror):
                        raise RuntimeError, e

                raise DatastreamRetrievalError("could not retrieve file '%s'"
                    "from '%s'\nURLError args:%s" % (hash, url_prefix,
                    " ".join([str(a) for a in e.args])))
        except KeyboardInterrupt:
                raise
        except Exception, e:
                raise DatastreamRetrievalError("could not retrieve manifest '%s'"
                    "from '%s'\nException: str:%s repr:%s" % (fmri.get_url_path(),
                    url_prefix, e, repr(e)))

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

                raise ManifestRetrievalError("could not retrieve manifest '%s' from '%s'\n"
                    "HTTPError code:%s" % (fmri.get_url_path(), url_prefix, 
                    e.code))
        except urllib2.URLError, e:
                if len(e.args) == 1 and isinstance(e.args[0], socket.sslerror):
                        raise RuntimeError, e
                elif len(e.args) == 1 and isinstance(e.args[0], socket.timeout):
                        raise TransferTimedOutException

                raise ManifestRetrievalError("could not retrieve manifest '%s' from '%s'\n"
                    "URLError, args:%s" % (fmri.get_url_path(), url_prefix,
                    " ".join([str(a) for a in e.args])))
        except KeyboardInterrupt:
                raise
        except Exception, e:
                raise ManifestRetrievalError("could not retrieve manifest '%s' from '%s'"
                    "Exception: str:%s repr:%s" % (fmri.get_url_path(),
                    url_prefix, e, repr(e)))

        return m.read()

def touch_manifest(img, fmri):
        """Perform a HEAD operation on the manifest for the given fmri.
        """

        authority = fmri.get_authority_str()
        authority = pkg.fmri.strip_auth_pfx(authority)
        url_prefix = img.get_url_by_authority(authority)

        try:
                __get_manifest(img, fmri, "HEAD")
        except urllib2.HTTPError, e:
                if e.code in retryable_http_errors:
                        raise TransferTimedOutException

                raise ManifestRetrievalError("could not 'touch' manifest '%s' from '%s'\n"
                    "HTTPError code:%s" % (fmri.get_url_path(), url_prefix, 
                    e.code))
        except urllib2.URLError, e:
                if len(e.args) == 1 and isinstance(e.args[0], socket.sslerror):
                        raise RuntimeError, e
                elif len(e.args) == 1 and isinstance(e.args[0], socket.timeout):
                        raise TransferTimedOutException

                raise ManifestRetrievalError("could not 'touch' manifest '%s' from '%s'\n"
                    "URLError, args:%s" % (fmri.get_url_path(), url_prefix,
                    " ".join([str(a) for a in e.args])))
        except KeyboardInterrupt:
                raise
        except Exception, e:
                raise ManifestRetrievalError("could not 'touch' manifest '%s' from '%s'"
                    "Exception: str:%s repr:%s" % (fmri.get_url_path(),
                    url_prefix, e, repr(e)))
