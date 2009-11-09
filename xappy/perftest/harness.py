# Copyright (C) 2009 Richard Boulton
# Copyright (C) 2008 Lemur Consulting Ltd
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
r"""harness.py: Framework for xappy performance tests.

Performance tests should just start with "from harness import *", which will
provide a convenient environment for writing tests of xappy performance.

"""
__docformat__ = "restructuredtext en"

import os
import shutil
import sys
import tempfile
import time
import unittest

# Ensure that xappy is on the path, when run uninstalled.
up = os.path.dirname
sys.path.insert(0, up(up(up(__file__))))
import xappy

class PerfTestCase(unittest.TestCase):
    """Base class of xappy performance tests.

    """
    def setUp(self):
        """Set up environment for a performance test.

        This should not normally be implemented in subclasses - instead,
        implement the pre_test() method, which is called by this method after
        performing the standard test setup process.

        Various directories are available:

         - self.tempdir: A temporary directory, which will be cleared after
           each test is run.
         - self.sourcedatadir: A directory containing fixed source data (same
           directory for all tests).
         - self.builtdatadir: A directory for storing persistent generated data
           for a test.

        """
        self.tempdir = tempfile.mkdtemp()
        testdatadir = os.path.join(os.path.dirname(__file__), 'data')
        self.sourcedatadir = os.path.join(testdatadir, 'source')
        self.builtdatadir = os.path.join(testdatadir, 'built',
                                         'test_' + type(self).__name__)
        hashpath = os.path.join(testdatadir, 'built',
                                'hash_' + type(self).__name__ + '.txt')

        if not os.path.exists(self.builtdatadir):
            current_hash = None
        else:
            try:
                current_hash = open(hashpath).read()
            except IOError:
                current_hash = None

        new_hash = self.hash_data()
        if current_hash is None or current_hash != new_hash:
            try:
                if os.path.exists(self.builtdatadir):
                    shutil.rmtree(self.builtdatadir)
                os.makedirs(self.builtdatadir)
                self.build_data()
            except:
                if os.path.exists(hashpath):
                    os.unlink(hashpath)
                raise

            fd = open(hashpath, 'w')
            fd.write(new_hash)
            fd.close()

        self.pre_test()
        self.timers = {}
        self.timer_order = []
        self.start_timer('main')

    def start_timer(self, timer, desc=None):
        """Start the named timer.

        `desc` is a description of what is being timed.  This is ignored if the
        timer has been started before.

        """
        if desc is None:
            desc = timer
        try:
            data = self.timers[timer]
            data[2] = time.time()
        except KeyError:
            data = [0, 0.0, time.time(), desc]
            self.timers[timer] = data
            self.timer_order.append(timer)

    def stop_timer(self, timer):
        """Stop the named timer.

        """
        data = self.timers[timer]
        if data[2] is None:
            return
        now = time.time()
        data[0] += 1
        data[1] += now - data[2]
        data[2] = None

    def reset_timers(self, timers):
        """Reset the named timers to 0.

        """
        for timer in timers:
            data = self.timers.get(timer, None)
            if data is not None:
                data[0] = 0
                data[1] = 0.0

    def format_timers(self):
        """Format the timers for display.

        """
        result = []
        for timer in self.timer_order:
            count, totaltime, starttime, desc = self.timers[timer]
            if count == 1:
                result.append('%12.6fs: %s' % (totaltime, desc))
            else:
                result.append('%12.6fs: %s (%d instances)' % (totaltime, desc, count))
        return '\n'.join(result)

    def tearDown(self):
        """Clean up after a test.

        This should not normally be implemented in subclasses - instead,
        implement the post_test() method, which is called by this method before
        performing the standard cleanup process.

        """
        for timer in self.timers.keys():
            self.stop_timer(timer)
        self.post_test()
        shutil.rmtree(self.tempdir)
        print self.format_timers()

    def hash_data(self):
        """Get a hash, or some other identifier, for the data which will be
        stored by the current version of the test when build_data() is called.

        The hash must change whenever the data stored changes.

        This should be implemented in subclasses.

        """
        return None

    def build_data(self):
        """Build the data needed for a test.

        The data should be put into self.builtdatadir, which is a directory which
        will exist when this is called.

        """
        pass

    def pre_test(self):
        """Prepare for a test.  This is called before a test is started, but
        after the standard setup process.

        This is intended to be overridden by subclasses when special setup is
        required for a test.

        """
        pass

    def post_test(self):
        """Cleanup after a test.  This is called after a test finishes, but
        before the standard cleanup process.

        This is intended to be overridden by subclasses when special cleanup is
        required for a test.

        """
        pass

main = unittest.main
