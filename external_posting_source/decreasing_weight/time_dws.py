import timeit

import dws

def do_time(index, st, res_count, warm = False):
    setup_string = """
import dws
import xappy
conn = xappy.SearchConnection('%s')
st = %d
    """ % (index, st)
    if warm:
        setup_string = setup_string + """\

dws.make_page_rank_query(conn, %d)
""" % st
    execute_string = """
query = dws.make_page_rank_query(conn, st)
res = conn.search(query, 0, %d)
list(res)
    """ % res_count
    timer = timeit.Timer(execute_string, setup_string)
    try:
        time = timer.timeit(10)
        print st, warm, time, res_count
    except:
        timer.print_exc()
    
def main(index):
    for st in (dws.FILE, dws.VECTOR, dws.CACHED_VECTOR):
        do_time(index, st, 100)
        do_time(index, st, 100, True)
        do_time(index, st, 10000)
        do_time(index, st, 10000, True)


if __name__ == "__main__":
    import sys
    main(sys.argv[1])
