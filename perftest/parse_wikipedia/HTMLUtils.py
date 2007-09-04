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

import urllib
import re
import htmlentitydefs

def __booltonum(val):
    """Convert any boolean values to '0' or '1'.
    
    Leave other values alone.

    """
    if val is True:
        return '1'
    elif val is False:
        return '0'
    return val

def encodeParams(paramdict, **kwargs):
    """Encode a dictionary of parameters to a querystring.

    `paramdict` is a dictionary of parameters to encode.

    `kwargs` is an optional set of keyword arguments to be added to the
    parameters to be encoded.  Any entries in kwargs which are also present in
    paramdict override the entries in paramdict.  Any entries in kwargs with a
    value of None cause any corresponding entry in paramdict to be omitted from
    the encoded output.

    """
    if isinstance(paramdict, dict):
        paramlist = [(key, __booltonum(val))
                     for (key, val) in paramdict.iteritems()
                     if key not in kwargs and val is not None]
    else:
        paramlist = [(key, __booltonum(val))
                     for (key, val) in paramdict
                     if key not in kwargs and val is not None]

    paramlist.extend([(key, val)
                      for (key, val) in kwargs.iteritems()
                      if val is not None])
    paramlist.sort()
    return urllib.urlencode (paramlist)

def encodeAttribValue(value):
    """
    Encode an attribute value by replacing HTML characters with entity values.
    The value may be unicode or a UTF-8 encoded string.
    The result is a UTF-8 encoded string.

    >>> encodeAttribValue('bar')
    'bar'
    >>> encodeAttribValue('bar"')
    'bar&quot;'
    >>> encodeAttribValue('bar"<>&"')
    'bar&quot;&lt;&gt;&amp;&quot;'

    >>> print repr(encodeAttribValue(u'bar\\xa3'))
    'bar&#xa3;'
    >>> utf8=u'bar\\xa3\\u1234'.encode('utf-8')
    >>> print repr(utf8)
    'bar\\xc2\\xa3\\xe1\\x88\\xb4'
    >>> print repr(encodeAttribValue(utf8))
    'bar&#xa3;&#x1234;'

    Ampersands are escaped even if they already form part of a valid
    entity:

    >>> encodeAttribValue('bar&quot;<>&"')
    'bar&amp;quot&#x3b;&lt;&gt;&amp;&quot;'

    All non-alphanumeric characters are also escaped.
    """
    result = []
    if isinstance(value, str):
        value = unicode(value, 'utf-8')
    for char in value:
        if (char >= '0' and char <= '9') or (char >= 'a' and char <= 'z') or (char >= 'A' and char <= 'Z') or char in './#_':
            result.append(char)
        elif char == '&':
            result.append('&amp;')
        elif char == '"':
            result.append('&quot;')
        elif char == '<':
            result.append('&lt;')
        elif char == '>':
            result.append('&gt;')
        elif char == '(':
            result.append('&#40;')
        elif char == ')':
            result.append('&#41;')
        elif char == '#':
            result.append('&#35;')
        else:
            result.append('&#%s;' % hex(ord(char))[1:])

    return ''.join(result).encode('utf-8')

def encodeText(value):
    """Encode a piece of text by replacing HTML characters with entity values.

    >>> encodeText('bar')
    'bar'
    >>> encodeText('bar"')
    'bar&quot;'
    >>> encodeText('bar"<>&"(')
    'bar&quot;&lt;&gt;&amp;&quot;('

    Ampersands are escaped even if they already form part of a valid
    entity:

    >>> encodeText('bar&quot;<>&"')
    'bar&amp;quot;&lt;&gt;&amp;&quot;'

    A non-string will be returned unchanged:
    >>> encodeText(1)
    1

    """
    if not isinstance(value, basestring):
        return value
    result = value.replace('&', '&amp;')
    result = result.replace('#', '&#35;')
    result = result.replace('"', '&quot;')
    result = result.replace('<', '&lt;')
    result = result.replace('>', '&gt;')
    return result

def percentEncode(value):
    """Percent encode a component of a URI.
    
    This replaces special characters with %XX where XX is the hexadecimal value
    of the character.

    Currently replaces all non-alphanumeric characters with the following
    exceptions:
    <space> is replaced by +
    ., /, #, _, = are not replaced.

    >>> percentEncode('q=M&%&%; S')
    'q=M%26%25%26%25%3B+S'
    >>> percentEncode(u'\u00a3')
    '%C2%A3'
    """
    result = []
    if isinstance(value, unicode):
        value = value.encode('utf-8')
    assert isinstance(value, str)
    for char in value:
        if (char >= '0' and char <= '9') or (char >= 'a' and char <= 'z') or (char >= 'A' and char <= 'Z') or char in './#_=':
            result.append(char)
        elif char == ' ':
            result.append('+')
        else:
            result.append('%%%s' % hex(ord(char)).upper()[2:])
    return ''.join(result)

def percentDecode(value):
    r"""Percent decode a component or a URI.

    This replaces percent encode sequences (ie, %XX, where XX is the
    hexadecimal value of the character) with the corresponding character.

    In addition, it replaces '+' with a space character (ie, + is equivalent to
    %20).
    
    Any other sequences following a % will be ignored.

    >>> percentDecode('q=M%26%25%26%25%3B+S')
    'q=M&%&%; S'
    >>> percentDecode('%C2%A3')
    '\xc2\xa3'

    """
    value = value
    if isinstance(value, unicode):
        value = value.encode('utf-8')
    value = value.replace('+', ' ')
    i = 0
    result = []
    while i != -1:
        j = value.find('%', i)
        if j == -1:
            result.append(value[i:])
            break
        if j != i:
            result.append(value[i:j])
        # Everything before position j has now been added to result.

        hexdigits = value[j + 1 : j + 3]
        try:
            hexval = int(hexdigits, 16)
            result.append(chr(hexval))
            i = j + 3
        except ValueError:
            result.append(value[j])
            i = j + 1

    return ''.join(result)

_markupre = re.compile ('</?\w[^>]*>')

def stripMarkup (s):
    """
    Strip all markup (<tags>) out of the supplied string.
    """
    return _markupre.sub ('', s)

_wikitags = { "''":'i', "'''":'b', '`':'tt', '__':'u', '^':'sup', ',,':'sub',
              '~-':'small', '~+':'big' }

_ent_re = re.compile ('&#x[\da-fA-F]+;|&#\d+;|&\w+;')

def ents2uni (s):
    """
    Substitute unicode characters for common HTML entities.
    
    This returns a unicode string.
    """
    def _subst (mo):
        ms = mo.group(0).lower()
        if ms.startswith ('&#x'):
            return unichr (int (ms[3:-1], 16))
        elif ms.startswith ('&#'):
            return unichr (int (ms[2:-1]))
        elif ms.startswith ('&'):
            try:
                return unichr (htmlentitydefs.name2codepoint[ms[1:-1]])
            except KeyError:
                return ms
        else:
            return ''
            
    return _ent_re.sub (_subst, unicode (s))

_js_slash = { '"':'\\"', '\n':'\\n', '\r':'\\r' }
def js_encode (s):
    """
    Encode a unicode string in Javascript literal form.
    """
    if isinstance (s, str): return s
    ret = []
    for c in s:
        if c in _js_slash:
            ret.append (_js_slash[c])
        elif ord(c) < 128:
            ret.append (str(c))
        else:
            ret.append ('\\u%04x' % ord(c))
    
    return ''.join (ret)

__tests__ = {
"Invalid % sequences to decode": """
>>> print percentDecode('%')
%
>>> print percentDecode('%')
%
>>> print percentDecode('foo%')
foo%
>>> print percentDecode('foo%%')
foo%%
>>> print percentDecode('foo%7g')
foo%7g
>>> print percentDecode('foo+%%20%')
foo % %
"""
}

if __name__ == "__main__":
    import doctest, sys
    doctest.testmod (sys.modules[__name__])
