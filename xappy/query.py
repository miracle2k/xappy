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
import errors
from replaylog import log

class Query(object):
    """A query.

    """

    OP_AND = xapian.Query.OP_AND
    OP_OR = xapian.Query.OP_OR

    def __init__(self, query=None, _refs=None):
        """Create a new query.

        If `query` is a xappy.Query, or xapian.Query, object, the new query is
        initialised as a copy of the supplied query.

        """
        if _refs is None:
            _refs = []
        if query is None:
            self.__query = log(xapian.Query)
            self.__refs = _refs
        elif isinstance(query, xapian.Query):
            self.__query = query
            self.__refs = _refs
        else:
            self.__query = query.__query
            self.__refs = []
            self.__refs.extend(query.__refs)
            self.__refs.extend(_refs)
        assert(self.__refs is not None)

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
        for q in queries:
            if isinstance(q, xapian.Query):
                xapqs.append(q)
            elif isinstance(q, Query):
                xapqs.append(q.__query)
                result.__refs.extend(q.__refs)
            else:
                raise TypeError("queries must contain a list of xapian.Query or xappy.Query objects")
        result.__query = log(xapian.Query, operator, xapqs)
        return result

    def __mul__(self, multiplier):
        """Return a query with the weight scaled by multiplier.

        """
        result = Query()
        result.__refs = self.__refs

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
        result = Query()
        # Take a copy of the refs, so we don't modify the original query's
        # list.
        result.__refs = []
        result.__refs.extend(self.__refs)

        if isinstance(other, xapian.Query):
            oquery = other
        elif isinstance(other, Query):
            oquery = other.__query
            result.__refs.extend(other.__refs)
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

    def _get_xapian_query(self):
        """Get the query as a xapian object.

        This is intended for internal use in xappy only.

        If you _must_ use it outside xappy, note in particular that the xapian
        query will only remain valid as long as this object is valid.  Using it
        after this object has been deleted may result in invalid memory access
        and segmentation faults.

        """
        return self.__query

    def __str__(self):
        return str(self.__query)

    def __repr__(self):
        return "<xappy.Query(%s)>" % str(self.__query)
