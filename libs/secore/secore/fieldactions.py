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
r"""fieldactions.py: Definitions and implementations of field actions.

"""
__docformat__ = "restructuredtext en"

import errors as _errors
import marshall as _marshall
import xapian as _xapian
import parsedate as _parsedate

def _act_store_content(fieldname, doc, value, context):
    """Perform the STORE_CONTENT action.
    
    """
    try:
        fielddata = doc.data[fieldname]
    except KeyError:
        fielddata = []
        doc.data[fieldname] = fielddata
    fielddata.append(value)

def _act_index_exact(fieldname, doc, value, context):
    """Perform the INDEX_EXACT action.
    
    """
    doc.add_term(fieldname, value, 0)

def _act_index_freetext(fieldname, doc, value, context, weight=1, 
                        language=None, stop=None, spell=False,
                        nopos=False, noprefix=False):
    """Perform the INDEX_FREETEXT action.
    
    """
    termgen = _xapian.TermGenerator()
    if language is not None:
        termgen.set_stemmer(_xapian.Stem(language))
        
    if stop is not None:
        stopper = _xapian.SimpleStopper()
        for term in stop:
            stopper.add (term)
        termgen.set_stopper (stopper)

    if spell:
        termgen.set_database(context.index)
        termgen.set_flags(termgen.FLAG_SPELLING)
    
    termgen.set_document(doc._doc)
    termgen.set_termpos(context.current_position)
    if nopos:
        termgen.index_text_without_positions(value, weight, '')
    else:
        termgen.index_text(value, weight, '')

    if not noprefix:
        # Store a second copy of the term with a prefix, for field-specific
        # searches.
        prefix = doc._fieldmappings.get_prefix(fieldname)
        if len(prefix) != 0:
            termgen.set_termpos(context.current_position)
            if nopos:
                termgen.index_text_without_positions(value, weight, prefix)
            else:
                termgen.index_text(value, weight, prefix)

    # Add a gap between each field instance, so that phrase searches don't
    # match across instances.
    termgen.increase_termpos(10)
    context.current_position = termgen.get_termpos()

class SortableMarshaller(object):
    """Implementation of marshalling for sortable values.

    """
    def __init__(self, indexing=True):
        if indexing:
            self._err = _errors.IndexerError
        else:
            self._err = _errors.SearchError

    def marshall_string(self, fieldname, value):
        """Marshall a value for sorting in lexicograpical order.

        This returns the input as the output, since strings already sort in
        lexicographical order.

        """
        return value

    def marshall_float(self, fieldname, value):
        """Marshall a value for sorting as a floating point value.

        """
        # convert the value to a float
        try:
            value = float(value)
        except ValueError:
            raise self._err("Value supplied to field %r must be a "
                            "valid floating point number: was %r" %
                            (fieldname, value))
        return _marshall.float_to_string(value)

    def marshall_date(self, fieldname, value):
        """Marshall a value for sorting as a date.

        """
        try:
            value = _parsedate.date_from_string(value)
        except ValueError, e:
            raise self._err("Value supplied to field %r must be a "
                            "valid date: was %r: error is '%s'" %
                            (fieldname, value, str(e)))
        return _marshall.date_to_string(value)

    def get_marshall_function(self, fieldname, sorttype):
        """Get a function used to marshall values of a given sorttype.

        """
        try:
            return {
                None: self.marshall_string,
                'string': self.marshall_string,
                'float': self.marshall_float,
                'date': self.marshall_date,
            }[sorttype]
        except KeyError:
            raise self._err("Unknown sort type %r for field %r" %
                            (sorttype, fieldname))


def _act_sort_and_collapse(fieldname, doc, value, context, type=None):
    """Perform the SORTABLE action.

    """
    marshaller = SortableMarshaller()
    fn = marshaller.get_marshall_function(fieldname, type)
    value = fn(fieldname, value)
    doc.add_value(fieldname, value)

class ActionContext(object):
    """The context in which an action is performed.

    This is just used to pass term generators, word positions, and the like
    around.

    """
    def __init__(self, index):
        self.current_language = None
        self.current_position = 0
        self.index = index

class FieldActions(object):
    """An object describing the actions to be performed on a field.

    The supported actions are:
    
    - `STORE_CONTENT`: store the unprocessed content of the field in the search
      engine database.  All fields which need to be displayed or used when
      displaying the search results need to be given this action.

    - `INDEX_EXACT`: index the exact content of the field as a single search
      term.  Fields whose contents need to be searchable as an "exact match"
      need to be given this action.

    - `INDEX_FREETEXT`: index the content of this field as text.  The content
      will be split into terms, allowing free text searching of the field.  Four
      optional parameters may be supplied:

      - 'weight' is a multiplier to apply to the importance of the field.  This
        must be an integer, and the default value is 1.
      - 'language' is the language to use when processing the field.  This can
        be expressed as an ISO 2-letter language code.  The supported languages
        are those supported by the xapian core in use.
      - 'stop' is an iterable of stopwords to filter out of the generated
        terms.  Note that due to Xapian design, only non-positional terms are
        affected, so this is of limited use.
      - 'spell' is a boolean flag - if true, the contents of the field will be
        used for spelling correction.
      - 'nopos' is a boolean flag - if true, positional information is not
        stored.
      - 'noprefix' is a boolean flag - if true, prevents terms with the field
        prefix being generated.  This means that searches specific to this
        field will not work, and thus should only be used for special cases.

    - `SORTABLE`: index the content of the field such that it can be used to
      sort result sets.  It also allows result sets to be restricted to those
      documents with a field values in a given range.  One optional parameter
      may be supplied:

      - 'type' is a value indicating how to sort the field.  It has several
        possible values:

        - 'string' - sort in lexicographic (ie, alphabetical) order.
          This is the default, used if no type is set.
        - 'float' - treat the values as (decimal representations of) floating
          point numbers, and sort in numerical order .  The values in the field
          must be valid floating point numbers (according to Python's float()
          function).
        - 'date' - sort in date order.  The values must be valid dates (either
          Python datetime.date objects, or ISO 8601 format (ie, YYYYMMDD or
          YYYY-MM-DD).

    - `COLLAPSE`: index the content of the field such that it can be used to
      "collapse" result sets, such that only the highest result with each value
      of the field will be returned.

    """

    # See the class docstring for the meanings of the following constants.
    STORE_CONTENT = 1
    INDEX_EXACT = 2
    INDEX_FREETEXT = 3
    SORTABLE = 4 
    COLLAPSE = 5

    # Sorting and collapsing store the data in a value, but the format depends
    # on the sort type.  Easiest way to implement is to treat them as the same
    # action.
    SORT_AND_COLLAPSE = -1

    # NEED_SLOT is a flag used to indicate that an action needs a slot number
    NEED_SLOT = 1
    # NEED_PREFIX is a flag used to indicate that an action needs a prefix
    NEED_PREFIX = 2

    def __init__(self, fieldname):
        # Dictionary of actions, keyed by type.
        self._actions = {}
        self._fieldname = fieldname

    def add(self, field_mappings, action, **kwargs):
        """Add an action to perform on a field.

        """
        if action not in (FieldActions.STORE_CONTENT,
                          FieldActions.INDEX_EXACT,
                          FieldActions.INDEX_FREETEXT,
                          FieldActions.SORTABLE,
                          FieldActions.COLLAPSE,):
            raise _errors.IndexerError("Unknown field action: %r" % action)

        info = self._action_info[action]

        # Check parameter names
        for key in kwargs.keys():
            if key not in info[1]:
                raise _errors.IndexerError("Unknown parameter name for action %r: %r" % (info[0], key))

        # Fields cannot be indexed both with "EXACT" and "FREETEXT": whilst we
        # could implement this, the query parser wouldn't know what to do with
        # searches.
        if action == FieldActions.INDEX_EXACT:
            if FieldActions.INDEX_FREETEXT in self._actions:
                raise _errors.IndexerError("Field %r is already marked for indexing "
                                   "as free text: cannot mark for indexing "
                                   "as exact text as well" % self._fieldname)
        if action == FieldActions.INDEX_FREETEXT:
            if FieldActions.INDEX_EXACT in self._actions:
                raise _errors.IndexerError("Field %r is already marked for indexing "
                                   "as exact text: cannot mark for indexing "
                                   "as free text as well" % self._fieldname)

        # Fields cannot be indexed as more than one type for "SORTABLE": to
        # implement this, we'd need to use a different prefix for each sortable
        # type, but even then the search end wouldn't know what to sort on when
        # searching.  Also, if they're indexed as "COLLAPSE", the value must be
        # stored in the right format for the type "SORTABLE".
        if action == FieldActions.SORTABLE or action == FieldActions.COLLAPSE:
            if action == FieldActions.COLLAPSE:
                sorttype = None
            else:
                try:
                    sorttype = kwargs['type']
                except KeyError:
                    sorttype = 'string'
            kwargs['type'] = sorttype
            action = FieldActions.SORT_AND_COLLAPSE

            try:
                oldsortactions = self._actions[FieldActions.SORT_AND_COLLAPSE]
            except KeyError:
                oldsortactions = ()

            if len(oldsortactions) > 0:
                for oldsortaction in oldsortactions:
                    oldsorttype = oldsortaction['type']

                if sorttype == oldsorttype or oldsorttype is None:
                    # Use new type
                    self._actions[action] = []
                elif sorttype is None:
                    # Use old type
                    return
                else:
                    raise _errors.IndexerError("Field %r is already marked for "
                                               "sorting, with a different "
                                               "sort type" % self._fieldname)
        
        if self.NEED_PREFIX in info[3]:
            field_mappings.add_prefix(self._fieldname)
        if self.NEED_SLOT in info[3]:
            field_mappings.add_slot(self._fieldname)

        # Make an entry for the action
        if action not in self._actions:
            self._actions[action] = []

        # Check for repetitions of actions
        for old_action in self._actions[action]:
            if old_action == kwargs:
                return

        # Append the action to the list of actions
        self._actions[action].append(kwargs)

    def perform(self, doc, value, context):
        """Perform the actions on the field.

        - `doc` is a ProcessedDocument to store the result of the actions in.
        - `value` is a string holding the value of the field.
        - `context` is an ActionContext object used to keep state in.

        """
        for type, actionlist in self._actions.iteritems():
            info = self._action_info[type]            
            for kwargs in actionlist:
                info[2](self._fieldname, doc, value, context, **kwargs)

    _action_info = {
        STORE_CONTENT: ('STORE_CONTENT', (), _act_store_content, (), ),
        INDEX_EXACT: ('INDEX_EXACT', (), _act_index_exact, (NEED_PREFIX,), ),
        INDEX_FREETEXT: ('INDEX_FREETEXT', ('weight', 'language', 'stop', 'spell', 'nopos', 'noprefix', ), 
            _act_index_freetext, (NEED_PREFIX, ), ),
        SORTABLE: ('SORTABLE', ('type', ), None, (NEED_SLOT,), ),
        COLLAPSE: ('COLLAPSE', (), None, (NEED_SLOT,), ),
        SORT_AND_COLLAPSE: ('SORT_AND_COLLAPSE', ('type', ), _act_sort_and_collapse, (NEED_SLOT,), ),
    }

if __name__ == '__main__':
    import doctest, sys
    doctest.testmod (sys.modules[__name__])
