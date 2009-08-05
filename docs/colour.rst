Colour Searching in Xappy
=========================

Xappy has some features to assist with finding documents close to
given colour. There are three aspects of this support:

  - The code in the module xappy.colour generates terms suitable for
    passing to the fields marked with FieldActions.COLOUR.

  - At indexing time FieldActions.COLOUR causes weights for terms to
    be treated specially, on the assumption that weights represent
    frequency of occurence of colours.

  - At query time a custom weighting scheme ensures that frequencies
    of colours in the document are treated appropriately.

Indexing Time
-------------

A field marked with FieldActions.COLOUR accepts 
