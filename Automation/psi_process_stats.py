#!/usr/bin/python
#
# Copyright (c) 2011, Psiphon Inc.
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
#

import os
import re
import textwrap
import gzip
import csv
import datetime
import collections
import time
import traceback
import psycopg2
import sys
import multiprocessing
import argparse
import iso8601

import psi_ssh
import psi_ops
import psi_ops_stats_credentials


HOST_LOG_FILENAME_PATTERN = 'psiphonv.log*'
LOCAL_LOG_ROOT = os.path.join(os.path.abspath('.'), 'logs')
PSI_OPS_DB_FILENAME = os.path.join(os.path.abspath('.'), 'psi_ops_stats.dat')

TESTING_PROPAGATION_CHANNEL_NAME = 'Testing'


# Stats database schema consists of one table per event type. The tables
# have a column per log line field.
#
# The entire log line is considered to be unique. This is how we handle pulling
# down the same log file again: duplicate lines are discarded. This logic also
# handles the unlikely case where our SFTP pull happens in the middle of a
# log rotation, in which case we may pull the same log entries down twice in
# two different file names.
#
# The uniqueness assumption depends on a high resolution timestamp as it's
# likely that there will be multiple handshake events in the same second on
# the same server from the same region and client build.

# Example log file entries:

'''
2011-06-28T13:14:04.000000-07:00 host1 psiphonv: started 192.168.1.101
2011-06-28T13:15:59.000000-07:00 host1 psiphonv: handshake 192.168.1.101 CA DA77176D642E66FB 1F277F0BD58BB84D 1
2011-06-28T13:15:59.000000-07:00 host1 psiphonv: discovery 192.168.1.101 CA DA77176D642E66FB 1F277F0BD58BB84D 1 192.168.1.102 0
2011-06-28T13:16:00.000000-07:00 host1 psiphonv: download 192.168.1.101 CA DA77176D642E66FB 1F277F0BD58BB84D 2
2011-06-28T13:16:06.000000-07:00 host1 psiphonv: connected 192.168.1.101 CA DA77176D642E66FB 1F277F0BD58BB84D 2 10.1.0.2
2011-06-28T13:16:12.000000-07:00 host1 psiphonv: disconnected 10.1.0.2
'''

# Log line parser looks for space delimited fields. Every log line has a
# timestamp, host ID, and event type. The schema array defines the additional
# fields expected for each valid event type.

LOG_LINE_PATTERN = '([\dT\.:\+-]+) ([\w\(\)-]+) psiphonv: (\w+) (.+)'

LOG_ENTRY_COMMON_FIELDS = ('timestamp', 'host_id')

LOG_EVENT_TYPE_SCHEMA = {
    'started' :             ('server_id',),
    'handshake.7' :         ('server_id',
                             'client_region',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol'),
    'handshake.9' :         ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol'),
    'handshake' :           ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'tunnel_whole_device'),
    'discovery.9' :         ('server_id',
                             'client_region',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'discovery_server_id',
                             'client_unknown'),
    'discovery.11' :        ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'discovery_server_id',
                             'client_unknown'),
    'discovery' :           ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'tunnel_whole_device',
                             'discovery_server_id',
                             'client_unknown'),
    'connected.8' :         ('server_id',
                             'client_region',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'session_id'),
    'connected.11' :        ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'session_id',
                             'last_connected'),
    'connected' :           ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'tunnel_whole_device',
                             'session_id',
                             'last_connected'),
    'failed.8' :            ('server_id',
                             'client_region',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'error_code'),
    'failed.10' :           ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'error_code'),
    'failed' :              ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'tunnel_whole_device',
                             'error_code'),
    'download.6' :          ('server_id',
                             'client_region',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform'),
    'download.8' :          ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform'),
    'download' :            ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'tunnel_whole_device'),
    'disconnected' :        ('relay_protocol',
                             'session_id'),
    'status' :              ('relay_protocol',
                             'session_id'),
    'bytes_transferred.8' : ('server_id',
                             'client_region',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'bytes'),
    'bytes_transferred.12' :('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'session_id',
                             'connected',
                             'bytes'),
    'bytes_transferred' :   ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'tunnel_whole_device',
                             'session_id',
                             'connected',
                             'bytes'),
    'page_views.9' :        ('server_id',
                             'client_region',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'pagename',
                             'viewcount'),
    'page_views.13' :       ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'session_id',
                             'connected',
                             'pagename',
                             'viewcount'),
    'page_views' :          ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'tunnel_whole_device',
                             'session_id',
                             'connected',
                             'pagename',
                             'viewcount'),
    'https_requests.9' :    ('server_id',
                             'client_region',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'domain',
                             'count'),
    'https_requests.13' :   ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'session_id',
                             'connected',
                             'domain',
                             'count'),
    'https_requests' :      ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'tunnel_whole_device',
                             'session_id',
                             'connected',
                             'domain',
                             'count'),
    'speed.11' :            ('server_id',
                             'client_region',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'operation',
                             'info',
                             'milliseconds',
                             'size'),
    'speed.13' :            ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'operation',
                             'info',
                             'milliseconds',
                             'size'),
    'speed' :               ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'tunnel_whole_device',
                             'operation',
                             'info',
                             'milliseconds',
                             'size'),
    'feedback.12' :         ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'session_id',
                             'question',
                             'answer'),
    'feedback' :            ('server_id',
                             'client_region',
                             'client_city',
                             'client_isp',
                             'propagation_channel_id',
                             'sponsor_id',
                             'client_version',
                             'client_platform',
                             'relay_protocol',
                             'tunnel_whole_device',
                             'session_id',
                             'question',
                             'answer'),
    }


def iso8601_to_utc(timestamp):
    localized_datetime = datetime.datetime.strptime(timestamp[:26], '%Y-%m-%dT%H:%M:%S.%f')
    # NOTE: strptime slow! Consider replacing with robust version of following.
    #year = int(timestamp[0:4])
    #month = int(timestamp[5:7])
    #day = int(timestamp[8:10])
    #hour = int(timestamp[11:13])
    #minute = int(timestamp[14:16])
    #second = int(timestamp[17:19])
    #microsecond = int(timestamp[20:26])
    localized_datetime = datetime.datetime(year, month, day, hour, minute, second, microsecond)
    timezone_delta = datetime.timedelta(
                                hours = int(timestamp[-6:-3]),
                                minutes = int(timestamp[-2:]))
    return (localized_datetime - timezone_delta).strftime('%Y-%m-%dT%H:%M:%S.%fZ')

def fix_timestamp(timestamp):
    try:
        iso8601.parse_date(timestamp.strip())
    except:
        try:
            timestamp = iso8601.parse_date(timestamp.strip()[:10]).isoformat()
        except:
            pass
    return timestamp

def process_stats(host, servers, db_cur, psinet, minimal, error_file=None):

    print 'process stats from host %s...' % (host.id,)

    server_ip_address_to_id = {}
    for server in servers:
        server_ip_address_to_id[server.internal_ip_address] = server.id

    line_re = re.compile(LOG_LINE_PATTERN)

    # Download each log file from the host, parse each line and insert
    # log entries into database.

    directory = os.path.join(LOCAL_LOG_ROOT, host.id)
    if not os.path.exists(directory):
        return

    # Only process logs lines after last timestamp processed. This gives a
    # significant performance boost.

    db_cur[None].execute(
        'select last_timestamp from processed_logs where host_id = %s',
        [host.id])
    last_timestamp = db_cur[None].fetchone()
    if last_timestamp:
        last_timestamp = last_timestamp[0]
    next_last_timestamp = None

    # Prepare some loop invariant formatted strings. Gives a significant
    # performance boots vs. formatting per log line.

    event_columns = {}
    event_sql = {}

    for event_type, event_fields in LOG_EVENT_TYPE_SCHEMA.iteritems():
        event_columns[event_type] = LOG_ENTRY_COMMON_FIELDS + event_fields
        assert(event_fields[0] == 'server_id' or 'server_id' not in event_fields)
        assert(len(LOG_ENTRY_COMMON_FIELDS) == 2)
        table_name = event_type
        if event_type.find('.') != -1:
            table_name = event_type.split('.')[0]
        command = 'insert into %s (%s) select %s where not exists (select 1 from %s where %s)' % (
                        table_name,
                        ', '.join(event_columns[event_type]),
                        ', '.join(['%s']*len(event_columns[event_type])),
                        table_name,
                        ' and '.join(['%s = %%s' % x for x in event_columns[event_type]]))
        event_sql[event_type] = command

        # Add special case statement to use when last_connected is NULL
        if 'last_connected' in event_columns[event_type]:
            command = 'insert into %s (%s) select %s where not exists (select 1 from %s where %s)' % (
                            table_name,
                            ', '.join(event_columns[event_type]),
                            ', '.join(['%s']*len(event_columns[event_type])),
                            table_name,
                            ' and '.join([('%s is %%s' % x) if x == 'last_connected' else ('%s = %%s' % x)
                                        for x in event_columns[event_type]]))
            event_sql[event_type + '.last_connected_NULL'] = command

    # Don't record entries for testing or deployment-validation logs.
    # Manual and automated testing are typically done with a propagation channel
    # name of 'Testing' (which we're going to look up in psinet to get the ID).
    # All logs that use this propagation channel will be discarded to prevent
    # stats confusion.
    excluded_propagation_channel_ids = []
    if TESTING_PROPAGATION_CHANNEL_NAME:
        excluded_propagation_channel_ids += [psinet.get_propagation_channel_by_name(TESTING_PROPAGATION_CHANNEL_NAME).id]

    for filename in os.listdir(directory):
        if re.match(HOST_LOG_FILENAME_PATTERN, filename):
            path = os.path.join(directory, filename)
            if filename.endswith('.gz'):
                # Older log file archives are in gzip format
                file = gzip.open(path)
            else:
                file = open(path)
            print 'processing %s...' % (filename,)
            lines_processed = 0
            try:
                lines = file.read().split('\n')
                for line in reversed(lines):
                    match = line_re.match(line)
                    if (not match or
                        not LOG_EVENT_TYPE_SCHEMA.has_key(match.group(3))):
                        err = 'unexpected log line pattern: %s' % (line,)
                        if error_file:
                            error_file.write(err + '\n')
                        continue

                    # Note: We convert timestamps here to UTC so that they can all be rationally compared without
                    #       taking the timezone into consideration. This eases matching of outbound statistics
                    #       (and any other records that may not have consistent timezone info) to sessions.
                    # Update: no longer calling iso8601_to_utc(timestamp) as database can perform translation

                    timestamp = match.group(1)

                    # If we cannot parse the matched string as an ISO8601 timestamp, zero out the time and
                    # try to produce a valid timestamp. If this fails too, don't change the matched timestamp
                    timestamp = fix_timestamp(timestamp)

                    # Last timestamp check
                    # Note: - assuming lexicographical order (ISO8601)
                    #       - currently broken for 1 hour DST window or backwards moving server clock
                    #       - Strict < check to not skip new logs in same time... but this will
                    #         also guarantee reprocessing of the last line for each host

                    if last_timestamp and timestamp < last_timestamp:
                        # Assumes processing the lines in reverse chronological order
                        break

                    host_id = host.id
                    event_type = match.group(3)

                    if minimal:
                        if event_type not in ['connected', 'page_views']:
                            continue

                    if not next_last_timestamp or timestamp > next_last_timestamp:
                        next_last_timestamp = timestamp

                    event_values = [event_value.decode('utf-8', 'replace') for event_value in match.group(4).split()]
                    event_fields = LOG_EVENT_TYPE_SCHEMA[event_type]

                    if len(event_values) != len(event_fields):
                        # Backwards compatibility case
                        event_type = '%s.%d' % (event_type, len(event_values))
                        if event_type not in LOG_EVENT_TYPE_SCHEMA:
                            err = 'invalid log line fields %s' % (line,)
                            if error_file:
                                error_file.write(err + '\n')
                            continue
                        event_fields = LOG_EVENT_TYPE_SCHEMA[event_type]

                    if len(event_values) != len(event_fields):
                        err = 'invalid log line fields %s' % (line,)
                        if error_file:
                            error_file.write(err + '\n')
                        continue

                    field_names = event_columns[event_type]

                    field_values = [timestamp, host_id] + event_values
                    assert(len(field_names) == len(field_values))

                    # Check for invalid bytes value for bytes_transferred

                    if event_type == 'bytes_transferred.8':
                        assert(field_names[9] == 'bytes')
                        # Client version 24 had a bug which resulted in
                        # corrupt byte transferred values, so discard them
                        assert(field_names[6] == 'client_version')
                        if int(field_values[6]) == 24:
                            continue

                    invalid_byte_field = False
                    for index, field_name in enumerate(field_names):
                        if field_name == 'bytes':
                            # This is an integer field
                            if not (0 <= int(field_values[index]) < 2147483647):
                                err = 'invalid byte fields %s' % (line,)
                                print err
                                if error_file:
                                    error_file.write(err + '\n')
                                invalid_byte_field = True
                                break
                    if invalid_byte_field:
                        continue

                    # Don't record entries for testing or deployment-validation logs
                    try:
                        if field_values[field_names.index('propagation_channel_id')] in excluded_propagation_channel_ids:
                            continue
                    except:
                        # propagation_channel_id is not present
                        pass

                    # Replace server IP addresses with server IDs in
                    # stats to keep IP addresses confidental in reporting.

                    for index, field_name in enumerate(field_names):
                        if field_name == 'server_id' or field_name == 'discovery_server_id':
                            field_values[index] = server_ip_address_to_id.get(field_values[index], 'Unknown')

                    # Fixup for last_connected: this field (in the log) contains either a timestamp,
                    # 'None' (meaning a first time connection), or 'Unknown' (meaning an old client that
                    # doesn't send this info connected)
                    if event_type.find('connected') == 0:
                        for index, field_name in enumerate(field_names):
                            if field_name == 'last_connected':
                                if field_values[index] == 'Unknown':
                                    # Use alternate SQL that works with NULL values
                                    event_type += '.last_connected_NULL'
                                    field_values[index] = None
                                elif field_values[index] == 'None':
                                    field_values[index] = '1900-01-01T00:00:00Z'
                                else:
                                    field_values[index] = fix_timestamp(field_values[index])

                    # SQL injection note: the table name isn't parameterized
                    # and comes from log file data, but it's implicitly
                    # validated by hash table lookups

                    command = event_sql[event_type]

                    try:
                        table = event_type
                        if table.find('.') != -1:
                            table = table.split('.')[0]
                        if table in db_cur:
                            cursor = db_cur[table]
                        else:
                            cursor = db_cur[None]
                        cursor.execute(command, field_values + field_values)
                    except psycopg2.DataError as data_error:
                        print host.id + ': ' + filename + ': ' + str(data_error)

                    lines_processed += 1

            finally:
                file.close()

            print '%d new lines processed' % (lines_processed)
            sys.stdout.flush()

    if next_last_timestamp:
        if not last_timestamp:
            db_cur[None].execute(
                'insert into processed_logs (host_id, last_timestamp) values (%s, %s)',
                [host.id, next_last_timestamp])
        else:
            db_cur[None].execute(
                'update processed_logs set last_timestamp = %s where host_id = %s',
                [next_last_timestamp, host.id])


def reconstruct_sessions(db):
    # Populate the session table. For each connection, create a session. Some
    # connections will have no end time, depending on when the logs are pulled.
    # Find the end time by selecting the 'disconnected' or 'status' event with
    # the same host_id and session_id soonest after the connected timestamp.

    session_cursor = db.cursor()

    print 'Reconstructing sessions...'
    sys.stdout.flush()
    start_time = time.time()

    session_cursor.execute('SELECT doSessionReconstruction()')

    session_cursor.execute('COMMIT')

    print 'Reconstruct sessions elapsed time: %fs' % (time.time()-start_time,)


def update_propagation_channels(db, propagation_channels):

    cursor = db.cursor()

    for channel in propagation_channels:
        cursor.execute('UPDATE propagation_channel SET name = %s WHERE id = %s',
                       [channel.name, channel.id])
        cursor.execute('INSERT INTO propagation_channel (id, name) SELECT %s, %s ' +
                       'WHERE NOT EXISTS (SELECT 1 FROM propagation_channel WHERE id = %s AND name = %s)',
                       [channel.id, channel.name, channel.id, channel.name])

    cursor.execute('COMMIT')


def update_sponsors(db, sponsors):

    cursor = db.cursor()

    for sponsor in sponsors:
        cursor.execute('UPDATE sponsor SET name = %s WHERE id = %s',
                       [sponsor.name, sponsor.id])
        cursor.execute('INSERT INTO sponsor (id, name) SELECT %s, %s ' +
                       'WHERE NOT EXISTS (SELECT 1 FROM sponsor WHERE id = %s AND name = %s)',
                       [sponsor.id, sponsor.name, sponsor.id, sponsor.name])

    cursor.execute('COMMIT')


def update_servers(db, psinet):

    cursor = db.cursor()

    for server in psinet.get_servers():
        host = psinet.get_host_for_server(server)
        server_type = 'Propagation'
        if server.discovery_date_range:
            server_type = 'Discovery'
        else:
            if server.is_embedded:
                server_type = 'Embedded'
            if server.is_permanent:
                server_type = 'Permanent'
        cursor.execute('UPDATE server SET type = %s, datacenter_name = %s WHERE id = %s',
                       [server_type, host.datacenter_name, server.id])
        cursor.execute('INSERT INTO server (id, type, datacenter_name) SELECT %s, %s, %s ' +
                       'WHERE NOT EXISTS (SELECT 1 FROM server WHERE id = %s AND type = %s AND datacenter_name = %s)',
                       [server.id, server_type, host.datacenter_name,
                        server.id, server_type, host.datacenter_name])

    cursor.execute('COMMIT')


def process_stats_on_host(args):

    start_time = time.time()

    host = args[0]
    servers = args[1]
    psinet = args[2]
    minimal = args[3]

    db_conn = build_db_connections()
    cursors = {}

    try:
        for table, conn in db_conn.iteritems():
            cursors[table] = conn.cursor()
        process_stats(host, servers, cursors, psinet, minimal)
        for cursor in cursors.itervalues():
            cursor.close()
        for connection in db_conn.itervalues():
            connection.commit()
    except Exception as e:
        for line in traceback.format_exc().split('\n'):
            print line
    finally:
        for connection in db_conn.itervalues():
            connection.close()

    return (host.id, time.time()-start_time)


def build_db_connections():
    db_conn = {}
    if hasattr(psi_ops_stats_credentials,'DB_MAP'):
        for table,db_ipaddress in psi_ops_stats_credentials.DB_MAP.iteritems():
            db_conn[table] = psycopg2.connect(
                'dbname=%s user=%s password=%s port=%d host=%s' % (
                    psi_ops_stats_credentials.POSTGRES_DBNAME,
                    psi_ops_stats_credentials.POSTGRES_USER,
                    psi_ops_stats_credentials.POSTGRES_PASSWORD,
                    psi_ops_stats_credentials.POSTGRES_PORT,
                    db_ipaddress))
    else:
        db_conn[None] = psycopg2.connect(
            'dbname=%s user=%s password=%s port=%d' % (
                psi_ops_stats_credentials.POSTGRES_DBNAME,
                psi_ops_stats_credentials.POSTGRES_USER,
                psi_ops_stats_credentials.POSTGRES_PASSWORD,
                psi_ops_stats_credentials.POSTGRES_PORT))
    return db_conn


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--minimal', dest='minimal', action='store_true',
                        help='minimal processing')
    args = parser.parse_args()

    start_time = time.time()

    psinet = psi_ops.PsiphonNetwork.load_from_file(PSI_OPS_DB_FILENAME)

    db_conn = build_db_connections()
    print db_conn

    hosts = psinet.get_hosts()
    servers = psinet.get_servers()
    propagation_channels = psinet.get_propagation_channels()
    sponsors = psinet.get_sponsors()

    try:
        update_propagation_channels(db_conn[None], propagation_channels)
        update_sponsors(db_conn[None], sponsors)
        update_servers(db_conn[None], psinet)

        pool = multiprocessing.pool.ThreadPool(4)
        results = pool.map(process_stats_on_host, [(host, servers, psinet, args.minimal) for host in hosts])

        # print results as a dict (sorted for visual inspection)
        print '{' + ','.join(['"%s": %f' % (host_id, host_time) for (host_id, host_time)
                in sorted(results, key=lambda item: item[1], reverse=True)]) + '}'

        if not args.minimal:
            reconstruct_sessions(db_conn[None])

        for connection in db_conn.itervalues():
            connection.commit()
    except Exception as e:
        for line in traceback.format_exc().split('\n'):
            print line
    finally:
        for connection in db_conn.itervalues():
            connection.close()

    print 'Total stats processing elapsed time: %fs' % (time.time()-start_time,)
