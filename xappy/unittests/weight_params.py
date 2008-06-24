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

def result_ids(results):
    return [int(i.id) for i in results]

class TestWeightParams(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('text', xappy.FieldActions.INDEX_FREETEXT,)
        for i in xrange(5):
            doc = xappy.UnprocessedDocument()
            doc.fields.append(xappy.Field('text', 'foo ' * (i + 1)))
            doc.fields.append(xappy.Field('text', ' '.join('one two three four five'.split()[i:])))
            iconn.add(doc)
        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_wdf_importance(self):
        q = self.sconn.query_field("text", "foo")
        r = self.sconn.search(q, 0, 10)
        self.assertEqual(result_ids(r), [4, 3, 2, 1, 0])
        r = self.sconn.search(q, 0, 10, weight_params={'k1': 0})
        self.assertEqual(result_ids(r), [0, 1, 2, 3, 4])
        r = self.sconn.search(q, 0, 10, weight_params={'k1': 0.1})
        self.assertEqual(result_ids(r), [4, 3, 2, 1, 0])

        q = self.sconn.query_field("text", "foo one", default_op=self.sconn.OP_OR)
        r = self.sconn.search(q, 0, 10)
        self.assertEqual(result_ids(r), [0, 4, 3, 2, 1])
        r = self.sconn.search(q, 0, 10, weight_params={'k1': 0})
        self.assertEqual(result_ids(r), [0, 1, 2, 3, 4])
        r = self.sconn.search(q, 0, 10, weight_params={'k1': 0.1})
        self.assertEqual(result_ids(r), [0, 4, 3, 2, 1])

if __name__ == '__main__':
    main()
