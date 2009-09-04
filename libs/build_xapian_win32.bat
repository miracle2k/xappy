@echo off
rem  
rem Build script for Xapian on Win32 using MSVC
rem This replicates the function of build_xapian.sh for those running Win32 and MSVC and without a BASH shell
rem .Remember to run get_xapian.py first!

rem Requirements:
rem    MSVC Express Edition 2005 (start the command line prompt)
rem    Python 2.4 - 2.6 (this must be on your Path, after starting the above)

rem Commands:
rem     Specify the Python version as 'XX' i..e for Python 2.5 run 'build_xapian_win32 25'

if (%1) == () goto nover
goto 1
:nover
echo Please specify a version of Python, i.e. "24" for version 2.4
goto:EOF

:1
cd xapian-core\win32
nmake COPYMAKFILES
if ERRORLEVEL 1 goto f1
nmake clean
if ERRORLEVEL 1 goto f1
nmake check
if ERRORLEVEL 1 goto f1
goto 2
:f1
echo ERROR failed to build Xapian core
goto:EOF

:2
cd ..\..\xapian-bindings\python
nmake PYTHON_VER=%1 CLEAN
if ERRORLEVEL 1 goto f2
nmake PYTHON_VER=%1 DIST
if ERRORLEVEL 1 goto f2
goto 3
:f2
echo ERROR failed to build Xapian Python bindings
goto:EOF

:3

echo Done.

rem ------- We don't support these under Windows yet -------
rem cd ../xapian-extras
rem ../../xapian-extras/configure --prefix=$instdir XAPIAN_CONFIG="$instdir/bin/xapian-config-1.1"
rem make
rem make install

rem cd ../xapian-extras-bindings
rem ../../xapian-extras-bindings/configure --with-python --prefix=$instdir XAPIAN_CONFIG="$instdir/bin/xapian-config-1.1" PYTHON="$PYTHON" PYTHON_LIB="$instdir/lib/python$pythonver/site-packages"
rem make
rem make install
rem ------- We don't support these under Windows yet -------
