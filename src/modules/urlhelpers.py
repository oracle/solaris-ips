# Additional classes to supplement functionality in urllib2

import urllib2
import urllib
import httplib
import socket

class HTTPSCertHandler(urllib2.HTTPSHandler):

        def __init__(self, key_file=None, cert_file=None, strict=None):
                self.key = key_file
                self.cert = cert_file
                self.strict = strict

                urllib2.AbstractHTTPHandler.__init__(self)

        def https_open(self, req):
                host = req.get_host()
                if not host:
                        raise urllib2.URLError('no host given')

                h = httplib.HTTPSConnection(host, key_file=self.key,
                    cert_file=self.cert, strict=self.strict)
                h.set_debuglevel(self._debuglevel)

                headers = dict(req.headers)
                headers.update(req.unredirected_hdrs)
                headers["Connection"] = "close"
                try:
                        h.request(req.get_method(), req.get_selector(), req.data, headers)
                        r = h.getresponse()
                except socket.error, err:
                        raise urllib2.URLError(err)

                r.recv = r.read
                fp = socket._fileobject(r)

                resp = urllib.addinfourl(fp, r.msg, req.get_full_url())
                resp.code = r.status
                resp.msg = r.reason
                return resp


        https_request = urllib2.AbstractHTTPHandler.do_request_
