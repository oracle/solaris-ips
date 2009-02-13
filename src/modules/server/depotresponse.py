#
# copyright (c) 2004-2007, cherrypy team (team@cherrypy.org)
# all rights reserved.
#
# redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#     * redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#     * neither the name of the cherrypy team nor the names of its contributors
#       may be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# this software is provided by the copyright holders and contributors "as is" and
# any express or implied warranties, including, but not limited to, the implied
# warranties of merchantability and fitness for a particular purpose are
# disclaimed. in no event shall the copyright owner or contributors be liable
# for any direct, indirect, incidental, special, exemplary, or consequential
# damages (including, but not limited to, procurement of substitute goods or
# services; loss of use, data, or profits; or business interruption) however
# caused and on any theory of liability, whether in contract, strict liability,
# or tort (including negligence or otherwise) arising in any way out of the use
# of this software, even if advised of the possibility of such damage.
#

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import sys as _sys
import cherrypy as _cherrypy
from cherrypy import _cperror
from cherrypy import _cpwsgi

class DepotResponse(_cpwsgi.AppResponse):
        """ This class is a partial combination of a cherrypy's original
            AppResponse class with a change to "Stage 2" of setapp to provide
            access to the write() callable specified by PEP 333.  Access to this
            callable is necessary to maintain a minimal memory and disk
            footprint for streaming operations performed by the depot server,
            such as filelist. """

        def __add_write_hook(self, s, h, exc):
                # The WSGI specification includes a special write()
                # callable returned by the start_response callable.
                # cherrypy traditionally hides this from applications
                # as new WSGI applications and frameworks are not
                # supposed to use it if at all possible.  The write()
                # callable is considered a hack to support imperative
                # streaming APIs.
                #
                # As a result, we have to provide access to the write()
                # callable ourselves by replacing the default
                # response_class with our own.  This callable is
                # provided so that streaming APIs can be treated as if
                # their output had been yielded by an iterable.
                #
                # The cherrypy singleton below is thread-local, and
                # guaranteed to only be set for a specific request.
                # This means any callables that use the singleton
                # to access this method are guaranteed to write output
                # back to the same request.
                #
                # See: http://www.python.org/dev/peps/pep-0333/
                #
                _cherrypy.response.write = self.start_response(s, h, exc)

        def setapp(self):
                try:
                        self.request = self.get_request()
                        s, h, b = self.get_response()
                        self.iter_response = iter(b)
                        self.__add_write_hook(s, h, None)
                except self.throws:
                        self.close()
                        raise
                except _cherrypy.InternalRedirect, ir:
                        self.environ['cherrypy.previous_request'] = _cherrypy.serving.request
                        self.close()
                        self.iredirect(ir.path, ir.query_string)
                        return
                except:
                        if getattr(self.request, "throw_errors", False):
                                self.close()
                                raise

                        tb = _cperror.format_exc()
                        _cherrypy.log(tb, severity=40)
                        if not getattr(self.request, "show_tracebacks", True):
                                tb = ""
                        s, h, b = _cperror.bare_error(tb)
                        self.iter_response = iter(b)

                        try:
                                self.__add_write_hook(s, h, _sys.exc_info())
                        except:
                                # "The application must not trap any exceptions raised by
                                # start_response, if it called start_response with exc_info.
                                # Instead, it should allow such exceptions to propagate
                                # back to the server or gateway."
                                # But we still log and call close() to clean up ourselves.
                                _cherrypy.log(traceback=True, severity=40)
                                self.close()
                                raise

