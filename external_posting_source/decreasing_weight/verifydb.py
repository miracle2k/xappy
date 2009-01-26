"""verifies that the document ids in a database don't have any 'gaps'
and start at 1. This is necessary for
decreasing_weight_source.DecreasingWeightSource to work correctly.

"""


import xappy

def main(dbname):
    conn = xappy.SearchConnection(dbname)
    failed = False;
    for i, d in enumerate(conn.iter_documents()):
        if (i+1) != d._doc.get_docid():
            print "WARNING: database %s has non-contiguous doc ids!" % dbname
            failed = True
            break
    if not failed:
        print "database %s has contiguous doc ids starting at 1" % dbname

if __name__ == '__main__':
    import sys
    main(sys.argv[1])
