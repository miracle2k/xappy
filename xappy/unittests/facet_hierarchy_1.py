from unittest import TestCase, main
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from xappy.indexerconnection import *
from xappy.fieldactions import *
from xappy.searchconnection import *

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
                    'offer': '2 for 1',
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
                {
                    'category': 'animal',
                    'colour': 'black',
                    'species': 'Persian',
                    'make': 'God',
                },
                {
                    'category': 'animal',
                    'colour': 'grey',
                    'species': 'husky',
                },
            ]

class TestFacetHierarchy(TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.indexpath = os.path.join(self.tempdir, 'foo')
        iconn = IndexerConnection(self.indexpath)
        for name in facets:
            iconn.add_field_action(name, FieldActions.INDEX_EXACT)
            iconn.add_field_action(name, FieldActions.STORE_CONTENT)
            iconn.add_field_action(name, FieldActions.FACET)
        for name, parents in facets.iteritems():
            for parent in parents:
                if parent:
                    iconn.add_subfacet(name, parent)
        for values in docvalues:
            doc = UnprocessedDocument()
            for name, value in values.iteritems():
                doc.fields.append(Field(name, value))
            iconn.add(doc)
        iconn.flush()
        iconn.close()
        self.sconn = SearchConnection(self.indexpath)
        self.faceted_query = self.sconn.query_facet('category', 'instrument')
        self.faceted_query2 = self.sconn.query_facet('colour', 'black')

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
        iconn = IndexerConnection(path)
        iconn.close()
        sconn = SearchConnection(path)
        sconn.close()

    def tearDown(self):
        self.sconn.close()
        shutil.rmtree(self.tempdir)

if __name__ == '__main__':
    main()
