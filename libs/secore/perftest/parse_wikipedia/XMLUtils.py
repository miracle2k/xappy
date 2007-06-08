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

import xml.dom.minidom
import xml.dom.pulldom
import xml.parsers.expat
import xml.sax
import copy, re
import Errors, HTMLUtils


class ParsedXmlTextGetter:
    """
    Class used to implement the process of extracting the textual contents of
    some XML.  Implemented as a class rather than a method so that the setup
    process can be shared between calls.

    """

    __spaces_re = re.compile(r'\s+')

    def __init__(self, nospacetags=None, spacetags=None,
                       ignoretags=None, requiretags=None,
                       condenseSpaces=False,
                       caseInsensitiveTags=False):
        """Set up a text getter.

	`nospacetags` is a sequence of tags where the tags should be discarded,
        but the contents preserved.

	`spacetags` is a sequence of tags where the tags should be replaced by
        whitespace, but the contents preserved.

        `ignoretags` is a sequence of tags which should be ignored completely.

        `requiretags` is a sequence of tags which, if supplied, will cause any
        content not contained in one of the tags to be ignored completely.

	`condenseSpaces` is a flag; if True, all sequences of whitespace in the
        output will be replaced by a single space, and whitespace will be
        stripped from the start and end of the result.

	`caseInsensitiveTags` is a flag; if True, all tag names will be matched
        in a case insensitive manner.

        Any tags which are found which are not in one of the above lists will
        be treated as if it were in spacetags.  (Future implementations may
        raise an error here, or be configurable, however.)

        """
        if nospacetags is None:
            nospacetags = set()
        else:
            nospacetags = set(nospacetags)

        if spacetags is None:
            spacetags = set()
        else:
            spacetags = set(spacetags)

        if ignoretags is None:
            ignoretags = set()
        else:
            ignoretags = set(ignoretags)

        if requiretags is not None:
            requiretags = set(requiretags)

        if nospacetags.intersection(spacetags):
            raise ValueError, "Tags may not be shared between nospacetags and spacetags"
        if nospacetags.intersection(ignoretags):
            raise ValueError, "Tags may not be shared between nospacetags and ignoretags"
        if spacetags.intersection(ignoretags):
            raise ValueError, "Tags may not be shared between spacetags and ignoretags"

        if requiretags is not None and ignoretags.intersection(requiretags):
            raise ValueError, "Tags may not be shared between ignoretags and requiretags"

        if caseInsensitiveTags:
            if requiretags is not None:
                requiretags = set((item.lower() for item in requiretags))
            nospacetags = set((item.lower() for item in nospacetags))
            spacetags = set((item.lower() for item in spacetags))
            ignoretags = set((item.lower() for item in ignoretags))

        self._nospacetags = nospacetags
        self._spacetags = spacetags
        self._ignoretags = ignoretags
        self._requiretags = requiretags

        self._condenseSpaces = condenseSpaces
        self._caseInsensitiveTags = caseInsensitiveTags

    def toText(self, parsedXml):
        """
        Convert a parsedXML object to text, according to the rules set up in
        this getter.
        """
        text = u''
        ignoring = 0 # Count of number of ignore tags we're within
        required = 0 # Count of number of require tags we're within
        if self._requiretags is None:
            required = 1 # Pretend we're always within a require tag
        for item in parsedXml.getItems():
            if item.type == ParsedXmlItem.START:
                name = item.nodeNames[-1]
                if self._caseInsensitiveTags:
                    name = name.lower()
                if self._requiretags is not None and name in self._requiretags:
                    required += 1
                if name in self._ignoretags:
                    ignoring += 1
                elif ignoring == 0 and required != 0:
                    if name in self._nospacetags:
                        pass
                    elif name in self._spacetags:
                        text += u' '
                    else:
                        text += u' '
            elif item.type == ParsedXmlItem.END:
                name = item.nodeNames[-1]
                if self._caseInsensitiveTags:
                    name = name.lower()
                if name in self._ignoretags:
                    ignoring -= 1
                elif ignoring == 0 and required != 0:
                    if name in self._nospacetags:
                        pass
                    elif name in self._spacetags:
                        text += u' '
                    else:
                        text += u' '
                if self._requiretags is not None and name in self._requiretags:
                    required -= 1
            elif item.type == ParsedXmlItem.DATA:
                if ignoring == 0 and required != 0:
                    text += item.data

        if self._condenseSpaces:
            text = self.__spaces_re.sub(' ', text).strip()
        return text


class ParsedXmlItem:
    """
    Class representing an item of XML.  This is either the start of an element,
    the end of an element, or a piece of textual data.
    """
    START = 0
    END = 1
    DATA = 2
    typenames = {
        START: "START",
        END: "END",
        DATA: "DATA",
    }

    def __init__(self, type, nodeNames, atts=None, data=None, node=None, unlinker=None):
        self.type = type
        self.nodeNames = nodeNames
        self.atts = atts
        self.data = data
        self._node = node
        self._unlinker = unlinker

    def expand(self):
        assert self.type == self.START, 'Cannot expand() when item is not a START item'
        expanded = ParsedXml()
        expanded._node = self._node
        expanded._unlinker = self._unlinker
        return expanded

    def getAttr(self, name, default=None):
        """Return the attribute of the given name.

        If not found, returns default.
        """
        try:
            return self.atts[name].nodeValue
        except KeyError:
            return default

    def __str__(self):
        extra=u''
        if self.atts is not None:
            for i in xrange(len(self.atts)):
                att = self.atts.item(i)
                extra += u" %s='%s'" % (att.name, att.nodeValue)
        if self.data is not None:
            extra += u' data=%s' % repr(self.data)
        if len(extra) != 0:
            extra = u',' + extra
        return u'(%s, %s%s)' % (
            self.typenames[self.type],
            repr(self.nodeNames),
            extra
        )

    def __repr__(self):
        extra=''
        if self.atts is not None:
            extra += ', atts=%s' % repr(self.atts)
        if self.data is not None:
            extra += ', data=%s' % repr(self.data)
        return 'ParsedXmlItem(ParsedXmlItem.%s, %s%s)' % (
            self.typenames[self.type],
            repr(self.nodeNames),
            extra
        )

    def toxml (self):
        """
        Return this tag/data formatted as XML.
        """
        if self.type == self.START:
            ret = ['<%s' % self.nodeNames[-1]]
            for i in xrange(len(self.atts)):
                att = self.atts.item (i)
                ret.append (u' %s="%s"' % (att.name, HTMLUtils.encodeText (att.nodeValue)))
            ret.append ('>')
            return ''.join (ret)

        elif self.type == self.END:
            return '</%s>' % self.nodeNames[-1]        

        else:
            return HTMLUtils.encodeText (self.data)


def _convertParseExceptions(callable, xmlString=None):
    """
    Convert exceptions raised by XML parsers to UserErrors describing the
    error.
    """
    try:
        return callable()
    except xml.parsers.expat.ExpatError, e:
        context = ''
        if xmlString:
            try:
                lines = xmlString.split('\n')
                pos = max(e.offset - 10, 0)
                line = lines[e.lineno - 1]
                context = " (near <q>%s</q>)" % HTMLUtils.encodeText(line[pos:pos + 20])
                context = context.replace('%', '%%')
            except:
                pass
        raise Errors.UserError("at line %%s, column %%s%s: %%s" % context,
                               e.lineno, e.offset,
                               xml.parsers.expat.ErrorString(e.code))
    except xml.sax.SAXParseException, e:
        context = ''
        if xmlString:
            try:
                lines = xmlString.split('\n')
                pos = max(e.getColumnNumber() - 10, 0)
                line = lines[e.getLineNumber() - 1]
                context = " (near <q>%s</q>)" % HTMLUtils.encodeText(line[pos:pos + 20])
                context = context.replace('%', '%%')
            except:
                pass
        raise Errors.UserError("at line %%s, column %%s%s: %%s" % context,
                               e.getLineNumber(), e.getColumnNumber(),
                               e.getMessage())
    except ValueError, e:
        raise Errors.UserError("Parse error: %s", str(e))


class ParsedXml:
    """
    Class representing a parsed piece of XML, and providing several convenience
    methods for getting at the parsed XML.
    The parsed piece of XML is a single well-formed tag (ie, has exactly one
    root node).
    """

    def __init__(self, xmlString=None):
        """Initialise the ParsedXml object.
        
        If xmlString is supplied (and not None), it should contain either a
        unicode object or utf-8 encoded string object.  If fh is supplied, it
        should be a filehandle which is open for reading, and is pointing to
        the start of an XML file.

        Only one of xmlString and fh may be supplied.
        """
        # A DOM node representing the parsed XML.
        # Used if reading from a string.
        self._node = None

        # The parsedXml object which should call unlink() on _node, or None if
        # this is the object which should do that.
        # This is used to ensure that the object which calls unlink isn't
        # garbage collected (and hence calls unlink) before all users have
        # finished, and hence released their references to it.
        self._unlinker = None

        # Parse the string:
        if xmlString is not None:
            self._parseFragment(xmlString)

    def __del__(self):
        """
        Free the internals.  This avoids cyclic garbage collection being
        needed.
        """
        if self._node is not None:
            if self._unlinker is None:
                self._node.unlink()
            self._node = None
        self._unlinker = None

    def getAsString(self):
        """Get the parsed piece of XML as a utf-8 string.
        """
        if self._node is not None:
            return self._node.toxml('utf-8')

    def getContentsAsString(self):
        """Get the contents of the parsed piece of XML.
        
        This returns the contents as a utf-8 string.
        This includes the contents of the root tag, but not the root tag
        itself.
        """
        if not self._node.hasChildNodes:
            return ''

        contents = []
        currnode = self._node.firstChild
        while currnode is not None:
            contents.append(currnode.toxml('utf-8'))
            currnode = currnode.nextSibling

        return ''.join(contents)

    def getText(self, *args, **kwargs):
        """
        Get the textual contents of this piece of XML, as a unicode string.

        See the documentation for ParsedXmlTextGetter.__init__() for details of
        the parameters.
        """
        getter = ParsedXmlTextGetter(*args, **kwargs)
        return getter.toText(self)

    def _parseFragment(self, xmlString):
        """
        Parse a fragment of XML, storing the resulting DOM node in this
        ParsedXml object.
        """
        if isinstance(xmlString, unicode):
            # Convert to utf-8
            xmlString = xmlString.encode('utf-8')
        result = []
        def callable():
            result.append(xml.dom.minidom.parseString(xmlString))
        _convertParseExceptions(callable, xmlString)

        # Don't call unlink on the old value of _node: we can't guarantee that
        # noone is using it, so we just have to wait for cyclic garbage
        # collection to pick it up.
        self._node = result[0]
        self._unlinker = None

    def getItems(self):
        """Return an iterator which returns all the items in the parsed XML.
        """
        root = self._node
        if root is None:
            return iter(())
        if root.nodeType == root.DOCUMENT_NODE:
            root = root.documentElement

        class Iter:
            def __init__(self, root, unlinker):
                self._unlinker = unlinker
                self._nodelist = [[root, None]]
                self._nodeNames = []

            def __iter__(self):
                'Method needed to satisfy iterator protocol.'
                return self

            def next(self):
                'Move to next element, or throw StopIteration.'
                if len(self._nodelist) == 0:
                    raise StopIteration

                while len(self._nodelist) != 0:
                    (node, subpos) = self._nodelist[-1]
                    if node.nodeType == node.ELEMENT_NODE:
                        if subpos is None:
                            # Haven't returned start of node yet.
                            self._nodeNames.append(node.nodeName)
                            self._nodelist[-1][1] = 0
                            return ParsedXmlItem(ParsedXmlItem.START, self._nodeNames, atts=node.attributes, node=node, unlinker=self._unlinker)
                        else:
                            # Get next subnode which we care about.
                            while True:
                                if subpos >= len(node.childNodes):
                                    break
                                newnode = node.childNodes[subpos]
                                subpos += 1
                                if newnode.nodeType == newnode.ELEMENT_NODE:
                                    # Have an element node
                                    self._nodelist[-1][1] = subpos
                                    self._nodelist.append([newnode, 0])
                                    self._nodeNames.append(newnode.nodeName)
                                    return ParsedXmlItem(ParsedXmlItem.START, self._nodeNames, atts=newnode.attributes, node=newnode, unlinker=self._unlinker)
                                elif newnode.nodeType == newnode.TEXT_NODE or newnode.nodeType == newnode.CDATA_SECTION_NODE:
                                    # Have a text node - join it with any subsequent text nodes.
                                    result = ParsedXmlItem(ParsedXmlItem.DATA, self._nodeNames, data=newnode.data)
                                    resultdata = [result.data]
                                    while subpos < len(node.childNodes):
                                        nextnode = node.childNodes[subpos]
                                        if nextnode.nodeType == nextnode.ELEMENT_NODE:
                                            # An element - need to leave this
                                            # to be dealt with later.
                                            break
                                        elif nextnode.nodeType == nextnode.TEXT_NODE or nextnode.nodeType == nextnode.CDATA_SECTION_NODE:
                                            # More text - add it to this node.
                                            resultdata.append(nextnode.data)
                                        else:
                                            pass
                                        subpos += 1
                                    result.data = u''.join(resultdata)
                                    self._nodelist[-1][1] = subpos
                                    return result
                                else:
                                    # Have a node which is neither text nor an element.
                                    # Skip it.
                                    pass
                            # No more subnodes - return end of parent node.
                            result = ParsedXmlItem(ParsedXmlItem.END, copy.copy(self._nodeNames), atts=node.attributes)
                            self._nodeNames.pop()
                            self._nodelist.pop()
                            return result
                    elif node.nodeType == node.TEXT_NODE or node.nodeType == node.CDATA_SECTION_NODE:
                        # Have a text node
                        self._nodelist.pop()
                        return ParsedXmlItem(ParsedXmlItem.DATA, self._nodeNames, data=node.data)
                    else:
                        # Have a node which is neither text nor an element.
                        # Skip it.
                        pass

            def expand(self):
                """
                Expand the current item (and its subitems) by returning a
                ParsedXml object representing the current item.
                Only valid when the current item (ie, last returned by next())
                is a START item.  See also the skipContents() method, which is
                often useful in conjunction with this method.
                """
                assert self._nodelist[-1][1] != 0, 'Cannot expand() when current item is not a START item'
                expanded = ParsedXml()
                expanded._node = self._nodelist[-1][0]
                expanded._unlinker = self._unlinker
                return expanded

            def skipContents(self):
                """
                If the current item is a START item, advances the iterator such
                that the next item is the corresponding END item.  Otherwise,
                has no effect.
                """
                if self._nodelist[-1][1] != 0:
                    return
                self._nodelist[-1][1] = len(self._nodelist[-1][0].childNodes)

        if self._unlinker is None:
            return Iter(root, self)
        else:
            return Iter(root, self._unlinker)

class ParsedXmlFileItem(ParsedXmlItem):
    """Class representing an item of XML read from a file.

    This is either the start of an element, the end of an element, or a piece
    of textual data.
    
    """
    def __init__(self, type, nodeNames, atts=None, data=None, node=None, unlinker=None, expander=None):
        ParsedXmlItem.__init__(self, type, nodeNames, atts=atts, data=data, node=node, unlinker=unlinker)
        self._expander = expander

    def expand(self):
        """Expand the item, by returning a ParsedXml object representing the
        current item.

        Note that this is only valid if the iterator that this
        ParsedXmlFileItem came from hasn't moved since making this
        ParsedXmlFileItem.
        """
        return self._expander.expand(node=self._node)

    def __repr__(self):
        extra=''
        if self.atts is not None:
            extra += ', atts=%s' % repr(self.atts)
        if self.data is not None:
            extra += ', data=%s' % repr(self.data)
        return 'ParsedXmlFileItem(ParsedXmlItem.%s, %s%s)' % (
            self.typenames[self.type],
            repr(self.nodeNames),
            extra
        )

class ParsedXmlFile(ParsedXml):
    """Class representing a parsed XML file.

    The file is actually read and parsed lazily, but this implementation is
    hidden, and the interface provided is precisely that of ParsedXml.
    """

    def __init__(self, fh):
        ParsedXml.__init__(self, None)

        # File handle that file is being read from.
        # Used if reading from a file.
        self._fh = None

        # Position in file handle that XML starts at.
        # Used if reading from a file.
        self._startpos = None

        # If we've been supplied a filename instead of a file handle, try
        # opening it.
        if isinstance(fh, basestring):
            try:
                handle = open(fh)
            except IOError, e:
                raise Errors.UserError("Can't open file <q>%s</q>: %s", fh, str(e))
            fh = handle

        # Store the file handle and current position, for use when we start
        # reading the file.
        if fh is not None:
            self._fh = fh
            self._startpos = fh.tell()

    def _getParseEvents(self):
        """Parse from a file handle.

        This uses the pulldom interfsce to avoid having to read in the whole
        file at once.  It returns a DOMEventStream object, which provides a
        stream of parse events.
        """
        if self._fh.tell() != self._startpos:
            self._fh.seek(self._startpos)
        result = []
        def callable():
            result.append(xml.dom.pulldom.parse(self._fh))
        _convertParseExceptions(callable)
        return result[0]

    def getAsString(self):
        """Get the parsed piece of XML as a utf-8 string.
        """
        events = self._getParseEvents()
        result = []
        def callable():
            for (event, node) in events:
                if event == "START_ELEMENT":
                    events.expandNode(node)
                    result.append(node.toxml())
        _convertParseExceptions(callable)
        return ''.join(result)

    def getContentsAsString(self):
        """Get the contents of the parsed piece of XML.
        
        This returns the contents as a utf-8 string.
        This includes the contents of the root tag, but not the root tag
        itself.
        """
        events = self._getParseEvents()
        result = []
        def callable():
            for (event, node) in events:
                if event == "START_ELEMENT":
                    break
            for (event, node) in events:
                if event == "START_ELEMENT":
                    events.expandNode(node)
                    result.append(node.toxml())
                if event == "END_ELEMENT":
                    break
        _convertParseExceptions(callable)
        return ''.join(result)

    def getItems(self):
        """
        Return an iterator which returns all the items in the parsed XML.
        """
        class Iter:
            def __init__(self, events, unlinker):
                self._events = events
                self._unlinker = unlinker
                self._nodeNames = []
                self._lastEvent = None
                self._lastNode = None
                self._nextItem = None
                self._expandedIter = None
                self._expandedIterStarted = False
                self._expandedXml = None
                def callable():
                    while True:
                        self._nextItem = self._events.next()
                        if self._nextItem[0] == 'START_ELEMENT':
                            break
                try:
                    _convertParseExceptions(callable)
                except StopIteration:
                    self._events = None

            def __iter__(self):
                'Method needed to satisfy iterator protocol.'
                return self

            def next(self):
                'Move to next element, or throw StopIteration.'

                # If we've got an expanded iterator, pass through items from
                # the iterator over the expanded node, but add the preceding
                # nodenames to it.
                if self._expandedIter is not None:
                    try:
                        item = self._expandedIter.next()
                        self._expandedIterStarted = True
                        newNodeNames = []
                        newNodeNames.extend(self._nodeNames[:-1])
                        newNodeNames.extend(item.nodeNames)
                        item.nodeNames = newNodeNames
                        return item
                    except StopIteration:
                        self._expandedIter = None
                        self._expandedXml = None
                        self._expandedIterStarted = False
                        self._nodeNames.pop()

                # Read events from the file, merging any character events, and
                # return ParsedXmlFileItems for each one.
                while True:
                    # If we haven't already read ahead by one, read the next
                    # event.
                    if self._nextItem is None:
                        if self._events is None:
                            raise StopIteration
                        def callable():
                            self._nextItem = self._events.next()
                        try:
                            _convertParseExceptions(callable)
                        except StopIteration:
                            self._events = None
                            raise
                    (self._lastEvent, self._lastNode) = self._nextItem
                    self._nextItem = None
                    if self._lastEvent is None:
                        raise StopIteration

                    # Now return a node based on self._lastEvent and self._lastNode
                    if self._lastEvent == 'START_ELEMENT':
                        # Return start of node
                        self._nodeNames.append(self._lastNode.nodeName)
                        return ParsedXmlFileItem(ParsedXmlFileItem.START, self._nodeNames, atts=self._lastNode.attributes, node=self._lastNode, unlinker=self._unlinker, expander=self)
                    elif self._lastEvent == 'CHARACTERS':
                        # Text data in the node.
                        # Move forward merging CHARACTERS nodes together, until
                        # we have a different type of node.
                        characters = [self._lastNode.data]
                        def callable():
                            while self._nextItem is None:
                                self._nextItem = self._events.next()
                                if self._nextItem[0] == 'CHARACTERS':
                                    characters.append(self._nextItem[1].data)
                                    self._nextItem = None
                        try:
                            _convertParseExceptions(callable)
                        except StopIteration:
                            self._nextItem = None
                            self._events = None
                        return ParsedXmlFileItem(ParsedXmlFileItem.DATA, self._nodeNames, data=''.join(characters))
                    elif self._lastEvent == 'END_ELEMENT':
                        # End of a node.
                        result = ParsedXmlFileItem(ParsedXmlFileItem.END, copy.copy(self._nodeNames), atts=self._lastNode.attributes)
                        self._nodeNames.pop()
                        return result
                    else:
                        # Something else: ignore it, go round the loop again.
                        pass

            def expand(self, node=None):
                """
                Expand the current item (and its subitems) by returning a
                ParsedXml object representing the current item.
                Only valid when the current item (ie, last returned by next())
                is a START item.  See also the skipContents() method, which is
                often useful in conjunction with this method.

                If node is supplied, will raise an error if the supplied node
                is not the last node supplied.
                """
                if self._expandedIter is not None:
                    if self._expandedIterStarted:
                        return self._expandedIter.expand()
                    else:
                        return self._expandedXml

                assert node is None or node is self._lastNode
                assert self._lastEvent == 'START_ELEMENT', 'Cannot expand() when current item is not a START item'

                def callable():
                    self._events.expandNode(self._lastNode)
                _convertParseExceptions(callable)
                self._expandedXml = ParsedXml()
                self._expandedXml._node = self._lastNode
                self._expandedXml._unlinker = self._unlinker
                self._expandedIter = self._expandedXml.getItems()
                self._expandedIterStarted = False
                try:
                    self._expandedIter.next()
                except StopIteration:
                    self._expandedIter = None
                    self._expandedXml = None
                return self._expandedXml

            def skipContents(self):
                """
                If the current item is a START item, advances the iterator such
                that the next item is the corresponding END item.  Otherwise,
                has no effect.
                """
                if self._lastEvent != 'START_ELEMENT':
                    return
                if self._expandedXml:
                    self._expandedIter.skipContents()
                    return

                def callable():
                    nodeNames = [self._lastNode.nodeName]
                    while len(nodeNames) != 0:
                        if self._nextItem is not None:
                            (self._lastEvent, self._lastNode) = self._nextItem
                        self._nextItem = self._events.next()
                        print self._nextItem, nodeNames
                        (event, node) = self._nextItem
                        if event == 'START_ELEMENT':
                            nodeNames.append(node.nodeName)
                        elif event == 'END_ELEMENT':
                            assert nodeNames[-1] == node.nodeName
                            nodeNames.pop()
                try:
                    _convertParseExceptions(callable)
                except StopIteration:
                    self._nextItem = None

        return Iter(self._getParseEvents(), self)


__test__ = {
    'Getting items': r"""
    Get some items, and check that all the subitems expand correctly.
    >>> parsed=ParsedXml('<b a="" b="" c=""><!-- Comment\n --><a>A</a></b>')
    >>> for item in parsed.getItems():
    ...     print "Item:", item
    ...     if item.type == item.START:
    ...         subparsed = item.expand()
    ...         for item2 in subparsed.getItems():
    ...             print "Item2:", item2
    Item: (START, [u'b'], a='' c='' b='')
    Item2: (START, [u'b'], a='' c='' b='')
    Item2: (START, [u'b', u'a'])
    Item2: (DATA, [u'b', u'a'], data=u'A')
    Item2: (END, [u'b', u'a'])
    Item2: (END, [u'b'], a='' c='' b='')
    Item: (START, [u'b', u'a'])
    Item2: (START, [u'a'])
    Item2: (DATA, [u'a'], data=u'A')
    Item2: (END, [u'a'])
    Item: (DATA, [u'b', u'a'], data=u'A')
    Item: (END, [u'b', u'a'])
    Item: (END, [u'b'], a='' c='' b='')

    Get some items, and check that all the subitems expand correctly.
    >>> parsed=ParsedXml('<b a="" b="" c=""><!-- Comment\n --><a>A</a></b>')
    >>> it = parsed.getItems()
    >>> for item in it:
    ...     print "Item:", item
    ...     if item.type == item.START and item.nodeNames[-1] == 'a':
    ...         it.skipContents()
    ...         subparsed = item.expand()
    ...         it.skipContents()
    ...         for item2 in subparsed.getItems():
    ...             print "Item2:", item2
    Item: (START, [u'b'], a='' c='' b='')
    Item: (START, [u'b', u'a'])
    Item2: (START, [u'a'])
    Item2: (DATA, [u'a'], data=u'A')
    Item2: (END, [u'a'])
    Item: (END, [u'b', u'a'])
    Item: (END, [u'b'], a='' c='' b='')

    Check that iterator now raises StopIteration
    >>> it.next()
    Traceback (most recent call last):
    ...
    StopIteration


    First, just parse some simple XML and check that the element list is right.
    >>> parsed=ParsedXml('<field name="title">Normal <i>italic <b>italicbold</b></i> normalagain mi<i>x</i>ed.</field>')
    >>> for item in parsed.getItems(): print item
    (START, [u'field'], name='title')
    (DATA, [u'field'], data=u'Normal ')
    (START, [u'field', u'i'])
    (DATA, [u'field', u'i'], data=u'italic ')
    (START, [u'field', u'i', u'b'])
    (DATA, [u'field', u'i', u'b'], data=u'italicbold')
    (END, [u'field', u'i', u'b'])
    (END, [u'field', u'i'])
    (DATA, [u'field'], data=u' normalagain mi')
    (START, [u'field', u'i'])
    (DATA, [u'field', u'i'], data=u'x')
    (END, [u'field', u'i'])
    (DATA, [u'field'], data=u'ed.')
    (END, [u'field'], name='title')

    Next, parse some XML with an SGML comment.  Should get exactly the same output.
    >>> parsed=ParsedXml('<field name="title">Norma<!-- Comment\n -->l <i>italic <b>italicbold</b></i> normalagain mi<i>x</i>ed.</field>')
    >>> for item in parsed.getItems(): print item
    (START, [u'field'], name='title')
    (DATA, [u'field'], data=u'Normal ')
    (START, [u'field', u'i'])
    (DATA, [u'field', u'i'], data=u'italic ')
    (START, [u'field', u'i', u'b'])
    (DATA, [u'field', u'i', u'b'], data=u'italicbold')
    (END, [u'field', u'i', u'b'])
    (END, [u'field', u'i'])
    (DATA, [u'field'], data=u' normalagain mi')
    (START, [u'field', u'i'])
    (DATA, [u'field', u'i'], data=u'x')
    (END, [u'field', u'i'])
    (DATA, [u'field'], data=u'ed.')
    (END, [u'field'], name='title')

    Now, convert some XML to text.
    >>> parsed=ParsedXml('<field name="title">Norma<!-- Comment\n -->l <i>italic <b>italicbold</b></i> normalagain mi<i>x</i>ed.</field>')
    >>> print parsed.getText(nospacetags=['field', 'i', 'b'])
    Normal italic italicbold normalagain mixed.
    >>> for item in parsed.getItems():
    ...     if item.type == item.START and item.nodeNames[-1] == 'i':
    ...         print item.expand().getText(nospacetags=['i', 'b'])
    italic italicbold
    x

    Check if parameters supplied to the getText() method work.
    >>> for item in parsed.getItems():
    ...     if item.type == item.START and item.nodeNames[-1] == 'i':
    ...         print item.expand().getText(spacetags=['b'], nospacetags=['i'])
    italic  italicbold 
    x
    >>> parsed=ParsedXml('<a><b><c>C1</c>B1<c>C2</c></b>A1<b>B2</b><c>C3</c>A2</a>')
    >>> for item in parsed.getItems():
    ...     if item.type == item.START:
    ...         expanded = item.expand()
    ...         print expanded.getAsString()
    ...         print expanded.getContentsAsString()
    ...         print item.expand().getText(nospacetags=['b', 'a'])
    ...         print item.expand().getText(nospacetags=['b', 'a'], spacetags=['c'])
    ...         print item.expand().getText(spacetags=['b'])
    ...         print item.expand().getText(nospacetags=['a'], ignoretags=['c'])
    ...         print item.expand().getText(ignoretags=['b'])
    ...         print '.' #doctest: +REPORT_NDIFF
    <a><b><c>C1</c>B1<c>C2</c></b>A1<b>B2</b><c>C3</c>A2</a>
    <b><c>C1</c>B1<c>C2</c></b>A1<b>B2</b><c>C3</c>A2
     C1 B1 C2 A1B2 C3 A2
     C1 B1 C2 A1B2 C3 A2
       C1 B1 C2  A1 B2  C3 A2 
     B1 A1 B2 A2
     A1 C3 A2 
    .
    <b><c>C1</c>B1<c>C2</c></b>
    <c>C1</c>B1<c>C2</c>
     C1 B1 C2 
     C1 B1 C2 
      C1 B1 C2  
     B1 
    <BLANKLINE>
    .
    <c>C1</c>
    C1
     C1 
     C1 
     C1 
    <BLANKLINE>
     C1 
    .
    <c>C2</c>
    C2
     C2 
     C2 
     C2 
    <BLANKLINE>
     C2 
    .
    <b>B2</b>
    B2
    B2
    B2
     B2 
     B2 
    <BLANKLINE>
    .
    <c>C3</c>
    C3
     C3 
     C3 
     C3 
    <BLANKLINE>
     C3 
    .
    """,
    'Getting items from file': r"""
    Get some items, and check that all the subitems expand correctly.
    >>> import StringIO
    >>> iostring = StringIO.StringIO('<b a="" b="" c=""><!-- Comment\n --><a>A</a></b>')
    >>> parsed=ParsedXmlFile(iostring)
    >>> for item in parsed.getItems():
    ...     print "Item:", item
    ...     if item.type == item.START:
    ...         subparsed = item.expand()
    ...         for item2 in subparsed.getItems():
    ...             print "Item2:", item2 #doctest: +REPORT_NDIFF
    Item: (START, [u'b'], a='' c='' b='')
    Item2: (START, [u'b'], a='' c='' b='')
    Item2: (START, [u'b', u'a'])
    Item2: (DATA, [u'b', u'a'], data=u'A')
    Item2: (END, [u'b', u'a'])
    Item2: (END, [u'b'], a='' c='' b='')
    Item: (START, [u'b', u'a'])
    Item2: (START, [u'a'])
    Item2: (DATA, [u'a'], data=u'A')
    Item2: (END, [u'a'])
    Item: (DATA, [u'b', u'a'], data=u'A')
    Item: (END, [u'b', u'a'])
    Item: (END, [u'b'], a='' c='' b='')
    """,

    'Get items from file and check expand': r"""
    Get some items, and check that all the subitems expand correctly.
    >>> import StringIO
    >>> parsed=ParsedXmlFile(StringIO.StringIO('<b a="" b="" c=""><!-- Comment\n --><a>A</a></b>'))
    >>> it = parsed.getItems()
    >>> for item in it:
    ...     print "Item:", item
    ...     if item.type == item.START and item.nodeNames[-1] == 'a':
    ...         subparsed = item.expand()
    ...         it.skipContents()
    ...         it.skipContents()
    ...         for item2 in subparsed.getItems():
    ...             print "Item2:", item2 #doctest: +REPORT_NDIFF
    Item: (START, [u'b'], a='' c='' b='')
    Item: (START, [u'b', u'a'])
    Item2: (START, [u'a'])
    Item2: (DATA, [u'a'], data=u'A')
    Item2: (END, [u'a'])
    Item: (END, [u'b', u'a'])
    Item: (END, [u'b'], a='' c='' b='')

    Check that iterator now raises StopIteration
    >>> it.next()
    Traceback (most recent call last):
    ...
    StopIteration


    Check that if skipContents() is not used, the results are the same whether
    expand is called or not.
    >>> it = parsed.getItems()
    >>> for item in it:
    ...     print "Item:", item
    ...     if item.type == item.START and item.nodeNames[-1] == 'a':
    ...         subparsed = item.expand()
    ...         for item2 in subparsed.getItems():
    ...             print "Item2:", item2 #doctest: +REPORT_NDIFF
    Item: (START, [u'b'], a='' c='' b='')
    Item: (START, [u'b', u'a'])
    Item2: (START, [u'a'])
    Item2: (DATA, [u'a'], data=u'A')
    Item2: (END, [u'a'])
    Item: (DATA, [u'b', u'a'], data=u'A')
    Item: (END, [u'b', u'a'])
    Item: (END, [u'b'], a='' c='' b='')

    Check that iterator now raises StopIteration
    >>> it.next()
    Traceback (most recent call last):
    ...
    StopIteration

    >>> it = parsed.getItems()
    >>> for item in it:
    ...     print "Item:", item
    ...     if item.type == item.START and item.nodeNames[-1] == 'a':
    ...         subparsed = item.expand() #doctest: +REPORT_NDIFF
    Item: (START, [u'b'], a='' c='' b='')
    Item: (START, [u'b', u'a'])
    Item: (DATA, [u'b', u'a'], data=u'A')
    Item: (END, [u'b', u'a'])
    Item: (END, [u'b'], a='' c='' b='')

    Check that iterator now raises StopIteration
    >>> it.next()
    Traceback (most recent call last):
    ...
    StopIteration

    >>> it = parsed.getItems()
    >>> for item in it:
    ...     print "Item:", item #doctest: +REPORT_NDIFF
    Item: (START, [u'b'], a='' c='' b='')
    Item: (START, [u'b', u'a'])
    Item: (DATA, [u'b', u'a'], data=u'A')
    Item: (END, [u'b', u'a'])
    Item: (END, [u'b'], a='' c='' b='')

    Check that iterator now raises StopIteration
    >>> it.next()
    Traceback (most recent call last):
    ...
    StopIteration

    """,

    'Parse XML from file': r"""
    First, just parse some simple XML and check that the element list is right.
    >>> import StringIO
    >>> parsed=ParsedXmlFile(StringIO.StringIO('<field name="title">Normal <i>italic <b>italicbold</b></i> normalagain mi<i>x</i>ed.</field>'))
    >>> for item in parsed.getItems(): print item #doctest: +REPORT_NDIFF
    (START, [u'field'], name='title')
    (DATA, [u'field'], data=u'Normal ')
    (START, [u'field', u'i'])
    (DATA, [u'field', u'i'], data=u'italic ')
    (START, [u'field', u'i', u'b'])
    (DATA, [u'field', u'i', u'b'], data=u'italicbold')
    (END, [u'field', u'i', u'b'])
    (END, [u'field', u'i'])
    (DATA, [u'field'], data=u' normalagain mi')
    (START, [u'field', u'i'])
    (DATA, [u'field', u'i'], data=u'x')
    (END, [u'field', u'i'])
    (DATA, [u'field'], data=u'ed.')
    (END, [u'field'], name='title')
    """,

    'Parse XML with SGML comment from file': r"""
    Next, parse some XML with an SGML comment.  Should get exactly the same output.
    >>> import StringIO
    >>> parsed=ParsedXmlFile(StringIO.StringIO('<field name="title">Norma<!-- Comment\n -->l <i>italic <b>italicbold</b></i> normalagain mi<i>x</i>ed.</field>'))
    >>> for item in parsed.getItems(): print item #doctest: +REPORT_NDIFF
    (START, [u'field'], name='title')
    (DATA, [u'field'], data=u'Normal ')
    (START, [u'field', u'i'])
    (DATA, [u'field', u'i'], data=u'italic ')
    (START, [u'field', u'i', u'b'])
    (DATA, [u'field', u'i', u'b'], data=u'italicbold')
    (END, [u'field', u'i', u'b'])
    (END, [u'field', u'i'])
    (DATA, [u'field'], data=u' normalagain mi')
    (START, [u'field', u'i'])
    (DATA, [u'field', u'i'], data=u'x')
    (END, [u'field', u'i'])
    (DATA, [u'field'], data=u'ed.')
    (END, [u'field'], name='title')
    """,

    'Parse XML from file and convert to text': r"""
    Now, convert some XML to text.
    >>> import StringIO
    >>> parsed=ParsedXmlFile(StringIO.StringIO('<field name="title">Norma<!-- Comment\n -->l <i>italic <b>italicbold</b></i> normalagain mi<i>x</i>ed.</field>'))
    >>> print parsed.getText(nospacetags=['field', 'i', 'b'])
    Normal italic italicbold normalagain mixed.
    >>> for item in parsed.getItems():
    ...     if item.type == item.START and item.nodeNames[-1] == 'i':
    ...         print item.expand().getText(nospacetags=['i', 'b'])
    italic italicbold
    x

    Check if parameters supplied to the getText() method work.
    >>> for item in parsed.getItems():
    ...     if item.type == item.START and item.nodeNames[-1] == 'i':
    ...         print item.expand().getText(spacetags=['b'], nospacetags=['i'])
    italic  italicbold 
    x
    >>> parsed=ParsedXmlFile(StringIO.StringIO('<a><b><c>C1</c>B1<c>C2</c></b>A1<b>B2</b><c>C3</c>A2</a>'))
    >>> for item in parsed.getItems():
    ...     if item.type == item.START:
    ...         expanded = item.expand()
    ...         print expanded.getAsString()
    ...         print expanded.getContentsAsString()
    ...         print item.expand().getText(nospacetags=['b', 'a'])
    ...         print item.expand().getText(nospacetags=['b', 'a'], spacetags=['c'])
    ...         print item.expand().getText(spacetags=['b'])
    ...         print item.expand().getText(nospacetags=['a'], ignoretags=['c'])
    ...         print item.expand().getText(ignoretags=['b'])
    ...         print '.' #doctest: +REPORT_NDIFF
    <a><b><c>C1</c>B1<c>C2</c></b>A1<b>B2</b><c>C3</c>A2</a>
    <b><c>C1</c>B1<c>C2</c></b>A1<b>B2</b><c>C3</c>A2
     C1 B1 C2 A1B2 C3 A2
     C1 B1 C2 A1B2 C3 A2
       C1 B1 C2  A1 B2  C3 A2 
     B1 A1 B2 A2
     A1 C3 A2 
    .
    <b><c>C1</c>B1<c>C2</c></b>
    <c>C1</c>B1<c>C2</c>
     C1 B1 C2 
     C1 B1 C2 
      C1 B1 C2  
     B1 
    <BLANKLINE>
    .
    <c>C1</c>
    C1
     C1 
     C1 
     C1 
    <BLANKLINE>
     C1 
    .
    <c>C2</c>
    C2
     C2 
     C2 
     C2 
    <BLANKLINE>
     C2 
    .
    <b>B2</b>
    B2
    B2
    B2
     B2 
     B2 
    <BLANKLINE>
    .
    <c>C3</c>
    C3
     C3 
     C3 
     C3 
    <BLANKLINE>
     C3 
    .
    """
}

if __name__ == '__main__':
    import doctest, sys
    doctest.testmod (sys.modules[__name__])
