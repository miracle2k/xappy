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
        for fieldnum in xrange(30):
            iconn.add_field_action('a%d' % fieldnum, xappy.FieldActions.TAG)
        iconn.add_field_action('s', xappy.FieldActions.INDEX_FREETEXT)

        doc = xappy.UnprocessedDocument()
        for fieldnum in xrange(30):
            doc.fields.append(xappy.Field('a%d' % fieldnum, 'Hello'))
        doc.fields.append(xappy.Field('s', 'Hello'))
        iconn.add(doc)

        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_tag_prefix(self):
        """Test that getting the list of tags returns the right set.

        This is a regression test - in previous versions, a second tag would
        be returned: "Ahello", due to one of the other fields sharing a common
        prefix.

        """
        q = self.sconn.query_parse('Hello')
        r = q.search(0, 10, gettags='a0')
        t = r.get_top_tags('a0', 10)
        self.assertEqual(tuple(t), (('hello', 1),))

if __name__ == '__main__':
    main()
