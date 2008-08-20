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

# Facets used in documents and their parent facets (or None for top-level facets)
facets = {
            'category': [None,],
            'colour': [None,],
            'type': ['category',],
            'make': ['category', 'colour',],
            'species': ['category',],
            'strings': ['type',],
         }

# Documents
docvalues = [
                (
                    ('category', 'instrument'),
                    ('colour', 'blue'),
                    ('type', 'drums'),
                    ('type', '2drums'),
                    ('make', 'Gretsch'),
                ),
                (
                    ('category', 'instrument'),
                    ('colour', 'red'),
                    ('colour', 'red'),
                    ('type', 'drums'),
                    ('type', '2drums'),
                    ('make', 'Stagg'),
                    ('offer', '2 for 1'),
                ),
                (
                    ('category', 'instrument'),
                    ('colour', 'black'),
                    ('type', 'accessories'),
                    ('make', 'Yamaha'),
                ),
                (
                    ('category', 'instrument'),
                    ('colour', 'brown'),
                    ('type', 'bass guitar'),
                    ('type', '2bass guitar'),
                    ('make', 'Musicman'),
                    ('strings', '4'),
                ),
                (
                    ('category', 'instrument'),
                    ('colour', 'green'),
                    ('type', 'bass guitar'),
                    ('type', '2bass guitar'),
                    ('make', 'Yamaha'),
                    ('strings', '5'),
                ),
                (
                    ('category', 'animal'),
                    ('colour', 'black'),
                    ('species', 'Persian'),
                    ('make', 'God'),
                ),
                (
                    ('category', 'animal'),
                    ('colour', 'grey'),
                    ('species', 'husky'),
                ),
            ]

class TestFacetHierarchy(TestCase):
    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = xappy.IndexerConnection(self.indexpath)
        for name in facets:
            iconn.add_field_action(name, xappy.FieldActions.INDEX_EXACT)
            iconn.add_field_action(name, xappy.FieldActions.STORE_CONTENT)
            iconn.add_field_action(name, xappy.FieldActions.FACET)
        for name, parents in facets.iteritems():
            for parent in parents:
                if parent:
                    iconn.add_subfacet(name, parent)
        for values in docvalues:
            doc = xappy.UnprocessedDocument()
            for name, value in values:
                doc.fields.append(xappy.Field(name, value))
            iconn.add(doc)
        iconn.flush()
        iconn.close()
        self.sconn = xappy.SearchConnection(self.indexpath)
        self.faceted_query = self.sconn.query_facet('category', 'instrument')
        self.faceted_query2 = self.sconn.query_facet('colour', 'black')

    def post_test(self):
        self.sconn.close()

    def _get_facets(self, query, usesubfacets=None, maxfacets=100, required_facets=None):
        results = self.sconn.search(query, 0, 10, getfacets=True, usesubfacets=usesubfacets)
        tuples = results.get_suggested_facets(maxfacets=maxfacets, required_facets=required_facets)
        return set([tuple[0] for tuple in tuples])

    def test_non_hierarchy(self):
        # Test that all facets with > 1 value are suggested when the m-set is all documents
        assert self._get_facets(self.sconn.query_all()) == set(['colour', 'category', 'species', 'type', 'make', 'strings'])
        # Test that all facets on instruments are returned for the faceted query
        assert self._get_facets(self.faceted_query) == set(['colour', 'type', 'make', 'strings'])

    def test_hierarchy(self):
        # Test that only top-level facets are suggested for a non-faceted query for all documents
        self.assertEqual(self._get_facets(self.sconn.query_all(), usesubfacets=True), set(['colour', 'category']))
        # Test that only top-level facets and subfacets of category are suggested for the faceted query,
        # but not 'category' for which there is only 1 value
        self.assertEqual(self._get_facets(self.faceted_query, usesubfacets=True), set(['make', 'type', 'colour']))
        # Test that subfacets 'make' and 'type' are suggested first over the top-level facet 'colour'
        self.assertEqual(self._get_facets(self.faceted_query, usesubfacets=True, maxfacets=2), set(['make', 'type']))
        # Test that if we explicitely ask for 'category' then we get it regardless
        self.assertEqual(self._get_facets(self.faceted_query, usesubfacets=True, required_facets='category'), set(['make', 'type', 'colour', 'category']))

        # Test that subfacet 'make' is suggested first over the top-level facet 'colour'
        self.assertEqual(self._get_facets(self.faceted_query2, usesubfacets=True, maxfacets=2), set(['category', 'make']))
        self.assertEqual(self._get_facets(self.faceted_query2, usesubfacets=True, maxfacets=1), set(['make']))

    def test_backwards_compatibility1(self):
        path = os.path.join(os.path.dirname(__file__), 'testdata', 'old_facet_db')
        iconn = xappy.IndexerConnection(path)
        iconn.close()
        sconn = xappy.SearchConnection(path)
        sconn.close()

    def test_start_with_number(self):
        """Regression test for bug with field contents starting with numbers.

        """
        # This search should only return the top-level colour facet, and the
        # "strings" subfacet of "type".
        query1 = self.sconn.query_facet('type', 'drums')
        query2 = self.sconn.query_facet('type', 'bass guitar')
        query = query1 | query2
        self.assertEqual(self._get_facets(query, usesubfacets=True),
                         set(['colour', 'strings']))

        # This search should return the same, but used not to because the 2
        # confused the prefix splitting code.
        query1 = self.sconn.query_facet('type', '2drums')
        query2 = self.sconn.query_facet('type', '2bass guitar')
        query = query1 | query2
        self.assertEqual(self._get_facets(query, usesubfacets=True),
                         set(['colour', 'strings']))


if __name__ == '__main__':
    main()
