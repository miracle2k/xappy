# vim: set fileencoding=utf-8 :
#
# Copyright (C) 2008 Michael Elsdörfer
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
from datetime import date
from xappytest import *

class TestSortBy(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('name', xappy.FieldActions.INDEX_FREETEXT)
        iconn.add_field_action('name', xappy.FieldActions.SORTABLE)
        iconn.add_field_action('date', xappy.FieldActions.SORTABLE, type='date')

        data =\
            [{'name': 'a', 'date': date(2008, 1, 1)},
             {'name': 'c', 'date': date(2008, 6, 1)},
             {'name': 'b', 'date': date(2008, 6, 1)}]
        for row in data:
            doc = xappy.UnprocessedDocument()
            for field, value in row.items():
                doc.fields.append(xappy.Field(field, value))
            iconn.add(doc)
        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def _search(self, sortby):
        res = self.sconn.query_all().search(0, 100, sortby=sortby)
        return [int(item.id) for item in res]

    def test_single_field(self):
        """Test that sorting by a single field works.

        """
        self.assertEqual(self._search('name'), [0,2,1])
        self.assertEqual(self._search('+name'), [0,2,1])
        self.assertEqual(self._search('-name'), [1,2,0])

    def test_multiple_fields(self):
        """Test that sorting by multiple fields works.

        """
        self.assertEqual(self._search(('date', 'name')), [0,2,1])
        self.assertEqual(self._search(('date', '+name')), [0,2,1])
        self.assertEqual(self._search(('date', '-name')), [0,1,2])
        self.assertEqual(self._search(('+date', 'name')), [0,2,1])
        self.assertEqual(self._search(('+date', '+name')), [0,2,1])
        self.assertEqual(self._search(('+date', '-name')), [0,1,2])
        self.assertEqual(self._search(('-date', 'name')), [2,1,0])
        self.assertEqual(self._search(('-date', '+name')), [2,1,0])
        self.assertEqual(self._search(('-date', '-name')), [1,2,0])

if __name__ == '__main__':
    main()
