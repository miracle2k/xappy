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

import os
import sys
import time

def _setup_path():
    """Set up sys.path to allow us to import secore when run uninstalled.

    """
    abspath = os.path.abspath(__file__)
    dirname = os.path.dirname(abspath)
    dirname, ourdir = os.path.split(dirname)
    if os.path.exists(os.path.join(dirname, 'secore')):
        if ourdir == 'perftest':
            sys.path.insert(0, dirname)

_setup_path()
import secore

def create_index(dbpath):
    """Create a new index, and set up its field structure.

    """
    iconn = secore.IndexerConnection(dbpath)

    iconn.add_field_action('title', secore.FieldActions.STORE_CONTENT)
    iconn.add_field_action('title', secore.FieldActions.INDEX_FREETEXT,
                           language="en", weight=5)

    iconn.add_field_action('text', secore.FieldActions.STORE_CONTENT)
    iconn.add_field_action('text', secore.FieldActions.INDEX_FREETEXT,
                           language='en')

    iconn.add_field_action('doclen', secore.FieldActions.STORE_CONTENT)
    iconn.add_field_action('doclen', secore.FieldActions.SORTABLE, type='float')
    iconn.add_field_action('doclen', secore.FieldActions.COLLAPSE)

    iconn.close()

def open_index(dbpath):
    """Open an existing index.

    """
    return secore.IndexerConnection(dbpath)

def dirsize(dirname):
    size = 0
    for dirpath, dirnames, filenames in os.walk(dirname):
        for filename in filenames:
            size += os.stat(os.path.join(dirpath, filename)).st_size
    return size

def log_entry(logfd, dbdir, action, addcount, starttime, inputsize):
    currtime = time.time()
    dbsize = dirsize(dbdir)
    logfd.write("%s,%d,%f,%d,%d\n" % (action, addcount, currtime - starttime, dbsize, inputsize))
    logfd.flush()

def index_file(iconn, dbdir, dumpfd, logfd, flushspeed):
    """Index a file."""

    logfd.write("Action,Documents Added,Time(seconds),dbsize(bytes),inputsize(bytes)\n")
    logfd.flush()
    starttime = time.time()
    linenum = 0
    addcount = 0
    doc = secore.UnprocessedDocument()
    doclen = 0
    inputsize = 0
    fieldlen = 0
    while True:
        line = dumpfd.readline()
        linenum += 1

        if len(line) == 0:
            break
        if line[0] == '=' and len(doc.fields) > 0 and len(doc.fields[-1].value) > 1000:
            # Truncate fields of more than 1000 characters, for a more
            # reasonable data size.
            continue

        inputsize += len(line)
        line = line.rstrip('\n\r')
        if len(line) == 0:
            if len(doc.fields) != 0:
                doc.fields.append(secore.Field('doclen', doclen))
                iconn.add(doc)
                addcount += 1
                if addcount % 1000 == 0:
                    log_entry(logfd, dbdir, "A", addcount, starttime, inputsize)
                if flushspeed is not None and (addcount % flushspeed) == 0:
                    iconn.flush()
                    log_entry(logfd, dbdir, "F", addcount, starttime, inputsize)
                doc = secore.UnprocessedDocument()
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
            doc.fields.append(secore.Field(line[:equals], line[equals + 1:]))
            if doc.fields[-1].name == 'id':
                doc.id = doc.fields[-1].value
            elif doc.fields[-1].name == 'text':
                doclen = len(doc.fields[-1].value)

    # Add any left-over documents
    if len(doc.fields) != 0:
        doc.fields.append(secore.Field('doclen', doclen))
        iconn.add(doc)
        addcount += 1
    log_entry(logfd, dbdir, "A", addcount, starttime, inputsize)
    iconn.flush()
    log_entry(logfd, dbdir, "F", addcount, starttime, inputsize)

def main(dumpfile, dbdir, logfile, flushspeed):
    create_index(dbdir)
    iconn = open_index(dbdir)
    dumpfd = open(dumpfile)
    logfd = open(logfile, "a")
    index_file(iconn, dbdir, dumpfd, logfd, flushspeed)

def parse_argv(argv):
    if len(argv) < 4 or len(argv) > 5:
        print("Usage: index_from_dump.py <dumpfile> <dbdir> <logfile> [<flushnum>]")
        sys.exit(1)
    if len(argv) == 5:
        return argv[1], argv[2], argv[3], int(argv[4])
    else:
        return argv[1], argv[2], argv[3], None

if __name__ == '__main__':
    dumpfile, dbdir, logfile, flushspeed = parse_argv(sys.argv)
    main(dumpfile, dbdir, logfile, flushspeed)
