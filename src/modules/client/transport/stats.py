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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import division

import os
import datetime
import random
from six.moves.urllib.parse import urlsplit
import pkg.misc as misc


class RepoChooser(object):
        """An object that contains repo statistics.  It applies algorithms
        to choose an optimal set of repos for a given publisher, based
        upon the observed repo statistics.

        The RepoChooser object is a container for RepoStats objects.
        It's used to return the RepoStats in an ordered list, which
        helps the transport pick the best performing destination."""

        def __init__(self):
                # A dictionary containing the RepoStats objects. The dictionary
                # uses TransportRepoURI.key() values as its key.
                self.__rsobj = {}

        def __getitem__(self, key):
                return self.__rsobj[key]

        def __contains__(self, key):
                return key in self.__rsobj

        def __get_proxy(self, ds):
                """Gets the proxy that was used at runtime for a given
                RepoStats object.  This may differ from the persistent
                configuration of any given TransportRepoURI.  We do not use the
                ds.runtime_proxy value, since that may include cleartext
                passwords."""

                # we don't allow the proxy used for the system publisher to be
                # overridden
                if ds.system:
                        if not ds.proxy:
                                return "-"
                        return ds.proxy

                proxy = misc.get_runtime_proxy(ds.proxy, ds.url)
                if not proxy:
                        return "-"
                return proxy

        def dump(self):
                """Write the repo statistics to stdout."""

                hfmt = "{0:41.41} {1:30} {2:6} {3:4} {4:4} {5:8} {6:10} {7:5} {8:7} {9:4}"
                dfmt = "{0:41.41} {1:30} {2:6} {3:4} {4:4} {5:8} {6:10} {7:5} {8:6f} {9:4}"
                misc.msg(hfmt.format("URL", "Proxy", "Good", "Err", "Conn",
                    "Speed", "Size", "Used", "CSpeed", "Qual"))

                for ds in self.__rsobj.values():

                        speedstr = misc.bytes_to_str(ds.transfer_speed,
                            "{num:>.0f} {unit}/s")

                        sizestr = misc.bytes_to_str(ds.bytes_xfr)
                        proxy = self.__get_proxy(ds)
                        misc.msg(dfmt.format(ds.url, proxy, ds.success,
                            ds.failures, ds.num_connect, speedstr, sizestr,
                            ds.used, ds.connect_time, ds.quality))

        def get_num_visited(self, repouri_list):
                """Walk a list of TransportRepoURIs and return the number
                that have been visited as an integer.  If a repository
                is in the list, but we don't know about it yet, create a
                stats object to keep track of it, and include it in
                the visited count."""

                found_rs = []

                for ruri in repouri_list:
                        key = ruri.key()
                        if key in self.__rsobj:
                                rs = self.__rsobj[key]
                        else:
                                rs = RepoStats(ruri)
                                self.__rsobj[key] = rs
                        found_rs.append((rs, ruri))

                return len([x for x in found_rs if x[0].used])

        def get_repostats(self, repouri_list, origin_list=misc.EmptyI):
                """Walk a list of TransportRepoURIs and return a sorted list of
                status objects.  The better choices should be at the
                beginning of the list."""

                found_rs = []
                origin_speed = 0
                origin_count = 0
                origin_avg_speed = 0
                origin_cspeed = 0
                origin_ccount = 0
                origin_avg_cspeed = 0

                for ouri in origin_list:
                        key = ouri.key()
                        if key in self.__rsobj:
                                rs = self.__rsobj[key]
                                if rs.bytes_xfr > 0:
                                        # Exclude sources that don't
                                        # contribute to transfer speed.
                                        origin_speed += rs.transfer_speed
                                        origin_count += 1
                                if rs.connect_time > 0:
                                        # Exclude sources that don't
                                        # contribute to connection
                                        # time.
                                        origin_cspeed += rs.connect_time
                                        origin_ccount += 1
                        else:
                                rs = RepoStats(ouri)
                                self.__rsobj[key] = rs

                if origin_count > 0:
                        origin_avg_speed = origin_speed // origin_count
                if origin_ccount > 0:
                        origin_avg_cspeed = origin_cspeed // origin_ccount

                # Walk the list of repouris that we were provided.
                # If they're already in the dictionary, copy a reference
                # into the found_rs list, otherwise create the object
                # and then add it to our list of found objects.
                num_origins = len(origin_list)
                num_mirrors = len(repouri_list) - len(origin_list)
                o_idx = 0
                m_idx = 0
                for ruri in repouri_list:
                        key = ruri.key()
                        if key in self.__rsobj:
                                rs = self.__rsobj[key]
                        else:
                                rs = RepoStats(ruri)
                                self.__rsobj[key] = rs
                        found_rs.append((rs, ruri))
                        if ruri in origin_list:
                                n = num_origins - o_idx
                                # old-division; pylint: disable=W1619
                                rs.origin_factor = n / num_origins
                                o_idx += 1
                        else:
                                n = num_mirrors - m_idx
                                # old-division; pylint: disable=W1619
                                rs.origin_factor = n / num_mirrors
                                m_idx += 1
                        if origin_count > 0:
                                rs.origin_speed = origin_avg_speed
                                rs.origin_count = origin_count
                        if origin_ccount > 0:
                                rs.origin_cspeed = origin_avg_cspeed

                        # Decay error rate for transient errors.
                        # Reduce the error penalty by .1% each iteration.
                        # In other words, keep 99.9% of the current value.
                        rs._err_decay *= 0.999
                        # Decay origin bonus each iteration to gradually give
                        # up slow and erroneous origins.
                        rs.origin_decay *= 0.95

                found_rs.sort(key=lambda x: x[0].quality, reverse=True)

                # list of tuples, (repostatus, repouri)
                return found_rs

        def clear(self):
                """Clear all statistics count."""

                self.__rsobj = {}

        def reset(self):
                """reset each stats object"""

                for v in self.__rsobj.values():
                        v.reset()


class RepoStats(object):
        """An object for keeping track of observed statistics for a particular
        TransportRepoURI.  This includes things like observed performance,
        availability, successful and unsuccessful transaction rates, etc.

        There's one RepoStats object per transport destination.
        This allows the transport to keep statistics about each
        host that it visits."""

        def __init__(self, repouri):
                """Initialize a RepoStats object.  Pass a TransportRepoURI
                object in repouri to configure an object for a particular
                repository URI."""

                self.__url = repouri.uri.rstrip("/")
                self.__scheme = urlsplit(self.__url)[0]
                self.__priority = repouri.priority

                self.__proxy = repouri.proxy
                self.__system = repouri.system

                self._err_decay = 0
                self.__failed_tx = 0
                self.__content_err = 0
                self.__decayable_err = 0
                self.__timeout_err = 0
                self.__total_tx = 0
                self.__consecutive_errors = 0

                self.__connections = 0
                self.__connect_time = 0.0

                self.__used = False

                self.__bytes_xfr = 0.0
                self.__seconds_xfr = 0.0
                self.origin_speed = 0.0
                self.origin_cspeed = 0.0
                self.origin_count = 1
                self.origin_factor = 1
                self.origin_decay = 1

        def clear_consecutive_errors(self):
                """Set the count of consecutive errors to zero.  This is
                done once we know a transaction has been successfully
                completed."""

                self.__consecutive_errors = 0

        def record_connection(self, time):
                """Record amount of time spent connecting."""

                if not self.__used:
                        self.__used = True

                self.__connections += 1
                self.__connect_time += time

        def record_error(self, decayable=False, content=False, timeout=False):
                """Record that an operation to the TransportRepoURI represented
                by this RepoStats object failed with an error.

                Set decayable to true if the error is a transient
                error that may be decayed by the stats framework.

                Set content to true if the error is caused by
                corrupted or invalid content."""

                if not self.__used:
                        self.__used = True

                self.__consecutive_errors += 1
                if decayable:
                        self.__decayable_err += 1
                        self._err_decay += 1
                elif content:
                        self.__content_err += 1
                else:
                        self.__failed_tx += 1
                # A timeout may be decayable or not, so track it in addition
                # to the other classes of errors.
                if timeout:
                        self.__timeout_err += 1


        def record_progress(self, bytes, seconds):
                """Record time and size of a network operation to a
                particular TransportRepoURI, represented by the RepoStats
                object.
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

        def reset(self):
                """Reset transport stats in preparation for next operation."""

                # The connection stats (such as number, cspeed, time) are not
                # reset because the metadata bandwidth calculation would be
                # skewed when picking a host that gives us fast data.  In that
                # case, keeping track of the latency helps quality make a
                # better choice.
                self.__bytes_xfr = 0.0
                self.__seconds_xfr = 0.0
                self.__failed_tx = 0
                self.__content_err = 0
                self.__decayable_err = 0
                self._err_decay = 0
                self.__total_tx = 0
                self.__consecutive_errors = 0
                self.origin_speed = 0.0

        @property
        def bytes_xfr(self):
                """Return the number of bytes transferred."""

                return self.__bytes_xfr

        @property
        def connect_time(self):
                """The average connection time for this host."""

                if self.__connections == 0:
                        if self.__used and self.__timeout_err > 0:
                                return 1.0
                        else:
                                return 0.0

                # old-division; pylint: disable=W1619
                return self.__connect_time / self.__connections

        @property
        def consecutive_errors(self):
                """Return the number of successive errors this endpoint
                has encountered."""

                return self.__consecutive_errors

        @property
        def failures(self):
                """Return the number of failures that the client has encountered
                   while trying to perform operations on this repository."""

                return self.__failed_tx + self.__content_err + \
                    self.__decayable_err

        @property
        def content_errors(self):
                """Return the number of content errors that the client has
                encountered while trying to perform operation on this
                repository."""

                return self.__content_err

        @property
        def num_connect(self):
                """Return the number of times that the host has had a
                connection established.  This is less than or equal to the
                number of transactions."""

                return self.__connections

        @property
        def priority(self):
                """Return the priority of the URI, if one is assigned."""

                if self.__priority is None:
                        return 0

                return self.__priority

        @property
        def scheme(self):
                """Return the scheme of the RepoURI. (e.g. http, file.)"""

                return self.__scheme

        @property
        def quality(self):
                """Return the quality, as an integer value, of the
                repository.  A higher value means better quality.

                This particular implementation of quality() contains
                a random term.  Two successive calls to this function
                may return different values."""

                Nused = 20
                Cused = 10

                Cspeed = 100
                Cconn_speed = 66
                Cerror = 500
                Ccontent_err = 1000
                Crand_max = 20
                Cospeed_none = 100000
                Cocspeed_none = 1

                if self.origin_speed > 0:
                        ospeed = self.origin_speed
                else:
                        ospeed = Cospeed_none

                if self.origin_cspeed > 0:
                        ocspeed = self.origin_cspeed
                else:
                        ocspeed = Cocspeed_none

                # This function applies a bonus to hosts that have little or
                # no usage.  It started out life as a Heaviside step function,
                # but it has since been adjusted so that it scales back the
                # bonus as the host approaches the limit where the bonus
                # is applied.  Hosts with no use recieve the largest bonus,
                # while hosts at <= Nused transactions receive the none.
                def unused_bonus(self):
                        tx = 0

                        tx = self.__total_tx

                        if tx < 0:
                                return 0

                        if tx < Nused:
                                return Cused * (Nused - tx)**2

                        return 0

                def origin_order_bonus(self):
                        b = Cspeed * (self.origin_count) ** 2 + Nused ** 2 * \
                            Cused
                        return self.origin_factor * b * self.origin_decay


                #
                # Quality function:
                #
                # This function presents the quality of a repository as an
                # integer value.  The quality is determined by observing
                # different aspects of the repository's performance.  This
                # includes how often it has been used, the transfer speed, the
                # connect speed, and the number of errors classified by type.
                #
                # The equation is currently defined as:
                #
                # Q = Origin_order_bonus() + Unused_bonus() + Cspeed *
                # ((bytes/.001+seconds) / origin_speed)^2 + random_bonus(
                # Crand_max) - Cconn_speed * (connect_speed /
                # origin_connect_speed)^2 - Ccontent_error * (content_errors)^2
                # - Cerror * (non_decayable_errors + value_of_decayed_errors)^2
                #
                # Unused_bonus = Cused * (MaxUsed - total tx)^2 if total_tx
                # is less than MaxUsed, otherwise return 0.
                #
                # random_bonus is a gaussian distribution where random_max is
                # set as the argument for the stddev.  Most numbers generated
                # will fall between 0 and -/+ random_max, but some will fall
                # outside of the first standard deviation.
                #
                # The constants were derived by live testing, and using
                # a simulated environment.
                #
                # old-division; pylint: disable=W1619
                q = origin_order_bonus(self) + unused_bonus(self) + \
                    (Cspeed * ((self.__bytes_xfr / (.001 + self.__seconds_xfr))
                    / ospeed)**2) + \
                    int(random.gauss(0, Crand_max)) - \
                    (Cconn_speed * (self.connect_time / ocspeed)**2) - \
                    (Ccontent_err * (self.__content_err)**2) - \
                    (Cerror * (self.__failed_tx + self._err_decay)**2)
                return int(q)

        @property
        def seconds_xfr(self):
                """Return the total amount of time elapsed while performing
                operations against this host."""

                return self.__seconds_xfr

        @property
        def success(self):
                """Return the number of successful transaction that this client
                   has performed while communicating with this repository."""

                return self.__total_tx - (self.__failed_tx +
                    self.__content_err +  self.__decayable_err)


        @property
        def transfer_speed(self):
                """Return the average transfer speed in bytes/sec for
                   operations against this uri."""

                if self.__seconds_xfr == 0:
                        return 0.0

                # old-division; pylint: disable=W1619
                return self.__bytes_xfr / self.__seconds_xfr

        @property
        def url(self):
                """Return the URL that identifies the repository that we're
                   keeping statistics about."""

                return self.__url

        @property
        def proxy(self):
                """Return the default proxy being used to contact the repository
                that we're keeping statistics about.  Note that OS
                environment variables, "http_proxy", "https_proxy", "all_proxy"
                and "no_proxy" values will override this value in
                pkg.client.transport.engine."""

                return self.__proxy

        @property
        def system(self):
                """Return whether these statistics are being used to track the
                system publisher, in which case, we always use the proxy
                provided rather than proxy environment variables."""

                return self.__system

        @property
        def used(self):
                """A boolean value that indicates whether the URI
                   has been used for network operations."""

                return self.__used
