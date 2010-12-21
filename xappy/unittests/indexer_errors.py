# vim: set fileencoding=utf-8 :
#
# Copyright (C) 2009 Pablo Hoffman
# Copyright (C) 2009 Lemur Consulting Ltd
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

from xappy.errors import DuplicatedIdError

class TestIndexerErrors(TestCase):

    def test_indexer_errors(self):
        """Test that DuplicatedIdError is thrown appropriately.

        """
        indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(indexpath)

        doc = xappy.UnprocessedDocument("121")
        iconn.add(doc)

        doc = xappy.UnprocessedDocument("121")
        self.assertRaises(DuplicatedIdError, iconn.add, doc)

        iconn.flush()

        self.assertRaises(DuplicatedIdError, iconn.add, doc)

        iconn.delete("121")
        iconn.add(doc)
        self.assertRaises(DuplicatedIdError, iconn.add, doc)

        iconn.close()


if __name__ == '__main__':
    main()
