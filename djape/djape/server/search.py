# TODO - tests
# TODO - change default server location (ie, remove "xapian/" prefix)
# TODO - add api versioning

import dircache
import os
import re
import settings
import simplejson
import shutil
import time
import traceback
from wsgisupport import Response
import xapian # For calling the latlong code directly
import xappy

api_version = 0

class SearchError(Exception):
    """Base class for errors raised and to be shown to user.

    The errtype property should contain the value to put in the "type" return
    value.

    """
    pass

class ValidationError(SearchError):
    """Raised when an invalid parameter value is supplied to the query string.

    """
    errtype = 'Validation'

class DatabaseExistsError(SearchError):
    """Raised when there is already a database of the name we want to use.
    
    When creating a database, this either means that the database is already
    there, or that there's something else in the location to be used for the
    database on the filesystem.

    """
    errtype = 'DatabaseExists'

class DatabaseNotFoundError(SearchError):
    """Raised when no database is present at the path we expect.

    """
    errtype = 'DatabaseNotFound'


def errchecked(fn):
    """Decorator to handle returning error descriptions

    """
    def res(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
            # FIXME - log these errors
        except SearchError, e:
            return {"error": str(e), "type": e.errtype}
        except xappy.SearchEngineError, e:
            return {"error": str(e), "type": "xappy.%s" % e.__class__.__name__}
    return res

def jsonreturning(fn):
    """Decorator to wrap function's return value as JSON.

    """
    def res(*args, **kwargs):
        result = fn(*args, **kwargs)
        return Response(simplejson.dumps(result, indent=4),
                        mimetype="text/javascript")
    return res

def timed(fn):
    """Decorator to time function and insert time into result

    """
    def res(*args, **kwargs): 
        start = time.time()
        retval = fn(*args, **kwargs)
        retval['elapsed'] = time.time() - start
        return retval
    return res

def validate_param(key, vals, minreps, maxreps, pattern, default):
    """Validate a particular parameter.

    """
    l = len(vals)

    # If not present, and there is a default, set vals to default
    if l == 0 and default is not None:
        vals = default

    # Check we've got an acceptable number of values.
    if l < minreps:
        raise ValidationError("Too few instances of %r supplied "
                              "(needed %d, got %d)" %
                              (key, minreps, l))
    if maxreps is not None and l > maxreps:
        raise ValidationError("Too many instances of %r supplied "
                              "(maximum %d, got %d)" %
                              (key, maxreps, l))

    if pattern is not None:
        # Check the regexp pattern matches
        m = re.compile(pattern)
        for val in vals:
            if not m.match(val):
                raise ValidationError("Invalid parameter value for %r" % key)

    return vals

def validate_dbname(db_name):
    """Validate a database name.

    """
    if not re.match('\w+$', db_name):
        raise ValidationError("Invalid database name: '%r'" % db_name)
    return db_name

def validate_params(requestobj, constraints):
    """Validate parameters, raising ValidationError for problems.

    `constraints` is a dict of tuples, one for each field.  Unknown fields
    raise an error.

    """
    p = {}

    # Check for missing parameters - add if they have a default, otherwise give
    # and error.
    missing_params = set()
    for key, constraint in constraints.iteritems():
        if constraint[3] is not None:
            if key not in requestobj:
                p[key] = constraint[3]
        else:
            # check for missing params
            if constraint[0] > 0 and key not in requestobj:
                missing_params.add(key)

    if len(missing_params) != 0:
        # We trust the list of missing_params not to be trying to hack us.
        raise ValidationError("Missing required parameters %s" %
                              ', '.join("'%s'" % p for p in missing_params))

    for key in requestobj:
        constraint = constraints.get(key, None)
        if constraint is None:
            if re.match('\w+$', key):
                # No potentially dangerous characters
                raise ValidationError("Unknown parameter %r supplied" % key)
            else:
                raise ValidationError("Unknown parameter supplied")
        p[key] = validate_param(key, requestobj[key], *constraint)

    return p

def get_db_path(dbname):
    return os.path.join(settings.XAPPY_DATABASE_DIR, dbname)

def parse_freetext_opts(opts):
    """Validate and parse the options for a freetext query.

    """
    validate_dict_entries(opts, ('default_op',
                                 'allow', 'deny',
                                 'default_allow', 'default_deny',
                                ),
                          'Invalid item in freetext query options: %s')
    xapopts = {}
    if 'default_op' in opts:
        defop = opts['default_op']
        if int(defop) == 0:
            xapopts['default_op'] = xappy.Query.OP_AND
        elif int(defop) == 1:
            xapopts['default_op'] = xappy.Query.OP_OR
    for opt in ('allow', 'deny', 'default_allow', 'default_deny'):
        if opt in opts:
            xapopts[opt] = opts[opt]
    return xapopts

def parse_query_spec(db, subq, spell=False):
    """Parse the parameters representing a query.
    
    Raises a ValidationError if the parameters are invalid.

    Returns a xappy query, and 

    """
    if subq is None:
        return db.query_all()

    if not isinstance(subq, (list, tuple)):
        raise ValidationError("Invalid query specification - expected [query_type, parameters], didn't get a list (got %r)" % subq)
    if len(subq) != 2:
        raise ValidationError("Invalid query specification - expected [query_type, parameters], got a list of length %d" % len(subq))

    # Handle the different types of subq.  Convert this to a dict lookup if we
    # end up with lots.
    if subq[0] == 'freetext':
        query_text = subq[1]
        opts = {}
        if not isinstance(query_text, basestring):
            query_text, opts = query_text
            opts = parse_freetext_opts(opts)
        if spell:
            spell_corrected = db.spell_correct(query_text)
            return db.query_parse(spell_corrected, **opts), spell_corrected

        return db.query_parse(query_text, **opts), None
    if subq[0] == 'all':
        return db.query_all(), None

    raise ValidationError("Invalid query specification - unknown query type '%s'" % subq[0])



@jsonreturning
@timed
@errchecked
def latestapi(request):
    """Return information about the API version.

    Returns a JSON string holding a dict with 'latest_version' set to the
    latest version for the API.

    """
    return {
        'latest_version': str(api_version),
    }

@jsonreturning
@timed
@errchecked
def search(request, db_name):
    """Serve a search request.

    Accepts GET requests only.

     - `db_name`: contains the name of the database.

    Supported query parameters:

     - `q`: contains the search specification.  (If None, all documents will be
       matched by the search).
     - `start_rank` is the rank of the start of the range of matching documents
       to return (ie, the result with this rank will be returned).  ranks start
       at 0, which represents the "best" matching document.  Defaults to 0.
     - `end_rank` is the rank at the end of the range of matching documents to
       return.  This is exclusive, so the result with this rank will not be
       returned.  Defaults to 10.
     - `relevant_data` is an int: if non 0, return some data items (up to
       number given in parameter) which are relevant.  Defaults to 0.
     - `summarise` is an int: if specified and non 0, returned data (in `data`)
       will be summarised to the length supplied.
     - `hl` is a pair of tags used for marking relevant items in the summarised
       data. 

    Returns some JSON:

     - `db_name`: database name:
     - `items`: list of search result items (in rank order, best first). Each
       item is a dict of:
        - `rank`: rank of result - 0 is best
        - `id`: id of result
        - `data`: data of result, which is a dict, keyed by name, contents is a
          list of all values stored in the document, (or just the relevant
          ones, possibly summarised and highlighted, if `relevant_data` and/or
          `summarise` were supplied).
     - `matches_lower_bound`: lower bound on number of matches.
     - `matches_estimated`: estimated number of matches.
     - `matches_upper_bound`: upper bound on number of matches.
     - `doc_count`: number of documents in database.
     - `has_more_results`: true if the search has more results (at a lower
       rank) than have been displayed.

    """
    db_name = validate_dbname(db_name)
    params = validate_params(request.GET, {
                             'q': (0, 1, '^.*$', []),
                             'start_rank': (1, 1, '^\d+$', ['0']),
                             'end_rank': (1, 1, '^\d+$', ['10']),
                             'spell_correct': (1, 1, '^never|auto|always$', ['auto']),
                             'relevant_data': (1, 1, '^\d+$', ['0']),
                             'summarise': (0, 1, '^\d+$', ['0']),
                             'hl': (0, 1, None, [None]),
                             })

    db = xappy.SearchConnection(get_db_path(db_name))

    retval = {
        'ok': 1,
        'db_name': db_name,
        'doc_count': db.get_doccount(),
    }

    sort_by = None
    distance_centre = None
    distance_centre_field = None
    if len(params['q']) == 0:
        q = db.query_all()
    else:
        query_defn = simplejson.loads(params['q'][0])
        validate_dict_entries(query_defn, ('opts', 'query'),
                              'Invalid item in query definition: %s')

        if params['spell_correct'][0] == 'always':
            q, ignore = parse_query_spec(db, query_defn.get('query'), spell=True)
        else:
            q, ignore = parse_query_spec(db, query_defn.get('query'))

        opts = query_defn.get('opts')
        if opts is not None:
            validate_dict_entries(opts, ('sort_by', 'sort_by_distance'),
                                  'Invalid search option: %s')
            if 'sort_by' in opts and 'sort_by_distance' in opts:
                raise ValidationError("At most one of 'sort_by' and "
                                      "'sort_by_distance' may be specified.")
            if 'sort_by' in opts:
                raise ValidationError("sort_by not yet implemented")

            if 'sort_by_distance' in opts:
                sort_by_distance = opts['sort_by_distance']
                if len(sort_by_distance) != 1:
                    raise ValidationError("sort_by_distance can currently only contain one location")
                sort_by_distance = sort_by_distance[0]
                if len(sort_by_distance) != 2:
                    raise ValidationError("sort_by_distance must contain instances of (fieldname, location)")
                sort_by = db.SortByGeolocation(*sort_by_distance)
                distance_centre = xapian.LatLongCoords()
                distance_centre.insert(xapian.LatLongCoord.parse_latlong(sort_by_distance[1]))
                distance_centre_field = sort_by_distance[0]

    res = q.search(int(params['start_rank'][0]),
                   int(params['end_rank'][0]),
                   sortby=sort_by)
    retval['_orig_xapian_query'] = str(q._get_xapian_query())

    if len(res) == 0:
        if len(params['q']) != 0 and params['spell_correct'][0] == 'auto':
            # Try spell correcting
            query_defn = simplejson.loads(params['q'][0])
            q, corrected_q = parse_query_spec(db, query_defn.get('query'),
                                              spell=True)

            res = q.search(int(params['start_rank'][0]),
                           int(params['end_rank'][0]),
                           sortby=sort_by)
            retval['_spellcorrected_xapian_query'] = str(q._get_xapian_query())
            if len(res) != 0:
                retval['spell_corrected'] = True
                retval['spellcorr_q'] = corrected_q

    if distance_centre is not None:
        distance_metric = xapian.GreatCircleMetric()

    items = []
    for item in res:
        itemres = {
            'rank': (item.rank),
            'id': (item.id),
            'data': (item.data),
        }
        if distance_centre is not None:
            val = item.get_value(distance_centre_field, 'loc')
            doc_coords = xapian.LatLongCoords.unserialise(val)
            distance = distance_metric(distance_centre, doc_coords)
            itemres['geo_distance'] = {
                distance_centre_field: distance,
            }

        relevant_data = int(params['relevant_data'][0])
        if relevant_data > 0:
            reldata = item.relevant_data(relevant_data)
            itemres['relevant_data'] = reldata

        summarise = int(params['summarise'][0])
        hl = params['hl'][0]
        if hl == '' or hl is None:
            hl = None
        else:
            hl = simplejson.loads(hl)

        if summarise > 0:
            summary = {}
            for field in item.data.iterkeys():
                summary[field] = [item.summarise(field, summarise, hl)]
            itemres['data'] = summary
        elif hl is not None:
            summary = {}
            for field in item.data.iterkeys():
                summary[field] = [item.highlight(field, hl)]
            itemres['data'] = summary

        items.append(itemres)

    retval.update({
        'items': items,
        'matches_lower_bound': res.matches_lower_bound,
        'matches_estimated': res.matches_estimated,
        'matches_upper_bound': res.matches_upper_bound,
        'has_more_results': res.more_matches,
    })
    return retval

@jsonreturning
@timed
@errchecked
def get(request, db_name):
    """Serve a get document (or documents) request.

    Accepts GET requests only.

     - `db_name`: contains the name of the database.

    Supported query parameters:

     - `id`: contains the id of the document to get.  May be repeated
       arbitrarily.

    Returns some JSON:

     - `ok`: 1
     - `items`: list of result items found (order is undefined - don't rely on
       it!). Each item is a dict of:
        - `id`: id of result
        - `data`: data of result, which is a dict, keyed by name, contents is a
          list of values.
     - `missing_ids`: list of missing items (ie, those for which the ID was
       not found).

    """
    db_name = validate_dbname(db_name)
    params = validate_params(request.GET, {
                             'id': (0, None, '^.*$', []),
                             })

    db = xappy.SearchConnection(get_db_path(db_name))

    items = []
    missing_ids = []
    for item_id in params['id']:
        try:
            item = db.get_document(item_id)
        except KeyError:
            # docid not found
            missing_ids.append(item_id)
            continue
        items.append({'id': item.id, 'data': item.data})

    return {
        'ok': 1,
        'db_name': db_name,
        'doc_count': db.get_doccount(),
        'items': items,
        'missing_ids': missing_ids
    }

@jsonreturning
@timed
@errchecked
def listdbs(request):
    """Get a list of available databases.

    """
    if not os.path.isdir(settings.XAPPY_DATABASE_DIR):
        names = []
    else:
        names = dircache.listdir(settings.XAPPY_DATABASE_DIR)
    return {'db_names': names}

@jsonreturning
@timed
@errchecked
def parse_latlong(request):
    """Parse a latitude/longitude coordinate, in a variety of formats, to a
    pair of floating point numbers.

    Takes a single querystring parameter.

    Returns {'ok': 1, 'latitude': latitude, 'longitude': longitude} if it could
    parse, or {'ok': 0} if it couldn't.

    """
    params = validate_params(request.GET, {
                             'latlong_string': (1, 1, '^.*$', None),
                             })
    try:
        coord = xapian.LatLongCoord.parse_latlong(params['latlong_string'][0])
    except xapian.LatLongParserError, e:
        return {'ok': 0}
    return {'ok': 1, 'latitude': coord.latitude, 'longitude': coord.longitude}

valid_field_config_keys = set((
    'exacttext',
    'field_name',
    'freetext',
    'geo',
    'store',
    'type',
))

valid_freetext_options = set((
    'language',
    'term_frequency_multiplier',
    'enable_phrase_search',
    'index_groups',
))

valid_geo_options = set ((
    'enable_bounding_box_search',
    'enable_range_search',
))

def validate_dict_entries(dict, allowed, msg):
    """Check that a dict has no entried other than those in allowed.

    `msg` should contain the message to use in the ValidationError raised if
    a problem is found.  %s in this will be replaced with the list of
    disallowed items.

    """
    invalid_keys = []
    for key in dict.keys():
        if key not in allowed:
            invalid_keys.append(key)
    if len(invalid_keys) != 0:
        raise ValidationError(
            msg % ', '.join("'%s'" % p for p in invalid_keys))

@jsonreturning
@timed
@errchecked
def newdb(request):
    """Create a new database.

    Accepts POST requests only.

    If the database already exists:
     - if overwrite is 1, replaces the database completely with a new one
       (deleting all the contents).
     - if allow_reopen is 1, allows the database to be reopened, but only if
       the supplied configuration is identical.  Otherwise gives an error.

    Supported parameters:

     - `db_name`: contains the name of the database.
     - `fields`: the field parameters (see the client for documentation for
       now: major FAIL, FIXME)
     - `overwrite`: if 1, and the database already exists, instead of returning
       an error, remove it and create it anew. (doesn't affect behaviour if
       database doesn't exist).  defaults to 0.
     - `allow_reopen`: if 1, and the database already exists, check if the
       supplied configuration is identical.  Otherwise, gives an error.
 
    """
    params = validate_params(request.POST, {
                             'db_name': (1, 1, '^\w+$', None),
                             'fields': (1, 1, None, None),
                             'overwrite': (1, 1, '^[01]$', [0]),
                             'allow_reopen': (1, 1, '^[01]$', [0]),
                             })
    overwrite = params['overwrite'][0] == '1'
    allow_reopen = params['allow_reopen'][0] == '1'

    if overwrite and allow_reopen:
        raise ValidationError('"overwrite" and "allow_reopen" must not both be specified')

    db_name = params['db_name'][0]
    db_path = os.path.realpath(get_db_path(db_name))

    db = None

    if os.path.exists(db_path):
        if overwrite:
            shutil.rmtree(db_path)
        elif allow_reopen:
            if not os.path.exists(os.path.dirname(db_path)):
                os.makedirs(os.path.dirname(db_path))
            db = xappy.IndexerConnection(db_path)
            try:
                oldconfig = db.get_metadata('_xappyclient_config')
                if oldconfig != '':
                    oldconfig = simplejson.loads(oldconfig)
                config = simplejson.loads(params['fields'][0])
                if oldconfig != config:
                    raise DatabaseExistsError("The path for '%s' is already "
                        "in use, and the configuration does not match: \n"
                        "old config=%r\nnew config=%r" %
                        (db_path, oldconfig, config))
                else:
                    return {'ok': 1}
            except:
                db.close()
                raise
        else:
            raise DatabaseExistsError("The path for '%s' is already in use" % db_path)

    if not os.path.exists(os.path.dirname(db_path)):
        os.makedirs(os.path.dirname(db_path))
    db = xappy.IndexerConnection(db_path)

    try:
        try:
            # Set up the field actions from fields
            config = simplejson.loads(params['fields'][0])

            # Store the field configuration.
            db.set_metadata('_xappyclient_config', simplejson.dumps(config))

            # FIXME -perhaps we should validate here?
            for settings in config:
                validate_dict_entries(settings, valid_field_config_keys,
                                      'Invalid field setting parameter(s): %s')

                field_name = settings.get('field_name', None)
                if field_name is None:
                    raise ValidationError("Missing field_name parameter")

                field_type = settings.get('type', 'text')
                if field_type not in ('text', 'date', 'float', 'geo'):
                    raise ValidationError("Unknown field_type parameter %s" %
                                          field_type)

                if settings.get('store', False):
                    db.add_field_action(field_name, xappy.FieldActions.STORE_CONTENT)

                spelling_word_source = settings.get('spelling_word_source', True)
                #collapsible = settings.get('collapsible', False)
                #sortable = settings.get('sortable', False)
                #range_searchable = settings.get('range_searchable', False)
                #is_document_weight = settings.get('is_document_weight', False)

                noindex = settings.get('noindex', False)
                freetext_params = settings.get('freetext', None)
                exacttext_params = settings.get('exacttext', None)

                if (freetext_params is not None and
                    exacttext_params is not None):
                    raise ValidationError(
                         "Field settings for %s specify both 'freetext' and "
                         "'exacttext' for a single field - at most one may be "
                         "specified")

                if freetext_params is not None and noindex:
                    raise ValidationError(
                         "Field settings for %s specify both 'freetext' and "
                         "'noindex' for a single field - at most one may be "
                         "specified")

                if exacttext_params is not None and noindex:
                    raise ValidationError(
                         "Field settings for %s specify both 'exacttext' and "
                         "'noindex' for a single field - at most one may be "
                         "specified")

                if (freetext_params is not None or
                    exacttext_params is not None):
                    if field_type != 'text':
                        raise ValidationError(
                            "Text searching options specified, but field type "
                            "is not text")

                if freetext_params is not None or (
                        field_type == 'text' and
                        freetext_params is None and
                        exacttext_params is None and
                        not noindex):
                    if freetext_params is None:
                        freetext_params = {}
                    validate_dict_entries(freetext_params, valid_freetext_options,
                                          'Invalid freetext option(s): %s')
                    opts = {}

                    lang = freetext_params.get('language', None)
                    if lang is not None:
                        opts['language'] = lang

                    opts['weight'] = freetext_params.get('term_frequency_multiplier', 1)

                    phrase = freetext_params.get('enable_phrase_search', True)
                    if not phrase:
                        opts['nopos'] = True

                    if spelling_word_source:
                        opts['spell'] = True

                    index_groups = freetext_params.get('index_groups',
                        ['_FIELD_INDEX', '_GENERAL_INDEX'])
                    db.add_field_action(field_name,
                                        xappy.FieldActions.INDEX_FREETEXT,
                                        **opts)

                if exacttext_params is not None:
                    #FIXME - implement
                    raise ValidationError("exacttext not yet implemented")

                geo_params = settings.get('geo', None)
                if geo_params is not None and noindex:
                    raise ValidationError(
                         "Field settings for %s specify both 'geo' and "
                         "'noindex' for a single field - at most one may be "
                         "specified")

                if geo_params is not None:
                    if field_type != 'geo':
                        raise ValidationError(
                            "Text searching options specified, but field type "
                            "is not text")

                if geo_params is not None or (
                        field_type == 'geo' and
                        geo_params is None and
                        not noindex):
                    if geo_params is None:
                        geo_params = {}

                    validate_dict_entries(geo_params, valid_geo_options,
                                          'Invalid freetext option(s): %s')
                    bounding_box_search = geo_params.get('enable_bounding_box_search', True)
                    range_search = geo_params.get('enable_range_search', True)

                    # Geolocation action (for sorting by distance).
                    db.add_field_action(field_name,
                                        xappy.FieldActions.GEOLOCATION)

                    if bounding_box_search or range_search:
                        pass
                        # FIXME - need to do something to index these.

            db.flush()
        finally:
            db.close()
    except:
        del db
        shutil.rmtree(db_path)
        dircache.reset()
        raise
    dircache.reset()
    return {'ok': 1}

@jsonreturning
@timed
@errchecked
def deldb(request):
    """Delete a database.

    Accepts POST requests only.

    Returns an error if the database doesn't already exist.

    Supported parameters:

     - `db_name`: contains the name of the database.
 
    """
    params = validate_params(request.POST, {
                             'db_name': (1, 1, '^\w+$', None),
                             })
    db_name = params['db_name'][0]
    db_path = os.path.realpath(get_db_path(db_name))

    if not os.path.exists(db_path):
        raise DatabaseNotFoundError("The path '%s' is already empty" % db_path)

    shutil.rmtree(db_path)
    dircache.reset()
    return {'ok': 1}

def doc_from_params(params):
    doc = xappy.UnprocessedDocument()
    doc.extend(params['data'])
    if params['id'] is not None and len(params['id']) > 0:
        doc.id = params['id']
    return doc

@jsonreturning
@timed
@errchecked
def add(request, db_name):
    """Add a document.

    Accepts POST requests only.

    Returns an error if the database doesn't already exist.

    Supported parameters:

     'doc': JSON encoded document to add.  When unencoded, contains:
     {
      'id': (optional) Document ID (string)
      'data': (reqired) list of fieldname/value pairs.  fieldnames may be repeated.
       [
         [fieldname, value],
         [fieldname, value],
       ]
     }

    Returns, if successfully added,

    {
     'ok': 1,
     'ids': # list of ids used for new documents - autogenerated if no id specified
     'doc_count': # new number of documents in database (ie, after all adds/replaces)
     'prev_doc_count': # number of documents in database before the add/replace
    }
 
    """
    db_name = validate_dbname(db_name)
    params = validate_params(request.POST, {
                             'doc': (1, None, None, None),
                             })

    db = xappy.IndexerConnection(get_db_path(db_name))
    try:
        prev_doc_count = db.get_doccount()
        newids = []
        for doc in params['doc']:
            doc = simplejson.loads(doc)
            doc = doc_from_params(doc)
            if doc.id is None:
                newids.append(db.add(doc))
            else:
                db.replace(doc)
                newids.append(doc.id)
        db.flush()
        return {'ok': 1, 'ids': newids, 'doc_count': db.get_doccount(),
            'prev_doc_count': prev_doc_count}
    finally:
        db.close()

