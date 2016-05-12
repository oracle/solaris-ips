#!/usr/bin/python2.7
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

from __future__ import print_function
import gettext
import locale
import sys

import depot
import stats
import pkg.misc as misc

class Scenario(object):
        """A Scenario has a list of depot.RepositoryURIs."""

        def __init__(self, title):
                self.title = title
                self.repo_uris = []
                self.origin_uris = []

        def get_repo_uris(self):
                return self.repo_uris

        def add_repo_uri(self, label, speed, cspeed,
            error_rate=depot.ERROR_FREE, error_type=depot.ERROR_T_NET,
            speed_distribution=depot.MODAL_SINGLE):

                r = depot.RepositoryURI(label, speed, cspeed,
                    error_rate=error_rate, error_type=error_type,
                    modality=speed_distribution)

                self.repo_uris.append(r)

        def add_origin_uri(self, label, speed, cspeed,
            error_rate=depot.ERROR_FREE, error_type=depot.ERROR_T_NET,
            speed_distribution=depot.MODAL_SINGLE):

                r = depot.RepositoryURI(label, speed, cspeed,
                    error_rate=error_rate, error_type=error_type,
                    modality=speed_distribution)

                self.origin_uris.append(r)

        def get_megabytes(self):
                return self.__total_mb

        def set_megabytes(self, mb):
                self.__total_mb = mb

        def run(self):
                print("SCENARIO: {0}".format(self.title))

                total = self.__total_mb * 1024 * 1024

                rc = stats.RepoChooser()
                urilist = self.repo_uris[:]
                urilist.extend(self.origin_uris)

                while total > 0:
                        s = rc.get_repostats(urilist, self.origin_uris)

                        n = len(s)
                        m = rc.get_num_visited(urilist)

                        if m < n:
                                c = 10
                        else:
                                c = 100

                        print("bytes left {0:d}; retrieving {1:d} files".format(
                            total, c))
                        rc.dump()

                        # get 100 files
                        r = s[0]
                        for n in range(c):
                                req = r[1].request(rc)
                                total -= req[1]

                rc.dump()

misc.setlocale(locale.LC_ALL)
gettext.install("pkg", "/usr/share/locale")

total_mb = 1000

# Scenario 1.  A single origin.

single = Scenario("single origin")

single.add_origin_uri("origin", depot.SPEED_FAST, depot.CSPEED_LAN)

single.set_megabytes(total_mb)

single.run()

# Scenario 2a.  An origin and mirror, mirror faster.

one_mirror = Scenario("origin and a faster mirror")

one_mirror.add_origin_uri("origin", depot.SPEED_FAST, depot.CSPEED_NEARBY)
one_mirror.add_repo_uri("mirror", depot.SPEED_VERY_FAST, depot.CSPEED_LAN)

one_mirror.set_megabytes(total_mb)

one_mirror.run()

# Scenario 2b.  An origin and mirror, origin faster.

one_mirror = Scenario("origin and a slower mirror")

one_mirror.add_origin_uri("origin", depot.SPEED_VERY_FAST, depot.CSPEED_LAN)
one_mirror.add_repo_uri("mirror", depot.SPEED_FAST, depot.CSPEED_NEARBY)

one_mirror.set_megabytes(total_mb)

one_mirror.run()

# Scenario 2c.  An origin and mirror, mirror faster, but decaying.

one_mirror = Scenario("origin and a faster, but decaying, mirror")

one_mirror.add_origin_uri("origin", depot.SPEED_FAST, depot.CSPEED_NEARBY)
one_mirror.add_repo_uri("mirror", depot.SPEED_VERY_FAST, depot.CSPEED_LAN,
    speed_distribution=depot.MODAL_DECAY)

one_mirror.set_megabytes(total_mb)

one_mirror.run()

# Scenario 2d.  An origin and mirror, mirror slower, but increasing.

one_mirror = Scenario("origin and a slower, but increasing, mirror")

one_mirror.add_origin_uri("origin", depot.SPEED_MEDIUM, depot.CSPEED_MEDIUM)
one_mirror.add_repo_uri("mirror", depot.SPEED_FAST, depot.CSPEED_LAN,
    speed_distribution=depot.MODAL_INCREASING)

one_mirror.set_megabytes(total_mb)

one_mirror.run()

# Scenario 2e.  An origin and mirror, mirror encountering decyable transport
# errors.

one_mirror = Scenario("origin and a faster mirror.  Mirror gets decayable errors")

one_mirror.add_origin_uri("origin", depot.SPEED_FAST, depot.CSPEED_LAN)
one_mirror.add_repo_uri("mirror", depot.SPEED_SLIGHTLY_FASTER, depot.CSPEED_LAN,
    error_rate=depot.ERROR_LOW, error_type=depot.ERROR_T_DECAYABLE)


one_mirror.set_megabytes(total_mb)

one_mirror.run()

# Scenario 3a.  An origin and two mirrors, one decaying.

one_mirror = Scenario("origin and two mirrors")

one_mirror.add_origin_uri("origin", depot.SPEED_FAST, depot.CSPEED_NEARBY)
one_mirror.add_repo_uri("mirror", depot.SPEED_SLIGHTLY_FASTER,
    depot.CSPEED_LAN)
one_mirror.add_repo_uri("mirror2", depot.SPEED_VERY_FAST, depot.CSPEED_NEARBY,
    speed_distribution=depot.MODAL_DECAY)

one_mirror.set_megabytes(total_mb)

one_mirror.run()

# Scenario 3b.  An origin and five mirrors.

one_mirror = Scenario("origin and five mirrors")

one_mirror.add_origin_uri("origin", depot.SPEED_MODERATE, depot.CSPEED_MEDIUM)
one_mirror.add_repo_uri("mirror", depot.SPEED_SLIGHTLY_FASTER, depot.CSPEED_LAN)
one_mirror.add_repo_uri("mirror2", depot.SPEED_MEDIUM, depot.CSPEED_SLOW)
one_mirror.add_repo_uri("mirror3", depot.SPEED_SLOW, depot.CSPEED_SLOW)
one_mirror.add_repo_uri("mirror4", depot.SPEED_VERY_SLOW,
   depot.CSPEED_VERY_SLOW)
one_mirror.add_repo_uri("mirror5", depot.SPEED_SLOW, depot.CSPEED_FARAWAY)

one_mirror.set_megabytes(total_mb)

one_mirror.run()

# Scenario 4.  Six origins.

six_origin = Scenario("six origins")

six_origin.add_origin_uri("origin1", depot.SPEED_VERY_SLOW,
   depot.CSPEED_VERY_SLOW)
six_origin.add_origin_uri("origin2", depot.SPEED_SLOW, depot.CSPEED_FARAWAY)
six_origin.add_origin_uri("origin3", depot.SPEED_MODERATE, depot.CSPEED_MEDIUM)
six_origin.add_origin_uri("origin4", depot.SPEED_SLIGHTLY_FASTER, depot.CSPEED_LAN)
six_origin.add_origin_uri("origin5", depot.SPEED_MEDIUM, depot.CSPEED_SLOW)
six_origin.add_origin_uri("origin6", depot.SPEED_FAST, depot.CSPEED_MEDIUM)

six_origin.set_megabytes(total_mb)

six_origin.run()
