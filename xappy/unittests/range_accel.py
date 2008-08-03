from xappytest import *
import xapian
class RangeAccelIndexTest(TestCase):
    """ Tests for the range acceleration implementation. """

    def pre_test(self):
        self.dbpath = os.path.join(self.tempdir, 'db')
        self.iconn = xappy.IndexerConnection(self.dbpath)

    def post_test(self):
        self.iconn.close()

    def test_add_ranges_for_sortable(self):
        """Test that the ranges parameter is accepted for a SORTABLE field.

        """
        self.iconn.add_field_action('foo', xappy.FieldActions.SORTABLE, type='float', ranges=[(0,1), (1,2)])

    def test_add_ranges_for_facet(self):
        """Test that the ranges parameter is accepted for a FACET field.

        """
        self.iconn.add_field_action('foo', xappy.FieldActions.FACET, type='float', ranges=[(-1, 1), (10, 20)])

    def test_add_invalid_ranges(self):
        """Test that the ranges parameter raises an error if it's invalid.

        """
        self.assertRaises(ValueError, self.iconn.add_field_action, 'foo', xappy.FieldActions.SORTABLE, type='float', ranges='rhubarb')

    def _add_data_to_range_field(self, add_action, action):
        """Add some data to a range field, and check the terms generated.

        """
        self.iconn.add_field_action('foo', add_action, type='float',
                                    ranges=[(0, 1), (1, 2), (2, 3)])
        doc = xappy.UnprocessedDocument()
        doc.fields.append(xappy.Field('foo', 1.5))
        docid = self.iconn.add(doc)
        xdoc = self.iconn.get_document(docid)
        #the document should have at a term with the correct prefix
        prefix = self.iconn._field_actions['foo']._actions[action][0]['_range_accel_prefix']
        found = False
        for t in xdoc._doc.termlist():
            if t.term.startswith(prefix):
                found = True
                break
        self.assertTrue(found, "No term with the range_accel_prefix found")

    def test_add_data_to_range_field_sortable(self):
        """Test adding some data to a SORTABLE field.

        """
        self._add_data_to_range_field(xappy.FieldActions.SORTABLE, xappy.FieldActions.SORT_AND_COLLAPSE)

    def test_add_data_to_range_field_facet(self):
        """Test adding some data to a FACET field.

        """
        self._add_data_to_range_field(xappy.FieldActions.FACET, xappy.FieldActions.FACET)


class RangeAccelSearchTest(TestCase):
    def pre_test(self):
        self.dbpath = os.path.join(self.tempdir, 'db')
        self.iconn = xappy.IndexerConnection(self.dbpath)
        self.iconn.add_field_action('foo', xappy.FieldActions.SORTABLE, type='float',
                                    ranges=[(x, x+1) for x in xrange(10)])
        self.iconn.add_field_action('bar', xappy.FieldActions.FACET, type='float',
                                    ranges=[(x, x+1) for x in xrange(10)])
        for val in xrange(10):
            doc = xappy.UnprocessedDocument()
            sval = val + 0.5
            doc.fields.append(xappy.Field('foo', sval))
            doc.fields.append(xappy.Field('bar', sval))
            self.iconn.add(doc)
        self.iconn.close()
        self.sconn = xappy.SearchConnection(self.dbpath)

    def post_test(self):
        self.sconn.close()

    def single_range(self, field, purpose, q):
        """Check the result of a range search which should return 1 item.

        """
        r = [x for x in q.search(0, 10)]
        self.assertEqual(len(r), 1)
        val = xapian.sortable_unserialise(r[0].get_value(field, purpose))
        self.assertTrue(3 <= val)
        self.assertTrue(val <= 4.01)

    def three_range(self, field, purpose, q):
        """Check the result of a range search which should return 3 items.

        """
        r = [x for x in q.search(0, 10)]
        self.assertEqual(len(r), 3)
        val = xapian.sortable_unserialise(r[0].get_value('foo', 'collsort'))
        self.assertTrue(2 <= val)
        self.assertTrue(val <= 3)
        val = xapian.sortable_unserialise(r[1].get_value('foo', 'collsort'))
        self.assertTrue(3 <= val)
        self.assertTrue(val <= 4)
        val = xapian.sortable_unserialise(r[2].get_value('foo', 'collsort'))
        self.assertTrue(4 <= val)
        self.assertTrue(val <= 5)

    def test_single_approx_range_conservative_sortable(self):
        """Check an approximate, conservative, search.

        """
        q = self.sconn.query_range('foo', 3, 4.01, approx=True)
        self.assertEqual(str(q), "Xapian::Query(0 * XA1\xa6\xa8)")
        self.single_range('foo', 'collsort', q)

    def test_single_approx_range_non_conservative_sortable(self):
        """Check an approximate, non-conservative, search.

        """
        q = self.sconn.query_range('foo', 3.01, 3.99, approx=True,
                                   conservative=False)
        self.assertEqual(str(q), "Xapian::Query(0 * XA1\xa6\xa8)")
        self.single_range('foo', 'collsort', q)

    def test_three_entry_approx_range_non_conservative_sortable(self):
        """Check an approximate, non-conservative, search returning 3 results.

        """
        q = self.sconn.query_range('foo', 3, 4.01, approx=True,
                                   conservative=False)
        self.assertEqual(str(q), "Xapian::Query(0 * (XA1\xa4\xa6 OR " +
                         "XA1\xa6\xa8 OR XA1\xa8\xa9))")
        self.three_range('foo', 'collsort', q)

    def test_single_exact_range_sortable_accel(self):
        """Check an exact range search which is accelerated.

        """
        q = self.sconn.query_range('foo', 3, 4)
        self.assertEqual(str(q), "Xapian::Query(0 * (XA1\xa6\xa8 OR " +
                         "VALUE_RANGE 0 \xa6 \xa8))")
        self.single_range('foo', 'collsort', q)

        q = self.sconn.query_range('foo', 3.01, 3.99)
        self.assertEqual(str(q), "Xapian::Query(VALUE_RANGE 0 " +
                         "\xa6\x05\x1e\xb8Q\xeb\x85 \xa7\xfa\xe1G\xae\x14{)")
        self.single_range('foo', 'collsort', q)

    def test_single_exact_range_sortable(self):
        """Check an exact range search which is not accelerated.

        """
        q = self.sconn.query_range('foo', 3, 4, accelerate=False)
        self.assertEqual(str(q), "Xapian::Query(VALUE_RANGE 0 \xa6 \xa8)")
        self.single_range('foo', 'collsort', q)

        q = self.sconn.query_range('foo', 3.01, 3.99, accelerate=False)
        self.assertEqual(str(q), "Xapian::Query(VALUE_RANGE 0 " +
                         "\xa6\x05\x1e\xb8Q\xeb\x85 \xa7\xfa\xe1G\xae\x14{)")
        self.single_range('foo', 'collsort', q)

    def test_single_approx_facet_conservative_sortable(self):
        """Check an approximate, conservative, search.

        """
        q = self.sconn.query_facet('bar', (3, 4.01), approx=True)
        self.assertEqual(str(q), "Xapian::Query(0 * XC1\xa6\xa8)")
        self.single_range('bar', 'facet', q)

    def test_single_approx_facet_non_conservative_sortable(self):
        """Check an approximate, non-conservative, search.

        """
        q = self.sconn.query_facet('bar', (3.01, 3.99), approx=True,
                                   conservative=False)
        self.assertEqual(str(q), "Xapian::Query(0 * XC1\xa6\xa8)")
        self.single_range('bar', 'facet', q)

    def test_three_entry_approx_facet_non_conservative_sortable(self):
        """Check an approximate, non-conservative, search returning 3 results.

        """
        q = self.sconn.query_facet('bar', (3, 4.01), approx=True,
                                   conservative=False)
        self.assertEqual(str(q), "Xapian::Query(0 * (XC1\xa4\xa6 OR " +
                         "XC1\xa6\xa8 OR XC1\xa8\xa9))")
        self.three_range('bar', 'facet', q)

    def test_single_exact_facet_sortable_accel(self):
        """Check an exact facet search which is accelerated.

        """
        q = self.sconn.query_facet('bar', (3, 4))
        self.assertEqual(str(q), "Xapian::Query(0 * (XC1\xa6\xa8 OR " +
                         "VALUE_RANGE 1 \xa6 \xa8))")
        self.single_range('bar', 'facet', q)

        q = self.sconn.query_facet('bar', (3.01, 3.99))
        self.assertEqual(str(q), "Xapian::Query(VALUE_RANGE 1 " +
                         "\xa6\x05\x1e\xb8Q\xeb\x85 \xa7\xfa\xe1G\xae\x14{)")
        self.single_range('bar', 'facet', q)

    def test_single_exact_facet_sortable(self):
        """Check an exact facet search which is not accelerated.

        """
        q = self.sconn.query_facet('bar', (3, 4), accelerate=False)
        self.assertEqual(str(q), "Xapian::Query(VALUE_RANGE 1 \xa6 \xa8)")
        self.single_range('bar', 'facet', q)

        q = self.sconn.query_facet('bar', (3.01, 3.99), accelerate=False)
        self.assertEqual(str(q), "Xapian::Query(VALUE_RANGE 1 " +
                         "\xa6\x05\x1e\xb8Q\xeb\x85 \xa7\xfa\xe1G\xae\x14{)")
        self.single_range('bar', 'facet', q)

 

if __name__ == '__main__':
    main()
