#!/usr/bin/env python
#
# Copyright (C) 2007 Lemur Consulting Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import sys
import time
import thread
import threading
import getopt
import xappy

class TestRunner(threading.Thread):
    def __init__(self, tests, num):
        threading.Thread.__init__(self)
        self.tests = tests
        self.num = num
        self.sconn = xappy.SearchConnection(tests.dbdir)

    def run(self):
        try:
            while True:
                querynum, query = self.tests.get_query()
                query = query.strip()
                querystart = time.time()

                if self.tests.use_or:
                    parsedquery = self.sconn.query_parse(query,
                                                         default_op=self.sconn.OP_OR)
                else:
                    parsedquery = self.sconn.query_parse(query)
                if self.tests.range is not None:
                    rangequery = self.sconn.query_range(*self.tests.range)
                    parsedquery = self.sconn.query_filter(parsedquery, rangequery)

                search_getfacets = (self.tests.getfacets is not None)
                search_gettags = None
                if self.tests.gettags is not None:
                    self.search_gettags = self.tests.gettags[0]

                results = self.sconn.search(parsedquery, 0, 10,
                                            sortby=self.tests.sort,
                                            collapse=self.tests.collapse,
                                            getfacets=search_getfacets,
                                            gettags=search_gettags)
                self.tests.log_search(self.num, querynum, results.matches_estimated, querystart, parsedquery.get_length(), query)
        except StopIteration:
            return


class QueryTests(object):
    def __init__(self, queryfile=None, dbdir=None, logfile=None, threads=1,
                 sort=None, collapse=None, range=None, getfacets=None,
                 gettags=None, use_or=False):
        self.queryfile = queryfile
        self.dbdir = dbdir
        self.logfile = logfile

        self.qfd = open(queryfile)
        self.logfd = open(logfile, "a")
        self.logfd.write("Thread Num,Query Num,Count of queries with some matches,Estimated matches,Time (seconds),Elapsed Time(seconds)\n")
        self.querycount = 0
        self.matchingcount = 0
        self.starttime = time.time()
        self.threads = threads

        self.use_or = use_or

        self.sort = sort
        self.collapse = collapse
        self.range = range
        self.getfacets = getfacets
        self.gettags = gettags

        self.mutex = threading.Lock()

    def get_query(self):
        self.mutex.acquire()
        try:
            q = self.qfd.readline()
            if len(q) == 0:
                raise StopIteration
            self.querycount += 1
            return self.querycount, q
        finally:
            self.mutex.release()

    def log_search(self, threadnum, querynum, resultest, querystart, querylen, query):
        self.mutex.acquire()
        try:
            try:
                if resultest != 0:
                    self.matchingcount += 1
                currtime = time.time()
                self.logfd.write("%d,%d,%d,%d,%f,%f,%d,%r\n" % (threadnum,
                                                                querynum,
                                                                self.matchingcount,
                                                                resultest,
                                                                currtime - querystart,
                                                                currtime - self.starttime,
                                                                querylen,
                                                                query))
                self.logfd.flush()
            except StopIteration:
                return
        finally:
            self.mutex.release()

    def run(self):
        for i in xrange(self.threads):
            runner = TestRunner(self, i + 1)
            runner.start()
        runner.join()
