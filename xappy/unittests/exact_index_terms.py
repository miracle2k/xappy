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

class TestGetTermsForField(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('a', xappy.FieldActions.INDEX_FREETEXT)
        iconn.add_field_action('b', xappy.FieldActions.INDEX_EXACT)
        iconn.add_field_action('c', xappy.FieldActions.INDEX_EXACT)

        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('a', 'Zebra Monkey'))
        doc.fields.append(xappy.Field('b', 'Zebra Monkey'))
        iconn.add(doc)

        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('a', 'dog'))
        doc.fields.append(xappy.Field('a', 'cat'))
        iconn.add(doc)

        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('a', 'lemur'))
        iconn.add(doc)

        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('a', 'dog'))
        iconn.add(doc)

        # Add some empty field values.  For indexing as freetext, this should
        # have no effect.  For INDEX_EXACT, the empty value should be stored as
        # a term.
        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('a', ''))
        doc.fields.append(xappy.Field('b', ''))
        iconn.add(doc)
        
        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_iter_terms_for_field1(self):
        """Test an iterator across a freetext field.

        """
        terms = self.sconn.iter_terms_for_field('a')
        self.assertEqual(list(terms), ['cat', 'dog', 'lemur', 'monkey', 'zebra'])

    def test_iter_terms_for_field2(self):
        """Test an iterator across an exact match field.

        """
        terms = self.sconn.iter_terms_for_field('b')
        self.assertEqual(list(terms), ['', 'Zebra Monkey'])

    def test_iter_terms_for_field_empty(self):
        """Test an iterator across a field with no terms.

        """
        terms = self.sconn.iter_terms_for_field('c')
        self.assertEqual(list(terms), [])


if __name__ == '__main__':
    main()
