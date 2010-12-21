# Copyright (C) 2009 Lemur Consulting Ltd
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
r"""utils.py: Utility functions.

"""
__docformat__ = "restructuredtext en"

import math

def get_significant_digits(value, lower, upper):
    """Get the significant digits of value which are constrained by the
    (inclusive) lower and upper bounds.

    If there are no significant digits which are definitely within the
    bounds, exactly one significant digit will be returned in the result.

    >>> get_significant_digits(15,15,15)
    15
    >>> get_significant_digits(15,15,17)
    20
    >>> get_significant_digits(4777,208,6000)
    5000
    >>> get_significant_digits(4777,4755,4790)
    4800
    >>> get_significant_digits(4707,4695,4710)
    4700
    >>> get_significant_digits(4719,4717,4727)
    4720
    >>> get_significant_digits(0,0,0)
    0
    >>> get_significant_digits(9,9,10)
    9
    >>> get_significant_digits(9,9,100)
    9

    """
    assert(lower <= value)
    assert(value <= upper)
    diff = upper - lower

    # Get the first power of 10 greater than the difference.
    # This corresponds to the magnitude of the smallest significant digit.
    if diff == 0:
        pos_pow_10 = 1
    else:
        pos_pow_10 = int(10 ** math.ceil(math.log10(diff)))

    # Special case for situation where we don't have any significant digits:
    # get the magnitude of the most significant digit in value.
    if pos_pow_10 > value:
        if value == 0:
            pos_pow_10 = 1
        else:
            pos_pow_10 = int(10 ** math.floor(math.log10(value)))

    # Return the value, rounded to the nearest multiple of pos_pow_10
    return ((value + pos_pow_10 // 2) // pos_pow_10) * pos_pow_10

def add_to_dict_of_dicts(d, key, item, value):
    """Add an entry to a dict of dicts.

    """
    try:
        d[key][item] = d[key].get(item, 0) + value
    except KeyError:
        d[key] = {item: value}
