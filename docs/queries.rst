Queries
=======

.. contents:: Table of contents

All searches that you want to perform with Xappy must first be
described by building a Query object to represent the search.  There
are several methods of SearchConnection which allow you to create
Query objects, and there are also several ways to combine Query
objects together once you have created them.

Note that Query objects are immutable: they cannot be changed once
created.  All operations on them will result in creating new Query
objects without modifying the original Query.

Creating Query objects from a SearchConnection
==============================================

SearchConnection supports several methods which create a brand new
Query() object:

 - `query_parse()`
 - `query_field()`
 - `query_range()`
 - `query_facet()`
 - `query_similar()`
 - `query_all()`
 - `query_none()`

*FIXME* - document further here.  For now, see the introductory
document for examples of using these, and the doccomments for detailed
usage information.


Combining Query objects
=======================

Once you have a query, it can be used to produce new queries, by
combining it with other queries (in several different ways), or
by modifying the weights produced by the query.

Modifying the weights
---------------------

Firstly, given an existing Query, the weights returned by it may be
modified simply by multiplying or dividing the Query by a number::

 >>> conn = get_example_search_connection()
 >>> query = conn.query_parse("hello")
 >>> print query
 Xapian::Query((hello:(pos=1) AND_MAYBE hello:(pos=1)))
 >>> print query * 2
 Xapian::Query(2 * (hello:(pos=1) AND_MAYBE hello:(pos=1)))

Often, the reason for modifying the weights is to combine different
queries together.  The absolute value of weights returned by searches
varies widely (depending on the distribution and number of the terms
involved in the search), so when combining parts of a query, it is
often desirable to normalise the range of the weights first.

Unfortunately, the exact range of weights resulting from a query
cannot be determined without running the full search, and it is
desirable to avoid this if at all possible.  Instead, it is possible
to quickly calculate a upper bound on the weight, which gives some
idea of the range of values returned by a query::

 >>> print "%.2f" % query.get_max_possible_weight()
 1.62

Since the reason for calculating the weight is often to normalise the
weights returned by a query, there is a special method which does
precisely this.  Note that this simply divides the weight by the
maximum possible weight, so it is very likely that the upper limit of
the resulting weights will be considerably lower than 1::

 >>> qnorm = query.norm()
 >>> print "%.2f" % qnorm.get_max_possible_weight()
 1.00

Note that with the "Flint" database backend, searches involving
document weights, as stored by the `WEIGHT` field action, will return
a very large value (generally, the largest representable floating
point number) as their maximum possible weight.  This is due to
insufficient information being stored in the "Flint" database format
to calculate an upper bound.  If this is a problem, try using the
"Chert" backend instead.

Combining a list of Query objects
---------------------------------

The Query.compose() method (which is a static method), allows any list (or
other iterable) of Query objects to be used to produce a combined query.  The
query may be combined using either the `Query.OP_OR` or the `Query.OP_AND`
operator.  `OP_OR` produces queries which return all documents which would be
returned by any of the supplied queries, whereas `OP_AND` produces only those
documents which would be returned by all of the supplied queries.

The weights associated with the returned documents will simply be the sum of
the weights from each of the supplied queries which match that particular
document::

 >>> query2 = conn.query_parse("world")
 >>> print Query.compose(Query.OP_OR, (query, query2))
 Xapian::Query(((hello:(pos=1) AND_MAYBE hello:(pos=1)) OR (world:(pos=1) AND_MAYBE world:(pos=1))))

Combining queries with binary operators
---------------------------------------

Instead of using `Query.compose()`, it is often more convenient to use some
binary operators which Query overrides.  You can use the `&` operator to
combine two queries with an AND (similar to `Query.compose(Query.OP_AND, ...)`,
and the `|` operator to combine two queries with an OR::

 >>> print query & query2
 Xapian::Query(((hello:(pos=1) AND_MAYBE hello:(pos=1)) AND (world:(pos=1) AND_MAYBE world:(pos=1))))

Note that if you have a long list of queries to join with an `AND` or an `OR`,
it is likely to be more efficient to combine these with `Query.compose()` than
by repeatedly using the `&` or `|` binary operators.  (Currently,
Query.compose() scales as O(N) where N is the number of queries, whereas
repeatedly combining queries with binary operators scales O(N*N).  Clever use
of the operators by combining queries in a tree-structure could bring this down
to O(N*log(N)), but why bother?  Just use `Query.compose()` instead!)

You can also use the `^` operator to combine two queries with XOR: the result
will be a query which returns all those documents which match exactly one of
the two sub-queries (though this is rarely useful, there may be specialised
situations where it is helpful).

Restricting a query with another query
--------------------------------------

FIXME - describe Query.and_not() and Query.filter()

Adjusting the weight from one query with another query
------------------------------------------------------

FIXME - describe Query.adjust()

Combining Query objects using a SearchConnection
------------------------------------------------

An alternative way of combining queries is to use some methods of
`SearchConnection`.  However, these methods do not provide any
features not already available by using `Query` objects directly: this
method of combining queries was implemented before `Query` objects
could be manipulated directly, and is probably not useful to use in
new applications.

 - `SearchConnection.query_composite()`: Equivalent to
   `Query.compose()`.
 - `SearchConnection.query_multweight()`: Equivalent to multiplying a
   `Query` by a number.
 - `SearchConnection.query_filter()`: Equivalent to `Query.and_not()`
   or `Query.filter()` (depending on the `exclude` parameter of
   `SearchConnection.query_filter()`).
 - `SearchConnection.query_adjust()`: Equivalent to `Query.adjust()`.

Performing searches with Queries
================================

Given a query, a search can be performed directly by calling its
`search` method.  This is equivalent to passing the query to the
`SearchConnection.search()` method.
