#!/usr/bin/env python
#
# Copyright (C) 2009 Richard Boulton
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
r"""xapian_manager.py: Cache manager using Xapian as its storage backend.

"""
__docformat__ = "restructuredtext en"

import generic
import os
import xapian

class XapianCacheManager(generic.KeyValueStoreCacheManager):
    """A cache manager that stores the cached items in a Xapian database.

    Note: we need to change this if we need to support keys which are longer
    than 240 characters or so.  We could fix this by using a hashing scheme for
    the tail of such keys, and add some handling for collisions.

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

    def __delitem__(self, key):
        if self.db is None or not self.writable:
            self.db = xapian.WritableDatabase(self.dbpath,
                                              xapian.DB_CREATE_OR_OPEN)
            self.writable = True
        self.db.set_metadata(key, '')

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
