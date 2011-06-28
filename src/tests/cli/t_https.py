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

#
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.
#
import sys

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os

import pkg.portable as portable
from pkg.client.debugvalues import DebugValues
from pkg.client.transport.exception import TransportFailures

class TestHTTPS(pkg5unittest.SingleDepotTestCase):
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add file tmp/example_file mode=0555 owner=root group=bin path=/usr/bin/example_path
            close"""

        misc_files = ["tmp/example_file"]

        def pkg_image_create(self, *args, **kwargs):
                pkg5unittest.SingleDepotTestCase.pkg_image_create(self,
                    *args, **kwargs)
                self.ta_dir = os.path.join(self.img_path(), "etc/certs/CA")
                os.makedirs(self.ta_dir)

        def image_create(self, *args, **kwargs):
                pkg5unittest.SingleDepotTestCase.image_create(self,
                    *args, **kwargs)
                self.ta_dir = os.path.join(self.img_path(), "etc/certs/CA")
                os.makedirs(self.ta_dir)

        def pkg(self, command, *args, **kwargs):
                # The value for ssl_ca_file is pulled from DebugValues because
                # ssl_ca_file needs to be set there so the api object calls work
                # as desired.
                command = "--debug ssl_ca_file=%s %s" % \
                    (DebugValues["ssl_ca_file"], command)
                return pkg5unittest.SingleDepotTestCase.pkg(self, command,
                    *args, **kwargs)

        def seed_ta_dir(self, certs, dest_dir=None):
                if isinstance(certs, basestring):
                        certs = [certs]
                if not dest_dir:
                        dest_dir = self.ta_dir
                self.assert_(dest_dir)
                self.assert_(self.raw_trust_anchor_dir)
                for c in certs:
                        name = "%s_cert.pem" % c
                        portable.copyfile(
                            os.path.join(self.raw_trust_anchor_dir, name),
                            os.path.join(dest_dir, name))
                        DebugValues["ssl_ca_file"] = os.path.join(dest_dir,
                            name)

        def killalldepots(self):
                try:
                        pkg5unittest.SingleDepotTestCase.killalldepots(self)
                finally:
                        if self.ac:
                                self.debug("killing apache controller")
                                try:
                                        self.ac.kill()
                                except Exception,e :
                                        pass

        def setUp(self):
                self.ac = None
                pkg5unittest.SingleDepotTestCase.setUp(self, start_depot=True)
                self.testdata_dir = os.path.join(self.test_root, "testdata")
                self.make_misc_files(self.misc_files)

                self.durl1 = self.dcs[1].get_depot_url()
                self.rurl1 = self.dcs[1].get_repo_url()

                # Set up the directories that apache needs.
                self.apache_dir = os.path.join(self.test_root, "apache")
                os.makedirs(self.apache_dir)
                self.apache_log_dir = os.path.join(self.apache_dir,
                    "apache_logs")
                os.makedirs(self.apache_log_dir)
                self.apache_content_dir = os.path.join(self.apache_dir,
                    "apache_content")
                self.pidfile = os.path.join(self.apache_dir, "httpd.pid")
                self.common_config_dir = os.path.join(self.test_root,
                    "apache-serve")
                # Choose a port for apache to run on.
                self.https_port = self.next_free_port
                self.next_free_port += 1

                # Set up the paths to the certificates that will be needed.
                self.path_to_certs = os.path.join(self.ro_data_root,
                    "signing_certs", "produced")
                self.keys_dir = os.path.join(self.path_to_certs, "keys")
                self.cs_dir = os.path.join(self.path_to_certs,
                    "code_signing_certs")
                self.chain_certs_dir = os.path.join(self.path_to_certs,
                    "chain_certs")
                self.pub_cas_dir = os.path.join(self.path_to_certs,
                    "publisher_cas")
                self.inter_certs_dir = os.path.join(self.path_to_certs,
                    "inter_certs")
                self.raw_trust_anchor_dir = os.path.join(self.path_to_certs,
                    "trust_anchors")
                self.crl_dir = os.path.join(self.path_to_certs, "crl")

                self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                conf_dict = {
                    "common_log_format": "%h %l %u %t \\\"%r\\\" %>s %b",
                    "https_port": self.https_port,
                    "log_locs": self.apache_log_dir,
                    "pidfile": self.pidfile,
                    "port": self.https_port,
                    "proxied-server": self.durl1,
                    "serve_root": self.apache_content_dir,
                    "server-ssl-cert":os.path.join(self.cs_dir,
                        "cs1_ta7_cert.pem"),
                    "server-ssl-key":os.path.join(self.keys_dir,
                        "cs1_ta7_key.pem"),
                    "server-ca-cert":os.path.join(self.raw_trust_anchor_dir,
                        "ta6_cert.pem"),
                    "server-ca-taname": "ta6",
                    "ssl-special": "%{SSL_CLIENT_I_DN_OU}",
                }

                self.https_conf_path = os.path.join(self.test_root,
                    "https.conf")
                with open(self.https_conf_path, "wb") as fh:
                        fh.write(self.https_conf % conf_dict)
                
                self.ac = pkg5unittest.ApacheController(self.https_conf_path,
                    self.https_port, self.common_config_dir, https=True)
                self.acurl = self.ac.url

        def test_01_basics(self):
                """Test that adding a https publisher works and that a package
                can be installed from that publisher."""

                self.ac.start()
                # Test that creating an image using a HTTPS repo without
                # providing any keys or certificates fails.
                self.assertRaises(TransportFailures, self.image_create,
                    self.acurl)
                self.pkg_image_create(repourl=self.acurl, exit=1)
                api_obj = self.image_create()

                # Test that adding a HTTPS repo fails if the image does not
                # contain the trust anchor to verify the server's identity.
                self.pkg("set-publisher -k %(key)s -c %(cert)s -p %(url)s" % {
                    "url": self.acurl,
                    "cert": os.path.join(self.cs_dir, "cs1_ta6_cert.pem"),
                    "key": os.path.join(self.keys_dir, "cs1_ta6_key.pem"),
                }, exit=1)

                # Add the trust anchor needed to verify the server's identity to
                # the image.
                self.seed_ta_dir("ta7")
                self.pkg("set-publisher -k %(key)s -c %(cert)s -p %(url)s" % {
                    "url": self.acurl,
                    "cert": os.path.join(self.cs_dir, "cs1_ta6_cert.pem"),
                    "key": os.path.join(self.keys_dir, "cs1_ta6_key.pem"),
                })
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

                # Verify that if the image location changes, SSL operations
                # are still possible.  (The paths to key and cert should be
                # updated on load.)
                opath = self.img_path()
                npath = opath.replace("image0", "new.image")
                portable.rename(opath, npath)
                odebug = DebugValues["ssl_ca_file"]
                DebugValues["ssl_ca_file"] = odebug.replace("image0",
                    "new.image")
                self.pkg("-R %s refresh --full test" % npath)

                # Listing the test publisher causes its cert and key to be
                # validated.
                self.pkg("-R %s publisher test" % npath)
                assert os.path.join("new.image", "var", "pkg", "ssl") in \
                    self.output

                # Restore image to original location.
                portable.rename(npath, opath)
                DebugValues["ssl_ca_file"] = odebug

        https_conf = """\
# Configuration and logfile names: If the filenames you specify for many
# of the server's control files begin with "/" (or "drive:/" for Win32), the
# server will use that explicit path.  If the filenames do *not* begin
# with "/", the value of ServerRoot is prepended -- so "/var/apache2/2.2/logs/foo_log"
# with ServerRoot set to "/usr/apache2/2.2" will be interpreted by the
# server as "/usr/apache2/2.2//var/apache2/2.2/logs/foo_log".

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

PidFile "%(pidfile)s"

#
# Listen: Allows you to bind Apache to specific IP addresses and/or
# ports, instead of the default. See also the <VirtualHost>
# directive.
#
# Change this to Listen on specific IP addresses as shown below to 
# prevent Apache from glomming onto all bound IP addresses.
#
Listen 0.0.0.0:%(https_port)s

#
# Dynamic Shared Object (DSO) Support
#
# To be able to use the functionality of a module which was built as a DSO you
# have to place corresponding `LoadModule' lines within the appropriate 
# (32-bit or 64-bit module) /etc/apache2/2.2/conf.d/modules-*.load file so that
# the directives contained in it are actually available _before_ they are used.
#
<IfDefine 64bit>
Include /etc/apache2/2.2/conf.d/modules-64.load
</IfDefine>
<IfDefine !64bit>
Include /etc/apache2/2.2/conf.d/modules-32.load
</IfDefine>

<IfModule !mpm_netware_module>
#
# If you wish httpd to run as a different user or group, you must run
# httpd as root initially and it will switch.  
#
# User/Group: The name (or #number) of the user/group to run httpd as.
# It is usually good practice to create a dedicated user and group for
# running httpd, as with most system services.
#
User webservd
Group webservd

</IfModule>

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
# ServerName gives the name and port that the server uses to identify itself.
# This can often be determined automatically, but we recommend you specify
# it explicitly to prevent problems during startup.
#
# If your host doesn't have a registered DNS name, enter its IP address here.
#
ServerName 127.0.0.1

#
# DocumentRoot: The directory out of which you will serve your
# documents. By default, all requests are taken from this directory, but
# symbolic links and aliases may be used to point to other locations.
#
DocumentRoot "/"

#
# Each directory to which Apache has access can be configured with respect
# to which services and features are allowed and/or disabled in that
# directory (and its subdirectories). 
#
# First, we configure the "default" to be a very restrictive set of 
# features.  
#
<Directory />
    Options None
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
ErrorLog "%(log_locs)s/error_log"

#
# LogLevel: Control the number of messages logged to the error_log.
# Possible values include: debug, info, notice, warn, error, crit,
# alert, emerg.
#
LogLevel debug



<IfModule log_config_module>
    #
    # The following directives define some format nicknames for use with
    # a CustomLog directive (see below).
    #
    LogFormat "%(common_log_format)s" common

    #
    # The location and format of the access logfile (Common Logfile Format).
    # If you do not define any access logfiles within a <VirtualHost>
    # container, they will be logged here.  Contrariwise, if you *do*
    # define per-<VirtualHost> access logfiles, transactions will be
    # logged therein and *not* in this file.
    #
    CustomLog "%(log_locs)s/access_log" common
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

<IfModule mime_module>
    #
    # TypesConfig points to the file containing the list of mappings from
    # filename extension to MIME-type.
    #
    TypesConfig /etc/apache2/2.2/mime.types

    #
    # AddType allows you to add to or override the MIME configuration
    # file specified in TypesConfig for specific file types.
    #
    AddType application/x-compress .Z
    AddType application/x-gzip .gz .tgz

    # Add a new mime.type for .p5i file extension so that clicking on
    # this file type on a web page launches PackageManager in a Webinstall mode.
    AddType application/vnd.pkg5.info .p5i
</IfModule>

#
# Note: The following must must be present to support
#       starting without SSL on platforms with no /dev/random equivalent
#       but a statically compiled-in mod_ssl.
#
<IfModule ssl_module>
SSLRandomSeed startup builtin
SSLRandomSeed connect builtin
</IfModule>

<VirtualHost 0.0.0.0:%(https_port)s>
        AllowEncodedSlashes On
        ProxyRequests Off
        MaxKeepAliveRequests 10000

        SSLEngine On

        # Cert paths
        SSLCertificateFile %(server-ssl-cert)s
        SSLCertificateKeyFile %(server-ssl-key)s

        # Combined product CA certs for client verification
        SSLCACertificateFile %(server-ca-cert)s

	SSLVerifyClient require

        <Location />
                SSLVerifyDepth 1

	        # The client's certificate must pass verification, and must have
	        # a CN which matches this repository.
                SSLRequire ( %(ssl-special)s =~ m/%(server-ca-taname)s/ )

                # set max to number of threads in depot
                ProxyPass %(proxied-server)s/ nocanon max=500
        </Location>
</VirtualHost>


"""
