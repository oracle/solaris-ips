#!/usr/bin/python2.4
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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

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

# 3rd party software required for the build
CP = 'CherryPy'
CPIDIR = 'cherrypy'
CPVER = '3.1.0'
CPARC = '%s-%s.tar.gz' % (CP, CPVER)
CPDIR = '%s-%s' % (CP, CPVER)
CPURL = 'http://download.cherrypy.org/cherrypy/%s/%s' % (CPVER, CPARC)

PO = 'pyOpenSSL'
POIDIR = 'OpenSSL'
POVER = '0.7'
POARC = '%s-%s.tar.gz' % (PO, POVER)
PODIR = '%s-%s' % (PO, POVER)
POURL = 'http://downloads.sourceforge.net/pyopenssl/%s' % (POARC)

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

pwd = os.path.normpath(sys.path[0])

#
# Unbuffer stdout and stderr.  This helps to ensure that subprocess output
# is properly interleaved with output from this program.
#
sys.stdout = os.fdopen(sys.stdout.fileno(), "w", 0)
sys.stderr = os.fdopen(sys.stderr.fileno(), "w", 0)

dist_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "dist_" + arch))
build_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "build_" + arch))
root_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "root_" + arch))
pkgs_dir = os.path.normpath(os.path.join(pwd, os.pardir, "packages", arch))

py_install_dir = 'usr/lib/python2.4/vendor-packages'

scripts_dir = 'usr/bin'
lib_dir = 'usr/lib'

man1_dir = 'usr/share/man/cat1'
man1m_dir = 'usr/share/man/cat1m'
man5_dir = 'usr/share/man/cat5'
resource_dir = 'usr/share/lib/pkg'
smf_dir = 'var/svc/manifest/application'
zones_dir = 'etc/zones'
brand_dir = 'usr/lib/brand/ipkg'

scripts_sunos = {
        scripts_dir: [
                ['client.py', 'pkg'],
                ['publish.py', 'pkgsend'],
                ['pull.py', 'pkgrecv'],
                ['packagemanager.py', 'packagemanager'],
                ['updatemanager.py', 'updatemanager'],
                ],
        lib_dir: [
                ['depot.py', 'pkg.depotd'],
                ['updatemanagernotifier.py', 'updatemanagernotifier'],
                ],
        }
            
scripts_windows = {
        scripts_dir: [
                ['client.py', 'client.py'],
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
        "unknown": scripts_sunos,
        }

man1_files = [
        'man/pkg.1',
        'man/pkgsend.1',
        'man/pkgrecv.1',
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
        'pkg.portable',
        'pkg.publish',
        'pkg.server'
        ]
web_files = [
        'web/pkg-block-icon.png',
        'web/pkg-block-logo.png',
        'web/pkg.css',
        'web/feed-icon-32x32.png',
        'web/robots.txt',
        ]
zones_files = [
        'brand/SUNWipkg.xml',
        ]
brand_files = [
        'brand/config.xml',
        'brand/platform.xml',
        'brand/pkgcreatezone',
        ]
smf_files = [
        'pkg-server.xml',
        'pkg-update.xml',
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

                        print(" ".join(archcmd))
                        os.system(" ".join(archcmd))
                        print(" ".join(elfcmd))
                        os.system(" ".join(elfcmd))
                        print(" ".join(_actionscmd))
                        os.system(" ".join(_actionscmd))

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

                # It's OK to have /'s here, python figures it out when writing files
                if private_build is None:
                        self.install_lib = py_install_dir
                        self.install_data = "/"
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
                Also, make sure that cherrypy is installed.
                """
                for f in man1_files + man1m_files + man5_files:
                        file_util.copy_file(f + ".txt", f, update=1)

                _install.run(self)

                for d, files in scripts[osname].iteritems():
                        for (srcname, dstname) in files:
                                dst_dir = util.change_root(self.root_dir, d)
                                dst_path = util.change_root(self.root_dir,
                                       os.path.join(d, dstname))
                                dir_util.mkpath(dst_dir, verbose = True)
                                file_util.copy_file(srcname, dst_path, update = True)
                                # make scripts executable
                                os.chmod(dst_path,
                                        os.stat(dst_path).st_mode | stat.S_IEXEC)

                install_sw(CP, CPVER, CPARC, CPDIR, CPURL, CPIDIR)
                install_sw(PO, POVER, POARC, PODIR, POURL, POIDIR)

def install_sw(swname, swver, swarc, swdir, swurl, swidir):
        if not os.path.exists(swarc):
                print "downloading %s" % swname
                try:
                        fname, hdr = urllib.urlretrieve(swurl, swarc)
                except IOError:
                        pass
                if not os.path.exists(swarc) or \
                    (hdr.gettype() != "application/x-gzip" and
                     hdr.gettype() != "application/x-tar"):
                        print "Unable to retrieve %s.\nPlease retrieve the file " \
                            "and place it at: %s\n" % (swurl, swarc)
                        # remove a partial download or error message from proxy
                        remove_sw(swname)
                        sys.exit(1)
        if not os.path.exists(swdir):
                print "unpacking %s" % swname
                tar = tarfile.open(swarc)
                # extractall doesn't exist until python 2.5
                for m in tar.getmembers():
                        tar.extract(m)
                tar.close()
        swinst_dir = os.path.join(root_dir, py_install_dir, swidir)
        if not os.path.exists(swinst_dir):
                print "installing %s" % swname
                subprocess.Popen(['python', 'setup.py', 'install',
                    '--root=%s' % root_dir,
                    '--install-lib=%s' % py_install_dir,
                    '--install-data=%s' % py_install_dir],
                    cwd = swdir).wait()

        
def remove_sw(swname):
        print("deleting %s" % swname)
        for file in os.listdir("."):
                if fnmatch.fnmatch(file, "%s*" % swname):
                        if os.path.isfile(file):
                                os.unlink(file)
                        else:
                                shutil.rmtree(file, True)
        
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
                remove_sw(CP)
                remove_sw(PO)

class test_func(Command):
        # NOTE: these options need to be in sync with tests/run.py
        user_options = [("verbosemode", 'v', "run tests in verbose mode"),
            ("genbaseline", 'g', "generate test baseline"),
            ("parseable", 'p', "parseable output"),
            ("baselinefile=", 'b', "baseline file <file>"),
            ("only=", "o", "only <regex>")]
        description = "Runs unit and functional tests"

        def initialize_options(self):
                self.only = ""
                self.baselinefile = ""
                self.verbosemode = 0
                self.parseable = 0
                self.genbaseline = 0
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
ext_modules = None
compile_args = None
link_args = None
elf_libraries = None
data_files = [ (resource_dir, web_files) ]
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
        ]

if osname == 'sunos':
        # Solaris-specific extensions are added here
        data_files += [
                (zones_dir, zones_files),
                (brand_dir, brand_files),
                (smf_dir, smf_files),
                ]

if osname == 'sunos' or osname == "linux":
        # Unix platforms which the elf extension has been ported to
        # are specified here, so they are built automatically
        elf_libraries = ['elf']
        ext_modules = [
                Extension(
                        'elf',
                        elf_srcs,
                        include_dirs = include_dirs,
                        libraries = elf_libraries,
                        extra_compile_args = compile_args,
                        extra_link_args = link_args
                        ),
                Extension(
                        'actions._actions',
                        _actions_srcs,
                        include_dirs = include_dirs,
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
                    ]
        else:
            elf_libraries += [ 'ssl' ]

setup(cmdclass = cmdclasses,
    name = 'ips',
    version = '1.0',
    package_dir = {'pkg':'modules'},
    packages = packages,
    data_files = data_files,
    ext_package = 'pkg',
    ext_modules = ext_modules,
    )
