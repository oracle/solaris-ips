#!/usr/bin/python2.6
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
# Copyright (c) 2008, 2010 Oracle and/or its affiliates.  All rights reserved.
#

import errno
import fnmatch
import os
import platform
import stat
import sys
import shutil
import re
import subprocess
import tarfile
import tempfile
import urllib
import py_compile
import hashlib

from distutils.errors import DistutilsError
from distutils.core import setup, Extension
from distutils.cmd import Command
from distutils.command.install import install as _install
from distutils.command.build import build as _build
from distutils.command.build_py import build_py as _build_py
from distutils.command.bdist import bdist as _bdist
from distutils.command.clean import clean as _clean

from distutils.sysconfig import get_python_inc
import distutils.file_util as file_util
import distutils.dir_util as dir_util
import distutils.util as util

osname = platform.uname()[0].lower()
ostype = arch = 'unknown'
if osname == 'sunos':
        arch = platform.processor()
        ostype = "posix"
elif osname == 'linux':
        arch = "linux_" + platform.machine()
        ostype = "posix"
elif osname == 'windows':
        arch = osname
        ostype = "windows"
elif osname == 'darwin':
        arch = osname
        ostype = "posix"
elif osname == 'aix':
        arch = "aix"
        ostype = "posix"

# 3rd party software required for the build
CP = 'CherryPy'
CPIDIR = 'cherrypy'
CPVER = '3.1.2'
CPARC = '%s-%s.tar.gz' % (CP, CPVER)
CPDIR = '%s-%s' % (CP, CPVER)
CPURL = 'http://download.cherrypy.org/cherrypy/%s/%s' % (CPVER, CPARC)
CPHASH = 'a94aedfd0e675858dbcc32dd250c23d285ee9b88'

PO = 'pyOpenSSL'
POIDIR = 'OpenSSL'
POVER = '0.7'
POARC = '%s-%s.tar.gz' % (PO, POVER)
PODIR = '%s-%s' % (PO, POVER)
POURL = 'http://downloads.sourceforge.net/pyopenssl/%s' % (POARC)
POHASH = 'bd072fef8eb36241852d25a9161282a051f0a63e'

COV = 'coveragepy'
COVIDIR = 'coverage'
COVVER = '3.2b2'
COVARC = '%s-%s.tar.gz' % (COVIDIR, COVVER)
COVDIR = '%s-%s' % (COVIDIR, COVVER)
COVURL = 'http://pypi.python.org/packages/source/c/coverage/%s' % COVARC
# No hash, since we always fetch the latest
COVHASH = '4710d033b8c6de1efaa562243e5b29e0a31fb8b9'

LDTP = 'ldtp'
LDTPIDIR = 'ldtp'
LDTPVER = '1.7.1'
LDTPMINORVER = '1.7.x'
LDTPMAJORVER = '1.x'
LDTPARC = '%s-%s.tar.gz' % (LDTP, LDTPVER)
LDTPDIR = '%s-%s' % (LDTP, LDTPVER)
LDTPURL = 'http://download.freedesktop.org/ldtp/%s/%s/%s' % \
    (LDTPMAJORVER, LDTPMINORVER, LDTPARC)
LDTPHASH = 'd31213d2b1449a0dadcace723b9ff7041169f7ce'

MAKO = 'Mako'
MAKOIDIR = 'mako'
MAKOVER = '0.2.2'
MAKOARC = '%s-%s.tar.gz' % (MAKO, MAKOVER)
MAKODIR = '%s-%s' % (MAKO, MAKOVER)
MAKOURL = 'http://www.makotemplates.org/downloads/%s' % (MAKOARC)
MAKOHASH = '85c04ab3a6a26a1cab47067449712d15a8b29790'

PLY = 'ply'
PLYIDIR = 'ply'
PLYVER = '3.1'
PLYARC = '%s-%s.tar.gz' % (PLY, PLYVER)
PLYDIR = '%s-%s' % (PLY, PLYVER)
PLYURL = 'http://www.dabeaz.com/ply/%s' % (PLYARC)
PLYHASH = '38efe9e03bc39d40ee73fa566eb9c1975f1a8003'

PBJ = 'pybonjour'
PBJIDIR = 'pybonjour'
PBJVER = '1.1.1'
PBJARC = '%s-%s.tar.gz' % (PBJ, PBJVER)
PBJDIR = '%s-%s' % (PBJ, PBJVER)
PBJURL = 'http://pybonjour.googlecode.com/files/%s' % (PBJARC)
PBJHASH = '92cabd14e04c5f62ce067c47c2057ee3d424d29b'

PC = 'pycurl'
PCIDIR = 'curl'
PCVER = '7.19.0'
PCARC = '%s-%s.tar.gz' % (PC, PCVER)
PCDIR = '%s-%s' % (PC, PCVER)
PCURL = 'http://pycurl.sourceforge.net/download/%s' % PCARC
PCHASH = '3fb59eca1461331bb9e9e8d6fe3b23eda961a416'
PCENVIRON = {}
if osname in ("sunos", "linux", "darwin"):
        PCENVIRON = {'CFLAGS': '-O3'}

M2C = 'M2Crypto'
M2CIDIR = 'm2crypto'
M2CVER = '0.20.2'
M2CARC = '%s-%s.tar.gz' % (M2C, M2CVER)
M2CDIR = '%s-%s' % (M2C, M2CVER)
M2CURL = 'http://pypi.python.org/packages/source/M/M2Crypto/%s' % (M2CARC)
M2CHASH = '6e85d7035971c353db74a497fca0ec2eaea4dea0'

pwd = os.path.normpath(sys.path[0])

#
# Unbuffer stdout and stderr.  This helps to ensure that subprocess output
# is properly interleaved with output from this program.
#
sys.stdout = os.fdopen(sys.stdout.fileno(), "w", 0)
sys.stderr = os.fdopen(sys.stderr.fileno(), "w", 0)

dist_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "dist_" + arch))
build_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "build_" + arch))
if "ROOT" in os.environ and os.environ["ROOT"] != "":
        root_dir = os.environ["ROOT"]
else:
        root_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "root_" + arch))
pkgs_dir = os.path.normpath(os.path.join(pwd, os.pardir, "packages", arch))
extern_dir = os.path.normpath(os.path.join(pwd, "extern"))

py_install_dir = 'usr/lib/python2.6/vendor-packages'

scripts_dir = 'usr/bin'
lib_dir = 'usr/lib'
svc_method_dir = 'lib/svc/method'

man1_dir = 'usr/share/man/cat1'
man1m_dir = 'usr/share/man/cat1m'
man5_dir = 'usr/share/man/cat5'
resource_dir = 'usr/share/lib/pkg'
smf_dir = 'var/svc/manifest/application'
zones_dir = 'etc/zones'
etcbrand_dir = 'etc/brand/ipkg'
brand_dir = 'usr/lib/brand/ipkg'
execattrd_dir = 'etc/security/exec_attr.d'
authattrd_dir = 'etc/security/auth_attr.d'

# A list of source, destination tuples of modules which should be hardlinked
# together if the os supports it and otherwise copied.
hardlink_modules = [
    ("%s/pkg/flavor/depthlimitedmf24" % py_install_dir,
    "%s/pkg/flavor/depthlimitedmf25" % py_install_dir)
]

scripts_sunos = {
        scripts_dir: [
                ['client.py', 'pkg'],
                ['pkgdep.py', 'pkgdepend'],
                ['pkgrepo.py', 'pkgrepo'],
                ['util/publish/pkgdiff.py', 'pkgdiff'],
                ['util/publish/pkgfmt.py', 'pkgfmt'],
                ['util/publish/pkglint.py', 'pkglint'],
                ['util/publish/pkgmogrify.py', 'pkgmogrify'],
                ['publish.py', 'pkgsend'],
                ['pull.py', 'pkgrecv'],
                ['sign.py', 'pkgsign'],
                ['packagemanager.py', 'packagemanager'],
                ['updatemanager.py', 'pm-updatemanager'],
                ],
        lib_dir: [
                ['depot.py', 'pkg.depotd'],
                ['checkforupdates.py', 'pm-checkforupdates'],
                ['updatemanagernotifier.py', 'updatemanagernotifier'],
                ['launch.py', 'pm-launch'],
                ],
        svc_method_dir: [
                ['svc/svc-pkg-depot', 'svc-pkg-depot'],
                ['svc/svc-pkg-mdns', 'svc-pkg-mdns'],
                ],
        }

scripts_windows = {
        scripts_dir: [
                ['client.py', 'client.py'],
                ['pkgrepo.py', 'pkgrepo.py'],
                ['publish.py', 'publish.py'],
                ['pull.py', 'pull.py'],
                ['scripts/pkg.bat', 'pkg.bat'],
                ['scripts/pkgsend.bat', 'pkgsend.bat'],
                ['scripts/pkgrecv.bat', 'pkgrecv.bat'],
                ],
        lib_dir: [
                ['depot.py', 'depot.py'],
                ['scripts/pkg.depotd.bat', 'pkg.depotd.bat'],
                ],
        }

scripts_other_unix = {
        scripts_dir: [
                ['client.py', 'client.py'],
                ['pkgdep.py', 'pkgdep'],
                ['util/publish/pkgdiff.py', 'pkgdiff'],
                ['util/publish/pkgfmt.py', 'pkgfmt'],
                ['util/publish/pkgmogrify.py', 'pkgmogrify'],
                ['pull.py', 'pull.py'],
                ['publish.py', 'publish.py'],
                ['scripts/pkg.sh', 'pkg'],
                ['scripts/pkgsend.sh', 'pkgsend'],
                ['scripts/pkgrecv.sh', 'pkgrecv'],
                ],
        lib_dir: [
                ['depot.py', 'depot.py'],
                ['scripts/pkg.depotd.sh', 'pkg.depotd'],
                ],
        }

# indexed by 'osname'
scripts = {
        "sunos": scripts_sunos,
        "linux": scripts_other_unix,
        "windows": scripts_windows,
        "darwin": scripts_other_unix,
        "aix" : scripts_other_unix,
        "unknown": scripts_sunos,
        }

man1_files = [
        'man/packagemanager.1',
        'man/pkg.1',
        'man/pkgdepend.1',
        'man/pkgdiff.1',
        'man/pkgfmt.1',
        'man/pkglint.1',
        'man/pkgmogrify.1',
        'man/pkgsend.1',
        'man/pkgsign.1',
        'man/pkgrecv.1',
        'man/pkgrepo.1',
        'man/pm-updatemanager.1',
        ]
man1m_files = [
        'man/pkg.depotd.1m'
        ]
man5_files = [
        'man/pkg.5'
        ]
packages = [
        'pkg',
        'pkg.actions',
        'pkg.bundle',
        'pkg.client',
        'pkg.client.transport',
        'pkg.file_layout',
        'pkg.flavor',
        'pkg.lint',
        'pkg.portable',
        'pkg.publish',
        'pkg.server'
        ]

web_files = []
for entry in os.walk("web"):
        web_dir, dirs, files = entry
        if not files:
                continue
        web_files.append((os.path.join(resource_dir, web_dir), [
            os.path.join(web_dir, f) for f in files
            if f != "Makefile"
            ]))

zones_files = [
        'brand/SUNWipkg.xml',
        ]
brand_files = [
        'brand/pkgcreatezone',
        'brand/attach',
        'brand/clone',
        'brand/detach',
        'brand/prestate',
        'brand/poststate',
        'brand/uninstall',
        'brand/common.ksh',
        ]
etcbrand_files = [
        'brand/pkgrm.conf',
        'brand/smf_disable.conf',
        ]
smf_files = [
        'svc/pkg-mdns.xml',
        'svc/pkg-server.xml',
        'svc/pkg-update.xml',
        ]
resource_files = [
        'util/pkglintrc',
        ]
execattrd_files = ['util/misc/exec_attr.d/SUNWipkg']
authattrd_files = ['util/misc/auth_attr.d/SUNWipkg']
pspawn_srcs = [
        'modules/pspawn.c'
        ]
elf_srcs = [
        'modules/elf.c',
        'modules/elfextract.c',
        'modules/liblist.c',
        ]
arch_srcs = [
        'modules/arch.c'
        ]
_actions_srcs = [
        'modules/actions/_actions.c'
        ]
solver_srcs = [
        'modules/solver/solver.c', 
        'modules/solver/py_solver.c'
        ]
solver_link_args = ["-lm", "-lc"]
if osname == 'sunos':
        solver_link_args = ["-ztext"] + solver_link_args

include_dirs = [ 'modules' ]
lint_flags = [ '-u', '-axms', '-erroff=E_NAME_DEF_NOT_USED2' ]

# Runs lint on the extension module source code
class lint_func(Command):
        description = "Runs various lint tools over IPS extension source code"
        user_options = []

        def initialize_options(self):
                pass

        def finalize_options(self):
                pass

        # Make string shell-friendly
        @staticmethod
        def escape(astring):
                return astring.replace(' ', '\\ ')

        def run(self):
                # assumes lint is on the $PATH
                if osname == 'sunos' or osname == "linux":
                        archcmd = ['lint'] + lint_flags + ['-D_FILE_OFFSET_BITS=64'] + \
                            ["%s%s" % ("-I", k) for k in include_dirs] + \
                            ['-I' + self.escape(get_python_inc())] + \
                            arch_srcs
                        elfcmd = ['lint'] + lint_flags + \
                            ["%s%s" % ("-I", k) for k in include_dirs] + \
                            ['-I' + self.escape(get_python_inc())] + \
                            ["%s%s" % ("-l", k) for k in elf_libraries] + \
                            elf_srcs
                        _actionscmd = ['lint'] + lint_flags + \
                            ["%s%s" % ("-I", k) for k in include_dirs] + \
                            ['-I' + self.escape(get_python_inc())] + \
                            _actions_srcs
                        pspawncmd = ['lint'] + lint_flags + ['-D_FILE_OFFSET_BITS=64'] + \
                            ["%s%s" % ("-I", k) for k in include_dirs] + \
                            ['-I' + self.escape(get_python_inc())] + \
                            pspawn_srcs

                        print(" ".join(archcmd))
                        os.system(" ".join(archcmd))
                        print(" ".join(elfcmd))
                        os.system(" ".join(elfcmd))
                        print(" ".join(_actionscmd))
                        os.system(" ".join(_actionscmd))
                        print(" ".join(pspawncmd))
                        os.system(" ".join(pspawncmd))

                        proto = os.path.join(root_dir, py_install_dir)
                        sys.path.insert(0, proto)

                        # Insert tests directory onto sys.path so any custom checkers
                        # can be found.
                        sys.path.insert(0, os.path.join(pwd, 'tests'))
                        print(sys.path)

                # assumes pylint is accessible on the sys.path
                from pylint import lint
                scriptlist = [ 'setup.py' ]
                for d, m in scripts_sunos.items():
                        for a in m:
                                # specify the filenames of the scripts, in addition
                                # to the package names themselves
                                scriptlist.append(os.path.join(root_dir, d, a[1]))

                # For some reason, the load-plugins option, when used in the
                # rcfile, does not work, so we put it here instead, to load
                # our custom checkers.
                lint.Run(['--load-plugins=multiplatform', '--rcfile',
                          os.path.join(pwd, 'tests', 'pylintrc')] +
                          scriptlist + packages)

class install_func(_install):
        def initialize_options(self):
                _install.initialize_options(self)

                # PRIVATE_BUILD set in the environment tells us to put the build
                # directory into the .pyc files, rather than the final
                # installation directory.
                private_build = os.getenv("PRIVATE_BUILD", None)

                if private_build is None:
                        self.install_lib = py_install_dir
                        self.install_data = os.path.sep
                        self.root = root_dir
                else:
                        self.install_lib = os.path.join(root_dir, py_install_dir)
                        self.install_data = root_dir

                # This is used when installing scripts, below, but it isn't a
                # standard distutils variable.
                self.root_dir = root_dir

        def run(self):
                """
                At the end of the install function, we need to rename some files
                because distutils provides no way to rename files as they are
                placed in their install locations.
                Also, make sure that cherrypy and other external dependencies
                are installed.
                """
                for f in man1_files + man1m_files + man5_files:
                        file_util.copy_file(f + ".txt", f, update=1)

                _install.run(self)

                for o_src, o_dest in hardlink_modules:
                        for e in [".py", ".pyc"]:
                                src = util.change_root(self.root_dir, o_src + e)
                                dest = util.change_root(
                                    self.root_dir, o_dest + e)
                                if ostype == "posix":
                                        if os.path.exists(dest) and \
                                            os.stat(src)[stat.ST_INO] != \
                                            os.stat(dest)[stat.ST_INO]:
                                                os.remove(dest)
                                        file_util.copy_file(src, dest,
                                            link="hard", update=1)
                                else:
                                        file_util.copy_file(src, dest, update=1)

                for d, files in scripts[osname].iteritems():
                        for (srcname, dstname) in files:
                                dst_dir = util.change_root(self.root_dir, d)
                                dst_path = util.change_root(self.root_dir,
                                       os.path.join(d, dstname))
                                dir_util.mkpath(dst_dir, verbose = True)
                                file_util.copy_file(srcname, dst_path, update = True)
                                # make scripts executable
                                os.chmod(dst_path,
                                    os.stat(dst_path).st_mode
                                    | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

                prep_sw(CP, CPARC, CPDIR, CPURL, CPHASH)
                install_sw(CP, CPDIR, CPIDIR)
		if osname == "sunos" and platform.uname()[2] == "5.11":
                        prep_sw(LDTP, LDTPARC, LDTPDIR, LDTPURL,
                            LDTPHASH)
                        saveenv = os.environ.copy()
                        os.environ["LDFLAGS"] = os.environ.get("LDFLAGS", "") + \
                            " -lsocket -lnsl"
                        install_ldtp(LDTP, LDTPDIR, LDTPIDIR)
                        os.environ = saveenv

		if "BUILD_PYOPENSSL" in os.environ and \
                    os.environ["BUILD_PYOPENSSL"] != "":
                        #
                        # Include /usr/sfw/lib in the build environment
                        # to ensure that this builds and runs on older
                        # nevada builds, before openssl moved out of /usr/sfw.
                        #
                        saveenv = os.environ.copy()
                        if osname == "sunos":
                                os.environ["CFLAGS"] = "-I/usr/sfw/include " + \
                                    os.environ.get("CFLAGS", "")
                                os.environ["LDFLAGS"] = \
                                    "-L/usr/sfw/lib -R/usr/sfw/lib " + \
                                    os.environ.get("LDFLAGS", "")
                        prep_sw(PO, POARC, PODIR, POURL, POHASH)
                        install_sw(PO, PODIR, POIDIR)
                        os.environ = saveenv
                prep_sw(M2C, M2CARC, M2CDIR, M2CURL, M2CHASH)
                install_sw(M2C, M2CDIR, M2CIDIR)
                prep_sw(MAKO, MAKOARC, MAKODIR, MAKOURL, MAKOHASH)
                install_sw(MAKO, MAKODIR, MAKOIDIR)
                prep_sw(PLY, PLYARC, PLYDIR, PLYURL, PLYHASH)
                install_sw(PLY, PLYDIR, PLYIDIR)
                prep_sw(PC, PCARC, PCDIR, PCURL, PCHASH)
                install_sw(PC, PCDIR, PCIDIR, extra_env=PCENVIRON)
                prep_sw(COV, COVARC, COVDIR, COVURL, COVHASH)
                install_sw(COV, COVDIR, COVIDIR)
                prep_sw(PBJ, PBJARC, PBJDIR, PBJURL, PBJHASH)
                install_sw(PBJ, PBJDIR, PBJIDIR)

                # Remove some bits that we're not going to package, but be sure
                # not to complain if we try to remove them twice.
                def onerror(func, path, exc_info):
                        if exc_info[1].errno != errno.ENOENT:
                                raise

                for dir in ("cherrypy/scaffold", "cherrypy/test",
                    "cherrypy/tutorial"):
                        shutil.rmtree(os.path.join(root_dir, py_install_dir, dir),
                            onerror=onerror)
                try:
                        os.remove(os.path.join(root_dir, "usr/bin/mako-render"))
                except EnvironmentError, e:
                        if e.errno != errno.ENOENT:
                                raise

def hash_sw(swname, swarc, swhash):
        if swhash == None:
                return True

        print "checksumming %s" % swname
        hash = hashlib.sha1()
        f = open(swarc, "rb")
        while True:
                data = f.read(65536)
                if data == "":
                        break
                hash.update(data)
        f.close()

        if hash.hexdigest() == swhash:
                return True
        else:
                print >> sys.stderr, "bad checksum! %s != %s" % \
                    (swhash, hash.hexdigest())
                return False

def prep_sw(swname, swarc, swdir, swurl, swhash):
        swarc = os.path.join(extern_dir, swarc)
        swdir = os.path.join(extern_dir, swdir)
        if not os.path.exists(extern_dir):
                os.mkdir(extern_dir)

        if not os.path.exists(swarc):
                print "downloading %s" % swname
                try:
                        fname, hdr = urllib.urlretrieve(swurl, swarc)
                except IOError:
                        pass
                if not os.path.exists(swarc) or \
                    (hdr.gettype() != "application/x-gzip" and
                     hdr.gettype() != "application/x-tar"):
                        print >> sys.stderr, "Unable to retrieve %s.\n" \
                            "Please retrieve the file " \
                            "and place it at: %s\n" % (swurl, swarc)
                        # remove a partial download or error message from proxy
                        remove_sw(swname)
                        sys.exit(1)
        if not os.path.exists(swdir):
                if not hash_sw(swname, swarc, swhash):
                        sys.exit(1)

                print "unpacking %s" % swname
                tar = tarfile.open(swarc)
                # extractall doesn't exist until python 2.5
                for m in tar.getmembers():
                        tar.extract(m, extern_dir)
                tar.close()

        # If there are patches, apply them now.
        patchdir = os.path.join("patch", swname)
        already_patched = os.path.join(swdir, ".patched")
        if os.path.exists(patchdir) and not os.path.exists(already_patched):
                patches = os.listdir(patchdir)
                for p in patches:
                        patchpath = os.path.join(os.path.pardir,
                            os.path.pardir, patchdir, p)
                        print "Applying %s to %s" % (p, swname)
                        args = ["patch", "-d", swdir, "-i", patchpath, "-p0"]
                        if osname == "windows":
                                args.append("--binary")
                        ret = subprocess.Popen(args).wait()
                        if ret != 0:
                                print >> sys.stderr, \
                                    "patch failed and returned %d." % ret
                                print >> sys.stderr, \
                                    "Command was: %s" % " ".join(args)
                                sys.exit(1)
                file(already_patched, "w").close()

def install_ldtp(swname, swdir, swidir):
        swdir = os.path.join(extern_dir, swdir)
        swinst_file = os.path.join(root_dir, py_install_dir, swidir + ".py")
        if not os.path.exists(swinst_file):
                print "installing %s" % swname
                args_config = ['./configure',
                    '--prefix=/usr',
                    '--bindir=/usr/bin',
                    'PYTHONPATH=""',
                       ]
                args_make_install = ['make', 'install', 
                    'DESTDIR=%s' % root_dir
                       ]
                run_cmd(args_config, swdir)
                run_cmd(args_make_install, swdir)

def install_sw(swname, swdir, swidir, extra_env=None):
        swdir = os.path.join(extern_dir, swdir)
        swinst_dir = os.path.join(root_dir, py_install_dir, swidir)
        inst_env = os.environ.copy()
        if extra_env:
                inst_env.update(extra_env)

        if not os.path.exists(swinst_dir):
                print "installing %s" % swname
                args = ['python2.6', 'setup.py', 'install',
                    '--root=%s' % root_dir,
                    '--install-lib=%s' % py_install_dir,
                    '--install-data=%s' % py_install_dir]
                run_cmd(args, swdir, env=inst_env)

def run_cmd(args, swdir, env=None):
                if env is None:
                        env = os.environ
                ret = subprocess.Popen(args, cwd=swdir, env=env).wait()
                if ret != 0:
                        print >> sys.stderr, \
                            "install failed and returned %d." % ret
                        print >> sys.stderr, \
                            "Command was: %s" % " ".join(args)
                        sys.exit(1)

def remove_sw(swname):
        print("deleting %s" % swname)
        for file in os.listdir(extern_dir):
                if fnmatch.fnmatch(file, "%s*" % swname):
                        fpath = os.path.join(extern_dir, file)
                        if os.path.isfile(fpath):
                                os.unlink(fpath)
                        else:
                                shutil.rmtree(fpath, True)

class build_func(_build):
        def initialize_options(self):
                _build.initialize_options(self)
                self.build_base = build_dir

def get_hg_version():
        try:
                p = subprocess.Popen(['hg', 'id', '-i'], stdout = subprocess.PIPE)
                return p.communicate()[0].strip()
        except OSError:
                print >> sys.stderr, "ERROR: unable to obtain mercurial version"
                return "unknown"

def syntax_check(filename):
        """ Run python's compiler over the file, and discard the results.
            Arrange to generate an exception if the file does not compile.
            This is needed because distutil's own use of pycompile (in the
            distutils.utils module) is broken, and doesn't stop on error. """
        try:
                py_compile.compile(filename, os.devnull, doraise=True)
        except py_compile.PyCompileError, e:
                raise DistutilsError("%s: failed syntax check: %s" %
                    (filename, e))


class build_py_func(_build_py):
        # override the build_module method to do VERSION substitution on pkg/__init__.py
        def build_module (self, module, module_file, package):

                if module == "__init__" and package == "pkg":
                        versionre = '(?m)^VERSION[^"]*"([^"]*)"'
                        # Grab the previously-built version out of the build
                        # tree.
                        try:
                                ocontent = \
                                    file(self.get_module_outfile(self.build_lib,
                                        [package], module)).read()
                                ov = re.search(versionre, ocontent).group(1)
                        except IOError:
                                ov = None
                        v = get_hg_version()
                        vstr = 'VERSION = "%s"' % v
                        # If the versions haven't changed, there's no need to
                        # recompile.
                        if v == ov:
                                return

                        mcontent = file(module_file).read()
                        mcontent = re.sub(versionre, vstr, mcontent)
                        tmpfd, tmp_file = tempfile.mkstemp()
                        os.write(tmpfd, mcontent)
                        os.close(tmpfd)
                        print "doing version substitution: ", v
                        rv = _build_py.build_module(self, module, tmp_file, package)
                        os.unlink(tmp_file)
                        return rv

                # Will raise a DistutilsError on failure.
                syntax_check(module_file)

                return _build_py.build_module(self, module, module_file, package)

class clean_func(_clean):
        def initialize_options(self):
                _clean.initialize_options(self)
                self.build_base = build_dir

class clobber_func(Command):
        user_options = []
        description = "Deletes any and all files created by setup"

        def initialize_options(self):
                pass
        def finalize_options(self):
                pass
        def run(self):
                # nuke everything
                print("deleting " + dist_dir)
                shutil.rmtree(dist_dir, True)
                print("deleting " + build_dir)
                shutil.rmtree(build_dir, True)
                print("deleting " + root_dir)
                shutil.rmtree(root_dir, True)
                print("deleting " + pkgs_dir)
                shutil.rmtree(pkgs_dir, True)
                print("deleting " + extern_dir)
                shutil.rmtree(extern_dir, True)

class test_func(Command):
        # NOTE: these options need to be in sync with tests/run.py and the
        # list of options stored in initialize_options below. The first entry
        # in each tuple must be the exact name of a member variable.
        user_options = [
            ("archivedir=", 'a', "archive failed tests <dir>"),
            ("baselinefile=", 'b', "baseline file <file>"),
            ("coverage", "c", "collect code coverage data"),
            ("genbaseline", 'g', "generate test baseline"),
            ("only=", "o", "only <regex>"),
            ("parseable", 'p', "parseable output"),
            ("timing", "t", "timing file <file>"),
            ("verbosemode", 'v', "run tests in verbose mode"),
            ("stoponerr", 'x', "stop when a baseline mismatch occurs"),
            ("debugoutput", 'd', "emit debugging output"),
            ("showonexpectedfail", 'f',
                "show all failure info, even for expected fails"),
            ("startattest=", 's', "start at indicated test"),
        ]
        description = "Runs unit and functional tests"

        def initialize_options(self):
                self.only = ""
                self.baselinefile = ""
                self.verbosemode = 0
                self.parseable = 0
                self.genbaseline = 0
                self.timing = 0
                self.coverage = 0
                self.stoponerr = 0
                self.debugoutput = 0
                self.showonexpectedfail = 0
                self.startattest = ""
                self.archivedir = ""

        def finalize_options(self):
                pass

        def run(self):

                os.putenv('PYEXE', sys.executable)
                os.chdir(os.path.join(pwd, "tests"))

                # Reconstruct the cmdline and send that to run.py
                cmd = [sys.executable, "run.py"]
                args = ""
                if "test" in sys.argv:
                        args = sys.argv[sys.argv.index("test")+1:]
                        cmd.extend(args)
                subprocess.call(cmd)

class dist_func(_bdist):
        def initialize_options(self):
                _bdist.initialize_options(self)
                self.dist_dir = dist_dir


# These are set to real values based on the platform, down below
compile_args = None
if osname in ("sunos", "linux", "darwin"):
        compile_args = [ "-O3" ]
link_args = None
ext_modules = [
        Extension(
                'actions._actions',
                _actions_srcs,
                include_dirs = include_dirs,
                extra_compile_args = compile_args,
                extra_link_args = link_args
                ),
        Extension(
                'solver',
                solver_srcs,
                include_dirs = include_dirs + ["."],
                extra_compile_args = compile_args,
                extra_link_args = solver_link_args,
                define_macros = [('_FILE_OFFSET_BITS', '64')]
                ),
        ]
elf_libraries = None
data_files = web_files
cmdclasses = {
        'install': install_func,
        'build': build_func,
        'build_py': build_py_func,
        'bdist': dist_func,
        'lint': lint_func,
        'clean': clean_func,
        'clobber': clobber_func,
        'test': test_func,
        }

# all builds of IPS should have manpages
data_files += [
        (man1_dir, man1_files),
        (man1m_dir, man1m_files),
        (man5_dir, man5_files),
        (resource_dir, resource_files),
        ]

if osname == 'sunos':
        # Solaris-specific extensions are added here
        data_files += [
                (zones_dir, zones_files),
                (brand_dir, brand_files),
                (etcbrand_dir, etcbrand_files),
                (smf_dir, smf_files),
                (execattrd_dir, execattrd_files),
                (authattrd_dir, authattrd_files),
                ]

if osname == 'sunos' or osname == "linux":
        # Unix platforms which the elf extension has been ported to
        # are specified here, so they are built automatically
        elf_libraries = ['elf']
        ext_modules += [
                Extension(
                        'elf',
                        elf_srcs,
                        include_dirs = include_dirs,
                        libraries = elf_libraries,
                        extra_compile_args = compile_args,
                        extra_link_args = link_args
                        ),
                ]

        # Solaris has built-in md library and Solaris-specific arch extension
        # All others use OpenSSL and cross-platform arch module
        if osname == 'sunos':
            elf_libraries += [ 'md' ]
            ext_modules += [
                    Extension(
                            'arch',
                            arch_srcs,
                            include_dirs = include_dirs,
                            extra_compile_args = compile_args,
                            extra_link_args = link_args,
                            define_macros = [('_FILE_OFFSET_BITS', '64')]
                            ),
                    Extension(
                            'pspawn',
                            pspawn_srcs,
                            include_dirs = include_dirs,
                            extra_compile_args = compile_args,
                            extra_link_args = link_args,
                            define_macros = [('_FILE_OFFSET_BITS', '64')]
                            ),
                    ]
        else:
            elf_libraries += [ 'ssl' ]

setup(cmdclass = cmdclasses,
    name = 'pkg',
    version = '0.1',
    package_dir = {'pkg':'modules'},
    packages = packages,
    data_files = data_files,
    ext_package = 'pkg',
    ext_modules = ext_modules,
    )
