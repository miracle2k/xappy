# Copyright (C) 2009 Pablo Hoffman
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

class TestStoreOnly(TestCase):

    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('a', xappy.FieldActions.INDEX_FREETEXT, allow_field_specific=False)
        iconn.add_field_action('a', xappy.FieldActions.STORE_CONTENT)

        doc1 = xappy.UnprocessedDocument("1")
        doc1.fields.append(xappy.Field('a', 'first item'))
        doc2 = xappy.UnprocessedDocument("2")
        doc2.fields.append(xappy.Field('a', 'second item'))
        doc3 = xappy.UnprocessedDocument("3")
        doc3.fields.append(xappy.Field('a', 'third item'))
        iconn.add(doc1)
        iconn.add(doc2, store_only=True)
        iconn.add(doc3)
        iconn.flush()
        iconn.replace(doc3, store_only=True)
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_store_only(self):
        """Test the "store_only" arguments for IndexerConnection methods.

        """
        # regular queries only return items indexed with store_only=False
        q = self.sconn.query_parse('item')
        self.assertEqual([r.data for r in self.sconn.search(q, 0, 10)], 
                         [{'a': ['first item']}])

        # get_document() can access all of them
        self.assertEqual(self.sconn.get_document('2').data,
                         {'a': ['second item']})
        self.assertEqual(self.sconn.get_document('3').data,
                         {'a': ['third item']})

        # query all will also return those added with store_only=True because
        # it doesn't actually search for anything
        q = self.sconn.query_all()
        self.assertEqual(len(self.sconn.search(q, 0, 10)), 3)

if __name__ == '__main__':
    main()
