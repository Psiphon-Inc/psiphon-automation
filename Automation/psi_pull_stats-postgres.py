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
import posixpath
import sys
import tempfile
import re
import textwrap
import gzip
import traceback
import csv
import datetime
import collections
import bisect
import base64
import hashlib
import socket
import time
import subprocess
import shlex

import psycopg2

import psi_ssh
import psi_ops
import psi_ops_stats_credentials


#==== Syslog File Configuration  ===============================================

HOST_LOG_DIR = '/var/log'
HOST_LOG_FILENAME_PATTERN = 'psiphonv.log*'


#==== psi_ops DB Configuration  =================================================

PSI_OPS_ROOT = os.path.abspath(os.path.join('.'))
PSI_OPS_DB_FILENAME = os.path.join(PSI_OPS_ROOT, 'psi_ops.dat')


#==============================================================================

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

LOG_LINE_PATTERN = '([\dT\.:\+-]+) ([\w-]+) psiphonv: (\w+) (.+)'

LOG_ENTRY_COMMON_FIELDS = ('timestamp', 'host_id')

LOG_EVENT_TYPE_SCHEMA = {
    'started' :         ('server_id',),
    'handshake' :       ('server_id',
                         'client_region',
                         'propagation_channel_id',
                         'sponsor_id',
                         'client_version'),
    'discovery' :       ('server_id',
                         'client_region',
                         'propagation_channel_id',
                         'sponsor_id',
                         'client_version',
                         'discovery_server_id',
                         'client_unknown'),
    'connected' :       ('server_id',
                         'client_region',
                         'propagation_channel_id',
                         'sponsor_id',
                         'client_version',
                         'relay_protocol',
                         'session_id'),
    'failed' :          ('server_id',
                         'client_region',
                         'propagation_channel_id',
                         'sponsor_id',
                         'client_version',
                         'relay_protocol',
                         'error_code'),
    'download' :        ('server_id',
                         'client_region',
                         'propagation_channel_id',
                         'sponsor_id',
                         'client_version'),
    'disconnected' :    ('relay_protocol',
                         'session_id'),
    'status' :          ('relay_protocol',
                         'session_id')}

# Additional stat tables that don't correspond to log line entries. Currently
# this is the session table, which is populated in post-processing that links
# connected and disconnected events.

ADDITIONAL_TABLES_SCHEMA = {
    'session' :         ('host_id',
                         'server_id',
                         'client_region',
                         'propagation_channel_id',
                         'sponsor_id',
                         'client_version',
                         'relay_protocol',
                         'session_id',
                         'session_start_timestamp',
                         'session_end_timestamp'),
    'outbound' :        ('host_id',
                         'server_id',
                         'client_region',
                         'propagation_channel_id',
                         'sponsor_id',
                         'client_version',
                         'relay_protocol',
                         'session_id',
                         'day',
                         'domain',
                         'protocol',
                         'port',
                         'flow_count',
                         'outbound_byte_count')}


def iso8601_to_utc(timestamp):
    localized_datetime = datetime.datetime.strptime(timestamp[:26], '%Y-%m-%dT%H:%M:%S.%f')
    timezone_delta = datetime.timedelta(
                                hours = int(timestamp[-6:-3]),
                                minutes = int(timestamp[-2:]))
    return (localized_datetime - timezone_delta).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def pull_stats(db_cur, error_file, host, servers):

    print 'pull stats from host %s...' % (host.id,)

    server_ip_address_to_id = {}
    for server in servers:
        server_ip_address_to_id[server.ip_address] = server.id

    line_re = re.compile(LOG_LINE_PATTERN)

    ssh = psi_ssh.SSH(
            host.ip_address, host.ssh_port,
            host.stats_ssh_username, host.stats_ssh_password,
            host.ssh_host_key)

    # Download each log file from the host, parse each line and insert
    # log entries into database.

    dirlist = ssh.list_dir(HOST_LOG_DIR)
    for filename in dirlist:
        if re.match(HOST_LOG_FILENAME_PATTERN, filename):
            if filename.endswith('.gz'):
                # NOTE: skipping older files -- using frequent run loop
                continue
            print 'fetching %s...' % (filename,)
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file.close()
            try:
                file = None
                ssh.get_file(
                    posixpath.join(HOST_LOG_DIR, filename), temp_file.name)
                if filename.endswith('.gz'):
                    # Older log file archives are in gzip format
                    file = gzip.open(temp_file.name)
                else:
                    file = open(temp_file.name)
                print 'processing %s...' % (filename,)
                for line in file.read().split('\n'):
                    match = line_re.match(line)
                    if (not match or
                        not LOG_EVENT_TYPE_SCHEMA.has_key(match.group(3))):
                        err = 'unexpected log line pattern: %s' % (line,)
                        error_file.write(err + '\n')
                        continue
                    # Note: We convert timestamps here to UTC so that they can all be rationally compared without
                    #       taking the timezone into consideration. This eases matching of outbound statistics
                    #       (and any other records that may not have consistent timezone info) to sessions.
                    timestamp = iso8601_to_utc(match.group(1))
                    host_id = match.group(2)
                    event_type = match.group(3)
                    event_values = match.group(4).split()
                    event_fields = LOG_EVENT_TYPE_SCHEMA[event_type]
                    if len(event_values) != len(event_fields):
                        err = 'invalid log line fields %s' % (line,)
                        error_file.write(err + '\n')
                        continue
                    field_names = LOG_ENTRY_COMMON_FIELDS + event_fields
                    field_values = [timestamp, host_id] + event_values
                    # Replace server IP addresses with server IDs in
                    # stats to keep IP addresses confidental in reporting.
                    assert(len(field_names) == len(field_values))
                    for index, name in enumerate(field_names):
                        if name.find('server_id') != -1:
                            field_values[index] = server_ip_address_to_id[
                                                    field_values[index]]
                    # SQL injection note: the table name isn't parameterized
                    # and comes from log file data, but it's implicitly
                    # validated by hash table lookups
                    command = 'insert into %s (%s) select %s where not exists (select 1 from %s where %s)' % (
                                    event_type,
                                    ', '.join(field_names),
                                    ', '.join(['%s']*len(field_values)),
                                    event_type,
                                    ' and '.join(['%s = %%s' % x for x in field_names]))

                    db_cur.execute(command, field_values + field_values)
            finally:
                # Always delete temporary downloaded log file
                if file:
                    file.close()
                os.remove(temp_file.name)
    ssh.close()


'''
PostgreSQL additional columns, constraints, and indexes for reconstruct_sessions

ALTER TABLE connected ADD COLUMN id bigint;
ALTER TABLE connected ALTER COLUMN id SET NOT NULL;
ALTER TABLE connected ALTER COLUMN id SET DEFAULT nextval('connected_id_seq'::regclass);
ALTER TABLE "session" ADD COLUMN id bigint;
ALTER TABLE "session" ALTER COLUMN id SET NOT NULL;
ALTER TABLE "session" ALTER COLUMN id SET DEFAULT nextval('session_id_seq'::regclass);
ALTER TABLE "session" ADD COLUMN connected_id bigint;
ALTER TABLE "session" ALTER COLUMN connected_id SET NOT NULL;
ALTER TABLE "session" ADD CONSTRAINT connected_id FOREIGN KEY (connected_id) REFERENCES connected (id)
   ON UPDATE NO ACTION ON DELETE NO ACTION;
CREATE INDEX fki_connected_id ON "session"(connected_id);
CREATE INDEX session_reconstruction
  ON disconnected
  USING btree
  ("timestamp", host_id, relay_protocol, session_id);
'''
    
def reconstruct_sessions(db):
    # Populate the session table. For each connection, create a session. Some
    # connections will have no end time, depending on when the logs are pulled.
    # Find the end time by selecting the 'disconnected' event with the same
    # host_id and session_id soonest after the connected timestamp.

    session_cursor = db.cursor()    
    
    # There may be existing sessions that started before start_date that don't have an end
    # time.  We first iterate through each of those and try to find a new 'disconnected'
    # event for each, updating each when we find an end time.

    start_time = time.time()
    
    print 'Reconstructing previously incomplete sessions...'

    # Note: I tried adding an index on session((session_end_timestamp IS NULL)),
    # and the query planner showed that it was being used instead of a Seq Scan,
    # but it didn't speed up the operation at all.
    session_cursor.execute(textwrap.dedent('''
        UPDATE session
        SET session_end_timestamp =
            (SELECT disconnected.timestamp FROM disconnected
             WHERE disconnected.timestamp > session.session_start_timestamp
                AND disconnected.host_id = session.host_id
                AND disconnected.relay_protocol = session.relay_protocol
                AND disconnected.session_id = session.session_id
             ORDER BY disconnected.timestamp ASC LIMIT 1)
        WHERE session_end_timestamp IS NULL
        '''))
    initial_incomplete_session_count = session_cursor.rowcount

    session_cursor.execute('SELECT COUNT(*) FROM session WHERE session_end_timestamp IS NULL')
    final_incomplete_session_count = session_cursor.fetchone()[0]

    session_cursor.execute('COMMIT')

    sessions_completed = initial_incomplete_session_count - final_incomplete_session_count
    total_time = time.time() - start_time

    if sessions_completed > 0:
        # Note that this output isn't stricly true. The total number of rows updated
        # is equal to the total IS-NULL count at the start, but some of those
        # updates are from NULL to NULL. Instead of the truth, our output here
        # will describe how many records were actually changed.
        print 'Updated %d session records (%d still incomplete); total time: %fs; avg. time: %fs' \
            % (sessions_completed,
               final_incomplete_session_count,
               total_time,
               total_time/sessions_completed)
    else:
        print 'No session rows updated (%d still incomplete); time: %fs' % (final_incomplete_session_count, total_time)

    #
    # Reconstruct and insert all sessions.
    # We do this in a single SQL statement, which we have found to perform much
    # better than looping through results.
    # Here is the explain-analyze output, in case it's useful in the future:
    #~ Insert on session  (cost=350.22..178171102.21 rows=253176 width=102) (actual time=170023.948..170023.948 rows=0 loops=1)
    #~ ->  Nested Loop Left Join  (cost=350.22..178171102.21 rows=253176 width=102) (actual time=7.710..73784.441 rows=256209 loops=1)
         #~ ->  Merge Anti Join  (cost=0.00..71595.67 rows=253176 width=94) (actual time=0.203..33355.666 rows=256209 loops=1)
               #~ Merge Cond: (connected.id = public.session.connected_id)
               #~ ->  Index Scan using connected_pkey on connected  (cost=0.00..54151.52 rows=253295 width=94) (actual time=0.189..32486.386 rows=256209 loops=1)
                     #~ Filter: (relay_protocol <> 'SSH'::text)
               #~ ->  Index Scan using fki_connected_id on session  (cost=0.00..17077.97 rows=570 width=8) (actual time=0.007..0.007 rows=0 loops=1)
         #~ ->  Index Scan using session_reconstruction on disconnected  (cost=350.22..353.22 rows=1 width=29) (actual time=0.013..0.015 rows=1 loops=256209)
               #~ Index Cond: (("timestamp" = (SubPlan 2)) AND (connected.host_id = host_id) AND (connected.relay_protocol = relay_protocol) AND (connected.session_id = session_id))
               #~ SubPlan 2
                 #~ ->  Result  (cost=350.21..350.22 rows=1 width=0) (actual time=0.120..0.122 rows=1 loops=256209)
                       #~ InitPlan 1 (returns $4)
                         #~ ->  Limit  (cost=0.00..350.21 rows=1 width=8) (actual time=0.114..0.115 rows=1 loops=256209)
                               #~ ->  Index Scan using session_reconstruction on disconnected d  (cost=0.00..4902.89 rows=14 width=8) (actual time=0.109..0.109 rows=1 loops=256209)
                                     #~ Index Cond: (("timestamp" IS NOT NULL) AND ("timestamp" > connected."timestamp") AND (host_id = connected.host_id) AND (relay_protocol = connected.relay_protocol) AND (session_id = connected.session_id))
               #~ SubPlan 2
                 #~ ->  Result  (cost=350.21..350.22 rows=1 width=0) (actual time=0.120..0.122 rows=1 loops=256209)
                       #~ InitPlan 1 (returns $4)
                         #~ ->  Limit  (cost=0.00..350.21 rows=1 width=8) (actual time=0.114..0.115 rows=1 loops=256209)
                               #~ ->  Index Scan using session_reconstruction on disconnected d  (cost=0.00..4902.89 rows=14 width=8) (actual time=0.109..0.109 rows=1 loops=256209)
                                     #~ Index Cond: (("timestamp" IS NOT NULL) AND ("timestamp" > connected."timestamp") AND (host_id = connected.host_id) AND (relay_protocol = connected.relay_protocol) AND (session_id = connected.session_id))
    #~ Trigger for constraint connected_id: time=90772.022 calls=256209
    #~ Total runtime: 261575.361 ms

    print "Reconstructing new sessions..."
    start_time = time.time()
    
	# Note: only using this session reconstruction logic for VPN protocol at this time;
	#       SSH and OSSH durations are implemented using views (see psi_pull_stats-postgres-schema.sql)
	
    session_cursor.execute(textwrap.dedent('''
        INSERT INTO session (host_id, server_id, client_region, propagation_channel_id,
                             sponsor_id, client_version, relay_protocol, session_id,
                             session_start_timestamp, session_end_timestamp, connected_id)
            SELECT connected.host_id, connected.server_id, connected.client_region,
                connected.propagation_channel_id, connected.sponsor_id, connected.client_version,
                connected.relay_protocol, connected.session_id, connected.timestamp,
                disconnected.timestamp, connected.id
            FROM
                connected
            LEFT OUTER JOIN
                disconnected
            ON
                -- Get the disconnect time that matches the connection
                disconnected.timestamp =
                    (SELECT d.timestamp FROM disconnected AS d
                     WHERE d.timestamp > connected.timestamp
                        AND d.host_id = connected.host_id
                        AND d.relay_protocol = connected.relay_protocol
                        AND d.session_id = connected.session_id
                     ORDER BY d.timestamp ASC LIMIT 1)
                AND connected.host_id = disconnected.host_id
                AND connected.relay_protocol = disconnected.relay_protocol
                AND connected.session_id = disconnected.session_id
            WHERE connected.relay_protocol = 'VPN'
            AND NOT EXISTS (SELECT * FROM session WHERE connected_id = connected.id)
        '''))

    rowcount = session_cursor.rowcount

    session_cursor.execute('COMMIT')

    total_time = time.time() - start_time

    if rowcount > 0:
        print 'Inserted %d session records; total time: %fs; avg. time: %fs' % (rowcount, total_time, total_time/rowcount)
    else:
        print 'No session rows inserted; total time: %fs' % total_time

        
def sync_psi_ops():
    # Try to get latest psi_ops data file
    try:
        cmd = 'CipherShareScriptingClient.exe \
                ExportDocument \
                -UserName %s -Password %s \
                -OfficeName %s -DatabasePath "%s" -ServerHost %s -ServerPort %s \
                -SourceDocument "%s" \
                -TargetFile "%s"' \
             % (psi_ops_stats_credentials.CIPHERSHARE_USERNAME,
                psi_ops_stats_credentials.CIPHERSHARE_PASSWORD,
                psi_ops_stats_credentials.CIPHERSHARE_OFFICENAME,
                psi_ops_stats_credentials.CIPHERSHARE_DATABASEPATH,
                psi_ops_stats_credentials.CIPHERSHARE_SERVERHOST,
                psi_ops_stats_credentials.CIPHERSHARE_SERVERPORT,
                psi_ops_stats_credentials.CIPHERSHARE_PSI_OPS_STATS_DOCUMENT_PATH,
                PSI_OPS_DB_FILENAME)
        
        proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = proc.communicate()
        
        if proc.returncode != 0:
            raise Exception('CipherShare export failed: ' + str(output))
    except Exception as e:
        print str(e)


if __name__ == "__main__":

    sync_psi_ops()

    psinet = psi_ops.PsiphonNetwork.load_from_file(PSI_OPS_DB_FILENAME, lock_file=True)

    db_conn = psycopg2.connect(
        'dbname=%s user=%s password=%s' % (
            psi_ops_stats_credentials.POSTGRES_DBNAME,
            psi_ops_stats_credentials.POSTGRES_USER,
            psi_ops_stats_credentials.POSTGRES_PASSWORD))

    # Note: truncating error file
    error_file = open('pull_stats.err', 'w')

    hosts = psinet.get_hosts()
    servers = psinet.get_servers()

    try:
        for host in hosts:
            db_cur = db_conn.cursor()
            pull_stats(db_cur, error_file, host, servers)
            db_cur.close()
            db_conn.commit()
        reconstruct_sessions(db_conn)
        db_conn.commit()
    finally:
        error_file.close()
        db_conn.close()
