# Copyright (C) 2007 Lemur Consulting Ltd
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
r"""setuppaths.py: Setup sys.path

This is a special module which ensures that sys.path is set appropriately
simply by being imported.

To use, simply import it at the very start of any module which requires
use of xappy.  This will allow the module to work with an uninstalled version
of xappy located relative to this path.

"""
__docformat__ = "restructuredtext en"

import os
import sys

def setup_path():
    """Set up sys.path to allow us to import Xappy when run uninstalled.

    """
    abspath = os.path.abspath(__file__)
    dirname = os.path.dirname(abspath)
    dirname = os.path.dirname(dirname)
    if os.path.exists(os.path.join(dirname, 'xappy')):
        sys.path.insert(0, dirname)

setup_path()
