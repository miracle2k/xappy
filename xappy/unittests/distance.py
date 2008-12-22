# Copyright (C) 2008 Lemur Consulting Ltd
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

from xappytest import *
from xappy.fieldactions import FieldActions
import xapian

class DistanceSearchTest(TestCase):
    locations = [
        ('Alderney', '49.5474 -2.8435'),
        ('Enfield', '51.6667 -0.0667', '51.3333 -0.0667'),
        ('Trent Park', '51.3417 -0.1583'),
    ]

    def pre_test(self):
        self.dbpath = os.path.join(self.tempdir, 'db')
        self.iconn = xappy.IndexerConnection(self.dbpath)

        self.iconn.add_field_action('location', xappy.FieldActions.GEOLOCATION)
        self.iconn.add_field_action('name', xappy.FieldActions.STORE_CONTENT)
        self.iconn.add_field_action('name', xappy.FieldActions.INDEX_FREETEXT, spell=True)
        for vals in self.locations:
            name, vals = vals[0], vals[1:]
            doc = xappy.UnprocessedDocument()
            doc.append('name', name)
            for val in vals:
                doc.append('location', val)
            self.iconn.add(doc)
        self.iconn.close()
        self.sconn = xappy.SearchConnection(self.dbpath)

    def post_test(self):
        self.sconn.close()

    def test_distance(self):
        doc = self.sconn.get_document('0')
        centre = xapian.LatLongCoords.unserialise(doc.get_value('location', 'loc'))
        self.assertEqual(centre.size(), 1)

        doc = self.sconn.get_document('1')
        centre = xapian.LatLongCoords.unserialise(doc.get_value('location', 'loc'))
        self.assertEqual(centre.size(), 2)

        doc = self.sconn.get_document('2')
        centre = xapian.LatLongCoords.unserialise(doc.get_value('location', 'loc'))
        self.assertEqual(centre.size(), 1)

        q = self.sconn.query_all()
        geosort = self.sconn.SortByGeolocation('location', '0, 0')
        res = list(self.sconn.search(q, 0, 10, sortby=geosort))
        self.assertEqual([int(item.id) for item in res], [0, 1, 2])

        q = self.sconn.query_distance('location', '0, 0')
        res = list(self.sconn.search(q, 0, 10))

if __name__ == '__main__':
    main()
