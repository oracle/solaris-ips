<%doc>
#
# This file is the template for the IPS system publisher Apache configuration
# file.
#
</%doc>
<%      context.write("""
#
# This is an automatically generated file for the IPS system publisher, and
# should not be modified directly.  Changes made to this file will be
# overwritten the next time svc:/application/pkg/system-repository:default is
# refreshed or restarted.
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
ServerRoot "/usr/apache2/2.2"
PidFile "${sysrepo_runtime_dir}/../sysrepo_httpd.pid"
#
# Listen: Allows you to bind Apache to specific IP addresses and/or
# ports, instead of the default. See also the <VirtualHost>
# directive.
#
# Change this to Listen on specific IP addresses as shown below to
# prevent Apache from glomming onto all bound IP addresses.
#
#Listen 12.34.56.78:80
Listen ${host}:${port}

#
# Dynamic Shared Object (DSO) Support
#
# To be able to use the functionality of a module which was built as a DSO you
# have to include a `LoadModule' line so that the directives contained in it
# are actually available _before_ they are used.
#

LoadModule authz_host_module libexec/64/mod_authz_host.so
LoadModule cache_module libexec/64/mod_cache.so
LoadModule disk_cache_module libexec/64/mod_disk_cache.so
LoadModule mem_cache_module libexec/64/mod_mem_cache.so
LoadModule log_config_module libexec/64/mod_log_config.so
LoadModule proxy_module libexec/64/mod_proxy.so
LoadModule proxy_connect_module libexec/64/mod_proxy_connect.so
LoadModule proxy_http_module libexec/64/mod_proxy_http.so
LoadModule ssl_module libexec/64/mod_ssl.so
LoadModule mime_module libexec/64/mod_mime.so
LoadModule dir_module libexec/64/mod_dir.so
LoadModule alias_module libexec/64/mod_alias.so
LoadModule rewrite_module libexec/64/mod_rewrite.so

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
ServerName ${host}

#
# DocumentRoot: The directory out of which you will serve your
# documents. By default, all requests are taken from this directory, but
# symbolic links and aliases may be used to point to other locations.
#
DocumentRoot "${sysrepo_runtime_dir}/htdocs"

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
    Order deny,allow
    Deny from all
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
<Directory "${sysrepo_runtime_dir}/htdocs">
    #
    # Possible values for the Options directive are "None", "All",
    # or any combination of:
    #   Indexes Includes FollowSymLinks SymLinksifOwnerMatch ExecCGI MultiViews
    #
    # Note that "MultiViews" must be named *explicitly* --- "Options All"
    # doesn't give it to you.
    #
    # The Options directive is both complicated and important.  Please see
    # http://httpd.apache.org/docs/2.2/mod/core.html#options
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
    Order allow,deny
    Allow from 127.0.0.1

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
    Order allow,deny
    Deny from all
    Satisfy All
</FilesMatch>

#
# ErrorLog: The location of the error log file.
# If you do not specify an ErrorLog directive within a <VirtualHost>
# container, error messages relating to that virtual host will be
# logged here.  If you *do* define an error logfile for a <VirtualHost>
# container, that host's errors will be logged there and not here.
#
ErrorLog "${sysrepo_log_dir}/error_log"

#
# LogLevel: Control the number of messages logged to the error_log.
# Possible values include: debug, info, notice, warn, error, crit,
# alert, emerg.
#
LogLevel warn

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
    CustomLog "${sysrepo_log_dir}/access_log" common

    #
    # If you prefer a logfile with access, agent, and referer information
    # (Combined Logfile Format) you can use the following directive.
    #
    #CustomLog "/var/apache2/2.2/logs/access_log" combined
</IfModule>

#
# DefaultType: the default MIME type the server will use for a document
# if it cannot otherwise determine one, such as from filename extensions.
# If your server contains mostly text or HTML documents, "text/plain" is
# a good value.  If most of your content is binary, such as applications
# or images, you may want to use "application/octet-stream" instead to
# keep browsers from trying to display binary files as though they are
# text.
#
DefaultType text/plain

#
# Note: The following must must be present to support
#       starting without SSL on platforms with no /dev/random equivalent
#       but a statically compiled-in mod_ssl.
#
<IfModule ssl_module>
SSLRandomSeed startup builtin
SSLRandomSeed connect builtin
</IfModule>

RewriteEngine on

<%doc> #
       # Specify http and https proxies if we need them
       # values are urls of the form http://<hostname>:[port]
</%doc>
% if http_proxy != None:
ProxyRemote http ${http_proxy}
% endif
% if https_proxy != None:
ProxyRemote https ${https_proxy}
% endif

<%doc> #
       # We only perform caching if cache_dir is set.  It need to be set to
       # an absolute path to a directory writable by the apache process.
       # Alternatively, if set to 'memory', we enable mod_mem_cache.
       #
</%doc>
% if cache_dir != None:
<IfModule mod_cache.c>
% if cache_dir.startswith("/"):
<IfModule mod_disk_cache.c>
CacheRoot ${cache_dir}
CacheEnable disk /
# The levels and length of the cache directories can
# be small here, as ZFS is good at dealing with directories
# containing many files.
CacheDirLevels 1
CacheDirLength 2
# A 44mb seems like a reasonable size for the largest
# file we will choose to cache.
CacheMaxFileSize 45690876
</IfModule>
% elif cache_dir == "memory":
CacheEnable mem /
MCacheSize ${cache_size}
# cache a suitably large number of files
MCacheMaxObjectCount 200000
MCacheMinObjectSize 1
MCacheMaxObjectSize 45690876
% endif
CacheDisable /versions/0
CacheDisable /syspub/0
</IfModule>
% endif

RewriteLog "${sysrepo_log_dir}/rewrite.log"
RewriteLogLevel 0

# We need to allow these as they're encoded in the package/manifest names
# when looking up file:// repositories
AllowEncodedSlashes On

ProxyRequests On

SSLProxyEngine on
SSLProxyMachineCertificateFile ${sysrepo_runtime_dir}/crypto.txt
SSLProxyProtocol all

<Proxy *>
       Order deny,allow
       Deny from all
       Allow from 127.0.0.1
</Proxy>

<%doc>
# All of our rules specify the NE flag, 'noescape', that is
# we don't want any rewritten URLs being decoded en-route through
# the set of RewriteRule directives.
#
# We must be careful to iterate over the URIs in reverse order, since we're
# applying regular expressions that would otherwise match any URIs that happen
# to be substrings of another URI.
#
</%doc>

% for uri in reversed(sorted(uri_pub_map.keys())):
        % for pub, cert_path, key_path, hash in uri_pub_map[uri]:
<%doc>
                # for any https publishers, we want to allow proxy clients
                # access the repos using the key/cert from the sysrepo
                </%doc>
                % if uri.startswith("https:"):
<%
                        no_https = uri.replace("https:", "http:")
                        context.write("RewriteRule ^proxy:%(no_https)s/(.*)$ "
                            "%(uri)s/$1 [P,NE]" % locals())
%>
                % elif uri.startswith("file:"):
<%doc>
                        # Point to our local versions/0 response or
                        # publisher-specific publisher/0, response, then stop.
                        </%doc>
<%
                        context.write("RewriteRule ^/%(pub)s/%(hash)s/versions/0 "
                            "/versions/0/index.html [L,NE]\n" % locals())
                        context.write("RewriteRule ^/%(pub)s/%(hash)s/publisher/0 "
                            "/%(pub)s/%(hash)s/publisher/0/index.html [L,NE]" % locals())
%><%doc>

                        # Modify the catalog and manifest URLs, then
                        # 'passthrough' (PT), letting the Alias below rewrite
                        # the URL instead.
                        </%doc>
<%                      context.write(
                            "RewriteRule ^/%(pub)s/%(hash)s/catalog/1/(.*)$ "
                            "/%(pub)s/%(hash)s/publisher/%(pub)s/catalog/$1 [NE,PT]" %
                            locals())
%><%doc>
                        # file responses are a little tricky - we need to index
                        # the first two characters of the filename and use that
                        # as an index into the directory of filenames.
                        #
                        # eg. the request
                        # http://localhost:15000/pkg5-nightly/abcdef/file/1/87ad645695abb22b2959f73d22022c5cffeccb13
                        # gets rewritten as:
                        # http://localhost:15000/pkg5-nightly/abcdef/publisher/pkg5-nightly/file/87/87ad645695abb22b2959f73d22022c5cffeccb13
                        </%doc>
<%                      context.write("RewriteRule ^/%(pub)s/%(hash)s/file/1/(..)(.*)$ "
                            "/%(pub)s/%(hash)s/publisher/%(pub)s/file/$1/$1$2 [NE,PT]\n"
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
                        #  '/pkg5-nightly/abcdef/manifest/0/package/sysrepo@0.5.11,5.11-0.159:20110308T011843Z'
                        #
                        # which comes from the HTTP request:
                        #  'GET /pkg5-nightly/abcdef/manifest/0/package%2Fsysrepo@0.5.11%2C5.11-0.159%3A20110308T011843Z HTTP/1.1'
                        #
                        # which we eventually rewrite as:
                        #  -> '/pkg5-nightly/abcdef/publisher/pkg5-nightly/pkg/package%2Fsysrepo/0.5.11%2C5.11-0.159%3A20110308T011843Z'
</%doc><%
                        context.write("RewriteRule ^/%(pub)s/%(hash)s/manifest/0/.*$ "
                            "%%{THE_REQUEST} [NE,C]\n" % locals())

                        context.write("RewriteRule ^GET\ "
                            "/%(pub)s/%(hash)s/manifest/0/([^@]+)@([^\ ]+)(\ HTTP/1.1)$ "
                            "/%(pub)s/%(hash)s/publisher/%(pub)s/pkg/$1/$2 [NE,PT,C]\n"
                            % locals())
                        context.write("RewriteRule ^/%(pub)s/%(hash)s/(.*)$ - [NE,L]"
                            % locals())
%>
                % else:
<%                      context.write("RewriteRule ^proxy:%(uri)s/(.*)$ "
                            "%(uri)s/$1 [NE,P]" % locals())
%>
                % endif
        % endfor uri
% endfor pub

# any non-file-based repositories get our local versions and syspub responses
RewriteRule ^.*/versions/0/?$ - [L]
RewriteRule ^.*/syspub/0/?$ - [L]
# allow for 'OPTIONS * HTTP/1.0' requests
RewriteCond %{REQUEST_METHOD} OPTIONS [NC]
RewriteRule \* - [L] 
# catch all, denying everything
RewriteRule ^.*$ - [R=404]

% for uri in reversed(sorted(uri_pub_map.keys())):
        % for pub, cert_path, key_path, hash in uri_pub_map[uri]:
                <%doc>
                # Create an alias for the file repository under ${pub}
                </%doc>
                % if uri.startswith("file:"):
                        <% repo_path = uri.replace("file:", "") %>
# a file repository alias to serve ${uri} content.
<Directory "${repo_path}">
    AllowOverride None
    Order allow,deny
    Allow from 127.0.0.1
</Directory>
                                % if cache_dir != None:
CacheDisable /${pub}/${hash}/publisher/0
CacheDisable /${pub}/${hash}/versions/0
                                % endif
Alias /${pub}/${hash} ${repo_path}
                % endif
        % endfor uri
% endfor pub

