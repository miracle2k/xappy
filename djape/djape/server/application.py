"""WSGI application wrapping the search server.

"""

import search
import settings
import traceback
from wsgisupport import SpecialResponse, Request, ResponseNotFound, \
                        ResponseServerError, WSGIResponse

class Application(object):
    """WSGI application wrapping the search server.

    """
    urls = {
        u'search': {
            u'latestapi': search.latestapi,
            u'0': {
                # Searching and getting info
                u'search': search.search,
                u'get': search.get,
                u'parse_latlong': search.parse_latlong,

                # Database administration
                u'listdbs': search.listdbs,
                u'newdb': search.newdb,
                u'deldb': search.deldb,

                # Database modification
                u'add': search.add,
            }
        }
    }

    def __call__(self, environ, start_response):
        try:
            request = Request(environ)
            # FIXME - make logging customisable
            print request.method, request.path
            handlers = self.urls
            for i in xrange(len(request.path_components)):
                handler = handlers.get(request.path_components[i], None)
                if handler is None:
                    break
                if hasattr(handler, '__call__'):
                    break
                handlers = handler
            if handler is None:
                raise ResponseNotFound(request.path)
            if not hasattr(handler, '__call__'):
                raise ResponseNotFound(request.path)
            return WSGIResponse(start_response,
                                handler(request,
                                        *(request.path_components[i + 1:])))
        except SpecialResponse, e:
            return WSGIResponse(start_response, e)
        except Exception, e:
            # Handle uncaught exceptions by returning a 500 error.
            # FIXME - make logging customisable
            traceback.print_exc()
            return WSGIResponse(start_response, ResponseServerError(str(e)))
