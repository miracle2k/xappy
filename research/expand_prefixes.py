#!/usr/bin/env python2.5

# Script to take a xappy database, and build a xapian database from the first
# 10000 documents, expanding the xappy prefixes into full fieldnames.  This is
# to compare the sizes of the resulting databases.

import xapian
import xappy

def split_prefix(term):
    if term[0] == 'Z':
        term = term[1:]
        z = 'Z'
    else:
        z = ''
    for i in xrange(len(term)):
        if term[i] == ':':
            return term[:i], z + term[i+1:]
        if not term[i].isupper():
            return term[:i], z + term[i:]
    return '', z + term

def expand_term(term):
    prefix, term = split_prefix(term)
    field = fieldname.get(prefix, prefix)
    if field != '':
        return field + ':' + term
    return term

sconn = xappy.SearchConnection("in")
fieldname = dict((v, k) for (k, v) in sconn._field_mappings._prefixes.iteritems())
newdb = xapian.WritableDatabase("out", xapian.DB_CREATE_OR_OVERWRITE)

count = 10000
for doc in sconn.iter_documents():
    newdoc = xapian.Document()
    for item in doc._doc.termlist():
        #term = item.term
        term = expand_term(item.term)
        newdoc.add_term(term, item.wdf)
        for position in item.positer:
            newdoc.add_posting(term, position, 0)
    newdb.add_document(newdoc)

    count -= 1
    if count <= 0: break
