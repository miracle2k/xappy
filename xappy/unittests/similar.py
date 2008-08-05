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

class TestSimilar(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('text', xappy.FieldActions.INDEX_FREETEXT)

        iconn.add_field_action('text', xappy.FieldActions.STORE_CONTENT)

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
            docid = iconn.add(doc)
            self.docs[docid] = doc

        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_similar_existing_document(self):
        """Test that query_similar() works for existing documents.

        """
        self.assertEqual(self.sconn.significant_terms('1'),
                         [('text', 'termf'), ('text', 'terma')])
        self.assertEqual(self.sconn.significant_terms('12'),
                         [('text', 'termf'), ('text', 'termd'),
                          ('text', 'termb'), ('text', 'termc')])
        self.assertEqual(self.sconn.significant_terms(self.docs['12']),
                         [('text', 'termf'), ('text', 'termd'),
                          ('text', 'termb'), ('text', 'termc')])

        r1 = self.sconn.query_similar('12').search(0, 10)
        r2 = self.sconn.query_similar(self.docs['12']).search(0, 10)

        self.assertNotEqual(len(r1), 0)
        for i1, i2 in zip(r1, r2):
            self.assertEqual(i1.id, i2.id)
            self.assertAlmostEqual(i1.weight, i2.weight)

if __name__ == '__main__':
    main()
