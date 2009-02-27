# Copyright (C) 2009 Lemur Consulting Ltd
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

class TestImgSeek(TestCase):
    """Test of the image similarity search action.

    """
    def pre_test(self):
        """Build a database of test images.

        """
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('image', xappy.FieldActions.IMGSEEK)
        iconn.add_field_action('file', xappy.FieldActions.STORE_CONTENT)
        imagedir = os.path.join(os.path.dirname(__file__), 'testdata', 'sampleimages')
        for dirpath, dirnames, filenames in os.walk(imagedir):
            for fname in filenames:
                if not fname.endswith('jpg'):
                    continue
                doc = xappy.UnprocessedDocument()
                path = os.path.abspath(os.path.join(dirpath, fname))
                doc.fields.append(xappy.Field('image', path))
                doc.fields.append(xappy.Field('file', os.path.basename(path)))
                iconn.add(doc)
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def post_test(self):
        """Clean up after the test.
        """
        self.sconn.close()

    def test_query_image_similarity(self):
        """Basic test of image similarity search.

        """
        # Check that we have similarity
        self.assertEqual(self.sconn.get_doccount(), 3)
        q = self.sconn.query_image_similarity('image', docid='0')
        s = self.sconn.search(q, 0, 10)

        # Candle is more similar to looroll than a cat.
        self.assertEqual([i.data['file'][0][:-4] for i in s],
                         ['looroll', 'candle', 'cat'])

        self.assertAlmostEqual(s[0].weight, 100.0)
        self.assertAlmostEqual(s[1].weight, 33.41085261614748)
        self.assertAlmostEqual(s[2].weight, 20.697674393961904)
 
if __name__ == '__main__':
    main()
