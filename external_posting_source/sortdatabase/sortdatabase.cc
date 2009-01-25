/** @file sortdatabase.cc
 * @brief Sort a database into a different order.
 */
/* Copyright (C) 2006,2007,2008 Olly Betts
 * Copyright (C) 2009 Lemur Consulting Ltd
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
 */

#include <xapian.h>

#include <iomanip>
#include <iostream>

#include <cerrno>
#include <cmath> // For log10().
#include <cstdlib> // For exit().
#include <cstring> // For strcmp() and strrchr().
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

using namespace std;

#define PROG_NAME "sortdatabase"
#define PROG_DESC "Sort a xapian database into a different order."

static void
show_usage(int rc)
{
    cout << "Usage: "PROG_NAME" SOURCE_DATABASE ORDER DESTINATION_DATABASE\n\n"
"ORDER is a file containing a list of document IDs: each document ID is "
"represented as a 4 byte, fixed width quantity.\n\n"
"Options:\n"
"  --help           display this help and exit\n"
"  --version        output version information and exit" << endl;
    exit(rc);
}

size_t
read_from_file(int handle, char * p, size_t n, size_t min)
{
    size_t total = 0;
    while (n) {
	ssize_t c = read(handle, p, n);
	if (c <= 0) {
	    if (c == 0) {
		if (total >= min) break;
		throw Xapian::DatabaseError("Couldn't read enough (EOF)");
	    }
	    if (errno == EINTR) continue;
	    throw Xapian::DatabaseError("Error reading from file", errno);
	}
	p += c;
	total += c;
	n -= c;
    }
    return total;
}

Xapian::docid
read_next_docid(int handle)
{
    int32 id;
    size_t bytes = read_from_file(handle, reinterpret_cast<char*>(&id), 4, 4);
    if (bytes != 4) {
	throw Xapian::DatabaseError("Error reading from file", errno);
    }
    return id;
}

int
main(int argc, char **argv)
try {
    if (argc > 1 && argv[1][0] == '-') {
	if (strcmp(argv[1], "--help") == 0) {
	    cout << PROG_NAME" - "PROG_DESC"\n\n";
	    show_usage(0);
	}
	if (strcmp(argv[1], "--version") == 0) {
	    cout << PROG_NAME" - xapian-core " << Xapian::version_string() << endl;
	    exit(0);
	}
    }

    // We expect exactly three arguments: the source database path followed by
    // the order file, followed by the destination database path.
    if (argc != 4) show_usage(1);

    // Create the destination database, using DB_CREATE so that we don't
    // try to overwrite or update an existing database in case the user
    // got the command line argument order wrong.
    const char *dest = argv[argc - 1];
    Xapian::WritableDatabase db_out(dest, Xapian::DB_CREATE);

    char * src = argv[1];
    if (*src) {
	// Remove any trailing directory separator.
	char & ch = src[strlen(src) - 1];
	if (ch == '/' || ch == '\\') ch = '\0';
    }

    // Open the order file.
    char * order = argv[2];
#if defined __WIN32__ || defined __EMX__
#else
#define O_BINARY 0
#endif
    int order_handle = ::open(order, O_RDONLY | O_BINARY);
    if (order_handle < 0) {
	throw Xapian::DatabaseError("Couldn't open order file");
    }

    off_t order_size;
    {
	struct stat buf;
	if (fstat(order_handle, &buf)) {
	    throw Xapian::DatabaseError("Couldn't stat the order file", errno);
	}
	order_size = buf.st_size;
    }

    Xapian::Database db_in;
    try {
	// Open the source database.
	db_in = Xapian::Database(src);

	// Find the leaf-name of the database path for reporting progress.
	const char * leaf = strrchr(src, '/');
#if defined __WIN32__ || defined __EMX__
	if (!leaf) leaf = strrchr(src, '\\');
#endif
	if (leaf) ++leaf; else leaf = src;

	// Iterate over all the documents in db_in, copying each to db_out.
	Xapian::doccount dbsize = order_size / 4;
	if (dbsize == 0) {
	    cout << leaf << ": empty!" << endl;
	} else {
	    // Calculate how many decimal digits there are in dbsize.
	    int width = static_cast<int>(log10(double(dbsize))) + 1;

	    Xapian::doccount c = 0;
	    while (c < dbsize) {
		Xapian::docid docid = read_next_docid(order_handle);
		db_out.add_document(db_in.get_document(docid));

		// Update for the first 10, and then every 13th document
		// counting back from the end (this means that all the
		// digits "rotate" and the counter ends up on the exact
		// total.
		++c;
		if (c <= 10 || (dbsize - c) % 13 == 0) {
		    cout << '\r' << leaf << ": ";
		    cout << setw(width) << c << '/' << dbsize << flush;
		}
	    }

	    cout << endl;
	}

    	::close(order_handle);
    } catch(...) {
	::close(order_handle);
	throw;
    }

    cout << "Copying spelling data..." << flush;
    Xapian::TermIterator spellword = db_in.spellings_begin();
    while (spellword != db_in.spellings_end()) {
	db_out.add_spelling(*spellword, spellword.get_termfreq());
	++spellword;
    }
    cout << " done." << endl;

    cout << "Copying synonym data..." << flush;
    Xapian::TermIterator synkey = db_in.synonym_keys_begin();
    while (synkey != db_in.synonym_keys_end()) {
	string key = *synkey;
	Xapian::TermIterator syn = db_in.synonyms_begin(key);
	while (syn != db_in.synonyms_end(key)) {
	    db_out.add_synonym(key, *syn);
	    ++syn;
	}
	++synkey;
    }
    cout << " done." << endl;

    cout << "Copying user metadata..." << flush;
    Xapian::TermIterator metakey = db_in.metadata_keys_begin();
    while (metakey != db_in.metadata_keys_end()) {
	string key = *metakey;
	db_out.set_metadata(key, db_in.get_metadata(key));
	++metakey;
    }
    cout << " done." << endl;

    cout << "Flushing..." << flush;
    // Flush explicitly so that any error is reported.
    db_out.flush();
    cout << " done." << endl;
} catch (const Xapian::Error & e) {
    cerr << '\n' << argv[0] << ": " << e.get_description() << endl;
    exit(1);
}
