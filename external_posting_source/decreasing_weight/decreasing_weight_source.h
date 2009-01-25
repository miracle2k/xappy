#ifdef SWIG
%module decreasing_weight_source
%import xapian.i

%{
#include "xapian.h"
namespace Xapian {
    void SetPythonException();
}
#include "decreasing_weight_source.h"
%}
%feature("notabstract") DecreasingWeightSource;
#endif

#include <xapian/postingsource.h>
#include <vector>

/* Reads weights from the filename supplied to the constructor.  The
   file must contain 32 bit floating point values, one for each
   document in a xapian database, in document id order. The weights
   must be decreasing.

   It is assumed that the database has no gaps in its document ids.

   See ../sortdatabase/ for creating an appropriate database.
 */

class DecreasingWeightSource : public Xapian::PostingSource {
	std::vector<Xapian::weight> weights;
	std::vector<Xapian::weight>::const_iterator pos;
	bool started;
        bool finished;

    public:
	DecreasingWeightSource(char *);
	Xapian::doccount get_termfreq_min() const;
	Xapian::doccount get_termfreq_est() const;
	Xapian::doccount get_termfreq_max() const;
        Xapian::weight get_maxweight() const;
	void reset();
	void next(Xapian::weight);
        void skip_to(Xapian::docid, Xapian::weight);
	bool at_end() const;
	Xapian::docid get_docid() const;
        Xapian::weight get_weight() const;
};
