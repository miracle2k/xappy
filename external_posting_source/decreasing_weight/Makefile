all: decreasing_weight_source.py, _decreasing_weight_source.so

decreasing_weight_source.py, decreasing_weight_source_wrap.cxx: decreasing_weight_source.h
	swig -Wall -python -c++ -I../../libs/xapian-bindings/ -I../../libs/xapian-bindings/python/ -I../../libs/xapian-core/include/ decreasing_weight_source.h

_decreasing_weight_source.so: decreasing_weight_source.h decreasing_weight_source.cc decreasing_weight_source_wrap.cxx
	g++ -lxapian -I/usr/include/python2.5/ -shared -fPIC -o _decreasing_weight_source.so -I../../libs/build/xapian-bindings/python/ -I../../libs/xapian-core/include/ -I/usr/include/python2.5 decreasing_weight_source.cc decreasing_weight_source_wrap.cxx /usr/lib/python2.5/site-packages/xapian/_xapian.so

clean:
	rm -rf _decreasing_weight_source.so decreasing_weight_source_wrap.cxx decreasing_weight_source.py