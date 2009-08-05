Xappy Image Similarity
======================

Xappy has the capability to index image data in such a way that
searches for documents with similar images can be performed. (Assuming
that a sufficiently recent version of xapian is present.)


Accuracy
--------

Note the following points:

  - The process of extracting image information is lossy so that
    recall cannot be perfect.

  - Images are all scaled to the same size (currently 128x128 pixels)
    before analysis. The scaling process can lose detail (when scaling
    down) or blur images (when scaling up).

  - It is a somewhat subjective question as to how similar two images
    are. (I have discovered that opinions on this can be quite
    markedly different!)

  - The similarity algorithm has no notion of the absolute size of
    objects depicted in an image, or the kind of thing represented;
    whereas subjective assesments are influenced by this sort of
    thing. For example if we recognize an image as being of a big
    building, then we will tend to favour other images of big
    buildings over images of other categories of objects, or small
    objects; even if the actual shapes and colours in the image do not
    warrant this.

  - Colour forms part of similarity algorithm. For example it might be
    that a blue square and a red square of the same dimensions are
    considered "less similar" than a blue square and a blue hexagon of
    similar size.


Indexing
--------

The field action xappy.FieldActions.IMGSEEK is used to indicate that a
field is to be used for data relating to image similarity. For
example::

  conn.add_field_action('image', xappy.FieldActions.IMGSEEK, terms = True)

Note the `terms` argument. If this is True then on adding data to the
field a number of terms are added to the document, which can
subsuently used for querying. If false, then serialised data about the
image is stored in a value which is used for the same purpose at query
time. For large databases `terms = True` is normally significantly
faster than `terms = False`.

At indexing time the corresponding field of a document must be
supplied with the name of an image file. For example::

  doc.fields.append(xappy.Field('image', '/path/to/foo.jpg'))
  conn.add(doc)

The main drawback with specifying `terms = True` is that you can only
sensibly associate one image with each document, whereas `terms =
False` deals gracefully with multiple images per document.

Searching
---------

At search time the `query_image_similarity` method of a
SearchConnection constructs a query that will return documents with
similar images::

  query = self.sconn.query_image_similarity('image', docid='0')
  results = self.sconn.search(query, 0, 10)

`query_image_similarity` can be passed exactly one of the parameters
`docid`, `xapid` or `image`. The first is a xappy document identifier;
the second a xapian document identifier; and the last an image file
path. It is only useful to use one of the first two forms for a
document that has been indexed with image data in the specified
field. These forms are useful when you want to find documents with
similar images to the image data supplied at indexing time. The last
form allows you to search for documents with images similar to an
arbitrary image.

Where the action has been specified with `terms = False` and multiple
images have been associated with documents, then documents are return
in order of best image similarity with the target.

Associating multiple images with a single document in the `terms =
True` case is not forbidden, but it's not really clear exactly what
the results mean; so this is not recommended.

Performance Note
----------------

Note that `IndexerConnection` and `SearchConnection` objects cache
data necessary to perform analysis of the image and construct queries.
So using the same connection object will be faster than creating a new
connection object for the same database. The first indexing or query
construction for a given connection object will probably be
significantly slower than subsequent ones.

References
----------

The implementation (mostly in xapian) is partly derived from the
imgseek project - http://imgseek.net - and the underlying techniques
are from ideas described in the paper
http://grail.cs.washington.edu/projects/query/mrquery.pdf
