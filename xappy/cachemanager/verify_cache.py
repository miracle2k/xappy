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

class Handler(object):
    """Default handler context.

    """

    def __init__(self):
        self.failcount = 0
        self.failmax = 100

    def fail_handler(self, msg):
        """Handler for a failure.

        `msg` is the message describing the failure.

        """
        print "Error:", msg
        self.failcount +=1
        if self.failcount >= self.failmax:
            raise RuntimeError("Too many failures - aborting verification")

    def info_handler(self, msg):
        """Handler for an informative message.

        `msg` is the message.

        """
        print msg

def verify(dbpath, fail_cb, info_cb):
    """Verify that a cache stored in a database has been applied correctly.

    - `dbpath` is the path to the database.

    - `fail_cb` is the callback to call for a failure.  It is supplied with a
      single string of text describing the failure, and may be called multiple
      times.  It may raise an exception to escape from the verification routine
      if it doesn't wish the verification to continue.

    - `info_cb` is the callback to call for informative messages.  It is
      supplied with a single string of text giving information about the
      verification process.

    Returns True if the cache verified ok, False if any errors were found.

    """
    db = xapian.Database(dbpath)
    cm = xappy.cachemanager.XapianCacheManager(dbpath)
    ok = True

    info_cb("Starting verification for %r" % dbpath)
    info_cb("Checking for querystr->queryid mapping")
    queryids = {}
    for querystr in cm.iter_query_strs():
        queryid = cm.get_queryid(querystr)
        if queryid in queryids:
            fail_cb("queryid %d occurs multiple times: for both querystr "
                    "%r and %r" % (queryid, querystr, queryids[queryid]))
            ok = False
        queryids[queryid] = querystr

    info_cb("Checking queryids")
    for queryid in cm.iter_queryids():
        if queryid not in queryids:
            fail_cb("queryid %d not found in querystr->queryid mapping" %
                    queryid)
            ok = False

    info_cb("Checking values stored in cached documents")
    for queryid in cm.iter_queryids():
        hits = cm.get_hits(queryid)
        prevvalue = None
        slot = queryid + 10000
        missing_values = []
        for docid in hits:
            doc = db.get_document(docid)
            value = doc.get_value(slot)
            if value == '':
                missing_values.append(docid)
                continue
            if prevvalue is not None:
                if value >= prevvalue:
                    fail_cb("Values in wrong order for queryid %d: %r "
                            "followed by %r" % (queryid, prevvalue, value))
                    ok = False
                    continue
            prevvalue = value
        if len(missing_values) != 0:
            if len(missing_values) > 10:
                fail_cb("%d/%d missing values in slot %d for queryid %d: "
                        "starting with %r" %
                        (len(missing_values), len(hits), slot, queryid,
                         missing_values[:10]))
            else:
                fail_cb("%d/%d missing values in slot %d for queryid %d: %r" %
                        (len(missing_values), len(hits), slot, queryid,
                         missing_values))
            ok = False

    info_cb("Checking valuestreams match cached values")
    if not hasattr(db, 'valuestream'):
        info_cb("Skipping check - xapian version in use does not support "
                "valuestream iterators")
    else:
        for queryid in cm.iter_queryids():
            hits = cm.get_hits(queryid)
            storedhits = []
            for item in db.valuestream(queryid + 10000):
                storedhits.append(item.value, item.docid)
            storedhits.sort()
            storedhits = [item[1] for item in storedhits]
            if hits != storedhits:
                fail_cb("Stored hits do not match hits in cache for queryid "
                        "%d: cache has %r, stored hits are %r" %
                        (queryid, hits, storedhits))
                ok = False

    return ok

if __name__ == '__main__':
    import sys
    handler = Handler()
    verify(sys.argv[1], handler.fail_handler, handler.info_handler)
