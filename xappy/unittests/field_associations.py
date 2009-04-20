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
        iconn.add_field_action('i', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('j', xappy.FieldActions.STORE_CONTENT,
                               link_associations=False)

        iconn.add_field_action('a', xappy.FieldActions.INDEX_FREETEXT)
        iconn.add_field_action('b', xappy.FieldActions.INDEX_FREETEXT)
        iconn.add_field_action('c', xappy.FieldActions.INDEX_EXACT)
        iconn.add_field_action('d', xappy.FieldActions.SORTABLE, type="string")
        iconn.add_field_action('e', xappy.FieldActions.SORTABLE, type="float")
        iconn.add_field_action('f', xappy.FieldActions.TAG)
        iconn.add_field_action('g', xappy.FieldActions.FACET, type="string")
        iconn.add_field_action('h', xappy.FieldActions.FACET, type="float")
        iconn.add_field_action('i', xappy.FieldActions.INDEX_FREETEXT,
                               allow_field_specific=False)
        iconn.add_field_action('j', xappy.FieldActions.INDEX_FREETEXT)

        doc = xappy.UnprocessedDocument()
        doc.extend((('a', 'Africa America'),
                    ('b', 'Andes America'),
                    ('c', 'Arctic America'),
                    ('d', 'Australia'),
                    ('e', '1.0'),
                    ('f', 'Ave'),
                    ('g', 'Atlantic'),
                    ('h', '1.0'),
                    ('j', 'Africa America'),
                   ))
        iconn.add(doc)

        doc = xappy.UnprocessedDocument()
        doc.extend((('a', 'Africa America', 'Brown Bible'),
                    ('b', 'Andes America', 'Bath Bible'),
                    ('c', 'Arctic America', 'Lesser Baptist'),
                    ('c', 'Arctic America', 'Baptist Bible', 2.0),
                    ('c', 'Arctic America'),
                    ('d', 'Australia', 'Braille'),
                    ('e', '1.0', 'Sortable one'),
                    ('f', 'Ave', 'Blvd'),
                    ('g', 'Atlantic', 'British'),
                    ('h', '1.0', 'Facet one'),
                    ('j', 'Africa America', 'Brown Bible'),
                   ))
        iconn.add(doc)

        doc = xappy.UnprocessedDocument()
        doc.extend((('c', 'Arctic America', 'Lesser Baptist'),
                    ('c', 'Arctic America', 'Lesser Baptist'),
                    ('c', 'Arctic America', 'Baptist Bible', 1.5),
                    ('c', 'Arctic America'),
                    ('c', 'Baptist Bible'),
                   ))
        iconn.add(doc)

        doc = xappy.UnprocessedDocument()
        doc.extend((('i', 'Some interesting words'),
                    ('i', 'Some boring words'),
                   ))
        iconn.add(doc)

        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_non_field_specific_relevant_data(self):
        """The get_relevant_data with non-field-specific fields.

        """
        q = self.sconn.query_parse('interesting')
        results = q.search(0, 10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].relevant_data(),
                         (('i', ('Some interesting words',)),)
                        )

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
        q10 = self.sconn.query_field('j', 'america')

        # Check an internal detail
        results = q1.search(0, 10)
        self.assertEqual(results[0]._get_assocs(), {})
        self.assertNotEqual(results[1]._get_assocs(), {})

        # Check that grouped_data is the same as data when there's no group.
        self.assertEqual(results[0].data, results[0].grouped_data[0])

        # Check that the relevant data is appropriate.  For the second result,
        # the associated data should be returned.
        self.assertEqual(results[0].relevant_data(simple=False), (('a', ('Africa America',)),))
        self.assertEqual(results[0].relevant_data(simple=True), (('a', ('Africa America',)),))
        self.assertEqual(results[1].relevant_data(simple=False), (('a', ('Brown Bible',)),))
        self.assertEqual(results[1].relevant_data(simple=True), ())

        # Check an internal detail - there shouldn't be any associations for
        # the j field.
        results = q10.search(0, 10)
        self.assertEqual(results[0]._get_assocs(), {})
        self.assertNotEqual(results[1]._get_assocs(), {})
        self.assertEqual(results[1]._get_assocs().get('j'), None)

        # Check that grouped_data is the same as data when there's no group.
        self.assertEqual(results[0].data, results[0].grouped_data[0])
        self.assertEqual(results[1].data, results[1].grouped_data[0])

        # Check that the relevant data is appropriate.  For the second result,
        # the associated data should be returned.
        self.assertEqual(results[0].relevant_data(simple=False), ())
        self.assertEqual(results[0].relevant_data(simple=True), (('j', ('Africa America',)),))
        self.assertEqual(results[1].relevant_data(simple=False), ())
        self.assertEqual(results[1].relevant_data(simple=True), ())

        # Check a query which returns two items
        results = (q1 | q2).search(0, 10)
        self.assertEqual(results[0].relevant_data(simple=False),
                         (('a', ('Africa America',)),
                          ('b', ('Andes America',))))
        self.assertEqual(results[0].relevant_data(simple=True),
                         (('a', ('Africa America',)),
                          ('b', ('Andes America',))))
        self.assertEqual(results[1].relevant_data(simple=False),
                         (('a', ('Brown Bible',)),
                          ('b', ('Bath Bible',))))
        self.assertEqual(results[1].relevant_data(simple=True),
                         ())

        results = q3.search(0, 10)
        self.assertEqual(results[0].relevant_data(simple=False),
                         (('e', ('1.0',)),))
        self.assertEqual(results[0].relevant_data(simple=True),
                         (('e', ('1.0',)),))
        self.assertEqual(results[1].relevant_data(simple=False),
                         (('e', ('Sortable one',)),))
        self.assertEqual(results[1].relevant_data(simple=True),
                         (('e', ('Sortable one',)),))

        results2 = q4.search(0, 10)
        self.assertEqual(results[0].relevant_data(simple=False), results2[0].relevant_data(simple=False))
        self.assertEqual(results[0].relevant_data(simple=True), results2[0].relevant_data(simple=True))
        self.assertEqual(results[1].relevant_data(simple=False), results2[1].relevant_data(simple=False))
        self.assertEqual(results[1].relevant_data(simple=True), results2[1].relevant_data(simple=True))

        results2 = q5.search(0, 10)
        self.assertEqual(results[0].relevant_data(simple=False), results2[0].relevant_data(simple=False))
        self.assertEqual(results[0].relevant_data(simple=True), results2[0].relevant_data(simple=True))
        self.assertEqual(results[1].relevant_data(simple=False), results2[1].relevant_data(simple=False))
        self.assertEqual(results[1].relevant_data(simple=True), results2[1].relevant_data(simple=True))

        results2 = q6.search(0, 10)
        self.assertEqual(results[0].relevant_data(simple=False), results2[0].relevant_data(simple=False))
        self.assertEqual(results[0].relevant_data(simple=True), results2[0].relevant_data(simple=True))
        self.assertEqual(results[1].relevant_data(simple=False), results2[1].relevant_data(simple=False))
        self.assertEqual(results[1].relevant_data(simple=True), results2[1].relevant_data(simple=True))

        results = (q1 | q3).search(0, 10)
        self.assertEqual(results[0].relevant_data(simple=False),
                         (('a', ('Africa America',)),
                          ('e', ('1.0',)),
                         ))
        self.assertEqual(results[0].relevant_data(simple=True),
                         (('a', ('Africa America',)),
                          ('e', ('1.0',)),
                         ))
        self.assertEqual(results[1].relevant_data(simple=False),
                         (('a', ('Brown Bible',)),
                          ('e', ('Sortable one',)),
                         ))
        self.assertEqual(results[1].relevant_data(simple=True),
                         (
                          ('e', ('Sortable one',)),
                         ))


        results = q7.search(0, 10)
        self.assertEqual(results[0].relevant_data(simple=False),
                         (('h', ('1.0',)),))
        self.assertEqual(results[0].relevant_data(simple=True),
                         (('h', ('1.0',)),))
        self.assertEqual(results[1].relevant_data(simple=False),
                         (('h', ('Facet one',)),))
        self.assertEqual(results[1].relevant_data(simple=True),
                         (('h', ('Facet one',)),))

        results = q8.search(0, 10)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].relevant_data(simple=False),
                         (('c', ('Arctic America',)),))
        self.assertEqual(results[0].relevant_data(simple=True),
                         (('c', ('Arctic America',)),))
        self.assertEqual(results[1].relevant_data(simple=False),
                         (('c', ('Baptist Bible', 'Arctic America', 'Lesser Baptist',)),))
        self.assertEqual(results[1].relevant_data(simple=True),
                         (('c', ('Arctic America', )),))
        self.assertEqual(results[2].relevant_data(simple=False),
                         (('c', ('Lesser Baptist', 'Baptist Bible', 'Arctic America',)),))
        self.assertEqual(results[2].relevant_data(simple=True),
                         (('c', ('Arctic America',)),))

        results = q9.search(0, 10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].relevant_data(simple=False),
                         (('c', ('Baptist Bible',)),))
        self.assertEqual(results[0].relevant_data(simple=True),
                         (('c', ('Baptist Bible',)),))

        results = (q8 | q9).search(0, 10)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].relevant_data(simple=False),
                         (('c', ('Arctic America',)),))
        self.assertEqual(results[0].relevant_data(simple=True),
                         (('c', ('Arctic America',)),))
        self.assertEqual(results[1].relevant_data(simple=False),
                         (('c', ('Baptist Bible', 'Arctic America', 'Lesser Baptist',)),))
        self.assertEqual(results[1].relevant_data(simple=True),
                         (('c', ('Baptist Bible', 'Arctic America',)),))
        self.assertEqual(results[2].relevant_data(simple=False),
                         (('c', ('Baptist Bible', 'Lesser Baptist', 'Arctic America',)),))
        self.assertEqual(results[2].relevant_data(simple=True),
                         (('c', ('Baptist Bible', 'Arctic America',)),))



if __name__ == '__main__':
    main()
