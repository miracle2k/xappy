#!/usr/bin/env python
#
# Copyright (C) 2009 Richard Boulton
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
r"""numpy_inverter.py: Inversion routine using numpy.

"""
__docformat__ = "restructuredtext en"

import queryinvert

class NumpyInverterMixIn(object):
    """Inverting implementation which uses a numpy array for storage.

    Should be able to scale to larger data volumes than the naive version.

    """
    def prepare_iter_by_docid(self):
        """Prepare to iterate by document ID.

        This builds an inverted list in memory, if there isn't already a list
        built.

        """
        if getattr(self, 'inverted_iter', None) is None:
            if self.is_empty():
                self.inverted_iter = ()
                return
            def itemiter():
                """Forward iterator, as required by queryinvert.InverseIterator.

                """
                for queryid in self.iter_queryids():
                    yield queryid, self.get_hits(queryid)
            self.inverted_iter = queryinvert.InverseIterator(itemiter())

    def invalidate_iter_by_docid(self):
        """Invalidate any cached items for the iter_by_docid.

        """
        if getattr(self, 'inverted_iter', None) is not None:
            if not isinstance(self.inverted_iter, tuple):
                self.inverted_iter.close()
        self.inverted_iter = None

    def iter_by_docid(self):
        """Return an iterator which returns all the documents with cached hits,
        in order of document ID, together with the queryids and ranks for those
        queries.

        Returns (docid, <list of (queryid, rank)>) pairs.

        """
        self.prepare_iter_by_docid()
        return self.inverted_iter
