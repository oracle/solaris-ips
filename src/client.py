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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#
# pkg - package system client utility
#
# We use urllib2 for GET and POST operations, but httplib for PUT and DELETE
# operations.
#
# The client is going to maintain an on-disk cache of its state, so that startup
# assembly of the graph is reduced.
#
# Client graph is of the entire local catalog.  As operations progress, package
# states will change.
#
# Deduction operation allows the compilation of the local component of the
# catalog, only if an authoritative repository can identify critical files.
#
# Environment variables
#
# PKG_IMAGE - root path of target image
# PKG_IMAGE_TYPE [entire, partial, user] - type of image
#       XXX or is this in the Image configuration?

import getopt
import gettext
import itertools
import os
import re
import sys
import traceback
import urllib2
import urlparse
import errno
import socket

import pkg.client.image as image
import pkg.client.imageplan as imageplan
import pkg.client.filelist as filelist
import pkg.client.progress as progress
import pkg.client.bootenv as bootenv
import pkg.fmri as fmri
import pkg.misc as misc

def usage(usage_error = None):
        """ Emit a usage message and optionally prefix it with a more
            specific error message.  Causes program to exit. """

        pname = os.path.basename(sys.argv[0])
        if usage_error:
                print >> sys.stderr, pname + ": " + usage_error

        print >> sys.stderr, _("""\
Usage:
        pkg [options] command [cmd_options] [operands]

Basic subcommands:
        pkg install [-nvq] package...
        pkg uninstall [-nrvq] package...
        pkg list [-aHsuv] [package...]
        pkg image-update [-nvq]
        pkg refresh [--full]

Advanced subcommands:
        pkg info [pkg_fmri_pattern ...]
        pkg search [-lr] [-s server] token
        pkg verify [-fHqv] [pkg_fmri_pattern ...]
        pkg contents [-Hm] [-o attribute ...] [-s sort_key] [-t action_type ... ]
            pkg_fmri_pattern [...]
        pkg image-create [-FPUz] [--full|--partial|--user] [--zone]
            [-k ssl_key] [-c ssl_cert] -a <prefix>=<url> dir

        pkg set-authority [-P] [-k ssl_key] [-c ssl_cert]
            [-O origin_url] authority
        pkg unset-authority authority ...
        pkg authority [-H] [authname]

Options:
        --server, -s
        --image, -R

Environment:
        PKG_SERVER
        PKG_IMAGE""")
        sys.exit(2)


def error(error):
        """ Emit an error message prefixed by the command name """

        pname = os.path.basename(sys.argv[0])
        print >> sys.stderr, pname + ": " + error


# XXX Subcommands to implement:
#        pkg image-set name value
#        pkg image-unset name
#        pkg image-get [name ...]

def list_inventory(img, args):
        all_known = False
        display_headers = True
        upgradable_only = False
        verbose = False
        summary = False

        opts, pargs = getopt.getopt(args, "aHsuv")

        for opt, arg in opts:
                if opt == "-a":
                        all_known = True
                elif opt == "-H":
                        display_headers = False
                elif opt == "-s":
                        summary = True
                elif opt == "-u":
                        upgradable_only = True
                elif opt == "-v":
                        verbose = True

        if summary and verbose:
                usage(_("-s and -v may not be combined"))               

        if verbose:
                fmt_str = "%-64s %-10s %s"
        elif summary:
                fmt_str = "%-30s %s"
        else:
                fmt_str = "%-45s %-15s %-10s %s"

        img.load_catalogs(progress.NullProgressTracker())

        try:
                found = False
                for pkg, state in img.gen_inventory(pargs, all_known):
                        if upgradable_only and not state["upgradable"]:
                                continue

                        if not found:
                                if display_headers:
                                        if verbose:
                                                print fmt_str % \
                                                    ("FMRI", "STATE", "UFIX")
                                        elif summary:
                                                print fmt_str % \
                                                    ("NAME (AUTHORITY)",
                                                    "SUMMARY")
                                        else:
                                                print fmt_str % \
                                                    ("NAME (AUTHORITY)",
                                                    "VERSION", "STATE", "UFIX")
                                found = True

                        ufix = "%c%c%c%c" % \
                            (state["upgradable"] and "u" or "-",
                            state["frozen"] and "f" or "-",
                            state["incorporated"] and "i" or "-",
                            state["excludes"] and "x" or "-")

                        if pkg.preferred_authority():
                                auth = ""
                        else:
                                auth = " (" + pkg.get_authority() + ")"

                        if verbose:
                                pf = pkg.get_fmri(img.get_default_authority())
                                print "%-64s %-10s %s" % (pf, state["state"],
                                    ufix)
                        elif summary:
                                pf = pkg.get_name() + auth

                                m = img.get_manifest(pkg, filtered = True)
                                print fmt_str % (pf, m.get("description", ""))

                        else:
                                pf = pkg.get_name() + auth
                                print fmt_str % (pf, pkg.get_version(),
                                    state["state"], ufix)


                if not found:
                        if not pargs:
                                error(_("no matching packages installed"))
                        return 1
                return 0

        except RuntimeError, e:
                if not found:
                        error(_("no matching packages installed"))
                        return 1

                for pat in e.args[0]:
                        error(_("no packages matching '%s' installed") % pat)
                return 1
                img.display_inventory(args)


def get_tracker(quiet = False):
        if quiet:
                progresstracker = progress.QuietProgressTracker()
        else:
                try:
                        progresstracker = \
                            progress.FancyUNIXProgressTracker()
                except progress.ProgressTrackerException:
                        progresstracker = progress.CommandLineProgressTracker()
        return progresstracker



def installed_fmris_from_args(image, args):
        """ Helper function to translate client command line arguments
            into a list of installed fmris.  Used by info, contents, verify.

            XXX consider moving into image class
        """
        if not args:
                fmris = list(image.gen_installed_pkgs())
        else:
                try:
                        matches = image.get_matching_fmris(args)
                except KeyError:
                        error(_("no matching packages found in catalog"))
                        return 1, []

                fmris = [ m for m in matches if image.is_installed(m) ]
        return 0, fmris


def verify_image(img, args):
        opts, pargs = getopt.getopt(args, "vfqH")

        quiet = forever = verbose = False
        display_headers = True

        for opt, arg in opts:
                if opt == "-H":
                        display_headers = False
                if opt == "-v":
                        verbose = True
                elif opt == "-f":
                        forever = True
                elif opt == "-q":
                        quiet = True
                        display_headers = False

        if verbose and quiet:
                usage(_("verify: -v and -q may not be combined"))

        progresstracker = get_tracker(quiet)

        img.load_catalogs(progresstracker)

        err, fmris = installed_fmris_from_args(img, pargs)
        if err != 0:
                return err
        if not fmris:
                return 0
        

        any_errors = False

        header = False
        for f in fmris:
                pkgerr = False
                for err in img.verify(f, progresstracker,
                    verbose=verbose, forever=forever):
                        #
                        # Eventually this code should probably
                        # move into the progresstracker
                        #
                        if not pkgerr:
                                if display_headers and not header:
                                        print "%-50s %7s" % ("PACKAGE", "STATUS")
                                        header = True

                                if not quiet:
                                        print "%-50s %7s" % (f.get_pkg_stem(), "ERROR")
                                pkgerr = True

                        if not quiet:
                                print "\t%s" % err[0]
                                for x in err[1]:
                                        print "\t\t%s" % x
                if verbose and not pkgerr:
                        if display_headers and not header:
                                print "%-50s %7s" % ("PACKAGE", "STATUS")
                                header = True
                        print "%-50s %7s" % (f.get_pkg_stem(), "OK")

                any_errors = any_errors or pkgerr

        progresstracker.verify_done()
        if any_errors:
                return 1
        return 0


def image_update(img, args):
        """Attempt to take all installed packages specified to latest
        version."""

        # XXX Authority-catalog issues.
        # XXX Are filters appropriate for an image update?
        # XXX Leaf package refinements.

        opts, pargs = getopt.getopt(args, "b:nvq")

        quiet = noexecute = verbose = False
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-b":
                        filelist.FileList.maxbytes_default = int(arg)
                elif opt == "-q":
                        quiet = True

        if verbose and quiet:
                usage(_("image-update: -v and -q may not be combined"))

        progresstracker = get_tracker(quiet)
        img.load_catalogs(progresstracker)

        try:
                img.retrieve_catalogs()
        except RuntimeError, failures:
                if display_catalog_failures(failures) == 0:
                        return 1
                else:
                        return 3

        # Reload catalog.  This picks up the update from retrieve_catalogs.
        img.load_catalogs(progresstracker)

        pkg_list = [ ipkg.get_pkg_stem() for ipkg in img.gen_installed_pkgs() ]

        try:
                img.make_install_plan(pkg_list, progresstracker, verbose = verbose,
                    noexecute = noexecute)
        except RuntimeError, e:
                error(_("image-update failed: %s") % e)

        assert img.imageplan

        if img.imageplan.nothingtodo():
                print _("No updates available for this image.")
                return 0

        if noexecute:
                return 0

        try:
                be = bootenv.BootEnv(img.get_root())
        except RuntimeError:
                be = bootenv.BootEnvNull(img.get_root())

        be.init_image_recovery(img)

        try:
                img.imageplan.execute()
                be.activate_image()
                ret_code = 0
        except RuntimeError, e:
                error(_("image_update failed: %s") % e)
                be.restore_image()
                ret_code = 1
        except Exception, e:
                error(_("An unexpected error happened during image-update: %s") % e)
                be.restore_image()
                img.cleanup_downloads()
                raise

        img.cleanup_downloads()
        return ret_code


def install(img, args):
        """Attempt to take package specified to INSTALLED state.  The operands
        are interpreted as glob patterns."""

        # XXX Authority-catalog issues.

        opts, pargs = getopt.getopt(args, "nvb:f:q")

        quiet = noexecute = verbose = False
        filters = []
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-b":
                        filelist.FileList.maxbytes_default = int(arg)
                elif opt == "-f":
                        filters += [ arg ]
                elif opt == "-q":
                        quiet = True

        if not pargs:
                usage(_("install: at least one package name required"))

        if verbose and quiet:
                usage(_("install: -v and -q may not be combined"))

        progresstracker = get_tracker(quiet)

        img.load_catalogs(progresstracker)

        pkg_list = [ pat.replace("*", ".*").replace("?", ".")
            for pat in pargs ]

        try:
                img.make_install_plan(pkg_list, progresstracker, filters = filters,
                    verbose = verbose, noexecute = noexecute)
        except RuntimeError, e:
                error(_("install failed: %s") % e)
                return 1

        assert img.imageplan

        #
        # The result of make_install_plan is that an imageplan is now filled out
        # for the image.
        #
        if img.imageplan.nothingtodo():
                print _("Nothing to install in this image (is this package already installed?)")
                return 0

        if noexecute:
                return 0

        try:
                be = bootenv.BootEnv(img.get_root())
        except RuntimeError:
                be = bootenv.BootEnvNull(img.get_root())

        try:
                img.imageplan.execute()
                be.activate_install_uninstall()
                ret_code = 0
        except RuntimeError, e:
                error(_("installation failed: %s") % e)
                be.restore_install_uninstall()
                ret_code = 1
        except Exception, e:
                error(_("An unexpected error happened during installation: %s") % e)
                be.restore_install_uninstall()
                img.cleanup_downloads()
                raise

        img.cleanup_downloads()   
        return ret_code


def uninstall(img, args):
        """Attempt to take package specified to DELETED state."""

        opts, pargs = getopt.getopt(args, "nrvq")

        quiet = noexecute = recursive_removal = verbose = False
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-r":
                        recursive_removal = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-q":
                        quiet = True

        if verbose and quiet:
                usage(_("uninstall: -v and -q may not be combined"))

        progresstracker = get_tracker(quiet)

        img.load_catalogs(progresstracker)

        ip = imageplan.ImagePlan(img, progresstracker, recursive_removal)

        err = 0

        for ppat in pargs:
                rpat = re.sub("\*", ".*", ppat)
                rpat = re.sub("\?", ".", rpat)

                try:
                        matches = img.get_matching_fmris(rpat)
                except KeyError:
                        error(_("'%s' not even in catalog!") % ppat)
                        err = 1
                        continue

                pnames = [ m for m in matches if img.is_installed(m) ]

                if len(pnames) > 1:
                        error(_("'%s' matches multiple packages") % ppat)
                        for k in pnames:
                                print "\t%s" % k
                        err = 1
                        continue

                if len(pnames) < 1:
                        error(_("'%s' matches no installed packages") % \
                            ppat)
                        err = 1
                        continue

                ip.propose_fmri_removal(pnames[0])

        if err == 1:
                return err

        if verbose:
                print _("Before evaluation:")
                print ip

        ip.evaluate()
        img.imageplan = ip

        if verbose:
                print _("After evaluation:")
                ip.display()

        assert not ip.nothingtodo()

        if noexecute:
                return 0

	try:
		be = bootenv.BootEnv(img.get_root())
	except RuntimeError:
		be = bootenv.BootEnvNull(img.get_root())
               
	try:
                ip.execute()
        except RuntimeError, e:
                error(_("installation failed: %s") % e)
                be.restore_install_uninstall()
                ret_code = 1
	except:
                error(_("An unexpected error happened during uninstallation: %s") % e)
		be.restore_install_uninstall()
		raise

	if ip.state == imageplan.EXECUTED_OK:
		be.activate_install_uninstall()
	else:
		be.restore_install_uninstall()

        return err

def freeze(img, args):
        """Attempt to take package specified to FROZEN state, with given
        restrictions.  Package must have been in the INSTALLED state."""
        return 0

def unfreeze(img, args):
        """Attempt to return package specified to INSTALLED state from FROZEN
        state."""
        return 0

def search(img, args):
        """Search through the reverse index databases for the given token."""

        opts, pargs = getopt.getopt(args, "lrs:")

        local = remote = False
        servers = []
        for opt, arg in opts:
                if opt == "-l":
                        local = True
                elif opt == "-r":
                        remote = True
                elif opt == "-s":
                        if not arg.startswith("http://") and \
                            not arg.startswith("https://"):
                                arg = "http://" + arg
                        remote = True
                        servers.append({"origin": arg})

        if not local and not remote:
                local = True

        if not pargs:
                usage()

        searches = []
        if local:
                searches.append(img.local_search(pargs))
        if remote:
                searches.append(img.remote_search(pargs, servers))

        # By default assume we don't find anything.
        retcode = 1

        try:
                first = True
                for index, mfmri, action, value in itertools.chain(*searches):
                        retcode = 0
                        if first:
                                if action and value:
                                        print "%-10s %-9s %-25s %s" % ("INDEX",
                                            "ACTION", "VALUE", "PACKAGE")
                                else:
                                        print "%-10s %s" % ("INDEX", "PACKAGE")
                                first = False
                        if action and value:
                                print "%-10s %-9s %-25s %s" % (index, action,
                                    value, fmri.PkgFmri(str(mfmri)).get_short_fmri())
                        else:
                                print "%-10s %s" % (index, mfmri)

        except RuntimeError, failed:
                print >> sys.stderr, "Some servers failed to respond:"
                for auth, err in failed.args[0]:
                        if isinstance(err, urllib2.HTTPError):
                                print >> sys.stderr, "    %s: %s (%d)" % \
                                    (auth["origin"], err.msg, err.code)
                        elif isinstance(err, urllib2.URLError):
                                if isinstance(err.args[0], socket.timeout):
                                        print >> sys.stderr, "    %s: %s" % \
                                            (auth["origin"], "timeout")
                                else:
                                        print >> sys.stderr, "    %s: %s" % \
                                            (auth["origin"], err.args[0][1])

                retcode = 4

        return retcode

def info(img, args):
        """Display information about a package or packages.
        """

        # XXX Need remote-info option, to request equivalent information
        # from repository.

        opts, pargs = getopt.getopt(args, "")

        img.load_catalogs(progress.NullProgressTracker())

        err, fmris = installed_fmris_from_args(img, pargs)
        if err != 0:
                return err
        if not fmris:
                return 0
        
        manifests = ( img.get_manifest(f, filtered = True) for f in fmris )

        for i, m in enumerate(manifests):
                if i > 0:
                        print

                authority, name, version = m.fmri.tuple()
                summary = m.get("description", "")
                if authority == img.get_default_authority():
                        authority += _(" (preferred)")

                print "          Name:", name
                print "       Summary:", summary
                # XXX Hard wired for now.
                print "         State: Installed"

                # XXX even more info on the authority would be nice?
                print "     Authority:", authority
                print "       Version:", version.release
                print " Build Release:", version.build_release
                print "        Branch:", version.branch
                print "Packaging Date:", version.get_timestamp().ctime()
                if m.size > (1024 * 1024):
                        print "          Size: %.1f MB" % \
                            (m.size / float(1024 * 1024))
                elif m.size > 1024:
                        print "          Size: %d kB" % (m.size / 1024)
                else:
                        print "          Size: %d B" % m.size
                print "          FMRI:", m.fmri
                # XXX need to properly humanize the manifest.size
                # XXX add license/copyright info here?



def display_contents_results(actionlist, attrs, sort_attrs, action_types,
    display_headers):
        """ Print results of a "list" operation """

        # widths is a list of tuples of column width and justification.  Start
        # with the widths of the column headers.
        JUST_UNKN = 0
        JUST_LEFT = -1
        JUST_RIGHT = 1
        widths = [ (len(attr) - attr.find(".") - 1, JUST_UNKN)
            for attr in attrs ]
        lines = []

        for manifest, action in actionlist:
                if action_types and action.name not in action_types:
                        continue
                line = []
                for i, attr in enumerate(attrs):
                        just = JUST_UNKN
                        # As a first approximation, numeric attributes
                        # are right justified, non-numerics left.
                        try:
                                int(action.attrs[attr])
                                just = JUST_RIGHT
                        # attribute is non-numeric or is something like
                        # a list.
                        except (ValueError, TypeError):
                                just = JUST_LEFT
                        # attribute isn't in the list, so we don't know
                        # what it might be
                        except KeyError:
                                pass

                        if attr in action.attrs:
                                a = action.attrs[attr]
                        elif attr == "action.name":
                                a = action.name
                                just = JUST_LEFT
                        elif attr == "action.key":
                                a = action.attrs[action.key_attr]
                                just = JUST_LEFT
                        elif attr == "action.raw":
                                a = action
                                just = JUST_LEFT
                        elif attr == "pkg.name":
                                a = manifest.fmri.get_name()
                                just = JUST_LEFT
                        elif attr == "pkg.fmri":
                                a = manifest.fmri
                                just = JUST_LEFT
                        elif attr == "pkg.shortfmri":
                                a = manifest.fmri.get_short_fmri()
                                just = JUST_LEFT
                        elif attr == "pkg.authority":
                                a = manifest.fmri.get_authority()
                                just = JUST_LEFT
                        else:
                                a = ""

                        line.append(a)

                        # XXX What to do when a column's justification
                        # changes?
                        if just != JUST_UNKN:
                                widths[i] = \
                                    (max(widths[i][0], len(str(a))), just)

                if line and [e for e in line if str(e) != ""]:
                        lines.append(line)

        sortidx = 0
        for i, attr in enumerate(attrs):
                if attr == sort_attrs[0]:
                        sortidx = i
                        break

        # Sort numeric columns numerically.
        if widths[sortidx][1] == JUST_RIGHT:
                def key_extract(x):
                        try:
                                return int(x[sortidx])
                        except (ValueError, TypeError):
                                return 0
        else:
                key_extract = lambda x: x[sortidx]

        if display_headers:
                headers = []
                for i, attr in enumerate(attrs):
                        headers.append(str(attr.upper()))
                        widths[i] = \
                            (max(widths[i][0], len(attr)), widths[i][1])

                # Now that we know all the widths, multiply them by the
                # justification values to get positive or negative numbers to
                # pass to the %-expander.
                widths = [ e[0] * e[1] for e in widths ]
                fmt = ("%%%ss " * len(widths)) % tuple(widths)

                print (fmt % tuple(headers)).rstrip()
        else:
                fmt = "%s\t" * len(widths)
                fmt.rstrip("\t")

        for line in sorted(lines, key = key_extract):
                print (fmt % tuple(line)).rstrip()



def list_contents(img, args):
        """List package contents.

        If no arguments are given, display for all locally installed packages.
        With -H omit headers and use a tab-delimited format; with -o select
        attributes to display; with -s, specify attributes to sort on; with -t,
        specify which action types to list."""

        # XXX Need remote-info option, to request equivalent information
        # from repository.

        opts, pargs = getopt.getopt(args, "Ho:s:t:mf")

        valid_special_attrs = [ "action.name", "action.key", "action.raw",
            "pkg.name", "pkg.fmri", "pkg.shortfmri", "pkg.authority",
            "pkg.size" ]

        display_headers = True
        display_raw = False
        display_nofilters = False
        attrs = []
        sort_attrs = []
        action_types = []
        for opt, arg in opts:
                if opt == "-H":
                        display_headers = False
                elif opt == "-o":
                        attrs.extend(arg.split(","))
                elif opt == "-s":
                        sort_attrs.append(arg)
                elif opt == "-t":
                        action_types.extend(arg.split(","))
                elif opt == "-m":
                        display_raw = True
                elif opt == "-f":
                        # Undocumented, for now.
                        display_nofilters = True

        if display_raw:
                display_headers = False
                attrs = [ "action.raw" ]

                if set(("-H", "-o", "-t")). \
                    intersection(set([x[0] for x in opts])):
                        usage(_("contents: -m and %s may not be specified at the same time") % opt)


        for a in attrs:
                if a.startswith("action.") and not a in valid_special_attrs:
                        usage(_("Invalid attribute '%s'") % a)

                if a.startswith("pkg.") and not a in valid_special_attrs:
                        usage(_("Invalid attribute '%s'") % a)

        img.load_catalogs(progress.NullProgressTracker())

        err, fmris = installed_fmris_from_args(img, pargs)
        if err != 0:
                return err
        if not fmris:
                return 0

        #
        # If the user specifies no specific attrs, and no specific
        # sort order, then we fill in some defaults.
        #
        if not attrs:
                # XXX Possibly have multiple exclusive attributes per column?
                # If listing dependencies and files, you could have a path/fmri
                # column which would list paths for files and fmris for
                # dependencies.
                attrs = [ "path" ]

        if not sort_attrs:
                # XXX reverse sorting
                # Most likely want to sort by path, so don't force people to
                # make it explicit
                if "path" in attrs:
                        sort_attrs = [ "path" ]
                else:
                        sort_attrs = attrs[:1]

        filt = not display_nofilters
        manifests = ( img.get_manifest(f, filtered = filt) for f in fmris )

        actionlist = [ (m, a)
                    for m in manifests
                    for a in m.actions ]

        display_contents_results(actionlist, attrs, sort_attrs, action_types,
            display_headers)

        
        

def display_catalog_failures(failures):
        total, succeeded = failures.args[1:3]
        print _("pkg: %s/%s catalogs successfully updated:") % \
            (succeeded, total)

        for auth, err in failures.args[0]:
                if isinstance(err, urllib2.HTTPError):
                        print >> sys.stderr, "   %s: %s - %s" % \
                            (err.filename, err.code, err.msg)
                elif isinstance(err, urllib2.URLError):
                        if err.args[0][0] == 8:
                                print >> sys.stderr, "    %s: %s" % \
                                    (urlparse.urlsplit(auth["origin"])[1].split(":")[0],
                                    err.args[0][1])
                        else:
                                if isinstance(err.args[0], socket.timeout):
                                        print >> sys.stderr, "    %s: %s" % \
                                            (auth["origin"], "timeout")
                                else:
                                        print >> sys.stderr, "    %s: %s" % \
                                            (auth["origin"], err.args[0][1])
                else:
                        print >> sys.stderr, "   ", err

        return succeeded

def catalog_refresh(img, args):
        """Update image's catalogs."""

        # XXX will need to show available content series for each package
        full_refresh = False
        opts, pargs = getopt.getopt(args, "", ["full"])
        for opt, arg in opts:
                if opt == "--full":
                        full_refresh = True

        # Ensure Image directory structure is valid.
        if not os.path.isdir("%s/catalog" % img.imgdir):
                img.mkdirs()

        # Loading catalogs allows us to perform incremental update
        img.load_catalogs(get_tracker())

        try:
                img.retrieve_catalogs(full_refresh)
        except RuntimeError, failures:
                if display_catalog_failures(failures) == 0:
                        return 1
                else:
                        return 3
        else:
                return 0

def authority_set(img, args):
        """pkg set-authority [-P] [-k ssl_key] [-c ssl_cert]
            [-O origin_url] authority"""

        preferred = False
        ssl_key = None
        ssl_cert = None
        origin_url = None

        opts, pargs = getopt.getopt(args, "Pk:c:O:")
        for opt, arg in opts:
                if opt == "-P":
                        preferred = True
                if opt == "-k":
                        ssl_key = arg
                if opt == "-c":
                        ssl_cert = arg
                if opt == "-O":
                        origin_url = arg

        if len(pargs) != 1:
                usage(
                    _("pkg: set-authority: one and only one authority may be set"))

        auth = pargs[0]

        if ssl_key:
                ssl_key = os.path.abspath(ssl_key)
                if not os.path.exists(ssl_key):
                        error(_("set-authority: SSL key file '%s' does not exist" \
                            ) % ssl_key)
                        return 1

        if ssl_cert:
                ssl_cert = os.path.abspath(ssl_cert)
                if not os.path.exists(ssl_cert):
                        error(_("set-authority: SSL key cert '%s' does not exist" \
                            ) % ssl_cert)
                        return 1


        if not img.has_authority(auth) and origin_url == None:
                error(_("set-authority: must define origin URL for new authority"))
                return 1

        elif not img.has_authority(auth) and not misc.valid_auth_prefix(auth):
                error(_("set-authority: authority name has invalid characters"))
                return 1

        if origin_url and not misc.valid_auth_url(origin_url):
                error(_("set-authority: authority URL is invalid"))
                return 1

        img.set_authority(auth, origin_url = origin_url, ssl_key = ssl_key,
            ssl_cert = ssl_cert)

        if preferred:
                img.set_preferred_authority(auth)

        return 0

def authority_unset(img, args):
        """pkg unset-authority authority ..."""

        # is this an existing authority in our image?
        # if so, delete it
        # if not, error
        preferred_auth = img.get_default_authority()

        if len(args) == 0:
                usage()

        for a in args:
                if not img.has_authority(a):
                        error(_("unset-authority: no such authority: %s") \
                            % a)
                        return 1

                if a == preferred_auth:
                        error(_("unset-authority: removal of preferred authority not allowed."))
                        return 1

                img.delete_authority(a)

        return 0

def authority_list(img, args):
        """pkg authorities"""
        omit_headers = False
        preferred_authority = img.get_default_authority()

        opts, pargs = getopt.getopt(args, "H")
        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True

        if len(pargs) == 0:
                if not omit_headers:
                        print "%-35s %s" % ("AUTHORITY", "URL")
                for a in img.gen_authorities():
                        # summary list
                        pfx, url, ssl_key, ssl_cert, dt = img.split_authority(a)
                        if pfx == preferred_authority:
                                pfx += " (preferred)"
                        print "%-35s %s" % (pfx, url)
        else:
                img.load_catalogs(get_tracker())

                for a in pargs:
                        if not img.has_authority(a):
                                error(_("authority: no such authority: %s") \
                                    % a)
                                return 1

                        # detailed print
                        auth = img.get_authority(a)
                        pfx, url, ssl_key, ssl_cert, dt = \
                            img.split_authority(auth)

                        if dt:
                                dt = dt.ctime()

                        print ""
                        print "      Authority:", pfx
                        print "     Origin URL:", url
                        print "        SSL Key:", ssl_key
                        print "       SSL Cert:", ssl_cert
                        print "Catalog Updated:", dt

        return 0

def image_create(img, args):
        """Create an image of the requested kind, at the given path.  Load
        catalog for initial authority for convenience.

        At present, it is legitimate for a user image to specify that it will be
        deployed in a zone.  An easy example would be a program with an optional
        component that consumes global zone-only information, such as various
        kernel statistics or device information."""

        # XXX Long options support

        imgtype = image.IMG_USER
        is_zone = False
        ssl_key = None
        ssl_cert = None
        auth_name = None
        auth_url = None

        opts, pargs = getopt.getopt(args, "FPUza:k:c:",
            ["full", "partial", "user", "zone", "authority="])

        for opt, arg in opts:
                if opt == "-F" or opt == "--full":
                        imgtype = image.IMG_ENTIRE
                if opt == "-P" or opt == "--partial":
                        imgtype = image.IMG_PARTIAL
                if opt == "-U" or opt == "--user":
                        imgtype = image.IMG_USER
                if opt == "-z" or opt == "--zone":
                        is_zone = True
                if opt == "-k":
                        ssl_key = arg
                if opt == "-c":
                        ssl_cert = arg
                if opt == "-a" or opt == "--authority":
                        try:
                                auth_name, auth_url = arg.split("=", 1)
                        except ValueError:
                                usage(_("image-create requires authority "
                                    "argument to be of the form "
                                    "'<prefix>=<url>'."))

        if len(pargs) != 1:
                usage(_("image-create requires a single image directory path"))

        if ssl_key:
                ssl_key = os.path.abspath(ssl_key)
                if not os.path.exists(ssl_key):
                        print _("pkg: set-authority: SSL key file '%s' does not exist"
                            ) % ssl_key
                        return 1

        if ssl_cert:
                ssl_cert = os.path.abspath(ssl_cert)
                if not os.path.exists(ssl_cert):
                        print _("pkg: set-authority: SSL key cert '%s' does not exist"
                            ) % ssl_cert
                        return 1

        if not auth_name and not auth_url:
                usage("image-create requires an authority argument")

        if not auth_name or not auth_url:
                usage(_("image-create requires authority argument to be of "
                    "the form '<prefix>=<url>'."))

        if auth_name.startswith(fmri.PREF_AUTH_PFX):
                error(_("image-create requires that a prefix not match: %s"
                        % fmri.PREF_AUTH_PFX))
                return 1

        if not misc.valid_auth_prefix(auth_name):
                error(_("image-create: authority prefix has invalid characters"))
                return 1

        if not misc.valid_auth_url(auth_url):
                error(_("image-create: authority URL is invalid"))
                return 1 

        try:
                img.set_attrs(imgtype, pargs[0], is_zone, auth_name, auth_url,
                    ssl_key = ssl_key, ssl_cert = ssl_cert)
        except OSError, e:
                error(_("cannot create image at %s: %s") % \
                    (pargs[0], e.args[1]))
                return 1

        try:
                img.retrieve_catalogs()
        except RuntimeError, failures:
                if display_catalog_failures(failures) == 0:
                        return 1
                else:
                        return 3
        else:
                return 0

def main_func():
        img = image.Image()

        # XXX /usr/lib/locale is OpenSolaris-specific.
        gettext.install("pkg", "/usr/lib/locale")

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "s:R:")
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        if pargs == None or len(pargs) == 0:
                usage()

        subcommand = pargs[0]
        del pargs[0]

        socket.setdefaulttimeout(
            int(os.environ.get("PKG_CLIENT_TIMEOUT", "30"))) # in seconds

        # XXX Handle PKG_SERVER environment variable.

        if subcommand == "image-create":
                try:
                        ret = image_create(img, pargs)
                except getopt.GetoptError, e:
                        usage(_("illegal %s option -- %s") % \
                            (subcommand, e.opt))
                return ret

        for opt, arg in opts:
                if opt == "-R":
                        mydir = arg

        if "mydir" not in locals():
                try:
                        mydir = os.environ["PKG_IMAGE"]
                except KeyError:
                        mydir = os.getcwd()

        try:
                img.find_root(mydir)
        except ValueError:
                error(_("'%s' is not an install image") % mydir)
                return 1

        img.load_config()

        try:
                if subcommand == "refresh":
                        return catalog_refresh(img, pargs)
                elif subcommand == "list":
                        return list_inventory(img, pargs)
                elif subcommand == "image-update":
                        return image_update(img, pargs)
                elif subcommand == "install":
                        return install(img, pargs)
                elif subcommand == "uninstall":
                        return uninstall(img, pargs)
                elif subcommand == "freeze":
                        return freeze(img, pargs)
                elif subcommand == "unfreeze":
                        return unfreeze(img, pargs)
                elif subcommand == "search":
                        return search(img, pargs)
                elif subcommand == "info":
                        return info(img, pargs)
                elif subcommand == "contents":
                        return list_contents(img, pargs)
                elif subcommand == "verify":
                        return verify_image(img, pargs)
                elif subcommand == "set-authority":
                        return authority_set(img, pargs)
                elif subcommand == "unset-authority":
                        return authority_unset(img, pargs)
                elif subcommand == "authority":
                        return authority_list(img, pargs)
                else:
                        usage(_("unknown subcommand '%s'") % subcommand)

        except getopt.GetoptError, e:
                usage(_("illegal %s option -- %s") % (subcommand, e.opt))


#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":
        try:
                ret = main_func()
        except SystemExit, e:
                raise e
        except KeyboardInterrupt:
                print "Interrupted"
                sys.exit(1)
        except:
                traceback.print_exc()
                sys.exit(99)
        sys.exit(ret)
