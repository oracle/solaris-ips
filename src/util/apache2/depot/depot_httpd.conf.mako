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
# Copyright (c) 2013, 2023, Oracle and/or its affiliates.
#

#
# This file is the template for the Apache configuration that serves pkg(7)
# repositories.
#
</%doc>
<%
        import os.path
        context.write("""
#
# This is an automatically generated file for IPS repositories, and
# should not be modified directly.  Changes made to this file will be
# overwritten the next time svc:/application/pkg/server:default is
# refreshed or restarted.  /etc/pkg/depot/conf.d can be used for user
# customizations.
#
""")
%>

#
# ServerRoot: The top of the directory tree under which the server's
# configuration, error, and log files are kept.
#
# Do not add a slash at the end of the directory path.  If you point
# ServerRoot at a non-local disk, be sure to point the LockFile directive
# at a local disk.  If you wish to share the same ServerRoot for multiple
# httpd daemons, you will need to change at least LockFile and PidFile.
#
ServerRoot "/usr/apache2/2.4"
PidFile "${runtime_dir}/../depot_httpd.pid"
#
# Listen: Allows you to bind Apache to specific IP addresses and/or
# ports, instead of the default. See also the <VirtualHost>
# directive.
#
# Change this to Listen on specific IP addresses as shown below to
# prevent Apache from glomming onto all bound IP addresses.
#
# Listen 12.34.56.78:80

Listen ${host}:${port}

#
# Dynamic Shared Object (DSO) Support
#
# To be able to use the functionality of a module which was built as a DSO you
# have to include a `LoadModule' line so that the directives contained in it
# are actually available _before_ they are used.
#

LoadModule access_compat_module libexec/mod_access_compat.so
LoadModule alias_module libexec/mod_alias.so
LoadModule authn_core_module libexec/mod_authn_core.so
LoadModule authz_core_module libexec/mod_authz_core.so
LoadModule authz_host_module libexec/mod_authz_host.so
LoadModule cache_module libexec/mod_cache.so
LoadModule cache_disk_module libexec/mod_cache_disk.so
LoadModule deflate_module libexec/mod_deflate.so
LoadModule filter_module libexec/mod_filter.so
LoadModule dir_module libexec/mod_dir.so
LoadModule env_module libexec/mod_env.so
LoadModule headers_module libexec/mod_headers.so
LoadModule log_config_module libexec/mod_log_config.so
LoadModule mime_module libexec/mod_mime.so
LoadModule mpm_event_module libexec/mod_mpm_event.so
LoadModule rewrite_module libexec/mod_rewrite.so
LoadModule ssl_module libexec/mod_ssl.so
LoadModule socache_shmcb_module libexec/mod_socache_shmcb.so
LoadModule unixd_module libexec/mod_unixd.so
<%!
    import os
    import sys
%>
<%
        context.write("""
LoadModule wsgi_module libexec/mod_wsgi-{0}.{1}.so
""".format(*sys.version_info[0:2]))
%>

#
# Prevent the browser from rendering the  web page in an <iframe>
# unless it comes from the same origin as the page itself. This is to avoid
# Clickjacking attacks by ensuring that the content is not embedded into other
# sites. We only allow it if it comes from the same origin since we need that
# The X-Frame-Options is supported by most browsers.
# The Content-Security-Policy is a more modern option which will not work for
# all browsers.
#
Header always append X-Frame-Options SAMEORIGIN
Header always append Content-Security-Policy "frame-ancestors 'self'"

#
# Enable XSS filtering by having the browser prevent rendering the
# web page if a cross-site scripting (XSS) attack is detected.
#
Header always set X-XSS-Protection "1; mode=block"

#
# Prevent browsers from trying to guess the type of data in a file. This
# assumes that the web server correctly reports the content type in the header.
#
Header always set X-Content-Type-Options "nosniff"

#
# Restrict cookie to the current site.
#
Header always edit Set-Cookie ^(.*)$ $1;SameSite=strict

# Turn on deflate for file types that support it
AddOutputFilterByType DEFLATE text/html application/javascript text/css text/plain
# We only alias a specific script, not all files in ${template_dir}
WSGIScriptAlias ${sroot}/depot ${template_dir}/depot_index.py

# We set a 5 minute inactivity timeout: if no requests have been received in the
# last 5 minutes and no requests are currently being processed, mod_wsgi shuts
# down the Python interpreter. An exception is made for index-refresh
# operations, which are allowed to run to completion by periodically sending
# requests to the server during the course of the refresh.
<%
        test_proto = os.environ.get("PKG5_TEST_PROTO", None)
        if test_proto:
                context.write("""
WSGIDaemonProcess pkgdepot processes=1 threads=21 user=pkg5srv group=pkg5srv display-name=pkg5_depot inactivity-timeout=300 python-path={0}/usr/lib/python{1}.{2}
SetEnv PKG5_TEST_PROTO {3}
""".format(test_proto, *sys.version_info[0:2], test_proto))
        else:
                context.write("""
WSGIDaemonProcess pkgdepot processes=1 threads=21 user=pkg5srv group=pkg5srv display-name=pkg5_depot inactivity-timeout=300
""")
%>
WSGIProcessGroup pkgdepot
WSGISocketPrefix ${runtime_dir}/wsgi
# don't accept requests over 100k
LimitRequestBody 102400
# Set environment variables used by our wsgi application
SetEnv PKG5_RUNTIME_DIR ${runtime_dir}

#
# If you wish httpd to run as a different user or group, you must run
# httpd as root initially and it will switch.
#
# User/Group: The name (or #number) of the user/group to run httpd as.
# It is usually good practice to create a dedicated user and group for
# running httpd, as with most system services.
#
User pkg5srv
Group pkg5srv

# 'Main' server configuration
#
# The directives in this section set up the values used by the 'main'
# server, which responds to any requests that aren't handled by a
# <VirtualHost> definition.  These values also provide defaults for
# any <VirtualHost> containers you may define later in the file.
#
# All of these directives may appear inside <VirtualHost> containers,
# in which case these default settings will be overridden for the
# virtual host being defined.
#

#
# ServerAdmin: Your address, where problems with the server should be
# e-mailed.  This address appears on some server-generated pages, such
# as error documents.  e.g. admin@your-domain.com
#
ServerAdmin you@example.com

#
# ServerName gives the name and port that the server uses to identify itself.
# This can often be determined automatically, but we recommend you specify
# it explicitly to prevent problems during startup.
#
# If your host doesn't have a registered DNS name, enter its IP address here.
#
# Workaround an Apache bug where IPv6 addresses in server names are not accepted
<%
        servername = context.get("host")
        serverport = context.get("port")
        if ":" not in servername:
                context.write("ServerName {host}:{port}\n".format(
                    host=servername, port=serverport))
%>

#
# DocumentRoot: The directory out of which you will serve your
# documents. By default, all requests are taken from this directory, but
# symbolic links and aliases may be used to point to other locations.
#
DocumentRoot "${runtime_dir}/htdocs"

#
# Each directory to which Apache has access can be configured with respect
# to which services and features are allowed and/or disabled in that
# directory (and its subdirectories).
#
# First, we configure the "default" to be a very restrictive set of
# features.
#
<Directory />
    Options FollowSymLinks
    AllowOverride None
    Require all denied
</Directory>

#
# Note that from this point forward you must specifically allow
# particular features to be enabled - so if something's not working as
# you might expect, make sure that you have specifically enabled it
# below.
#

#
# This should be changed to whatever you set DocumentRoot to.
#
<Directory "${runtime_dir}/htdocs">
    #
    # Possible values for the Options directive are "None", "All",
    # or any combination of:
    #   Indexes Includes FollowSymLinks SymLinksifOwnerMatch ExecCGI MultiViews
    #
    # Note that "MultiViews" must be named *explicitly* --- "Options All"
    # doesn't give it to you.
    #
    # The Options directive is both complicated and important.  Please see
    # http://httpd.apache.org/docs/2.4/mod/core.html#options
    # for more information.
    #
    Options FollowSymLinks

    #
    # AllowOverride controls what directives may be placed in .htaccess files.
    # It can be "All", "None", or any combination of the keywords:
    #   Options FileInfo AuthConfig Limit
    #
    AllowOverride None

    #
    # Controls who can get stuff from this server.
    #
    Require all granted

</Directory>

# Allow access to wsgi scripts under ${template_dir}
<Directory ${template_dir}>
    SetHandler wsgi-script
    WSGIProcessGroup pkgdepot
    Options ExecCGI
    Require all granted
</Directory>

#
# DirectoryIndex: sets the file that Apache will serve if a directory
# is requested.
#
<IfModule dir_module>
    DirectoryIndex index.html
</IfModule>

#
# The following lines prevent .htaccess and .htpasswd files from being
# viewed by Web clients.
#
<FilesMatch "^\.ht">
    Require all denied
</FilesMatch>

#
# ErrorLog: The location of the error log file.
# If you do not specify an ErrorLog directive within a <VirtualHost>
# container, error messages relating to that virtual host will be
# logged here.  If you *do* define an error logfile for a <VirtualHost>
# container, that host's errors will be logged there and not here.
#
ErrorLog "${log_dir}/error_log"

#
# LogLevel: Control the number of messages logged to the error_log.
# Possible values include: debug, info, notice, warn, error, crit,
# alert, emerg.
#
LogLevel warn rewrite:debug

<IfModule log_config_module>
    #
    # The following directives define some format nicknames for use with
    # a CustomLog directive (see below).
    #
    LogFormat "%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\"" combined
    LogFormat "%h %l %u %t \"%r\" %>s %b" common

    <IfModule logio_module>
      # You need to enable mod_logio.c to use %I and %O
      LogFormat "%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\" %I %O" combinedio
    </IfModule>

    #
    # The location and format of the access logfile (Common Logfile Format).
    # If you do not define any access logfiles within a <VirtualHost>
    # container, they will be logged here.  Contrariwise, if you *do*
    # define per-<VirtualHost> access logfiles, transactions will be
    # logged therein and *not* in this file.
    #
    CustomLog "${log_dir}/access_log" common

    #
    # If you prefer a logfile with access, agent, and referer information
    # (Combined Logfile Format) you can use the following directive.
    #
    #CustomLog "/var/apache2/2.4/logs/access_log" combined
</IfModule>

#
# Note: The following must must be present to support
#       starting without SSL on platforms with no /dev/random equivalent
#       but a statically compiled-in mod_ssl.
#
<IfModule ssl_module>
SSLRandomSeed startup builtin
SSLRandomSeed connect builtin
SSLSessionCache shmcb:${cache_dir}/ssl_scache(512000)
Include ${template_dir}/depot_httpd_ssl_protocol.conf
</IfModule>


% if allow_refresh:
# When set to true, we allow admin/0 operations to rebuild the index
SetEnv PKG5_ALLOW_REFRESH true
% endif

% if int(cache_size) > 0:
CacheRoot ${cache_dir}
# The levels and length of the cache directories can
# be small here, as ZFS is good at dealing with directories
# containing many files.
CacheDirLevels 1
CacheDirLength 2
# A 44mb seems like a reasonable size for the largest
# file we will choose to cache.
CacheMaxFileSize 45690876
% endif

<%
        ssl_cert_file_path = context.get("ssl_cert_file", "")
        ssl_key_file_path = context.get("ssl_key_file", "")
        if ssl_cert_file_path and ssl_key_file_path:
                context.write("""
# DNS domain name of the server
ServerName {0}
# enable SSL
SSLEngine On
# Location of the server certificate and key.
""".format(context.get("host", "localhost")))
                context.write("SSLCertificateFile {0}\n".format(ssl_cert_file_path))
                context.write("SSLCertificateKeyFile {0}\n".format(ssl_key_file_path))
                context.write("""
# Intermediate CA certificate file. Required if your server certificate
# is not signed by a top-level CA directly but an intermediate authority.
# Comment out this section if you don't need one or if you are using a
# test certificate
""")
                ssl_cert_chain_file_path = context.get("ssl_cert_chain_file",
                    "")
                if ssl_cert_chain_file_path:
                        context.write("SSLCertificateChainFile {0}\n".format(
                            ssl_cert_chain_file_path))
                else:
                        context.write("# SSLCertificateChainFile /cert_path\n")
%>

# Rules to serve static content directly from the file-repositories.
<%include file="/depot.conf.mako"/>
# with no URL-path, we show an index of the available repositories.
RewriteRule ^${sroot}[/]?$ ${sroot}/depot/repos.shtml [NE,PT]

<%
        path_info = set()
        root = context.get("sroot")
        context.write("# the repositories our search app should index.\n")
        for pub, repo_path, repo_prefix, writable_root in pubs:
                path_info.add(
                    (repo_path, repo_prefix.rstrip("/"), writable_root))
        for repo_path, repo_prefix, writable_root in path_info:
                context.write(
                    "SetEnv PKG5_REPOSITORY_{repo_prefix} {repo_path}\n".format(
                    **locals()))
                if writable_root:
                        context.write(
                            "SetEnv PKG5_WRITABLE_ROOT_{repo_prefix} "
                            "{writable_root}\n".format(**locals()))
                context.write("RewriteRule ^/{root}{repo_prefix}/[/]?$ "
                    "{root}/depot/{repo_prefix}/ [NE,PT]\n".format(
                    **locals()))
                context.write("RewriteRule ^/{root}{repo_prefix}/([a-z][a-z])[/]?$ "
                    "{root}/depot/{repo_prefix}/$1 [NE,PT]\n".format(
                    **locals()))
%>
% for pub, repo_path, repo_prefix, writable_root in pubs:
% if int(cache_size) > 0:
CacheEnable disk /${root}${repo_prefix}${pub}/file
CacheEnable disk /${root}${repo_prefix}${pub}/manifest
% endif
<%
        #
        # A series of rules to redirect into /depot where the WSGI application
        # is mounted to serve requests for the BUI application.
        #
        root = context.get("sroot")
        # search responses
        context.write("RewriteRule ^/{root}{repo_prefix}{pub}/search/(.*)$ "
            "{root}/depot/{repo_prefix}{pub}/search/$1 [NE,PT]\n".format(
            **locals()))
        # admin responses
        context.write("RewriteRule ^/{root}{repo_prefix}{pub}/admin/(.*)$ "
            "{root}/depot/{repo_prefix}{pub}/admin/$1 [NE,PT]\n".format(
            **locals()))
        # info responses
        context.write("RewriteRule ^/{root}{repo_prefix}{pub}/info/(.*)$ "
            "{root}/depot/{repo_prefix}{pub}/info/$1 [NE,PT]\n".format(
            **locals()))
        # p5i responses
        context.write("RewriteRule ^/{root}{repo_prefix}{pub}/p5i/(.*)$ "
            "{root}/depot/{repo_prefix}{pub}/p5i/$1 [NE,PT]\n".format(
            **locals()))
        # Deal with languages - any two letter language code.
        context.write("RewriteRule ^/{root}{repo_prefix}{pub}/([a-z][a-z])/(.*)$ "
            "{root}/depot/{repo_prefix}{pub}/$1/$2 [NE,PT]\n".format(
            **locals()))
        context.write("RewriteRule ^/{root}{repo_prefix}{pub}/([a-z][a-z])$ "
            "{root}/depot/{repo_prefix}{pub}/$1/ [NE,PT]\n".format(
            **locals()))
        # Deal with just the publisher
        context.write("RewriteRule ^/{root}{repo_prefix}{pub}[/]?$ "
            "{root}/depot/{repo_prefix}{pub}/ [NE,PT]\n".format(
            **locals()))
        # redirect themes requests into the CherryPy code
        context.write("RewriteRule ^/{root}{repo_prefix}{pub}/_themes/(.*)$ "
            "{root}/depot/{repo_prefix}{pub}/_themes/$1 [NE,PT]\n".format(
            **locals()))
%>
% endfor pub
RewriteRule ^${sroot}/_themes/(.*)$ ${sroot}/depot/_themes/$1 [NE,PT]
RewriteRule ^${sroot}/repos.shtml$ ${sroot}/depot/repos.shtml [NE,PT]

% for pub, repo_path, repo_prefix in default_pubs:
<%
        #
        # When publisher names are not included in the request, we use the
        # default publisher set in the repository.
        #
        root = context.get("sroot")
        context.write("# Map the default publishers for {repo_path} to "
            "{pub}\n".format(**locals()))

        if "pub" != None:
                # search
                context.write("RewriteRule ^/{root}{repo_prefix}search/(.*)$ "
                    "{root}/depot/{repo_prefix}{pub}/search/$1 [NE,PT]\n"
                   .format(**locals()))
                # admin
                context.write("RewriteRule ^/{root}{repo_prefix}admin/(.*)$ "
                    "{root}/depot/{repo_prefix}{pub}/admin/$1 [NE,PT]\n"
                   .format(**locals()))
                # info
                context.write("RewriteRule ^/{root}{repo_prefix}info/(.*)$ "
                    "{root}/depot/{repo_prefix}{pub}/info/$1 [NE,PT]\n"
                   .format(**locals()))
                # p5i
                context.write("RewriteRule ^/{root}{repo_prefix}p5i/(.*)$ "
                    "{root}/depot/{repo_prefix}{pub}/p5i/$1 [NE,PT]\n"
                   .format(**locals()))
                # Deal with languages - any two-letter language code.
                context.write("RewriteRule ^/{root}{repo_prefix}([a-z][a-z])/(.*)$ "
                        "{root}/depot/{repo_prefix}{pub}/$1/$2 [NE,PT]\n".format(
                        **locals()))
                # redirect themes requests into the CherryPy code
                context.write("RewriteRule ^/{root}{repo_prefix}_themes/(.*)$ "
                    "{root}/depot/{repo_prefix}{pub}/_themes/$1 [NE,PT]\n".format(
                    **locals()))
%>
% endfor pub

# Don't cache search requests.
<LocationMatch ".*/search/\d/.*">
        Header set Content-Type "text/plain;charset=utf-8"
        Header set Cache-Control no-cache
</LocationMatch>

<%
        if not test_proto:
                context.write("""
# Include any site-specific configuration
IncludeOptional /etc/pkg/depot/conf.d/*.conf
""")
%>
