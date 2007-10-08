#!/usr/bin/env python

"""Parse command line arguments.

"""

import getopt
import sys

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

