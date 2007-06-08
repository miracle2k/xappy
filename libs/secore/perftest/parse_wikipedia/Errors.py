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

import HTMLUtils

class UserError(Exception):
    """
    Class used to pass a minor error from code performing an action to code
    which displays errors to the user.

    The message stored in such an exception should be raw HTML, as passed to
    the browser.  Any content in this message resulting from user inputs, MUST
    be HTML encoded (probably using HTMLUtils.encodeText()) to avoid risk of
    cross-site scripting attacks.

    For convenience, extra arguments may be provided which will be encoded and
    then merged with the message using the % operator.  For example:

    >>> print UserError('Error message')
    Error message
    >>> print UserError('Error %s', 'message with <html> quoted')
    Error message with &lt;html&gt; quoted
    """
    _cname = 'UserError'
    def __init__(self, msg, *args):
        self.msg = msg % tuple(HTMLUtils.encodeText(arg) for arg in args)

    def __str__(self):
        return self.msg

    def __repr__(self):
        return '%s("%s")' % (self._cname, self.msg.replace('\\', '\\\\').replace('"', '\\"'))

if __name__ == '__main__':
    import doctest, sys
    doctest.testmod (sys.modules[__name__])
