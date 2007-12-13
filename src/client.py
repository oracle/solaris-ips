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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#
# pkg - package system client utility
#
# We use urllib2 for GET and POST operations, but httplib for PUT and DELETE
# operations.

# The client is going to maintain an on-disk cache of its state, so that startup
# assembly of the graph is reduced.

# Client graph is of the entire local catalog.  As operations progress, package
# states will change.

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
import httplib
import itertools
import os
import re
import sha
import sys
import traceback
import urllib
import urllib2
import urlparse

import pkg.arch as arch
import pkg.catalog as catalog
import pkg.config as config
import pkg.dependency as dependency
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.version as version

import pkg.client.image as image
import pkg.client.imageplan as imageplan
import pkg.client.filelist as filelist

def usage():
        print >> sys.stderr, _("""\
Usage:
        pkg [options] command [cmd_options] [operands]

Install subcommands:
        pkg refresh [--full]
        pkg install [-nv] pkg_fmri
        pkg uninstall [-nrv] pkg_fmri

        pkg info [-sv] pkg_fmri_pattern [pkg_fmri_pattern ... ]
        pkg list [-o attribute ...] [-s sort_key] [-t action_type ... ]
            pkg_fmri_pattern [pkg_fmri_pattern ...]
        pkg search [-lr] [-s server] token
        pkg status [-auv] [pkg_fmri_pattern ...]

        pkg image-create [-FPUz] [--full|--partial|--user] [--zone]
            [--authority prefix=url] dir
        pkg image-update [-nv]

Options:
        --server, -s
        --image, -R

Environment:
        PKG_SERVER
        PKG_IMAGE""")
        sys.exit(2)

# XXX Subcommands to implement:
#        pkg image-set name value
#        pkg image-unset name
#        pkg image-get [name ...]

def catalog_refresh(img, args):
        """Update image's catalogs."""

        # XXX will need to show available content series for each package
        full_refresh = False
        try:
                opts, pargs = getopt.getopt(args, None, ["full"])
                for opt, arg in opts:
                        if opt == "--full":
                                full_refresh = True
        except getopt.GetoptError, e:
                print "pkg: refresh: illegal option -- %s" % e.opt
                usage()

        # Ensure Image directory structure is valid.
        if not os.path.isdir("%s/catalog" % img.imgdir):
                img.mkdirs()

        # Loading catalogs allows us to perform incremental update
        img.load_catalogs()

        try:
                img.retrieve_catalogs(full_refresh)
        except RuntimeError, failures:
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
                                        print >> sys.stderr, "    %s: %s" % \
                                            (auth["origin"], err.args[0][1])
                        elif isinstance(err, IOError):
                                print >> sys.stderr, "   ", err

                if succeeded == 0:
                        return 1
                else:
                        return 3
        else:
                return 0

def inventory_display(img, args):
        img.load_catalogs()
        img.display_inventory(args)

def image_update(img, args):
        """Attempt to take all installed packages specified to latest
        version."""

        # XXX Authority-catalog issues.
        # XXX Are filters appropriate for an image update?
        # XXX Leaf package refinements.

        opts, pargs = getopt.getopt(args, "b:nv")

        strict = noexecute = verbose = False
        filters = []
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-b":
                        filelist.FileList.maxfiles = int(arg)

        img.load_catalogs()

        pkg_list = [ ipkg.get_pkg_stem() for ipkg in img.gen_installed_pkgs() ]
        try:
                img.list_install(pkg_list, verbose = verbose,
                    noexecute = noexecute)
        except RuntimeError, e:
		print >> sys.stderr, _("image_update failed: %s") % e
                sys.exit(1)

def install(img, args):
        """Attempt to take package specified to INSTALLED state.  The operands
        are interpreted as glob patterns."""

        # XXX Authority-catalog issues.

        opts, pargs = getopt.getopt(args, "Snvb:f:")

        strict = noexecute = verbose = False
        filters = []
        for opt, arg in opts:
                if opt == "-S":
                        strict = True
                elif opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-b":
                        filelist.FileList.maxfiles = int(arg)

                elif opt == "-f":
                        filters += [ arg ]

        img.load_catalogs()

        ip = imageplan.ImagePlan(img, filters = filters)

        pkg_list = [ pat.replace("*", ".*").replace("?", ".")
            for pat in pargs ]

        try:
                img.list_install(pkg_list, filters = filters, verbose = verbose,
                    noexecute = noexecute)
        except RuntimeError, e:
		print >> sys.stderr, _("install failed: %s") % e
                sys.exit(1)

def uninstall(img, args):
        """Attempt to take package specified to DELETED state."""

        # XXX Move uninstall logic to pkg.client.image.

        opts, pargs = getopt.getopt(args, "nrv")

        noexecute = recursive_removal = verbose = False
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-r":
                        recursive_removal = True
                elif opt == "-v":
                        verbose = True

        img.load_catalogs()

        ip = imageplan.ImagePlan(img, recursive_removal)

        for ppat in pargs:
                rpat = re.sub("\*", ".*", ppat)
                rpat = re.sub("\?", ".", rpat)

                try:
                        matches = img.get_matching_fmris(rpat)
                except KeyError:
                        print >> sys.stderr, \
                            _("pkg: '%s' not even in catalog!") % ppat
                        error = 1
                        continue

                pnames = dict(
                    (m, 1)
                    for m in matches
                    if img.is_installed(m)
                )

                if len(pnames) > 1:
                        print >> sys.stderr, \
                            _("pkg: '%s' matches multiple packages") % ppat
                        for k in pnames.keys():
                                print "\t%s" % k
                        continue

                if len(pnames) < 1:
                        print >> sys.stderr, \
                            _("pkg: '%s' matches no installed packages") % ppat
                        continue

                ip.propose_fmri_removal(pnames.keys()[0])

        if verbose:
                print _("Before evaluation:")
                print ip

        ip.evaluate()

        if verbose:
                print _("After evaluation:")
                print ip

        if not noexecute:
                ip.execute()

def freeze(img, args):
        """Attempt to take package specified to FROZEN state, with given
        restrictions.  Package must have been in the INSTALLED state."""
        return

def unfreeze(img, args):
        """Attempt to return package specified to INSTALLED state from FROZEN
        state."""
        return

def search(img, args):
        """Search through the reverse index databases for the given token."""

        opts, pargs = getopt.getopt(args, "lrs:")

        local = remote = False
        servers = []
        for opt, arg in opts:
                if opt == "-l":
                        local = True
                if opt == "-r":
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
                for k, v in itertools.chain(*searches):
                        retcode = 0
                        print k, v
        except RuntimeError, failed:
                print "Some servers failed to respond:"
                for auth, err in failed.args[0]:
                        if isinstance(err, urllib2.HTTPError):
                                print "    %s: %s (%d)" % \
                                    (auth["origin"], err.msg, err.code)
                        elif isinstance(err, urllib2.URLError):
                                print "    %s: %s" % \
                                    (auth["origin"], err.args[0][1])

                retcode = 4

        return retcode

def info(img, args):
        """Display information about the package.

        By default, display generic metainformation about the package.  With -v,
        display verbosely.  With -s, a short display.
        """

        # XXX Need remote-info option, to request equivalent information
        # from repository.

        opts, pargs = getopt.getopt(args, "sv")

        verbose = short = False
        for opt, arg in opts:
                if opt == "-s":
                        short = True
                elif opt == "-v":
                        verbose = True # XXX -vv ?

        img.load_catalogs()

        # XXX Want to show info for all packages if no args given.
        try:
                matches = img.get_matching_fmris(pargs)
        except KeyError:
                print >> sys.stderr, \
                    _("pkg: no matching packages found in catalog")
                return

        fmris = [
            m
            for m in matches
            if img.is_installed(m)
        ]

        if not fmris:
                return

        manifests = ( img.get_manifest(f, filtered = True) for f in fmris )

        for i, m in enumerate(manifests):
                if not short and i > 0:
                        print
                info_one(m, short, verbose)

def info_one(manifest, short, verbose):
        authority, name, version = manifest.fmri.tuple()
        summary = manifest.get("description", "")

        if short:
                print "%-12s%s" % (name, summary)
        else:
                print "Name:", name
                print "FMRI:", manifest.fmri
                print "Version:", version.release
                print "Branch:", version.branch
                print "Packaging Date:", version.get_datetime()
                print "Size:", sum(int(a.attrs.get("pkg.size", 0))
                    for a in manifest.actions)
                print "Summary:", summary

def list_contents(img, args):
        """List package contents."""

        # XXX Need remote-info option, to request equivalent information
        # from repository.

        opts, pargs = getopt.getopt(args, "o:s:t:")

        verbose = False
        attrs = []
        sort_attrs = []
        action_types = []
        for opt, arg in opts:
                if opt == "-o":
                        attrs.extend(arg.split(","))
                elif opt == "-s":
                        sort_attrs.append(arg)
                elif opt == "-t":
                        action_types.extend(arg.split(","))

        img.load_catalogs()

        # XXX Want to list contents of all packages if no args given.
        # XXX Maybe want to make get_matching_fmris() return only installed
        # fmris, if asked.
        try:
                matches = img.get_matching_fmris(pargs)
        except KeyError:
                print _("pkg: no matching packages found in catalog")
                return

        fmris = [
            m
            for m in matches
            if img.is_installed(m)
        ]

        if not attrs:
                # XXX Possibly have multiple exclusive attributes per column?
                # If listing dependencies and files, you could have a path/fmri
                # column which would list paths for files and fmris for
                # dependencies.
                attrs = [ "path" ]
        # XXX reverse sorting
        if not sort_attrs:
                # Most likely want to sort by path, so don't force people to
                # make it explicit
                if "path" in attrs:
                        sort_attrs = [ "path" ]
                else:
                        sort_attrs = attrs[:1]

        if not fmris:
                return

        manifests = ( img.get_manifest(f, filtered = True) for f in fmris )

        lines = []
        # widths is a list of tuples of column width and justification.  Start
        # with the widths of the column headers, excluding any dotted prefixes.
        JUST_UNKN = 0
        JUST_LEFT = -1
        JUST_RIGHT = 1
        widths = [ (len(attr) - attr.find(".") - 1, JUST_UNKN) for attr in attrs ]
        for manifest in manifests:
                for action in manifest.actions:
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
                                elif attr == ":name":
                                        a = action.name
                                        just = JUST_LEFT
                                elif attr == ":key":
                                        a = action.attrs[action.key_attr]
                                        just = JUST_LEFT
                                else:
                                        a = ""

                                line.append(a)

                                # XXX What to do when a column's justification
                                # changes?
                                if just != JUST_UNKN:
                                        widths[i] = \
                                            (max(widths[i][0], len(a)), just)

                        if line and [e for e in line if e != ""]:
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

        # Now that we know all the widths, multiply them by the justification
        # values to get positive or negative numbers to pass to the %-expander.
        widths = [ e[0] * e[1] for e in widths ]
        fmt = ("%%%ss " * len(widths)) % tuple(widths)
        headers = [a[a.find(".") + 1:].upper() for a in attrs]
        print (fmt % tuple(headers)).rstrip()
        for line in sorted(lines, key = key_extract):
                print (fmt % tuple(line)).rstrip()

def image_create(img, args):
        """Create an image of the requested kind, at the given path.  Load
        catalog for initial authority for convenience.

        At present, it is legitimate for a user image to specify that it will be
        deployed in a zone.  An easy example would be a program with an optional
        component that consumes global zone-only information, such as various
        kernel statistics or device information."""

        # XXX Long options support

        type = image.IMG_USER
        filter_tags = arch.get_isainfo()
        is_zone = False
        auth_name = None
        auth_url = None

	opts, pargs = getopt.getopt(args, "FPUza:")

        for opt, arg in opts:
                if opt == "-F":
                        type = image.IMG_ENTIRE
                if opt == "-P":
                        type = image.IMG_PARTIAL
                if opt == "-U":
                        type = image.IMG_USER
                if opt == "-z":
                        is_zone = True
                if opt == "-a":
                        auth_name, auth_url = arg.split("=", 1)

        img.set_attrs(type, pargs[0], is_zone, auth_name, auth_url)

        try:
                img.retrieve_catalogs()
        except urllib2.URLError, e:
                print >> sys.stderr, "pkg:", e.reason[1]
                return 1

        return 0

img = image.Image()

def main_func():
        # XXX /usr/lib/locale is OpenSolaris-specific.
        gettext.install("pkg", "/usr/lib/locale")

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "s:R:")
        except getopt.GetoptError, e:
                print >> sys.stderr, \
                    _("pkg: illegal global option -- %s") % e.opt
                usage()

        if pargs == None or len(pargs) == 0:
                usage()

        subcommand = pargs[0]
        del pargs[0]

        # XXX Handle PKG_SERVER environment variable.

        if subcommand == "image-create":
		try:
			ret = image_create(img, pargs)
		except getopt.GetoptError, e:
			print >> sys.stderr, \
                            _("pkg: illegal %s option -- %s") % \
                            (subcommand, e.opt)
                        usage()
		return ret

        for opt, arg in opts:
                if opt == "-R":
                        dir = arg

        if "dir" not in locals():
                try:
                        dir = os.environ["PKG_IMAGE"]
                except KeyError:
                        dir = os.getcwd()

        try:
                img.find_root(dir)
        except AssertionError:
                print >> sys.stderr, \
                    _("'%s' is not an install image") % dir
                return 1

        img.load_config()

        try:
                if subcommand == "refresh":
                        return catalog_refresh(img, pargs)
                elif subcommand == "status":
                        inventory_display(img, pargs)
                elif subcommand == "image-update":
                        image_update(img, pargs)
                elif subcommand == "install":
                        install(img, pargs)
                elif subcommand == "uninstall":
                        try:
                                uninstall(img, pargs)
                        except KeyboardInterrupt:
                                pass
                elif subcommand == "freeze":
                        freeze(img, pargs)
                elif subcommand == "unfreeze":
                        unfreeze(img, pargs)
                elif subcommand == "search":
                        return search(img, pargs)
                elif subcommand == "info":
                        info(img, pargs)
                elif subcommand == "list":
                        list_contents(img, pargs)
                else:
                        print >> sys.stderr, \
                            _("pkg: unknown subcommand '%s'") % subcommand
                        usage()

        except getopt.GetoptError, e:
                print >> sys.stderr, \
                    _("pkg: illegal %s option -- %s") % (subcommand, e.opt)
                usage()

        return 0


#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":
	try:
		ret = main_func()
	except SystemExit, e:
		raise e
	except:
		traceback.print_exc()
		sys.exit(99)
	sys.exit(ret)
