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

"""feed - routines for generating RFC 4287 Atom feeds for packaging server

   At present, the pkg.server.feed module provides a set of routines that, from
   a catalog, allow the construction of a feed representing the activity within
   a given time period."""

import cherrypy
from cherrypy.lib.static import serve_file
import cStringIO
import datetime
import httplib
import os
import rfc822
import time
import urllib
import xml.dom.minidom as xmini

from pkg.misc import get_rel_path
import pkg.server.catalog as catalog
import pkg.fmri as fmri
import pkg.Uuid25 as uuid

MIME_TYPE = 'application/atom+xml'
CACHE_FILENAME = "feed.xml"
RFC3339_FMT = "%Y-%m-%dT%H:%M:%SZ"

def dt_to_rfc3339_str(ts):
        """Returns a string representing a datetime object formatted according
        to RFC 3339.
        """
        return ts.strftime(RFC3339_FMT)

def rfc3339_str_to_ts(ts_str):
        """Returns a timestamp representing 'ts_str', which should be in the
        format specified by RFC 3339.
        """
        return time.mktime(time.strptime(ts_str, RFC3339_FMT))

def rfc3339_str_to_dt(ts_str):
        """Returns a datetime object representing 'ts_str', which should be in
        the format specified by RFC 3339.
        """
        return datetime.datetime(*time.strptime(ts_str, RFC3339_FMT)[0:6])

def ults_to_ts(ts_str):
        """Returns a timestamp representing 'ts_str', which should be in
        updatelog format.
        """
        # Python doesn't support fractional seconds for strptime.
        ts_str = ts_str.split('.')[0]
        # Currently, updatelog entries are in local time, not UTC.
        return time.mktime(time.strptime(ts_str, "%Y-%m-%dT%H:%M:%S"))

def ults_to_rfc3339_str(ts_str):
        """Returns a timestamp representing 'ts_str', which should be in
        updatelog format.
        """
        ltime = ults_to_ts(ts_str)
        # Currently, updatelog entries are in local time, not UTC.
        return dt_to_rfc3339_str(datetime.datetime(
            *time.gmtime(ltime)[0:6]))

def fmri_to_taguri(rcfg, f):
        """Generates a 'tag' uri compliant with RFC 4151.  Visit
        http://www.taguri.org/ for more information.
        """
        pfx = rcfg.get_attribute("publisher", "prefix")
        if not pfx:
                pfx = "unknown"
        return "tag:%s,%s:%s" % (pfx, f.get_timestamp().strftime("%Y-%m-%d"),
            urllib.unquote(f.get_url_path()))

def init(scfg, rcfg):
        """This function performs general initialization work that is needed
        for feeds to work correctly.
        """

        if not scfg.feed_cache_read_only():
                # RSS/Atom feeds require a unique identifier, so
                # generate one if isn't defined already.  This
                # needs to be a persistent value, so we only
                # generate this if we can save the configuration.
                fid = rcfg.get_attribute("feed", "id")
                if not fid:
                        # Create a random UUID (type 4).
                        rcfg._set_attribute("feed", "id", uuid.uuid4())

                # Ensure any configuration changes are reflected in the feed.
                __clear_cache(scfg)

def set_title(request, rcfg, doc, feed, update_ts):
        """This function attaches the necessary RSS/Atom feed elements needed
        to provide title, author and contact information to the provided
        xmini document object using the provided feed object and update
        time.
        """

        t = doc.createElement("title")
        ti = xmini.Text()
        ti.replaceWholeText(rcfg.get_attribute("feed", "name"))
        t.appendChild(ti)
        feed.appendChild(t)

        l = doc.createElement("link")
        l.setAttribute("href", cherrypy.url())
        l.setAttribute("rel", "self")
        feed.appendChild(l)

        # Atom requires each feed to have a permanent, universally unique
        # identifier.
        i = doc.createElement("id")
        it = xmini.Text()
        it.replaceWholeText("urn:uuid:%s" % rcfg.get_attribute("feed", "id"))
        i.appendChild(it)
        feed.appendChild(i)

        # Indicate when the feed was last updated.
        u = doc.createElement("updated")
        ut = xmini.Text()
        ut.replaceWholeText(dt_to_rfc3339_str(update_ts))
        u.appendChild(ut)
        feed.appendChild(u)

        # Add our icon.
        i = doc.createElement("icon")
        it = xmini.Text()
        it.replaceWholeText(rcfg.get_attribute("feed", "icon"))
        i.appendChild(it)
        feed.appendChild(i)

        # Add our logo.
        l = doc.createElement("logo")
        lt = xmini.Text()
        lt.replaceWholeText(rcfg.get_attribute("feed", "logo"))
        l.appendChild(lt)
        feed.appendChild(l)

        maintainer = rcfg.get_attribute("repository", "maintainer")
        # The author information isn't required, but can be useful.
        if maintainer:
                name, email = rfc822.AddressList(maintainer).addresslist[0]

                if email and not name:
                        # If we got an email address, but no name, then
                        # the name was likely parsed as a local address. In
                        # that case, assume the whole string is the name.
                        name = maintainer
                        email = None

                a = doc.createElement("author")

                # First we have to add a name element. This is required if an
                # author element exists.
                n = doc.createElement("name")
                nt = xmini.Text()
                nt.replaceWholeText(name)
                n.appendChild(nt)
                a.appendChild(n)

                if email:
                        # If we were able to extract an email address from the
                        # maintainer information, add the optional email
                        # element to provide a point of communication.
                        e = doc.createElement("email")
                        et = xmini.Text()
                        et.replaceWholeText(email)
                        e.appendChild(et)
                        a.appendChild(e)

                # Done with the author.
                feed.appendChild(a)

operations = {
        "+": ["Added", "%s was added to the repository."],
        "-": ["Removed", "%s was removed from the repository."],
        "U": ["Updated", "%s, an update to an existing package, was added to "
            "the repository."]
}

def add_transaction(request, scfg, rcfg, doc, feed, txn, fmris):
        """Each transaction is an entry.  We have non-trivial content, so we
        can omit summary elements.
        """

        e = doc.createElement("entry")

        tag, fmri_str = txn["catalog"].split()
        f = fmri.PkgFmri(fmri_str)
 
        # Generate a 'tag' uri, to uniquely identify the entry, using the fmri.
        i = xmini.Text()
        i.replaceWholeText(fmri_to_taguri(rcfg, f))
        eid = doc.createElement("id")
        eid.appendChild(i)
        e.appendChild(eid)

        # Attempt to determine the operation that was performed and generate
        # the entry title and content.
        if txn["operation"] in operations:
                op_title, op_content = operations[txn["operation"]]
        else:
                # XXX Better way to reflect an error?  (Aborting will make a
                # non-well-formed document.)
                op_title = "Unknown Operation"
                op_content = "%s was changed in the repository."

        if txn["operation"] == "+":
                # Get all FMRIs matching the current FMRI's package name.
                matches = fmris[f.pkg_name]
                if len(matches["versions"]) > 1:
                        # Get the oldest fmri.
                        of = matches[str(matches["versions"][0])][0]

                        # If the current fmri isn't the oldest one, then this
                        # is an update to the package.
                        if f != of:
                                # If there is more than one matching FMRI, and
                                # it isn't the same version as the oldest one,
                                # we can assume that this is an update to an
                                # existing package.
                                op_title, op_content = operations["U"]

        # Now add a title for our entry.
        etitle = doc.createElement("title")
        ti = xmini.Text()
        ti.replaceWholeText(" ".join([op_title, fmri_str]))
        etitle.appendChild(ti)
        e.appendChild(etitle)

        # Indicate when the entry was last updated (in this case, when the
        # package was added).
        eu = doc.createElement("updated")
        ut = xmini.Text()
        ut.replaceWholeText(ults_to_rfc3339_str(txn["timestamp"]))
        eu.appendChild(ut)
        e.appendChild(eu)

        # Link to the info output for the given package FMRI.
        e_uri = get_rel_path(request, 'info/0/%s' % f.get_url_path())

        l = doc.createElement("link")
        l.setAttribute("rel", "alternate")
        l.setAttribute("href", e_uri)
        e.appendChild(l)

        # Using the description for the operation performed, add the FMRI and
        # tag information.
        content_text = op_content % fmri_str
        if tag == "C":
                content_text += "  This version is tagged as critical."

        co = xmini.Text()
        co.replaceWholeText(content_text)
        ec = doc.createElement("content")
        ec.appendChild(co)
        e.appendChild(ec)

        feed.appendChild(e)

def update(request, scfg, rcfg, t, cf):
        """Generate new Atom document for current updates.  The cached feed
        file is written to scfg.feed_cache_root/CACHE_FILENAME.
        """

        # Our configuration is stored in hours, convert it to seconds.
        window_seconds = rcfg.get_attribute("feed", "window") * 60 * 60
        feed_ts = datetime.datetime.fromtimestamp(t - window_seconds)

        d = xmini.Document()

        feed = d.createElementNS("http://www.w3.org/2005/Atom", "feed")
        feed.setAttribute("xmlns", "http://www.w3.org/2005/Atom")

        set_title(request, rcfg, d, feed, scfg.updatelog.last_update)

        d.appendChild(feed)

        # The feed should be presented in reverse chronological order.
        def compare_ul_entries(a, b):
                return cmp(ults_to_ts(a["timestamp"]),
                    ults_to_ts(b["timestamp"]))

        # Get the entire catalog in the format returned by catalog.cache_fmri,
        # so that we don't have to keep looking for possible matches.
        fmris = {}
        catalog.ServerCatalog.read_catalog(fmris,
            scfg.updatelog.catalog.catalog_root)

        for txn in sorted(scfg.updatelog.gen_updates_as_dictionaries(feed_ts),
            cmp=compare_ul_entries, reverse=True):
                add_transaction(request, scfg, rcfg, d, feed, txn, fmris)

        d.writexml(cf)

def __get_cache_pathname(scfg):
        return os.path.join(scfg.feed_cache_root, CACHE_FILENAME)

def __clear_cache(scfg):
        if scfg.feed_cache_read_only():
                # Ignore the request due to server configuration.
                return

        pathname = __get_cache_pathname(scfg)
        try:
                if os.path.exists(pathname):
                        os.remove(pathname)
        except IOError:
                raise cherrypy.HTTPError(
                    httplib.INTERNAL_SERVER_ERROR,
                    "Unable to clear feed cache.")

def __cache_needs_update(scfg):
        """Checks to see if the feed cache file exists and if it is still
        valid.  Returns False, None if the cache is valid or True, last
        where last is a timestamp representing when the cache was
        generated.
        """
        cfpath = __get_cache_pathname(scfg)
        last = None
        need_update = True
        if os.path.isfile(cfpath):
                # Attempt to parse the cached copy.  If we can't, for any
                # reason, assume we need to remove it and start over.
                try:
                        d = xmini.parse(cfpath)
                except Exception:
                        d = None
                        __clear_cache(scfg)

                # Get the feed element and attempt to get the time we last
                # generated the feed to determine whether we need to regenerate
                # it.  If for some reason we can't get that information, assume
                # the cache is invalid, clear it, and force regeneration.
                fe = None
                if d:
                        fe = d.childNodes[0]

                if fe:
                        utn = None
                        for cnode in fe.childNodes:
                                if cnode.nodeName == "updated":
                                        utn = cnode.childNodes[0]
                                        break

                        if utn:
                                last_ts = rfc3339_str_to_dt(utn.nodeValue)

                                # Since our feed cache and updatelog might have
                                # been created within the same second, we need
                                # to ignore small variances when determining
                                # whether to update the feed cache.
                                update_ts = scfg.updatelog.last_update.replace(
                                    microsecond=0)

                                if last_ts >= update_ts:
                                        need_update = False
                                else:
                                        last = rfc3339_str_to_ts(utn.nodeValue)
                        else:
                                __clear_cache(scfg)
                else:
                        __clear_cache(scfg)

        return need_update, last

def handle(scfg, rcfg, request, response):
        """If there have been package updates since we last generated the feed,
        update the feed and send it to the client.  Otherwise, send them the
        cached copy if it is available.
        """

        cfpath = __get_cache_pathname(scfg)

        # First check to see if we already have a valid cache of the feed.
        need_update, last = __cache_needs_update(scfg)

        if need_update:
                # Update always looks at feed.window seconds before the last
                # update until "now."  If last is none, we want it to use "now"
                # as its starting point.
                if last is None:
                        last = time.time()

                if scfg.feed_cache_read_only():
                        # If the server is operating in readonly mode, the
                        # feed will have to be generated every time.
                        cf = cStringIO.StringIO()
                        update(request, scfg, rcfg, last, cf)
                        cf.seek(0)
                        buf = cf.read()
                        cf.close()

                        # Now that the feed has been generated, set the headers
                        # correctly and return it.
                        response.headers['Content-type'] = MIME_TYPE

                        # Return the current time and date in GMT.
                        response.headers['Last-Modified'] = rfc822.formatdate()

                        response.headers['Content-length'] = len(buf)
                        return buf
                else:
                        # If the server isn't operating in readonly mode, the
                        # feed can be generated and cached in inst_dir.
                        cf = file(cfpath, "w")
                        update(request, scfg, rcfg, last, cf)
                        cf.close()

        return serve_file(cfpath, MIME_TYPE)

