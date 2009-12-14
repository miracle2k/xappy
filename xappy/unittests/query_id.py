# vim: set fileencoding=utf-8 :
#
# Copyright (C) 2008 Pablo Hoffman
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

class TestQueryId(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)

        doc = xappy.UnprocessedDocument("121")
        iconn.add(doc)
        doc = xappy.UnprocessedDocument("122")
        iconn.add(doc)
        doc = xappy.UnprocessedDocument("123")
        iconn.add(doc)

        iconn.flush()
        iconn.close()

        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        self.sconn.close()

    def test_query_id(self):
        """Test the SearchConnection.query_id() method.

        """
        query = self.sconn.query_id(["121", "123"])
        results = query.search(0, 10)
        self.assertEqual([r.id for r in results], ["121", "123"])

        query = self.sconn.query_id(["121"])
        results = query.search(0, 10)
        self.assertEqual([r.id for r in results], ["121"])

        query = self.sconn.query_id("121")
        results = query.search(0, 10)
        self.assertEqual([r.id for r in results], ["121"])

        self.assertEqual(query.evalable_repr(), "conn.query_id('121')")

if __name__ == '__main__':
    main()
