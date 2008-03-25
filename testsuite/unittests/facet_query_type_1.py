from unittest import TestCase, main
import tempfile, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from xappy.indexerconnection import *
from xappy.fieldactions import *
from xappy.searchconnection import *

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

class TestFacetHierarchy(TestCase):
    def setUp(self):
        tempdir = tempfile.mkdtemp()
        indexpath = os.path.join(tempdir, 'foo')
        self.iconn = IndexerConnection(indexpath)
        for name in facets:
            self.iconn.add_field_action(name, FieldActions.INDEX_EXACT)
            self.iconn.add_field_action(name, FieldActions.STORE_CONTENT)
            self.iconn.add_field_action(name, FieldActions.FACET)
        for values in docvalues:
            doc = UnprocessedDocument()
            for name, value in values.iteritems():
                doc.fields.append(Field(name, value))
            self.iconn.add(doc)
        self.iconn.set_facet_for_query_type('type1', 'colour', self.iconn.FacetQueryType_Preferred)
        self.iconn.set_facet_for_query_type('type1', 'colour', self.iconn.FacetQueryType_Never)
        self.iconn.set_facet_for_query_type('type2', 'colour', self.iconn.FacetQueryType_Preferred)
        self.iconn.set_facet_for_query_type('type2', 'make', self.iconn.FacetQueryType_Preferred)
        self.iconn.set_facet_for_query_type('type3', 'colour', self.iconn.FacetQueryType_Preferred)
        self.iconn.set_facet_for_query_type('type3', 'colour', None)
        self.iconn.flush()
        self.sconn = SearchConnection(indexpath)

    def _get_facets(self, query, maxfacets=100, query_type=None):
        results = self.sconn.search(query, 0, 10, getfacets=True, query_type=query_type)
        tuples = results.get_suggested_facets(maxfacets=maxfacets)
        return set([tuple[0] for tuple in tuples])

    def test_facet_query_types(self):
        # Test facets have the right preference for query types
        assert self.iconn.get_facets_for_query_type('type1', self.iconn.FacetQueryType_Never) == set(['colour'])
        assert self.iconn.get_facets_for_query_type('type1', self.iconn.FacetQueryType_Preferred) == set()
        assert self.iconn.get_facets_for_query_type('type2', self.iconn.FacetQueryType_Preferred) == set(['colour', 'make'])
        assert self.iconn.get_facets_for_query_type('type3', self.iconn.FacetQueryType_Preferred) == None
        assert self.iconn.get_facets_for_query_type('not_a_type', self.iconn.FacetQueryType_Preferred) == None

    def test_facet_search(self):
        query = self.sconn.query_facet('category', 'instrument')
        # Test suggested facets are what we expect
        assert self._get_facets(query) == set(['colour', 'type', 'make', 'strings']);
        # Test 'colour' not suggested for query_type 'type1'
        assert self._get_facets(query, query_type='type1') == set(['type', 'make', 'strings']);
        # Test 'colour' and 'make' preferred for query_type 'type2'
        assert self._get_facets(query, query_type='type2', maxfacets=2) == set(['colour', 'make']);

    def tearDown(self):
        self.iconn.close()
        self.sconn.close()

if __name__ == '__main__':
    main()
