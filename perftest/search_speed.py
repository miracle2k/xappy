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

def _setup_path():
    """Set up sys.path to allow us to import secore when run uninstalled.

    """
    abspath = os.path.abspath(__file__)
    dirname = os.path.dirname(abspath)
    dirname, ourdir = os.path.split(dirname)
    if os.path.exists(os.path.join(dirname, 'secore')):
        if ourdir == 'perftest':
            sys.path.insert(0, dirname)

_setup_path()
import secore

class TestRunner(threading.Thread):
    def __init__(self, tests, num):
        threading.Thread.__init__(self)
        self.tests = tests
        self.num = num
        self.sconn = secore.SearchConnection(tests.dbdir)

    def run(self):
        try:
            while True:
                querynum, query = self.tests.get_query()
                query = query.strip()
                querystart = time.time()
                parsedquery = self.sconn.query_parse(query)
                if self.tests.rangefield is not None:
                    rangequery = self.sconn.query_range(self.tests.rangefield, self.tests.rangebegin, self.tests.rangeend)
                    parsedquery = self.sconn.query_filter(parsedquery, rangequery)
                results = self.sconn.search(parsedquery, 0, 10,
                                            sortby=self.tests.sort,
                                            collapse=self.tests.collapse)
                self.tests.log_search(results.matches_estimated, querystart, self.num, query, parsedquery.get_length(), querynum)
        except StopIteration:
            return


class QueryTests(object):
    def __init__(self, queryfile=None, dbdir=None, logfile=None, threads=1,
                 rangefield=None, rangebegin=None, rangeend=None,
                 sort=None, collapse=None):
        self.queryfile = queryfile
        self.dbdir = dbdir
        self.logfile = logfile

        self.qfd = open(queryfile)
        self.logfd = open(logfile, "a")
        self.logfd.write("Thread Num,Query Count,Matching Count,Estimated matches,Time (seconds),Total Time(seconds)\n")
        self.querycount = 0
        self.matchingcount = 0
        self.starttime = time.time()
        self.threads = threads

        self.rangefield = rangefield
        self.rangebegin = rangebegin
        self.rangeend = rangeend
        self.sort = sort
        self.collapse = collapse

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

    def log_search(self, resultest, querystart, threadnum, query, querylen, querynum):
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

def usage(exitval):
    print("Usage: search_speed.py [options] <queryfile> <dbdir> <logfile>")
    print("Options are:")
    print("  --threads=<threads>: set number of threads to use")
    print("  --range=<field>,<begin>,<end>: filter results with a range")
    print("  --sort=<field>: sort on a field")
    print("  --collapse=<field>: collapse on a field")
    sys.exit(exitval)

def parse_argv(argv):
    kwargs = {}
    kwargs['queryfile'] = None
    kwargs['dbdir'] = None
    kwargs['logfile'] = None
    kwargs['threads'] = 1
    try:
        optlist, args = getopt.gnu_getopt(argv, 'h', ('help', 'threads=', 'range=', 'sort=', 'collapse='))
        for (opt, val) in optlist:
            if opt == '-h' or opt == '--help':
                usage(0)
            elif opt == '--threads':
                kwargs['threads'] = int(val)
            elif opt == '--range':
                field,begin,end = val.split(',')
                kwargs['rangefield'] = field
                kwargs['rangebegin'] = begin
                kwargs['rangeend'] = end
            elif opt == '--sort':
                kwargs['sort'] = val
            elif opt == '--collapse':
                kwargs['collapse'] = val
            else:
                print("Unknown option %r" % opt)
                usage(1)
    except getopt.GetoptError, e:
        print("Bad options: %r" % str(e))
        usage(1)

    if len(args) < 4 or len(args) > 5:
        print("Wrong number of arguments")
        usage(1)
    kwargs['queryfile'] = args[1]
    kwargs['dbdir'] = args[2]
    kwargs['logfile'] = args[3]
    if len(args) > 4:
       kwargs['threads'] = int(args[4])

    return kwargs

if __name__ == '__main__':
    tests = QueryTests(**parse_argv(sys.argv))
    tests.run()
