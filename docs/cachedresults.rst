====================
Cached Query Results
====================

WARNING - This document describes a feature which is still under heavy
development, and is therefore likely to change in the near future.

Overview
========

Xappy supports the use of cached results for queries.  These can be used simply
to speed up returning the results of common queries, but are also designed to
allow external algorithms to be used to calculate the top results of certain
queries.  The results stored in the cache need not be in the same order as
those which would be returned by performing the query directly, and, indeed,
need not even be the same results.

This can be used to allow hand-picked results to be displayed first, or to
display results which have been pre-calculated using ranking algorithms which
are too slow to perform in real-time.

If a user asks for more results than are held in the cache for a particular
query, Xappy will calculate the results following the end of the cached results
using its normal ranking algorithms, remove any which were held in the cache,
and return the remaining results at the ranks requested.

Usage
=====

To use the cache, you need to make an instance of a CacheManager subclass (see
below for help in choosing which one to use).

The CacheManager instance can be used independently of a Xappy database when
populating the cache, or when querying it.  The CacheManager can also be
associated with a Xappy database connection (either an IndexerConnection or a
SearchConnection) to enable updates to the database to update the cache, or to
perform combined searches against the cache and the database.

As far as the cache is concerned, queries are identified by numeric query IDs.
To assist with this, the CacheManager class has a `get_queryid()` method and a
`get_or_make_queryid()` method which can be used to maintain a mapping from
string representations of the queries (including all relevant options, such as
sort orders) to numeric IDs.  This may be bypassed entirely if desired, and an
external mapping used.  Nothing else in Xappy uses this mapping - only the
numeric IDs are used at indexing and search time to refer to a cached query.

Typically, you might do a bulk build of the cached queries for a database on a
cluster of machines, and feed the results into an independent instance of
CacheManager (calling `CacheManager.set_hits()` for each query to set the list
of cached results).  Then, you would connect this Cache to the
IndexerConnection for the database (using
`IndexerConnection.set_cache_manager()`), and call
`IndexerConnection.apply_cached_items()` to populate the database with links
for each document to the cached queries which contain that document.

When performing modifications, you would also use an IndexerConnection
connected to the cache, to ensure that any deleted documents are removed from
the cache.  We make the assumption that if a document is modified, its changes
are sufficiently minor that the document need not be removed from the cache -
caches should probably be refreshed reasonably frequently to ensure that this
does not pose a long-term problem.

At the search side, searches would first hit a standalone instance of the
CacheManager, using the `CacheManager.get_hits()` method to return the list of
matching documents.  Note that `get_hits()` allows the range of ranks of
documents requested to be specified, to avoid needing to pull more items from
the cache than necessary.  This might well be run on a separate front-end
machine, using a replicated copy of the Cache database.

For searches which can't be fully satisfied by the CacheManager (which can be
detected by the list returned by the `get_hits()` method containing fewer
entries than requested), the search needs to be performed against a
SearchConnection which has been joined with the CacheManager using the
`SearchConnection.set_cache_manager()` method.  Once this has been done, the
`SearchConnection.query_cached()` method can be used to obtain a query which
returns the cached results, in the appropriate order.  The weights returned by
this are guaranteed to differ by at least 1.0 between each result.  This means
that if the result of `query_cached()` is combined with normalised existing
query, the result order is simply that of all the cached results, followed by
the results in rank order excluding those already returned.

In other words, to combine the cached query with an existing query, do::

  orig_query = sconn.query_parse("This is the existing query")
  cached_query = sconn.query_cached(query_id_number)
  combined_query = orig_query.norm() | cached_query

Implementation
==============

All CacheManagers store a mapping from query ID to an ordered list of docids,
in ascending rank order (ie, "best" result first).  This is used when searching
a disconnected CacheManager object.

However, when a CacheManager is connected to an IndexerConnection and the
`apply_cached_items()` methods is used, the IndexerConnection needs to iterate
over a list of the document IDs, obtaining the list of cached queryids which
match that document (together with their ranks).  This is required so that each
Xapian document can be associated with the corresponding query IDs.

To obtain this list, the CacheManager either needs to invert the
queryid->docids mapping to produce a docid->queryids mapping, or needs to be
provided with such a mapping from an external source (eg, from a hadoop cluster
which has done the inversion).

CacheManager subclasses should provide a `prepare_iter_by_docid()` method,
which either performs the inversion, or pulls it from an external source.  They
should then provide an `iter_by_docid()` method which iterates through the
result of this inversion.

CacheManager variants
=====================

Currently, all CacheManager variants are implementations of the
KeyValueStoreCacheManager, which as the name implies, stores the necessary data
in a Key-Value store.

The KeyValueStoreCacheManager uses cPickle by default to encode various items,
but this can be customised by modifying the `encode()` and `decode()` methods,
or the `encode_int()`, `encode_docids()`, `decode_int()`, `decode_docids()`
methods.  However, cPickle seems to be fairly fast, and isn't an obvious
bottleneck in any of the tests I've done so far.  (Note - I also tested with
using JSON encoding, but found that this was around 100 times slower, using
both simplejson and the "json" module included in Python 2.6.  I've heard
rumours that this is a known problem which is fixed in later releases, but it's
easier to just use cPickle by default for now, since that seems to be reliable
across all releases.)

If you have Xappy installed and working, you must also have Xapian installed,
and Xapian provides an easy key-value store implementation (in the form of the
Xapian database metadata).  This is used by the XapianCacheManager
implementation, which is an easy default implementation to use.  However, the
XapianCacheManager simply uses the default implementation of
`prepare_iter_by_docid()`, which builds up the mapping from docid to query ids
in memory.  This is fine for small numbers of cached queries or documents, but
doesn't scale well.

An attempt to scale better is the `XapianSelfInvertingCacheManager` class.
This uses a temporary Xapian database, instead of an in-memory structure, to
perform the inversion.  For small databases, this is noticeably slower than for
the simple in-memory implementation, but for datasets for which the in-memory
implementation would run out of memory, this appears to be much faster.  (I've
done basic tests of it, but don't have any concrete figures with very large
datasets yet.)

Performance analysis
====================

My initial plan was to test with 1,000,000 queryids, each with between 1000 and
10,000 cached hits, and 1,000,000 docids in the database, and to check the
behaviour when deleting 100,000 documents from the database.

I wrote a script to generate some randomly distributed sample data for this,
and then to run some performance tests (xappy/xappy/perftest/cachemanager.py).
It turns out that the raw data for 1000 queryids takes around 25Mb, which means
that 1,000,000 queryids requires 25Gb of storage for the initial data alone.
The database to hold these queryids would be around 50 Gb in size (I haven't
actually created this, but this is an extrapolation based on the size of
databases for smaller numbers of query ids) - twice the size of the initial
data.  Merging the cached items into the database would create an even larger
database.

Therefore, I've run my initial tests with smaller numbers of cached queries
(1,000 instead of 1,000,000), and deleting only 1000 documents.

Raw numbers
-----------

The following are the search times for a run of xappy/perftest/cachemanager.py
with the chert backend:

  287.069452s: main
    7.092814s: Copy initial database into place
    3.721386s: Initial population of cache with 1000 queries
    2.498641s: ... flush
    0.114490s: Timing pure-cached searches
    0.016635s: ... Getting numeric query id (1000 instances)
    0.093183s: ... Getting cached query results (1000 instances)
  207.242773s: Apply cached items to the database
   56.099616s: ... prepare
  149.914106s: ... apply
    1.226644s: ... flush
    0.332378s: No-cache searches, getting results 0-100
    0.331967s: No-cache searches, getting results 10000-10100
    3.769758s: Cached searches, getting results 0-100
    0.017773s: ... Getting numeric query id (1000 instances)
    3.618549s: ... Getting cached query results (1000 instances)
    3.791935s: Cached searches, getting results 10000-10100
    0.018035s: ... Getting numeric query id (1000 instances)
    3.640521s: ... Getting cached query results (1000 instances)
   10.201199s: Deleting 1000 documents without cache attached
    9.680530s: ... flush
   20.182612s: Deleting 1000 documents with cache attached
    5.309771s: ... flush

For comparison, the following are the search times for a run of
xappy/perftest/cachemanager.py with the flint backend.  Note that only 10
searches were performed in this run (for each test), rather than the 1000
searches performed in the run with "chert", due to the extreme slowness of
these searches.  I also reduced the number of deletes similarly, but that
appears to have been unneccesary; flint is actually faster for deleting
documents than chert, because there is no need to seek through each value list
to remove the entry for the deleted document - with flint, the values are all
stored together in a single entry in the btree:

  235.660532s: main
    5.565150s: Copy initial database into place
    3.200986s: Initial population of cache with 1000 queries
    1.931045s: ... flush
    0.001559s: Timing pure-cached searches
    0.000241s: ... Getting numeric query id (10 instances)
    0.001249s: ... Getting cached query results (10 instances)
   96.754025s: Apply cached items to the database
   56.268883s: ... prepare
   40.461529s: ... apply
    0.021841s: ... flush
    0.004593s: No-cache searches, getting results 0-100
    0.003086s: No-cache searches, getting results 10000-10100
   22.691393s: Cached searches, getting results 0-100
    0.000308s: ... Getting numeric query id (10 instances)
   22.688762s: ... Getting cached query results (10 instances)
   22.837269s: Cached searches, getting results 10000-10100
    0.000311s: ... Getting numeric query id (10 instances)
   22.834603s: ... Getting cached query results (10 instances)
    3.898820s: Deleting 10 documents without cache attached
    3.895825s: ... flush
    4.479297s: Deleting 10 documents with cache attached
    1.800579s: ... flush


The "double inversion" inefficiency
-----------------------------------

There is a fundamental inefficiency in the design used so far, which is
unavoidable given the current design of Xapian, if we are to store the cached
entries in the Xapian database value slots for each queryid.

To implement `CacheManager.iter_by_docid()`, the CacheManager must invert the
mapping from queryid -> document to produce a document -> queryid mapping
(either internally, or by relying on some outside process to do this).  This is
an expensive process, however it is implemented.

When `IndexerConnection.apply_cached_items()` is called, this calls
`CacheManager.iter_by_docid()`, and adds each of the returned lists of queryids
to the appropriate value slot in the appropriate document, in ascending docid
order.

When searching using cached items, we typically have a user's query, combined
with a ValueWeightPostingSource query representing the cached set of results,
using the `OP_OR` operator (since documents should be returned if they're in the
cache or in the set of matching results).

In the Flint backend, values are simply stored in an entry in the "value" table
in the database for each document; this means that iterating through the values
at search time requires reading the entire "value" table, and is very very
slow.  (Experimental results showed that with Flint, searches which were being
modified by a cache component took around 1,000 times longer than those which
didn't.)

In the Chert backend, the list of value slots (but not their values) is stored
in an entry in the database for each document, and inverted lists of values are
also calculated, allowing the list of entries in each value slot to be iterated
efficiently.  This is good at search time, since it allows us to iterate
through the documents matching a given cached query quickly, without having to
do an exhaustive check.  (Experimental results showed that with Chert, searches
which were being modified by a cache component took about 5 times longer than
those which didn't.  However, this is for very simple searches (actually, ones
which contain only one term, and return only one document anyway), and
corresponded to an average time of around 0.004 seconds per query; this is
probably fast enough for most purposes.)

However, to calculate these inverted lists, at indexing time Xapian has to
perform a mapping from the document -> queryid mapping it is provided with to
the queryid -> document mapping it wants to store.  In other words, the system
as a whole does two inversions, from queryid -> document -> queryid.  Clearly,
there is wasted effort at indexing time here; the performance test shows that
applying the cached queries to the database takes several times longer with
Chert than with Flint.

There are two possible ways around this: either we could modify Xapian to allow
it to be given both the forward and the inverted lists when both are available,
or we could store the lists outside of Xapian's value slots, and implement a
custom PostingSource subclass which iterated through an external list.

I think the latter would be the preferable solution - the former would be a
major change to Xapian's API, and incorrect use of the new API could leave
Xapian databases in an inconsistent state, leading to hard-to-debug bugs.

Instead, we could store both the forward and the inverted lists in the
CacheManager, and it could simply be provided with the list stored in the
CacheManager's table.

Inefficient delete
------------------

The performance test also shows that deleting documents is rather inefficient
with the current implementation: deleting a document with the cache enabled can
easily take 25 times as long as deleting the document without having to update
the cache.

This is in large part because when a document is deleted from the cache, all
the queryids which had a cache entry for that document need to be updated.  In
the best case, this involves reading the chunk of the cache containing that
range of ranks, updating it, and updating all the following cache chunks for
that query (since the ranks will have all changed).

However, if any other deletes have happened on the cache entry for that
queryid, it's likely that the stored docid at that rank is incorrect (because
it's already been shuffled along).  In this case, the code has no option other
than to move through the list looking for the position which the document has
moved to, in order to delete it.  Therefore, as each delete happens, the
average time of the next delete increases.

Proposed solution
-----------------

The core of the inefficiencies is the inversion operation: we certainly need to
avoid doing it twice, and it would be best if we could avoid doing it once.

A simplifying assumption which I think we can make in many situations is that
deletes will be rare: we could reasonably hope that at most 10% of the database
will ever be deleted before the database is rebuilt (or recompacted and the
caches recreated, etc).  For an efficient solution, we could therefore use a
"delete list" of some form to represent the documents which have been deleted.
A very simple datastructure for this would be a flat bit-array file, in which
each bit indicates whether the corresponding document ID is deleted - this
would only result in a 122Kb file for a 1,000,000 document database (and would
obviously scale linearly with database size, as long as docids are compact).
The `CacheManager.remove_hits()` method would then simply have to add the docid
supplied to the cache.

With a "delete list", we would no longer need to have the ability to map from
document ID to query ID; when a document was deleted, the CacheManager would
simply add it to the delete list.  The delete list would be checked by the
cache before returning each document.

(Instead of maintaining a delete list, we could simply use Xapian to check for
the existence of the document - eg, by using `xapian.Database.get_doclength()`
and comparing to 0.  However this would be considerably slower than a simple
bit check in a file.)

The downside of a "delete list" is that when the item at rank "R" is requested
from the cache, it is necessary to iterate through all the hits in the cache
entry with a rank less than "R" to skip.  However, the tests show that the time
taken to retrieve all the hits for a single queryid from the cache is tiny -
around 10,000 such retrievals can be performed in a second on the test machine.
This will be dwarfed by the time taken to perform the rest of the search.

So, a scalable CacheManager might operate as follows:

 - The CacheManager stores the cached entries in single blocks in underlying
   storage.
 - A Xapian PostingSource is implemented which understands the storage format
   (and probably actually exposes APIs to encode a STL / Python list of docids,
   and to iterate through a part of the list).
 - A delete list is implemented and used by the PostingSource to skip over any
   documents which have been deleted.  (If the document ID is re-added in
   future, the delete list would, of course, need to be updated to mark the
   document as not-deleted.)
 - The delete list would need to be propagated to the frontend standalone
   CacheManager, for use there.  The delete list should therefore probably be
   stored (in chunks) in the same key-value store as the cache entries are
   stored in, to ensure consistency.
 - With this CacheManager, the IndexerConnection would no longer store the
   ranks for that document in value slots for each queryid; it wouldn't be
   possible to find the relevant cached queryids for a given document
   efficiently, but that would be okay, because there is no need to.

This CacheManager would have the advantages that:

 - attaching the cache to the database would be extremely cheap.
 - individual cached queries could be updated fairly efficiently.
 - deletes would be only marginally more expensive than without a cache involved.

The disadvantages are:

 - The CacheManager would get slower once any deletes had happened, because the
   Cache would then need to check all the cached items before those requested
   against the "delete list".
 - A custom version of Xapian would be needed to expose the appropriate
   PostingSource (and the associated encoding and decoding methods).
