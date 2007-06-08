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
r"""build.py: Build the documentation for secore.

"""
__docformat__ = "restructuredtext en"

import os
import sys

# Set the locale, if possible, so rst2html doesn't produce localised output.
try:
    import locale
    locale.setlocale(locale.LC_ALL, '')
except:
    pass

from docutils.core import publish_cmdline, default_description
import epydoc.cli

def call_rst2html(*args):
    description = ('Generates (X)HTML documents from standalone reStructuredText '
                   'sources.  ' + default_description)
    args = list(args)
    publish_cmdline(writer_name='html', description=description, argv=args)

def call_epydoc(*args):
    args = list(args)
    args.insert(0, 'epydoc')
    sys.argv = args
    epydoc.cli.cli()


call_rst2html('docs/introduction.rst', 'docs/introduction.html')
call_rst2html('README', 'README.html')
call_epydoc('-o', 'docs/api', '--name', 'secore', 'secore')
