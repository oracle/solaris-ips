#! /usr/bin/python
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
# Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.
#

from pkg.api_common import PackageInfo
import pkg.client.api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress
import pkg.client.publisher as publisher

import pkg.lint.base as base
import pkg.lint.config
import pkg.lint.log as log

import pkg.fmri

import ConfigParser
import logging
import os
import shutil
import sys

PKG_CLIENT_NAME = "pkglint"
CLIENT_API_VERSION = 46
pkg.client.global_settings.client_name = PKG_CLIENT_NAME

class LintEngineException(Exception):
        """An exception thrown when something fatal goes wrong with the engine.
            """
        def __unicode__(self):
                # To workaround python issues 6108 and 2517, this provides a
                # a standard wrapper for this class' exceptions so that they
                # have a chance of being stringified correctly.
                return str(self)


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

        The engine has support for a "/* LINTED */"-like functionality,
        omitting lint checks for actions or manifests that contain
        a pkg.linted attribute set to True."""

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

                # the pkglint LogFormatters we are configured with
                self.logs = [formatter]

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

                # whether to run checks that may only be valid for published
                # manifests
                self.do_pub_checks = True

        def _load_checker_module(self, name, config):
                """Dynamically loads a given checker module, returning new
                instances of the checker classes the module declares,
                assuming they haven't been excluded by the config object."""

                try:
                        self.logger.debug("Loading module %s" % name)
                        __import__(name, None, None, [], -1)
                        (checkers, excluded) = \
                            base.get_checkers(sys.modules[name], config)
                        return (checkers, excluded)
                except (KeyError, ImportError), err:
                        raise base.LintException(err)

        def load_config(self, config, verbose=False):
                """Loads configuration from supplied config file, allowing
                a verbosity override."""

                conf = pkg.lint.config.PkglintConfig(config_file=config).config
                excl = []

                try:
                        excl = conf.get("pkglint", "pkglint.exclude").split()
                except ConfigParser.NoOptionError:
                        pass

                try:
                        self.version_pattern = conf.get("pkglint",
                            "version.pattern")
                except ConfigParser.NoOptionError:
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

                                except base.LintException, err:
                                        raise LintEngineException(
                                            _("Error parsing config value for "
                                            "%(key)s: %(err)s") % locals())

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
                except ConfigParser.NoOptionError:
                        pass

                try:
                        self.use_tracker = conf.get("pkglint",
                            "use_progress_tracker").lower() == "true"

                except ConfigParser.NoOptionError:
                        pass

                return conf

        def setup(self, lint_manifests=[], ref_uris=[], lint_uris=[],
            cache=None, pattern="*", release=None):
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
                self.pattern = pattern
                self.release = release
                self.in_setup = True

                if not cache and not lint_manifests:
                        raise LintEngineException(
                            _("Either a cache directory, or some local "
                            "manifest files must be provided."))

                if not cache and (ref_uris or lint_uris):
                        raise LintEngineException(
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
                                                self.logger.info(
                                                    _("Ignoring -l option, "
                                                    "existing image found."))

                                # only create a new image if we've not been
                                # able to load one, and we have been given a uri
                                if not self.lint_api_inst and lint_uris:
                                        self.lint_api_inst = self._create_image(
                                            self.lint_image, self.lint_uris)

                        except LintEngineException, err:
                                raise LintEngineException(
                                    _("Unable to create lint image: %s") %
                                    str(err))
                        try:
                                self.ref_image = os.path.join(self.basedir,
                                    "ref_image")
                                if os.path.exists(self.ref_image):
                                        self.ref_api_inst = self._get_image(
                                            self.ref_image)
                                        if self.ref_api_inst and ref_uris:
                                                self.logger.info(
                                                    _("Ignoring -r option, "
                                                    "existing image found."))

                                # only create a new image if we've not been
                                # able to load one, and we have been given a uri
                                if not self.ref_api_inst and ref_uris:
                                        if not (self.lint_api_inst or \
                                            lint_manifests):
                                                raise LintEngineException(
                                                    "No lint image or manifests"
                                                    " provided.")
                                        self.ref_api_inst = self._create_image(
                                            self.ref_image, self.ref_uris)

                        except LintEngineException, err:
                                raise LintEngineException(
                                    _("Unable to create reference image: %s") %
                                    str(err))

                        if not (self.ref_api_inst or self.lint_api_inst):
                                raise LintEngineException(
                                    _("Unable to access any pkglint images "
                                   "under %s") % cache)

                for checker in self.checkers:
                        checker.startup(self)
                self.get_tracker().index_done()
                self.in_setup = False
                

        def execute(self):
                """Run the checks that have been configured for this engine.
                We run checks on all lint_manifests as well as all manifests
                in a configured lint repository that match both our pattern
                and release (if they have been configured)."""

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
                                raise LintEngineException(
                                    _("%s does not subclass a known "
                                    "Checker subclass intended for use by "
                                    "pkglint extensions") % str(checker))

                self.logger.debug(_("Total number of checks found: %s") % count)

                for mf in self.lint_manifests:
                        self._check_manifest(mf, manifest_checks,
                            action_checks)

                for manifest in self.gen_manifests(self.lint_api_inst,
                    pattern=self.pattern, release=self.release):
                        self._check_manifest(manifest, manifest_checks,
                            action_checks)

        def gen_manifests(self, api_inst, pattern="*", release=None):
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

                if release:
                        search_type = pkg.client.api.ImageInterface.LIST_ALL
                        pattern_list = ["%s@%s%s" % (pattern,
                            self.version_pattern, release)]
                else:
                        search_type = pkg.client.api.ImageInterface.LIST_NEWEST
                        pattern_list = [pattern]

                packages = {}

                for item in api_inst.get_pkg_list(
                    search_type, patterns=pattern_list):
                        pub_name, stem, version = item[0]
                        pub = api_inst.get_publisher(prefix=pub_name)
                        fmri ="pkg://%s/%s@%s" % (pub, stem, version)
                        if release:
                                # when we're doing searches for a single
                                # release, we may have multiple versions of a
                                # package on the server for that release - we
                                # only want the most recent one available.
                                if stem in packages:
                                        candidate = pkg.fmri.PkgFmri(fmri)
                                        if candidate.is_successor(packages[stem]):
                                                packages[stem] = candidate
                                else:
                                        packages[stem] = pkg.fmri.PkgFmri(fmri)
                        else:
                                packages[stem] = pkg.fmri.PkgFmri(fmri)

                if not packages:
                        raise LintEngineException(
                            _("No packages matched %s") % pattern_list[0])

                keys = packages.keys()
                keys.sort()

                tracker = self.get_tracker()
                if self.in_setup:
                        self.tracker_phase = self.tracker_phase + 1
                else:
                        self.tracker_phase = 0
                tracker.index_set_goal(self.tracker_phase, len(packages))

                for key in keys:
                        fmri = packages[key]
                        tracker.index_add_progress()
                        yield api_inst.get_manifest(fmri)

                if not self.in_setup:
                        tracker.index_done()

        EXACT = 0
        LATEST_SUCCESSOR = 1

        def get_manifest(self, pkg_name, search_type=EXACT):
                """Returns the first available manifest for a given package
                name, searching hierarchically in the lint manifests,
                the lint_repo or the ref_repo for that single package.

                By default, we search for an exact match on the provided
                pkg_name, throwing a LintEngineException if we get more than
                one match for the supplied pkg_name.
                When search_type is LintEngine.LATEST_SUCCESSOR, we return the
                most recent successor of the provided package, using the
                lint_fmri_successor() method defined in this module.
                """

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
                                        fmri = pkg.fmri.PkgFmri(pkg_name,
                                            build_release="5.11")
                                        return fmri
                                except:
                                        msg = _("unable to construct fmri from %s") % \
                                            pkg_name
                                        raise base.LintException(msg)

                def get_fmri(api_inst, pkg_name):
                        name = pkg_name

                        if not name.startswith("pkg:/"):
                                name = "pkg:/%s" % name
                        search_fmri = build_fmri(name)

                        if search_type == self.LATEST_SUCCESSOR and "@" in name:
                                name = search_fmri.get_pkg_stem()

                        # Make sure we've been given something sane to look up
                        if "*" in name or "?" in name:
                                raise base.LintException(
                                    _("invalid pkg name %s") % name)

                        fmris = []
                        for item in api_inst.get_pkg_list(
                            pkg.client.api.ImageInterface.LIST_ALL,
                            patterns=[name], variants=True, return_fmris=True):
                                fmris.append(item[0])

                        fmri_list = []
                        for item in fmris:
                                if (search_type == self.LATEST_SUCCESSOR and
                                    lint_fmri_successor(item, search_fmri)):
                                        fmri_list.append(item.get_fmri())

                                elif search_type == self.EXACT:
                                        fmri_list.append(item.get_fmri())

                        if len(fmri_list) == 1:
                                return fmri_list[0]

                        elif len(fmri_list) == 0:
                                return None
                        else:
                                if search_type == self.LATEST_SUCCESSOR:
                                        # get_pkg_list generates most recent
                                        # package first
                                        return fmri_list[0]
                                else:
                                        # we expected to get only 1 hit, so
                                        # something has gone wrong
                                        raise LintEngineException(
                                            _("get_fmri(pattern) %(pattern)s "
                                                "matched %(count)s packages: "
                                                "%(pkgs)s") %
                                                {"pattern": pkg_name,
                                                "count": len(fmri_list),
                                                "pkgs": " ".join(fmri_list)
                                                })

                for mf in self.lint_manifests:
                        search_fmri = build_fmri(pkg_name)
                        if search_type == self.LATEST_SUCCESSOR and \
                            lint_fmri_successor(mf.fmri, search_fmri):
                                return mf

                        if str(mf.fmri) == pkg_name:
                                return mf
                        if mf.fmri.get_name() == pkg_name:
                                return mf

                if self.lint_api_inst:
                        fmri = get_fmri(self.lint_api_inst, pkg_name)
                        if fmri:
                                mf = self.lint_api_inst.get_manifest(
                                    pkg.fmri.PkgFmri(fmri))
                                if mf:
                                        return mf

                if self.ref_api_inst:
                        fmri = get_fmri(self.ref_api_inst, pkg_name)
                        if fmri:
                                mf = self.ref_api_inst.get_manifest(
                                    pkg.fmri.PkgFmri(fmri))
                                if mf:
                                        return mf

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
                except Exception, err:
                        raise LintEngineException(
                            _("Unable to get image at %(dir)s: %(reason)s") %
                            {"dir": image_dir,
                            "reason": str(err)})

                # restore the current directory, which ImageInterace had changed
                os.chdir(cdir)
                return api_inst

        def _create_image(self,  image_dir, repo_uris):
                """Create image in the given image directory. For now, only
                a single publisher is supported per image."""

                if len(repo_uris) != 1:
                        raise LintEngineException(
                            _("pkglint only supports a single publisher "
                            "per image."))

                tracker = self.get_tracker()

                is_zone = False
                refresh_allowed = True

                self.logger.debug(_("Creating image at %s") % image_dir)

                try:
                        api_inst = pkg.client.api.image_create(
                            PKG_CLIENT_NAME, CLIENT_API_VERSION, image_dir,
                            pkg.client.api.IMG_TYPE_USER, is_zone,
                            facets=pkg.facet.Facets(), force=False,
                            progtrack=tracker, refresh_allowed=refresh_allowed,
                            repo_uri=repo_uris[0])
                except (pkg.client.api_errors.ApiException, OSError), err:
                        raise LintEngineException(err)
                return api_inst

        def _check_manifest(self, manifest, manifest_checks, action_checks):
                """Check a given manifest."""

                if "pkg.linted" in manifest and \
                    manifest["pkg.linted"].lower() == "true":
                        self.info("Not checking linted manifest %s" %
                            manifest.fmri, msgid="pkglint001.1")
                        return

                self.debug(_("Checking %s") % manifest.fmri, "pkglint001.3")

                for checker in manifest_checks:
                        try:
                                checker.check(manifest, self)
                        except base.LintException, err:
                                self.error(err, msgid="lint.error")

                if action_checks:
                        for action in manifest.gen_actions():
                                try:
                                        self._check_action(action, manifest,
                                            action_checks)
                                except base.LintException, err:
                                        self.error(err, msgid="lint.error")

        def _check_action(self, action, manifest, action_checks):
                if "pkg.linted" in action.attrs and \
                    action.attrs["pkg.linted"].lower() == "true":
                        self.info("Not checking linted action %s" %
                            str(action), msgid="pkglint001.2")
                        return

                for checker in action_checks:
                        try:
                                checker.check(action, manifest, self)
                        except base.LintException, err:
                                self.error(err, msgid="lint.error")

        # convenience methods to log lint messages to all loggers
        # configured for this engine
        def debug(self, message, msgid=None):
                for log in self.logs:
                        log.debug(message, msgid=msgid)

        def info(self, message, msgid=None):
                for log in self.logs:
                        log.info(message, msgid=msgid)

        def warning(self, message, msgid=None):
                for log in self.logs:
                        log.warning(message, msgid=msgid)

        def error(self, message, msgid=None,):
                for log in self.logs:
                        log.error(message, msgid=msgid)

        def critical(self, message, msgid=None):
                for log in self.logs:
                        log.critical(message, msgid=msgid)

        def teardown(self, clear_cache=False):
                """Ends a pkglint session.
                clear_cache    False by default, True causes the cache to be
                               destroyed."""
                for checker in self.checkers:
                        try:
                                checker.shutdown(self)
                        except base.LintException, err:
                                self.error(err)
                self.checkers = []
                if clear_cache:
                        shutil.rmtree(self.basedir)

        def get_tracker(self):
                """Creates a ProgressTracker if we don't already have one,
                otherwise resetting our current tracker and returning it"""

                if self.tracker and self.in_setup:
                        return self.tracker
                if self.tracker:
                        self.tracker.reset()
                        return self.tracker
                if not self.use_tracker:
                        self.tracker = progress.QuietProgressTracker()
                else:
                        try:
                                self.tracker = progress.FancyUNIXProgressTracker()
                        except progress.ProgressTrackerException:
                                self.tracker = progress.CommandLineProgressTracker()
                return self.tracker

def lint_fmri_successor(new, old):
        """Given two FMRIs, determine if new_fmri is a successor of old_fmri.

        This differs from pkg.fmri.is_successor() in that it treats un-versioned
        FMRIs as being newer than versioned FMRIs of the same package name,
        and un-timestamped packages as being newer than versioned FMRIs of the
        same package name and version.

        We use this when looking for dependencies, or when comparing
        FMRIs presented in manifests for linting against those present in an
        existing repository (where, eg. a new timestamp would be supplied to a
        package during the import process and the timestamp would not
        necessarily be in the manifest file presented for linting)
        """
        new_name = new.get_name()
        old_name = old.get_name()
        return new.is_successor(old) or \
            (not new.has_version() and
            new_name == old_name) or \
            (not new.get_timestamp() and
            new.has_version() and old.has_version() and
            new.get_version() == old.get_version() and
            new_name == old_name)
