from xappytest import *
import random
import time
import xapian

def conv(val):
    return "%.0f" % val

class RangeTest(TestCase):
    def pre_test(self, *args):
        self.dbpath = os.path.join(self.tempdir, 'db')
        iconn = xappy.IndexerConnection(self.dbpath)
        iconn.add_field_action('price', xappy.FieldActions.FACET, type='float')
        iconn.add_field_action('price_text', xappy.FieldActions.INDEX_EXACT)
        iconn.add_field_action('price_ranges', xappy.FieldActions.FACET, type='float',
                               ranges=[(x * 10, (x + 1) * 10) for x in xrange(10)])

        # Set the random seed, so that test runs are repeatable.
        random.seed(42)

        self.doccount = 100000
        self.repeats = 100
        self.results = 10000

        self.doccount = 1000
        self.repeats = 10

        # make documents with random price and add the price as text as well
        for _ in xrange(self.doccount):
            doc = xappy.UnprocessedDocument()
            val = float(random.randint(0, 100))
            strval = conv(val)
            doc.fields.append(xappy.Field('price', val))
            doc.fields.append(xappy.Field('price_text', strval))
            doc.fields.append(xappy.Field('price_ranges', val))
            iconn.add(doc)
        iconn.close()

    def test_timings(self):
        self.sconn = xappy.SearchConnection(self.dbpath)
        self.target_price = 50
        self.range_bottom = 40
        self.range_top = 60

        # These queries should both return all the documents with the target
        # price.
        facet_q = self.sconn.query_facet('price',
            (self.target_price - 0.5, self.target_price + 0.5))
        text_q = self.sconn.query_field('price_text', conv(self.target_price))
        accel_facet_q = self.sconn.query_facet('price_ranges',
            (self.target_price - 0.5, self.target_price + 0.5))

        facet_rangeq = self.sconn.query_facet('price',
            (self.range_bottom, self.range_top))

        text_rangeq = self.sconn.query_composite(self.sconn.OP_OR,
            (self.sconn.query_field('price_text', conv(x))
             for x in xrange(self.range_bottom, self.range_top + 1)))

        accel_facet_rangeq = self.sconn.query_facet('price_ranges',
            (self.range_bottom, self.range_top))
        approx_facet_rangeq = self.sconn.query_facet('price_ranges',
            (self.range_bottom, self.range_top), approx=True)

        t1, r1 = self.search_repeater(facet_q)
        t2, r2 = self.search_repeater(text_q)
        t3, r3 = self.search_repeater(accel_facet_q)
        self.check_equal_results(r1, r2)
        self.check_equal_results(r1, r3)

        t4, r4 = self.search_repeater(facet_rangeq)
        t5, r5 = self.search_repeater(text_rangeq)
        t6, r6 = self.search_repeater(accel_facet_rangeq)
        t7, r7 = self.search_repeater(approx_facet_rangeq)
        self.check_equal_results(r4, r5)
        self.check_equal_results(r4, r6)
        self.check_equal_results(r4, r7)

        return
        print "facet:", t1 #, facet_q
        print "text:", t2 #, text_q
        print "accel_facet:", t3 #, accel_facet_q

        print "facet_range:", t4 #, facet_rangeq
        print "text_range:", t5 #, text_rangeq
        print "accel_facet_range:", t6 #, accel_facet_rangeq
        print "approx_facet_range:", t7 #, approx_facet_rangeq

    def check_equal_results(self, r1, r2):
        r1_ids = set((x.id for x in r1))
        r2_ids = set((x.id for x in r2))
        self.display_differences(r1_ids, r2_ids)
        self.assertEqual(r1_ids, r2_ids)

    def display_differences(self, ids1, ids2):
        ids1_unique = ids1 - ids2
        if ids1_unique:
            print "ids only in ids1: ", ids1_unique
        ids2_unique = ids2 - ids1
        if ids2_unique:
            print "ids only in ids2: ", ids2_unique

        for i in ids1 ^ ids2:
            d = self.sconn.get_document(i)
            print "value: ", xapian.sortable_unserialise(d.get_value('price', 'facet'))
            print "termlist: ", map (lambda t: t.term, d._doc.termlist())

    def search_repeater(self, query):
        """Run a search repeatedly, timing it.

        Returns a tuple containing:
         - The average time taken per search.
         - The results of the (last execution of the) search.

        """
        now = time.time()
        for _ in xrange(self.repeats):
            r = query.search(0, self.results)
        return (time.time() - now) / self.repeats, r
