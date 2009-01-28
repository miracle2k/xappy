""" unit tests for dws

"""
from __future__ import with_statement
import os
import shutil
import tempfile
import unittest

import numpy
import dws
import xappy


class sourceTest(object):

    def setUp(self):
        self.index = tempfile.mkdtemp()
        iconn = xappy.IndexerConnection(self.index)
        self.count = 100
        self.weights = numpy.array(
          [x/float(self.count) for x in xrange(self.count, 0 ,-1)],
          'float32')
        for w in self.weights:
            iconn.add(xappy.UnprocessedDocument())
        self.weights.tofile(os.path.join(self.index, "weights.dat"))
        iconn.close()
        self.sconn = xappy.SearchConnection(self.index)
        self.query = dws.make_page_rank_query(self.sconn, self.source_type())

    def tearDown(self):
        self.sconn.close()
        shutil.rmtree(self.index)

    def test_check_weights(self):
        """ ensure that the weights for search results are as they
        should be.
        """
        for i, r in enumerate (self.sconn.search(self.query, 0, self.count)):
            self.assertAlmostEqual(r.weight, self.weights[i])

    def test_cutoff_next(self):
        source = self.query._Query__refs[0]
        source.reset()
        for _ in xrange(50):
            source.next(0)
        self.failIf(source.at_end())
        source.next(0.7)
        self.failUnless(source.at_end())

    def test_cutoff_skip_to(self):
        source = self.query._Query__refs[0]
        source.reset()
        source.skip_to(77, 0)
        self.failIf(source.at_end())
        source.skip_to(80, 0.7)
        self.failUnless(source.at_end())

class VDWSTestCase(sourceTest, unittest.TestCase):

    def source_type(self):
        return dws.VECTOR

class FDWSTestCase(sourceTest, unittest.TestCase):

    def source_type(self):
        return dws.FILE

class CVDWSTestCase(sourceTest, unittest.TestCase):

    def source_type(self):
        return dws.CACHED_VECTOR

if __name__ == "__main__":
    unittest.main()
