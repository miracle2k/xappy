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

def get_av_docspersec(times, interval, docscale):
    docspersec = []
    docs = []
    for i in xrange(interval, len(times)):
        docinterval = times[i].docs - times[i-interval].docs
        timeinterval = times[i].time - times[i-interval].time
        docspersec.append(docinterval / timeinterval)
        docs.append(times[i].docs / docscale)
    if interval >= len(times):
        return docspersec, docs, 0
    else:
        return docspersec, docs, times[interval].docs - times[0].docs

def calc_docscale(times):
    docscale = 1000
    if len(times) > 2:
        docdiff = times[1].docs - times[0].docs
        while docscale > 1 and docdiff <= docscale:
            docscale //= 10

    if docscale == 1:
        docscalestr = ""
    else:
        docscalestr = " (x%d)" % docscale

    return docscale, docscalestr

def generate_figures(times, outprefix, pretitle):
    docscale, docscalestr = calc_docscale(times)

    # Generate a "total time" versus "total documents" plot
    if len(times) > 1:
        pylab.figure()
        total_times = [row.time / 3600.0 for row in times]
        total_documents = [row.docs / docscale for row in times]
        pylab.plot(total_times, total_documents)
        pylab.xlabel('Time (hours)')
        pylab.ylabel('Documents%s' % docscalestr)
        pylab.title(pretitle + r': documents indexed after a given time')
        pylab.axis([0, max(total_times) * 1.05, 0, max(total_documents) * 1.05])
        pylab.savefig(outprefix + "totaltime_v_totaldocs.png", format="png")

    # Generate a "documents/second" plot
    docspersec_av1, docs_av1, docinterval = get_av_docspersec(times, 1, docscale)
    if len(docs_av1) > 1:
        pylab.figure()
        pylab.plot(docs_av1, docspersec_av1)
        pylab.xlabel('Documents%s' % docscalestr)
        pylab.ylabel('Docs per second')
        pylab.title(pretitle + ': indexing rate versus documents processed\nAveraged every %d documents' % docinterval)
        pylab.axis([0, max(docs_av1) * 1.05, 0, max(docspersec_av1) * 1.05])
        pylab.savefig(outprefix + "docspersec_v_totaldocs_av1.png", format="png")

    docspersec_av10, docs_av10, docinterval = get_av_docspersec(times, 10, docscale)
    if len(docs_av10) > 1:
        pylab.figure()
        pylab.plot(docs_av10, docspersec_av10)
        pylab.xlabel('Documents%s' % docscalestr)
        pylab.ylabel('Docs per second')
        pylab.title(pretitle + ': indexing rate versus documents processed\nAveraged every %d documents' % docinterval)
        pylab.axis([0, max(docs_av10) * 1.05, 0, max(docspersec_av10) * 1.05])
        pylab.savefig(outprefix + "docspersec_v_totaldocs_av10.png", format="png")

    
    docspersec_av100, docs_av100, docinterval = get_av_docspersec(times, 100, docscale)
    if len(docs_av100) > 1:
        pylab.figure()
        pylab.plot(docs_av100, docspersec_av100)
        pylab.xlabel('Documents%s' % docscalestr)
        pylab.ylabel('Docs per second')
        pylab.title(pretitle + ': indexing rate versus documents processed\nAveraged every %d documents' % docinterval)
        pylab.axis([0, max(docs_av100) * 1.05, 0, max(docspersec_av100) * 1.05])
        pylab.savefig(outprefix + "docspersec_v_totaldocs_av100.png", format="png")

def generate_comparison_figures(alltimes, outprefix, pretitle):
    docscale, docscalestr = calc_docscale(alltimes[0][1])

    # Generate a "total time" versus "total documents" plot
    have_plotted = False
    xaxis = 0
    yaxis = 0
    for legend, times in alltimes:
        if len(times) > 1:
            if not have_plotted:
                pylab.figure()
            have_plotted = True
            total_times = [row.time / 3600.0 for row in times]
            total_documents = [row.docs / docscale for row in times]
            pylab.plot(total_times, total_documents, label=legend)
            xaxis = max(xaxis, max(total_times) * 1.05)
            yaxis = max(yaxis, max(total_documents) * 1.05)
    pylab.legend(loc="lower right")
    pylab.xlabel('Time (hours)')
    pylab.ylabel('Documents%s' % docscalestr)
    pylab.title(pretitle + r': documents indexed after a given time')
    pylab.axis([0, xaxis, 0, yaxis])
    if have_plotted:
        pylab.savefig(outprefix + "totaltime_v_totaldocs.png", format="png")

    # Generate a "documents/second" plot
    have_plotted = False
    xaxis = 0
    yaxis = 0
    for legend, times in alltimes:
        docspersec_av1, docs_av1, docinterval = get_av_docspersec(times, 1, docscale)
        if len(docs_av1) > 1:
            if not have_plotted:
                pylab.figure()
            have_plotted = True
            pylab.plot(docs_av1, docspersec_av1, label=legend)
            xaxis = max(xaxis, max(docs_av1) * 1.05)
            yaxis = max(yaxis, max(docspersec_av1) * 1.05)
    pylab.legend(loc="lower left")
    pylab.xlabel('Documents%s' % docscalestr)
    pylab.ylabel('Docs per second')
    pylab.title(pretitle + ': indexing rate versus documents processed\nAveraged every %d documents' % docinterval)
    pylab.axis([0, xaxis, 0, yaxis])
    if have_plotted:
        pylab.savefig(outprefix + "docspersec_v_totaldocs_av1.png", format="png")

    have_plotted = False
    xaxis = 0
    yaxis = 0
    for legend, times in alltimes:
        docspersec_av10, docs_av10, docinterval = get_av_docspersec(times, 10, docscale)
        if len(docs_av10) > 1:
            if not have_plotted:
                pylab.figure()
            have_plotted = True
            pylab.plot(docs_av10, docspersec_av10, label=legend)
            xaxis = max(xaxis, max(docs_av10) * 1.05)
            yaxis = max(yaxis, max(docspersec_av10) * 1.05)
    pylab.legend(loc="lower left")
    pylab.xlabel('Documents%s' % docscalestr)
    pylab.ylabel('Docs per second')
    pylab.title(pretitle + ': indexing rate versus documents processed\nAveraged every %d documents' % docinterval)
    pylab.axis([0, xaxis, 0, yaxis])
    if have_plotted:
        pylab.savefig(outprefix + "docspersec_v_totaldocs_av10.png", format="png")

    have_plotted = False
    xaxis = 0
    yaxis = 0
    for legend, times in alltimes:
        docspersec_av100, docs_av100, docinterval = get_av_docspersec(times, 100, docscale)
        if len(docs_av100) > 1:
            if not have_plotted:
                pylab.figure()
            have_plotted = True
            pylab.plot(docs_av100, docspersec_av100, label=legend)
            xaxis = max(xaxis, max(docs_av100) * 1.05)
            yaxis = max(yaxis, max(docspersec_av100) * 1.05)
    pylab.legend(loc="lower left")
    pylab.xlabel('Documents%s' % docscalestr)
    pylab.ylabel('Docs per second')
    pylab.title(pretitle + ': indexing rate versus documents processed\nAveraged every %d documents' % docinterval)
    pylab.axis([0, xaxis, 0, yaxis])
    if have_plotted:
        pylab.savefig(outprefix + "docspersec_v_totaldocs_av100.png", format="png")




class logrow(object):
    __slots__ = ('docs', 'time', 'dbsize', 'tablesizes')
    def __init__(self, docs, time, dbsize, *tablesizes):
        self.docs = int(docs)
        self.time = float(time)
        self.dbsize = int(dbsize)
        self.tablesizes = [int(tablesize) for tablesize in tablesizes]

def parse_logfile(filename):
    fd = open(filename)
    times = []
    reader = csv.reader(fd)
    descline = reader.next()
    headings = reader.next()
    assert(','.join(headings) == 'Documents Added,Time(seconds),dbsize(bytes),inputsize(bytes)')
    for row in reader:
        newrow = logrow(*row)
        if len(times) > 0 and times[-1].docs == newrow.docs:
            times[-1] = newrow
        else:
            times.append(newrow)
    return descline, times
