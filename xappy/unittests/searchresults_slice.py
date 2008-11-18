# Copyright (C) 2008 Lemur Consulting Ltd
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

def _to_ids(res):
    """Get a set of ids from a SearchResults object.

    """
    return [int(item.id) for item in res]

class TestSearchResultsSlice(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('a', xappy.FieldActions.INDEX_EXACT)

        for i in xrange(5):
            doc = xappy.UnprocessedDocument()
            doc.fields.append(xappy.Field('a', str(i)))
            iconn.add(doc)
        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_search_results_slice(self):
        """Test slicing the searchresults object.

        """
        q = self.sconn.query_all()
        allres = q.search(0, 100)
        self.assertEqual(_to_ids(allres), [0,1,2,3,4])

        for res, expected in (
                              (allres[:], [0,1,2,3,4]),
                              (allres[1:], [1,2,3,4]),
                              (allres[-1:], [4]),
                              (allres[-2:], [3,4]),
                              (allres[0:-3], [0,1]),
                              (allres[0:-1], [0,1,2,3]),
                              (allres[0:-1:2], [0,2]),
                              (allres[0::2], [0,2,4]),
        ):
            self.assertEqual(_to_ids(res), expected)

if __name__ == '__main__':
    main()
