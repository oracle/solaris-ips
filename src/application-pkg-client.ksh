#!/bin/ksh -px

export MACH=`uname -p`
eval `pkgsend open application/pkg@0.1-1`
if [ $? != 0 ]; then
	echo \*\* script aborted
	exit 1
fi

echo $PKG_TRANS_ID
pkgsend add file 0555 root bin \
	/usr/bin/pkg proto/root_$MACH/usr/bin/pkg
pkgsend add file 0555 root bin \
	/usr/bin/pkgsend proto/root_$MACH/usr/bin/pkgsend
pkgsend add file 0555 root bin \
	/usr/lib/pkg.depotd proto/root_$MACH/usr/lib/pkg.depotd
pkgsend add file 0444 root bin \
	/usr/lib/python2.4/vendor-packages/pkg/__init__.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/__init__.py
pkgsend add file 0444 root bin \
	/usr/lib/python2.4/vendor-packages/pkg/catalog.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/catalog.py
pkgsend add file 0444 root bin \
	/usr/lib/python2.4/vendor-packages/pkg/config.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/config.py
pkgsend add file 0444 root bin \
	/usr/lib/python2.4/vendor-packages/pkg/content.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/content.py
pkgsend add file 0444 root bin \
	/usr/lib/python2.4/vendor-packages/pkg/dependency.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/dependency.py
pkgsend add file 0444 root bin \
	/usr/lib/python2.4/vendor-packages/pkg/fmri.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/fmri.py
pkgsend add file 0444 root bin \
	/usr/lib/python2.4/vendor-packages/pkg/image.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/image.py
pkgsend add file 0444 root bin \
	/usr/lib/python2.4/vendor-packages/pkg/package.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/package.py
pkgsend add file 0444 root bin \
	/usr/lib/python2.4/vendor-packages/pkg/version.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/version.py
# XXX replace with service action
#pkgsend add file 0444 root bin \
#	/var/svc/manifest/application/pkg-server.xml proto/root_$MACH/var/svc/manifest/application/pkg-server.xml
# we depend on 2.4 being present on the system in the standard location
# XXXrequire pkg://application/python@2.4
# some people might split this into three packages:  common/pkg,
# application/pkg/client, and application/pkg/server.
pkgsend close
