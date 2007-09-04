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
import pylab
import sys

def get_av_docspersec(times, interval):
    docspersec = []
    docs = []
    for i in xrange(interval, len(times)):
        docinterval = times[i].docs - times[i-interval].docs
        timeinterval = times[i].time - times[i-interval].time
        docspersec.append(docinterval / timeinterval)
        docs.append(times[i].docs / 1000)
    return docspersec, docs, times[interval].docs - times[0].docs

def generate_figures(times, outprefix, pretitle):
    # Generate a "total time" versus "total documents" plot
    total_times = [row.time / 3600.0 for row in times]
    total_documents = [row.docs / 1000 for row in times]
    pylab.plot(total_times, total_documents)
    pylab.xlabel('Time (hours)')
    pylab.ylabel('Documents (x1000)')
    pylab.title(pretitle + r': documents indexed after a given time')
    pylab.axis([0, max(total_times) * 1.05, 0, max(total_documents) * 1.05])
    pylab.savefig(outprefix + "totaltime_v_totaldocs.png", format="png")

    # Generate a "documents/second" plot
    pylab.figure()
    docspersec_av1, docs_av1, docinterval = get_av_docspersec(times, 1)
    pylab.plot(docs_av1, docspersec_av1)
    pylab.xlabel('Documents (x1000)')
    pylab.ylabel('Docs per second')
    pylab.title(pretitle + ': indexing rate versus documents processed\nAveraged every %d documents' % docinterval)
    pylab.axis([0, max(docs_av1) * 1.05, 0, max(docspersec_av1) * 1.05])
    pylab.savefig(outprefix + "docspersec_v_totaldocs_av1.png", format="png")

    pylab.figure()
    docspersec_av100, docs_av100, docinterval = get_av_docspersec(times, 100)
    pylab.plot(docs_av100, docspersec_av100)
    pylab.xlabel('Documents (x1000)')
    pylab.ylabel('Docs per second')
    pylab.title(pretitle + ': indexing rate versus documents processed\nAveraged every %d documents' % docinterval)
    pylab.axis([0, max(docs_av100) * 1.05, 0, max(docspersec_av100) * 1.05])
    pylab.savefig(outprefix + "docspersec_v_totaldocs_av100.png", format="png")


class logrow(object):
    __slots__ = ('action', 'docs', 'time', 'dbsize', 'inputsize')
    def __init__(self, action, docs, time, dbsize, inputsize):
        self.action = action
        self.docs = float(docs)
        self.time = float(time)
        self.dbsize = float(dbsize)
        self.inputsize = float(inputsize)

def parse_logfile(filename):
    fd = open(filename)
    times = []
    titles = None
    for row in csv.reader(fd):
        if titles is None:
            titles = row
        else:
            newrow = logrow(*row)
            if len(times) > 0 and times[-1].docs == newrow.docs:
                times[-1] = newrow
            else:
                times.append(newrow)
    return times

if __name__ == '__main__':
    try:
        filename = sys.argv[1]
        outprefix = sys.argv[2]
        pretitle = sys.argv[3]
    except IndexError:
        print "Usage: %s <logfile> <outprefix> <pretitle>" % sys.argv[0]
        sys.exit(1)

    times = parse_logfile(filename)
    generate_figures(times, outprefix, pretitle)
