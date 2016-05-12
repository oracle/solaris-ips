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
# pylint is picky about this message:
# old-division; pylint: disable=W1619
import math
import random
import sys

import stats

# Simulator error rate.  These values are divided by 1000 and compared
# against a random float [0, 1).  A larger number means errors occur more
# frequently.
ERROR_FREE = 0
ERROR_RARELY = 1
ERROR_LOW = 5
ERROR_MEDIUM = 10
ERROR_HIGH = 150

# Describes the type of error that will be generated.
#
# General network error.
ERROR_T_NET = 0
# Transient error (decayable).
ERROR_T_DECAYABLE = 1
# Error from invalid content.
ERROR_T_CONTENT = 2

# Describes the mode of the depot's speed distribution.
#
# A single speed.
MODAL_SINGLE = 0
# Two speeds.
MODAL_DUAL = 1
# Speed decreases over time.
MODAL_DECAY = 2
# Speed increases over time.
MODAL_INCREASING = 3
# Speed is random.
MODAL_RANDOM = 4

# These constants define the depots' max speed in kB/s
SPEED_VERY_FAST = 400
SPEED_SLIGHTLY_FASTER = 105
SPEED_FAST = 100
SPEED_MODERATE = 75
SPEED_MEDIUM = 50
SPEED_SLOW = 10
SPEED_VERY_SLOW = 5

# Constants define the latency / connect time measurement for
# the simulated depot.  The values are in milliseconds.
CSPEED_LAN = 1
CSPEED_NEARBY = 2
CSPEED_MEDIUM = 10
CSPEED_SLOW = 50
CSPEED_VERY_SLOW = 100
CSPEED_FARAWAY = 3500


class RepositoryURI(object):
        def __init__(self, label, speed, cspeed, error_rate=ERROR_FREE,
            error_type=ERROR_T_NET, modality=MODAL_SINGLE):
                """Create a RepositoryURI object.  The 'speed' argument
                gives the speed in kB/s.  The 'cspeed' argument gives the
                connect time in milliseconds.  The 'error_rate' variable
                defines how often errors occur.  The error_type is
                defined by 'error_type'.  The 'modality' argument
                defines the different speed distributions."""

                # Production members
                self.uri = "http://" + label
                self.priority = 1

                # Simulator members
                self.label = label
                self.speed = speed * 1024
                self.cspeed = cspeed / 1000.0
                self.maxtx = 10000.0
                self.warmtx = 1000.0
                self.minspeed = .1
                self.__tx = 0
                self.__error_rate = error_rate / 1000.0
                self.__error_type = error_type
                self.__response_modality = modality
                self.__decay = 0.9
                self.__proxy = None
                self.__system = None
                self.aggregate_decay = 1

                self.stats = stats.RepoStats(self)

        def __get_proxy(self):
                return self.__proxy

        def __set_proxy(self, val):
                self.__proxy = val

        def __get_system(self):
                return self.__system

        def __set_system(self, val):
                self.__system = val

        proxy = property(__get_proxy, __set_proxy, None, "Proxy of the "
            "repository URI.")

        system = property(__get_system, __set_system, None, "System publisher "
            "of the repository URI.")

        def key(self):
                """Returns a value that can be used to identify this RepoURI
                uniquely for the transport system.  Normally, this would be done
                using __hash__() however, TransportRepoURI objects are not
                guaranteed to be immutable.

                The key is a (uri, proxy) tuple, where the proxy is
                the proxy used to reach that URI.  Note that in the transport
                system, we may choose to override the proxy value here."""

                u = self.uri
                p = self.__proxy

                if self.uri:
                        u = self.uri.rstrip("/")
                return (u, p)

        def speed_single(self, size):
                """Implements a depot that runs at a single speed."""

                return size / random.gauss(self.speed, self.speed / 4)

        def speed_increasing(self, size):
                """Depot's speed gradually increases over time."""

                s = min(self.minspeed + (self.__tx / self.warmtx), 1) * \
                    random.gauss(self.speed, self.speed / 4)

                return size / s

        def speed_decay(self, size):
                """Depot gets slower as time goes on."""

                if random.uniform(0., 1.) < 0.05:
                        self.aggregate_decay *= self.__decay

                return size / (self.aggregate_decay *
                    random.gauss(self.speed, self.speed / 4))

        def request(self, rc, size=None):
                """Simulate a transport request using RepoChooser 'rc'.
                Size is given in the 'size' argument."""

                errors = 0

                if not size:
                        size = random.randint(1, 1000) * 1024

                if not rc[self.key()].used:
                        rc[self.key()].record_connection(self.cspeed)
                else:
                        conn_choose = (1 / self.maxtx) * \
                            math.exp(-1 / self.maxtx)
                        if random.random() < conn_choose:
                                rc[self.key()].record_connection(self.cspeed)

                rc[self.key()].record_tx()
                self.__tx += 1

                if random.random() < self.__error_rate:
                        if self.__error_type == ERROR_T_DECAYABLE:
                                rc[self.key()].record_error(decayable=True)
                        elif self.__error_type == ERROR_T_CONTENT:
                                rc[self.key()].record_error(content=True)
                        else:
                                rc[self.key()].record_error()
                        return (1, size, None)

                if self.__response_modality == MODAL_SINGLE:
                        time = self.speed_single(size)
                elif self.__response_modality == MODAL_DECAY:
                        time = self.speed_decay(size)
                elif self.__response_modality == MODAL_INCREASING:
                        time = self.speed_increasing(size)
                else:
                        raise RuntimeError("no modality")

                rc[self.key()].record_progress(size, time)

                return (errors, size, time)
