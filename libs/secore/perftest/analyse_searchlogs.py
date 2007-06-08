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

def generate_figures(log, outprefix, pretitle):
    query_v_time = [(row.time, row.query) for row in log]
    query_v_time.sort()
    query_v_time.reverse()
    print "Average speed: %f seconds" % (sum((row.time for row in log)) / len(log))
    print "Slowest queries:"
    for time, query in query_v_time[:10]:
        print "%s: %f seconds" % (query, time)

    # Generate a "total time" versus "total documents" plot
    total_times = [row.tottime for row in log]
    query_times = [row.time for row in log]

    pylab.figure(figsize=(8,12))
    pylab.subplot(311)
    pylab.plot(total_times)
    pylab.xlabel('Queries completed')
    pylab.ylabel('Total time (seconds)')
    pylab.title(pretitle + '\nQueries completed after given time')

    pylab.subplot(312)
    pylab.axis([0, len(query_times), 0, max(query_times) * 1.05])
    pylab.plot(query_times)
    pylab.xlabel('Queries completed')
    pylab.ylabel('Query time (seconds)')
    pylab.title('Query times')

    pylab.subplot(313)
    pylab.axis([0, len(query_times), 0, 50])
    pylab.hist(query_times, 50, log="true")
    pylab.xlabel('Query time (seconds)')
    pylab.ylabel('Queries')
    pylab.title('Query time histogram')
    pylab.savefig(outprefix + "query_times.png", format="png")

class logrow(object):
    __slots__ = ('thread', 'querycount', 'matchingcount', 'estmatches', 'time',
                 'tottime', 'querywords', 'query')

    def __init__(self, thread, querycount, matchingcount, estmatches, time,
                 tottime, querywords, query):
        self.thread = int(thread)
        self.querycount = int(querycount)
        self.matchingcount = int(matchingcount)
        self.estmatches = int(estmatches)
        self.time = float(time)
        self.tottime = float(tottime)
        self.querywords = int(querywords)
        self.query = query

def parse_logfile(filename):
    fd = open(filename)
    times = []
    titles = None
    for row in csv.reader(fd):
        if titles is None:
            titles = row
        else:
            if len(row) > 8:
                enditem = row[7:]
                row = row[:7]
                row.append(','.join(enditem))
            newrow = logrow(*row)
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

    log = parse_logfile(filename)
    generate_figures(log, outprefix, pretitle)
