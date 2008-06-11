from unittest import TestCase, main
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from xappy.indexerconnection import *
import xappy

class TestDbType(TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.indexpath = os.path.join(self.tempdir, 'db')
        self.indexpath_flint = os.path.join(self.tempdir, 'flint_db')
        self.indexpath_chert = os.path.join(self.tempdir, 'chert_db')

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_unknown_type(self):
        self.assertRaises(xappy.XapianInvalidArgumentError, IndexerConnection, self.indexpath, dbtype="footype")

        iconn = IndexerConnection(self.indexpath)
        self.assertTrue(os.path.exists(os.path.join(self.indexpath, 'iamflint')))
        self.assertFalse(os.path.exists(os.path.join(self.indexpath, 'iamchert')))
        iconn.close()

        iconn = IndexerConnection(self.indexpath_flint, dbtype="flint")
        self.assertTrue(os.path.exists(os.path.join(self.indexpath_flint, 'iamflint')))
        self.assertFalse(os.path.exists(os.path.join(self.indexpath_flint, 'iamchert')))
        iconn.close()

        iconn = IndexerConnection(self.indexpath_chert, dbtype="chert")
        self.assertTrue(os.path.exists(os.path.join(self.indexpath_chert, 'iamchert')))
        self.assertFalse(os.path.exists(os.path.join(self.indexpath_chert, 'iamflint')))
        iconn.close()

if __name__ == '__main__':
    main()
