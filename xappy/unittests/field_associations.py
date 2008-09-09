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

class TestFieldAssociations(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('a', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('b', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('c', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('d', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('e', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('f', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('g', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('h', xappy.FieldActions.STORE_CONTENT)

        iconn.add_field_action('a', xappy.FieldActions.INDEX_FREETEXT)
        iconn.add_field_action('b', xappy.FieldActions.INDEX_FREETEXT)
        iconn.add_field_action('c', xappy.FieldActions.INDEX_EXACT)
        iconn.add_field_action('d', xappy.FieldActions.SORTABLE, type="string")
        iconn.add_field_action('e', xappy.FieldActions.SORTABLE, type="float")
        iconn.add_field_action('f', xappy.FieldActions.TAG)
        iconn.add_field_action('g', xappy.FieldActions.FACET, type="string")
        iconn.add_field_action('h', xappy.FieldActions.FACET, type="float")

        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('a', 'Africa America'))
        doc.fields.append(xappy.Field('b', 'Andes America'))
        doc.fields.append(xappy.Field('c', 'Arctic America'))
        doc.fields.append(xappy.Field('d', 'Australia'))
        doc.fields.append(xappy.Field('e', '1.0'))
        doc.fields.append(xappy.Field('f', 'Ave'))
        doc.fields.append(xappy.Field('g', 'Atlantic'))
        doc.fields.append(xappy.Field('h', '1.0'))
        iconn.add(doc)

        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('a', 'Africa America', 'Brown Bible'))
        doc.fields.append(xappy.Field('b', 'Andes America', 'Bath Bible'))
        doc.fields.append(xappy.Field('c', 'Arctic America', 'Lesser Baptist'))
        doc.fields.append(xappy.Field('c', 'Arctic America', 'Baptist Bible',
                                      weight=2.0))
        doc.fields.append(xappy.Field('c', 'Arctic America'))
        doc.fields.append(xappy.Field('d', 'Australia', 'Braille'))
        doc.fields.append(xappy.Field('e', '1.0', 'Sortable one'))
        doc.fields.append(xappy.Field('f', 'Ave', 'Blvd'))
        doc.fields.append(xappy.Field('g', 'Atlantic', 'British'))
        doc.fields.append(xappy.Field('h', '1.0', 'Facet one'))
        iconn.add(doc)

        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('c', 'Arctic America', 'Lesser Baptist'))
        doc.fields.append(xappy.Field('c', 'Arctic America', 'Lesser Baptist'))
        doc.fields.append(xappy.Field('c', 'Arctic America', 'Baptist Bible',
                                      weight=1.5))
        doc.fields.append(xappy.Field('c', 'Arctic America'))
        doc.fields.append(xappy.Field('c', 'Baptist Bible'))
        iconn.add(doc)

        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_freetext_assocs(self):
        """Test field associations for freetext fields.

        """
        q1 = self.sconn.query_field('a', 'america')
        q2 = self.sconn.query_field('b', 'america')
        q3 = self.sconn.query_range('e', 0.0, 2.0)
        q4 = self.sconn.query_range('e', 0.0, None)
        q5 = self.sconn.query_range('e', None, 2.0)
        q6 = self.sconn.query_range('e', None, None)
        q7 = self.sconn.query_facet('h', (0.0, 2.0))
        q8 = self.sconn.query_field('c', 'Arctic America')
        q9 = self.sconn.query_field('c', 'Baptist Bible')

        # Check an internal detail
        results = q1.search(0, 10)
        self.assertEqual(results[0]._get_assocs(), {})
        self.assertNotEqual(results[1]._get_assocs(), {})

        # Check that the relevant data is appropriate.  For the second result,
        # the associated data should be returned.
        self.assertEqual(results[0].relevant_data(), (('a', ('Africa America',)),))
        self.assertEqual(results[1].relevant_data(), (('a', ('Brown Bible',)),))

        # Check a query which returns two items
        results = (q1 | q2).search(0, 10)
        self.assertEqual(results[0].relevant_data(),
                         (('a', ('Africa America',)),
                          ('b', ('Andes America',))))
        self.assertEqual(results[1].relevant_data(),
                         (('a', ('Brown Bible',)),
                          ('b', ('Bath Bible',))))

        results = q3.search(0, 10)
        self.assertEqual(results[0].relevant_data(),
                         (('e', ('1.0',)),))
        self.assertEqual(results[1].relevant_data(),
                         (('e', ('Sortable one',)),))

        results2 = q4.search(0, 10)
        self.assertEqual(results[0].relevant_data(), results2[0].relevant_data())
        self.assertEqual(results[1].relevant_data(), results2[1].relevant_data())

        results2 = q5.search(0, 10)
        self.assertEqual(results[0].relevant_data(), results2[0].relevant_data())
        self.assertEqual(results[1].relevant_data(), results2[1].relevant_data())

        results2 = q6.search(0, 10)
        self.assertEqual(results[0].relevant_data(), results2[0].relevant_data())
        self.assertEqual(results[1].relevant_data(), results2[1].relevant_data())

        results = (q1 | q3).search(0, 10)
        self.assertEqual(results[0].relevant_data(),
                         (('a', ('Africa America',)),
                          ('e', ('1.0',)),
                         ))
        self.assertEqual(results[1].relevant_data(),
                         (('a', ('Brown Bible',)),
                          ('e', ('Sortable one',)),
                         ))

        results = q7.search(0, 10)
        self.assertEqual(results[0].relevant_data(),
                         (('h', ('1.0',)),))
        self.assertEqual(results[1].relevant_data(),
                         (('h', ('Facet one',)),))

        results = q8.search(0, 10)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].relevant_data(),
                         (('c', ('Arctic America',)),))
        self.assertEqual(results[1].relevant_data(),
                         (('c', ('Baptist Bible', 'Arctic America', 'Lesser Baptist',)),))
        self.assertEqual(results[2].relevant_data(),
                         (('c', ('Lesser Baptist', 'Baptist Bible', 'Arctic America',)),))

        results = q9.search(0, 10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].relevant_data(),
                         (('c', ('Baptist Bible',)),))

        results = (q8 | q9).search(0, 10)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].relevant_data(),
                         (('c', ('Arctic America',)),))
        self.assertEqual(results[1].relevant_data(),
                         (('c', ('Baptist Bible', 'Arctic America', 'Lesser Baptist',)),))
        self.assertEqual(results[2].relevant_data(),
                         (('c', ('Baptist Bible', 'Lesser Baptist', 'Arctic America',)),))



if __name__ == '__main__':
    main()
