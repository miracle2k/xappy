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
r"""test.py: Run a set of tests with doctest and unittest.

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
    'xappy',
    'xappy.datastructures',
    'xappy.errors',
    'xappy.fieldactions',
    'xappy.fieldmappings',
    'xappy.highlight',
    'xappy.indexerconnection',
    'xappy.marshall',
    'xappy.parsedate',
    'xappy.searchconnection',
)

# List the documentation files which should be valid doctest inputs
OTHER_FILES = (
    'docs/introduction.rst',
    'docs/weighting.rst',
    'docs/queries.rst',
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

def create_docfile_suite(mod, moddir, testpath):
    """Create a suite of tests from a text file containing doctests.

    The dictionary of the module is imported into the namespace which the tests
    are run in (excluding any entries which begin with a double underscore), so
    the tests can be written as if they were entries in the modules __test__
    dictionary.

    """
    globs = {
        '__file__': moddir,
    }
    for key in mod.__dict__.keys():
        if not key.startswith('__'):
            globs[key] = mod.__dict__[key]
    return doctest.DocFileSuite(testpath,
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

def get_example_search_connection():
    import os, xappy
    db_path = os.path.abspath('exampledb')
    iconn = xappy.IndexerConnection(db_path)
    iconn.add_field_action('text', xappy.FieldActions.INDEX_FREETEXT, spell=True, stop=("a be not or to"), weight=2, language="en")
    iconn.flush()

    return xappy.SearchConnection(db_path)

def get_example_indexer_connection():
    import os, xappy
    db_path = os.path.abspath('exampledb')
    iconn = xappy.IndexerConnection(db_path)
    iconn.add_field_action('text', xappy.FieldActions.INDEX_FREETEXT, spell=True, stop=("a be not or to"), weight=2, language="en")
    return iconn


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

    import xappy
    dtobj.globs['get_example_search_connection'] = get_example_search_connection
    dtobj.globs['get_example_indexer_connection'] = get_example_indexer_connection
    dtobj.globs['Query'] = xappy.Query
    dtobj.globs['FieldActions'] = xappy.FieldActions

    testdir = dtobj.globs['__file__']
    sys.path.insert(0, testdir)

    os.mkdir(tmpdir)
    os.chdir(tmpdir)

def teardown_test(dtobj):
    """Cleanup after running a test.

    """
    for key, val in list(dtobj.globs.iteritems()):
        if hasattr(val, '__module__') and \
           val.__module__ is not None and \
           val.__module__.startswith('xappy'):
            if hasattr(val, 'close'):
                if not isinstance(val, type):
                    val.close()
        del dtobj.globs[key]
    del key
    del val
    dtobj.globs.clear()
    # Try really hard to make sure any xapian databases have been closed
    # properly, so that windows doesn't give errors when we try and delete
    # them.
    import gc
    gc.collect()
    tmpdir = 'test_tmp'
    os.chdir(_orig_vals['wd'])
    sys.path = _orig_vals['path']
    recursive_rm(tmpdir)

def find_unittests(testdir):
    """Find all files containing unit tests under a top directory.

    """
    unittests = []
    for root, dirnames, filenames in os.walk(testdir):
        for filename in filenames:
            filepath = os.path.join(root, filename)
            relpath = filepath[len(testdir)+1:]
            if filename == "__init__.py":
                continue

            if filename.endswith(".py"):
                unittests.append(relpath)
    return unittests

def get_topdir():
    return canonical_path(os.path.dirname(__file__))

def make_suite(modnames, other_files, use_coverage, specific_mods):
    topdir = get_topdir()
    # Make a test suite to put all the tests in.
    suite = unittest.TestSuite()

    if use_coverage:
        # Use the coverage test module to get coverage information.
        import coverage
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
            moddir, modfilename = os.path.split(modpath)
            modpath = os.path.join(moddir, "doctests", modfilename + '_doctest%d.txt')
            num = 1
            while os.path.exists(modpath % num):
                suite.addTest(create_docfile_suite(mod, moddir, modpath % num))
                num += 1

        except ImportError, e:
            print "Couldn't import module `%s`: %s" % (modname, e)
            traceback.print_exc()

    # Add any other files with doctests in them.
    for file in other_files:
        fullpath = os.path.join(topdir, file)
        globs = {'__file__': canonical_path("xappy"),}
        suite.addTest(doctest.DocFileSuite(fullpath,
                                           module_relative=False,
                                           globs=globs,
                                           setUp=setup_test,
                                           tearDown=teardown_test,
                                          ))

    # Add unittests
    loader = unittest.TestLoader()
    for testpath in find_unittests(os.path.join(topdir, "xappy", "unittests")):
        modpath = "xappy.unittests." + testpath.replace('/', '.')[:-3]
        mod = __import__(modpath, None, None, [''])
        test = loader.loadTestsFromModule(mod)
        suite.addTest(test)

    return modules, suite


def run_tests(modnames, other_files, use_coverage, specific_mods):
    """Run tests on the specified modules.

    Returns a list of modules which were tested.

    """

    # Check command line for overrides to module names
    if specific_mods:
        newnames = []
        for arg in specific_mods:
            if arg in modnames:
                newnames.append(arg)
            else:
                print "Module `%s' not known" % arg
                sys.exit(1)
        modnames = newnames

    modules, suite = make_suite(modnames, other_files, use_coverage, specific_mods)

    # Now, run everything.
    runner = unittest.TextTestRunner()
    runner.run(suite)

    if use_coverage:
        # Finished run - stop the coverage tests
        import coverage
        coverage.stop()
    return modules

def get_coverage(modules, covered_lines):
    topdir = get_topdir()
    import coverage

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

def run(specific_mods, use_coverage=False, use_profiling=False):
    if use_profiling:
        try:
            import cProfile as profile
        except ImportError:
            import profile

        modules = profile.run('run_tests(MODNAMES, OTHER_FILES, %r, %r)' % (use_coverage, specific_mods), os.path.join(get_topdir(), '.runtests.prof'))
    else:
        modules = run_tests(MODNAMES, OTHER_FILES, use_coverage,
                            specific_mods)

    if use_coverage:
        display_coverage(get_coverage(modules, COVERED_LINES))

def make_all_suite():
    modules, suite = make_suite(MODNAMES, OTHER_FILES, False, ())
    return suite

if __name__ == '__main__':
    run(sys.argv[1:])
    #run(sys.argv[1:], use_profiling=True)
    #run(sys.argv[1:], use_coverage=True)
