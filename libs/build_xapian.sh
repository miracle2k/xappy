#!/bin/sh -e

PYTHON="${PYTHON=python}"
instdir="`pwd`/install/usr"
pythonver=`$PYTHON -c 'import sys;print sys.version[:3]'`

[ ! -d build ] && mkdir build
cd build
[ ! -d xapian-core ] && mkdir xapian-core
[ ! -d xapian-bindings ] && mkdir xapian-bindings
[ ! -d xapian-extras ] && mkdir xapian-extras
[ ! -d xapian-extras-bindings ] && mkdir xapian-extras-bindings

cd xapian-core
../../xapian-core/configure --prefix=$instdir
make
make install

cd ../xapian-bindings
../../xapian-bindings/configure --with-python --prefix=$instdir XAPIAN_CONFIG="$instdir/bin/xapian-config" PYTHON="$PYTHON" PYTHON_LIB="$instdir/lib/python$pythonver/site-packages"
make
make install

cd ../xapian-extras
../../xapian-extras/configure --prefix=$instdir XAPIAN_CONFIG="$instdir/bin/xapian-config"
make
make install

cd ../xapian-extras-bindings
../../xapian-extras-bindings/configure --with-python --prefix=$instdir XAPIAN_CONFIG="$instdir/bin/xapian-config" PYTHON="$PYTHON" PYTHON_LIB="$instdir/lib/python$pythonver/site-packages"
make
make install
