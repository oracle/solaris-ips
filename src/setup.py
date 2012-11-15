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
# Copyright (c) 2008, 2012, Oracle and/or its affiliates. All rights reserved.
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
import time
import StringIO

from distutils.errors import DistutilsError, DistutilsFileError
from distutils.core import setup
from distutils.cmd import Command
from distutils.command.install import install as _install
from distutils.command.install_data import install_data as _install_data
from distutils.command.install_lib import install_lib as _install_lib
from distutils.command.build import build as _build
from distutils.command.build_ext import build_ext as _build_ext
from distutils.command.build_py import build_py as _build_py
from distutils.command.bdist import bdist as _bdist
from distutils.command.clean import clean as _clean
from distutils.dist import Distribution
from distutils import log

from distutils.sysconfig import get_python_inc
import distutils.dep_util as dep_util
import distutils.dir_util as dir_util
import distutils.file_util as file_util
import distutils.util as util
import distutils.ccompiler
from distutils.unixccompiler import UnixCCompiler

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

pwd = os.path.normpath(sys.path[0])

# the version of pylint that we must have in order to run the pylint checks.
req_pylint_version = "0.25.2"

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

man1_dir = 'usr/share/man/man1'
man1m_dir = 'usr/share/man/man1m'
man5_dir = 'usr/share/man/man5'
man1_ja_JP_dir = 'usr/share/man/ja_JP.UTF-8/man1'
man1m_ja_JP_dir = 'usr/share/man/ja_JP.UTF-8/man1m'
man5_ja_JP_dir = 'usr/share/man/ja_JP.UTF-8/man5'
man1_zh_CN_dir = 'usr/share/man/zh_CN.UTF-8/man1'
man1m_zh_CN_dir = 'usr/share/man/zh_CN.UTF-8/man1m'
man5_zh_CN_dir = 'usr/share/man/zh_CN.UTF-8/man5'

resource_dir = 'usr/share/lib/pkg'
transform_dir = 'usr/share/pkg/transforms'
smf_app_dir = 'lib/svc/manifest/application/pkg'
execattrd_dir = 'etc/security/exec_attr.d'
authattrd_dir = 'etc/security/auth_attr.d'
sysrepo_dir = 'etc/pkg/sysrepo'
sysrepo_logs_dir = 'var/log/pkg/sysrepo'
sysrepo_cache_dir = 'var/cache/pkg/sysrepo'
autostart_dir = 'etc/xdg/autostart'
desktop_dir = 'usr/share/applications'
gconf_dir = 'etc/gconf/schemas'
help_dir = 'usr/share/gnome/help/package-manager'
omf_dir = 'usr/share/omf/package-manager'
startpage_dir = 'usr/share/package-manager/data/startpagebase'
um_lib_dir = 'usr/lib/update-manager'
um_share_dir = 'usr/share/update-manager'
pm_share_dir = 'usr/share/package-manager'
locale_dir = 'usr/share/locale'


# A list of source, destination tuples of modules which should be hardlinked
# together if the os supports it and otherwise copied.
hardlink_modules = []

scripts_sunos = {
        scripts_dir: [
                ['client.py', 'pkg'],
                ['pkgdep.py', 'pkgdepend'],
                ['pkgrepo.py', 'pkgrepo'],
                ['util/publish/pkgdiff.py', 'pkgdiff'],
                ['util/publish/pkgfmt.py', 'pkgfmt'],
                ['util/publish/pkglint.py', 'pkglint'],
                ['util/publish/pkgmerge.py', 'pkgmerge'],
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
                ['sysrepo.py', 'pkg.sysrepo'],
                ],
        um_lib_dir: [
                ['um/update-refresh.sh', 'update-refresh.sh'],
        ],
        svc_method_dir: [
                ['svc/svc-pkg-depot', 'svc-pkg-depot'],
                ['svc/svc-pkg-mdns', 'svc-pkg-mdns'],
                ['svc/svc-pkg-sysrepo', 'svc-pkg-sysrepo'],
                ['um/pkg-update', 'pkg-update'],
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
        'man/pkgmerge.1',
        'man/pkgmogrify.1',
        'man/pkgsend.1',
        'man/pkgsign.1',
        'man/pkgrecv.1',
        'man/pkgrepo.1',
        'man/pm-updatemanager.1',
        ]
man1m_files = [
        'man/pkg.depotd.1m',
        'man/pkg.sysrepo.1m'
        ]
man5_files = [
        'man/pkg.5'
        ]

man1_ja_files = [
        'man/ja_JP/packagemanager.1',
        'man/ja_JP/pkg.1',
        'man/ja_JP/pkgdepend.1',
        'man/ja_JP/pkgdiff.1',
        'man/ja_JP/pkgfmt.1',
        'man/ja_JP/pkglint.1',
        'man/ja_JP/pkgmerge.1',
        'man/ja_JP/pkgmogrify.1',
        'man/ja_JP/pkgsend.1',
        'man/ja_JP/pkgsign.1',
        'man/ja_JP/pkgrecv.1',
        'man/ja_JP/pkgrepo.1',
        'man/ja_JP/pm-updatemanager.1',
        ]
man1m_ja_files = [
        'man/ja_JP/pkg.depotd.1m',
        'man/ja_JP/pkg.sysrepo.1m'
        ]
man5_ja_files = [
        'man/ja_JP/pkg.5'
        ]

man1_zh_CN_files = [
        'man/zh_CN/packagemanager.1',
        'man/zh_CN/pkg.1',
        'man/zh_CN/pkgdepend.1',
        'man/zh_CN/pkgdiff.1',
        'man/zh_CN/pkgfmt.1',
        'man/zh_CN/pkglint.1',
        'man/zh_CN/pkgmerge.1',
        'man/zh_CN/pkgmogrify.1',
        'man/zh_CN/pkgsend.1',
        'man/zh_CN/pkgsign.1',
        'man/zh_CN/pkgrecv.1',
        'man/zh_CN/pkgrepo.1',
        'man/zh_CN/pm-updatemanager.1',
        ]
man1m_zh_CN_files = [
        'man/zh_CN/pkg.depotd.1m',
        'man/zh_CN/pkg.sysrepo.1m'
        ]
man5_zh_CN_files = [
        'man/zh_CN/pkg.5'
        ]

packages = [
        'pkg',
        'pkg.actions',
        'pkg.bundle',
        'pkg.client',
        'pkg.client.linkedimage',
        'pkg.client.transport',
        'pkg.file_layout',
        'pkg.flavor',
        'pkg.gui',
        'pkg.lint',
        'pkg.portable',
        'pkg.publish',
        'pkg.server'
        ]

pylint_targets = [
        'pkg.altroot',
        'pkg.client.__init__',
        'pkg.client.api',
        'pkg.client.linkedimage',
        'pkg.client.pkgdefs',
        'pkg.client.pkgremote',
        'pkg.client.plandesc',
        'pkg.client.printengine',
        'pkg.client.progress',
        'pkg.misc',
        'pkg.pipeutils',
        'checkforupdates',
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
        # install same set of files in "en/" in "__LOCALE__/ as well" 
        # for localizable file package (regarding themes, install
        # theme "oracle.com" only)
        if os.path.basename(web_dir) == "en" and \
            os.path.dirname(web_dir) in ("web", "web/_themes/oracle.com"):
                web_files.append((os.path.join(resource_dir,
                    os.path.dirname(web_dir), "__LOCALE__"), [
                        os.path.join(web_dir, f) for f in files
                        if f != "Makefile"
                    ]))

smf_app_files = [
        'svc/pkg-mdns.xml',
        'svc/pkg-server.xml',
        'svc/pkg-update.xml',
        'svc/pkg-system-repository.xml',
        'svc/zoneproxy-client.xml',
        'svc/zoneproxyd.xml'
        ]
resource_files = [
        'util/opensolaris.org.sections',
        'util/pkglintrc',
        ]
transform_files = [
        'util/publish/transforms/developer',
        'util/publish/transforms/documentation',
        'util/publish/transforms/locale',
        'util/publish/transforms/smf-manifests'
        ]
sysrepo_files = [
        'util/apache2/sysrepo/sysrepo_p5p.py',
        'util/apache2/sysrepo/sysrepo_httpd.conf.mako',
        'util/apache2/sysrepo/sysrepo_publisher_response.mako',
        ]
sysrepo_log_stubs = [
        'util/apache2/sysrepo/logs/access_log',
        'util/apache2/sysrepo/logs/error_log',
        ]
execattrd_files = [
        'util/misc/exec_attr.d/package:pkg',
        'util/misc/exec_attr.d/package:pkg:package-manager'
]
authattrd_files = ['util/misc/auth_attr.d/package:pkg']
autostart_files = [
        'um/data/updatemanagernotifier.desktop',
]
desktop_files = [
        'gui/data/addmoresoftware.desktop',
        'gui/data/packagemanager.desktop',
        'um/data/updatemanager.desktop',
]
gconf_files = [
        'gui/data/packagemanager-preferences.schemas',
        'um/data/updatemanager-preferences.schemas',
]
intl_files = [
        'gui/data/addmoresoftware.desktop.in',
        'gui/data/packagemanager-info.xml.in',
        'gui/data/packagemanager-preferences.schemas.in',
        'gui/data/packagemanager.desktop.in',
        'um/data/updatemanager-preferences.schemas.in',
        'um/data/updatemanager.desktop.in',
        'um/data/updatemanagernotifier.desktop.in',
]
help_locales = \
    'C ar ca cs de es fr hu id it ja ko pl pt_BR ru sv zh_CN zh_HK zh_TW'.split()
help_files = {
        'C': ['gui/help/C/package-manager.xml'],
        'C/figures': [
            'gui/help/C/figures/%s.png' % n
            for n in 'pkgmgr-main startpage_new update_all_new webinstall'.split()
        ]
}
help_files.update(
        (locale, ['gui/help/%s/package-manager.xml' % locale])
        for locale in help_locales[1:]
)
# add package-manager-__LOCALE__.omf for localizable file package
omf_files = [
        'gui/help/package-manager-%s.omf' % locale
        for locale in help_locales + [ "__LOCALE__" ]
]
startpage_locales = \
    'C ar ca cs de es fr hu id it ja ko nl pt_BR ru sv zh_CN zh_HK zh_TW'.split()
startpage_files = {
        'C': [
            'gui/data/startpagebase/C/%s.png' % n
            for n in [
                'dialog-information', 'dialog-warning', 'hc_dialog-information',
                'hc_dialog-warning', 'hc_install', 'hc_opensolaris',
                'hci_dialog-information', 'hci_dialog-warning', 'hci_install',
                'hci_opensolaris', 'install', 'opensolaris'
            ]
        ] + ['gui/data/startpagebase/C/startpage.html']
}
startpage_files.update(
        (locale, ['gui/data/startpagebase/%s/startpage.html' % locale])
        for locale in startpage_locales[1:]
)
pkg_locales = \
    'ar ca cs de es fr he hu id it ja ko nl pl pt_BR ru sk sv zh_CN zh_HK zh_TW'.split()

syscallat_srcs = [
        'modules/syscallat.c'
        ]
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
_actcomm_srcs = [
        'modules/actions/_common.c'
        ]
_varcet_srcs = [
        'modules/_varcet.c'
        ]
solver_srcs = [
        'modules/solver/solver.c',
        'modules/solver/py_solver.c'
        ]
solver_link_args = ["-lm", "-lc"]
if osname == 'sunos':
        solver_link_args = ["-ztext"] + solver_link_args

# Runs lint on the extension module source code
class pylint_func(Command):
        description = "Runs pylint tools over IPS python source code"
        user_options = []

        def initialize_options(self):
                pass

        def finalize_options(self):
                pass

        # Make string shell-friendly
        @staticmethod
        def escape(astring):
                return astring.replace(' ', '\\ ')

        def run(self, quiet=False):

                def supported_pylint_ver(version):
                        """Compare the installed version against the version
                        we require to build with, returning False if the version
                        is too old. It's tempting to use pkg.version.Version
                        here, but since that's a build artifact, we'll do it
                        the long way."""
                        inst_pylint_ver = version.split(".")
                        req_pylint_ver = req_pylint_version.split(".")

                        # if the lists are of different lengths, we just
                        # compare with the precision we have.
                        vers_comp = zip(inst_pylint_ver, req_pylint_ver)
                        for inst, req in vers_comp:
                                try:
                                        if int(inst) < int(req):
                                                return False
                                except ValueError:
                                        # if we somehow get non-numeric version
                                        # components, we ignore them.
                                        continue
                        return True

                # it's fine to default to the required version - the build will
                # break if the installed version is incompatible and $PYLINT_VER
                # didn't get set, somehow.
                pylint_ver_str = os.environ.get("PYLINT_VER",
                    req_pylint_version)

                if os.environ.get("PKG_SKIP_PYLINT"):
                        log.warn("WARNING: skipping pylint checks: "
                            "$PKG_SKIP_PYLINT was set")
                        return
                elif not pylint_ver_str or \
                    not supported_pylint_ver(pylint_ver_str):
                        log.warn("WARNING: skipping pylint checks: the "
                            "installed version %s is older than version %s" %
                            (pylint_ver_str, req_pylint_version))
                        return

                proto = os.path.join(root_dir, py_install_dir)
                sys.path.insert(0, proto)

                # Insert tests directory onto sys.path so any custom checkers
                # can be found.
                sys.path.insert(0, os.path.join(pwd, 'tests'))
                # assumes pylint is accessible on the sys.path
                from pylint import lint

                #
                # For some reason, the load-plugins option, when used in the
                # rcfile, does not work, so we put it here instead, to load
                # our custom checkers.
                #
                # Unfortunately, pylint seems pretty fragile and will crash if
                # we try to run it over all the current pkg source.  Hence for
                # now we only run it over a subset of the source.  As source
                # files are made pylint clean they should be added to the
                # pylint_targets list.
                #
                args = ['--load-plugins=multiplatform']
                if quiet:
                        args += ['--reports=no']
                args += ['--rcfile', os.path.join(pwd, 'tests', 'pylintrc')]
                args += pylint_targets
                lint.Run(args)


class pylint_func_quiet(pylint_func):

        def run(self, quiet=False):
                pylint_func.run(self, quiet=True)


include_dirs = [ 'modules' ]
lint_flags = [ '-u', '-axms', '-erroff=E_NAME_DEF_NOT_USED2' ]

# Runs lint on the extension module source code
class clint_func(Command):
        description = "Runs lint tools over IPS C extension source code"
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
                if "LINT" in os.environ and os.environ["LINT"] != "":
                        lint = [os.environ["LINT"]]
                else:
                        lint = ['lint']
                if osname == 'sunos' or osname == "linux":
                        archcmd = lint + lint_flags + \
                            ['-D_FILE_OFFSET_BITS=64'] + \
                            ["%s%s" % ("-I", k) for k in include_dirs] + \
                            ['-I' + self.escape(get_python_inc())] + \
                            arch_srcs
                        elfcmd = lint + lint_flags + \
                            ["%s%s" % ("-I", k) for k in include_dirs] + \
                            ['-I' + self.escape(get_python_inc())] + \
                            ["%s%s" % ("-l", k) for k in elf_libraries] + \
                            elf_srcs
                        _actionscmd = lint + lint_flags + \
                            ["%s%s" % ("-I", k) for k in include_dirs] + \
                            ['-I' + self.escape(get_python_inc())] + \
                            _actions_srcs
                        _actcommcmd = lint + lint_flags + \
                            ["%s%s" % ("-I", k) for k in include_dirs] + \
                            ['-I' + self.escape(get_python_inc())] + \
                            _actcomm_srcs
                        _varcetcmd = lint + lint_flags + \
                            ["%s%s" % ("-I", k) for k in include_dirs] + \
                            ['-I' + self.escape(get_python_inc())] + \
                            _varcet_srcs
                        pspawncmd = lint + lint_flags + \
                            ['-D_FILE_OFFSET_BITS=64'] + \
                            ["%s%s" % ("-I", k) for k in include_dirs] + \
                            ['-I' + self.escape(get_python_inc())] + \
                            pspawn_srcs
                        syscallatcmd = lint + lint_flags + \
                            ['-D_FILE_OFFSET_BITS=64'] + \
                            ["%s%s" % ("-I", k) for k in include_dirs] + \
                            ['-I' + self.escape(get_python_inc())] + \
                            syscallat_srcs

                        print(" ".join(archcmd))
                        os.system(" ".join(archcmd))
                        print(" ".join(elfcmd))
                        os.system(" ".join(elfcmd))
                        print(" ".join(_actionscmd))
                        os.system(" ".join(_actionscmd))
                        print(" ".join(_actcommcmd))
                        os.system(" ".join(_actcommcmd))
                        print(" ".join(_varcetcmd))
                        os.system(" ".join(_varcetcmd))
                        print(" ".join(pspawncmd))
                        os.system(" ".join(pspawncmd))
                        print(" ".join(syscallatcmd))
                        os.system(" ".join(syscallatcmd))


# Runs both C and Python lint
class lint_func(Command):
        description = "Runs C and Python lint checkers"
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
                clint_func(Distribution()).run()
                pylint_func(Distribution()).run()

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
                """At the end of the install function, we need to rename some
                files because distutils provides no way to rename files as they
                are placed in their install locations.
                """

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
                                dir_util.mkpath(dst_dir, verbose=True)
                                file_util.copy_file(srcname, dst_path, update=True)
                                # make scripts executable
                                os.chmod(dst_path,
                                    os.stat(dst_path).st_mode
                                    | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

class install_lib_func(_install_lib):
        """Remove the target files prior to the standard install_lib procedure
        if the build_py module has determined that they've actually changed.
        This may be needed when a module's timestamp goes backwards in time, if
        a working-directory change is reverted, or an older changeset is checked
        out.
        """

        def install(self):
                build_py = self.get_finalized_command("build_py")
                prefix_len = len(self.build_dir) + 1
                for p in build_py.copied:
                        id_p = os.path.join(self.install_dir, p[prefix_len:])
                        rm_f(id_p)
                        if self.compile:
                                rm_f(id_p + "c")
                        if self.optimize > 0:
                                rm_f(id_p + "o")
                return _install_lib.install(self)

class install_data_func(_install_data):
        """Enhance the standard install_data subcommand to take not only a list
        of filenames, but a list of source and destination filename tuples, for
        the cases where a filename needs to be renamed between the two
        locations."""

        def run(self):
                self.mkpath(self.install_dir)
                for f in self.data_files:
                        dir, files = f
                        dir = util.convert_path(dir)
                        if not os.path.isabs(dir):
                                dir = os.path.join(self.install_dir, dir)
                        elif self.root:
                                dir = change_root(self.root, dir)
                        self.mkpath(dir)

                        if not files:
                                self.outfiles.append(dir)
                        else:
                                for file in files:
                                        if isinstance(file, basestring):
                                                infile = file
                                                outfile = os.path.join(dir,
                                                    os.path.basename(file))
                                        else:
                                                infile, outfile = file
                                        infile = util.convert_path(infile)
                                        outfile = util.convert_path(outfile)
                                        if os.path.sep not in outfile:
                                                outfile = os.path.join(dir,
                                                    outfile)
                                        self.copy_file(infile, outfile)
                                        self.outfiles.append(outfile)

                # Don't bother making this generic for the one symlink.
                src = "HighContrastInverse"
                dst = os.path.join(self.install_dir, pm_share_dir,
                    "icons/HighContrastLargePrintInverse")
                try:
                        targ = os.readlink(dst)
                except OSError, e:
                        if e.errno in (errno.ENOENT, errno.EINVAL):
                                targ = None
                        else:
                                raise

                if src != targ:
                        log.info("linking %s -> %s" % (src, dst))
                        rm_f(dst)
                        os.symlink(src, dst)

def run_cmd(args, swdir, updenv=None, ignerr=False, savestderr=None):
                if updenv:
                        # use temp environment modified with the given dict
                        env = os.environ.copy()
                        env.update(updenv)
                else:
                        # just use environment of this (parent) process as is
                        env = os.environ
                if ignerr:
                        # send stderr to devnull
                        stderr = open(os.devnull)
                elif savestderr:
                        stderr = savestderr
                else:
                        # just use stderr of this (parent) process
                        stderr = None
                ret = subprocess.Popen(args, cwd=swdir, env=env,
                    stderr=stderr).wait()
                if ret != 0:
                        if stderr:
                            stderr.close()
                        print >> sys.stderr, \
                            "install failed and returned %d." % ret
                        print >> sys.stderr, \
                            "Command was: %s" % " ".join(args)
                        sys.exit(1)
                if stderr:
                        stderr.close()

def _copy_file_contents(src, dst, buffer_size=16*1024):
        """A clone of distutils.file_util._copy_file_contents() that strips the
        CDDL text.  For Python files, we replace the CDDL text with an equal
        number of empty comment lines so that line numbers match between the
        source and destination files."""

        # Match the lines between and including the CDDL header signposts, as
        # well as empty comment lines before and after, if they exist.
        cddl_re = re.compile("\n(#\s*\n)?^[^\n]*CDDL HEADER START.+"
            "CDDL HEADER END[^\n]*$(\n#\s*$)?", re.MULTILINE|re.DOTALL)

        with file(src, "r") as sfp:
                try:
                        os.unlink(dst)
                except EnvironmentError, e:
                        if e.errno != errno.ENOENT:
                                raise DistutilsFileError("could not delete "
                                    "'%s': %s" % (dst, e))

                with file(dst, "w") as dfp:
                        while True:
                                buf = sfp.read(buffer_size)
                                if not buf:
                                        break
                                if src.endswith(".py"):
                                        match = cddl_re.search(buf)
                                        if match:
                                                # replace the CDDL expression
                                                # with the same number of empty
                                                # comment lines as the cddl_re
                                                # matched.
                                                substr = buf[
                                                    match.start():match.end()]
                                                count = len(
                                                    substr.split("\n")) - 2
                                                blanks = "#\n" * count
                                                buf = cddl_re.sub("\n" + blanks,
                                                    buf)
                                else:
                                         buf = cddl_re.sub("", buf)
                                dfp.write(buf)

# Make file_util use our version of _copy_file_contents
file_util._copy_file_contents = _copy_file_contents

def intltool_update_maintain():
        """Check if scope of localization looks up-to-date or possibly not,
        by comparing file set described in po/POTFILES.{in,skip} and
        actual source files (e.g. .py) detected.
        """
        rm_f("po/missing")
        rm_f("po/notexist")

        args = [
            "/usr/bin/intltool-update", "--maintain"
        ]
        print " ".join(args)
        podir = os.path.join(os.getcwd(), "po")
        run_cmd(args, podir, updenv={"LC_ALL": "C"}, ignerr=True)

        if os.path.exists("po/missing"):
            print >> sys.stderr, \
                "New file(s) with translatable strings detected:"
            missing = open("po/missing", "r")
            print >> sys.stderr, "--------"
            for fn in missing:
                print >> sys.stderr, "%s" % fn.strip()
            print >> sys.stderr, "--------"
            missing.close()
            print >> sys.stderr, \
"""Please evaluate whether any of the above file(s) needs localization. 
If so, please add its name to po/POTFILES.in.  If not (e.g., it's not 
delivered), please add its name to po/POTFILES.skip. 
Please be sure to maintain alphabetical ordering in both files."""
            sys.exit(1)

        if os.path.exists("po/notexist"):
            print >> sys.stderr, \
"""The following files are listed in po/POTFILES.in, but no longer exist 
in the workspace:"""
            notexist = open("po/notexist", "r")
            print >> sys.stderr, "--------"
            for fn in notexist:
                print >> sys.stderr, "%s" % fn.strip()
            print >> sys.stderr, "--------"
            notexist.close()
            print >> sys.stderr, \
                "Please remove the file names from po/POTFILES.in"
            sys.exit(1)

def intltool_update_pot():
        """Generate pkg.pot by extracting localizable strings from source
        files (e.g. .py)
        """
        rm_f("po/pkg.pot")

        args = [
            "/usr/bin/intltool-update", "--pot"
        ]
        print " ".join(args)
        podir = os.path.join(os.getcwd(), "po")
        run_cmd(args, podir,
            updenv={"LC_ALL": "C", "XGETTEXT": "/usr/gnu/bin/xgettext"})

        if not os.path.exists("po/pkg.pot"):
            print >> sys.stderr, \
                "Failed in generating pkg.pot."
            sys.exit(1)

def intltool_merge(src, dst):
        if not dep_util.newer(src, dst):
                return

        args = [
            "/usr/bin/intltool-merge", "-d", "-u",
            "-c", "po/.intltool-merge-cache", "po", src, dst
        ]
        print " ".join(args)
        run_cmd(args, os.getcwd(), updenv={"LC_ALL": "C"})

def i18n_check():
        """Checks for common i18n messaging bugs in the source."""

        src_files = []
        # A list of the i18n errors we check for in the code
        common_i18n_errors = [
            # This checks that messages with multiple parameters are always
            # written using "%(name)s" format, rather than just "%s"
            "format string with unnamed arguments cannot be properly localized"
        ]

        for line in open("po/POTFILES.in", "r").readlines():
                if line.startswith("["):
                        continue
                if line.startswith("#"):
                        continue
                src_files.append(line.rstrip())

        args = [
            "/usr/gnu/bin/xgettext", "--from-code=UTF-8", "-o", "/dev/null"]
        args += src_files

        xgettext_output_path = tempfile.mkstemp()[1]
        xgettext_output = open(xgettext_output_path, "w")
        run_cmd(args, os.getcwd(), updenv={"LC_ALL": "C"},
            savestderr=xgettext_output)

        found_errs = False
        i18n_errs = open("po/i18n_errs.txt", "w")
        for line in open(xgettext_output_path, "r").readlines():
                for err in common_i18n_errors:
                        if err in line:
                                i18n_errs.write(line)
                                found_errs = True
        i18n_errs.close()
        if found_errs:
                print >> sys.stderr, \
"The following i18n errors were detected and should be corrected:\n" \
"(this list is saved in po/i18n_errs.txt)\n"
                for line in open("po/i18n_errs.txt", "r"):
                        print >> sys.stderr, line.rstrip()
                sys.exit(1)
        os.remove(xgettext_output_path)

def msgfmt(src, dst):
        if not dep_util.newer(src, dst):
                return

        args = ["/usr/bin/msgfmt", "-o", dst, src]
        print " ".join(args)
        run_cmd(args, os.getcwd())

def localizablexml(src, dst):
        """create XML help for localization, where French part of legalnotice
        is stripped off
        """
        if not dep_util.newer(src, dst):
                return

        fsrc = open(src, "r")
        fdst = open(dst, "w")

        # indicates currently in French part of legalnotice
        in_fr = False

        for l in fsrc:
            if in_fr: # in French part
                if l.startswith('</legalnotice>'):
                    # reached end of legalnotice
                    print >> fdst, l,
                    in_fr = False
            elif l.startswith('<para lang="fr"/>') or \
                    l.startswith('<para lang="fr"></para>'):
                in_fr = True
            else:
                # not in French part
                print >> fdst, l,
        
        fsrc.close()
        fdst.close()

def xml2po_gen(src, dst):
        """Input is English XML file. Output is pkg_help.pot, message
        source for next translation update.
        """
        if not dep_util.newer(src, dst):
                return

        args = ["/usr/bin/xml2po", "-o", dst, src]
        print " ".join(args)
        run_cmd(args, os.getcwd())

def xml2po_merge(src, dst, mofile):
        """Input is English XML file and <lang>.po file (which contains
        translations). Output is translated XML file.
        """
        msgfmt(mofile[:-3] + ".po", mofile)

        monewer = dep_util.newer(mofile, dst)
        srcnewer = dep_util.newer(src, dst)

        if not srcnewer and not monewer:
                return

        args = ["/usr/bin/xml2po", "-t", mofile, "-o", dst, src]
        print " ".join(args)
        run_cmd(args, os.getcwd())

class installfile(Command):
        user_options = [
            ("file=", "f", "source file to copy"),
            ("dest=", "d", "destination directory"),
            ("mode=", "m", "file mode"),
        ]

        description = "De-CDDLing file copy"

        def initialize_options(self):
                self.file = None
                self.dest = None
                self.mode = None

        def finalize_options(self):
                if self.mode is None:
                        self.mode = 0644
                elif isinstance(self.mode, basestring):
                        try:
                                self.mode = int(self.mode, 8)
                        except ValueError:
                                self.mode = 0644

        def run(self):
                dest_file = os.path.join(self.dest, os.path.basename(self.file))
                ret = self.copy_file(self.file, dest_file)

                os.chmod(dest_file, self.mode)
                os.utime(dest_file, None)

                return ret

class build_func(_build):
        sub_commands = _build.sub_commands + [('build_data', None)]

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
                res = ""
                for err in e.exc_value:
                        if isinstance(err, basestring):
                                res += err + "\n"
                                continue

                        # Assume it's a tuple of (filename, lineno, col, code)
                        fname, line, col, code = err
                        res += "line %d, column %s, in %s:\n%s" % (line,
                            col or "unknown", fname, code)

                raise DistutilsError(res)

# On Solaris, ld inserts the full argument to the -o option into the symbol
# table.  This means that the resulting object will be different depending on
# the path at which the workspace lives, and not just on the interesting content
# of the object.
#
# In order to work around that bug (7076871), we create a new compiler class
# that looks at the argument indicating the output file, chdirs to its
# directory, and runs the real link with the output file set to just the base
# name of the file.
#
# Unfortunately, distutils isn't too customizable in this regard, so we have to
# twiddle with a couple of the names in the distutils.ccompiler namespace: we
# have to add a new entry to the compiler_class dict, and we have to override
# the new_compiler() function to point to our own.  Luckily, our copy of
# new_compiler() gets to be very simple, since we always know what we want to
# return.
class MyUnixCCompiler(UnixCCompiler):

        def link(self, *args, **kwargs):

                output_filename = args[2]
                output_dir = kwargs.get('output_dir')
                cwd = os.getcwd()

                assert(not output_dir)
                output_dir = os.path.join(cwd, os.path.dirname(output_filename))
                output_filename = os.path.basename(output_filename)
                nargs = args[:2] + (output_filename,) + args[3:]
                if not os.path.exists(output_dir):
                        os.mkdir(output_dir, 0755)
                os.chdir(output_dir)

                UnixCCompiler.link(self, *nargs, **kwargs)

                os.chdir(cwd)

distutils.ccompiler.compiler_class['myunix'] = (
    'unixccompiler', 'MyUnixCCompiler',
    'standard Unix-style compiler with a link stage modified for Solaris'
)

def my_new_compiler(plat=None, compiler=None, verbose=0, dry_run=0, force=0):
        return MyUnixCCompiler(None, dry_run, force)

if osname == 'sunos':
        distutils.ccompiler.new_compiler = my_new_compiler

class build_ext_func(_build_ext):

        def initialize_options(self):
                _build_ext.initialize_options(self)
                self.build64 = False

                if osname == 'sunos':
                        self.compiler = 'myunix'

        def build_extension(self, ext):
                # Build 32-bit
                _build_ext.build_extension(self, ext)
                if not ext.build_64:
                        return

                # Set up for 64-bit
                old_build_temp = self.build_temp
                d, f = os.path.split(self.build_temp)

                # store our 64-bit extensions elsewhere
                self.build_temp = d + "/temp64.%s" % \
                    os.path.basename(self.build_temp).replace("temp.", "")
                ext.extra_compile_args += ["-m64"]
                ext.extra_link_args += ["-m64"]
                self.build64 = True

                # Build 64-bit
                _build_ext.build_extension(self, ext)

                # Reset to 32-bit
                self.build_temp = old_build_temp
                ext.extra_compile_args.remove("-m64")
                ext.extra_link_args.remove("-m64")
                self.build64 = False

        def get_ext_fullpath(self, ext_name):
                path = _build_ext.get_ext_fullpath(self, ext_name)
                if not self.build64:
                        return path

                dpath, fpath = os.path.split(path)
                return os.path.join(dpath, "64", fpath)


class build_py_func(_build_py):

        def __init__(self, dist):
                ret = _build_py.__init__(self, dist)

                self.copied = []

                # Gather the timestamps of the .py files in the gate, so we can
                # force the mtimes of the built and delivered copies to be
                # consistent across builds, causing their corresponding .pyc
                # files to be unchanged unless the .py file content changed.

                self.timestamps = {}

                p = subprocess.Popen(
                    [sys.executable, os.path.join(pwd, "pydates")],
                    stdout=subprocess.PIPE)

                for line in p.stdout:
                        stamp, path = line.split()
                        stamp = float(stamp)
                        self.timestamps[path] = stamp

                if p.wait() != 0:
                        print >> sys.stderr, "ERROR: unable to gather .py " \
                            "timestamps"
                        sys.exit(1)

                return ret

        # override the build_module method to do VERSION substitution on
        # pkg/__init__.py
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

        def copy_file(self, infile, outfile, preserve_mode=1, preserve_times=1,
            link=None, level=1):

                # If the timestamp on the source file (coming from mercurial if
                # unchanged, or from the filesystem if changed) doesn't match
                # the filesystem timestamp on the destination, then force the
                # copy to make sure the right data is in place.

                try:
                        dst_mtime = os.stat(outfile).st_mtime
                except OSError, e:
                        if e.errno != errno.ENOENT:
                                raise
                        dst_mtime = time.time()

                # The timestamp for __init__.py is the timestamp for the
                # workspace itself.
                if outfile.endswith("/pkg/__init__.py"):
                        src_mtime = self.timestamps["."]
                else:
                        src_mtime = self.timestamps.get(
                            os.path.join("src", infile), self.timestamps["."])

                # Force a copy of the file if the source timestamp is different
                # from that of the destination, not just if it's newer.  This
                # allows timestamps in the working directory to regress (for
                # instance, following the reversion of a change).
                if dst_mtime != src_mtime:
                        f = self.force
                        self.force = True
                        dst, copied = _build_py.copy_file(self, infile, outfile,
                            preserve_mode, preserve_times, link, level)
                        self.force = f
                else:
                        dst, copied = outfile, 0

                # If we copied the file, then we need to go and readjust the
                # timestamp on the file to match what we have in our database.
                # Save the filename aside for our version of install_lib.
                if copied and dst.endswith(".py"):
                        os.utime(dst, (src_mtime, src_mtime))
                        self.copied.append(dst)

                return dst, copied

class build_data_func(Command):
        description = "build data files whose source isn't in deliverable form"
        user_options = []

        # As a subclass of distutils.cmd.Command, these methods are required to
        # be implemented.
        def initialize_options(self):
                pass

        def finalize_options(self):
                pass

        def run(self):
                # Anything that gets created here should get deleted in
                # clean_func.run() below.
                i18n_check()
                for f in intl_files:
                        intltool_merge(f, f[:-3])

                for l in help_locales:
                        path = "gui/help/%s/" % l
                        xml2po_merge(path + "package-manager.xml.in",
                            path + "package-manager.xml",
                            path + "%s.mo" % l)

                # create xml for localization
                localizablexml("gui/help/C/package-manager.xml",
                    "gui/help/C/package-manager.localizable.xml")

                # generate pkg_help.pot for next translation
                xml2po_gen("gui/help/C/package-manager.localizable.xml",
                    "gui/help/C/pkg_help.pot")

                for l in pkg_locales:
                        msgfmt("po/%s.po" % l, "po/%s.mo" % l)

                # generate pkg.pot for next translation
                intltool_update_maintain()
                intltool_update_pot()

                # create __LOCALE__ -> C symlink for omf file
                # to make installation with data_files list work
                locomf="gui/help/package-manager-__LOCALE__.omf"
                if not os.path.exists(locomf):
                    os.symlink("package-manager-C.omf", locomf)

def rm_f(filepath):
        """Remove a file without caring whether it exists."""

        try:
                os.unlink(filepath)
        except OSError, e:
                if e.errno != errno.ENOENT:
                        raise

class clean_func(_clean):
        def initialize_options(self):
                _clean.initialize_options(self)
                self.build_base = build_dir

        def run(self):
                _clean.run(self)

                rm_f("po/.intltool-merge-cache")

                for f in intl_files:
                        rm_f(f[:-3])

                for l in pkg_locales:
                        rm_f("po/%s.mo" % l)

                rm_f("po/pkg.pot")

                for l in help_locales:
                        path = "gui/help/%s/" % l
                        rm_f(path + "package-manager.xml")
                        rm_f(path + "%s.mo" % l)

                rm_f("gui/help/C/pkg_help.pot")

                rm_f("gui/help/package-manager-__LOCALE__.omf")
                rm_f("po/i18n_errs.txt")

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
            ("port=", "z", "lowest port to start a depot on"),
            ("timing", "t", "timing file <file>"),
            ("verbosemode", 'v', "run tests in verbose mode"),
            ("enableguitests", 'u', "enable IPS GUI tests, disabled by default"),
            ("stoponerr", 'x', "stop when a baseline mismatch occurs"),
            ("debugoutput", 'd', "emit debugging output"),
            ("showonexpectedfail", 'f',
                "show all failure info, even for expected fails"),
            ("startattest=", 's', "start at indicated test"),
            ("jobs=", 'j', "number of parallel processes to use"),
            ("quiet", "q", "use the dots as the output format"),
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
                self.port = 12001
                self.jobs = 1
                self.quiet = False

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

class Extension(distutils.core.Extension):
        # This class wraps the distutils Extension class, allowing us to set
        # build_64 in the object constructor instead of being forced to add it
        # after the object has been created.
        def __init__(self, name, sources, build_64=False, **kwargs):
                distutils.core.Extension.__init__(self, name, sources, **kwargs)
                self.build_64 = build_64

# These are set to real values based on the platform, down below
compile_args = None
if osname in ("sunos", "linux", "darwin"):
        compile_args = [ "-O3" ]
if osname == "sunos":
        link_args = [ "-zstrip-class=nonalloc" ]
else:
        link_args = []
# We don't support 64-bit yet, but 64-bit _actions.so, _common.so, and
# _varcet.so are needed for a system repository mod_wsgi application,
# sysrepo_p5p.py.
ext_modules = [
        Extension(
                'actions._actions',
                _actions_srcs,
                include_dirs = include_dirs,
                extra_compile_args = compile_args,
                extra_link_args = link_args,
                build_64 = True
                ),
        Extension(
                'actions._common',
                _actcomm_srcs,
                include_dirs = include_dirs,
                extra_compile_args = compile_args,
                extra_link_args = link_args,
                build_64 = True
                ),
        Extension(
                '_varcet',
                _varcet_srcs,
                include_dirs = include_dirs,
                extra_compile_args = compile_args,
                extra_link_args = link_args,
                build_64 = True
                ),
        Extension(
                'solver',
                solver_srcs,
                include_dirs = include_dirs + ["."],
                extra_compile_args = compile_args,
                extra_link_args = link_args + solver_link_args,
                define_macros = [('_FILE_OFFSET_BITS', '64')]
                ),
        ]
elf_libraries = None
data_files = web_files
cmdclasses = {
        'install': install_func,
        'install_data': install_data_func,
        'install_lib': install_lib_func,
        'build': build_func,
        'build_data': build_data_func,
        'build_ext': build_ext_func,
        'build_py': build_py_func,
        'bdist': dist_func,
        'lint': lint_func,
        'clint': clint_func,
        'pylint': pylint_func,
        'pylint_quiet': pylint_func_quiet,
        'clean': clean_func,
        'clobber': clobber_func,
        'test': test_func,
        'installfile': installfile,
        }

# all builds of IPS should have manpages
data_files += [
        (man1_dir, man1_files),
        (man1m_dir, man1m_files),
        (man5_dir, man5_files),
        (man1_ja_JP_dir, man1_ja_files),
        (man1m_ja_JP_dir, man1m_ja_files),
        (man5_ja_JP_dir, man5_ja_files),
        (man1_zh_CN_dir, man1_zh_CN_files),
        (man1m_zh_CN_dir, man1m_zh_CN_files),
        (man5_zh_CN_dir, man5_zh_CN_files),
        (resource_dir, resource_files),
        ]
# add transforms
data_files += [
        (transform_dir, transform_files)
        ]
if osname == 'sunos':
        # Solaris-specific extensions are added here
        data_files += [
                (smf_app_dir, smf_app_files),
                (execattrd_dir, execattrd_files),
                (authattrd_dir, authattrd_files),
                (sysrepo_dir, sysrepo_files),
                (sysrepo_logs_dir, sysrepo_log_stubs),
                (sysrepo_cache_dir, {}),
                (autostart_dir, autostart_files),
                (desktop_dir, desktop_files),
                (gconf_dir, gconf_files),
                (omf_dir, omf_files),
                ('usr/share/icons/hicolor/48x48/mimetypes',
                    ['gui/data/gnome-mime-application-vnd.pkg5.info.png']),
                ('usr/share/mime/packages', ['gui/data/packagemanager-info.xml']),
                (pm_share_dir, ['gui/data/packagemanager.ui']),
                ]
        data_files += [
            (os.path.join(startpage_dir, locale), files)
            for locale, files in startpage_files.iteritems()
        ]
        data_files += [
            (os.path.join(help_dir, locale), files)
            for locale, files in help_files.iteritems()
        ]
        # install localizable .xml and its .pot file to put into localizable file package
        data_files += [
            (os.path.join(help_dir, '__LOCALE__'),
                [('gui/help/C/package-manager.localizable.xml', 'package-manager.xml'),
                 ('gui/help/C/pkg_help.pot', 'pkg_help.pot')])
        ]
        data_files += [
            (os.path.join(locale_dir, locale, 'LC_MESSAGES'),
                [('po/%s.mo' % locale, 'pkg.mo')])
            for locale in pkg_locales
        ]
        # install English .pot file to put into localizable file package
        data_files += [
            (os.path.join(locale_dir, '__LOCALE__', 'LC_MESSAGES'),
                [('po/pkg.pot', 'pkg.pot')])
        ]
        for t in 'HighContrast', 'HighContrastInverse', '':
                for px in '24', '36', '48':
                        data_files += [(
                            '%s/icons/%s/%sx%s/actions' % (um_share_dir, t or 'hicolor', px, px),
                            ['um/data/icons/%s/%sx%s/updatemanager.png' % (t, px, px)]
                        )]
                data_files += [(
                    '%s/icons/%s/16x16/actions' % (pm_share_dir, t or 'hicolor'),
                    [
                        'gui/data/icons/%s/16x16/%s.png' % (t, n)
                        for n in ('filter_all', 'filter_selected', 'progress_checkmark',
                            'selection', 'status_checkmark', 'status_installed',
                            'status_newupdate', 'status_notinstalled')
                    ]
                )]
                data_files += [
                    ('%s/icons/%s/%sx%s/actions' % (pm_share_dir, t or 'hicolor', px, px),
                    [
                        'gui/data/icons/%s/%sx%s/%s.png' % (t, px, px, n)
                        for n in ('pm-install_update', 'pm-refresh',
                            'pm-remove', 'pm-update_all')
                    ])
                    for px in (24, 48)
                ]
                data_files += [(
                    '%s/icons/%s/48x48/actions' % (pm_share_dir, t or 'hicolor'),
                    ['gui/data/icons/%s/48x48/packagemanager.png' % t]
                )]
                data_files += [
                    ('usr/share/icons/%s/48x48/apps' % (t or 'hicolor'),
                        [
                            'um/data/icons/%s/48x48/updatemanager.png' % t,
                            'gui/data/icons/%s/48x48/packagemanager.png' % t
                        ]),
                ]
                # These two icons don't fit any patterns.
                data_files += [
                    (os.path.join(pm_share_dir, 'icons/hicolor/16x16/actions'), [
                        'gui/data/icons/16x16/progress_blank.png']),
                    (os.path.join(pm_share_dir, 'icons/hicolor/24x24/actions'), [
                        'gui/data/icons/24x24/pm-check.png']),
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
                        extra_link_args = link_args,
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
                    Extension(
                            'syscallat',
                            syscallat_srcs,
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
