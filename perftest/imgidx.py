import os
import xappy

def main(index, photodir, terms=True):
    terms = bool(terms)
    iconn = xappy.IndexerConnection(index)
    iconn.add_field_action('img', xappy.FieldActions.IMGSEEK, terms=terms)
    iconn.add_field_action('file', xappy.FieldActions.STORE_CONTENT)
    count = 0
    for p, n, f in os.walk(photodir):
        for fname in f:
            path = os.path.abspath(os.path.join(p, fname))
            ext = os.path.splitext(path)[1].upper()[1:]
            if ext in ("JPG", "JPEG"):
                doc = xappy.UnprocessedDocument()
                doc.fields.append(xappy.Field('img', path))
                doc.fields.append(xappy.Field('file', path))
                try:
                    i = iconn.add(doc)
                except:
                    print "problem with: ", path
                count += 1
                if count % 1000 == 0:
                    print count
    return iconn

if __name__ == "__main__":
    import sys
    import time
    start_time = time.clock()
    print "starting clock: ", start_time
    iconn = main(*sys.argv[1:])
    end_time = time.clock()
    print "ending clock: ", end_time, " elapsed: ", end_time - start_time, " doc_count: ", iconn.get_doccount()
    
    
