<%doc>
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
# Copyright (c) 2013, Oracle and/or its affiliates. All rights reserved.
#

#
# This file is the template for an Apache configuration that serves pkg(5)
# repositories.  On its own, it can be used to render a fragment that can be
# dropped into an Apache conf.d directory, or it can be referenced from
# a more complete httpd.conf template via an include directive.
#
</%doc><%
import urllib
%>
RewriteEngine on
RewriteLog "${log_dir}/rewrite.log"
RewriteLogLevel 0

# We need to allow these as they're encoded in the package/manifest names
# when looking up v4 repositories
AllowEncodedSlashes On
# The default of 500 MaxKeepAliveRequests is too low to be useful.
MaxKeepAliveRequests 10000

<%doc>
# All of our rules specify the NE flag, 'noescape', that is
# we don't want any rewritten URLs being decoded en-route through
# the set of RewriteRule directives.
#

# For all RewriteRule directives below, we allow sroot to specify
# a server-root beneath which we should operate.
</%doc>
<%

repo_prefixes = set()
root = context.get("sroot")
runtime_dir = context.get("runtime_dir")

for pub, repo_path, repo_prefix, writable_root in pubs:
        repo_prefixes.add(repo_prefix)
context.write("# per-repository versions, publishers and status responses\n")

for repo_prefix in repo_prefixes:
        context.write(
            "RewriteRule ^/%(root)s%(repo_prefix)sversions/0 "
            "/%(root)sversions/0/index.html [PT,NE]\n" % locals())
        context.write("RewriteRule ^/%(root)s%(repo_prefix)spublisher/0 "
            "/%(root)s%(repo_prefix)spublisher/1/index.html [PT,NE]\n" %
            locals())
        context.write(
            "RewriteRule ^/%(root)s%(repo_prefix)sstatus/0 "
            "/%(root)s%(repo_prefix)sstatus/0/index.html [PT,NE]\n" % locals())
%>

<%doc>
#
# Rules to redirect default publisher requests into the publisher-specific
# rules below.  Publisher and versions responses were handled above.
#
</%doc>
# Rules to deal with responses for default publishers
#
<%
        for pub, repo_path, repo_prefix in default_pubs:
                if pub == None:
                        continue
                root = context.get("sroot")
                # manifest rules need to use %{THE_REQUEST} undecoded
                # URI from mod_rewrite. However, since %{THE_REQUEST} is the
                # original request, we can't simply rewrite the URI
                # here to add the publisher, then let the other manifest rules
                # pick up the trail, so we need to do more work here,
                # basically duplicating how we deal with manifest responses
                # that have got a publisher included in the URI.
                context.write(
                    "RewriteRule ^/%(root)s%(repo_prefix)smanifest/0/.*$ "
                    "%%{THE_REQUEST} [NE,C]\n" % locals())
                context.write("RewriteRule ^GET\ "
                    "/%(root)s%(repo_prefix)smanifest/0/([^@]+)@([^\ ]+)(\ HTTP/1.1)$ "
                    "/%(root)s%(repo_prefix)s%(pub)s/publisher/%(pub)s/pkg/$1/$2 [NE,PT,C]\n"
                    % locals())
                context.write(
                    "RewriteRule ^/%(root)s%(repo_prefix)s%(pub)s/(.*)$ "
		    "%%{DOCUMENT_ROOT}/%(root)s%(repo_prefix)s%(pub)s/$1 [NE,L]\n"
                    % locals())

                # file responses require more work, so rewrite to
                # a URI that will get further rewrites later.
                context.write("RewriteRule "
                    "^/%(root)s%(repo_prefix)sfile/(.*$) "
                    "/%(root)s%(repo_prefix)s%(pub)s/file/$1 [NE]\n"
                    % locals())
                # for catalog parts, we can easily access the file with one
                # RewriteRule, so do that, then PT to the Alias directive.
                context.write("RewriteRule "
                    "^/%(root)s%(repo_prefix)scatalog/1/(.*$) "
                    "/%(root)s%(repo_prefix)s%(pub)s/publisher/%(pub)s/catalog/$1 [NE,PT]\n"
                    % locals())
%>

# Write per-publisher rules for publisher, version, file and manifest responses
% for pub, repo_path, repo_prefix, writable_root in pubs:
        <%doc>
        # Point to our local versions/0 response or
        # publisher-specific publisher/1, response, then stop.
        </%doc>
# Serve our static versions and publisher responses
<%
        root = context.get("sroot")
        context.write(
            "RewriteRule ^/%(root)s%(repo_prefix)s%(pub)s/versions/0 "
            "%%{DOCUMENT_ROOT}/%(root)sversions/0/index.html [L,NE]\n" % locals())
        context.write(
            "RewriteRule ^/%(root)s%(repo_prefix)s%(pub)s/publisher/0 "
            "%%{DOCUMENT_ROOT}/%(root)s%(repo_prefix)s%(pub)s/publisher/1/index.html [L,NE]\n" %
            locals())

%><%doc>
        # Modify the catalog, file and manifest URLs, then 'passthrough' (PT),
        # letting the Alias directives below serve the file.
        </%doc>
<%
        root = context.get("sroot")
        context.write(
            "RewriteRule ^/%(root)s%(repo_prefix)s%(pub)s/catalog/1/(.*)$ "
            "/%(root)s%(repo_prefix)s%(pub)s/publisher/%(pub)s/catalog/$1 [NE,PT]" %
            locals())
        %><%doc>
        # file responses are a little tricky - we need to index
        # the first two characters of the filename and use that
        # as an index into the directory of filenames.
        # (omitting sroot and repo_prefix here, for brevity)
        # eg. the request
        # http://localhost:10000/pkg5-nightly/file/1/87ad645695abb22b2959f73d22022c5cffeccb13
        # gets rewritten as:
        # http://localhost:10000/pkg5-nightly/publisher/pkg5-nightly/file/87/87ad645695abb22b2959f73d22022c5cffeccb13
        </%doc>
<%
        root = context.get("sroot")
        context.write(
            "RewriteRule ^/%(root)s%(repo_prefix)s%(pub)s/file/1/(..)(.*)$ "
            "/%(root)s%(repo_prefix)s%(pub)s/publisher/%(pub)s/file/$1/$1$2 [NE,PT]\n"
            % locals())
        %><%doc>
        # We need to use %THE_REQUEST here to get the undecoded
        # URI from mod_rewrite.  Hang on to your lunch.
        # We chain the rule that produces THE_REQUEST to the
        # following rule which picks apart the original http
        # request to separate the package name from the package
        # version.
        #
        # That is, mod_rewrite sees the pkg client asking for
        # the initial decoded URI:
        #  '/pkg5-nightly/manifest/0/package/sysrepo@0.5.11,5.11-0.159:20110308T011843Z'
        #
        # which comes from the HTTP request:
        #  'GET /pkg5-nightly/manifest/0/package%2Fsysrepo@0.5.11%2C5.11-0.159%3A20110308T011843Z HTTP/1.1'
        #
        # which we eventually rewrite as:
        #  -> '/pkg5-nightly/publisher/pkg5-nightly/pkg/package%2Fsysrepo/0.5.11%2C5.11-0.159%3A20110308T011843Z'
        </%doc>
<%
        root = context.get("sroot")
        context.write(
            "RewriteRule ^/%(root)s%(repo_prefix)s%(pub)s/manifest/0/.*$ "
            "%%{THE_REQUEST} [NE,C]\n" % locals())

        context.write("RewriteRule ^GET\ "
            "/%(root)s%(repo_prefix)s%(pub)s/manifest/0/([^@]+)@([^\ ]+)(\ HTTP/1.1)$ "
            "/%(root)s%(repo_prefix)s%(pub)s/publisher/%(pub)s/pkg/$1/$2 [NE,PT,C]\n"
            % locals())
        context.write(
            "RewriteRule ^/%(root)s%(repo_prefix)s%(pub)s/(.*)$ "
            "%%{DOCUMENT_ROOT}/%(root)s%(repo_prefix)s%(pub)s/$1 [NE,L]\n"
            % locals())
%>
% endfor pub

<%
paths = set()
root = context.get("sroot")
for pub, repo_path, repo_prefix, writable_root in pubs:
        paths.add((repo_path, repo_prefix))
        context.write(
            "Alias /%(root)s%(repo_prefix)s%(pub)s %(repo_path)s\n" %
            locals())
for repo_path, repo_prefix in paths:
        context.write("# an alias to serve %(repo_path)s content.\n"
            "<Directory \"%(repo_path)s\">\n"
            "    AllowOverride None\n"
            "    Order allow,deny\n"
            "    Allow from all\n"
            "</Directory>\n" % locals())
%>

# Our versions response.
RewriteRule ^/${sroot}.*[/]?versions/0/?$ %{DOCUMENT_ROOT}/versions/0/index.html [L]
# allow for 'OPTIONS * HTTP/1.0' requests
RewriteCond %{REQUEST_METHOD} OPTIONS [NC]
RewriteRule \* - [L]

<%
for repo_prefix in repo_prefixes:
        if root:
                context.write(
                    "# Since we're running as a fragment within an existing\n"
                    "# web server, we take a portion of the namespace for ourselves\n")
                context.write(
                    "Alias /%(root)s %(runtime_dir)s/htdocs/%(root)s\n" %
                     locals())
                context.write(
                    "<Directory \"%(runtime_dir)s/htdocs\">\n"
                    "    AllowOverride None\n"
                    "    Order allow,deny\n"
                    "    Allow from all\n"
                    "</Directory>\n" % locals())
%>

# These location matches are based on the final Rewrite paths for file,
# manifest, catalog and publisher responses.
<LocationMatch ".*/file/../[a-zA-Z0-9]+$">
        Header set Cache-Control "must-revalidate, no-transform, max-age=31536000"
        Header set Content-Type application/data
</LocationMatch>
<LocationMatch ".*/publisher/.*/pkg/.*">
        Header set Cache-Control "must-revalidate, no-transform, max-age=31536000"
        Header set Content-Type text/plain;charset=utf-8
</LocationMatch>
<LocationMatch ".*/catalog/catalog.*.C">
        Header set Cache-Control "must-revalidate, no-transform, max-age=86400"
        Header set Content-Type text/plain;charset=utf-8
</LocationMatch>
<LocationMatch ".*/catalog.attrs">
        Header set Cache-Control no-cache
</LocationMatch>
<LocationMatch ".*/publisher/\d/.*">
        Header set Cache-Control "must-revalidate, no-transform, max-age=31536000"
        Header set Content-Type application/vnd.pkg5.info
</LocationMatch>
