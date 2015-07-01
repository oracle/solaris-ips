#!/usr/bin/python2.7
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
# Copyright (c) 2012, 2015, Oracle and/or its affiliates. All rights reserved.

from __future__ import print_function
import pkg.p5p

import os
import shutil
import simplejson
import six
import sys
import threading
import traceback
from six.moves import http_client

# redirecting stdout for proper WSGI portability
sys.stdout = sys.stderr

SERVER_OK_STATUS = "{0} {1}".format(http_client.OK, http_client.responses[http_client.OK])
SERVER_ERROR_STATUS = "{0} {1}".format(http_client.INTERNAL_SERVER_ERROR,
    http_client.responses[http_client.INTERNAL_SERVER_ERROR])
SERVER_NOTFOUND_STATUS = "{0} {1}".format(http_client.NOT_FOUND,
    http_client.responses[http_client.NOT_FOUND])
SERVER_BADREQUEST_STATUS = "{0} {1}".format(http_client.BAD_REQUEST,
    http_client.responses[http_client.BAD_REQUEST])

response_headers = [("content-type", "application/binary")]

p5p_indices = {}

# A lock to prevent two threads from rebuilding our catalog parts cache
# at the same time.
p5p_update_lock = threading.Lock()

class UnknownPathException(Exception):
        """An exception thrown when a client requests a path within a p5p file
        which does not exist."""
        def __init__(self, path):
                self.path = path

        def __str__(self):
                return "Unknown path: {0}".format(self.path)


class MalformedQueryException(Exception):
        """An exception thrown when this wsgi application cannot parse a query
        from the client."""
        def __init__(self, query, reason):
                self.query = query
                self.reason = reason

        def __str__(self):
                return "Malformed query {0}: {1}".format(self.query, self.reason)


class MissingArchiveException(Exception):
        """An exception thrown when the p5p file referred to by the
        configuration does not exist."""
        def __init__(self, path):
                self.path = path

        def __str__(self):
                return "Missing p5p archive: {0}".format(self.path)


class SysrepoP5p(object):
        """An object to handle a request for p5p file contents from the
        system repository."""

        def __init__(self, environ, start_response):
                self.environ = environ
                self.start_response = start_response
                self.p5p_path = None
                self.p5p = None

                self.query = self.environ["QUERY_STRING"]
                self.runtime_dir = self.environ["SYSREPO_RUNTIME_DIR"]

        def close(self):
                """Release any resources we have used."""
                if self.p5p:
                        self.p5p.close()

        def log_exception(self, status=SERVER_ERROR_STATUS):
                """Print some information in the Apache log that will help
                determine what went wrong as well as updating the client
                response code.  The WSGI spec says we can call
                start_response multiple times, but must include exc_info
                if we do so."""

                # we only want error_log output if our status is not 4xx
                if status != SERVER_NOTFOUND_STATUS and \
                    status != SERVER_BADREQUEST_STATUS:
                        print(traceback.format_exc())
                self.start_response(status, response_headers,
                    sys.exc_info())

        def need_update(self, pub, hsh):
                """Determine if we need to update our cached catalog and
                reload the index by comparing the last modification time of a
                file we create per p5p archive, and the p5p archive itself."""

                htdocs_path = os.path.join(self.runtime_dir, "htdocs")
                timestamp_path = \
                    "{htdocs_path}/{pub}/{hsh}/sysrepo.timestamp".format(
                    **locals())

                update = False

                # Locking here is quite basic: we want to ensure that no two
                # threads simultaneously decide that they need to rebuild our
                # local catalog cache, stepping on each others toes.  It is
                # possible that while processing a single query, a user will
                # replace the p5p file on the server after this method has been
                # called, causing stale data to be returned at best, and a HTTP
                # 500 response at worst (as the p5p index used by this web
                # application will not match the one in the new archive)
                p5p_update_lock.acquire()
                try:
                        # don't write a timestamp if we're testing
                        if self.environ.get("PKG5_TEST_ENV") == "True":
                                return True

                        try:
                                st_p5p = os.stat(self.p5p_path)
                        except OSError as e:
                                if e.errno == os.errno.ENOENT:
                                        raise MissingArchiveException(
                                            self.p5p_path)
                        try:
                                st_ts = os.stat(timestamp_path)
                                if st_ts.st_mtime < st_p5p.st_mtime:
                                        open(timestamp_path, "wb").close()
                                        update = True
                        except OSError as e:
                                if e.errno == os.errno.ENOENT:
                                        open(timestamp_path, "wb").close()
                                        update = True

                except MissingArchiveException as e:
                        raise
                except Exception as e:
                        self.log_exception()
                finally:
                        p5p_update_lock.release()
                return update

        def _file_response(self, path, pub):
                """Process our file query."""

                # use the basename of the path, which is the pkg(5) hash
                self.start_response(SERVER_OK_STATUS, response_headers)
                try:
                        return self.p5p.get_package_file(os.path.basename(path),
                            pub=pub)
                except pkg.p5p.UnknownArchiveFiles as e:
                        self.log_exception(status=SERVER_NOTFOUND_STATUS)
                except Exception as e:
                        self.log_exception()

        def _catalog_response(self, path, pub, hsh):
                """Process our catalog query"""

                cat_part = os.path.basename(path)
                htdocs_path = os.path.join(self.runtime_dir, "htdocs")
                cat_path = \
                    "{htdocs_path}/{pub}/{hsh}/catalog/1/{cat_part}".format(
                    **locals())
                self.start_response(SERVER_OK_STATUS, response_headers)
                if os.path.exists(cat_path):
                        return open(cat_path, "rb")

                # this is unlikely to happen: it implies a catalog part has been
                # requested that wasn't listed in the catalog.attrs file
                # extracted during _precache_catalog() or the file has been
                # removed on the server.  Do our best to return the content.
                try:
                        cat_dir = os.path.dirname(cat_path)
                        p5p_update_lock.acquire()
                        try:
                                if not os.path.exists(cat_dir):
                                        os.makedirs(cat_dir, 0o755)
                                self.p5p.extract_catalog1(cat_part, cat_dir,
                                    pub=pub)
                                return open(cat_path, "rb")
                        except (pkg.p5p.UnknownArchiveFiles, IOError) as e:
                                self.log_exception(
                                    status=SERVER_NOTFOUND_STATUS)
                        except Exception as e:
                                self.log_exception()
                        finally:
                                p5p_update_lock.release()
                except OSError as e:
                        if e.errno == os.errno.ENOENT:
                                return open(cat_path, "rb")
                        else:
                                raise

        def _manifest_response(self, path, pub):
                """Return our manifest_response. """

                pkg_name = path.replace("manifest/0/", "")
                fmri = "pkg://{0}/{1}".format(pub, pkg_name)
                mf = None
                self.start_response(SERVER_OK_STATUS, response_headers)
                try:
                        mf = self.p5p.get_package_manifest(fmri, raw=True)
                        return mf
                except pkg.p5p.UnknownPackageManifest as e:
                        self.log_exception(status=SERVER_NOTFOUND_STATUS)
                except pkg.fmri.IllegalFmri as e:
                        self.log_exception(status=SERVER_NOTFOUND_STATUS)
                except Exception as e:
                        self.log_exception()

        def _precache_catalog(self, pub, hsh):
                """Extract the parts from the catalog_dir to the given path."""

                htdocs_path = os.path.join(self.runtime_dir, "htdocs")
                cat_dir = "{htdocs_path}/{pub}/{hsh}/catalog/1".format(
                    **locals())

                if os.path.exists(cat_dir):
                        shutil.rmtree(cat_dir)

                os.makedirs(cat_dir)
                try:
                        self.p5p.extract_catalog1("catalog.attrs", cat_dir,
                            pub=pub)
                        with open(os.path.join(cat_dir, "catalog.attrs"),
                            "rb") as catalog_attrs:
                                json = simplejson.load(catalog_attrs)
                                for part in json["parts"]:
                                        self.p5p.extract_catalog1(part, cat_dir,
                                            pub=pub)

                except pkg.p5p.UnknownArchiveFiles as e:
                        # if the catalog part is unavailable,
                        # we ignore this for now.  It will be
                        # reported later anyway.
                        pass

        def _parse_query(self):
                """Parse our query, returning publisher, hash, and path
                values."""

                keyvals = self.query.split("&")
                attrs = {}
                for keyval in keyvals:
                        try:
                                key, val = keyval.split("=", 1)
                                attrs[key] = val
                        except ValueError:
                                raise MalformedQueryException(self.query,
                                    "missing key=value pair for {0}.".format(keyval))

                pub = attrs.get("pub")
                hsh = attrs.get("hash")
                path = attrs.get("path")

                if not hsh:
                        raise MalformedQueryException(self.query,
                            "missing hash.")
                if hsh not in self.environ:
                        raise MalformedQueryException(self.query,
                            "unknown hash {0}.".format(hsh))
                if not pub:
                        raise MalformedQueryException(self.query,
                            "missing publisher.")
                if not path:
                        raise MalformedQueryException(self.query,
                            "missing path.")
                return pub, hsh, path

        def execute(self):
                """Process a query of the form:

                pub=<publisher>&hash=<hash>&path=<path>

                where:
                    <publisher>    the name of the publisher from the p5p file
                    <hash>         the sha1 hash of the location of the p5p file
                    <path>         the path of the pkg(5) client request

                In the environment of this WSGI application, apart from the
                default WSGI values, defined in PEP333, we expect:

                "SYSREPO_RUNTIME_DIR", a location pointing to the runtime
                directory, allowing us to serve static html from beneath a
                "htdocs" subdir.

                <hash>, which maps the sha1 hash of the p5p archive path, to the
                path itself, which is not visible to clients.
                """

                buf = []
                try:
                        pub, hsh, path = self._parse_query()
                        self.p5p_path = self.environ[hsh]
                        # In order to keep only one copy of the p5p index in
                        # memory, we cache it locally, and reuse it any time
                        # we're opening the same p5p file.  Before doing
                        # so, we need to ensure the p5p file hasn't been
                        # modified since we last looked at it.
                        if self.need_update(pub, hsh) or \
                            self.p5p_path not in p5p_indices:
                                p5p_update_lock.acquire()
                                try:
                                        self.p5p = pkg.p5p.Archive(
                                            self.p5p_path)
                                        p5p_indices[self.p5p_path] = \
                                            self.p5p.get_index()
                                        self._precache_catalog(pub, hsh)
                                except:
                                        raise
                                finally:
                                        p5p_update_lock.release()
                        else:
                                self.p5p = pkg.p5p.Archive(self.p5p_path,
                                    archive_index=p5p_indices[self.p5p_path])

                        if path.startswith("file"):
                                buf = self._file_response(path, pub)
                        elif path.startswith("catalog/1/"):
                                buf = self._catalog_response(path, pub, hsh)
                        elif path.startswith("manifest/0"):
                                buf = self._manifest_response(path, pub)
                        else:
                                raise UnknownPathException(path)
                except OSError as e:
                        print(e.errno)
                        if e.errno == os.errno.ENOENT:
                                self.log_Exception(
                                    status=SERVER_NOTFOUND_STATUS)
                except UnknownPathException as e:
                        self.log_exception(status=SERVER_NOTFOUND_STATUS)
                except MalformedQueryException as e:
                        self.log_exception(status=SERVER_BADREQUEST_STATUS)
                except MissingArchiveException as e:
                        self.log_exception()
                except Exception as e:
                        self.log_exception()
                return buf


#
# CloseGenerator,  AppWrapper and _application as an idiom together
# are described at
# http://code.google.com/p/modwsgi/wiki/RegisteringCleanupCode
# and exist to ensure that we close any server-side resources used by
# our application at the end of the request (i.e. after the client has
# received it)
#

def _application(environ, start_response):
        sysrepo = SysrepoP5p(environ, start_response)
        result = sysrepo.execute()
        return result, sysrepo


class CloseGenerator(object):
        """A wrapper class to ensure we have a close() method on the iterable
        returned from the mod_wsgi application, see PEP333."""

        def __init__(self, iterable, closeable):
                self.__iterable = iterable
                self.__closeable = closeable

        def __iter__(self):
                # if we haven't produced an iterable, that's
                # likely because of an exception. Do nothing.
                if not self.__iterable:
                        return
                for item in self.__iterable:
                        yield item

        def close(self):
                try:
                        if hasattr(self.__iterable, "close"):
                                self.__iterable.close()
                finally:
                        self.__closeable.close()


class AppWrapper(object):
        """Wrap a callable application with this class in order for its results
        to be handled by CloseGenerator when that callable is called."""

        def __init__(self, application):
                self.__application = application

        def __call__(self, environ, start_response):
                result, closeable = self.__application(environ, start_response)
                return CloseGenerator(result, closeable)


application = AppWrapper(_application)

if __name__ == "__main__":
        """A simple main function to allows us to test any given query/env"""
        from six.moves.urllib.parse import unquote

        def start_response(status, response_headers, exc_info=None):
                """A dummy response function."""
                print("responding with {0}".format(status))
                if exc_info:
                        print(traceback.format_exc(exc_info))

        if len(sys.argv) != 3:
                query = \
                ("'pub=test&hash=de5acae11333890c457665379eec812a67f78dd3"
                "&path=manifest/0/mypackage@1.2.9%2C5.11-1%3A20110617T204846Z'")
                alias = \
                "de5acae11333890c457665379eec812a67f78dd3=/tmp/archive.p5p"
                print("usage: sysrepo_p5p <query> <hash>=<path to p5p file>")
                print("eg: ./sysrepo_p5p.py {0} {1}".format(query, alias))
                sys.exit(2)

        environ = {}

        # unquote the url, so that we can easily copy/paste entries from
        # Apache logs when testing.
        environ["QUERY_STRING"] = unquote(sys.argv[1])
        environ["SYSREPO_RUNTIME_DIR"] = os.environ["PWD"]
        environ["PKG5_TEST_ENV"] = "True"
        hsh, path = sys.argv[2].split("=")
        environ[hsh] = path

        for response in application(environ, start_response):
                if isinstance(response, six.string_types):
                        print(response.rstrip())
                elif response:
                        for line in response.readlines():
                                print(line.rstrip())
