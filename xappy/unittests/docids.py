# Copyright (C) 2009 Richard Boulton
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
from xappytest import *

class TestDocId(TestCase):
    def pre_test(self):
        self.dbpath = os.path.join(self.tempdir, 'db')
        self.iconn = xappy.IndexerConnection(self.dbpath)
        self.iconn.add_field_action('a', xappy.FieldActions.INDEX_FREETEXT)
        self.iconn.add_field_action('a', xappy.FieldActions.STORE_CONTENT)

    def test_build_doc_fields(self):
        """Test buiding a document up using various different methods.

        """
        def mkdoc(num):
            doc = xappy.UnprocessedDocument()
            doc.append('a', 'Doc %d' % num)
            return doc

        def get_docids():
            return [(int(doc.data['a'][0][4:]), doc.id)
                    for doc in sconn.iter_documents()]

        self.iconn.replace(mkdoc(1), xapid=2)
        self.iconn.replace(mkdoc(2), xapid=1)
        self.iconn.flush()

        sconn = xappy.SearchConnection(self.dbpath)
        self.assertEqual(get_docids(), [(2, '1'), (1, '0')])

        doc3 = mkdoc(3)
        # Using replace sets the xappy document ID if it's not already set (to
        # a new value).
        self.iconn.replace(doc3, xapid=2)
        self.assertEqual(doc3.id, '2')
        self.iconn.flush()
        sconn = xappy.SearchConnection(self.dbpath)
        self.assertEqual(get_docids(), [(2, '1'), (3, '2')])

        # We can set the xappy document ID if we want, though.
        doc3.id = '4'
        self.iconn.replace(doc3, xapid=2)
        self.iconn.flush()
        sconn = xappy.SearchConnection(self.dbpath)
        self.assertEqual(get_docids(), [(2, '1'), (3, '4')])

        # If we use replace with a specified xapian ID, we can create a
        # situation where multiple documents have the same xappy document ID.
        self.iconn.replace(doc3, xapid=4)
        self.iconn.flush()
        sconn = xappy.SearchConnection(self.dbpath)
        self.assertEqual(get_docids(), [(2, '1'), (3, '4'), (3, '4')])

        # We can clean this up, though, by replacing the old document.
        doc3.id = None
        self.iconn.replace(doc3, xapid=2)
        self.assertEqual(doc3.id, '3')
        self.iconn.flush()
        sconn = xappy.SearchConnection(self.dbpath)
        self.assertEqual(get_docids(), [(2, '1'), (3, '3'), (3, '4')])

        # Let's mess it up again
        self.iconn.replace(doc3, xapid=3)
        self.iconn.flush()
        sconn = xappy.SearchConnection(self.dbpath)
        self.assertEqual(get_docids(), [(2, '1'), (3, '3'), (3, '3'), (3, '4')])

        # Deleting a document with multiple occurences of its xappy document ID
        # gets rid of all of the occurrences.
        self.iconn.delete('3')
        self.iconn.flush()
        sconn = xappy.SearchConnection(self.dbpath)
        self.assertEqual(get_docids(), [(2, '1'), (3, '4')])

        # We can also delete by xapid.
        self.iconn.delete(xapid=4)
        self.iconn.flush()
        sconn = xappy.SearchConnection(self.dbpath)
        self.assertEqual(get_docids(), [(2, '1')])

        # Specifying a non-existent ID raises an error
        self.assertRaises(xappy.XapianDocNotFoundError, self.iconn.delete, xapid=4)


if __name__ == '__main__':
    main()
