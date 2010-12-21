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
import itertools

from xappytest import *
from xappy.fieldactions import FieldActions
import xappy.colour
import xapian

colourdata = [[(0, 0, 0), 10, 0.01], #black
              [(255, 255, 255), 5,  0.01 ], #white
              [(0, 0, 255), 3, 0.01], #blue
              [(0, 255, 0), 2, 0.01], #green
              [(255, 0, 0), 1, 0.01]  #red
              ]

'''
class ColourTermsTestCase(TestCase):

    def test_within_range(self):
        """ Ensure that all the colour from
        rgb data in the 0-256 range result in LAB colours in the
        expected range.

        """
        min_a = min_l = min_b = 100000
        max_l = max_a = max_b = 0
        for r in xrange(256):
            for g in xrange(256):
                for b in xrange(256):
                    lab = xappy.colour.rgb2bucket((r, g, b), 25)
                    min_l = min(lab[0], min_l)
                    min_a = min(lab[1], min_a)
                    min_b = min(lab[2], min_b)
                    max_l = max(lab[0], max_l)
                    max_a = max(lab[1], max_a)
                    max_b = max(lab[2], max_b)
                    self.assert_(xappy.colour.check_in_range(lab))
        print "%f %f %f %f %f %f" % (min_l, max_l, min_a, max_a, min_b, max_b)
'''
        
class ColourIndexingTestCase(TestCase):

    def pre_test(self):
        self.dbpath = os.path.join(self.tempdir, 'db')
        self.iconn = xappy.IndexerConnection(self.dbpath)

    def post_test(self):
        self.iconn.close()

    def test_basic_indexing(self):
        self.iconn.add_field_action('colour', xappy.FieldActions.COLOUR)
        doc = xappy.UnprocessedDocument()
        for col, freq, spread in colourdata:
            colourterm = xappy.colour.rgb2term(col, 50)
            doc.fields.append(xappy.Field('colour', colourterm, weight=freq))
        self.iconn.add(doc)

    def test_normalisation(self):
        self.iconn.add_field_action('colour', xappy.FieldActions.COLOUR)
        doc = xappy.UnprocessedDocument()
        for col, freq, spread in colourdata:
            colourterm =  xappy.colour.rgb2term(col, 50)
            doc.fields.append(xappy.Field('colour', colourterm, weight=freq))
        did = self.iconn.add(doc)
        doc = self.iconn.get_document(did)
        prefix = doc._fieldmappings.get_prefix('colour')
        cumfreq = 0
        count = 0
        for t in doc._doc.termlist():
            if t.term.startswith(prefix):
                cumfreq += t.wdf
                count += 1
        # we may have some rounding errors, so allow a bit of slack
        fudge = count * xapian.ColourWeight.trigger
        self.assert_(995 <= cumfreq-fudge <= 1005)

class ClusterTestCase(TestCase):

    def test_lab_clusters(self):
        # hopefully two clusters here
        clustercols = [(128, 128, 128),
                       (127, 127, 127),
                       (126, 126, 126),
                       (50, 200, 20)]

        lab_cols = itertools.imap(xappy.colour.rgb2lab, clustercols)

        clusters = xappy.colour.cluster_coords(lab_cols)
        self.assertEqual(2, len(list(clusters)))


class ColourSearchTestCase(TestCase):

    PALETTE_COLOURS = [
        'D5F0FE', 'D7E2FD', 'D3C8FC', 'E6C8FC', 'EED2DF', 'F5D9D7', 'F7E1D6',
        'FAECD5', 'FBF1D5', 'FEFCDD', 'F8FADC', 'E3EDD4', 'AEE2FD', 'B0C4FC',
        'A68BFA', 'CF90FB', 'E0A2BE', 'EEB4AD', 'F1C3AB', 'F5D8A9', 'F7E3AA',
        'FEFBBB', 'F3F7B9', 'D4E8B6', '88D4FB', '84A5FC', '794FF9', 'B957F9',
        'D2709B', 'E78B81', 'EAA47E', 'F0C57A', 'F4D77C', 'FDF999', 'ECF394',
        'BDDD8F', '6CC5FA', '5A86FA', '5532E6', 'A439EF', 'C73E77', 'E16252',
        'E5854C', 'ECB24A', 'F1CA4D', 'FDF775', 'E6EF6F', 'A9D267', '59A1D5',
        '3761FA', '4626AF', '842DB8', '9F315C', 'DF431D', 'E36A18', 'EAA925',
        'EFC62C', 'FEFC55', 'DDEB4C', '8DBA4C', '4C8BB1', '3156D1', '341F90',
        '6A259A', '84294F', 'C32A00', 'BE520F', 'C1831C', 'C49C22', 'F2EB35',
        'C6D037', '789B40', '3C6D8C', '2644A5', '2B1974', '541D79', '68203F',
        '9B2100', '96400C', '986816', '9A7B1B', 'C0BB2A', '9CA42B', '5E7932',
        '2B4E64', '1C3278', '1D1252', '3D1558', '4B182D', '701800', '6B2E08',
        '6E4B10', '6F5813', '8A851E', '70761F', '445824', '20394A', '142356',
        '160D3D', '2B0F3F', '360F20', '501000', '4F2206', '50370C', '50400E',
        '656116', '525615', '32401A', 'F7F7F7', 'FFFFFF', 'E4E4E4', 'CBCBCB',
        'AFAFAF', '909090', '717171', '525252', '363636', '1D1D1D', '090909',
        '000000']

    PALETTE_DIMENSIONS = (12, 10)

    STEP_COUNT = 25

    def pre_test(self):
        self.dbpath = os.path.join(self.tempdir, 'db')
        self.iconn = xappy.IndexerConnection(self.dbpath)
        self.iconn.add_field_action('colour', xappy.FieldActions.COLOUR)
        for col, freq, spread in colourdata:
            doc = xappy.UnprocessedDocument()
            colourterm = xappy.colour.rgb2term(col, 50)
            doc.fields.append(xappy.Field('colour', colourterm, weight=freq))
            self.iconn.add(doc)
        self.iconn.close()
        self.sconn = xappy.SearchConnection(self.dbpath)

    def post_test(self):
        self.sconn.close()

    def test_basic_search(self):
        """Ensure that query_colour can be called without generating an error.

        """
        xappy.colour.query_colour(self.sconn, 'colour', colourdata, 50)

    def test_correct_colour(self):
        """Check that correct document is found when querying for the
        colours that were supplied at indexing time.

        """

        prefix = self.sconn._field_mappings.get_prefix('colour')

        action_params = self.sconn._field_actions['colour']._actions[FieldActions.COLOUR][0]

        for colour, frequency, spread in colourdata:
            query = xappy.colour.query_colour(
                self.sconn, 'colour', [[colour, frequency, spread]], 50,
                clustering=True)
            results = self.sconn.search(query, 0, 10)
            r = results[0]
            d = self.sconn.get_document(r.id)
            terms = d._doc.termlist()
            terms = [x.term for x in terms if x.term.startswith(prefix)]
            terms = set(terms)
            colourterm = xappy.colour.rgb2term(colour, 50)
            rgb_term = prefix + colourterm
            self.assert_(rgb_term in terms)

    def test_palette_query(self):

        class Facet(object):
            def __init__(self, val, weight):
                self.val = val
                self.weight = weight
                self.fieldname = 'colour'

        facets = [
            #first cluster
            Facet('01', 2),
            Facet('02', 3),
            Facet('0D', 1),
            #should be a second cluster here
            Facet('40', 5),
            Facet('41', 4)
            ]
        q = xappy.colour.facet_palette_query(
            self.sconn, facets, self.PALETTE_COLOURS,
            self.PALETTE_DIMENSIONS, self.STEP_COUNT)
        qstring = str(q)
        self.assertEqual(qstring.count('AND'), 1)

if __name__ == '__main__':
    main()
