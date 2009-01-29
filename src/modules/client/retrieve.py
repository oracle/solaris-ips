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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import socket
import httplib
import urllib2

import pkg.fmri
import pkg.client.imagestate as imagestate
import pkg.updatelog as updatelog
from pkg.misc import versioned_urlopen
from pkg.misc import TransferTimedOutException
from pkg.misc import TransferIOException
from pkg.misc import TruncatedTransferException
from pkg.misc import TransferContentException
from pkg.misc import retryable_http_errors
from pkg.misc import retryable_socket_errors
from pkg.client.api_errors import InvalidDepotResponseException

class CatalogRetrievalError(Exception):
        """Used when catalog retrieval fails"""
        def __init__(self, data, exc=None, auth=None):
                Exception.__init__(self)
                self.data = data
                self.exc = exc
                self.auth = auth

        def __str__(self):
                return str(self.data)

class VersionRetrievalError(Exception):
        """Used when catalog retrieval fails"""
        def __init__(self, data, exc=None, auth=None):
                Exception.__init__(self)
                self.data = data
                self.exc = exc
                self.auth = auth

        def __str__(self):
                return str(self.data)

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

def get_catalog(img, auth, hdr, ts):
        """Get a catalog from a remote host.  Img is the image object
        that we're updating.  Auth is the authority from which the
        catalog will be retrieved.  Additional headers are contained
        in hdr.  Ts is the timestamp if we're performing an incremental
        catalog operation."""

        prefix = auth["prefix"]
        ssl_tuple = img.get_ssl_credentials(authent=auth)

        try:
                c, v = versioned_urlopen(auth["origin"],
                    "catalog", [0], ssl_creds=ssl_tuple,
                    headers=hdr, imgtype=img.type,
                    uuid=img.get_uuid(prefix))
        except urllib2.HTTPError, e:
                # Server returns NOT_MODIFIED if catalog is up
                # to date
                if e.code == httplib.NOT_MODIFIED:
                        # success
                        return True
                elif e.code in retryable_http_errors:
                        raise TransferTimedOutException(prefix, "%d - %s" %
                            (e.code, e.msg))

                raise CatalogRetrievalError("Could not retrieve catalog from"
                    " '%s'\nHTTPError code: %d - %s" % (prefix, e.code, e.msg))
        except urllib2.URLError, e:
                if isinstance(e.args[0], socket.timeout):
                        raise TransferTimedOutException(prefix, e.reason)
                elif isinstance(e.args[0], socket.error):
                        sockerr = e.args[0]
                        if isinstance(sockerr.args, tuple) and \
                            sockerr.args[0] in retryable_socket_errors:
                                raise TransferIOException(prefix,
                                    "Retryable socket error: %s" % e.reason)

                raise CatalogRetrievalError("Could not retrieve catalog from"
                    " '%s'\nURLError, reason: %s" % (prefix, e.reason))
        except (ValueError, httplib.IncompleteRead):
                raise TransferContentException(prefix,
                    "Incomplete Read from remote host")
        except httplib.BadStatusLine:
                raise TransferContentException(prefix,
                    "Unable to read status of HTTP response")
        except KeyboardInterrupt:
                raise
        except Exception, e:
                raise CatalogRetrievalError("Could not retrieve catalog "
                    "from '%s'\nException: str:%s repr:%r" % (prefix,
                    e, e), e, prefix)

        # root for this catalog
        croot = "%s/catalog/%s" % (img.imgdir, prefix)

        try:
                updatelog.recv(c, croot, ts, auth)
        except (ValueError, httplib.IncompleteRead):
                raise TransferContentException(prefix,
                    "Incomplete Read from remote host")
        except socket.timeout, e:
                raise TransferTimedOutException(prefix)
        except socket.error, e:
                if isinstance(e.args, tuple) \
                     and e.args[0] in retryable_socket_errors:
                        raise TransferIOException(prefix,
                            "Retryable socket error: %s" % e)

                raise CatalogRetrievalError("Could not retrieve catalog"
                    " from '%s'\nsocket error, reason: %s" % (prefix, e))
        except pkg.fmri.IllegalFmri, e:
                raise CatalogRetrievalError("Could not retrieve catalog"
                    " from '%s'\nUnable to parse FMRI. Details follow:\n%s"
                    % (prefix, e))
        except EnvironmentError, e:
                raise CatalogRetrievalError("Could not retrieve catalog "
                    "from '%s'\nException: str:%s repr:%r" % (prefix,
                    e, e), e, prefix)
 
        return True

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
                raise DatastreamRetrievalError("Could not retrieve file '%s'\n"
                    "from '%s'\nHTTPError, code: %d" %
                    (fhash, url_prefix, e.code))
        except urllib2.URLError, e:
                raise DatastreamRetrievalError("Could not retrieve file '%s'\n"
                    "from '%s'\nURLError args:%s" % (fhash, url_prefix,
                    " ".join([str(a) for a in e.args])))
        except KeyboardInterrupt:
                raise
        except Exception, e:
                raise DatastreamRetrievalError("Could not retrieve file '%s'\n"
                    "from '%s'\nException: str:%s repr:%r" %
                    (fmri.get_url_path(), url_prefix, e, e))

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
                        raise TransferTimedOutException(url_prefix, "%d - %s" %
                            (e.code, e.msg))

                raise ManifestRetrievalError("Could not retrieve manifest"
                    " '%s' from '%s'\nHTTPError code: %d - %s" % 
                    (fmri.get_url_path(), url_prefix, e.code, e.msg))
        except urllib2.URLError, e:
                if isinstance(e.args[0], socket.timeout):
                        raise TransferTimedOutException(url_prefix, e.reason)
                elif isinstance(e.args[0], socket.error):
                        sockerr = e.args[0]
                        if isinstance(sockerr.args, tuple) and \
                            sockerr.args[0] in retryable_socket_errors:
                                raise TransferIOException(url_prefix,
                                    "Retryable socket error: %s" % e.reason)

                raise ManifestRetrievalError("Could not retrieve manifest"
                    " '%s' from '%s'\nURLError, reason: %s" %
                    (fmri.get_url_path(), url_prefix, e.reason))
        except (ValueError, httplib.IncompleteRead):
                raise TransferContentException(url_prefix,
                    "Incomplete Read from remote host")
        except httplib.BadStatusLine:
                raise TransferContentException(url_prefix,
                    "Unable to read status of HTTP response")
        except KeyboardInterrupt:
                raise
        except Exception, e:
                raise ManifestRetrievalError("Could not retrieve manifest"
                    " '%s' from '%s'\nException: str:%s repr:%r" %
                    (fmri.get_url_path(), url_prefix, e, e))

        cl_size = int(m.info().getheader("Content-Length", "-1"))

        try:
                mfst = m.read()
                mfst_len = len(mfst)
        except socket.timeout, e:
                raise TransferTimedOutException(url_prefix)
        except socket.error, e:
                if isinstance(e.args, tuple) \
                     and e.args[0] in retryable_socket_errors:
                        raise TransferIOException(url_prefix,
                            "Retryable socket error: %s" % e)

                raise ManifestRetrievalError("Could not retrieve"
                    " manifest from '%s'\nsocket error, reason: %s" %
                    (url_prefix, e))
        except (ValueError, httplib.IncompleteRead):
                raise TransferContentException(url_prefix,
                    "Incomplete Read from remote host")
        except EnvironmentError, e:
                raise ManifestRetrievalError("Could not retrieve manifest"
                    " '%s' from '%s'\nException: str:%s repr:%r" %
                    (fmri.get_url_path(), url_prefix, e, e))

        if cl_size > -1 and mfst_len != cl_size:
                raise TruncatedTransferException(m.geturl(), mfst_len, cl_size)

        return mfst

def touch_manifest(img, fmri):
        """Perform a HEAD operation on the manifest for the given fmri.
        """

        authority = fmri.get_authority_str()
        authority = pkg.fmri.strip_auth_pfx(authority)
        url_prefix = img.get_url_by_authority(authority)

        try:
                __get_manifest(img, fmri, "HEAD")
        except KeyboardInterrupt:
                raise
        except:
                # All other errors are ignored as this is a non-critical
                # operation that returns no information.
                pass

def get_versions(img, auth):
        """Get version information from a remote host.

        Img is the image object that the retrieve is using.
        Auth is the authority that will be queried for version information."""

        prefix = auth["prefix"]
        ssl_tuple = img.get_ssl_credentials(authent=auth)

        try:
                s, v = versioned_urlopen(auth["origin"],
                    "versions", [0], ssl_creds=ssl_tuple,
                    imgtype=img.type, uuid=img.get_uuid(prefix))
        except urllib2.HTTPError, e:
                if e.code in retryable_http_errors:
                        raise TransferTimedOutException(prefix, "%d - %s" %
                            (e.code, e.msg))

                raise VersionRetrievalError("Could not retrieve versions from"
                    " '%s'\nHTTPError code: %d - %s" % (prefix, e.code, e.msg))
        except urllib2.URLError, e:
                if isinstance(e.args[0], socket.timeout):
                        raise TransferTimedOutException(prefix, e.reason)
                elif isinstance(e.args[0], socket.error):
                        sockerr = e.args[0]
                        if isinstance(sockerr.args, tuple) and \
                            sockerr.args[0] in retryable_socket_errors:
                                raise TransferIOException(prefix,
                                    "Retryable socket error: %s" % e.reason)

                raise VersionRetrievalError("Could not retrieve versions from"
                    " '%s'\nURLError, reason: %s" % (prefix, e.reason))
        except (ValueError, httplib.IncompleteRead):
                raise TransferContentException(prefix,
                    "Incomplete Read from remote host")
        except httplib.BadStatusLine:
                raise TransferContentException(prefix,
                    "Unable to read status of HTTP response")
        except KeyboardInterrupt:
                raise
        except Exception, e:
                raise VersionRetrievalError("Could not retrieve versions "
                    "from '%s'\nException: str:%s repr:%r" % (prefix,
                    e, e), e, prefix)

        try:
                verlines = s.readlines()
        except (ValueError, httplib.IncompleteRead):
                raise TransferContentException(prefix,
                    "Incomplete Read from remote host")
        except socket.timeout, e:
                raise TransferTimedOutException(prefix)
        except socket.error, e:
                if isinstance(e.args, tuple) and \
                     e.args[0] in retryable_socket_errors:
                        raise TransferIOException(prefix,
                            "Retryable socket error: %s" % e)

                raise VersionRetrievalError("Could not retrieve versions"
                    " from '%s'\nsocket error, reason: %s" % (prefix, e))
        except EnvironmentError, e:
                raise VersionRetrievalError("Could not retrieve versions "
                    "from '%s'\nException: str:%s repr:%r" % (prefix,
                    e, e), e, prefix)

        # Convert the version lines to a method:version dictionary
        try:
                return dict(
                    s.split(None, 1)
                    for s in (l.strip() for l in verlines)
                )
        except ValueError:
                raise InvalidDepotResponseException(auth["origin"],
                    "Unable to parse server response")
