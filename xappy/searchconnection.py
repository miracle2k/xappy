#!/usr/bin/env python
#
# Copyright (C) 2007,2008,2009 Lemur Consulting Ltd
# Copyright (C) 2009 Pablo Hoffman
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
import os as _os
import cPickle as _cPickle
import math
import inspect
import itertools

import xapian as _xapian
from datastructures import *
from fieldactions import ActionContext, FieldActions, \
         ActionSet, SortableMarshaller, convert_range_to_term, \
         _get_imgterms
import fieldmappings as _fieldmappings
from fields import Field, FieldGroup
import highlight as _highlight
import errors as _errors
from indexerconnection import IndexerConnection, PrefixedTermIter, \
         DocumentIter, SynonymIter, _allocate_id
import re as _re
from query import Query

def add_to_dict_of_dicts(d, key, item, value):
    """Add to an an entry to a dict of dicts.

    """
    try:
        d[key][item] = d[key].get(item, 0) + value
    except KeyError:
        d[key] = {item: value}

class SearchResult(ProcessedDocument):
    """A result from a search.

    As well as being a ProcessedDocument representing the document in the
    database, the result has several members which may be used to get
    information about how well the document matches the search:

     - `rank`: The rank of the document in the search results, starting at 0
       (ie, 0 is the "top" result, 1 is the second result, etc).

     - `weight`: A floating point number indicating the weight of the result
       document.  The value is only meaningful relative to other results for a
       given search - a different search, or the same search with a different
       database, may give an entirely different scale to the weights.  This
       should not usually be displayed to users, but may be useful if trying to
       perform advanced reweighting operations on search results.

     - `percent`: A percentage value for the weight of a document.  This is
       just a rescaled form of the `weight` member.  It doesn't represent any
       kind of probability value; the only real meaning of the numbers is that,
       within a single set of results, a document with a higher percentage
       corresponds to a better match.  Because the percentage doesn't really
       represent a probability, or a confidence value, it is probably unhelpful
       to display it to most users, since they tend to place an over emphasis
       on its meaning.  However, it is included because it may be useful
       occasionally.

    """
    def __init__(self, msetitem, results):
        ProcessedDocument.__init__(self, results._fieldmappings, msetitem.document)
        self.rank = msetitem.rank
        self.weight = msetitem.weight
        self.percent = msetitem.percent
        self._results = results

        # Fields for which term and value assocs have been calculated.
        self._tvassocs_fields = None

        # termassocs is a map from a term to a list of tuples of (fieldname,
        # offset, weight) of relevant data.
        self._termassocs = None

        # valueassocs is a map from a value slot to a list of values with
        # associated (fieldname, offset) data.
        self._valueassocs = None

        # Map from (field, offset) to group number.
        self._grouplu = None

    def _get_language(self, field):
        """Get the language that should be used for a given field.

        Raises a KeyError if the field is not known.

        """
        actions = self._results._conn._field_actions[field]._actions
        for action, kwargslist in actions.iteritems():
            if action == FieldActions.INDEX_FREETEXT:
                for kwargs in kwargslist:
                    try:
                        return kwargs['language']
                    except KeyError:
                        pass
        return 'none'

    def _add_termvalue_assocs(self, assocs, fields=None):
        """Add the associations found in assocs to those in self.

        """
        for fieldname, tvoffsetlist in assocs.iteritems():
            if fields is not None and fieldname not in fields:
                continue
            for (tv, offset), weight in tvoffsetlist.iteritems():
                if tv[0] == 'T':
                    term = tv[1:]
                    try:
                        item = self._termassocs[term]
                    except KeyError:
                        item = []
                        self._termassocs[term] = item
                    item.append((fieldname, offset, weight))
                elif tv[0] == 'V':
                    slot, value = tv[1:].split(':', 1)
                    slot = int(slot)
                    try:
                        item = self._valueassocs[slot]
                    except KeyError:
                        item = []
                        self._valueassocs[slot] = item
                    item.append((value, (fieldname, offset, weight)))
                else:
                    assert False

    def _calc_termvalue_assocs(self, fields):
        """Calculate the term-value associations.

        """
        conn = self._results._conn
        self._termassocs = {}
        self._valueassocs = {}

        # Iterate through the stored content, extracting the set of terms and
        # values which are relevant to each piece.
        fields = set(fields)
        for field, values in self.data.iteritems():
            if field not in fields:
                continue
            unpdoc = UnprocessedDocument()
            for value in values:
                unpdoc.fields.append(Field(field, value, value))
            try:
                pdoc = conn.process(unpdoc)
            except errors.IndexerError:
                # Ignore indexing errors - these can happen if the stored
                # data isn't the original data (due to a field
                # association), resulting in the wrong type of data being
                # supplied to the indexing action.
                continue
            self._add_termvalue_assocs(pdoc._get_assocs())

        # Merge in the terms and values from the stored field associations.
        self._add_termvalue_assocs(self._get_assocs(), set(fields))


    def _relevant_data_simple(self, allow, query, groupnumbers):
        """Calculate the relevant data using a simple (faster but less
        accurate) algorithm.

        """
        # For each field, calculate a list of the prefixes under which terms
        # in that field are stored.
        allowset = set(allow)
        prefixes_ft = {}
        prefixes_exact = {}
        slots = {}
        for field in allow:
            p = []
            actions = self._results._conn._field_actions[field]._actions
            is_ft = None
            for action, kwargslist in actions.iteritems():
                if action == FieldActions.INDEX_FREETEXT:
                    is_ft = True
                    for kwargs in kwargslist:
                        if kwargs.get('search_by_default', True):
                            p.append('')
                        if kwargs.get('allow_field_specific', True):
                            p.append(self._fieldmappings.get_prefix(field))
                if action == FieldActions.INDEX_EXACT:
                    is_ft = False
                    for kwargs in kwargslist:
                        p.append(self._fieldmappings.get_prefix(field))
                if action == FieldActions.FACET:
                    for kwargs in kwargslist:
                        if kwargs.get('type') == 'float':
                            try:
                                slots[self._fieldmappings.get_slot(field, 'facet')] = field
                            except KeyError: pass
                if action == FieldActions.SORT_AND_COLLAPSE:
                    for kwargs in kwargslist:
                        if kwargs.get('type') == 'float':
                            try:
                                slots[self._fieldmappings.get_slot(field, 'collsort')] = field
                            except KeyError: pass
            if is_ft is True:
                prefixes_ft[field] = p
            elif is_ft is False:
                prefixes_exact[field] = p

        # For each term in the query, get the weight, and store it in a
        # dictionary.
        queryweights = {}
        for term in query._get_terms():
            try:
                queryweights[term] = self._results._mset.get_termweight(term)
            except errors.XapianError:
                pass

        # Build relevant_items, a dictionary keyed by (field, offset) pairs,
        # with values being the weights for the text at that offset in the
        # field.
        # Also build field_scores, a dictionary counting the sum of the score
        # for each field.
        relevant_items = {}
        field_scores = {}
        for field, values in self.data.iteritems():
            if field not in allowset:
                continue
            hl = _highlight.Highlighter(language_code=self._get_language(field))
            for i, value in enumerate(values):
                score = 0
                for prefix in prefixes_ft.get(field, ()):
                    score += hl._score_text(value, prefix, lambda term:
                                            queryweights.get(term, 0))
                for prefix in prefixes_exact.get(field, ()):
                    term = prefix
                    if len(value) > 0:
                        chval = ord(value[0])
                        if chval >= ord('A') and chval <= ord('Z'):
                            term += ':'
                    term += value
                    if term in queryweights:
                        score += 1
                if score > 0:
                    relevant_items.setdefault(field, []).append((-score, i))
                    field_scores[field] = field_scores.get(field, 0) + score

        # Iterate through the ranges in the query, checking them.
        for slot, begin, end in query._get_ranges():
            field = slots.get(slot)
            if field is None:
                continue
            value = self._doc.get_value(slot)
            in_range = False
            if begin is None:
                if end is None:
                    in_range = True
                elif value <= end:
                    in_range = True
            elif begin <= value:
                if end is None:
                    in_range = True
                elif value <= end:
                    in_range = True
            if in_range:
                relevant_items.setdefault(field, []).append((-1, 0))
                field_scores[field] = field_scores.get(field, 0) + 1

        # Build a list of the fields which match the query, counting the number
        # of clauses they match.
        scoreditems = [(-score, field)
                       for field, score in field_scores.iteritems()]
        scoreditems.sort()

        if groupnumbers:
            # First, build a dict from (field, offset) to group number
            if self._grouplu is None:
                self._grouplu = self._calc_group_lookup()

            # keyed by fieldname, values are sets of offsets for that field
            relevant_offsets = {}

            for score, field in scoreditems:
                for weight, offset in relevant_items[field]:
                    relevant_offsets.setdefault(field, {})[offset] = weight, None
                    groupnums = self._grouplu.get((field, offset), None)
                    if groupnums is not None:
                        for gn in groupnums:
                            for groupfield, groupoffset in self._get_groups()[gn]:
                                relevant_offsets.setdefault(groupfield, {})[groupoffset] = weight, gn

            result = []
            for score, field in scoreditems:
                fielddata = [(-weight, self.data[field][offset], groupnum) for offset, (weight, groupnum) in relevant_offsets[field].iteritems()]
                del relevant_offsets[field]
                fielddata.sort()
                result.append((field, tuple((data, groupnum) for weight, data, groupnum in fielddata)))
        else:
            # Return the relevant data for each field.
            result = []
            for score, field in scoreditems:
                fielddata = relevant_items[field]
                fielddata.sort()
                result.append((field, tuple(self.data[field][offset]
                                            for weight, offset in fielddata)))
        return tuple(result)

    def relevant_data(self, allow=None, deny=None, query=None,
                      groupnumbers=False, simple=True):
        """Return field data which was relevant for this result.

        This will return a tuple of fields which have data stored for them
        which was relevant to the search, together with the data which was
        relevant.

        If `groupnumbers` is `False` the returned tuple items will be tuples of
        (fieldname, data), where data is itself a tuple of strings. If
        `groupnumbers` is `True` the returned tuple items will be tuples of
        (fielddata, groupnum), instead of strings, where groupnum is the group
        number (starting from zero) which the relevant data belongs to. For
        ungrouped data, groupnum is `None`. You can use the `groupdict`
        attribute to get the full data for each group from the group numbers.

        In order to be returned the fields must have the STORE_CONTENT action,
        but must also be included in the query (so must have other actions
        specified too).  If there are multiple instances of a field, only those
        which have some relevance will be returned.

        If field associations were used when indexing the field (ie, the
        "Field.assoc" member was set), the associated data will be returned,
        but the original field data will be used to determine whether the
        field should be returned or not.

        By default, all fields will be considered by this function, but the
        list of fields considered may be adjusted with the allow and deny
        parameters.

         - `allow`: A list of fields to consider for relevance.
         - `deny`: A list of fields not to consider for relevance.

        If `query` is supplied, it should contain a Query object, as returned
        from SearchConnection.query_parse() or related methods, which will be
        used as the basis of selecting relevant data rather than the query
        which was used for the search.

        If `group` is set to True, any field data which shares a FieldGroup
        with some relevant data will also be returned.

        """
        if isinstance(allow, basestring):
            allow = (allow, )
        if isinstance(deny, basestring):
            deny = (deny, )
        if allow is not None and len(allow) == 0:
            allow = None
        if deny is not None and len(deny) == 0:
            deny = None
        if allow is not None and deny is not None:
            raise _errors.SearchError("Cannot specify both `allow` and `deny` "
                                      "(got %r and %r)" % (allow, deny))
        if allow is None:
            allow = [key for key in self._results._conn._field_actions]
        if deny is not None:
            allow = [key for key in allow if key not in deny]

        allow = list(allow)
        allow.sort()

        if query is None:
            query = self._results._query
        conn = self._results._conn

        if simple:
            return self._relevant_data_simple(allow, query, groupnumbers)

        if self._tvassocs_fields != allow:
            self._tvassocs_fields = None
            self._calc_termvalue_assocs(allow)
            self._tvassocs_fields = allow

        fieldscores = {}
        fieldassocs = {}
        # Iterate through the components of the query, looking for those terms
        # and values which match it.
        for term in query._get_terms():
            assocs = self._termassocs.get(term)
            if assocs is None:
                continue
            for field, offset, weight in assocs:
                fieldscores[field] = fieldscores.get(field, 0) + 1
                add_to_dict_of_dicts(fieldassocs, field, offset, weight)

        # Iterate through the ranges in the query, checking them.
        for slot, begin, end in query._get_ranges():
            assocs = self._valueassocs.get(slot)
            if assocs is None:
                continue
            for value, (field, offset, weight) in assocs:
                if begin is None:
                    if end is None:
                        fieldscores[field] = fieldscores.get(field, 0) + 1
                        add_to_dict_of_dicts(fieldassocs, field, offset, weight)
                    elif value <= end:
                        fieldscores[field] = fieldscores.get(field, 0) + 1
                        add_to_dict_of_dicts(fieldassocs, field, offset, weight)
                elif begin <= value:
                    if end is None:
                        fieldscores[field] = fieldscores.get(field, 0) + 1
                        add_to_dict_of_dicts(fieldassocs, field, offset, weight)
                    elif value <= end:
                        fieldscores[field] = fieldscores.get(field, 0) + 1
                        add_to_dict_of_dicts(fieldassocs, field, offset, weight)

        # Convert the dict of fields and data offsets with scores to to a list
        # of (field, data) item.  Sort in decreasing order of score, and
        # increasing alphabetical order if the score is the same.
        scoreditems = [(-score, field)
                       for field, score in fieldscores.iteritems()]
        scoreditems.sort()
        result = []

        if groupnumbers:
            # First, build a dict from (field, offset) to group number
            if self._grouplu is None:
                self._grouplu = self._calc_group_lookup()

            # keyed by fieldname, values are sets of offsets for that field
            relevant_offsets = {}

            for score, field in scoreditems:
                for offset, weight in fieldassocs[field].iteritems():
                    relevant_offsets.setdefault(field, {})[offset] = weight, None
                    groupnums = self._grouplu.get((field, offset), None)
                    if groupnums is not None:
                        for gn in groupnums:
                            for groupfield, groupoffset in self._get_groups()[gn]:
                                relevant_offsets.setdefault(groupfield, {})[groupoffset] = weight, gn

            for score, field in scoreditems:
                fielddata = [(-weight, self.data[field][offset], groupnum) for offset, (weight, groupnum) in relevant_offsets[field].iteritems()]
                del relevant_offsets[field]
                fielddata.sort()
                result.append((field, tuple((data, groupnum) for weight, data, groupnum in fielddata)))
        else:
            # Not grouped - just return the relevant data for each field.
            for score, field in scoreditems:
                fielddata = [(-weight, self.data[field][offset]) for offset, weight in fieldassocs[field].iteritems()]
                fielddata.sort()
                result.append((field, tuple(data for weight, data in fielddata)))
        return tuple(result)

    def summarise(self, field, maxlen=600, hl=('<b>', '</b>'), query=None):
        """Return a summarised version of the field specified.

        This will return a summary of the contents of the field stored in the
        search result, with words which match the query highlighted.

        The maximum length of the summary (in characters) may be set using the
        maxlen parameter.

        The return value will be a string holding the summary, with
        highlighting applied.  If there are multiple instances of the field in
        the document, the instances will be joined with a newline character.

        To turn off highlighting, set hl to None.  Each highlight will consist
        of the first entry in the `hl` list being placed before the word, and
        the second entry in the `hl` list being placed after the word.

        Any XML or HTML style markup tags in the field will be stripped before
        the summarisation algorithm is applied.

        If `query` is supplied, it should contain a Query object, as returned
        from SearchConnection.query_parse() or related methods, which will be
        used as the basis of the summarisation and highlighting rather than the
        query which was used for the search.

        Raises KeyError if the field is not known.

        """
        highlighter = _highlight.Highlighter(language_code=self._get_language(field))
        field = self.data[field]
        results = []
        text = '\n'.join(field)
        if query is None:
            query = self._results._query
        return highlighter.makeSample(text, query, maxlen, hl)

    def highlight(self, field, hl=('<b>', '</b>'), strip_tags=False, query=None):
        """Return a highlighted version of the field specified.

        This will return all the contents of the field stored in the search
        result, with words which match the query highlighted.

        The return value will be a list of strings (corresponding to the list
        of strings which is the raw field data).

        Each highlight will consist of the first entry in the `hl` list being
        placed before the word, and the second entry in the `hl` list being
        placed after the word.

        If `strip_tags` is True, any XML or HTML style markup tags in the field
        will be stripped before highlighting is applied.

        If `query` is supplied, it should contain a Query object, as returned
        from SearchConnection.query_parse() or related methods, which will be
        used as the basis of the summarisation and highlighting rather than the
        query which was used for the search.

        Raises KeyError if the field is not known.

        """
        highlighter = _highlight.Highlighter(language_code=self._get_language(field))
        field = self.data[field]
        results = []
        if query is None:
            query = self._results._query
        for text in field:
            results.append(highlighter.highlight(text, query, hl, strip_tags))
        return results

    def __repr__(self):
        return ('<SearchResult(rank=%d, id=%r, data=%r)>' %
                (self.rank, self.id, self.data))


class SearchResultIter(object):
    """An iterator over a set of results from a search.

    """
    def __init__(self, results, order):
        self._results = results
        self._order = order
        if self._order is None:
            self._iter = iter(results._mset)
        else:
            self._iter = iter(self._order)

    def next(self):
        if self._order is None:
            msetitem = self._iter.next()
        else:
            index = self._iter.next()
            msetitem = self._results._mset.get_hit(index)
        return SearchResult(msetitem, self._results)


def _get_significant_digits(value, lower, upper):
    """Get the significant digits of value which are constrained by the
    (inclusive) lower and upper bounds.

    If there are no significant digits which are definitely within the
    bounds, exactly one significant digit will be returned in the result.

    >>> _get_significant_digits(15,15,15)
    15
    >>> _get_significant_digits(15,15,17)
    20
    >>> _get_significant_digits(4777,208,6000)
    5000
    >>> _get_significant_digits(4777,4755,4790)
    4800
    >>> _get_significant_digits(4707,4695,4710)
    4700
    >>> _get_significant_digits(4719,4717,4727)
    4720
    >>> _get_significant_digits(0,0,0)
    0
    >>> _get_significant_digits(9,9,10)
    9
    >>> _get_significant_digits(9,9,100)
    9

    """
    assert(lower <= value)
    assert(value <= upper)
    diff = upper - lower

    # Get the first power of 10 greater than the difference.
    # This corresponds to the magnitude of the smallest significant digit.
    if diff == 0:
        pos_pow_10 = 1
    else:
        pos_pow_10 = int(10 ** math.ceil(math.log10(diff)))

    # Special case for situation where we don't have any significant digits:
    # get the magnitude of the most significant digit in value.
    if pos_pow_10 > value:
        if value == 0:
            pos_pow_10 = 1
        else:
            pos_pow_10 = int(10 ** math.floor(math.log10(value)))

    # Return the value, rounded to the nearest multiple of pos_pow_10
    return ((value + pos_pow_10 // 2) // pos_pow_10) * pos_pow_10

class SearchResults(object):
    """A set of results of a search.

    """
    def __init__(self, conn, enq, query, mset, fieldmappings,
                 facetspies, facetfields, facethierarchy,
                 facetassocs):
        self._conn = conn
        self._enq = enq
        self._query = query
        self._mset = mset
        self._mset_order = None
        self._fieldmappings = fieldmappings
        self._facetspies = facetspies
        self._facetfields = facetfields
        self._facethierarchy = facethierarchy
        self._facetassocs = facetassocs
        self._facetvalues = {}

    def _cluster(self, num_clusters, maxdocs, fields=None,
                 assume_single_value=False):
        """Cluster results based on similarity.

        Note: this method is experimental, and will probably disappear or
        change in the future.

        The number of clusters is specified by num_clusters: unless there are
        too few results, there will be exaclty this number of clusters in the
        result.

        """
        clusterer = _xapian.ClusterSingleLink()
        xapclusters = _xapian.ClusterAssignments()
        docsim = _xapian.DocSimCosine()
        source = _xapian.MSetDocumentSource(self._mset, maxdocs)

        if fields is None:
            try:
                # backwards compatibility; used to have to supply the index as
                # first param, and didn't have the slotnum option.
                clusterer.cluster(xapclusters, docsim, source, num_clusters)
            except TypeError:
                clusterer.cluster(self._conn._index, xapclusters, docsim, source, num_clusters)
        else:
            # If there's only one field and it has unique instances stored in a
            # value, use the value instead of the termlist.
            slotnum = self._get_singlefield_slot(fields, assume_single_value)
            try:
                if slotnum is not None:
                    decider = None
                    clusterer.cluster(xapclusters, docsim, source, slotnum, num_clusters)
                else:
                    decider = self._make_expand_decider(fields)
                    clusterer.cluster(xapclusters, docsim, source, decider, num_clusters)
            except TypeError:
                # backwards compatibility; used to have to supply the index as
                # first param, and didn't have the slotnum option.
                if decider is None:
                    decider = self._make_expand_decider(fields)
                clusterer.cluster(self._conn._index,
                                  xapclusters, docsim, source, decider, num_clusters)

        newid = 0
        idmap = {}
        clusters = {}
        for item in self._mset:
            docid = item.docid
            clusterid = xapclusters.cluster(docid)
            if clusterid not in idmap:
                idmap[clusterid] = newid
                newid += 1
            clusterid = idmap[clusterid]
            if clusterid not in clusters:
                clusters[clusterid] = []
            clusters[clusterid].append(item.rank)
        return clusters

    def _reorder_by_collapse(self, 
                             highest_possible_percentage = 50.0
                            ):
        """Reorder the result by the values in the slot used to collapse on.

        `highest_possible_percentage` is a tuning variable - we need to get an
        estimate of the probability that a particular hit satisfies the query.
        We use the relevance score for this estimate, but this requires us to
        pick a value for the top hit.  This variable specifies that percentage.

        """

        if self.startrank != 0:
            raise _errors.SearchError("startrank must be zero to reorder by collapse")
        if not hasattr(self, "collapse_max"):
            raise _errors.SearchError("A collapse must have been performed on the search in order to use _reorder_by_collapse")

        if self.collapse_max == 1:
            # No reordering to do - we're already fully diverse according to
            # the values in the slot.
            return

        if self.endrank <= 1:
            # No reordering to do - 0 or 1 items.
            return

        topweight = self._mset.get_hit(0).weight
        toppct = self._mset.get_hit(0).percent
        if topweight == 0 or toppct == 0:
            # No weights, so no reordering to do.
            # FIXME - perhaps we should pick items from each bin in turn until
            # the bins run out?  Not sure this is useful in any real situation,
            # though.
            return

        maxweight = topweight * 100.0 * 100.0 / highest_possible_percentage / float(toppct)

        # utility of each category; initially, this is the probability that the
        # category is relevant.
        utilities = {}
        pqc_sum = 0.0

        # key is the collapse key, value is a list of (rank, weight) tuples,
        # in that collapse bin.
        collapse_bins = {}

        # Fill collapse_bins.
        for i in xrange(self.endrank):
            hit = self._mset.get_hit(i)
            category = hit.collapse_key
            try:
                l = collapse_bins[category]
            except KeyError:
                l = []
                collapse_bins[category] = l
                if i < 100:
                    utilities[category] = hit.weight
                    pqc_sum += hit.weight
            l.append((i, hit.weight / maxweight))

        pqc_sum /= 0.99 # Leave 1% probability for other categories

        # Nomalise the probabilities for each query category, so they add up to
        # 1.
        utilities = dict((k, v / pqc_sum)
                         for (k, v)
                         in utilities.iteritems())

        # Calculate scores for the potential next hits.  These are the top
        # weighted hits in each category.
        potentials = {}
        for category, l in collapse_bins.iteritems():
            wt = l[0][1] # weight of the top item
            score = wt * utilities.get(category, 0.01) # current utility of the category
            potentials[category] = (l[0][0], score, wt)

        new_order = []
        while len(collapse_bins) != 0:
            # The potential next hits are the ones at the top of each
            # collapse_bin.

            # Pick the next category to use, by finding the maximum score
            # (breaking ties by choosing the highest ranked one in the original
            # order).
            next_cat, (next_i, next_score, next_wt) = max(potentials.iteritems(), key=lambda x: (x[1][1], -x[1][0]))

            # Update the utility of the chosen category
            utilities[next_cat] = (1.0 - next_wt) * utilities.get(next_cat, 0.01)
            
            # Move the newly picked item from collapse_bins to new_order
            new_order.append(next_i)
            l = collapse_bins[next_cat]
            if len(l) <= 1:
                del collapse_bins[next_cat]
                del potentials[next_cat]
            else:
                collapse_bins[next_cat] = l[1:]
                wt = l[1][1] # weight of the top item
                potentials[next_cat] = (l[1][0],
                                        wt * utilities.get(next_cat, 0.01), wt)

        self._mset_order = new_order

    def _reorder_by_clusters(self, clusters):
        """Reorder the mset based on some clusters.

        """
        if self.startrank != 0:
            raise _errors.SearchError("startrank must be zero to reorder by clusters")
        reordered = False
        tophits = []
        nottophits = []

        clusterstarts = dict(((c[0], None) for c in clusters.itervalues()))
        for i in xrange(self.endrank):
            if i in clusterstarts:
                tophits.append(i)
            else:
                nottophits.append(i)
        self._mset_order = tophits
        self._mset_order.extend(nottophits)

    def _get_singlefield_slot(self, fields, assume_single_value):
        """Return the slot number if the specified list of fields contains only
        one entry, and that entry is single-valued for each document, and
        stored in a value slot.

        Return None otherwise.

        """
        prefixes = {}
        if isinstance(fields, basestring):
            fields = [fields]
        if len(fields) != 1:
            return None

        field = fields[0]
        try:
            actions = self._conn._field_actions[field]._actions
        except KeyError:
            return None

        for action, kwargslist in actions.iteritems():
            if action == FieldActions.SORTABLE:
                return self._conn._field_mappings.get_slot(field, 'collsort')
            if action == FieldActions.WEIGHT:
                return self._conn._field_mappings.get_slot(field, 'weight')
            if assume_single_value:
                if action == FieldActions.FACET:
                    return self._conn._field_mappings.get_slot(field, 'facet')

    def _make_expand_decider(self, fields):
        """Make an expand decider which accepts only terms in the specified
        field.

        """
        prefixes = {}
        if isinstance(fields, basestring):
            fields = [fields]
        for field in fields:
            try:
                actions = self._conn._field_actions[field]._actions
            except KeyError:
                continue
            for action, kwargslist in actions.iteritems():
                if action == FieldActions.INDEX_FREETEXT:
                    prefix = self._conn._field_mappings.get_prefix(field)
                    prefixes[prefix] = None
                    prefixes['Z' + prefix] = None
                if action in (FieldActions.INDEX_EXACT,
                              FieldActions.FACET,):
                    prefix = self._conn._field_mappings.get_prefix(field)
                    prefixes[prefix] = None
        prefix_re = _re.compile('|'.join([_re.escape(x) + '[^A-Z]' for x in prefixes.keys()]))
        class decider(_xapian.ExpandDecider):
            def __call__(self, term):
                return prefix_re.match(term) is not None
        return decider()

    def _reorder_by_similarity(self, count, maxcount, max_similarity,
                               fields=None):
        """Reorder results based on similarity.

        The top `count` documents will be chosen such that they are relatively
        dissimilar.  `maxcount` documents will be considered for moving around,
        and `max_similarity` is a value between 0 and 1 indicating the maximum
        similarity to the previous document before a document is moved down the
        result set.

        Note: this method is experimental, and will probably disappear or
        change in the future.

        """
        if self.startrank != 0:
            raise _errors.SearchError("startrank must be zero to reorder by similiarity")
        ds = _xapian.DocSimCosine()
        ds.set_termfreqsource(_xapian.DatabaseTermFreqSource(self._conn._index))

        if fields is not None:
            ds.set_expand_decider(self._make_expand_decider(fields))

        tophits = []
        nottophits = []
        full = False
        reordered = False

        sim_count = 0
        new_order = []
        end = min(self.endrank, maxcount)
        for i in xrange(end):
            if full:
                new_order.append(i)
                continue
            hit = self._mset.get_hit(i)
            if len(tophits) == 0:
                tophits.append(hit)
                continue

            # Compare each incoming hit to tophits
            maxsim = 0.0
            for tophit in tophits[-1:]:
                sim_count += 1
                sim = ds.similarity(hit.document, tophit.document)
                if sim > maxsim:
                    maxsim = sim

            # If it's not similar to an existing hit, add to tophits.
            if maxsim < max_similarity:
                tophits.append(hit)
            else:
                nottophits.append(hit)
                reordered = True

            # If we're full of hits, append to the end.
            if len(tophits) >= count:
                for hit in tophits:
                    new_order.append(hit.rank)
                for hit in nottophits:
                    new_order.append(hit.rank)
                full = True
        if not full:
            for hit in tophits:
                new_order.append(hit.rank)
            for hit in nottophits:
                new_order.append(hit.rank)
        if end != self.endrank:
            new_order.extend(range(end, self.endrank))
        assert len(new_order) == self.endrank
        if reordered:
            self._mset_order = new_order
        else:
            assert new_order == range(self.endrank)

    def __repr__(self):
        return ("<SearchResults(startrank=%d, "
                "endrank=%d, "
                "more_matches=%s, "
                "matches_lower_bound=%d, "
                "matches_upper_bound=%d, "
                "matches_estimated=%d, "
                "estimate_is_exact=%s)>" %
                (
                 self.startrank,
                 self.endrank,
                 self.more_matches,
                 self.matches_lower_bound,
                 self.matches_upper_bound,
                 self.matches_estimated,
                 self.estimate_is_exact,
                ))

    def _get_more_matches(self):
        # This check relies on us having asked for at least one more result
        # than retrieved to be checked.
        return (self.matches_lower_bound > self.endrank)
    more_matches = property(_get_more_matches, doc=
    """Check whether there are further matches after those in this result set.

    """)

    def _get_startrank(self):
        return self._mset.get_firstitem()
    startrank = property(_get_startrank, doc=
    """Get the rank of the first item in the search results.

    This corresponds to the "startrank" parameter passed to the search() method.

    """)

    def _get_endrank(self):
        return self._mset.get_firstitem() + len(self._mset)
    endrank = property(_get_endrank, doc=
    """Get the rank of the item after the end of the search results.

    If there are sufficient results in the index, this corresponds to the
    "endrank" parameter passed to the search() method.

    """)

    def _get_lower_bound(self):
        return self._mset.get_matches_lower_bound()
    matches_lower_bound = property(_get_lower_bound, doc=
    """Get a lower bound on the total number of matching documents.

    """)

    def _get_upper_bound(self):
        return self._mset.get_matches_upper_bound()
    matches_upper_bound = property(_get_upper_bound, doc=
    """Get an upper bound on the total number of matching documents.

    """)

    def _get_human_readable_estimate(self):
        lower = self._mset.get_matches_lower_bound()
        upper = self._mset.get_matches_upper_bound()
        est = self._mset.get_matches_estimated()
        return _get_significant_digits(est, lower, upper)
    matches_human_readable_estimate = property(_get_human_readable_estimate,
                                               doc=
    """Get a human readable estimate of the number of matching documents.

    This consists of the value returned by the "matches_estimated" property,
    rounded to an appropriate number of significant digits (as determined by
    the values of the "matches_lower_bound" and "matches_upper_bound"
    properties).

    """)

    def _get_estimated(self):
        return self._mset.get_matches_estimated()
    matches_estimated = property(_get_estimated, doc=
    """Get an estimate for the total number of matching documents.

    """)

    def _estimate_is_exact(self):
        return self._mset.get_matches_lower_bound() == \
               self._mset.get_matches_upper_bound()
    estimate_is_exact = property(_estimate_is_exact, doc=
    """Check whether the estimated number of matching documents is exact.

    If this returns true, the estimate given by the `matches_estimated`
    property is guaranteed to be correct.

    If this returns false, it is possible that the actual number of matching
    documents is different from the number given by the `matches_estimated`
    property.

    """)

    def get_hit(self, index):
        """Get the hit with a given index.

        """
        if self._mset_order is None:
            msetitem = self._mset.get_hit(index)
        else:
            msetitem = self._mset.get_hit(self._mset_order[index])
        return SearchResult(msetitem, self)

    def __getitem__(self, index_or_slice):
        """Get an item, or slice of items.

        """
        if isinstance(index_or_slice, slice):
            start, stop, step = index_or_slice.indices(len(self._mset))
            return map(self.get_hit, xrange(start, stop, step))
        else:
            return self.get_hit(index_or_slice)

    def __iter__(self):
        """Get an iterator over the hits in the search result.

        The iterator returns the results in increasing order of rank.

        """
        return SearchResultIter(self, self._mset_order)

    def __len__(self):
        """Get the number of hits in the search result.

        Note that this is not (usually) the number of matching documents for
        the search.  If startrank is non-zero, it's not even the rank of the
        last document in the search result.  It's simply the number of hits
        stored in the search result.

        It is, however, the number of items returned by the iterator produced
        by calling iter() on this SearchResults object.

        """
        return len(self._mset)

    def get_suggested_facets(self, maxfacets=5, desired_num_of_categories=7,
                             required_facets=None):
        """Get a suggested set of facets, to present to the user.

        This returns a list, in descending order of the usefulness of the
        facet, in which each item is a tuple holding:

         - fieldname of facet.
         - sequence of 2-tuples holding the suggested values or ranges for that
           field:

           For facets of type 'string', the first item in the 2-tuple will
           simply be the string supplied when the facet value was added to its
           document.  For facets of type 'float', it will be a 2-tuple, holding
           floats giving the start and end of the suggested value range.

           The second item in the 2-tuple will be the frequency of the facet
           value or range in the result set.

        If required_facets is not None, it must be a field name, or a sequence
        of field names.  Any field names mentioned in required_facets will be
        returned if there are any facet values at all in the search results for
        that field.  The facet will only be omitted if there are no facet
        values at all for the field.

        The value of maxfacets will be respected as far as possible; the
        exception is that if there are too many fields listed in
        required_facets with at least one value in the search results, extra
        facets will be returned (ie, obeying the required_facets parameter is
        considered more important than the maxfacets parameter).

        If facet_hierarchy was indicated when search() was called, and the
        query included facets, then only subfacets of those query facets and
        top-level facets will be included in the returned list.  Furthermore
        top-level facets will only be returned if there are remaining places
        in the list after it has been filled with subfacets.  Note that
        required_facets is still respected regardless of the facet hierarchy.

        If a query type was specified when search() was called, and the query
        included facets, then facets with an association of Never to the
        query type are never returned, even if mentioned in required_facets.
        Facets with an association of Preferred are listed before others in
        the returned list.

        """
        if 'facets' in _checkxapian.missing_features:
            raise errors.SearchError("Facets unsupported with this release of xapian")
        if self._facetspies is None:
            raise _errors.SearchError("Facet selection wasn't enabled when the search was run")
        if isinstance(required_facets, basestring):
            required_facets = [required_facets]
        scores = []
        facettypes = {}
        for field, slot, kwargslist in self._facetfields:
            type = None
            for kwargs in kwargslist:
                type = kwargs.get('type', None)
                if type is not None: break
            if type is None: type = 'string'

            if field not in self._facetvalues:
                facetspy = self._facetspies.get(slot)
                if facetspy is None:
                    self._facetvalues[field] = []
                else:
                    if type == 'float':
                        self._facetvalues[field] = _xapian.NumericRanges(facetspy.get_values(), desired_num_of_categories)
                    else:
                        self._facetvalues[field] = facetspy

            facettypes[field] = type
            if isinstance(self._facetvalues[field], _xapian.NumericRanges):
                score = _xapian.score_evenness(self._facetvalues[field].get_ranges(),
                                               self._facetvalues[field].get_values_seen(),
                                               desired_num_of_categories)
            else:
                score = _xapian.score_evenness(self._facetvalues[field], desired_num_of_categories)
            scores.append((score, field, slot))

        # Sort on whether facet is top-level ahead of score (use subfacets first),
        # and on whether facet is preferred for the query type ahead of anything else
        if self._facethierarchy:
            # Note, tuple[-2] is the value of 'field' in a scores tuple
            scores = [(tuple[-2] not in self._facethierarchy,) + tuple for tuple in scores]
        if self._facetassocs:
            preferred = IndexerConnection.FacetQueryType_Preferred
            scores = [(self._facetassocs.get(tuple[-2]) != preferred,) + tuple for tuple in scores]
        scores.sort()
        if self._facethierarchy:
            index = 1
        else:
            index = 0
        if self._facetassocs:
            index += 1
        if index > 0:
            scores = [tuple[index:] for tuple in scores]

        results = []
        required_results = []
        for score, field, slot in scores:
            # Check if the facet is required
            required = False
            if required_facets is not None:
                required = field in required_facets

            # If we've got enough facets, and the field isn't required, skip it
            if not required and len(results) + len(required_results) >= maxfacets:
                continue

            # Get the values
            values = self._facetvalues[field]
            if isinstance(values, _xapian.MatchSpy):
                values = values.get_values_as_dict()
            elif isinstance(values, _xapian.NumericRanges):
                values = values.get_ranges_as_dict()

            # Required facets must occur at least once, other facets must occur
            # at least twice.
            if required:
                if len(values) < 1:
                    continue
            else:
                if len(values) <= 1:
                    continue

            newvalues = []
            if facettypes[field] == 'float':
                # Convert numbers to python numbers, and number ranges to a
                # python tuple of two numbers.
                for (value1, value2), frequency in values.iteritems():
                    newvalues.append(((value1, value2), frequency))
            else:
                for value, frequency in values.iteritems():
                    newvalues.append((value, frequency))

            newvalues.sort()
            if required:
                required_results.append((score, field, newvalues))
            else:
                results.append((score, field, newvalues))

        # Throw away any excess results if we have more required_results to
        # insert.
        maxfacets = maxfacets - len(required_results)
        if maxfacets <= 0:
            results = required_results
        else:
            results = results[:maxfacets]
            results.extend(required_results)
            results.sort()

        # Throw away the scores because they're not meaningful outside this
        # algorithm.
        results = [(field, newvalues) for (score, field, newvalues) in results]
        return results

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
    _qp_flags_wildcard = _xapian.QueryParser.FLAG_WILDCARD
    _qp_flags_base = _xapian.QueryParser.FLAG_LOVEHATE
    _qp_flags_phrase = _xapian.QueryParser.FLAG_PHRASE
    _qp_flags_synonym = (_xapian.QueryParser.FLAG_AUTO_SYNONYMS |
                         _xapian.QueryParser.FLAG_AUTO_MULTIWORD_SYNONYMS)
    _qp_flags_bool = _xapian.QueryParser.FLAG_BOOLEAN

    _index = None

    def __init__(self, indexpath):
        """Create a new connection to the index for searching.

        There may only an arbitrary number of search connections for a
        particular database open at a given time (regardless of whether there
        is a connection for indexing open as well).

        If the database doesn't exist, an exception will be raised.

        """
        self._indexpath = indexpath
        self._close_handlers = []
        self._index = _xapian.Database(indexpath)
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
        for field, actions in self._field_actions.iteritems():
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
            except _xapian.DatabaseModifiedError, e:
                # Don't call self.reopen() since that calls _load_config()!
                self._index.reopen()

        if len(config_str) == 0:
            self._field_actions = ActionSet()
            self._field_mappings = _fieldmappings.FieldMappings()
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
        self._field_mappings = _fieldmappings.FieldMappings(mappings)

    def reopen(self):
        """Reopen the connection.

        This updates the revision of the index which the connection references
        to the latest flushed revision.

        """
        if self._index is None:
            raise _errors.SearchError("SearchConnection has been closed")
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
            raise _errors.SearchError("SearchConnection has been closed")
        return self._index.get_doccount()

    OP_AND = Query.OP_AND
    OP_OR = Query.OP_OR
    def query_composite(self, operator, queries):
        """Build a composite query from a list of queries.

        The queries are combined with the supplied operator, which is either
        SearchConnection.OP_AND or SearchConnection.OP_OR.

        """
        if self._index is None:
            raise _errors.SearchError("SearchConnection has been closed")
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
            raise _errors.SearchError("SearchConnection has been closed")
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
            raise _errors.SearchError("SearchConnection has been closed")
        try:
            if exclude:
                return query.and_not(filter)
            else:
                return query.filter(filter)
        except TypeError:
            raise _errors.SearchError("Filter must be a Xapian Query object")

    def query_adjust(self, primary, secondary):
        """Adjust the weights of one query with a secondary query.

        Documents will be returned from the resulting query if and only if they
        match the primary query (specified by the "primary" parameter).
        However, the weights (and hence, the relevance rankings) of the
        documents will be adjusted by adding weights from the secondary query
        (specified by the "secondary" parameter).

        """
        if self._index is None:
            raise _errors.SearchError("SearchConnection has been closed")
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
            queries.append(Query(_xapian.Query(term), _conn=self,
                                 _ranges=query_ranges))
        return Query.compose(_xapian.Query.OP_OR, queries)

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
            return Query(_xapian.Query(''), _conn=self,
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
            for argname in argnames[1:-len(defaultargs)]:
                args.append(repr(values[argname]))
            if len(defaultargs) > 0:
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
            raise _errors.SearchError("SearchConnection has been closed")

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
            return Query(_xapian.Query(), _conn=self,
                         _serialised=serialised)

        if begin is None and end is None:
            # Return a query which matches everything with a non-empty value in
            # the slot.

            # FIXME - this can probably be done more efficiently when streamed
            # values are stored in the database, but I don't think Xapian
            # exposes a useful interface for this currently.
            return Query(_xapian.Query(_xapian.Query.OP_VALUE_GE, slot, '\x00'),
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
            result = Query(_xapian.Query(_xapian.Query.OP_VALUE_LE, slot,
                                         marshalled_end),
                           _conn=self, _ranges=query_ranges)
        elif marshalled_end is None:
            result = Query(_xapian.Query(_xapian.Query.OP_VALUE_GE, slot,
                                         marshalled_begin),
                           _conn=self, _ranges=query_ranges)
        else:
            result = Query(_xapian.Query(_xapian.Query.OP_VALUE_RANGE, slot,
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
            postingsource = _xapian.FixedWeightPostingSource(scale)
            fixedwt_query = Query(_xapian.Query(postingsource),
                           _refs=[postingsource], _conn=self)
            return fixedwt_query.filter(Query(_xapian.Query(term), _conn = self))


        queries = [make_query(scale, low_val, hi_val) for
                   scale, low_val, hi_val in scales_and_ranges]

        return Query.compose(_xapian.Query.OP_OR, queries)

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
            raise _errors.SearchError("SearchConnection has been closed")
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
                    doc_val = _xapian.sortable_unserialise(
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
            raise _errors.SearchError("SearchConnection has been closed")

        serialised = self._make_parent_func_repr("query_distance")

        metric = _xapian.GreatCircleMetric()

        # Build the list of coordinates
        coords = _xapian.LatLongCoords()
        if isinstance(centre, basestring):
            coords.insert(_xapian.LatLongCoord.parse_latlong(centre))
        else:
            for coord in centre:
                coords.insert(_xapian.LatLongCoord.parse_latlong(coord))

        # Get the slot
        try:
            slot = self._field_mappings.get_slot(field, 'loc')
        except KeyError:
            # Return a "match nothing" query
            return Query(_xapian.Query(), _conn=self,
                         _serialised=serialised)

        # Make the posting source
        postingsource = _xapian.LatLongDistancePostingSource(
            slot, coords, metric, max_range, k1, k2)

        result = Query(_xapian.Query(postingsource),
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
            raise _errors.SearchError(
                "Exactly one of image, docid or xapid is required for"
                " query_image_similarity().")

        actions =  self._field_actions[field]._actions
        terms = actions[FieldActions.IMGSEEK][0]['terms']
        if image:
            # Build a signature from an image.
            try:
                sig = xapian.imgseek.ImgSig.register_Image(image)
            except xapian.InvalidArgumentError:
                raise _errors.SearchError(
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
            return Query(_xapian.Query(), _conn=self,
                         _serialised=serialised)

        ps = xapian.imgseek.ImgSigSimilarityPostingSource(sigs, slot)
        result = Query(_xapian.Query(ps),
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
            raise _errors.SearchError("SearchConnection has been closed")
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
                return Query(_xapian.Query(), _conn=self,
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

            result = Query(_xapian.Query(_xapian.Query.OP_VALUE_RANGE, slot,
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
            result = Query(_xapian.Query(prefix + val.lower()), _conn=self) * 0
            result._set_serialised(serialised)
            return result

    def _prepare_queryparser(self, allow, deny, default_op, default_allow,
                             default_deny):
        """Prepare (and return) a query parser using the specified fields and
        operator.

        """
        if self._index is None:
            raise _errors.SearchError("SearchConnection has been closed")

        if isinstance(allow, basestring):
            allow = (allow, )
        if isinstance(deny, basestring):
            deny = (deny, )
        if allow is not None and len(allow) == 0:
            allow = None
        if deny is not None and len(deny) == 0:
            deny = None
        if allow is not None and deny is not None:
            raise _errors.SearchError("Cannot specify both `allow` and `deny` "
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
            raise _errors.SearchError("Cannot specify both `default_allow` and `default_deny` "
                                      "(got %r and %r)" % (default_allow, default_deny))

        qp = _xapian.QueryParser()
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
                            my_stemmer = _xapian.Stem(lang)
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
            base_flags |= _qp_flags_wildcard 
        try:
            q1 = self._query_parse_with_prefix(qp, string,
                                               base_flags |
                                               self._qp_flags_phrase |
                                               self._qp_flags_synonym |
                                               self._qp_flags_bool,
                                               prefix)
        except _xapian.QueryParserError, e:
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
        except _xapian.QueryParserError, e:
            # If we got a parse error, retry without boolean operators (since
            # these are the usual cause of the parse error).
            q2 = self._query_parse_with_prefix(qp, string, base_flags, prefix)

        return Query(_xapian.Query(_xapian.Query.OP_AND_MAYBE, q1, q2),
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
            raise _errors.SearchError("SearchConnection has been closed")
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
                    raise _errors.SearchError("Supplied value must not be None")
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
                result = Query(_xapian.Query(prefix + value), _conn=self) * 0
                result._set_serialised(serialised)
                return result
            if action == FieldActions.INDEX_FREETEXT:
                if value is None:
                    raise _errors.SearchError("Supplied value must not be None")
                qp = _xapian.QueryParser()
                qp.set_default_op(default_op)
                prefix = self._field_mappings.get_prefix(field)
                for kwargs in kwargslist:
                    try:
                        lang = kwargs['language']
                        qp.set_stemmer(_xapian.Stem(lang))
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
                    raise _errors.SearchError("Value supplied for a WEIGHT field must be None")
                slot = self._field_mappings.get_slot(field, 'weight')
                postingsource = _xapian.ValueWeightPostingSource(slot)
                result = Query(_xapian.Query(postingsource),
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
        q = _xapian.Query(_xapian.Query.OP_ELITE_SET, xapterms, numterms)
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
            raise _errors.SearchError("SearchConnection has been closed")
        if allow is not None and deny is not None:
            raise _errors.SearchError("Cannot specify both `allow` and `deny`")

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
            except _xapian.DatabaseModifiedError, e:
                self.reopen()
        return eterms, prefixes

    class _ExpandDecider(_xapian.ExpandDecider):
        def __init__(self, prefixes):
            _xapian.ExpandDecider.__init__(self)
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
        idquery = _xapian.Query(_xapian.Query.OP_OR, ['Q' + id for id in ids])

        if tempdb is not None:
            combined_db = xapian.Database()
            combined_db.add_database(self._index)
            combined_db.add_database(tempdb)
        else:
            combined_db = self._index
        enq = _xapian.Enquire(combined_db)
        enq.set_query(idquery)
        rset = _xapian.RSet()
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
        class ExternalWeightPostingSource(_xapian.PostingSource):
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
        return Query(_xapian.Query(postingsource),
                     _refs=[postingsource], _conn=self, _serialised=serialised)

    def query_all(self, weight=None):
        """A query which matches all the documents in the database.

        Such a query will normally return a weight of 0 for each document.
        However, it can be made to return a specific, fixed, weight by passing
        in a `weight` parameter.

        """
        serialised = self._make_parent_func_repr("query_all")
        all_query = Query(_xapian.Query(''), _conn=self,
                          _serialised = serialised)
        if weight is not None and weight > 0:
            postingsource = _xapian.FixedWeightPostingSource(weight)
            fixedwt_query = Query(_xapian.Query(postingsource),
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

        return Query(_xapian.Query(_xapian.Query.OP_OR, terms),
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
        vars = {'conn': self, 'xappy': xappy, 'xapian': xapian}
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
            base_flags |= _qp_flags_wildcard 
        try:
            qp.parse_query(querystr,
                           base_flags |
                           self._qp_flags_bool |
                           qp.FLAG_SPELLING_CORRECTION)
        except _xapian.QueryParserError:
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
            raise _errors.SearchError("SearchConnection has been closed")
        try:
            self._field_mappings.get_slot(field, 'collsort')
        except KeyError:
            return False
        return True

    def can_sort_on(self, field):
        """Check if this database supports sorting on a specified field.

        """
        if self._index is None:
            raise _errors.SearchError("SearchConnection has been closed")
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
            raise _errors.SearchError("SearchConnection has been closed")
        enq = _xapian.Enquire(self._index)

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
            except _xapian.DatabaseModifiedError, e:
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
            raise _errors.SearchError("Field %r was not indexed for sorting" % slotspec)

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

    def search(self, query, startrank, endrank,
               checkatleast=0, sortby=None, collapse=None,
               getfacets=None, allowfacets=None, denyfacets=None, usesubfacets=None,
               percentcutoff=None, weightcutoff=None,
               query_type=None, weight_params=None, collapse_max=1):
        """Perform a search, for documents matching a query.

        - `query` is the query to perform.
        - `startrank` is the rank of the start of the range of matching
          documents to return (ie, the result with this rank will be returned).
          ranks start at 0, which represents the "best" matching document.
        - `endrank` is the rank at the end of the range of matching documents
          to return.  This is exclusive, so the result with this rank will not
          be returned.
        - `checkatleast` is the minimum number of results to check for: the
          estimate of the total number of matches will always be exact if
          the number of matches is less than `checkatleast`.  A value of ``-1``
          can be specified for the checkatleast parameter - this has the
          special meaning of "check all matches", and is equivalent to passing
          the result of get_doccount().
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
        - `query_type` is a value indicating the type of query being
          performed.  If not None, the value is used to influence which facets
          are be returned by the get_suggested_facets() function.  If the
          value of `getfacets` is False, it has no effect.
        - `weight_params` is a dictionary (from string to number) of named
          parameters to pass to the weighting function.  Currently, the
          defined names are "k1", "k2", "k3", "b", "min_normlen".  Any
          unrecognised names will be ignored.  For documentation of the
          parameters, see the docs/weighting.rst document.

        If neither 'allowfacets' or 'denyfacets' is specified, all fields
        holding facets will be considered (but see 'usesubfacets').

        """
        if self._index is None:
            raise _errors.SearchError("SearchConnection has been closed")

        serialised = self._make_parent_func_repr("search")

        if 'facets' in _checkxapian.missing_features:
            if getfacets is not None or \
               allowfacets is not None or \
               denyfacets is not None or \
               usesubfacets is not None or \
               query_type is not None:
                raise errors.SearchError("Facets unsupported with this release of xapian")
        if checkatleast == -1:
            checkatleast = self._index.get_doccount()

        enq = _xapian.Enquire(self._index)
        if isinstance(query, xapian.Query):
            enq.set_query(query)
        else:
            enq.set_query(query._get_xapian_query())

        if sortby is not None:
            if isinstance(sortby, basestring):
                enq.set_sort_by_value_then_relevance(
                    *self._get_sort_slot_and_dir(sortby))
            elif isinstance(sortby, self.SortByGeolocation):
                # Get the slot
                try:
                    slot = self._field_mappings.get_slot(sortby.fieldname, 'loc')
                except KeyError:
                    # Return a "match nothing" query
                    return Query(_xapian.Query(), _conn=self,
                                 _serialised=serialised)

                # Get the coords
                coords = _xapian.LatLongCoords()
                if isinstance(sortby.centre, basestring):
                    coords.insert(_xapian.LatLongCoord.parse_latlong(sortby.centre))
                else:
                    for coord in sortby.centre:
                        coords.insert(_xapian.LatLongCoord.parse_latlong(coord))

                # Make and use the sorter
                metric = _xapian.GreatCircleMetric()
                sorter = _xapian.LatLongDistanceSorter(slot, coords, metric)
                enq.set_sort_by_key_then_relevance(sorter, False)
            else:
                sorter = xapian.MultiValueSorter()
                for field in sortby:
                    sorter.add(*self._get_sort_slot_and_dir(field))
                enq.set_sort_by_key_then_relevance(sorter, True)

        if collapse is not None:
            try:
                collapse_slotnum = self._field_mappings.get_slot(collapse, 'collsort')
            except KeyError:
                raise _errors.SearchError("Field %r was not indexed for collapsing" % collapse)
            if collapse_max == 1:
                # Backwards compatibility - only this form existed before 1.1.0
                enq.set_collapse_key(collapse_slotnum)
            else:
                enq.set_collapse_key(collapse_slotnum, collapse_max)

        maxitems = max(endrank - startrank, 0)
        # Always check for at least one more result, so we can report whether
        # there are more matches.
        checkatleast = max(checkatleast, endrank + 1)

        # add a matchspy for facet selection here.
        facetspies = None
        facetfields = []
        if getfacets:
            # Set facetspies to {}, even if no facet fields are found, to
            # distinguish from no facet calculation being performed.  (This
            # will prevent an error being thrown when the list of suggested
            # facets is requested - instead, an empty list will be returned.)
            facetspies = {}
            if allowfacets is not None and denyfacets is not None:
                raise _errors.SearchError("Cannot specify both `allowfacets` and `denyfacets`")
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
                        facettype = None
                        for kwargs in kwargslist:
                            facettype = kwargs.get('type', None)
                            if facettype is not None:
                                break
                        if facettype is None or facettype == 'string':
                            facetspy = _xapian.MultiValueCountMatchSpy(slot)
                        else:
                            facetspy = _xapian.ValueCountMatchSpy(slot)
                        enq.add_matchspy(facetspy)
                        facetspies[slot] = facetspy
                        facetfields.append((field, slot, kwargslist))

        enq.set_docid_order(enq.DONT_CARE)

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
                mset = enq.get_mset(startrank, maxitems, checkatleast)
                break
            except _xapian.DatabaseModifiedError, e:
                self.reopen()
        facet_hierarchy = None
        if usesubfacets:
            facet_hierarchy = self._facet_hierarchy

        res = SearchResults(self, enq, query, mset, self._field_mappings,
                            facetspies, facetfields,
                            facet_hierarchy,
                            self._facet_query_table.get(query_type))

        if collapse is not None:
            res.collapse_slotnum = collapse_slotnum
            res.collapse_max = collapse_max

        return res

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
            raise _errors.SearchError("SearchConnection has been closed")
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
            raise _errors.SearchError("SearchConnection has been closed")
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
            raise _errors.SearchError("SearchConnection has been closed")
        while True:
            try:
                if docid is not None:
                    if xapid is not None:
                        raise _errors.SearchError("Only one of docid and xapid"
                                                  " should be set")
                    postlist = self._index.postlist('Q' + docid)
                    try:
                        plitem = postlist.next()
                    except StopIteration:
                        # Unique ID not found
                        raise KeyError('Unique ID %r not found' % docid)
                    try:
                        postlist.next()
                        raise _errors.IndexerError("Multiple documents "
                                                   "found with same unique ID: %r" % docid)
                    except StopIteration:
                        # Only one instance of the unique ID found, as it
                        # should be.
                        pass
                    xapid = plitem.docid
                if xapid is None:
                    raise _errors.SearchError("Either docid or xapid must be "
                                              "set")

                result = ProcessedDocument(self._field_mappings)
                result._doc = self._index.get_document(xapid)
                return result
            except _xapian.DatabaseModifiedError, e:
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
            raise _errors.SearchError("SearchConnection has been closed")
        return SynonymIter(self._index, self._field_mappings, prefix)

    def get_metadata(self, key):
        """Get an item of metadata stored in the connection.

        This returns a value stored by a previous call to
        IndexerConnection.set_metadata.

        If the value is not found, this will return the empty string.

        """
        if self._index is None:
            raise _errors.IndexerError("SearchConnection has been closed")
        if not hasattr(self._index, 'get_metadata'):
            raise _errors.IndexerError("Version of xapian in use does not support metadata")
        while True:
            try:
                return self._index.get_metadata(key)
            except _xapian.DatabaseModifiedError, e:
                self.reopen()

    def iter_terms_for_field(self, field, starts_with=''):
        """Return an iterator over the terms that a field has in the index.

        Values are returned in sorted order (sorted by lexicographical binary
        sort order of the UTF-8 encoded version of the term).

        """
        if self._index is None:
            raise _errors.IndexerError("SearchConnection has been closed")
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

        return Query(_xapian.Query(ps),
                     _refs=[ps], _conn=self,
                     _serialised=serialised)

if __name__ == '__main__':
    import doctest, sys
    doctest.testmod(sys.modules[__name__])
