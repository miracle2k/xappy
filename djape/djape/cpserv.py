#!/usr/bin/env python

import cherrypy
from server.application import Application

server = cherrypy.wsgiserver.CherryPyWSGIServer(('0.0.0.0', 8080),
                                                Application())
                                                

if __name__ == '__main__':
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
