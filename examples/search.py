#!/usr/bin/env python

import sys
import os
import re

def _setup_path():
    """Set up sys.path to allow us to import secore when run uninstalled.

    """
    abspath = os.path.abspath(__file__)
    dirname = os.path.dirname(abspath)
    dirname, ourdir = os.path.split(dirname)
    dirname, parentdir = os.path.split(dirname)
    if (parentdir, ourdir) == ('secore', 'examples'):
        sys.path.insert(0, '..')

_setup_path()
import secore


_whitespace_re = re.compile('\s+')

def open_index(dbpath):
    return secore.SearchConnection(dbpath)

def main(argv):
    dbpath = 'foo'
    search = ' '.join(argv[1:])
    sconn = open_index(dbpath)
    print "Searching %d documents for \"%s\"" % (
        sconn.get_doccount(),
        search
    )

    q = sconn.query_parse(search, default_op=sconn.OP_AND)
    results = sconn.search(q, 0, 10)
    if results.estimate_is_exact:
        print "Found %d results" % results.matches_estimated
    else:
        print "Found approximately %d results" % results.matches_estimated
    for result in results:
        print result.data['path'][0]
        try:
            summary = result.summarise('text', hl=('*', '*'), maxlen=300)
            summary = ' '.join(_whitespace_re.split(summary))
            print summary
        except KeyError:
            pass
        print

if __name__ == '__main__':
    main(sys.argv)
