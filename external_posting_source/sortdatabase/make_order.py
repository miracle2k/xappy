"""
Given a xappy index and the name of a value field (and its purpose).
Make a numpy array with the xapian ids of the documents sorted by that
value (optionally reversed)

"""
from __future__ import with_statement
import numpy
import xapian
import xappy


def main(index, weightname, purposename, orderfilename, reversed):
    # Number of blank IDs to leave.
    # IDs start at 1, so the first ID used will be initial_blank_space + 1
    initial_blank_space = 1000

    sconn = xappy.SearchConnection(index)
    count = sconn.get_doccount()
    xapids = numpy.zeros((count), 'int32')
    weights = numpy.zeros((count), 'f')
    dociter = sconn.iter_documents()
    for i, doc in enumerate(dociter):
        xapid = doc._doc.get_docid()
        xapids[i] = xapid
        weights[i] = xapian.sortable_unserialise(
            doc.get_value(weightname, purposename))

    score_order = weights.argsort()
    if reversed:
        score_order = score_order[::-1]

    # score_order is the list of offsets in xapids which return the ids in
    # sorted order.  To get the mapping from old xapid to new xapid, we do the
    # following:
    max_id = xapids.max()
    new_xapids = numpy.zeros((max_id + 1), 'int32')
    for i, id in enumerate(xapids[score_order]):
        new_xapids[id] = i + 1 + initial_blank_space

    #print xapids
    #print weights
    #print score_order
    #print new_xapids

    with open(orderfilename, 'wb') as of:
        new_xapids.tofile(of)

def describe():
    print """
    usage: python make_order.py <index> <weightname> <purposename> <orderfilename> [<reversed>]
    where:
      <index> : name of an index
      <weight> : name of a value
      <purposename>: purpose of the value
      <orderfilename>: file containing the docids ordered by weight
      <reversed>: order in descending order of weight (optional - anything here triggers reversing)
      """
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        describe()
    else:
        index = sys.argv[1]
        weightname = sys.argv[2]
        purposename = sys.argv[3]
        orderfilename = sys.argv[4]
        reversed = len(sys.argv) >= 6
        main(index, weightname, purposename,
             orderfilename, reversed)
