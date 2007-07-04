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
r"""indexerconnection.py: A connection to the search engine for indexing.

"""
__docformat__ = "restructuredtext en"

import xapian as _xapian
from datastructures import *
from fieldactions import *
import fieldmappings as _fieldmappings
import errors as _errors
import os as _os
import cPickle as _cPickle

class IndexerConnection(object):
    """A connection to the search engine for indexing.

    """

    def __init__(self, indexpath):
        """Create a new connection to the index.

        There may only be one indexer connection for a particular database open
        at a given time.  Therefore, if a connection to the database is already
        open, this will raise a xapian.DatabaseLockError.

        If the database doesn't already exist, it will be created.

        """
        self._index = _xapian.WritableDatabase(indexpath, _xapian.DB_CREATE_OR_OPEN)
        self._indexpath = indexpath

        # Read existing actions.
        self._field_actions = {}
        self._field_mappings = _fieldmappings.FieldMappings()
        self._next_docid = 0
        self._config_modified = False
        self._load_config()

    def _store_config(self):
        """Store the configuration for the database.

        Currently, this stores the configuration in a file in the database
        directory, so changes to it are not protected by transactions.  When
        support is available in xapian for storing metadata associated with
        databases. this will be used instead of a file.

        """
        config_str = _cPickle.dumps((
                                     self._field_actions,
                                     self._field_mappings.serialise(),
                                     self._next_docid,
                                    ), 2)
        config_file = _os.path.join(self._indexpath, 'config')
        fd = open(config_file, "w")
        fd.write(config_str)
        fd.close()
        self._config_modified = False

    def _load_config(self):
        """Load the configuration for the database.

        """
        config_file = _os.path.join(self._indexpath, 'config')
        if not _os.path.exists(config_file):
            return
        fd = open(config_file)
        config_str = fd.read()
        fd.close()

        (self._field_actions, mappings, self._next_docid) = _cPickle.loads(config_str)
        self._field_mappings = _fieldmappings.FieldMappings(mappings)
        self._config_modified = False

    def _allocate_id(self):
        """Allocate a new ID.

        """
        while True:
            idstr = "%x" % self._next_docid
            self._next_docid += 1
            if not self._index.term_exists('Q' + idstr):
                break
        self._config_modified = True
        return idstr

    def add_field_action(self, fieldname, fieldtype, **kwargs):
        """Add an action to be performed on a field.

        Note that this change to the configuration will not be preserved on
        disk until the next call to flush().

        """
        if self._index is None:
            raise _errors.IndexerError("IndexerConnection has been closed")
        if fieldname in self._field_actions:
            actions = self._field_actions[fieldname]
        else:
            actions = FieldActions(fieldname)
            self._field_actions[fieldname] = actions
        actions.add(self._field_mappings, fieldtype, **kwargs)
        self._config_modified = True

    def clear_field_actions(self, fieldname):
        """Clear all actions for the specified field.

        This does not report an error if there are already no actions for the
        specified field.

        Note that this change to the configuration will not be preserved on
        disk until the next call to flush().

        """
        if self._index is None:
            raise _errors.IndexerError("IndexerConnection has been closed")
        if fieldname in self._field_actions:
            del self._field_actions[fieldname]
            self._config_modified = True

    def process(self, document):
        """Process an UnprocessedDocument with the settings in this database.

        The resulting ProcessedDocument is returned.

        Note that this processing will be automatically performed if an
        UnprocessedDocument is supplied to the add() or replace() methods of
        IndexerConnection.  This method is exposed to allow the processing to
        be performed separately, which may be desirable if you wish to manually
        modify the processed document before adding it to the database, or if
        you want to split processing of documents from adding documents to the
        database for performance reasons.

        """
        if self._index is None:
            raise _errors.IndexerError("IndexerConnection has been closed")
        result = ProcessedDocument(self._field_mappings)
        result.id = document.id
        context = ActionContext(self._index)

        for field in document.fields:
            try:
                actions = self._field_actions[field.name]
            except KeyError:
                # If no actions are defined, just ignore the field.
                continue
            actions.perform(result, field.value, context)

        return result

    def add(self, document):
        """Add a new document to the search engine index.

        If the document has a id set, and the id already exists in
        the database, an exception will be raised.  Use the replace() method
        instead if you wish to overwrite documents.

        Returns the id of the newly added document (making up a new
        unique ID if no id was set).

        The supplied document may be an instance of UnprocessedDocument, or an
        instance of ProcessedDocument.

        """
        if self._index is None:
            raise _errors.IndexerError("IndexerConnection has been closed")
        if not hasattr(document, '_doc'):
            # It's not a processed document.
            document = self.process(document)

        # Ensure that we have a id
        orig_id = document.id
        if orig_id is None:
            id = self._allocate_id()
            document.id = id
        else:
            id = orig_id
            if self._index.term_exists('Q' + id):
                raise _errors.IndexerError("Document ID of document supplied to add() is not unique.")
            
        # Add the document.
        xapdoc = document.prepare()
        self._index.add_document(xapdoc)

        if id is not orig_id:
            document.id = orig_id
        return id

    def replace(self, document):
        """Replace a document in the search engine index.

        If the document does not have a id set, an exception will be
        raised.

        If the document has a id set, and the id does not already
        exist in the database, this method will have the same effect as add().

        """
        if self._index is None:
            raise _errors.IndexerError("IndexerConnection has been closed")
        if not hasattr(document, '_doc'):
            # It's not a processed document.
            document = self.process(document)

        # Ensure that we have a id
        id = document.id
        if id is None:
            raise _errors.IndexerError("No document ID set for document supplied to replace().")

        self._index.replace_document('Q' + id, document._doc)

    def delete(self, id):
        """Delete a document from the search engine index.

        If the id does not already exist in the database, this method
        will have no effect (and will not report an error).

        """
        if self._index is None:
            raise _errors.IndexerError("IndexerConnection has been closed")
        self._index.delete_document('Q' + id)

    def flush(self):
        """Apply recent changes to the database.

        If an exception occurs, any changes since the last call to flush() may
        be lost.

        """
        if self._index is None:
            raise _errors.IndexerError("IndexerConnection has been closed")
        if self._config_modified:
            self._store_config()
        self._index.flush()

    def close(self):
        """Close the connection to the database.

        It is important to call this method before allowing the class to be
        garbage collected, because it will ensure that any un-flushed changes
        will be flushed.  It also ensures that the connection is cleaned up
        promptly.

        No other methods may be called on the connection after this has been
        called.  (It is permissible to call close() multiple times, but
        only the first call will have any effect.)

        If an exception occurs, the database will be closed, but changes since
        the last call to flush may be lost.

        """
        if self._index is None:
            return
        try:
            self.flush()
        finally:
            # There is currently no "close()" method for xapian databases, so
            # we have to rely on the garbage collector.  Since we never copy
            # the _index property out of this class, there should be no cycles,
            # so the standard python implementation should garbage collect
            # _index straight away.  A close() method is planned to be added to
            # xapian at some point - when it is, we should call it here to make
            # the code more robust.
            self._index = None
            self._indexpath = None
            self._field_actions = None
            self._config_modified = False

    def get_doccount(self):
        """Count the number of documents in the database.

        This count will include documents which have been added or removed but
        not yet flushed().

        """
        if self._index is None:
            raise _errors.IndexerError("IndexerConnection has been closed")
        return self._index.get_doccount()

    def iterids(self):
        """Get an iterator which returns all the ids in the database.

        The unqiue_ids are currently returned in binary lexicographical sort
        order, but this should not be relied on.

        """
        if self._index is None:
            raise _errors.IndexerError("IndexerConnection has been closed")
        return PrefixedTermIter('Q', self._index.allterms())

    def get_document(self, id):
        """Get the document with the specified unique ID.

        Raises a KeyError if there is no such document.  Otherwise, it returns
        a ProcessedDocument.

        """
        if self._index is None:
            raise _errors.IndexerError("IndexerConnection has been closed")
        postlist = self._index.postlist('Q' + id)
        try:
            plitem = postlist.next()
        except StopIteration:
            # Unique ID not found
            raise KeyError('Unique ID %r not found' % id)
        try:
            postlist.next()
            raise _errors.IndexerError("Multiple documents " #pragma: no cover
                                       "found with same unique ID")
        except StopIteration:
            # Only one instance of the unique ID found, as it should be.
            pass

        result = ProcessedDocument(self._field_mappings)
        result.id = id
        result._doc = self._index.get_document(plitem.docid)
        return result

class PrefixedTermIter(object):
    """Iterate through all the terms with a given prefix.

    """
    def __init__(self, prefix, termiter):
        """Initialise the prefixed term iterator.

        - `prefix` is the prefix to return terms for.
        - `termiter` is a xapian TermIterator, which should be at it's start.

        """

        # The algorithm used in next() currently only works for single
        # character prefixes, so assert that the prefix is single character.
        # To deal with multicharacter prefixes, we need to check for terms
        # which have a starting prefix equal to that given, but then have a
        # following uppercase alphabetic character, indicating that the actual
        # prefix is longer than the target prefix.  We then need to skip over
        # these.  Not too hard to implement, but we don't need it yet.
        assert(len(prefix) == 1)

        self._started = False
        self._prefix = prefix
        self._prefixlen = len(prefix)
        self._termiter = termiter

    def __iter__(self):
        return self

    def next(self):
        """Get the next term with the specified prefix.


        """
        if not self._started:
            term = self._termiter.skip_to(self._prefix).term
            self._started = True
        else:
            term = self._termiter.next().term
        if len(term) < self._prefixlen or term[:self._prefixlen] != self._prefix:
            raise StopIteration
        return term[self._prefixlen:]

if __name__ == '__main__':
    import doctest, sys
    doctest.testmod (sys.modules[__name__])
