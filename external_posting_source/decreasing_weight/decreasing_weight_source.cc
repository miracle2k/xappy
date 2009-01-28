#include <iostream>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include "decreasing_weight_source.h"

// data type of the binary data in the weights file.  I'm not sure
// whether we can be sure this is 32 bit. Normally it is so.
typedef float weight_data_type;

template<typename T, typename S>
void copy_binary_data_from_file(char* filename, std::vector<S>& dest) {
  /* append data to the provided vector with elements of type S, by
     reading the binary data (of type T) from the supplied file. T
     must be castable to S. */
  T val;
  std::ifstream bin(filename);
  if (bin.is_open()) {
    while (!bin.eof()) {
      bin.read(reinterpret_cast<char*>(&val), sizeof(T));
      dest.push_back(static_cast<S>(val));
    }
    bin.close();
  } else {
    throw std::invalid_argument(filename);
  }
}

DecreasingWeightSource::DecreasingWeightSource(char * weight_filename) {
  started = false;
  finished = false;
  copy_binary_data_from_file<weight_data_type, Xapian::weight>(weight_filename, weights);
  reset();
}

Xapian::doccount
DecreasingWeightSource::get_termfreq_min() const{
  return weights.size();
}

Xapian::doccount
DecreasingWeightSource::get_termfreq_est() const{
  return weights.size();
}

Xapian::doccount
DecreasingWeightSource::get_termfreq_max() const{
  return weights.size();
}

Xapian::weight
DecreasingWeightSource::get_maxweight() const {
  return *pos;
}

void
DecreasingWeightSource::reset() {
  pos = weights.begin();
  started = false;
  finished = false;
}

void
DecreasingWeightSource::next(Xapian::weight min_weight) {
  if (!started)
    started = true;
  else {
    if (!finished) 
      ++pos;

    if ((pos >= weights.end()) || (*pos < min_weight) )
      finished = true;
  }
}

void 
DecreasingWeightSource::skip_to(Xapian::docid did, Xapian::weight min_weight) {
  started = true;
  if (!finished) {
    pos = weights.begin() + (did - 1);
    if ( pos >= weights.end() || *pos < min_weight) 
      finished = true;
  }
}

bool
DecreasingWeightSource:: at_end() const {
  return finished;
}

Xapian::docid
DecreasingWeightSource::get_docid() const {
  return started ? (pos - weights.begin()) + 1 : 0;
}

Xapian::weight
DecreasingWeightSource::get_weight() const {
  // can we be called before started or after finished? if so does it
  // matter what we return?
  return *pos;
}


const size_t increment = sizeof(weight_data_type);

FDecreasingWeightSource::FDecreasingWeightSource(const char * weight_filename) :
  weights(weight_filename, std::ios::binary | std::ios::in | std::ios::ate) {
  if (!weights.is_open())
    throw std::invalid_argument(weight_filename);
  size = weights.tellg()/increment;
  reset();
}

Xapian::doccount
FDecreasingWeightSource::get_termfreq_min() const{
  return size;
}

Xapian::doccount
FDecreasingWeightSource::get_termfreq_est() const{
  return size;
}

Xapian::doccount
FDecreasingWeightSource::get_termfreq_max() const{
  return size;
}

Xapian::weight
FDecreasingWeightSource::get_maxweight() const {
  return get_weight();
}

void
FDecreasingWeightSource::reset() {
  started = false;
  finished = false;
  weights.seekg(0);
  val = 0;
  pos = 0;
}

void
FDecreasingWeightSource::next(Xapian::weight min_weight) {
  if (!finished) {
    if (!started) {
      started = true;
      ++pos;
    }
    else 
      weights.seekg(increment, std::ios::cur);
    set_current_val();
    }
  if ( weights.eof() || val < min_weight )
    finished = true;
}

void 
FDecreasingWeightSource::skip_to(Xapian::docid did, Xapian::weight min_weight) {
  started = true;
  if (!finished) {
    weights.seekg(did*increment, std::ios::beg);
    pos = did;
    set_current_val();
    if ( weights.eof() || val < min_weight) 
      finished = true;
  }
}

bool
FDecreasingWeightSource:: at_end() const {
  return finished;
}

Xapian::docid
FDecreasingWeightSource::get_docid() const {
  return pos;
}

Xapian::weight
FDecreasingWeightSource::get_weight() const {
  return val;
}

void
FDecreasingWeightSource::set_current_val() {
  weight_data_type v;
  weights.read(reinterpret_cast<char *>(&v), increment);
  weights.seekg(-increment, std::ios::cur);
  val = v;
}
