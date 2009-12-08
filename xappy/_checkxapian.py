# Copyright (C) 2008 Lemur Consulting Ltd
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
r"""_checkxapian.py: Check the version of xapian used.

Raises an ImportError on import if the version used is too old to be used at
all.

"""
__docformat__ = "restructuredtext en"

# The minimum version of xapian required to work at all.
min_xapian_version = (1, 0, 6)

# Dictionary of features we can't support do to them being missing from the
# available version of xapian.
missing_features = {}

import xapian

versions = xapian.major_version(), xapian.minor_version(), xapian.revision()


if versions < min_xapian_version:
    raise ImportError("""
        Xapian Python bindings installed, but need at least version %d.%d.%d - got %s
        """.strip() % tuple(list(min_xapian_version) + [xapian.version_string()]))

if not hasattr(xapian, 'ValueCountMatchSpy'):
    missing_features['facets'] = 1
if not hasattr(xapian, 'ValueWeightPostingSource'):
    missing_features['valueweight'] = 1

try:
    import xapian.imgseek
except ImportError:
    missing_features['imgseek'] = 1
