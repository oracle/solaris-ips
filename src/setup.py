#!/usr/bin/python3.9 -Es
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
# Copyright (c) 2008, 2024, Oracle and/or its affiliates.
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
import py_compile
import hashlib
import time

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

dist_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "dist_" + arch))
build_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "build_" + arch))
if "ROOT" in os.environ and os.environ["ROOT"] != "":
    root_dir = os.environ["ROOT"]
else:
    root_dir = os.path.normpath(os.path.join(pwd, os.pardir, "proto", "root_" + arch))
pkgs_dir = os.path.normpath(os.path.join(pwd, os.pardir, "packages", arch))
extern_dir = os.path.normpath(os.path.join(pwd, "extern"))
cffi_dir = os.path.normpath(os.path.join(pwd, "cffi_src"))

py_version = '.'.join(platform.python_version_tuple()[:2])
assert py_version in ('3.9', '3.11')
py_install_dir = 'usr/lib/python' + py_version + '/vendor-packages'

py64_executable = None
#Python 3 is always 64 bit and located in /usr/bin.
if float(py_version) < 3 and osname == 'sunos':
    py64_executable = '/usr/bin/64/python' + py_version

scripts_dir = 'usr/bin'
lib_dir = 'usr/lib'
svc_method_dir = 'lib/svc/method'
svc_share_dir = 'lib/svc/share'

resource_dir = 'usr/share/lib/pkg'
rad_dir = 'usr/share/lib/pkg'
transform_dir = 'usr/share/pkg/transforms'
ignored_deps_dir = 'usr/share/pkg/ignored_deps'
execattrd_dir = 'etc/security/exec_attr.d'
authattrd_dir = 'etc/security/auth_attr.d'
userattrd_dir = 'etc/user_attr.d'
sysrepo_dir = 'etc/pkg/sysrepo'
sysrepo_logs_dir = 'var/log/pkg/sysrepo'
sysrepo_cache_dir = 'var/cache/pkg/sysrepo'
depot_dir = 'etc/pkg/depot'
depot_conf_dir = 'etc/pkg/depot/conf.d'
depot_logs_dir = 'var/log/pkg/depot'
depot_cache_dir = 'var/cache/pkg/depot'
mirror_logs_dir = 'var/log/pkg/mirror'
mirror_cache_dir = 'var/cache/pkg/mirror'


# A list of source, destination tuples of modules which should be hardlinked
# together if the os supports it and otherwise copied.
hardlink_modules = []

symlink_modules = [
        ['cronjob-removal.sh', 'usr/lib/update-refresh.sh'],
        ['../cronjob-removal.sh', 'usr/lib/update-manager/update-refresh.sh']
        ]

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
                ['util/publish/pkgsurf.py', 'pkgsurf'],
                ['publish.py', 'pkgsend'],
                ['pull.py', 'pkgrecv'],
                ['sign.py', 'pkgsign'],
                ],
        lib_dir: [
                ['depot.py', 'pkg.depotd'],
                ['sysrepo.py', 'pkg.sysrepo'],
                ['depot-config.py', 'pkg.depot-config'],
                ['cronjob-removal.sh', 'cronjob-removal.sh'],
                ],
        svc_method_dir: [
                ['svc/svc-pkg-auto-update', 'svc-pkg-auto-update'],
                ['svc/svc-pkg-auto-update-cleanup',
                    'svc-pkg-auto-update-cleanup'],
                ['svc/svc-pkg-depot', 'svc-pkg-depot'],
                ['svc/svc-pkg-mdns', 'svc-pkg-mdns'],
                ['svc/svc-pkg-mirror', 'svc-pkg-mirror'],
                ['svc/svc-pkg-repositories-setup',
                    'svc-pkg-repositories-setup'],
                ['svc/svc-pkg-server', 'svc-pkg-server'],
                ['svc/svc-pkg-sysrepo', 'svc-pkg-sysrepo'],
                ['svc/svc-pkg-sysrepo-cache',
                    'svc-pkg-sysrepo-cache'],
                ],
        svc_share_dir: [
                ['svc/pkg5_include.sh', 'pkg5_include.sh'],
                ],
        rad_dir: [
                ["rad-invoke.py", "rad-invoke"],
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
        rad_dir: [
                ["rad-invoke.py", "rad-invoke"],
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

packages = [
        'pkg',
        'pkg.actions',
        'pkg.bundle',
        'pkg.client',
        'pkg.client.linkedimage',
        'pkg.client.transport',
        'pkg.file_layout',
        'pkg.flavor',
        'pkg.lint',
        'pkg.no_site_packages',
        'pkg.portable',
        'pkg.publish',
        'pkg.server'
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
        'util/apache2/sysrepo/logs/error_log'
        ]
depot_files = [
        'util/apache2/depot/depot.conf.mako',
        'util/apache2/depot/depot_httpd.conf.mako',
        'util/apache2/depot/depot_index.py',
        'util/apache2/depot/depot_httpd_ssl_protocol.conf',
        ]
depot_log_stubs = [
        'util/apache2/depot/logs/access_log',
        'util/apache2/depot/logs/error_log'
        ]
ignored_deps_files = []

execattrd_files = [
        'util/misc/exec_attr.d/package:pkg',
]
authattrd_files = ['util/misc/auth_attr.d/package:pkg']
userattrd_files = ['util/misc/user_attr.d/package:pkg']

sha512_t_srcs = [
        'cffi_src/_sha512_t.c'
        ]
sysattr_srcs = [
        'cffi_src/_sysattr.c'
        ]
syscallat_srcs = [
        'cffi_src/_syscallat.c'
        ]
elf_srcs = [
        'modules/elf.c',
        'modules/elfextract.c',
        'modules/liblist.c',
        ]
arch_srcs = [
        'cffi_src/_arch.c'
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
_misc_srcs = [
        'modules/_misc.c'
        ]
solver_srcs = [
        'modules/solver/solver.c',
        'modules/solver/py_solver.c'
        ]
solver_link_args = ["-lm", "-lc"]
if osname == 'sunos':
    solver_link_args = ["-ztext"] + solver_link_args

# solver code is external code with all its
# associated compiler warnings. Suppress them.
solver_suppress_args = ["-Wno-return-type",
                        "-Wno-strict-aliasing",
                        "-Wno-unused-function",
                        "-Wno-unused-variable"
                        ]


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
                ["{0}{1}".format("-I", k) for k in include_dirs] + \
                ['-I' + self.escape(get_python_inc())] + \
                arch_srcs
            elfcmd = lint + lint_flags + \
                ["{0}{1}".format("-I", k) for k in include_dirs] + \
                ['-I' + self.escape(get_python_inc())] + \
                ["{0}{1}".format("-l", k) for k in elf_libraries] + \
                elf_srcs
            _actionscmd = lint + lint_flags + \
                ["{0}{1}".format("-I", k) for k in include_dirs] + \
                ['-I' + self.escape(get_python_inc())] + \
                _actions_srcs
            _actcommcmd = lint + lint_flags + \
                ["{0}{1}".format("-I", k) for k in include_dirs] + \
                ['-I' + self.escape(get_python_inc())] + \
                _actcomm_srcs
            _varcetcmd = lint + lint_flags + \
                ["{0}{1}".format("-I", k) for k in include_dirs] + \
                ['-I' + self.escape(get_python_inc())] + \
                _varcet_srcs
            _misccmd = lint + lint_flags + \
                ["{0}{1}".format("-I", k) for k in include_dirs] + \
                ['-I' + self.escape(get_python_inc())] + \
                _misc_srcs
            syscallatcmd = lint + lint_flags + \
                ['-D_FILE_OFFSET_BITS=64'] + \
                ["{0}{1}".format("-I", k) for k in include_dirs] + \
                ['-I' + self.escape(get_python_inc())] + \
                syscallat_srcs
            sysattrcmd = lint + lint_flags + \
                ['-D_FILE_OFFSET_BITS=64'] + \
                ["{0}{1}".format("-I", k) for k in include_dirs] + \
                ['-I' + self.escape(get_python_inc())] + \
                ["{0}{1}".format("-l", k) for k in sysattr_libraries] + \
                sysattr_srcs
            sha512_tcmd = lint + lint_flags + \
                ['-D_FILE_OFFSET_BITS=64'] + \
                ["{0}{1}".format("-I", k) for k in include_dirs] + \
                ['-I' + self.escape(get_python_inc())] + \
                ["{0}{1}".format("-l", k) for k in sha512_t_libraries] + \
                sha512_t_srcs

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
            print(" ".join(_misccmd))
            os.system(" ".join(_misccmd))
            print(" ".join(syscallatcmd))
            os.system(" ".join(syscallatcmd))
            print(" ".join(sysattrcmd))
            os.system(" ".join(sysattrcmd))
            print(" ".join(sha512_tcmd))
            os.system(" ".join(sha512_tcmd))


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

        for d, files in scripts[osname].items():
            for (srcname, dstname) in files:
                dst_dir = util.change_root(self.root_dir, d)
                dst_path = util.change_root(self.root_dir,
                       os.path.join(d, dstname))
                dir_util.mkpath(dst_dir, verbose=True)
                file_util.copy_file(srcname, dst_path,
                    update=True)
                # make scripts executable
                os.chmod(dst_path,
                    os.stat(dst_path).st_mode
                    | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        for target, o_dest in symlink_modules:
            dest = util.change_root(self.root_dir, o_dest)
            dir_util.mkpath(os.path.dirname(dest), verbose=True)
            try:
                os.unlink(dest)
            except Exception:
                pass
            os.symlink(target, dest)


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
                    if isinstance(file, str):
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
        print("install failed and returned {0:d}.".format(ret),
            file=sys.stderr)
        print("Command was: {0}".format(" ".join(args)),
            file=sys.stderr)

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
    cddl_re = re.compile(b"\n(#\s*\n)?^[^\n]*CDDL HEADER START.+"
        b"CDDL HEADER END[^\n]*$(\n#\s*$)?", re.MULTILINE | re.DOTALL)

    # Look for shebang line to replace with arch-specific Python executable.
    shebang_re = re.compile('^#!.*python[0-9]\.[0-9]')
    first_buf = True

    with open(src, "rb") as sfp:
        try:
            os.unlink(dst)
        except EnvironmentError as e:
            if e.errno != errno.ENOENT:
                raise DistutilsFileError("could not delete "
                    "'{0}': {1}".format(dst, e))

        with open(dst, "wb") as dfp:
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
                            substr.split(b"\n")) - 2
                        blanks = b"#\n" * count
                        buf = cddl_re.sub(b"\n" + blanks,
                            buf)

                    if not first_buf or not py64_executable:
                        dfp.write(buf)
                        continue

                    fl = buf[:buf.find(os.linesep) + 1]
                    sb_match = shebang_re.search(fl)
                    if sb_match:
                        buf = shebang_re.sub(
                            "#!" + py64_executable,
                            buf)
                else:
                    buf = cddl_re.sub(b"", buf)
                dfp.write(buf)
                first_buf = False


# Make file_util use our version of _copy_file_contents
file_util._copy_file_contents = _copy_file_contents


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
                print(l, file=fdst)
                in_fr = False
        elif l.startswith('<para lang="fr"/>') or \
                l.startswith('<para lang="fr"></para>'):
            in_fr = True
        else:
            # not in French part
            print(l, file=fdst)

    fsrc.close()
    fdst.close()


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
            self.mode = 0o644
        elif isinstance(self.mode, str):
            try:
                self.mode = int(self.mode, 8)
            except ValueError:
                self.mode = 0o644

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
        p = subprocess.Popen(['hg', 'id', '-i'], stdout = subprocess.PIPE, text=True)
        return p.communicate()[0].strip()
    except OSError:
        print("ERROR: unable to obtain mercurial version",
            file=sys.stderr)
        return "unknown"


def syntax_check(filename):
    """ Run python's compiler over the file, and discard the results.
        Arrange to generate an exception if the file does not compile.
        This is needed because distutil's own use of pycompile (in the
        distutils.utils module) is broken, and doesn't stop on error. """
    try:
        tmpfd, tmp_file = tempfile.mkstemp()
        py_compile.compile(filename, tmp_file, doraise=True)
    except py_compile.PyCompileError as e:
        res = ""
        for err in e.exc_value:
            if isinstance(err, str):
                res += err + "\n"
                continue

            # Assume it's a tuple of (filename, lineno, col, code)
            fname, line, col, code = err
            res += "line {0:d}, column {1}, in {2}:\n{3}".format(
                line, col or "unknown", fname, code)

        raise DistutilsError(res)
    finally:
        os.remove(tmp_file)


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

        assert not output_dir
        output_dir = os.path.join(cwd, os.path.dirname(output_filename))
        output_filename = os.path.basename(output_filename)
        nargs = args[:2] + (output_filename,) + args[3:]
        if not os.path.exists(output_dir):
            os.mkdir(output_dir, 0o755)
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
        self.build_temp = str(self.build_temp)
        _build_ext.build_extension(self, ext)
        if not ext.build_64:
            return

        # Set up for 64-bit
        old_build_temp = self.build_temp
        d, f = os.path.split(self.build_temp)

        # store our 64-bit extensions elsewhere
        self.build_temp = str(d + "/temp64.{0}".format(
            os.path.basename(self.build_temp).replace("temp.", "")))
        ext.extra_compile_args += ["-m64"]
        ext.extra_link_args += ["-m64"]
        self.build64 = True

        # Build 64-bit
        _build_ext.build_extension(self, ext)

        # Reset to 32-bit
        self.build_temp = str(old_build_temp)
        ext.extra_compile_args.remove("-m64")
        ext.extra_link_args.remove("-m64")
        self.build64 = False

    def get_ext_fullpath(self, ext_name):
        path = _build_ext.get_ext_fullpath(self, ext_name)
        if not self.build64:
            return path

        dpath, fpath = os.path.split(path)
        if py_version < '3.0':
            return os.path.join(dpath, "64", fpath)
        return os.path.join(dpath, fpath)


class build_py_func(_build_py):

    def __init__(self, dist):
        _build_py.__init__(self, dist)

        self.copied = []

        # Gather the timestamps of the .py files in the gate, so we can
        # force the mtimes of the built and delivered copies to be
        # consistent across builds, causing their corresponding .pyc
        # files to be unchanged unless the .py file content changed.

        self.timestamps = {}

        p = subprocess.Popen(
            ["/usr/bin/python3.9", os.path.join(pwd, "pydates")],
            stdout=subprocess.PIPE, text=True)

        for line in p.stdout:
            stamp, path = line.split()
            stamp = float(stamp)
            self.timestamps[path] = stamp

        if p.wait() != 0:
            print("ERROR: unable to gather .py timestamps",
                file=sys.stderr)
            sys.exit(1)

        # Before building extensions, we need to generate .c files
        # for the C extension modules by running the CFFI build
        # script files.
        for path in os.listdir(cffi_dir):
            if not path.startswith("build_"):
                continue
            path = os.path.join(cffi_dir, path)
            # make scripts executable
            os.chmod(path,
                os.stat(path).st_mode
                | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            # run the scripts
            p = subprocess.Popen(
                [sys.executable, path])

    # override the build_module method to do VERSION substitution on
    # pkg/__init__.py
    def build_module (self, module, module_file, package):

        if module == "__init__" and package == "pkg":
            versionre = '(?m)^VERSION[^"]*"([^"]*)"'
            # Grab the previously-built version out of the build
            # tree.
            try:
                ocontent = \
                    open(self.get_module_outfile(self.build_lib,
                        [package], module)).read()
                ov = re.search(versionre, ocontent).group(1)
            except (IOError, AttributeError):
                ov = None
            v = get_hg_version()
            vstr = 'VERSION = "{0}"'.format(v)
            # If the versions haven't changed, there's no need to
            # recompile.
            if v == ov:
                return

            with open(module_file) as f:
                mcontent = f.read()
                mcontent = re.sub(versionre, vstr, mcontent)
                tmpfd, tmp_file = tempfile.mkstemp()
                with open(tmp_file, "w") as wf:
                    wf.write(mcontent)
            print("doing version substitution: ", v)
            rv = _build_py.build_module(self, module, tmp_file, str(package))
            os.unlink(tmp_file)
            return rv

        # Will raise a DistutilsError on failure.
        syntax_check(module_file)

        return _build_py.build_module(self, module, module_file, str(package))

    def copy_file(self, infile, outfile, preserve_mode=1, preserve_times=1,
        link=None, level=1):

        # If the timestamp on the source file (coming from mercurial if
        # unchanged, or from the filesystem if changed) doesn't match
        # the filesystem timestamp on the destination, then force the
        # copy to make sure the right data is in place.

        try:
            dst_mtime = os.stat(outfile).st_mtime
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
            dst_mtime = time.time()

        # The timestamp for __init__.py is the timestamp for the
        # workspace itself.
        if outfile.endswith("/pkg/__init__.py"):
            src_mtime = self.timestamps["."]
        else:
            src_mtime = self.timestamps.get(os.path.join("src",
                infile), self.timestamps["."])

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
        pass


def rm_f(filepath):
    """Remove a file without caring whether it exists."""

    try:
        os.unlink(filepath)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


class clean_func(_clean):
    def initialize_options(self):
        _clean.initialize_options(self)
        self.build_base = build_dir

    def run(self):
        _clean.run(self)


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
        # These files generated by the CFFI build scripts are useless
        # at this point, therefore clean them up.
        print("deleting temporary files generated by CFFI")
        for path in os.listdir(cffi_dir):
            if not path.startswith("_"):
                continue
            path = os.path.join(cffi_dir, path)
            rm_f(path)


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
        ("stoponerr", 'x', "stop when a baseline mismatch occurs"),
        ("debugoutput", 'd', "emit debugging output"),
        ("showonexpectedfail", 'f',
            "show all failure info, even for expected fails"),
        ("startattest=", 's', "start at indicated test"),
        ("jobs=", 'j', "number of parallel processes to use"),
        ("quiet", "q", "use the dots as the output format"),
        ("livesystem", 'l', "run tests on live system"),
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
        self.livesystem = False

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
        # 'name' and the item in 'sources' must be a string literal
        sources = [str(s) for s in sources]
        distutils.core.Extension.__init__(self, str(name), sources, **kwargs)
        self.build_64 = build_64


# These are set to real values based on the platform, down below
compile_args = None
if osname in ("sunos", "linux", "darwin"):
    compile_args = [ "-O3" ]
if osname == "sunos":
    link_args = [ "-zstrip-class=nonalloc" ]
else:
    link_args = []

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
                '_misc',
                _misc_srcs,
                include_dirs = include_dirs,
                extra_compile_args = compile_args,
                extra_link_args = link_args,
                build_64 = True
                ),
        Extension(
                'solver',
                solver_srcs,
                include_dirs = include_dirs + ["."],
                extra_compile_args = compile_args + solver_suppress_args,
                extra_link_args = link_args + solver_link_args,
                define_macros = [('_FILE_OFFSET_BITS', '64')],
                build_64 = True
                ),
        ]
elf_libraries = None
sysattr_libraries = None
sha512_t_libraries = None
data_files = []
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
        'clean': clean_func,
        'clobber': clobber_func,
        'test': test_func,
        'installfile': installfile,
        }

# add resource files
data_files += [
        (resource_dir, resource_files)
        ]
# add transforms
data_files += [
        (transform_dir, transform_files)
        ]
# add ignored deps
data_files += [
        (ignored_deps_dir, ignored_deps_files)
        ]
if osname == 'sunos':
    # Solaris-specific extensions are added here
    data_files += [
            (execattrd_dir, execattrd_files),
            (authattrd_dir, authattrd_files),
            (userattrd_dir, userattrd_files),
            (sysrepo_dir, sysrepo_files),
            (sysrepo_logs_dir, sysrepo_log_stubs),
            (sysrepo_cache_dir, {}),
            (depot_dir, depot_files),
            (depot_conf_dir, {}),
            (depot_logs_dir, depot_log_stubs),
            (depot_cache_dir, {}),
            (mirror_cache_dir, {}),
            (mirror_logs_dir, {}),
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
                    build_64 = True
                    ),
            ]

    # Solaris has built-in md library and Solaris-specific arch extension
    # All others use OpenSSL and cross-platform arch module
    if osname == 'sunos':
        elf_libraries += [ 'md' ]
        sysattr_libraries = [ 'nvpair' ]
        sha512_t_libraries = [ 'md' ]
        ext_modules += [
                Extension(
                        '_arch',
                        arch_srcs,
                        include_dirs = include_dirs,
                        extra_compile_args = compile_args,
                        extra_link_args = link_args,
                        define_macros = [('_FILE_OFFSET_BITS', '64')],
                        build_64 = True
                        ),
                Extension(
                        '_syscallat',
                        syscallat_srcs,
                        include_dirs = include_dirs,
                        extra_compile_args = compile_args,
                        extra_link_args = link_args,
                        define_macros = [('_FILE_OFFSET_BITS', '64')],
                        build_64 = True
                        ),
                Extension(
                        '_sysattr',
                        sysattr_srcs,
                        include_dirs = include_dirs,
                        libraries = sysattr_libraries,
                        extra_compile_args = compile_args,
                        extra_link_args = link_args,
                        define_macros = [('_FILE_OFFSET_BITS', '64')],
                        build_64 = True
                        ),
                Extension(
                        '_sha512_t',
                        sha512_t_srcs,
                        include_dirs = include_dirs,
                        libraries = sha512_t_libraries,
                        extra_compile_args = compile_args,
                        extra_link_args = link_args,
                        define_macros = [('_FILE_OFFSET_BITS', '64')],
                        build_64 = True
                        ),
                ]
    else:
        elf_libraries += [ 'ssl' ]

setup(cmdclass = cmdclasses,
    name = 'pkg',
    version = '0.1',
    package_dir = {'pkg': 'modules'},
    packages = packages,
    data_files = data_files,
    ext_package = 'pkg',
    ext_modules = ext_modules,
    classifiers = [
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.11',
    ]
)
