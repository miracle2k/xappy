# Copyright (C) 2007 Lemur Consulting Ltd
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
r"""parsedate.py: Parse date strings.

"""
__docformat__ = "restructuredtext en"

import datetime
import re

yyyymmdd_re = re.compile(r'(?P<year>[0-9]{4})(?P<month>[0-9]{2})(?P<day>[0-9]{2})$')
yyyy_mm_dd_re = re.compile(r'(?P<year>[0-9]{4})([-/.])(?P<month>[0-9]{2})\2(?P<day>[0-9]{2})$')

def date_from_string(value):
    """Parse a string into a date.

    If the value supplied is already a date-like object (ie, has 'year',
    'month' and 'day' attributes), it is returned without processing.

    Supported date formats are:

     - YYYYMMDD
     - YYYY-MM-DD 
     - YYYY/MM/DD 
     - YYYY.MM.DD 

    """
    if (hasattr(value, 'year')
        and hasattr(value, 'month')
        and hasattr(value, 'day')):
        return value

    mg = yyyymmdd_re.match(value)
    if mg is None:
        mg = yyyy_mm_dd_re.match(value)

    if mg is not None:
        year, month, day = (int(i) for i in mg.group('year', 'month', 'day'))
        return datetime.date(year, month, day)

    raise ValueError('Unrecognised date format')
