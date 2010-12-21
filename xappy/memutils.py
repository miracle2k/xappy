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
r"""memutils.py: Memory handling utilities.

"""
__docformat__ = "restructuredtext en"

import os

def _get_physical_mem_sysconf():
    """Try getting a value for the physical memory using os.sysconf().

    Returns None if no value can be obtained - otherwise, returns a value in
    bytes.

    """
    if getattr(os, 'sysconf', None) is None:
        return None

    try:
        pagesize = os.sysconf('SC_PAGESIZE')
    except ValueError:
        try:
            pagesize = os.sysconf('SC_PAGE_SIZE')
        except ValueError:
            return None

    try:
        pagecount = os.sysconf('SC_PHYS_PAGES')
    except ValueError:
        return None

    return pagesize * pagecount

def _get_physical_mem_win32():
    """Try getting a value for the physical memory using GlobalMemoryStatus.

    This is a windows specific method.  Returns None if no value can be
    obtained (eg, not running on windows) - otherwise, returns a value in
    bytes.

    """
    try:
        import ctypes
        import ctypes.wintypes as wintypes
    except ValueError:
        return None

    class MEMORYSTATUS(wintypes.Structure):
        _fields_ = [
            ('dwLength', wintypes.DWORD),
            ('dwMemoryLoad', wintypes.DWORD),
            ('dwTotalPhys', wintypes.DWORD),
            ('dwAvailPhys', wintypes.DWORD),
            ('dwTotalPageFile', wintypes.DWORD),
            ('dwAvailPageFile', wintypes.DWORD),
            ('dwTotalVirtual', wintypes.DWORD),
            ('dwAvailVirtual', wintypes.DWORD),
        ]

    m = MEMORYSTATUS()
    wintypes.windll.kernel32.GlobalMemoryStatus(wintypes.byref(m))
    return m.dwTotalPhys

def get_physical_memory():
    """Get the amount of physical memory in the system, in bytes.

    If this can't be obtained, returns None.

    """
    result = _get_physical_mem_sysconf()
    if result is not None:
        return result
    return _get_physical_mem_win32()
