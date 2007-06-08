#!/usr/bin/env python

import sys
import os

def _setup_path():
    """Set up sys.path to allow us to import secore when run uninstalled.

    """
    abspath = os.path.abspath(__file__)
    dirname = os.path.dirname(abspath)
    dirname, ourdir = os.path.split(dirname)
    dirname, parentdir = os.path.split(dirname)
    if (parentdir, ourdir) == ('secore', 'examples'):
        sys.path.insert(0, '..')

_setup_path()
import secore

def create_index(dbpath):
    """Create a new index, and set up its field structure.

    """
    iconn = secore.IndexerConnection(dbpath)

    iconn.add_field_action('path', secore.FieldActions.STORE_CONTENT)
    iconn.add_field_action('path', secore.FieldActions.INDEX_EXACT)
    iconn.add_field_action('pathcomponent', secore.FieldActions.INDEX_EXACT)
    iconn.add_field_action('text', secore.FieldActions.STORE_CONTENT)
    iconn.add_field_action('text', secore.FieldActions.INDEX_FREETEXT, language='en')

    iconn.close()

def open_index(dbpath):
    """Open an existing index.

    """
    return secore.IndexerConnection(dbpath)

def canonical_path(path):
    """Convert a path to a canonical form."""
    path = os.path.realpath(path)
    path = os.path.normpath(path)
    path = os.path.normcase(path)
    return path

def index_content(doc, filepath):
    """Index the content of the file."""
    fd = open(filepath)
    contents = fd.read()
    fd.close()
    try:
        contents = unicode(contents)
    except UnicodeDecodeError:
        return
    doc.fields.append(secore.Field('text', contents))

def index_file(iconn, filepath):
    """Index a file."""
    filepath = canonical_path(filepath)
    doc = secore.UnprocessedDocument()
    doc.fields.append(secore.Field('path', filepath))

    components = filepath
    while True:
        components, dirname = os.path.split(components)
        if len(dirname) == 0 or components == '/':
            break
        doc.fields.append(secore.Field('pathcomponent', components))

    index_content(doc, filepath)
    iconn.add(doc)

    return 1

def index_path(iconn, docpath):
    """Index a path."""
    count = 0
    for dirpath, dirnames, filenames in os.walk(docpath):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            index_file(iconn, filepath)
            count += 1
    return count

def main(argv):
    dbpath = 'foo'
    docpath = '/usr/share/doc/python2.5'
    create_index(dbpath)
    iconn = open_index(dbpath)
    count = index_path(iconn, docpath)
    print "Indexed %d documents." % count

if __name__ == '__main__':
    main(sys.argv)
