
from copy import copy

class Query(object):
    """A query object.  This is composed of query parts.

    This represents arbitrarily complex queries, together with the query
    options which they support.

    """

    OP_AND = 0
    OP_OR = 1

    def __init__(self, part=None):
        """Create the query object.

        If `part` is a string, it is equivalent to setting the query definition
        to FreeTextQuery(text).

        """
        self.opts = {}
        if isinstance(part, basestring):
            part = FreeTextQuery(part)
        self.part = part

    def sort_by(self, field_name, ascending=True):
        """Set the field to sort by.

        """
        self.opts['sort_by'] = [(field_name, ascending)]
        try:
            del self.opts['sort_by_distance']
        except KeyError:
            pass

    def sort_by_distance(self, field_name, centre, ascending=True):
        """Set sorting to be by distance from centre.

        `field_name` is the field name to get coordinates from.
        `centre` is the location to calculate distances from.

        """
        self.opts['sort_by_distance'] = [(field_name, centre)]
        try:
            del self.opts['sort_by']
        except KeyError:
            pass

    def to_params(self):
        res = {
            'query': self.part.to_params(),
        }
        if self.opts:
            res['opts'] = self.opts
        return res

class QueryPart(object):
    """A part of a query.

    This is an abstract class - use one of it's subclasses

    """
    def to_params(self):
        raise NotImplementedError('Implement this method in subclass.')

class AllQuery(QueryPart):
    """A query which returns all the documents.

    May usefully be combined, or sorted.

    """

    def to_params(self):
        return ['all', None]

class FreeTextQuery(QueryPart):
    """A query which searches for some free text.

    """
    def __init__(self, text=None, **opts):
        """Create a query object.

        `text` is a free text, non field-specific, query string.
        For more complex queries, use one of the factory methods.

        """
        self.text = text
        self.opts = opts
        QueryPart.__init__(self)

    def to_params(self):
        return ['freetext', (self.text, self.opts)]

class GeoDistanceQuery(QueryPart):
    def __init__(self, centre=None):
        """Create a query object, which weights documents by distance.

        `centre` is a text representation of a latlong coordinate.

        """
        self.centre = centre
        QueryPart.__init__(self)

    def to_params(self):
        return ['geodistance', self.centre]


# FIXME - implement more query types
