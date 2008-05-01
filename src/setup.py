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

import os
import stat
import sys
import platform
import shutil
import code
import subprocess
import tempfile

from distutils.core import setup, Extension
from distutils.cmd import Command
from distutils.command.install import install as _install
from distutils.command.build import build as _build
from distutils.command.bdist import bdist as _bdist
from distutils.command.clean import clean as _clean

from distutils.sysconfig import get_python_inc
import distutils.file_util as file_util
import distutils.dir_util as dir_util
import distutils.util as util

pwd = os.path.normpath(sys.path[0])

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

dist_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "dist_" + arch))
build_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "build_" + arch))
root_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "root_" + arch))

py_install_dir = 'usr/lib/python2.4/vendor-packages'

scripts_dir = 'usr/bin'
lib_dir = 'usr/lib'

man1_dir = 'usr/share/man/cat1'
man1m_dir = 'usr/share/man/cat1m'
man5_dir='usr/share/man/cat5'
resource_dir = 'usr/share/lib/pkg'
smf_dir = 'var/svc/manifest/application'
zones_dir = 'etc/zones'
brand_dir = 'usr/lib/brand/ipkg'

scripts_sunos =   {
             scripts_dir : [   
                             ['client.py', 'pkg'],
                             ['publish.py', 'pkgsend'],
                            ],
             lib_dir : [
                        ['depot.py', 'pkg.depotd'],
                       ],
            }
            
scripts_windows = {
            scripts_dir : [
                             ['client.py', 'client.py'],
                             ['publish.py', 'publish.py'],
                             ['scripts/pkg.bat', 'pkg.bat'],
                             ['scripts/pkgsend.bat', 'pkgsend.bat'],
                          ],
            lib_dir : [
                        ['depot.py', 'depot.py'],
                        ['scripts/pkg.depotd.bat', 'pkg.depotd.bat'],
                      ],
            }

scripts_other_unix = {
            scripts_dir : [
                             ['client.py', 'client.py'],
                             ['publish.py', 'publish.py'],
                             ['scripts/pkg.sh', 'pkg'],
                             ['scripts/pkgsend.sh', 'pkgsend'],
                          ],
            lib_dir : [
                        ['depot.py', 'depot.py'],
                        ['scripts/pkg.depotd.sh', 'pkg.depotd'],
                      ],
            }

# indexed by 'osname'
scripts = { "sunos" : scripts_sunos,
            "linux" : scripts_other_unix,
            "windows" : scripts_windows,
            "darwin" : scripts_other_unix,
            "unknown" : scripts_sunos,
          }

man1_files=   [
              'man/pkg.1.txt',
              'man/pkgsend.1.txt',
              ]
man1m_files = [
              'man/pkg.depotd.1m.txt'
              ]
man5_files =    [
                'man/pkg.5.txt'
                ]
packages =  [
            'pkg',
            'pkg.actions',
            'pkg.bundle',
            'pkg.client',
            'pkg.portable',
            'pkg.publish',
            'pkg.server',
            ]

web_files =    [
                'web/pkg-block-icon.png',
                'web/pkg-block-logo.png',
                'web/pkg.css',
                'web/robots.txt',
                ]

zones_files =   [
                'brand/SUNWipkg.xml',
                ]

brand_files =   [
                'brand/config.xml',
                'brand/platform.xml',
                'brand/pkgcreatezone',
                ]
smf_files =     [
                'pkg-server.xml',
                ]

elf_srcs =  [
            'modules/elf.c',
            'modules/elfextract.c',
            'modules/liblist.c',
            ]

arch_srcs = [
            'modules/arch.c'
            ]

include_dirs = ['modules']   

lint_flags = [  '-u', '-axms', '-erroff=E_NAME_DEF_NOT_USED2' ]

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
        def escape(string):
            return string.replace(' ', '\\ ')

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

                        print(" ".join(archcmd))
                        os.system(" ".join(archcmd))
                        print(" ".join(elfcmd))
                        os.system(" ".join(elfcmd))

            	proto = "%s/%s" % (root_dir, py_install_dir)
            	sys.path.insert(0, proto)

            	# Insert tests directory onto sys.path so any custom checkers
            	# can be found.
            	sys.path.insert(0, os.path.join(pwd, 'tests'))
            	print(sys.path)

                # assumes pylint is accessible on the sys.path
                from pylint import lint
                scriptlist=[]
                for dir,map in scripts_sunos.items():
                    for arr in map:
                        # specify the filenames of the scripts, in addition
                        # to the package names themselves
                        scriptlist.append(os.path.join(root_dir, dir, arr[1]))

                # For some reason, the load-plugins option, when used in the
                # rcfile, does not work, so we put it here instead, to load
                # our custom checkers.
                lint.Run(['--load-plugins=multiplatform', '--rcfile',
                          os.path.join(pwd, 'tests', 'pylintrc')] + 
                          scriptlist + packages)

# Developer command to connect the local machine to the current
# repository's working copy's versions of the commands, modules, and supporting
# files.
class link_func(Command):
    user_options = []
    description = "Developer command to connect local machine to working " \
        "copy of files in local repository"

    def initialize_options(self):
        pass
    def finalize_options(self):
        pass

    def run(self):
        os.system('mkdir -p /usr/share/lib/pkg')        
        os.system('mkdir -p /usr/lib/brand/ipkg')        
        os.system('mkdir -p /usr/share/man/cat1')
        os.system('mkdir -p /usr/share/man/cat1m')
        os.system('mkdir -p /usr/share/man/cat5')

        os.system('ln -sf ' + pwd + '/client.py /usr/bin/pkg')
        os.system('ln -sf ' + pwd + '/publish.py /usr/bin/pkgsend')
        os.system('ln -sf ' + pwd + '/depot.py /usr/bin/pkg.depotd')
        os.system('ln -sf ' + pwd + '/modules ' + '/' + py_install_dir + '/pkg')
        os.system('ln -sf ' + pwd + \
            '/pkg-server.xml /var/svc/manifest/pkg-server.xml')
        os.system('ln -sf ' + pwd + \
            '/web/pkg-block-icon.png /usr/share/lib/pkg/pkg-block-icon.png')
        os.system('ln -sf ' + pwd + \
            '/web/pkg-block-logo.png /usr/share/lib/pkg/pkg-block-logo.png')
        os.system('ln -sf ' + pwd + \
            '/web/pkg.css /usr/share/lib/pkg/pkg.css')
        os.system('ln -sf ' + pwd + \
            '/brand/config.xml /usr/lib/brand/ipkg/config.xml')
        os.system('ln -sf ' + pwd + \
            '/brand/platform.xml /usr/lib/brand/ipkg/platform.xml')
        os.system('ln -sf ' + pwd + 
            '/brand/pkgcreatezone /usr/lib/brand/ipkg/pkgcreatezone')
        os.system('ln -sf ' + pwd + \
            '/brand/SUNWipkg.xml /etc/zones/SUNWipkg.xml')
        os.system('ln -sf ' + pwd + '/man/pkg.1.txt /usr/share/man/cat1/pkg.1')
        os.system('ln -sf ' + pwd + \
            '/man/pkgsend.1.txt /usr/share/man/cat1/pkgsend.1')
        os.system('ln -sf ' + pwd + \
            '/man/pkg.depotd.1m.txt /usr/share/man/cat1m/pkg.depotd.1m')
        os.system('ln -sf ' + pwd + '/man/pkg.5.txt /usr/share/man/man5/pkg.5')

class link_clean_func(Command):
        user_options = []
        description = "Cleans up links created by the \"link\" command"

        def initialize_options(self):
                pass
        def finalize_options(self):
                pass

        def run(self):

            os.system('rm -f /usr/bin/pkg')
            os.system('rm -f /usr/bin/pkgsend')
            os.system('rm -f /usr/lib/pkg.depotd')
            os.system('rm -f ' + '/' + py_install_dir + '/pkg')
            os.system('rm -f /var/svc/manifest/pkg-server.xml')
            os.system('rm -rf /usr/share/lib/pkg')
            os.system('rm -rf /usr/lib/brand/ipkg')
            os.system('rm -f /etc/zones/SUNWipkg.xml')
            os.system('rm -f /usr/share/man/cat1/pkg.1')
            os.system('rm -f /usr/share/man/cat1/pkgsend.1')
            os.system('rm -f /usr/share/man/cat1m/pkg.depotd.1m')
            os.system('rm -f /usr/share/man/man5/pkg.5')

class install_func(_install):
        def initialize_options(self):
            _install.initialize_options(self)
            # It's OK to have /'s here, python figures it out when writing files
            self.install_purelib = py_install_dir
            self.install_platlib = py_install_dir
            self.root = root_dir
            self.prefix = '.'

        # At the end of the install function, we need to rename some files
        # because distutils provides no way to rename files as they are placed
        # in their install locations
        def run(self):
            _install.run(self)
            if ostype == 'posix':
                    # only rename manpages if building for unix-derived OS
                    for (dir, files) in [(man1_dir, man1_files), (man1m_dir,
                        man1m_files), (man5_dir, man5_files)]:
                        for file in files:
                            src = util.change_root(self.root, os.path.join(dir,
                                os.path.basename(file)))
                            if src.endswith('.txt'):
                                dst = src[:-4]
                                file_util.copy_file(src, dst, update=True)

            for dir, files in scripts[osname].iteritems():
                    for (srcname, dstname) in files:
                        dst_dir = util.change_root(self.root, dir)
                        dst_path = util.change_root(self.root,
                                       os.path.join(dir, dstname))
                        dir_util.mkpath(dst_dir, verbose=True)
                        file_util.copy_file(srcname, dst_path, update=True)
                        # make scripts executable
                        os.chmod(dst_path, os.stat(dst_path).st_mode | stat.S_IEXEC)

class build_func(_build):
        def initialize_options(self):            
            _build.initialize_options(self)
            self.build_base = build_dir

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
                print("Deleting " + dist_dir)
                shutil.rmtree(dist_dir, True)
                print("Deleting " + build_dir)
                shutil.rmtree(build_dir, True)
                print("Deleting " + root_dir)
                shutil.rmtree(root_dir, True)

class test_func(Command):
        user_options = []
        description = "Runs unit and functional tests"

        def initialize_options(self):
                pass
        def finalize_options(self):
                pass
        def run(self):
                os.putenv('PYEXE', sys.executable)
                os.chdir(os.path.join(pwd, "tests"))
                testlogfd, testlogpath = tempfile.mkstemp(suffix = '.pkg-test.log')
                testlogfp = os.fdopen(testlogfd, "w")
                print "Logging to %s" % testlogpath

                subprocess.call([sys.executable, "api-complete.py"], stdout=testlogfp)

                if ostype == 'posix':
                    subprocess.call([sys.executable, "cli-complete.py"], stdout=testlogfp)
                if osname == 'sunos':
                    subprocess.call(["/bin/ksh", "memleaks.ksh"], stdout=testlogfp)
                testlogfp.close()

class dist_func(_bdist):
        def initialize_options(self):
            _bdist.initialize_options(self)            
            self.dist_dir = dist_dir


# These are set to real values based on the platform, down below
ext_modules = None
compile_args = None
link_args = None
elf_libraries = None
data_files = [
                (resource_dir, web_files),
             ] 
cmdclasses={
            'link' : link_func,
            'linkclean' : link_clean_func,
            'install' : install_func,
            'build' : build_func,
            'bdist' : dist_func,
            'lint' : lint_func,
            'clean' : clean_func,
            'clobber' : clobber_func,
            'test' : test_func,
           }

if ostype == 'posix':
    # all unix builds of IPS should have manpages
    data_files +=   [
                    (man1_dir, man1_files),
                    (man1m_dir, man1m_files),
                    (man5_dir, man5_files),
                    ]

if osname == 'sunos':
    # Solaris-specific extensions are added here
    data_files +=   [
                    (zones_dir, zones_files),
                    (brand_dir, brand_files),
                    (smf_dir, smf_files),
                    ]

if osname == 'sunos' or osname == "linux":
    # Unix platforms which the elf extension has been ported to
    # are specified here, so they are built automatically
    elf_libraries = ['elf']
    ext_modules=[
        Extension(
            'elf',
            elf_srcs,
            include_dirs=include_dirs,
            libraries=elf_libraries,
            extra_compile_args=compile_args,
            extra_link_args=link_args
        ),
    ]

    # Solaris has built-in md library and Solaris-specific arch extension
    # All others use OpenSSL and cross-platform arch module
    if osname == 'sunos':
        elf_libraries += ['md']
        ext_modules += [
                Extension(
                    'arch', 
                    arch_srcs,
                    include_dirs=include_dirs,
                    extra_compile_args=compile_args,
                    extra_link_args=link_args,
                    define_macros=[('_FILE_OFFSET_BITS', '64')]
                ),
        ]
    else:
        elf_libraries += ['ssl']

setup(cmdclass=cmdclasses,
      name='ips',
      version='1.0',
      package_dir= {'pkg':'modules'},
      packages=packages,
      data_files=data_files,
      ext_package='pkg',
      ext_modules=ext_modules,
     )
