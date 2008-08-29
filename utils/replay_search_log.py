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
import time
import xappy

def display_time(starttime, count):
    endtime = time.time()
    print "%d,%.5f" % (count, endtime - starttime)

def replay_from_file(conn, fd):
    starttime = time.time()
    count = 0
    print "Searches,Total Time (seconds)"
    for line in fd:
        line = line.strip()
        queryrepr, args, kwargs = eval(line)
        query = conn.query_from_evalable(queryrepr)
        results = query.search(*args, **kwargs)
        count += 1
        if count % 10 == 0:
            display_time(starttime, count)
    display_time(starttime, count)


usage = """
replay_search_log.py <dbpath> <logpath>
"""

def run_from_commandline():
    import sys
    if len(sys.argv) != 3:
        print usage.strip()
        sys.exit(1)

    dbpath = sys.argv[1]
    replayfile = sys.argv[2]

    conn = xappy.SearchConnection(dbpath)
    fd = file(replayfile, "rb")
    replay_from_file(conn, fd)
    fd.close()

if __name__ == "__main__":
    run_from_commandline()
