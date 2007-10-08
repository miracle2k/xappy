#!/usr/bin/env python

"""Run performance tests.

"""

import getopt
import os
import os.path
import shutil
import sys
import subprocess
import time
import urllib
import setuppaths

import indexer
import analyse_indexlogs
#import searcher
import analyse_searchlogs


class Config(object):
    def __init__(self, **kwargs):
        for key, val in kwargs.iteritems():
            setattr(self, key, val)

def usage(exitval):
    print("Usage: perftest.py [options]")
    print("Options are:")
    print("  --help: Get help message")
    print("  --outdir: Set output directory")
    print("  --tmpdir: Set temporary directory")
    print("  --preserve: Preserve existing runs")
    sys.exit(exitval)

def parse_argv(argv, **defaults):
    config = Config(**defaults)
    try:
        optlist, argv = getopt.gnu_getopt(argv, 'ho:t:p',
                                          ('help', 'outdir=', 'tmpdir=', 'preserve', 'searchruns='))
        for (opt, val) in optlist:
            if opt == '-h' or opt == '--help':
                usage(0)
            elif opt == '-o' or opt == '--outdir':
                config.outdir = val
            elif opt == '-t' or opt == '--tmpdir':
                config.tmpdir = val
            elif opt == '-p' or opt == '--preserve':
                config.preserve = True
            elif opt == '--searchruns':
                config.searchruns = int(val)
            else:
                print("Unknown option %r" % opt)
                usage(1)
    except getopt.GetoptError, e:
        print("Bad options: %r" % str(e))
        usage(1)

    if len(argv) != 1:
        print("Wrong number of arguments")
        usage(1)

    return config

def do_index(config, testrun):
    dbpath = testrun.dbpath(config)
    indexlogpath = testrun.indexlogpath(config)

    if not config.preserve or \
       not os.path.exists(dbpath) or \
       not os.path.exists(indexlogpath):

        if os.path.exists(dbpath):
            shutil.rmtree(dbpath)
        if os.path.exists(indexlogpath):
            os.unlink(indexlogpath)

        indexer.index_file(inputfile=testrun.inputfile,
                           dbpath=dbpath,
                           logpath=indexlogpath,
                           flushspeed=testrun.flushspeed,
                           description=testrun.description,
                           maxdocs=testrun.maxdocs,
                           logspeed=testrun.logspeed)

def do_search(config, testrun):
    dbpath = testrun.dbpath(config)
    for runnum in range(1, config.searchruns + 1):
        for queryfile, concurrency, extraargs in testrun.queryruns:
            searchlogfile = testrun.searchlogpath(config, queryfile, concurrency, extraargs, runnum)
            serverlogfile = testrun.serverlogpath(config, queryfile, concurrency, extraargs, runnum)
            searchdumpdir = testrun.searchdumpdir(config, queryfile, concurrency, extraargs, runnum)

            if config.preserve and \
               os.path.exists(searchlogfile) and \
               os.path.exists(searchdumpdir):
                continue

            if os.path.exists(searchdumpdir):
                shutil.rmtree(searchdumpdir)
            if not os.path.exists(searchdumpdir):
                os.mkdir(searchdumpdir)

            # start search server
            print("Starting search server")
            dbpath = testrun.dbpath(config)
            subp = subprocess.Popen(('/usr/bin/env', 'python',
                                     '../src/start.py',
                                     '--dbdir=%s' % os.path.dirname(dbpath),
                                     '--log=%s' % serverlogfile,
                                     ))
            try:
                time.sleep(2)

                if len(extraargs) > 0 and not extraargs.endswith('&'):
                    extraargs += '&'
                searcher.run_query_file('127.0.0.1', 7080,
                                        '/json/search?%s' % extraargs +
                                        urllib.urlencode(
                                            (
                                             ('db', os.path.basename(dbpath)),
                                            )
                                        ) + '&query=',
                                        queryfile, concurrency, searchlogfile,
                                        searchdumpdir,
                                        testrun.description,
                                        runnum)

            finally:
                # stop search server
                print("Stopping search server")
                os.kill(subp.pid, 9)
                subp.wait()
                time.sleep(2)

def analyse_index(config):
    alltimes = {}

    for testrun in config.testruns:
        indexlogpath = testrun.indexlogpath(config)
        outprefix = testrun.indexoutprefix(config)

        desc_line, times = analyse_indexlogs.parse_logfile(indexlogpath)
        title_line = testrun.description
        if testrun.maxdocs is not None:
            title_line += ", maxdocs=%d" % testrun.maxdocs
        title_line += ", flush=%d" % testrun.flushspeed
        filenameprefix = testrun.filename_safe_description() + testrun.maxdocs_pathbit()

        analyse_indexlogs.generate_figures(times, outprefix, title_line)
        if filenameprefix not in alltimes:
            alltimes[filenameprefix] = (testrun.description, [])
        alltimes[filenameprefix][1].append(("flush=%d" % testrun.flushspeed, times))

    for desc in alltimes.iterkeys():
        outprefix = os.path.join(config.outdir, 'index_comparison_%s_' % (desc, ))
        analyse_indexlogs.generate_comparison_figures(alltimes[desc][1], outprefix, alltimes[desc][0])

def analyse_search(config):
    for testrun in config.testruns:
        for runnum in range(1, config.searchruns + 1):
            for queryfile, concurrency, extraargs in testrun.queryruns:
                searchlogpath = testrun.searchlogpath(config, queryfile, concurrency, extraargs, runnum)
                outprefix = testrun.searchoutprefix(config, queryfile, concurrency, extraargs, runnum)

                log = analyse_searchlogs.parse_logfile(searchlogpath)
                analyse_searchlogs.generate_figures(log, outprefix,
                                                    testrun.description + ", " +
                                                    os.path.basename(queryfile) + ", " +
                                                    "concurrency=%d" % concurrency)


class TestRun(object):
    def __init__(self, inputfile, description, flushspeed=10000, maxdocs=None, logspeed=1000):
        """

         - description: textual description of this run (excluding information
           about other parameters specified here)
         - flushspeed: frequency (ie, number of adds) with which to explicitly
           call flush() on the database.
         - maxdocs: maximum number of documents to add (stop automatically
           after this many).
         - logspeed: make a log entry each time we add "logspeed" documents.

        """
        self.inputfile = os.path.abspath(inputfile)
        self.description = description
        self.flushspeed = flushspeed
        self.maxdocs = maxdocs
        self.logspeed = logspeed
        self.queryruns = []

    def add_query_run(self, queryfile, concurrency, extraargs=''):
        self.queryruns.append((os.path.abspath(queryfile), concurrency, extraargs))

    def maxdocs_pathbit(self):
        if self.maxdocs is None: return ''
        return "_maxdocs%d" % self.maxdocs

    def _flushspeed_pathbit(self):
        return "_flush%d" % self.flushspeed

    def _index_pathbit(self):
        return "%s%s%s" % (self.filename_safe_description(),
                           self._flushspeed_pathbit(),
                           self.maxdocs_pathbit())

    def _filename_safe_path(self, path):
        desc = []
        for char in path.lower():
            if char.isalnum():
                desc.append(char)
            elif len(desc) > 0 and desc[-1] != '_':
                desc.append('_')
        return ''.join(desc)

    def filename_safe_description(self):
        return self._filename_safe_path(self.description)

    def dbpath(self, config):
        return os.path.join(config.tmpdir, 'db_%s' % self._index_pathbit())

    def indexlogpath(self, config):
        return os.path.join(config.outdir, 'indexlog_%s.csv' % self._index_pathbit())

    def indexoutprefix(self, config):
        return os.path.join(config.outdir, 'index_%s_' % self._index_pathbit())

    def searchlogpath(self, config, queryfile, concurrency, extraargs, runnum):
        return os.path.join(config.outdir, 'searchlog_%s_query%s_mult%d_%s_%d.csv' %
                            (self._index_pathbit(),
                             self._filename_safe_path(os.path.basename(queryfile)),
                             concurrency,
                             self._filename_safe_path(extraargs),
                             runnum))

    def serverlogpath(self, config, queryfile, concurrency, extraargs, runnum):
        return os.path.join(config.tmpdir, 'serverlog_%s_query%s_mult%d_%s_%d.csv' %
                            (self._index_pathbit(),
                             self._filename_safe_path(os.path.basename(queryfile)),
                             concurrency,
                             self._filename_safe_path(extraargs),
                             runnum))

    def searchoutprefix(self, config, queryfile, concurrency, extraargs, runnum):
        return os.path.join(config.outdir, 'search_%s_query%s_mult%d_%s_%d_' %
                            (self._index_pathbit(),
                             self._filename_safe_path(os.path.basename(queryfile)),
                             concurrency,
                             self._filename_safe_path(extraargs),
                             runnum))

    def searchdumpdir(self, config, queryfile, concurrency, extraargs, runnum):
        return os.path.join(config.tmpdir, 'searchdump_%s_query%s_mult%d_%s_%d' %
                            (self._index_pathbit(),
                             self._filename_safe_path(os.path.basename(queryfile)),
                             concurrency,
                             self._filename_safe_path(extraargs),
                             runnum))


if __name__ == '__main__':
    config = parse_argv(sys.argv,
                        tmpdir='perftesttmpdir',
                        outdir='perftestoutdir',
                        preserve=False,
                        searchruns=5)
    for key in ('tmpdir', 'outdir', ):
        setattr(config, key, os.path.abspath(getattr(config, key)))

    # Build up a set of test runs to do.
    config.testruns = []

    testrun = TestRun("sampledata/wikipedia.dump", "wikipedia", flushspeed=1, maxdocs=1000, logspeed=10)
    config.testruns.append(testrun)

    testrun = TestRun("sampledata/wikipedia.dump", "wikipedia", flushspeed=10, maxdocs=1000, logspeed=10)
    config.testruns.append(testrun)

    testrun = TestRun("sampledata/wikipedia.dump", "wikipedia", 1000)
    config.testruns.append(testrun)

    testrun = TestRun("sampledata/wikipedia.dump", "wikipedia", 10000)
    config.testruns.append(testrun)

    testrun = TestRun("sampledata/wikipedia.dump", "wikipedia", 100000)
    config.testruns.append(testrun)

    testrun = TestRun("sampledata/wikipedia.dump", "wikipedia", 1000000)
    testrun.add_query_run("sampledata/productqueries.txt", 1)
    testrun.add_query_run("sampledata/productqueries.txt", 10)
    testrun.add_query_run("sampledata/productqueries.txt", 100)

    testrun.add_query_run("sampledata/productqueries.txt", 1, "sort=price")
    testrun.add_query_run("sampledata/productqueries.txt", 1, "range=price,5,20")
    testrun.add_query_run("sampledata/productqueries.txt", 1, "getfacets=10")
    testrun.add_query_run("sampledata/productqueries.txt", 1, "gettags=tags,10")
    config.testruns.append(testrun)

    # Make directories (and ensure they're empty)
    if not config.preserve:
        if os.path.exists(config.outdir):
            shutil.rmtree(config.outdir)
        if os.path.exists(config.tmpdir):
            shutil.rmtree(config.tmpdir)
    if not os.path.exists(config.outdir):
        os.mkdir(config.outdir)
    if not os.path.exists(config.tmpdir):
        os.mkdir(config.tmpdir)

    # Do the indexing
    for testrun in config.testruns:
        do_index(config, testrun)

    analyse_index(config)

    # Do the searching
    for testrun in config.testruns:
        do_search(config, testrun)

    analyse_search(config)
