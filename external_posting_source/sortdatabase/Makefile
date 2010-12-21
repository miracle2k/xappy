
all: sortdatabase

sortdatabase.lo: sortdatabase.cc
	libtool --mode=compile g++ `xapian-config --cxxflags` $(CFLAGS) $? -c -o $@

sortdatabase: sortdatabase.lo
	libtool --mode=link g++ `xapian-config --ltlibs` $? -o $@

.PHONY:clean

clean:
	rm -rf sortdatabase sortdatabase.o sortdatabase.lo .libs
