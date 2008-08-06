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
import random
import time
import xapian

def conv(val):
    return "%.0f" % val

class RangeTest(TestCase):
    def pre_test(self, *args):
        self.dbpath = os.path.join(self.tempdir, 'db')
        iconn = xappy.IndexerConnection(self.dbpath)
        iconn.add_field_action('price', xappy.FieldActions.SORTABLE, type='float')
        iconn.add_field_action('price_text', xappy.FieldActions.INDEX_EXACT)
        iconn.add_field_action('price_ranges', xappy.FieldActions.SORTABLE, type='float',
                               ranges=[(x * 10, (x + 1) * 10) for x in xrange(10)])

        # Set the random seed, so that test runs are repeatable.
        random.seed(42)

        self.doccount = 100000
        self.results = 1000
        self.repeats = 10

        self.doccount = 100

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
        range_q = self.sconn.query_range('price',
            self.target_price - 0.5, self.target_price + 0.5)
        text_q = self.sconn.query_field('price_text', conv(self.target_price))
        accel_range_q = self.sconn.query_range('price_ranges',
            self.target_price - 0.5, self.target_price + 0.5)

        range_rangeq = self.sconn.query_range('price_ranges',
            self.range_bottom, self.range_top, accelerate=False)

        text_rangeq = self.sconn.query_composite(self.sconn.OP_OR,
            (self.sconn.query_field('price_text', conv(x))
             for x in xrange(self.range_bottom, self.range_top + 1)))

        accel_range_rangeq = self.sconn.query_range('price_ranges',
            self.range_bottom, self.range_top)
        approx_range_rangeq = self.sconn.query_range('price_ranges',
            self.range_bottom, self.range_top, approx=True)

        t1, r1 = self.search_repeater(range_q)
        t2, r2 = self.search_repeater(text_q)
        t3, r3 = self.search_repeater(accel_range_q)
        self.check_equal_results(r1, r2, "range_q", "text_q")
        self.check_equal_results(r1, r3, "range_q", "accel_range_q")

        t4, r4 = self.search_repeater(range_rangeq)
        t5, r5 = self.search_repeater(text_rangeq)
        t6, r6 = self.search_repeater(accel_range_rangeq)
        t7, r7 = self.search_repeater(approx_range_rangeq)
        self.check_equal_results(r4, r5, "range_rangeq", "text_q")
        self.check_equal_results(r4, r6, "range_rangeq", "accel_range_q")
        self.check_equal_results(r4, r7, "range_rangeq", "approx_range_q")

        return
        print "range:             ", t1, range_q
        print "text:              ", t2, text_q
        print "accel_range:       ", t3, accel_range_q

        print "text_range:        ", t5, text_rangeq
        print "range_range:       ", t4, range_rangeq
        print "accel_range_range: ", t6, accel_range_rangeq
        print "approx_range_range:", t7, approx_range_rangeq

    def check_equal_results(self, r1, r2, name1, name2):
        r1_ids = set((x.id for x in r1))
        r2_ids = set((x.id for x in r2))
        self.display_differences(r1_ids, r2_ids, name1, name2)
        self.assertEqual(r1_ids, r2_ids)

    def display_differences(self, ids1, ids2, name1, name2):
        ids1_unique = ids1 - ids2
        ids2_unique = ids2 - ids1
        if ids1_unique or ids2_unique:
            print "results for %s and %s differ" % (name1, name2)
        if ids1_unique:
            print "ids only in %s: " % name1, ids1_unique
        if ids2_unique:
            print "ids only in %s: " % name2, ids2_unique

        for i in ids1 ^ ids2:
            d = self.sconn.get_document(i)
            print "value: ", xapian.sortable_unserialise(d.get_value('price', 'collsort'))
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
