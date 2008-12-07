
class Field(object):
    """An instance of a Field in a document.

    """

    # Use __slots__ because we're going to have very many Field objects in
    # typical usage.
    __slots__ = 'name', 'value'

    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __repr__(self):
        return 'Field(%r, %r)' % (self.name, self.value)

