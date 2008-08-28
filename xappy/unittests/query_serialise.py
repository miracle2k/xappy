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

class TestQuerySerialise(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('a', xappy.FieldActions.INDEX_FREETEXT)
        iconn.add_field_action('b', xappy.FieldActions.INDEX_EXACT)
        iconn.add_field_action('c', xappy.FieldActions.SORTABLE, type="string")
        iconn.add_field_action('d', xappy.FieldActions.SORTABLE, type="float")
        iconn.add_field_action('e', xappy.FieldActions.FACET, type="string")
        iconn.add_field_action('f', xappy.FieldActions.FACET, type="float")
        iconn.add_field_action('g', xappy.FieldActions.WEIGHT)

        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('a', 'Africa America'))
        doc.fields.append(xappy.Field('b', 'America'))
        doc.fields.append(xappy.Field('c', 'Australia'))
        doc.fields.append(xappy.Field('d', '1.0'))
        doc.fields.append(xappy.Field('e', 'Atlantic'))
        doc.fields.append(xappy.Field('f', '1.0'))
        doc.fields.append(xappy.Field('g', '1.0'))
        iconn.add(doc)

        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_query_serialise(self):
        """Test serialising of queries.

        """
        q1 = self.sconn.query_field('a', 'America')
        q2 = self.sconn.query_field('b', 'America')
        q3 = self.sconn.query_range('c', 'Ache', 'Atlas')
        q4 = self.sconn.query_range('d', 0.0, 2.0)
        q5 = self.sconn.query_range('d', 0.0, None)
        q6 = self.sconn.query_range('d', None, 2.0)
        q7 = self.sconn.query_range('d', None, None)
        q8 = self.sconn.query_facet('e', 'Atlantic')
        q9 = self.sconn.query_facet('f', (0.0, 2.0))
        q10 = self.sconn.query_field('g')
        q11 = self.sconn.query_none()
        q12 = self.sconn.query_all()
        q13 = xappy.Query()

        queries = (q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, q11, q12, q13,
                   q1 | q2,
                   q1 & q2,
                   q1 ^ q2,
                   q1.adjust(q10),
                   q1.filter(q2),
                   q1.and_not(q2),
                   q1.and_maybe(q2),
                   xappy.Query.compose(xappy.Query.OP_OR, (q1, q2, q3, q4)),
                  )

        for q in queries:
            q_repr = q.evalable_repr()
            q_unrepr = self.sconn.query_from_evalable(q_repr)
            q_repr2 = q_unrepr.evalable_repr()
            self.assertEqual(repr(q), repr(q_unrepr))
            self.assertEqual(q_repr, q_repr2)


if __name__ == '__main__':
    main()
