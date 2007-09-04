#!/usr/bin/env python
#
# Copyright (C) 2006 Lemur Consulting Ltd
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

"""wiki2dump.py: Convert wikimedia xml dump files to scriptindex input files.

Usage:

./wiki2dump.py <xml dump> <output file> <redirects output file>

Outputs result to standard output.

"""

import sys
import os.path
from XMLUtils import ParsedXmlFile
from Errors import UserError
import re

class PageRevision:
    """A revision of a wikimedia page.

    This has an id number, timestamp, contributor_name, contributor_id, minor
    edit flag, comment, and text.

    """

    _re_redirect = re.compile('#REDIRECT\s*\[\[(?P<target>.*?)\]\]',
                              re.IGNORECASE)

    def __init__(self, xml):
        self.id = None
        self.timestamp = None
        self.contributor_name = ''
        self.contributor_id = None
        self.minor = False
        self.comment = ''
        self.text = ''
        self.redirect = None

        it = xml.getItems()
        for item in it:
            if item.type == item.DATA:
                if item.nodeNames[-2:] == [u'contributor', u'username']:
                    self.contributor_name = item.data
                elif item.nodeNames[-2:] == [u'contributor', u'id']:
                    self.contributor_id = item.data # FIXME - convert (checked) to int
                elif item.nodeNames[-1] == u'id':
                    self.id = item.data # FIXME - convert (checked) to int
                if item.nodeNames[-1] == u'timestamp':
                    self.timestamp = item.data # FIXME - convert (checked) to datetime
                if item.nodeNames[-1] == u'comment':
                    self.comment = item.data
                if item.nodeNames[-1] == u'text':
                    self.text = item.data
            elif item.type == item.START:
                if item.nodeNames[-1] == u'minor':
                    self.minor = True

        if len(self.text) > 0 and self.text[0] == '#':
            # Deal with special directives
            g = self._re_redirect.match(self.text)
            if g:
                self.redirect = g.group('target')

    def __repr__(self):
        return '<PageRevision id=%r timestamp=%r contributor_name=%r ' \
               'contributor_id=%r minor=%r comment=%r text=%r redirect=%r>' % (
                    self.id, self.timestamp, self.contributor_name,
                    self.contributor_id, self.minor, self.comment, self.text,
                    self.redirect,
               )

class Page:
    """A wikimedia page.

    This corresponds to a page tag in the input XML file.  It has a title, id
    number, and a list of PageRevision objects (which will often contain only a
    single entry).

    """
    def __init__(self, xml):
        self.title = None
        self.id = None
        self.revisions = []

        it = xml.getItems()
        for item in it:
            if item.type == item.START:
                if item.nodeNames[-1] == 'revision':
                    self.revisions.append(PageRevision(item.expand()))
                    it.skipContents()
            elif item.type == item.DATA:
                if item.nodeNames[-1] == 'title':
                    self.title = item.data
                elif item.nodeNames[-1] == 'id':
                    self.id = item.data # FIXME - convert (checked) to int

    def dump(self):
        redirect = False
        result = []
        if self.title is not None:
            result.append("title=%s" % self.title)
        if self.id is not None:
            result.append("id=%s" % self.id)

        maxrev = None
        for revision in self.revisions:
            if maxrev is None or maxrev.timestamp < revision.timestamp:
                maxrev = revision
        if maxrev is not None:
            if maxrev.redirect is not None:
                result.append("redirect=%s" % maxrev.redirect)
                redirect = True
            elif len(maxrev.text) > 0:
                text = maxrev.text.replace('\n', '\n=')
                result.append("text=%s" % text)

        return (u'\n'.join(result), redirect)

def parse(infile, outfile, redirfile):
    infile_size = os.path.getsize(infile)
    infh = open(infile, "rb")

    if os.path.exists(outfile):
        raise UserError("Error: output file \"%s\" already exists.", outfile)
    if os.path.exists(redirfile):
        raise UserError("Error: redirections output file \"%s\" already exists.", redirfile)

    outfh = open(outfile, "wb")
    redirfh = open(redirfile, "wb")

    xml = ParsedXmlFile(infh)
    state = 0
    it = xml.getItems()
    for item in it: 
        if state == 0:
            if item.type != item.START:
                raise UserError('Didn\'t get correct header at start of file')
            else:
                state = 1
                continue
        if state == 1:
            if item.type == item.START:
                if item.nodeNames[-1] == u'page':
                    page = Page(item.expand())
                    (dump, redirect) = page.dump()
                    if redirect:
                        redirfh.write(dump.encode('utf-8'))
                        redirfh.write('\n\n')
                    else:
                        outfh.write(dump.encode('utf-8'))
                        outfh.write('\n\n')
                    it.skipContents()
                    pos = infh.tell()
                    percent = 100.0 * pos / infile_size
                    if redirect:
                        print "Processed %f%%: %r (redirect to %r)" % (percent, page.title, redirect)
                    else:
                        print "Processed %f%%: %r" % (percent, page.title)

    infh.close()
    outfh.close()
    redirfh.close()

# Start
if len(sys.argv) != 4:
    print """
        Usage: ./wiki2dump.py <xml dump> <output file> <redirects output file>
    """.strip()
    sys.exit(0)

infile = sys.argv[1]
outfile = sys.argv[2]
redirfile = sys.argv[3]
try:
    parse(infile, outfile, redirfile)
except UserError, e:
    print e
