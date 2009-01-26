"""verifies that the document ids in a database don't have any 'gaps'
and start at 1. This is necessary for
decreasing_weight_source.DecreasingWeightSource to work correctly.

"""

import xappy

def main(dbname):
    conn = xappy.SearchConnection(dbname)
    if conn.get_doccount() == conn._index.get_lastdocid():
        print "Database %s has contiguous doc ids starting at 1." % dbname
    else:
        print "WARNING: Database %s has non-contiguous doc ids!" % dbname

if __name__ == '__main__':
    import sys
    main(sys.argv[1])
