Weighting parameters
====================

.. contents:: Table of contents

The default weighting scheme, used for calculating weights when searching
through ``INDEX_FREETEXT`` fields, is called the "BM25" weighting scheme.  This
has several parameters controlling the relative importance of various
statistics.  There are also some extra parameters available which aren't in the
"standard" BM25 definition, which allow further tweaks to the weights.

The parameters can be set using the ``weight_params`` parameter to
SearchConnection::search()

k1
--

Governs the importance of within document frequency.
Must be >= 0.  0 means ignore wdf.  Default is 1.

k2
--

Compensation factor for the high wdf values in
large documents.  Must be >= 0.  0 means no
compensation.  Default is 0.

k3
--

Governs the importance of within query frequency.
Must be >= 0.  0 means ignore wqf.  Default is 1.

b
-

Relative importance of within document frequency and
document length.  Must be >= 0 and <= 1.  Default
is 0.5.

min_normlen
-----------

Specifies a cutoff on the minimum value that
can be used for a normalised document length -
smaller values will be forced up to this cutoff.
This prevents very small documents getting a huge
bonus weight.  Default is 0.5.

