# Copyright (C) 2009 Lemur Consulting Ltd
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
from xappytest import *

class TestQueryAll(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        self.dbsize = 32
        iconn = xappy.IndexerConnection(self.indexpath)
        for i in xrange(self.dbsize):
            iconn.add(xappy.UnprocessedDocument())
        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_query_all(self):
        """Test queries produced by query_all.

        """
        for wt in (None, 0.0, 1.1, -2):
            if wt is None:
                results = self.sconn.query_all().search(0, 100)
            else:
                results = self.sconn.query_all(wt).search(0, 100)
            if wt is None or wt < 0: wt = 0.0
            self.assertEqual(len(results), self.dbsize)
            self.assertEqual(results.startrank, 0)
            self.assertEqual(results.endrank, self.dbsize)
            for i in xrange(self.dbsize):
                self.assertEqual(results[i]._doc.get_docid(), i + 1)
                self.assertEqual(results[i].rank, i)
                self.assertEqual(results[i].weight, wt)

if __name__ == '__main__':
    main()
