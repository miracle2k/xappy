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

class TestWeightAction(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('name', xappy.FieldActions.INDEX_FREETEXT,)
        iconn.add_field_action('exact', xappy.FieldActions.INDEX_EXACT,)
        iconn.add_field_action('weight', xappy.FieldActions.WEIGHT,)
        for i in xrange(5):
            doc = xappy.UnprocessedDocument()
            doc.fields.append(xappy.Field('name', 'bruno is a nice guy'))
            doc.fields.append(xappy.Field('name', ' '.join('one two three four five'.split()[i:])))
            doc.fields.append(xappy.Field('weight', i / 4.0))
            iconn.add(doc)
        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_pure_weight(self):
        q = self.sconn.query_field("weight")
        r = self.sconn.search(q, 0, 10)
        self.assertEqual([int(i.id) for i in r], [4, 3, 2, 1, 0])

    def test_weight_combined(self):
        q1 = self.sconn.query_parse("one nice guy", default_op=self.sconn.OP_OR)
        r = self.sconn.search(q1, 0, 10)
        self.assertEqual([int(i.id) for i in r], [0, 4, 3, 2, 1])

        q2 = self.sconn.query_field("weight")
        r = self.sconn.search(q2, 0, 10)
        self.assertEqual([int(i.id) for i in r], [4, 3, 2, 1, 0])

        # Combining the weights directly - the weight from the text overpowers
        # the document weight.
        q = self.sconn.query_composite(self.sconn.OP_OR, (q1, q2))
        r = self.sconn.search(q, 0, 10)
        self.assertEqual([int(i.id) for i in r], [0, 4, 3, 2, 1])

        # Combining the weights with normalisation - the weights are now
        # comparable, neither overpowering the other.
        maxwt = self.sconn.get_max_possible_weight(q1)
        q1b = self.sconn.query_multweight(q1, 2.0 / maxwt)
        q = self.sconn.query_composite(self.sconn.OP_OR, (q1b, q2))
        r = self.sconn.search(q, 0, 10)
        self.assertEqual([int(i.id) for i in r], [4, 0, 3, 2, 1])

    def test_regression(self):
        """This test is an attempt to reproduce a segfault.

        """
        query1 = self.sconn.query_field("exact", "33")
        query2 = self.sconn.query_parse("name:bruno")
        query2 = self.sconn.query_multweight(query2, 0.5)
        query = self.sconn.query_adjust(query1, query2)
        q_weight = self.sconn.query_field("weight")
        query_max_weight = self.sconn.get_max_possible_weight(query)
        multiplier = 1.0 / query_max_weight

        str(query)
        str(q_weight)
        str(multiplier)
        q_norm = self.sconn.query_multweight(query, multiplier) 
        str(q_norm)
        adj = self.sconn.query_adjust(q_norm, q_weight)
        str(adj)

if __name__ == '__main__':
    main()
