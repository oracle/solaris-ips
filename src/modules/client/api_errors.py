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

from pkg.misc import EmptyI

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

class InvalidCertException(ApiException):
        pass

class PlanExistsException(ApiException):
        def __init__(self, plan_type):
                ApiException.__init__(self)
                self.plan_type = plan_type

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

class UnrecognizedAuthorityException(ApiException):
        def __init__(self, auth):
                ApiException.__init__(self)
                self.auth = auth

class NoPackagesInstalledException(ApiException):
        pass

class PermissionsException(ApiException):
        def __init__(self, path):
                ApiException.__init__(self)
                self.path = path

        def __str__(self):
                if self.path:
                        return _("Could not operate on %s\nbecause of insufficient "
                                "permissions. Please try the command again using pfexec\n"
                                "or otherwise increase your permissions.") % self.path
                else:
                        return _("""
Could not complete the operation because of insufficient permissions. Please
try the command again using pfexec or otherwise increase your permissions.
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
        def __init__(self, unfound_fmris=EmptyI, multiple_matches=EmptyI,
            missing_matches=EmptyI, illegal=EmptyI, constraint_violations=EmptyI, 
            badarch=EmptyI):
                ApiException.__init__(self)
                self.unfound_fmris         = unfound_fmris
                self.multiple_matches      = multiple_matches
                self.missing_matches       = missing_matches
                self.illegal               = illegal
                self.constraint_violations = constraint_violations
                self.badarch               = badarch

        def __str__(self):
                res = []
                if self.unfound_fmris:
                        s = _("""\
pkg: The following pattern(s) did not match any packages in the current
catalog. Try relaxing the pattern, refreshing and/or examining the catalogs""")
                        res += [ s ]
                        res += [ "\t%s" % p for p in self.unfound_fmris ]

                if self.multiple_matches:
                        s = _("pkg: '%s' matches multiple packages")
                        for p, lst in self.multiple_matches:
                                res.append( s % p)
                                for pfmri, state in lst:
                                        res.append("\t%s" % pfmri)

                s = _("pkg: '%s' matches no installed packages")
                res += [ s % p for p in self.missing_matches ]

                s = _("pkg: '%s' is an illegal fmri")
                res += [ s % p for p in self.illegal ]

                if self.constraint_violations:
                        s = _("pkg: the following package(s) violated constraints:")
                        res += [ s ] 
                        res += [ "\t%s" % p for p in self.constraint_violations ]

                if self.badarch:
                        s = _("'%s' supports the following architectures: %s")
                        a = _("Image architecture is defined as: %s")
                        res += [ s % (self.badarch[0], 
                            ", ".join(self.badarch[1]))]
                        res += [ a % (self.badarch[2])]

                return '\n'.join(res)

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
                            "the current authorities:\n")

                        for x in self.notfound:
                                outstr += "%s\n" % x

                return outstr

class IndexingException(ApiException):
        """ The base class for all exceptions that can occur while indexing. """
        def __init__(self, private_exception):
                ApiException.__init__(self)
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
