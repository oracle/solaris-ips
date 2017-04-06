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
# actionbench - benchmark action creation
#

from __future__ import division
from __future__ import print_function

import pkg.actions as actions

import timeit

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":

        setup1 = "import pkg.actions as actions"
        str1 = 'action = actions.fromstr("file 58371e22b5e75ec66602b966edf29bcce7038db5 elfarch=i386 elfbits=32 elfhash=cd12b081ddaef993fd0276dd04d653222d25fa77 group=bin mode=0755 owner=root path=usr/lib/libzonecfg.so.1 pkg.size=178072")'

        print("action creation")
        n = 20000
        for i in (1, 2, 3):
                try:
                        t = timeit.Timer(str1, setup1).timeit(n)
                        print("{0:>20f}  {1:>8d} actions/sec".format(t,
                            int(n // t)))
                except KeyboardInterrupt:
                        import sys
                        sys.exit(0)

        setup2 = """import pkg.actions as actions
a1 = actions.fromstr("file 1234 group=bin mode=0755 owner=root path=usr/lib/libzonecfg.so.1")
a2 = actions.fromstr("dir group=bin mode=0755 owner=root path=usr/lib/libzonecfg.so.2")
        """

        n = 520000
        str2 = "a1 == a2"

        print("action comparison")
        print("\tequality")
        for i in (1, 2, 3):

                try:
                        t = timeit.Timer(str2, setup2).timeit(n)
                        print("{0:>20f}  {1:>8d} action comparisons/sec".format(t,
                            int(n // t)))
                except KeyboardInterrupt:
                        import sys
                        sys.exit(0)

        str2 = "a1 > a2"
        print("\tgt")
        for i in (1, 2, 3):

                try:
                        t = timeit.Timer(str2, setup2).timeit(n)
                        print("{0:>20f}  {1:>8d} action comparisons/sec".format(t,
                            int(n // t)))
                except KeyboardInterrupt:
                        import sys
                        sys.exit(0)

        str2 = "a1 < a2"
        print("\tlt")
        for i in (1, 2, 3):

                try:
                        t = timeit.Timer(str2, setup2).timeit(n)
                        print("{0:>20f}  {1:>8d} action comparisons/sec".format(t,
                            int(n // t)))
                except KeyboardInterrupt:
                        import sys
                        sys.exit(0)

        print("minimalist comparison equality")

        setup3 = """
class superc(object):
        def __lt__(a, b):
                return a.ordinality == b.ordinality

class aa(superc):
        def __init__(self):
                self.ordinality = 1

class bb(superc):
        def __init__(self):
                self.ordinality = 2

a = aa()
b = bb()
        """

        str3 = "a == b"
        for i in (1, 2, 3):

                try:
                        t = timeit.Timer(str3, setup3).timeit(n)
                        print("{0:>20f}  {1:>8d} comparisons/sec".format(t,
                            int(n // t)))
                except KeyboardInterrupt:
                        import sys
                        sys.exit(0)


        setup4 = """import pkg.actions as actions
a1 = actions.fromstr("file 1234 group=bin mode=0755 owner=root path=usr/lib/libzonecfg.so.1")
        """

        n = 260000
        str4 = "str(a1)"

        print("action to string conversion")
        for i in (1, 2, 3):

                try:
                        t = timeit.Timer(str4, setup4).timeit(n)
                        print("{0:>20f}  {1:>8d} actions to string/sec".format(t,
                            int(n // t)))
                except KeyboardInterrupt:
                        import sys
                        sys.exit(0)

        # I took an existing manifest and randomized the lines.
        setup5 = """
import pkg.manifest as manifest
m=\"\"\"
dir group=sys mode=0755 owner=root path=usr/share
dir group=sys mode=0755 owner=root path=usr/lib/brand/native
file 836b34c529720378b05e55aae1f9c07f148ad099 group=bin mode=0444 owner=root path=usr/lib/brand/native/config.xml pkg.size=3785
file dfa894680b63cba4ea06698ece7786e4af08ebe9 group=sys mode=0444 opensolaris.zone=global owner=root path=var/svc/manifest/system/zones.xml pkg.size=2835
link path=usr/bin/zonename target=../../sbin/zonename
dir group=sys mode=0755 owner=root path=usr/share/lib/xml
file 27bd43e341d2d68d6715e9c74986dc96efdbba04 group=sys mode=0644 opensolaris.zone=global owner=root path=etc/zones/index pkg.size=1103 preserve=true
file a98845cf2047a2eea8df6283201cc19c66dd6bbd elfarch=i386 elfbits=32 elfhash=9320a13a81de97546aec93b7c508d9c6de6dcf0e group=sys mode=0755 owner=root path=usr/kernel/drv/zcons pkg.size=9220
depend fmri=pkg:/SUNWpool@0.5.11-0.79 type=require
file 8030ff97f43d78d3539e6487e2f98b61a9450783 group=bin mode=0444 owner=root path=usr/lib/brand/native/platform.xml pkg.size=4452
file 58371e22b5e75ec66602b966edf29bcce7038db5 elfarch=i386 elfbits=32 elfhash=cd12b081ddaef993fd0276dd04d653222d25fa77 group=bin mode=0755 owner=root path=usr/lib/libzonecfg.so.1 pkg.size=178072
file 795465bd69c3b4f23ef5699c9422dcadf31e4e4a group=sys mode=0444 opensolaris.zone=global owner=root path=var/svc/manifest/system/resource-mgmt.xml pkg.size=2888
file a1f246522e3736f260028d4ad85520a5e8b735c9 elfarch=i386 elfbits=32 elfhash=1b9b337a8a5d5a401f6d6a2a91bc63940f5be885 group=bin mode=0755 owner=root path=usr/lib/libbrand.so.1 pkg.size=55616
dir group=bin mode=0755 owner=root path=usr/lib/zones
file 712d89faf0996dcc70aedbf73db024332894d24c elfarch=i386 elfbits=64 elfhash=da90e678c2478e3dc390df47c10535ab0b03270a group=bin mode=0755 owner=root path=usr/lib/amd64/libzonecfg.so.1 pkg.size=204992
dir group=sys mode=0755 opensolaris.zone=global owner=root path=etc
dir group=sys mode=0755 owner=root path=usr/share/lib
file a7521f402cbc479c160bde8a06fe00ab621426d3 group=bin mode=0444 opensolaris.zone=global owner=root path=etc/zones/SUNWblank.xml pkg.size=1196
dir group=sys mode=0755 owner=root path=usr/share/lib/xml/dtd
depend fmri=pkg:/SUNWzfs@0.5.11-0.79 type=require
dir group=sys mode=0755 opensolaris.zone=global owner=root path=var
file 0e42a6543bd2e9a005e2be1282dcb62a4853ddf7 elfarch=i386 elfbits=32 elfhash=d35f1848ac052bfee3ead95a1914c946d2d3466d group=bin mode=0555 owner=root path=usr/sbin/zonecfg pkg.size=216968
dir group=sys mode=0755 opensolaris.zone=global owner=root path=var/svc/manifest/system
set name=description value="Solaris Zones (Usr)"
file 7e95e16941d5de869da5f7a51c99d84139a35bb8 elfarch=i386 elfbits=64 elfhash=df2beb2742e8adfb774ecbf7802f6972e2c0b97f group=sys mode=0755 owner=root path=usr/kernel/drv/amd64/zcons pkg.size=15632
file 86bac4c0a58de192fcf22ea9060c91224ae5fa3c elfarch=i386 elfbits=32 elfhash=ddf1b4f11e7d74a9400ba4e3988a71809dca5631 group=bin mode=0555 owner=root path=usr/sbin/zlogin pkg.size=37460
license f9562cfd7500134682a60f6d9d6dc256902917c8 license=SUNWzoneu.copyright path=copyright pkg.size=93 transaction_id=1202260990_pkg%3A%2FSUNWzone%400.5.11%2C5.11-0.79%3A20080205T172310Z
dir group=bin mode=0755 owner=root path=usr/bin
dir group=sys mode=0755 opensolaris.zone=global owner=root path=var/svc
legacy arch=i386 category=system desc="Solaris Zones Configuration Files" hotline="Please contact your local service provider" name="Solaris Zones (Root)" pkg=SUNWzoner vendor="Sun Microsystems, Inc." version=11.11,REV=2008.01.05.16.07
dir group=sys mode=0755 opensolaris.zone=global owner=root path=var/svc/manifest
file cb02c2a749bf0e22fd02af975ddd9bf86bb0ce19 group=bin mode=0644 owner=root path=usr/share/lib/xml/dtd/zone_platform.dtd.1 pkg.size=4372
file 946db15bd854df6140bd4a48fb2b8e0238a81e3d group=bin mode=0555 opensolaris.zone=global owner=root path=lib/svc/method/svc-resource-mgmt pkg.size=1504
file 2f11fd3f39c87d7b70bd0d18808efdf6292b115f group=bin mode=0444 owner=root path=usr/share/lib/xml/dtd/zonecfg.dtd.1 pkg.size=3923
depend fmri=pkg:/SUNWtecla@1.6.0-0.79 type=require
dir group=bin mode=0755 owner=root path=usr/lib/amd64
file acf17653def8f31e2d1251436435151b98d5e4db group=bin mode=0555 opensolaris.zone=global owner=root path=lib/svc/method/svc-zones pkg.size=4448
depend fmri=pkg:/SUNWcsl@0.5.11-0.79 type=require
dir group=bin mode=0755 owner=root path=usr/lib/brand
dir group=sys mode=0755 owner=root path=usr
file b839312297d07b2596dff73cb449f1db768277ce elfarch=i386 elfbits=64 elfhash=5ee24f2fd5ffc9cb8dd0a1a42c0633ad955c6739 group=bin mode=0755 owner=root path=usr/lib/amd64/libbrand.so.1 pkg.size=61440
file 723401c446e8779a963d6d67cbb5f9ab187fd25a group=bin mode=0644 owner=root path=usr/share/lib/xml/dtd/brand.dtd.1 pkg.size=10159
dir group=bin mode=0755 owner=root path=usr/sbin
dir group=bin mode=0755 opensolaris.zone=global owner=root path=lib
dir group=bin mode=0755 opensolaris.zone=global owner=root path=lib/svc/method
file dbd52c79aa5a1dc92232994a815718dedbc70eec elfarch=i386 elfbits=32 elfhash=2b510c241544342123d3591ea17548a075192d89 group=bin mode=0555 owner=root path=usr/lib/zones/zoneadmd pkg.size=109720
legacy arch=i386 category=system desc="Solaris Zones Configuration and Administration" hotline="Please contact your local service provider" name="Solaris Zones (Usr)" pkg=SUNWzoneu vendor="Sun Microsystems, Inc." version=11.11,REV=2008.01.05.16.07
file 1269a117ab6ed3eb8e86f34aabfffba1221ac829 group=bin mode=0444 opensolaris.zone=global owner=root path=etc/zones/SUNWdefault.xml pkg.size=1366
set name=publisher value=foo
dir group=sys mode=0755 owner=root path=usr/kernel/drv/amd64
file 2c9c0651e59cbb4b12dd9c8b9502003fd4b0af74 group=bin mode=0755 owner=root path=usr/lib/brand/native/postclone pkg.size=1635
file 0049f03d9a0fc515a0b89579abac3f2d04f0dede elfarch=i386 elfbits=32 elfhash=4777a16b7740405428b46a221ba30e36916db4e8 group=bin mode=0555 owner=root path=usr/sbin/zoneadm pkg.size=107864
dir group=sys mode=0755 owner=root path=usr/kernel
set name=fmri value=pkg:/SUNWzone@0.5.11,5.11-0.79:20080205T172310Z
dir group=sys mode=0755 opensolaris.zone=global owner=root path=etc/zones
depend fmri=pkg:/SUNWlxml@2.6.23-0.79 type=require
dir group=bin mode=0755 opensolaris.zone=global owner=root path=lib/svc
dir group=sys mode=0755 owner=root path=usr/kernel/drv
dir group=bin mode=0755 owner=root path=usr/lib
license f9562cfd7500134682a60f6d9d6dc256902917c8 license=SUNWzoner.copyright path=copyright pkg.size=93 transaction_id=1202260990_pkg%3A%2FSUNWzone%400.5.11%2C5.11-0.79%3A20080205T172310Z
\"\"\"
"""

        n = 1000

        str5="""
mf = manifest.Manifest()
mf.set_content(m)
"""

        try:
                print("manifest contents loading")
                for i in (1, 2, 3):

                        t = timeit.Timer(str5, setup5).timeit(n)
                        print("{0:>20f} {1:>8d} manifest contents loads/sec ({2:d} actions/sec)".format(
                            t, int(n // t), int((n * 60) // t)))

                n = 1000000
                str6 = "id(a1)"
                print("id() speed")
                for i in (1, 2, 3):

                        t = timeit.Timer(str6, setup4).timeit(n)
                        print("{0:>20f} {1:>8d} calls to id(action) /sec".format(t,
                            int(n // t)))
        except KeyboardInterrupt:
                import sys
                sys.exit(0)
