#!/usr/bin/env python
#
# Copyright (C) 2007,2008 Lemur Consulting Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
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
    # Use __slots__ because we're going to have very many Field objects in
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
