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

class TestTypeCompat(TestCase):
    """Test compatibility with different types.

    """
    def test_open_chert(self):
        """Check that we can open an existing chert database.

        """
        path = os.path.join(self.datadir, 'chert_db')
        iconn = xappy.IndexerConnection(path)
        iconn.close()

    def test_open_flint(self):
        """Check that we can open an existing flint database.

        """
        path = os.path.join(self.datadir, 'flint_db')
        iconn = xappy.IndexerConnection(path)
        iconn.close()

if __name__ == '__main__':
    main()
