from unittest import TestCase, main
import tempfile, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from xappy.indexerconnection import *
from xappy.fieldactions import *
from xappy.searchconnection import *

class TestSpellCorrect(TestCase):
    def setUp(self):
        tempdir = tempfile.mkdtemp()
        self.indexpath = os.path.join(tempdir, 'foo')
        iconn = IndexerConnection(self.indexpath)
        iconn.add_field_action('name', FieldActions.INDEX_FREETEXT, spell=True,)
        for i in xrange(5):
            doc = UnprocessedDocument()
            doc.fields.append(Field('name', 'bruno is a nice guy'))
            iconn.add(doc)
        iconn.flush()
        iconn.close()
        self.sconn = SearchConnection(self.indexpath)

    def test_spell_correct(self):
        query = 'brunore'
        self.assertEqual('bruno', self.sconn.spell_correct(query))
        query = 'brunore-brunore'
        self.sconn.spell_correct(query)#will throw RuntimeError

    def tearDown(self):
        self.sconn.close()

if __name__ == '__main__':
    main()
