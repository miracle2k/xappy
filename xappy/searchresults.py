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
from datastructures import UnprocessedDocument, ProcessedDocument
from fieldactions import FieldActions
from fields import Field
import highlight
import errors
from indexerconnection import IndexerConnection
import re
from utils import get_significant_digits, add_to_dict_of_dicts

class SearchResultContext(object):
    """A context used by SearchResult objects to get various pieces of
    information about the search.

    """
    def __init__(self, conn, field_mappings, term_weights, query):
        """Initialise a context.

         - `conn`: the SearchConnection used.
         - `field_mappings`: the mappings from field names to prefixes and
           slots.
         - `term_weights`: an object used to get term weights.
         - `query`: the query which was performed.

        """
        self.conn = conn
        self.field_mappings = field_mappings
        self.term_weights = term_weights
        self.query = query

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
    def __init__(self, msetitem, context):
        ProcessedDocument.__init__(self, context.field_mappings, msetitem.document)
        self.rank = msetitem.rank
        self.weight = msetitem.weight
        self.percent = msetitem.percent
        self._term_weights = context.term_weights
        self._conn = context.conn
        self._query = context.query

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
        actions = self._conn._field_actions[field]._actions
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
        conn = self._conn
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
            actions = self._conn._field_actions[field]._actions
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
                queryweights[term] = self._term_weights.get(term)
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
            hl = highlight.Highlighter(language_code=self._get_language(field))
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
            raise errors.SearchError("Cannot specify both `allow` and `deny` "
                                     "(got %r and %r)" % (allow, deny))
        if allow is None:
            allow = [key for key in self._conn._field_actions]
        if deny is not None:
            allow = [key for key in allow if key not in deny]

        allow = list(allow)
        allow.sort()

        if query is None:
            query = self._query

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
        highlighter = highlight.Highlighter(language_code=self._get_language(field))
        field = self.data[field]
        results = []
        text = '\n'.join(field)
        if query is None:
            query = self._query
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
        highlighter = highlight.Highlighter(language_code=self._get_language(field))
        field = self.data[field]
        results = []
        if query is None:
            query = self._query
        for text in field:
            results.append(highlighter.highlight(text, query, hl, strip_tags))
        return results

    def __repr__(self):
        return ('<SearchResult(rank=%d, id=%r, data=%r)>' %
                (self.rank, self.id, self.data))


class MSetTermWeightGetter(object):
    """Object for getting termweights directly from an mset.

    """
    def __init__(self, mset):
        self.mset = mset

    def get(self, term):
        return self.mset.get_termweight(term)


class MSetSearchResultIter(object):
    """An iterator over a set of results from a search.

    """
    def __init__(self, mset, context):
        self.context = context
        self.it = iter(mset)

    def next(self):
        return SearchResult(self.it.next(), self.context)


class MSetResultOrdering(object):
    def __init__(self, mset, context):
        self.mset = mset
        self.context = context

    def get_iter(self):
        """Get an iterator over the search results.

        """
        return MSetSearchResultIter(self.mset, self.context)

    def get_hit(self, index):
        """Get the hit with a given index.

        """
        msetitem = self.mset.get_hit(index)
        return SearchResult(msetitem, self.context)

    def __len__(self):
        """Get the number of items in this ordering.

        """
        return len(self.mset)

class MSetResultStats(object):
    def __init__(self, mset):
        self.mset = mset

    def get_startrank(self):
        return self.mset.get_firstitem()

    def get_endrank(self):
        return self.mset.get_firstitem() + len(self.mset)

    def get_lower_bound(self):
        return self.mset.get_matches_lower_bound()

    def get_upper_bound(self):
        return self.mset.get_matches_upper_bound()

    def get_estimated(self):
        return self.mset.get_matches_estimated()

class ReorderedMSetSearchResultIter(object):
    """An iterator over a set of results from a search which have been
    reordered.

    """
    def __init__(self, mset, order, context):
        self.mset = mset
        self.order = order
        self.context = context
        self.it = iter(self.order)

    def next(self):
        index = self.it.next()
        msetitem = self.mset.get_hit(index)
        return SearchResult(msetitem, self.context)


class ReorderedMSetResultOrdering(object):
    def __init__(self, mset, mset_order, context):
        self.mset = mset
        self.mset_order = mset_order
        self.context = context

    def get_iter(self):
        """Get an iterator over the search results.

        """
        return ReorderedMSetSearchResultIter(self.mset, self.mset_order,
                                             self.context)

    def get_hit(self, index):
        """Get the hit with a given index.

        """
        msetitem = self.mset.get_hit(self.mset_order[index])
        return SearchResult(msetitem, self.context)

    def __len__(self):
        """Get the number of items in this ordering.

        """
        return len(self.mset_order)

class SearchResults(object):
    """A set of results of a search.

    """
    def __init__(self, conn, query, field_mappings,
                 facets,
                 ordering, stats, mset, context):
        self._conn = conn
        self._query = query
        self._ordering = ordering
        self._stats = stats
        self._mset = mset
        self._context = context
        self._field_mappings = field_mappings
        self._facets = facets

    def _cluster(self, num_clusters, maxdocs, fields=None,
                 assume_single_value=False):
        """Cluster results based on similarity.

        Note: this method is experimental, and will probably disappear or
        change in the future.

        The number of clusters is specified by num_clusters: unless there are
        too few results, there will be exaclty this number of clusters in the
        result.

        """
        clusterer = xapian.ClusterSingleLink()
        xapclusters = xapian.ClusterAssignments()
        docsim = xapian.DocSimCosine()
        source = xapian.MSetDocumentSource(self._mset, maxdocs)

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
            raise errors.SearchError("startrank must be zero to reorder by collapse")
        if not hasattr(self, "collapse_max"):
            raise errors.SearchError("A collapse must have been performed on the search in order to use _reorder_by_collapse")

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

        self._ordering = ReorderedMSetResultOrdering(self._mset, new_order,
                                                     self._context)

    def _reorder_by_clusters(self, clusters):
        """Reorder the mset based on some clusters.

        """
        if self.startrank != 0:
            raise errors.SearchError("startrank must be zero to reorder by clusters")
        tophits = []
        nottophits = []

        clusterstarts = dict(((c[0], None) for c in clusters.itervalues()))
        for i in xrange(self.endrank):
            if i in clusterstarts:
                tophits.append(i)
            else:
                nottophits.append(i)
        new_order = tophits
        new_order.extend(nottophits)
        self._ordering = ReorderedMSetResultOrdering(self._mset, new_order,
                                                     self._context)

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
        prefix_re = re.compile('|'.join([re.escape(x) + '[^A-Z]' for x in prefixes.keys()]))
        class decider(xapian.ExpandDecider):
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
            raise errors.SearchError("startrank must be zero to reorder by similiarity")
        ds = xapian.DocSimCosine()
        ds.set_termfreqsource(xapian.DatabaseTermFreqSource(self._conn._index))

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
            self._ordering = ReorderedMSetResultOrdering(self._mset, new_order,
                                                         self._context)
        else:
            assert new_order == range(self.endrank)
            self._ordering = MSetResultOrdering(self._mset)

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
        return self._stats.get_startrank()
    startrank = property(_get_startrank, doc=
    """Get the rank of the first item in the search results.

    This corresponds to the "startrank" parameter passed to the search() method.

    """)

    def _get_endrank(self):
        return self._stats.get_endrank()
    endrank = property(_get_endrank, doc=
    """Get the rank of the item after the end of the search results.

    If there are sufficient results in the index, this corresponds to the
    "endrank" parameter passed to the search() method.

    """)

    def _get_lower_bound(self):
        return self._stats.get_lower_bound()
    matches_lower_bound = property(_get_lower_bound, doc=
    """Get a lower bound on the total number of matching documents.

    """)

    def _get_upper_bound(self):
        return self._stats.get_upper_bound()
    matches_upper_bound = property(_get_upper_bound, doc=
    """Get an upper bound on the total number of matching documents.

    """)

    def _get_human_readable_estimate(self):
        lower = self._stats.get_lower_bound()
        upper = self._stats.get_upper_bound()
        est = self._stats.get_estimated()
        return get_significant_digits(est, lower, upper)
    matches_human_readable_estimate = property(_get_human_readable_estimate,
                                               doc=
    """Get a human readable estimate of the number of matching documents.

    This consists of the value returned by the "matches_estimated" property,
    rounded to an appropriate number of significant digits (as determined by
    the values of the "matches_lower_bound" and "matches_upper_bound"
    properties).

    """)

    def _get_estimated(self):
        return self._stats.get_estimated()
    matches_estimated = property(_get_estimated, doc=
    """Get an estimate for the total number of matching documents.

    """)

    def _estimate_is_exact(self):
        return self._stats.get_lower_bound() == \
               self._stats.get_upper_bound()
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
        return self._ordering.get_hit(index)

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
        return self._ordering.get_iter()

    def __len__(self):
        """Get the number of hits in the search result.

        Note that this is not (usually) the number of matching documents for
        the search.  If startrank is non-zero, it's not even the rank of the
        last document in the search result.  It's simply the number of hits
        stored in the search result.

        It is, however, the number of items returned by the iterator produced
        by calling iter() on this SearchResults object.

        """
        return len(self._ordering)

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
        return self._facets.get_suggested_facets(maxfacets,
                                                 desired_num_of_categories,
                                                 required_facets)

class MSetFacetResults(object):
    """The result of counting facets.

    """
    def __init__(self, facetspies, facetfields, facethierarchy, facetassocs):
        self.facetspies = facetspies
        self.facetfields = facetfields
        self.facethierarchy = facethierarchy
        self.facetassocs = facetassocs

        self.facetvalues = {}

    def get_suggested_facets(self, maxfacets,
                             desired_num_of_categories,
                             required_facets):
        """Get the suggested facets.  Parameters and return value are as for
        `SearchResults.get_suggested_facets()`.

        """
        if 'facets' in _checkxapian.missing_features:
            raise errors.SearchError("Facets unsupported with this release of xapian")
        if self.facetspies is None:
            raise errors.SearchError("Facet selection wasn't enabled when the search was run")
        if isinstance(required_facets, basestring):
            required_facets = [required_facets]
        scores = []
        facettypes = {}
        for field, slot, kwargslist in self.facetfields:
            type = None
            for kwargs in kwargslist:
                type = kwargs.get('type', None)
                if type is not None: break
            if type is None: type = 'string'

            if field not in self.facetvalues:
                facetspy = self.facetspies.get(slot)
                if facetspy is None:
                    self.facetvalues[field] = []
                else:
                    if type == 'float':
                        self.facetvalues[field] = xapian.NumericRanges(facetspy.get_values(), desired_num_of_categories)
                    else:
                        self.facetvalues[field] = facetspy

            facettypes[field] = type
            if isinstance(self.facetvalues[field], xapian.NumericRanges):
                score = xapian.score_evenness(self.facetvalues[field].get_ranges(),
                                              self.facetvalues[field].get_values_seen(),
                                              desired_num_of_categories)
            else:
                score = xapian.score_evenness(self.facetvalues[field], desired_num_of_categories)
            scores.append((score, field, slot))

        # Sort on whether facet is top-level ahead of score (use subfacets first),
        # and on whether facet is preferred for the query type ahead of anything else
        if self.facethierarchy:
            # Note, tuple[-2] is the value of 'field' in a scores tuple
            scores = [(tuple[-2] not in self.facethierarchy,) + tuple for tuple in scores]
        if self.facetassocs:
            preferred = IndexerConnection.FacetQueryType_Preferred
            scores = [(self.facetassocs.get(tuple[-2]) != preferred,) + tuple for tuple in scores]
        scores.sort()
        if self.facethierarchy:
            index = 1
        else:
            index = 0
        if self.facetassocs:
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
            values = self.facetvalues[field]
            if isinstance(values, xapian.MatchSpy):
                values = values.get_values_as_dict()
            elif isinstance(values, xapian.NumericRanges):
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
