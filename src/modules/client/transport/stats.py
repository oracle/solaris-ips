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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import pkg.misc as misc

class RepoChooser(object):
        """An object that contains repo statistics.  It applies algorithms
        to choose an optimal set of repos for a given publisher, based
        upon the observed repo statistics."""

        def __init__(self):
                self.__rsobj = {}

        def __getitem__(self, key):
                return self.__rsobj[key]

        def __contains__(self, key):
                return key in self.__rsobj

        def dump(self):
                """Write the repo statistics to stdout."""

                fmt = "%-30s %-8s %-8s %-12s %-4s %-4s"
                print fmt % ("URL", "Good Tx", "Errors", "Speed", "Prio",
                    "Used")

                for ds in self.__rsobj.values():

                        speedstr = misc.bytes_to_str(ds.transfer_speed,
                            "%(num).0f %(unit)s/sec")

                        print fmt % (ds.url, ds.success, ds.failures,
                            speedstr, ds.priority, ds.used)

        def get_repostats(self, repouri_list):
                """Walk a list of repo uris and return a sorted list of
                status objects.  The better choices should be at the
                beginning of the list."""

                found_rs = []

                # Walk the list of repouris that we were provided.
                # If they're already in the dictionary, copy a reference
                # into the found_rs list, otherwise create the object
                # and then add it to our list of found objects.
                for ruri in repouri_list:
                        url = ruri.uri.rstrip("/")
                        if url in self.__rsobj:
                                found_rs.append((self.__rsobj[url], ruri))
                        else:
                                rs = RepoStats(ruri)
                                self.__rsobj[rs.url] = rs
                                found_rs.append((rs, ruri))

                # XXX This is the existing sort algorithm for mirror
                # selection.  We should switch this to a positive definite
                # quality function, where each RepoStats object is capable
                # of generating its own quality number.

                found_rs.sort(key=lambda x: (x[0].failures, x[0].success))

                # list of tuples, (repostatus, repouri)
                return found_rs


class RepoStats(object):
        """An object for keeping track of observed statistics for a particular
        RepoURI.  This includes things like observed performance, availability,
        successful and unsuccessful transaction rates, etc."""

        def __init__(self, repouri):
                """Initialize a RepoStats object.  Pass a RepositoryURI object
                in repouri to configure an object for a particular
                repository URI."""

                self.__url = repouri.uri.rstrip("/")
                self.__priority = repouri.priority

                self.__failed_tx = 0
                self.__total_tx = 0

                self.__used = False

                self.__bytes_xfr = 0.0
                self.__seconds_xfr = 0.0

        def record_error(self):
                """Record that an operation to the RepositoryURI represented
                by this RepoStats object failed with an error."""

                if not self.__used:
                        self.__used = True
                self.__failed_tx += 1

        def record_progress(self, bytes, seconds):
                """Record time and size of a network operation to a
                particular RepositoryURI, represented by the RepoStats object.
                Place the number of bytes transferred in the bytes argument.
                The time, in seconds, should be supplied in the
                seconds argument."""

                if not self.__used:
                        self.__used = True
                self.__bytes_xfr += bytes
                self.__seconds_xfr += seconds

        def record_tx(self):
                """Record that an operation to the URI represented
                by this RepoStats object was initiated."""

                if not self.__used:
                        self.__used = True
                self.__total_tx += 1

        @property
        def bytes_xfr(self):
                """Return the number of bytes transferred."""

                return self.__bytes_xfr

        @property
        def failures(self):
                """Return the number of failures that the client has encountered
                   while trying to perform operations on this repository."""

                return self.__failed_tx

        @property
        def priority(self):
                """Return the priority of the URI, if one is assigned."""

                if self.__priority is None:
                        return 0

                return self.__priority

        @property
        def seconds_xfr(self):
                """Return the total amount of time elapsed while performing
                operations against this host."""

                return self.__seconds_xfr

        @property
        def success(self):
                """Return the number of successful transaction that this client
                   has performed while communicating with this repository."""

                return self.__total_tx - self.__failed_tx

        @property
        def transfer_speed(self):
                """Return the average transfer speed in bytes/sec for
                   operations against this uri."""

                if self.__seconds_xfr == 0:
                        return 0.0

                return float(self.__bytes_xfr / self.__seconds_xfr)

        @property
        def url(self):
                """Return the URL that identifies the repository that we're
                   keeping statistics about."""

                return self.__url

        @property
        def used(self):
                """A boolean value that indicates whether the URI
                   has been used for network operations."""

                return self.__used
