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
        def __init__(self, data, exc=None, prefix=None):
                Exception.__init__(self)
                self.data = data
                self.exc = exc
                self.prefix = prefix

        def __str__(self):
                return str(self.data)

class VersionRetrievalError(Exception):
        """Used when catalog retrieval fails"""
        def __init__(self, data, exc=None, prefix=None):
                Exception.__init__(self)
                self.data = data
                self.exc = exc
                self.prefix = prefix

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

def get_catalog(img, pub, hdr, ts):
        """Get a catalog from a remote host.  Img is the image object
        that we're updating.  pub is the publisher from which the
        catalog will be retrieved.  Additional headers are contained
        in hdr.  Ts is the timestamp if we're performing an incremental
        catalog operation."""

        prefix = pub["prefix"]
        ssl_tuple = img.get_ssl_credentials(pubent=pub)

        try:
                c, v = versioned_urlopen(pub["origin"],
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
                updatelog.recv(c, croot, ts, pub)
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
        target_pkg = None
        initial_pkg = None
        needed_by_pkg = None
        current_pub = fmri.get_publisher()

        targets = img.state.get_targets()
        if targets:
                # Attempt to determine why the client is retrieving the
                # manifest for this fmri and what its current target is.
                target, reason = targets[-1]

                # Compare the FMRIs with no publisher information embedded.
                na_current = fmri.get_fmri(anarchy=True)
                na_target = target.get_fmri(anarchy=True)

                if na_target == na_current:
                        # Only provide this information if the fmri for the
                        # manifest being retrieved matches the fmri of the
                        # target.  If they do not match, then the target fmri is
                        # being retrieved for information purposes only (e.g.
                        # dependency calculation, etc.).
                        target_pub = target.get_publisher()
                        if target_pub == current_pub:
                                # Prevent providing information across
                                # publishers.
                                target_pkg = na_target[len("pkg:/"):]
                        else:
                                target_pkg = "unknown"

                        # The very first fmri should be the initial target that
                        # caused the current and needed_by fmris to be
                        # retrieved.
                        initial = targets[0][0]
                        initial_pub = initial.get_publisher()
                        if initial_pub == current_pub:
                                # Prevent providing information across
                                # publishers.
                                initial_pkg = initial.get_fmri(
                                    anarchy=True)[len("pkg:/"):]

                                if target_pkg == initial_pkg:
                                        # Don't bother sending the target
                                        # information if it is the same
                                        # as the initial target (i.e. the
                                        # manifest for foo@1.0 is being
                                        # retrieved because the user is
                                        # installing foo@1.0).
                                        target_pkg = None

                        else:
                                # If they didn't match, indicate that
                                # the needed_by_pkg was a dependency of
                                # another, but not which one.
                                initial_pkg = "unknown"

                        if len(targets) > 1:
                                # The fmri responsible for the current one being
                                # processed should immediately precede the
                                # current one in the target list.
                                needed_by = targets[-2][0]

                                needed_by_pub = needed_by.get_publisher()
                                if needed_by_pub == current_pub:
                                        # To prevent dependency information
                                        # being shared across publisher
                                        # boundaries, publishers must match.
                                        needed_by_pkg = needed_by.get_fmri(
                                            anarchy=True)[len("pkg:/"):]
                                else:
                                        # If they didn't match, indicate that
                                        # the package is needed by another, but
                                        # not which one.
                                        needed_by_pkg = "unknown"
        else:
                # An operation is being performed that has not provided any
                # target information and is likely for informational purposes
                # only.  Assume the "initial target" is what is being retrieved.
                initial_pkg = str(fmri)[len("pkg:/"):]

        prior_version = None
        if reason != imagestate.INTENT_INFO:
                # Only provide version information for non-informational
                # operations.
                prior = img.get_version_installed(fmri)

                try:
                        prior_version = prior.version
                except AttributeError:
                        # We didn't get a match back, drive on.
                        pass
                else:
                        prior_pub = prior.get_publisher()
                        if prior_pub != current_pub:
                                # Prevent providing information across
                                # publishers by indicating that a prior
                                # version was installed, but not which one.
                                prior_version = "unknown"

        info = {
            "operation": op,
            "prior_version": prior_version,
            "reason": reason,
            "target": target_pkg,
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

        publisher = fmri.get_publisher_str()
        publisher = pkg.fmri.strip_pub_pfx(publisher)
        url_prefix = img.get_url_by_publisher(publisher)
        ssl_tuple = img.get_ssl_credentials(publisher)
        uuid = img.get_uuid(publisher)

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

        publisher = fmri.get_publisher_str()
        publisher = pkg.fmri.strip_pub_pfx(publisher)
        url_prefix = img.get_url_by_publisher(publisher)
        ssl_tuple = img.get_ssl_credentials(publisher)
        uuid = img.get_uuid(publisher)

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

        publisher = fmri.tuple()[0]
        publisher = pkg.fmri.strip_pub_pfx(publisher)
        url_prefix = img.get_url_by_publisher(publisher)

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

        publisher = fmri.get_publisher_str()
        publisher = pkg.fmri.strip_pub_pfx(publisher)

        try:
                __get_manifest(img, fmri, "HEAD")
        except KeyboardInterrupt:
                raise
        except:
                # All other errors are ignored as this is a non-critical
                # operation that returns no information.
                pass

def get_versions(img, pub):
        """Get version information from a remote host.

        Img is the image object that the retrieve is using.
        pub is the publisher that will be queried for version information."""

        prefix = pub["prefix"]
        ssl_tuple = img.get_ssl_credentials(pubent=pub)

        try:
                s, v = versioned_urlopen(pub["origin"],
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
                raise InvalidDepotResponseException(pub["origin"],
                    "Unable to parse server response")
