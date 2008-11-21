#!/usr/bin/env python
#
# Copyright (C) 2007 Lemur Consulting Ltd
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
r"""datastructures.py: Datastructures for search engine core.

"""
__docformat__ = "restructuredtext en"

import errors
from replaylog import log
from fields import Field, FieldGroup
import xapian
import cPickle

class UnprocessedDocument(object):
    """A unprocessed document to be passed to the indexer.

    This represents an item to be processed and stored in the search engine.
    Each document will be processed by the indexer to generate a
    ProcessedDocument, which can then be stored in the search engine index.

    Note that some information in an UnprocessedDocument will not be
    represented in the ProcessedDocument: therefore, it is not possible to
    retrieve an UnprocessedDocument from the search engine index.

    An unprocessed document is a simple container with two attributes:

     - `fields` is a list of Field objects, or an iterator returning Field
       objects.
     - `id` is a string holding a unique identifier for the document (or
       None to get the database to allocate a unique identifier automatically
       when the document is added).

    """

    __slots__ = 'id', 'fields',
    def __init__(self, id=None, fields=None):
        self.id = id
        if fields is None:
            self.fields = []
        else:
            self.fields = fields

    def __repr__(self):
        return 'UnprocessedDocument(%r, %r)' % (self.id, self.fields)

    def append(self, *args, **kwargs):
        """Append a field or group to the document.

        This may be called with a Field or a FieldGroup object, in which case
        it is the same as calling append on the "fields" member of the
        UnprocessedDocument.
        
        Alternatively. it may be called with a set of parameters for creating a
        Field object, in which case such a Field object is created (using the
        supplied parameters), and appended to the list of fields.

        Finally, it may be called with a sequence or iterable of Fields or sets
        of parameters for creating a Field object, in which case a FieldGroup
        is created, filled with the corresponding Field objects (which are
        newly created if parameters were suppled rather than ready-made Field
        objects), and added to the document.

        """
        if len(args) == 1 and len(kwargs) == 0:
            if isinstance(args[0], (Field, FieldGroup)):
                self.fields.append(args[0])
                return
            if not isinstance(args[0], basestring):
                # We assume we have a sequence of parameters for creating
                # Fields, to go in a FieldGroup
                fields = []
                for field in args[0]:
                    if not isinstance(field, Field):
                        field = Field(*field)
                    fields.append(field)
                self.fields.append(FieldGroup(fields))
                return
        # We assume we just had some arguments for appending a Field.
        self.fields.append(Field(*args, **kwargs))

    def extend(self, fields):
        """Append a sequence or iterable of fields or grous to the document.

        This is simply a shortcut for adding several Field objects to the
        document, by calling `append` with each item in the list of fields
        supplied.

        `fields` should be a sequence containing items which are either Field
        objects, or sequences of parameters for creating Field objects, or
        FieldGroups.

        """
        for field in fields:
            if isinstance(field, Field):
                self.fields.append(field)
            else:
                self.fields.append(Field(*field))

class ProcessedDocument(object):
    """A processed document, as stored in the index.

    This represents an item which is ready to be stored in the search engine,
    or which has been returned by the search engine.

    """

    __slots__ = '_doc', '_fieldmappings', '_data', '_assocs', '_groups'
    def __init__(self, fieldmappings, xapdoc=None):
        """Create a ProcessedDocument.

        `fieldmappings` is the configuration from a database connection used lookup
        the configuration to use to store each field.

        If supplied, `xapdoc` is a Xapian document to store in the processed
        document.  Otherwise, a new Xapian document is created.

        """
        if xapdoc is None:
            self._doc = log(xapian.Document)
        else:
            self._doc = xapdoc
        self._fieldmappings = fieldmappings
        # Dictionary, keyed by fieldname, of lists of data strings.
        self._data = None
        # Dictionary, keyed by fieldname, of lists of field associations.
        self._assocs = None
        # List of lists of (fieldname, offset) position.
        self._groups = None

    def add_term(self, field, term, wdfinc=1, positions=None):
        """Add a term to the document.

        Terms are the main unit of information used for performing searches.

        - `field` is the field to add the term to.
        - `term` is the term to add.
        - `wdfinc` is the value to increase the within-document-frequency
          measure for the term by.
        - `positions` is the positional information to add for the term.
          This may be None to indicate that there is no positional information,
          or may be an integer to specify one position, or may be a sequence of
          integers to specify several positions.  (Note that the wdf is not
          increased automatically for each position: if you add a term at 7
          positions, and the wdfinc value is 2, the total wdf for the term will
          only be increased by 2, not by 14.)

        """
        prefix = self._fieldmappings.get_prefix(field)
        if len(term) > 0:
            # We use the following check, rather than "isupper()" to ensure
            # that we match the check performed by the queryparser, regardless
            # of our locale.
            if ord(term[0]) >= ord('A') and ord(term[0]) <= ord('Z'):
                prefix = prefix + ':'

        # Note - xapian currently restricts term lengths to about 248
        # characters - except that zero bytes are encoded in two bytes, so
        # in practice a term of length 125 characters could be too long.
        # Xapian will give an error when commit() is called after such
        # documents have been added to the database.
        # As a simple workaround, we give an error here for terms over 220
        # characters, which will catch most occurrences of the error early.
        #
        # In future, it might be good to change to a hashing scheme in this
        # situation (or for terms over, say, 64 characters), where the
        # characters after position 64 are hashed (we obviously need to do this
        # hashing at search time, too).
        if len(prefix + term) > 220:
            raise errors.IndexerError("Field %r is too long: maximum length "
                                       "220 - was %d (%r)" %
                                       (field, len(prefix + term),
                                        prefix + term))

        if positions is None:
            self._doc.add_term(prefix + term, wdfinc)
        elif isinstance(positions, int):
            self._doc.add_posting(prefix + term, positions, wdfinc)
        else:
            self._doc.add_term(prefix + term, wdfinc)
            for pos in positions:
                self._doc.add_posting(prefix + term, pos, 0)

    def add_value(self, field, value, purpose=''):
        """Add a value to the document.

        Values are additional units of information used when performing
        searches.  Note that values are _not_ intended to be used to store
        information for display in the search results - use the document data
        for that.  The intention is that as little information as possible is
        stored in values, so that they can be accessed as quickly as possible
        during the search operation.

        Unlike terms, each document may have at most one value in each field
        (whereas there may be an arbitrary number of terms in a given field).
        If an attempt to add multiple values to a single field is made, only
        the last value added will be stored.

        """
        slot = self._fieldmappings.get_slot(field, purpose)
        self._doc.add_value(slot, value)

    def get_value(self, field, purpose=''):
        """Get a value from the document.

        """
        slot = self._fieldmappings.get_slot(field, purpose)
        return self._doc.get_value(slot)

    def prepare(self):
        """Prepare the document for adding to a xapian database.

        This updates the internal xapian document with any changes which have
        been made, and then returns it.

        """
        if self._data is not None or \
           self._assocs is not None or \
           self._groups is not None:
            unpacked = list(self._unpack_data())
            if self._data is not None:
                unpacked[0] = self._data
            if self._assocs is not None:
                unpacked[1] = self._assocs
            if self._groups is not None:
                unpacked[2] = self._groups
            self._doc.set_data(cPickle.dumps(tuple(unpacked), 2))
            self._data = None
            self._assocs = None
            self._groups = None
        return self._doc

    def _unpack_data(self):
        rawdata = self._doc.get_data()
        if rawdata == '':
            return ({}, {}, [])
        unpacked = cPickle.loads(rawdata)
        if isinstance(unpacked, dict):
            # Backwards compatibility
            return unpacked, {}, []
        else:
            # Backwards compatibility
            if len(unpacked) == 2:
                return unpacked[0], unpacked[1], []
            assert len(unpacked) == 3
            return unpacked

    def _set_from_unpacked_data(self):
        if self._data is not None and \
           self._assocs is not None and \
           self._groups is not None:
            return

        data, assocs, groups = self._unpack_data()
        if self._data is None:
            self._data = data
        if self._assocs is None:
            self._assocs = assocs
        if self._groups is None:
            self._groups = groups

    def _get_data(self):
        self._set_from_unpacked_data()
        return self._data
    def _set_data(self, data):
        if not isinstance(data, dict):
            raise TypeError("Cannot set data to any type other than a dict")
        self._data = data
    data = property(_get_data, _set_data, doc=
    """The data stored in this processed document.

    This data is a dictionary of entries, where the key is a fieldname, and the
    value is a list of strings.

    """)

    def _get_assocs(self):
        """Get the field associations for this document.
        
        This is intended for internal xappy use.

        """
        self._set_from_unpacked_data()
        return self._assocs

#    def _set_assocs(self, assocs):
#        if not isinstance(assocs, dict):
#            raise TypeError("Cannot set assocs to any type other than a dict")
#        self._assocs = assocs
#    _assocs = property(_get_assocs, _set_assocs, doc=
#    """The field associations stored in this processed document.
#
#    This is intended for internal xappy use.
#
#    This is a dictionary of entries, where the key is a fieldname, and the
#    value is a list of 2-tuples of strings, holding the field data, and the
#    association to store with that data.
#
#    """)

    def _get_groups(self):
        """Get the field groupings for this document.
        
        This is intended for internal xappy use.

        """
        self._set_from_unpacked_data()
        return self._groups
#
    def _get_id(self):
        tl = self._doc.termlist()
        try:
            term = tl.skip_to('Q').term
            if len(term) == 0 or term[0] != 'Q':
                return None
        except StopIteration:
            return None
        return term[1:]
    def _set_id(self, id):
        tl = self._doc.termlist()
        try:
            term = tl.skip_to('Q').term
        except StopIteration:
            term = ''
        if len(term) != 0 and term[0] == 'Q':
            self._doc.remove_term(term)
        if id is not None:
            self._doc.add_term('Q' + id, 0)
    id = property(_get_id, _set_id, doc=
    """The unique ID for this document.

    """)

    def __repr__(self):
        return '<ProcessedDocument(%r)>' % (self.id)

if __name__ == '__main__':
    import doctest, sys
    doctest.testmod (sys.modules[__name__])
