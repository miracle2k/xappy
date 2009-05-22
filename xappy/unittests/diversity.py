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

class TestDiversity(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('text', xappy.FieldActions.INDEX_FREETEXT)
        iconn.add_field_action('text', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('num', xappy.FieldActions.COLLAPSE)
        iconn.add_field_action('num', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('i', xappy.FieldActions.STORE_CONTENT)

        self.docs = {}
        for i in xrange(32):
            doc = xappy.UnprocessedDocument()
            if i % 2: # freq = 16
                doc.fields.append(xappy.Field('text', 'termA'))
            if (i / 2) % 2: # freq = 16
                doc.fields.append(xappy.Field('text', 'termB'))
            if i >= 8: # freq = 24
                doc.fields.append(xappy.Field('text', 'termC'))
            if i >= 18: # freq = 14
                doc.fields.append(xappy.Field('text', 'termD'))
            if i >= 24: # freq = 8
                doc.fields.append(xappy.Field('text', 'termE'))
            if (i / 3) % 3 == 0: # freq = 12
                doc.fields.append(xappy.Field('text', 'termF'))
            doc.fields.append(xappy.Field('num', str(int(i / 8))))
            doc.fields.append(xappy.Field('i', str(i)))
            docid = iconn.add(doc)
            self.docs[docid] = doc

        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_diversity(self):
        """Test reordering for diversity.

        """
        q = self.sconn.query_parse('termA termB', default_op=xappy.Query.OP_OR)
        results = q.search(0, 100, collapse='num', collapse_max=5)
        origorder = [int(hit.data['i'][0]) for hit in results]
        self.assertEqual([int(hit.data['num'][0]) for hit in results],
                         [0, 0, 1, 1, 2, 2, 3, 3, 0, 0, 0, 1, 1, 2, 1, 2, 2, 3,
                         3, 3])
        self.assertEqual(origorder,
                         [3, 7, 15, 11, 23, 19, 31, 27, 5, 6, 1, 13, 14, 17, 9,
                         21, 22, 25, 26, 30])

        results._reorder_by_collapse()
        neworder = [int(hit.data['i'][0]) for hit in results]
        self.assertEqual(sorted(neworder), sorted(origorder))
        self.assertEqual([int(hit.data['num'][0]) for hit in results],
                         [0, 1, 2, 3, 0, 1, 2, 3, 2, 1, 0, 3, 1, 2, 3, 0, 3, 2,
                         1, 0])
        self.assertEqual(neworder,
                         [3, 15, 23, 31, 7, 11, 19, 27, 17, 13, 5, 25, 14, 21,
                         26, 6, 30, 22, 9, 1])

if __name__ == '__main__':
    main()
