System Publisher Apache Configuration
-------------------------------------

This directory contains templates for the system publisher Apache configuration.
For more information, see pkg.sysrepo(1M).

The files in this directory are as follows:

./reference_httpd.conf			The reference Apache config file used to
					as a source for the content in
					sysrepo_httpd.conf.mako.

./sysrepo_publisher_response.mako	The template used for the "publisher/0
					response, served by the system publisher
					for client queries to file:// publishers
					(not normally used by syspub clients,
					who obtain all their publisher
					information from the "syspub/0"
					response.  This allows the system
					publisher to serve file:// repositories
					to standard pkg(5) clients over http.

./logs/error_log			Stub file used as an Apache log
./logs/access_log			Stub file used as an Apache log

./sysrepo_httpd.conf.mako		The main Apache httpd.conf file template
					which is used by pkg.sysrepo(1M) in
					conjunction with the publisher
					information obtained from a pkg(5) image
					to configure Apache to act as a
					system publisher.  This file was created
					with reference to the
					reference_httpd.conf file in this
					directory.

