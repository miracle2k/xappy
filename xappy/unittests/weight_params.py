from unittest import TestCase, main
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import xappy

def result_ids(results):
    return [int(i.id) for i in results]

class TestWeightParams(TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('text', xappy.FieldActions.INDEX_FREETEXT,)
        for i in xrange(5):
            doc = xappy.UnprocessedDocument()
            doc.fields.append(xappy.Field('text', 'foo ' * (i + 1)))
            doc.fields.append(xappy.Field('text', ' '.join('one two three four five'.split()[i:])))
            iconn.add(doc)
        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def test_wdf_importance(self):
        q = self.sconn.query_field("text", "foo")
        r = self.sconn.search(q, 0, 10)
        self.assertEqual(result_ids(r), [4, 3, 2, 1, 0])
        r = self.sconn.search(q, 0, 10, weight_params={'k1': 0})
        self.assertEqual(result_ids(r), [0, 1, 2, 3, 4])
        r = self.sconn.search(q, 0, 10, weight_params={'k1': 0.1})
        self.assertEqual(result_ids(r), [4, 3, 2, 1, 0])

        q = self.sconn.query_field("text", "foo one", default_op=self.sconn.OP_OR)
        r = self.sconn.search(q, 0, 10)
        self.assertEqual(result_ids(r), [0, 4, 3, 2, 1])
        r = self.sconn.search(q, 0, 10, weight_params={'k1': 0})
        self.assertEqual(result_ids(r), [0, 1, 2, 3, 4])
        r = self.sconn.search(q, 0, 10, weight_params={'k1': 0.1})
        self.assertEqual(result_ids(r), [0, 4, 3, 2, 1])

    def tearDown(self):
        self.sconn.close()
        shutil.rmtree(self.tempdir)

if __name__ == '__main__':
    main()
