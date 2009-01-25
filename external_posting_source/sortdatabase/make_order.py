"""
Given a xappy index and the name of a value field (and its purpose).
Make a numpy array with the xapian ids of the documents sorted by that
value (optionally reversed)

"""
from __future__ import with_statement
import numpy
import xapian
import xappy


def main(index, weightname, purposename,
         orderfilename, weightsfilename, reversed):
    sconn = xappy.SearchConnection(index)
    count = sconn.get_doccount()
    #the data base sorter expects 4 byte ints
    xapids = numpy.zeros((count), 'int32')
    weights = numpy.zeros((count), 'f')
    for i, doc in enumerate(sconn.iter_documents()):
        # will i always be the same as doc._doc.get_docid()?
        xapids[i] = doc._doc.get_docid()
        weights[i] = xapian.sortable_unserialise(
            doc.get_value(weightname, purposename))
    score_order = weights.argsort()
    if reversed:
        score_order = score_order[::-1]
    xapids = xapids[score_order]
    weights = weights[score_order]
    with open(orderfilename, 'wb') as of:
        xapids.tofile(of)
    with open(weightsfilename, 'wb') as wf:
        weights.tofile(wf)

def describe():
    print """
    usage: python make_order.py <index> <weightname> <purposename> <orderfilename> <weightsfilename> [<reversed>]
    where:
      <index> : name of an indx
      <weight> : name of a value
      <purposename>: purpose of the value
      <orderfilename>: file containing the docids ordered by weight
      <weightfilename>: file containing those weight in the corresponding order
      <reversed>: order in descending order of weight (optional - anything here triggers reversing
      """
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 6:
        describe()
    else:
        index = sys.argv[1]
        weightname = sys.argv[2]
        purposename = sys.argv[3]
        orderfilename = sys.argv[4]
        weightsfilename = sys.argv[5]
        reversed = len(sys.argv) >= 6
        main(index, weightname, purposename,
             orderfilename, weightsfilename, reversed)
