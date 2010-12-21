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

class TestCluster(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('text', xappy.FieldActions.INDEX_FREETEXT)
        iconn.add_field_action('text', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('num', xappy.FieldActions.INDEX_FREETEXT)
        iconn.add_field_action('num', xappy.FieldActions.SORTABLE)
        iconn.add_field_action('num', xappy.FieldActions.STORE_CONTENT)

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
            docid = iconn.add(doc)
            self.docs[docid] = doc

        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_cluster(self):
        """Test clustering.

        """
        results = self.sconn.query_all().search(0, 100)
        clusters = results._cluster(10, 100)
        self.assertEqual(clusters,
                         {0: [0, 1, 2], 1: [3, 5, 7], 2: [4], 3: [6], 4: [8],
                         5: [9, 10, 11, 13, 14, 15], 6: [12], 7: [16], 8: [17,
                         18, 19, 20, 21, 22, 23], 9: [24, 25, 26, 27, 28, 29,
                         30, 31]})

        clusters = results._cluster(10, 100, ['num', 'text', 'num'])
        clusters2 = results._cluster(10, 100, ['num', 'text'])
        self.assertEqual(clusters, clusters2)

        clusters = results._cluster(4, 100, 'num')
        self.assertEqual(clusters,
                         {0: [0, 1, 2, 3, 4, 5, 6, 7],
                          1: [8, 9, 10, 11, 12, 13, 14, 15],
                          2: [16, 17, 18, 19, 20, 21, 22, 23],
                          3: [24, 25, 26, 27, 28, 29, 30, 31]})

if __name__ == '__main__':
    main()
