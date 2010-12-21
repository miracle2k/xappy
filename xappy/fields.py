# Copyright (C) 2007,2008 Lemur Consulting Ltd
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
r"""fields.py: Fields and groups of fields.

"""
__docformat__ = "restructuredtext en"

class Field(object):
    """An instance of a Field in a document.

    """

    # Use __slots__ because we're going to have very many Field objects in
    # typical usage.
    __slots__ = 'name', 'value', 'assoc', 'weight'

    def __init__(self, name, value, assoc=None, weight=1.0):
        self.name = name
        self.value = value
        self.assoc = assoc
        self.weight = float(weight)

    def __repr__(self):
        extra = ''
        if self.assoc is not None:
            extra += ', %r' % self.assoc
        if self.weight != 1.0:
            extra += ', weight=%r' % self.weight
        return 'Field(%r, %r%s)' % (self.name, self.value, extra)

class FieldGroup(object):
    """A group of Fields in a document.

    """
    # Use __slots__ because we're going to have very many FieldGroup objects in
    # typical usage.
    __slots__ = 'fields'

    def __init__(self, fields=None, name=None, values=None):
        """Initialise a FieldGroup.

         - if `fields` is supplied, it should be a sequence (or iterable)
           containing either Field objects, or sequences of parameters for
           constructing Field objects (or a mix of both types of item).
         - if `name` is supplied, it should be a field name, and `values`
           should also be supplied.
         - if `values` is supplied, it should be a sequence (or iterable) of
           field values.  It will be ignored unless `name` is supplied.

        """
        self.fields = []
        if fields is not None:
            for field in fields:
                if isinstance(field, Field):
                    self.fields.append(field)
                else:
                    self.fields.append(Field(*field))
        if name is not None:
            for value in values:
                self.fields.append(Field(name, value))

    def __repr__(self):
        return 'FieldGroup(%s)' % (', '.join(repr(field)
                                             for field in self.fields))
