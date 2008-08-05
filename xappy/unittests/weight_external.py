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
import xapian

class ExternalWeightReadingFromValue(xappy.ExternalWeightSource):
    """An external weight source which reads from a value.

    """
    def __init__(self, field, purpose='', maxval=10000000):
        xappy.ExternalWeightSource.__init__(self)
        self.field = field
        self.purpose = purpose
        self.maxval = maxval

    def get_maxweight(self):
        return self.maxval

    def get_weight(self, doc):
        val = doc.get_value(self.field, self.purpose)
        val = xapian.sortable_unserialise(val)
        if val > self.maxval:
            return self.maxval
        return val

class ExternalWeightConstant(xappy.ExternalWeightSource):
    """An external weight source which always returns a constant value.

    """
    def __init__(self, value):
        xappy.ExternalWeightSource.__init__(self)
        self.value = value

    def get_maxweight(self):
        return self.value

    def get_weight(self, doc):
        return self.value

class TestWeightExternal(TestCase):
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
            doc.fields.append(xappy.Field('exact', str(i)))
            doc.fields.append(xappy.Field('weight', i / 4.0))
            iconn.add(doc)
        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def add_external_value(self, q):
        s = ExternalWeightReadingFromValue('weight', 'weight')
        return q.adjust(self.sconn.query_external_weight(s))

    def test_weight_from_value(self):
        """Check a search for a weight from an external value.

        """
        s = ExternalWeightReadingFromValue('weight', 'weight')
        q = self.sconn.query_external_weight(s)
        r = self.sconn.search(q, 0, 10)
        self.assertEqual([int(i.id) for i in r], [4, 3, 2, 1, 0])

    def test_weight_adjustment(self):
        q = self.sconn.query_parse("Bruno OR three")
        r = self.sconn.search(q, 0, 10)
        self.assertEqual([int(i.id) for i in r], [2, 1, 0, 4, 3])

        wtdiff = 1.7
        s2 = ExternalWeightConstant(wtdiff)
        q2 = self.sconn.query_external_weight(s2)
        q2 = q.adjust(q2)
        r2 = self.sconn.search(q2, 0, 10)
        self.assertEqual([int(i.id) for i in r2], [2, 1, 0, 4, 3])
        for v1, v2 in zip(r, r2):
            self.assertAlmostEqual(v1.weight + wtdiff, v2.weight)

    def test_weight_adjust_from_value(self):
        """Check a search adjusted by a weight from an external value.

        """
        query = self.sconn.query_field("exact", "3")
        q = self.add_external_value(query)
        r = self.sconn.search(q, 0, 10)
        self.assertEqual([int(i.id) for i in r], [3])

if __name__ == '__main__':
    main()
