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
r"""inverter.py: Base cachemanager classes.

"""
__docformat__ = "restructuredtext en"

class InMemoryInverterMixIn(object):
    """Simple inverting implementation: build up all the data in memory.

    """
    def prepare_iter_by_docid(self):
        """Prepare to iterate by document ID.

        This builds an inverted list in memory, if there isn't already a list
        built.

        """
        if getattr(self, 'inverted_items', None) is None:
            items = {}
            for queryid in self.iter_queryids():
                for rank, docid in enumerate(self.get_hits(queryid)):
                    items.setdefault(docid, []).append((queryid, rank))
            self.inverted_items = items

    def invalidate_iter_by_docid(self):
        """Invalidate any cached items for the iter_by_docid.

        """
        self.inverted_items = None

    def iter_by_docid(self):
        """Return an iterator which returns all the documents with cached hits,
        in order of document ID, together with the queryids and ranks for those
        queries.

        Returns (docid, <list of (queryid, rank)>) pairs.

        """
        self.prepare_iter_by_docid()
        items = self.inverted_items
        for docid in sorted(items.keys()):
            yield docid, items[docid]
