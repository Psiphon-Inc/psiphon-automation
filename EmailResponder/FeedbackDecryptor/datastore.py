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

# TODO: Create indexes

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


_EXPIRY_MINUTES = 360


_connection = MongoClient()
_db = _connection.maildecryptor
_diagnostic_info_store = _db.diagnostic_info
_email_diagnostic_info_store = _db.email_diagnostic_info
_stats_store = _db.stats
_errors_store = _db.errors


def insert_diagnostic_info(obj):
    obj['datetime'] = datetime.datetime.now()
    return _diagnostic_info_store.insert(obj)


def insert_email_diagnostic_info(diagnostic_info_id,
                                 email_id,
                                 email_subject):
    obj = {
           'diagnostic_info_id': diagnostic_info_id,
           'email_id': email_id,
           'email_subject': email_subject,
           'datetime': datetime.datetime.now()
          }
    return _email_diagnostic_info_store.insert(obj)


def get_email_diagnostic_info_iterator():
    return _email_diagnostic_info_store.find()


def find_diagnostic_info(diagnostic_info_id):
    return _diagnostic_info_store.find_one({'Metadata.id': diagnostic_info_id})


def remove_email_diagnostic_info(email_diagnostic_info):
    return _email_diagnostic_info_store.remove({'_id': email_diagnostic_info['_id']})


def expire_old_email_diagnostic_info_records():
    expiry_datetime = datetime.datetime.now() - datetime.timedelta(minutes=_EXPIRY_MINUTES)
    return _email_diagnostic_info_store.remove({'datetime': {'$lt': expiry_datetime}})


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

    return {
        'since_timestamp': since_time,
        'now_timestamp': datetime.datetime.now(),
        'new_android_records': _diagnostic_info_store.find({'Metadata.platform': 'android', 'datetime': {'$gt': since_time}}).count(),
        'new_windows_records': _diagnostic_info_store.find({'Metadata.platform': 'windows', 'datetime': {'$gt': since_time}}).count(),
        'response_stats': _get_response_stats(since_time),

        # WARNING: This is potentially unbounded. But using a generator seems
        # pointless because it needs to be reified for the email anyway.
        'new_errors': [_clean_record(e) for e in _errors_store.find({'datetime': {'$gt': since_time}})],
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


def _get_response_stats(since_time):
    allResponseChecks = {}

    #
    # Different platforms and versions have different structures
    #

    cur = _diagnostic_info_store.find({'Metadata.platform': 'android',
                                       'Metadata.version': 1,
                                       'datetime': {'$gt': since_time}})
    for rec in cur:
        propChannelID = rec.get('SystemInformation', {})\
                           .get('psiphonEmbeddedValues', {})\
                           .get('PROPAGATION_CHANNEL_ID')
        sponsorID = rec.get('SystemInformation', {})\
                       .get('psiphonEmbeddedValues', {})\
                       .get('SPONSOR_ID')

        if not propChannelID or not sponsorID:
            continue

        responseChecks = [r['data'] for r in rec.get('DiagnosticHistory', [])
                          if r.get('msg') == 'ServerResponseCheck'
                             and r.get('data').get('responded') and r.get('data').get('responseTime')]

        for r in responseChecks:
            if type(r['responded']) in (str, unicode):
                r['responded'] = (r['responded'] == 'Yes')
            if type(r['responseTime']) in (str, unicode):
                r['responseTime'] = int(r['responseTime'])

        if ('android', propChannelID, sponsorID) not in allResponseChecks:
            allResponseChecks[('android', propChannelID, sponsorID)] = []

        allResponseChecks[('android', propChannelID, sponsorID)].extend(responseChecks)

    # The structure got more standardized around here.
    for platform, version in (('android', 2), ('windows', 1)):
        cur = _diagnostic_info_store.find({'Metadata.platform': platform,
                                           'Metadata.version': version,
                                           'datetime': {'$gt': since_time}})
        for rec in cur:
            propChannelID = rec.get('DiagnosticInfo', {})\
                               .get('SystemInformation', {})\
                               .get('PsiphonInfo', {})\
                               .get('PROPAGATION_CHANNEL_ID')
            sponsorID = rec.get('DiagnosticInfo', {})\
                           .get('SystemInformation', {})\
                               .get('PsiphonInfo', {})\
                           .get('SPONSOR_ID')

            if not propChannelID or not sponsorID:
                continue

            responseChecks = (r['data'] for r in rec.get('DiagnosticInfo', {}).get('DiagnosticHistory', [])
                              if r.get('msg') == 'ServerResponseCheck'
                                 and r.get('data').get('responded') and r.get('data').get('responseTime'))

            if (platform, propChannelID, sponsorID) not in allResponseChecks:
                allResponseChecks[(platform, propChannelID, sponsorID)] = []

            allResponseChecks[(platform, propChannelID, sponsorID)].extend(responseChecks)

    responseStats = []
    for resultParams, results in allResponseChecks.iteritems():
        responseTimes = [r['responseTime'] for r in results if r['responded']]
        mean = numpy.mean(responseTimes) if len(responseTimes) else None
        median = numpy.median(responseTimes) if len(responseTimes) else None
        stddev = numpy.std(responseTimes) if len(responseTimes) else None
        failrate = float(len(results) - len(responseTimes)) / len(results) if len(results) else 1.0

        responseStats.append({
                              'platform': resultParams[0],
                              'propagation_channel_id': resultParams[1],
                              'sponsor_id': resultParams[2],
                              'mean': mean,
                              'median': median,
                              'stddev': stddev,
                              'failrate': failrate,
                              'count': len(results),
                              })

    return responseStats
