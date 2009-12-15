# Copyright (C) 2007,2008,2009 Lemur Consulting Ltd
# Copyright (C) 2009 Pablo Hoffman
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
r"""searchconnection.py: A connection to the search engine for searching.

"""
__docformat__ = "restructuredtext en"

import _checkxapian
import os as _os
import cPickle as _cPickle
import math
import inspect
import itertools

import xapian
from cache_search_results import CacheResultOrdering, CacheResultStats, \
         CacheFacetResults
from datastructures import UnprocessedDocument, ProcessedDocument
from fieldactions import ActionContext, FieldActions, \
         ActionSet, SortableMarshaller, convert_range_to_term, \
         _get_imgterms
import fieldmappings
import errors
from indexerconnection import IndexerConnection, PrefixedTermIter, \
         DocumentIter, SynonymIter, _allocate_id
from query import Query
from searchresults import SearchResults, SearchResultContext
from mset_search_results import MSetFacetResults, \
         MSetResultOrdering, MSetResultStats, MSetTermWeightGetter

class ExternalWeightSource(object):
    """A source of extra weight information for searches.

    """
    def get_maxweight(self):
        """Get the maximum weight that the weight source can return.

        """
        return NotImplementedError("Subclasses should implement this method")

    def get_weight(self, doc):
        """Get the weight associated with a given document.

        `doc` is a ProcessedDocument object.

        """
        return NotImplementedError("Subclasses should implement this method")

class SearchConnection(object):
    """A connection to the search engine for searching.

    The connection will access a view of the database.

    """
    _qp_flags_wildcard = xapian.QueryParser.FLAG_WILDCARD
    _qp_flags_base = xapian.QueryParser.FLAG_LOVEHATE
    _qp_flags_phrase = xapian.QueryParser.FLAG_PHRASE
    _qp_flags_synonym = (xapian.QueryParser.FLAG_AUTO_SYNONYMS |
                         xapian.QueryParser.FLAG_AUTO_MULTIWORD_SYNONYMS)
    _qp_flags_bool = xapian.QueryParser.FLAG_BOOLEAN

    _index = None

    # Slots after this number are used for the cache manager.
    # FIXME - don't hard-code this - put it in the settings instead?
    _cache_manager_slot_start = 10000

    def __init__(self, indexpath):
        """Create a new connection to the index for searching.

        There may only an arbitrary number of search connections for a
        particular database open at a given time (regardless of whether there
        is a connection for indexing open as well).

        If the database doesn't exist, an exception will be raised.

        """
        self.cache_manager = None
        self._indexpath = indexpath
        self._close_handlers = []
        self._index = xapian.Database(indexpath)
        try:
            # Read the actions.
            self._load_config()
        except:
            if hasattr(self._index, 'close'):
                self._index.close()
            self._index = None
            raise
        self._imgterms_cache = {}

    def __del__(self):
        self.close()

    def append_close_handler(self, handler, userdata=None):
        """Append a callback to the list of close handlers.

        These will be called when the SearchConnection is closed.  This happens
        when the close() method is called, or when the SearchConnection object
        is deleted.  The callback will be passed two arguments: the path to the
        SearchConnection object, and the userdata supplied to this method.

        The handlers will be called in the order in which they were added.

        The handlers will be called after the connection has been closed, so
        cannot prevent it closing: their return value will be ignored.  In
        addition, they should not raise any exceptions.

        """
        self._close_handlers.append((handler, userdata))

    def _get_sort_type(self, field):
        """Get the sort type that should be used for a given field.

        """
        try:
            actions = self._field_actions[field]._actions
        except KeyError:
            actions = {}
        for action, kwargslist in actions.iteritems():
            if action == FieldActions.SORT_AND_COLLAPSE:
                for kwargs in kwargslist:
                    return kwargs['type']

    def _get_freetext_fields(self):
        """Get the fields which are indexed as freetext.

        Returns a sequence of 2-tuples, (fieldname, searchbydefault)

        """
        for field, actions in self._field_actions.actions.iteritems():
            for action, kwargslist in actions.iteritems():
                if action == FieldActions.INDEX_FREETEXT:
                    for kwargs in kwargslist:
                        return kwargs['type']

    def _load_config(self):
        """Load the configuration for the database.

        """
        # Note: this code is basically duplicated in the IndexerConnection
        # class.  Move it to a shared location.
        assert self._index is not None

        while True:
            try:
                config_str = self._index.get_metadata('_xappy_config')
                break
            except xapian.DatabaseModifiedError, e:
                # Don't call self.reopen() since that calls _load_config()!
                self._index.reopen()

        if len(config_str) == 0:
            self._field_actions = ActionSet()
            self._field_mappings = fieldmappings.FieldMappings()
            self._next_docid = 0
            self._facet_hierarchy = {}
            self._facet_query_table = {}
            return

        try:
            (actions,
             mappings,
             self._facet_hierarchy,
             self._facet_query_table,
             self._next_docid) = _cPickle.loads(config_str)
            self._field_actions = ActionSet()
            self._field_actions.actions = actions
            # Backwards compatibility; there used to only be one parent.
            for key in self._facet_hierarchy:
                parents = self._facet_hierarchy[key]
                if isinstance(parents, basestring):
                    parents = [parents]
                    self._facet_hierarchy[key] = parents
        except ValueError:
            # Backwards compatibility - configuration used to lack _facet_hierarchy and _facet_query_table
            (actions,
             mappings,
             self._next_docid) = _cPickle.loads(config_str)
            self._field_actions = ActionSet()
            self._field_actions.actions = actions
            self._facet_hierarchy = {}
            self._facet_query_table = {}
        self._field_mappings = fieldmappings.FieldMappings(mappings)

    def reopen(self):
        """Reopen the connection.

        This updates the revision of the index which the connection references
        to the latest flushed revision.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        self._index.reopen()
        # Re-read the actions.
        self._load_config()

    def close(self):
        """Close the connection to the database.

        It is important to call this method before allowing the class to be
        garbage collected to ensure that the connection is cleaned up promptly.

        No other methods may be called on the connection after this has been
        called.  (It is permissible to call close() multiple times, but
        only the first call will have any effect.)

        If an exception occurs, the database will be closed, but changes since
        the last call to flush may be lost.

        """
        if self._index is None:
            return

        # Remember the index path
        indexpath = self._indexpath

        try:
            self._index.close()
        except AttributeError:
            # Xapian versions earlier than 1.1.0 didn't have a close()
            # method, so we just had to rely on the garbage collector to
            # clean up.  Ignore the exception that occurs if we're using
            # 1.0.x.
            # FIXME - remove this special case when we no longer support
            # the 1.0.x release series.  Also remove the equivalent special
            # case in __init__.
            pass
        self._index = None
        self._indexpath = None
        self._field_actions = None
        self._field_mappings = None

        if self.cache_manager is not None:
            self.cache_manager.close()

        # Call the close handlers.
        for handler, userdata in self._close_handlers:
            try:
                handler(indexpath, userdata)
            except Exception, e:
                import sys, traceback
                print >>sys.stderr, "WARNING: unhandled exception in handler called by SearchConnection.close(): %s" % traceback.format_exception_only(type(e), e)

    def process(self, document):
        """Process an UnprocessedDocument with the settings in this database.

        The resulting ProcessedDocument is returned.

        Note that this processing will be automatically performed if an
        UnprocessedDocument is supplied to the add() or replace() methods of
        IndexerConnection.  This method is exposed to allow the processing to
        be performed separately, which may be desirable if you wish to manually
        modify the processed document before adding it to the database, or if
        you want to split processing of documents from adding documents to the
        database for performance reasons.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        result = ProcessedDocument(self._field_mappings)
        result.id = document.id
        context = ActionContext(self, readonly=True)

        self._field_actions.perform(result, document, context)

        return result

    def get_doccount(self):
        """Count the number of documents in the database.

        This count will include documents which have been added or removed but
        not yet flushed().

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        return self._index.get_doccount()

    OP_AND = Query.OP_AND
    OP_OR = Query.OP_OR
    def query_composite(self, operator, queries):
        """Build a composite query from a list of queries.

        The queries are combined with the supplied operator, which is either
        SearchConnection.OP_AND or SearchConnection.OP_OR.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        return Query.compose(operator, list(queries))

    def query_multweight(self, query, multiplier):
        """Build a query which modifies the weights of a subquery.

        This produces a query which returns the same documents as the subquery,
        and in the same order, but with the weights assigned to each document
        multiplied by the value of "multiplier".  "multiplier" may be any floating
        point value, but negative values will be clipped to 0, since Xapian
        doesn't support negative weights.

        This can be useful when producing queries to be combined with
        query_composite, because it allows the relative importance of parts of
        the query to be adjusted.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        return Query(query) * multiplier

    def query_filter(self, query, filter, exclude=False):
        """Filter a query with another query.

        If exclude is False (or not specified), documents will only match the
        resulting query if they match the both the first and second query: the
        results of the first query are "filtered" to only include those which
        also match the second query.

        If exclude is True, documents will only match the resulting query if
        they match the first query, but not the second query: the results of
        the first query are "filtered" to only include those which do not match
        the second query.

        Documents will always be weighted according to only the first query.

        - `query`: The query to filter.
        - `filter`: The filter to apply to the query.
        - `exclude`: If True, the sense of the filter is reversed - only
          documents which do not match the second query will be returned.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        try:
            if exclude:
                return query.and_not(filter)
            else:
                return query.filter(filter)
        except TypeError:
            raise errors.SearchError("Filter must be a Xapian Query object")

    def query_adjust(self, primary, secondary):
        """Adjust the weights of one query with a secondary query.

        Documents will be returned from the resulting query if and only if they
        match the primary query (specified by the "primary" parameter).
        However, the weights (and hence, the relevance rankings) of the
        documents will be adjusted by adding weights from the secondary query
        (specified by the "secondary" parameter).

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        return primary.adjust(secondary)

    _RANGE_EXACT = 0 # A query exactly matching the range.
    _RANGE_SUBSET = 1 # A query matching only a subset of the range.
    _RANGE_SUPERSET = 2 # A query matching a superset of the range.
    _RANGE_NONE = 3 # A query matching a none of the range.

    def _build_range_query(self, prefix, ranges, query_ranges):
        """Build a range query by converting each range into a term, and ORing
        them together.

        """
        queries = []
        for r in ranges:
            term = convert_range_to_term(prefix, r[0], r[1])
            queries.append(Query(xapian.Query(term), _conn=self,
                                 _ranges=query_ranges))
        return Query.compose(xapian.Query.OP_OR, queries)

    def _build_range_query_cons(self, prefix, begin, end, ranges, query_ranges):
        """Build an approximate range query for the given range which matches
        a maximal subset of the range.

        """
        # Make test_fn to check if fully in range
        if begin is not None and end is not None:
            test_fn = lambda r: begin <= r[0] and r[1] <= end
        elif begin is not None:
            test_fn = (lambda r: begin <= r[0])
        else:
            assert end is not None
            test_fn = (lambda r: r[1] <= end)
        valid_ranges = filter(test_fn, ranges)
        if len(valid_ranges) == 0:
            return Query(_conn=self, _ranges=query_ranges) * 0, \
                   self._RANGE_NONE

        q = self._build_range_query(prefix, valid_ranges, query_ranges) * 0

        min_r = min(r[0] for r in valid_ranges)
        max_r = max(r[1] for r in valid_ranges)
        if min_r == begin and max_r == end:
            return q, self._RANGE_EXACT

        return q, self._RANGE_SUBSET

    def _build_range_query_noncons(self, prefix, begin, end, ranges, query_ranges):
        """Build an approximate range query for the given range which matches
        a minimal superset of the range.

        Note that this is a difficult problem to solve in general, and the
        current algorithm will often not generate the best possible set of
        terms, if there are overlapping ranges stored.

        """
        if begin is None or end is None:
            # Currently, don't support openended ranges here.
            return Query(_conn=self, _ranges=query_ranges), self._RANGE_NONE

        ranges = list(ranges)
        ranges.sort(key=lambda r: (r[0], -r[1]))

        curr_top = None
        chosen_ranges = []
        for r in ranges:
            if end <= r[0] or begin >= r[1]:
                continue
            if curr_top is None:
                chosen_ranges.append(r)
                if begin < r[0]:
                    # Don't have full coverage.
                    return Query(_conn=self, _ranges=query_ranges), self._RANGE_NONE
                curr_top = r[1]
                continue

            if r[0] <= begin and chosen_ranges[0][0] <= begin:
                # Restart, with a tighter starting point (we know it's tighter,
                # because the starting points are in sorted ascending order).
                chosen_ranges = [r]
                curr_top = r[1]
                continue

            if curr_top <= r[1]:
                if curr_top < r[0]:
                    # Don't have full coverage.
                    return Query(_conn=self, _ranges=query_ranges), self._RANGE_NONE
                chosen_ranges.append(r)
                curr_top = r[1]
                continue

        if len(chosen_ranges) == 0:
            return Query(_conn=self, _ranges=query_ranges), self._RANGE_NONE

        q = self._build_range_query(prefix, chosen_ranges, query_ranges)
        if chosen_ranges[0][0] == begin and chosen_ranges[-1][1] == end:
            return q, self._RANGE_EXACT
        return q, self._RANGE_SUPERSET

    def _range_accel_query(self, field, begin, end, prefix, ranges,
                           conservative, query_ranges):
        """Construct a range acceleration query.

        Returns a 2-tuple containing:

         - a query consisting of a set of range terms approximating the range
           'begin' to 'end'.
         - One of _RANGE_EXACT, _RANGE_SUBSET, _RANGE_SUPERSET and _RANGE_NONE
           to indicate whether the returned query matches the range exactly,
           matches a (strict) subset of the range, or matches a (strict)
           superset of the range.

        If possible, an exact range will always be returned, with _RANGE_EXACT.

        Otherwise, if 'conservative' is False, an attempt to build a query
        which completely covers the specified range is performed.  If this
        succeeds, this query will be returned, with _RANGE_SUPERSET.

        If 'conservative' is True, or the attempt to cover the range fails, an
        attempt to build a query which matches as much as possible of the
        range, but is fully contained within the range, is performed, with
        _RANGE_SUBSET.

        If all these attempts fail (ie, the only query possible matching a
        subset of the range is the empty query), an empty query will be
        returned, together with _RANGE_NONE.

        `query_ranges` is a description of the slot number, start and end of
        the range search.  This is stored in a hidden attribute of the
        generated query, and used in relevant_data() to check if a document
        matches the range.

        """
        if begin is not None:
            begin = float(begin)
        if end is not None:
            end = float(end)

        if begin is None and end is None:
            # No range restriction - return a match-all query, with
            # RANGE_EXACT.
            return Query(xapian.Query(''), _conn=self,
                         _serialised=self._make_parent_func_repr("query_all"),
                         _ranges=query_ranges) * 0, self._RANGE_EXACT

        if conservative:
            return self._build_range_query_cons(prefix, begin, end,
                                                ranges, query_ranges)
        else:
            q, q_type = self._build_range_query_noncons(prefix, begin, end,
                                                        ranges, query_ranges)
            if q_type == self._RANGE_NONE:
                return self._build_range_query_cons(prefix, begin, end,
                                                    ranges, query_ranges)
            return q * 0, q_type

    def _get_approx_params(self, field, action):
        try:
            action_params = self._field_actions[field]._actions[action][0]
        except KeyError:
            return None, None
        ranges = action_params.get('ranges')
        if ranges is None:
            return None, None
        try:
            range_accel_prefix = action_params['_range_accel_prefix']
        except KeyError:
            raise errors.SearchError("Internal xappy error, no _range_accel prefix for field: " + field)
        return ranges, range_accel_prefix

    def _make_parent_func_repr(self, funcname):
        """Make a python string representing the call to the parent function.

        """
        funcobj = getattr(SearchConnection, funcname)
        frame = inspect.currentframe().f_back
        try:
            argnames, varargsname, varkwname, defaultargs = inspect.getargspec(funcobj)
            values = frame.f_locals
            assert varargsname is None # Don't support *args parameter
            assert varkwname is None # Don't support **kwargs parameter
            if defaultargs is None:
                defaultargs = ()
            args = []
            if len(defaultargs) == 0:
                for argname in argnames[1:]:
                    args.append(repr(values[argname]))
            else:
                for argname in argnames[1:-len(defaultargs)]:
                    args.append(repr(values[argname]))
                for i, argname in enumerate(argnames[-len(defaultargs):]):
                    val = values[argname]
                    if val != defaultargs[i]:
                        args.append("%s=%r" % (argname, val))
            return "conn.%s(%s)" % (funcname, ', '.join(args))
        finally:
            del frame

    def query_range(self, field, begin, end, approx=False,
                    conservative=False, accelerate=True):
        """Create a query for a range search.

        This creates a query which matches only those documents which have a
        field value in the specified range.

        Begin and end must be appropriate values for the field, according to
        the 'type' parameter supplied to the SORTABLE action for the field.

        The begin and end values are both inclusive - any documents with a
        value equal to begin or end will be returned (unless end is less than
        begin, in which case no documents will be returned).

        Begin or end may be set to None in order to create an open-ended
        range.  (They may also both be set to None, which will generate a query
        which matches all documents containing any value for the field.)

        If the 'approx' parameter is true then a query that uses the 'ranges'
        for the field is returned.  The accuracy of the results returned by such
        a query depends on the ranges supplied when the field action was
        defined.  It is an error to set 'approx' to true if no 'ranges' were
        specified at indexing time.

        The 'conservative' parameter controls what kind of approximation is
        attempted - if True, the approximation will only return items which are
        within the range (but may fail to return other items which are within
        the range).  If False, the approximation will always include all items
        which are within the range, but may also return others which are
        outside the range.

        The 'accelerate' parameter is used only if approx is False.  If true,
        the resulting query will be an exact range search, but will attempt to
        use the range terms to perform the search faster.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")

        ranges, range_accel_prefix = \
            self._get_approx_params(field, FieldActions.SORT_AND_COLLAPSE)
        if ranges is None:
            ranges, range_accel_prefix = \
                self._get_approx_params(field, FieldActions.FACET)

        serialised = self._make_parent_func_repr("query_range")
        try:
            slot = self._field_mappings.get_slot(field, 'collsort')
        except KeyError:
            # Return a "match nothing" query
            return Query(xapian.Query(), _conn=self,
                         _serialised=serialised)

        if begin is None and end is None:
            # Return a query which matches everything with a non-empty value in
            # the slot.

            # FIXME - this can probably be done more efficiently when streamed
            # values are stored in the database, but I don't think Xapian
            # exposes a useful interface for this currently.
            return Query(xapian.Query(xapian.Query.OP_VALUE_GE, slot, '\x00'),
                         _conn=self, _serialised=serialised,
                         _ranges=((slot, None, None),))

        sorttype = self._get_sort_type(field)
        marshaller = SortableMarshaller(False)
        fn = marshaller.get_marshall_function(field, sorttype)

        if begin is not None:
            marshalled_begin = fn(field, begin)
        else:
            marshalled_begin = None
        if end is not None:
            marshalled_end = fn(field, end)
        else:
            marshalled_end = None

        # Parameter to supply to query constructor describing the ranges
        # that this query is searching for.
        query_ranges = ((slot, marshalled_begin, marshalled_end),)


        if approx:
            if ranges is None:
                errors.SearchError("Cannot do approximate range search on fields with no ranges")

            # Note:  The constituent terms of the _range_accel_query() result
            # always have wdf equal to 0.  However, Xapian doesn't know this,
            # so we multiply the result of this query by 0, to let Xapian know
            # that it never returns a weight other than 0.  This allows Xapian
            # to apply boolean-specific optimisations.
            accel_query, accel_type = \
                self._range_accel_query(field, begin, end, range_accel_prefix,
                                        ranges, conservative, query_ranges)
            accel_query._set_serialised(serialised)
            return accel_query

        if accelerate and ranges is not None:
            accel_query, accel_type = \
                self._range_accel_query(field, begin, end, range_accel_prefix,
                                        ranges, conservative, query_ranges)
        else:
            accel_type = self._RANGE_NONE

        if accel_type == self._RANGE_EXACT:
            accel_query._set_serialised(serialised)
            return accel_query

        if marshalled_begin is None:
            result = Query(xapian.Query(xapian.Query.OP_VALUE_LE, slot,
                                         marshalled_end),
                           _conn=self, _ranges=query_ranges)
        elif marshalled_end is None:
            result = Query(xapian.Query(xapian.Query.OP_VALUE_GE, slot,
                                         marshalled_begin),
                           _conn=self, _ranges=query_ranges)
        else:
            result = Query(xapian.Query(xapian.Query.OP_VALUE_RANGE, slot,
                                         marshalled_begin, marshalled_end),
                           _conn=self, _ranges=query_ranges)

        if accel_type == self._RANGE_SUBSET:
            result = accel_query | result
        if accel_type == self._RANGE_SUPERSET:
            result = accel_query & result

        # As before - multiply result weights by 0 to help Xapian optimise.
        result = result * 0

        result._set_serialised(serialised)
        return result

    def _difference_accel_query(self, ranges, prefix, val, difference_func, num):
        """ Create a query for differences using range acceleration terms.

        """
        scales_and_ranges = []
        inf = float('inf')

        for (low_val, hi_val) in ranges:
            mid = (low_val + hi_val) / 2
            difference = difference_func(val, mid)
            if difference >= 0 and abs(difference) != inf:
                scale = 1.0 / (difference + 1.0)
                scales_and_ranges.append((scale, low_val, hi_val))

        if num is not None:
            ordered = sorted(scales_and_ranges,
                             key=lambda x:x[0],
                             reverse=True)
            scales_and_ranges = itertools.islice(ordered, 0, num)

            scales_and_ranges = list(scales_and_ranges)

        def make_query(scale, low_val, hi_val):
            term = convert_range_to_term(prefix, low_val, hi_val)
            postingsource = xapian.FixedWeightPostingSource(scale)
            fixedwt_query = Query(xapian.Query(postingsource),
                           _refs=[postingsource], _conn=self)
            return fixedwt_query.filter(Query(xapian.Query(term), _conn = self))


        queries = [make_query(scale, low_val, hi_val) for
                   scale, low_val, hi_val in scales_and_ranges]

        return Query.compose(xapian.Query.OP_OR, queries)

    def query_difference(self, field, val, purpose, approx=False, num=None,
                         difference_func="abs(x - y)"):
        """Create a query for a difference search.

        This creates a query that ranks documents according to the
        difference of values in fields from 'val'.

        'purpose' should be one of 'collsort' or 'facet'

        The 'difference_func' parameter is a string, holding a formula to use
        to compute the difference of the field's value from the 'val'
        parameter.  This formula should assume that the two values are passed
        to it as "x" and "y".  Negative differences are not differentiated
        amongst and signify that documents should not be included in the
        results. For approximate queries this might result in significant
        performance improvements (provided a number of ranges are excluded),
        whereas for exact searches it is still necessary to test each document.

        If the 'approx' parameter tests true, then the ranges for the
        field are used to approximate differences. This is less accurate
        but likely to be much faster. It is necessary that 'ranges'
        was specified for the field at indexing time. (This is
        therefore only available for float fields.) The documents are
        ranked according to the difference of 'val' from the midpoint of
        each range.

        The precision will depend on the granularity of the ranges -
        using 'approx' means that values within a given range are not
        differentiated. Smaller ranges will give higher precision, but
        slower queries. Note that using a 'difference_func' that cuts
        off far values by returning a negative number is likely to
        improve performance significantly when 'approx' is specified.

        The 'num' parameter limits the number of range specific
        subqueries to the value supplied. The first 'num' subqueries
        in order of importance are used. Small values of 'num' mean
        that values further from the 'val' will be effectively
        ignored.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        serialised = self._make_parent_func_repr("query_difference")

        actions_map = {'collsort': FieldActions.SORT_AND_COLLAPSE,
                       'facet': FieldActions.FACET}

        if approx:
            #accelerate with ranges.
            ranges, range_accel_prefix = \
                    self._get_approx_params(field, actions_map[purpose])
            if not ranges:
                errors.SearchError("Cannot do approximate difference search "
                                   "on fields with no ranges")
            if isinstance(difference_func, basestring):
                difference_func = eval('lambda x, y: ' + difference_func)
            result = self._difference_accel_query(ranges, range_accel_prefix,
                                                  val, difference_func, num)
            result._set_serialised(serialised)
            return result
        else:
            # not approx
            # NOTE - very slow: needs to be implemented in C++.
            if isinstance(difference_func, basestring):
                difference_func = eval('lambda x, y: ' + difference_func)
            class DifferenceWeight(ExternalWeightSource):
                " An exteral weighting source for differences"
                def get_maxweight(self):
                    return 1.0

                def get_weight(self, doc):
                    doc_val = xapian.sortable_unserialise(
                            doc.get_value(field, purpose))
                    difference = difference_func(val, doc_val)
                    return 1.0 / (abs(difference) + 1.0)

            result = self.query_external_weight(DifferenceWeight())
            result._set_serialised(serialised)
            return result

    @staticmethod
    def calc_distance(location1, location2):
        """Calculate the distance, in metres, between two points.

        `location1` and `location2` are the locations to measure the distance
        between.  They should each be a string holding a single latlong
        coordinate, or a list of strings holding latlong coordinates.

        The closest distance between a point in location1 and in location2 will
        be returned.

        """
        coords1 = xapian.LatLongCoords()
        if isinstance(location1, basestring):
            coords1.insert(xapian.LatLongCoord.parse_latlong(location1))
        else:
            for coord in location1:
                coords1.insert(xapian.LatLongCoord.parse_latlong(coord))

        coords2 = xapian.LatLongCoords()
        if isinstance(location2, basestring):
            coords2.insert(xapian.LatLongCoord.parse_latlong(location2))
        else:
            for coord in location2:
                coords2.insert(xapian.LatLongCoord.parse_latlong(coord))

        metric = xapian.GreatCircleMetric()
        return metric(coords1, coords2)

    def query_distance(self, field, centre, max_range=0.0, k1=1000.0, k2=1.0):
        """Create a query which returns documents in order of distance.

        `field` is the field to get coordinates from, and must have been
        indexed with the GEOSPATIAL field action.

        `centre` is the center of the search - it may either be a string
        holding a latlong pair, or an iterable of strings containing latlong
        pairs.  If multiple points are specified, the closest distance from one
        of these points to the coordinates stored in the document will be used
        for the search.

        `max_range` is the maximum range, in metres, to use in the search: no
        items at a greater distance than this will be returned.

        `k1` and `k2` control how the weights varies with distance.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")

        serialised = self._make_parent_func_repr("query_distance")

        metric = xapian.GreatCircleMetric()

        # Build the list of coordinates
        coords = xapian.LatLongCoords()
        if isinstance(centre, basestring):
            coords.insert(xapian.LatLongCoord.parse_latlong(centre))
        else:
            for coord in centre:
                coords.insert(xapian.LatLongCoord.parse_latlong(coord))

        # Get the slot
        try:
            slot = self._field_mappings.get_slot(field, 'loc')
        except KeyError:
            # Return a "match nothing" query
            return Query(xapian.Query(), _conn=self,
                         _serialised=serialised)

        # Make the posting source
        postingsource = xapian.LatLongDistancePostingSource(
            slot, coords, metric, max_range, k1, k2)

        result = Query(xapian.Query(postingsource),
                       _refs=[postingsource, coords, metric],
                       _conn=self)
        result._set_serialised(serialised)
        return result

    def query_image_similarity(self, field, image=None, docid=None, xapid=None):
        """Create an image similarity query.
        
        This query returns documents in order of similarity to the supplied
        image.

        `field` is the field to get image similarity data from and must have
        been indexed with the IMGSEEK field action.

        Exactly one of `image`, `docid`, `xapid` must be supplied, to indicate the
        target of the similarity search.
        
         - If `image` is supplied, it should be the path to an image file.
         - If `docid` is supplied, it should be a document ID in the database.
         - If `xapid` is supplied, it should be the xapian document ID in the
           database (as would be supplied to get_document()).

        If multiple images are referenced by the specified field in the target
        document or searched documents, the best match is used.

        """
        serialised = self._make_parent_func_repr("query_image_similarity")
        import xapian.imgseek

        if len(filter(lambda x: x is not None, (image, docid, xapid))) != 1:
            raise errors.SearchError(
                "Exactly one of image, docid or xapid is required for"
                " query_image_similarity().")

        actions =  self._field_actions[field]._actions
        terms = actions[FieldActions.IMGSEEK][0]['terms']
        if image:
            # Build a signature from an image.
            try:
                sig = xapian.imgseek.ImgSig.register_Image(image)
            except xapian.InvalidArgumentError:
                raise errors.SearchError(
                    'Invalid or unsupported image file passed to '
                    'query_image_similarity(): ' + image)
            if terms:
                imgterms = _get_imgterms(self, field)
                return Query(imgterms.querySimilarSig(sig), _conn=self)
            else:
                sigs = xapian.imgseek.ImgSigs(sig)

        else:
            # Build a signature from a stored document.
            doc = self.get_document(docid=docid, xapid=xapid)
            if terms:
                imgterms = _get_imgterms(self, field)
                return Query(imgterms.querySimilarDoc(doc._doc),
                             _conn = self)
            else:
                val = doc.get_value(field, 'imgseek')
                sigs = xapian.imgseek.ImgSigs.unserialise(val)

        try:
            slot = self._field_mappings.get_slot(field, 'imgseek')
        except KeyError:
            return Query(xapian.Query(), _conn=self,
                         _serialised=serialised)

        ps = xapian.imgseek.ImgSigSimilarityPostingSource(sigs, slot)
        result = Query(xapian.Query(ps),
                       _refs=[ps],
                       _conn=self)
        return result

    def query_facet(self, field, val, approx=False,
                    conservative=True, accelerate=True):
        """Create a query for a facet value.

        This creates a query which matches only those documents which have a
        facet value in the specified range.

        For a numeric range facet, val should be a tuple holding the start and
        end of the range, or a comma separated string holding two floating
        point values.  For other facets, val should be the value to look
        for.

        The start and end values are both inclusive - any documents with a
        value equal to start or end will be returned (unless end is less than
        start, in which case no documents will be returned).

        If the 'approx' parameter is true then a query that uses the 'ranges'
        for the field is returned.  The accuracy of the results returned by such
        a query depends on the ranges supplied when the field action was
        defined.  It is an error to set 'approx' to true if no 'ranges' were
        specified at indexing time.

        The 'conservative' parameter is used only if approx is True - if True,
        the approximation will only return items which are within the range
        (but may fail to return other items which are within the range).  If
        False, the approximation will always include all items which are within
        the range, but may also return others which are outside the range.

        The 'accelerate' parameter is used only if approx is False.  If true,
        the resulting query will be an exact range search, but will attempt to
        use the range terms to perform the search faster.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        if 'facets' in _checkxapian.missing_features:
            raise errors.SearchError("Facets unsupported with this release of xapian")

        serialised = self._make_parent_func_repr("query_facet")
        try:
            actions = self._field_actions[field]._actions
        except KeyError:
            actions = {}
        facettype = None
        for action, kwargslist in actions.iteritems():
            if action == FieldActions.FACET:
                for kwargs in kwargslist:
                    facettype = kwargs.get('type', None)
                    if facettype is not None:
                        break
            if facettype is not None:
                break

        if facettype == 'float':
            if isinstance(val, basestring):
                val = [float(v) for v in val.split(',', 2)]
            assert(len(val) == 2)
            try:
                slot = self._field_mappings.get_slot(field, 'facet')
            except KeyError:
                return Query(xapian.Query(), _conn=self,
                             _serialised=serialised)

            # FIXME - check that sorttype == self._get_sort_type(field)
            sorttype = 'float'
            marshaller = SortableMarshaller(False)
            fn = marshaller.get_marshall_function(field, sorttype)
            marshalled_begin = fn(field, val[0])
            marshalled_end = fn(field, val[1])

            query_ranges = ((slot, marshalled_begin, marshalled_end),)
            ranges, range_accel_prefix = \
                self._get_approx_params(field, FieldActions.FACET)
            if ranges is None:
                ranges, range_accel_prefix = \
                    self._get_approx_params(field, FieldActions.SORT_AND_COLLAPSE)
            if approx:
                if ranges is None:
                    raise errors.SearchError("Cannot do approximate range search on fields with no ranges")
                accel_query, accel_type = \
                    self._range_accel_query(field, val[0], val[1],
                                            range_accel_prefix, ranges,
                                            conservative, query_ranges)
                accel_query._set_serialised(serialised)
                return accel_query

            if accelerate and ranges is not None:
                accel_query, accel_type = \
                    self._range_accel_query(field, val[0], val[1],
                                            range_accel_prefix,
                                            ranges, conservative,
                                            query_ranges)
            else:
                accel_type = self._RANGE_NONE

            if accel_type == self._RANGE_EXACT:
                accel_query._set_serialised(serialised)
                return accel_query

            result = Query(xapian.Query(xapian.Query.OP_VALUE_RANGE, slot,
                                         marshalled_begin, marshalled_end),
                           _conn=self, _ranges=query_ranges)

            if accel_type == self._RANGE_SUBSET:
                result = accel_query | result
            if accel_type == self._RANGE_SUPERSET:
                result = accel_query & result

            result = result * 0
            result._set_serialised(serialised)
            return result
        else:
            assert(facettype == 'string' or facettype is None)
            prefix = self._field_mappings.get_prefix(field)
            result = Query(xapian.Query(prefix + val.lower()), _conn=self) * 0
            result._set_serialised(serialised)
            return result

    def _prepare_queryparser(self, allow, deny, default_op, default_allow,
                             default_deny):
        """Prepare (and return) a query parser using the specified fields and
        operator.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")

        if isinstance(allow, basestring):
            allow = (allow, )
        if isinstance(deny, basestring):
            deny = (deny, )
        if allow is not None and len(allow) == 0:
            allow = None
        if deny is not None and len(deny) == 0:
            deny = None
        if allow is not None and deny is not None:
            raise errors.SearchError("Cannot specify both `allow` and `deny` "
                                      "(got %r and %r)" % (allow, deny))

        if isinstance(default_allow, basestring):
            default_allow = (default_allow, )
        if isinstance(default_deny, basestring):
            default_deny = (default_deny, )
        if default_allow is not None and len(default_allow) == 0:
            default_allow = None
        if default_deny is not None and len(default_deny) == 0:
            default_deny = None
        if default_allow is not None and default_deny is not None:
            raise errors.SearchError("Cannot specify both `default_allow` and `default_deny` "
                                      "(got %r and %r)" % (default_allow, default_deny))

        qp = xapian.QueryParser()
        qp.set_database(self._index)
        qp.set_default_op(default_op)

        if allow is None:
            allow = [key for key in self._field_actions]
        if deny is not None:
            allow = [key for key in allow if key not in deny]

        for field in allow:
            try:
                actions = self._field_actions[field]._actions
            except KeyError:
                actions = {}
            for action, kwargslist in actions.iteritems():
                if action == FieldActions.INDEX_EXACT:
                    # FIXME - need patched version of xapian to add exact prefixes
                    #qp.add_exact_prefix(field, self._field_mappings.get_prefix(field))
                    qp.add_prefix(field, self._field_mappings.get_prefix(field))
                if action == FieldActions.INDEX_FREETEXT:
                    allow_field_specific = True
                    for kwargs in kwargslist:
                        allow_field_specific = allow_field_specific or kwargs.get('allow_field_specific', True)
                    if not allow_field_specific:
                        continue
                    qp.add_prefix(field, self._field_mappings.get_prefix(field))
                    for kwargs in kwargslist:
                        try:
                            lang = kwargs['language']
                            my_stemmer = xapian.Stem(lang)
                            qp.my_stemmer = my_stemmer
                            qp.set_stemmer(my_stemmer)
                            qp.set_stemming_strategy(qp.STEM_SOME)
                        except KeyError:
                            pass

        if default_allow is not None or default_deny is not None:
            if default_allow is None:
                default_allow = [key for key in self._field_actions]
            if default_deny is not None:
                default_allow = [key for key in default_allow if key not in default_deny]
            for field in default_allow:
                try:
                    actions = self._field_actions[field]._actions
                except KeyError:
                    actions = {}
                for action, kwargslist in actions.iteritems():
                    if action == FieldActions.INDEX_FREETEXT:
                        qp.add_prefix('', self._field_mappings.get_prefix(field))
                        # FIXME - set stemming options for the default prefix

        return qp

    def _query_parse_with_prefix(self, qp, string, flags, prefix):
        """Parse a query, with an optional prefix.

        """
        if prefix is None:
            return qp.parse_query(string, flags)
        else:
            return qp.parse_query(string, flags, prefix)

    def _query_parse_with_fallback(self, qp, string, allow_wildcards,
                                   prefix=None):
        """Parse a query with various flags.

        If the initial boolean pass fails, fall back to not using boolean
        operators.

        """
        base_flags = self._qp_flags_base
        if allow_wildcards:
            base_flags |= self._qp_flags_wildcard 
        try:
            q1 = self._query_parse_with_prefix(qp, string,
                                               base_flags |
                                               self._qp_flags_phrase |
                                               self._qp_flags_synonym |
                                               self._qp_flags_bool,
                                               prefix)
        except xapian.QueryParserError, e:
            # If we got a parse error, retry without boolean operators (since
            # these are the usual cause of the parse error).
            q1 = self._query_parse_with_prefix(qp, string,
                                               base_flags |
                                               self._qp_flags_phrase |
                                               self._qp_flags_synonym,
                                               prefix)

        qp.set_stemming_strategy(qp.STEM_NONE)
        try:
            q2 = self._query_parse_with_prefix(qp, string,
                                               base_flags |
                                               self._qp_flags_bool,
                                               prefix)
        except xapian.QueryParserError, e:
            # If we got a parse error, retry without boolean operators (since
            # these are the usual cause of the parse error).
            q2 = self._query_parse_with_prefix(qp, string, base_flags, prefix)

        return Query(xapian.Query(xapian.Query.OP_AND_MAYBE, q1, q2),
                     _conn=self)

    def query_parse(self, string, allow=None, deny=None, default_op=OP_AND,
                    default_allow=None, default_deny=None,
                    allow_wildcards=False):
        """Parse a query string.

        This is intended for parsing queries entered by a user.  If you wish to
        combine structured queries, it is generally better to use the other
        query building methods, such as `query_composite` (though you may wish
        to create parts of the query to combine with such methods with this
        method).

        The string passed to this method can have various operators in it.  In
        particular, it may contain field specifiers (ie, field names, followed
        by a colon, followed by some text to search for in that field).  For
        example, if "author" is a field in the database, the search string
        could contain "author:richard", and this would be interpreted as
        "search for richard in the author field".  By default, any fields in
        the database which are indexed with INDEX_EXACT or INDEX_FREETEXT will
        be available for field specific searching in this way - however, this
        can be modified using the "allow" or "deny" parameters, and also by the
        allow_field_specific tag on INDEX_FREETEXT fields.

        Any text which isn't prefixed by a field specifier is used to search
        the "default set" of fields.  By default, this is the full set of
        fields in the database which are indexed with INDEX_FREETEXT and for
        which the search_by_default flag set (ie, if the text is found in any
        of those fields, the query will match).  However, this may be modified
        with the "default_allow" and "default_deny" parameters.  (Note that
        fields which are indexed with INDEX_EXACT aren't allowed to be used in
        the default list of fields.)

        - `string`: The string to parse.
        - `allow`: A list of fields to allow in the query.
        - `deny`: A list of fields not to allow in the query.
        - `default_op`: The default operator to combine query terms with.
        - `default_allow`: A list of fields to search for by default.
        - `default_deny`: A list of fields not to search for by default.

        Only one of `allow` and `deny` may be specified.

        Only one of `default_allow` and `default_deny` may be specified.

        If any of the entries in `allow` are not present in the configuration
        for the database, or are not specified for indexing (either as
        INDEX_EXACT or INDEX_FREETEXT), they will be ignored.  If any of the
        entries in `deny` are not present in the configuration for the
        database, they will be ignored.

        Returns a Query object, which may be passed to the search() method, or
        combined with other queries.

        """
        qp = self._prepare_queryparser(allow, deny, default_op, default_allow,
                                       default_deny)
        result = self._query_parse_with_fallback(qp, string, allow_wildcards)
        serialised = self._make_parent_func_repr("query_parse")
        result._set_serialised(serialised)
        return result

    def query_field(self, field, value=None, default_op=OP_AND,
                    allow_wildcards=False):
        """A query for a single field.

        If field is an exact field or a facet, the resulting query will return
        only those documents which have the exact value supplied in the `value`
        parameter in the field.

        If field is a freetext field, the resulting query will return documents
        with field contents relevant to the text supplied in the `value`
        parameter.

        If field is a weight field, the value parameter will be ignored.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        try:
            actions = self._field_actions[field]._actions
        except KeyError:
            actions = {}
        serialised = self._make_parent_func_repr("query_field")

        # need to check on field type, and stem / split as appropriate
        for action, kwargslist in actions.iteritems():
            if action in (FieldActions.INDEX_EXACT,
                          FieldActions.FACET,):
                if value is None:
                    raise errors.SearchError("Supplied value must not be None")
                prefix = self._field_mappings.get_prefix(field)
                if len(value) > 0:
                    chval = ord(value[0])
                    if chval >= ord('A') and chval <= ord('Z'):
                        prefix = prefix + ':'
                # WDF of INDEX_EXACT or FACET terms is always 0, so the
                # weight of such terms is also always zero.  However, Xapian
                # doesn't know this, so can't take advantage of the fact when
                # performing its optimisations.  We multiply the weight by 0 to
                # make Xapian know that the weight is always zero.  This means
                # that Xapian won't bother to ask the query for weights, and
                # can optimise in various ways.
                result = Query(xapian.Query(prefix + value), _conn=self) * 0
                result._set_serialised(serialised)
                return result
            if action == FieldActions.INDEX_FREETEXT:
                if value is None:
                    raise errors.SearchError("Supplied value must not be None")
                qp = xapian.QueryParser()
                qp.set_default_op(default_op)
                prefix = self._field_mappings.get_prefix(field)
                for kwargs in kwargslist:
                    try:
                        lang = kwargs['language']
                        qp.set_stemmer(xapian.Stem(lang))
                        qp.set_stemming_strategy(qp.STEM_SOME)
                    except KeyError:
                        pass
                result = self._query_parse_with_fallback(qp, value,
                                                         allow_wildcards,
                                                         prefix)
                result._set_serialised(serialised)
                return result
            if action == FieldActions.WEIGHT:
                if value is not None:
                    raise errors.SearchError("Value supplied for a WEIGHT field must be None")
                slot = self._field_mappings.get_slot(field, 'weight')
                postingsource = xapian.ValueWeightPostingSource(slot)
                result = Query(xapian.Query(postingsource),
                               _refs=[postingsource], _conn=self)
                result._set_serialised(serialised)
                return result

        return Query(_conn=self, _serialised=serialised)

    def query_similar(self, ids, allow=None, deny=None, simterms=10):
        """Get a query which returns documents which are similar to others.

        The list of document IDs to base the similarity search on is given in
        `ids`.  This should be an iterable, holding a list of strings.  If
        any of the supplied IDs cannot be found in the database, they will be
        ignored.  (If no IDs can be found in the database, the resulting query
        will not match any documents.)

        By default, all fields which have been indexed for freetext searching
        will be used for the similarity calculation.  The list of fields used
        for this can be customised using the `allow` and `deny` parameters
        (only one of which may be specified):

        - `allow`: A list of fields to base the similarity calculation on.
        - `deny`: A list of fields not to base the similarity calculation on.
        - `simterms`: Number of terms to use for the similarity calculation.

        For convenience, any of `ids`, `allow`, or `deny` may be strings, which
        will be treated the same as a list of length 1.

        Regardless of the setting of `allow` and `deny`, only fields which have
        been indexed for freetext searching will be used for the similarity
        measure - all other fields will always be ignored for this purpose.

        """
        eterms, prefixes = self._get_eterms(ids, allow, deny, simterms)
        return self._query_elite_set_from_raw_terms(eterms, simterms)

    def _query_elite_set_from_raw_terms(self, xapterms, numterms=10):
        """Build a query from an operator and a list of Xapian term strings.

        This interface exposes raw xapian terms, which are affected by the
        method by which prefixes are mapped to fields, which in turn is likely
        to change in future, so shouldn't be used by external code unless such
        code is willing to be broken by future releases of Xappy.

        """
        serialised = self._make_parent_func_repr("_query_elite_set_from_raw_terms")

        # Use the "elite set" operator, which chooses the terms with the
        # highest query weight to use.
        q = xapian.Query(xapian.Query.OP_ELITE_SET, xapterms, numterms)
        return Query(q, _conn=self, _serialised=serialised)

    def significant_terms(self, ids, maxterms=10, allow=None, deny=None):
        """Get a set of "significant" terms for a document, or documents.

        This has a similar interface to query_similar(): it takes a list of
        ids, and an optional specification of a set of fields to consider.
        Instead of returning a query, it returns a list of terms from the
        document (or documents), which appear "significant".  Roughly,
        in this situation significant means that the terms occur more
        frequently in the specified document than in the rest of the corpus.

        The list is in decreasing order of "significance".

        By default, all terms related to fields which have been indexed for
        freetext searching will be considered for the list of significant
        terms.  The list of fields used for this can be customised using the
        `allow` and `deny` parameters (only one of which may be specified):

        - `allow`: A list of fields to consider.
        - `deny`: A list of fields not to consider.

        For convenience, any of `ids`, `allow`, or `deny` may be strings, which
        will be treated the same as a list of length 1.

        Regardless of the setting of `allow` and `deny`, only fields which have
        been indexed for freetext searching will be considered - all other
        fields will always be ignored for this purpose.

        The maximum number of terms to return may be specified by the maxterms
        parameter.

        """
        eterms, prefixes = self._get_eterms(ids, allow, deny, maxterms)
        terms = []
        for term in eterms:
            pos = 0
            for char in term:
                if not char.isupper():
                    break
                pos += 1
            field = prefixes[term[:pos]]
            value = term[pos:]
            terms.append((field, value))
        return terms

    def _get_eterms(self, ids, allow, deny, simterms):
        """Get a set of terms for an expand.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        if allow is not None and deny is not None:
            raise errors.SearchError("Cannot specify both `allow` and `deny`")

        if isinstance(ids, (basestring, ProcessedDocument, UnprocessedDocument)):
            ids = (ids, )
        if isinstance(allow, basestring):
            allow = (allow, )
        if isinstance(deny, basestring):
            deny = (deny, )

        # Set "allow" to contain a list of all the fields to use.
        if allow is None:
            allow = [key for key in self._field_actions]
        if deny is not None:
            allow = [key for key in allow if key not in deny]

        # Set "prefixes" to contain a list of all the prefixes to use.
        prefixes = {}
        for field in allow:
            try:
                actions = self._field_actions[field]._actions
            except KeyError:
                actions = {}
            for action, kwargslist in actions.iteritems():
                if action == FieldActions.INDEX_FREETEXT:
                    prefixes[self._field_mappings.get_prefix(field)] = field

        # Handle any documents in the list of ids, by indexing them to a
        # temporary inmemory database, and using the generated id instead.
        tempdb = None
        next_docid = self._next_docid
        newids = []
        for doc in ids:
            if isinstance(doc, UnprocessedDocument):
                doc = self.process(doc)
            if isinstance(doc, ProcessedDocument):
                if tempdb is None:
                    tempdb = xapian.inmemory_open()
                # Store the docid (so that we don't alter the processed
                # document passed to us) then allocate an unused docid to go in
                # the temporary database.
                orig_docid = doc.id
                temp_docid, next_docid = _allocate_id(self._index, next_docid)
                doc.id = temp_docid

                # Add the document to the temporary database, and then reset
                # its docid.
                try:
                    doc.prepare()
                    tempdb.add_document(doc._doc)
                finally:
                    doc.id = orig_docid
                newids.append(temp_docid)
            else:
                newids.append(doc)
        ids = newids

        # Repeat the expand until we don't get a DatabaseModifiedError
        while True:
            try:
                eterms = self._perform_expand(ids, prefixes, simterms, tempdb)
                break;
            except xapian.DatabaseModifiedError, e:
                self.reopen()
        return eterms, prefixes

    class _ExpandDecider(xapian.ExpandDecider):
        def __init__(self, prefixes):
            xapian.ExpandDecider.__init__(self)
            self._prefixes = prefixes

        def __call__(self, term):
            pos = 0
            for char in term:
                if not char.isupper():
                    break
                pos += 1
            if term[:pos] in self._prefixes:
                return True
            return False

    def _perform_expand(self, ids, prefixes, simterms, tempdb):
        """Perform an expand operation to get the terms for a similarity
        search, given a set of ids (and a set of prefixes to restrict the
        similarity operation to).

        """
        # Set idquery to be a query which returns the documents listed in
        # "ids".
        idquery = xapian.Query(xapian.Query.OP_OR, ['Q' + id for id in ids])

        if tempdb is not None:
            combined_db = xapian.Database()
            combined_db.add_database(self._index)
            combined_db.add_database(tempdb)
        else:
            combined_db = self._index
        enq = xapian.Enquire(combined_db)
        enq.set_query(idquery)
        rset = xapian.RSet()
        for id in ids:
            # Note: might be more efficient to make a single postlist and
            # use skip_to() on it.  Note that this will require "ids" to be in
            # (binary, lexicographical) sorted order, though.
            pl = combined_db.postlist('Q' + id)
            try:
                xapid = pl.next()
                rset.add_document(xapid.docid)
            except StopIteration:
                pass

        expanddecider = self._ExpandDecider(prefixes)
        # The USE_EXACT_TERMFREQ gets the term frequencies from the combined
        # database, not from the database which the relevant document is found
        # in.  This has a performance penalty, but this should be minimal in
        # our case, where we only have at most two databases, one of which is
        # an inmemory database.
        eset = enq.get_eset(simterms, rset, xapian.Enquire.USE_EXACT_TERMFREQ,
                            1.0, expanddecider)
        return [term.term for term in eset]

    def query_external_weight(self, source):
        """A query which uses an external source of weighting information.

        The external source should be an instance of ExternalWeightSource.

        Note that this type of query will be fairly slow - it involves a
        callback to Python for every document considered, and also a lookup of
        the document ID for each of these documents.  Usually, the weights
        should simply be stored in the database, in a "weight" field.  However,
        this method can be useful for small databases where the slowness
        doesn't matter too much, or for experimenting with new weight schemes
        offline before indexing them.

        """
        serialised = self._make_parent_func_repr("query_external_weight")
        class ExternalWeightPostingSource(xapian.PostingSource):
            """A xapian posting source reading from an ExternalWeightSource.

            """
            def __init__(self, conn, wtsource):
                xapian.PostingSource.__init__(self)
                self.conn = conn
                self.wtsource = wtsource

            def init(self, xapdb):
                self.alldocs = xapdb.postlist('')

            def reset(self, xapdb):
                # backwards compatibility
                self.init(xapdb)

            def get_termfreq_min(self): return 0
            def get_termfreq_est(self): return self.conn._index.get_doccount()
            def get_termfreq_max(self): return self.conn._index.get_doccount()

            def next(self, minweight):
                try:
                    self.current = self.alldocs.next()
                except StopIteration:
                    self.current = None

            def skip_to(self, docid, minweight):
                try:
                    self.current = self.alldocs.skip_to(docid)
                except StopIteration:
                    self.current = None

            def at_end(self):
                return self.current is None

            def get_docid(self):
                return self.current.docid

            def get_maxweight(self):
                return self.wtsource.get_maxweight()

            def get_weight(self):
                xapdoc = self.conn._index.get_document(self.current.docid)
                doc = ProcessedDocument(self.conn._field_mappings, xapdoc)
                return self.wtsource.get_weight(doc)

        postingsource = ExternalWeightPostingSource(self, source)
        return Query(xapian.Query(postingsource),
                     _refs=[postingsource], _conn=self, _serialised=serialised)

    def query_all(self, weight=None):
        """A query which matches all the documents in the database.

        Such a query will normally return a weight of 0 for each document.
        However, it can be made to return a specific, fixed, weight by passing
        in a `weight` parameter.

        """
        serialised = self._make_parent_func_repr("query_all")
        all_query = Query(xapian.Query(''), _conn=self,
                          _serialised = serialised)
        if weight is not None and weight > 0:
            postingsource = xapian.FixedWeightPostingSource(weight)
            fixedwt_query = Query(xapian.Query(postingsource),
                           _refs=[postingsource], _conn=self)
            result = fixedwt_query.filter(all_query)
            result._set_serialised(serialised)
            return result
        return all_query

    def query_none(self):
        """A query which matches no documents in the database.

        This may be useful as a placeholder in various situations.

        """
        return Query(_conn=self,
                     _serialised = self._make_parent_func_repr("query_none"))

    def query_id(self, docid):
        """A query which matches documents with the specified ids.

        `docid` contains the xappy document ID to search for.  It may be a
        single document ID, or an iterator returning a list of IDs.  In the
        latter case, documents with any of the IDs listed will be returned.

        Note that it is not recommended to use a large number of document IDs
        (for example, over 100) with this method, since it will not produce a
        particularly efficient query.

        """
        if isinstance(docid, basestring):
            terms = ['Q' + docid]
        else:
            terms = ['Q' + docid for docid in docid]

        return Query(xapian.Query(xapian.Query.OP_OR, terms),
                     _conn=self,
                     _serialised = self._make_parent_func_repr("query_id"))

    def query_from_evalable(self, serialised):
        """Create a query from an serialised evalable repr string.

        Note that this works by calling eval on the string, so should only be
        used if the string is from a trusted source.  If an attacker could set
        the string, he could execute arbitrary code.

        Queries can be serialised into a form suitable to be passed to this
        method using the xappy.Query.evalable_repr() method.

        """
        import xappy
        vars = {'conn': self, 'xappy': xappy, 'xapian': xapian,
                'Query': xappy.Query}
        return eval(serialised, vars)

    def spell_correct(self, querystr, allow=None, deny=None, default_op=OP_AND,
                      default_allow=None, default_deny=None,
                      allow_wildcards=False):
        """Correct a query spelling.

        This returns a version of the query string with any misspelt words
        corrected.

        - `allow`: A list of fields to allow in the query.
        - `deny`: A list of fields not to allow in the query.
        - `default_op`: The default operator to combine query terms with.
        - `default_allow`: A list of fields to search for by default.
        - `default_deny`: A list of fields not to search for by default.

        Only one of `allow` and `deny` may be specified.

        Only one of `default_allow` and `default_deny` may be specified.

        If any of the entries in `allow` are not present in the configuration
        for the database, or are not specified for indexing (either as
        INDEX_EXACT or INDEX_FREETEXT), they will be ignored.  If any of the
        entries in `deny` are not present in the configuration for the
        database, they will be ignored.

        Note that it is possible that the resulting spell-corrected query will
        still match no documents - the user should usually check that some
        documents are matched by the corrected query before suggesting it to
        users.

        """
        qp = self._prepare_queryparser(allow, deny, default_op, default_allow,
                                       default_deny)
        base_flags = (self._qp_flags_base |
                      self._qp_flags_phrase |
                      self._qp_flags_synonym)
        if allow_wildcards:
            base_flags |= self._qp_flags_wildcard 
        try:
            qp.parse_query(querystr,
                           base_flags |
                           self._qp_flags_bool |
                           qp.FLAG_SPELLING_CORRECTION)
        except xapian.QueryParserError:
            qp.parse_query(querystr,
                           base_flags |
                           qp.FLAG_SPELLING_CORRECTION)
        corrected = qp.get_corrected_query_string()
        if len(corrected) == 0:
            if isinstance(querystr, unicode):
                # Encode as UTF-8 for consistency - this happens automatically
                # to values passed to Xapian.
                return querystr.encode('utf-8')
            return querystr
        return corrected

    def can_collapse_on(self, field):
        """Check if this database supports collapsing on a specified field.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        try:
            self._field_mappings.get_slot(field, 'collsort')
        except KeyError:
            return False
        return True

    def can_sort_on(self, field):
        """Check if this database supports sorting on a specified field.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        try:
            self._field_mappings.get_slot(field, 'collsort')
        except KeyError:
            return False
        return True

    def _get_prefix_from_term(self, term):
        """Get the prefix of a term.

        Prefixes are any initial capital letters, with the exception that R always
        ends a prefix, even if followed by capital letters.

        """
        for p in xrange(len(term)):
            if not term[p].isupper():
                return term[:p]
            elif term[p] == 'R':
                return term[:p+1]
        return term

    def _facet_query_never(self, facet, query_type):
        """Check if a facet must never be returned by a particular query type.

        Returns True if the facet must never be returned.

        Returns False if the facet may be returned - either becuase there is no
        entry for the query type, or because the entry is not
        FacetQueryType_Never.

        """
        if query_type is None:
            return False
        if query_type not in self._facet_query_table:
            return False
        if facet not in self._facet_query_table[query_type]:
            return False
        return self._facet_query_table[query_type][facet] == IndexerConnection.FacetQueryType_Never

    @staticmethod
    def __set_weight_params(enq, weight_params):
        """Use a set of weighting parameters to modify the weight scheme.

        `enq` is an Enquire object to set the weighting scheme for.

        """
        if weight_params is not None:
            k1 = weight_params.get('k1', 1)
            if k1 < 0:
                raise ValueError("k1 must be >= 0")
            k2 = weight_params.get('k2', 0)
            if k2 < 0:
                raise ValueError("k2 must be >= 0")
            k3 = weight_params.get('k3', 1)
            if k3 < 0:
                raise ValueError("k3 must be >= 0")
            b = weight_params.get('b', 0.5)
            if b < 0:
                raise ValueError("b must be >= 0")
            if b > 1:
                raise ValueError("b must be <= 1")
            min_normlen = weight_params.get('min_normlen', 0.5)
            if min_normlen < 0:
                raise ValueError("min_normlen must be >= 0")
            try:
                wt = xapian.ColourWeight_(k1, k2, k3, b, min_normlen)
            except AttributeError:
                wt = xapian.BM25Weight(k1, k2, k3, b, min_normlen)
            enq.set_weighting_scheme(wt)
            enq._wt = wt # Ensure that wt isn't dereferenced too soon.

    def get_max_possible_weight(self, query, weight_params=None):
        """Calculate the maximum possible weight returned by a search.

        This looks only at the term statistics, and not at the lists of
        documents indexed by the terms, and returns a weight value.  As a
        result, it is usually very fast.

        However, the returned value is an upper bound on the weight which could
        be attained by a document in the database.  It is very unusual for this
        weight to actually be attained (indeed, with most weighting schemes, it
        is impossible for the bound to be attained).

        As a very rough rule of thumb, for a textual search in which the top
        document matches all the terms in the query, the maximum weight
        attained is usually about half the maximum possible weight.

        The bound may reasonably be used to normalise weights returned from
        various distinct queries when joining them together - for example, if
        the full search involves a textual part, and some fixed scores for
        documents, it may be useful to normalise weights for a textual part of
        a query by multiplying them by the reciprocal of this value, to get
        them into a similar range as the fixed document scores.

        `weight_params` is a dictionary (from string to number) of named
        parameters to pass to the weighting function.  Currently, the defined
        names are "k1", "k2", "k3", "b", "min_normlen".  Any unrecognised names
        will be ignored.  For documentation of the parameters, see the
        docs/weighting.rst document.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        enq = xapian.Enquire(self._index)

        if isinstance(query, xapian.Query):
            enq.set_query(query)
        else:
            enq.set_query(query._get_xapian_query())
        enq.set_docid_order(enq.DONT_CARE)

        # Set weighting scheme
        self.__set_weight_params(enq, weight_params)

        while True:
            try:
                mset = enq.get_mset(0, 0)
                break
            except xapian.DatabaseModifiedError, e:
                self.reopen()
        return mset.get_max_possible()

    def _get_sort_slot_and_dir(self, slotspec):
        """Get the value slot number and direction from a sortby parameter.

        Returns a tuple of (slot number, ascending).

        """
        asc = True
        if slotspec[0] == '-':
            asc = False
            slotspec = slotspec[1:]
        elif slotspec[0] == '+':
            slotspec = slotspec[1:]

        try:
            slotnum = self._field_mappings.get_slot(slotspec, 'collsort')
        except KeyError:
            raise errors.SearchError("Field %r was not indexed for sorting" % slotspec)

        # Note: we invert the "asc" parameter, because xapian treats
        # "ascending" as meaning "higher values are better"; in other
        # words, it considers "ascending" to mean return results in
        # descending order.  See xapian bug #311
        # (http://trac.xapian.org/ticket/311)
        return slotnum, not asc

    class SortByGeolocation(object):
        def __init__(self, fieldname, centre):
            self.fieldname = fieldname
            self.centre = centre

    def set_cache_manager(self, cache_manager):
        """Set the cache manager.

        To remove the cache manager, pass None as the cache_manager parameter.

        Once the cache manager has been set, the cached query results can be
        used to affect search results.

        """
        self.cache_manager = cache_manager

    def query_cached(self, cached_queryid):
        """Create a query which returns the cached set of results for the given
        query ID, weighted such that the difference in weight between all cached documents is at
        least 1.

        This will typically be used by combining it with an existing query with
        the OR operator, having normalised the existing query to ensure that
        none of its weights are greater than 1 (so they cannot override the
        cached weights).

        """
        serialised = self._make_parent_func_repr("query_cached")

        slot = cached_queryid + self._cache_manager_slot_start
        ps = xapian.ValueWeightPostingSource(slot)
        return Query(xapian.Query(ps), _refs=[ps], _conn=self, _serialised=serialised,
                     _queryid=cached_queryid)

    @staticmethod
    def _field_type_from_kwargslist(kwargslist):
        for kwargs in kwargslist:
            fieldtype = kwargs.get('type', None)
            if fieldtype is not None:
                return fieldtype
        return 'string'

    def _make_facet_matchspies(self, query, allowfacets, denyfacets,
                               usesubfacets, query_type):
        # Set facetspies to {}, even if no facet fields are found, to
        # distinguish from no facet calculation being performed.  (This
        # will prevent an error being thrown when the list of suggested
        # facets is requested - instead, an empty list will be returned.)
        facetspies = {}
        facetfields = []

        if allowfacets is not None and denyfacets is not None:
            raise errors.SearchError("Cannot specify both `allowfacets` and `denyfacets`")
        if allowfacets is None:
            allowfacets = [key for key in self._field_actions]
        if denyfacets is not None:
            allowfacets = [key for key in allowfacets if key not in denyfacets]

        # include None in queryfacets so a top-level facet will
        # satisfy self._facet_hierarchy.get(field) in queryfacets
        # (i.e. always include top-level facets)
        queryfacets = set([None])
        if usesubfacets:
            # add facets used in the query to queryfacets
            for term in query._get_xapian_query():
                prefix = self._get_prefix_from_term(term)
                field = self._field_mappings.get_fieldname_from_prefix(prefix)
                if field and FieldActions.FACET in self._field_actions[field]._actions:
                    queryfacets.add(field)

        for field in allowfacets:
            try:
                actions = self._field_actions[field]._actions
            except KeyError:
                actions = {}
            for action, kwargslist in actions.iteritems():
                if action == FieldActions.FACET:
                    # filter out non-top-level facets that aren't subfacets
                    # of a facet in the query
                    if usesubfacets:
                        is_subfacet = False
                        for parent in self._facet_hierarchy.get(field, [None]):
                            if parent in queryfacets:
                                is_subfacet = True
                        if not is_subfacet:
                            continue
                    # filter out facets that should never be returned for the query type
                    if self._facet_query_never(field, query_type):
                        continue
                    slot = self._field_mappings.get_slot(field, 'facet')
                    facettype = self._field_type_from_kwargslist(kwargslist)
                    if facettype == 'string':
                        facetspy = xapian.MultiValueCountMatchSpy(slot)
                    else:
                        facetspy = xapian.ValueCountMatchSpy(slot)
                    facetspies[slot] = facetspy
                    facetfields.append((field, slot, facettype))
        return facetspies, facetfields

    def _make_enquire(self, query):
        if not isinstance(query, xapian.Query):
            xapq = query._get_xapian_query()
        else:
            xapq = query
        enq = xapian.Enquire(self._index)
        enq.set_query(xapq)
        enq.set_docid_order(enq.DONT_CARE)
        return enq

    def _apply_sort_parameters(self, enq, sortby):
        if isinstance(sortby, basestring):
            enq.set_sort_by_value_then_relevance(
                *self._get_sort_slot_and_dir(sortby))
        elif isinstance(sortby, self.SortByGeolocation):
            # Get the slot
            try:
                slot = self._field_mappings.get_slot(sortby.fieldname, 'loc')
            except KeyError:
                raise errors.SearchError("Field %r was not indexed for geolocation sorting" % slotspec)

            # Get the coords
            coords = xapian.LatLongCoords()
            if isinstance(sortby.centre, basestring):
                coords.insert(xapian.LatLongCoord.parse_latlong(sortby.centre))
            else:
                for coord in sortby.centre:
                    coords.insert(xapian.LatLongCoord.parse_latlong(coord))

            # Make and use the keymaker
            metric = xapian.GreatCircleMetric()
            keymaker = xapian.LatLongDistanceKeyMaker(slot, coords, metric)
            enq.set_sort_by_key_then_relevance(keymaker, False)
            enq._keymaker = keymaker
            enq._metric = metric
        else:
            keymaker = xapian.MultiValueKeyMaker()
            for field in sortby:
                keymaker.add_value(*self._get_sort_slot_and_dir(field))
            enq.set_sort_by_key_then_relevance(keymaker, False)
            enq._keymaker = keymaker

    def _apply_collapse_parameters(self, enq, collapse, collapse_max):
        try:
            collapse_slotnum = self._field_mappings.get_slot(collapse, 'collsort')
        except KeyError:
            raise errors.SearchError("Field %r was not indexed for collapsing" % collapse)
        if collapse_max == 1:
            # Backwards compatibility - only this form existed before 1.1.0
            enq.set_collapse_key(collapse_slotnum)
        else:
            enq.set_collapse_key(collapse_slotnum, collapse_max)
        return collapse_slotnum

    def search(self, query, startrank, endrank,
               checkatleast=0, sortby=None, collapse=None,
               getfacets=None, allowfacets=None, denyfacets=None, usesubfacets=None,
               percentcutoff=None, weightcutoff=None,
               query_type=None, weight_params=None, collapse_max=1,
               stats_checkatleast=0, facet_checkatleast=0,
               facet_desired_num_of_categories=7):
        """Perform a search, for documents matching a query.

        - `query` is the query to perform.
        - `startrank` is the rank of the start of the range of matching
          documents to return (ie, the result with this rank will be returned).
          ranks start at 0, which represents the "best" matching document.
        - `endrank` is the rank at the end of the range of matching documents
          to return.  This is exclusive, so the result with this rank will not
          be returned.
        - `checkatleast` is the minimum number of results to check for when
          doing a normal (non facet) search: the estimate of the total number
          of matches will always be exact if the number of matches is less than
          `checkatleast`.  A value of ``-1`` can be specified for the
          checkatleast parameter - this has the special meaning of "check all
          matches", and is equivalent to passing the result of get_doccount().
        - `facet_checkatleast` is the minimum number of results to check for
          when doing a facet search.
        - `sortby` is the name of a field to sort by.  It may be preceded by a
          '+' or a '-' to indicate ascending or descending order
          (respectively).  If the first character is neither '+' or '-', the
          sort will be in ascending order.  Alternatively, a sequence holding
          field names (each optionally prefixed by '+' or '-') may be supplied
          in this parameter, to sort by multiple fields.  In this case, the
          sort will use the first field named in this list as the primary sort
          key, and use subsequent fields only when all the earlier fields have
          the same value in each document.
        - `collapse` is the name of a field to collapse the result documents
          on.  If this is specified, there will be at most `collapse_max`
          results in the result set for each value of the field.
        - `collapse_max` is the maximum number of items to allow in each
          collapse category.
        - `getfacets` is a boolean - if True, the matching documents will be
          examined to build up a list of the facet values contained in them.
        - `allowfacets` is a list of the fieldnames of facets to consider.
        - `denyfacets` is a list of fieldnames of facets which will not be
          considered.
        - `usesubfacets` is a boolean - if True, only top-level facets and
          subfacets of facets appearing in the query are considered (taking
          precedence over `allowfacets` and `denyfacets`).
        - `percentcutoff` is the minimum percentage a result must have to be
          returned.
        - `weightcutoff` is the minimum weight a result must have to be
          returned.
        - `query_type` is a value indicating the type of query being performed.
          If not None, the value is used to influence which facets are be
          returned by the get_suggested_facets() function.  If the value of
          `getfacets` is False, it has no effect.
        - `weight_params` is a dictionary (from string to number) of named
          parameters to pass to the weighting function.  Currently, the defined
          names are "k1", "k2", "k3", "b", "min_normlen".  Any unrecognised
          names will be ignored.  For documentation of the parameters, see the
          docs/weighting.rst document.

        If neither 'allowfacets' or 'denyfacets' is specified, all fields
        holding facets will be considered (but see 'usesubfacets').

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")

        if 'facets' in _checkxapian.missing_features:
            if getfacets is not None or \
               allowfacets is not None or \
               denyfacets is not None or \
               usesubfacets is not None or \
               query_type is not None:
                raise errors.SearchError("Facets unsupported with this release of xapian")
        if checkatleast == -1:
            checkatleast = self._index.get_doccount()
        if stats_checkatleast == -1:
            stats_checkatleast = self._index.get_doccount()
        if facet_checkatleast == -1:
            facet_checkatleast = self._index.get_doccount()

        # Check if we've got a cached query.
        queryid = None
        uncached_query = query
        if self.cache_manager is not None:
            if hasattr(query, '_get_queryid'):
                queryid = query._get_queryid()
                uncached_query = query._get_original_query()

        # Prepare the facet spies.
        if getfacets:
            facetspies, facetfields = self._make_facet_matchspies(uncached_query,
                allowfacets, denyfacets, usesubfacets, query_type)
        else:
            facetspies, facetfields = None, []

        # Get whatever information we can from the cache.
        cache_hits, cache_stats, cache_facets = None, None, None
        if queryid is not None:
            if sortby is None and collapse is None:
                # Get the ordering of the requested hits.  Ask for one more, so
                # we can tell if there are further hits.
                cache_hits = self.cache_manager.get_hits(queryid, startrank, endrank + 1)
                if len(cache_hits) < endrank - startrank:
                    # Drop the cached hits if we don't have enough from the
                    # pure cache lookup - we'll need to do a combined search
                    # instead.
                    cache_hits = None

                # Get statistics on the number of matches.
                cache_stats = self.cache_manager.get_stats(queryid)

                # Get the stored facet values.
                if len(facetfields) != 0:
                    cache_facets = self.cache_manager.get_facets(queryid)


        # Work out how many results we need.
        real_maxitems = 0
        need_to_search = False

        if cache_hits is None:
            real_maxitems = max(endrank - startrank, 0)
            # Always check for at least one more result, so we can report
            # whether there are more matches.
            checkatleast = max(checkatleast, endrank + 1)
            need_to_search = True
        else:
            # We have cached hits, so don't need to run the search to get the
            # ordering.  Therefore, no need for the query which is combined
            # with the cache.
            query = uncached_query

        if cache_stats is None:
            # Need to get basic statistics from the search, but we'll just to a
            # 0-document search for this if we don't need anything else.
            need_to_search = True
            checkatleast = max(checkatleast, stats_checkatleast)

        if len(facetfields) != 0:
            # FIXME - check if the facets requested were available - if not all
            # available, set cache_facets to None.

            if cache_facets is None:
                checkatleast = max(checkatleast, facet_checkatleast)
                need_to_search = True

        # FIXME - we currently always need to search to get a mset object for 
        need_to_search = True

        if need_to_search:
            # Build up the xapian enquire object
            enq = self._make_enquire(query)
            if sortby is not None:
                self._apply_sort_parameters(enq, sortby)
            if collapse is not None:
                collapse_slotnum = self._apply_collapse_parameters(enq, collapse, collapse_max)
            if getfacets:
                for facetspy in facetspies.itervalues():
                    enq.add_matchspy(facetspy)

            # Set percentage and weight cutoffs
            if percentcutoff is not None or weightcutoff is not None:
                if percentcutoff is None:
                    percentcutoff = 0
                if weightcutoff is None:
                    weightcutoff = 0
                enq.set_cutoff(percentcutoff, weightcutoff)

            # Set weighting scheme
            self.__set_weight_params(enq, weight_params)

            # Repeat the search until we don't get a DatabaseModifiedError
            while True:
                try:
                    mset = enq.get_mset(startrank, real_maxitems, checkatleast)
                    break
                except xapian.DatabaseModifiedError, e:
                    self.reopen()


        # Build the search results:
        if cache_facets is None:
            # The facet results don't depend on anything else.
            facet_hierarchy = None
            if usesubfacets:
                facet_hierarchy = self._facet_hierarchy
            facets = MSetFacetResults(facetspies, facetfields, facet_hierarchy,
                                      self._facet_query_table.get(query_type),
                                      facet_desired_num_of_categories)
        else:
            facets = CacheFacetResults(cache_facets)

        if need_to_search:
            # Need a way to get term weights.
            weightgetter = MSetTermWeightGetter(mset)

        # The context is supplied to each SearchResult.
        context = SearchResultContext(self, self._field_mappings, weightgetter, query)

        if cache_hits is None:
            # Use the ordering returned by the MSet.
            ordering = MSetResultOrdering(mset, context, self)
            if collapse is not None:
                ordering.collapse_slotnum = collapse_slotnum
                ordering.collapse_max = collapse_max
        else:
            # Use the ordering returned by the Cache.
            ordering = CacheResultOrdering(context,
                                           cache_hits[:endrank-startrank],
                                           startrank)

        # Statistics on the number of matching documents.
        if cache_stats is None:
            stats = MSetResultStats(mset)
        else:
            stats = CacheResultStats(cache_stats)

        return SearchResults(self, query, self._field_mappings,
                             facets, ordering, stats, context)

    def iterids(self):
        """Get an iterator which returns all the ids in the database.

        The unqiue_ids are currently returned in binary lexicographical sort
        order, but this should not be relied on.

        Note that the iterator returned by this method may raise a
        xapian.DatabaseModifiedError exception if modifications are committed
        to the database while the iteration is in progress.  If this happens,
        the search connection must be reopened (by calling reopen) and the
        iteration restarted.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        return PrefixedTermIter('Q', self._index.allterms())

    def iter_documents(self):
        """Get an iterator which returns all the documents in the database.

        The documents will often be returned in the order in which they were
        added, but this should not be relied on.

        Note that the iterator returned by this method may raise a
        xapian.DatabaseModifiedError exception if modifications are committed
        to the database while the iteration is in progress.  If this happens,
        the search connection must be reopened (by calling reopen) and the
        iteration restarted.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        return DocumentIter(self, self._index.postlist(''))

    def get_document(self, docid=None, xapid=None):
        """Get the document with the specified unique ID.

        This should usually be called with the `docid` parameter set to the
        document ID of the document (which is an arbitrary string value).

        However, if you happen to know the xapian document ID, you can pass it
        in instead, by using the `xapid` parameter.  Note that xapian document
        IDs are liable to change between revisions of the database, thoguh.

        Exactly one of the `docid` and `xapid` parameters should be set to
        non-None.

        Raises a KeyError if there is no such document.  Otherwise, it returns
        a ProcessedDocument.

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        if docid is not None and xapid is not None:
            raise errors.SearchError("Only one of docid and xapid "
                                      "should be set")
        while True:
            try:
                if docid is not None:
                    postlist = self._index.postlist('Q' + docid)
                    try:
                        plitem = postlist.next()
                    except StopIteration:
                        # Unique ID not found
                        raise KeyError('Unique ID %r not found' % docid)
                    try:
                        postlist.next()
                        raise errors.IndexerError("Multiple documents "
                                                   "found with same unique ID: %r" % docid)
                    except StopIteration:
                        # Only one instance of the unique ID found, as it
                        # should be.
                        pass
                    xapid = plitem.docid
                if xapid is None:
                    raise errors.SearchError("Either docid or xapid must be "
                                              "set")

                result = ProcessedDocument(self._field_mappings)
                result._doc = self._index.get_document(xapid)
                return result
            except xapian.DatabaseModifiedError, e:
                self.reopen()

    def iter_synonyms(self, prefix=""):
        """Get an iterator over the synonyms.

         - `prefix`: if specified, only synonym keys with this prefix will be
           returned.

        The iterator returns 2-tuples, in which the first item is the key (ie,
        a 2-tuple holding the term or terms which will be synonym expanded,
        followed by the fieldname specified (or None if no fieldname)), and the
        second item is a tuple of strings holding the synonyms for the first
        item.

        These return values are suitable for the dict() builtin, so you can
        write things like:

         >>> conn = IndexerConnection('foo')
         >>> conn.add_synonym('foo', 'bar')
         >>> conn.add_synonym('foo bar', 'baz')
         >>> conn.add_synonym('foo bar', 'foo baz')
         >>> conn.flush()
         >>> conn = SearchConnection('foo')
         >>> dict(conn.iter_synonyms())
         {('foo', None): ('bar',), ('foo bar', None): ('baz', 'foo baz')}

        """
        if self._index is None:
            raise errors.SearchError("SearchConnection has been closed")
        return SynonymIter(self._index, self._field_mappings, prefix)

    def get_metadata(self, key):
        """Get an item of metadata stored in the connection.

        This returns a value stored by a previous call to
        IndexerConnection.set_metadata.

        If the value is not found, this will return the empty string.

        """
        if self._index is None:
            raise errors.IndexerError("SearchConnection has been closed")
        if not hasattr(self._index, 'get_metadata'):
            raise errors.IndexerError("Version of xapian in use does not support metadata")
        while True:
            try:
                return self._index.get_metadata(key)
            except xapian.DatabaseModifiedError, e:
                self.reopen()

    def iter_terms_for_field(self, field, starts_with=''):
        """Return an iterator over the terms that a field has in the index.

        Values are returned in sorted order (sorted by lexicographical binary
        sort order of the UTF-8 encoded version of the term).

        """
        if self._index is None:
            raise errors.IndexerError("SearchConnection has been closed")
        prefix = self._field_mappings.get_prefix(field)
        trimlen = len(starts_with)
        return PrefixedTermIter(prefix, self._index.allterms(prefix), trimlen)

    def query_valuemap(self, field, weightmap, default_weight=None):
        """Return a query consisting of a value map posting source.

         - `field` should have been indexed with field action SORTABLE.
         - `weightmap` is a dict of value strings to weights.
         - `default_weight` is the weight to return if the document's value has
           no mapping, and defaults to 0.0.

        """
        serialised = self._make_parent_func_repr("query_valuemap")
        slot = self._field_mappings.get_slot(field, 'collsort')

        # Construct a posting source
        ps = xapian.ValueMapPostingSource(slot)
        if default_weight is not None:
            if default_weight < 0:
                raise ValueError("default_weight must be >= 0")
            ps.set_default_weight(default_weight)
        for k, v in weightmap.items():
            if v < 0:
                raise ValueError("weights in weightmap must be >= 0")
            ps.add_mapping(k, v)

        return Query(xapian.Query(ps),
                     _refs=[ps], _conn=self,
                     _serialised=serialised)
