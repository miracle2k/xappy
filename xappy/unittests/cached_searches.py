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

class TestCachedSearches(TestCase):
    def pre_test(self):
        self.cachepath = os.path.join(self.tempdir, 'cache')
        self.dbpath = os.path.join(self.tempdir, 'db')
        self.doccount = 120

    def test_xapian_cache(self):
        random.seed(42)

        # Make a database, and add some documents to it.
        iconn = xappy.IndexerConnection(self.dbpath)
        iconn.add_field_action('text', xappy.FieldActions.INDEX_FREETEXT)
        iconn.add_field_action('f1', xappy.FieldActions.FACET)
        iconn.add_field_action('f2', xappy.FieldActions.FACET, type='float')

        for i in xrange(self.doccount):
            doc = xappy.UnprocessedDocument()
            doc.append('text', 'hello')
            if i > self.doccount / 2:
                doc.append('text', 'world')
            doc.append('f1', str(i % 5))
            doc.append('f2', i % 7)
            iconn.add(doc)

        # Make a cache, and set the hits for some queries.
        man = XapianCacheManager(self.cachepath)
        man.set_hits(man.get_or_make_queryid('hello'),
                     range(self.doccount, 0, -10))

        uncached_world_order = list(xrange(self.doccount / 2 + 2,
                                           self.doccount + 1))
        world_order = list(xrange(1, self.doccount + 1))
        random.shuffle(world_order)
        man.set_hits(man.get_or_make_queryid('world'), world_order)
        man.set_stats(man.get_or_make_queryid('world'), 5)
        man.add_stats(man.get_or_make_queryid('world'), 5)
        man.set_facets(man.get_or_make_queryid('world'), {
            'f1': (('0', 7),
                   ('3', 6),
                   ('4', 12)),
        })
        man.add_facets(man.get_or_make_queryid('world'), {
            'f1': (('2', 12),
                   ('3', 6),
                  ),
        })

        # Apply the cache to the index.
        iconn.set_cache_manager(man)
        iconn.apply_cached_items()
        iconn.flush()

        iconn.delete('10')
        iconn.flush()
        iconn.delete(xapid=50)

        doc = xappy.UnprocessedDocument()
        doc.append('text', 'hello')
        doc.id = hex(50)[2:]
        iconn.replace(doc)
        doc.id = hex(20)[2:]
        iconn.replace(doc, xapid=21)
        iconn.flush()

        # Try a plain search.
        sconn = xappy.SearchConnection(self.dbpath)
        sconn.set_cache_manager(man)

        query_hello = sconn.query_parse('hello')
        query_world = sconn.query_parse('world')

        results = sconn.search(query_hello, 0, self.doccount)
        results = [int(result.id, 16) for result in results]
        expected = list(xrange(self.doccount))
        expected.remove(16)
        expected.remove(49)
        self.assertEqual(results, expected)

        expected2 = list(xrange(self.doccount - 1, 0, -10))
        expected2.remove(49)

        # Test that merge_with_cached works
        cached_id = man.get_queryid('hello')
        cached_hello = sconn.query_cached(cached_id)
        self.assertEqual(repr(query_hello.norm() | cached_hello),
                         repr(query_hello.merge_with_cached(cached_id)))

        # Test a search for all documents, merged with a cache.
        results = sconn.query_all().merge_with_cached(cached_id).\
                    search(0, self.doccount)
        resultids = [int(result.id, 16) for result in results]
        self.assertEqual(resultids[:11], expected2)
        self.assertEqual(resultids[:20], expected2 + range(9))

        # Try a search with a cache.
        results = sconn.search(query_hello.merge_with_cached(cached_id),
                               0, self.doccount)
        results = [int(result.id, 16) for result in results]
        self.assertEqual(results[:11], expected2)
        self.assertEqual(list(sorted(results)), expected)

        # Try searches for each of the sub ranges.
        expected2_full = expected2 + sorted(set(expected) - set(expected2))
        for i in xrange(len(expected) + 10):
            results = sconn.search(query_hello.merge_with_cached(cached_id),
                                   i, i + 10)
            results = [int(result.id, 16) for result in results]
            self.assertEqual(results, expected2_full[i:i + 10])

        # Try the same search with a different set of cached results.
        world_queryid = man.get_queryid('world')
        cached_world = sconn.query_cached(world_queryid)
        results = sconn.search(query_hello.norm() | cached_world, 0, self.doccount)
        results = [int(result.id, 16) for result in results]
        world_order.remove(17)
        world_order.remove(50)
        self.assertEqual(results, [i - 1 for i in world_order])
        self.assertEqual(list(sorted(results)), expected)

        # Try another search with a cache.
        results = sconn.search(query_world.norm() | cached_world, 0, self.doccount)
        results = [int(result.id, 16) for result in results]
        self.assertEqual(results, [i - 1 for i in world_order])

        # Try doing a search which is a pure cache hit.
        results = sconn.search(cached_world, 0, 2)
        results = [int(result.id, 16) for result in results]
        self.assertEqual(results, [i - 1 for i in world_order[:2]])

        # Try doing a search which is a pure cache hit.
        results = sconn.search(query_world.merge_with_cached(world_queryid), 0, 2)
        self.assertEqual(results.matches_lower_bound, 8)
        self.assertEqual(results.matches_estimated, 59)
        self.assertEqual(results.matches_upper_bound, 59)
        self.assertEqual(results.matches_human_readable_estimate, 60)
        results = [int(result.id, 16) for result in results]
        self.assertEqual(results, [i - 1 for i in world_order[:2]])

        # Try pure cache hits at non-0 start offset.
        for i in xrange(100):
            results = sconn.search(query_world.merge_with_cached(world_queryid),
                                   i, i + 10)
            for j in xrange(len(results)):
                self.assertEqual(int(results[j].id, 16), world_order[i + j] - 1)
            results = [int(result.id, 16) for result in results]
            self.assertEqual(results, [i - 1 for i in world_order[i:i + 10]])

        # Try getting some facet results for a non-cached search.
        results = query_world.search(0, self.doccount, getfacets=True)
        resultids = [int(result.id, 16) for result in results]
        self.assertEqual(resultids, [i - 1 for i in uncached_world_order])
        self.assertEqual(results.matches_lower_bound, 59)
        self.assertEqual(results.matches_upper_bound, 59)
        self.assertEqual(results.matches_estimated, 59)
        self.assertEqual(results.get_facets(), {
            'f1': (
                   ('0', 11),
                   ('1', 12),
                   ('2', 12),
                   ('3', 12),
                   ('4', 12),
                  ),
            'f2': (((0.0, 0.0), 9),
                   ((1.0, 1.0), 8),
                   ((2.0, 2.0), 8),
                   ((3.0, 3.0), 8),
                   ((4.0, 4.0), 8),
                   ((5.0, 5.0), 9),
                   ((6.0, 6.0), 9),
                  )
        })
        self.assertEqual(results.get_suggested_facets(1),
                         [('f2', (((0.0, 0.0), 9),
                                  ((1.0, 1.0), 8),
                                  ((2.0, 2.0), 8),
                                  ((3.0, 3.0), 8),
                                  ((4.0, 4.0), 8),
                                  ((5.0, 5.0), 9),
                                  ((6.0, 6.0), 9),
                                 ))])
        self.assertEqual(results.get_suggested_facets(2),
                         [('f2', (((0.0, 0.0), 9),
                                  ((1.0, 1.0), 8),
                                  ((2.0, 2.0), 8),
                                  ((3.0, 3.0), 8),
                                  ((4.0, 4.0), 8),
                                  ((5.0, 5.0), 9),
                                  ((6.0, 6.0), 9),
                                 )),
                          ('f1', (
                                  ('0', 11),
                                  ('1', 12),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 ))])
        self.assertEqual(results.get_suggested_facets(2,
                                                required_facets=('f1', )),
                         [('f2', (((0.0, 0.0), 9),
                                  ((1.0, 1.0), 8),
                                  ((2.0, 2.0), 8),
                                  ((3.0, 3.0), 8),
                                  ((4.0, 4.0), 8),
                                  ((5.0, 5.0), 9),
                                  ((6.0, 6.0), 9),
                                 )),
                          ('f1', (
                                  ('0', 11),
                                  ('1', 12),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 ))])
        self.assertEqual(results.get_suggested_facets(1,
                                                required_facets=('f1', )),
                         [('f1', (
                                  ('0', 11),
                                  ('1', 12),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 ))])

        # Try getting some facet results for a cached search.
        results = query_world.merge_with_cached(world_queryid) \
                             .search(0, self.doccount, getfacets=True)
        resultids = [int(result.id, 16) for result in results]
        self.assertEqual(resultids, [i - 1 for i in world_order])
        self.assertEqual(results.matches_lower_bound, 8)
        self.assertEqual(results.matches_upper_bound, 118)
        self.assertEqual(results.matches_estimated, 118)
        self.assertEqual(results.get_facets(), {
            'f1': (
                   ('0', 7),
                   ('2', 12),
                   ('3', 12),
                   ('4', 12),
                  ),
            'f2': (((0.0, 0.0), 17),
                   ((1.0, 1.0), 16),
                   ((2.0, 2.0), 16),
                   ((3.0, 3.0), 17),
                   ((4.0, 4.0), 17),
                   ((5.0, 5.0), 17),
                   ((6.0, 6.0), 16),
                  )
        })
        self.assertEqual(results.get_suggested_facets(1),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 ))])
        self.assertEqual(results.get_suggested_facets(2),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 )),
                          ('f2', (((0.0, 0.0), 17),
                                  ((1.0, 1.0), 16),
                                  ((2.0, 2.0), 16),
                                  ((3.0, 3.0), 17),
                                  ((4.0, 4.0), 17),
                                  ((5.0, 5.0), 17),
                                  ((6.0, 6.0), 16),
                                 ))])
        self.assertEqual(results.get_suggested_facets(2,
                                                required_facets=('f1', )),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 )),
                          ('f2', (((0.0, 0.0), 17),
                                  ((1.0, 1.0), 16),
                                  ((2.0, 2.0), 16),
                                  ((3.0, 3.0), 17),
                                  ((4.0, 4.0), 17),
                                  ((5.0, 5.0), 17),
                                  ((6.0, 6.0), 16),
                                 ))])
        self.assertEqual(results.get_suggested_facets(1,
                                                required_facets=('f1', )),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 ))])

        # Try getting some facet results for a pure cache hit,
        # with some facets not in the cache.
        count = 2
        results = query_world.merge_with_cached(world_queryid) \
                             .search(0, count, getfacets=True,
                                     facet_checkatleast=2)
        resultids = [int(result.id, 16) for result in results]
        self.assertEqual(resultids, [i - 1 for i in world_order[:count]])
        self.assertEqual(results.matches_lower_bound, 8)
        self.assertEqual(results.matches_upper_bound, 59)
        self.assertEqual(results.matches_estimated, 59)
        self.assertEqual(results.get_facets(), {
            'f1': (
                   ('0', 7),
                   ('2', 12),
                   ('3', 12),
                   ('4', 12),
                  ),
            'f2': (((0.0, 0.0), 9),
                   ((1.0, 1.0), 8),
                   ((2.0, 2.0), 8),
                   ((3.0, 3.0), 8),
                   ((4.0, 4.0), 8),
                   ((5.0, 5.0), 9),
                   ((6.0, 6.0), 9),
                  )
        })
        self.assertEqual(results.get_suggested_facets(1),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 ))])
        self.assertEqual(results.get_suggested_facets(2),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 )),
                          ('f2', (((0.0, 0.0), 9),
                                  ((1.0, 1.0), 8),
                                  ((2.0, 2.0), 8),
                                  ((3.0, 3.0), 8),
                                  ((4.0, 4.0), 8),
                                  ((5.0, 5.0), 9),
                                  ((6.0, 6.0), 9),
                                 ))])
        self.assertEqual(results.get_suggested_facets(2,
                                                required_facets=('f1', )),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 )),
                          ('f2', (((0.0, 0.0), 9),
                                  ((1.0, 1.0), 8),
                                  ((2.0, 2.0), 8),
                                  ((3.0, 3.0), 8),
                                  ((4.0, 4.0), 8),
                                  ((5.0, 5.0), 9),
                                  ((6.0, 6.0), 9),
                                 ))])
        self.assertEqual(results.get_suggested_facets(1,
                                                required_facets=('f1', )),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 ))])

        # Try getting some facet results for a pure cache hit,
        # with all facets in the cache.
        count = 2
        results = query_world.merge_with_cached(world_queryid) \
                             .search(0, count, getfacets=True,
                                     allowfacets=['f1'],
                                     facet_checkatleast=2)
        resultids = [int(result.id, 16) for result in results]
        self.assertEqual(resultids, [i - 1 for i in world_order[:count]])
        self.assertEqual(results.matches_lower_bound, 8)
        self.assertEqual(results.matches_upper_bound, 59)
        self.assertEqual(results.matches_estimated, 59)
        self.assertEqual(results.get_facets(), {
            'f1': (
                   ('0', 7),
                   ('2', 12),
                   ('3', 12),
                   ('4', 12),
                  ),
        })
        self.assertEqual(results.get_suggested_facets(1),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 ))])
        self.assertEqual(results.get_suggested_facets(2),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 )),
                          ])
        self.assertEqual(results.get_suggested_facets(2,
                                                required_facets=('f1', )),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 )),
                          ])
        self.assertEqual(results.get_suggested_facets(1,
                                                required_facets=('f1', )),
                         [('f1', (
                                  ('0', 7),
                                  ('2', 12),
                                  ('3', 12),
                                  ('4', 12),
                                 ))])

if __name__ == '__main__':
    main()
