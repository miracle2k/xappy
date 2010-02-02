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
r"""mset_search_results.py: The results of a search performed against xapian.

"""
__docformat__ = "restructuredtext en"

import _checkxapian

import errors
from fieldactions import FieldActions
from indexerconnection import IndexerConnection
import re
from searchresults import SearchResult
import xapian

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
    def __init__(self, mset, context, connection):
        self.mset = mset
        self.context = context
        self._conn = connection

    def get_iter(self):
        """Get an iterator over the search results.

        """
        return MSetSearchResultIter(self.mset, self.context)

    def get_hit(self, index):
        """Get the hit with a given index.

        """
        msetitem = self.mset.get_hit(index)
        return SearchResult(msetitem, self.context)

    def get_startrank(self):
        return self.mset.get_firstitem()

    def get_endrank(self):
        return self.mset.get_firstitem() + len(self.mset)

    def __len__(self):
        """Get the number of items in this ordering.

        """
        return len(self.mset)

    def _cluster(self, num_clusters, maxdocs, fields, assume_single_value):
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
        source = xapian.MSetDocumentSource(self.mset, maxdocs)

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
        for item in self.mset:
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

    def _reorder_by_collapse(self, highest_possible_percentage):
        """Reorder the result by the values in the slot used to collapse on.

        `highest_possible_percentage` is a tuning variable - we need to get an
        estimate of the probability that a particular hit satisfies the query.
        We use the relevance score for this estimate, but this requires us to
        pick a value for the top hit.  This variable specifies that percentage.

        """

        if self.mset.get_firstitem() != 0:
            raise errors.SearchError("startrank must be zero to reorder by collapse")
        if not hasattr(self, "collapse_max"):
            raise errors.SearchError("A collapse must have been performed on the search in order to use _reorder_by_collapse")

        if self.collapse_max == 1:
            # No reordering to do - we're already fully diverse according to
            # the values in the slot.
            return

        if self.mset.get_firstitem() + len(self.mset) <= 1:
            # No reordering to do - 0 or 1 items.
            return

        topweight = self.mset.get_hit(0).weight
        toppct = self.mset.get_hit(0).percent
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
        for i in xrange(self.mset.get_firstitem() + len(self.mset)):
            hit = self.mset.get_hit(i)
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

        return ReorderedMSetResultOrdering(self.mset, new_order, self.context)

    def _reorder_by_clusters(self, clusters):
        """Reorder the mset based on some clusters.

        """
        if self.mset.get_firstitem() != 0:
            raise errors.SearchError("startrank must be zero to reorder by clusters")
        tophits = []
        nottophits = []

        clusterstarts = dict(((c[0], None) for c in clusters.itervalues()))
        for i in xrange(self.mset.get_firstitem() + len(self.mset)):
            if i in clusterstarts:
                tophits.append(i)
            else:
                nottophits.append(i)
        new_order = tophits
        new_order.extend(nottophits)
        return ReorderedMSetResultOrdering(self.mset, new_order, self.context)

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
                               fields):
        """Reorder results based on similarity.

        The top `count` documents will be chosen such that they are relatively
        dissimilar.  `maxcount` documents will be considered for moving around,
        and `max_similarity` is a value between 0 and 1 indicating the maximum
        similarity to the previous document before a document is moved down the
        result set.

        Note: this method is experimental, and will probably disappear or
        change in the future.

        """
        if self.mset.get_firstitem() != 0:
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
        end = min(self.mset.get_firstitem() + len(self.mset), maxcount)
        for i in xrange(end):
            if full:
                new_order.append(i)
                continue
            hit = self.mset.get_hit(i)
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
        if end != self.mset.get_firstitem() + len(self.mset):
            new_order.extend(range(end,
                                   self.mset.get_firstitem() + len(self.mset)))
        assert len(new_order) == self.mset.get_firstitem() + len(self.mset)
        if reordered:
            return ReorderedMSetResultOrdering(self.mset, new_order,
                                               self.context)
        else:
            assert new_order == range(self.mset.get_firstitem() +
                                      len(self.mset))
            return self


class ResultStats(object):
    def __init__(self, mset, cache_stats):
        self.mset = mset
        self.cache_stats = list(cache_stats)

    def get_lower_bound(self):
        if self.cache_stats[0] is None:
            self.cache_stats[0] = self.mset.get_matches_lower_bound()
        return self.cache_stats[0]

    def get_upper_bound(self):
        if self.cache_stats[1] is None:
            self.cache_stats[1] = self.mset.get_matches_upper_bound()
        return self.cache_stats[1]

    def get_estimated(self):
        if self.cache_stats[2] is None:
            self.cache_stats[2] = self.mset.get_matches_estimated()
        return self.cache_stats[2]


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

    def get_startrank(self):
        return self.mset.get_firstitem()

    def get_endrank(self):
        return self.mset.get_firstitem() + len(self.mset)

    def __len__(self):
        """Get the number of items in this ordering.

        """
        return len(self.mset_order)


class NoFacetResults(object):
    """Stub used when no facet results asked for.

    """
    def __init__(self, *args, **kwargs):
        pass

    def get_facets(self):
        raise errors.SearchError("Facet selection wasn't enabled when the search was run")

    def get_suggested_facets(self, maxfacets, required_facets):
        raise errors.SearchError("Facet selection wasn't enabled when the search was run")


class FacetResults(object):
    """The result of counting facets.

    """
    def __init__(self, facetspies, facetfields, facethierarchy, facetassocs,
                 desired_num_of_categories, cache_facets):
        self.facetspies = facetspies
        self.facetfields = facetfields
        self.facethierarchy = facethierarchy
        self.facetassocs = facetassocs

        self.facetvalues = {}
        self.facetscore = {}
        for field, slot, facettype in facetfields:
            values, score = self._calc_facet_value(slot, facettype,
                                                  desired_num_of_categories)
            self.facetvalues[field] = values
            self.facetscore[field] = score

        if cache_facets is not None:
            self.facetvalues.update(cache_facets)
            self.facetscore.update((fieldname, 0)
                                   for fieldname, _ in cache_facets)

    def _calc_facet_value(self, slot, facettype, desired_num_of_categories):
        """Calculate the facet value for a given slot, and return it.

        """
        facetspy = self.facetspies.get(slot, None)
        if facetspy is None:
            return (), 0
        else:
            if facettype == 'float':
                if hasattr(xapian, 'UnbiasedNumericRanges'):
                    ranges = xapian.UnbiasedNumericRanges(
                        facetspy.get_values(), desired_num_of_categories)
                else:
                    ranges = xapian.NumericRanges(facetspy.get_values(),
                                                  desired_num_of_categories)

                score = xapian.score_evenness(ranges.get_ranges(),
                                              ranges.get_values_seen(),
                                              desired_num_of_categories)
                values = ranges.get_ranges_as_dict()
            else:
                score = xapian.score_evenness(facetspy,
                                              desired_num_of_categories)
                values = facetspy.get_values_as_dict()
            values = tuple(sorted(values.iteritems()))
            return values, score

    def get_facets(self):
        """Get all the calculated facets.

        Returns a dictionary, mapping from field name to the values for that
        field.

        """
        return self.facetvalues

    def get_suggested_facets(self, maxfacets, required_facets):
        """Get the suggested facets.  Parameters and return value are as for
        `SearchResults.get_suggested_facets()`.

        """
        if isinstance(required_facets, basestring):
            required_facets = [required_facets]
        scores = []

        for field in self.facetvalues.iterkeys():
            score = self.facetscore[field] 
            scores.append((score, field))

        # Sort on whether facet is top-level ahead of score (use subfacets first),
        # and on whether facet is preferred for the query type ahead of anything else
        if self.facethierarchy:
            # Note, tuple[-1] is the value of 'field' in a scores tuple
            scores = [(tuple[-1] not in self.facethierarchy,) + tuple for tuple in scores]
        if self.facetassocs:
            preferred = IndexerConnection.FacetQueryType_Preferred
            scores = [(self.facetassocs.get(tuple[-1]) != preferred,) + tuple for tuple in scores]
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
        for score, field in scores:
            # Check if the facet is required
            required = False
            if required_facets is not None:
                required = field in required_facets

            # If we've got enough facets, and the field isn't required, skip it
            if not required and len(results) + len(required_results) >= maxfacets:
                continue

            values = self.facetvalues[field] 

            # Required facets must occur at least once, other facets must occur
            # at least twice.
            if required:
                if len(values) < 1:
                    continue
            else:
                if len(values) <= 1:
                    continue

            score = self.facetscore[field] 
            if required:
                required_results.append((score, field, values))
            else:
                results.append((score, field, values))

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
