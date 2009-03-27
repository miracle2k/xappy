#!/bin/sh -e

PYTHON="${PYTHON=python}"
instdir="`pwd`/install/usr"
pythonver=`$PYTHON -c 'import sys;print sys.version[:3]'`

mkdir build
cd build
mkdir xapian-core
mkdir xapian-bindings
mkdir xapian-extras
mkdir xapian-extras-bindings

cd xapian-core
../../xapian-core/configure --prefix=$instdir
make
make install

cd ../xapian-bindings
../../xapian-bindings/configure --with-python --prefix=$instdir XAPIAN_CONFIG="$instdir/bin/xapian-config-1.1" PYTHON="$PYTHON" PYTHON_LIB="$instdir/lib/python$pythonver/site-packages"
make
make install

cd ../xapian-extras
../../xapian-extras/configure --prefix=$instdir XAPIAN_CONFIG="$instdir/bin/xapian-config-1.1"
make
make install

cd ../xapian-extras-bindings
../../xapian-extras-bindings/configure --with-python --prefix=$instdir XAPIAN_CONFIG="$instdir/bin/xapian-config-1.1" PYTHON="$PYTHON" PYTHON_LIB="$instdir/lib/python$pythonver/site-packages"
make
make install
