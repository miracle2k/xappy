#!/bin/sh -e

instdir="`pwd`/install/usr"
pythonver=`python -c 'import sys;print sys.version[:3]'`

mkdir build
cd build
mkdir xapian-core
mkdir xapian-bindings
mkdir xapian-extras
mkdir xapian-extras-bindings

cd xapian-core
../../xapian-core/configure --prefix=$instdir --program-suffix=
make
make install

cd ../xapian-bindings
../../xapian-bindings/configure --with-python --prefix=$instdir XAPIAN_CONFIG="$instdir/bin/xapian-config" PYTHON_LIB="$instdir/lib/python$pythonver/site-packages"
make
make install

cd ../xapian-extras
../../xapian-extras/configure --prefix=$instdir XAPIAN_CONFIG="$instdir/bin/xapian-config"
make
make install

cd ../xapian-extras-bindings
../../xapian-extras-bindings/configure --with-python --prefix=$instdir XAPIAN_CONFIG="$instdir/bin/xapian-config" PYTHON_LIB="$instdir/lib/python$pythonver/site-packages"
make
make install
