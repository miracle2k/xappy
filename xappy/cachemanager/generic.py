#!/usr/bin/env python
#
# Copyright (C) 2009,2010 Richard Boulton
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
r"""generic.py: Base cachemanager classes.

"""
__docformat__ = "restructuredtext en"

import cPickle
import operator
import UserDict
try:
    from hashlib import md5
except ImportError:
    from md5 import md5

try:
    from numpy_inverter import NumpyInverterMixIn
    InverterMixIn = NumpyInverterMixIn
except ImportError:
    from inmemory_inverter import InMemoryInverterMixIn
    InverterMixIn = InMemoryInverterMixIn

def sort_facets(facets):
    """Sort an iterable of facets.

    Returns a tuple, sorted by fieldname.  Also sorts the values into
    descending frequency order (and ascending order of key for equal
    frequencies).

    """
    if isinstance(facets, dict):
        facets = facets.iteritems()
    return tuple(sorted((fieldname,
                         tuple(sorted(valfreqs.iteritems() if isinstance(valfreqs, dict) else valfreqs,
                                      key=lambda x: (-x[1], x[0]))))
                        for fieldname, valfreqs in facets))

class CacheManager(object):
    """Base class for caches of precalculated results.

    """
    def prepare_iter_by_docid(self):
        """Prepare to iterate by document ID.

        This does any preparations necessary for iter_by_docid().

        Caches should keep track of whether any changes have been made since
        this was last called, and use the values calculated last time if not.

        """
        raise NotImplementedError

    def invalidate_iter_by_docid(self):
        """Invalidate any cached items for the iter_by_docid.

        """
        raise NotImplementedError

    def iter_by_docid(self):
        """Return an iterator which returns all the documents with cached hits,
        in order of document ID, together with the queryids and ranks for those
        queries.

        Returns (docid, <list of (queryid, rank)>) pairs.

        """
        raise NotImplementedError

    def is_empty(self):
        """Return True iff the cache is empty.

        """
        raise NotImplementedError

    def iter_queryids(self):
        """Return an iterator returning all the queryids for which there are
        cached items.

        Doesn't guarantee any ordering on the queryids.

        """
        raise NotImplementedError

    def iter_query_strs(self):
        """Iterate the string form of all the stored queries.

        Doesn't guarantee any ordering on the query strings.

        """
        raise NotImplementedError

    def get_queryid(self, query_str):
        """Get a (numeric) query ID given a query string.

        If the query string is not in the cache, returns None.

        """
        raise NotImplementedError

    def get_or_make_queryid(self, query_str):
        """Get or allocate a (numeric) query ID given a query string.

        If the query string is not in the cache, makes a new query ID and
        return it.  Otherwise, returns the existing query ID.

        """
        raise NotImplementedError

    def get_hits(self, queryid, startrank=0, endrank=None):
        """Get the Xapian document IDs of documents matching a query.

        This returns a list of document IDs, in ascending rank order.

        `queryid` is the numeric ID of the query to look up.

        `startrank` is the rank (starting at 0) of the first result to return.

        `endrank` is the rank at which to stop returning results: ie, 1 more
        than the rank of the last result to return.  If `endrank` is None, return
        all the results.

        """
        raise NotImplementedError

    def get_stats(self, queryid):
        """Return some stats about the number of matching documents for a query.

        This returns a 3-tuple of:

         - matches_lower_bound
         - matches_upper_bound
         - matches_estimated

        Any of these values may be None, indicating that they are not stored in
        the cache.

        """
        raise NotImplementedError

    def set_hits(self, queryid, docids,
                 matches_lower_bound=None,
                 matches_upper_bound=None,
                 matches_estimated=None):
        """Set the Xapian document IDs of documents matching a query.

        `queryid` is the numeric ID of the query to look up.

        """
        raise NotImplementedError

    def set_stats(self, queryid,
                  matches_lower_bound=None,
                  matches_upper_bound=None,
                  matches_estimated=None):
        """Set the statistics on the numbers of matching documents for a query.

        `queryid` is the numeric ID of the query to look up.

        """
        raise NotImplementedError

    def add_stats(self, queryid,
                  matches_lower_bound=None,
                  matches_upper_bound=None,
                  matches_estimated=None):
        """Add to the statistics on the numbers of matching documents for a query.

        `queryid` is the numeric ID of the query to look up.

        Any statistics provided which are None are left unaltered.

        """
        raise NotImplementedError

    def clear_stats(self, queryid):
        """Clear the statistics for a query.

        `queryid` is the numeric ID of the query to look up.

        """
        raise NotImplementedError

    def remove_hits(self, queryid, ranks_and_docids):
        """Remove the hits at given ranks from the cached entry for a query.

        `queryid` is the numeric ID of the query to look up.

        ranks_and_docids is a iterable of (rank, docid) pairs.  The docids in
        these pairs are the docids of the items to remove. The ranks in the
        pairs are _hints_ of the ranks to remove: the hints are allowed to be
        overestimates (but not underestimates).  This will happen when the
        IndexerConnection tries to remove hits from queries which have already
        had some items removed.

        """
        raise NotImplementedError

    def get_facets(self, queryid):
        """Get the facets matched by a query.

        The result of this is exactly the same as the `facets` parameter passed
        to set_facets().

        If no facets are stored, this should return None.

        """
        raise NotImplementedError

    def set_facets(self, queryid, facets):
        """Set the facets matched by a query.

        `facets` is a sequence containing the facet data, as follows:

         - items in the sequence are (fieldname, facetvalues)
         - fieldname is a string
         - facetvalues is a sequence of (value, frequency)
         - value is a string for string fields
         - value is a 2-tuple of (start, end) for float fields
         - start and end are floats.
         - frequency is an integer

        ie: facets=(
                    (fieldname1, ((val1, freq1), (val2, freq2), ))
                    (fieldname2, (((start3, end3), freq3), ))
                   )

        """
        raise NotImplementedError

    def add_facets(self, queryid, facets):
        """Add to the facets matched by a query.

        `queryid` and `facets` are as for `set_facets`.

        This behaves like set_facets(), except that instead of overwriting the
        existing facets, the new facet values are combined with the existing
        ones, and where a facet occurs in both, the frequencies are added
        together.

        """
        raise NotImplementedError

    def flush(self):
        """Ensure that all changes made to the cache are written to disk.

        """
        raise NotImplementedError

    def close(self):
        """Close the storage for the cache (if this means anything).

        """
        raise NotImplementedError

class KeyValueStoreCacheManager(InverterMixIn, UserDict.DictMixin,
                                CacheManager):
    """A manager that stores the cached items in chunks in a key-value store.

    Subclasses must implement:

     - __getitem__()
     - __setitem__()
     - __delitem__()
     - flush()
     - close()

    Subclasses may change the serialised representation by implementing:

     - encode()
     - decode()

    or, individually:

     - encode_int()
     - decode_int()
     - encode_docids()
     - decode_docids()

    Prefixes used:

     - 'I': A single value holding the next queryid to allocate.
     - 'S': Followed by a decimal queryid, contains the query string.
     - 'Q': Followed by a md5sum of the query string, contains the query string
       and the query ID.
     - 'H': Followed by queryid:chunkid, contains a chunk of hits.
     - 'T': Followed by a queryid, contains the stats for that query.
     - 'F': Followed by a queryid, contains the facets for that query.

    """
    encode = staticmethod(lambda x: cPickle.dumps(x, 2))
    decode = staticmethod(cPickle.loads)

    encode_int = encode
    decode_int = decode
    encode_docids = encode
    decode_docids = decode

    def __init__(self, chunksize=None):
        if chunksize is None:
            chunksize = 1000
        self.chunksize = chunksize
        CacheManager.__init__(self)

    def __getitem__(self, key):
        """Get the value for a given key.

        If there is no value for the key, return an empty string.

        This must be implemented by subclasses.

        """
        raise NotImplementedError

    def __setitem__(self, key, value):
        """Set the value for a given key.

        Replaces any existing value.

        This must be implemented by subclasses.

        """
        raise NotImplementedError

    def __delitem__(self, key):
        """Delete the value for a given key.

        If there is no value for the key, do nothing.

        This must be implemented by subclasses.

        """
        raise NotImplementedError

    def keys(self):
        """Iterate through all the keys stored.

        The keys can be returned in any order, as long as each is returned
        exactly once.

        This must be implemented by subclasses.

        """
        raise NotImplementedError

    def clear(self):
        """Remove all items stored in the cache manager.

        """
        self.invalidate_iter_by_docid()
        for key in tuple(self.keys()):
            del self[key]

    def is_empty(self):
        # Just need to check if self['I'] exists - we don't allow complete
        # removal of a cached query, so if we've ever populated self['I'] we're
        # not empty.
        v = self['I']
        return (len(v) == 0)

    def iter_queryids(self):
        # Currently, we don't allow sparse queryids, so we can just return an
        # iterator over the range of values.
        # Key 'I' holds the (encoded) value of the next ID to allocate.
        v = self['I']
        if len(v) == 0:
            return iter(())
        return xrange(self.decode_int(v))

    def iter_query_strs(self):
        for query_id in self.iter_queryids():
            query_str = self['S' + str(query_id)]
            if len(query_str) > 0:
                yield query_str

    @staticmethod
    def _make_query_key(query_str):
        return 'Q' + md5(query_str).digest()

    def get_queryid(self, query_str):
        v = self[self._make_query_key(query_str)]
        if len(v) == 0:
            return None
        stored_str, retval  = self.decode(v)
        if stored_str == query_str:
            return retval
        # Collision for the hash - very very unlikely, so just return a cache
        # miss in this case.
        return None

    def get_or_make_queryid(self, query_str):
        query_key = self._make_query_key(query_str)
        v = self[query_key]
        if len(v) == 0:
            # Get the next ID to use.
            v = self['I']
            if len(v) == 0:
                thisid = 0
            else:
                thisid = self.decode_int(v)

            self[query_key] = self.encode((query_str, thisid))
            self['S' + str(thisid)] = query_str
            self['I'] = self.encode_int(thisid + 1)
            return thisid
        stored_str, retval  = self.decode(v)
        if stored_str == query_str:
            return retval
        raise ValueError("Hash values collide: stored query string is %r, "
                         "query string is %r" % (stored_str, query_str))

    @staticmethod
    def make_hit_chunk_key(queryid, chunk):
        """Make the key for looking up a particular chunk for a given queryid.

        """
        return 'H%d:%d' % (queryid, chunk)

    def get_hits(self, queryid, startrank=0, endrank=None):
        startchunk = int(startrank // self.chunksize)
        if endrank is None:
            endchunk = None
        else:
            endchunk = int(endrank // self.chunksize)

        hits = []
        chunk = startchunk
        startrank_in_chunk = startrank - chunk * self.chunksize
        while endchunk is None or chunk <= endchunk:
            data = self[self.make_hit_chunk_key(queryid, chunk)]
            if len(data) == 0:
                # Chunk doesn't exist: implies that we're at the end
                break
            chunkhits = self.decode_docids(data)

            if endrank is None:
                # Use the whole of the chunk
                if startrank_in_chunk == 0:
                    # Avoid doing a slice if we don't have to.
                    hits.extend(chunkhits)
                else:
                    hits.extend(chunkhits[startrank_in_chunk:])
            else:
                endrank_in_chunk = min(len(chunkhits),
                                       endrank - chunk * self.chunksize)
                hits.extend(chunkhits[startrank_in_chunk:endrank_in_chunk])

            startrank_in_chunk = 0
            chunk += 1

        return hits

    def get_stats(self, queryid):
        data = self['T' + str(queryid)]
        if len(data) == 0:
            return (None, None, None)
        return self.decode(data)

    def set_hits(self, queryid, docids,
                 matches_lower_bound=None,
                 matches_upper_bound=None,
                 matches_estimated=None):
        self.set_hits_internal(queryid, docids, 0)

        # Backwards compatibility.
        if (matches_lower_bound is not None or
            matches_upper_bound is not None or
            matches_estimated is not None):
            self.set_stats(queryid, matches_lower_bound,
                           matches_upper_bound, matches_estimated)

    def set_hits_internal(self, queryid, docids, chunk):
        """Internal implementation of set_hits.

        Set the hits starting at the chunk number specified by `chunk`.

        """
        # Convert docids into a list - allows iterators to be supplied.
        # Could be done chunk-by-chunk, but it's easier to do this way, and
        # probably fast enough.
        docids = list(docids)

        chunkcount = int(len(docids) // self.chunksize) + 1 + chunk

        # Add the data in chunks
        offset = 0
        while chunk < chunkcount:
            data = self.encode_docids(docids[offset : offset + self.chunksize])
            offset += self.chunksize
            self[self.make_hit_chunk_key(queryid, chunk)] = data
            chunk += 1

        # Ensure that there aren't any chunks for further bits of data
        # remaining
        while True:
            key = self.make_hit_chunk_key(queryid, chunk)
            data = self[key]
            if len(data) == 0:
                break
            del self[key]
            chunk += 1

    def set_stats(self, queryid,
                  matches_lower_bound=None,
                  matches_upper_bound=None,
                  matches_estimated=None):
        """Set the statistics for this queryid.

        """
        key = 'T' + str(queryid)
        self[key] = self.encode((matches_lower_bound,
                                 matches_upper_bound,
                                 matches_estimated))

    def add_stats(self, queryid,
                  matches_lower_bound=None,
                  matches_upper_bound=None,
                  matches_estimated=None):
        """Set the statistics for this queryid.

        """
        key = 'T' + str(queryid)

        data = self[key]
        if len(data) == 0:
            data = (None, None, None)
        else:
            data = self.decode(data)

        if matches_lower_bound is None:
            matches_lower_bound = data[0]
        elif data[0] is not None:
            matches_lower_bound += data[0]

        if matches_upper_bound is None:
            matches_upper_bound = data[1]
        elif data[1] is not None:
            matches_upper_bound += data[1]

        if matches_estimated is None:
            matches_estimated = data[2]
        elif data[2] is not None:
            matches_estimated += data[2]

        self[key] = self.encode((matches_lower_bound,
                                 matches_upper_bound,
                                 matches_estimated))

    def clear_stats(self, queryid):
        """Clear the statistics for a query.

        `queryid` is the numeric ID of the query to look up.

        """
        del self['T' + str(queryid)]

    def remove_hits(self, queryid, ranks_and_docids):
        if len(ranks_and_docids) == 0:
            return

        # To remove a hit, we need to get all chunks after the one containing
        # the given rank, and update them.

        # First, ensure the ranks are a sorted list - sort in descending order.
        ranks_and_docids = list(ranks_and_docids)
        ranks_and_docids.sort(reverse=True)

        startchunk = int(ranks_and_docids[-1][0] // self.chunksize)
        startrank = startchunk * self.chunksize
        hits = self.get_hits(queryid, startrank)

        unmatched = []
        for rank, docid in ranks_and_docids:
            if ((len(hits) > rank - startrank) and
                (hits[rank - startrank] == docid)):
                del hits[rank - startrank]
            else:
                unmatched.append((rank, docid))

        if len(unmatched) != 0:
            #print "%d unmatched item in chunk %d" % (len(unmatched), startchunk)
            # Get all the hits, so that we can find the mismatched ones.
            # We might be able to get away without fetching all the hits in
            # some cases, but that would increase code complexity, so let's not
            # do it unless profiling shows it to be necessary.
            hits = self.get_hits(queryid, 0, startrank) + hits
            startrank = 0
            startchunk = 0

            for rank, docid in unmatched:
                rank = min(rank, len(hits) - 1)
                while rank >= 0:
                    if hits[rank] == docid:
                        del hits[rank]
                        break
                    rank -= 1
                assert rank != -1

        self.set_hits_internal(queryid, hits, startchunk)

        # Decrease the stats
        delcount = len(ranks_and_docids)

        data = self['T' + str(queryid)]
        if len(data) != 0:
            data = list(self.decode(data))
            if data[0] is not None:
                data[0] -= 1
            if data[1] is not None:
                data[1] -= 1
            if data[2] is not None:
                data[2] -= 1
            self['T' + str(queryid)] = self.encode(data)

    def get_facets(self, queryid):
        data = self['F' + str(queryid)]
        if len(data) == 0:
            return None
        return self.decode(data)

    def set_facets(self, queryid, facets):
        self['F' + str(queryid)] = self.encode(sort_facets(facets))

    def add_facets(self, queryid, facets):
        key = 'F' + str(queryid)
        data = self[key]
        if len(data) == 0:
            self.set_facets(queryid, facets)
            return
        newfacets = dict(self.decode(data))
        for fieldname, new_valfreqs in facets.iteritems():
            try:
                existing_valfreqs = newfacets[fieldname]
            except KeyError:
                newfacets[fieldname] = new_valfreqs
                continue
            # Merge existing_valfreqs with new_valfreqs
            existing_valfreqs = dict(existing_valfreqs)
            for value, freq in new_valfreqs:
                try:
                    freq += existing_valfreqs[value]
                except KeyError:
                    pass
                existing_valfreqs[value] = freq
            newfacets[fieldname] = tuple(existing_valfreqs.iteritems())

        self[key] = self.encode(sort_facets(newfacets))

    def clear_facets(self, queryid):
        del self['F' + str(queryid)]
