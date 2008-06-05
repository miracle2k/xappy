from unittest import TestCase, main
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import xappy

class TestWeightAction(TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        iconn.add_field_action('name', xappy.FieldActions.INDEX_FREETEXT,)
        iconn.add_field_action('weight', xappy.FieldActions.WEIGHT,)
        for i in xrange(5):
            doc = xappy.UnprocessedDocument()
            doc.fields.append(xappy.Field('name', 'bruno is a nice guy'))
            doc.fields.append(xappy.Field('name', ' '.join('one two three four five'.split()[i:])))
            doc.fields.append(xappy.Field('weight', i / 4.0))
            iconn.add(doc)
        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)

    def test_pure_weight(self):
        q = self.sconn.query_field("weight")
        r = self.sconn.search(q, 0, 10)
        self.assertEqual([int(i.id) for i in r], [4, 3, 2, 1, 0])

    def test_weight_combined(self):
        q1 = self.sconn.query_parse("one nice guy", default_op=self.sconn.OP_OR)
        r = self.sconn.search(q1, 0, 10)
        self.assertEqual([int(i.id) for i in r], [0, 4, 3, 2, 1])

        q2 = self.sconn.query_field("weight")
        r = self.sconn.search(q2, 0, 10)
        self.assertEqual([int(i.id) for i in r], [4, 3, 2, 1, 0])

        # Combining the weights directly - the weight from the text overpowers
        # the document weight.
        q = self.sconn.query_composite(self.sconn.OP_OR, (q1, q2))
        r = self.sconn.search(q, 0, 10)
        self.assertEqual([int(i.id) for i in r], [0, 4, 3, 2, 1])

        # Combining the weights with normalisation - the weights are now
        # comparable, neither overpowering the other.
        maxwt = self.sconn.get_max_possible_weight(q1)
        q1b = self.sconn.query_multweight(q1, 2.0 / maxwt)
        q = self.sconn.query_composite(self.sconn.OP_OR, (q1b, q2))
        r = self.sconn.search(q, 0, 10)
        self.assertEqual([int(i.id) for i in r], [4, 0, 3, 2, 1])

    def tearDown(self):
        self.sconn.close()
        shutil.rmtree(self.tempdir)

if __name__ == '__main__':
    main()
