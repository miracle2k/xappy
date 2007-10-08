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

import csv
import os
import sys
import time
import xappy

class CsvLogger(object):
    def __init__(self, filepath):
        self.fd = open(filepath, 'ab')
        self.csvwriter = csv.writer(self.fd)

    def log(self, *args):
        self.csvwriter.writerow(args)
        self.fd.flush()

def create_index(dbpath):
    """Create a new index, and set up its field structure.

    """
    iconn = xappy.IndexerConnection(dbpath)

    iconn.add_field_action('title', xappy.FieldActions.STORE_CONTENT)
    iconn.add_field_action('title', xappy.FieldActions.INDEX_FREETEXT,
                           language="en", weight=5)

    iconn.add_field_action('text', xappy.FieldActions.STORE_CONTENT)
    iconn.add_field_action('text', xappy.FieldActions.INDEX_FREETEXT,
                           language='en')

    iconn.add_field_action('doclen', xappy.FieldActions.STORE_CONTENT)
    iconn.add_field_action('doclen', xappy.FieldActions.SORTABLE, type='float')
    iconn.add_field_action('doclen', xappy.FieldActions.COLLAPSE)

    iconn.close()

def open_index(dbpath):
    """Open an existing index.

    """
    return xappy.IndexerConnection(dbpath)

def dirsize(dirname):
    size = 0
    for dirpath, dirnames, filenames in os.walk(dirname):
        for filename in filenames:
            size += os.stat(os.path.join(dirpath, filename)).st_size
    return size

def log_entry(logger, dbpath, addcount, starttime, inputsize):
    currtime = time.time()
    dbsize = dirsize(dbpath)
    logger.log(addcount, currtime - starttime, dbsize, inputsize)

def index_scriptindex_file(iconn, dbpath, dumpfd, logger, flushspeed, maxdocs,
                           logspeed):
    """Index a xapian "scriptindex" format file.

    """
    logger.log("Documents Added", "Time(seconds)", "dbsize(bytes)", "inputsize(bytes)")
    starttime = time.time()
    linenum = 0
    addcount = 0
    doc = xappy.UnprocessedDocument()
    doclen = 0
    inputsize = 0
    fieldlen = 0
    while maxdocs is None or addcount < maxdocs:
        line = dumpfd.readline()
        linenum += 1

        if len(line) == 0:
            break

        inputsize += len(line)
        line = line.rstrip('\n\r')
        if len(line) == 0:
            if len(doc.fields) != 0:
                doc.fields.append(xappy.Field('doclen', doclen))
                iconn.add(doc)
                addcount += 1
                if flushspeed is not None and (addcount % flushspeed) == 0:
                    iconn.flush()
                if addcount % logspeed == 0:
                    log_entry(logger, dbpath, addcount, starttime, inputsize)
                doc = xappy.UnprocessedDocument()
            continue

        if line[0] == '#':
            continue

        equals = line.find("=")
        if equals == -1:
            raise ValueErrror("Missing '=' in line %d" % linenum)
        elif equals == 0:
            if len(doc.fields) == 0:
                raise ValueError("Continuation line %d is first in document" % linenum)
            else:
                doc.fields[-1].value += '\n' + line[1:]
                if doc.fields[-1].name == 'text':
                    doclen = len(doc.fields[-1].value)
        else:
            doc.fields.append(xappy.Field(line[:equals], line[equals + 1:]))
            if doc.fields[-1].name == 'id':
                doc.id = doc.fields[-1].value
            elif doc.fields[-1].name == 'text':
                doclen = len(doc.fields[-1].value)

    # Add any left-over documents
    if len(doc.fields) != 0:
        doc.fields.append(xappy.Field('doclen', doclen))
        iconn.add(doc)
        addcount += 1
    iconn.flush()
    log_entry(logger, dbpath, addcount, starttime, inputsize)

def index_file(inputfile, dbpath, logpath, flushspeed, description, maxdocs, logspeed):
    create_index(dbpath)
    iconn = open_index(dbpath)
    dumpfd = open(inputfile)
    logger = CsvLogger(logpath)
    descline = [description, "flushspeed=%d" % flushspeed]
    if maxdocs is not None:
        descline.append("maxdocs=%d" % maxdocs)
    if logspeed is not None:
        descline.append("logspeed=%d" % logspeed)
    logger.log(*descline)
    index_scriptindex_file(iconn, dbpath, dumpfd, logger, flushspeed, maxdocs,
                           logspeed)

