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
from xappy.cachemanager import *
import random

class TestCacheManager(TestCase):
    def pre_test(self):
        self.dbpath = os.path.join(self.tempdir, 'db')
        self.maxdocid = 12345
        self.maxqueryid = 100

    def check_matches(self, man, queryid, items, exhaustive):
        cacheditems = man.get_hits(queryid)
        self.assertEqual(len(cacheditems), len(items))
        self.assertEqual(cacheditems, items)

        if exhaustive:
            for j in xrange(len(cacheditems)):
                subitems = man.get_hits(queryid, j)
                self.assertEqual(items[j:], subitems)
                if (j % 99 == 0):
                    for k in xrange(j, self.maxdocid, 10):
                        subitems = man.get_hits(queryid, j, k)
                        self.assertEqual(items[j:k], subitems)
 

    def test_xapian_cache(self):
        random.seed(42)
        man = XapianCacheManager(self.dbpath, chunksize=100)

        # Check the behaviour of an empty cache.
        self.assertEqual(list(man.iter_by_docid()), [])
        self.assertEqual(man.get_hits(0), [])
        self.assertEqual(list(man.keys()), [])

        # Datastructures used to check the values returned by the cache:

        # Map from queryid to the ordered docids for that queryid
        ids = {}

        # queryids, an array, to be indexed by (docid - 1).
        # Each item needs to be a new array, and will be filled with the
        # queryid and rank for the items for this docid.
        queryids = map(list, [[]] * self.maxdocid)

        # List of all the docids in use. 
        docids = list(range(1, self.maxdocid + 1))

        querystrs = []
        for i in xrange(1, self.maxqueryid + 1):
            count = random.randint(i, i * 100)
            items = random.sample(docids, count)
            random.shuffle(items)
            self.assertEqual(len(items), count)
            querystr = 'q%d' % i
            querystrs.append(querystr)
            queryid = man.get_or_make_queryid(querystr)
            ids[queryid] = items
            for rank, docid in enumerate(items):
                queryids[docid - 1].append((queryid, rank))
            man.set_hits(queryid, items)
        querystrs.sort()

        man.flush()
        self.assertEqual(list(sorted(man.iter_query_strs())), querystrs)
        self.assertEqual(list(sorted(ids.keys())), range(0, self.maxqueryid))
        self.assertEqual(list(man.iter_queryids()),
                         list(sorted(ids.keys())))
        man = XapianCacheManager(self.dbpath, chunksize=100)
        self.assertNotEqual(list(man.keys()), [])

        for docid, qids in man.iter_by_docid():
            self.assertTrue(list(qids) == queryids[docid - 1])

        # Do an exhastive check that the docids for subslices are right for the
        # first queryid: afterwards, just do a check that the sum of the docids
        # is right.
        exhaustive = True
        for queryid, items in ids.iteritems():
            self.check_matches(man, queryid, items, exhaustive)
            exhaustive = False

        for i in xrange(100):
            queryid = random.randint(0, self.maxqueryid - 1)

            # Remove some of the items
            ranks = random.sample(range(len(ids[queryid])),
                                  random.randint(0, min(5, len(ids[queryid]))))
            ranks.sort(reverse=True)
            ranks_and_docids = []
            for rank in ranks:
                docid = ids[queryid][rank]
                items = queryids[docid - 1]
                for i in xrange(len(items)):
                    if items[i][0] == queryid:
                        del items[i]
                        break
                del ids[queryid][rank]

                # The rank supplied to remove_hits is allowed to be an over
                # estimate.
                ranks_and_docids.append((rank + random.randint(0, 5), docid))
            random.shuffle(ranks_and_docids)

            man.remove_hits(queryid, ranks_and_docids)

            self.check_matches(man, queryid, ids[queryid], exhaustive)

        for docid, qids in man.iter_by_docid():
            # The ranks have gone wrong by now, so just test the query ids.
            self.assertEqual([qid for qid, rank in qids],
                             [qid for qid, rank in queryids[docid - 1]])

        self.assertNotEqual(list(man.keys()), [])
        man.clear()
        self.assertEqual(list(man.keys()), [])
        self.assertEqual(list(man.iter_by_docid()), [])

if __name__ == '__main__':
    main()
