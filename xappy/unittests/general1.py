# vim: set fileencoding=utf-8 :
#
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

class TestPercent(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)

        iconn.add_field_action('author', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('title', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('category', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('text', xappy.FieldActions.STORE_CONTENT)

        iconn.add_field_action('author', xappy.FieldActions.INDEX_FREETEXT, weight=2)
        iconn.add_field_action('title', xappy.FieldActions.INDEX_FREETEXT, weight=5)
        iconn.add_field_action('category', xappy.FieldActions.INDEX_EXACT)
        iconn.add_field_action('category', xappy.FieldActions.SORTABLE)
        iconn.add_field_action('category', xappy.FieldActions.COLLAPSE)
        iconn.add_field_action('category', xappy.FieldActions.FACET)
        iconn.add_field_action('text', xappy.FieldActions.INDEX_FREETEXT, language='en',
                               spell=True, stop=('basic',))

        iconn.add_field_action('date', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('date', xappy.FieldActions.COLLAPSE)
        iconn.add_field_action('date', xappy.FieldActions.SORTABLE, type='date')
        iconn.add_field_action('date', xappy.FieldActions.COLLAPSE)
        iconn.add_field_action('price', xappy.FieldActions.STORE_CONTENT)
        iconn.add_field_action('price', xappy.FieldActions.SORTABLE, type='float')
        iconn.add_field_action('price', xappy.FieldActions.COLLAPSE)
        iconn.add_field_action('price', xappy.FieldActions.FACET, type='float')
        iconn.add_field_action('price3', xappy.FieldActions.SORTABLE, type='float')
        iconn.add_field_action('price3', xappy.FieldActions.FACET, type='float')
        iconn.add_field_action('price3', xappy.FieldActions.STORE_CONTENT)

        iconn.add_field_action('facet1', xappy.FieldActions.FACET)
        iconn.add_field_action('facet2', xappy.FieldActions.FACET)
        iconn.add_field_action('facet3', xappy.FieldActions.FACET)
        iconn.add_field_action('facet4', xappy.FieldActions.FACET, type='float')
        iconn.add_field_action('facet5', xappy.FieldActions.FACET)
        iconn.add_field_action('facet6', xappy.FieldActions.FACET)
        iconn.add_field_action('facet7', xappy.FieldActions.FACET)
        iconn.add_field_action('facet8', xappy.FieldActions.FACET, type='float')

        iconn.add_field_action('facet9', xappy.FieldActions.FACET, type='float')
        iconn.add_field_action('facet9', xappy.FieldActions.SORTABLE)

        iconn.flush()
        iconn.close()

    def test_one_sort_type(self):
        """Test that a field can only be sorted according to one type.

        """
        iconn = xappy.IndexerConnection(self.indexpath)
        try:
            iconn.add_field_action('date', xappy.FieldActions.SORTABLE, type='float')
            self.assertTrue(False)
        except xappy.IndexerError, e:
            self.assertEqual(str(e), "Field 'date' is already marked for "
                             "sorting, with a different sort type")

    def test_unknown_sort_type(self):
        """Test that the sort type used is known.

        """
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('price2', xappy.FieldActions.SORTABLE, type='unknown')
        doc = xappy.UnprocessedDocument()
        doc.append('price2', '1.0')
        try:
            iconn.process(doc)
            self.assertTrue(False)
        except xappy.IndexerError, e:
            self.assertEqual(str(e), "Unknown sort type 'unknown' for field "
                             "'price2'")

    def _add_content(self, iconn):
        """Add some content to the database.

        """
        for i in xrange(200):
            doc = xappy.UnprocessedDocument()
            doc.append('author', 'Richard Boulton')
            doc.append('category', 'Cat %d' % ((i + 5) % 20))
            doc.append('text', 'This document is a basic test document.')
            doc.append('title', 'Test document %d' % i)
            doc.append('text', 'More test text about this document.')
            doc.append('date', '2007%02d%02d' % (i % 12 + 1, i // 12 + 1))
            doc.append('price', '%f' % ((float(i) / 7) % 10))
            doc.append('price3', '%f' % ((float(i) * 6.7)))
            doc.append('facet1', '%d' % (i // 40))
            doc.append('facet2', '%d' % (i // 20))
            doc.append('facet3', '%d' % (i // 12))
            doc.append('facet4', '%d' % (i // 8))
            doc.append('facet5', '%d' % (i // 5))
            doc.append('facet6', '0')
            doc.append('facet7', '2000')
            doc.append('facet7', '2001')
            doc.append('facet7', '%d' % (i % 2))
            doc.append('facet8', '2000')
            doc.append('facet8', '2001')
            doc.append('facet8', '%d' % (i % 2))
            doc.append('facet9', '%d' % (i // 5))
            iconn.add(doc)
        iconn.flush()

    def test_search1(self):
        """Test some simple searches.

        """
        iconn = xappy.IndexerConnection(self.indexpath)
        self._add_content(iconn)
        sconn = xappy.SearchConnection(self.indexpath)

        q = sconn.query_parse('document')
        self.assertEqual(str(q), "Xapian::Query((Zdocument:(pos=1) AND_MAYBE "
                         "document:(pos=1)))")

        # Normal search
        results = sconn.search(q, 0, 30)
        self.assertEqual([result.id for result in results],
                         ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                         'a', 'b', 'c', 'd', 'e', 'f', '10', '11', '12', '13',
                         '14', '15', '16', '17', '18', '19', '1a', '1b', '1c',
                         '1d'])

        # Sorted by price
        results = sconn.search(q, 0, 30, sortby="price")
        prev_price = results[0].data['price']
        for price in (result.data['price'] for result in results):
            self.assertTrue(price >= prev_price)
            prev_price = price

        self.assertEqual([int(result.id, 16) for result in results],
                         [0, 70, 140, 1, 71, 141, 2, 72, 142, 3, 73, 143, 4,
                         74, 144, 5, 75, 145, 6, 76, 146, 7, 77, 147, 8, 78,
                         148, 9, 79, 149])

        self.assertEqual([result.data['price'] for result in results],
                         [['0.000000'], ['0.000000'], ['0.000000'],
                         ['0.142857'], ['0.142857'], ['0.142857'],
                         ['0.285714'], ['0.285714'], ['0.285714'],
                         ['0.428571'], ['0.428571'], ['0.428571'],
                         ['0.571429'], ['0.571429'], ['0.571429'],
                         ['0.714286'], ['0.714286'], ['0.714286'],
                         ['0.857143'], ['0.857143'], ['0.857143'],
                         ['1.000000'], ['1.000000'], ['1.000000'],
                         ['1.142857'], ['1.142857'], ['1.142857'],
                         ['1.285714'], ['1.285714'], ['1.285714']])

        # Sorted by price in reverse order
        results = sconn.search(q, 0, 30, sortby="-price")
        prev_price = results[0].data['price']
        for price in (result.data['price'] for result in results):
            self.assertTrue(price <= prev_price)
            prev_price = price

        self.assertEqual([int(result.id, 16) for result in results],
                         [69, 139, 68, 138, 67, 137, 66, 136, 65, 135, 64, 134,
                         63, 133, 62, 132, 61, 131, 60, 130, 59, 129, 199, 58,
                         128, 198, 57, 127, 197, 56])

    def _summarise_results(self, results):
        """Make a list summarising a result set.

        """
        return [(result.id, result.percent, int(result.weight * 10))
                for result in results]

    def test_search1(self):
        """Test some searches with weight cutoffs.

        """
        iconn = xappy.IndexerConnection(self.indexpath)
        self._add_content(iconn)
        sconn = xappy.SearchConnection(self.indexpath)

        q = sconn.query_parse('richard OR 7 OR 7 OR 8')

        results = sconn.search(q, 0, 5, sortby="date")
        self.assertEqual(self._summarise_results(results),
                         [('7', 62, 326), ('8', 31, 163)])

        try:
            results = sconn.search(q, 0, 5, sortby="date", percentcutoff=30)
            had_exc = False
        except xappy.XapianError:
            had_exc = True
        if not had_exc:
            self.assertEqual(self._summarise_results(results),
                             [('7', 62, 326)])

        results = sconn.search(q, 0, 5, sortby="date", weightcutoff=20)
        self.assertEqual(self._summarise_results(results),
                         [('7', 62, 326)])

        try:
            results = sconn.search(q, 0, 5, sortby="date", percentcutoff=56)
            had_exc = False
        except xappy.XapianError:
            had_exc = True
        if not had_exc:
            self.assertEqual(self._summarise_results(results), [])

        results = sconn.search(q, 0, 5, sortby="date", weightcutoff=33)
        self.assertEqual(self._summarise_results(results), [])


if __name__ == '__main__':
    main()
