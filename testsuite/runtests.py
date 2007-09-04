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
r"""runtests.py: Run a set of tests with doctest and unittest.

The list of modules to test is specified at the top of the file, in the
MODNAMES variable.

Other files containing documentation to be tested is listed in the OTHER_FILES
variable.

A subset of the modules can be tested by specifying a list of module names on
the command line.

"""
__docformat__ = "restructuredtext en"

#######################
# Begin configuration #
#######################

# List the modules to test with doctest (please keep this list in alphabetical
# order, for ease of maintenance).
MODNAMES = (
    'secore',
    'secore.datastructures',
    'secore.errors',
    'secore.fieldactions',
    'secore.fieldmappings',
    'secore.highlight',
    'secore.indexerconnection',
    'secore.marshall',
    'secore.parsedate',
    'secore.searchconnection',
)

# List the documentation files which should be valid doctest inputs
OTHER_FILES = (
    'docs/introduction.rst',
)


# Whitelist lines for coverage report (ie, lines which should always be
# considered as having been executed).  The first item in each line is a line
# number that the line can appear at, which may be negative to indicate lines
# from the end of the file.  The second item is a regular expression to match
# against the line: if the expression matches, the line will be considered
# executed.
COVERED_LINES = (
    (-2, r'\s*import doctest, sys'),
    (-1, r'\s*doctest.testmod'),
)

########################
# End of configuration #
########################

import sys
import os
import re
import unittest
import doctest
import coverage
import traceback
import copy

def canonical_path(path):
    return os.path.normcase(os.path.normpath(os.path.realpath(path)))

def check_whitelist(lines, checklinenum, covered_lines):
    """Check whether line `checklinenum`, for the file with contents `lines`
    is in the whitelist.  Return True if so, False otherwise.
    """
    for linenum, pattern in covered_lines:
        if linenum < 0:
            linenum += len(lines) + 1
        if linenum <= 0 or linenum > len(lines):
            continue
        if checklinenum != linenum:
            continue
        if not pattern.match(lines[checklinenum - 1]):
            continue
        return True
    return False

def create_docfile_suite(mod, modpath):
    """Create a suite of tests from a text file containing doctests.

    The dictionary of the module is imported into the namespace which the tests
    are run in (excluding any entries which begin with a double underscore), so
    the tests can be written as if they were entries in the modules __test__
    dictionary.

    """
    globs = {'__file__': modpath,
    }
    for key in mod.__dict__.keys():
        if not key.startswith('__'):
            globs[key] = mod.__dict__[key]
    return doctest.DocFileSuite(modpath,
                                module_relative=False,
                                globs=globs,
                                setUp=setup_test,
                                tearDown=teardown_test,
                                )

def recursive_rm(path):
    """Recursively remove a directory and its contents.

    """
    if os.path.isdir(path):
        for root, dirs, files in os.walk(path, topdown=False):
            for file in files:
                os.remove(os.path.join(root, file))
            for dir in dirs:
                os.rmdir(os.path.join(root, dir))
        os.rmdir(path)


_orig_vals = {}
def setup_test(dtobj):
    """Prepare for running a test.

    """
    tmpdir = 'test_tmp'
    recursive_rm(tmpdir)

    _orig_vals['wd'] = os.path.abspath(os.getcwd())
    _orig_vals['path'] = sys.path
    sys.path = copy.copy(sys.path)
    sys.path.insert(0, _orig_vals['wd'])

    testdir = os.path.dirname(dtobj.globs['__file__'])
    sys.path.insert(0, testdir)

    os.mkdir(tmpdir)
    os.chdir(tmpdir)

def teardown_test(dtobj):
    """Cleanup after running a test.

    """
    tmpdir = 'test_tmp'
    os.chdir(_orig_vals['wd'])
    sys.path = _orig_vals['path']
    recursive_rm(tmpdir)

def run_tests(topdir, modnames, other_files):
    """Run tests on the specified modules.

    Returns a list of modules which were tested.

    """

    # Check command line for overrides to module names
    if len(sys.argv) > 1:
        newnames = []
        for arg in sys.argv[1:]:
            if arg in modnames:
                newnames.append(arg)
            else:
                print "Module `%s' not known" % arg
                sys.exit(1)
        modnames = newnames

    # Make a test suite to put all the tests in.
    suite = unittest.TestSuite()

    # Use the coverage test module to get coverage information.
    coverage.erase()
    coverage.start()
    coverage.exclude('#pragma[: ]+[nN][oO] [cC][oO][vV][eE][rR]')

    # Add all the doctest tests.
    modules = []
    for modname in modnames:
        try:
            # Get the path of the module (to search for associated tests)
            modpath = os.path.join(*(modname.split('.')))
            modpath = canonical_path(modpath)
            if os.path.isdir(modpath):
                modpath = os.path.join(modpath, '__init__')

            # Import the module
            sys.path.insert(0, topdir)
            mod = __import__(modname, None, None, [''])
            del sys.path[0]

            # Check that the module imported came from the expected path.
            if os.path.splitext(mod.__file__)[0] != modpath:
                print "Couldn't import module `%s`: got module of same name, from wrong path (%r)" %  (modname, mod.__file__)
                continue

            # Add module to test suite.
            suite.addTest(doctest.DocTestSuite(mod, setUp=setup_test, tearDown=teardown_test))
            modules.append(mod)

            # Check for additional doctest files
            modpath = modpath + '_doctest%d.txt'
            num = 1
            while os.path.exists(modpath % num):
                suite.addTest(create_docfile_suite(mod, modpath % num))
                num += 1

        except ImportError, e:
            print "Couldn't import module `%s`: %s" % (modname, e)
            traceback.print_exc()

    # Add any other files with doctests in them.
    for file in other_files:
        fullpath = os.path.join(topdir, file)
        globs = {'__file__': modpath,}
        suite.addTest(doctest.DocFileSuite(fullpath,
                                           module_relative=False,
                                           globs=globs,
                                           setUp=setup_test,
                                           tearDown=teardown_test,
                                          ))

    # Now, run everything.
    runner = unittest.TextTestRunner()
    runner.run(suite)

    # Finished run - stop the coverage tests
    coverage.stop()
    return modules

def get_coverage(topdir, modules, covered_lines):
    # Compile the expressions in COVERED_LINES
    covered_lines = [(lines, re.compile(pattern))
                     for (lines, pattern) in covered_lines]

    # Get the coverage statistics
    stats = []
    for module in modules:
        (filename, stmtlines, stmtmissed, stmtmissed_desc) = coverage.analysis(module)
        filename = canonical_path(filename)
        if filename.startswith(topdir):
            filename = filename[len(topdir) + 1:]

        lines = open(filename).readlines()
        linenum = len(lines)

        # Remove whitelisted lines
        stmtmissed = [linenum for linenum in stmtmissed
                      if not check_whitelist(lines, linenum, covered_lines)]

        # Sort the lines (probably already in order, but let's double-check)
        stmtlines.sort()
        stmtmissed.sort()

        # Build a compressed list of ranges of lines which have no statements
        # which were executed, but do contain statements.
        missed_ranges = []
        stmtpos = 0
        currrange = None
        for linenum in stmtmissed:
            while stmtlines[stmtpos] < linenum:
                # If there are any statements before the current linenum, we
                # end the current range of missed statements
                currrange = None
                stmtpos += 1
            if currrange is None:
                currrange = [linenum, linenum]
                missed_ranges.append(currrange)
            else:
                currrange[1] = linenum
            stmtpos += 1

        percent = (len(stmtlines) - len(stmtmissed)) * 100.0 / len(stmtlines)
        stats.append((filename, percent, len(stmtlines), missed_ranges))
    return stats

def display_coverage(stats):
    print "Coverage report:"
    max_filename_len  = max(len(stat[0]) for stat in stats)
    for filename, percent, total, missed in stats:
        msg = "%r%s %5.1f%% of %d" % (filename, ' ' * (max_filename_len - len(filename)), percent, total)
        if len(missed) != 0:
            for pos in xrange(len(missed)):
                if missed[pos][0] == missed[pos][1]:
                    missed[pos] = str(missed[pos][0])
                elif missed[pos][0] + 1 == missed[pos][1]:
                    missed[pos] = "%d,%d" % tuple(missed[pos])
                else:
                    missed[pos] = "%d-%d" % tuple(missed[pos])
            msg += "\t Missed: %s" % ','.join(missed)
        print msg

topdir = canonical_path(os.path.join(os.path.dirname(__file__), '..'))
modules = run_tests(topdir, MODNAMES, OTHER_FILES)
display_coverage(get_coverage(topdir, modules, COVERED_LINES))
