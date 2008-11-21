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
        doc.append('a', 'Africa America')
        doc.append([('b', 'Andes America'),
                    ('c', 'Arctic America')])
        doc.append('d', 'Australia')
        doc.append([('e', '1.0')])
        doc.append('f', 'Ave')
        doc.append([('g', 'Atlantic'),
                    ('h', '1.0')])
        doc.append('i', 'Apt America')
        pdoc = iconn.process(doc)
        self.groups = pdoc._groups
        iconn.add(pdoc)

        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_field_groups(self):
        """Test field groups for freetext fields.

        """
        id = list(self.sconn.iterids())[0]
        doc = self.sconn.get_document(id)
        # Test an internal detail
        self.assertEqual(doc._get_groups(),
                         [(('b', 0), ('c', 0)), (('g', 0), ('h', 0))])


if __name__ == '__main__':
    main()
