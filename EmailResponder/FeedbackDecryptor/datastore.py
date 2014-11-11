# Copyright (c) 2013, Psiphon Inc.
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


'''
There are currently three tables in our Mongo DB:

- diagnostic_info: Holds diagnostic info sent by users. This typically includes
  info about client version, OS, server response time, etc. Data in this table
  is permanent. The idea is that we can mine it to find out relationships
  between Psiphon performance and user environment.

- email_diagnostic_info: This is a little less concrete. The short version is:
  This table indicates that a particlar diagnostic_info record should be
  formatted and emailed. It might also record additional information (like the
  email ID and subject) about the email that should be sent. Once the diagnostic_info
  has been sent, the associated record is removed from this table.

- stats: A dumb DB that is really just used for maintaining state between stats
  service restarts.
'''

import datetime
from pymongo import MongoClient
import numpy
import pytz


_connection = MongoClient()
_db = _connection.maildecryptor


#
# The tables in our DB
#

# Holds diagnostic info sent by users. This typically includes info about
# client version, OS, server response time, etc. Data in this table is
# permanent. The idea is that we can mine it to find out relationships between
# Psiphon performance and user environment.
_diagnostic_info_store = _db.diagnostic_info

# This table indicates that a particlar diagnostic_info record should be
# formatted and emailed. It might also record additional information (like the
# email ID and subject) about the email that should be sent. Once the
# diagnostic_info has been sent, the associated record is removed from this
# table.
_email_diagnostic_info_store = _db.email_diagnostic_info

# Single-record DB that stores the last time a stats email was sent.
_stats_store = _db.stats

# Stores info about autoresponses that should be sent.
_autoresponder_store = _db.autoresponder

# Time-limited store of email address to which responses have been sent. This
# is used to help us avoid sending responses to the same person more than once
# per day (or whatever).
_response_blacklist_store = _db.response_blacklist

# A store of the errors we've seen. Printed into the stats email.
_errors_store = _db.errors


#
# Create any necessary indexes
#

# This index is used for iterating through the diagnostic_info store, and
# for stats queries.
# It's also a TTL index, and purges old records.
DIAGNOSTIC_DATA_LIFETIME_SECS = 60*60*24*7*26  # half a year
_diagnostic_info_store.ensure_index('datetime', expireAfterSeconds=DIAGNOSTIC_DATA_LIFETIME_SECS)

# We use a TTL index on the response_blacklist collection, to expire records.
_BLACKLIST_LIFETIME_SECS = 60*60*24  # one day
_response_blacklist_store.ensure_index('datetime', expireAfterSeconds=_BLACKLIST_LIFETIME_SECS)

# Add a TTL index to the errors store.
_ERRORS_LIFETIME_SECS = 60*60*24*7*26  # half a year
_errors_store.ensure_index('datetime', expireAfterSeconds=_ERRORS_LIFETIME_SECS)

# Add a TTL index to the errors store.
_EMAIL_DIAGNOSTIC_INFO_LIFETIME_SECS = 60*60  # one hour
_email_diagnostic_info_store.ensure_index('datetime', expireAfterSeconds=_EMAIL_DIAGNOSTIC_INFO_LIFETIME_SECS)

# More loookup indexes
_diagnostic_info_store.ensure_index('Metadata.platform')
_diagnostic_info_store.ensure_index('Metadata.version')


#
# Functions to manipulate diagnostic info
#

def insert_diagnostic_info(obj):
    obj['datetime'] = datetime.datetime.now()
    return _diagnostic_info_store.insert(obj)


def insert_email_diagnostic_info(diagnostic_info_record_id,
                                 email_id,
                                 email_subject):
    obj = {'diagnostic_info_record_id': diagnostic_info_record_id,
           'email_id': email_id,
           'email_subject': email_subject,
           'datetime': datetime.datetime.now()
           }
    return _email_diagnostic_info_store.insert(obj)


def get_email_diagnostic_info_iterator():
    return _email_diagnostic_info_store.find()


def find_diagnostic_info(diagnostic_info_record_id):
    if not diagnostic_info_record_id:
        return None

    return _diagnostic_info_store.find_one({'_id': diagnostic_info_record_id})


def remove_email_diagnostic_info(email_diagnostic_info):
    return _email_diagnostic_info_store.remove({'_id': email_diagnostic_info['_id']})


#
# Functions related to the autoresponder
#

def insert_autoresponder_entry(email_info, diagnostic_info_record_id):
    if not email_info and not diagnostic_info_record_id:
        return

    obj = {'diagnostic_info_record_id': diagnostic_info_record_id,
           'email_info': email_info,
           'datetime': datetime.datetime.now()
           }
    return _autoresponder_store.insert(obj)


def get_autoresponder_iterator():
    while True:
        next_rec = _autoresponder_store.find_and_modify(remove=True)
        if not next_rec:
            raise StopIteration()
        yield next_rec


def remove_autoresponder_entry(entry):
    return _autoresponder_store.remove(entry)


#
# Functions related to the email address blacklist
#

def check_and_add_response_address_blacklist(address):
    '''
    Returns True if the address is blacklisted, otherwise inserts it in the DB
    and returns False.
    '''
    now = datetime.datetime.now(pytz.timezone('UTC'))
    # Check and insert with a single command
    match = _response_blacklist_store.find_and_modify(query={'address': address},
                                                      update={'$setOnInsert': {'datetime': now}},
                                                      upsert=True)

    return bool(match)


#
# Functions for the stats DB
#

def set_stats_last_send_time(timestamp):
    '''
    Sets the last send time to `timestamp`.
    '''
    _stats_store.update({}, {'$set': {'last_send_time': timestamp}}, upsert=True)


def get_stats_last_send_time():
    rec = _stats_store.find_one()
    return rec['last_send_time'] if rec else None


def get_new_stats_count(since_time):
    assert(since_time)
    return _diagnostic_info_store.find({'datetime': {'$gt': since_time}}).count()


def get_stats(since_time):
    if not since_time:
        # Pick a sufficiently old date
        since_time = datetime.datetime(2000, 1, 1)

    ERROR_LIMIT = 500

    return {
        'since_timestamp': since_time,
        'now_timestamp': datetime.datetime.now(),
        'new_android_records': _diagnostic_info_store.find({'datetime': {'$gt': since_time}, 'Metadata.platform': 'android'}).count(),
        'new_windows_records': _diagnostic_info_store.find({'datetime': {'$gt': since_time}, 'Metadata.platform': 'windows'}).count(),
        'stats': _get_stats_helper(since_time),

        # The number of errors is unbounded, so we're going to limit the count.
        'new_errors': [_clean_record(e) for e in _errors_store.find({'datetime': {'$gt': since_time}}).limit(ERROR_LIMIT)],
    }


def add_error(error):
    _errors_store.insert({'error': error, 'datetime': datetime.datetime.now()})


def _clean_record(rec):
    '''
    Remove the _id field. Both alters the `rec` param and returns it.
    '''
    if '_id' in rec:
        del rec['_id']
    return rec


def _get_stats_helper(since_time):
    raw_stats = {}

    #
    # Different platforms and versions have different structures
    #

    cur = _diagnostic_info_store.find({'datetime': {'$gt': since_time},
                                       'Metadata.platform': 'android',
                                       'Metadata.version': 1})
    for rec in cur:
        propagation_channel_id = rec.get('SystemInformation', {})\
                                    .get('psiphonEmbeddedValues', {})\
                                    .get('PROPAGATION_CHANNEL_ID')
        sponsor_id = rec.get('SystemInformation', {})\
                        .get('psiphonEmbeddedValues', {})\
                        .get('SPONSOR_ID')

        if not propagation_channel_id or not sponsor_id:
            continue

        response_checks = [r['data'] for r in rec.get('DiagnosticHistory', [])
                           if r.get('msg') == 'ServerResponseCheck'
                             and r.get('data').get('responded') and r.get('data').get('responseTime')]

        for r in response_checks:
            if type(r['responded']) in (str, unicode):
                r['responded'] = (r['responded'] == 'Yes')
            if type(r['responseTime']) in (str, unicode):
                r['responseTime'] = int(r['responseTime'])

        if ('android', propagation_channel_id, sponsor_id) not in raw_stats:
            raw_stats[('android', propagation_channel_id, sponsor_id)] = {'count': 0, 'response_checks': [], 'survey_results': []}

        raw_stats[('android', propagation_channel_id, sponsor_id)]['response_checks'].extend(response_checks)
        raw_stats[('android', propagation_channel_id, sponsor_id)]['count'] += 1

    # The structure got more standardized around here.
    for platform, version in (('android', 2), ('windows', 1)):
        cur = _diagnostic_info_store.find({'datetime': {'$gt': since_time},
                                           'Metadata.platform': platform,
                                           'Metadata.version': {'$gt': version}})
        for rec in cur:
            propagation_channel_id = rec.get('DiagnosticInfo', {})\
                                        .get('SystemInformation', {})\
                                        .get('PsiphonInfo', {})\
                                        .get('PROPAGATION_CHANNEL_ID')
            sponsor_id = rec.get('DiagnosticInfo', {})\
                            .get('SystemInformation', {})\
                            .get('PsiphonInfo', {})\
                            .get('SPONSOR_ID')

            if not propagation_channel_id or not sponsor_id:
                continue

            response_checks = (r['data'] for r in rec.get('DiagnosticInfo', {}).get('DiagnosticHistory', [])
                              if r.get('msg') == 'ServerResponseCheck'
                                 and r.get('data').get('responded') and r.get('data').get('responseTime'))

            survey_results = rec.get('Feedback', {}).get('Survey', {}).get('results', [])
            if type(survey_results) != list:
                survey_results = []

            if (platform, propagation_channel_id, sponsor_id) not in raw_stats:
                raw_stats[(platform, propagation_channel_id, sponsor_id)] = {'count': 0, 'response_checks': [], 'survey_results': []}

            raw_stats[(platform, propagation_channel_id, sponsor_id)]['response_checks'].extend(response_checks)
            raw_stats[(platform, propagation_channel_id, sponsor_id)]['survey_results'].extend(survey_results)
            raw_stats[(platform, propagation_channel_id, sponsor_id)]['count'] += 1

    def survey_reducer(accum, val):
        accum.setdefault(val.get('title', 'INVALID'), {}).setdefault(val.get('answer', 'INVALID'), 0)
        accum[val.get('title', 'INVALID')][val.get('answer', 'INVALID')] += 1
        return accum

    stats = []
    for result_params, results in raw_stats.iteritems():
        response_times = [r['responseTime'] for r in results['response_checks'] if r['responded']]
        mean = float(numpy.mean(response_times)) if len(response_times) else None
        median = float(numpy.median(response_times)) if len(response_times) else None
        stddev = float(numpy.std(response_times)) if len(response_times) else None
        quartiles = [float(q) for q in numpy.percentile(response_times, [5.0, 25.0, 50.0, 75.0, 95.0])] if len(response_times) else None
        failrate = float(len(results['response_checks']) - len(response_times)) / len(results['response_checks']) if len(results['response_checks']) else 1.0

        survey_results = reduce(survey_reducer, results['survey_results'], {})

        stats.append({
                      'platform': result_params[0],
                      'propagation_channel_id': result_params[1],
                      'sponsor_id': result_params[2],
                      'mean': mean,
                      'median': median,
                      'stddev': stddev,
                      'quartiles': quartiles,
                      'failrate': failrate,
                      'response_sample_count': len(results['response_checks']),
                      'survey_results': survey_results,
                      'record_count': results['count'],
                      })

    return stats


#
# Functions related to the sqlexporter
#

def get_sqlexporter_diagnostic_info_iterator(start_datetime):
    cursor = _diagnostic_info_store.find({'datetime': {'$gt': start_datetime}})
    cursor.sort('datetime')
    return cursor
