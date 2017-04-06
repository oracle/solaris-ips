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
# Copyright (c) 2008, 2015, Oracle and/or its affiliates. All rights reserved.
#

#
# fmribench - benchmark fmri creation and other related operations
#

from __future__ import division
from __future__ import print_function

import pkg.fmri as fmri
import pkg.version as version
import time
import timeit
import sys

benches = [
        
        [ "dotsequence creation", 100000,
        """import pkg.version as version""",
        """v1 = version.DotSequence("0.72.1")"""
        ],

        [ "dotsequence cmp 1 (v2 > v1)", 1000000,
        """import pkg.version as version
v1 = version.DotSequence("0.72.1")
v2 = version.DotSequence("0.73.1")""",
        """v2 > v1"""
        ],

        [ "dotsequence cmp 2 (v1 > None)", 1000000,
        """import pkg.version as version
v1 = version.DotSequence("0.72.1")""",
        """v1 > None"""
        ],

        [ "dotsequence cmp 3 (same)", 1000000,
        """import pkg.version as version
v1 = version.DotSequence("0.72.1")
v2 = version.DotSequence("0.72.1")""",
        """v1 == v2"""
        ],

        [ "dotsequence is_subsequence (true)", 100000,
        """import pkg.version as version
v1 = version.DotSequence("0.72.1")
v2 = version.DotSequence("0.72.1.3.4.5")""",
        """v1.is_subsequence(v2)"""
        ],

        [ "dotsequence is_subsequence (false)", 100000,
        """import pkg.version as version
v1 = version.DotSequence("0.72.1")
v2 = version.DotSequence("0.72.1.3.4.5")""",
        """v2.is_subsequence(v1)"""
        ],

        [ "dotsequence to string", 100000,
        """import pkg.version as version
v1 = version.DotSequence("0.72.1")""",
        """str(v1)"""
        ],

        [ "version hash (tstamp)", 100000,
        """import pkg.version as version
f1 = version.Version("5.11-0.72:20070921T203926Z", "0.5.11")""",
        """hash(f1)"""
        ],

        [ "version hash (no-tstamp)", 100000,
        """import pkg.version as version
f1 = version.Version("5.11-0.72", "0.5.11")""",
        """hash(f1)"""
        ],

        [ "fmri create (string)", 50000,
        """import pkg.fmri as fmri""",
        """f = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")"""
        ],

        [ "fmri create (parts)", 50000,
        """import pkg.fmri as fmri""",
        """f = fmri.PkgFmri(publisher="origin", name="SUNWxwssu", version="0.5.11,5.11-0.72:20070921T203926Z")"""
        ],

        [ "fmri create (no tstamp)", 50000,
        """import pkg.fmri as fmri""",
        """f = fmri.PkgFmri("pkg://origin/SUNWlxml@2.6.31,0.5.11-0.90")"""
        ],

        [ "fmri create (no tstamp, no bld/branch)", 50000,
        """import pkg.fmri as fmri""",
        """f = fmri.PkgFmri("pkg://origin/SUNWlxml@2.6.31")"""
        ],

        [ "fmri create (no tstamp, no bld/branch, no origin)", 50000,
        """import pkg.fmri as fmri""",
        """f = fmri.PkgFmri("pkg:/SUNWlxml@2.6.31-0.90")"""
        ],

        [ "fmri to string (no tstamp)", 100000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg:/SUNWxwssu@0.5.11,5.11-0.72")""",
        """str(f1)"""
        ],

        [ "fmri to string (no publisher)", 100000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg:/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")""",
        """str(f1)"""
        ],

        [ "fmri to string (with publisher)", 100000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")""",
        """str(f1)"""
        ],

        [ "fmri hash (tstamp)", 100000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")""",
        """hash(f1)"""
        ],

        [ "fmri hash (no-tstamp)", 100000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72")""",
        """hash(f1)"""
        ],

        [ "fmri equality (timestamp)", 500000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
f2 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203927Z")""",
        """f1 == f2"""
        ],

        [ "fmri equality (branch)", 500000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
f2 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.74:20070921T203927Z")""",
        """f1 == f2"""
        ],

        [ "fmri equality (version)", 500000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
f2 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.12,5.11-0.74:20070921T203927Z")""",
        """f1 == f2"""
        ],

        [ "fmri equality (pkgname)", 100000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
f2 = fmri.PkgFmri("pkg://origin/SUNWxwssx@0.5.12,5.11-0.74:20070921T203927Z")""",
        """f1 == f2"""
        ],

        [ "fmri equality (same)", 100000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
f2 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")""",
        """f1 == f2"""
        ],

        [ "fmri gt (timestamp)", 500000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
f2 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203927Z")""",
        """f1 > f2"""
        ],

        [ "fmri is_successor (timestamp)", 100000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
f2 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203927Z")""",
        """f1.is_successor(f2)"""
        ],

        [ "fmri is_successor (branch)", 100000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
f2 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.74:20070921T203926Z")""",
        """f1.is_successor(f2)"""
        ],

        [ "fmri is_successor (version, false)", 100000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
f2 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.12,5.11-0.74:20070921T203926Z")""",
        """f1.is_successor(f2)"""
        ],

        [ "fmri is_successor (version, true)", 100000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
f2 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.12,5.11-0.74:20070921T203926Z")""",
        """f2.is_successor(f1)"""
        ],

        [ "fmri is_successor (pkgname)", 1000000,
        """import pkg.fmri as fmri
f1 = fmri.PkgFmri("pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
f2 = fmri.PkgFmri("pkg://origin/SUNWxwssx@0.5.12,5.11-0.74:20070921T203926Z")""",
        """f1.is_successor(f2)"""
        ],


]

if __name__ == "__main__":

        for b in benches:
                bname = b[0]
                iter = b[1]
                setup = b[2]
                action = b[3]
                tsum = 0
                itersum = 0
                print("# {0}".format(bname))
                try:
                        for i in (1, 2, 3):
                                t = timeit.Timer(action, setup).timeit(iter)
                                print("#   {0:>6.2f}s   {1:>9d}/sec".format(t, int(iter // t)))
                                tsum += t
                                itersum += iter
                        print("#\n{0:40}  {1:>9d}/sec".format(bname, int(itersum // tsum)))
                        print("#\n#")
                except KeyboardInterrupt:
                        print("Tests stopped at user request.")
                        sys.exit(1)
                except:
                        print("#\n{0:40}  <Test Failed>".format(bname))
                        raise
