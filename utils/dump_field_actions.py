#!/usr/bin/env python
#
# Copyright (C) 2008 Lemur Consulting Ltd
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
import xappy

actionnames = {
    xappy.FieldActions.STORE_CONTENT: "STORE_CONTENT",
    xappy.FieldActions.INDEX_EXACT: "INDEX_EXACT",
    xappy.FieldActions.INDEX_FREETEXT: "INDEX_FREETEXT",
    xappy.FieldActions.SORTABLE: "SORTABLE",
    xappy.FieldActions.COLLAPSE: "COLLAPSE",
    xappy.FieldActions.TAG: "TAG",
    xappy.FieldActions.FACET: "FACET",
    xappy.FieldActions.WEIGHT: "WEIGHT",
    xappy.FieldActions.SORT_AND_COLLAPSE: "SORT_AND_COLLAPSE",
}

def dump_field_actions(fieldname, actions):
    for actiontype, kwargslist in actions._actions.iteritems():
        actionname = actionnames.get(actiontype)
        for kwargs in kwargslist:
            print "(%r, %s, %s)" % (fieldname, actionname, repr(kwargs))

def dump_actions(conn, fieldname):
    if fieldname is None:
        fields = conn._field_actions.keys()
        fields.sort()
    else:
        fields = (fieldname, )
    for field in fields:
        actions = conn._field_actions[field]
        dump_field_actions(field, actions)

usage = """
dump_field_actions.py <dbpath> [fieldname]
"""

def run_from_commandline():
    import sys
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print usage.strip()
        sys.exit(1)

    dbpath = sys.argv[1]
    if len(sys.argv) == 3:
        fieldname = sys.argv[2]
    else:
        fieldname = None

    conn = xappy.SearchConnection(dbpath)
    dump_actions(conn, fieldname)

if __name__ == "__main__":
    run_from_commandline()
