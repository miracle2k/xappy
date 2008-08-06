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

class RangeTest(TestCase):
    def pre_test(self, *args):
        self.dbpath = os.path.join(self.tempdir, 'db')
        iconn = xappy.IndexerConnection(self.dbpath)
        iconn.add_field_action('text', xappy.FieldActions.STORE_CONTENT)

        # make documents with simple text
        # Add them with document IDs in decreasing order.
        for i in xrange(10):
            doc = xappy.UnprocessedDocument()
            doc.fields.append(xappy.Field('text', "Hello world %d" % i))
            pdoc = iconn.process(doc)
            pdoc.id = str(9 - i)
            iconn.add(pdoc)
        iconn.close()

    def test_dociter(self):
        sconn = xappy.SearchConnection(self.dbpath)
        ids = [i for i in sconn.iterids()]
        docids = [doc.id for doc in sconn.iter_documents()]
        # The docids were added in reverse order, so the iterids() method
        # should return items in opposite order to iter_documents().
        # (Note, this behaviour isn't guaranteed by the API, but if it changes,
        # this test will fail and we can put an appropriate release note in
        # place to warn people.)
        docids.reverse()
        self.assertEqual(ids, docids)
