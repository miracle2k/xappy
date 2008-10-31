/** mypostingsource.cc: Example posting source for python wrapping.
 */

#ifdef SWIG
%module mypostingsource
%import xapian.i
%{
#include "xapian.h"
namespace Xapian {
    void SetPythonException();
}
#include "mypostingsource.h"
%}
#endif

#include <xapian/postingsource.h>
#include <vector>

// Implementation of a custom posting source.
class MyPostingSource : public Xapian::PostingSource {
	std::vector<Xapian::docid> docs;
	std::vector<Xapian::docid>::const_iterator it;
	bool started;

    public:
	MyPostingSource()
		: docs(), it(), started(false)
	{}

	void add_doc(int docid) {
	    docs.push_back(docid);
	}

	Xapian::doccount get_termfreq_min() const { return docs.size(); }
	Xapian::doccount get_termfreq_est() const { return docs.size(); }
	Xapian::doccount get_termfreq_max() const { return docs.size(); }

	void next(Xapian::weight min_wt)
	{
	    if (!started) {
		it = docs.begin();
		started = true;
	    } else {
		++it;
	    }
	}

	bool at_end() const
	{
	    if (!started) return false;
	    return (it == docs.end());
	}

	Xapian::docid get_docid() const
	{
	    return *it;
	}

	void reset()
	{
	    started = false;
	}
};
