import random
import time
import xappy


def search(q, sconn):
    start_clock = time.clock()
    results = sconn.search(q, 0, 10)
    end_clock = time.clock()
    print "Elapsed: ", end_clock - start_clock
    return results

def main(index):
    sconn = xappy.SearchConnection(index)
    doccount = sconn.get_doccount()
    target = hex(random.randint(0, doccount))[2:]
    q = sconn.query_image_similarity('img', docid = target)
    search(q, sconn)
    results = search(q, sconn)
    tdoc = sconn.get_document(target)
    print "target: ",
    print '<img src="'+tdoc.data['file'][0]+'">'
    print "results:"
    for r in results:
        print '<img src="'+r.data['file'][0]+'">'

if __name__ == '__main__':
    import sys
    main(*sys.argv[1:])
