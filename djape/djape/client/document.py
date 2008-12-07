
from django.utils import simplejson
from field import Field

class Document(object):
    """A document to be passed to the indexer.

    This represents an item to be stored in the search engine.

    Note that some information in a Document will not be represented in the
    index: therefore, it is not possible to retrieve a full Document from the
    search engine index.

    A document is a simple container with two attributes:

     - `fields` is a list of Field objects, or an iterator returning Field
       objects.
     - `id` is a string holding a unique identifier for the document (or
       None to get the database to allocate a unique identifier automatically
       when the document is added).

    It also has some convenience methods to assist in building up the contents.

    """

    __slots__ = 'id', 'fields',
    def __init__(self, id=None, fields=None):
        self.id = id
        if fields is None:
            self.fields = []
        else:
            self.fields = fields

    def __repr__(self):
        return 'Document(%r, %r)' % (self.id, self.fields)

    def append(self, *args, **kwargs):
        """Append a field to the document.

        This may be called with a Field object, in which case it is the same as
        calling append on the "fields" member of the Document.
        
        Alternatively. it may be called with a set of parameters for creating a
        Field object, in which case such a Field object is created (using the
        supplied parameters), and appended to the list of fields.

        """
        if len(args) == 1 and len(kwargs) == 0:
            if isinstance(args[0], Field):
                self.fields.append(args[0])
                return
        # We assume we just had some arguments for appending a Field.
        self.fields.append(Field(*args, **kwargs))

    def extend(self, fields):
        """Append a sequence or iterable or dict of fields to the document.

        This is simply a shortcut for adding several Field objects to the
        document, by calling `append` with each item in the list of fields
        supplied.

        `fields` should be a sequence containing items which are either Field
        objects, or sequences of parameters for creating Field objects.

        """
        if hasattr(fields, 'iteritems'):
            for field_name, field_items in fields.iteritems():
                for field in field_items:
                    if isinstance(field, Field):
                        if field.name != field_name:
                            raise Error
                        self.fields.append(field)
                    else:
                        self.fields.append(Field(field_name, field))
        else: # Assume sequence
            for field in fields:
                if isinstance(field, Field):
                    self.fields.append(field)
                else:
                    self.fields.append(Field(*field))

    def as_json(self):
        """Return a JSON represenation of the document.

        Probably not the best implementation currently - lots of copying.

        """
        req = {
            'id': self.id,
            'data': [[field.name, field.value] for field in self.fields],
        }
        return simplejson.dumps(req)

