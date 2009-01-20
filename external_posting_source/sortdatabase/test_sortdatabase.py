#!/usr/bin/env python

def make_sort_array(filename, length):
    import numpy
    import random
    mm=numpy.memmap(filename, numpy.int32, 'w+', shape=(50,))
    for num in xrange(length):
        mm[num] = num + 1
    random.shuffle(mm)

def make_sample_db(dbpath, length):
    import xapian
    db = xapian.WritableDatabase(dbpath, xapian.DB_CREATE)
    for num in xrange(1, length + 1):
        doc = xapian.Document()
        doc.add_term("T%d" % num)
        db.add_document(doc)

if __name__ == '__main__':
    length = 50
    make_sort_array('sortdatabase_test.dborder', length)
    make_sample_db('sortdatabase_test.db', length)
