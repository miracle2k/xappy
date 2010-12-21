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

# Facets used in documents
facets = [
            'category',
            'colour',
            'type',
            'make',
            'species',
            'strings',
         ]

# Documents
docvalues = [
                {
                    'category': 'instrument',
                    'colour': 'blue',
                    'type': 'drums',
                    'make': 'Gretsch',
                },
                {
                    'category': 'instrument',
                    'colour': 'red',
                    'type': 'drums',
                    'make': 'Stagg',
                },
                {
                    'category': 'instrument',
                    'colour': 'black',
                    'type': 'accessories',
                    'make': 'Yamaha',
                },
                {
                    'category': 'instrument',
                    'colour': 'brown',
                    'type': 'bass guitar',
                    'make': 'Musicman',
                    'strings': '4',
                },
                {
                    'category': 'instrument',
                    'colour': 'green',
                    'type': 'bass guitar',
                    'make': 'Yamaha',
                    'strings': '5',
                },
            ]

class TestValueMapSource(TestCase):
    def pre_test(self):
        indexpath = os.path.join(self.tempdir, 'foo')
        self.iconn = xappy.IndexerConnection(indexpath)
        for name in facets:
            self.iconn.add_field_action(name, xappy.FieldActions.INDEX_EXACT)
            self.iconn.add_field_action(name, xappy.FieldActions.STORE_CONTENT)
            self.iconn.add_field_action(name, xappy.FieldActions.FACET)
            self.iconn.add_field_action(name, xappy.FieldActions.SORTABLE)
        for values in docvalues:
            doc = xappy.UnprocessedDocument()
            for name, value in values.iteritems():
                doc.fields.append(xappy.Field(name, value))
            self.iconn.add(doc)
        self.iconn.flush()
        self.sconn = xappy.SearchConnection(indexpath)

    def post_test(self):
        self.iconn.close()
        self.sconn.close()

    def test_query_1(self):
        colour_wt = { 'blue': 1.0, 'red': 2.0, 'black': 3.0, 'brown': 1.5, 'green': 2.5 }
        q = self.sconn.query_valuemap('colour', colour_wt)
        results = self.sconn.search(q, 0, 10)
        assert results.matches_estimated == 5
        assert results.estimate_is_exact
        assert [r.data['colour'][0] for r in results] == ['black', 'green', 'red', 'brown', 'blue']

    def test_query_2(self):
        colour_wt = { 'blue': 1.0, 'red': 2.0, 'black': 3.0 }
        q = self.sconn.query_valuemap('colour', colour_wt, 4.0)
        results = self.sconn.search(q, 0, 10)
        assert results.matches_estimated == 5
        assert results.estimate_is_exact
        assert [r.data['colour'][0] for r in results] == ['brown', 'green', 'black', 'red', 'blue']
        

if __name__ == '__main__':
    main()
