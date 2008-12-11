# Additional classes to supplement functionality in urllib2

import urllib2
import urllib
from urlparse import urlparse
import httplib
import socket
import base64

class HTTPSCertHandler(urllib2.HTTPSHandler):

        def __init__(self, key_file=None, cert_file=None, strict=None):
                self.key = key_file
                self.cert = cert_file
                self.strict = strict

                urllib2.AbstractHTTPHandler.__init__(self)

        def https_open(self, req):
                if hasattr(req, 'connection'):
                        # have the connection from the proxy, make it ssl
                        h = req.connection
                        ssl = socket.ssl(h.sock, self.key, self.cert)
                        h.sock = httplib.FakeSocket(h.sock, ssl)
                        h.strict = self.strict
                else:
                        host = req.get_host()
                        if not host:
                                raise urllib2.URLError('no host given')

                        h = httplib.HTTPSConnection(host, key_file=self.key,
                            cert_file=self.cert, strict=self.strict)
                        h.set_debuglevel(self._debuglevel)
                        self.connection = h

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

class HTTPSProxyHandler(urllib2.ProxyHandler):
        # Proxies must be in front
        handler_order = 100

        def __init__(self, proxies=None):
                if proxies is None:
                        proxies = urllib2.getproxies()
                assert isinstance(proxies, dict)
                # only handle https proxy
                self.proxy = None
                if 'https' in proxies:
                        self.proxy = proxies['https']

        def https_open(self, req):
                # do nothing if no proxy is defined
                if not self.proxy:
                        return None

                realurl = urlparse(req.get_full_url())
                assert(realurl[0] == 'https')
                real_host, real_port = urllib.splitport(realurl[1])
                if real_port is None:
                        real_port = 443

                proxyurl = urlparse(self.proxy)
                phost = proxyurl[1]
                pw_hdr = ''
                if '@' in phost:
                        user_pass, phost = host.split('@', 1)
                        if ':' in user_pass:
                                user, password = user_pass.split(':', 1)
                                user_pass = base64.encodestring(
                                    '%s:%s' % (unquote(user),
                                    unquote(password))).strip()
                        pw_hdr = 'Proxy-authorization: Basic %s\r\n' % user_pass
                phost = urllib.unquote(phost)
                req.set_proxy(phost, proxyurl[0])

                h = httplib.HTTPConnection(phost)
                h.connect()
                # send proxy CONNECT request
                h.send("CONNECT %s:%d HTTP/1.0%s\r\n\r\n" % \
                    (real_host, real_port, pw_hdr))
                # expect a HTTP/1.0 200 Connection established
                response = h.response_class(h.sock, strict=h.strict, 
                    method=h._method)
                response.begin()
                if response.status != httplib.OK:
                        # proxy returned an error: abort connection, 
                        # and raise exception
                        h.close()
                        raise urllib2.HTTPError, \
                            (self.proxy, response.status,
                            "proxy connection failed: %s" % response.reason,
                            None, None)

                # make the connection available for HTTPSCertHandler
                req.connection = h
                return None        
