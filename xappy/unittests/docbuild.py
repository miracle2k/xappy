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

class TestDocBuild(TestCase):
    def test_build_doc_fields(self):
        """Test buiding a document up using various different methods.

        """
        doc = xappy.UnprocessedDocument()
        doc.append('a', 'Africa America', 'Brown Bible')
        doc.append('b', 'Andes America')
        doc.append(xappy.Field('c', 'Arctic America'))
        doc.append(xappy.Field('d', 'Australia', weight=2.0))
        self.assertRaises(TypeError, doc.extend, ['e', '1.0'])
        doc.extend([('e', '2.0')])
        doc.extend([('f', 'Ave'), ('g', 'Atlantic')])
        doc.append('h', '1.0')
        doc.append('i', 'Apt America')

        self.assertEqual(repr(doc.fields),
            "[Field('a', 'Africa America', 'Brown Bible'), "
            "Field('b', 'Andes America'), "
            "Field('c', 'Arctic America'), "
            "Field('d', 'Australia', weight=2.0), "
            "Field('e', '2.0'), "
            "Field('f', 'Ave'), "
            "Field('g', 'Atlantic'), "
            "Field('h', '1.0'), "
            "Field('i', 'Apt America')]")

    def test_build_doc_fieldgroups(self):
        """Test buiding a document up using FieldGroups.

        """
        doc = xappy.UnprocessedDocument()
        doc.append('a', 'Africa America', 'Brown Bible')
        doc.append(xappy.Field('b', 'Andes America'))
        doc.append('c', 'Arctic America')
        doc.append(xappy.Field('d', 'Australia', weight=2.0))
        doc.extend([('e', '2.0')])
        doc.append([('f', 'Ave'), ('g', 'Atlantic')])
        doc.extend([('h', '1.0'), ('i', 'Apt America')])

        self.assertEqual(repr(doc.fields),
            "[Field('a', 'Africa America', 'Brown Bible'), "
            "Field('b', 'Andes America'), "
            "Field('c', 'Arctic America'), "
            "Field('d', 'Australia', weight=2.0), "
            "Field('e', '2.0'), "
            "FieldGroup(Field('f', 'Ave'), "
            "Field('g', 'Atlantic')), "
            "Field('h', '1.0'), "
            "Field('i', 'Apt America')]")


if __name__ == '__main__':
    main()
