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
r"""marshall.py: Marshal values into strings

"""
__docformat__ = "restructuredtext en"

import math

def _long_to_base256_array(value, length, flip):
    result = []
    for i in xrange(length):
        n = value % 256
        if flip: n = 255 - n
        result.insert(0, chr(n))
        value /= 256
    return result

def float_to_string(value):
    """Marshall a floating point number to a string which sorts in the
    appropriate manner.

    """
    mantissa, exponent = math.frexp(value)
    sign = '1'
    if mantissa < 0:
        mantissa = -mantissa
        sign = '0'

    # IEEE representation of doubles uses 11 bits for the exponent, with a bias
    # of 1023.  There's then another 52 bits in the mantissa, so we need to
    # add 1075 to be sure that the exponent won't be negative.
    # Even then, we check that the exponent isn't negative, and consider the
    # value to be equal to zero if it is.
    exponent += 1075
    if exponent < 0: # Note - this can't happen on most architectures #pragma: no cover
        exponent = 0
        mantissa = 0
    elif mantissa == 0:
        exponent = 0

    # IEEE representation of doubles uses 52 bits for the mantissa.  Convert it
    # to a 7 character string, and convert the exponent to a 2 character
    # string.

    mantissa = long(mantissa * (2**52))

    digits = [sign]
    digits.extend(_long_to_base256_array(exponent, 2, sign == '0'))
    digits.extend(_long_to_base256_array(mantissa, 7, sign == '0'))

    return ''.join(digits)

def date_to_string(date):
    """Marshall a date to a string which sorts in the appropriate manner.

    """
    return '%04d%02d%02d' % (date.year, date.month, date.day)
