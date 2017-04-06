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
# Copyright (c) 2010, 2015, Oracle and/or its affiliates. All rights reserved.
#

import random
from six.moves import range

import pkg.misc as misc
import pkg.client.publisher as pub
import pkg.client.transport.exception as tx

try:
        import pybonjour
except (OSError, ImportError):
        pass
else:
        import select


class MirrorDetector(object):
        """This class uses mDNS and DNS-SD to find link-local content
        mirrors that may be present on the client's subnet."""

        def __init__(self):
                self._mirrors = []
                self.__timeout = 1
                self.__service = "_pkg5._tcp"

        def __contains__(self, key):
                return key in self._mirrors

        def __getitem__(self, pos):
                return self._mirrors[pos]

        def __iter__(self):
                """Each time iterator is invoked, randomly select up to
                five mirrors from the list of available mirrors."""

                listlen = len(self._mirrors)
                iterlst = random.sample(range(listlen), min(listlen, 5))

                for v in iterlst:
                        yield self._mirrors[v]

        def locate(self):
                """When invoked, this populates the MirrorDetector object with
                URLs that name dynamically discovered content mirrors."""

                # Clear the list of mirrors.  It will be repopulated later.
                self._mirrors = []      

                if not "pybonjour" in globals():
                        return

                timedout = False
                tval = self.__timeout

                def browse_cb(sd_hdl, flags, interface_idx, error_code,
                    service_name, regtype, reply_domain):

                        if error_code != pybonjour.kDNSServiceErr_NoError:
                                return

                        if not (flags & pybonjour.kDNSServiceFlagsAdd):
                                return

                        self._resolve_server(interface_idx, error_code,
                            service_name, regtype, reply_domain)

                try:
                        sd_hdl = pybonjour.DNSServiceBrowse(
                            regtype=self.__service, callBack=browse_cb)
                except pybonjour.BonjourError as e:
                        errstr = "mDNS Service Browse Failed: {0}\n".format(
                            e.args[0][1])
                        raise tx.mDNSException(errstr)

                try:
                        while not timedout:
                                avail = select.select([sd_hdl], [], [], tval)
                                if sd_hdl in avail[0]:
                                        pybonjour.DNSServiceProcessResult(
                                            sd_hdl)
                                        tval = 0
                                else:
                                        timedout = True
                except select.error as e:
                        errstr = "Select failed: {0}\n".format(e.args[1])
                        raise tx.mDNSException(errstr)
                except pybonjour.BonjourError as e:
                        errstr = "mDNS Process Result failed: {0}\n".format(
                            e.args[0][1])
                        raise tx.mDNSException(errstr)
                finally:
                        sd_hdl.close()

        def _resolve_server(self, if_idx, ec, service_name, regtype,
            reply_domain):
                """Invoked to resolve mDNS information about a service that
                was discovered by a Browse call."""

                timedout = False
                tval = self.__timeout

                def resolve_cb(sd_hdl, flags, interface_idx, error_code,
                    full_name, host_target, port, txt_record):

                        if error_code != pybonjour.kDNSServiceErr_NoError:
                                return

                        tr = pybonjour.TXTRecord.parse(txt_record)
                        if "url" in tr:
                                url = tr["url"]
                                if not misc.valid_pub_url(url):
                                        return
                                self._mirrors.append(pub.RepositoryURI(url))

                try:
                        sd_hdl =  pybonjour.DNSServiceResolve(0, if_idx,
                            service_name, regtype, reply_domain, resolve_cb)
                except pybonjour.BonjourError as e:
                        errstr = "mDNS Service Resolve Failed: {0}\n".format(
                            e.args[0][1])
                        raise tx.mDNSException(errstr)

                try:
                        while not timedout:
                                avail = select.select([sd_hdl], [], [], tval)
                                if sd_hdl in avail[0]:
                                        pybonjour.DNSServiceProcessResult(
                                            sd_hdl)
                                        tval = 0
                                else:
                                        timedout = True
                except select.error as e:
                        errstr = "Select failed; {0}\n".format(e.args[1])
                        raise tx.mDNSException(errstr)
                except pybonjour.BonjourError as e:
                        errstr = "mDNS Process Result Failed: {0}\n".format(
                            e.args[0][1])
                        raise tx.mDNSException(errstr)
                finally:
                        sd_hdl.close()
