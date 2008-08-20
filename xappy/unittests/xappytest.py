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
r"""xappytest.py: Framework for xappy unittests.

Unittests should just start with "from xappytest import *", which will provide
a convenient environment for writing tests of xappy features.

"""
__docformat__ = "restructuredtext en"

import os
import shutil
import sys
import tempfile
import unittest

# Ensure that xappy is on the path, when run uninstalled.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
import xappy

class TestCase(unittest.TestCase):
    """Base class of xappy unittests.

    """
    def setUp(self):
        """Set up environment for a unittest.

        This should not normally be implemented in subclasses - instead,
        implement the pre_test() method, which is called by this method after
        performing the standard test setup process.

        """
        self.tempdir = tempfile.mkdtemp()
        self.datadir = os.path.join(os.path.dirname(__file__), 'testdata')
        self.pre_test()

    def tearDown(self):
        """Clean up after a unittest.

        This should not normally be implemented in subclasses - instead,
        implement the post_test() method, which is called by this method before
        performing the standard cleanup process.

        """
        self.post_test()
        shutil.rmtree(self.tempdir)

    def pre_test(self):
        """Prepare for a test.  This is called before a test is started, but
        after the standard setup process.

        This is intended to be overridden by subclasses when special setup is
        required for a test.

        """
        pass

    def post_test(self):
        """Cleanup after a test.  This is called after a test finishes, but
        before the standard cleanup process.

        This is intended to be overridden by subclasses when special cleanup is
        required for a test.

        """
        pass



main = unittest.main
