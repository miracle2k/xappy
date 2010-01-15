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

#define PROG_NAME "sortdatabase"
#define PROG_DESC "Sort a xapian database into a different order."

#include <xapian.h>

#include <iomanip>
#include <iostream>

#include <cerrno>
#include <cmath> // For log10().
#include <cstdio>
#include <cstdlib> // For exit().
#include <cstring> // For strcmp() and strrchr().
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <map>
#include <vector>

using namespace std;

#if defined __WIN32__ || defined __EMX__
#else
#define O_BINARY 0
#endif

// This ought to be enough for any of the conversions below.
#define BUFSIZE 100

#ifdef SNPRINTF
#define CONVERT_TO_STRING(FMT) \
    char buf[BUFSIZE];\
    int len = SNPRINTF(buf, BUFSIZE, (FMT), val);\
    if (len == -1 || len > BUFSIZE) return string(buf, BUFSIZE);\
    return string(buf, len);
#else
#define CONVERT_TO_STRING(FMT) \
    char buf[BUFSIZE];\
    buf[BUFSIZE - 1] = '\0';\
    sprintf(buf, (FMT), val);\
    if (buf[BUFSIZE - 1]) abort(); /* Uh-oh, buffer overrun */ \
    return string(buf);
#endif

string
om_tostring(Xapian::doccount val)
{
    CONVERT_TO_STRING("%d");
}

static void
show_usage(int rc)
{
    cout << "Usage: "PROG_NAME" SOURCE_DATABASE ORDER TMPDIR DESTINATION_DATABASE\n\n"
"ORDER is a file containing a list of document IDs: each document ID is "
"represented as a 4 byte, fixed width quantity.\n\n"
"Options:\n"
"  --help           display this help and exit\n"
"  --version        output version information and exit" << endl;
    exit(rc);
}

size_t
pread_from_file(int handle, off_t offset, unsigned char * p, size_t n, size_t min)
{
    size_t total = 0;
    while (n) {
	ssize_t c = pread(handle, p, n, offset);
	if (c <= 0) {
	    if (c == 0) {
		if (total >= min) break;
		throw Xapian::DatabaseError("Couldn't read enough (EOF)");
	    }
	    if (errno == EINTR) continue;
	    throw Xapian::DatabaseError("Error reading from file", errno);
	}
	offset += c;
	p += c;
	total += c;
	n -= c;
    }
    return total;
}

size_t
read_from_file(int handle, unsigned char * p, size_t n, size_t min)
{
    size_t total = 0;
    while (n) {
	ssize_t c = read(handle, p, n);
	if (c <= 0) {
	    if (c == 0) {
		if (total >= min) break;
		throw Xapian::DatabaseError("Couldn't read enough (EOF): read " + om_tostring(total) + " wanted " + om_tostring(min));
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
read_docid(int handle, Xapian::docid oldid)
{
    off_t offset = oldid * 4;
    unsigned char buf[4];
    size_t bytes = pread_from_file(handle, offset, buf, 4, 4);
    if (bytes != 4) {
	throw Xapian::DatabaseError("Error reading from file", errno);
    }
    return buf[3] << 24 | buf[2] << 16 | buf[1] << 8 | buf[0];
}

unsigned int
uint_from_file(int handle, bool * eof)
{
    unsigned char buf[4];
    size_t min = 0;
    if (eof == NULL) min = 4;
    size_t bytes = read_from_file(handle, buf, 4, min);
    if (bytes == 0) {
	if (eof != NULL) *eof = true;
	return 0;
    }
    if (bytes != 4) {
	throw Xapian::DatabaseError("Error reading from file", errno);
    }
    return buf[3] << 24 | buf[2] << 16 | buf[1] << 8 | buf[0];
}

std::string
uint_to_string(unsigned int id)
{
    unsigned char buf[4];
    buf[0] = id & 0xff;
    buf[1] = (id >> 8) & 0xff;
    buf[2] = (id >> 16) & 0xff;
    buf[3] = (id >> 24) & 0xff;
    return string((const char *)buf, 4);
}

unsigned int
write_docs_to_groups(std::string groupbase,
		     Xapian::doccount dbsize,
		     Xapian::doccount docs_read,
		     Xapian::doccount * docs_grouped,
		     size_t group_size,
		     const std::vector<std::pair<Xapian::docid, std::string> > & docs)
{
    int width = static_cast<int>(log10(double(dbsize))) + 1;
    std::map<Xapian::doccount, std::vector<std::pair<Xapian::docid, std::string> > > groups;
    std::vector<std::pair<Xapian::docid, std::string> >::const_iterator dociter;
    for (dociter = docs.begin(); dociter != docs.end(); ++dociter) {
	Xapian::doccount groupid = dociter->first / group_size;
	groups[groupid].push_back(*dociter);
    }

    if (groups.begin() == groups.end())
	return 0;

    std::map<Xapian::doccount, std::vector<std::pair<Xapian::docid, std::string> > >::const_iterator groupiter;
    for (groupiter = groups.begin(); groupiter != groups.end(); ++groupiter) {
	std::string num = om_tostring(groupiter->first);
	std::string grouppath = groupbase + num;
	int group_handle = ::open(grouppath.c_str(), O_WRONLY | O_BINARY | O_APPEND | O_CREAT, 0666);
	if (group_handle < 0) {
	    cerr << "Failed to open groupfile " << grouppath << ": " << strerror(errno) << "\n";
	    exit(1);
	}
	std::string buf;
	for (dociter = groupiter->second.begin();
	     dociter != groupiter->second.end();
	     ++dociter) {
	    buf.append(uint_to_string(dociter->first));
	    buf.append(uint_to_string(dociter->second.size()));
	    buf.append(dociter->second);

	    ++(*docs_grouped);
	    if (*docs_grouped <= 10 || (dbsize - *docs_grouped) % 13 == 0) {
		cout << '\r' << setw(width) << docs_read << " read, " <<
			*docs_grouped << " grouped, " <<
			"out of " << dbsize << flush;
	    }
	}
	write(group_handle, buf.data(), buf.size());
	::close(group_handle);
    }

    groupiter = groups.end();
    --groupiter;
    return (groupiter->first);
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
    if (argc != 5) show_usage(1);

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
    int order_handle = ::open(order, O_RDONLY | O_BINARY);
    if (order_handle < 0) {
	throw Xapian::DatabaseError("Couldn't open order file");
    }

    // Get the temporary dir.
    std::string tempdir = argv[3];

    std::string groupbase = tempdir + "/group_";

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
	Xapian::doccount dbsize = db_in.get_doccount();
	if (dbsize == 0) {
	    cout << leaf << ": empty!" << endl;
	} else {
	    // Calculate how many decimal digits there are in dbsize.
	    int width = static_cast<int>(log10(double(dbsize))) + 1;

	    Xapian::doccount docs_written = 0;
	    std::vector<std::pair<Xapian::docid, std::string> > docs;

	    // FIXME - the following should be configurable.
	    size_t flush_size = 100000; // Number of documents to read before sorting into groups.
	    size_t group_size = 100000; // Number of documents to put in each chunk (actually, size of the docid range used for each chunk)
	    docs.reserve(flush_size);

	    Xapian::PostingIterator dociter(db_in.postlist_begin(std::string()));

	    cout << leaf << "\n";
	    Xapian::doccount docs_read = 0;
	    Xapian::doccount docs_grouped = 0;
	    unsigned int maxgroup = 0;
	    unsigned int bufbytes = 0;
	    while (dociter != db_in.postlist_end(std::string())) {
		Xapian::docid oldid = *dociter;
		Xapian::Document doc(db_in.get_document(oldid));
		Xapian::docid newid = read_docid(order_handle, oldid);
		std::string serdoc = doc.serialise();
		docs.push_back(std::make_pair(newid, serdoc));
		bufbytes += serdoc.size();
		++docs_read;
		++dociter;
		if (docs_read <= 10 || (dbsize - docs_read) % 13 == 0) {
		    cout << '\r' << setw(width) << docs_read << " read, " <<
			    docs_grouped << " grouped, " <<
			    "out of " << dbsize <<
			    " (" << (bufbytes / 1024 / 1024) << "Mb buffered)     " << flush;
		}
		if (docs.size() == flush_size) {
		    unsigned int mg = write_docs_to_groups(groupbase, dbsize, docs_read, &docs_grouped, group_size, docs);
		    if (maxgroup < mg) maxgroup = mg;
		    docs.clear();
		    bufbytes = 0;
		}
	    }
	    {
		unsigned int mg = write_docs_to_groups(groupbase, dbsize, docs_read, &docs_grouped, group_size, docs);
		if (maxgroup < mg) maxgroup = mg;
		docs.clear();
		bufbytes = 0;
	    }
	    cout << '\n' << docs_grouped << " in " << (maxgroup + 1) << " groups\n";

	    // Read each group, sort the contents, and write them.
	    unsigned int groupnum;
	    for (groupnum = 0; groupnum <= maxgroup; ++groupnum) {
		std::string num = om_tostring(groupnum);
		std::string grouppath = groupbase + num;
		int group_handle = ::open(grouppath.c_str(), O_RDONLY | O_BINARY);
		if (group_handle < 0) {
		    //cerr << "Failed to open groupfile " << grouppath << ": " << strerror(errno) << "\n";
		    continue;
		}

		std::map<Xapian::docid, std::string> grouped_docs;
		while(1) {
		    bool eof = false;
		    Xapian::docid new_docid = uint_from_file(group_handle, &eof);
		    if (eof) break;
		    size_t docstr_len = uint_from_file(group_handle, NULL);
		    unsigned char buf[docstr_len];
		    size_t bytes = read_from_file(group_handle, buf, docstr_len, docstr_len);
		    if (bytes != docstr_len) {
			throw Xapian::DatabaseError("Couldn't read all of doc from file");
		    }
		    std::string docstr((char *)buf, docstr_len);
		    grouped_docs[new_docid] = docstr;
		}

		::close(group_handle);

		std::map<Xapian::docid, std::string>::const_iterator groupdocs;
		for (groupdocs = grouped_docs.begin();
		     groupdocs != grouped_docs.end();
		     ++groupdocs)
		{
		    db_out.replace_document(groupdocs->first, Xapian::Document::unserialise(groupdocs->second));
		    ++docs_written;
		    if (docs_written <= 10 || (dbsize - docs_written) % 13 == 0) {
			cout << '\r' << leaf << ": ";
			cout << setw(width) << docs_written << " written, out of " << dbsize << "                    " << flush;
		    }
		}
	    }

	    cout << endl;
	}

    	::close(order_handle);
    } catch(...) {
	::close(order_handle);
	throw;
    }

    cout << "Flushing document data..." << flush;
    db_out.flush();
    cout << " done." << endl;

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
