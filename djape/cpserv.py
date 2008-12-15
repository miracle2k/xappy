#!/usr/bin/env python

import sys
import os.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ext'))

import cherrypy.wsgiserver
from djape.server.application import Application

server = cherrypy.wsgiserver.CherryPyWSGIServer(('0.0.0.0', 8080),
                                                Application())
                                                

if __name__ == '__main__':
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
