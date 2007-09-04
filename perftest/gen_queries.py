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

import random
from sets import Set

# Remove this line, or change to a different value, to get different output.
random.seed(1)

class WordSource:
    def __init__(self, infile):
        fd = open(infile, "r")
        words = Set()
        for line in fd.readlines():
            line = line.replace('"', ' ')
            for word in line.split():
                words.add(word)
        self.words = []
        for word in words:
            self.words.append(word)

    def next(self):
        return random.choice(self.words)

class QueryGenerator:
    def __init__(self, source, distribution):
        self.source = source
        self.distribution = []
        for key, val in distribution.iteritems():
            self.distribution.extend((key,) * val)

    def __iter__(self):
        return self

    def next(self):
        qlen = random.choice(self.distribution)
        qterms = []
        while qlen > 0:
            qterms.append(self.source.next())
            qlen -= 1
        return ' '.join(qterms)

def gen_queries(infile, outfile, limit, distribution):
    querygen = QueryGenerator(WordSource(infile), distribution)
    outfd = open(outfile, 'wb')

    count = 0
    for query in querygen:
        query = query.replace('\n', ' ')
        outfd.write(query + '\n')
        count += 1
        if count >= limit:
            break

    outfd.close()

if __name__ == '__main__':
    infile = '../testdata/query_sourcewords.txt'
    outfile = '../testdata/queries.txt'
    limit = 100000
    gen_queries(infile, outfile, limit, {1: 10, 2:3, 5:1})
