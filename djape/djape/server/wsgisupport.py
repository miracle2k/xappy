"""Support utilities for building a WSGI application.

"""

import cgi
import StringIO

def to_uni(text):
    """Convert text into unicode, if it's not already unicode.

    """
    if isinstance(text, str):
        return text.decode('utf-8')
    return text

class Request(object):
    """Request object, used to represent a request via WSGI.

    """
    def __init__(self, environ):
        self.path = to_uni(environ.get('PATH_INFO', u'/'))
        if not self.path:
            self.path = u'/'
        self.path_components = self.path.split(u'/')[1:]

        # FIXME - set method
        self.method = environ['REQUEST_METHOD'].upper()

        self.GET = cgi.parse_qs(environ.get('QUERY_STRING', ''))
        self.POST = {}

        if self.method == 'POST':
            try:
                content_length = int(environ.get('CONTENT_LENGTH', 0))
            except (ValueError, TypeError):
                content_length = 0
            if content_length > 0:
                fd = environ['wsgi.input']
                buf = StringIO.StringIO()
                while content_length > 0:
                    chunk = fd.read(min(content_length, 65536))
                    if not chunk:
                        break
                    buf.write(chunk)
                    content_length -= len(chunk)
                self.raw_post_data = buf.getvalue()
                buf.close()
            else:
                self.raw_post_data = ''
            self.POST = cgi.parse_qs(self.raw_post_data)

class WSGIResponse(object):
    """Object satisfying the WSGI protocol for make a response.

    """
    def __init__(self, start_response, response):
        self.start_response = start_response
        self.response = response

    def __iter__(self):
        self.start_response(self.response.status, self.response.headers)
        yield self.response.body

    def __len__(self):
        return len(self.response.body)

class Response(object):
    """Response object, used to return stuff via WSGI protocol.

    """
    def __init__(self, body='', status='200 OK', mimetype='text/plain'):
        self.status = status
        self.headers = []
        self.body = body
        self.headers.append(("Content-Type", mimetype))

class SpecialResponse(Exception, Response):
    def __init__(self, status, msg):
        Exception.__init__(self)
        body = status + '\n' + msg
        Response.__init__(self, body=body, status=status)

class ResponseNotFound(SpecialResponse):
    """Raise this exception if a requested resource is not found.

    """
    def __init__(self, path):
        SpecialResponse.__init__(self, u'404 NOT FOUND', 'Path \'%s\' not found' % path)

class ResponseServerError(SpecialResponse):
    """Raise this exception if a server error occurs.

    """
    def __init__(self, body):
        SpecialResponse.__init__(self, u'500 SERVER ERROR', body)


