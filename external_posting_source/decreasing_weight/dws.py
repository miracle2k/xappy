
import os

import xappy
import xapian
import decreasing_weight_source as _dws

_WEIGHTS_FILE_NAME = "weights.dat"

class _dws_mixin(object):
    
    def __init__(self, conn):
        super(_dws_mixin, self).__init__(os.path.join(conn._indexpath,
                                                      _WEIGHTS_FILE_NAME))

class Vector_DWS(_dws_mixin, _dws.DecreasingWeightSource):
    pass

class File_DWS(_dws_mixin, _dws.FDecreasingWeightSource):
    pass

class Vector_DWS_Cache(object):

    def __init__(self):
        self.cache = {}

    def get_Vector_DWS_for_conn(self, conn):
        cached = self.cache.get(conn)

        if cached:
            source = cached
        else:
            source = Vector_DWS(conn)
            self.cache[conn] = source

        source.reset()
        return source

FILE, VECTOR, CACHED_VECTOR = range(3)
_VCACHE = Vector_DWS_Cache()

def make_page_rank_query(conn, source_type):
    if source_type == FILE:
        source = File_DWS(conn)
    elif source_type == VECTOR:
        source = Vector_DWS(conn)
    elif source_type == CACHED_VECTOR:
        source = _VCACHE.get_Vector_DWS_for_conn(conn)
    else:
        raise ValueError("Bad source_type %s for make_page_rank_query"
                         % string(source_type))

    return xappy.Query(xapian.Query(source),
                       _refs = [source],
                       _conn = conn)

    

    
        


