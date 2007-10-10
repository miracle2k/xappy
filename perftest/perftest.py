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
r"""perftest.py: Perform automated performance tests.

This script performs automated performance tests of the Xappy module.

First, it downloads sample data to use for the performance tests, if such data
isn't already downloaded.

Next, it performs some timed indexing runs, producing CSV log files and graphs
of the performance of these runs.

Next, it performs some timed search runs, producing CSV log files and graphs
of the performance of these runs.


FIXME - needs to have support for clearing the cache between runs (but also do
some hot-cache runs):

To clear the cache:
 1. If /proc/sys/vm/drop_caches exists, and is writable, writing "1" to it
    clears the cache.
 2. Otherwise, creates a large file containing random data, read all the
    data from it, and then delete it.


"""

import getopt
import os
import os.path
import shutil
import sys
import time
import urllib
import setuppaths

import indexer
import searcher
try:
    import analyse_indexlogs
    import analyse_searchlogs
except ImportError:
    analyse_indexlogs = None
    analyse_searchlogs = None


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
    print("  --searchruns: How many times to repeat each search run")
    print("  --usedb: Use a particular existing database (only do search tests)")
    sys.exit(exitval)

def parse_argv(argv, **defaults):
    config = Config(**defaults)
    try:
        optlist, argv = getopt.gnu_getopt(argv, 'ho:t:p',
                                          ('help', 'outdir=', 'tmpdir=', 'preserve', 'searchruns=', 'usedb='))
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
            elif opt == '--usedb':
                config.usedb = val
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

        print "Starting index run (creating %s)" % dbpath
        indexer.index_file(inputfile=testrun.inputfile,
                           dbpath=dbpath,
                           logpath=indexlogpath,
                           flushspeed=testrun.flushspeed,
                           description=testrun.description,
                           maxdocs=testrun.maxdocs,
                           logspeed=testrun.logspeed)
        print "Ending index run"

def do_search(config, testrun):
    dbpath = testrun.dbpath(config)
    # FIXME - clear cache before first run
    for runnum in range(1, config.searchruns + 1):
        for queryfile, concurrency, extraargs in testrun.queryruns:
            searchlogfile = testrun.searchlogpath(config, queryfile, concurrency, extraargs, runnum)

            if config.preserve and \
               os.path.exists(searchlogfile):
                continue

            print "Starting search run (logging to %s)" % searchlogfile 
            tests = searcher.QueryTests(queryfile, dbpath, searchlogfile, concurrency, **extraargs)
            tests.run()
            print "Ending search run"

def analyse_index(config):
    if analyse_indexlogs is None:
        return
    alltimes = {}

    for testrun in config.testruns:
        if testrun.noindex:
            continue
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
    if analyse_searchlogs is None:
        return
    for testrun in config.testruns:
        for runnum in range(1, config.searchruns + 1):
            for queryfile, concurrency, extraargs in testrun.queryruns:
                searchlogpath = testrun.searchlogpath(config, queryfile, concurrency, extraargs, runnum)
                outprefix = testrun.searchoutprefix(config, queryfile, concurrency, extraargs, runnum)

                log = analyse_searchlogs.parse_logfile(searchlogpath)
                title = testrun.description
                title += ", " + os.path.basename(queryfile)
                if concurrency != 1:
                    title += ", concurrency=%d" % concurrency
                for arg in extraargs:
                    if arg == 'range':
                        title += ", range=%s,%d,%d" % extraargs[arg]
                    elif arg == 'gettags':
                        title += ", gettags=%s,%d" % extraargs[arg]
                    else:
                        title += ", %s=%s" % (arg, extraargs[arg])

                analyse_searchlogs.generate_figures(log, outprefix, title)


class TestRun(object):
    def __init__(self, inputfile, description, flushspeed=10000, maxdocs=None, logspeed=1000, noindex=False):
        """

         - description: textual description of this run (excluding information
           about other parameters specified here)
         - flushspeed: frequency (ie, number of adds) with which to explicitly
           call flush() on the database.
         - maxdocs: maximum number of documents to add (stop automatically
           after this many).
         - logspeed: make a log entry each time we add "logspeed" documents.
         - noindex: If True, don't do an indexing run (use existing database)

        """
        self.inputfile = os.path.abspath(inputfile)
        self.description = description
        self.flushspeed = flushspeed
        self.maxdocs = maxdocs
        self.logspeed = logspeed
        self.noindex = noindex
        self.queryruns = []

    def add_query_run(self, queryfile, concurrency, **extraargs):
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
        if self.noindex:
            return self.inputfile
        return os.path.join(config.tmpdir, 'db_%s' % self._index_pathbit())

    def indexlogpath(self, config):
        return os.path.join(config.outdir, 'indexlog_%s.csv' % self._index_pathbit())

    def indexoutprefix(self, config):
        return os.path.join(config.outdir, 'index_%s_' % self._index_pathbit())

    def extraargs_pathbit(self, extraargs):
        extraargs_list = list(extraargs.iteritems())
        extraargs_list.sort()
        extraargs = []
        for key, val in extraargs_list:
            extraargs.append(key + "_" + str(val))

        extraargs = '_'.join(extraargs)
        extraargs = self._filename_safe_path(extraargs)
        while extraargs.endswith('_'):
            extraargs = extraargs[:-1]
        if extraargs == '':
            return ''
        return "_" + extraargs

    def queryfile_pathbit(self, queryfile):
        return self._filename_safe_path(os.path.splitext(os.path.basename(queryfile))[0])

    def searchlogpath(self, config, queryfile, concurrency, extraargs, runnum):
        return os.path.join(config.outdir, 'searchlog_%s_%s_threads%d%s_run%d.csv' %
                            (self._index_pathbit(),
                             self.queryfile_pathbit(queryfile),
                             concurrency,
                             self.extraargs_pathbit(extraargs),
                             runnum))

    def searchoutprefix(self, config, queryfile, concurrency, extraargs, runnum):
        return os.path.join(config.outdir, 'search_%s_%s_threads%d%s_run%d_' %
                            (self._index_pathbit(),
                             self.queryfile_pathbit(queryfile),
                             concurrency,
                             self.extraargs_pathbit(extraargs),
                             runnum))

    def searchdumpdir(self, config, queryfile, concurrency, extraargs, runnum):
        return os.path.join(config.tmpdir, 'searchdump_%s_%s_threads%d%s_run%d' %
                            (self._index_pathbit(),
                             self.queryfile_pathbit(queryfile),
                             concurrency,
                             self.extraargs_pathbit(extraargs),
                             runnum))


if __name__ == '__main__':
    config = parse_argv(sys.argv,
                        tmpdir='perftesttmpdir',
                        outdir='perftestoutdir',
                        preserve=False,
                        searchruns=5,
                        usedb=None)
    for key in ('tmpdir', 'outdir', ):
        setattr(config, key, os.path.abspath(getattr(config, key)))

    # Build up a set of test runs to do.
    config.testruns = []

    # Comment out the index runs with different flush values for now.
    if False:
        testrun = TestRun("sampledata/wikipedia.dump", "wikipedia", flushspeed=1, maxdocs=1000, logspeed=10)
        config.testruns.append(testrun)

        testrun = TestRun("sampledata/wikipedia.dump", "wikipedia", flushspeed=10, maxdocs=1000, logspeed=10)
        config.testruns.append(testrun)

        testrun = TestRun("sampledata/wikipedia.dump", "wikipedia", 1000, maxdocs=10000)
        config.testruns.append(testrun)

        testrun = TestRun("sampledata/wikipedia.dump", "wikipedia", 10000)
        config.testruns.append(testrun)

    if config.usedb is None:
        testrun = TestRun("sampledata/wikipedia.dump", "wikipedia", 100000)
    else:
        testrun = TestRun(config.usedb, "wikipedia", noindex=True)
    testrun.add_query_run("sampledata/queries.txt", 1)
    testrun.add_query_run("sampledata/queries.txt", 1, use_or=True)
    testrun.add_query_run("sampledata/queries.txt", 10)
    testrun.add_query_run("sampledata/queries.txt", 100)

    testrun.add_query_run("sampledata/queries.txt", 1, sort="doclen")
    testrun.add_query_run("sampledata/queries.txt", 1, collapse="doclen")
    testrun.add_query_run("sampledata/queries.txt", 1, range=("doclen", 10000, 30000))
    #testrun.add_query_run("sampledata/queries.txt", 1, getfacets=10)
    #testrun.add_query_run("sampledata/queries.txt", 1, gettags=("tags",10))
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
        if not testrun.noindex:
            do_index(config, testrun)

    analyse_index(config)

    # Do the searching
    for testrun in config.testruns:
        do_search(config, testrun)

    analyse_search(config)
