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
r"""cache_search_results.py: The results of a search from a cache.

"""
__docformat__ = "restructuredtext en"

from searchresults import SearchResult
try:
    import simplejson as json
except ImportError:
    import json


class CacheTermWeightGetter(object):
    """Object for getting termweights directly from an mset.

    """
    def __init__(self):
        pass

    def get(self, term):
        # Not sure how to implement this.  Perhaps we actually need to make an
        # mset, but for a 0-entry search.
        return FIXME


class CacheMSetItem(object):
    def __init__(self, conn, rank, xapid):
        self.document = conn.get_document(xapid=xapid)._doc
        self.rank = rank
        self.weight = 0
        self.percent = 0


class CacheSearchResultIter(object):
    """An iterator over a set of results from a search.

    """
    def __init__(self, xapids, context):
        self.context = context
        self.it = enumerate(xapids)

    def next(self):
        rank, xapid = self.it.next()
        msetitem = CacheMSetItem(self.context.conn, rank, xapid)
        return SearchResult(msetitem, self.context)


class CacheResultOrdering(object):
    def __init__(self, context, xapids, startrank):
        self.context = context
        self.xapids = xapids
        self.startrank = startrank

    def get_iter(self):
        """Get an iterator over the search results.

        """
        return CacheSearchResultIter(self.xapids, self.context)

    def get_hit(self, index):
        """Get the hit with a given index.

        """
        msetitem = CacheMSetItem(self.context.conn, index,
                                 self.xapids[index - self.startrank])
        return SearchResult(msetitem, self.context)

    def __len__(self):
        """Get the number of items in this ordering.

        """
        return len(self.xapids)

    def get_startrank(self):
        return self.startrank

    def get_endrank(self):
        return self.startrank + len(self.xapids)


class CacheFacetResults(object):
    """The result of counting facets.

    """
    def __init__(self, facets):
        self.facets = facets

    def get_suggested_facets(self, maxfacets,
                             desired_num_of_categories,
                             required_facets):
        return self.facets
