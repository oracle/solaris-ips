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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import httplib
import os
import socket
import urllib2
import urlparse

# EmptyI for argument defaults; can't import from misc due to circular
# dependency.
EmptyI = tuple()

class ApiException(Exception):
        pass

class ImageNotFoundException(ApiException):
        """Used when an image was not found"""
        def __init__(self, user_specified, user_dir, root_dir):
                ApiException.__init__(self)
                self.user_specified = user_specified
                self.user_dir = user_dir
                self.root_dir = root_dir

class NetworkUnavailableException(ApiException):
        def __init__(self, caught_exception):
                ApiException.__init__(self)
                self.ex = caught_exception

        def __str__(self):
                return str(self.ex)

class VersionException(ApiException):
        def __init__(self, expected_version, received_version):
                ApiException.__init__(self)
                self.expected_version = expected_version
                self.received_version = received_version

class PlanExistsException(ApiException):
        def __init__(self, plan_type):
                ApiException.__init__(self)
                self.plan_type = plan_type

class ActuatorException(ApiException):
        def __init__(self, e):
                ApiException.__init__(self)
                self.exception = e

        def __str__(self):
                return str(self.exception)

class PrematureExecutionException(ApiException):
        pass

class AlreadyPreparedException(ApiException):
        pass

class AlreadyExecutedException(ApiException):
        pass

class ImageplanStateException(ApiException):
        def __init__(self, state):
                ApiException.__init__(self)
                self.state = state

class IpkgOutOfDateException(ApiException):
        pass

class ImageUpdateOnLiveImageException(ApiException):
        pass

class CanceledException(ApiException):
        pass

class PlanMissingException(ApiException):
        pass

class NoPackagesInstalledException(ApiException):
        pass

class PermissionsException(ApiException):
        def __init__(self, path):
                ApiException.__init__(self)
                self.path = path

        def __str__(self):
                if self.path:
                        return _("Could not operate on %s\nbecause of "
                            "insufficient permissions. Please try the command "
                            "again using pfexec\nor otherwise increase your "
                            "privileges.") % self.path
                else:
                        return _("""
Could not complete the operation because of insufficient permissions. Please
try the command again using pfexec or otherwise increase your privileges.
""")

class FileInUseException(PermissionsException):
        def __init__(self, path):
                PermissionsException.__init__(self, path)
                assert path

        def __str__(self):
                return _("Could not operate on %s\nbecause the file is "
                    "in use. Please stop using the file and try the\n"
                    "operation again.") % self.path

class PlanCreationException(ApiException):
        def __init__(self, unmatched_fmris=EmptyI, multiple_matches=EmptyI,
            missing_matches=EmptyI, illegal=EmptyI,
            constraint_violations=EmptyI, badarch=EmptyI):
                ApiException.__init__(self)
                self.unmatched_fmris       = unmatched_fmris
                self.multiple_matches      = multiple_matches
                self.missing_matches       = missing_matches
                self.illegal               = illegal
                self.constraint_violations = constraint_violations
                self.badarch               = badarch

        def __str__(self):
                res = []
                if self.unmatched_fmris:
                        s = _("""\
The following pattern(s) did not match any packages in the current catalog.
Try relaxing the pattern, refreshing and/or examining the catalogs:""")
                        res += [s]
                        res += ["\t%s" % p for p in self.unmatched_fmris]

                if self.multiple_matches:
                        s = _("'%s' matches multiple packages")
                        for p, lst in self.multiple_matches:
                                res.append(s % p)
                                for pfmri in lst:
                                        res.append("\t%s" % pfmri)

                s = _("'%s' matches no installed packages")
                res += [ s % p for p in self.missing_matches ]

                s = _("'%s' is an illegal fmri")
                res += [ s % p for p in self.illegal ]

                if self.constraint_violations:
                        s = _("The following package(s) violated constraints:")
                        res += [s]
                        res += ["\t%s" % p for p in self.constraint_violations]

                if self.badarch:
                        s = _("'%s' supports the following architectures: %s")
                        a = _("Image architecture is defined as: %s")
                        res += [ s % (self.badarch[0],
                            ", ".join(self.badarch[1]))]
                        res += [ a % (self.badarch[2])]

                return '\n'.join(res)


class ActionExecutionError(ApiException):
        """An error was encountered executing an action.

        In particular, this exception indicates that something went wrong in the
        application (or unapplication) of the action to the system, not an error
        in the pkg(5) code.

        The 'msg' argument can provide a more specific message than what would
        be returned from, and 'ignoreerrno' can be set to True to indicate that
        the sterror() text is misleading, and shouldn't be displayed.
        """

        def __init__(self, action, exception, msg=None, ignoreerrno=False):
                self.action = action
                self.exception = exception
                self.msg = msg
                self.ignoreerrno = ignoreerrno

        def __str__(self):
                errno = ""
                if not self.ignoreerrno and hasattr(self.exception, "errno"):
                        errno = "[errno %d: %s]" % (self.exception.errno,
                            os.strerror(self.exception.errno))

                msg = self.msg or ""

                # Fall back on the wrapped exception if we don't have anything
                # useful.
                if not errno and not msg:
                        return str(self.exception)

                if errno and msg:
                        return "%s: %s" % (errno, msg)

                # If we only have one of the two, no need for the colon.
                return "%s%s" % (errno, msg)


class CatalogCacheError(ApiException):
        """Base class used for all catalog cache errors."""

        def __init__(self, *args, **kwargs):
                ApiException.__init__(self, *args)
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self.args = kwargs


class CatalogCacheBadVersion(CatalogCacheError):
        """Used to indicate that the catalog cache is invalid or is not of a
        supported version."""

        def __str__(self):
                return _("Unsupported catalog cache Version: '%(found)s'; "
                    "expected: '%(expected)s'") % { "found": self.data,
                    "expected": self.args["expected"] }


class CatalogCacheInvalid(CatalogCacheError):
        """Used to indicate that the catalog cache is corrupt or otherwise
        unparseable."""

        def __str__(self):
                return _("Catalog cache is corrupt or invalid; error "
                    "encountered while reading:\nline %(lnum)d: '%(data)s'") % {
                    "lnum": self.args["line_number"], "data": self.data }


class CatalogCacheMissing(CatalogCacheError):
        """Used to indicate that the catalog cache is missing."""

        def __str__(self):
                return _("Catalog cache is missing.")


class CatalogRefreshException(ApiException):
        def __init__(self, failed, total, succeeded, message=None):
                ApiException.__init__(self)
                self.failed = failed
                self.total = total
                self.succeeded = succeeded
                self.message = message


class InventoryException(ApiException):
        def __init__(self, notfound=EmptyI, illegal=EmptyI):
                ApiException.__init__(self)
                self.notfound = notfound
                self.illegal = illegal
                assert(self.notfound or self.illegal)

        def __str__(self):
                outstr = ""
                for x in self.illegal:
                        # Illegal FMRIs have their own __str__ method
                        outstr += "%s\n" % x

                if self.notfound:
                        outstr += _("No matching package could be found for "
                            "the following FMRIs in any of the catalogs for "
                            "the current publishers:\n")

                        for x in self.notfound:
                                outstr += "%s\n" % x

                return outstr


class SearchException(ApiException):
        """Based class used for all search-related api exceptions."""
        pass


class IndexingException(SearchException):
        """ The base class for all exceptions that can occur while indexing. """

        def __init__(self, private_exception):
                SearchException.__init__(self)
                self.cause = private_exception.cause


class CorruptedIndexException(IndexingException):
        """This is used when the index is not in a correct state."""
        pass


class ProblematicPermissionsIndexException(IndexingException):
        """ This is used when the indexer is unable to create, move, or remove
        files or directories it should be able to. """
        def __str__(self):
                return "Could not remove or create " \
                    "%s because of incorrect " \
                    "permissions. Please correct this issue then " \
                    "rebuild the index." % self.cause


class MainDictParsingException(SearchException):
        """This is used when the main dictionary could not parse a line."""
        def __init__(self, e):
                SearchException.__init__(self)
                self.e = e

        def __str__(self):
                return str(self.e)


class NonLeafPackageException(ApiException):
        """Removal of a package which satisfies dependencies has been attempted.

        The first argument to the constructor is the FMRI which we tried to
        remove, and is available as the "fmri" member of the exception.  The
        second argument is the list of dependent packages that prevent the
        removal of the package, and is available as the "dependents" member.
        """

        def __init__(self, *args):
                ApiException.__init__(self, *args)

                self.fmri = args[0]
                self.dependents = args[1]

class InvalidDepotResponseException(ApiException):
        """Raised when the depot doesn't have versions of operations
        that the client needs to operate successfully."""
        def __init__(self, url, data):
                ApiException.__init__(self)
                self.url = url
                self.data = data

        def __str__(self):
                s = "Unable to contact valid package server"
                if self.url:
                        s += ": %s" % self.url
                if self.data:
                        s += "\nEncountered the following error(s):\n%s" % \
                            self.data
                return s

class DataError(ApiException):
        """Base exception class used for all data related errors."""

        def __init__(self, *args, **kwargs):
                ApiException.__init__(self, *args)
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self.args = kwargs


class InvalidP5IFile(DataError):
        """Used to indicate that the specified location does not contain a
        valid p5i-formatted file."""

        def __str__(self):
                if self.data:
                        return _("The specified file is in an unrecognized "
                            "format or does not contain valid publisher "
                            "information: %s") % self.data
                return _("The specified file is in an unrecognized format or "
                    "does not contain valid publisher information.")


class UnsupportedP5IFile(DataError):
        """Used to indicate that an attempt to read an unsupported version
        of pkg(5) info file was attempted."""

        def __str__(self):
                return _("Unsupported pkg(5) publisher information data "
                    "format.")


class TransportError(ApiException):
        """Base exception class for all transfer exceptions."""

        def __init__(self, *args, **kwargs):
                ApiException.__init__(self, *args)
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self.args = kwargs

        def __str__(self):
                return str(self.data)


class RetrievalError(TransportError):
        """Used to indicate that a a requested resource could not be
        retrieved."""

        def __str__(self):
                location = self.args.get("location", None)
                if location:
                        return _("Error encountered while retrieving data from "
                            "'%s':\n%s") % (location, self.data)
                return _("Error encountered while retrieving data from: %s") % \
                    self.data


class InvalidResourceLocation(TransportError):
        """Used to indicate that an invalid transport location was provided."""

        def __str__(self):
                return _("'%s' is not a valid location.") % self.data

class BEException(ApiException):
        def __init__(self):
                ApiException.__init__(self)

class InvalidBENameException(BEException):
        def __init__(self, be_name):
                BEException.__init__(self)
                self.be_name = be_name

        def __str__(self):
                return _("'%s' is not a valid boot environment name.") % \
                    self.be_name

class DuplicateBEName(BEException):
        """Used to indicate that there is an existing boot environment 
        with this name"""

        def __init__(self, be_name):
                BEException.__init__(self)
                self.be_name = be_name

        def __str__(self):
                return _("The boot environment '%s' already exists.") % \
                    self.be_name

class BENamingNotSupported(BEException):
        def __init__(self, be_name):
                BEException.__init__(self)
                self.be_name = be_name

        def __str__(self):
                return _("""\
Boot environment naming during package install is not supported on this
version of OpenSolaris. Please image-update without the --be-name option.""")

class UnableToCopyBE(BEException):
        def __str__(self):
                return _("Unable to clone the current boot environment.")

class UnableToRenameBE(BEException):
        def __init__(self, orig, dest):
                BEException.__init__(self)
                self.original_name = orig
                self.destination_name = dest

        def __str__(self):
                d = {
                    "orig": self.original_name,
                    "dest": self.destination_name
                }
                return _("""\
A problem occurred while attempting to rename the boot environment
currently named %(orig)s to %(dest)s.""") % d

class UnableToMountBE(BEException):
        def __init__(self, be_name, be_dir):
                BEException.__init__(self)
                self.name = be_name
                self.mountpoint = be_dir

        def __str__(self):
                return _("Unable to mount %(name)s at %(mt)s") % \
                    {"name": self.name, "mt": self.mountpoint}

class BENameGivenOnDeadBE(BEException):
        def __init__(self, be_name):
                BEException.__init__(self)
                self.name = be_name

        def __str__(self):
                return _("""\
Naming a boot environment when operating on a non-live image is
not allowed.""")


class UnrecognizedOptionsToInfo(ApiException):
        def __init__(self, opts):
                ApiException.__init__(self)
                self._opts = opts

        def __str__(self):
                s = _("Info does not recognize the following options:")
                for o in self._opts:
                        s += _(" '") + str(o) + _("'")
                return s


class ProblematicSearchServers(SearchException):
        """This class wraps exceptions which could appear while trying to
        do a search request."""

        def __init__(self, failed, invalid):
                self.failed_servers = failed
                self.invalid_servers  = invalid

        def __str__(self):
                s = _("Some servers failed to respond appropriately:\n")
                for pub, err in self.failed_servers:
                        # The messages and structure for these error
                        # messages was often lifted from retrieve.py.
                        if isinstance(err, urllib2.HTTPError):
                                s += _("    %(o)s: %(msg)s (%(code)d)\n") % \
                                    { "o": pub["origin"], "msg": err.msg,
                                    "code": err.code }
                        elif isinstance(err, urllib2.URLError):
                                if isinstance(err.args[0], socket.timeout):
                                        s += _("    %s: timeout\n") % \
                                            (pub["origin"],)
                                else:
                                        s += _("    %(o)s: %(other)s\n") % \
                                            { "o": pub["origin"],
                                            "other": err.args[0][1] }
                        elif isinstance(err, httplib.BadStatusLine):
                                s += _("    %(o)s: Unable to read status of "
                                    "HTTP response:%(l)s\n        This is "
                                    "most likely not a pkg(5) depot.  Please "
                                    "check the URL and the \n        port "
                                    "number.") % \
                                    { "o": pub["origin"], "l": err.line}
                        elif isinstance(err,
                            (httplib.IncompleteRead, ValueError)):
                                s += _("    %s: Incomplete read from "
                                       "host") % pub["origin"]
                        # RunetimeErrors arise when no supported version
                        # of the operation request is found.
                        elif isinstance(err, RuntimeError):
                                s += _("    %(o)s: %(msg)s\n") % \
                                    { "o": pub["origin"], "msg": err}
                        elif isinstance(err, socket.timeout):
                                s += _("    %s: Socket timeout") % pub["origin"]
                        elif isinstance(err, socket.error):
                                s += _("    %(o)s: Socket error, reason: "
                                    "%(msg)s") % { "o": pub["origin"],
                                    "msg": err }
                        else:
                                s += _("    %(o)s: %(msg)s") % \
                                    { "o": pub["origin"], "msg": err}
                for pub in self.invalid_servers:
                        s += _("%s appears not to be a valid package depot.\n" \
                            % pub['origin'])
                return s


class IncorrectIndexFileHash(ApiException):
        """This is used when the index hash value doesn't match the hash of the
        packages installed in the image."""
        pass


class InconsistentIndexException(IndexingException):
        """This is used when the existing index is found to have inconsistent
        versions."""
        def __init__(self, e):
                self.exception = e

        def __str__(self):
                return str(self.exception)


class SlowSearchUsed(SearchException):
        """This exception is thrown when a local search is performed without
        an index.  It's raised after all results have been yielded."""

        def __str__(self):
                return _("Search performance is degraded.\n"
                    "Run 'pkg rebuild-index' to improve search speed.")


class BooleanQueryException(ApiException):
        """This exception is used when the children of a boolean operation
        have different return types.  The command 'pkg search foo AND <bar>'
        is the simplest example of this."""

        def __init__(self, e):
                ApiException.__init__(self)
                self.e = e

        def __str__(self):
                return str(self.e)


class ParseError(ApiException):
        def __init__(self, e):
                ApiException.__init__(self)
                self.e = e

        def __str__(self):
                return str(self.e)


class PublisherError(ApiException):
        """Base exception class for all publisher exceptions."""

        def __init__(self, *args, **kwargs):
                ApiException.__init__(self, *args)
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self.args = kwargs

        def __str__(self):
                return str(self.data)


class BadPublisherMetaRoot(PublisherError):
        """Used to indicate an operation on the publisher's meta_root failed
        because the meta_root is invalid."""

        def __str__(self):
                return _("Publisher meta_root '%(root)s' is invalid; unable "
                    "to complete operation: '%(op)s'.") % { "root": self.data,
                    "op": self.args.get("operation", None) }


class BadPublisherPrefix(PublisherError):
        """Used to indicate that a publisher name is not valid."""

        def __str__(self):
                return _("'%s' is not a valid publisher name.") % self.data


class BadRepositoryAttributeValue(PublisherError):
        """Used to indicate that the specified repository attribute value is
        invalid."""

        def __str__(self):
                return _("'%(value)s' is not a valid value for repository "
                    "attribute '%(attribute)s'.") % {
                    "value": self.args["value"], "attribute": self.data }


class BadRepositoryCollectionType(PublisherError):
        """Used to indicate that the specified repository collection type is
        invalid."""

        def __init__(self, *args, **kwargs):
                PublisherError.__init__(self, *args, **kwargs)

        def __str__(self):
                return _("'%s' is not a valid repository collection type.") % \
                    self.data


class BadRepositoryURI(PublisherError):
        """Used to indicate that a repository URI is not syntactically valid."""

        def __str__(self):
                return _("'%s' is not a valid URI.") % self.data


class BadRepositoryURIPriority(PublisherError):
        """Used to indicate that the priority specified for a repository URI is
        not valid."""

        def __str__(self):
                return _("'%s' is not a valid URI priority; integer value "
                    "expected.") % self.data


class BadRepositoryURISortPolicy(PublisherError):
        """Used to indicate that the specified repository URI sort policy is
        invalid."""

        def __init__(self, *args, **kwargs):
                PublisherError.__init__(self, *args, **kwargs)

        def __str__(self):
                return _("'%s' is not a valid repository URI sort policy.") % \
                    self.data


class DisabledPublisher(PublisherError):
        """Used to indicate that an attempt to use a disabled publisher occurred
        during an operation."""

        def __str__(self):
                return _("Publisher '%s' is disabled and cannot be used for "
                    "packaging operations.") % self.data


class DuplicatePublisher(PublisherError):
        """Used to indicate that a publisher with the same name or alias already
        exists for an image."""

        def __str__(self):
                return _("A publisher with the same name or alias as '%s' "
                    "already exists.") % self.data


class DuplicateRepository(PublisherError):
        """Used to indicate that a repository with the same origin uris
        already exists for a publisher."""

        def __str__(self):
                return _("A repository with the same name or origin URIs "
                   "already exists for publisher '%s'.") % self.data


class DuplicateRepositoryMirror(PublisherError):
        """Used to indicate that a repository URI is already in use by another
        repository mirror."""

        def __str__(self):
                return _("Mirror '%s' already exists for the specified "
                    "repository.") % self.data


class DuplicateRepositoryOrigin(PublisherError):
        """Used to indicate that a repository URI is already in use by another
        repository origin."""

        def __str__(self):
                return _("Origin '%s' already exists for the specified "
                    "repository.") % self.data


class RemovePreferredPublisher(PublisherError):
        """Used to indicate an attempt to remove the preferred publisher was
        made."""

        def __str__(self):
                return _("The preferred publisher cannot be removed.")


class SelectedRepositoryRemoval(PublisherError):
        """Used to indicate that an attempt to remove the selected repository
        for a publisher was made."""

        def __str__(self):
                return _("Cannot remove the selected repository for a "
                    "publisher.")


class SetPreferredPublisherDisabled(PublisherError):
        """Used to indicate an attempt to set a disabled publisher as the
        preferred publisher was made."""

        def __str__(self):
                return _("Publisher '%s' is disabled and cannot be set as the "
                    "preferred publisher.") % self.data


class UnknownLegalURI(PublisherError):
        """Used to indicate that no matching legal URI could be found using the
        provided criteria."""

        def __str__(self):
                return _("Unknown legal URI '%s'.") % self.data


class UnknownPublisher(PublisherError):
        """Used to indicate that no matching publisher could be found using the
        provided criteria."""

        def __str__(self):
                return _("Unknown publisher '%s'.") % self.data


class UnknownRelatedURI(PublisherError):
        """Used to indicate that no matching related URI could be found using
        the provided criteria."""

        def __str__(self):
                return _("Unknown related URI '%s'.") % self.data


class UnknownRepository(PublisherError):
        """Used to indicate that no matching repository could be found using the
        provided criteria."""

        def __str__(self):
                return _("Unknown repository '%s'.") % self.data


class UnknownRepositoryMirror(PublisherError):
        """Used to indicate that a repository URI could not be found in the
        list of repository mirrors."""

        def __str__(self):
                return _("Unknown repository mirror '%s'.") % self.data


class UnknownRepositoryOrigin(PublisherError):
        """Used to indicate that a repository URI could not be found in the
        list of repository origins."""

        def __str__(self):
                return _("Unknown repository origin '%s'") % self.data


class UnsupportedRepositoryURI(PublisherError):
        """Used to indicate that the specified repository URI uses an
        unsupported scheme."""

        def __str__(self):
                if self.data:
                        scheme = urlparse.urlsplit(self.data,
                            allow_fragments=0)[0]
                        return _("The URI '%(uri)s' contains an unsupported "
                            "scheme '%(scheme)s'.") % { "uri": self.data,
                            "scheme": scheme }
                return _("The specified URI contains an unsupported scheme.")


class UnsupportedRepositoryURIAttribute(PublisherError):
        """Used to indicate that the specified repository URI attribute is not
        supported for the URI's scheme."""

        def __str__(self):
                return _("'%(attr)s' is not supported for '%(scheme)s'.") % {
                    "attr": self.data, "scheme": self.args["scheme"] }


class CertificateError(ApiException):
        """Base exception class for all certificate exceptions."""

        def __init__(self, *args, **kwargs):
                ApiException.__init__(self, *args)
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self.args = kwargs

        def __str__(self):
                return str(self.data)


class ExpiredCertificate(CertificateError):
        """Used to indicate that a certificate has expired."""

        def __str__(self):
                publisher = self.args.get("publisher", None)
                uri = self.args.get("uri", None)
                if publisher:
                        if uri:
                                return _("Certificate '%(cert)s' for publisher "
                                    "'%(pub)s' needed to access '%(uri)s', "
                                    "has expired.  Please install a valid "
                                    "certificate.") % { "cert": self.data,
                                    "pub": publisher, "uri": uri }
                        return _("Certificate '%(cert)s' for publisher "
                            "'%(pub)s', has expired.  Please install a valid "
                            "certificate.") % { "cert": self.data,
                            "pub": publisher }
                if uri:
                        return _("Certificate '%(cert)s', needed to access "
                            "'%(uri)s', has expired.  Please install a valid "
                            "certificate.") % { "cert": self.data, "uri": uri }
                return _("Certificate '%s' has expired.  Please install a "
                    "valid certificate.") % self.data


class ExpiringCertificate(CertificateError):
        """Used to indicate that a certificate has expired."""

        def __str__(self):
                publisher = self.args.get("publisher", None)
                uri = self.args.get("uri", None)
                days = self.args.get("days", 0)
                if publisher:
                        if uri:
                                return _("Certificate '%(cert)s' for publisher "
                                    "'%(pub)s', needed to access '%(uri)s', "
                                    "will expire in '%(days)s' days.") % {
                                    "cert": self.data, "pub": publisher,
                                    "uri": uri, "days": days }
                        return _("Certificate '%(cert)s' for publisher "
                            "'%(pub)s' will expire in '%(days)s' days.") % {
                            "cert": self.data, "pub": publisher, "days": days }
                if uri:
                        return _("Certificate '%(cert)s', needed to access "
                            "'%(uri)s', will expire in '%(days)s' days.") % {
                            "cert": self.data, "uri": uri, "days": days }
                return _("Certificate '%(cert)s' will expire in "
                    "'%(days)s' days.") % { "cert": self.data, "days": days }


class InvalidCertificate(CertificateError):
        """Used to indicate that a certificate is invalid."""

        def __str__(self):
                publisher = self.args.get("publisher", None)
                uri = self.args.get("uri", None)
                if publisher:
                        if uri:
                                return _("Certificate '%(cert)s' for publisher "
                                    "'%(pub)s', needed to access '%(uri)s', is "
                                    "invalid.") % { "cert": self.data,
                                    "pub": publisher, "uri": uri }
                        return _("Certificate '%(cert)s' for publisher "
                            "'%(pub)s' is invalid.") % { "cert": self.data,
                            "pub": publisher }
                if uri:
                        return _("Certificate '%(cert)s' needed to access "
                            "'%(uri)s' is invalid.") % { "cert": self.data,
                            "uri": uri }
                return _("Invalid certificate '%s'.") % self.data


class NoSuchCertificate(CertificateError):
        """Used to indicate that a certificate could not be found."""

        def __str__(self):
                publisher = self.args.get("publisher", None)
                uri = self.args.get("uri", None)
                if publisher:
                        if uri:
                                return _("Unable to locate certificate "
                                    "'%(cert)s' for publisher '%(pub)s' needed "
                                    "to access '%(uri)s'.") % {
                                    "cert": self.data, "pub": publisher,
                                    "uri": uri }
                        return _("Unable to locate certificate '%(cert)s' for "
                            "publisher '%(pub)s'.") % { "cert": self.data,
                            "pub": publisher }
                if uri:
                        return _("Unable to locate certificate '%(cert)s' "
                            "needed to access '%(uri)s'.") % {
                            "cert": self.data, "uri": uri }
                return _("Unable to locate certificate '%s'.") % self.data


class NotYetValidCertificate(CertificateError):
        """Used to indicate that a certificate is not yet valid (future
        effective date)."""

        def __str__(self):
                publisher = self.args.get("publisher", None)
                uri = self.args.get("uri", None)
                if publisher:
                        if uri:
                                return _("Certificate '%(cert)s' for publisher "
                                    "'%(pub)s', needed to access '%(uri)s', "
                                    "has a future effective date.") % {
                                    "cert": self.data, "pub": publisher,
                                    "uri": uri }
                        return _("Certificate '%(cert)s' for publisher "
                            "'%(pub)s' has a future effective date.") % {
                            "cert": self.data, "pub": publisher }
                if uri:
                        return _("Certificate '%(cert)s' needed to access "
                            "'%(uri)s' has a future effective date.") % {
                            "cert": self.data, "uri": uri }
                return _("Certificate '%s' has a future effective date.") % \
                    self.data


class ServerReturnError(ApiException):
        """This exception is used when the server reutrns a line which the
        client cannot parse correctly."""

        def __init__(self, line):
                ApiException.__init__(self)
                self.line = line

        def __str__(self):
                return _("Gave a bad response:%s") % self.line
