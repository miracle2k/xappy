TARGETS = decreasing_weight_source.py, _decreasing_weight_source.so

all: $(TARGETS)

%.py, %_wrap.cxx: %.h
	swig -Wall -python -c++ -I../../libs/xapian-bindings/ -I../../libs/xapian-bindings/python/ -I../../libs/xapian-core/include/ $<

_%.so: %.cc %_wrap.cxx
	g++ -lxapian -I/usr/include/python2.5/ -shared -fPIC -o _decreasing_weight_source.so -I../../libs/build/xapian-bindings/python/ -I../../libs/xapian-core/include/ -I/usr/include/python2.5 $^ /usr/lib/python2.5/site-packages/xapian/_xapian.so

clean:
	rm -rf $(TARGETS)

%.cc: %.h