Introduction
============

.. contents:: Table of contents

The "secore" module is an easy-to-use interface to the Xapian search engine.
Xapian provides a low level interface, dealing with terms and documents, but
not really worrying about where terms come from, or how to build searches to
match the way in which data has been indexed.  In contrast, secore allows you
to design a field structure, specifying what kind of information is held in
particular fields, and then uses this field structure to index data
appropriately, and to build and perform searches.

Installing and testing
======================

Dependencies
------------

You will need an up-to-date version of Xapian to use secore.  The 1.0.0 release
release almost satisfies all the needs of this interface, but there is a small
issue with the way in which range restrictions are implemented.  A bugfix 1.0.1
release will be made shortly to fix this, and another few issues, but until
this is released, you will need a SVN snapshot of the Xapian sources.  The core
Xapian library and the Python bindings to go with it will need to be compiled
and installed.

Installation
------------

There is not yet a distutils setup script for secore, but other than Xapian it
has no dependencies or resources which need installing, so it may be installed
simply by copying the "secore" directory to somewhere on your Python path.

Once Xapian and secore are installed, you should be able to start the python
interpreter and run::

  >>> import secore

Running the testsuite
---------------------

To run the testsuite, simply run "./testsuite/runtests.py".  This will
display any errors produced when running the testsuite, and then display a
coverage report for the modules tested.

The testsuite is composed of tests taken from three sources:

 - doctest tests in the code comments in the 
 - additional doctest tests in text files with names of the form
   'FOO_doctestN.txt', which test the module named "FOO" (and are run in a
   context in which the modules public symbols have all been imported).
 - additional documentation files (such as this one) which contain doctest
   formatted examples.

The list of core modules to test, and additional documentation files to check,
is maintained in the "testsuite/runtests.py" file.

The coverage report displayed after running the testsuite is statement based,
which is sadly one of the least precise methods of generating a coverage
report, and counts lines as having been executed even if they haven't been
tested in all possible code paths.  On the plus side, its judgement is reliable
if it considers that a line of code hasn't been tested.  For this reason, it is
reasonable to aim for 100% coverage by this metric, and the coverage report can
be helpful to keep track of sections of code which aren't tested at all.

Presently, the coverage report should indicate 100% coverage for all
modules, except for 'secore/textprocessor.py' which was imported from a
different piece of code and is not all being used by the search engine
interface at present.  It is due to be replaced shortly anyway, because the
code it implements is being moved into the core C++ Xapian library.


Building a database
===================

Setting up a field structure
----------------------------

Before we process any documents, we need to create a database to hold the
documents.  This is done simply by creating an "IndexerConnection" object, and
passing it the path we want to create the database at.  If the database doesn't
already exist, this will create a new, empty, database::

  >>> conn = secore.IndexerConnection('db1')

.. note:: All connections may only be accessed from a single thread at a time,
  and there may only be one IndexerConnection in existence at any given time.
  Additionally, it generally gives a large performance gain to ensure that the
  connection is kept open between modifications of the database, so that
  modifications can be grouped together.  Therefore, you must protect access to
  the connection with a mutex if multiple threads might access it.

Once we've created an IndexerConnection, we can use it to specify the actions
which should be performed on fields with a given name.  There are several
actions available, for different types of field content, and for different
types of searches.  You need to decide what actions you need before adding
documents, because the database does not store enough information about
documents to get back to the unprocessed document.  The connection will allow
you to change the field actions after documents have been added, but this
change will not be reflected in any documents which have already been added to
the database.

Fields which contain plain text should be added with the ``INDEX_FREETEXT``
action.  This action takes various optional parameters:

 - ``weight``: if this is supplied, the frequency information for all terms in
   the specified field will be multiplied by the given factor; this can be used
   for fields which are often a better indication of the subject matter than
   other fields (eg, title fields).

 - ``language``: if this is supplied, it indicates the language that the
   supplied text is written in: this is used to perform language specific term
   normalising (to allow, for example, plural and singular forms to be
   matched).  The language may be specified as a 2 character ISO-639 language
   code.

 - ``stop``: if this is supplied, it must contain an sequence or other iterable
   which returns a list of stopwords, which will be filtered out of the index.
   This may reduce index size and improve search and indexing speed, but will
   reduce the flexibility of the search.  Note that some information on the
   terms in the stoplist will still be stored, to allow phrase searches to be
   performed.

 - ``spell``: this is a boolean flag; if supplied, and true, the contents of
   the field will be used for spelling correction.

 - ``nopos``: this is a boolean flag; if supplied, and true, the positions of
   words in the field will not be stored.  These are used for performing phrase
   and proximity searches, so this kind of search will not be possible on the
   field.  On the other hand, the amount of data indexed for the field will be
   reduced, resulting in a lower database size, faster indexing, and
   potentially faster searching.

 - ``noprefix``: this is a boolean flag; if supplied and true, the contents of
   the field will be indexed only for a general, non-field-specific search.
   This should only be used in special cases to reduce the index size with very
   large datasets, and will probably be removed in future when new Xapian
   features are developed which remove the overhead of performing field
   specific searches.

All text passed to the interface is assumed to be UTF-8 encoded Unicode.

::

  >>> conn.add_field_action('title', secore.FieldActions.INDEX_FREETEXT, weight=5, language='en')
  >>> conn.add_field_action('text', secore.FieldActions.INDEX_FREETEXT, language='en', spell=True)


Any fields which contain exact values which we want to search for (such as a
category name, or an ID number should be given the ``INDEX_EXACT`` actions.
This doesn't perform any processing on the field value, so any symbols or
punctuation will be preserved in the database::

  >>> conn.add_field_action('category', secore.FieldActions.INDEX_EXACT)

If we want to be able to sort on a field, we need to give it the ``SORTABLE``
action.  By default, sorting is performed based on a lexicographical comparison
of string values, but it is possible to set the sort order to be by date, or by
floating point number.  Fields which are given then ``SORTABLE`` action can
also be used to restrict the results to a given range - think of it as
declaring that there is a useful ordering for the field values.

Date values can be supplied as strings in the form YYYYMMDD or YYYY-MM-DD (or
using / or . as separators).  Floating point numbers can be in any
representation which is understood by Python's float() function::

  >>> conn.add_field_action('category', secore.FieldActions.SORTABLE)
  >>> conn.add_field_action('date', secore.FieldActions.SORTABLE, type="date")
  >>> conn.add_field_action('price', secore.FieldActions.SORTABLE, type="float")

If we want to be able to be able to remove duplicates based on a field, we need
to give it the ``COLLAPSE`` action.  This allows the result set to be
"collapsed" such that only the highest result with each value of a field will
be returned.  For example, we might want to just display the highest ranked
document in each category (with a link to a list of the results in that
category)::

  >>> conn.add_field_action('category', secore.FieldActions.COLLAPSE)

If we want to be able to retrieve data from the document when it is
the result of a search, we need to set the ``STORE_CONTENT`` action::

  >>> conn.add_field_action('text', secore.FieldActions.STORE_CONTENT)
  >>> conn.add_field_action('title', secore.FieldActions.STORE_CONTENT)
  >>> conn.add_field_action('category', secore.FieldActions.STORE_CONTENT)

If we want to use the contents of a field as "tags", which can be counted at
search time (possibly, in order to build a tag-cloud, or other such
visualisation), we need to set the ``TAG`` action::

  >>> conn.add_field_action('tag', secore.FieldActions.TAG)


Secore also supports "faceted browsing": this means attaching "facets" to
documents, where a facet is a values representing one aspect of information
about a document: for example, the price of an object would be a facet of a
document representing that object.  Secore supports storing many facets about a
document, restricting the search results to only those documents which contain
that facet, and automatically selecting a set of facets which are relevant to
the set of results returned by a search (so that the facets can be presented to
the user to be used to refine their search).

If we want to use a field as a facet, we simply add the ``FACET`` action to it.
Facets can be of two types - "string" (which are just exact string matches), or
"float" (which will automatically be grouped into ranges when returning a
suggested list of facets).  The default is "string"::

  >>> conn.add_field_action('price', secore.FieldActions.FACET, type='float')
  >>> conn.add_field_action('category', secore.FieldActions.FACET, type='string')

Indexing
--------

To add data to the database, we first create ``UnprocessedDocument`` objects.
These contain a list of fields, which are processed in turn to create a
``ProcessedDocument``, which can be added to the database.  The
``ProcessedDocument`` can't be converted back into an ``UnprocessedDocument``
because some information is generally lost in this processing process (but it
is possible to make alterations directly to the ``ProcessedDocument`` later.

We can access the list of fields in an ``UnprocessedDocument`` directly, using
the ``fields`` member::

  >>> doc = secore.UnprocessedDocument()
  >>> doc.fields.append(secore.Field("title", "Our first document"))
  >>> doc.fields.append(secore.Field("text", "This is a paragraph of text.  It's quite short."))
  >>> doc.fields.append(secore.Field("text", "We can create another paragraph of text.  "
  ...                                "We can have as many of these as we like."))
  >>> doc.fields.append(secore.Field("category", "Test documents"))
  >>> doc.fields.append(secore.Field("tag", "Tag1"))
  >>> doc.fields.append(secore.Field("tag", "Test document"))
  >>> doc.fields.append(secore.Field("tag", "Test document"))
  >>> doc.fields.append(secore.Field("price", "20.56"))

We can add the document directly to the database: if we do this, the connection
will process the document to generate a ``ProcessedDocument`` behind the
scenes, and then add this::

  >>> conn.add(doc)
  '0'

Note that the ``add`` method returned a value ``'0'``.  This is a unique
identifier for the document which was added, and may be used later to delete or
replace the document.  If we have externally generated unique identifiers, we
can specify that the system should use them instead of generating its own, by
setting the ``id`` property on the processed or unprocessed document
before adding it to the database.


We can also ask the database to process a document explicitly before calling
the "add" method.  We might do this if we want to change the processed document
in some way, but this isn't generally necessary::

  >>> doc = secore.UnprocessedDocument()
  >>> doc.fields.append(secore.Field("title", "Our second document"))
  >>> doc.fields.append(secore.Field("text", "In the beginning God created the heaven and the earth."))
  >>> doc.fields.append(secore.Field("category", "Bible"))
  >>> doc.id='Bible1'
  >>> pdoc = conn.process(doc)
  >>> conn.add(pdoc)
  'Bible1'
  >>> doc = secore.UnprocessedDocument()
  >>> doc.fields.append(secore.Field("title", "Our third document"))
  >>> doc.fields.append(secore.Field("text", "And the earth was without form, and void; "
  ...                                "and darkness was upon the face of the deep. "
  ...                                "And the Spirit of God moved upon the face of the waters."))
  >>> doc.fields.append(secore.Field("category", "Bible"))
  >>> doc.fields.append(secore.Field("date", "17501225"))
  >>> doc.fields.append(secore.Field("price", "16.56"))
  >>> doc.id='Bible2'
  >>> pdoc = conn.process(doc)
  >>> conn.add(pdoc)
  'Bible2'


Once we have finished indexing, we should flush the changes to disk.  Any
changes which are unflushed may not be preserved if the processes exits without
closing the database nicely::

  >>> conn.flush()

Finally, we should close the connection to release its resources (if we leave
this to the garbage collector, this might not happen for a long time).  After
closing, no other methods may be called on the connection, but a new connection
can be made.::

  >>> conn.close()

Searching
=========

A search connection is opened similarly to an indexing connection.  However,
note that multiple search connections may be opened at once (though each
connection must not be accessed from more than one thread).  Search connections
can even be open while indexing connections are::

  >>> conn = secore.SearchConnection('db1')

A search connection attempts to provide a stable view of the database, so when
an update is made by a concurrent indexing process, the search connection will
not reflect this change.  This allows the results of the search to be gathered
without needing to worry about concurrent updates (but see the section below
about this for limitations on this facility).

The search connection can be reopened at any time to make it point to the
latest version of the database::

  >>> conn.reopen()

To perform a search, we need to specify what we're searching for.  This is
called a "Query", and the search connection provides several methods for
building up a query.  The simplest of these is the ``query_field`` method,
which builds a query to search a single field::

  >>> q = conn.query_field('text', 'create a paragraph')
  >>> str(q)
  'Xapian::Query((ZXBcreat:(pos=1) AND ZXBa:(pos=2) AND ZXBparagraph:(pos=3)))'

As you can see, the str() function will display the underlying Xapian query
which is generated by the search connection.  This may look a little weird at
first, but you can get a general idea of the shape of the query: in this case,
we have three terms which are combined together with an "AND" operator.

The default operator for searches is "AND", but if we wish to be a little wider
in our search, we can use the "OR" operator instead::

  >>> q = conn.query_field('text', 'create a paragraph', default_op=conn.OP_OR)
  >>> str(q)
  'Xapian::Query((ZXBcreat:(pos=1) OR ZXBa:(pos=2) OR ZXBparagraph:(pos=3)))'

Once we have a query, we can use it to get a set of search results.  Xapian is
optimised for situations where only a small subset of the total result set is
required, so when we perform a search we specify the starting `rank` (ie, the
position in the total set of results, starting at 0) of the results we want to
retrieve, and also the ending rank.  Following usual Python conventions, the
ending rank isn't inclusive, but the starting rank is.

In this case we want the first 10 results, so we can search with::

  >>> results = conn.search(q, 0, 10)

The result set has a variety of pieces of information, but a useful one is the
estimate of the total number of matching documents::

  >>> results.matches_estimated
  2

Only an estimated value is available because of Xapian's optimisations: the
search process can often stop early because it has proved that there can be no
better ranked documents, and especially for large searches, it would be a waste
of time to then attempt to calculate the precise number of matching documents.
We can check if the estimate is known to be correct by looking at the
``estimate_is_exact`` property::

  >>> results.estimate_is_exact
  True

The ``SearchResults`` object also provides upper and lower bounds on the number
of matching documents, and a check for whether there are more results following
those in this result set (very useful when writing a "pager" type interface,
which needs to know whether to include a "Next" button).

Once you have a ``SearchResults`` object, you want to be able to get at the
actual resulting documents.  This can be done by using the ``get_hit()``
method, or by iterating through all the results with the usual Python iterator
idiom.  Both of these will return ``SearchResult`` objects, which is a subclass
of ``ProcessedDocument``, but has the additional property of `rank`::

  >>> for result in results:
  ...     print result.rank, result.id, result.data['category']
  0 0 ['Test documents']
  1 Bible1 ['Bible']

In addition, ``SearchResults`` objects have methods allowing a highlighted or
summarised version of a field to be displayed::

  >>> results.get_hit(0).highlight('text')[0]
  "This is <b>a</b> <b>paragraph</b> of text.  It's quite short."
  >>> results.get_hit(0).summarise('text', maxlen=20)
  'This is <b>a</b> <b>paragraph</b>..'

(Note that the highlight() method returns a list of field instances, as stored
in the document data, so we've asked for it to only return the first of these,
but the summarise() method joins these all together before generating the
summary.)

Queries can be built and combined with other methods.  The most flexible of
these is the ``query_parse()`` method, which allows a user entered query to be
parsed appropriately.  The parser understands "Google style" searches, in which
a search term can be restricted to a specified field by writing
"fieldname:term", and in which boolean operators can be used in the search.
The full syntax is described in the `Xapian QueryParser documentation`_.
(Note that the wildcard option is currently disabled by default.)

If a field has been indexed with the "spell" option turned on, the
``spell_correct()`` method can return a version of the query string with the
spelling corrected.  This method takes similar arguments to ``query_parse()``,
but instead of performing a search, it returns the corrected query string (or
the original query string, if no spelling corrections were found).

  >>> conn.spell_correct('teext')
  'text'

In addition, two queries may be combined (with an AND or OR operator) using the
``query_composite()`` method, or a query can be "filtered" with another query
such that only documents which match both queries will be returned (but the
rankings are determined by the first query) using the ``query_filter()``
method.

To perform a range restriction, a range query can be built using the
``query_range()`` method.  This will return a query which matches all documents
in the database which satisfy the range restriction::

  >>> rq = conn.query_range('date', '20000101', '20010101')

This query can be performed on its own, but note that for a large database it
could take a long time to run, because if run on its own it will iterate
through all the values in the database to return those which fit in the range.
Instead, it will usually be used in conjunction with the ``query_filter()``
method, to filter the results of an existing query::

  >>> filtered_query = conn.query_filter(q, rq)
  >>> print filtered_query
  Xapian::Query(((ZXBcreat:(pos=1) OR ZXBa:(pos=2) OR ZXBparagraph:(pos=3)) FILTER VALUE_RANGE 1 20000101 20010101))

.. Note:: The implementation of sorting and range filtering for floating point values uses terms which typically contain non-printable characters.  Don't panic if you call ``print`` on a query generated with ``query_range()`` and odd control-characters are displayed; it's probably normal.)


To get a list of the tags which are contained in the result set, we have to
specify the gettags parameter to the search() method::

  >>> results = conn.search(q, 0, 10, gettags='tag')
  >>> results.get_top_tags('tag', 10)
  [('tag1', 1), ('test document', 1)]

.. Note:: When the result set is being generated, various optimisations are performed to avoid wasting time looking at documents which can't possibly get into the portion of the result set which has been requested.  These are normally desirable optimisations because they can speed up searches considerably, but if information about the tags in the result set as a whole is desired, the optimisations can cause inaccurate values to be returned.  Therefore, it is possible to force the search engine to look at at least a minimum number of results, by setting the "checkatleast" parameter of the search() method.  As a special case, a value of -1 forces all matches to be examined, regardless of database size: this should be used with care, because it can result in slow searches.

To search for only those documents containing a given tag, we can use the
query_field() method::

  >>> results = conn.search(conn.query_field('tag', 'tag1'), 0, 10)
  >>> results.matches_estimated, results.estimate_is_exact
  (1, True)
  >>> results.get_hit(0).highlight('text')[0]
  "This is a paragraph of text.  It's quite short."


To get a list of facets which are relevant to the result set, we have to
specify the getfacets parameter to the search() method.  We can also specify
the allowfacets or denyfacets parameters to control the set of facets which are
considered for display (this may be useful to reduce work if we've already
restricted to a particular facet value, for example).  Note that as with the
gettags option, it may be advisable to specify a reasonably high value for the
"checkatleast" parameter::

  >>> results = conn.search(q, 0, 10, checkatleast=1000, getfacets=True)
  >>> results.get_suggested_facets()
  [('category', [('Bible', 1), ('Test documents', 1)]), ('price', [((20.559999999999999, 20.559999999999999), 1)])]

Note that the values for the suggested facets contain the string for facets of
type "string", but contain a pair of numbers for facets of type "float" - these
numbers define an automatically suggested range of values to use for the facet.


Concurrent update limitations
-----------------------------

Unfortunately, Xapian's current database implementation doesn't allow search
connections to be arbitrarily old: once *two* updates have been made to the
database since the connection was opened, the connection may fail with a
"DatabaseModifiedError" when it tries to access the database.  Once this has
happened, the search connection needs to be reopened to proceed further, and
will then access a new, updated, view of the database.

To make this easier to manage, if the "DatabaseModifiedError" occurs during the
search process, the error will be handled automatically, and the search will be
re-performed.  However, it is still possible for the error to occur when
retrieving the document data from a search result, so handling for this should
be included in code which reads the data from search results.

To avoid this happening, avoid calling the flush() method on the indexer
connection too frequently, and call the reopen() method on the search
connection before performing each new search.  You should generally try not to
call flush() more than once every 60 seconds anyway, because performance with
many small flushes will be sub-optimal.

We hope to remove this restriction in a future release of Xapian.

Sorting
-------

By default, the results are returned in order sorted by their "relevance" to
the query, with the most relevant documents returned first.  This order may be
changed by specifying the sortby parameter of the search() method.  The field
specified in this parameter must have been given the ``SORTABLE`` action before
indexing::

  >>> results = conn.search(q, 0, 10, sortby='category')
  >>> for result in results:
  ...     print result.rank, result.id, result.data['category']
  0 Bible1 ['Bible']
  1 0 ['Test documents']

The sort is in ascending order by default (ie, documents with a field value
which is first in order will be returned first).  The opposite order can be
requested by preceding the field name with a "-" sign::

  >>> results = conn.search(q, 0, 10, sortby='-category')
  >>> for result in results:
  ...     print result.rank, result.id, result.data['category']
  0 0 ['Test documents']
  1 Bible1 ['Bible']

.. note:: There is some potential for confusion here, because Xapian defines
   ascending order in the opposite direction: its logic is that ascending order
   means that the value should be highest in documents which come top of the
   result list.  This seems counter-intuitive to many people, and hopefully the
   sort order definition here will seem more natural.

If the sort terms are equal, the documents with equal sort terms will be
returned in relevance order.

Collapsing
----------

Xapian offers the useful feature of collapsing the result set such that only
the top result with a given "collapse" value is returned.  This feature can be
used by adding a ``COLLAPSE`` action to the field before indexing, and then
setting the collapse parameter of the ``search()`` method to the field name::

  >>> q = conn.query_field('title', 'document')
  >>> [result.id for result in conn.search(q, 0, 10)]
  ['Bible1', '0', 'Bible2']
  >>> [result.id for result in conn.search(q, 0, 10, collapse='category')]
  ['Bible1', '0']

Other documentation
===================

Detailed API documentation is available as docstrings in the Python code, but
you may find it more convenient to browse it in `formatted form (as generated by
epydoc)`_.


.. _formatted form (as generated by epydoc): api/index.html
.. _Xapian QueryParser documentation: http://xapian.org/docs/queryparser.html
