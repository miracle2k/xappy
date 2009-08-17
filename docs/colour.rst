Colour Searching in Xappy
=========================

Xappy has some features to assist with finding documents close to
given colour. There are three aspects of this support:

  - The code in the module xappy.colour generates terms suitable for
    passing to the fields marked with FieldActions.COLOUR.

  - At indexing time FieldActions.COLOUR causes weights for terms to
    be treated specially, on the assumption that weights represent
    frequency of occurence of colours.

  - At query time a custom weighting scheme ensures that frequencies
    of colours in the document are treated appropriately.


The values passed to fields with the COLOUR field action should be
strings, which are just treated as terms for the field in
question. They are not used internally by xappy/xapian (however the
weights for such fields are treated specially).

The code in xappy.colour can however be used to construct terms that
have special meaning when used with queries generated from functions
in that module.

xappy.colour functionality
--------------------------

Internally the code in xappy.colour works with colour values from the
lab colour space. This is chosen because euclidean distance in this
colour space is supposed to correspond well to human perception of
degrees of colour difference. That is - two lab colours with a large
(euclidean) distance between their value will be percieved as being
very different colours by humans.

The whole colour space that we use is notionally divided up into
rectagular cuboids of equal size. The granularity of this division is
divided controlled by the `step_count` parameter that must be passed
to some of the fuctions in the module. Note well that in order to get
useful result the same `step_count` must be used to generate terms as
is used to generate queries. The total colour space notionally
contains `step_count` cubed seperate "buckets".

The function xappy.colour.rgb2term takes a triple of rgb values (each
in the range 0-255 inclusive) and returns a string that represent the
buckets into which the lab colourspace value corresponding to the rgb
value supplied falls. [Note that (at least when there are relatively
few buckets) many rgb values might map to the same term. It is also
possible that there may be some buckets which no rgb value fall into.]

Values passed to fields with the COLOUR field action should be
obtained by using rgb2term. The weight for such fields can be used to
indicate how much of the corresponding colour is represented in the
documents. For example the colours and weights might be obtain from a
colour histogram of an image associated with document.

When a document is added to the index all of the colour weights for a
given field with the colour field action will be normalized. Their
(approximate) ratios will be maintained, but the absolute values will
be modified. Therefore the absolute values of such weights is
irrelevant - all that matters is their relative size.

Once an index has been constructed special queries may be constructed
from colour data to find documents that were indexed with colours
"close" to the supplied colours.

The routine xappy.colour.query_colour expects to receive a sequence of
triples of the form `(colour, frequency, spread)`. `colour` is an rgb
triple, `frequency` is used to weight the subqueries for that colour,
and `spread` is used to determine how far away from colour to
cover. `spread` should range between 0 and 100. At 0 only documents
indexed with the bucket corresponding to `colour` will be found. As
this value increases more buckets will be included in the search, but
the buckets will be weighted according to their distance from `colour`
in the underlying lab colour space. Hence documents returned by a
search using such a query should be in order or closeness to the
supplied colours.

If the `cluster` parameter is `True` (which it is not by
default). Then the query is constructed slightly differently. Colours
that are close to each other are treated as a "cluster". Within each
cluster the frequencies are equalised to be the arithmetic mean of the
supplied frequencies and the query will AND together the terms
obtained from each cluster - so matching documents need to have
representative colours from each cluster. 

xappy.colour.facet_palette_query - see the docstring.
xappy.colour.colour_text_query - see the docstring.
