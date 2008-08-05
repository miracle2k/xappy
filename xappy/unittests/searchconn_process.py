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

class TestSearchConnProcess(TestCase):  
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        self.iconn = xappy.IndexerConnection(self.indexpath)
        self.iconn.add_field_action('name', xappy.FieldActions.INDEX_FREETEXT, spell=True)
        self.iconn.add_field_action('name', xappy.FieldActions.STORE_CONTENT)
        self.iconn.add_field_action('weight', xappy.FieldActions.WEIGHT)
        self.iconn.flush()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.iconn.close()
        self.sconn.close()

    def test_search_conn_process(self):
        """Check that the SearchConnection.process() method works.

        """
        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('name', 'bruno is a nice guy'))
        doc.fields.append(xappy.Field('weight', '17'))
        spdoc = self.sconn.process(doc)
        ipdoc = self.iconn.process(doc)

        self.assertEqual([t.term for t in spdoc._doc.termlist()],
                         [t.term for t in ipdoc._doc.termlist()])
        self.assertEqual([(v.num, v.value) for v in spdoc._doc.values()],
                         [(v.num, v.value) for v in ipdoc._doc.values()])
        self.assertEqual(spdoc.data, ipdoc.data)

if __name__ == '__main__':
    main()
