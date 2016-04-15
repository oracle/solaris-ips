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
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

import pkg.client.api
import pkg.client.api_errors as apx
import pkg.client.progress as progress
import pkg.client.publisher as publisher
import pkg.lint.base as base
import pkg.lint.config
import pkg.fmri
from pkg.client.api_errors import ApiException
from pkg.version import DotSequence, Version

import logging
import os
import shutil
import six
import sys
from six.moves import configparser
from six.moves.urllib.parse import urlparse, quote

PKG_CLIENT_NAME = "pkglint"
CLIENT_API_VERSION = 82
pkg.client.global_settings.client_name = PKG_CLIENT_NAME

class LintEngineException(Exception):
        """An exception thrown when something fatal goes wrong with the engine,
        such that linting can no longer continue."""
        pass


class LintEngineSetupException(LintEngineException):
        """An exception thrown when the engine failed to complete its setup."""
        pass


class LintEngineCache():
        """This class provides two caches for the LintEngine.  A cache of the
        latest packages for one or more ImageInterface objects intended to be
        seeded at startup, and a generic manifest cache"""

        def __init__(self, version_pattern, release=None):
                self.latest_cache = {}
                self.misc_cache = {}
                self.logger = logging.getLogger("pkglint")
                self.seeded = False

                # release is a build number, eg. 150
                # version_pattern used by the engine is a regexp, intended
                # to be used when searching for images, combined with the
                # release - eg. "*,5.11-0."
                #
                self.version_pattern = version_pattern
                self.release = release
                if self.release:
                        combined = "{0}{1}".format(
                            version_pattern.split(",")[1], release)
                        try:
                                self.branch = DotSequence(
                                    combined.split("-")[1])
                        except pkg.version.IllegalDotSequence:
                                raise LintEngineSetupException(
                                    _("Invalid release string: {0}").format(
                                    self.release))

        def seed_latest(self, api_inst, tracker, phase):
                """Builds a cache of latest manifests for this api_inst, using
                the provided progress tracker, phase and release.
                """
                search_type = pkg.client.api.ImageInterface.LIST_NEWEST
                pattern_list = ["*"]
                self.seeded = True

                # a dictionary of PkgFmri objects which we'll use to retrieve
                # manifests
                packages = {}

                # a dictionary of the latest packages for a given release
                self.latest_cache[api_inst] = {}
                # a dictionary of packages at other versions
                self.misc_cache[api_inst] = {}

                if not self.release:
                        for item in api_inst.get_pkg_list(
                            search_type, patterns=pattern_list, variants=True):
                                pub_name, name, version = item[0]
                                pub = api_inst.get_publisher(prefix=pub_name)
                                fmri ="pkg://{0}/{1}@{2}".format(pub, name,
                                    version)
                                pfmri = pkg.fmri.PkgFmri(fmri)
                                # index with just the pkg name, allowing us to
                                # use this cache when searching for dependencies
                                packages["pkg:/{0}".format(name)] = pfmri

                else:
                        # take a bit more time building up the latest version
                        # of all packages not greater than build_release
                        search_type = pkg.client.api.ImageInterface.LIST_ALL

                        for item in api_inst.get_pkg_list(
                            search_type, variants=True):
                                pub_name, name, version = item[0]
                                pub = api_inst.get_publisher(prefix=pub_name)
                                fmri ="pkg://{0}/{1}@{2}".format(pub, name,
                                    version)
                                # obtain just the build branch, e.g. from
                                # 0.5.11,5.11-0.111:20090508T235707Z, return
                                # 0.111
                                branch = Version(version, None).branch

                                pfmri = pkg.fmri.PkgFmri(fmri)
                                key = "pkg:/{0}".format(name)

                                if key not in packages and \
                                    branch <= self.branch:
                                        packages[key] = pfmri
                                # get_pkg_list returns results sorted by
                                # publisher, then sorted by version. We may find
                                # another publisher that has a more recent
                                # package available, so we need to respect
                                # timestamps in that case.
                                elif key in packages:
                                        prev = packages[key]
                                        if lint_fmri_successor(pfmri, prev,
                                            ignore_timestamps=False) and \
                                            branch <= self.branch:
                                                packages[key] = pfmri

                # now get the manifests
                tracker.manifest_fetch_start(len(packages))
                for item in packages:
                        self.latest_cache[api_inst][item] = \
                            api_inst.get_manifest(packages[item])
                        tracker.manifest_fetch_progress(completion=True)
                tracker.manifest_fetch_done()

        def gen_latest(self, api_inst, pattern):
                """ A generator function to return the latest version of the
                packages matching the supplied pattern from the publishers set
                for api_inst"""
                if not self.seeded:
                        raise LintEngineException("Cache has not been seeded")

                if api_inst in self.latest_cache:
                        for item in sorted(self.latest_cache[api_inst]):
                                mf = self.latest_cache[api_inst][item]
                                if pattern and pkg.fmri.glob_match(
                                    str(mf.fmri), pattern):
                                        yield mf
                                elif not pattern:
                                        yield mf

        def get_latest(self, api_inst, pkg_name):
                """ Return the package matching pkg_name from the publishers set
                for api_inst """
                if not self.seeded:
                        raise LintEngineException("Cache has not been seeded")

                if api_inst in self.latest_cache:
                        if pkg_name in self.latest_cache[api_inst]:
                                return self.latest_cache[api_inst][pkg_name]
                return None

        def count_latest(self, api_inst, pattern):
                """Returns the number of manifests in the given api_inst cache
                that match the provided pattern. If pattern is None,
                we return the length of the api_inst cache."""
                if not self.seeded:
                        raise LintEngineException("Cache has not been seeded")
                if not pattern:
                        return len(self.latest_cache[api_inst])
                count = 0
                for item in self.latest_cache[api_inst]:
                        mf = self.latest_cache[api_inst][item]
                        if pkg.fmri.glob_match(str(mf.fmri), pattern):
                                count = count + 1
                return count

        def add(self, api_inst, pkg_name, manifest):
                """Adds a given manifest to the cache for a given api_inst"""
                # we don't update latest_cache, since that should have been
                # pre-seeded on startup.
                self.misc_cache[api_inst][pkg_name] = manifest

        def get(self, api_inst, pkg_name):
                """Retrieves a given pkg_name entry from the cache.
                Can raise KeyError if the package isn't in the cache."""
                if not self.seeded:
                        raise LintEngineException("Cache has not been seeded")
                if pkg_name in self.latest_cache[api_inst]:
                        return self.latest_cache[api_inst][pkg_name]
                else:
                        return self.misc_cache[api_inst][pkg_name]


class LintEngine(object):
        """LintEngine is the main object used by pkglint to discover lint
        plugins, and execute lint checks on package manifests, retrieved
        from a repository or from local objects.

        Lint plugins are written as subclasses of pkg.lint.base.Checker
        and are discovered once the module containing them has been listed
        in either the shipped pkglintrc file, a user-supplied version, or
        the pkg.lint.config.PkglintConfig defaults.

        User-supplied manifests for linting are read directly as files
        provided on the command line.  For cross-checking against a
        reference repository, or linting the manifests in a repository, we
        create a reference or lint user-images in a provided cache location,
        used to obtain manifests from those repositories.

        Multiple repositories can be provided, however each must
        use a different publisher.prefix (as they are added as publishers
        to a single user image)

        Our reference image is stored in

        <cache>/ref_image/

        The image for linting is stored in

        <cache>/lint_image/

        We can also lint pkg.manifest.Manifest objects, passed as the
        lint_manifests list to the setup(..) method.

        The config object for the engine has the following keys:

        'log_level' The minimum level at which to emit lint messages. Lint
        messages lower than this level are discarded.

        By default, this is set to INFO. Log levels in order of least to most
        severe are: DEBUG, INFO, WARNING, ERROR, CRITICAL

        'do_pub_checks' Whether to perform checks which may  only  make  sense
        for published packages. Set to True by default.

        'pkglint.ext.*' Multiple keys, specifying modules to load which contain
        subclasses of pkg.lint.base.Checker.  The value of this property should
        be fully specified python module name, assumed to be in $PYTHONPATH

        'pkglint.exclude' A space-separated list of fully-specified Python
        modules, classes or function names which should be omitted from the set
        of checks performed. eg.

        'pkg.lint.opensolaris.ActionChecker' or
        'my.lint.module' or
        'my.lint.module.ManifestChecker.crosscheck_paths'

        'version.pattern' A version pattern, used when specifying a build number
        to lint against (-b). If not specified in the rcfile, this pattern is
        "*,5.11-0.", matching all components of the '5.11' build, with a branch
        prefix of '0.'

        'info_classification_path' A path the file used to check the values
        of info.classification attributes in manifests.

        'use_progress_tracker' Whether to use progress tracking.

        'ignore_different_publishers' Whether to ignore differences in publisher
        when comparing package FMRIs.

        The engine has support for a "/* LINTED */"-like functionality,
        see the comment for <LintEngine>.execute()"""

        def __init__(self, formatter, verbose=False, config_file=None,
            use_tracker=None):
                """Creates a lint engine a given pkg.lint.log.LogFormatter.
                'verbose' overrides any log_level settings in the config file
                to DEBUG
                'config_file' specifies a path to a pkglintrc configuration file
                'use_tracker' overrides any pkglintrc settings to either
                explicitly enable or disable the use of a tracker, set to None,
                we don't override the config file setting."""

                # the directory used to store our user-images.
                self.basedir = None

                # a pattern used to narrow searches in the lint image
                self.pattern = None
                self.release = None
                # a prefix for the pattern used to search for given releases
                self.version_pattern = "*,5.11-0."

                # lists of checker functions and excluded checker functions
                self.checkers = []
                self.excluded_checkers = []

                # A progress tracker, used during the lint run
                self.tracker = None

                # set up our python logger
                self.logger = logging.getLogger("pkglint")

                formatter.engine = self

                # the pkglint LogFormatters we are configured with
                self.logs = [formatter]

                # whether to run checks that may only be valid for published
                # manifests
                self.do_pub_checks = True

                # whether to ignore publisher differences when comparing vers
                self.ignore_pubs = True

                self.conf = self.load_config(config_file, verbose=verbose)
                # overrides config_file entry
                if use_tracker is not None:
                        self.use_tracker = use_tracker

                self.tracker_phase = 0
                self.in_setup = False
                formatter.tracker = self.get_tracker()

                self.ref_image = None
                self.lint_image = None

                self.lint_uris = []
                self.ref_uris = []

                # a reference to the pkg.client.api for our reference and lint
                # images
                self.ref_api_inst = None
                self.lint_api_inst = None

                # manifests presented to us for parsing on the command line
                self.lint_manifests = []

                self.mf_cache = None

        def _load_checker_module(self, name, config):
                """Dynamically loads a given checker module, returning new
                instances of the checker classes the module declares,
                assuming they haven't been excluded by the config object."""

                try:
                        self.logger.debug("Loading module {0}".format(name))
                        # the fifth parameter is 'level', which defautls to -1
                        # in Python 2 and 0 in Python 3.
                        __import__(name, None, None, [])
                        (checkers, excluded) = \
                            base.get_checkers(sys.modules[name], config)
                        return (checkers, excluded)
                except (KeyError, ImportError) as err:
                        raise base.LintException(err)

        def _unique_checkers(self):
                """Ensure that the engine has unique names for all of the loaded
                checks."""

                unique_names = set()
                for checker in self.checkers:
                        if checker.name in unique_names:
                                raise LintEngineSetupException(
                                    _("loading extensions: "
                                    "duplicate checker name {name}: "
                                    "{classname}").format(
                                    name=checker.name,
                                    classname=checker))
                        unique_names.add(checker.name)
                        unique_methods = set()

                        for method, pkglint_id in checker.included_checks + \
                            checker.excluded_checks:

                                if pkglint_id in unique_methods:
                                        raise LintEngineSetupException(_(
                                            "loading extension "
                                            "{checker}: duplicate pkglint_id "
                                            "{pkglint_id} in {method}").format(
                                            checker=checker.name,
                                            pkglint_id=pkglint_id,
                                            method=method))
                                unique_methods.add(pkglint_id)

        def load_config(self, config, verbose=False):
                """Loads configuration from supplied config file, allowing
                a verbosity override."""

                try:
                        conf = pkg.lint.config.PkglintConfig(
                            config_file=config).config
                except (pkg.lint.config.PkglintConfigException) as err:
                        raise LintEngineSetupException(err)

                excl = []

                try:
                        excl = conf.get("pkglint", "pkglint.exclude")
                        if excl is None:
                                excl = ""
                        else:
                                excl = excl.split()
                except configparser.NoOptionError:
                        pass

                try:
                        self.version_pattern = conf.get("pkglint",
                            "version.pattern")
                except configparser.NoOptionError:
                        pass

                for key, value in conf.items("pkglint"):
                        if "pkglint.ext" in key:
                                if value in excl:
                                        # want to exclude everything from here
                                        (checkers, exclude) = \
                                            self._load_checker_module(value,
                                            conf)
                                        self.excluded_checkers.extend(checkers)
                                        self.excluded_checkers.extend(exclude)
                                        continue
                                try:
                                        (checkers, exclude) = \
                                            self._load_checker_module(value,
                                            conf)
                                        self.checkers.extend(checkers)
                                        self.excluded_checkers.extend(exclude)

                                except base.LintException as err:
                                        raise LintEngineSetupException(
                                            _("Error parsing config value for "
                                            "{key}: {err}").format(**locals()))

                self._unique_checkers()

                if verbose:
                        for lint_log in self.logs:
                                lint_log.level = "DEBUG"
                else:
                        for lint_log in self.logs:
                                lint_log.level = conf.get("pkglint",
                                    "log_level")

                try:
                        self.do_pub_checks = conf.getboolean("pkglint",
                            "do_pub_checks")
                except configparser.NoOptionError:
                        pass

                try:
                        self.use_tracker = conf.get("pkglint",
                            "use_progress_tracker").lower() == "true"
                except configparser.NoOptionError:
                        pass

                try:
                        self.ignore_pubs = conf.get("pkglint",
                            "ignore_different_publishers").lower() == "true"
                except configparser.NoOptionError:
                        pass

                return conf

        def setup(self, lint_manifests=[], ref_uris=[], lint_uris=[],
            cache=None, pattern=None, release=None):
                """Starts a pkglint session, creates our image, pulls manifests,
                etc. from servers if necessary.

                'cache' An area where we create images to access repos for both
                reference and linting purposes

                'lint_manifests' An array of paths to manifests for linting

                'ref_uris' A list of repositories which will be added to the
                image used as a reference for linting

                'lint_uris' A list of repositories which will be added to th
                image we want to lint

                'pattern' A regexp to match the packages we want to lint, if
                empty, we match everything.  Note that this is only applied when
                searching for packages to lint: we lint against all packages for
                a given release in the reference repository (if configured)

                'release' A release value that narrows the set of packages we
                lint with.  This affects both the packages presented for linting
                as well as the packages in the repository we are linting
                against. If release if set to None, we lint with and against the
                latest available packages in the repositories."""

                self.ref_uris = ref_uris
                self.lint_uris = lint_uris
                self.lint_manifests = lint_manifests
                self.lint_manifests.sort(key=_manifest_sort_key)
                self.pattern = pattern
                self.release = release
                self.in_setup = True
                self.mf_cache = LintEngineCache(self.version_pattern,
                    release=release)

                if not cache and not lint_manifests:
                        raise LintEngineSetupException(
                            _("Either a cache directory, or some local "
                            "manifest files must be provided."))

                if not cache and (ref_uris or lint_uris):
                        raise LintEngineSetupException(
                            _("A cache directory must be provided if using "
                            "reference or lint repositories."))

                if cache:
                        self.basedir = os.path.abspath(cache)

                        try:
                                self.lint_image = os.path.join(self.basedir,
                                    "lint_image")

                                if os.path.exists(self.lint_image):
                                        self.lint_api_inst = self._get_image(
                                            self.lint_image)
                                        if self.lint_api_inst and lint_uris:
                                                self.tracker.flush()
                                                self.logger.info(
                                                    _("Ignoring -l option, "
                                                    "existing image found."))

                                # only create a new image if we've not been
                                # able to load one, and we have been given a uri
                                if not self.lint_api_inst and lint_uris:
                                        self.lint_api_inst = self._create_image(
                                            self.lint_image, self.lint_uris)

                                if self.lint_api_inst:
                                        self.tracker_phase = \
                                            self.tracker_phase + 1
                                        self.mf_cache.seed_latest(
                                            self.lint_api_inst,
                                            self.get_tracker(),
                                            self.tracker_phase)

                        except LintEngineException as err:
                                raise LintEngineSetupException(
                                    _("Unable to create lint image: {0}").format(
                                    str(err)))
                        try:
                                self.ref_image = os.path.join(self.basedir,
                                    "ref_image")
                                if os.path.exists(self.ref_image):
                                        self.ref_api_inst = self._get_image(
                                            self.ref_image)
                                        if self.ref_api_inst and ref_uris:
                                                self.tracker.flush()
                                                self.logger.info(
                                                    _("Ignoring -r option, "
                                                    "existing image found."))

                                # only create a new image if we've not been
                                # able to load one, and we have been given a uri
                                if not self.ref_api_inst and ref_uris:
                                        if not (self.lint_api_inst or \
                                            lint_manifests):
                                                raise LintEngineSetupException(
                                                    "No lint image or manifests"
                                                    " provided.")
                                        self.ref_api_inst = self._create_image(
                                            self.ref_image, self.ref_uris)

                                if self.ref_api_inst:
                                        self.tracker_phase = \
                                            self.tracker_phase + 1
                                        self.mf_cache.seed_latest(
                                            self.ref_api_inst,
                                            self.get_tracker(),
                                            self.tracker_phase)

                        except LintEngineException as err:
                                raise LintEngineSetupException(
                                    _("Unable to create reference image: {0}").format(
                                    str(err)))

                        if not (self.ref_api_inst or self.lint_api_inst):
                                raise LintEngineSetupException(
                                    _("Unable to access any pkglint images "
                                   "under {0}").format(cache))

                for checker in self.checkers:
                        checker.startup(self)

                self.get_tracker().lint_done()
                self.in_setup = False

        def execute(self):
                """Run the checks that have been configured for this engine.
                We run checks on all lint_manifests as well as all manifests
                in a configured lint repository that match both our pattern
                and release (if they have been configured).

                We allow for pkg.linted=True and pkg.linted.<name>=True, where
                <name> is a substring of a pkglint id to skip logging errors
                for that action or manifest.

                As much of the pkg.linted functionality as possible is handled
                by the logging system, in combination with the engine calling
                advise_loggers() as appropriate, however some ManifestChecker
                methods may still need to use engine.linted() or
                <LintEngine>.advise_loggers() manually when iterating over
                manifest actions in order to properly respect pkg.linted
                attributes."""

                manifest_checks = []
                action_checks = []
                count = 0
                for checker in self.checkers:

                        count = count + len(checker.included_checks)
                        if isinstance(checker, base.ManifestChecker):
                                manifest_checks.append(checker)
                        elif isinstance(checker, base.ActionChecker):
                                action_checks.append(checker)
                        else:
                                raise LintEngineSetupException(
                                    _("{0} does not subclass a known "
                                    "Checker subclass intended for use by "
                                    "pkglint extensions").format(str(checker)))

                self.tracker.flush()
                self.logger.debug(_("Total number of checks found: {0}").format(
                    count))

                for mf in self.lint_manifests:
                        self._check_manifest(mf, manifest_checks,
                            action_checks)

                for manifest in self.gen_manifests(self.lint_api_inst,
                    pattern=self.pattern, release=self.release):
                        self._check_manifest(manifest, manifest_checks,
                            action_checks)
                self.tracker.flush()

        def gen_manifests(self, api_inst, pattern=None, release=None):
                """A generator to return package manifests for a given image.
                With a given pattern, it narrows the set of manifests
                returned to match that pattern.

                With the given 'release' number, it searches for manifests for
                that release using "<pattern>@<version.pattern><release>"
                where <version.pattern> is set in pkglintrc and
                <pattern> and <release> are the keyword arguments to this
                method. """

                if not api_inst:
                        return

                tracker = self.get_tracker()
                if self.in_setup:
                        pt = tracker.LINT_PHASETYPE_SETUP
                else:
                        pt = tracker.LINT_PHASETYPE_EXECUTE
                tracker.lint_next_phase(
                    self.mf_cache.count_latest(api_inst, pattern), pt)

                for m in self.mf_cache.gen_latest(api_inst, pattern):
                        tracker.lint_add_progress()
                        yield m
                return

        EXACT = 0
        LATEST_SUCCESSOR = 1

        def get_manifest(self, pkg_name, search_type=EXACT, reference=False):
                """Returns the first available manifest for a given package
                name, searching hierarchically in the lint manifests,
                the lint_repo or the ref_repo for that single package.

                By default, we search for an exact match on the provided
                pkg_name, throwing a LintEngineException if we get more than
                one match for the supplied pkg_name.
                When search_type is LintEngine.LATEST_SUCCESSOR, we return the
                most recent successor of the provided package, using the
                lint_fmri_successor() method defined in this module.

                If 'reference' is True, only search for the package using the
                reference image. If no reference image has been configured, this
                raises a pkg.lint.base.LintException.
                """

                if not pkg_name.startswith("pkg:/"):
                        pkg_name = "pkg:/{0}".format(pkg_name)

                def build_fmri(pkg_name):
                        """builds a pkg.fmri.PkgFmri from a string."""
                        try:
                                fmri = pkg.fmri.PkgFmri(pkg_name)
                                return fmri
                        except pkg.fmri.IllegalFmri:
                                try:
                                        # FMRIs listed as dependencies often
                                        # omit build_release, use a dummy one
                                        # for now
                                        fmri = pkg.fmri.PkgFmri(pkg_name)
                                        return fmri
                                except:
                                        msg = _("unable to construct fmri from "
                                            "{0}").format(pkg_name)
                                        raise base.LintException(msg)

                def get_fmri(api_inst, pkg_name):
                        """Retrieve an fmri string that matches pkg_name."""

                        if "*" in pkg_name or "?" in pkg_name:
                                raise base.LintException(
                                    _("invalid pkg name {0}").format(pkg_name))

                        if "@" not in pkg_name and self.release:
                                pkg_name = "{0}@{1}{2}".format(
                                    pkg_name, self.version_pattern,
                                    self.release)

                        fmris = []
                        for item in api_inst.get_pkg_list(
                            pkg.client.api.ImageInterface.LIST_ALL,
                            patterns=[pkg_name], variants=True,
                            return_fmris=True):
                                fmris.append(item[0])

                        fmri_list = []
                        for item in fmris:
                                fmri_list.append(item.get_fmri())

                        if len(fmri_list) == 1:
                                return fmri_list[0]

                        elif len(fmri_list) == 0:
                                return None
                        else:
                                # we expected to get only 1 hit, so
                                # something has gone wrong
                                raise LintEngineException(
                                    _("get_fmri(pattern) {pattern} "
                                    "matched {count} packages: "
                                    "{pkgs}").format(
                                    pattern=pkg_name,
                                    count=len(fmri_list),
                                    pkgs=" ".join(fmri_list)
                                    ))

                def mf_from_image(api_inst, pkg_name, search_type):
                        """Fetch a manifest for the given package name using
                        the ImageInterface provided."""
                        if not api_inst:
                                return None

                        search_fmri = build_fmri(pkg_name)
                        if search_type == self.LATEST_SUCCESSOR:
                                # we want to normalize the pkg_name, removing
                                # the publisher, if any.
                                name = "pkg:/{0}".format(search_fmri.get_name())
                                mf = self.mf_cache.get_latest(api_inst, name)
                                if not mf:
                                        return
                                # double-check the publishers match, since we
                                # searched for just a package name
                                if search_fmri.publisher:
                                        if search_fmri.publisher == \
                                            mf.fmri.publisher:
                                                return mf
                                else:
                                        return mf

                        # We've either not found a matching publisher, or we're
                        # doing an exact search.
                        try:
                                mf = self.mf_cache.get(api_inst, pkg_name)
                                return mf
                        except KeyError:
                                mf = None
                                fmri = get_fmri(api_inst, pkg_name)
                                if fmri:
                                        mf = api_inst.get_manifest(
                                            pkg.fmri.PkgFmri(fmri))
                                self.mf_cache.add(api_inst, pkg_name, mf)
                                return mf

                # search hierarchically for the given package name in our
                # local manifests, using our lint image, or using our reference
                # image and return a manifest for that package.
                if reference:
                     if not self.ref_api_inst:
                             raise base.LintException(
                                _("No reference repository has been "
                                "configured"))
                     return mf_from_image(self.ref_api_inst, pkg_name,
                        search_type)

                for mf in self.lint_manifests:
                        search_fmri = build_fmri(pkg_name)
                        if search_type == self.LATEST_SUCCESSOR and \
                            lint_fmri_successor(mf.fmri, search_fmri,
                                ignore_pubs=self.ignore_pubs):
                                return mf

                        if str(mf.fmri) == pkg_name:
                                return mf
                        if mf.fmri.get_name() == pkg_name:
                                return mf
                mf = mf_from_image(self.lint_api_inst, pkg_name, search_type)
                if mf:
                        return mf
                # fallback to our reference api, returning None if that's
                # what we were given.
                return mf_from_image(self.ref_api_inst, pkg_name, search_type)

        def _get_image(self, image_dir):
                """Return a pkg.client.api.ImageInterface for the provided
                image directory."""

                cdir = os.getcwd()
                tracker = self.get_tracker()
                api_inst = None
                try:
                        api_inst = pkg.client.api.ImageInterface(
                            image_dir, CLIENT_API_VERSION,
                            tracker, None, PKG_CLIENT_NAME)

                        if api_inst.root != image_dir:
                                api_inst = None
                        else:
                                # given that pkglint is expected to be used
                                # during manifest development, we always want
                                # to refresh now, rather than waiting for some
                                # update interval
                                api_inst.refresh(immediate=True)
                except Exception as err:
                        raise LintEngineSetupException(
                            _("Unable to get image at {dir}: {reason}").format(
                            dir=image_dir,
                            reason=str(err)))

                # restore the current directory, which ImageInterace had changed
                os.chdir(cdir)
                return api_inst

        def _create_image(self, image_dir, repo_uris):
                """Create image in the given image directory. For now, only
                a single publisher is supported per image."""

                tracker = self.get_tracker()

                is_zone = False
                refresh_allowed = True

                self.tracker.flush()
                self.logger.debug(_("Creating image at {0}").format(image_dir))

                # Check to see if a scheme was used, if not, treat it as a
                # file:// URI, and get the absolute path.  Missing or invalid
                # repositories will be caught by pkg.client.api.image_create.
                for i, uri in enumerate(repo_uris):
                        if not urlparse(uri).scheme:
                                repo_uris[i] = "file://{0}".format(
                                    quote(os.path.abspath(uri)))

                try:
                        api_inst = pkg.client.api.image_create(
                            PKG_CLIENT_NAME, CLIENT_API_VERSION, image_dir,
                            pkg.client.api.IMG_TYPE_USER, is_zone,
                            facets=pkg.facet.Facets(), force=False,
                            progtrack=tracker, refresh_allowed=refresh_allowed,
                            repo_uri=repo_uris[0])
                except (ApiException, OSError, IOError) as err:
                        raise LintEngineSetupException(err)

                # Check to see if multiple repositories are specified.
                repo_uris.pop(0)
                if repo_uris:
                        try:
                                self._set_publisher(api_inst, repo_uris)
                        except ApiException as e:
                                api_inst._img.destroy()
                                if os.path.abspath(image_dir) != "/" and \
                                    os.path.exists(image_dir):
                                        shutil.rmtree(image_dir, True)
                                raise LintEngineSetupException(e)

                return api_inst

        def _set_publisher(self, api_inst, repo_uris):
                """Helper function to set publishers on a ref or lint image."""

                for repo_uri in repo_uris:
                        repo = publisher.RepositoryURI(repo_uri)
                        pubs = []
                        try:
                                pubs = api_inst.get_publisherdata(repo=repo)
                        except apx.UnsupportedRepositoryOperation:
                                raise

                        for pub in sorted(pubs):
                                prefix = pub.prefix
                                src_repo = pub.repository
                                if api_inst.has_publisher(prefix=prefix):
                                        add_origins = []
                                        dest_pub = api_inst.get_publisher(
                                            prefix=prefix, duplicate=True)
                                        dest_repo = dest_pub.repository
                                        # dest_repo.origins is not None here
                                        # after invoking api.image_create()
                                        # in _create_image().
                                        if not dest_repo.has_origin(repo_uri):
                                                add_origins = [repo_uri]

                                        if src_repo:
                                                # Add unknown origins but avoid
                                                # duplicates.
                                                add_origins = [
                                                    u.uri
                                                    for u in src_repo.origins
                                                    if u.uri not in \
                                                        dest_repo.origins
                                                ]

                                        for u in add_origins:
                                                dest_repo.add_origin(u)

                                        api_inst.update_publisher(dest_pub,
                                            refresh_allowed=False)
                                else:
                                        if not src_repo:
                                                # Repository configuration info
                                                # was not provided, assume
                                                # origin is repo_uri.
                                                pub.repository = \
                                                    publisher.Repository(
                                                    origins=[repo_uri])
                                        elif not src_repo.origins:
                                                # No origin was provided in
                                                # repository configuration,
                                                # assume origin is repo_uri.
                                                src_repo.add_origin(repo_uri)

                                        api_inst.add_publisher(pub,
                                            refresh_allowed=False)

        def _check_manifest(self, manifest, manifest_checks, action_checks):
                """Check a given manifest."""

                self.debug(_("Checking {0}").format(manifest.fmri),
                    "pkglint001.3")

                for checker in manifest_checks:
                        checker.check(manifest, self)

                if action_checks:
                        for action in manifest.gen_actions():
                                self._check_action(action, manifest,
                                    action_checks)

        def _check_action(self, action, manifest, action_checks):
                """Check a given action."""

                for checker in action_checks:
                        checker.check(action, manifest, self)

        def advise_loggers(self, action=None, manifest=None):
                """Called to advise any loggers we have set that we're about
                to perform lint checks on the given action or manifest.

                In particular, this is used to let the logger objects access
                the manifest or action being linted without needing to pass
                those objects each time we log a message.

                Care must be taken in base.ManifestChecker methods to call
                this any time they're iterating over actions and are likely to
                report lint errors that may be related to that action.  When
                finished iterating, they should re-call this method with only
                the manifest keyword argument, to clear the last action used.

                Between each Checker method invocation, the Checker subclass
                calls this automatically to clear any state set by those method
                calls.
                """
                for log in self.logs:
                        log.advise(action=action, manifest=manifest)

        # convenience methods to log lint messages to all loggers
        # configured for this engine
        def debug(self, message, msgid=None, ignore_linted=False):
                """Log a debug message to all loggers."""
                for log in self.logs:
                        log.debug(message, msgid=msgid,
                            ignore_linted=ignore_linted)

        def info(self, message, msgid=None, ignore_linted=False):
                """Log an info message to all loggers."""
                for log in self.logs:
                        log.info(message, msgid=msgid,
                            ignore_linted=ignore_linted)

        def warning(self, message, msgid=None, ignore_linted=False):
                """Log a warning message to all loggers."""
                for log in self.logs:
                        log.warning(message, msgid=msgid,
                            ignore_linted=ignore_linted)

        def error(self, message, msgid=None, ignore_linted=False):
                """Log an error message to all loggers."""
                for log in self.logs:
                        log.error(message, msgid=msgid,
                            ignore_linted=ignore_linted)

        def critical(self, message, msgid=None, ignore_linted=False):
                """Log a critical message to all loggers."""
                for log in self.logs:
                        log.critical(message, msgid=msgid,
                            ignore_linted=ignore_linted)

        def skip_check_msg(self, action, msgid):
                """Log a message saying we're skipping a particular check."""
                self.info(_("Not running {check} checks on linted action "
                    "{action}").format(check=msgid, action=str(action)),
                    msgid="pkglint001.4", ignore_linted=True)

        def teardown(self, clear_cache=False):
                """Ends a pkglint session.
                clear_cache    False by default, True causes the cache to be
                               destroyed."""
                for checker in self.checkers:
                        try:
                                checker.shutdown(self)
                        except base.LintException as err:
                                self.error(err)
                self.checkers = []

                # Reset the API object before destroying it; because it does a
                # chdir(), we need to save and restore our cwd.
                cwd = os.getcwd()
                if self.lint_api_inst:
                        self.lint_api_inst.reset()
                os.chdir(cwd)
                self.lint_api_inst = None

                if clear_cache:
                        shutil.rmtree(self.basedir)
                self.advise_loggers()

        def get_tracker(self):
                """Creates a ProgressTracker if we don't already have one,
                otherwise resetting our current tracker and returning it"""

                if self.tracker:
                        if not self.in_setup:
                                self.tracker.reset()
                        self.tracker.set_major_phase(self.tracker.PHASE_UTILITY)
                        return self.tracker
                if not self.use_tracker:
                        self.tracker = progress.NullProgressTracker()
                else:
                        try:
                                self.tracker = \
                                    progress.FancyUNIXProgressTracker()
                        except progress.ProgressTrackerException:
                                self.tracker = \
                                    progress.CommandLineProgressTracker()
                self.tracker.set_major_phase(self.tracker.PHASE_UTILITY)
                return self.tracker

        def follow_renames(self, pkg_name, target=None, old_mfs=[],
            warn_on_obsolete=False, legacy=False):
                """Given a package name, and an optional target pfmri that we
                expect to be ultimately renamed to, follow package renames from
                pkg_name, looking for the package we expect to be at the end of
                the chain.

                If there was a break in the renaming chain, we return None.
                old_mfs, if passed, should be a list of manifests that were
                sources of this rename.

                If legacy is True, as well as checking that the target
                name was reached, we also look for the leaf-name of the target.
                This lets legacy action checking function properly, allowing,
                say pkg:/SUNWbip or pkg:/compatibility/package/SUNWbip to
                satisfy the rename check.
                """

                # When doing legacy action checks, the leaf of the target pkg
                # matching the pkg_name is enough so long as that package is
                # not marked as 'pkg.renamed'
                if legacy and target:
                        leaf_name = target.get_name().split("/")[-1]
                        if leaf_name == pkg_name:
                                leaf_mf = self.get_manifest(target.get_name(),
                                    search_type=self.LATEST_SUCCESSOR)
                                if leaf_mf and leaf_mf.get("pkg.renamed",
                                    "false") == "false":
                                        return leaf_mf

                mf = self.get_manifest(pkg_name,
                    search_type=self.LATEST_SUCCESSOR)

                if not mf:
                        return None

                if warn_on_obsolete and "pkg.obsolete" in mf:
                        raise base.LintException(
                            _("obsolete package: {0}").format(mf.fmri))

                # if we're trying to rename to a package in our history,
                # we should complain
                for old_mf in old_mfs:
                        if old_mf.fmri.get_name() == mf.fmri.get_name():
                                old_mfs.append(mf)
                                raise base.LintException(
                                    _("loop detected in rename: {0}").format(
                                    " -> ".join(str(s.fmri) for s in old_mfs)))

                if "pkg.renamed" in mf and \
                    mf["pkg.renamed"].lower() == "true":

                        old_mfs.append(mf)

                        for dep in mf.gen_actions_by_type("depend"):
                                # disregard dependencies on incorporations
                                if "incorporation" in dep.attrs["fmri"]:
                                        continue
                                follow = dep.attrs["fmri"]

                                # the engine's cache lookup doesn't include
                                # versions, so remove those and lookup the
                                # latest available version of this dependency
                                if "@" in follow:
                                        follow = follow.split("@")[0]
                                mf = self.follow_renames(follow,
                                    target=target, old_mfs=old_mfs,
                                    warn_on_obsolete=warn_on_obsolete,
                                    legacy=legacy)

                                # we can stop looking if we've found a package
                                # of which our target is a successor
                                if target and mf and \
                                    lint_fmri_successor(target, mf.fmri,
                                        ignore_pubs=self.ignore_pubs):
                                        return mf
                return mf

        def get_param(self, key, action=None, manifest=None):
                """Returns a string value of a given pkglint parameter,
                intended for use by pkglint Checker objects to provide hints as
                to how particular checks should be run.

                Keys are searched for first in the action, if provided, then as
                manifest attributes, finally falling back to the pkglintrc
                config file.

                The return value is a space-separated string of parameters.

                When searching for keys in the manifest or action, we prepend
                "pkg.lint" to the key name to ensure that we play in our own
                namespace and don't clash with other manifest or action attrs.
                """

                param_key = "pkg.lint.{0}".format(key)
                val = None
                if action and param_key in action.attrs:
                        val = action.attrs[param_key]
                if manifest and param_key in manifest:
                        val = manifest[param_key]
                if val:
                        if isinstance(val, six.string_types):
                                return val
                        else:
                                return " ".join(val)
                try:
                        val = self.conf.get("pkglint", key)
                        if val:
                                return val.replace("\n", " ")
                except configparser.NoOptionError:
                        return None

        def get_attr_action(self, attr, manifest):
                """Return the AttributeAction that sets a given attribute in a
                manifest.

                This is available for clients, particularly ManifestCheckers
                that need to see whether a lint flag has been set on a given
                'set' action.
                """
                if attr not in manifest:
                        raise KeyError(
                            _("{0} is not set in manifest").format(attr))
                for action in manifest.gen_actions_by_type("set"):
                        if action.attrs.get("name", "") == attr:
                                return action
                return None

        def linted(self, action=None, manifest=None, lint_id=None):
                """Determine whether pkg.linted.* flags are present on the
                action and/or manifest passed as arguments.  If lint_id is set,
                we look for pkg.linted.<lint_id> attributes as well."""
                ret = False
                try:
                        ret = base.linted(action=action, manifest=manifest,
                            lint_id=lint_id)
                except base.DuplicateLintedAttrException as err:
                        self.error(err, msgid="pkglint001.6")
                return ret


def lint_fmri_successor(new, old, ignore_pubs=True, ignore_timestamps=True):
        """Given two FMRIs, determine if new_fmri is a successor of old_fmri.

        This differs from pkg.fmri.is_successor() in that it treats un-versioned
        FMRIs as being newer than versioned FMRIs of the same package name,
        and un-timestamped packages as being newer than versioned FMRIs of the
        same package name and version.

        For published packages, where the version and pkg names are identical,
        but the publisher differs, it also treats the new package as being a
        successor of the old.

        If ignore_pubs is set, any differences in publishers between the
        provided FMRIs are ignored.

        if ignore_timestamps is set, timestamps are not used as a basis for
        comparison between new and old FMRIs.

        We use this when looking for dependencies, or when comparing
        FMRIs presented in manifests for linting against those present in an
        existing repository (where, eg. a new timestamp would be supplied to a
        package during the import process and the timestamp would not
        necessarily be in the manifest file presented for linting)
        """

        if not ignore_pubs and new.publisher != old.publisher:
                return False

        new_name = new.get_name()
        old_name = old.get_name()

        if new_name != old_name:
                return False

        if not new.has_version():
                return True

        # compare everything except the timestamp
        if new.has_version() and old.has_version():
                if new.version.release > old.version.release:
                        return True
                if new.version.release < old.version.release:
                        return False

                if new.version.branch > old.version.branch:
                        return True
                if new.version.branch < old.version.branch:
                        return False

                if new.version.build_release > old.version.build_release:
                        return True
                if new.version.build_release < old.version.build_release:
                        return False
                if not ignore_timestamps:
                        new_ts = new.version.get_timestamp()
                        old_ts = old.version.get_timestamp()
                        if new_ts > old_ts:
                                return True
                        if new_ts < old_ts:
                                return False

        # everything is equal, or old has no version and we'll favour new
        return True

def _manifest_sort_key(mf):
        """The lint engine uses the FMRI of a package to deterine the order in
        which to iterate over manifests.  This is done using the 'key' attribute
        to the Python sort() and sorted() methods."""
        if mf.fmri:
                return mf.fmri
        return mf.get("pkg.fmri")
