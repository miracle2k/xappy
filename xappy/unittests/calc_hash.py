# Copyright (C) 2009 Pablo Hoffman
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

class TestCalcHash(TestCase):

    def pre_test(self):
        self.indexpath = os.path.join(self.tempdir, 'foo')
        self.iconn = xappy.IndexerConnection(self.indexpath)
        self.iconn.add_field_action('a', xappy.FieldActions.INDEX_FREETEXT)
        self.iconn.add_field_action('b', xappy.FieldActions.INDEX_EXACT)
        self.iconn.add_field_action('c', xappy.FieldActions.STORE_CONTENT)
        self.iconn.add_field_action('d', xappy.FieldActions.SORTABLE)
        self.iconn.add_field_action('hash', xappy.FieldActions.SORTABLE)

    def post_test(self):
        self.iconn.close()

    def test_calc_hash_1(self):
        doc = xappy.UnprocessedDocument("1")
        doc.fields.append(xappy.Field('a', 'freetext'))
        pdoc1 = self.iconn.process(doc)

        doc = xappy.UnprocessedDocument("1")
        doc.fields.append(xappy.Field('a', 'freetext'))
        pdoc2 = self.iconn.process(doc)

        pdoc3 = self.iconn.process(doc)
        pdoc3.add_term('a', 'some', 1)

        doc.id = "2"
        pdoc4 = self.iconn.process(doc)

        pdoc5 = self.iconn.process(doc)
        pdoc5.add_term('a', 'some', 1)
        pdoc5.remove_term('a', 'some')

        self.assertEqual(len(pdoc1.calc_hash()), 40)
        self.assertEqual(pdoc1.calc_hash(), pdoc2.calc_hash())
        self.assertNotEqual(pdoc1.calc_hash(), pdoc3.calc_hash())
        self.assertNotEqual(pdoc1.calc_hash(), pdoc4.calc_hash())
        self.assertEqual(pdoc4.calc_hash(), pdoc5.calc_hash())

    def test_calc_hash_2(self):
        doc = xappy.UnprocessedDocument("1")
        doc.fields.append(xappy.Field('a', 'freetext'))
        doc.fields.append(xappy.Field('b', 'exact'))
        doc.fields.append(xappy.Field('c', 'stored'))
        doc.fields.append(xappy.Field('d', 'sortable'))

        pdoc1 = self.iconn.process(doc)
        doc.fields.pop()
        pdoc2 = self.iconn.process(doc)
        doc.fields.append(xappy.Field('d', 'sortable'))
        pdoc3 = self.iconn.process(doc)

        self.assertNotEqual(pdoc1.calc_hash(), pdoc2.calc_hash())
        self.assertEqual(pdoc1.calc_hash(), pdoc3.calc_hash())

    def test_calc_hash_groups(self):
        doc = xappy.UnprocessedDocument("1")
        doc.fields.append(xappy.Field('a', 'freetext'))
        doc.fields.append(xappy.Field('c', 'stored1'))
        doc.fields.append(xappy.Field('c', 'stored2'))

        pdoc1 = self.iconn.process(doc)

        doc.fields = doc.fields[:1]
        doc.fields.append(xappy.FieldGroup([xappy.Field('c', 'stored1'),
                                            xappy.Field('c', 'stored2')]))
        pdoc2 = self.iconn.process(doc)

        self.assertEqual(pdoc1.data, pdoc2.data)
        self.assertNotEqual(pdoc1.calc_hash(), pdoc2.calc_hash())

    def test_calc_hash_stored(self):
        doc = xappy.UnprocessedDocument("1")
        doc.fields.append(xappy.Field('a', 'freetext'))
        doc.fields.append(xappy.Field('c', 'stored'))
        pdoc1 = self.iconn.process(doc)
        hash1 = pdoc1.calc_hash()
        pdoc1.data['hash'] = hash1
        self.iconn.add(pdoc1)
        self.iconn.flush()

        pdoc2 = self.iconn.get_document("1")
        hash2 = pdoc2.data.pop('hash')
        hash3 = pdoc2.calc_hash()

        self.assertEqual(hash1, hash2)
        self.assertEqual(hash2, hash3)

if __name__ == '__main__':
    main()
