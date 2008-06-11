from unittest import TestCase, main
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from xappy.indexerconnection import *

class TestTypeCompat(TestCase):
    def test_backwards_compatibility1(self):
        path = os.path.join(os.path.dirname(__file__), 'testdata', 'chert_db')
        iconn = IndexerConnection(path)
        iconn.close()
        path = os.path.join(os.path.dirname(__file__), 'testdata', 'flint_db')
        iconn = IndexerConnection(path)
        iconn.close()

if __name__ == '__main__':
    main()
