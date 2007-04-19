# shorthand we need
#
# file mode owner group dest offset/$@
#
# set file1 file2 file3 ... rule file mode owner group dest/$1 offset/$@
#
# if directory is not defined, then root:bin or root:sys according to
# image policy
#
file 0555 root bin /usr/bin/pkg proto/root_$MACH/usr/bin/pkg
file 0555 root bin /usr/bin/pkgsend proto/root_$MACH/usr/bin/pkgsend
file 0555 root bin /usr/lib/pkg.depotd proto/root_$MACH/usr/lib/pkg.depotd
file 0444 root bin /usr/lib/python2.4/vendor-packages/pkg/__init__.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/__init__.py
file 0444 root bin /usr/lib/python2.4/vendor-packages/pkg/catalog.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/catalog.py
file 0444 root bin /usr/lib/python2.4/vendor-packages/pkg/config.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/config.py
file 0444 root bin /usr/lib/python2.4/vendor-packages/pkg/content.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/content.py
file 0444 root bin /usr/lib/python2.4/vendor-packages/pkg/dependency.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/dependency.py
file 0444 root bin /usr/lib/python2.4/vendor-packages/pkg/fmri.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/fmri.py
file 0444 root bin /usr/lib/python2.4/vendor-packages/pkg/image.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/image.py
file 0444 root bin /usr/lib/python2.4/vendor-packages/pkg/package.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/package.py
file 0444 root bin /usr/lib/python2.4/vendor-packages/pkg/version.py proto/root_$MACH/usr/lib/python2.4/vendor-packages/pkg/version.py
service proto/root_$MACH/var/svc/manifest/application/pkg-server.xml
# we depend on 2.4 being present on the system in the standard location
require pkg://application/python@2.4
# some people might split this into three packages:  common/pkg,
# application/pkg/client, and application/pkg/server.
