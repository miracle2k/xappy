# Copyright (C) 2010 Richard Boulton
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
"""Verify that a cache stored in a database has been applied correctly.

"""

import xapian
import xappy.cachemanager

def default_fail_handler(msg):
    """Default handler for a failure.

    `msg` is the message describing the failure.

    """
    print "Error:", msg

def verify(dbpath, fail_cb):
    """Verify that a cache stored in a database has been applied correctly.

    - `dbpath` is the path to the database.

    - `fail_cb` is the callback to call for a failure.  It is supplied with a
      single string of text describing the failure, and may be called multiple
      times.  It may raise an exception to escape from the verification routine
      if it doesn't wish the verification to continue.

    """
    db = xapian.Database(dbpath)
    cm = xappy.cachemanager.XapianCacheManager(dbpath)

    queryids = {}
    for querystr in cm.iter_query_strs():
        queryid = cm.get_queryid(querystr)
        if queryid in queryids:
            fail_cb("queryid %d occurs multiple times: for both querystr "
                    "%r and %r" % (queryid, querystr, queryids[queryid]))
        queryids[queryid] = querystr

    for queryid in cm.iter_queryids():
        hits = cm.get_hits(queryid)
        storedhits = []
        for item in db.valuestream(queryid + 10000):
            storedhits.append(item.value, item.docid)
        storedhits.sort()
        storedhits = [item[1] for item in storedhits]
        if hits != storedhits:
            fail_cb("Stored hits do not match hits in cache for queryid %d: "
                    "cache has %r, stored hits are %r" %
                    (queryid, hits, storedhits))

if __name__ == '__main__':
    import sys
    verify(sys.argv[1], default_fail_handler)
