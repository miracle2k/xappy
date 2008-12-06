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

class TestFieldGroups(TestCase):
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
        iconn.add_field_action('i', xappy.FieldActions.INDEX_FREETEXT)

        doc = xappy.UnprocessedDocument()
        doc.extend((
                    ('a', 'Africa America'),
                    ('a', 'Uninteresting'),
                    xappy.FieldGroup([('b', 'Andes America'), ('c', 'Arctic America')]),
                    ('b', 'Notinteresting'),
                    ('d', 'Australia'),
                    xappy.FieldGroup([('e', '1.0')]),
                    ('f', 'Ave'),
                    xappy.FieldGroup([('g', 'Atlantic'), ('h', '1.0')]),
                    ('i', 'Apt America'),
                   ))
        pdoc = iconn.process(doc)
        self.groups = pdoc._groups
        iconn.add(pdoc)

        doc = xappy.UnprocessedDocument()
        doc.extend((('a', 'Africa America', 'Brown Bible'),
                    ('a', 'Uninteresting'),
                    ('b', 'Andes America', 'Bath Bible'),
                    ('b', 'Notinteresting'),
                    (
                     ('c', 'Arctic America', 'Lesser Baptist'),
                     ('c', 'Arctic America', 'Baptist Bible', 2.0),
                    ),
                    ('c', 'Arctic America'),
                    ('d', 'Australia', 'Braille'),
                    ('e', '1.0', 'Sortable one'),
                    ('f', 'Ave', 'Blvd'),
                    ('g', 'Atlantic', 'British'),
                    ('h', '1.0', 'Facet one'),
                    ('i', 'Apt America', 'Be British'),
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


        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_field_groups(self):
        """Test field groups for freetext fields.

        """
        # Test internal representation of groups
        id = list(self.sconn.iterids())[0]
        doc = self.sconn.get_document(id)
        self.assertEqual(doc._get_groups(),
                         [(('b', 0), ('c', 0)), (('g', 0), ('h', 0))])

        id = list(self.sconn.iterids())[1]
        doc = self.sconn.get_document(id)
        self.assertEqual(doc._get_groups(), [(('c', 0), ('c', 1))])

        id = list(self.sconn.iterids())[2]
        doc = self.sconn.get_document(id)
        self.assertEqual(doc._get_groups(), [])


        q1 = self.sconn.query_field('a', 'america')
        q2 = self.sconn.query_field('b', 'america')
        q3 = self.sconn.query_field('b', 'notinteresting')
        q8 = self.sconn.query_field('c', 'Arctic America')
        q9 = self.sconn.query_field('c', 'Baptist Bible')

        # Check an internal detail
        results = q1.search(0, 10)
        self.assertEqual(results[0]._get_assocs(), {})

        # Check that the relevant data is appropriate.  For the second result,
        # the associated data should be returned.
        self.assertEqual(results[0].relevant_data(), (('a', ('Africa America',)),))

        # Check a query which returns two items
        results = (q1 | q2).search(0, 10)
        self.assertEqual(results[0].data,
                         {'a': ['Africa America', 'Uninteresting'],
                          'c': ['Arctic America'],
                          'b': ['Andes America', 'Notinteresting'],
                          'e': ['1.0'],
                          'd': ['Australia'],
                          'g': ['Atlantic'],
                          'f': ['Ave'],
                          'h': ['1.0']})
        self.assertEqual(results[0].relevant_data(),
                         (('a', ('Africa America',)),
                          ('b', ('Andes America',))))
        self.assertEqual(results[0].relevant_data(group=True),
                         (
                          ('a', ('Africa America',)),
                          ('b', ('Andes America',)),
                          ('c', ('Arctic America',)),
                         ))

        results = (q1 | q2 | q8).search(0, 10)
        self.assertEqual(results[0].relevant_data(),
                         (('a', ('Africa America',)),
                          ('b', ('Andes America',)),
                          ('c', ('Arctic America',)),
                         ))

        self.assertEqual(results[0].relevant_data(group=True),
                         (
                          ('a', ('Africa America',)),
                          ('b', ('Andes America',)),
                          ('c', ('Arctic America',)),
                         ))

        results = (q1 | q2 | q3).search(0, 10)
        self.assertEqual(results[0].relevant_data(),
                         (('b', ('Andes America', 'Notinteresting')),
                          ('a', ('Africa America',)),
                         ))

        self.assertEqual(results[0].relevant_data(group=True),
                         (
                          ('b', ('Andes America', 'Notinteresting')),
                          ('a', ('Africa America',)),
                          ('c', ('Arctic America',)),
                         ))

if __name__ == '__main__':
    main()
