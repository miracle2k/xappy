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
"""Setup script for xappy extension module.

"""

import sys

# Use setuptools if we're part of a larger build system which is already using
# it.
if ('setuptools' in sys.modules):
    import setuptools
    from setuptools import setup, Extension
    from setuptools.command.build_ext import build_ext
    using_setuptools = True
else:
    import distutils
    from distutils.core import setup, Extension
    from distutils import sysconfig
    using_setuptools = False

# Customise compiler options.
if using_setuptools:
    try:
        setuptools_build_ext = build_ext.build_extension
        def my_build_ext(self, ext):
            """Remove the -Wstrict-prototypes option from the compiler command.

            This option isn't supported for C++, so we remove it to avoid annoying
            warnings.

            """
            try:
                self.compiler.compiler_so.remove('-Wstrict-prototypes')
            except (AttributeError, ValueError):
                pass
            retval = setuptools_build_ext(self, ext)
            return retval
        build_ext.build_extension = my_build_ext
    except AttributeError:
        pass
else:
    distutils_customize_compiler = sysconfig.customize_compiler
    def my_customize_compiler(compiler):
        """Remove the -Wstrict-prototypes option from the compiler command.

        This option isn't supported for C++, so we remove it to avoid annoying
        warnings.

        """
        retval = distutils_customize_compiler(compiler)
        try:
            compiler.compiler_so.remove('-Wstrict-prototypes')
        except (AttributeError, ValueError):
            pass
        return retval
    sysconfig.customize_compiler = my_customize_compiler

# Extra arguments for setup() which we don't always want to supply.
extra_kwargs = {}
if using_setuptools:
    extra_kwargs['test_suite'] = "test.test" # FIXME

long_description = """
The "xappy" python module is an easy-to-use interface to the Xapian search
engine. Xapian provides a low level interface, dealing with terms and
documents, but not really worrying about where terms come from, or how to build
searches to match the way in which data has been indexed. In contrast, "xappy"
allows you to design a field structure, specifying what kind of information is
held in particular fields, and then uses this field structure to index data
appropriately, and to build and perform searches.

Xappy is not yet stable - in particular, both the API and database format will
change in future releases.   If you wish to use it, we recommend that you
subscribe to the xappy-discuss mailing list (see
http://groups.google.com/group/xappy-discuss) to keep up-to-date with changes
to Xappy. 

"""


setup(name = "xappy",
      version = "0.5", # update this in xappy/__init__.py, too.  FIXME - get automatically
      author = "Richard Boulton",
      author_email = "richard@lemurconsulting.com",
      maintainer = "Richard Boulton",
      maintainer_email = "richard@lemurconsulting.com",
      url = "http://code.google.com/p/xappy",
      download_url = "http://xappy.googlecode.com/files/xappy-0.5.tar.gz",
      description = "Easy-to-use interface to the Xapian search engine",
      long_description = long_description,
      classifiers = [
          'Development Status :: 3 - Alpha',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: GNU General Public License (GPL)',
          'Programming Language :: C++',
          'Topic :: Internet :: WWW/HTTP :: Indexing/Search',
          'Operating System :: MacOS',
          'Operating System :: Microsoft',
          'Operating System :: POSIX',
      ],
      license = 'GPL',
      platforms = 'Any',

      packages = ['xappy'],
      package_dir = {'xappy': 'xappy'},
                              
      **extra_kwargs)
