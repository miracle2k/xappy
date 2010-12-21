#!/usr/bin/env python
#
# Copyright (C) 2009 Shane Evans
# Copyright (C) 2009 Richard Boulton
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""
Query inversion

This module provides iterators for converting from a sequence of:
    (queryid, [docid+])
to
    (docid, [(queryid, rank)+])

"""
import tempfile
from itertools import groupby, izip, repeat
from operator import itemgetter
import numpy as np

class InverseIterator(object):
    def __init__(self, sequence, tmpdir=None):
        """
        Converts a sequence of (key, [value+]) to (value, [(key, position)+]).
        (Positions start at 0.)

        This returns a pair of iterators: a forward iterator and a reverse
        iterator.  The forward iterator must be fully exhausted before the
        reverse iterator is first used.

        Temporary data is buffered on disk. It requires 12 bytes per (key,
        value) pair. Each (key, [value+]) will be temporarily buffered in
        memory.

        Keys and values must be 32 bit integers.

        >>> data = [(2, [3, 4, 5]), (3, [4, 5, 6]), (1, [7, 2, 1])]
        >>> invseq = InverseIterator(data)
        >>> [(k, list(v)) for (k, v) in invseq]
        [(1, [(1, 2)]), (2, [(1, 1)]), (3, [(2, 0)]), (4, [(2, 1), (3, 0)]), (5, [(2, 2), (3, 1)]), (6, [(3, 2)]), (7, [(1, 0)])]
    
        """
        # this is deleted when it goes out of scope
        self.tf = tempfile.TemporaryFile(prefix='invdata',
                                         suffix='xappy', dir=tmpdir)
        self.dtype = [('value', np.int32),
                      ('key', np.int32),
                      ('rank', np.int32)]

        for (key, values) in sequence:
            # we need to iterate the values sequence as well as allowing caller
            # to iterate, so it must be materialized
            valuecopy = np.fromiter(izip(values,
                                         repeat(key),
                                         xrange(len(values))), self.dtype)
            buf = valuecopy.tostring()
            del valuecopy
            self.tf.write(buf)

        a = np.memmap(self.tf, dtype=self.dtype, mode='r+')
        a.sort()
        del a
    
    def __iter__(self):
        a = np.memmap(self.tf, dtype=self.dtype, mode='r')
        for (k, vals) in groupby(a, itemgetter(0)):
            yield (int(k), map(lambda x: (int(x[1]), int(x[2])), vals))
        del a

    def close(self):
        """Close the temporary file used.

        """
        if self.tf is not None:
            self.tf.close()
            self.tf = None

    def __del__(self):
        self.close()

def runtest():
    """Run a test of this code - intended to be called from the command line.

    """
    import random
    querycount = 100000
    # really we'd expect few large and many more small
    min_docs_per_query = 20
    average_docs_per_query = 200
    max_docid = 1000000

    def input_iter():
        count = 0
        r = random.Random()
        lambd = 1.0 / (average_docs_per_query - min_docs_per_query)
        for i in xrange(querycount):
            newlen = int(r.expovariate(lambd))
            yield (i, (np.random.randint(0, max_docid, newlen)))
            if (i + 1) % 10000 == 0:
                print "creating %s.." % (i + 1)
            count += newlen
        print "iterated %s queries with %s doc references" % (querycount, count)

    print "testing..."
    inverse_iter = InverseIterator(input_iter())
    
    count = 0
    i = 0
    for (_, vals) in inverse_iter:
        newlen = len(vals)
        count += newlen
        i += 1
        if i % 10000 == 0:
            print "iterated %s.." % i
    print "iterated %s docs with %s query references" % (querycount, count)

if __name__ == "__main__" :
    runtest()
