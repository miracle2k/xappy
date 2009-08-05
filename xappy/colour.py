# Copyright (C) 2009 Lemur Consulting Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""colour.py utilities for bucketing and clustering colours.

Terminology:

 rgb: colour data in the RGB colourspace (a 3-tuple) each coordinate in being
    an integer the range [0..255]

 lab: colour data in the L*a*b* colourspace (a 3-tuple) each coordinate being a
    float in a range determined by the conversion mechanism - see the function
    _compute_range_limits and the variable lab_ranges. (Clearly there are only
    256^3 possible values obtainable from conversion from rgb data in the
    format we use.)

 step_count: the granularity of the quantization of the lab colour space - this
    is taken as a parameter by most routines. A given application is likely to
    want to only use one step_count and stick with it. It makes no sense to mix
    terms generated with different step counts.

 bucket: the step_count and lab_ranges induce a partitioning of the 3d lab
    colour space into cubiods. A given bucket is identified by the 3-tuple for
    the its indices in the whole space. These indices are only useful in the
    range [0, step_count).  Every bucket represent a region of the lab colour
    space.
         
 term: Each bucket has a string representation for storing as a term in the
    database. This is just the the hex string for the bucket position in the
    lexicographic ordering of bucket coordinates.

"""
__docformat__ = "restructuredtext en"

# Standard python modules
import collections
import operator
import itertools
import math

# Third-party modules
#import colour_data
#import colormath
#import colormath.color_objects
import numpy
import scipy.cluster
import scipy.ndimage

# Xapian modules
import xapian
from query import Query

def _compute_range_limits(dim=256):
    """Compute the range of possible Lab coordinates.
    
    This finds the extremes of the Lab coordinates by iterating over all
    possible rgb colours (assuming `dim` steps in each of the rgb axes).

    Warning: this is slow, but it's only needed for checking and
    testing, not for indexing or query generation.

    """
    min_l = min_a = min_b = 10000000.0
    max_l = max_a = max_b = -10000000.0

    for x in xrange(256):
        for y in xrange(256):
            for z in xrange(256):
                rgb = colormath.color_objects.RGBColor(*rgb_coords)
                lab = rgb.convert_to('lab')
                min_l = min(min_l, lab.lab_l)
                min_a = min(min_a, lab.lab_a)
                min_b = min(min_b, lab.lab_b)
                max_l = max(max_l, lab.lab_l)
                max_a = max(max_a, lab.lab_a)
                max_b = max(max_b, lab.lab_b)

    return (min_l, max_l), (min_a, max_a), (min_b, max_b)    

# The possible ranges of Lab values.  This can be recalculated if necessary
# using the _compute_range_limits() function - the following hardcoded values
# are the output of this function.
lab_ranges = (
              (0.0, 99.999984533331272),
              (-86.182949405160798, 98.235320176646439),
              (-107.86546414496824, 94.477318179693782)
)

def cartesian_distance(c1, c2):
    """Calculate the cartesian distance between two colour values.

    This corresponds to the delta-E 1976 distance (dE76) if the colour values
    are in the L*a*b* colour space.

    """
    return math.sqrt(sum(map(lambda x, y: (x - y) * (x - y), c1, c2)))

max_distance = cartesian_distance([x[0] for x in lab_ranges],
                                  [x[1] for x in lab_ranges])

step_size_cache = {}
def step_sizes(step_count):
    """Get the step size for each Lab dimentsion for a given step count.

    """
    try:
        return step_size_cache[step_count]
    except KeyError:
        sizes = tuple(map((lambda x: (x[1] - x[0]) / float(step_count)),
                          lab_ranges))
        step_size_cache[step_count] = sizes
        return sizes

def rgb2lab(rgb):
    """Convert an RGB tuple to Lab.

    """
    rgb = colormath.color_objects.RGBColor(*rgb)
    return rgb.convert_to('lab').get_value_tuple()

def check_in_range(lab):
    """Check that a coordinate is in the acceptable Lab ranges.

    Returns True if in range, False otherwise.

    """
    l, a, b = lab
    r = lab_ranges
    return ( (r[0][0] <= l <= r[0][1]) and
             (r[1][0] <= a <= r[1][1]) and
             (r[2][0] <= b <= r[2][1]) )

def lab2bucket(lab, step_count):
    """Find which bucket a given coordinate occurs in.
    
    Return the indices of the bucket within which the point lab falls, assuming
    that the space is divided up into `step_count` steps in each coordinate.

    """
    l, a, b = lab
    l_step, a_step, b_step = step_sizes(step_count)
    return (int((l - lab_ranges[0][0]) / l_step),
            int((a - lab_ranges[1][0]) / a_step),
            int((b - lab_ranges[2][0]) / b_step))

def bucket2lab(bucket, step_count):
    """Return the coordinates of the least point of `bucket`.

    """
    l_step, a_step, b_step = step_sizes(step_count)
    x, y, z = bucket
    return (lab_ranges[0][1] + x * l_step,
            lab_ranges[1][1] + y * a_step,
            lab_ranges[2][1] + z * b_step)

def rgb2bucket(rgb, step_count):
    """Convert some RGB coordinates into the indices of a bucket.

    """
    return lab2bucket(rgb2lab(rgb), step_count)

def encode_bucket(bucket_indices, step_count):
    """Return a hex string identifying the supplied bucket.
    
    Buckets are numbered according to their position in the lexicographic
    ordering of their coordinates.

    """
    
    l, a, b = bucket_indices
    position = (l +
                step_count * a +
                step_count * step_count * b)
    return hex(position)

def decode_bucket(bucket_id, step_count):
    """Return the bucket indices of a string encoded with encode_bucket.
    
    """
    val = int(bucket_id, 16)
    b, rem = divmod(val, step_count * step_count)
    a, l = divmod(rem, step_count)
    return l, a, b

def lab2term(lab, step_count):
    """Convert some Lab coordinates to a term for the corresponding bucket.

    """
    return encode_bucket(lab2bucket(lab, step_count), step_count)

def rgb2term(rgb, step_count):
    """Convert some RGB coordinates to a term for the corresponding bucket.

    """
    return lab2term(rgb2lab(rgb), step_count)

# synonyms
term2bucket = decode_bucket
bucket2term = encode_bucket

def cluster_coords(coords, coord_fun=None, distance_factor=0.05):
    """Cluster a set of coordinates into groups.
    
    `coords` is an iterable, `coord_fun` is a function that yields
    lab coordinates from elements of `coords`. If `coord_fun` is None
    then the `coords` must contain lab coordinates.

    `distance_factor` is a percentage of the maximum distance across
    the whole of the lab space that we use and controls the size of
    clusters.

    The return value groups `coords` into clusters containing elements
    within the specified distance of each other.

    """
    
    distance = distance_factor * max_distance
    coord_list = list(coords)
    if coord_fun is None:
        source = coord_list
    else:
        source = map(coord_fun, coord_list)
    if len(source) < 2:
        yield coord_list
    else:
        coord_array = numpy.array(source)
    
        clusters = scipy.cluster.hierarchy.fclusterdata(
            coord_array, distance, criterion='distance')

        def keyf(c):
            return clusters[c[0]]

        sfreqs = sorted(enumerate(coord_list), key=keyf)
        groups =  itertools.groupby(sfreqs, keyf)
        for k, group in groups:
            yield map(operator.itemgetter(1), group)

def cluster_terms(terms, step_count, distance_factor=0.05):
    """Clusters terms by converting them to corresponding lab coordinates.

    See cluster_coords.

    """
    coord_fun = lambda t: term2lab(t, step_count)
    return cluster_coords(
        terms, coord_fun=coord_fun, distance_factor = distance_factor)

def average_weights(terms_and_weights):
    """Average the weights in a set of terms.
    
    `terms_and_weights` is a dictionary mapping terms to weights.  The weights
    are replaced by the average weight amongst them all.

    """
    average =  sum(terms_and_weights.itervalues()) / len(terms_and_weights)
    for t in terms_and_weights.iterkeys():
        terms_and_weights[t] = average

# this could all be pushed down into numpy, but colormath needs a
# colour object. This is a candidate for speeding up if performance is
# problematic.

def near_buckets(bucket, distance_factor, step_count):
    """ yield (bucket, distance) pairs for all the buckets within
    `distance_factor` of the supplied `bucket`.

    """
    # with small step counts and small distance factors we have to be
    # a bit careful about which buckets we want. Start at the original
    # bucket and work outwards until we exceed
    # bucket_index_distance. Watch for going out of bounds

    # how far to go in each direction from the original
    bucket_index_distance = int(step_count * distance_factor)

    origin = colormath.color_objects.LabColor(*bucket2lab(bucket, step_count))

    ranges = [(int(max(i - bucket_index_distance, 0)),
               int(min(i + bucket_index_distance + 1, step_count)))
              for i in bucket]

    for x in xrange(*ranges[0]):
        for y in xrange(*ranges[1]):
            for z in xrange(*ranges[2]):
                lab = bucket2lab((x, y, z), step_count)
                lab_obj = colormath.color_objects.LabColor(*lab)
                yield ((x, y, z), origin.delta_e(lab_obj))

def terms_and_weights(colour_freqs, step_count, weight_dict=None):
    if weight_dict is None:
        weight_dict = collections.defaultdict(float)
    for col, freq, spread in colour_freqs:
        distances = near_buckets(rgb2bucket(col, step_count), spread, step_count)
        for bucket, distance in distances:
            term = bucket2term(bucket, step_count)
            weight_dict[term] += freq / (1.0 + distance)
    return weight_dict

def query_colour(sconn, field, colour_freqs, step_count, clustering=False):
    """ Generate a query to find document with similar colours in
    `field` to those specified in `colour_freqs`. `colour_freqs`
    should be at iterable whose members are lists or tuples
    consisting of 3 data. These being (in order) a sequence
    consisting rgb colour coordinates, each in the range 0-255; a
    frequency measure and a precision measure.
    
    If `clustering` is True then individual colours will be grouped
    together into clusters, and the total frequency for the
    cluster used to weight terms for its consituent colours.

    If `clustering` is False then no clustering will be done and each
    frequency is simply used to weight the terms generated from
    that colour.

    In either case each colour will be used to generate terms for
    colours close to that colour, with decreasing weights as the
    distance increases. The number of terms generated is
    controlled by the precision, which indicates the percentage of
    the total range of colour values represented by the
    colour. Note that the higher this value the more terms that
    will be generated, which may affect performance. A value of 0
    means that only one term will be generated. (It is not
    possible to exclude a colour completely with this mechanism -
    simply omit it from `colour_freqs` to achieve this.)
    
    """

    if clustering:
        clusters = cluster_coords(
            colour_freqs, coord_fun=operator.itemgetter(0))
        
    else:
        clusters = [colour_freqs]
    

    return query_from_clusters(sconn, field, clusters, step_count,
                               averaging=clustering)

def query_from_clusters(sconn, field, clusters, step_count, averaging=False):

    prefix = sconn._field_mappings.get_prefix(field)

    def term_subqs(ts):
        return [Query(xapian.Query(prefix + term)) * weight for
                term, weight in ts.iteritems()]


    subqs = []
    for cluster in clusters:
        weighted_terms = terms_and_weights(cluster, step_count)
        if averaging:
            average_weights(weighted_terms)
        subqs.append(Query.compose(Query.OP_OR,
                                   term_subqs(weighted_terms)))
    return Query.compose(Query.OP_AND, subqs)


colour_terms_cache = {}

def colour_terms(step_count, rgb_data=colour_data.rgb_data):
    """ Return a dictionary of name -> term for `step_count`
    corresponding to the name -> rgb data in `rgb_data`.

    """
    try:
        terms = colour_terms_cache[step_count]
    except KeyError:
        terms = {}
        for colourname, rgb in rgb_data.iteritems():
            terms[colourname] = rgb2term(rgb, step_count)
        colour_terms_cache[step_count] = terms
    return terms

def text_weights(text, step_count,
                 rgb_data = colour_data.rgb_data,
                 colour_spreads = colour_data.colour_spreads):
    """ find occurences of colour names in text; compute a dictionary
    of terms -> weights, for adding to a document. The keys are terms
    corresponding to colours near those found, and the weights fall
    off according to distance from the colours found. The number of
    terms added depends on the spread for the colour given by
    colour_spreads.  This is a dictionary mapping colour names to a
    figure on the range 0->1.  A spread of 0 means that only the
    actual colour mentioned will be included; a spread of 1 means the
    whole colour space will be included. Higher values are unlikely to
    be desirable.

    """
    weights = collections.defaultdict(float)
    for colour_name, rgb in rgb_data:
        count = text.count(colour_name)
        spread = colour_spreads[colour_name]
        terms_and_weights((rgb, count, spread), step_count, weights)
    return weights


def facet_palette_query(conn, facets, palette, dimensions, step_count):
    """ facets are objects that quack as:
      - .val a hex string representing an index into palette
      - .weight a weight for the facet.
      - .fieldname = xappy field indexed with FieldActions.COLOUR
         it is assumed that all facets have the same fieldname.
      
    dimensions is the shape of a 2d array for which palette contains the data.
    palette contains strings, each of which represents a triple of rgb data.

    colour facet values are clustered according to adjacency in the 2d array
    implied by palette and dimensions.

    conn is the SearchConnection to create the query for.
    
    step_count is the granularity of the colour space bucketing (as usual).

    A query for the field is constructed by averaging the weights
    within a cluster, ORing those values togther and then ANDing the
    resulting subqueries.

    """

    # facet values are hex strings for indexes into the palette array
    # the corresponding coordinates come from  the dimensions.

    if len(facets) == 0:
        return xappy.Query()

    fieldname = facets[0].fieldname
    palette_array = numpy.array(palette).reshape(dimensions)
    facet_positions = numpy.zeros(dimensions, int)
    facet_weights = numpy.zeros_like(facet_positions)
    for f in facets:
        facet_index = divmod(int(f.val, 16), dimensions[0])
        facet_positions[facet_index] = 1
        # accumulate = we may get the same facet value more than once.
        facet_weights[facet_index] += f.weight
        
    structure = numpy.ones((3,3), int)
    labels, count = scipy.ndimage.label(facet_positions)
    #labels now contains the connected regions of the input
    #facets. count is the number of regions

    # choose a spread for each cluster - not sure what's best here
    spread = 0.05

    def make_clusters():
        for l in xrange(1, count+1):
            rgbs = palette_array[labels == l]
            mean_weight = scipy.ndimage.mean(facet_weights, labels=labels, index=l)
            cluster_vals = [ ((int(x[:2], 16), int(x[2:4], 16), int(x[4:], 16)),
                              mean_weight, spread)
                             for x in rgbs]
            yield cluster_vals

    return query_from_clusters(conn, fieldname, make_clusters(), step_count)
