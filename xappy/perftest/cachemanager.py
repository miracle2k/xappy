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
from harness import *
from xappy.cachemanager import *

import cPickle
import random
import time

config = {
    'version': 1,
    'seed': 42,
    'docids': 1000000,
    'deldocs': 100000,
    'cacheditems': 1000000,
    'minitemspercache': 1000,
    'maxitemspercache': 10000,
}

config['cacheditems'] = 1000
config['deldocs'] = 1000

class TestCacheManager(PerfTestCase):
    def hash_data(self):
        return ','.join("%s,%s" % (key, value) for key, value in sorted(config.iteritems()))

    def build_data(self):
        """Build the datafile.

        """
        print "Building datafile"
        random.seed(config['seed'])
        datafile = os.path.join(self.builtdatadir, 'data')
        fd = open(datafile, 'w')

        def make_query_id():
            return ''.join('%x' % random.randint(1, 16) for i in xrange(16))

        for i in xrange(config['cacheditems']):
            qid = make_query_id()
            itemcount = random.randint(config['minitemspercache'],
                                         config['maxitemspercache'])
            ids = random.sample(xrange(1, config['docids'] + 1), itemcount)
            p = cPickle.dumps(ids, 2)
            fd.write('%d\nQuery(%s)\n' % (len(p), qid) + p)
            if (i + 1) % 1000 == 0:
                print "%d queries added" % i
        fd.close()

        print "Building empty database"
        iconn = xappy.IndexerConnection(self.get_origdbpath())
        iconn.add_field_action('text', xappy.FieldActions.INDEX_FREETEXT)

        for i in xrange(1, config['docids'] + 1):
            doc = xappy.UnprocessedDocument()
            doc.append('text', 'doc %d' % i)
            iconn.add(doc)
            if i % 1000 == 0:
                print "%d documents added" % i
        iconn.flush()

    def iter_data(self):
        """Iterate through the stored datafile.

        Returns tuples of queryid, list_of_docids

        """
        datafile = os.path.join(self.builtdatadir, 'data')
        fd = open(datafile)

        while True:
            bytes = fd.readline()
            if len(bytes) == 0:
                break
            bytes = int(bytes)
            qid = fd.readline()
            data = fd.read(bytes)
            assert len(data) == bytes
            data = cPickle.loads(data)
            yield qid, data

    def get_origdbpath(self):
        return os.path.join(self.builtdatadir, 'db')

    def test_cache_perf_standalone(self):
        """Test the standalone performance of the cache.

        """
        dbpath = os.path.join(self.tempdir, 'db')
        cachepath = os.path.join(self.tempdir, 'cache')
        cache = XapianCacheManager(cachepath, chunksize=100)
        #cache = XapianSelfInvertingCacheManager(cachepath, chunksize=100)

        # Copy the database into the temporary directory.
        self.start_timer('copydb', 'Copy initial database into place')
        shutil.copytree(self.get_origdbpath(), dbpath)
        self.stop_timer('copydb')

        # Check the behaviour of an empty cache.
        self.assertEqual(list(cache.iter_by_docid()), [])
        self.assertEqual(cache.get_hits(0), [])
        self.assertEqual(list(cache.keys()), [])

        # Add the hits to the cache.
        self.start_timer('set_hits',
                         'Initial population of cache with %d queries' %
                         config['cacheditems'])
        for qidstr, docids in self.iter_data():
            qid = cache.get_or_make_queryid(qidstr)
            cache.set_hits(qid, docids)
        self.start_timer('flush1', '... flush')
        cache.flush()
        self.stop_timer('flush1')
        self.stop_timer('set_hits')

        self.start_timer('apply_cache', 'Apply cached items to the database')
        iconn = xappy.IndexerConnection(dbpath)
        iconn.set_cache_manager(cache)
        self.start_timer('prepare_cache', '... prepare')
        cache.prepare_iter_by_docid()
        self.stop_timer('prepare_cache')
        self.start_timer('do_apply_cache', '... apply')
        iconn.apply_cached_items()
        self.stop_timer('do_apply_cache')
        self.start_timer('flush2', '... flush')
        iconn.flush()
        self.stop_timer('flush2')
        self.stop_timer('apply_cache')

        self.start_timer('del_docs', 'Delete %d documents' % config['deldocs'])
        for docid in random.sample(xrange(1, config['docids'] + 1),
                                   config['deldocs']):
            print docid
            iconn.delete(xapid=docid)
        self.start_timer('flush3', ' ... flush')
        iconn.flush()
        self.stop_timer('flush3')
        self.stop_timer('del_docs')

        print dbpath
        import time
        time.sleep(600)

if __name__ == '__main__':
    main()
