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

        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('a', 'zebra'))
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
        
        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_get_terms_for_field1(self):
        terms = self.sconn.get_terms_for_field('a')
        self.assertEqual(terms, ['cat', 'dog', 'lemur', 'zebra'])

    def test_get_terms_for_field2(self):
        terms = self.sconn.get_terms_for_field('b')
        self.assertEqual(terms, [])

if __name__ == '__main__':
    main()
