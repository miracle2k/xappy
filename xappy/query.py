#!/usr/bin/env python
#
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
r"""searchconnection.py: A connection to the search engine for searching.

"""
__docformat__ = "restructuredtext en"

import _checkxapian
import xapian
from replaylog import log

class Query(object):
    """A query.

    """

    OP_AND = xapian.Query.OP_AND
    OP_OR = xapian.Query.OP_OR

    def __init__(self, query=None, _refs=None, _conn=None, _ranges=None,
                 _serialised=None):
        """Create a new query.

        If `query` is a xappy.Query, or xapian.Query, object, the new query is
        initialised as a copy of the supplied query.

        """
        # Copy _refs, and make sure it's a list.
        if _refs is None:
            _refs = []
        else:
            _refs = [ref for ref in _refs]

        if _ranges is None:
            _ranges = []
        else:
            _ranges = [tuple(range) for range in _ranges]

        if query is None:
            query = log(xapian.Query)
            if _serialised is None:
                _serialised = 'xappy.Query()'

        # Set the default query parameters.
        self.__checkatleast = 0
        self.__sortby = None

        if isinstance(query, xapian.Query):
            self.__query = query
            self.__refs = _refs
            self.__conn = _conn
            self.__ranges = _ranges
            self.__serialised = _serialised
        else:
            # Assume `query` is a xappy.Query() object.
            self.__query = query.__query
            self.__refs = _refs
            self.__conn = _conn
            self.__ranges = _ranges
            if _serialised is None:
                self.__serialised = query.__serialised
            else:
                self.__serialised = _serialised
            self.__merge_params(query)

    def empty(self):
        """Test if the query is empty.

        A empty query contains no terms or other sources of documents, and will
        thus match no documents.

        An empty query may be constructed by the default constructor, or by
        composing an empty list.

        """
        return self.__query.empty()

    def __merge_params(self, query):
        """Merge the parameters in this query with those in another query.

        """
        # Check that the connection is compatible.
        if self.__conn is not query.__conn:
            if self.__conn is None:
                self.__conn = query.__conn
            elif query.__conn is not None:
                raise ValueError("Queries are not from the same connection")

        # Combine the refs
        self.__refs.extend(query.__refs)

        # Combine the ranges
        for range in query.__ranges:
            if range not in self.__ranges:
                self.__ranges.append(range)

    @staticmethod
    def compose(operator, queries):
        """Build and return a composite query from a list of queries.

        The queries are combined with the supplied operator, which is either
        Query.OP_AND or Query.OP_OR.

        `queries` is any iterable which returns a list of queries (either
        xapian.Query or xappy.Query objects).

        """
        result = Query()
        xapqs = []
        serialisedqs = []
        for q in queries:
            if isinstance(q, xapian.Query):
                xapqs.append(q)
                serialisedqs = None
            elif isinstance(q, Query):
                xapqs.append(q.__query)
                if serialisedqs is not None:
                    serialisedq = q.__serialised
                    if serialisedq is None:
                        serialisedqs = None
                    else:
                        serialisedqs.append(serialisedq)
                result.__merge_params(q)
            else:
                raise TypeError("queries must contain a list of xapian.Query or xappy.Query objects")
        result.__query = log(xapian.Query, operator, xapqs)
        if serialisedqs is not None:
            serialisedqs = ', '.join(serialisedqs)
            if serialisedqs != '':
                serialisedqs = '(' + serialisedqs + ',)'
            else:
                serialisedqs = '()'
            result.__serialised = "xappy.Query.compose(%d, %s)" % (operator, serialisedqs)
        return result

    def __mul__(self, multiplier):
        """Return a query with the weight scaled by multiplier.

        """
        result = Query()
        result.__merge_params(self)
        if self.__serialised is not None:
            result.__serialised = "%s * %.65g" % (self.__serialised, multiplier)
        try:
            result.__query = log(xapian.Query,
                                 xapian.Query.OP_SCALE_WEIGHT,
                                 self.__query, multiplier)
        except TypeError:
            return NotImplemented
        return result

    def __rmul__(self, lhs):
        """Return a query with the weight scaled by multiplier.

        """
        return self.__mul__(lhs)

    def __div__(self, rhs):
        """Return a query with the weight divided by a number.

        """
        try:
            return self.__mul__(1.0 / rhs)
        except TypeError:
            return NotImplemented

    def __truediv__(self, rhs):
        """Return a query with the weight divided by a number.

        """
        try:
            return self.__mul__(1.0 / rhs)
        except TypeError:
            return NotImplemented

    def __and__(self, other):
        """Return a query combined using AND with another query.

        """
        if not isinstance(other, (Query, xapian.Query)):
            return NotImplemented
        return self.__combine_with(Query.OP_AND, other)

    def __or__(self, other):
        """Return a query combined using OR with another query.

        """
        if not isinstance(other, (Query, xapian.Query)):
            return NotImplemented
        return self.__combine_with(Query.OP_OR, other)

    def __xor__(self, other):
        """Return a query combined using XOR with another query.

        """
        if not isinstance(other, (Query, xapian.Query)):
            return NotImplemented
        return self.__combine_with(xapian.Query.OP_XOR, other)

    def __combine_with(self, operator, other):
        """Return the result of combining this query with another query.

        """
        result = Query(self)
        if isinstance(other, xapian.Query):
            oquery = other
        elif isinstance(other, Query):
            oquery = other.__query
            result.__merge_params(other)
            if self.__serialised is not None and other.__serialised is not None:
                funcname = {
                    Query.OP_AND: " & ",
                    Query.OP_OR: " | ",
                    xapian.Query.OP_XOR: " ^ ",
                    xapian.Query.OP_AND_NOT: ".and_not",
                    xapian.Query.OP_FILTER: ".filter",
                    xapian.Query.OP_AND_MAYBE: ".adjust",
                }[operator]
                result.__serialised = ''.join(('(', self.__serialised, ')',
                                               funcname, '(',
                                               other.__serialised, ')'))
        else:
            raise TypeError("other must be a xapian.Query or xappy.Query object")

        result.__query = log(xapian.Query, operator, self.__query, oquery)

        return result

    def and_not(self, other):
        """Return a query which returns filtered results of this query.

        The query will return only those results which aren't also matched by
        `other`, which should also be a query.

        """
        return self.__combine_with(xapian.Query.OP_AND_NOT, other)

    def filter(self, other):
        """Return a query which returns filtered results of this query.

        The query will return only those results which are also matched by
        `other`, which should also be a query, but the weights of the results will not be modified by those
        from `other`.

        """
        return self.__combine_with(xapian.Query.OP_FILTER, other)

    def adjust(self, other):
        """Return a query with this query's weights adjusted by another query.

        Documents will be returned from the resulting query if and only if they
        match this query.  However, the weights of the resulting documents will
        be adjusted by adding weights from the secondary query (specified by
        the `other` parameter).

        Note: this method is available both as "adjust" and as "and_maybe".

        """
        return self.__combine_with(xapian.Query.OP_AND_MAYBE, other)

    # Add "and_maybe" as an alternative name for "adjust", since this name is
    # familiar to people with a Xapian background.
    and_maybe = adjust

    def get_max_possible_weight(self):
        """Calculate the maximum possible weight returned by this query.

        See `SearchConnection.get_max_possible_weight()` for more details.

        """
        if self.empty():
            return 0
        if self.__conn is None:
            raise ValueError("This Query is not associated with a SearchConnection")

        return self.__conn.get_max_possible_weight(self)

    def norm(self):
        """Normalise the possible weights returned by a query.

        This will return a new Query, which returns the same documents as this
        query, but for which the weights will fall strictly in the range 0..1.

        This is equivalent to dividing the query by the result of
        `get_max_possible_weight()`, except that the case of the maximum
        possible weight being 0 is handled correctly.  Note that this means
        that it will be very rare for a resulting document to attain a weight
        of 1.0.

        """
        max_possible = self.get_max_possible_weight()
        if max_possible > 0:
            return self / max_possible
        return self

    def search(self, startrank, endrank, *args, **kwargs):
        """Perform a search using this query.

        - `startrank` is the rank of the start of the range of matching
          documents to return (ie, the result with this rank will be returned).
          ranks start at 0, which represents the "best" matching document.
        - `endrank` is the rank at the end of the range of matching documents
          to return.  This is exclusive, so the result with this rank will not
          be returned.

        Additional arguments and keyword arguments may be specified.  These
        will be interpreted as by SearchConnection.search().

        """
        if self.__conn is None:
            raise ValueError("This Query is not associated with a SearchConnection")

        return self.__conn.search(self, startrank, endrank, *args, **kwargs)

    def _get_xapian_query(self):
        """Get the query as a xapian object.

        This is intended for internal use in xappy only.

        If you _must_ use it outside xappy, note in particular that the xapian
        query will only remain valid as long as this object is valid.  Using it
        after this object has been deleted may result in invalid memory access
        and segmentation faults.

        """
        return self.__query

    def _get_terms(self):
        """Get a list of the terms in the query.

        This is intended for internal use in xappy only.

        """
        qtermiter = xapian.TermIter(self.__query.get_terms_begin(),
                                    self.__query.get_terms_end())
        return [item.term for item in qtermiter]

    def _get_ranges(self):
        """Get a list of the ranges in the query.

        This is intended for internal use in xappy only.

        The return type is a tuple of items, where each item consists of
        (fieldname, start, end)

        """
        return self.__ranges

    def evalable_repr(self):
        """Return a serialised form of this query, suitable for eval.

        This form can be passed to eval to get back the unserialised query,
        though this must be done in a context in which "conn" is a symbol
        defined to be the search connection which the query is associated with,
        and in which "xapian" is the appropriate module.  A convenient method
        to do this is the SearchConnection.query_from_evalable() method.

        If the query was originally created by passing a raw xapian query to
        the query constructor, the serialised form cannot be computed, and this
        method will return None.

        """
        return self.__serialised

    def _set_serialised(self, serialised):
        """Set the serialised form of this query.

        This is intended for internal use in xappy only.

        """
        self.__serialised = serialised

    def __str__(self):
        return str(self.__query)

    def __repr__(self):
        return "<xappy.Query(%s)>" % str(self.__query)
