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

class TestDbType(TestCase):
    """Tests of specifying the type of a database.

    """

    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'db')
        self.indexpath_flint = os.path.join(self.tempdir, 'flint_db')
        self.indexpath_chert = os.path.join(self.tempdir, 'chert_db')

    def test_unknown_type(self):
        """Check that specifying an unknown type raises the appropriate error.

        """
        self.assertRaises(xappy.XapianInvalidArgumentError, xappy.IndexerConnection, self.indexpath, dbtype="footype")

    def test_default_type(self):
        """Check that the default type is flint.

        """
        iconn = xappy.IndexerConnection(self.indexpath)
        self.assertTrue(os.path.exists(os.path.join(self.indexpath, 'iamflint')))
        self.assertFalse(os.path.exists(os.path.join(self.indexpath, 'iamchert')))
        iconn.close()

    def test_flint_type(self):
        """Check that specifying the type as flint works.

        """
        iconn = xappy.IndexerConnection(self.indexpath_flint, dbtype="flint")
        self.assertTrue(os.path.exists(os.path.join(self.indexpath_flint, 'iamflint')))
        self.assertFalse(os.path.exists(os.path.join(self.indexpath_flint, 'iamchert')))
        iconn.close()

    def test_chert_type(self):
        """Check that specifying the type as chert works.

        """
        iconn = xappy.IndexerConnection(self.indexpath_chert, dbtype="chert")
        self.assertTrue(os.path.exists(os.path.join(self.indexpath_chert, 'iamchert')))
        self.assertFalse(os.path.exists(os.path.join(self.indexpath_chert, 'iamflint')))
        iconn.close()

if __name__ == '__main__':
    main()
