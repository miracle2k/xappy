# Copyright (C) 2008 Lemur Consulting Ltd
# Copyright (C) 2009 Richard Boulton
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

class TestFacets(TestCase):
    def pre_test(self):
        indexpath = os.path.join(self.tempdir, 'foo')
        self.iconn = xappy.IndexerConnection(indexpath)
        for name in facets:
            self.iconn.add_field_action(name, xappy.FieldActions.STORE_CONTENT)
            if name == 'strings':
                self.iconn.add_field_action(name, xappy.FieldActions.FACET,
                                            type='float')
            else:
                self.iconn.add_field_action(name, xappy.FieldActions.FACET)
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

    def test_facets(self):
        query = self.sconn.query_facet('category', 'instrument')
        results = query.search(0, 10, getfacets=True)

        self.assertEqual(results.get_facets(),
                         {
                            'category': (('instrument', 5),),
                            'colour': (('black', 1), ('blue', 1), ('brown', 1), ('green', 1), ('red', 1)),
                            'strings': (((4.0, 4.0), 1), ((5.0, 5.0), 1)),
                            'species': (),
                            'type': (('accessories', 1), ('bass guitar', 2), ('drums', 2)),
                            'make': (('gretsch', 1), ('musicman', 1), ('stagg', 1), ('yamaha', 2))
                         }
                        )

if __name__ == '__main__':
    main()
