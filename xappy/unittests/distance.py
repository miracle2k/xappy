from xappytest import *
import xapian
from xappy.fieldactions import FieldActions

class DifferenceSearchTest(TestCase):

    def pre_test(self):
        self.dbpath = os.path.join(self.tempdir, 'db')
        self.iconn = xappy.IndexerConnection(self.dbpath)
        ranges = [(x, x + 1) for x in xrange(10)]
        self.iconn.add_field_action('foo', xappy.FieldActions.SORTABLE,
                                    type='float', ranges=ranges)
        self.iconn.add_field_action('foo', xappy.FieldActions.STORE_CONTENT)
        self.iconn.add_field_action('bar', xappy.FieldActions.FACET,
                                    type='float', ranges=ranges)
        self.iconn.add_field_action('bar', xappy.FieldActions.STORE_CONTENT)
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

    def make_dist_comp(self, val, field):
        return lambda x: abs(val - self.sconn.get_document(x.id).data[field][0])

    def difference_test(self, val, field, purpose, approx=True):
        q = self.sconn.query_difference(field, val, purpose, approx=approx)
        res =  list(self.sconn.search(q, 0, 10))
        orig = res[:]
        dist = self.make_dist_comp(val, field)
        res.sort(lambda x, y: cmp(dist(x), dist(y)))
        self.assertEqual(orig, res)

    def test_difference_sortable_low(self):
        self.difference_test(0, 'foo', 'collsort')

    def test_difference_sortable_low_exact(self):
        self.difference_test(0, 'foo', 'collsort', False)

    def test_difference_facet_low(self):
        self.difference_test(0, 'bar', 'facet')

    def test_difference_facet_low_exact(self):
        self.difference_test(0, 'bar', 'facet', False)

    def test_difference_sortable_mid(self):
        self.difference_test(5, 'foo', 'collsort')

    def test_difference_sortable_mid_exact(self):
        self.difference_test(5, 'foo', 'collsort', False)

    def test_difference_facet_mid(self):
        self.difference_test(5, 'bar', 'facet')

    def test_difference_facet_mid_exact(self):
        self.difference_test(5, 'bar', 'facet', False)

    def test_difference_sortable_high(self):
        self.difference_test(10, 'foo', 'collsort')

    def test_difference_sortable_high_exact(self):
        self.difference_test(10, 'foo', 'collsort',  False)

    def test_difference_facet_high(self):
        self.difference_test(10, 'bar', 'facet')

    def test_difference_facet_high_exact(self):
        self.difference_test(10, 'bar', 'facet', False)

    def cutoff_test(self, val, field, purpose, approx = True):
        difference_test = "abs(x - y) if abs(x - y) < 3 else -1"

        query = self.sconn.query_difference(field, val, purpose,
                                            approx=approx,
                                            difference_func=difference_test)
        res = self.sconn.search(query, 0, 10)
        dist = self.make_dist_comp(val, field)
        filtered = filter(lambda x: dist(x) < 3, res)
        self.assert_(len(filtered) == 6)

    def test_cuttoff_facet_approx(self):
        self.cutoff_test(5, 'bar', 'facet')

    def test_cuttoff_facet_exact(self):
        self.cutoff_test(5, 'bar', 'facet', False)

    def test_cuttoff_sortable_approx(self):
        self.cutoff_test(5, 'foo', 'collsort')

    def test_cuttoff_facet_exact(self):
        self.cutoff_test(5, 'foo', 'collsort', False)

if __name__ == '__main__':
    main()
