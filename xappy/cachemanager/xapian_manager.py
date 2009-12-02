#!/usr/bin/env python
#
# Copyright (C) 2009 Richard Boulton
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
r"""xapian_manager.py: Cache manager using Xapian as its storage backend.

"""
__docformat__ = "restructuredtext en"

import generic
import os
import shutil
import tempfile
import xapian

class XapianCacheManager(generic.KeyValueStoreCacheManager):
    """A cache manager that stores the cached items in a Xapian database.

    Note: we need to change this if we need to support keys which are longer
    than 240 characters or so.  We could fix this by using a hashing scheme for
    the tail of such keys, and add some handling for collisions.

    This class uses the default implementation of iter_by_docid().  Subclasses
    provide other implementations of iter_by_docid(), which may be more
    efficient for some situations.

    """
    def __init__(self, dbpath, chunksize=None):
        self.dbpath = dbpath
        self.db = None
        self.writable = False
        generic.KeyValueStoreCacheManager.__init__(self, chunksize)

    def __getitem__(self, key):
        if self.db is None:
            try:
                self.db = xapian.Database(self.dbpath)
            except xapian.DatabaseOpeningError: 
                if not os.path.exists(self.dbpath):
                    # Not created yet - no value.
                    return ''
                raise
            self.writable = False
        return self.db.get_metadata(key)

    def __setitem__(self, key, value):
        if self.db is None or not self.writable:
            self.db = xapian.WritableDatabase(self.dbpath,
                                              xapian.DB_CREATE_OR_OPEN)
            self.writable = True
        self.db.set_metadata(key, value)
        self.invalidate_iter_by_docid()

    def __delitem__(self, key):
        if self.db is None or not self.writable:
            self.db = xapian.WritableDatabase(self.dbpath,
                                              xapian.DB_CREATE_OR_OPEN)
            self.writable = True
        self.db.set_metadata(key, '')
        self.invalidate_iter_by_docid()

    def keys(self):
        if self.db is None:
            try:
                self.db = xapian.Database(self.dbpath)
            except xapian.DatabaseOpeningError: 
                if not os.path.exists(self.dbpath):
                    # Not created yet - no values
                    return iter(())
                raise
            self.writable = False
        return self.db.metadata_keys()

    def flush(self):
        if self.db is None or not self.writable:
            return
        self.db.flush()

    def close(self):
        if self.db is None:
            return
        self.db.close()
        self.db = None

class XapianSelfInvertingCacheManager(XapianCacheManager):
    """Cache manager using Xapian both as a key-value store, and as a mechanism
    for implementing the inversion process required by iter_by_docid.

    """
    def __init__(self, *args, **kwargs):
        XapianCacheManager.__init__(self, *args, **kwargs)
        self.inverted = False
        self.inverted_db_path = os.path.join(self.dbpath, 'inv')

    def prepare_iter_by_docid(self):
        """Prepare to iterate by document ID.
        
        This makes a Xapian database, in which each document represents a
        cached query, and is indexed by terms corresponding to the document IDs
        of the making terms.

        This is used to get the inverse of the queryid->docid list mapping
        provided to the cache.

        """
        if self.inverted: return

        if not os.path.exists(self.dbpath):
            self.inverted = True
            return

        shutil.rmtree(self.inverted_db_path, ignore_errors=True)
        invdb = xapian.WritableDatabase(self.inverted_db_path,
                                        xapian.DB_CREATE_OR_OPEN)
        try:
            for qid in self.iter_queryids():
                doc = xapian.Document()
                for rank, docid in enumerate(self.get_hits(qid)):
                    # We store the docid encoded as the term (encoded such that
                    # it will sort lexicographically into numeric order), and
                    # the rank as the wdf.
                    term = '%x' % docid
                    term = ('%x' % len(term)) + term
                    doc.add_term(term, rank)
                newdocid = invdb.add_document(doc)

                assert(newdocid == qid + 1)
            invdb.flush()
        finally:
            invdb.close()

        self.inverted = True

    def invalidate_iter_by_docid(self):
        if not self.inverted:
            return
        shutil.rmtree(self.inverted_db_path, ignore_errors=True)
        self.inverted = False

    def iter_by_docid(self):
        """Implementation of iter_by_docid() which uses a temporary Xapian
        database to perform the inverting of the queryid->docid list mapping,
        to return the docid->queryid list mapping.

        This uses an on-disk database, so is probably a bit slower than the
        naive implementation for small cases, but should scale arbitrarily (as
        well as Xapian does, anyway).

        It would be faster if we could tell Xapian not to perform fsyncs for
        the temporary database.

        """
        self.prepare_iter_by_docid()

        if os.path.exists(self.dbpath):
            invdb = xapian.Database(self.inverted_db_path)
        else:
            invdb = xapian.Database()

        try:

            for item in invdb.allterms():
                docid = int(item.term[1:], 16)
                items = tuple((item.docid - 1, item.wdf) for item in invdb.postlist(item.term))
                yield docid, items
            invdb.close()

        finally:
            invdb.close()
